from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import JsonValue

from pilot_assessment.anchors.catalog import load_parameter_schema, parameter_schema_sha256
from pilot_assessment.anchors.fingerprint import (
    parameter_snapshot_fingerprint,
    plugin_definition_fingerprint,
    preprocessing_definition_fingerprint,
    schema_descriptor_sha256,
)
from pilot_assessment.anchors.registry import PluginRegistry
from pilot_assessment.anchors.scoring import compile_scorer_policy
from pilot_assessment.contracts.anchor_execution import (
    AnchorDependency,
    AnchorExecutionEntry,
    AnchorExecutionPlan,
    AnchorPluginDefinition,
    DependencyKind,
    PreprocessingDependencySpec,
    PreprocessingProviderDefinition,
    ResolvedInputFieldContract,
    ResolvedInputTableContract,
    ResolvedPreprocessingDependencyBinding,
    ResolvedPreprocessingRecipe,
    ScientificValidationStatus,
    SemanticApplicabilityStatus,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64

_OUTPUT_DESCRIPTOR: dict[str, JsonValue] = {
    "type": "table",
    "fields": [
        {"name": "event_id", "dtype": "utf8", "unit": "id", "nullable": False},
        {"name": "t_ns", "dtype": "i64", "unit": "ns", "nullable": False},
    ],
    "canonical_order_keys": ["t_ns", "event_id"],
}


def _schema_defaults(schema_id: str) -> dict[str, JsonValue]:
    schema = load_parameter_schema(schema_id)
    properties = schema["properties"]
    assert isinstance(properties, Mapping)
    result: dict[str, JsonValue] = {}
    for name, raw_property in properties.items():
        assert isinstance(raw_property, Mapping)
        assert "default" in raw_property
        result[name] = raw_property["default"]  # type: ignore[assignment]
    return result


def _scorer():
    schema = load_parameter_schema("o1-parameters-0.1")
    annotation = schema["x-scorer-policy-default"]
    assert isinstance(annotation, Mapping)
    return compile_scorer_policy(annotation)


def _dependency(
    dependency_id: str,
    target_anchor_id: str,
) -> AnchorDependency:
    return AnchorDependency(
        dependency_id=dependency_id,
        kind=DependencyKind.RESULT,
        target_anchor_id=target_anchor_id,
        expected_schema_id="anchor-result-0.2.0",
        required=True,
    )


def _definition(
    anchor_id: str,
    dependencies: tuple[AnchorDependency, ...] = (),
) -> AnchorPluginDefinition:
    return AnchorPluginDefinition(
        anchor_id=anchor_id,
        definition_version="0.1.0",
        plugin_id=f"test-{anchor_id.lower()}-plugin",
        plugin_version="0.1.0",
        api_version="0.1.0",
        required_streams=("X",),
        required_context_paths=(),
        required_semantic_paths=(),
        required_reference_ids=(),
        dependencies=dependencies,
        parameter_schema_id="o1-parameters-0.1",
        measurement_schema_id="anchor-measurement-0.1.0",
        artifact_recipes=(),
    )


def _entry(
    anchor_id: str,
    order: int,
    dependencies: tuple[AnchorDependency, ...] = (),
) -> AnchorExecutionEntry:
    definition = _definition(anchor_id, dependencies)
    parameters: dict[str, JsonValue] = {}
    return AnchorExecutionEntry(
        anchor_id=anchor_id,
        definition_version="0.1.0",
        lifecycle="active",
        canonical_order=order,
        plugin_id=definition.plugin_id,
        plugin_version=definition.plugin_version,
        api_version="0.1.0",
        definition_fingerprint=plugin_definition_fingerprint(definition),
        implementation_digest=SHA_A,
        parameter_schema_id=definition.parameter_schema_id,
        parameters=parameters,
        parameter_hash=parameter_snapshot_fingerprint(parameters),
        required_streams=("X",),
        required_context_paths=(),
        required_semantic_paths=(),
        required_reference_ids=(),
        applicability=SemanticApplicabilityStatus.APPLICABLE,
        phase_scope=("phase-1",),
        event_scope=(),
        dependencies=dependencies,
        measurement_schema_id=definition.measurement_schema_id,
        result_schema_id="anchor-result-0.2.0",
        artifact_recipes=(),
        temporal_recipe={"scope": "phase"},
        scorer_policy=_scorer(),
    )


def _input_contract(modality: str) -> ResolvedInputTableContract:
    return ResolvedInputTableContract(
        modality=modality,
        table_role="samples",
        stream_aligned_schema_id=f"{modality.lower()}-aligned-v0.1",
        table_aligned_schema_id=f"{modality.lower()}-samples-aligned-v0.1",
        coordinate_frame_id="simulator",
        fields=(
            ResolvedInputFieldContract(
                field_name="t_ns", dtype_id="i64", unit="ns", nullable=False
            ),
        ),
    )


def _provider_definition(
    dependencies: tuple[PreprocessingDependencySpec, ...] = (),
) -> PreprocessingProviderDefinition:
    return PreprocessingProviderDefinition(
        provider_id="test-movement-provider",
        provider_version="1.0.0",
        api_version="0.1.0",
        required_streams=("U",),
        required_context_paths=(),
        required_semantic_paths=(),
        required_reference_ids=(),
        dependencies=dependencies,
        parameter_schema_id="movement-events-v1-parameters-0.1",
        output_schema_id="test-events-v0.1",
        output_schema_descriptor=_OUTPUT_DESCRIPTOR,
        artifact_kind="event_trace",
        output_payload_kind="table",
    )


def _recipe(
    recipe_id: str,
    *,
    dependencies: tuple[PreprocessingDependencySpec, ...] = (),
    bindings: tuple[ResolvedPreprocessingDependencyBinding, ...] = (),
    scope_policy: str = "phase",
) -> ResolvedPreprocessingRecipe:
    definition = _provider_definition(dependencies)
    parameters = _schema_defaults(definition.parameter_schema_id)
    return ResolvedPreprocessingRecipe(
        recipe_id=recipe_id,
        recipe_version="0.1.0",
        provider_id=definition.provider_id,
        provider_version=definition.provider_version,
        api_version="0.1.0",
        definition_fingerprint=preprocessing_definition_fingerprint(definition),
        implementation_digest=SHA_B,
        parameter_schema_id=definition.parameter_schema_id,
        parameter_schema_sha256=parameter_schema_sha256(definition.parameter_schema_id),
        parameters=parameters,
        parameter_hash=parameter_snapshot_fingerprint(parameters),
        required_streams=("U",),
        required_context_paths=(),
        required_semantic_paths=(),
        required_reference_ids=(),
        dependency_specs=dependencies,
        dependency_bindings=bindings,
        output_schema_id=definition.output_schema_id,
        output_schema_descriptor=_OUTPUT_DESCRIPTOR,
        output_schema_sha256=schema_descriptor_sha256(
            definition.output_schema_id, _OUTPUT_DESCRIPTOR
        ),
        artifact_kind=definition.artifact_kind,
        output_payload_kind="table",
        scope_policy=scope_policy,  # type: ignore[arg-type]
    )


class _Plugin:
    def __init__(self, definition: AnchorPluginDefinition) -> None:
        self._definition = definition

    def definition(self) -> AnchorPluginDefinition:
        return self._definition

    def compute(self, *args: object, **kwargs: object) -> Any:
        raise AssertionError("DAG validation must not call compute")


class _Provider:
    def __init__(self, definition: PreprocessingProviderDefinition) -> None:
        self._definition = definition

    def definition(self) -> PreprocessingProviderDefinition:
        return self._definition

    def compute(self, *args: object, **kwargs: object) -> Any:
        raise AssertionError("DAG validation must not call compute")


def _registry(
    entries: tuple[AnchorExecutionEntry, ...],
    recipes: tuple[ResolvedPreprocessingRecipe, ...] = (),
) -> PluginRegistry:
    definitions = {
        (entry.plugin_id, entry.plugin_version): _definition(entry.anchor_id, entry.dependencies)
        for entry in entries
    }
    provider_definitions = {
        (recipe.provider_id, recipe.provider_version): _provider_definition(recipe.dependency_specs)
        for recipe in recipes
    }
    return PluginRegistry.from_factories_for_testing(
        {
            key: (lambda definition=definition: _Plugin(definition))
            for key, definition in definitions.items()
        },
        {
            key: (lambda definition=definition: _Provider(definition))
            for key, definition in provider_definitions.items()
        },
    )


def _plan(
    entries: tuple[AnchorExecutionEntry, ...],
    recipes: tuple[ResolvedPreprocessingRecipe, ...] = (),
) -> AnchorExecutionPlan:
    modalities = {str(modality) for entry in entries for modality in entry.required_streams}
    modalities.update(str(modality) for recipe in recipes for modality in recipe.required_streams)
    return AnchorExecutionPlan(
        plan_id="test-plan-1",
        model_profile_id="test-profile-1",
        scientific_validation_status=ScientificValidationStatus.NOT_SUPPORTED,
        catalog_fingerprint=SHA_A,
        registry_fingerprint=SHA_B,
        source_snapshot_fingerprint=SHA_A,
        synchronization_fingerprint=SHA_B,
        semantic_snapshot_fingerprint=SHA_C,
        reference_set_fingerprint=SHA_A,
        entries=entries,
        input_table_contracts=tuple(_input_contract(modality) for modality in sorted(modalities)),
        algorithm_profiles=(),
        preprocessing_recipes=recipes,
        parameter_fingerprint=SHA_B,
        plan_fingerprint=SHA_C,
    )


def _codes(outcome: object) -> set[str]:
    return {item.error_code for item in outcome.diagnostics}  # type: ignore[attr-defined]


def test_valid_plan_has_canonical_levels_without_calling_compute() -> None:
    from pilot_assessment.anchors.dag import topological_levels, validate_execution_plan

    entries = (
        _entry("O1", 0),
        _entry("O5", 1),
        _entry("O8", 2, (_dependency("o8-from-o5", "O5"),)),
        _entry("O13", 3, (_dependency("o13-from-o1", "O1"),)),
    )
    plan = _plan(entries)

    assert topological_levels(entries) == (("O1", "O5"), ("O8", "O13"))
    outcome = validate_execution_plan(plan, _registry(entries))
    assert outcome.disposition == "valid"
    assert outcome.validated_plan is not None
    assert outcome.validated_plan.levels == (("O1", "O5"), ("O8", "O13"))


def test_trusted_registry_rejects_partial_or_catalog_divergent_production_plan() -> None:
    from pilot_assessment.anchors.catalog import load_packaged_catalog
    from pilot_assessment.anchors.dag import validate_execution_plan
    from pilot_assessment.anchors.registry import (
        load_packaged_registry,
        packaged_registry_fingerprint,
    )

    catalog = load_packaged_catalog()
    plan = _plan((_entry("O1", 0),)).model_copy(
        update={
            "model_profile_id": catalog.profile_id,
            "catalog_fingerprint": catalog.catalog_fingerprint,
            "registry_fingerprint": packaged_registry_fingerprint(),
        }
    )

    outcome = validate_execution_plan(plan, load_packaged_registry())

    assert "anchor.plan.catalog_inventory_mismatch" in _codes(outcome)


def test_catalog_required_inputs_are_adapted_to_definition_canonical_order() -> None:
    from pilot_assessment.anchors.catalog import load_packaged_catalog
    from pilot_assessment.anchors.dag import _canonical_catalog_required_inputs

    catalog = load_packaged_catalog()
    o1 = next(entry for entry in catalog.entries if entry.anchor_id == "O1")

    assert o1.required_inputs == (
        "stream.X",
        "semantic.phases",
        "semantic.envelopes",
    )
    assert _canonical_catalog_required_inputs(o1.required_inputs) == (
        "stream.X",
        "semantic.envelopes",
        "semantic.phases",
    )
    assert set(_canonical_catalog_required_inputs(o1.required_inputs)) == set(o1.required_inputs)


def test_plan_validation_blocks_duplicate_missing_cycle_and_schema_tamper() -> None:
    from pilot_assessment.anchors.dag import validate_execution_plan

    base = _entry("O1", 0)
    plan = _plan((base,))
    duplicate = plan.model_copy(update={"entries": (base, base)})
    assert "anchor.plan.duplicate_anchor" in _codes(
        validate_execution_plan(duplicate, _registry((base,)))
    )

    missing_entry = _entry("O2", 1, (_dependency("missing", "O9"),))
    missing = plan.model_copy(update={"entries": (base, missing_entry)})
    assert "anchor.plan.dependency_unresolved" in _codes(
        validate_execution_plan(missing, _registry((base, missing_entry)))
    )

    first = _entry("O1", 0, (_dependency("from-o2", "O2"),))
    second = _entry("O2", 1, (_dependency("from-o1", "O1"),))
    cyclic = plan.model_copy(update={"entries": (first, second)})
    assert "anchor.plan.anchor_cycle" in _codes(
        validate_execution_plan(cyclic, _registry((first, second)))
    )

    invalid_parameters = base.model_copy(
        update={
            "parameters": {"unexpected": 1},
            "parameter_hash": parameter_snapshot_fingerprint({"unexpected": 1}),
        }
    )
    invalid = plan.model_copy(update={"entries": (invalid_parameters,)})
    assert "anchor.plan.parameter_schema_invalid" in _codes(
        validate_execution_plan(invalid, _registry((invalid_parameters,)))
    )


def test_plan_validation_reconstructs_exact_plugin_definition_before_factory_access() -> None:
    from pilot_assessment.anchors.dag import validate_execution_plan

    entry = _entry("O1", 0)
    tampered = entry.model_copy(update={"definition_fingerprint": SHA_A})
    outcome = validate_execution_plan(
        _plan((entry,)).model_copy(update={"entries": (tampered,)}),
        _registry((entry,)),
    )
    assert outcome.disposition == "blocked"
    assert "anchor.plan.definition_fingerprint_mismatch" in _codes(outcome)


def test_provider_dag_requires_unique_binding_and_equal_scope_policy() -> None:
    from pilot_assessment.anchors.dag import validate_execution_plan

    entry = _entry("O1", 0)
    leaf = _recipe("leaf")
    spec = PreprocessingDependencySpec(
        dependency_id="upstream",
        expected_schema_id=leaf.output_schema_id,
        expected_artifact_kind=leaf.artifact_kind,
    )
    parent = _recipe(
        "parent",
        dependencies=(spec,),
        bindings=(
            ResolvedPreprocessingDependencyBinding(
                dependency_id="upstream", target_recipe_id="leaf"
            ),
        ),
    )
    valid = _plan((entry,), (leaf, parent))
    assert (
        validate_execution_plan(valid, _registry((entry,), (leaf, parent))).disposition == "valid"
    )

    wrong_scope_leaf = leaf.model_copy(update={"scope_policy": "session"})
    wrong_scope = valid.model_copy(update={"preprocessing_recipes": (wrong_scope_leaf, parent)})
    outcome = validate_execution_plan(wrong_scope, _registry((entry,), (wrong_scope_leaf, parent)))
    assert "anchor.plan.preprocessing_scope_mismatch" in _codes(outcome)

    cycle_leaf = leaf.model_copy(
        update={
            "dependency_specs": (spec,),
            "dependency_bindings": (
                ResolvedPreprocessingDependencyBinding(
                    dependency_id="upstream", target_recipe_id="parent"
                ),
            ),
        }
    )
    cycle = valid.model_copy(update={"preprocessing_recipes": (cycle_leaf, parent)})
    assert "anchor.plan.preprocessing_cycle" in _codes(
        validate_execution_plan(cycle, _registry((entry,), (cycle_leaf, parent)))
    )
