"""Technical-only preflight and portable exact run-plan snapshots."""

from __future__ import annotations

import platform
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from typing import Literal

from pydantic import JsonValue, ValidationError, model_validator

from pilot_assessment.bayesian.inference import InferenceCompileError, InferenceEngine
from pilot_assessment.contracts.assessment_scheme import (
    AssessmentSchemeVersion,
    CoverageReportingPolicyVersion,
)
from pilot_assessment.contracts.common import (
    Sha256Digest,
    StrictContractModel,
)
from pilot_assessment.contracts.model_components import (
    ComponentKind,
    EvidenceVersion,
    PinnedComponentRef,
)
from pilot_assessment.contracts.project import SessionRevisionRef
from pilot_assessment.contracts.run import (
    ExecutableIdentity,
    RunDiagnostic,
    RunDiagnosticSeverity,
    RunPreflightReport,
    RunPurpose,
    RunSnapshot,
    TechnicalDisposition,
)
from pilot_assessment.evidence.compiler import RecipeCompilationError, compile_recipe
from pilot_assessment.evidence.registry import OperatorRegistry, OperatorRegistryError
from pilot_assessment.model_library.identity import typed_content_sha256
from pilot_assessment.model_library.repository import (
    ComponentLibraryRepository,
    LibraryItemNotFoundError,
)
from pilot_assessment.model_library.sources import SourceCatalog
from pilot_assessment.persistence.database import (
    Clock,
    ProjectDatabase,
    decode_canonical_json,
    encode_canonical_json,
)
from pilot_assessment.persistence.sessions import (
    ManagedSessionChangedError,
    SessionImportService,
)
from pilot_assessment.runtime.repository import run_snapshot_hash
from pilot_assessment.schemes.validation import (
    SchemeDiagnosticSeverity,
    SchemeValidationDisposition,
    validate_executable_scheme,
)
from pilot_assessment.synchronization.models import SynchronizationOutcome
from pilot_assessment.synchronization.service import synchronize_bundle

ZERO_HASH = "0" * 64


class RunPreflightError(RuntimeError):
    """Base class for exact technical-preflight failures."""


class RunPreflightNotFoundError(RunPreflightError):
    """Raised when a requested durable preflight identity does not exist."""


class RunPreflightIntegrityError(RunPreflightError):
    """Raised when stored preflight content disagrees with its identity."""


class RunPreflightBlockedError(RunPreflightError):
    """Raised when a blocked preflight is asked to create a run snapshot."""


class RunPreflightStaleError(RunPreflightError):
    """Raised when a previously prepared execution lock is no longer current."""


class PreflightExecutionLock(StrictContractModel):
    """Portable execution identities not duplicated in the public report."""

    contract_id: Literal["preflight-execution-lock"] = "preflight-execution-lock"
    contract_version: Literal["0.1.0"] = "0.1.0"
    purpose: RunPurpose
    session_revision_ref: SessionRevisionRef
    scheme_ref: PinnedComponentRef
    locked_component_refs: tuple[PinnedComponentRef, ...]
    locked_source_refs: tuple[PinnedComponentRef, ...]
    locked_operator_identities: tuple[ExecutableIdentity, ...]
    engine_identity: ExecutableIdentity
    numeric_runtime_identities: tuple[ExecutableIdentity, ...]
    runtime_parameters_hash: Sha256Digest
    synchronization_fingerprint: Sha256Digest

    @model_validator(mode="after")
    def validate_lock(self) -> PreflightExecutionLock:
        if self.scheme_ref.kind is not ComponentKind.ASSESSMENT_SCHEME_VERSION:
            raise ValueError("scheme_ref must identify an assessment scheme version")
        if any(
            reference.kind is ComponentKind.SOURCE_DESCRIPTOR
            for reference in self.locked_component_refs
        ):
            raise ValueError("source descriptors belong in locked_source_refs")
        if any(
            reference.kind is not ComponentKind.SOURCE_DESCRIPTOR
            for reference in self.locked_source_refs
        ):
            raise ValueError("locked_source_refs may contain only source descriptors")
        return self


class PreparedRunPreflight(StrictContractModel):
    """Durable report plus every identity needed to construct a run snapshot."""

    contract_id: Literal["prepared-run-preflight"] = "prepared-run-preflight"
    contract_version: Literal["0.1.0"] = "0.1.0"
    report: RunPreflightReport
    lock: PreflightExecutionLock

    @model_validator(mode="after")
    def validate_prepared(self) -> PreparedRunPreflight:
        if self.report.session_revision_ref != self.lock.session_revision_ref:
            raise ValueError("report and execution lock session identities differ")
        if self.report.scheme_ref != self.lock.scheme_ref:
            raise ValueError("report and execution lock scheme identities differ")
        expected_refs = tuple(
            sorted(
                (*self.lock.locked_component_refs, *self.lock.locked_source_refs),
                key=lambda item: (item.kind.value, item.version_id),
            )
        )
        if self.report.locked_component_refs != expected_refs:
            raise ValueError("report component closure differs from the execution lock")
        if prepared_preflight_hash(self.report, self.lock) != self.report.preflight_hash:
            raise ValueError("preflight hash does not match the report and execution lock")
        if self.report.preflight_id != preflight_id_from_hash(self.report.preflight_hash):
            raise ValueError("preflight ID is not derived from the preflight hash")
        return self


def preflight_id_from_hash(preflight_hash: str) -> str:
    return f"preflight.{preflight_hash[:32]}"


def prepared_preflight_hash(
    report: RunPreflightReport,
    lock: PreflightExecutionLock,
) -> str:
    report_payload = report.model_dump(mode="json")
    report_payload.pop("preflight_id")
    report_payload.pop("preflight_hash")
    return typed_content_sha256(
        "prepared-run-preflight",
        "0.1.0",
        {
            "report": report_payload,
            "lock": lock.model_dump(mode="json"),
        },
    )


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise RunPreflightError("preflight clock must return timezone-aware timestamps")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _pin_sort_key(reference: PinnedComponentRef) -> tuple[str, str]:
    return (reference.kind.value, reference.version_id)


def _scheme_pins(scheme: AssessmentSchemeVersion) -> tuple[PinnedComponentRef, ...]:
    return tuple(
        sorted(
            (
                scheme.task_profile,
                scheme.reporting_policy,
                scheme.layout,
                *scheme.source_descriptors,
                *scheme.evidence_versions,
                *scheme.evidence_binding_versions,
                *scheme.bn_node_versions,
                *scheme.cpt_versions,
            ),
            key=_pin_sort_key,
        )
    )


def _diagnostic(
    code: str,
    location: str,
    message: str,
    *,
    severity: RunDiagnosticSeverity = RunDiagnosticSeverity.ERROR,
    details: Mapping[str, JsonValue] | None = None,
) -> RunDiagnostic:
    return RunDiagnostic(
        code=code,
        severity=severity,
        location=location,
        message=message,
        details=dict(details or {}),
    )


def _ordered_diagnostics(values: list[RunDiagnostic]) -> tuple[RunDiagnostic, ...]:
    unique: dict[tuple[str, str, str, str], RunDiagnostic] = {}
    for item in values:
        key = (item.location, item.code, item.severity.value, item.message)
        unique.setdefault(key, item)
    return tuple(unique[key] for key in sorted(unique))


def _definition_identity(
    operator_registry: OperatorRegistry,
    operator_id: str,
    operator_version: str,
) -> ExecutableIdentity:
    definition = operator_registry.definition(operator_id, operator_version)
    digest = typed_content_sha256(
        definition.contract_id,
        definition.contract_version,
        definition.model_dump(mode="json"),
    )
    return ExecutableIdentity(
        identity_id=f"operator.{digest[:32]}",
        version=definition.implementation_version,
        content_hash=digest,
    )


def _operator_identities(
    evidence_versions: tuple[EvidenceVersion, ...],
    operator_registry: OperatorRegistry,
) -> tuple[ExecutableIdentity, ...]:
    keys: set[tuple[str, str]] = set()
    for evidence in evidence_versions:
        keys.update(
            (node.operator_id, node.operator_version) for node in evidence.recipe.graph.nodes
        )
        scoring = evidence.recipe.scoring
        if (
            scoring is not None
            and scoring.custom_operator_id is not None
            and scoring.custom_operator_version is not None
        ):
            keys.add((scoring.custom_operator_id, scoring.custom_operator_version))
    identities = tuple(
        _definition_identity(operator_registry, operator_id, operator_version)
        for operator_id, operator_version in sorted(keys)
    )
    return tuple(sorted(identities, key=lambda item: item.identity_id))


def _package_version(distribution: str, fallback: str) -> str:
    try:
        return package_version(distribution)
    except PackageNotFoundError:
        return fallback


def _executable_identity(identity_id: str, version: str, kind: str) -> ExecutableIdentity:
    return ExecutableIdentity(
        identity_id=identity_id,
        version=version,
        content_hash=typed_content_sha256(
            "executable-identity",
            "0.1.0",
            {"identity_id": identity_id, "version": version, "kind": kind},
        ),
    )


def _engine_identity() -> ExecutableIdentity:
    return _executable_identity(
        "engine.bayesian.variable-elimination",
        _package_version("pilot-assessment-system", "0.1.0"),
        "finite-discrete-exact-inference",
    )


def _numeric_runtime_identities() -> tuple[ExecutableIdentity, ...]:
    values = (
        ("runtime.numpy", _package_version("numpy", "unknown"), "numeric-library"),
        ("runtime.polars", _package_version("polars", "unknown"), "table-library"),
        ("runtime.python", platform.python_version(), "language-runtime"),
        ("runtime.scipy", _package_version("scipy", "unknown"), "numeric-library"),
    )
    return tuple(_executable_identity(*value) for value in values)


def _runtime_parameters_hash(runtime_parameters: Mapping[str, JsonValue]) -> str:
    payload = dict(runtime_parameters)
    # Canonical encoding rejects non-JSON and non-finite values before hashing.
    encode_canonical_json(payload)
    return typed_content_sha256("run-runtime-parameters", "0.1.0", payload)


class RunPreflightService:
    """Prepare and persist exact plans without judging observed performance quality."""

    def __init__(
        self,
        database: ProjectDatabase,
        components: ComponentLibraryRepository,
        sessions: SessionImportService,
        *,
        source_catalog: SourceCatalog,
        operator_registry: OperatorRegistry,
        clock: Clock,
    ) -> None:
        self.database = database
        self.components = components
        self.sessions = sessions
        self.source_catalog = source_catalog
        self.operator_registry = operator_registry
        self.clock = clock
        self._synchronization_cache: dict[str, SynchronizationOutcome] = {}

    def prepare(
        self,
        *,
        session_revision_id: str,
        scheme_version_id: str,
        purpose: RunPurpose,
        runtime_parameters: Mapping[str, JsonValue],
    ) -> PreparedRunPreflight:
        diagnostics: list[RunDiagnostic] = []
        revision = self.sessions.get_revision(session_revision_id)
        session_ref = SessionRevisionRef(
            session_id=revision.session_id,
            session_revision_id=revision.session_revision_id,
            bundle_root_hash=revision.bundle_root_hash,
        )
        managed_verified = True
        try:
            verified_revision = self.sessions.verify_managed_revision(session_revision_id)
            if verified_revision != revision:
                raise ManagedSessionChangedError(
                    "MANAGED_SESSION_CHANGED: revision identity changed during verification"
                )
        except ManagedSessionChangedError as error:
            managed_verified = False
            diagnostics.append(
                _diagnostic(
                    "MANAGED_SESSION_CHANGED",
                    "/session_revision_ref",
                    str(error),
                    details={"session_revision_id": session_revision_id},
                )
            )

        scheme: AssessmentSchemeVersion | None = None
        try:
            item = self.components.get_exact(
                ComponentKind.ASSESSMENT_SCHEME_VERSION,
                scheme_version_id,
            )
            if not isinstance(item, AssessmentSchemeVersion):
                raise TypeError("stored scheme record has an unexpected contract type")
            scheme = item
            scheme_ref = PinnedComponentRef(
                kind=ComponentKind.ASSESSMENT_SCHEME_VERSION,
                version_id=scheme.scheme_version_id,
                content_hash=scheme.content_hash,
            )
        except (LibraryItemNotFoundError, TypeError) as error:
            scheme_ref = PinnedComponentRef(
                kind=ComponentKind.ASSESSMENT_SCHEME_VERSION,
                version_id=scheme_version_id,
                content_hash=ZERO_HASH,
            )
            diagnostics.append(
                _diagnostic(
                    "run.scheme_not_found",
                    "/scheme_ref",
                    str(error),
                    details={"scheme_version_id": scheme_version_id},
                )
            )

        synchronization: SynchronizationOutcome | None = None
        synthetic_data = False
        synchronization_fingerprint = ZERO_HASH
        if managed_verified:
            try:
                synchronization = self._synchronize(revision.bundle_root_hash, session_revision_id)
                sync_report = synchronization.report
                synthetic_data = sync_report.source_classification == "synthetic-test-data"
                synchronization_fingerprint = sync_report.synchronization_fingerprint
                if not sync_report.can_continue_to_anchor_availability:
                    diagnostics.append(
                        _diagnostic(
                            "run.synchronization_blocked",
                            "/session_revision_ref/synchronization",
                            "managed session cannot produce an aligned runtime view",
                            details={"disposition": sync_report.disposition.value},
                        )
                    )
            except Exception as error:  # boundary converts loader/adapter faults to diagnostics
                diagnostics.append(
                    _diagnostic(
                        "run.synchronization_failed",
                        "/session_revision_ref/synchronization",
                        str(error),
                    )
                )

        pins: tuple[PinnedComponentRef, ...] = ()
        evidence_versions: list[EvidenceVersion] = []
        formal_policy_declared = False
        if scheme is not None:
            pins = _scheme_pins(scheme)
            outcome = validate_executable_scheme(
                scheme,
                self.components,
                self.source_catalog,
                self.operator_registry,
            )
            for item in outcome.diagnostics:
                severity = (
                    RunDiagnosticSeverity.ERROR
                    if item.severity is SchemeDiagnosticSeverity.ERROR
                    else RunDiagnosticSeverity.WARNING
                )
                details: dict[str, JsonValue] = {}
                if item.component_id is not None:
                    details["component_id"] = item.component_id
                diagnostics.append(
                    _diagnostic(
                        item.code,
                        f"/scheme{item.location}",
                        item.message,
                        severity=severity,
                        details=details,
                    )
                )
            if outcome.disposition is not SchemeValidationDisposition.EXECUTABLE and not any(
                item.severity is RunDiagnosticSeverity.ERROR for item in diagnostics
            ):
                diagnostics.append(
                    _diagnostic(
                        "run.scheme_not_executable",
                        "/scheme_ref",
                        "assessment scheme is not technically executable",
                    )
                )

            for index, reference in enumerate(scheme.evidence_versions):
                try:
                    evidence = self.components.get_exact(
                        ComponentKind.EVIDENCE_VERSION,
                        reference.version_id,
                    )
                    if not isinstance(evidence, EvidenceVersion):
                        raise TypeError("record is not an EvidenceVersion")
                    evidence_versions.append(evidence)
                    compile_recipe(evidence.recipe, self.operator_registry)
                except (LibraryItemNotFoundError, TypeError, RecipeCompilationError) as error:
                    diagnostics.append(
                        _diagnostic(
                            "run.evidence_compile_failed",
                            f"/scheme/evidence_versions/{index}",
                            str(error),
                            details={"evidence_version_id": reference.version_id},
                        )
                    )

            try:
                InferenceEngine(self.components).compile(scheme)
            except InferenceCompileError as error:
                diagnostics.append(
                    _diagnostic(
                        error.code,
                        "/scheme/inference",
                        str(error),
                    )
                )

            try:
                policy = self.components.get_exact(
                    ComponentKind.COVERAGE_REPORTING_POLICY_VERSION,
                    scheme.reporting_policy.version_id,
                )
                if not isinstance(policy, CoverageReportingPolicyVersion):
                    raise TypeError("reporting policy pin has an unexpected contract type")
                formal_policy_declared = policy.output_rules.get("formal_run_authorized") is True
            except (LibraryItemNotFoundError, TypeError) as error:
                diagnostics.append(
                    _diagnostic(
                        "run.reporting_policy_invalid",
                        "/scheme/reporting_policy",
                        str(error),
                    )
                )

        try:
            operator_identities = _operator_identities(
                tuple(evidence_versions),
                self.operator_registry,
            )
        except OperatorRegistryError as error:
            operator_identities = ()
            diagnostics.append(
                _diagnostic(
                    "run.operator_unavailable",
                    "/scheme/evidence_versions",
                    str(error),
                )
            )

        non_source_pins = tuple(
            reference for reference in pins if reference.kind is not ComponentKind.SOURCE_DESCRIPTOR
        )
        source_pins = tuple(
            reference for reference in pins if reference.kind is ComponentKind.SOURCE_DESCRIPTOR
        )
        lock = PreflightExecutionLock(
            purpose=purpose,
            session_revision_ref=session_ref,
            scheme_ref=scheme_ref,
            locked_component_refs=non_source_pins,
            locked_source_refs=source_pins,
            locked_operator_identities=operator_identities,
            engine_identity=_engine_identity(),
            numeric_runtime_identities=_numeric_runtime_identities(),
            runtime_parameters_hash=_runtime_parameters_hash(runtime_parameters),
            synchronization_fingerprint=synchronization_fingerprint,
        )

        technical_errors_before_purpose = any(
            item.severity is RunDiagnosticSeverity.ERROR for item in diagnostics
        )
        provisionally_formal = (
            not technical_errors_before_purpose and formal_policy_declared and not synthetic_data
        )
        if purpose is RunPurpose.ASSESSMENT and not provisionally_formal:
            diagnostics.append(
                _diagnostic(
                    "run.assessment_not_authorized",
                    "/purpose",
                    "assessment purpose requires a ready, non-synthetic, "
                    "formally authorized policy",
                    details={
                        "formal_policy_declared": formal_policy_declared,
                        "synthetic_data": synthetic_data,
                    },
                )
            )

        ordered_diagnostics = _ordered_diagnostics(diagnostics)
        blocked = any(item.severity is RunDiagnosticSeverity.ERROR for item in ordered_diagnostics)
        disposition = TechnicalDisposition.BLOCKED if blocked else TechnicalDisposition.READY
        formal_authorized = (
            disposition is TechnicalDisposition.READY
            and formal_policy_declared
            and not synthetic_data
        )
        all_pins = tuple(sorted((*non_source_pins, *source_pins), key=_pin_sort_key))
        provisional_report = RunPreflightReport(
            preflight_id="preflight.pending",
            session_revision_ref=session_ref,
            scheme_ref=scheme_ref,
            technical_disposition=disposition,
            formal_run_authorized=formal_authorized,
            synthetic_data=synthetic_data,
            locked_component_refs=all_pins,
            diagnostics=ordered_diagnostics,
            preflight_hash=ZERO_HASH,
        )
        digest = prepared_preflight_hash(provisional_report, lock)
        report = provisional_report.model_copy(
            update={
                "preflight_id": preflight_id_from_hash(digest),
                "preflight_hash": digest,
            }
        )
        prepared = PreparedRunPreflight(report=report, lock=lock)
        self._persist(prepared)
        return prepared

    def get(self, preflight_id: str) -> PreparedRunPreflight:
        row = self.database.fetchone(
            "SELECT * FROM run_preflights WHERE preflight_id = ?",
            (preflight_id,),
        )
        if row is None:
            raise RunPreflightNotFoundError(preflight_id)
        return self._from_row(row)

    def build_snapshot(self, preflight_id: str, *, run_id: str) -> RunSnapshot:
        prepared = self.get(preflight_id)
        if prepared.report.technical_disposition is not TechnicalDisposition.READY:
            raise RunPreflightBlockedError(f"preflight {preflight_id!r} is technically blocked")
        try:
            revision = self.sessions.verify_managed_revision(
                prepared.lock.session_revision_ref.session_revision_id
            )
        except ManagedSessionChangedError as error:
            raise RunPreflightStaleError(str(error)) from error
        if revision.bundle_root_hash != prepared.lock.session_revision_ref.bundle_root_hash:
            raise RunPreflightStaleError("managed session root no longer matches preflight")
        if prepared.lock.purpose is RunPurpose.ASSESSMENT and not (
            prepared.report.formal_run_authorized
        ):
            raise RunPreflightBlockedError("assessment preflight is not formally authorized")

        provisional = RunSnapshot(
            run_id=run_id,
            purpose=prepared.lock.purpose,
            session_revision_ref=prepared.lock.session_revision_ref,
            scheme_ref=prepared.lock.scheme_ref,
            locked_component_refs=prepared.lock.locked_component_refs,
            locked_source_refs=prepared.lock.locked_source_refs,
            locked_operator_identities=prepared.lock.locked_operator_identities,
            engine_identity=prepared.lock.engine_identity,
            numeric_runtime_identities=prepared.lock.numeric_runtime_identities,
            runtime_parameters_hash=prepared.lock.runtime_parameters_hash,
            preflight_hash=prepared.report.preflight_hash,
            snapshot_hash=ZERO_HASH,
        )
        return provisional.model_copy(update={"snapshot_hash": run_snapshot_hash(provisional)})

    def synchronization_outcome(self, preflight_id: str) -> SynchronizationOutcome:
        prepared = self.get(preflight_id)
        if prepared.report.technical_disposition is not TechnicalDisposition.READY:
            raise RunPreflightBlockedError(preflight_id)
        revision = self.sessions.verify_managed_revision(
            prepared.lock.session_revision_ref.session_revision_id
        )
        outcome = self._synchronize(
            revision.bundle_root_hash,
            revision.session_revision_id,
        )
        if outcome.report.synchronization_fingerprint != prepared.lock.synchronization_fingerprint:
            raise RunPreflightStaleError("synchronization fingerprint no longer matches preflight")
        return outcome

    def _synchronize(
        self,
        bundle_root_hash: str,
        session_revision_id: str,
    ) -> SynchronizationOutcome:
        cached = self._synchronization_cache.get(bundle_root_hash)
        if cached is not None:
            return cached
        outcome = synchronize_bundle(self.sessions.managed_bundle_path(session_revision_id))
        self._synchronization_cache[bundle_root_hash] = outcome
        return outcome

    def _persist(self, prepared: PreparedRunPreflight) -> None:
        payload = encode_canonical_json(prepared.model_dump(mode="json"))
        try:
            with self.database.transaction() as connection:
                existing = connection.execute(
                    """
                    SELECT * FROM run_preflights
                    WHERE preflight_id = ? OR preflight_hash = ?
                    """,
                    (
                        prepared.report.preflight_id,
                        prepared.report.preflight_hash,
                    ),
                ).fetchone()
                if existing is not None:
                    current = self._from_row(existing)
                    if current != prepared:
                        raise RunPreflightIntegrityError(
                            "preflight identity collides with different canonical content"
                        )
                    return
                connection.execute(
                    """
                    INSERT INTO run_preflights(
                        preflight_id, preflight_hash, report_json, created_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        prepared.report.preflight_id,
                        prepared.report.preflight_hash,
                        payload,
                        _utc_text(self.clock()),
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise RunPreflightIntegrityError(
                "preflight identity could not be persisted exactly"
            ) from error

    @staticmethod
    def _from_row(row: sqlite3.Row) -> PreparedRunPreflight:
        try:
            prepared = PreparedRunPreflight.model_validate(
                decode_canonical_json(row["report_json"])
            )
        except (ValueError, ValidationError) as error:
            raise RunPreflightIntegrityError("stored preflight JSON is invalid") from error
        if (
            prepared.report.preflight_id != row["preflight_id"]
            or prepared.report.preflight_hash != row["preflight_hash"]
        ):
            raise RunPreflightIntegrityError(
                "stored preflight identity columns disagree with canonical content"
            )
        return prepared


__all__ = [
    "PreflightExecutionLock",
    "PreparedRunPreflight",
    "RunPreflightBlockedError",
    "RunPreflightError",
    "RunPreflightIntegrityError",
    "RunPreflightNotFoundError",
    "RunPreflightService",
    "RunPreflightStaleError",
    "preflight_id_from_hash",
    "prepared_preflight_hash",
]
