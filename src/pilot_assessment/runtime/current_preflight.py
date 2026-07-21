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
from pilot_assessment.contracts.project import (
    ArtifactIdRef,
    ArtifactOwnerKind,
    ArtifactReference,
)
from pilot_assessment.contracts.run import (
    AssessmentRunV3,
    CurrentModelRunPreflightReport,
    CurrentModelRunPreflightReportV2,
    CurrentModelRunSnapshot,
    CurrentModelRunSnapshotV2,
    CurrentModelRunSnapshotV3,
    RunDiagnostic,
    RunDiagnosticSeverity,
    RunPurpose,
    TechnicalDisposition,
)
from pilot_assessment.model_library.identity import typed_content_sha256
from pilot_assessment.model_workspace.execution import CurrentModelExecutionMaterializer
from pilot_assessment.model_workspace.service import CurrentModelWorkspaceService
from pilot_assessment.persistence.artifacts import ArtifactOwner, ManagedArtifactStore
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
from pilot_assessment.runtime.source_provenance import BackendSourceProvenance

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


CurrentPreflightRecord = CurrentModelRunPreflightReport | CurrentModelRunPreflightReportV2
CurrentSnapshotRecord = (
    CurrentModelRunSnapshot | CurrentModelRunSnapshotV2 | CurrentModelRunSnapshotV3
)


def current_preflight_hash(report: CurrentPreflightRecord) -> str:
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
        artifacts: ManagedArtifactStore,
        source_provenance: BackendSourceProvenance,
        *,
        clock: Clock,
    ) -> None:
        self.database = database
        self.workspace = workspace
        self.materializer = materializer
        self.legacy = legacy
        self.runs = runs
        self.artifacts = artifacts
        self.source_provenance = source_provenance
        self.clock = clock

    def prepare(
        self,
        *,
        session_revision_id: str,
        scheme_id: str,
        purpose: RunPurpose,
        runtime_parameters: Mapping[str, JsonValue],
    ) -> CurrentModelRunPreflightReportV2:
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
        source_status = self.source_provenance.disk_status()
        if source_status.runtime_restart_required:
            diagnostics.append(
                RunDiagnostic(
                    code="runtime.restart_required",
                    severity=RunDiagnosticSeverity.ERROR,
                    location="/backend_source",
                    message=(
                        "Backend source or dependency lock changed after this runtime started; "
                        "restart the application before running."
                    ),
                    details={
                        "loaded_source_tree_sha256": (
                            source_status.loaded_identity.source_tree_sha256
                        ),
                        "disk_source_tree_sha256": source_status.disk_source_tree_sha256,
                        "added": list(source_status.loaded_to_disk_changes.added),
                        "modified": list(source_status.loaded_to_disk_changes.modified),
                        "deleted": list(source_status.loaded_to_disk_changes.deleted),
                    },
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
            and not source_status.runtime_restart_required
            and not any(item.severity is RunDiagnosticSeverity.ERROR for item in ordered)
        )
        disposition = TechnicalDisposition.READY if ready else TechnicalDisposition.BLOCKED
        formal = ready and execution.report.formal_run_authorized
        embedded_execution = execution.report
        if embedded_execution.formal_run_authorized is not formal:
            embedded_execution = None
        source_snapshot_ref = None
        if ready:
            source_snapshot_ref = ArtifactIdRef(
                artifact_id=f"artifact.{self.source_provenance.snapshot_sha256}",
                sha256=self.source_provenance.snapshot_sha256,
            )
        provisional = CurrentModelRunPreflightReportV2(
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
            backend_source_identity=self.source_provenance.loaded_identity,
            source_snapshot_ref=source_snapshot_ref,
            preflight_hash=ZERO_HASH,
        )
        digest = current_preflight_hash(provisional)
        report = provisional.model_copy(
            update={
                "preflight_id": current_preflight_id_from_hash(digest),
                "preflight_hash": digest,
            }
        )
        if report.source_snapshot_ref is not None:
            artifact = self.artifacts.put_bytes(
                self.source_provenance.snapshot_bytes,
                transaction_id=f"source-snapshot.{report.source_snapshot_ref.sha256[:32]}",
                media_type="application/zip",
                schema_id="backend-source-snapshot-v1",
                owner=ArtifactOwner(
                    owner_kind=ArtifactOwnerKind.RUN_PREFLIGHT,
                    owner_id=report.preflight_id,
                    role="backend-source-snapshot",
                ),
            )
            if (
                artifact.artifact_id != report.source_snapshot_ref.artifact_id
                or artifact.sha256 != report.source_snapshot_ref.sha256
            ):
                raise CurrentRunPreflightIntegrityError(
                    "stored backend source snapshot identity changed"
                )
        self._persist(
            report,
            legacy_preflight_id=execution.report.preflight_id,
            legacy_preflight_hash=execution.report.preflight_hash,
        )
        return report

    def get(self, preflight_id: str) -> CurrentPreflightRecord:
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
    ) -> CurrentModelRunSnapshotV3:
        report = self.get(preflight_id)
        if not isinstance(report, CurrentModelRunPreflightReportV2):
            raise CurrentRunPreflightStaleError(
                "legacy current-model preflight has no backend provenance; run preflight again"
            )
        if report.technical_disposition is not TechnicalDisposition.READY:
            raise CurrentRunPreflightBlockedError(preflight_id)
        if expected_scheme_revision != report.scheme_semantic_revision:
            raise CurrentRunPreflightStaleError(
                "expected scheme revision differs from the prepared revision"
            )
        source_status = self.source_provenance.disk_status()
        if source_status.runtime_restart_required:
            raise CurrentRunPreflightStaleError(
                "backend source changed after preflight; restart the application "
                "and run preflight again"
            )
        if report.backend_source_identity != self.source_provenance.loaded_identity:
            raise CurrentRunPreflightIntegrityError(
                "preflight backend identity differs from the loaded runtime"
            )
        if report.source_snapshot_ref is None:
            raise CurrentRunPreflightIntegrityError(
                "ready preflight does not reference a backend source snapshot"
            )
        with self.artifacts.open_verified(report.source_snapshot_ref.artifact_id):
            pass
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
        provisional = CurrentModelRunSnapshotV3(
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
            backend_source_identity=report.backend_source_identity,
            source_snapshot_ref=report.source_snapshot_ref,
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
    ) -> AssessmentRunV3:
        try:
            existing = self.runs.get(run_id)
        except RunNotFoundError:
            pass
        else:
            report = self.get(preflight_id)
            if not isinstance(existing, AssessmentRunV3) or (
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
        created = self.runs.create_current(
            snapshot,
            current_preflight_id=preflight_id,
            requested_at=requested_at,
        )
        if not isinstance(created, AssessmentRunV3):
            raise CurrentRunPreflightIntegrityError(
                "single-English snapshot produced a non-v0.3 run record"
            )
        with self.database.transaction(join_existing=True) as connection:
            self.artifacts.add_reference_in_transaction(
                connection,
                ArtifactReference(
                    owner_kind=ArtifactOwnerKind.RUN,
                    owner_id=run_id,
                    role="backend-source-snapshot",
                    artifact_id=snapshot.source_snapshot_ref.artifact_id,
                ),
            )
        return created

    def preview(
        self,
        *,
        session_revision_id: str,
        scheme_id: str,
        runtime_parameters: Mapping[str, JsonValue],
        preview_id: str,
    ) -> CurrentModelRunSnapshotV3:
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
    ) -> CurrentModelRunSnapshotV3:
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
        report: CurrentPreflightRecord,
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

    def _from_row(self, row) -> CurrentPreflightRecord:
        try:
            payload = decode_canonical_json(row["report_json"])
            if not isinstance(payload, dict):
                raise ValueError("current preflight JSON must be an object")
            report_type = (
                CurrentModelRunPreflightReportV2
                if payload.get("contract_version") == "0.2.0"
                else CurrentModelRunPreflightReport
            )
            report = report_type.model_validate(payload)
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
