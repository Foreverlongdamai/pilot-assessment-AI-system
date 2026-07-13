from __future__ import annotations

import copy
import importlib
import json
import math
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "anchor_result_v2_computed.json"

EXPECTED_PUBLIC_FIELDS = {
    "MetricValue": {"scalar_kind", "value", "unit"},
    "ClassificationOverride": {"code", "details"},
    "SourceWindowV2": {
        "window_id",
        "start_t_ns",
        "end_t_ns",
        "phase_id",
        "event_id",
        "include_session_terminal_point",
    },
    "AnchorArtifactRef": {
        "artifact_id",
        "kind",
        "schema_id",
        "logical_content_sha256",
        "storage_file_sha256",
        "row_count",
        "start_t_ns",
        "end_t_ns",
        "grid_hash",
        "producer_anchor_id",
        "producer_plugin_id",
        "producer_plugin_version",
        "parameter_hash",
        "dependency_fingerprints",
    },
    "ComputationTrace": {
        "sample_count",
        "source_start_t_ns",
        "source_end_t_ns",
        "analysis_start_t_ns",
        "analysis_end_t_ns",
        "grid_id",
        "window_ids",
        "interpolation_method",
        "matching_method",
        "diagnostics",
    },
    "AnchorBreakdownResult": {
        "breakdown_id",
        "calculation_status",
        "evidence_state",
        "evidence_likelihood",
        "continuous_score",
        "primary_value",
        "primary_value_reason",
        "raw_metrics",
        "classification_override",
        "trace",
        "diagnostics",
    },
    "AnchorResultProvenance": {
        "plugin_id",
        "plugin_version",
        "implementation_digest",
        "parameter_hash",
        "dependency_fingerprints",
        "computation_trace",
    },
    "AnchorResultV2": {
        "contract_id",
        "contract_version",
        "anchor_id",
        "calculation_status",
        "evidence_state",
        "evidence_likelihood",
        "continuous_score",
        "primary_value",
        "primary_value_reason",
        "classification_override",
        "raw_metrics",
        "phase_results",
        "event_results",
        "derived_artifacts",
        "diagnostics",
        "provenance",
        "result_fingerprint",
    },
}


def _v2_module() -> Any:
    return importlib.import_module("pilot_assessment.contracts.anchor_v2")


def _v2_model() -> Any:
    return _v2_module().AnchorResultV2


@pytest.fixture
def computed_data() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _make_noncomputed(data: dict[str, Any], status: str) -> dict[str, Any]:
    candidate = copy.deepcopy(data)
    candidate.update(
        calculation_status=status,
        evidence_state=None,
        evidence_likelihood=None,
        continuous_score=None,
        primary_value=None,
        primary_value_reason=None,
        classification_override=None,
        raw_metrics={},
        phase_results=[],
        event_results=[],
        derived_artifacts=[],
    )
    return candidate


def _set_standard_computed_observation(
    target: dict[str, Any],
    *,
    values: list[float],
    state: str,
    score: float,
    primary_value_ms: float,
) -> None:
    target["evidence_likelihood"]["values"] = values
    target["evidence_state"] = state
    target["continuous_score"] = score
    target["primary_value"] = {
        "scalar_kind": "float",
        "value": primary_value_ms,
        "unit": "ms",
    }
    target["primary_value_reason"] = None
    target["classification_override"] = None
    target["raw_metrics"] = {
        "observed_wait_ms": {
            "scalar_kind": "float",
            "value": primary_value_ms,
            "unit": "ms",
        }
    }


def test_v2_contract_module_and_exact_public_field_sets_exist() -> None:
    module = _v2_module()
    public_contracts = importlib.import_module("pilot_assessment.contracts")

    assert {status.value for status in module.AnchorCalculationStatusV2} == {
        "computed",
        "missing_input",
        "not_applicable",
        "not_computable",
        "dependency_missing",
        "extractor_error",
    }
    for class_name, fields in EXPECTED_PUBLIC_FIELDS.items():
        assert set(getattr(module, class_name).model_fields) == fields
        assert getattr(public_contracts, class_name) is getattr(module, class_name)


def test_source_window_required_fields_defaults_and_scalar_types_are_frozen() -> None:
    source_window = _v2_module().SourceWindowV2
    fields = source_window.model_fields

    assert all(fields[name].is_required() for name in ("phase_id", "event_id"))
    assert fields["include_session_terminal_point"].default is False

    valid = {
        "window_id": "phase-window-1",
        "start_t_ns": 0,
        "end_t_ns": 1,
        "phase_id": None,
        "event_id": None,
    }
    assert source_window.model_validate(valid).include_session_terminal_point is False

    for field, value in (
        ("start_t_ns", 0.0),
        ("end_t_ns", 0),
        ("include_session_terminal_point", "false"),
    ):
        invalid = copy.deepcopy(valid)
        invalid[field] = value
        with pytest.raises(ValidationError):
            source_window.model_validate(invalid)


def test_computed_v2_fixture_round_trips_without_changing_json_scalar_kinds(
    computed_data: dict[str, Any],
) -> None:
    result = _v2_model().model_validate(computed_data)
    dumped = result.model_dump(mode="json")

    assert dumped == computed_data
    assert type(dumped["raw_metrics"]["miss_count"]["value"]) is int
    assert type(dumped["raw_metrics"]["observed_wait_ms"]["value"]) is float
    assert type(dumped["derived_artifacts"][0]["row_count"]) is int
    assert type(dumped["provenance"]["computation_trace"]["source_end_t_ns"]) is int


@pytest.mark.parametrize("field", ["evidence_state", "evidence_likelihood", "continuous_score"])
def test_computed_result_requires_complete_observation(
    computed_data: dict[str, Any], field: str
) -> None:
    computed_data[field] = None
    with pytest.raises(ValidationError):
        _v2_model().model_validate(computed_data)


@pytest.mark.parametrize(
    "status",
    [
        "missing_input",
        "not_applicable",
        "not_computable",
        "dependency_missing",
        "extractor_error",
    ],
)
def test_noncomputed_statuses_omit_observation_and_measurement_fields(
    computed_data: dict[str, Any], status: str
) -> None:
    candidate = _make_noncomputed(computed_data, status)
    result = _v2_model().model_validate(candidate)
    assert result.evidence_state is None

    for field, value in (
        ("evidence_state", "unacceptable"),
        (
            "evidence_likelihood",
            {"state_order": ["unacceptable", "adequate", "desired"], "values": [1.0, 0.0, 0.0]},
        ),
        ("continuous_score", 0.0),
        ("primary_value", {"scalar_kind": "float", "value": 1.0, "unit": "ms"}),
        ("primary_value_reason", "partial_value"),
        ("classification_override", {"code": "response_missed", "details": {}}),
    ):
        invalid = copy.deepcopy(candidate)
        invalid[field] = value
        with pytest.raises(ValidationError):
            _v2_model().model_validate(invalid)


@pytest.mark.parametrize(
    ("values", "state", "score", "primary_value_ms"),
    [
        ([0.0, 1.0, 0.0], "adequate", 0.5, 750.0),
        ([0.0, 0.0, 1.0], "desired", 1.0, 250.0),
    ],
)
def test_canonical_one_hot_likelihood_determines_state_and_score(
    computed_data: dict[str, Any],
    values: list[float],
    state: str,
    score: float,
    primary_value_ms: float,
) -> None:
    _set_standard_computed_observation(
        computed_data,
        values=values,
        state=state,
        score=score,
        primary_value_ms=primary_value_ms,
    )
    _set_standard_computed_observation(
        computed_data["event_results"][0],
        values=values,
        state=state,
        score=score,
        primary_value_ms=primary_value_ms,
    )

    result = _v2_model().model_validate(computed_data)
    assert result.evidence_state.value == state


def test_computed_result_accepts_a_typed_scalar_primary_without_a_null_reason(
    computed_data: dict[str, Any],
) -> None:
    for target in (computed_data, computed_data["event_results"][0]):
        _set_standard_computed_observation(
            target,
            values=[0.0, 0.0, 1.0],
            state="desired",
            score=1.0,
            primary_value_ms=250.0,
        )

    result = _v2_model().model_validate(computed_data)
    assert result.primary_value is not None
    assert result.primary_value.scalar_kind == "float"
    assert result.primary_value.value == 250.0
    assert result.primary_value_reason is None

    computed_data["primary_value_reason"] = "response_missed"
    with pytest.raises(ValidationError):
        _v2_model().model_validate(computed_data)


@pytest.mark.parametrize(
    ("field_path", "value"),
    [
        (("evidence_likelihood", "state_order"), ["desired", "adequate", "unacceptable"]),
        (("evidence_likelihood", "values"), [0.5, 0.5, 0.0]),
        (("evidence_state",), "desired"),
        (("continuous_score",), 0.5),
    ],
)
def test_one_hot_state_order_state_and_score_cannot_disagree(
    computed_data: dict[str, Any], field_path: tuple[str, ...], value: object
) -> None:
    target: Any = computed_data
    for key in field_path[:-1]:
        target = target[key]
    target[field_path[-1]] = value

    with pytest.raises(ValidationError):
        _v2_model().model_validate(computed_data)


def test_override_is_allowed_only_for_computed_unacceptable(
    computed_data: dict[str, Any],
) -> None:
    assert _v2_model().model_validate(computed_data).classification_override is not None

    computed_data["evidence_state"] = "adequate"
    computed_data["evidence_likelihood"]["values"] = [0.0, 1.0, 0.0]
    computed_data["continuous_score"] = 0.5
    with pytest.raises(ValidationError):
        _v2_model().model_validate(computed_data)


def test_null_primary_requires_reason_and_typed_raw_metric(
    computed_data: dict[str, Any],
) -> None:
    computed_data["primary_value_reason"] = None
    with pytest.raises(ValidationError):
        _v2_model().model_validate(computed_data)

    computed_data["primary_value_reason"] = "response_missed"
    computed_data["raw_metrics"] = {}
    with pytest.raises(ValidationError):
        _v2_model().model_validate(computed_data)


@pytest.mark.parametrize(
    ("scalar_kind", "value"),
    [
        ("integer", 1.0),
        ("integer", True),
        ("float", 1),
        ("float", math.nan),
        ("float", math.inf),
    ],
)
def test_metric_scalar_kind_is_strict_and_finite(
    computed_data: dict[str, Any], scalar_kind: str, value: object
) -> None:
    computed_data["raw_metrics"]["miss_count"].update(
        scalar_kind=scalar_kind,
        value=value,
    )
    with pytest.raises(ValidationError):
        _v2_model().model_validate(computed_data)


@pytest.mark.parametrize(
    ("field_path", "value"),
    [
        (("derived_artifacts", 0, "row_count"), 201.0),
        (("derived_artifacts", 0, "start_t_ns"), 0.0),
        (("provenance", "computation_trace", "sample_count"), 201.0),
        (("provenance", "computation_trace", "source_end_t_ns"), 2000000000.0),
    ],
)
def test_counts_and_timestamps_require_exact_json_integers(
    computed_data: dict[str, Any], field_path: tuple[str | int, ...], value: object
) -> None:
    target: Any = computed_data
    for key in field_path[:-1]:
        target = target[key]
    target[field_path[-1]] = value
    with pytest.raises(ValidationError):
        _v2_model().model_validate(computed_data)


def test_breakdown_has_its_own_status_observation_and_trace(
    computed_data: dict[str, Any],
) -> None:
    breakdown_model = _v2_module().AnchorBreakdownResult
    breakdown = computed_data["event_results"][0]
    breakdown["evidence_likelihood"] = None
    with pytest.raises(ValidationError):
        breakdown_model.model_validate(breakdown)

    breakdown.update(
        calculation_status="missing_input",
        evidence_state=None,
        evidence_likelihood=None,
        continuous_score=None,
        primary_value=None,
        primary_value_reason=None,
        classification_override=None,
        raw_metrics={},
    )
    assert breakdown_model.model_validate(breakdown).evidence_state is None

    breakdown["trace"]["source_end_t_ns"] = -1
    with pytest.raises(ValidationError):
        breakdown_model.model_validate(breakdown)


@pytest.mark.parametrize(
    "legacy_field",
    [
        "model_version",
        "quality",
        "thresholds_used",
        "parameters_used",
        "parameter_hash",
        "dependencies",
        "input_status_snapshot",
        "source_windows",
        "extensions",
        "quality_gates",
        "min_valid_coverage",
        "quality_transform",
    ],
)
def test_v2_rejects_legacy_and_quality_gate_fields(
    computed_data: dict[str, Any], legacy_field: str
) -> None:
    computed_data[legacy_field] = {}
    with pytest.raises(ValidationError):
        _v2_model().model_validate(computed_data)


def test_v2_rejects_legacy_invalid_quality_status(computed_data: dict[str, Any]) -> None:
    computed_data["calculation_status"] = "invalid_quality"
    with pytest.raises(ValidationError):
        _v2_model().model_validate(computed_data)


@pytest.mark.parametrize(
    ("field_path", "value"),
    [
        (("result_fingerprint",), "not-a-sha256"),
        (("derived_artifacts", 0, "logical_content_sha256"), "not-a-sha256"),
        (("classification_override", "details", "bad_number"), math.nan),
    ],
)
def test_fingerprints_and_nested_json_numbers_are_valid(
    computed_data: dict[str, Any], field_path: tuple[str | int, ...], value: object
) -> None:
    target: Any = computed_data
    for key in field_path[:-1]:
        target = target[key]
    target[field_path[-1]] = value
    with pytest.raises(ValidationError):
        _v2_model().model_validate(computed_data)
