"""Technical preflight and immutable run snapshots for current M7 schemes."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime

from pydantic import JsonValue, ValidationError

from pilot_assessment.contracts.model_workspace import (
    ModelDiagnosticSeverity,
    ModelObjectLifecycle,
    ModelTechnicalStatus,
)
from pilot_assessment.contracts.run import (
    AssessmentRunV2,
    CurrentModelRunPreflightReport,
    CurrentModelRunSnapshot,
    RunDiagnostic,
    RunDiagnosticSeverity,
    RunPurpose,
    TechnicalDisposition,
)
from pilot_assessment.model_library.identity import typed_content_sha256
from pilot_assessment.model_workspace.execution import CurrentModelExecutionMaterializer
from pilot_assessment.model_workspace.service import CurrentModelWorkspaceService
from pilot_assessment.persistence.database import (
    Clock,
    ProjectDatabase,
    decode_canonical_json,
    encode_canonical_json,
)
from pilot_assessment.runtime.preflight import RunPreflightService
from pilot_assessment.runtime.repository import (
    RunNotFoundError,
    RunRepository,
    run_snapshot_hash,
)

ZERO_HASH = "0" * 64


class CurrentRunPreflightError(RuntimeError):
    """Base class for current-model preflight failures."""


class CurrentRunPreflightNotFoundError(CurrentRunPreflightError):
    """The requested current-model preflight is absent."""


class CurrentRunPreflightIntegrityError(CurrentRunPreflightError):
    """Persisted current-model preflight bytes disagree with their identity."""


class CurrentRunPreflightBlockedError(CurrentRunPreflightError):
    """A blocked current-model preflight cannot freeze a run."""


class CurrentRunPreflightStaleError(CurrentRunPreflightError):
    """The autosaved scheme or a locked node changed after preflight."""


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CurrentRunPreflightError("current preflight timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def current_preflight_hash(report: CurrentModelRunPreflightReport) -> str:
    payload = report.model_dump(mode="json")
    payload.pop("preflight_id")
    payload.pop("preflight_hash")
    return typed_content_sha256(
        report.contract_id,
        report.contract_version,
        payload,
    )


def current_preflight_id_from_hash(digest: str) -> str:
    return f"current-preflight.{digest[:32]}"


def _ordered_diagnostics(values: list[RunDiagnostic]) -> tuple[RunDiagnostic, ...]:
    unique: dict[tuple[str, str, str, str], RunDiagnostic] = {}
    for item in values:
        key = (item.location, item.code, item.severity.value, item.message)
        unique.setdefault(key, item)
    return tuple(unique[key] for key in sorted(unique))


class CurrentRunPreflightService:
    """Bridge editable current objects to the unchanged trusted execution engine."""

    def __init__(
        self,
        database: ProjectDatabase,
        workspace: CurrentModelWorkspaceService,
        materializer: CurrentModelExecutionMaterializer,
        legacy: RunPreflightService,
        runs: RunRepository,
        *,
        clock: Clock,
    ) -> None:
        self.database = database
        self.workspace = workspace
        self.materializer = materializer
        self.legacy = legacy
        self.runs = runs
        self.clock = clock

    def prepare(
        self,
        *,
        session_revision_id: str,
        scheme_id: str,
        purpose: RunPurpose,
        runtime_parameters: Mapping[str, JsonValue],
    ) -> CurrentModelRunPreflightReport:
        scheme = self.workspace.get_scheme(scheme_id)
        materialization = self.materializer.materialize(scheme_id)
        execution = self.legacy.prepare(
            session_revision_id=session_revision_id,
            scheme_version_id=materialization.legacy_scheme_ref.version_id,
            purpose=purpose,
            runtime_parameters=runtime_parameters,
        )
        diagnostics: list[RunDiagnostic] = list(execution.report.diagnostics)
        severity_map = {
            ModelDiagnosticSeverity.INFO: RunDiagnosticSeverity.INFO,
            ModelDiagnosticSeverity.WARNING: RunDiagnosticSeverity.WARNING,
            ModelDiagnosticSeverity.ERROR: RunDiagnosticSeverity.ERROR,
        }
        for item in scheme.diagnostics:
            diagnostics.append(
                RunDiagnostic(
                    code=item.code,
                    severity=severity_map[item.severity],
                    location=f"/current_scheme{item.location}",
                    message=item.message,
                    details=dict(item.details),
                )
            )
        if scheme.lifecycle is not ModelObjectLifecycle.ACTIVE:
            diagnostics.append(
                RunDiagnostic(
                    code="current.scheme_archived",
                    severity=RunDiagnosticSeverity.ERROR,
                    location="/current_scheme/lifecycle",
                    message="An archived current scheme cannot run.",
                    details={"scheme_id": scheme.scheme_id},
                )
            )
        if scheme.technical_status is not ModelTechnicalStatus.EXECUTABLE and not any(
            item.severity is RunDiagnosticSeverity.ERROR for item in diagnostics
        ):
            diagnostics.append(
                RunDiagnostic(
                    code="current.scheme_not_executable",
                    severity=RunDiagnosticSeverity.ERROR,
                    location="/current_scheme/technical_status",
                    message="The selected current scheme is technically incomplete or blocked.",
                    details={"technical_status": scheme.technical_status.value},
                )
            )

        ordered = _ordered_diagnostics(diagnostics)
        ready = (
            scheme.technical_status is ModelTechnicalStatus.EXECUTABLE
            and execution.report.technical_disposition is TechnicalDisposition.READY
            and not any(item.severity is RunDiagnosticSeverity.ERROR for item in ordered)
        )
        disposition = TechnicalDisposition.READY if ready else TechnicalDisposition.BLOCKED
        formal = ready and execution.report.formal_run_authorized
        embedded_execution = execution.report
        if embedded_execution.formal_run_authorized is not formal:
            embedded_execution = None
        provisional = CurrentModelRunPreflightReport(
            preflight_id="current-preflight.pending",
            session_revision_ref=execution.report.session_revision_ref,
            scheme_id=scheme.scheme_id,
            scheme_semantic_revision=scheme.semantic_revision,
            scheme_content_hash=scheme.content_hash,
            active_node_refs=materialization.active_node_refs,
            technical_disposition=disposition,
            formal_run_authorized=formal,
            synthetic_data=execution.report.synthetic_data,
            diagnostics=ordered,
            execution_preflight=embedded_execution,
            preflight_hash=ZERO_HASH,
        )
        digest = current_preflight_hash(provisional)
        report = provisional.model_copy(
            update={
                "preflight_id": current_preflight_id_from_hash(digest),
                "preflight_hash": digest,
            }
        )
        self._persist(
            report,
            legacy_preflight_id=execution.report.preflight_id,
            legacy_preflight_hash=execution.report.preflight_hash,
        )
        return report

    def get(self, preflight_id: str) -> CurrentModelRunPreflightReport:
        row = self.database.fetchone(
            "SELECT * FROM model_run_preflights_v2 WHERE current_preflight_id = ?",
            (preflight_id,),
        )
        if row is None:
            raise CurrentRunPreflightNotFoundError(preflight_id)
        return self._from_row(row)

    def build_snapshot(
        self,
        preflight_id: str,
        *,
        run_id: str,
        expected_scheme_revision: int,
    ) -> CurrentModelRunSnapshot:
        report = self.get(preflight_id)
        if report.technical_disposition is not TechnicalDisposition.READY:
            raise CurrentRunPreflightBlockedError(preflight_id)
        if expected_scheme_revision != report.scheme_semantic_revision:
            raise CurrentRunPreflightStaleError(
                "expected scheme revision differs from the prepared revision"
            )
        scheme = self.workspace.get_scheme(report.scheme_id)
        if (
            scheme.semantic_revision != report.scheme_semantic_revision
            or scheme.content_hash != report.scheme_content_hash
        ):
            raise CurrentRunPreflightStaleError("current scheme changed after preflight")
        nodes = {
            node.node_id: node
            for node in self.workspace.list_nodes(lifecycle=ModelObjectLifecycle.ACTIVE)
        }
        active_nodes = []
        for reference in report.active_node_refs:
            node = nodes.get(reference.node_id)
            if node is None or (
                node.node_kind is not reference.node_kind
                or node.semantic_revision != reference.semantic_revision
                or node.content_hash != reference.content_hash
            ):
                raise CurrentRunPreflightStaleError(
                    f"current node {reference.node_id!r} changed after preflight"
                )
            active_nodes.append(node)
        row = self.database.fetchone(
            "SELECT legacy_preflight_id FROM model_run_preflights_v2 "
            "WHERE current_preflight_id = ?",
            (preflight_id,),
        )
        if row is None:
            raise CurrentRunPreflightNotFoundError(preflight_id)
        execution = self.legacy.build_snapshot(row["legacy_preflight_id"], run_id=run_id)
        provisional = CurrentModelRunSnapshot(
            run_id=run_id,
            purpose=execution.purpose,
            session_revision_ref=execution.session_revision_ref,
            scheme=scheme,
            active_nodes=tuple(active_nodes),
            locked_operator_identities=execution.locked_operator_identities,
            engine_identity=execution.engine_identity,
            numeric_runtime_identities=execution.numeric_runtime_identities,
            runtime_parameters_hash=execution.runtime_parameters_hash,
            preflight_hash=report.preflight_hash,
            execution_snapshot=execution,
            snapshot_hash=ZERO_HASH,
        )
        return provisional.model_copy(update={"snapshot_hash": run_snapshot_hash(provisional)})

    def create_run(
        self,
        preflight_id: str,
        *,
        run_id: str,
        expected_scheme_revision: int,
        requested_at: datetime,
    ) -> AssessmentRunV2:
        try:
            existing = self.runs.get(run_id)
        except RunNotFoundError:
            pass
        else:
            report = self.get(preflight_id)
            if not isinstance(existing, AssessmentRunV2) or (
                existing.snapshot.preflight_hash != report.preflight_hash
                or existing.snapshot.scheme.semantic_revision != expected_scheme_revision
                or existing.requested_at != requested_at
            ):
                raise CurrentRunPreflightIntegrityError(
                    f"run {run_id!r} already owns a different immutable request"
                )
            return existing
        snapshot = self.build_snapshot(
            preflight_id,
            run_id=run_id,
            expected_scheme_revision=expected_scheme_revision,
        )
        return self.runs.create_current(
            snapshot,
            current_preflight_id=preflight_id,
            requested_at=requested_at,
        )

    def preview(
        self,
        *,
        session_revision_id: str,
        scheme_id: str,
        runtime_parameters: Mapping[str, JsonValue],
        preview_id: str,
    ) -> CurrentModelRunSnapshot:
        """Freeze a read-only ephemeral preview without creating a run record."""

        report = self.prepare(
            session_revision_id=session_revision_id,
            scheme_id=scheme_id,
            purpose=RunPurpose.PREVIEW,
            runtime_parameters=runtime_parameters,
        )
        return self.build_snapshot(
            report.preflight_id,
            run_id=preview_id,
            expected_scheme_revision=report.scheme_semantic_revision,
        )

    def preview_node(
        self,
        *,
        session_revision_id: str,
        scheme_id: str,
        node_id: str,
        runtime_parameters: Mapping[str, JsonValue],
        preview_id: str,
    ) -> CurrentModelRunSnapshot:
        """Freeze the containing scheme so a node editor can request its trace safely."""

        scheme = self.workspace.get_scheme(scheme_id)
        if node_id not in scheme.computed_active_closure:
            raise CurrentRunPreflightError(
                f"node {node_id!r} is not active in current scheme {scheme_id!r}"
            )
        return self.preview(
            session_revision_id=session_revision_id,
            scheme_id=scheme_id,
            runtime_parameters=runtime_parameters,
            preview_id=preview_id,
        )

    def _persist(
        self,
        report: CurrentModelRunPreflightReport,
        *,
        legacy_preflight_id: str,
        legacy_preflight_hash: str,
    ) -> None:
        payload = encode_canonical_json(report.model_dump(mode="json"))
        try:
            with self.database.transaction() as connection:
                existing = connection.execute(
                    """
                    SELECT * FROM model_run_preflights_v2
                    WHERE current_preflight_id = ? OR current_preflight_hash = ?
                    """,
                    (report.preflight_id, report.preflight_hash),
                ).fetchone()
                if existing is not None:
                    if self._from_row(existing) != report:
                        raise CurrentRunPreflightIntegrityError(
                            "current preflight identity collides with different content"
                        )
                    return
                connection.execute(
                    """
                    INSERT INTO model_run_preflights_v2(
                        current_preflight_id, current_preflight_hash,
                        scheme_id, scheme_semantic_revision, scheme_content_hash,
                        report_json, legacy_preflight_id, legacy_preflight_hash, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report.preflight_id,
                        report.preflight_hash,
                        report.scheme_id,
                        report.scheme_semantic_revision,
                        report.scheme_content_hash,
                        payload,
                        legacy_preflight_id,
                        legacy_preflight_hash,
                        _utc_text(self.clock()),
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise CurrentRunPreflightIntegrityError(
                "current preflight could not be persisted exactly"
            ) from error

    def _from_row(self, row) -> CurrentModelRunPreflightReport:
        try:
            report = CurrentModelRunPreflightReport.model_validate(
                decode_canonical_json(row["report_json"])
            )
        except (ValueError, ValidationError) as error:
            raise CurrentRunPreflightIntegrityError(
                "stored current preflight JSON is invalid"
            ) from error
        if (
            report.preflight_id != row["current_preflight_id"]
            or report.preflight_hash != row["current_preflight_hash"]
            or report.scheme_id != row["scheme_id"]
            or report.scheme_semantic_revision != int(row["scheme_semantic_revision"])
            or report.scheme_content_hash != row["scheme_content_hash"]
            or current_preflight_hash(report) != report.preflight_hash
        ):
            raise CurrentRunPreflightIntegrityError(
                "stored current preflight identity columns disagree"
            )
        execution = self.legacy.get(row["legacy_preflight_id"])
        if execution.report.preflight_hash != row["legacy_preflight_hash"]:
            raise CurrentRunPreflightIntegrityError(
                "stored current preflight legacy execution link changed"
            )
        if report.execution_preflight is not None and (
            report.execution_preflight != execution.report
        ):
            raise CurrentRunPreflightIntegrityError(
                "embedded execution preflight differs from the durable legacy link"
            )
        return report


__all__ = [
    "CurrentRunPreflightBlockedError",
    "CurrentRunPreflightError",
    "CurrentRunPreflightIntegrityError",
    "CurrentRunPreflightNotFoundError",
    "CurrentRunPreflightService",
    "CurrentRunPreflightStaleError",
    "current_preflight_hash",
    "current_preflight_id_from_hash",
]
