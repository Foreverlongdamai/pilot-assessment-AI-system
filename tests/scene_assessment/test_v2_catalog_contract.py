"""User-approved catalog boundaries, independently of the grading algorithm."""

from pilot_assessment.scene_assessment.catalog import load_catalog


def test_current_catalog_contains_four_items_and_procedure_checklist():
    catalog = load_catalog(schema_version="2.0")
    assert catalog["schema_version"] == "2.0"
    assert [item["item_id"] for item in catalog["items"]] == [
        "A-S1-06",
        "A-S2-08",
        "A-S2-05",
        "A-S2-30",
    ]
    checklist = catalog["items"][0]
    assert checklist["assessment_kind"] == "checklist"
    metrics = {metric["metric_id"]: metric for metric in catalog["metrics"]}
    for point in checklist["checkpoints"]:
        for key in point["metric_ids"]:
            assert metrics[key]["rule"] == "must_be_true"
            assert metrics[key]["input_kind"] == "scalar"
    assert "A-S1-06" not in catalog["configuration_template"]["skill_models"]


def test_numeric_inputs_are_actual_quantities_with_unfilled_relative_parameters():
    catalog = load_catalog(schema_version="2.0")
    assert catalog["schema_version"] == "2.0"
    parameters = catalog["configuration_template"]["parameters"]
    for metric in catalog["metrics"]:
        if metric["rule"] != "interval":
            continue
        assert "max_" not in metric["metric_id"]
        assert "error" not in metric["metric_id"]
        assert metric["comparison"] in {"linear", "angle_degrees"}
        assert parameters[metric["metric_id"]]["expected"] is None
        assert parameters[metric["metric_id"]]["desired"]["lower"] is None
    assert "takeoff_heading_deg" in parameters
    assert "air_taxi_heading_deg" in parameters
    assert "quickstop_heading_deg" in parameters


def test_template_routes_evidence_to_each_checkpoint_without_demo_probabilities():
    catalog = load_catalog(schema_version="2.0")
    assert catalog["schema_version"] == "2.0"
    template = catalog["input_template"]
    assert "results" not in template
    assert set(template["items"]) == {item["item_id"] for item in catalog["items"]}
    for item in catalog["items"]:
        points = template["items"][item["item_id"]]["checkpoints"]
        assert set(points) == {point["checkpoint_id"] for point in item["checkpoints"]}
        for point in points.values():
            assert point["samples"] == []
            assert all(value is None for value in point["values"].values())
    for model in catalog["configuration_template"]["skill_models"].values():
        assert model["parameter_source"] == "unconfigured"
        assert model["prior"] == [None, None, None]
        for point in model["checkpoint_models"].values():
            assert all(value is None for row in point["probabilities"] for value in row)
