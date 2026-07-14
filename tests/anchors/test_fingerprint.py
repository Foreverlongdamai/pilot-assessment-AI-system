from __future__ import annotations

import hashlib
import json
import struct
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import JsonValue

from pilot_assessment.anchors import catalog as catalog_module
from pilot_assessment.anchors.fingerprint import (
    anchor_result_fingerprint_payload,
    catalog_fingerprint_payload,
    evaluation_fingerprint_payload,
    execution_plan_fingerprint_payload,
    jcs_bytes,
    logical_artifact_identity_payload,
    logical_table_sha256,
    packaged_catalog_fingerprint,
    parameter_snapshot_fingerprint,
    plugin_definition_fingerprint,
    plugin_implementation_digest_payload,
    preprocessing_definition_fingerprint,
    preprocessing_implementation_digest_payload,
    runtime_registry_fingerprint,
    schema_descriptor_sha256,
    scorer_policy_fingerprint,
    typed_json_sha256,
    validate_logical_artifact_ref,
)
from pilot_assessment.anchors.protocols import (
    ReadOnlyBlobPayload,
    ResolvedArtifactDependency,
)
from pilot_assessment.contracts.anchor import EvidenceLikelihood, EvidenceState
from pilot_assessment.contracts.anchor_execution import (
    AnchorApplicability,
    AnchorArtifactRecipe,
    AnchorCapabilityStatus,
    AnchorEvaluationDisposition,
    AnchorEvaluationReport,
    AnchorExecutionEntry,
    AnchorExecutionPlan,
    AnchorInventoryItem,
    AnchorInventoryStatus,
    AnchorPluginDefinition,
    AnchorRuntimeRegistry,
    ContentMemberIdentity,
    NumericRuntimeIdentity,
    PluginRegistryEntry,
    PreprocessingProviderDefinition,
    PreprocessingRegistryEntry,
    PythonRuntimeIdentity,
    ResolvedAlgorithmProfile,
    ResolvedInputFieldContract,
    ResolvedInputTableContract,
    ScientificValidationStatus,
    ScorerPolicy,
    SemanticApplicabilityStatus,
)
from pilot_assessment.contracts.anchor_v2 import (
    AnchorArtifactRef,
    AnchorCalculationStatusV2,
    AnchorResultProvenance,
    AnchorResultV2,
    ComputationTrace,
    MetricValue,
)
from pilot_assessment.contracts.session import CoreModality

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64
SHA_F = "f" * 64
SAFE_INTEGER = 9_007_199_254_740_991


def _descriptor() -> dict[str, Any]:
    return {
        "type": "table",
        "fields": [
            {"name": "t_ns", "dtype": "i64", "unit": "ns", "nullable": False},
            {"name": "value", "dtype": "f64", "unit": "m", "nullable": False},
            {"name": "valid", "dtype": "bool", "unit": "bool", "nullable": False},
        ],
        "canonical_order_keys": ["t_ns"],
    }


def _rows() -> tuple[dict[str, Any], ...]:
    return (
        {"t_ns": 0, "value": 1.25, "valid": True},
        {"t_ns": 1, "value": -2.5, "valid": False},
    )


def _artifact_recipe() -> AnchorArtifactRecipe:
    return AnchorArtifactRecipe(
        artifact_id="trace",
        kind="sample_trace",
        schema_id="trace-v0.1",
        schema_descriptor=_descriptor(),
        payload_kind="table",
    )


def _plugin_definition() -> AnchorPluginDefinition:
    return AnchorPluginDefinition(
        anchor_id="O1",
        definition_version="0.1.0",
        plugin_id="o1-plugin",
        plugin_version="0.1.0",
        api_version="0.1.0",
        required_streams=(),
        required_context_paths=(),
        required_semantic_paths=(),
        required_reference_ids=(),
        dependencies=(),
        parameter_schema_id="o1-parameters-0.1",
        measurement_schema_id="anchor-measurement-0.1.0",
        artifact_recipes=(_artifact_recipe(),),
    )


def _preprocessing_definition() -> PreprocessingProviderDefinition:
    return PreprocessingProviderDefinition(
        provider_id="tiny-provider",
        provider_version="0.1.0",
        api_version="0.1.0",
        required_streams=(),
        required_context_paths=(),
        required_semantic_paths=(),
        required_reference_ids=(),
        dependencies=(),
        parameter_schema_id="tiny-provider-parameters-0.1",
        output_schema_id="tiny-provider-output-v0.1",
        output_schema_descriptor=_descriptor(),
        artifact_kind="sample_trace",
        output_payload_kind="table",
    )


def _python_runtime() -> PythonRuntimeIdentity:
    return PythonRuntimeIdentity(
        implementation_name="cpython",
        version=(3, 11, 9),
        cache_tag="cpython-311",
        soabi="cp311-win_amd64",
    )


def _numeric_runtime() -> NumericRuntimeIdentity:
    return NumericRuntimeIdentity(
        normalized_name="numpy",
        version="2.3.5",
        record_content_sha256=SHA_A,
    )


def _plugin_registry_entry() -> PluginRegistryEntry:
    return PluginRegistryEntry(
        anchor_id="O1",
        definition_version="0.1.0",
        plugin_id="o1-plugin",
        plugin_version="0.1.0",
        api_version="0.1.0",
        factory_module="pilot_assessment.anchors.plugins.o1",
        factory_symbol="create_plugin",
        allowed_package_namespace="pilot_assessment.anchors.plugins",
        definition_fingerprint=SHA_A,
        parameter_schema_id="o1-parameters-0.1",
        parameter_schema_sha256=SHA_B,
        measurement_schema_id="anchor-measurement-0.1.0",
        measurement_schema_sha256=SHA_C,
        artifact_schema_hashes={"trace-v0.1": SHA_D},
        implementation_members=(
            ContentMemberIdentity(
                package_relative_path="pilot_assessment/anchors/plugins/o1.py",
                content_sha256=SHA_E,
            ),
        ),
        resource_members=(),
        python_runtime=_python_runtime(),
        numeric_runtimes=(_numeric_runtime(),),
        implementation_digest=SHA_F,
    )


def _preprocessing_registry_entry() -> PreprocessingRegistryEntry:
    return PreprocessingRegistryEntry(
        provider_id="tiny-provider",
        provider_version="0.1.0",
        api_version="0.1.0",
        factory_module="pilot_assessment.anchors.primitives.tiny",
        factory_symbol="create_provider",
        allowed_package_namespace="pilot_assessment.anchors.primitives",
        definition_fingerprint=SHA_A,
        parameter_schema_id="tiny-provider-parameters-0.1",
        parameter_schema_sha256=SHA_B,
        output_schema_id="tiny-provider-output-v0.1",
        output_schema_sha256=SHA_C,
        artifact_kind="sample_trace",
        output_payload_kind="table",
        implementation_members=(
            ContentMemberIdentity(
                package_relative_path="pilot_assessment/anchors/primitives/tiny.py",
                content_sha256=SHA_D,
            ),
        ),
        resource_members=(),
        python_runtime=_python_runtime(),
        numeric_runtimes=(_numeric_runtime(),),
        implementation_digest=SHA_E,
    )


def _artifact_ref(*, storage_hash: str | None = SHA_B) -> AnchorArtifactRef:
    return AnchorArtifactRef(
        artifact_id="trace",
        kind="sample_trace",
        schema_id="trace-v0.1",
        logical_content_sha256=SHA_A,
        storage_file_sha256=storage_hash,
        row_count=2,
        start_t_ns=0,
        end_t_ns=1,
        grid_hash=SHA_C,
        producer_anchor_id="O1",
        producer_plugin_id="o1-plugin",
        producer_plugin_version="0.1.0",
        parameter_hash=SHA_D,
        dependency_fingerprints=(SHA_E,),
    )


def _trace() -> ComputationTrace:
    return ComputationTrace(
        sample_count=2,
        source_start_t_ns=0,
        source_end_t_ns=1,
        analysis_start_t_ns=0,
        analysis_end_t_ns=1,
        grid_id="grid-1",
        window_ids=("window-1",),
        interpolation_method="none",
        matching_method="direct",
        diagnostics=(),
    )


def _result() -> AnchorResultV2:
    return AnchorResultV2(
        anchor_id="O1",
        calculation_status=AnchorCalculationStatusV2.COMPUTED,
        evidence_state=EvidenceState.UNACCEPTABLE,
        evidence_likelihood=EvidenceLikelihood(
            state_order=("unacceptable", "adequate", "desired"),
            values=(1.0, 0.0, 0.0),
        ),
        continuous_score=0.0,
        primary_value=MetricValue(scalar_kind="float", value=1.25, unit="m"),
        primary_value_reason=None,
        classification_override=None,
        raw_metrics={"error": MetricValue(scalar_kind="float", value=1.25, unit="m")},
        phase_results=(),
        event_results=(),
        derived_artifacts=(_artifact_ref(),),
        diagnostics=(),
        provenance=AnchorResultProvenance(
            plugin_id="o1-plugin",
            plugin_version="0.1.0",
            implementation_digest=SHA_E,
            parameter_hash=SHA_D,
            dependency_fingerprints=(),
            computation_trace=_trace(),
        ),
        result_fingerprint=SHA_F,
    )


def _report(result: AnchorResultV2) -> AnchorEvaluationReport:
    return AnchorEvaluationReport(
        session_id="session-1",
        disposition=AnchorEvaluationDisposition.READY,
        inventory=(
            AnchorInventoryItem(
                anchor_id=result.anchor_id,
                capability_status=AnchorCapabilityStatus.AVAILABLE,
                evaluation_status=AnchorInventoryStatus.EXECUTED,
                result_fingerprint=result.result_fingerprint,
                global_block_reason=None,
                diagnostics=(),
            ),
        ),
        results=(result,),
        expected_count=1,
        executed_count=1,
        applicable_count=1,
        computed_count=1,
        raw_availability=1.0,
        catalog_fingerprint=SHA_A,
        registry_fingerprint=SHA_B,
        execution_plan_fingerprint=SHA_C,
        evaluation_fingerprint=SHA_D,
        scientific_validation_status=ScientificValidationStatus.NOT_SUPPORTED,
        diagnostics=(),
    )


def _input_contract(table_role: str) -> ResolvedInputTableContract:
    return ResolvedInputTableContract(
        modality=CoreModality.X,
        table_role=table_role,
        stream_aligned_schema_id="x-aligned-v0.1",
        table_aligned_schema_id=f"x-{table_role}-aligned-v0.1",
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


def _execution_entry(anchor_id: str = "O1") -> AnchorExecutionEntry:
    return AnchorExecutionEntry(
        anchor_id=anchor_id,
        definition_version="0.1.0",
        lifecycle="active",
        canonical_order=0,
        plugin_id=f"{anchor_id.lower()}-plugin",
        plugin_version="0.1.0",
        api_version="0.1.0",
        definition_fingerprint=SHA_A,
        implementation_digest=SHA_B,
        parameter_schema_id=f"{anchor_id.lower()}-parameters-0.1",
        parameters={},
        parameter_hash=parameter_snapshot_fingerprint({}),
        required_streams=(CoreModality.X,),
        required_context_paths=(),
        required_semantic_paths=(),
        required_reference_ids=(),
        applicability=SemanticApplicabilityStatus.APPLICABLE,
        phase_scope=(),
        event_scope=(),
        dependencies=(),
        measurement_schema_id="anchor-measurement-0.1.0",
        result_schema_id="anchor-result-0.2.0",
        artifact_recipes=(_artifact_recipe(),),
        temporal_recipe={"scope": "session"},
        scorer_policy=ScorerPolicy(
            scorer_id="hard_threshold_v1",
            scorer_version="0.1.0",
            policy_schema_id="ordered-dau-threshold-policy-v0.1",
            parameters={
                "state_order": ["unacceptable", "adequate", "desired"],
                "evaluation_order": ["desired", "adequate"],
                "rules": [],
                "fallback_state": "unacceptable",
                "computed_u_overrides": [],
            },
            policy_hash=SHA_C,
        ),
    )


def _nonempty_plan() -> AnchorExecutionPlan:
    return AnchorExecutionPlan(
        plan_id="tiny-plan",
        model_profile_id="tiny-profile",
        scientific_validation_status=ScientificValidationStatus.NOT_SUPPORTED,
        catalog_fingerprint=SHA_A,
        registry_fingerprint=SHA_B,
        source_snapshot_fingerprint=SHA_C,
        synchronization_fingerprint=SHA_D,
        semantic_snapshot_fingerprint=SHA_E,
        reference_set_fingerprint=SHA_F,
        entries=(_execution_entry(),),
        input_table_contracts=(_input_contract("attitude"), _input_contract("samples")),
        algorithm_profiles=(),
        preprocessing_recipes=(),
        parameter_fingerprint=SHA_A,
        plan_fingerprint=SHA_B,
    )


def test_jcs_bytes_match_rfc8785_map_unicode_and_number_rules() -> None:
    assert jcs_bytes({"b": 1, "a": "é", "negative_zero": -0.0}) == (
        b'{"a":"\xc3\xa9","b":1,"negative_zero":0}'
    )
    assert jcs_bytes((True, None, 1.0)) == b"[true,null,1]"


def test_jcs_matches_published_number_vector_and_utf16_property_order() -> None:
    assert (
        jcs_bytes({"numbers": [333333333.33333329, 1e30, 4.50, 2e-3, 1e-27]})
        == b'{"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27]}'
    )
    assert jcs_bytes({"\ue000": 1, "\U0001f600": 2}) == (b'{"\xf0\x9f\x98\x80":2,"\xee\x80\x80":1}')


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (5e-324, b"5e-324"),
        (1.7976931348623157e308, b"1.7976931348623157e+308"),
        (1e-7, b"1e-7"),
        (1e-6, b"0.000001"),
    ),
)
def test_jcs_edge_floats_use_ecmascript_serialization(value: float, expected: bytes) -> None:
    assert jcs_bytes(value) == expected


@pytest.mark.parametrize("value", (SAFE_INTEGER, -SAFE_INTEGER))
def test_jcs_accepts_both_safe_integer_boundaries(value: int) -> None:
    assert jcs_bytes(value) == str(value).encode("ascii")


@pytest.mark.parametrize("value", (SAFE_INTEGER + 1, -SAFE_INTEGER - 1, float("nan"), float("inf")))
def test_jcs_rejects_values_outside_the_canonical_number_domain(value: int | float) -> None:
    with pytest.raises(ValueError):
        jcs_bytes(value)


@pytest.mark.parametrize("value", (b"bytes", {1: "non-string-key"}, "\ud800"))
def test_jcs_rejects_unsupported_python_or_unicode_shapes(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        jcs_bytes(value)


def test_typed_hash_uses_exact_ascii_nul_and_uint64_framing() -> None:
    payload = {"message": "值"}
    canonical = jcs_bytes(payload)
    framed = b"example-type\0" + b"0.1.0\0" + struct.pack(">Q", len(canonical)) + canonical
    assert typed_json_sha256("example-type", "0.1.0", payload) == hashlib.sha256(framed).hexdigest()

    for type_id, version in (("", "0.1.0"), ("é", "0.1.0"), ("type\0id", "0.1.0")):
        with pytest.raises(ValueError):
            typed_json_sha256(type_id, version, payload)


def test_schema_descriptor_and_logical_table_use_the_exact_nested_arrays() -> None:
    descriptor = _descriptor()
    rows = _rows()
    assert schema_descriptor_sha256("tiny-v0.1", descriptor) == typed_json_sha256(
        "typed-inline-schema-descriptor", "0.1.0", ["tiny-v0.1", descriptor]
    )
    expected_payload = [
        ["tiny-v0.1", descriptor, ["t_ns"]],
        [[0, 1.25, True], [1, -2.5, False]],
    ]
    assert logical_table_sha256("tiny-v0.1", descriptor, rows, ("t_ns",)) == (
        typed_json_sha256("logical-table", "0.1.0", expected_payload)
    )
    assert logical_table_sha256("tiny-v0.1", descriptor, (), ("t_ns",))


def _scalar_descriptor(dtype_id: str, *, nullable: bool = False) -> dict[str, Any]:
    return {
        "type": "table",
        "fields": [
            {"name": "row", "dtype": "i64", "unit": "index", "nullable": False},
            {"name": "value", "dtype": dtype_id, "unit": "value", "nullable": nullable},
        ],
        "canonical_order_keys": ["row"],
    }


@pytest.mark.parametrize(
    ("dtype_id", "valid_value", "invalid_value"),
    (
        ("bool", True, 1),
        ("i8", 127, 128),
        ("i16", -32768, -32769),
        ("i32", 2_147_483_647, 2_147_483_648),
        ("i64", SAFE_INTEGER, SAFE_INTEGER + 1),
        ("u8", 255, 256),
        ("u16", 65_535, 65_536),
        ("u32", 4_294_967_295, 4_294_967_296),
        ("u64", SAFE_INTEGER, SAFE_INTEGER + 1),
        ("f32", 3.0e38, 3.5e38),
        ("f64", 1.7976931348623157e308, float("inf")),
        ("utf8", "é", "\ud800"),
    ),
)
def test_all_twelve_primitive_dtypes_enforce_strict_values_and_bounds(
    dtype_id: str, valid_value: JsonValue, invalid_value: JsonValue
) -> None:
    descriptor = _scalar_descriptor(dtype_id)
    assert logical_table_sha256(
        "scalar-v0.1", descriptor, ({"row": 0, "value": valid_value},), ("row",)
    )
    with pytest.raises((TypeError, ValueError)):
        logical_table_sha256(
            "scalar-v0.1", descriptor, ({"row": 0, "value": invalid_value},), ("row",)
        )


def test_logical_table_enforces_nullable_and_nonnullable_values() -> None:
    nullable = _scalar_descriptor("f64", nullable=True)
    assert logical_table_sha256("nullable-v0.1", nullable, ({"row": 0, "value": None},), ("row",))
    with pytest.raises((TypeError, ValueError)):
        logical_table_sha256(
            "required-v0.1",
            _scalar_descriptor("f64"),
            ({"row": 0, "value": None},),
            ("row",),
        )


@pytest.mark.parametrize(
    ("dtype_id", "values"),
    (("i64", (1, 0)), ("bool", (True, False)), ("utf8", ("b", "a"))),
)
def test_logical_table_rejects_unsorted_order_keys(
    dtype_id: str, values: tuple[JsonValue, JsonValue]
) -> None:
    descriptor = {
        "type": "table",
        "fields": [{"name": "key", "dtype": dtype_id, "unit": "id", "nullable": False}],
        "canonical_order_keys": ["key"],
    }
    with pytest.raises((TypeError, ValueError)):
        logical_table_sha256(
            "ordered-v0.1",
            descriptor,
            ({"key": values[0]}, {"key": values[1]}),
            ("key",),
        )


def test_logical_table_rejects_duplicate_or_nullable_order_keys() -> None:
    descriptor = _scalar_descriptor("f64")
    duplicate_rows = ({"row": 0, "value": 1.0}, {"row": 0, "value": 2.0})
    with pytest.raises((TypeError, ValueError)):
        logical_table_sha256("duplicate-v0.1", descriptor, duplicate_rows, ("row",))

    nullable_key = _scalar_descriptor("f64")
    nullable_key["fields"][0]["nullable"] = True
    with pytest.raises((TypeError, ValueError)):
        logical_table_sha256(
            "nullable-key-v0.1",
            nullable_key,
            ({"row": 0, "value": 1.0},),
            ("row",),
        )


@pytest.mark.parametrize("mutation", ("extra-field", "missing-field", "bool-as-int", "row-order"))
def test_logical_table_rejects_noncanonical_rows(mutation: str) -> None:
    rows = [dict(row) for row in _rows()]
    if mutation == "extra-field":
        rows[0]["extra"] = 1
    elif mutation == "missing-field":
        del rows[0]["value"]
    elif mutation == "bool-as-int":
        rows[0]["valid"] = 1
    else:
        rows.reverse()
    with pytest.raises((TypeError, ValueError)):
        logical_table_sha256("tiny-v0.1", _descriptor(), rows, ("t_ns",))


def test_descriptor_validation_is_closed_and_declared_field_order_is_identity() -> None:
    descriptor = _descriptor()
    reordered = deepcopy(descriptor)
    reordered["fields"][1], reordered["fields"][2] = (
        reordered["fields"][2],
        reordered["fields"][1],
    )
    assert schema_descriptor_sha256("tiny-v0.1", reordered) != schema_descriptor_sha256(
        "tiny-v0.1", descriptor
    )

    invalid = deepcopy(descriptor)
    invalid["unexpected"] = True
    with pytest.raises(ValueError):
        schema_descriptor_sha256("tiny-v0.1", invalid)
    with pytest.raises(ValueError):
        logical_table_sha256("tiny-v0.1", descriptor, _rows(), ("value",))


def test_parameter_scorer_and_algorithm_profile_hashes_use_fixed_projections() -> None:
    parameters = {"threshold": 1.25, "state_order": ["u", "a", "d"]}
    parameter_hash = parameter_snapshot_fingerprint(parameters)
    assert parameter_hash == typed_json_sha256("parameter-snapshot", "0.1.0", parameters)
    assert parameter_hash == parameter_snapshot_fingerprint(
        {"state_order": ["u", "a", "d"], "threshold": 1.25}
    )
    assert parameter_hash != parameter_snapshot_fingerprint({**parameters, "threshold": 2.0})

    policy = ScorerPolicy(
        scorer_id="hard-threshold-v1",
        scorer_version="0.1.0",
        policy_schema_id="hard-threshold-policy-v0.1",
        parameters=parameters,
        policy_hash=SHA_A,
    )
    expected = [
        policy.scorer_id,
        policy.scorer_version,
        policy.policy_schema_id,
        policy.parameters,
    ]
    assert scorer_policy_fingerprint(policy) == typed_json_sha256(
        "scorer-policy", "0.1.0", expected
    )
    assert scorer_policy_fingerprint(
        policy.model_copy(update={"policy_hash": SHA_B})
    ) == scorer_policy_fingerprint(policy)

    profile = ResolvedAlgorithmProfile(
        profile_id="o1-algorithm-profile",
        profile_version="0.1.0",
        parameters=parameters,
        parameter_hash=parameter_hash,
        implementation_digest=SHA_B,
        output_schema_id="o1-algorithm-profile-output-v0.1",
    )
    assert profile.parameter_hash == parameter_snapshot_fingerprint(profile.parameters)


def test_all_task7_scorer_annotations_compile_to_the_exact_policy_hash() -> None:
    assert len(catalog_module.REFERENCE_ANCHOR_PARAMETER_SCHEMA_IDS) == 18
    for schema_id in catalog_module.REFERENCE_ANCHOR_PARAMETER_SCHEMA_IDS:
        document = json.loads(catalog_module.load_parameter_schema_bytes(schema_id))
        annotation = document["x-scorer-policy-default"]
        expected_payload = [
            annotation["scorer_id"],
            annotation["scorer_version"],
            annotation["policy_schema_id"],
            annotation["parameters"],
        ]
        expected_hash = typed_json_sha256("scorer-policy", "0.1.0", expected_payload)
        policy = ScorerPolicy(**annotation, policy_hash=expected_hash)

        assert scorer_policy_fingerprint(policy) == expected_hash
        assert (
            scorer_policy_fingerprint(policy.model_copy(update={"policy_hash": SHA_F}))
            == expected_hash
        )


def _algorithm_profile_parameters(source_anchor_id: str) -> dict[str, Any]:
    applicability = AnchorApplicability(
        anchor_id=source_anchor_id,
        status=SemanticApplicabilityStatus.APPLICABLE,
    )
    return {
        "semantic_snapshot_fingerprint": SHA_E,
        "source_entry": _execution_entry(source_anchor_id).model_dump(mode="json"),
        "parameter_schema_sha256": catalog_module.parameter_schema_sha256(
            f"{source_anchor_id.lower()}-parameters-0.1"
        ),
        "applicability": applicability.model_dump(mode="json"),
        "input_table_contracts": [_input_contract("samples").model_dump(mode="json")],
        "semantic_projection": {
            "phases": [],
            "envelopes": [],
            "control_mappings": [],
        },
        "preprocessing_recipes": [],
    }


def test_task7_o1_o5_o7_algorithm_profiles_use_exact_identity_and_parameter_hash() -> None:
    expected_keys = {
        "semantic_snapshot_fingerprint",
        "source_entry",
        "parameter_schema_sha256",
        "applicability",
        "input_table_contracts",
        "semantic_projection",
        "preprocessing_recipes",
    }
    identities = tuple(dict(item) for item in catalog_module.REFERENCE_ALGORITHM_PROFILE_IDENTITIES)
    assert tuple(item["source_anchor_id"] for item in identities) == ("O1", "O5", "O7")

    for identity in identities:
        source_anchor_id = cast(str, identity["source_anchor_id"])
        parameters = _algorithm_profile_parameters(source_anchor_id)
        parameter_hash = parameter_snapshot_fingerprint(parameters)
        profile = ResolvedAlgorithmProfile(
            profile_id=cast(str, identity["profile_id"]),
            profile_version=cast(str, identity["profile_version"]),
            parameters=parameters,
            parameter_hash=parameter_hash,
            implementation_digest=SHA_B,
            output_schema_id=cast(str, identity["output_schema_id"]),
        )

        assert set(profile.parameters) == expected_keys
        assert profile.profile_id == f"{source_anchor_id.lower()}-algorithm-profile"
        assert profile.parameter_hash == typed_json_sha256(
            "parameter-snapshot", "0.1.0", parameters
        )
        for key in expected_keys:
            mutated = deepcopy(parameters)
            del mutated[key]
            assert parameter_snapshot_fingerprint(mutated) != parameter_hash


def test_definition_fingerprints_are_complete_strict_model_dumps() -> None:
    plugin = _plugin_definition()
    provider = _preprocessing_definition()
    assert plugin_definition_fingerprint(plugin) == typed_json_sha256(
        "anchor-plugin-definition", "0.1.0", plugin.model_dump(mode="json")
    )
    assert preprocessing_definition_fingerprint(provider) == typed_json_sha256(
        "preprocessing-provider-definition", "0.1.0", provider.model_dump(mode="json")
    )
    changed = plugin.model_copy(update={"plugin_version": "0.2.0"})
    assert plugin_definition_fingerprint(changed) != plugin_definition_fingerprint(plugin)


def test_implementation_and_registry_projections_have_exact_self_ownership() -> None:
    plugin = _plugin_registry_entry()
    provider = _preprocessing_registry_entry()
    expected_plugin = plugin.model_dump(mode="json")
    del expected_plugin["implementation_digest"]
    expected_provider = provider.model_dump(mode="json")
    del expected_provider["implementation_digest"]
    assert plugin_implementation_digest_payload(plugin) == expected_plugin
    assert preprocessing_implementation_digest_payload(provider) == expected_provider
    assert (
        plugin_implementation_digest_payload(
            plugin.model_copy(update={"implementation_digest": SHA_A})
        )
        == expected_plugin
    )

    registry = AnchorRuntimeRegistry(entries=(plugin,), preprocessors=(provider,))
    assert runtime_registry_fingerprint(registry) == typed_json_sha256(
        "anchor-runtime-registry", "0.1.0", registry.model_dump(mode="json")
    )
    changed = AnchorRuntimeRegistry(
        entries=(plugin.model_copy(update={"implementation_digest": SHA_A}),),
        preprocessors=(provider,),
    )
    assert runtime_registry_fingerprint(changed) != runtime_registry_fingerprint(registry)


def test_catalog_and_execution_plan_projections_exclude_only_their_self_field() -> None:
    catalog = catalog_module.load_packaged_catalog()
    expected_catalog = catalog.model_dump(mode="json")
    del expected_catalog["catalog_fingerprint"]
    assert catalog_fingerprint_payload(catalog) == expected_catalog
    assert (
        catalog_fingerprint_payload(catalog.model_copy(update={"catalog_fingerprint": SHA_F}))
        == expected_catalog
    )
    expected_hash = typed_json_sha256("anchor-catalog", "0.1.0", expected_catalog)
    assert packaged_catalog_fingerprint() == expected_hash
    assert catalog.catalog_fingerprint == expected_hash != "0" * 64

    plan = AnchorExecutionPlan(
        plan_id="tiny-plan",
        model_profile_id="tiny-profile",
        scientific_validation_status=ScientificValidationStatus.NOT_SUPPORTED,
        catalog_fingerprint=SHA_A,
        registry_fingerprint=SHA_B,
        source_snapshot_fingerprint=SHA_C,
        synchronization_fingerprint=SHA_D,
        semantic_snapshot_fingerprint=SHA_E,
        reference_set_fingerprint=SHA_F,
        entries=(),
        input_table_contracts=(),
        algorithm_profiles=(),
        preprocessing_recipes=(),
        parameter_fingerprint=SHA_A,
        plan_fingerprint=SHA_B,
    )
    expected_plan = plan.model_dump(mode="json")
    del expected_plan["plan_fingerprint"]
    assert execution_plan_fingerprint_payload(plan) == expected_plan
    assert (
        execution_plan_fingerprint_payload(plan.model_copy(update={"plan_fingerprint": SHA_C}))
        == expected_plan
    )


def test_nonempty_plan_binds_every_input_table_and_field_contract_member() -> None:
    plan = _nonempty_plan()
    expected = typed_json_sha256(
        "anchor-execution-plan", "0.1.0", execution_plan_fingerprint_payload(plan)
    )
    first, second = plan.input_table_contracts
    value_field = first.fields[1]
    contract_mutations = {
        "table-role": first.model_copy(update={"table_role": "controls"}),
        "stream-schema": first.model_copy(update={"stream_aligned_schema_id": "x-v2-aligned-v0.1"}),
        "table-schema": first.model_copy(
            update={"table_aligned_schema_id": "x-attitude-v2-aligned-v0.1"}
        ),
        "coordinate-frame": first.model_copy(update={"coordinate_frame_id": "body"}),
        "field-name": first.model_copy(
            update={
                "fields": (
                    first.fields[0],
                    value_field.model_copy(update={"field_name": "value-2"}),
                )
            }
        ),
        "field-dtype": first.model_copy(
            update={
                "fields": (
                    first.fields[0],
                    value_field.model_copy(update={"dtype_id": "f32"}),
                )
            }
        ),
        "field-unit": first.model_copy(
            update={
                "fields": (
                    first.fields[0],
                    value_field.model_copy(update={"unit": "ft"}),
                )
            }
        ),
        "field-nullable": first.model_copy(
            update={
                "fields": (
                    first.fields[0],
                    value_field.model_copy(update={"nullable": True}),
                )
            }
        ),
        "physical-field-order": first.model_copy(update={"fields": tuple(reversed(first.fields))}),
    }
    for label, changed_contract in contract_mutations.items():
        changed_plan = plan.model_copy(update={"input_table_contracts": (changed_contract, second)})
        actual = typed_json_sha256(
            "anchor-execution-plan",
            "0.1.0",
            execution_plan_fingerprint_payload(changed_plan),
        )
        assert actual != expected, label

    changed_contracts = tuple(
        contract.model_copy(
            update={
                "modality": CoreModality.U,
                "stream_aligned_schema_id": "u-aligned-v0.1",
                "table_aligned_schema_id": contract.table_aligned_schema_id.replace("x-", "u-"),
            }
        )
        for contract in plan.input_table_contracts
    )
    changed_entry = plan.entries[0].model_copy(update={"required_streams": (CoreModality.U,)})
    modality_plan = plan.model_copy(
        update={"entries": (changed_entry,), "input_table_contracts": changed_contracts}
    )
    assert (
        typed_json_sha256(
            "anchor-execution-plan",
            "0.1.0",
            execution_plan_fingerprint_payload(modality_plan),
        )
        != expected
    )


def test_plan_fingerprint_rejects_noncanonical_outer_input_table_order() -> None:
    plan = _nonempty_plan()
    reordered = plan.model_copy(
        update={"input_table_contracts": tuple(reversed(plan.input_table_contracts))}
    )
    with pytest.raises((TypeError, ValueError)):
        execution_plan_fingerprint_payload(reordered)


def _task7_json_bytes(document: object) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


@pytest.mark.parametrize("claimed_hash", ("0" * 64, SHA_F), ids=("sentinel", "stale"))
def test_catalog_loader_owned_boundary_rejects_untrusted_hash_claims(
    claimed_hash: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    document = catalog_module.load_packaged_catalog().model_dump(mode="json")
    document["catalog_fingerprint"] = claimed_hash
    (tmp_path / "reference-model-v0.1-anchor-catalog.json").write_bytes(_task7_json_bytes(document))
    monkeypatch.setattr(catalog_module, "files", lambda _package: tmp_path)
    with pytest.raises(ValueError):
        catalog_module.load_packaged_catalog()


def test_result_and_report_projections_are_complete_and_storage_independent() -> None:
    result = _result()
    artifact_payload = logical_artifact_identity_payload(result.derived_artifacts[0])
    assert "storage_file_sha256" not in artifact_payload
    expected_result = result.model_dump(mode="json")
    del expected_result["result_fingerprint"]
    expected_result["derived_artifacts"] = [artifact_payload]
    assert anchor_result_fingerprint_payload(result) == expected_result
    assert (
        anchor_result_fingerprint_payload(result.model_copy(update={"result_fingerprint": SHA_A}))
        == expected_result
    )
    storage_changed = result.model_copy(
        update={"derived_artifacts": (_artifact_ref(storage_hash=SHA_F),)}
    )
    assert anchor_result_fingerprint_payload(storage_changed) == expected_result

    report = _report(result)
    expected_report = report.model_dump(mode="json")
    del expected_report["evaluation_fingerprint"]
    expected_report["results"] = [result.result_fingerprint]
    expected_report["reachable_logical_artifacts"] = [artifact_payload]
    assert evaluation_fingerprint_payload(report) == expected_report
    assert (
        evaluation_fingerprint_payload(report.model_copy(update={"evaluation_fingerprint": SHA_A}))
        == expected_report
    )
    changed = report.model_copy(update={"catalog_fingerprint": SHA_F})
    assert evaluation_fingerprint_payload(changed) != expected_report


def test_logical_blob_artifact_boundary_recomputes_bytes_before_consumption() -> None:
    payload_bytes = b"tiny-artifact"
    digest = hashlib.sha256(payload_bytes).hexdigest()
    ref = AnchorArtifactRef(
        artifact_id="tiny-blob",
        kind="audit_blob",
        schema_id="tiny-blob-v0.1",
        logical_content_sha256=digest,
        storage_file_sha256=digest,
        row_count=0,
        start_t_ns=None,
        end_t_ns=None,
        grid_hash=None,
        producer_anchor_id="O1",
        producer_plugin_id="o1-plugin",
        producer_plugin_version="0.1.0",
        parameter_hash=SHA_A,
        dependency_fingerprints=(),
    )
    payload = ReadOnlyBlobPayload(
        schema_id=ref.schema_id,
        payload_bytes=payload_bytes,
        artifact_kind=ref.kind,
        start_t_ns=None,
        end_t_ns=None,
        logical_content_sha256=digest,
    )
    resolved = ResolvedArtifactDependency(ref=ref, payload=payload)
    validate_logical_artifact_ref(ref, resolved)

    false_ref = ref.model_copy(update={"producer_plugin_version": "0.2.0"})
    with pytest.raises(ValueError):
        validate_logical_artifact_ref(false_ref, resolved)

    stale_payload = ReadOnlyBlobPayload(
        schema_id=ref.schema_id,
        payload_bytes=b"tampered",
        artifact_kind=ref.kind,
        start_t_ns=None,
        end_t_ns=None,
        logical_content_sha256=digest,
    )
    with pytest.raises(ValueError):
        validate_logical_artifact_ref(
            ref, ResolvedArtifactDependency(ref=ref, payload=stale_payload)
        )
