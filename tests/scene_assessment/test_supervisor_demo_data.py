"""Verify the supervisor examples demonstrate their stated, synthetic contrast."""

from __future__ import annotations

import copy
import importlib.util
import math
from pathlib import Path

import pytest

from pilot_assessment.scene_assessment.calculator import evaluate


@pytest.fixture(scope="module")
def demo():
    path = Path(__file__).resolve().parents[2] / "tools" / "Generate-SupervisorDemo.py"
    spec = importlib.util.spec_from_file_location("supervisor_demo_data", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def turning_points(values):
    deltas = [b - a for a, b in zip(values, values[1:], strict=False) if abs(b - a) > 1e-7]
    return sum(a * b < 0 for a, b in zip(deltas, deltas[1:], strict=False))


@pytest.mark.parametrize("case", ["01-proficient", "02-marginal", "03-unqualified"])
def test_demo_has_resolved_small_corrections_and_balanced_speed(demo, case):
    _, data, _ = demo.generate_case("SCN-001", case)
    hold = [f for f in data["items"]["A-S2-05"]["frames"] if f["phase_id"] == "hold"]
    speeds = [f["values"]["air_taxi_airspeed_mps"] for f in hold]
    assert turning_points(speeds) >= 6  # Irregular corrections, not only one slow sine.
    integral = sum(
        (a + b - 20) / 2 * (right["timestamp_s"] - left["timestamp_s"])
        for a, b, left, right in zip(speeds, speeds[1:], hold, hold[1:], strict=False)
    )
    assert integral == pytest.approx(0, abs=1e-7)
    assert speeds[0] == speeds[-1] == 10
    assert max(abs(b - a) for a, b in zip(speeds, speeds[1:], strict=False)) < 0.65

    _, hover, _ = demo.generate_case("SCN-002", case)
    frames = [f for f in hover["items"]["A-S2-02"]["frames"] if f["phase_id"] == "lower_1"]
    heights = [f["values"]["hover_lower_height_m"] for f in frames]
    # Even an otherwise settled period has several small corrections. Strong
    # slow drift may mask reversals in a marginal pilot's raw position.
    if case != "02-marginal":
        assert turning_points(heights) >= 4
    velocities = [f["values"]["hover_vz_mps"] for f in frames]
    assert turning_points(velocities) >= 6
    assert all(math.isfinite(v) for v in heights + velocities)


def test_demo_provides_acceleration_and_hold_on_one_reference(demo):
    for case in demo.CASES:
        config, data, _ = demo.generate_case("SCN-001", case)
        frames = data["items"]["A-S2-05"]["frames"]
        assert {f["phase_id"] for f in frames} == {"acceleration", "hold"}
        assert all("air_taxi_airspeed_mps" in f["values"] for f in frames)
        assert all("speed_hold_duration_s" not in f["values"] for f in frames)
        first = frames[0]
        assert first["values"]["air_taxi_airspeed_mps"] == 0
        profile = config["parameters"]["air_taxi_airspeed_mps"]["reference_profile"]
        assert frames[-1]["timestamp_s"] - first["timestamp_s"] == pytest.approx(
            profile[-1]["elapsed_s"]
        )
        accel = [f for f in frames if f["phase_id"] == "acceleration"]
        assert accel[-1]["values"]["air_taxi_airspeed_mps"] == 10
        assert len({f["values"]["air_taxi_airspeed_mps"] for f in accel}) > 30
        assert sum(
            (a["values"]["air_taxi_airspeed_mps"] + b["values"]["air_taxi_airspeed_mps"])
            / 2
            * (b["timestamp_s"] - a["timestamp_s"])
            for a, b in zip(accel, accel[1:], strict=False)
        ) == pytest.approx(30, abs=1e-7)


@pytest.mark.parametrize("case", ["01-proficient", "02-marginal", "03-unqualified"])
def test_stop_demonstrates_continuous_capture_and_settling(demo, case):
    config, data, _ = demo.generate_case("SCN-001", case)
    stop = [f for f in data["items"]["A-S2-30"]["frames"] if f["phase_id"] == "stop"]
    assert len(stop) == 51
    assert stop[-1]["timestamp_s"] - stop[0]["timestamp_s"] == pytest.approx(5)
    assert all(
        b["timestamp_s"] - a["timestamp_s"] == pytest.approx(0.1)
        for a, b in zip(stop, stop[1:], strict=False)
    )
    errors = [f["values"]["stop_x_m"] - 160 for f in stop]
    assert len({round(v, 5) for v in errors}) > 30
    assert errors[-1] == pytest.approx(0)
    report = evaluate(config, data)
    item = next(i for i in report["items"] if i["item_id"] == "A-S2-30")
    point = next(p for p in item["checkpoints"] if p["checkpoint_id"] == "A-S2-30-02")
    assert len(point["timeline"]) == 51
    expected = {"01-proficient": "D", "02-marginal": "A", "03-unqualified": "U"}
    assert point["grade"] == expected[case]


@pytest.mark.parametrize("scene_id", ["SCN-001", "SCN-002"])
def test_three_coherent_profiles_have_real_rule_and_quantity_contrast(demo, scene_id):
    reports = []
    for case in demo.CASES:
        config, data, metadata = demo.generate_case(scene_id, case)
        assert (config, data, metadata) == demo.generate_case(scene_id, case)
        report = evaluate(config, data)
        assert report["calculation_status"] == "complete"
        assert report["issues"] == []
        assert report["grade"] == metadata["expected_grade"]
        assert report["passed"] is (case != "03-unqualified")
        checks = demo.diagnostics(scene_id, data, report)
        assert checks["motion_checks"]["derivative_consistency_check"].startswith("pass")
        flight_items = [
            item
            for item in report["items"]
            if item["skill_quantification"].get("score") is not None
        ]
        assert len(flight_items) == 2
        for item in flight_items:
            quantity = item["skill_quantification"]
            assert quantity["status"] == "complete"
            assert sum(quantity["posterior"]) == pytest.approx(1)
            cumulative = quantity["cumulative_trace"]
            assert cumulative["method"] == "sequential_bayes_compensation_v1"
            assert len(cumulative["timeline"]) == len(data["items"][item["item_id"]]["frames"])
            assert cumulative["timeline"][-1]["posterior"] == quantity["posterior"]
            assert cumulative["timeline"][-1]["score"] == quantity["score"]
            assert cumulative["timeline"][-1]["status"] == "complete"
            proportions = item["frame_distribution"]["proportions"]
            if case == "01-proficient":
                assert 0.75 < proportions["D"] < 1
                assert proportions["A"] > 0
                assert proportions["U"] == 0
            elif case == "02-marginal":
                assert 0 < proportions["D"] < 0.9
                assert proportions["A"] > 0
                assert proportions["U"] == 0
            else:
                assert proportions["U"] > 0
        reports.append(flight_items)
    for same_item in zip(*reports, strict=True):
        assert len({item["item_id"] for item in same_item}) == 1
        proficient, marginal, _unqualified = [
            item["skill_quantification"]["score"] for item in same_item
        ]
        assert proficient > marginal
        # A brief known U retains Fail even if its whole-run score exceeds a
        # sustained-A Pass. Case names must not impose an artificial ranking.


def test_diagnostics_reject_unrelated_hover_velocity_or_laser_fields(demo):
    config, data, _ = demo.generate_case("SCN-002", "02-marginal")
    report = evaluate(config, data)
    corrupted = copy.deepcopy(data)
    corrupted["items"]["A-S2-02"]["frames"][10]["values"]["hover_vx_mps"] += 2
    with pytest.raises(AssertionError):
        demo.diagnostics("SCN-002", corrupted, report)
    corrupted = copy.deepcopy(data)
    corrupted["items"]["A-S2-02"]["frames"][10]["values"]["laser_lower_spot"]["u_m"] += 1
    with pytest.raises(AssertionError):
        demo.diagnostics("SCN-002", corrupted, report)


def test_unqualified_hover_retains_fail_after_final_recovery(demo):
    config, data, _ = demo.generate_case("SCN-002", "03-unqualified")
    report = evaluate(config, data)
    for item in report["items"][:2]:
        assert item["grade"] == "U"
        assert item["timeline"][-1]["grade"] == "D"
    laser_frames = data["items"]["A-S2-02"]["frames"]
    assert any(
        spot["status"] == "miss"
        for frame in laser_frames
        for key, spot in frame["values"].items()
        if key.startswith("laser_")
    )


def test_hover_examples_use_one_ordered_frame_stream_for_position_and_height(demo):
    _, data, _ = demo.generate_case("SCN-002", "01-proficient")
    assert set(data["items"]) == {"A-S2-02", "SCENE-VERTICAL"}
    frames = data["items"]["A-S2-02"]["frames"]
    timestamps = [frame["timestamp_s"] for frame in frames]
    assert timestamps == sorted(set(timestamps))
    assert len(frames) == 204
    for frame in frames:
        lower = frame["phase_id"].startswith("lower")
        height_key = "hover_lower_height_m" if lower else "hover_upper_height_m"
        other_key = "hover_upper_height_m" if lower else "hover_lower_height_m"
        assert height_key in frame["values"]
        assert other_key not in frame["values"]


def test_height_only_failure_reduces_the_same_hover_item_process(demo):
    config, data, _ = demo.generate_case("SCN-002", "01-proficient")
    baseline = next(
        item for item in evaluate(config, data)["items"] if item["item_id"] == "A-S2-02"
    )
    altered = copy.deepcopy(data)
    for frame in altered["items"]["A-S2-02"]["frames"]:
        if frame["phase_id"] == "lower_1":
            frame["values"]["hover_lower_height_m"] = 8.0
    report = evaluate(config, altered)
    assert report["calculation_status"] == "complete", report["issues"]
    hover = next(item for item in report["items"] if item["item_id"] == "A-S2-02")
    assert baseline["passed"] is True
    assert hover["grade"] == "U" and hover["passed"] is False
    affected = hover["skill_quantification"]["temporal_analysis"]["item_trace"]["timeline"]
    reference = baseline["skill_quantification"]["temporal_analysis"]["item_trace"]["timeline"]
    changed_pairs = [
        (a, b) for a, b in zip(affected, reference, strict=True) if a["phase_id"] == "lower_1"
    ]
    assert changed_pairs
    assert all(a["score"] < b["score"] for a, b in changed_pairs)
    assert hover["skill_quantification"]["score"] == affected[-1]["score"]
    baseline_points = {point["checkpoint_id"]: point for point in baseline["checkpoints"]}
    for point in hover["checkpoints"]:
        if point["checkpoint_id"] == "A-S2-02-04":
            assert point["grade"] == "U"
        else:
            assert point["timeline"] == baseline_points[point["checkpoint_id"]]["timeline"]
