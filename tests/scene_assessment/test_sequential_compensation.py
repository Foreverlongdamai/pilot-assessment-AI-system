"""Versioned CPT Bayes, then bidirectional compensation, with one shared trace."""

from __future__ import annotations

import copy
import math
import runpy
from pathlib import Path

import pytest

from pilot_assessment.scene_assessment.calculator import evaluate, validate_configuration
from pilot_assessment.scene_assessment.catalog import load_catalog

_helpers = runpy.run_path(str(Path(__file__).with_name("scene_test_cases.py")))
METHOD = "sequential_bayes_compensation_v1"
CPT = _helpers["CPT"]


def case_for(grades="DU", *, second=None, alpha=0.2, prior=None):
    case = _helpers["make_case"](grades, second_grades=second)
    model = case[1]["skill_models"]["flight"]
    model.update(inference_method=METHOD, compensation={"alpha": alpha})
    if prior is not None:
        model["prior"] = list(prior)
    return case


def report_for(case):
    return evaluate(case[1], case[2], catalog=case[0])


def quantity(case):
    return report_for(case)["items"][0]["skill_quantification"]


def steps(case):
    result = quantity(case)
    assert result["status"] == "complete", result
    return result["temporal_analysis"]["item_trace"]["timeline"]


def normalized(values):
    total = sum(values)
    return [value / total for value in values]


def test_cpt_then_compensation_uses_previous_compensated_prior_and_one_endpoint():
    case = case_for("DU", prior=[0.2, 0.3, 0.5])
    result = quantity(case)
    assert result["status"] == "complete", result
    temporal = result["temporal_analysis"]
    assert temporal["method"] == result["method"] == METHOD
    first, second = temporal["item_trace"]["timeline"]
    bayes_d = normalized([0.2 * 0.1, 0.3 * 0.35, 0.5 * 0.9])
    after_d = [0.8 * p + bonus for p, bonus in zip(bayes_d, [0, 0, 0.2], strict=True)]
    bayes_u = normalized([p * row[2] for p, row in zip(after_d, CPT, strict=True)])
    after_u = [0.8 * p + bonus for p, bonus in zip(bayes_u, [0.2, 0, 0], strict=True)]
    assert first["prior"] == [0.2, 0.3, 0.5]
    assert first["bayes_posterior"] == pytest.approx(bayes_d)
    assert first["posterior"] == pytest.approx(after_d)
    assert second["prior"] == pytest.approx(after_d)
    assert second["bayes_posterior"] == pytest.approx(bayes_u)
    assert second["compensation_target"] == [1.0, 0.0, 0.0]
    assert second["compensation_alpha"] == 0.2
    assert second["compensation_delta"] == pytest.approx(
        [final - base for final, base in zip(after_u, bayes_u, strict=True)]
    )
    assert second["log_bayes_factor_high_low"] == pytest.approx(math.log(0.001 / 0.65))
    assert result["posterior"] == second["posterior"]
    assert result["score"] == second["score"] == pytest.approx(after_u[1] * 50 + after_u[2] * 100)
    assert result["local_traces"] == []
    assert "evidence_strength" not in result
    cp = temporal["checkpoint_traces"][0]["timeline"]
    cumulative = result["cumulative_trace"]["timeline"]
    for item_point, cp_point, cumulative_point in zip([first, second], cp, cumulative, strict=True):
        assert cp_point["posterior"] == cumulative_point["posterior"] == item_point["posterior"]
        assert cp_point["score"] == cumulative_point["score"] == item_point["score"]


@pytest.mark.parametrize(
    "prior,grade,target",
    [
        ([0, 0, 1], "U", 0),
        ([1, 0, 0], "D", 2),
        ([0, 1, 0], "D", 2),
        ([0, 1, 0], "U", 0),
        ([0.0005, 0.0005, 0.999], "A", 1),
        ([0.999, 0.0005, 0.0005], "A", 1),
    ],
)
def test_extreme_beliefs_recover_in_both_directions(prior, grade, target):
    trace = steps(case_for(grade * 2, prior=prior))
    assert trace[0]["posterior"][target] >= 0.2
    assert all(sum(point["posterior"]) == pytest.approx(1) for point in trace)


def test_alpha_zero_is_exact_sequential_bayes_and_cpt_changes_results():
    case = case_for("DAU", alpha=0)
    prior = [1 / 3] * 3
    for grade, point in zip("DAU", steps(case), strict=True):
        index = "DAU".index(grade)
        prior = normalized([p * row[index] for p, row in zip(prior, CPT, strict=True)])
        assert point["posterior"] == pytest.approx(prior)
        assert point["compensation_delta"] == [0, 0, 0]
    baseline = steps(case_for("DD"))[-1]["posterior"]
    altered = case_for("DD")
    altered[1]["skill_models"]["flight"]["checkpoint_models"]["cp0"]["probabilities"] = [
        [1 / 3] * 3 for _ in range(3)
    ]
    assert steps(altered)[-1]["posterior"] != pytest.approx(baseline)


def test_item_multiplies_same_frame_cpt_likelihoods_then_compensates_once():
    case = case_for("DD", second="AU", prior=[0.1, 0.2, 0.7])
    trace = steps(case)
    bayes = normalized([p * row[0] * row[1] for p, row in zip([0.1, 0.2, 0.7], CPT, strict=True)])
    expected = [0.8 * p + bonus for p, bonus in zip(bayes, [0, 0.2, 0], strict=True)]
    assert trace[0]["bayes_posterior"] == pytest.approx(bayes)
    assert trace[0]["posterior"] == pytest.approx(expected)
    assert trace[0]["compensation_target"] == [0, 1, 0]
    assert trace[1]["compensation_target"] == [1, 0, 0]
    assert trace[0]["evidence_count"] == 2


def test_score_anchors_never_enter_probability_updates():
    case = case_for("DADU")
    original = steps(case)
    case[1]["skill_models"]["flight"]["state_scores"] = [10, 70, 90]
    changed = steps(case)
    for old, new in zip(original, changed, strict=True):
        assert new["posterior"] == old["posterior"]
        assert new["score"] == pytest.approx(
            sum(p * v for p, v in zip(new["posterior"], [10, 70, 90], strict=True))
        )


def test_phase_boundary_does_not_reset_ability_or_count_as_extra_evidence():
    case = case_for("DADU")
    original = steps(case)
    phase = copy.deepcopy(case[0]["items"][0]["phases"][0])
    phase["phase_id"] = "stop"
    case[0]["items"][0]["phases"].append(phase)
    case[0]["metrics"][0]["phase_ids"].append("stop")
    for frame in case[2]["items"]["flight"]["frames"][2:]:
        frame["phase_id"] = "stop"
    changed = steps(case)
    assert [p["posterior"] for p in changed] == [p["posterior"] for p in original]
    assert changed[2]["prior"] == changed[1]["posterior"]


def test_missing_evidence_keeps_known_fail_and_taints_only_affected_checkpoint():
    case = case_for("DUDD", second="DDDD")
    case[2]["items"]["flight"]["frames"][2]["values"]["m0"] = None
    report = report_for(case)
    result = report["items"][0]["skill_quantification"]
    assert report["passed"] is False
    assert result["status"] == "insufficient_evidence"
    assert result["posterior"] is result["score"] is None
    temporal = result["temporal_analysis"]
    assert temporal["status"] == "partial"
    trace = temporal["item_trace"]["timeline"]
    assert trace[1]["posterior"] is not None
    assert all(point["posterior"] is None for point in trace[2:])
    assert temporal["checkpoint_traces"][1]["timeline"][-1]["posterior"] is not None
    assert all(point["posterior"] is None for point in result["cumulative_trace"]["timeline"][2:])


@pytest.mark.parametrize("alpha", [-0.1, 1.1, None, True, "0.2", float("nan")])
def test_invalid_compensation_is_not_repaired_or_replaced_by_legacy_method(alpha):
    case = case_for(alpha=alpha)
    result = quantity(case)
    assert result["method"] == METHOD
    assert result["status"] == "invalid_model"
    assert result["score"] is None
    assert result["temporal_analysis"]["status"] == "invalid_model"
    assert any(
        "compensation" in issue["path"]
        for issue in validate_configuration(case[1], catalog=case[0])["issues"]
    )


def test_new_method_requires_explicit_compensation_and_rejects_old_process():
    case = case_for()
    del case[1]["skill_models"]["flight"]["compensation"]
    assert quantity(case)["status"] == "invalid_model"
    case = case_for()
    case[1]["skill_models"]["flight"]["process_model"] = {
        "method": "fixed_skill_markov_v1",
        "checkpoint_time_constants_s": {"cp0": [5, 5, 5]},
    }
    assert quantity(case)["status"] == "invalid_model"


def test_new_templates_select_new_method_without_inventing_prior_or_cpt():
    for scene in ("SCN-001", "SCN-002"):
        for model in load_catalog(scene)["configuration_template"]["skill_models"].values():
            assert model["inference_method"] == METHOD
            assert model["compensation"] == {"alpha": 0.2}
            assert model["prior"] == [None, None, None]
            assert model["state_scores"] == [0, 50, 100]
            assert "process_model" not in model


def test_sequential_quantification_retains_detached_input_and_model_snapshots():
    case = case_for()
    result = report_for(case)
    frozen = copy.deepcopy(result)
    case[1]["skill_models"]["flight"]["compensation"]["alpha"] = 1
    case[2]["items"]["flight"]["frames"][0]["values"]["m0"] = 100
    assert result == frozen


def test_invalid_frame_order_blocks_all_probability_curves():
    case = case_for()
    case[2]["items"]["flight"]["frames"].reverse()
    result = quantity(case)
    assert result["score"] is None
    assert result["temporal_analysis"]["status"] == "blocked"
    assert result["temporal_analysis"]["item_trace"] is None
    assert result["cumulative_trace"] is None


def test_binary_forbidden_event_keeps_three_hidden_states_and_uses_two_cpt_columns():
    case = case_for("DU")
    case[0]["metrics"][0].update(rule="zero_events", value_type="integer")
    case[1]["parameters"] = {}
    case[2]["items"]["flight"]["frames"][1]["values"]["m0"] = 1
    cpt = [[0.2, 0.8], [0.5, 0.5], [0.9, 0.1]]
    case[1]["skill_models"]["flight"]["checkpoint_models"]["cp0"] = {
        "states": ["D", "U"],
        "probabilities": cpt,
    }
    first, second = steps(case)
    expected = normalized([p * row[1] for p, row in zip(first["posterior"], cpt, strict=True)])
    assert second["bayes_posterior"] == pytest.approx(expected)
    assert second["compensation_target"] == [1, 0, 0]
    assert report_for(case)["passed"] is False


def test_nonapplicable_checkpoint_neither_updates_nor_repeats_prior_in_item():
    case = case_for("DDUU", second="DDAA")
    phase = copy.deepcopy(case[0]["items"][0]["phases"][0])
    phase["phase_id"] = "stop"
    case[0]["items"][0]["phases"].append(phase)
    case[0]["metrics"][1]["phase_ids"] = ["stop"]
    for index, frame in enumerate(case[2]["items"]["flight"]["frames"]):
        if index < 2:
            del frame["values"]["m1"]
        else:
            frame["phase_id"] = "stop"
            del frame["values"]["m0"]
    result = quantity(case)
    assert result["status"] == "complete", result
    temporal = result["temporal_analysis"]
    assert temporal["checkpoint_traces"][1]["timeline"][0]["posterior"] is None
    assert temporal["checkpoint_traces"][1]["timeline"][2]["prior"] == [1 / 3] * 3
    item_trace = temporal["item_trace"]["timeline"]
    assert item_trace[2]["prior"] == item_trace[1]["posterior"]
    expected = normalized(
        [p * row[1] for p, row in zip(item_trace[1]["posterior"], CPT, strict=True)]
    )
    assert item_trace[2]["bayes_posterior"] == pytest.approx(expected)


def test_missing_required_phase_retains_prefix_but_no_final_endpoint():
    case = case_for("DU")
    case[0]["items"][0]["phases"][0]["required_duration_s"] = 10
    result = quantity(case)
    assert result["status"] == "insufficient_evidence"
    assert result["score"] is None
    assert result["temporal_analysis"]["item_trace"]["timeline"][0]["posterior"] is not None
    assert result["temporal_analysis"]["item_trace"]["timeline"][-1]["posterior"] is None
    assert result["cumulative_trace"]["timeline"][-1]["posterior"] is None


def test_repeated_success_still_responds_to_later_failure_and_recovery():
    case = case_for("D" * 10000 + "U" + "D")
    trace = steps(case)
    assert trace[-3]["posterior"][2] > 0.999
    assert trace[-2]["posterior"][0] >= 0.2
    assert trace[-2]["posterior"][2] <= 0.8
    assert trace[-1]["posterior"][2] > trace[-2]["posterior"][2]
    assert report_for(case)["passed"] is False


def test_alpha_one_targets_actual_grade_and_zero_total_likelihood_is_explicit():
    assert [point["posterior"] for point in steps(case_for("DAU", alpha=1))] == [
        [0, 0, 1],
        [0, 1, 0],
        [1, 0, 0],
    ]
    from pilot_assessment.scene_assessment.sequential_compensation import bayes_compensation_update

    with pytest.raises(ValueError, match="positive finite evidence"):
        bayes_compensation_update([0, 0, 0], [0, 0, 0], "D", 0.2, [0, 50, 100])


@pytest.mark.parametrize("field", ["prior", "cpt"])
def test_incomplete_or_nonpositive_cpt_cannot_silently_infer(field):
    case = case_for()
    model = case[1]["skill_models"]["flight"]
    if field == "prior":
        model["prior"] = [None, None, None]
    else:
        model["checkpoint_models"]["cp0"]["probabilities"][0] = [0, 0.5, 0.5]
    assert quantity(case)["status"] == "invalid_model"
