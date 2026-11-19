from __future__ import annotations

import importlib
import json
import subprocess
import sys


def load_catalog():
    module = importlib.import_module("pilot_assessment.scene_assessment.catalog")
    return module.load_catalog(schema_version="1.0")


def configured_case():
    catalog = load_catalog()
    configuration = catalog["configuration_template"]
    input_data = catalog["input_template"]
    for metric in catalog["metrics"]:
        key, kind, rule = metric["metric_id"], metric["parameter_kind"], metric["rule"]
        if rule != "interval":
            input_data["results"][key] = rule == "must_be_true" if rule == "must_be_true" else 0
            continue
        if kind == "error":
            values = (0, 0, 1, 0, 2)
        elif kind == "signed":
            values = (0, -1, 1, -2, 2)
        elif kind == "hold":
            values = (5, 4, None, 2, None)
        else:
            values = (3, 2, 4, 1, 5)
        expected, dl, du, al, au = values
        configuration["parameters"][key] = {
            "expected": expected,
            "desired": {"lower": dl, "upper": du, "unbounded_upper": du is None},
            "acceptable": {"lower": al, "upper": au, "unbounded_upper": au is None},
        }
        input_data["results"][key] = expected
    return configuration, input_data


def test_packaged_catalog_has_six_items_and_no_scientific_defaults():
    catalog = load_catalog()
    assert len(catalog["metrics"]) == 30
    assert len(catalog["items"]) == 6
    assert sum(len(item["checkpoints"]) for item in catalog["items"]) == 19
    metrics = {metric["metric_id"] for metric in catalog["metrics"]}
    assert len(metrics) == 30
    references = {
        key
        for item in catalog["items"]
        for point in item["checkpoints"]
        for key in point["metric_ids"]
    }
    assert references == metrics
    assert all(value is None for value in catalog["input_template"]["results"].values())
    rows = catalog["configuration_template"]["parameters"]
    assert len(rows) == 27
    assert all(row["desired"]["upper"] is None for row in rows.values())
    assert sum(key == "terminal_hover_duration_s" for key in rows) == 1
    catalog["configuration_template"]["parameters"]["energy_electrical"]["expected"] = 99
    assert (
        load_catalog()["configuration_template"]["parameters"]["energy_electrical"]["expected"]
        is None
    )


def test_real_scene_all_items_and_external_short_circuit():
    calculator = importlib.import_module("pilot_assessment.scene_assessment.calculator")
    configuration, input_data = configured_case()
    assert calculator.validate_configuration(configuration)["valid"]
    report = calculator.evaluate(configuration, input_data)
    assert report["grade"] == "D"
    assert [item["grade"] for item in report["items"]] == ["D"] * 6
    input_data["results"].update(
        deceleration_started=False,
        deceleration_onset_position_error_m=None,
        quickstop_entry_airspeed_error_mps=None,
        deceleration_duration_s=None,
        stop_achieved=None,
    )
    report = calculator.evaluate(configuration, input_data)
    quickstop = next(item for item in report["items"] if item["item_id"] == "A-S2-30")
    assert [point["grade"] for point in quickstop["checkpoints"]][:2] == ["U", "U"]
    assert report["grade"] == "U"
    assert report["calculation_status"] == "complete"


def test_absent_terminal_hold_does_not_request_nonexistent_heading():
    calculator = importlib.import_module("pilot_assessment.scene_assessment.calculator")
    configuration, input_data = configured_case()
    catalog = load_catalog()
    position = next(item for item in catalog["items"] if item["item_id"] == "A-S2-02")
    heading = next(
        point for point in position["checkpoints"] if point["checkpoint_id"] == "A-S2-02-02"
    )
    # The rule is a catalog instruction, not a calculator special case for this item.
    assert heading["not_required_when"] == [{"metric_id": "terminal_hover_duration_s", "equals": 0}]
    for key in input_data["results"]:
        if key.startswith("terminal_"):
            input_data["results"][key] = None
    input_data["results"]["terminal_hover_duration_s"] = 0
    report = calculator.evaluate(configuration, input_data, catalog=catalog)
    position_result = next(item for item in report["items"] if item["item_id"] == "A-S2-02")
    heading_result = position_result["checkpoints"][1]
    assert position_result["grade"] == "U"
    assert heading_result["grade"] is None
    assert heading_result["metrics"][0]["status"] == "not_required"
    assert heading_result["metrics"][0]["grade"] is None
    assert not any("terminal_max_heading_error_deg" in entry["path"] for entry in report["issues"])
    assert report["calculation_status"] == "complete"
    assert report["grade"] == "U"
    # Supplied values remain visible; the exemption only concerns absent values.
    input_data["results"]["terminal_max_heading_error_deg"] = 1.5
    supplied = calculator.evaluate(configuration, input_data, catalog=catalog)
    position_result = next(item for item in supplied["items"] if item["item_id"] == "A-S2-02")
    assert position_result["checkpoints"][1]["grade"] == "A"


def test_stdio_hello_catalog_calculation_and_shutdown_do_not_create_old_store(tmp_path):
    configuration, input_data = configured_case()
    requests = [
        ("runtime.hello", {"supported_protocols": ["1.0"]}),
        ("capabilities.list", {}),
        ("runtime.status", {}),
        ("scene.catalog", {"schema_version": "1.0"}),
        ("scene.validate_configuration", {"configuration": configuration}),
        ("scene.evaluate", {"configuration": configuration, "input": input_data}),
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
        timeout=20,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    responses = [json.loads(line) for line in process.stdout.splitlines()]
    assert len(responses) == len(requests)
    assert all("error" not in response for response in responses), responses
    hello = responses[0]["result"]
    assert hello["capabilities"] == [
        "runtime.protocol.v1",
        "scene.assessment.v1",
        "scene.assessment.v2",
        "scene.assessment.v3",
    ]
    assert hello["runtime_id"] and hello["backend_version"] and hello["max_message_bytes"]
    assert "scene.evaluate" in responses[1]["result"]["methods"]
    assert responses[2]["result"]["state"] == "ready"
    assert responses[3]["result"]["scene_id"] == "SCN-001"
    assert responses[4]["result"]["valid"]
    assert responses[5]["result"]["grade"] == "D"
    assert responses[6]["result"]["state"] == "stopping"
    assert not list(tmp_path.iterdir()), "Scene startup must not create an old model database"


def test_stdio_rejects_nonfinite_numbers_and_recovers(tmp_path):
    lines = [
        '{"jsonrpc":"2.0","id":0,"method":"runtime.hello",'
        '"params":{"supported_protocols":["1.0"]}}',
        '{"jsonrpc":"2.0","id":1,"method":"scene.evaluate",'
        '"params":{"configuration":{},"input":{"bad":NaN}}}',
        '{"jsonrpc":"2.0","id":2,"method":"scene.evaluate",'
        '"params":{"configuration":{},"input":{"bad":Infinity}}}',
        '{"jsonrpc":"2.0","id":3,"method":"scene.evaluate",'
        '"params":{"configuration":{},"input":{"bad":1e999}}}',
        '{"jsonrpc":"2.0","id":4,"method":"runtime.shutdown","params":{}}',
    ]
    process = subprocess.run(
        [sys.executable, "-m", "pilot_assessment.scene_assessment"],
        input="\n".join(lines) + "\n",
        text=True,
        encoding="utf-8",
        capture_output=True,
        cwd=tmp_path,
        timeout=20,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    responses = [json.loads(line) for line in process.stdout.splitlines()]
    assert [response["error"]["code"] for response in responses[1:4]] == [
        -32700,
        -32700,
        -32602,
    ]
    assert responses[-1]["result"]["state"] == "stopping"
