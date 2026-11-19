"""Re-evaluate the existing demo inputs without generating or changing signals."""
from pathlib import Path
import hashlib
import json
import shutil

from pilot_assessment.scene_assessment.calculator import evaluate

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "examples/supervisor-demo-2026-09-15"
OUTPUT = ROOT / "examples/process-model-run-2026-09-16"
if OUTPUT.exists():
    raise RuntimeError(f"Run output already exists: {OUTPUT}")
shutil.copytree(SOURCE, OUTPUT)
manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
records = []
for scene in manifest["scenes"]:
    configuration_path = SOURCE / scene["configuration_file"]
    configuration = json.loads(configuration_path.read_text(encoding="utf-8"))
    for case in scene["cases"]:
        input_path = SOURCE / case["input_file"]
        data = json.loads(input_path.read_text(encoding="utf-8"))
        report = evaluate(configuration, data)
        assert report["calculation_status"] == "complete" and not report["issues"]
        assert report["grade"] == case["expected_grade"]
        assert (OUTPUT / case["input_file"]).read_bytes() == input_path.read_bytes()
        items = []
        for item in report["items"]:
            q = item["skill_quantification"]
            process = q["temporal_analysis"]
            assert process["status"] in {"complete", "not_applicable"}
            items.append({"item_id": item["item_id"], "name": item["name"],
                          "grade": item["grade"], "passed": item["passed"],
                          "final_score": q.get("score"), "process_status": process["status"],
                          "process_frames": len((process.get("item_trace") or {}).get("timeline", []))})
        (OUTPUT / case["report_file"]).write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        record = {"scene_id": scene["scene_id"], "case_id": case["case_id"],
                  "evaluated_at": report["evaluated_at"], "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
                  "configuration_sha256": hashlib.sha256(configuration_path.read_bytes()).hexdigest(),
                  "frame_count": sum(len(item["frames"]) for item in data["items"].values()),
                  "grade": report["grade"], "passed": report["passed"], "items": items}
        records.append(record)
        print(json.dumps(record, ensure_ascii=False))
(OUTPUT / "RUN_AUDIT.json").write_text(json.dumps({"source": str(SOURCE), "synthetic": True,
    "input_and_parameters_unchanged": True, "runs": records}, ensure_ascii=False, indent=2), encoding="utf-8")
