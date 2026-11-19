"""Current scene content and raw frame templates, independent of inference."""

from pilot_assessment.scene_assessment.catalog import list_scenes, load_catalog


def test_current_registry_contains_two_scenes_using_frames():
    registry = list_scenes()
    assert registry["schema_version"] == "3.0"
    assert [scene["scene_id"] for scene in registry["scenes"]] == ["SCN-001", "SCN-002"]
    for scene in registry["scenes"]:
        catalog = load_catalog(scene["scene_id"])
        assert catalog["schema_version"] == "3.0"
        for item in catalog["items"]:
            frames = catalog["input_template"]["items"][item["item_id"]]["frames"]
            assert {frame["phase_id"] for frame in frames} == {
                phase["phase_id"] for phase in item["phases"]
            }
            assert all(frame["timestamp_s"] is None for frame in frames)
            assert all(set(frame) == {"timestamp_s", "phase_id", "values"} for frame in frames)


def test_quick_stop_only_scores_position_in_explicit_stop_frame():
    catalog = load_catalog()
    item = next(item for item in catalog["items"] if item["item_id"] == "A-S2-30")
    assert item["name"] == "快速减速／快速停止"
    assert "Rapid Deceleration/Quick Stop" in item["description"]
    assert [point["checkpoint_id"] for point in item["checkpoints"]] == [
        "A-S2-30-02", "A-S2-30-03", "A-S2-30-04"
    ]
    metrics = {metric["metric_id"]: metric for metric in catalog["metrics"]}
    assert "deceleration_started" not in metrics
    assert "stop_achieved" not in metrics
    for key in item["checkpoints"][0]["metric_ids"]:
        assert metrics[key]["phase_ids"] == ["stop"]
    assert all("duration" not in key for key in item["checkpoints"][0]["metric_ids"])


def test_acceleration_scene_excludes_an_unflown_approach_from_every_current_template():
    catalog = load_catalog()
    assert [item["item_id"] for item in catalog["items"]] == [
        "A-S1-06", "A-S2-05", "A-S2-30"
    ]
    assert sum(len(item["checkpoints"]) for item in catalog["items"]) == 12
    assert len(catalog["metrics"]) == 17
    assert catalog["phase_sequence"] == [
        "preflight", "acceleration", "hold", "deceleration", "stop"
    ]
    assert "A-S2-23" not in catalog["input_template"]["items"]
    assert "A-S2-23" not in catalog["configuration_template"]["skill_models"]
    for metric in catalog["metrics"]:
        assert not metric["metric_id"].startswith(("approach_", "arrival_"))
    for key in catalog["configuration_template"]["parameters"]:
        assert not key.startswith(("approach_", "arrival_"))
    assert "SCENE-START" not in catalog["input_template"]["items"]


def test_hover_reuses_items_and_encodes_four_five_second_holds():
    catalog = load_catalog("SCN-002")
    assert len(catalog["items"]) == 2
    assert sum(len(item["checkpoints"]) for item in catalog["items"]) == 6
    assert "start" not in catalog["phase_sequence"]
    assert "SCENE-START" not in catalog["input_template"]["items"]
    assert "SCENE-START" not in catalog["configuration_template"]["skill_models"]
    for item in catalog["items"]:
        if item["item_id"] == "A-S2-02":
            assert [phase["phase_id"] for phase in item["phases"]] == [
                "lower_1", "upper_1", "lower_2", "upper_2"
            ]
            assert all(phase["required_duration_s"] == 5 for phase in item["phases"])
    transfer = catalog["items"][-1]
    assert [phase["phase_id"] for phase in transfer["phases"]] == [
        "rise_1", "descend_1", "rise_2"
    ]


def test_empty_templates_do_not_invent_tolerances_or_bayesian_parameters():
    for scene_id in ("SCN-001", "SCN-002"):
        catalog = load_catalog(scene_id)
        config = catalog["configuration_template"]
        for parameter in config["parameters"].values():
            assert parameter["desired"]["upper"] is None
            assert parameter["acceptable"]["upper"] is None
        for model in config["skill_models"].values():
            assert model["prior"] == [None, None, None]
        for item in catalog["items"]:
            allowed = {
                key for point in item["checkpoints"] for key in point["metric_ids"]
            }
            for frame in catalog["input_template"]["items"][item["item_id"]]["frames"]:
                assert set(frame["values"]) <= allowed


def test_radial_points_are_three_state_and_geometry_is_editable():
    catalog = load_catalog("SCN-002")
    radial = [metric for metric in catalog["metrics"] if metric["comparison"] == "radial"]
    assert len(radial) == 2
    for metric in radial:
        assert metric["rule"] == "interval"
        parameter = catalog["configuration_template"]["parameters"][metric["metric_id"]]
        assert parameter["center_u"] is None and parameter["center_v"] is None
        assert parameter["target_radius"] is None
        assert parameter["desired"]["lower"] == 0
    laser = catalog["configuration_template"]["skill_models"]["A-S2-02"]
    assert laser["checkpoint_models"]["A-S2-02-03"]["states"] == ["D", "A", "U"]
