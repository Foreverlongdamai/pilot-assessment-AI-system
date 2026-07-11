from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from pilot_assessment.contracts.anchor import AnchorResult
from pilot_assessment.contracts.session import SessionManifest
from pilot_assessment.schemas.export import (
    ANCHOR_RESULT_SCHEMA_ID,
    ANCHOR_RESULT_SCHEMA_TITLE,
    SCHEMA_DIALECT,
    SESSION_MANIFEST_SCHEMA_ID,
    SESSION_MANIFEST_SCHEMA_TITLE,
    export_schemas,
    render_schemas,
)

PROJECT_ROOT = Path(__file__).parents[2]
FIXTURES = PROJECT_ROOT / "tests" / "fixtures"


def _make_present(manifest: dict[str, object], modality: str, path: str) -> None:
    streams = manifest["streams"]
    assert isinstance(streams, dict)
    stream = streams[modality]
    assert isinstance(stream, dict)
    x_stream = streams["X"]
    assert isinstance(x_stream, dict)
    stream.update(
        status="present",
        required_for_import=False,
        paths=[path],
        clock_sync=copy.deepcopy(x_stream["clock_sync"]),
        quality_summary=None,
        checksums={path: "c" * 64},
    )


def test_rendered_schemas_are_deterministic_and_valid_draft_2020_12() -> None:
    first = render_schemas()
    second = render_schemas()

    assert first == second
    assert set(first) == {
        "anchor-result-0.1.0.schema.json",
        "session-manifest-0.1.0.schema.json",
    }
    for payload in first.values():
        schema = json.loads(payload)
        assert schema["$schema"] == SCHEMA_DIALECT
        Draft202012Validator.check_schema(schema)


def test_schema_ids_titles_and_cross_language_invariants_are_frozen() -> None:
    rendered = render_schemas()
    session_schema = json.loads(rendered["session-manifest-0.1.0.schema.json"])
    anchor_schema = json.loads(rendered["anchor-result-0.1.0.schema.json"])

    assert session_schema["$id"] == SESSION_MANIFEST_SCHEMA_ID
    assert session_schema["title"] == SESSION_MANIFEST_SCHEMA_TITLE
    assert anchor_schema["$id"] == ANCHOR_RESULT_SCHEMA_ID
    assert anchor_schema["title"] == ANCHOR_RESULT_SCHEMA_TITLE

    stream_rules = session_schema["properties"]["streams"]
    assert set(stream_rules["allOf"][0]["required"]) == {
        "X",
        "U",
        "I",
        "G",
        "EEG",
        "ECG",
        "pilot_camera",
    }
    assert "P" in stream_rules["allOf"][1]["not"]["required"]
    assert session_schema["x-runtime-invariants"]
    assert anchor_schema["x-runtime-invariants"]
    assert anchor_schema["x-soft-tie-policies"] == [
        "prefer_adequate",
        "prefer_desired",
        "prefer_unacceptable",
    ]


def test_published_schemas_accept_the_canonical_json_fixtures() -> None:
    rendered = render_schemas()
    pairs = [
        ("session-manifest-0.1.0.schema.json", "session_manifest_valid.json"),
        ("anchor-result-0.1.0.schema.json", "anchor_result_computed.json"),
    ]
    for schema_name, fixture_name in pairs:
        schema = json.loads(rendered[schema_name])
        fixture = json.loads((FIXTURES / fixture_name).read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(fixture)


def test_exported_schemas_match_committed_contracts(tmp_path: Path) -> None:
    written = export_schemas(tmp_path)
    rendered = render_schemas()

    assert {path.name for path in written} == set(rendered)
    for name, payload in rendered.items():
        assert (tmp_path / name).read_bytes() == payload
        assert (PROJECT_ROOT / "schemas" / name).read_bytes() == payload


def test_schema_export_module_runs_without_preload_warning() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "pilot_assessment.schemas.export"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "RuntimeWarning" not in completed.stderr


def test_session_schema_rejects_values_rejected_by_runtime_contract() -> None:
    schema = json.loads(render_schemas()["session-manifest-0.1.0.schema.json"])
    validator = Draft202012Validator(schema)
    valid = json.loads((FIXTURES / "session_manifest_valid.json").read_text(encoding="utf-8"))

    invalid_cases: list[tuple[str, dict[str, object]]] = []

    unsupported_version = copy.deepcopy(valid)
    unsupported_version["bundle_schema_version"] = "1.0.0"
    invalid_cases.append(("unsupported major", unsupported_version))

    invalid_id = copy.deepcopy(valid)
    invalid_id["session_id"] = "has space"
    invalid_cases.append(("invalid stable ID", invalid_id))

    traversal = copy.deepcopy(valid)
    traversal["streams"]["X"]["paths"] = ["../outside.parquet"]
    traversal["streams"]["X"]["checksums"] = {"../outside.parquet": "a" * 64}
    invalid_cases.append(("path traversal", traversal))

    invalid_checksum = copy.deepcopy(valid)
    invalid_checksum["streams"]["X"]["checksums"]["streams/flight_state.parquet"] = "not-a-hash"
    invalid_cases.append(("invalid checksum", invalid_checksum))

    timestamp_number = copy.deepcopy(valid)
    timestamp_number["created_at"] = 1_720_620_000
    invalid_cases.append(("numeric timestamp", timestamp_number))

    boolean_string = copy.deepcopy(valid)
    boolean_string["streams"]["X"]["required_for_import"] = "false"
    invalid_cases.append(("string boolean", boolean_string))

    integer_string = copy.deepcopy(valid)
    integer_string["streams"]["X"]["clock_sync"]["offset_ns"] = "0"
    invalid_cases.append(("string integer", integer_string))

    number_string = copy.deepcopy(valid)
    number_string["streams"]["X"]["sample_rate_hz"] = "100.0"
    invalid_cases.append(("string number", number_string))

    bundle_reference_without_stream_id = copy.deepcopy(valid)
    bundle_reference_without_stream_id["task"]["reference"] = {
        "source": "bundle",
        "reference_id": "commanded-path-v0.1",
    }
    invalid_cases.append(
        ("bundle reference without stream id", bundle_reference_without_stream_id)
    )

    unsupported_reference_source = copy.deepcopy(valid)
    unsupported_reference_source["task"]["reference"] = {
        "source": "external",
        "reference_id": "commanded-path-v0.1",
    }
    invalid_cases.append(("unsupported reference source", unsupported_reference_source))

    invalid_without_files = copy.deepcopy(valid)
    invalid_without_files["streams"]["X"].update(
        status="invalid",
        paths=[],
        clock_sync=None,
        quality_summary=None,
        checksums={},
    )
    invalid_cases.append(("invalid stream without files", invalid_without_files))

    export_pending_with_quality = copy.deepcopy(valid)
    export_pending_with_quality["streams"]["I"]["quality_summary"] = {
        "coverage_ratio": 0.5
    }
    invalid_cases.append(("export pending quality", export_pending_with_quality))

    missing_with_clock = copy.deepcopy(valid)
    missing_with_clock["streams"]["I"].update(
        status="missing",
        clock_sync=copy.deepcopy(valid["streams"]["X"]["clock_sync"]),
    )
    invalid_cases.append(("missing stream clock", missing_with_clock))

    required_not_applicable = copy.deepcopy(valid)
    required_not_applicable["streams"]["I"].update(
        status="not_applicable",
        required_for_import=True,
    )
    invalid_cases.append(("required not applicable", required_not_applicable))

    duplicate_pending_biometric = copy.deepcopy(valid)
    duplicate_pending_biometric["privacy"][
        "biometric_modalities_export_pending"
    ].append("EEG")
    invalid_cases.append(("duplicate pending biometric", duplicate_pending_biometric))

    for label, candidate in invalid_cases:
        with pytest.raises(ValidationError):
            SessionManifest.model_validate(candidate)
        assert list(validator.iter_errors(candidate)), f"JSON Schema accepted {label}"


def test_session_schema_accepts_synthetic_present_biometrics() -> None:
    schema = json.loads(render_schemas()["session-manifest-0.1.0.schema.json"])
    candidate = json.loads(
        (FIXTURES / "session_manifest_valid.json").read_text(encoding="utf-8")
    )
    for modality in ("G", "EEG", "ECG", "pilot_camera"):
        _make_present(candidate, modality, f"streams/{modality}.parquet")
    candidate["privacy"].update(
        classification="synthetic-test-data",
        contains_biometric_data=False,
        biometric_modalities_export_pending=[],
        permitted_use="software-testing-only",
    )

    SessionManifest.model_validate(candidate)
    Draft202012Validator(schema).validate(candidate)


def test_anchor_schema_rejects_common_invalid_runtime_values() -> None:
    schema = json.loads(render_schemas()["anchor-result-0.1.0.schema.json"])
    validator = Draft202012Validator(schema)
    valid = json.loads((FIXTURES / "anchor_result_computed.json").read_text(encoding="utf-8"))

    invalid_cases: list[tuple[str, dict[str, object]]] = []

    invalid_id = copy.deepcopy(valid)
    invalid_id["anchor_id"] = "bad id"
    invalid_cases.append(("invalid stable ID", invalid_id))

    traversal = copy.deepcopy(valid)
    traversal["derived_artifacts"][0]["path"] = "../outside.parquet"
    invalid_cases.append(("artifact path traversal", traversal))

    invalid_hash = copy.deepcopy(valid)
    invalid_hash["parameter_hash"] = "not-a-hash"
    invalid_cases.append(("invalid parameter hash", invalid_hash))

    string_boolean = copy.deepcopy(valid)
    string_boolean["quality"]["passed"] = "true"
    invalid_cases.append(("string boolean", string_boolean))

    string_number = copy.deepcopy(valid)
    string_number["raw_metrics"]["translation_precision_pct"] = "94.2"
    invalid_cases.append(("string number", string_number))

    for label, candidate in invalid_cases:
        with pytest.raises(ValidationError):
            AnchorResult.model_validate(candidate)
        assert list(validator.iter_errors(candidate)), f"JSON Schema accepted {label}"
