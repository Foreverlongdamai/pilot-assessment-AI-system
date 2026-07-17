"""Dynamic managed-session Evidence extraction and exact Bayesian inference pipeline."""

from __future__ import annotations

import hashlib
import math
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from enum import Enum
from numbers import Real
from typing import TypeAlias, cast

from pydantic import BaseModel, JsonValue, ValidationError

from pilot_assessment.bayesian.inference import InferenceEngine
from pilot_assessment.contracts.anchor import EvidenceLikelihood
from pilot_assessment.contracts.assessment_scheme import (
    AssessmentSchemeVersion,
    TaskProfileVersion,
)
from pilot_assessment.contracts.bayesian import (
    Observation,
    ObservationKind,
)
from pilot_assessment.contracts.model_components import (
    ComponentKind,
    EvidenceBindingVersion,
    EvidenceVersion,
    ObservationPolicy,
    PinnedComponentRef,
    SourceDescriptor,
)
from pilot_assessment.contracts.project import (
    ArtifactIdRef,
    ArtifactOwnerKind,
)
from pilot_assessment.contracts.run import (
    CurrentModelRunSnapshot,
    RunResultEnvelope,
    RunScientificStatus,
    RunSnapshot,
    RunStage,
)
from pilot_assessment.evidence.compiler import compile_recipe
from pilot_assessment.evidence.executor import RecipeExecutionResult, execute_recipe
from pilot_assessment.evidence.registry import OperatorRegistry
from pilot_assessment.model_library.identity import typed_content_sha256
from pilot_assessment.model_library.repository import (
    ComponentLibraryRepository,
    LibraryItemNotFoundError,
    VersionLibraryItem,
    component_content_hash,
)
from pilot_assessment.model_library.sources import SourceCatalog
from pilot_assessment.persistence.artifacts import (
    ArtifactOwner,
    ManagedArtifactStore,
)
from pilot_assessment.persistence.database import (
    ProjectDatabase,
    decode_canonical_json,
    encode_canonical_json,
)
from pilot_assessment.runtime.coordinator import run_total_units
from pilot_assessment.runtime.preflight import (
    RunPreflightService,
    preflight_id_from_hash,
)
from pilot_assessment.runtime.repository import run_snapshot_hash
from pilot_assessment.runtime.sources import (
    ResolvedRecipeInputs,
    RuntimeSourceProviderRegistry,
    RuntimeSourceResolver,
    SourceResolutionContext,
)

ZERO_HASH = "0" * 64

CancellationProbe: TypeAlias = Callable[[], None]
ProgressSink: TypeAlias = Callable[[RunStage, int, int, str], None]


class AssessmentPipelineError(RuntimeError):
    """Technical pipeline failure with a stable code and optional Evidence identity."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        evidence_version_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.evidence_version_id = evidence_version_id


class RunResultRepositoryError(RuntimeError):
    """Base error for exact durable run-result envelopes."""


class RunResultNotFoundError(RunResultRepositoryError):
    """Raised when no result exists for a requested run."""


class RunResultIntegrityError(RunResultRepositoryError):
    """Raised when a result conflicts with its run or canonical identity."""


def result_envelope_hash(envelope: RunResultEnvelope) -> str:
    payload = envelope.model_dump(mode="json")
    payload.pop("result_hash")
    return typed_content_sha256(
        envelope.contract_id,
        envelope.contract_version,
        payload,
    )


class RunResultRepository:
    """Immutable one-result-per-run storage after artifacts are durable."""

    def __init__(self, database: ProjectDatabase) -> None:
        self.database = database

    def add(self, envelope: RunResultEnvelope) -> RunResultEnvelope:
        if result_envelope_hash(envelope) != envelope.result_hash:
            raise RunResultIntegrityError("run result hash does not match canonical content")
        try:
            with self.database.transaction() as connection:
                run = connection.execute(
                    """
                    SELECT COALESCE(link.current_snapshot_hash, runs.snapshot_hash)
                           AS effective_snapshot_hash
                    FROM runs
                    LEFT JOIN model_run_links AS link ON link.run_id = runs.run_id
                    WHERE runs.run_id = ?
                    """,
                    (envelope.run_id,),
                ).fetchone()
                if run is None:
                    raise RunResultIntegrityError(f"owning run {envelope.run_id!r} does not exist")
                if run["effective_snapshot_hash"] != envelope.snapshot_hash:
                    raise RunResultIntegrityError(
                        "run result snapshot hash differs from its owning run"
                    )
                existing = connection.execute(
                    "SELECT * FROM run_results WHERE run_id = ? OR result_id = ?",
                    (envelope.run_id, envelope.result_id),
                ).fetchone()
                if existing is not None:
                    current = self._from_row(existing)
                    if current != envelope:
                        raise RunResultIntegrityError(
                            "run result identity already owns different canonical content"
                        )
                    return current
                connection.execute(
                    """
                    INSERT INTO run_results(
                        result_id, run_id, result_hash, envelope_json
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        envelope.result_id,
                        envelope.run_id,
                        envelope.result_hash,
                        encode_canonical_json(envelope.model_dump(mode="json")),
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise RunResultIntegrityError("run result could not be persisted exactly") from error
        return envelope

    def get_by_run(self, run_id: str) -> RunResultEnvelope:
        row = self.database.fetchone(
            "SELECT * FROM run_results WHERE run_id = ?",
            (run_id,),
        )
        if row is None:
            raise RunResultNotFoundError(run_id)
        return self._from_row(row)

    def get(self, result_id: str) -> RunResultEnvelope:
        row = self.database.fetchone(
            "SELECT * FROM run_results WHERE result_id = ?",
            (result_id,),
        )
        if row is None:
            raise RunResultNotFoundError(result_id)
        return self._from_row(row)

    @staticmethod
    def _from_row(row: sqlite3.Row) -> RunResultEnvelope:
        try:
            envelope = RunResultEnvelope.model_validate(decode_canonical_json(row["envelope_json"]))
        except (ValueError, ValidationError) as error:
            raise RunResultIntegrityError("stored run result JSON is invalid") from error
        if (
            envelope.result_id != row["result_id"]
            or envelope.run_id != row["run_id"]
            or envelope.result_hash != row["result_hash"]
            or result_envelope_hash(envelope) != envelope.result_hash
        ):
            raise RunResultIntegrityError("stored run result identity columns disagree")
        return envelope


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


def _portable_json(value: object, label: str) -> JsonValue:
    if value is None or type(value) in {str, bool, int}:
        return cast(JsonValue, value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise AssessmentPipelineError(
                "pipeline.non_finite_output",
                f"{label} contains a non-finite number",
            )
        return value
    if isinstance(value, Enum):
        return _portable_json(value.value, label)
    if isinstance(value, BaseModel):
        return _portable_json(value.model_dump(mode="json"), label)
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if type(key) is not str:
                raise AssessmentPipelineError(
                    "pipeline.output_not_json",
                    f"{label} mapping keys must be strings",
                )
            result[key] = _portable_json(item, label)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_portable_json(item, label) for item in value]
    if isinstance(value, Real) and not isinstance(value, bool):
        numeric = float(value)
        if math.isfinite(numeric):
            return numeric
    raise AssessmentPipelineError(
        "pipeline.output_not_json",
        f"{label} contains unsupported {type(value).__name__}",
    )


def _state_text(value: object) -> str | None:
    if isinstance(value, Enum):
        value = value.value
    return value if type(value) is str and value else None


def _likelihood_values(value: object) -> tuple[tuple[str, ...], tuple[float, ...]] | None:
    if isinstance(value, EvidenceLikelihood):
        return (tuple(value.state_order), tuple(value.values))
    if not isinstance(value, Mapping):
        return None
    mapping = cast(Mapping[str, object], value)
    raw_order = mapping.get("state_order")
    raw_values = mapping.get("values")
    if (
        isinstance(raw_order, (str, bytes))
        or not isinstance(raw_order, Sequence)
        or isinstance(raw_values, (str, bytes))
        or not isinstance(raw_values, Sequence)
        or len(raw_order) != len(raw_values)
    ):
        return None
    order: list[str] = []
    values: list[float] = []
    for state, raw_value in zip(raw_order, raw_values, strict=True):
        state_id = _state_text(state)
        if state_id is None or isinstance(raw_value, bool) or not isinstance(raw_value, Real):
            return None
        numeric = float(raw_value)
        if not math.isfinite(numeric) or numeric < 0.0:
            return None
        order.append(state_id)
        values.append(numeric)
    if not values or math.fsum(values) <= 0.0:
        return None
    total = math.fsum(values)
    return (tuple(order), tuple(value / total for value in values))


def _observation(
    binding: EvidenceBindingVersion,
    execution: RecipeExecutionResult,
) -> Observation:
    mapping = cast(Mapping[str, object], binding.observation_mapping)
    raw_state_map = mapping.get("evidence_state_map", {})
    state_map = (
        cast(Mapping[str, object], raw_state_map) if isinstance(raw_state_map, Mapping) else {}
    )
    source_state = _state_text(execution.scoring_outputs.get("state"))
    mapped_state = None
    if source_state is not None:
        candidate = state_map.get(source_state, source_state)
        mapped_state = _state_text(candidate)
    target_states = tuple(state.state_id for state in binding.ordered_observation_states)
    if mapped_state is not None and mapped_state not in target_states:
        raise AssessmentPipelineError(
            "pipeline.observation_state_unknown",
            f"mapped Evidence state {mapped_state!r} is outside the binding state order",
            evidence_version_id=binding.evidence_version_id.version_id,
        )

    likelihood = _likelihood_values(execution.scoring_outputs.get("likelihood"))
    ordered_likelihood: tuple[float, ...] | None = None
    if likelihood is not None:
        source_order, source_values = likelihood
        by_target: dict[str, float] = {}
        for source_id, value in zip(source_order, source_values, strict=True):
            mapped = _state_text(state_map.get(source_id, source_id))
            if mapped is None or mapped not in target_states or mapped in by_target:
                raise AssessmentPipelineError(
                    "pipeline.observation_likelihood_mapping_invalid",
                    "likelihood state mapping is missing, duplicated, or outside the binding",
                    evidence_version_id=binding.evidence_version_id.version_id,
                )
            by_target[mapped] = value
        if set(by_target) != set(target_states):
            raise AssessmentPipelineError(
                "pipeline.observation_likelihood_mapping_invalid",
                "likelihood states do not cover the exact binding state order",
                evidence_version_id=binding.evidence_version_id.version_id,
            )
        raw_strength = mapping.get("likelihood_strength", 1.0)
        if isinstance(raw_strength, bool) or not isinstance(raw_strength, Real):
            raise AssessmentPipelineError(
                "pipeline.observation_strength_invalid",
                "binding likelihood_strength must be numeric",
                evidence_version_id=binding.evidence_version_id.version_id,
            )
        strength = float(raw_strength)
        if not math.isfinite(strength) or not 0.0 <= strength <= 1.0:
            raise AssessmentPipelineError(
                "pipeline.observation_strength_invalid",
                "binding likelihood_strength must be between zero and one",
                evidence_version_id=binding.evidence_version_id.version_id,
            )
        uniform = (1.0 - strength) / len(target_states)
        ordered_likelihood = tuple(
            strength * by_target[state_id] + uniform for state_id in target_states
        )

    variable_id = binding.evidence_version_id.model_copy(
        update={
            "kind": ComponentKind.EVIDENCE_BINDING_VERSION,
            "version_id": binding.evidence_binding_version_id,
        }
    )
    if binding.observation_policy is ObservationPolicy.HARD:
        if mapped_state is None:
            raise AssessmentPipelineError(
                "pipeline.hard_observation_missing_state",
                "hard Evidence binding requires a scorer state",
                evidence_version_id=binding.evidence_version_id.version_id,
            )
        return Observation(
            variable_id=variable_id,
            kind=ObservationKind.HARD,
            hard_state_id=mapped_state,
            likelihood=None,
        )
    if ordered_likelihood is None:
        if mapped_state is None:
            raise AssessmentPipelineError(
                "pipeline.virtual_observation_missing_output",
                "virtual Evidence binding requires a state or likelihood",
                evidence_version_id=binding.evidence_version_id.version_id,
            )
        ordered_likelihood = tuple(
            1.0 if state_id == mapped_state else 0.0 for state_id in target_states
        )
    return Observation(
        variable_id=variable_id,
        kind=ObservationKind.VIRTUAL,
        hard_state_id=None,
        likelihood=ordered_likelihood,
    )


def _omitted_observation(binding: EvidenceBindingVersion) -> Observation:
    variable_id = binding.evidence_version_id.model_copy(
        update={
            "kind": ComponentKind.EVIDENCE_BINDING_VERSION,
            "version_id": binding.evidence_binding_version_id,
        }
    )
    return Observation(
        variable_id=variable_id,
        kind=ObservationKind.OMITTED,
        hard_state_id=None,
        likelihood=None,
    )


def _artifact_ref(artifact) -> ArtifactIdRef:
    return ArtifactIdRef(artifact_id=artifact.artifact_id, sha256=artifact.sha256)


def _result_id(run_id: str) -> str:
    digest = hashlib.sha256(run_id.encode("utf-8")).hexdigest()
    return f"result.{digest[:32]}"


class AssessmentPipeline:
    """Execute only the Evidence and BN components selected by one frozen snapshot."""

    def __init__(
        self,
        components: ComponentLibraryRepository,
        artifacts: ManagedArtifactStore,
        preflight: RunPreflightService,
        results: RunResultRepository,
        *,
        operator_registry: OperatorRegistry,
        source_provider_registry: RuntimeSourceProviderRegistry,
    ) -> None:
        self.components = components
        self.artifacts = artifacts
        self.preflight = preflight
        self.results = results
        self.operator_registry = operator_registry
        self.source_provider_registry = source_provider_registry

    def execute(
        self,
        snapshot: RunSnapshot | CurrentModelRunSnapshot,
        *,
        cancellation: CancellationProbe | None = None,
        progress: ProgressSink | None = None,
    ) -> RunResultEnvelope:
        try:
            return self.results.get_by_run(snapshot.run_id)
        except RunResultNotFoundError:
            pass
        cancel = cancellation or (lambda: None)
        report = progress or (lambda _stage, _completed, _total, _message: None)
        total = run_total_units(snapshot)
        cancel()
        execution_snapshot = (
            snapshot.execution_snapshot
            if isinstance(snapshot, CurrentModelRunSnapshot)
            else snapshot
        )
        if isinstance(snapshot, CurrentModelRunSnapshot) and (
            run_snapshot_hash(snapshot) != snapshot.snapshot_hash
        ):
            raise AssessmentPipelineError(
                "pipeline.current_snapshot_hash_mismatch",
                "current run snapshot hash does not match canonical content",
            )
        self._validate_snapshot(execution_snapshot)
        report(
            RunStage.SNAPSHOT_VALIDATION,
            1,
            total,
            "Validated frozen run snapshot",
        )
        cancel()
        scheme = self._load_scheme(execution_snapshot.scheme_ref)
        prepared = self.preflight.get(preflight_id_from_hash(execution_snapshot.preflight_hash))
        if prepared.report.preflight_hash != execution_snapshot.preflight_hash:
            raise AssessmentPipelineError(
                "pipeline.preflight_mismatch",
                "snapshot preflight identity does not exist exactly",
            )
        report(
            RunStage.INGESTION,
            2,
            total,
            "Loaded exact managed session revision",
        )
        cancel()
        synchronized = self.preflight.synchronization_outcome(prepared.report.preflight_id)
        aligned = synchronized.aligned_session
        if aligned is None:
            raise AssessmentPipelineError(
                "pipeline.aligned_session_missing",
                "ready preflight did not produce an aligned session",
            )
        report(
            RunStage.SYNCHRONIZATION,
            3,
            total,
            "Loaded exact synchronized session",
        )
        cancel()
        pins = _scheme_pins(scheme)
        expected_components = tuple(
            reference for reference in pins if reference.kind is not ComponentKind.SOURCE_DESCRIPTOR
        )
        expected_sources = tuple(
            reference for reference in pins if reference.kind is ComponentKind.SOURCE_DESCRIPTOR
        )
        if (
            execution_snapshot.locked_component_refs != expected_components
            or execution_snapshot.locked_source_refs != expected_sources
        ):
            raise AssessmentPipelineError(
                "pipeline.scheme_closure_mismatch",
                "snapshot component closure differs from the exact selected scheme",
            )
        task = self._load_task(scheme.task_profile)
        exact_source_catalog = self._source_catalog(scheme)
        resolver = RuntimeSourceResolver(
            exact_source_catalog,
            self.source_provider_registry,
            SourceResolutionContext(
                aligned_session=aligned,
                task_profile=task,
                runtime_parameters=prepared.lock.runtime_parameters,
            ),
        )
        evidence_versions = tuple(
            self._load_evidence(reference) for reference in scheme.evidence_versions
        )
        bindings = tuple(
            self._load_binding(reference) for reference in scheme.evidence_binding_versions
        )
        bindings_by_evidence: dict[str, list[EvidenceBindingVersion]] = {}
        for binding in bindings:
            bindings_by_evidence.setdefault(
                binding.evidence_version_id.version_id,
                [],
            ).append(binding)

        result_id = _result_id(snapshot.run_id)
        owners: list[ArtifactOwner] = []
        evidence_result_refs: list[ArtifactIdRef] = []
        evidence_trace_refs: list[ArtifactIdRef] = []
        observations: list[Observation] = []
        try:
            for index, evidence in enumerate(evidence_versions):
                cancel()
                selected_bindings = tuple(
                    bindings_by_evidence.get(evidence.evidence_version_id, ())
                )
                if not selected_bindings:
                    raise AssessmentPipelineError(
                        "pipeline.evidence_binding_missing",
                        "selected Evidence has no BN observation binding",
                        evidence_version_id=evidence.evidence_version_id,
                    )
                resolved = resolver.resolve_bindings(evidence.recipe.inputs)
                if resolved.error_binding_ids:
                    raise AssessmentPipelineError(
                        "pipeline.source_resolution_failed",
                        "; ".join(item.message for item in resolved.diagnostics),
                        evidence_version_id=evidence.evidence_version_id,
                    )
                if resolved.omitted_binding_ids:
                    observations.extend(
                        _omitted_observation(binding) for binding in selected_bindings
                    )
                    evidence_payload = self._omitted_evidence_payload(
                        evidence,
                        selected_bindings,
                        resolved,
                    )
                    trace_payload = self._source_trace_payload(evidence, resolved)
                else:
                    compiled = compile_recipe(evidence.recipe, self.operator_registry)
                    try:
                        execution = execute_recipe(
                            compiled,
                            self.operator_registry,
                            binding_values=resolved.binding_values,
                        )
                    except Exception as error:
                        raise AssessmentPipelineError(
                            "pipeline.evidence_execution_failed",
                            f"Evidence recipe raised {type(error).__name__}: {error}",
                            evidence_version_id=evidence.evidence_version_id,
                        ) from error
                    observations.extend(
                        _observation(binding, execution) for binding in selected_bindings
                    )
                    evidence_payload = self._computed_evidence_payload(
                        evidence,
                        selected_bindings,
                        execution,
                    )
                    trace_payload = self._execution_trace_payload(evidence, execution)
                cancel()
                evidence_result_refs.append(
                    self._put_json(
                        evidence_payload,
                        result_id=result_id,
                        role=f"evidence-result-{index:04d}",
                        schema_id="evidence-runtime-result-0.1.0",
                        owners=owners,
                    )
                )
                cancel()
                evidence_trace_refs.append(
                    self._put_json(
                        trace_payload,
                        result_id=result_id,
                        role=f"evidence-trace-{index:04d}",
                        schema_id="evidence-runtime-trace-0.1.0",
                        owners=owners,
                    )
                )
                report(
                    RunStage.EVIDENCE,
                    index + 4,
                    total,
                    f"Executed Evidence {index + 1} of {len(evidence_versions)}",
                )

            cancel()
            engine = InferenceEngine(self.components)
            plan = engine.compile(scheme)
            observation_set = engine.observe(plan, observations)
            posterior = engine.infer(plan, observation_set, scheme.output_node_ids)
            inference_trace = engine.explain(plan, observation_set, scheme.output_node_ids)
            observation_ref = self._put_contract(
                observation_set,
                result_id=result_id,
                role="observation-set",
                schema_id="observation-set-0.1.0",
                owners=owners,
            )
            cancel()
            posterior_ref = self._put_contract(
                posterior,
                result_id=result_id,
                role="posterior",
                schema_id="posterior-result-0.1.0",
                owners=owners,
            )
            cancel()
            inference_trace_ref = self._put_contract(
                inference_trace,
                result_id=result_id,
                role="inference-trace",
                schema_id="inference-trace-0.1.0",
                owners=owners,
            )
            report(
                RunStage.INFERENCE,
                len(evidence_versions) + 4,
                total,
                "Computed exact Bayesian posterior",
            )
            cancel()
            provisional = RunResultEnvelope(
                result_id=result_id,
                run_id=snapshot.run_id,
                snapshot_hash=snapshot.snapshot_hash,
                evidence_result_refs=tuple(evidence_result_refs),
                evidence_trace_refs=tuple(evidence_trace_refs),
                observation_set_ref=observation_ref,
                posterior_ref=posterior_ref,
                inference_trace_ref=inference_trace_ref,
                reporting_refs=(),
                coverage_refs=(),
                scientific_status=RunScientificStatus.NOT_SUPPORTED,
                result_hash=ZERO_HASH,
            )
            envelope = provisional.model_copy(
                update={"result_hash": result_envelope_hash(provisional)}
            )
            cancel()
            persisted = self.results.add(envelope)
            report(
                RunStage.REPORTING,
                len(evidence_versions) + 5,
                total,
                "Persisted exact run result envelope",
            )
            return persisted
        except BaseException:
            for owner in reversed(owners):
                self.artifacts.remove_reference(owner)
            raise

    def _validate_snapshot(self, snapshot: RunSnapshot) -> None:
        if run_snapshot_hash(snapshot) != snapshot.snapshot_hash:
            raise AssessmentPipelineError(
                "pipeline.snapshot_hash_mismatch",
                "run snapshot hash does not match canonical content",
            )
        prepared = self.preflight.get(preflight_id_from_hash(snapshot.preflight_hash))
        lock = prepared.lock
        comparisons = (
            (snapshot.purpose, lock.purpose),
            (snapshot.session_revision_ref, lock.session_revision_ref),
            (snapshot.scheme_ref, lock.scheme_ref),
            (snapshot.locked_component_refs, lock.locked_component_refs),
            (snapshot.locked_source_refs, lock.locked_source_refs),
            (snapshot.locked_operator_identities, lock.locked_operator_identities),
            (snapshot.engine_identity, lock.engine_identity),
            (snapshot.numeric_runtime_identities, lock.numeric_runtime_identities),
            (snapshot.runtime_parameters_hash, lock.runtime_parameters_hash),
        )
        if any(left != right for left, right in comparisons):
            raise AssessmentPipelineError(
                "pipeline.snapshot_lock_mismatch",
                "run snapshot differs from its prepared execution lock",
            )

    def _load_scheme(self, reference: PinnedComponentRef) -> AssessmentSchemeVersion:
        item = self._load_exact(reference)
        if not isinstance(item, AssessmentSchemeVersion):
            raise AssessmentPipelineError(
                "pipeline.scheme_type_mismatch",
                "snapshot scheme reference does not resolve to an assessment scheme",
            )
        return item

    def _load_task(self, reference: PinnedComponentRef) -> TaskProfileVersion:
        item = self._load_exact(reference)
        if not isinstance(item, TaskProfileVersion):
            raise AssessmentPipelineError(
                "pipeline.task_type_mismatch",
                "scheme task reference does not resolve to a task profile",
            )
        return item

    def _load_evidence(self, reference: PinnedComponentRef) -> EvidenceVersion:
        item = self._load_exact(reference)
        if not isinstance(item, EvidenceVersion):
            raise AssessmentPipelineError(
                "pipeline.evidence_type_mismatch",
                "scheme Evidence reference has an unexpected contract type",
            )
        return item

    def _load_binding(self, reference: PinnedComponentRef) -> EvidenceBindingVersion:
        item = self._load_exact(reference)
        if not isinstance(item, EvidenceBindingVersion):
            raise AssessmentPipelineError(
                "pipeline.binding_type_mismatch",
                "scheme Evidence binding reference has an unexpected contract type",
            )
        return item

    def _load_exact(self, reference: PinnedComponentRef) -> VersionLibraryItem:
        try:
            item = self.components.get_exact(reference.kind, reference.version_id)
        except LibraryItemNotFoundError as error:
            raise AssessmentPipelineError(
                "pipeline.component_missing",
                f"exact component {reference.kind.value}:{reference.version_id} is missing",
            ) from error
        if not hasattr(item, "content_hash"):
            raise AssessmentPipelineError(
                "pipeline.component_type_mismatch",
                "exact component is not a versioned execution record",
            )
        versioned = cast(VersionLibraryItem, item)
        if (
            versioned.content_hash != reference.content_hash
            or component_content_hash(versioned) != reference.content_hash
        ):
            raise AssessmentPipelineError(
                "pipeline.component_pin_mismatch",
                f"exact component {reference.kind.value}:{reference.version_id} changed",
            )
        return versioned

    def _source_catalog(self, scheme: AssessmentSchemeVersion) -> SourceCatalog:
        descriptors: list[SourceDescriptor] = []
        for reference in scheme.source_descriptors:
            item = self._load_exact(reference)
            if not isinstance(item, SourceDescriptor):
                raise AssessmentPipelineError(
                    "pipeline.source_type_mismatch",
                    "scheme source reference has an unexpected contract type",
                )
            descriptors.append(item)
        return SourceCatalog(descriptors)

    def _put_contract(
        self,
        contract: BaseModel,
        *,
        result_id: str,
        role: str,
        schema_id: str,
        owners: list[ArtifactOwner],
    ) -> ArtifactIdRef:
        return self._put_json(
            cast(dict[str, JsonValue], contract.model_dump(mode="json")),
            result_id=result_id,
            role=role,
            schema_id=schema_id,
            owners=owners,
        )

    def _put_json(
        self,
        payload: Mapping[str, JsonValue],
        *,
        result_id: str,
        role: str,
        schema_id: str,
        owners: list[ArtifactOwner],
    ) -> ArtifactIdRef:
        owner = ArtifactOwner(
            owner_kind=ArtifactOwnerKind.RUN_RESULT,
            owner_id=result_id,
            role=role,
        )
        transaction_digest = hashlib.sha256(f"{result_id}\0{role}".encode()).hexdigest()
        artifact = self.artifacts.put_bytes(
            encode_canonical_json(dict(payload)),
            transaction_id=f"tx.artifact.{transaction_digest[:32]}",
            media_type="application/json",
            schema_id=schema_id,
            owner=owner,
        )
        owners.append(owner)
        return _artifact_ref(artifact)

    @staticmethod
    def _computed_evidence_payload(
        evidence: EvidenceVersion,
        bindings: tuple[EvidenceBindingVersion, ...],
        execution: RecipeExecutionResult,
    ) -> dict[str, JsonValue]:
        return {
            "contract_id": "evidence-runtime-result",
            "contract_version": "0.1.0",
            "evidence_version_id": evidence.evidence_version_id,
            "evidence_binding_version_ids": [
                binding.evidence_binding_version_id for binding in bindings
            ],
            "calculation_status": "computed",
            "primary_value": _portable_json(execution.scoring_input, "scoring input"),
            "scoring_outputs": _portable_json(
                execution.scoring_outputs,
                "scoring outputs",
            ),
        }

    @staticmethod
    def _omitted_evidence_payload(
        evidence: EvidenceVersion,
        bindings: tuple[EvidenceBindingVersion, ...],
        resolved: ResolvedRecipeInputs,
    ) -> dict[str, JsonValue]:
        return {
            "contract_id": "evidence-runtime-result",
            "contract_version": "0.1.0",
            "evidence_version_id": evidence.evidence_version_id,
            "evidence_binding_version_ids": [
                binding.evidence_binding_version_id for binding in bindings
            ],
            "calculation_status": "missing_input",
            "omitted_binding_ids": list(resolved.omitted_binding_ids),
            "primary_value": None,
            "scoring_outputs": {},
        }

    @staticmethod
    def _execution_trace_payload(
        evidence: EvidenceVersion,
        execution: RecipeExecutionResult,
    ) -> dict[str, JsonValue]:
        return {
            "contract_id": "evidence-runtime-trace",
            "contract_version": "0.1.0",
            "evidence_version_id": evidence.evidence_version_id,
            "recipe_id": execution.recipe_id,
            "recipe_version": execution.recipe_version,
            "nodes": [
                {
                    "node_id": trace.node_id,
                    "operator_id": trace.operator_id,
                    "operator_version": trace.operator_version,
                    "input_ports": list(trace.input_ports),
                    "output_ports": list(trace.output_ports),
                }
                for trace in execution.traces
            ],
        }

    @staticmethod
    def _source_trace_payload(
        evidence: EvidenceVersion,
        resolved: ResolvedRecipeInputs,
    ) -> dict[str, JsonValue]:
        return {
            "contract_id": "evidence-runtime-trace",
            "contract_version": "0.1.0",
            "evidence_version_id": evidence.evidence_version_id,
            "recipe_id": evidence.recipe.recipe_id,
            "recipe_version": evidence.recipe.recipe_version,
            "nodes": [],
            "source_diagnostics": [
                {
                    "code": item.code,
                    "source_id": item.source_id,
                    "message": item.message,
                    "dependency_path": list(item.dependency_path),
                }
                for item in resolved.diagnostics
            ],
        }


__all__ = [
    "AssessmentPipeline",
    "AssessmentPipelineError",
    "CancellationProbe",
    "ProgressSink",
    "RunResultIntegrityError",
    "RunResultNotFoundError",
    "RunResultRepository",
    "RunResultRepositoryError",
    "result_envelope_hash",
]
