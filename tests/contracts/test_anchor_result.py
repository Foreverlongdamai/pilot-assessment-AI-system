from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from pilot_assessment.contracts.anchor import (
    PROBABILITY_TOLERANCE,
    AnchorResult,
    CalculationStatus,
    EvidenceState,
)

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "anchor_result_computed.json"


@pytest.fixture
def anchor_data() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_computed_anchor_fixture_is_valid(anchor_data: dict[str, Any]) -> None:
    result = AnchorResult.model_validate(anchor_data)

    assert result.calculation_status is CalculationStatus.COMPUTED
    assert result.evidence_state is EvidenceState.ADEQUATE
    assert result.continuous_score == 0.5
    assert result.evidence_likelihood is not None
    assert result.evidence_likelihood.values == (0.0, 1.0, 0.0)


@pytest.mark.parametrize("field", ["evidence_state", "continuous_score", "evidence_likelihood"])
def test_computed_result_requires_all_observation_fields(
    anchor_data: dict[str, Any], field: str
) -> None:
    anchor_data[field] = None
    with pytest.raises(ValidationError):
        AnchorResult.model_validate(anchor_data)


def test_likelihood_requires_canonical_state_order(anchor_data: dict[str, Any]) -> None:
    anchor_data["evidence_likelihood"]["state_order"] = [
        "desired",
        "adequate",
        "unacceptable",
    ]
    with pytest.raises(ValidationError):
        AnchorResult.model_validate(anchor_data)


@pytest.mark.parametrize(
    "values",
    [
        [-0.1, 1.1, 0.0],
        [0.5, 0.5],
        [0.1, 0.2, 0.3],
        [math.nan, 1.0, 0.0],
        [math.inf, 0.0, 0.0],
    ],
)
def test_likelihood_requires_three_finite_probabilities_summing_to_one(
    anchor_data: dict[str, Any], values: list[float]
) -> None:
    anchor_data["evidence_likelihood"]["values"] = values
    with pytest.raises(ValidationError):
        AnchorResult.model_validate(anchor_data)


def test_continuous_score_must_match_ordinal_expectation(anchor_data: dict[str, Any]) -> None:
    anchor_data["continuous_score"] = 0.5 + 10 * PROBABILITY_TOLERANCE
    with pytest.raises(ValidationError):
        AnchorResult.model_validate(anchor_data)


def test_hard_threshold_requires_one_hot_likelihood_and_matching_state(
    anchor_data: dict[str, Any],
) -> None:
    not_one_hot = copy.deepcopy(anchor_data)
    not_one_hot["evidence_likelihood"]["values"] = [0.0, 0.8, 0.2]
    not_one_hot["continuous_score"] = 0.6
    with pytest.raises(ValidationError):
        AnchorResult.model_validate(not_one_hot)

    wrong_state = copy.deepcopy(anchor_data)
    wrong_state["evidence_state"] = "desired"
    with pytest.raises(ValidationError):
        AnchorResult.model_validate(wrong_state)


def test_soft_likelihood_tie_requires_explicit_tie_policy(anchor_data: dict[str, Any]) -> None:
    anchor_data["parameters_used"]["scoring_transform"] = "soft_transition_v1"
    anchor_data["evidence_likelihood"]["values"] = [0.4, 0.4, 0.2]
    anchor_data["continuous_score"] = 0.4
    with pytest.raises(ValidationError):
        AnchorResult.model_validate(anchor_data)

    anchor_data["parameters_used"]["tie_policy"] = "prefer_adequate"
    result = AnchorResult.model_validate(anchor_data)
    assert result.evidence_state is EvidenceState.ADEQUATE


def test_soft_likelihood_unique_maximum_must_match_evidence_state(
    anchor_data: dict[str, Any],
) -> None:
    anchor_data["parameters_used"]["scoring_transform"] = "soft_transition_v1"
    anchor_data["evidence_likelihood"]["values"] = [0.8, 0.1, 0.1]
    anchor_data["continuous_score"] = 0.15
    anchor_data["evidence_state"] = "desired"

    with pytest.raises(ValidationError):
        AnchorResult.model_validate(anchor_data)

    anchor_data["evidence_state"] = "unacceptable"
    assert AnchorResult.model_validate(anchor_data).evidence_state is EvidenceState.UNACCEPTABLE


def test_soft_likelihood_tie_policy_must_select_a_tied_state(
    anchor_data: dict[str, Any],
) -> None:
    anchor_data["parameters_used"]["scoring_transform"] = "soft_transition_v1"
    anchor_data["parameters_used"]["tie_policy"] = "prefer_desired"
    anchor_data["evidence_likelihood"]["values"] = [0.4, 0.4, 0.2]
    anchor_data["continuous_score"] = 0.4
    anchor_data["evidence_state"] = "desired"

    with pytest.raises(ValidationError):
        AnchorResult.model_validate(anchor_data)


@pytest.mark.parametrize(
    "status",
    [status for status in CalculationStatus if status is not CalculationStatus.COMPUTED],
)
def test_noncomputed_results_must_omit_bn_observation_fields(
    anchor_data: dict[str, Any], status: CalculationStatus
) -> None:
    anchor_data["calculation_status"] = status.value
    anchor_data["evidence_state"] = None
    anchor_data["continuous_score"] = None
    anchor_data["evidence_likelihood"] = None
    anchor_data["quality"]["passed"] = False
    anchor_data["quality"]["score"] = 0.0

    result = AnchorResult.model_validate(anchor_data)
    assert result.evidence_state is None

    anchor_data["evidence_state"] = "unacceptable"
    with pytest.raises(ValidationError):
        AnchorResult.model_validate(anchor_data)


def test_invalid_quality_requires_failed_quality_gate(anchor_data: dict[str, Any]) -> None:
    anchor_data["calculation_status"] = "invalid_quality"
    anchor_data["evidence_state"] = None
    anchor_data["continuous_score"] = None
    anchor_data["evidence_likelihood"] = None
    with pytest.raises(ValidationError):
        AnchorResult.model_validate(anchor_data)


@pytest.mark.parametrize("field", ["score", "valid_coverage"])
@pytest.mark.parametrize("value", [-0.1, 1.1, math.nan, math.inf])
def test_quality_values_are_finite_unit_intervals(
    anchor_data: dict[str, Any], field: str, value: float
) -> None:
    anchor_data["quality"][field] = value
    with pytest.raises(ValidationError):
        AnchorResult.model_validate(anchor_data)


def test_source_window_end_must_follow_start(anchor_data: dict[str, Any]) -> None:
    anchor_data["source_windows"][0]["end_t_ns"] = 0
    with pytest.raises(ValidationError):
        AnchorResult.model_validate(anchor_data)


def test_derived_artifact_path_cannot_escape_managed_root(anchor_data: dict[str, Any]) -> None:
    anchor_data["derived_artifacts"][0]["path"] = "../outside.parquet"
    with pytest.raises(ValidationError):
        AnchorResult.model_validate(anchor_data)


def test_window_trace_requires_complete_window_definition(anchor_data: dict[str, Any]) -> None:
    del anchor_data["derived_artifacts"][0]["step_s"]
    with pytest.raises(ValidationError):
        AnchorResult.model_validate(anchor_data)


def test_parameter_hash_is_required_sha256(anchor_data: dict[str, Any]) -> None:
    anchor_data["parameter_hash"] = "not-a-hash"
    with pytest.raises(ValidationError):
        AnchorResult.model_validate(anchor_data)


@pytest.mark.parametrize(
    ("field_path", "value"),
    [
        (("quality", "passed"), "true"),
        (("quality", "score"), "1.0"),
        (("source_windows", 0, "start_t_ns"), "0"),
        (("raw_metrics", "translation_precision_pct"), "94.2"),
    ],
)
def test_anchor_json_scalar_types_are_not_silently_coerced(
    anchor_data: dict[str, Any], field_path: tuple[str | int, ...], value: object
) -> None:
    target: Any = anchor_data
    for key in field_path[:-1]:
        target = target[key]
    target[field_path[-1]] = value

    with pytest.raises(ValidationError):
        AnchorResult.model_validate(anchor_data)
