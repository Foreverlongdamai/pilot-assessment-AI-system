from __future__ import annotations

import io
import json
import subprocess
import sys

from pilot_assessment.scene_assessment.catalog import load_catalog
from pilot_assessment.scene_assessment.server import serve


def synthetic_case():
    """Deliberately artificial arithmetic fixture, never a default flight profile."""
    catalog = load_catalog(schema_version="2.0")
    configuration, input_data = catalog["configuration_template"], catalog["input_template"]
    metrics = {metric["metric_id"]: metric for metric in catalog["metrics"]}
    for key, parameter in configuration["parameters"].items():
        parameter.update(
            expected=359 if metrics[key]["comparison"] == "angle_degrees" else 100,
            desired={"lower": -2, "upper": 2, "unbounded_upper": False},
            acceptable={"lower": -5, "upper": 5, "unbounded_upper": False},
        )
    for item in catalog["items"]:
        for checkpoint in item["checkpoints"]:
            target = input_data["items"][item["item_id"]]["checkpoints"][
                checkpoint["checkpoint_id"]
            ]
            series = []
            for key in checkpoint["metric_ids"]:
                metric = metrics[key]
                if metric["input_kind"] == "series":
                    series.append(key)
                elif metric["rule"] == "must_be_true":
                    target["values"][key] = True
                elif metric["rule"] == "zero_events":
                    target["values"][key] = 0
                else:
                    target["values"][key] = configuration["parameters"][key]["expected"]
            if series:
                target["samples"] = [
                    {
                        "start_s": start,
                        "end_s": end,
                        "values": {
                            key: (
                                (configuration["parameters"][key]["expected"] + deviation) % 360
                                if metrics[key]["comparison"] == "angle_degrees"
                                else configuration["parameters"][key]["expected"] + deviation
                            )
                            for key in series
                        },
                    }
                    for start, end, deviation in [(0, 1, 2), (1, 4, 4), (4, 5, 6)]
                ]
    return configuration, input_data


def test_v2_stdio_roundtrip_preserves_raw_samples_and_reports_distribution(tmp_path):
    configuration, input_data = synthetic_case()
    requests = [
        ("runtime.hello", {"supported_protocols": ["1.0"]}),
        ("scene.catalog", {"schema_version": "2.0"}),
        ("scene.validate_configuration", {"configuration": configuration}),
        ("scene.evaluate", {"configuration": configuration, "input": input_data}),
        ("scene.catalog", {"schema_version": "1.0"}),
        ("runtime.shutdown", {}),
    ]
    payload = "".join(
        json.dumps({"jsonrpc": "2.0", "id": index, "method": method, "params": params}) + "\n"
        for index, (method, params) in enumerate(requests)
    )
    process = subprocess.run(
        [sys.executable, "-m", "pilot_assessment.scene_assessment"],
        input=payload,
        text=True,
        encoding="utf-8",
        capture_output=True,
        cwd=tmp_path,
        timeout=30,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    responses = [json.loads(line) for line in process.stdout.splitlines()]
    assert all("error" not in response for response in responses), responses
    assert responses[0]["result"]["max_message_bytes"] == 64 * 1024 * 1024
    assert responses[1]["result"]["schema_version"] == "2.0"
    assert responses[2]["result"]["valid"]
    report = responses[3]["result"]
    assert report["input"] == input_data and report["configuration"] == configuration
    assert report["calculation_status"] == "complete" and report["grade"] == "U"
    assert report["items"][0]["skill_quantification"]["status"] == "not_applicable"
    assert all(
        item["skill_quantification"]["status"] == "pending_method" for item in report["items"][1:]
    )
    heading = next(
        metric
        for item in report["items"]
        for checkpoint in item["checkpoints"]
        for metric in checkpoint["metrics"]
        if metric["metric_id"] == "takeoff_heading_deg"
    )
    assert heading["timeline"][0]["value"] == 1
    assert heading["timeline"][0]["deviation"] == 2
    assert heading["distribution"]["proportions"] == {"D": 0.2, "A": 0.6, "U": 0.2}
    assert responses[4]["result"]["schema_version"] == "1.0"
    assert len(responses[4]["result"]["items"]) == 6


def test_scene_frame_limit_accepts_more_than_legacy_four_mib():
    from pilot_assessment.sidecar.framing import DEFAULT_MAX_MESSAGE_BYTES

    assert DEFAULT_MAX_MESSAGE_BYTES == 4 * 1024 * 1024
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "runtime.hello",
            "params": {"supported_protocols": ["1.0"]},
        },
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "scene.catalog",
            "params": {"extra": "x" * (5 * 1024 * 1024)},
        },
        {"jsonrpc": "2.0", "id": 2, "method": "runtime.shutdown", "params": {}},
    ]
    output = io.BytesIO()
    serve(
        io.BytesIO(("\n".join(json.dumps(message) for message in messages) + "\n").encode()), output
    )
    responses = [json.loads(line) for line in output.getvalue().splitlines()]
    # It reaches ordinary parameter validation rather than failing frame parsing.
    assert responses[1]["id"] == 1 and responses[1]["error"]["code"] == -32602
    assert responses[2]["result"]["state"] == "stopping"
