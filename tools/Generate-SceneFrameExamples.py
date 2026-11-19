"""Export v3 blank templates and clearly synthetic arithmetic examples for both scenes."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from pilot_assessment.scene_assessment.calculator import evaluate
from pilot_assessment.scene_assessment.catalog import load_catalog


def write_json(directory: Path, name: str, value: object) -> None:
    (directory / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def engineering_case(catalog):
    config = copy.deepcopy(catalog["configuration_template"])
    data = copy.deepcopy(catalog["input_template"])
    metrics = {metric["metric_id"]: metric for metric in catalog["metrics"]}
    for key, parameter in config["parameters"].items():
        metric = metrics[key]
        if metric["comparison"] == "radial":
            parameter.update(expected=0, center_u=0, center_v=0, target_radius=1)
            parameter["desired"].update(lower=0, upper=0.2)
            parameter["acceptable"].update(lower=0, upper=0.5)
        elif metric["comparison"] == "route_3d":
            # Manually defined synthetic geometry, never inferred from observations.
            parameter.update(expected=0, route_points=[
                {"x_m": 0, "y_m": 0, "height_m": 17},
                {"x_m": 50, "y_m": 50, "height_m": 12},
                {"x_m": 100, "y_m": 100, "height_m": 7},
            ])
            parameter["desired"].update(lower=0, upper=0.5)
            parameter["acceptable"].update(lower=0, upper=1)
        elif metric["comparison"] == "angle_degrees":
            parameter.update(expected=359)
            parameter["desired"].update(lower=-3, upper=3)
            parameter["acceptable"].update(lower=-6, upper=6)
        elif metric.get("target_mode") == "item_profile":
            parameter.update(expected=None, reference_profile=[
                {"elapsed_s": 0, "expected": 0},
                {"elapsed_s": 3, "expected": 20},
                {"elapsed_s": 6.7, "expected": 20},
            ])
            parameter["desired"].update(lower=-0.5, upper=0.5)
            parameter["acceptable"].update(lower=-1, upper=1)
        elif metric.get("target_mode") == "phase_profile":
            # Synthetic targets only: these are not aircraft or FAA thresholds.
            targets = {
                "approach_airspeed_mps": {"approach": (12, 6), "approach_deceleration": (6, 0)},
                "approach_height_m": {"approach": (16, 10), "approach_deceleration": (10, 7)},
                "approach_vertical_speed_mps": {
                    "approach": (-2, -2), "approach_deceleration": (-2, 0)
                },
            }
            parameter["expected"] = None
            parameter["reference_profiles"] = {
                phase: [{"elapsed_s": 0, "expected": ends[0]},
                        {"elapsed_s": 3, "expected": ends[1]}]
                for phase, ends in targets[key].items()
            }
            parameter["desired"].update(lower=-0.5, upper=0.5)
            parameter["acceptable"].update(lower=-1, upper=1)
        else:
            expected = metric.get("default_expected", 100)
            if "height" in key:
                expected = 15 if "upper" in key else 10
                if key == "arrival_height_m":
                    expected = 7
            elif "airspeed" in key:
                expected = 20
            elif "duration" in key:
                expected = 3
            parameter.update(expected=expected)
            parameter["desired"].update(lower=-0.5, upper=0.5)
            parameter["acceptable"].update(lower=-1, upper=1)

    hover_origins = {"lower_1": 10, "upper_1": 20, "lower_2": 30, "upper_2": 40}
    transfer_origins = {"rise_1": 15.1, "descend_1": 25.1, "rise_2": 35.1}
    scene1_origins = {
        "preflight": 0, "approach": 1, "approach_deceleration": 4.1,
        "arrival_hover": 7.2, "acceleration": 10.3, "hold": 14,
        "deceleration": 18, "stop": 22,
    }
    for item in catalog["items"]:
        frames = []
        keys = {key for point in item["checkpoints"] for key in point["metric_ids"]}
        for phase in item["phases"]:
            phase_id = phase["phase_id"]
            if catalog["scene_id"] == "SCN-001":
                origin = scene1_origins[phase_id]
            else:
                origin = hover_origins.get(phase_id, transfer_origins.get(phase_id))
            count = 1 if phase["single_frame"] else (
                51 if phase["required_duration_s"] == 5 else 31
            )
            for index in range(count):
                values = {}
                for key in sorted(keys):
                    metric = metrics[key]
                    if phase_id not in metric["phase_ids"]:
                        continue
                    if metric["rule"] == "must_be_true":
                        value = True
                    elif metric["rule"] == "zero_events":
                        value = 0
                    elif metric["comparison"] == "radial":
                        # A short pointing failure followed by a return to the inner circle.
                        radius = 0.8 if phase_id == "upper_1" and 20 <= index < 25 else (
                            0.35 if 25 <= index < 30 else 0.1
                        )
                        value = {"status": "hit", "u_m": radius, "v_m": 0}
                    elif metric["comparison"] == "route_3d":
                        nodes = config["parameters"][key]["route_points"]
                        segment = 0 if phase_id == "approach" else 1
                        # Generate test observations; production never interpolates frames.
                        value = {
                            axis: nodes[segment][axis] + index / 30 * (
                                nodes[segment + 1][axis] - nodes[segment][axis]
                            ) for axis in ("x_m", "y_m", "height_m")
                        }
                    else:
                        value = config["parameters"][key]["expected"]
                        if metric.get("target_mode") == "item_profile":
                            value = 20 * index / 30 if phase_id == "acceleration" else 20
                        if metric.get("target_mode") == "phase_profile":
                            nodes = config["parameters"][key]["reference_profiles"][phase_id]
                            value = nodes[0]["expected"] + index / 30 * (
                                nodes[1]["expected"] - nodes[0]["expected"]
                            )
                        if key == "air_taxi_heading_deg" and phase_id == "hold":
                            offset = 9 if 10 <= index < 13 else 4 if 13 <= index < 18 else 2
                            value = (value + offset) % 360
                        if key == "hover_x_m" and phase_id == "lower_2" and 15 <= index < 18:
                            value += 1.5
                    values[key] = value
                frames.append({
                    "timestamp_s": round(origin + index / 10, 4),
                    "phase_id": phase_id,
                    "values": values,
                })
        data["items"][item["item_id"]] = {"frames": frames}
    return config, data


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    for scene_id in ("SCN-001", "SCN-002"):
        catalog = load_catalog(scene_id, "3.0")
        directory = root / "examples" / "scenes" / scene_id / "v3"
        directory.mkdir(parents=True, exist_ok=True)
        write_json(directory, "configuration-template.json", catalog["configuration_template"])
        write_json(directory, "input-template.json", catalog["input_template"])
        config, data = engineering_case(catalog)
        write_json(directory, "engineering-demo-configuration.json", config)
        write_json(directory, "engineering-demo-input.json", data)
        report = evaluate(config, data)
        if report["calculation_status"] != "complete" or report["grade"] != "U":
            raise RuntimeError(f"{scene_id}: expected a complete synthetic recovery/Fail case: "
                               f"{report.get('issues')}")
        write_json(directory, "engineering-demo-report.json", report)
        print(f"{scene_id}: wrote blank templates and synthetic U/recovery example")


if __name__ == "__main__":
    main()
