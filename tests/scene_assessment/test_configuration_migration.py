"""Known old v3 configurations enter the sole current inference algorithm."""

import copy
import importlib.util
import runpy
from pathlib import Path

import pytest

from pilot_assessment.scene_assessment.calculator import evaluate, validate_configuration
from pilot_assessment.scene_assessment.catalog import load_catalog

_helpers = runpy.run_path(str(Path(__file__).with_name("test_sequential_compensation.py")))


@pytest.mark.parametrize("method", ["absent", None, "demo_normalized_grade_likelihood_v1"])
def test_known_old_configuration_is_upgraded_without_mutating_cpt_prior_or_caller(method):
    catalog, config, data = _helpers["case_for"]()
    model = config["skill_models"]["flight"]
    if method == "absent":
        model.pop("inference_method")
    else:
        model["inference_method"] = method
    model.pop("compensation")
    model["process_model"] = {
        "method": "fixed_skill_markov_v1",
        "checkpoint_time_constants_s": {"cp0": [5, 5, 5]},
    }
    frozen = copy.deepcopy(config)
    validation = validate_configuration(config, catalog=catalog)
    assert validation["valid"], validation
    report = evaluate(config, data, catalog=catalog)
    assert config == frozen
    normalized = report["configuration"]["skill_models"]["flight"]
    assert normalized["inference_method"] == "sequential_bayes_compensation_v1"
    assert normalized["compensation"] == {"alpha": 0.2}
    assert "process_model" not in normalized
    for key in ("prior", "state_scores", "checkpoint_models"):
        assert normalized[key] == model[key]
    assert (
        report["items"][0]["skill_quantification"]["method"] == "sequential_bayes_compensation_v1"
    )
    assert report["items"][0]["skill_quantification"]["status"] == "complete"


def test_current_missing_or_invalid_compensation_is_not_silently_filled():
    catalog, config, data = _helpers["case_for"]()
    model = config["skill_models"]["flight"]
    model.pop("compensation")
    assert not validate_configuration(config, catalog=catalog)["valid"]
    assert (
        evaluate(config, data, catalog=catalog)["items"][0]["skill_quantification"]["status"]
        == "invalid_model"
    )


@pytest.mark.parametrize("missing", ["absent", "null", "empty"])
def test_missing_v3_model_is_not_configured_rather_than_an_undecided_method(missing):
    catalog, config, data = _helpers["case_for"]()
    if missing == "absent":
        config.pop("skill_models")
    else:
        config["skill_models"] = None if missing == "null" else {}
    report = evaluate(config, data, catalog=catalog)
    result = report["items"][0]["skill_quantification"]
    assert result["status"] == "not_configured"
    assert result["method"] == "sequential_bayes_compensation_v1"
    assert result["score"] is result["posterior"] is None
    assert result["temporal_analysis"]["status"] == "not_configured"


def test_unknown_method_cannot_be_migrated_into_an_existing_algorithm():
    catalog, config, data = _helpers["case_for"]()
    config["skill_models"]["flight"]["inference_method"] = "unrecognized_method"
    report = evaluate(config, data, catalog=catalog)
    assert (
        report["configuration"]["skill_models"]["flight"]["inference_method"]
        == "unrecognized_method"
    )
    assert report["items"][0]["skill_quantification"]["status"] == "invalid_model"
    assert report["items"][0]["skill_quantification"]["posterior"] is None


def test_retired_algorithms_are_not_importable_production_modules():
    for module in (
        "demo_quantification",
        "temporal_analysis",
        "temporal_validation",
        "skill_quantification",
    ):
        assert importlib.util.find_spec("pilot_assessment.scene_assessment." + module) is None


def test_v1_keeps_rule_evaluation_but_no_longer_runs_static_probability_model():
    helpers = runpy.run_path(str(Path(__file__).with_name("test_catalog_and_stdio.py")))
    config, data = helpers["configured_case"]()
    report = evaluate(config, data, catalog=load_catalog(schema_version="1.0"))
    assert report["grade"] == "D"
    assert all(item["skill_quantification"]["posterior"] is None for item in report["items"])
    assert all(item["skill_quantification"]["score"] is None for item in report["items"])
    assert all(
        item["skill_quantification"]["status"] == "requires_frames" for item in report["items"]
    )
