from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import polars as pl
import pytest

from pilot_assessment.anchors.artifacts import InMemoryDerivedArtifactSink
from pilot_assessment.anchors.catalog import (
    load_parameter_schema,
    parameter_schema_sha256,
)
from pilot_assessment.anchors.fingerprint import (
    execution_plan_fingerprint_payload,
    parameter_snapshot_fingerprint,
    plugin_definition_fingerprint,
    preprocessing_definition_fingerprint,
    resolved_reference_set_fingerprint,
    session_semantic_snapshot_fingerprint,
    typed_json_sha256,
)
from pilot_assessment.anchors.models import (
    AnchorEvaluationRequest,
    AnchorRequestValidationError,
    ResolvedReferenceSet,
)
from pilot_assessment.anchors.protocols import TabularArtifactPayload
from pilot_assessment.anchors.registry import PluginRegistry
from pilot_assessment.anchors.scoring import compile_scorer_policy
from pilot_assessment.contracts.anchor_execution import (
    AnchorApplicability,
    AnchorArtifactRecipe,
    AnchorDependency,
    AnchorExecutionEntry,
    AnchorExecutionPlan,
    AnchorPluginDefinition,
    ControlEffectMapping,
    DependencyKind,
    EnvelopeAxisLimit,
    EnvelopeDefinition,
    PreprocessingProviderDefinition,
    ResolvedAlgorithmProfile,
    ResolvedPreprocessingRecipe,
    ResolvedReferenceSetSnapshot,
    SemanticApplicabilityStatus,
    SemanticVector,
    SessionSemanticSnapshot,
    TaskTargetDefinition,
)
from pilot_assessment.contracts.anchor_v2 import (
    AnchorCalculationStatusV2,
    AnchorMeasurement,
    ComputationTrace,
    MetricValue,
)
from pilot_assessment.contracts.errors import DomainErrorData, ErrorSeverity
from pilot_assessment.contracts.session import CoreModality
from pilot_assessment.contracts.synchronization import SynchronizationItemStatus
from tests.anchors.test_dag import _definition, _entry, _plan
from tests.anchors.test_preprocessing import _definition as _provider_definition
from tests.anchors.test_preprocessing import _recipe as _provider_recipe
from tests.anchors.test_request_validation import (
    _input_contract,
    _report,
    _resolved_empty,
    _semantic,
    _session,
)


def _trace() -> ComputationTrace:
    return ComputationTrace(
        sample_count=1,
        source_start_t_ns=0,
        source_end_t_ns=1,
        analysis_start_t_ns=0,
        analysis_end_t_ns=1,
        grid_id=None,
        window_ids=(),
        interpolation_method="none",
        matching_method="direct",
        diagnostics=(),
    )


def _measurement(
    anchor_id: str,
    value: float = 95.0,
    unit: str = "percent",
) -> AnchorMeasurement:
    return AnchorMeasurement(
        anchor_id=anchor_id,
        calculation_status=AnchorCalculationStatusV2.COMPUTED,
        primary_value=MetricValue(scalar_kind="float", value=value, unit=unit),
        primary_value_reason=None,
        raw_metrics={},
        phase_results=(),
        event_results=(),
        classification_override_candidate=None,
        source_windows=(),
        derived_artifacts=(),
        trace=_trace(),
        diagnostics=(),
    )


def _entry_definition(entry: AnchorExecutionEntry) -> AnchorPluginDefinition:
    return AnchorPluginDefinition(
        anchor_id=entry.anchor_id,
        definition_version=entry.definition_version,
        plugin_id=entry.plugin_id,
        plugin_version=entry.plugin_version,
        api_version=entry.api_version,
        required_streams=entry.required_streams,
        required_context_paths=entry.required_context_paths,
        required_semantic_paths=entry.required_semantic_paths,
        required_reference_ids=entry.required_reference_ids,
        dependencies=entry.dependencies,
        parameter_schema_id=entry.parameter_schema_id,
        measurement_schema_id=entry.measurement_schema_id,
        artifact_recipes=entry.artifact_recipes,
    )


class _Plugin:
    def __init__(
        self,
        entry: AnchorExecutionEntry,
        calls: list[dict[str, Any]],
        *,
        fail: bool = False,
    ) -> None:
        self._entry = entry
        self._calls = calls
        self._fail = fail

    def definition(self):
        return _entry_definition(self._entry)

    def compute(self, context, parameters, temporal_recipe, dependencies, artifacts):
        self._calls.append(
            {
                "context": context,
                "parameters": parameters,
                "temporal_recipe": temporal_recipe,
                "dependencies": dependencies,
                "artifacts": artifacts,
            }
        )
        if self._fail:
            raise RuntimeError("simulated plugin failure")
        unit = "percent_full_travel" if self._entry.anchor_id == "O6" else "percent"
        return _measurement(self._entry.anchor_id, unit=unit)


class _FailingProvider:
    def __init__(self, definition: PreprocessingProviderDefinition, calls: list[object]) -> None:
        self._definition = definition
        self._calls = calls

    def definition(self) -> PreprocessingProviderDefinition:
        return self._definition

    def compute(self, *args: object, **kwargs: object) -> TabularArtifactPayload:
        self._calls.append((args, kwargs))
        raise RuntimeError("simulated provider failure")


class _SuccessfulProvider:
    def __init__(self, definition: PreprocessingProviderDefinition, calls: list[object]) -> None:
        self._definition = definition
        self._calls = calls

    def definition(self) -> PreprocessingProviderDefinition:
        return self._definition

    def compute(self, context, recipe, scope, dependencies) -> TabularArtifactPayload:
        self._calls.append((context, recipe, scope, dependencies))
        return TabularArtifactPayload(
            schema_id=recipe.output_schema_id,
            schema_descriptor=recipe.output_schema_descriptor,
            frame=pl.DataFrame(
                {"event_id": ["event-1"], "t_ns": [scope.start_t_ns]},
                schema={"event_id": pl.String, "t_ns": pl.Int64},
            ),
            order_keys=("t_ns", "event_id"),
            artifact_kind=recipe.artifact_kind,
            grid_hash=None,
            start_t_ns=scope.start_t_ns,
            end_t_ns=scope.end_t_ns,
        )


class _SpySink(InMemoryDerivedArtifactSink):
    def __init__(self) -> None:
        super().__init__()
        self.begin_calls = 0

    def begin_evaluation(self, evaluation_key: str):
        self.begin_calls += 1
        return super().begin_evaluation(evaluation_key)


def _canonical_semantic(anchor_ids: tuple[str, ...]):
    semantic = _semantic()
    base = semantic.applicability[0]
    semantic = semantic.model_copy(
        update={
            "applicability": tuple(
                base.model_copy(update={"anchor_id": anchor_id}) for anchor_id in anchor_ids
            )
        }
    )
    return semantic.model_copy(
        update={"semantic_snapshot_fingerprint": session_semantic_snapshot_fingerprint(semantic)}
    )


def _canonical_references() -> ResolvedReferenceSet:
    references = _resolved_empty()
    snapshot = ResolvedReferenceSetSnapshot(
        session_identity=references.session_identity,
        descriptors=(),
        reference_set_fingerprint=references.reference_set_fingerprint,
    )
    return ResolvedReferenceSet(
        session_identity=references.session_identity,
        entries={},
        reference_set_fingerprint=resolved_reference_set_fingerprint(snapshot),
    )


def _canonical_plan(
    entries: tuple[AnchorExecutionEntry, ...],
    semantic_fingerprint: str,
    reference_fingerprint: str,
    *,
    recipes: tuple[ResolvedPreprocessingRecipe, ...] = (),
    contracts: tuple[object, ...] | None = None,
) -> AnchorExecutionPlan:
    draft = _plan(entries, recipes).model_copy(
        update={
            "input_table_contracts": contracts or (_input_contract(),),
            "semantic_snapshot_fingerprint": semantic_fingerprint,
            "reference_set_fingerprint": reference_fingerprint,
        }
    )
    return draft.model_copy(
        update={
            "plan_fingerprint": typed_json_sha256(
                draft.contract_id,
                draft.contract_version,
                execution_plan_fingerprint_payload(draft),
            )
        }
    )


def _request(
    entries: tuple[AnchorExecutionEntry, ...],
    *,
    recipes: tuple[ResolvedPreprocessingRecipe, ...] = (),
    contracts: tuple[object, ...] | None = None,
    synchronization_report=None,
) -> AnchorEvaluationRequest:
    semantic = _canonical_semantic(tuple(entry.anchor_id for entry in entries))
    references = _canonical_references()
    plan = _canonical_plan(
        entries,
        semantic.semantic_snapshot_fingerprint,
        references.reference_set_fingerprint,
        recipes=recipes,
        contracts=contracts,
    )
    return AnchorEvaluationRequest(
        aligned_session=_session(),
        synchronization_report=synchronization_report or _report(),
        session_semantic_snapshot=semantic,
        execution_plan=plan,
        resolved_references=references,
    )


def _o6_request(
    mappings: tuple[ControlEffectMapping, ...],
    weights: list[dict[str, object]],
    *,
    applicable: bool = True,
) -> tuple[AnchorEvaluationRequest, AnchorExecutionEntry]:
    parameters = {"channel_weights": weights}
    scorer_annotation = load_parameter_schema("o6-parameters-0.1")["x-scorer-policy-default"]
    assert isinstance(scorer_annotation, Mapping)
    entry = _entry("O6", 0).model_copy(
        update={
            "parameter_schema_id": "o6-parameters-0.1",
            "parameters": parameters,
            "parameter_hash": parameter_snapshot_fingerprint(parameters),
            "scorer_policy": compile_scorer_policy(scorer_annotation),
            "applicability": (
                SemanticApplicabilityStatus.APPLICABLE
                if applicable
                else SemanticApplicabilityStatus.NOT_APPLICABLE
            ),
            "phase_scope": ("phase-1",) if applicable else (),
        }
    )
    entry = entry.model_copy(
        update={"definition_fingerprint": plugin_definition_fingerprint(_entry_definition(entry))}
    )
    base = _request((_entry("O1", 0),))
    semantic = base.session_semantic_snapshot.model_copy(
        update={
            "control_mappings": mappings if applicable else (),
            "applicability": (
                AnchorApplicability(
                    anchor_id="O6",
                    status="applicable",
                    phase_ids=("phase-1",),
                    control_mapping_ids=tuple(mapping.control_mapping_id for mapping in mappings),
                )
                if applicable
                else AnchorApplicability(
                    anchor_id="O6",
                    status="not_applicable",
                    reason="not-configured",
                ),
            ),
        }
    )
    semantic = semantic.model_copy(
        update={"semantic_snapshot_fingerprint": session_semantic_snapshot_fingerprint(semantic)}
    )
    plan = _canonical_plan(
        (entry,),
        semantic.semantic_snapshot_fingerprint,
        base.resolved_references.reference_set_fingerprint,
    )
    return (
        AnchorEvaluationRequest(
            aligned_session=base.aligned_session,
            synchronization_report=base.synchronization_report,
            session_semantic_snapshot=semantic,
            execution_plan=plan,
            resolved_references=base.resolved_references,
        ),
        entry,
    )


def _control_mapping(
    mapping_id: str,
    channel_id: str,
    *,
    upper: float = 1.0,
) -> ControlEffectMapping:
    return ControlEffectMapping(
        control_mapping_id=mapping_id,
        state_axis_id=f"axis-{mapping_id}",
        control_channel_id=channel_id,
        correct_sign=1,
        state_unit="m",
        control_unit="ratio",
        lower=-1.0,
        trim=0.0,
        upper=upper,
    )


def _o13_request_and_registry() -> tuple[
    AnchorEvaluationRequest,
    PluginRegistry,
    dict[str, list[dict[str, Any]]],
    list[object],
]:
    movement_definition = _provider_definition("movement-events-v1").model_copy(
        update={"required_streams": (CoreModality.X,)}
    )
    movement_recipe = _provider_recipe("movement-events-v1", "movement-events-v1").model_copy(
        update={
            "required_streams": (CoreModality.X,),
            "definition_fingerprint": preprocessing_definition_fingerprint(movement_definition),
        }
    )
    movement_dependency = AnchorDependency(
        dependency_id="movement-events",
        kind=DependencyKind.PREPROCESSING,
        target_resource_id=movement_recipe.recipe_id,
        expected_schema_id=movement_recipe.output_schema_id,
        expected_artifact_kind=movement_recipe.artifact_kind,
        required=True,
    )
    o1 = _entry("O1", 0)
    o5 = _entry("O5", 1, (movement_dependency,))
    o7 = _entry("O7", 2, (movement_dependency,))
    h4 = _entry("H4", 4)
    profile_dependencies = tuple(
        AnchorDependency(
            dependency_id=f"{anchor_id.lower()}-profile",
            kind=DependencyKind.ALGORITHM_PROFILE,
            target_resource_id=f"{anchor_id.lower()}-algorithm-profile",
            expected_schema_id=f"{anchor_id.lower()}-algorithm-profile-output-v0.1",
            required=True,
        )
        for anchor_id in ("O1", "O5", "O7")
    )
    h4_dependency = AnchorDependency(
        dependency_id="h4-result",
        kind=DependencyKind.RESULT,
        target_anchor_id="H4",
        expected_schema_id=h4.result_schema_id,
        required=True,
    )
    o13 = _entry("O13", 3, (*profile_dependencies, h4_dependency))
    entries = (o1, o5, o7, o13, h4)

    base = _request((_entry("O1", 0),))
    base_phase = base.session_semantic_snapshot.phases[0]
    phase = base_phase.model_copy(update={"target_id": "target-1", "envelope_id": "envelope-1"})
    target = TaskTargetDefinition(
        target_id="target-1",
        position=SemanticVector(
            coordinate_frame_id="world",
            unit="m",
            values=(0.0, 0.0, 0.0),
        ),
    )
    envelope = EnvelopeDefinition(
        envelope_id="envelope-1",
        target_id=target.target_id,
        axis_limits=(
            EnvelopeAxisLimit(
                metric_id="position-error",
                desired_abs_max=1.0,
                adequate_abs_max=2.0,
                unit="m",
            ),
        ),
    )
    mapping = _control_mapping("mapping-a", "stick-x")
    applicability = (
        AnchorApplicability(anchor_id="H4", status="applicable", phase_ids=("phase-1",)),
        AnchorApplicability(
            anchor_id="O1",
            status="applicable",
            phase_ids=("phase-1",),
            target_ids=(target.target_id,),
            envelope_ids=(envelope.envelope_id,),
        ),
        AnchorApplicability(anchor_id="O13", status="applicable", phase_ids=("phase-1",)),
        AnchorApplicability(
            anchor_id="O5",
            status="applicable",
            phase_ids=("phase-1",),
            control_mapping_ids=(mapping.control_mapping_id,),
        ),
        AnchorApplicability(
            anchor_id="O7",
            status="applicable",
            phase_ids=("phase-1",),
            control_mapping_ids=(mapping.control_mapping_id,),
        ),
    )
    semantic_data = base.session_semantic_snapshot.model_dump(mode="python")
    semantic_data.update(
        {
            "phases": (phase,),
            "control_mappings": (mapping,),
            "targets": (target,),
            "envelopes": (envelope,),
            "applicability": applicability,
        }
    )
    semantic = SessionSemanticSnapshot.model_validate(semantic_data)
    semantic = semantic.model_copy(
        update={"semantic_snapshot_fingerprint": session_semantic_snapshot_fingerprint(semantic)}
    )
    input_contract = _input_contract()
    entry_by_id = {entry.anchor_id: entry for entry in entries}
    applicability_by_id = {item.anchor_id: item for item in semantic.applicability}
    output_schemas = {
        "O1": "o1-algorithm-profile-output-v0.1",
        "O5": "o5-algorithm-profile-output-v0.1",
        "O7": "o7-algorithm-profile-output-v0.1",
    }
    profiles = []
    for anchor_id in ("O1", "O5", "O7"):
        source_entry = entry_by_id[anchor_id]
        source_applicability = applicability_by_id[anchor_id]
        parameters = {
            "semantic_snapshot_fingerprint": semantic.semantic_snapshot_fingerprint,
            "source_entry": source_entry.model_dump(mode="json"),
            "parameter_schema_sha256": parameter_schema_sha256(source_entry.parameter_schema_id),
            "applicability": source_applicability.model_dump(mode="json"),
            "input_table_contracts": [input_contract.model_dump(mode="json")],
            "semantic_projection": {
                "phases": [phase.model_dump(mode="json")],
                "envelopes": ([envelope.model_dump(mode="json")] if anchor_id == "O1" else []),
                "control_mappings": (
                    [mapping.model_dump(mode="json")] if anchor_id in {"O5", "O7"} else []
                ),
            },
            "preprocessing_recipes": (
                [movement_recipe.model_dump(mode="json")] if anchor_id in {"O5", "O7"} else []
            ),
        }
        profiles.append(
            ResolvedAlgorithmProfile(
                profile_id=f"{anchor_id.lower()}-algorithm-profile",
                profile_version=source_entry.definition_version,
                parameters=parameters,
                parameter_hash=parameter_snapshot_fingerprint(parameters),
                implementation_digest=source_entry.implementation_digest,
                output_schema_id=output_schemas[anchor_id],
            )
        )

    skeleton_o13 = _entry("O13", 3, (h4_dependency,))
    skeleton_plan = _plan((o1, o5, o7, skeleton_o13, h4), (movement_recipe,))
    draft = skeleton_plan.model_copy(
        update={
            "entries": entries,
            "input_table_contracts": (input_contract,),
            "algorithm_profiles": tuple(profiles),
            "semantic_snapshot_fingerprint": semantic.semantic_snapshot_fingerprint,
            "reference_set_fingerprint": base.resolved_references.reference_set_fingerprint,
        }
    )
    plan = draft.model_copy(
        update={
            "plan_fingerprint": typed_json_sha256(
                draft.contract_id,
                draft.contract_version,
                execution_plan_fingerprint_payload(draft),
            )
        }
    )
    request = AnchorEvaluationRequest(
        aligned_session=base.aligned_session,
        synchronization_report=base.synchronization_report,
        session_semantic_snapshot=semantic,
        execution_plan=plan,
        resolved_references=base.resolved_references,
    )
    calls: dict[str, list[dict[str, Any]]] = {}
    provider_calls: list[object] = []

    def provider_factory() -> _FailingProvider:
        return _FailingProvider(movement_definition, provider_calls)

    registry = _registry(
        entries,
        calls,
        providers={
            (movement_recipe.provider_id, movement_recipe.provider_version): provider_factory
        },
    )
    return request, registry, calls, provider_calls


def _registry(
    entries: tuple[AnchorExecutionEntry, ...],
    calls: dict[str, list[dict[str, Any]]],
    *,
    failing: set[str] | None = None,
    providers: Mapping[tuple[str, str], Any] | None = None,
) -> PluginRegistry:
    failing = failing or set()
    factories = {}
    for entry in entries:
        anchor_calls = calls.setdefault(entry.anchor_id, [])
        factories[(entry.plugin_id, entry.plugin_version)] = (
            lambda entry=entry, anchor_calls=anchor_calls: _Plugin(
                entry,
                anchor_calls,
                fail=entry.anchor_id in failing,
            )
        )
    return PluginRegistry.from_factories_for_testing(factories, providers or {})


def _policy():
    from pilot_assessment.anchors.dag import EvaluationPolicy

    return EvaluationPolicy(
        require_packaged_registry_fingerprint=False,
        allow_injected_test_profile_ids=True,
    )


def test_evaluator_runs_valid_plugin_and_builds_canonical_complete_report() -> None:
    from pilot_assessment.anchors.service import AnchorEvaluator

    entry = _entry("O1", 0)
    request = _request((entry,))
    calls: dict[str, list[dict[str, Any]]] = {}
    sink = _SpySink()

    report = AnchorEvaluator.for_testing(_registry((entry,), calls), _policy()).evaluate(
        request, sink
    )

    assert report.disposition.value == "ready"
    assert tuple(item.anchor_id for item in report.inventory) == ("O1",)
    assert tuple(item.anchor_id for item in report.results) == ("O1",)
    assert report.raw_availability == 1.0
    assert report.results[0].evidence_state.value == "desired"
    assert len(calls["O1"]) == 1
    assert set(calls["O1"][0]["context"].streams) == {"X"}
    assert calls["O1"][0]["temporal_recipe"] == entry.temporal_recipe
    assert sink.begin_calls == 1


def test_injected_registry_is_available_only_through_for_testing() -> None:
    from pilot_assessment.anchors.service import AnchorEvaluator

    entry = _entry("O1", 0)
    calls: dict[str, list[dict[str, Any]]] = {}

    with pytest.raises(ValueError, match="for_testing"):
        AnchorEvaluator(_registry((entry,), calls), _policy())


def test_injected_plan_requires_both_test_plan_and_profile_ids_before_sink_access() -> None:
    from pilot_assessment.anchors.service import AnchorEvaluator

    entry = _entry("O1", 0)
    request = _request((entry,))
    draft = request.execution_plan.model_copy(update={"plan_id": "production-plan"})
    plan = draft.model_copy(
        update={
            "plan_fingerprint": typed_json_sha256(
                draft.contract_id,
                draft.contract_version,
                execution_plan_fingerprint_payload(draft),
            )
        }
    )
    request = AnchorEvaluationRequest(
        aligned_session=request.aligned_session,
        synchronization_report=request.synchronization_report,
        session_semantic_snapshot=request.session_semantic_snapshot,
        execution_plan=plan,
        resolved_references=request.resolved_references,
    )
    calls: dict[str, list[dict[str, Any]]] = {}
    sink = _SpySink()

    report = AnchorEvaluator.for_testing(_registry((entry,), calls), _policy()).evaluate(
        request, sink
    )

    assert report.disposition.value == "blocked"
    assert report.diagnostics[0].error_code == "anchor.plan.test_profile_required"
    assert calls["O1"] == []
    assert sink.begin_calls == 0


def test_o6_accepts_canonical_weights_and_equal_duplicate_channel_calibration() -> None:
    from pilot_assessment.anchors.service import AnchorEvaluator

    mappings = (
        _control_mapping("mapping-a", "stick-x"),
        _control_mapping("mapping-b", "stick-x"),
    )
    request, entry = _o6_request(
        mappings,
        [{"channel_id": "stick-x", "weight": 1.0}],
    )
    calls: dict[str, list[dict[str, Any]]] = {}

    report = AnchorEvaluator.for_testing(_registry((entry,), calls), _policy()).evaluate(
        request, _SpySink()
    )

    assert report.disposition.value == "ready"
    assert report.results[0].calculation_status.value == "computed"
    assert len(calls["O6"]) == 1


def test_o6_rejects_conflict_inventory_duplicates_and_non_unit_weights_before_side_effects() -> (
    None
):
    from pilot_assessment.anchors.service import AnchorEvaluator

    cases = (
        (
            (
                _control_mapping("mapping-a", "stick-x"),
                _control_mapping("mapping-b", "stick-x", upper=2.0),
            ),
            [{"channel_id": "stick-x", "weight": 1.0}],
        ),
        (
            (
                _control_mapping("mapping-a", "stick-x"),
                _control_mapping("mapping-b", "stick-y"),
            ),
            [{"channel_id": "stick-x", "weight": 1.0}],
        ),
        (
            (_control_mapping("mapping-a", "stick-x"),),
            [
                {"channel_id": "stick-x", "weight": 0.5},
                {"channel_id": "stick-x", "weight": 0.5},
            ],
        ),
        (
            (_control_mapping("mapping-a", "stick-x"),),
            [{"channel_id": "stick-x", "weight": 0.9}],
        ),
        (
            (_control_mapping("mapping-a", "stick-x"),),
            [
                {"channel_id": "stick-x", "weight": 0.5},
                {"channel_id": "stick-y", "weight": 0.5},
            ],
        ),
    )

    for mappings, weights in cases:
        request, entry = _o6_request(mappings, weights)
        calls: dict[str, list[dict[str, Any]]] = {}
        sink = _SpySink()
        report = AnchorEvaluator.for_testing(_registry((entry,), calls), _policy()).evaluate(
            request, sink
        )
        assert report.disposition.value == "blocked"
        assert report.diagnostics[0].error_code in {
            "anchor.plan.o6_parameter_mismatch",
            "anchor.plan.o6_semantic_mismatch",
        }
        assert calls["O6"] == []
        assert sink.begin_calls == 0


def test_o6_not_applicable_requires_exact_empty_weights() -> None:
    from pilot_assessment.anchors.service import AnchorEvaluator

    valid_request, valid_entry = _o6_request((), [], applicable=False)
    valid_calls: dict[str, list[dict[str, Any]]] = {}
    report = AnchorEvaluator.for_testing(
        _registry((valid_entry,), valid_calls), _policy()
    ).evaluate(valid_request, _SpySink())
    assert report.results[0].calculation_status.value == "not_applicable"
    assert valid_calls["O6"] == []

    invalid_request, invalid_entry = _o6_request(
        (), [{"channel_id": "stick-x", "weight": 1.0}], applicable=False
    )
    invalid_calls: dict[str, list[dict[str, Any]]] = {}
    sink = _SpySink()
    report = AnchorEvaluator.for_testing(
        _registry((invalid_entry,), invalid_calls), _policy()
    ).evaluate(invalid_request, sink)
    assert report.disposition.value == "blocked"
    assert report.diagnostics[0].error_code == "anchor.plan.o6_parameter_mismatch"
    assert invalid_calls["O6"] == []
    assert sink.begin_calls == 0


def test_o13_algorithm_profiles_match_the_exact_seven_key_authoritative_closure() -> None:
    from pilot_assessment.anchors.dag import validate_request_bound_execution_plan

    request, registry, calls, provider_calls = _o13_request_and_registry()

    outcome = validate_request_bound_execution_plan(request, registry)

    assert outcome.disposition == "valid"
    assert outcome.validated_plan is not None
    assert all(anchor_calls == [] for anchor_calls in calls.values())
    assert provider_calls == []


def test_o13_profile_closure_mutation_blocks_before_factory_or_sink_access() -> None:
    from pilot_assessment.anchors.service import AnchorEvaluator

    request, registry, calls, provider_calls = _o13_request_and_registry()
    profile = request.execution_plan.algorithm_profiles[0]
    mutated_parameters = dict(profile.parameters)
    mutated_parameters["unexpected"] = "not-authoritative"
    mutated_profile = ResolvedAlgorithmProfile(
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        parameters=mutated_parameters,
        parameter_hash=parameter_snapshot_fingerprint(mutated_parameters),
        implementation_digest=profile.implementation_digest,
        output_schema_id=profile.output_schema_id,
    )
    profiles = (mutated_profile, *request.execution_plan.algorithm_profiles[1:])
    draft = request.execution_plan.model_copy(update={"algorithm_profiles": profiles})
    plan = draft.model_copy(
        update={
            "plan_fingerprint": typed_json_sha256(
                draft.contract_id,
                draft.contract_version,
                execution_plan_fingerprint_payload(draft),
            )
        }
    )
    mutated_request = AnchorEvaluationRequest(
        aligned_session=request.aligned_session,
        synchronization_report=request.synchronization_report,
        session_semantic_snapshot=request.session_semantic_snapshot,
        execution_plan=plan,
        resolved_references=request.resolved_references,
    )
    sink = _SpySink()

    report = AnchorEvaluator.for_testing(registry, _policy()).evaluate(mutated_request, sink)

    assert report.disposition.value == "blocked"
    assert report.diagnostics[0].error_code == "anchor.plan.algorithm_profile_mismatch"
    assert all(anchor_calls == [] for anchor_calls in calls.values())
    assert provider_calls == []
    assert sink.begin_calls == 0


def test_valid_request_with_invalid_plan_returns_blocked_inventory_without_factories_or_sink() -> (
    None
):
    from pilot_assessment.anchors.service import AnchorEvaluator

    entry = _entry("O1", 0)
    request = _request((entry,))
    missing_definition = _definition("O1").model_copy(
        update={"plugin_id": "test-unregistered-plugin"}
    )
    missing_entry = entry.model_copy(
        update={
            "plugin_id": missing_definition.plugin_id,
            "definition_fingerprint": plugin_definition_fingerprint(missing_definition),
        }
    )
    semantic = request.session_semantic_snapshot
    references = request.resolved_references
    invalid_plan = _canonical_plan(
        (missing_entry,),
        semantic.semantic_snapshot_fingerprint,
        references.reference_set_fingerprint,
    )
    invalid_request = AnchorEvaluationRequest(
        aligned_session=request.aligned_session,
        synchronization_report=request.synchronization_report,
        session_semantic_snapshot=semantic,
        execution_plan=invalid_plan,
        resolved_references=references,
    )
    calls: dict[str, list[dict[str, Any]]] = {}
    sink = _SpySink()

    report = AnchorEvaluator.for_testing(_registry((entry,), calls), _policy()).evaluate(
        invalid_request, sink
    )

    assert report.disposition.value == "blocked"
    assert report.results == ()
    assert tuple(item.anchor_id for item in report.inventory) == ("O1",)
    assert report.inventory[0].global_block_reason == "plan_invalid"
    assert calls["O1"] == []
    assert sink.begin_calls == 0


def test_global_evaluation_commit_failure_aborts_results_and_returns_blocked_report() -> None:
    from pilot_assessment.anchors.service import AnchorEvaluator

    entry = _entry("O1", 0)
    request = _request((entry,))
    calls: dict[str, list[dict[str, Any]]] = {}

    class CommitFailureProxy:
        def __init__(self, transaction: object) -> None:
            self._transaction = transaction

        def __getattr__(self, name: str):
            return getattr(self._transaction, name)

        def commit(self) -> None:
            raise RuntimeError("simulated evaluation commit failure")

    class CommitFailingSink(_SpySink):
        def begin_evaluation(self, evaluation_key: str):
            return CommitFailureProxy(super().begin_evaluation(evaluation_key))

    sink = CommitFailingSink()
    report = AnchorEvaluator.for_testing(_registry((entry,), calls), _policy()).evaluate(
        request, sink
    )

    assert report.disposition.value == "blocked"
    assert report.results == ()
    assert report.inventory[0].global_block_reason == "transaction_failed"
    assert report.diagnostics[0].error_code == "anchor.transaction.finalization_failed"
    assert len(calls["O1"]) == 1
    assert sink.begin_calls == 1


def test_plugin_failure_is_consumer_local_and_report_order_stays_canonical() -> None:
    from pilot_assessment.anchors.service import AnchorEvaluator

    entries = (_entry("O1", 0), _entry("O2", 1))
    request = _request(entries)
    calls: dict[str, list[dict[str, Any]]] = {}
    report = AnchorEvaluator.for_testing(
        _registry(entries, calls, failing={"O1"}), _policy()
    ).evaluate(request, _SpySink())

    assert tuple(result.anchor_id for result in report.results) == ("O1", "O2")
    assert tuple(result.calculation_status.value for result in report.results) == (
        "extractor_error",
        "computed",
    )
    assert report.disposition.value == "ready_partial"
    assert len(calls["O1"]) == 1
    assert len(calls["O2"]) == 1


def test_computed_unacceptable_result_remains_available_to_required_downstream() -> None:
    from pilot_assessment.anchors.service import AnchorEvaluator

    producer = _entry("O1", 0)
    dependency = AnchorDependency(
        dependency_id="o1-result",
        kind=DependencyKind.RESULT,
        target_anchor_id="O1",
        expected_schema_id=producer.result_schema_id,
        required=True,
    )
    consumer = _entry("O2", 1, (dependency,))
    consumer_calls: list[dict[str, Any]] = []

    class UnacceptablePlugin:
        def definition(self):
            return _entry_definition(producer)

        def compute(self, *args: object, **kwargs: object):
            del args, kwargs
            return _measurement("O1", value=0.0)

    registry = PluginRegistry.from_factories_for_testing(
        {
            (producer.plugin_id, producer.plugin_version): UnacceptablePlugin,
            (consumer.plugin_id, consumer.plugin_version): lambda: _Plugin(
                consumer, consumer_calls
            ),
        },
        {},
    )
    report = AnchorEvaluator.for_testing(registry, _policy()).evaluate(
        _request((producer, consumer)), _SpySink()
    )

    assert report.results[0].calculation_status.value == "computed"
    assert report.results[0].evidence_state.value == "unacceptable"
    assert report.results[1].calculation_status.value == "computed"
    assert consumer_calls[0]["dependencies"].results["o1-result"].evidence_state.value == (
        "unacceptable"
    )


def test_missing_optional_artifact_does_not_block_consumer_with_required_result() -> None:
    from pilot_assessment.anchors.service import AnchorEvaluator

    descriptor = {
        "type": "table",
        "fields": [{"name": "t_ns", "dtype": "i64", "unit": "ns", "nullable": False}],
        "canonical_order_keys": ["t_ns"],
    }
    artifact_recipe = AnchorArtifactRecipe(
        artifact_id="optional-trace",
        kind="window_trace",
        schema_id="test-optional-trace-v0.1",
        schema_descriptor=descriptor,
        payload_kind="table",
    )
    producer = _entry("O1", 0).model_copy(update={"artifact_recipes": (artifact_recipe,)})
    producer = producer.model_copy(
        update={
            "definition_fingerprint": plugin_definition_fingerprint(_entry_definition(producer))
        }
    )
    required_result = AnchorDependency(
        dependency_id="producer-result",
        kind=DependencyKind.RESULT,
        target_anchor_id="O1",
        expected_schema_id=producer.result_schema_id,
        required=True,
    )
    optional_artifact = AnchorDependency(
        dependency_id="producer-optional-trace",
        kind=DependencyKind.ARTIFACT,
        target_anchor_id="O1",
        target_resource_id=artifact_recipe.artifact_id,
        expected_schema_id=artifact_recipe.schema_id,
        expected_artifact_kind=artifact_recipe.kind,
        required=False,
    )
    consumer = _entry("O2", 1, (required_result, optional_artifact))
    entries = (producer, consumer)
    request = _request(entries)
    calls: dict[str, list[dict[str, Any]]] = {}

    report = AnchorEvaluator.for_testing(_registry(entries, calls), _policy()).evaluate(
        request, _SpySink()
    )

    assert tuple(result.calculation_status.value for result in report.results) == (
        "computed",
        "computed",
    )
    assert tuple(calls["O2"][0]["dependencies"].results) == ("producer-result",)
    assert calls["O2"][0]["dependencies"].artifacts == {}


def test_provider_failure_only_marks_the_dependent_anchor() -> None:
    from pilot_assessment.anchors.service import AnchorEvaluator

    recipe = _provider_recipe("events", "test-provider").model_copy(
        update={"required_streams": (CoreModality.X,)}
    )
    provider_definition = _provider_definition("test-provider").model_copy(
        update={"required_streams": (CoreModality.X,)}
    )
    recipe = recipe.model_copy(
        update={"definition_fingerprint": preprocessing_definition_fingerprint(provider_definition)}
    )
    dependency = AnchorDependency(
        dependency_id="events",
        kind=DependencyKind.PREPROCESSING,
        target_resource_id=recipe.recipe_id,
        expected_schema_id=recipe.output_schema_id,
        expected_artifact_kind=recipe.artifact_kind,
        required=True,
    )
    entries = (_entry("O1", 0), _entry("O2", 1, (dependency,)))
    request = _request(entries, recipes=(recipe,))
    plugin_calls: dict[str, list[dict[str, Any]]] = {}
    provider_calls: list[object] = []

    def provider_factory() -> _FailingProvider:
        return _FailingProvider(provider_definition, provider_calls)

    registry = _registry(
        entries,
        plugin_calls,
        providers={(recipe.provider_id, recipe.provider_version): provider_factory},
    )

    report = AnchorEvaluator.for_testing(registry, _policy()).evaluate(request, _SpySink())

    assert tuple(result.calculation_status.value for result in report.results) == (
        "computed",
        "dependency_missing",
    )
    assert len(plugin_calls["O1"]) == 1
    assert plugin_calls["O2"] == []
    assert len(provider_calls) == 1


def test_preprocessing_fault_hook_is_consumer_local_and_preserves_memoized_product() -> None:
    from pilot_assessment.anchors.dag import TestFaultHooks
    from pilot_assessment.anchors.service import AnchorEvaluator

    provider_definition = _provider_definition("movement-events-v1").model_copy(
        update={"required_streams": (CoreModality.X,)}
    )
    recipe = _provider_recipe("movement-events-v1", "movement-events-v1").model_copy(
        update={
            "required_streams": (CoreModality.X,),
            "definition_fingerprint": preprocessing_definition_fingerprint(provider_definition),
        }
    )
    dependency = AnchorDependency(
        dependency_id="movement-events",
        kind=DependencyKind.PREPROCESSING,
        target_resource_id=recipe.recipe_id,
        expected_schema_id=recipe.output_schema_id,
        expected_artifact_kind=recipe.artifact_kind,
        required=True,
    )
    entries = (_entry("O1", 0, (dependency,)), _entry("O2", 1, (dependency,)))
    plugin_calls: dict[str, list[dict[str, Any]]] = {}
    provider_calls: list[object] = []

    def provider_factory() -> _SuccessfulProvider:
        return _SuccessfulProvider(provider_definition, provider_calls)

    registry = _registry(
        entries,
        plugin_calls,
        providers={(recipe.provider_id, recipe.provider_version): provider_factory},
    )
    hook = DomainErrorData(
        error_code="test.preprocessing_projection_missing",
        severity=ErrorSeverity.ERROR,
        recoverable=True,
        message="simulated consumer-local preprocessing miss",
        remediation="test only",
    )
    evaluator = AnchorEvaluator.for_testing(
        registry,
        _policy(),
        TestFaultHooks(preprocessing_resolution_failures={("O1", recipe.recipe_id): hook}),
    )

    request = _request(entries, recipes=(recipe,))
    report = evaluator.evaluate(request, _SpySink())

    assert tuple(result.calculation_status.value for result in report.results) == (
        "dependency_missing",
        "computed",
    )
    assert hook in report.results[0].diagnostics
    assert plugin_calls["O1"] == []
    assert len(plugin_calls["O2"]) == 1
    assert len(provider_calls) == 1
    provider_context, _provider_recipe_value, _provider_scope, _provider_dependencies = (
        provider_calls[0]
    )
    assert provider_context.input_table_contracts == request.execution_plan.input_table_contracts


def test_idempotent_request_validation_rejects_stale_semantics_before_any_side_effect() -> None:
    from pilot_assessment.anchors.service import AnchorEvaluator

    entry = _entry("O1", 0)
    request = _request((entry,))
    stale_semantic = request.session_semantic_snapshot.model_copy(
        update={"scenario_id": "scenario-2"}
    )
    stale_request = AnchorEvaluationRequest(
        aligned_session=request.aligned_session,
        synchronization_report=request.synchronization_report,
        session_semantic_snapshot=stale_semantic,
        execution_plan=request.execution_plan,
        resolved_references=request.resolved_references,
    )
    calls: dict[str, list[dict[str, Any]]] = {}
    sink = _SpySink()

    with pytest.raises(AnchorRequestValidationError) as caught:
        AnchorEvaluator.for_testing(_registry((entry,), calls), _policy()).evaluate(
            stale_request, sink
        )

    assert caught.value.code == "request_fingerprint_mismatch"
    assert calls["O1"] == []
    assert sink.begin_calls == 0


def test_consumer_local_stream_fault_hook_yields_missing_input_without_calling_plugin() -> None:
    from pilot_assessment.anchors.dag import TestFaultHooks
    from pilot_assessment.anchors.service import AnchorEvaluator

    entry = _entry("O1", 0)
    request = _request((entry,))
    calls: dict[str, list[dict[str, Any]]] = {}
    hook = DomainErrorData(
        error_code="test.stream_projection_missing",
        severity=ErrorSeverity.ERROR,
        recoverable=True,
        message="simulated consumer-local projection miss",
        remediation="test only",
    )
    evaluator = AnchorEvaluator.for_testing(
        _registry((entry,), calls),
        _policy(),
        TestFaultHooks(direct_stream_projection_failures={("O1", "X"): hook}),
    )

    report = evaluator.evaluate(request, _SpySink())

    assert report.results[0].calculation_status.value == "missing_input"
    assert calls["O1"] == []
    assert hook in report.results[0].diagnostics


@pytest.mark.parametrize(
    "status",
    (
        SynchronizationItemStatus.NOT_ATTEMPTED,
        SynchronizationItemStatus.UNAVAILABLE,
        SynchronizationItemStatus.INVALID,
        SynchronizationItemStatus.UNSUPPORTED,
        SynchronizationItemStatus.NOT_APPLICABLE,
    ),
)
def test_optional_non_aligned_stream_becomes_exact_per_anchor_missing_input(
    status: SynchronizationItemStatus,
) -> None:
    from pilot_assessment.anchors.service import AnchorEvaluator

    definition = _definition("O1").model_copy(update={"required_streams": (CoreModality.SCENE,)})
    entry = _entry("O1", 0).model_copy(
        update={
            "required_streams": (CoreModality.SCENE,),
            "definition_fingerprint": plugin_definition_fingerprint(definition),
        }
    )
    request = _request(
        (entry,),
        contracts=(_input_contract(CoreModality.SCENE),),
        synchronization_report=_report(optional_status=status),
    )
    calls: dict[str, list[dict[str, Any]]] = {}

    report = AnchorEvaluator.for_testing(_registry((entry,), calls), _policy()).evaluate(
        request, _SpySink()
    )

    assert report.results[0].calculation_status.value == "missing_input"
    assert calls["O1"] == []
    diagnostic = report.results[0].diagnostics[0]
    assert diagnostic.diagnostics["modality"] == "I"
    assert diagnostic.diagnostics["synchronization_status"] == status.value


def test_service_commits_exact_artifact_then_resolves_it_for_true_downstream() -> None:
    from pilot_assessment.anchors.dag import TestFaultHooks
    from pilot_assessment.anchors.service import AnchorEvaluator

    descriptor = {
        "type": "table",
        "fields": [
            {"name": "t_ns", "dtype": "i64", "unit": "ns", "nullable": False},
            {"name": "value", "dtype": "f64", "unit": "ratio", "nullable": False},
        ],
        "canonical_order_keys": ["t_ns"],
    }
    recipe = AnchorArtifactRecipe(
        artifact_id="trace",
        kind="sample_trace",
        schema_id="test-trace-v0.1",
        schema_descriptor=descriptor,
        payload_kind="table",
    )
    producer_definition = _definition("O1").model_copy(update={"artifact_recipes": (recipe,)})
    producer_entry = _entry("O1", 0).model_copy(
        update={
            "artifact_recipes": (recipe,),
            "definition_fingerprint": plugin_definition_fingerprint(producer_definition),
        }
    )
    dependency = AnchorDependency(
        dependency_id="trace",
        kind=DependencyKind.ARTIFACT,
        target_anchor_id="O1",
        target_resource_id="trace",
        expected_schema_id="test-trace-v0.1",
        expected_artifact_kind="sample_trace",
        required=True,
    )
    consumer_entry = _entry("O2", 1, (dependency,))
    entries = (producer_entry, consumer_entry)
    request = _request(entries)
    producer_calls: list[object] = []
    consumer_calls: list[dict[str, Any]] = []

    class ArtifactPlugin:
        def definition(self):
            return producer_definition

        def compute(self, context, parameters, temporal_recipe, dependencies, artifacts):
            del context, parameters, temporal_recipe, dependencies
            ref = artifacts.stage_table(
                "trace",
                TabularArtifactPayload(
                    schema_id="test-trace-v0.1",
                    schema_descriptor=descriptor,
                    frame=pl.DataFrame(
                        {"t_ns": [0], "value": [1.0]},
                        schema={"t_ns": pl.Int64, "value": pl.Float64},
                    ),
                    order_keys=("t_ns",),
                    artifact_kind="sample_trace",
                    grid_hash=None,
                    start_t_ns=0,
                    end_t_ns=1,
                ),
            )
            producer_calls.append(ref)
            return _measurement("O1").model_copy(update={"derived_artifacts": (ref,)})

    factories = {
        (producer_entry.plugin_id, producer_entry.plugin_version): ArtifactPlugin,
        (consumer_entry.plugin_id, consumer_entry.plugin_version): lambda: _Plugin(
            consumer_entry, consumer_calls
        ),
    }
    registry = PluginRegistry.from_factories_for_testing(factories, {})
    evaluator = AnchorEvaluator.for_testing(registry, _policy())

    report = evaluator.evaluate(request, _SpySink())

    assert tuple(result.calculation_status.value for result in report.results) == (
        "computed",
        "computed",
    )
    assert len(producer_calls) == 1
    assert tuple(consumer_calls[0]["dependencies"].artifacts) == ("trace",)
    resolved = consumer_calls[0]["dependencies"].artifacts["trace"]
    assert resolved.ref == producer_calls[0]

    hook = DomainErrorData(
        error_code="test.anchor_commit_failed",
        severity=ErrorSeverity.ERROR,
        recoverable=True,
        message="simulated anchor commit failure",
        remediation="test only",
    )
    producer_calls.clear()
    consumer_calls.clear()
    hooked = AnchorEvaluator.for_testing(
        registry,
        _policy(),
        TestFaultHooks(anchor_transaction_failures={"O1": hook}),
    ).evaluate(request, _SpySink())
    assert tuple(result.calculation_status.value for result in hooked.results) == (
        "extractor_error",
        "dependency_missing",
    )
    assert consumer_calls == []
    assert hook in hooked.results[0].diagnostics
