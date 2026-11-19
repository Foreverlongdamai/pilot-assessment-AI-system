"""Regenerate v2 blank files and a synthetic engineering-only recovery example."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from pilot_assessment.scene_assessment.calculator import evaluate
from pilot_assessment.scene_assessment.catalog import load_catalog


def main() -> None:
    catalog = load_catalog("SCN-001", schema_version="2.0")
    output = Path(__file__).resolve().parents[1] / "examples/scenes/SCN-001/v2"
    output.mkdir(parents=True, exist_ok=True)

    def write(name: str, value: object) -> None:
        (output / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )

    write("configuration-template.json", catalog["configuration_template"])
    write("input-template.json", catalog["input_template"])
    configuration = copy.deepcopy(catalog["configuration_template"])
    inputs = copy.deepcopy(catalog["input_template"])
    metrics = {metric["metric_id"]: metric for metric in catalog["metrics"]}

    # Deliberately synthetic numbers for software verification, never defaults.
    for metric_id, parameter in configuration["parameters"].items():
        if "heading" in metric_id:
            expected = 359
        elif "height" in metric_id:
            expected = 100
        elif "airspeed" in metric_id:
            expected = 20
        elif "duration" in metric_id:
            expected = 10
        else:
            expected = 0
        parameter.update(
            expected=expected,
            desired={"lower": -2, "upper": 2, "unbounded_upper": False},
            acceptable={"lower": -5, "upper": 5, "unbounded_upper": False},
        )

    for item_index, item in enumerate(catalog["items"]):
        for checkpoint in item["checkpoints"]:
            point = inputs["items"][item["item_id"]]["checkpoints"][
                checkpoint["checkpoint_id"]
            ]
            for metric_id in point["values"]:
                rule = metrics[metric_id]["rule"]
                point["values"][metric_id] = (
                    True
                    if rule == "must_be_true"
                    else 0
                    if rule == "zero_events"
                    else configuration["parameters"][metric_id]["expected"]
                )
            series_ids = [
                metric_id
                for metric_id in checkpoint["metric_ids"]
                if metrics[metric_id]["input_kind"] == "series"
            ]
            if not series_ids:
                continue
            origin = 20 * item_index
            # Four externally supplied intervals: D, U, A, then recovered D.
            for start, end, heading_offset in [(0, 4, 1), (4, 5, 8), (5, 7, 3), (7, 10, 1)]:
                values = {}
                for metric_id in series_ids:
                    value = configuration["parameters"][metric_id]["expected"]
                    if metric_id == "air_taxi_heading_deg":
                        value = (value + heading_offset) % 360
                    values[metric_id] = value
                point["samples"].append(
                    {"start_s": origin + start, "end_s": origin + end, "values": values}
                )

    write("engineering-demo-configuration.json", configuration)
    write("engineering-demo-input.json", inputs)
    report = evaluate(configuration, inputs)
    write("engineering-demo-report.json", report)
    print(f"Wrote v2 templates and synthetic engineering example to {output}")


if __name__ == "__main__":
    main()
