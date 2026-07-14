from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from enum import StrEnum
from typing import Any, Literal, cast

import pytest
from pydantic import JsonValue, ValidationError

from pilot_assessment.contracts.anchor_execution import (
    AnchorArtifactRecipe,
    AnchorCatalog,
    AnchorCatalogEntry,
    AnchorDependency,
    AnchorExecutionEntry,
    AnchorExecutionPlan,
    AnchorLifecycle,
    AnchorPluginDefinition,
    AnchorRuntimeRegistry,
    ContentMemberIdentity,
    DependencyKind,
    NumericRuntimeIdentity,
    PluginRegistryEntry,
    PreprocessingDependencySpec,
    PreprocessingProviderDefinition,
    PreprocessingRegistryEntry,
    PythonRuntimeIdentity,
    ResolvedAlgorithmProfile,
    ResolvedInputFieldContract,
    ResolvedInputTableContract,
    ResolvedPreprocessingDependencyBinding,
    ResolvedPreprocessingRecipe,
    ScientificValidationStatus,
    ScorerPolicy,
    SemanticApplicabilityStatus,
)
from pilot_assessment.contracts.session import CoreModality

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64
SHA_F = "f" * 64


def _table_descriptor() -> dict[str, JsonValue]:
    return {
        "type": "table",
        "fields": [
            {"name": "t_ns", "dtype": "i64", "unit": "ns", "nullable": False},
            {"name": "value", "dtype": "f64", "unit": "m", "nullable": False},
        ],
        "canonical_order_keys": ["t_ns"],
    }


def _artifact(artifact_id: str = "trace") -> AnchorArtifactRecipe:
    return AnchorArtifactRecipe(
        artifact_id=artifact_id,
        kind="trajectory-trace",
        schema_id="trajectory-trace-v0.1",
        schema_descriptor=_table_descriptor(),
        payload_kind="table",
    )


def _conflicting_artifact(artifact_id: str = "trace-conflict") -> AnchorArtifactRecipe:
    return AnchorArtifactRecipe(
        artifact_id=artifact_id,
        kind="trajectory-trace",
        schema_id="trajectory-trace-v0.1",
        schema_descriptor={
            **_table_descriptor(),
            "fields": [
                {"name": "t_ns", "dtype": "i64", "unit": "ns", "nullable": False},
                {"name": "value", "dtype": "f64", "unit": "ft", "nullable": False},
            ],
        },
        payload_kind="table",
    )


def _plugin(anchor_id: str = "O1") -> AnchorPluginDefinition:
    return AnchorPluginDefinition(
        anchor_id=anchor_id,
        definition_version="0.1.0",
        plugin_id=f"{anchor_id.lower()}-plugin",
        plugin_version="0.1.0",
        api_version="0.1.0",
        required_streams=(CoreModality.X,),
        required_context_paths=("context.flight_mode",),
        required_semantic_paths=("semantic.phases",),
        required_reference_ids=(),
        dependencies=(),
        parameter_schema_id=f"{anchor_id.lower()}-parameters-v0.1",
        measurement_schema_id="anchor-measurement-v0.1",
        artifact_recipes=(_artifact(),),
    )


def _runtime_identities() -> tuple[PythonRuntimeIdentity, tuple[NumericRuntimeIdentity, ...]]:
    return (
        PythonRuntimeIdentity(
            implementation_name="cpython",
            version=(3, 11, 15),
            cache_tag="cpython-311",
            soabi="cp311-win_amd64",
        ),
        (
            NumericRuntimeIdentity(
                normalized_name="numpy",
                version="2.3.5",
                record_content_sha256=SHA_A,
            ),
        ),
    )


def _plugin_registry_entry(anchor_id: str = "O1") -> PluginRegistryEntry:
    python_runtime, numeric_runtimes = _runtime_identities()
    return PluginRegistryEntry(
        anchor_id=anchor_id,
        definition_version="0.1.0",
        plugin_id=f"{anchor_id.lower()}-plugin",
        plugin_version="0.1.0",
        api_version="0.1.0",
        factory_module=f"pilot_assessment.anchors.plugins.{anchor_id.lower()}",
        factory_symbol="factory",
        allowed_package_namespace="pilot_assessment.anchors.plugins",
        definition_fingerprint=SHA_A,
        parameter_schema_id=f"{anchor_id.lower()}-parameters-v0.1",
        parameter_schema_sha256=SHA_B,
        measurement_schema_id="anchor-measurement-v0.1",
        measurement_schema_sha256=SHA_C,
        artifact_schema_hashes={"trajectory-trace-v0.1": SHA_D},
        implementation_members=(
            ContentMemberIdentity(
                package_relative_path=f"anchors/plugins/{anchor_id.lower()}.py",
                content_sha256=SHA_E,
            ),
        ),
        resource_members=(),
        python_runtime=python_runtime,
        numeric_runtimes=numeric_runtimes,
        implementation_digest=SHA_F,
    )


def _provider_definition(provider_id: str = "movement-events") -> PreprocessingProviderDefinition:
    return PreprocessingProviderDefinition(
        provider_id=provider_id,
        provider_version="0.1.0",
        api_version="0.1.0",
        required_streams=(CoreModality.U,),
        required_context_paths=(),
        required_semantic_paths=("semantic.phases",),
        required_reference_ids=(),
        dependencies=(),
        parameter_schema_id=f"{provider_id}-parameters-v0.1",
        output_schema_id=f"{provider_id}-output-v0.1",
        output_schema_descriptor=_table_descriptor(),
        artifact_kind=f"{provider_id}-table",
        output_payload_kind="table",
    )


def _preprocessor_registry_entry(
    provider_id: str = "movement-events",
) -> PreprocessingRegistryEntry:
    python_runtime, numeric_runtimes = _runtime_identities()
    return PreprocessingRegistryEntry(
        provider_id=provider_id,
        provider_version="0.1.0",
        api_version="0.1.0",
        factory_module=f"pilot_assessment.anchors.preprocessing.{provider_id}",
        factory_symbol="factory",
        allowed_package_namespace="pilot_assessment.anchors.preprocessing",
        definition_fingerprint=SHA_A,
        parameter_schema_id=f"{provider_id}-parameters-v0.1",
        parameter_schema_sha256=SHA_B,
        output_schema_id=f"{provider_id}-output-v0.1",
        output_schema_sha256=SHA_C,
        artifact_kind=f"{provider_id}-table",
        output_payload_kind="table",
        implementation_members=(
            ContentMemberIdentity(
                package_relative_path=f"anchors/preprocessing/{provider_id}.py",
                content_sha256=SHA_D,
            ),
        ),
        resource_members=(),
        python_runtime=python_runtime,
        numeric_runtimes=numeric_runtimes,
        implementation_digest=SHA_E,
    )


def _catalog_entry(anchor_id: str = "O1", order: int = 0) -> AnchorCatalogEntry:
    return AnchorCatalogEntry(
        anchor_id=anchor_id,
        definition_version="0.1.0",
        lifecycle=AnchorLifecycle.ACTIVE,
        required=True,
        canonical_order=order,
        plugin_id=f"{anchor_id.lower()}-plugin",
        plugin_version="0.1.0",
        parameter_schema_id=f"{anchor_id.lower()}-parameters-v0.1",
        scorer_id="dau-threshold-scorer",
        required_inputs=("X",),
        dependencies=(),
        artifact_recipes=(_artifact(),),
    )


def _input_contract(modality: CoreModality = CoreModality.X) -> ResolvedInputTableContract:
    return ResolvedInputTableContract(
        modality=modality,
        table_role="samples",
        stream_aligned_schema_id=f"{modality.value.lower()}-aligned-v0.1",
        table_aligned_schema_id=f"{modality.value.lower()}-samples-aligned-v0.1",
        coordinate_frame_id="world",
        fields=(
            ResolvedInputFieldContract(
                field_name="t_ns", dtype_id="i64", unit="ns", nullable=False
            ),
            ResolvedInputFieldContract(
                field_name="value", dtype_id="f64", unit="m", nullable=False
            ),
        ),
    )


def _scorer() -> ScorerPolicy:
    return ScorerPolicy(
        scorer_id="dau-threshold-scorer",
        scorer_version="0.1.0",
        policy_schema_id="dau-threshold-policy-v0.1",
        parameters={"desired_max": 1.0, "adequate_max": 2.0},
        policy_hash=SHA_A,
    )


def _execution_entry(
    anchor_id: str = "O1",
    order: int = 0,
    *,
    required_streams: tuple[CoreModality, ...] = (CoreModality.X,),
    dependencies: tuple[AnchorDependency, ...] = (),
    artifact_recipes: tuple[AnchorArtifactRecipe, ...] = (_artifact(),),
) -> AnchorExecutionEntry:
    return AnchorExecutionEntry(
        anchor_id=anchor_id,
        definition_version="0.1.0",
        lifecycle="active",
        canonical_order=order,
        plugin_id=f"{anchor_id.lower()}-plugin",
        plugin_version="0.1.0",
        api_version="0.1.0",
        definition_fingerprint=SHA_A,
        implementation_digest=SHA_B,
        parameter_schema_id=f"{anchor_id.lower()}-parameters-v0.1",
        parameters={"gain": 1.0},
        parameter_hash=SHA_C,
        required_streams=required_streams,
        required_context_paths=("context.flight_mode",),
        required_semantic_paths=("semantic.phases",),
        required_reference_ids=(),
        applicability=SemanticApplicabilityStatus.APPLICABLE,
        phase_scope=("phase-1",),
        event_scope=(),
        dependencies=dependencies,
        measurement_schema_id="anchor-measurement-v0.1",
        result_schema_id="anchor-result-0.2.0",
        artifact_recipes=artifact_recipes,
        temporal_recipe={"scope": "phase"},
        scorer_policy=_scorer(),
    )


def _plan(
    *,
    entries: tuple[AnchorExecutionEntry, ...] | None = None,
    input_table_contracts: tuple[ResolvedInputTableContract, ...] | None = None,
    algorithm_profiles: tuple[ResolvedAlgorithmProfile, ...] = (),
    preprocessing_recipes: tuple[ResolvedPreprocessingRecipe, ...] = (),
) -> AnchorExecutionPlan:
    return AnchorExecutionPlan(
        plan_id="plan-1",
        model_profile_id="model-profile-1",
        scientific_validation_status=ScientificValidationStatus.ENGINEERING_DEFAULT,
        catalog_fingerprint=SHA_A,
        registry_fingerprint=SHA_B,
        source_snapshot_fingerprint=SHA_C,
        synchronization_fingerprint=SHA_D,
        semantic_snapshot_fingerprint=SHA_E,
        reference_set_fingerprint=SHA_F,
        entries=entries or (_execution_entry(),),
        input_table_contracts=input_table_contracts or (_input_contract(),),
        algorithm_profiles=algorithm_profiles,
        preprocessing_recipes=preprocessing_recipes,
        parameter_fingerprint=SHA_A,
        plan_fingerprint=SHA_B,
    )


def _recipe(
    recipe_id: str,
    *,
    dependencies: tuple[PreprocessingDependencySpec, ...] = (),
    bindings: tuple[ResolvedPreprocessingDependencyBinding, ...] = (),
    scope_policy: Literal["session", "phase", "event", "window"] = "session",
) -> ResolvedPreprocessingRecipe:
    return ResolvedPreprocessingRecipe(
        recipe_id=recipe_id,
        recipe_version="0.1.0",
        provider_id=recipe_id,
        provider_version="0.1.0",
        api_version="0.1.0",
        definition_fingerprint=SHA_A,
        implementation_digest=SHA_B,
        parameter_schema_id=f"{recipe_id}-parameters-v0.1",
        parameter_schema_sha256=SHA_C,
        parameters={"threshold": 1.0},
        parameter_hash=SHA_D,
        required_streams=(CoreModality.X,),
        required_context_paths=(),
        required_semantic_paths=("semantic.phases",),
        required_reference_ids=(),
        dependency_specs=dependencies,
        dependency_bindings=bindings,
        output_schema_id=f"{recipe_id}-output-v0.1",
        output_schema_descriptor=_table_descriptor(),
        output_schema_sha256=SHA_E,
        artifact_kind=f"{recipe_id}-table",
        output_payload_kind="table",
        scope_policy=scope_policy,
    )


def test_public_enums_and_strict_round_trips_are_exact() -> None:
    assert {item.value for item in DependencyKind} == {
        "result_dependency",
        "artifact_dependency",
        "algorithm_profile_dependency",
        "preprocessing_dependency",
    }
    assert {item.value for item in AnchorLifecycle} == {"active", "deprecated", "retired"}
    assert {item.value for item in ScientificValidationStatus} == {
        "engineering_default",
        "expert_reviewed",
        "calibrated",
        "internally_validated",
        "externally_validated",
        "not_supported",
    }
    plan = _plan()
    assert AnchorExecutionPlan.model_validate_json(plan.model_dump_json()) == plan
    with pytest.raises(ValidationError):
        AnchorExecutionPlan.model_validate({**plan.model_dump(), "test_only_partial_plan": True})
    with pytest.raises(ValidationError):
        plan.plan_id = "changed"  # ty: ignore[invalid-assignment]


@pytest.mark.parametrize(
    ("kind", "fields"),
    [
        (
            DependencyKind.RESULT,
            {
                "target_anchor_id": "O1",
                "expected_schema_id": "anchor-result-0.2.0",
            },
        ),
        (
            DependencyKind.ARTIFACT,
            {
                "target_anchor_id": "O1",
                "target_resource_id": "trace",
                "expected_schema_id": "trajectory-trace-v0.1",
                "expected_artifact_kind": "trajectory-trace",
            },
        ),
        (
            DependencyKind.ALGORITHM_PROFILE,
            {
                "target_resource_id": "filter-profile",
                "expected_schema_id": "filter-output-v0.1",
            },
        ),
        (
            DependencyKind.PREPROCESSING,
            {
                "target_resource_id": "movement-events",
                "expected_schema_id": "movement-events-output-v0.1",
                "expected_artifact_kind": "movement-events-table",
            },
        ),
    ],
)
def test_dependency_kind_field_matrices(kind: DependencyKind, fields: dict[str, str]) -> None:
    dependency = AnchorDependency(
        dependency_id=f"{kind.name.lower()}-1", kind=kind, required=True, **fields
    )
    assert dependency.kind is kind
    with pytest.raises(ValidationError):
        AnchorDependency.model_validate(
            {
                **dependency.model_dump(),
                "target_anchor_id": None,
                "target_resource_id": None,
            }
        )


def test_artifact_inline_schema_and_plugin_namespaces_are_closed() -> None:
    assert _plugin().artifact_recipes[0].schema_descriptor["type"] == "table"
    with pytest.raises(ValidationError):
        AnchorArtifactRecipe(
            artifact_id="bad-table",
            kind="bad",
            schema_id="bad-v0.1",
            schema_descriptor={"type": "table", "fields": []},
            payload_kind="table",
        )
    with pytest.raises(ValidationError):
        AnchorArtifactRecipe(
            artifact_id="bad-blob",
            kind="bad",
            schema_id="bad-v0.1",
            schema_descriptor={"type": "blob", "canonical_order_keys": []},
            payload_kind="blob",
        )
    with pytest.raises(ValidationError):
        AnchorArtifactRecipe(
            artifact_id="missing-blob-contract",
            kind="bad",
            schema_id="bad-v0.1",
            schema_descriptor={"type": "blob"},
            payload_kind="blob",
        )
    valid_blob = AnchorArtifactRecipe(
        artifact_id="valid-blob",
        kind="diagnostic-image",
        schema_id="png-rgb8-v0.1",
        schema_descriptor={
            "type": "blob",
            "media_type": "image/png",
            "content_encoding": "identity",
        },
        payload_kind="blob",
    )
    assert valid_blob.schema_descriptor["media_type"] == "image/png"
    with pytest.raises(ValidationError):
        AnchorArtifactRecipe(
            artifact_id="untyped-table",
            kind="bad",
            schema_id="bad-v0.1",
            schema_descriptor={
                "type": "table",
                "fields": [{"name": "value"}],
                "canonical_order_keys": ["value"],
            },
            payload_kind="table",
        )

    with pytest.raises(ValidationError):
        AnchorPluginDefinition.model_validate(
            {
                **_plugin().model_dump(),
                "artifact_recipes": (_artifact(), _conflicting_artifact()),
            }
        )
    payload = _plugin().model_dump(mode="python")
    payload["required_context_paths"] = ("semantic.phases",)
    with pytest.raises(ValidationError):
        AnchorPluginDefinition.model_validate(payload)


def test_catalog_allows_history_but_execution_is_active_only_and_canonical() -> None:
    deprecated = _catalog_entry().model_copy(update={"lifecycle": AnchorLifecycle.DEPRECATED})
    catalog = AnchorCatalog(
        profile_id="reference-18",
        profile_version="0.1.0",
        scientific_validation_status=ScientificValidationStatus.ENGINEERING_DEFAULT,
        entries=(deprecated,),
        catalog_fingerprint=SHA_A,
    )
    assert catalog.entries[0].lifecycle is AnchorLifecycle.DEPRECATED

    with pytest.raises(ValidationError):
        AnchorExecutionEntry.model_validate(
            {**_execution_entry().model_dump(), "lifecycle": "deprecated"}
        )
    with pytest.raises(ValidationError):
        AnchorCatalog(
            profile_id="p",
            profile_version="0.1.0",
            scientific_validation_status=ScientificValidationStatus.NOT_SUPPORTED,
            entries=(_catalog_entry("O2", 1), _catalog_entry("O1", 0)),
            catalog_fingerprint=SHA_A,
        )


def test_runtime_registry_has_one_exact_serialized_contract() -> None:
    registry = AnchorRuntimeRegistry(
        entries=(_plugin_registry_entry(),),
        preprocessors=(_preprocessor_registry_entry(),),
    )
    assert AnchorRuntimeRegistry.model_validate_json(registry.model_dump_json()) == registry
    with pytest.raises(ValidationError):
        AnchorRuntimeRegistry.model_validate({**registry.model_dump(), "extra": 1})
    duplicate = _plugin_registry_entry("O2").model_copy(update={"plugin_id": "o1-plugin"})
    with pytest.raises(ValidationError):
        AnchorRuntimeRegistry(entries=(registry.entries[0], duplicate), preprocessors=())
    with pytest.raises(ValidationError):
        ContentMemberIdentity(package_relative_path="../escape.py", content_sha256=SHA_A)


def test_runtime_registry_and_closure_inventories_are_canonical() -> None:
    first = ContentMemberIdentity(
        package_relative_path="anchors/plugins/a.py", content_sha256=SHA_A
    )
    second = ContentMemberIdentity(
        package_relative_path="anchors/plugins/b.py", content_sha256=SHA_B
    )
    with pytest.raises(ValidationError):
        PluginRegistryEntry.model_validate(
            {
                **_plugin_registry_entry().model_dump(),
                "implementation_members": (second, first),
            }
        )

    alpha = NumericRuntimeIdentity(
        normalized_name="alpha", version="1.0", record_content_sha256=SHA_A
    )
    zeta = NumericRuntimeIdentity(
        normalized_name="zeta", version="1.0", record_content_sha256=SHA_B
    )
    with pytest.raises(ValidationError):
        PluginRegistryEntry.model_validate(
            {
                **_plugin_registry_entry().model_dump(),
                "numeric_runtimes": (zeta, alpha),
            }
        )

    with pytest.raises(ValidationError):
        AnchorRuntimeRegistry(
            entries=(_plugin_registry_entry("O2"), _plugin_registry_entry("O1")),
            preprocessors=(),
        )
    with pytest.raises(ValidationError):
        AnchorRuntimeRegistry(
            entries=(),
            preprocessors=(
                _preprocessor_registry_entry("z-provider"),
                _preprocessor_registry_entry("a-provider"),
            ),
        )


@pytest.mark.parametrize("dtype", ["float64", "list[f64]", "F64", "struct"])
def test_input_contract_rejects_alias_nested_and_unknown_dtypes(dtype: str) -> None:
    with pytest.raises(ValidationError):
        ResolvedInputFieldContract(field_name="value", dtype_id=dtype, unit="m", nullable=False)


def test_plan_input_contracts_exactly_cover_required_modalities() -> None:
    assert _plan().input_table_contracts[0].modality is CoreModality.X
    with pytest.raises(ValidationError):
        _plan(input_table_contracts=(_input_contract(CoreModality.U),))
    with pytest.raises(ValidationError):
        _plan(input_table_contracts=(_input_contract(), _input_contract()))

    second = _input_contract().model_copy(
        update={
            "table_role": "secondary",
            "stream_aligned_schema_id": "different-aligned-v0.1",
        }
    )
    with pytest.raises(ValidationError):
        _plan(input_table_contracts=(_input_contract(), second))


def test_plan_rejects_one_schema_id_with_multiple_inline_descriptors() -> None:
    first = _execution_entry("O1", 0)
    second = _execution_entry("O2", 1, artifact_recipes=(_conflicting_artifact("trace-o2"),))
    with pytest.raises(ValidationError):
        _plan(entries=(first, second))

    conflicting_recipe = _recipe("derived").model_copy(
        update={
            "output_schema_id": "trajectory-trace-v0.1",
            "output_schema_descriptor": _conflicting_artifact().schema_descriptor,
        }
    )
    with pytest.raises(ValidationError):
        _plan(preprocessing_recipes=(conflicting_recipe,))


def test_parameters_reject_nonfinite_and_quality_gate_fields_recursively() -> None:
    with pytest.raises(ValidationError):
        ScorerPolicy(
            scorer_id="s",
            scorer_version="0.1.0",
            policy_schema_id="s-v0.1",
            parameters={"threshold": float("nan")},
            policy_hash=SHA_A,
        )
    payload = _execution_entry().model_dump(mode="python")
    payload["parameters"] = {"nested": {"min_valid_coverage": 0.5}}
    with pytest.raises(ValidationError):
        AnchorExecutionEntry.model_validate(payload)


def _scorer_with_parameters(parameters: dict[str, JsonValue]) -> ScorerPolicy:
    return ScorerPolicy(
        scorer_id="hard-threshold-v1",
        scorer_version="0.1.0",
        policy_schema_id="ordered-dau-threshold-policy-v0.1",
        parameters=parameters,
        policy_hash=SHA_A,
    )


def _entry_with_json_surface(field_name: str, value: dict[str, JsonValue]) -> AnchorExecutionEntry:
    payload = _execution_entry().model_dump(mode="python")
    payload[field_name] = value
    return AnchorExecutionEntry.model_validate(payload)


def _recipe_with_parameters(parameters: dict[str, JsonValue]) -> ResolvedPreprocessingRecipe:
    payload = _recipe("movement-events-v1").model_dump(mode="python")
    payload["parameters"] = parameters
    return ResolvedPreprocessingRecipe.model_validate(payload)


@pytest.mark.parametrize(
    ("factory", "field_name"),
    [
        (_scorer_with_parameters, "parameters"),
        (lambda value: _entry_with_json_surface("parameters", value), "parameters"),
        (
            lambda value: _entry_with_json_surface("temporal_recipe", value),
            "temporal_recipe",
        ),
        (_recipe_with_parameters, "parameters"),
    ],
    ids=(
        "scorer-policy-parameters",
        "execution-entry-parameters",
        "execution-entry-temporal-recipe",
        "preprocessing-recipe-parameters",
    ),
)
def test_plan_time_json_surfaces_are_deep_immutable_snapshots(
    factory: Callable[[dict[str, JsonValue]], Any], field_name: str
) -> None:
    caller_owned: dict[str, JsonValue] = {
        "nested": {"rules": [{"metric_id": "primary_value", "operator": "<=", "value": 2.0}]}
    }
    expected = deepcopy(caller_owned)

    model = factory(caller_owned)
    snapshot = getattr(model, field_name)
    nested = cast(dict[str, JsonValue], caller_owned["nested"])
    rules = cast(list[JsonValue], nested["rules"])
    condition = cast(dict[str, JsonValue], rules[0])
    condition["value"] = 999.0

    assert snapshot == expected
    with pytest.raises(TypeError, match="immutable"):
        snapshot["nested"]["rules"][0]["value"] = 3.0
    with pytest.raises(TypeError, match="immutable"):
        snapshot["nested"]["rules"].append({"value": 4.0})


@pytest.mark.parametrize(
    "factory",
    [
        lambda descriptor: PreprocessingProviderDefinition.model_validate(
            {
                **_provider_definition().model_dump(mode="python"),
                "output_schema_descriptor": descriptor,
            }
        ),
        lambda descriptor: ResolvedPreprocessingRecipe.model_validate(
            {
                **_recipe("movement-events-v1").model_dump(mode="python"),
                "output_schema_descriptor": descriptor,
            }
        ),
    ],
    ids=("provider-definition", "resolved-provider-recipe"),
)
def test_preprocessing_output_descriptors_are_deep_immutable_snapshots(
    factory: Callable[[dict[str, JsonValue]], Any],
) -> None:
    caller_owned = _table_descriptor()
    expected = deepcopy(caller_owned)

    model = factory(caller_owned)
    snapshot = model.output_schema_descriptor
    caller_fields = cast(list[JsonValue], caller_owned["fields"])
    caller_field = cast(dict[str, JsonValue], caller_fields[0])
    caller_field["unit"] = "caller-mutated"

    assert snapshot == expected
    with pytest.raises(TypeError, match="immutable"):
        snapshot["fields"][0]["unit"] = "post-construction-mutated"


def test_provider_recipe_bindings_are_exact_acyclic_and_scope_compatible() -> None:
    spec_a = PreprocessingDependencySpec(
        dependency_id="upstream",
        expected_schema_id="recipe-b-output-v0.1",
        expected_artifact_kind="recipe-b-table",
    )
    bind_a = ResolvedPreprocessingDependencyBinding(
        dependency_id="upstream", target_recipe_id="recipe-b"
    )
    recipe_a = _recipe("recipe-a", dependencies=(spec_a,), bindings=(bind_a,))
    recipe_b = _recipe("recipe-b")
    plan = _plan(
        input_table_contracts=(_input_contract(),),
        preprocessing_recipes=(recipe_a, recipe_b),
    )
    assert len(plan.preprocessing_recipes) == 2

    cyclic_spec = PreprocessingDependencySpec(
        dependency_id="back",
        expected_schema_id="recipe-a-output-v0.1",
        expected_artifact_kind="recipe-a-table",
    )
    cyclic_binding = ResolvedPreprocessingDependencyBinding(
        dependency_id="back", target_recipe_id="recipe-a"
    )
    with pytest.raises(ValidationError):
        _plan(
            preprocessing_recipes=(
                recipe_a,
                _recipe(
                    "recipe-b",
                    dependencies=(cyclic_spec,),
                    bindings=(cyclic_binding,),
                ),
            )
        )
    with pytest.raises(ValidationError):
        _plan(
            preprocessing_recipes=(
                recipe_a,
                _recipe("recipe-b", scope_policy="phase"),
            )
        )


def test_anchor_artifact_dependency_resolves_exact_producer_recipe() -> None:
    dependency = AnchorDependency(
        dependency_id="needs-trace",
        kind=DependencyKind.ARTIFACT,
        target_anchor_id="O1",
        target_resource_id="trace",
        expected_schema_id="trajectory-trace-v0.1",
        expected_artifact_kind="trajectory-trace",
        required=True,
    )
    consumer = _execution_entry(
        "O2", 1, dependencies=(dependency,), artifact_recipes=(_artifact("consumer-trace"),)
    )
    assert len(_plan(entries=(_execution_entry(), consumer)).entries) == 2

    bad = dependency.model_copy(update={"expected_schema_id": "wrong-schema"})
    with pytest.raises(ValidationError):
        _plan(entries=(_execution_entry(), _execution_entry("O2", 1, dependencies=(bad,))))


def test_algorithm_profile_dependency_resolves_frozen_profile() -> None:
    profile = ResolvedAlgorithmProfile(
        profile_id="filter-profile",
        profile_version="0.1.0",
        parameters={"cutoff_hz": 2.0},
        parameter_hash=SHA_A,
        implementation_digest=SHA_B,
        output_schema_id="filter-output-v0.1",
    )
    dependency = AnchorDependency(
        dependency_id="filter",
        kind=DependencyKind.ALGORITHM_PROFILE,
        target_resource_id="filter-profile",
        expected_schema_id="filter-output-v0.1",
        required=True,
    )
    plan = _plan(
        entries=(_execution_entry(dependencies=(dependency,)),),
        algorithm_profiles=(profile,),
    )
    assert plan.algorithm_profiles == (profile,)


def test_all_declared_contract_classes_are_versioned_or_closed_models() -> None:
    assert _plugin().contract_id == "anchor-plugin-definition"
    assert _provider_definition().contract_id == "preprocessing-provider-definition"
    assert AnchorRuntimeRegistry(entries=(), preprocessors=()).contract_id == (
        "anchor-runtime-registry"
    )
    for enum_type in (DependencyKind, AnchorLifecycle, ScientificValidationStatus):
        assert issubclass(enum_type, StrEnum)
