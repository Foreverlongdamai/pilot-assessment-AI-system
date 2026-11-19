"""Exercise the packaged scenes through the real stdio interface."""

import json
import runpy
import subprocess
import sys
from pathlib import Path

from pilot_assessment.scene_assessment.catalog import load_catalog


def test_two_packaged_scenes_round_trip_actual_frame_evidence(tmp_path):
    root = Path(__file__).resolve().parents[2]
    factory = runpy.run_path(str(root / "tools/Generate-SceneFrameExamples.py"))["engineering_case"]
    cases = [factory(load_catalog(scene_id)) for scene_id in ("SCN-001", "SCN-002")]
    cases[1][1]["items"]["A-S2-02"]["frames"][0]["controls"] = {
        "Pilot Lat": 20,
        "Pilot Yaw": -12,
        "Pilot Lon": 7,
        "Pilot Heave": 3,
    }
    requests = [("runtime.hello", {"supported_protocols": ["1.0"]}), ("scene.list", {})]
    requests.extend(
        ("scene.evaluate", {"configuration": config, "input": data}) for config, data in cases
    )
    requests.append(("runtime.shutdown", {}))
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
    assert len(responses) == len(requests)
    assert all("error" not in response for response in responses), responses
    assert [scene["scene_id"] for scene in responses[1]["result"]["scenes"]] == [
        "SCN-001",
        "SCN-002",
    ]
    for index, (config, data) in enumerate(cases):
        report = responses[index + 2]["result"]
        assert report["configuration"] == config
        assert report["input"] == data
        assert report["calculation_status"] == "complete", report["issues"]
        assert report["grade"] == "U" and report["passed"] is False
        for item in report["items"]:
            for point in item["checkpoints"]:
                for metric in point["metrics"]:
                    assert all("timestamp_s" in frame for frame in metric["timeline"])
                    assert all("start_s" not in frame for frame in metric["timeline"])
    hover = responses[3]["result"]
    assert {item["item_id"] for item in hover["items"]} == {"A-S2-02", "SCENE-VERTICAL"}
    point_hold = next(item for item in hover["items"] if item["item_id"] == "A-S2-02")
    assert len(point_hold["checkpoints"]) == 4
    assert "hover_lower_height_m" in hover["input"]["items"]["A-S2-02"]["frames"][0]["values"]
    assert len(point_hold["phase_results"]) == 4
    assert all(phase["observed_span_s"] == 5 for phase in point_hold["phase_results"])
    assert [phase["grade"] for phase in point_hold["phase_results"]] == ["A", "U", "U", "A"]
    assert point_hold["timeline"][0]["grade"] == "D"  # Control effort alone does not reduce grade.
