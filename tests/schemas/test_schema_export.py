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
from pilot_assessment.contracts.ingestion import IngestionReadinessReport
from pilot_assessment.contracts.session import SessionManifest
from pilot_assessment.schemas.export import (
    ANCHOR_RESULT_SCHEMA_ID,
    ANCHOR_RESULT_SCHEMA_TITLE,
    INGESTION_READINESS_SCHEMA_ID,
    INGESTION_READINESS_SCHEMA_TITLE,
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


def _task_reference_descriptor(manifest: dict[str, object]) -> dict[str, object]:
    streams = manifest["streams"]
    assert isinstance(streams, dict)
    descriptor = copy.deepcopy(streams["X"])
    assert isinstance(descriptor, dict)
    path = "references/commanded_path.parquet"
    descriptor.update(
        modality="task_reference",
        required_for_import=False,
        paths=[path],
        format="parquet",
        schema_id="task-reference-path-raw-v0.1",
        units="task-reference-units-v0.1",
        quality_summary=None,
        checksums={path: "d" * 64},
        metadata={"artifact_role": "task_reference"},
    )
    return descriptor


def _make_uninspected_readiness_result(
    result: dict[str, object],
    *,
    declared_status: str,
    readiness: str,
    required_for_import: bool,
) -> None:
    result.update(
        declared_status=declared_status,
        required_for_import=required_for_import,
        readiness=readiness,
        adapter_id=None,
        adapter_version=None,
        source_paths=[],
        source_checksums={},
        normalized_schema_id=None,
        row_count=None,
        artifact_row_counts={},
        source_time_start_s=None,
        source_time_end_s=None,
        observed_sample_rate_hz=None,
        canonical_fields=[],
        units={},
        quality_summary={},
        assumptions=[],
        issues=[],
    )


def test_rendered_schemas_are_deterministic_and_valid_draft_2020_12() -> None:
    first = render_schemas()
    second = render_schemas()

    assert first == second
    assert set(first) == {
        "anchor-result-0.1.0.schema.json",
        "ingestion-readiness-report-0.1.0.schema.json",
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
    readiness_schema = json.loads(rendered["ingestion-readiness-report-0.1.0.schema.json"])

    assert session_schema["$id"] == SESSION_MANIFEST_SCHEMA_ID
    assert session_schema["title"] == SESSION_MANIFEST_SCHEMA_TITLE
    assert anchor_schema["$id"] == ANCHOR_RESULT_SCHEMA_ID
    assert anchor_schema["title"] == ANCHOR_RESULT_SCHEMA_TITLE
    assert readiness_schema["$id"] == INGESTION_READINESS_SCHEMA_ID
    assert readiness_schema["title"] == INGESTION_READINESS_SCHEMA_TITLE

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
        (
            "ingestion-readiness-report-0.1.0.schema.json",
            "ingestion_readiness_ready.json",
        ),
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
    invalid_cases.append(("bundle reference without stream id", bundle_reference_without_stream_id))

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
    export_pending_with_quality["streams"]["I"]["quality_summary"] = {"coverage_ratio": 0.5}
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
    duplicate_pending_biometric["privacy"]["biometric_modalities_export_pending"].append("EEG")
    invalid_cases.append(("duplicate pending biometric", duplicate_pending_biometric))

    for label, candidate in invalid_cases:
        with pytest.raises(ValidationError):
            SessionManifest.model_validate(candidate)
        assert list(validator.iter_errors(candidate)), f"JSON Schema accepted {label}"


def test_session_schema_accepts_synthetic_present_biometrics() -> None:
    schema = json.loads(render_schemas()["session-manifest-0.1.0.schema.json"])
    candidate = json.loads((FIXTURES / "session_manifest_valid.json").read_text(encoding="utf-8"))
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


def test_session_schema_enforces_biometric_pending_membership_and_privacy() -> None:
    schema = json.loads(render_schemas()["session-manifest-0.1.0.schema.json"])
    validator = Draft202012Validator(schema)
    valid = json.loads((FIXTURES / "session_manifest_valid.json").read_text(encoding="utf-8"))

    invalid_cases: list[tuple[str, dict[str, object]]] = []

    missing_pending_member = copy.deepcopy(valid)
    missing_pending_member["privacy"]["biometric_modalities_export_pending"].remove("EEG")
    invalid_cases.append(("export pending EEG omitted from privacy", missing_pending_member))

    stale_pending_member = copy.deepcopy(valid)
    stale_pending_member["streams"]["EEG"].update(
        status="missing",
        clock_sync=None,
    )
    invalid_cases.append(("missing EEG retained in pending privacy list", stale_pending_member))

    non_biometric_pending_member = copy.deepcopy(valid)
    non_biometric_pending_member["privacy"]["biometric_modalities_export_pending"].append("I")
    invalid_cases.append(
        ("non-biometric I appears in pending privacy list", non_biometric_pending_member)
    )

    synthetic_with_pending = copy.deepcopy(valid)
    synthetic_with_pending["privacy"].update(
        classification="synthetic-test-data",
        contains_biometric_data=False,
        permitted_use="software-testing-only",
    )
    invalid_cases.append(("synthetic bundle declares pending biometrics", synthetic_with_pending))

    synthetic_with_real_biometric_flag = copy.deepcopy(valid)
    for modality in ("G", "EEG", "ECG", "pilot_camera"):
        _make_present(
            synthetic_with_real_biometric_flag,
            modality,
            f"streams/{modality}.parquet",
        )
    synthetic_with_real_biometric_flag["privacy"].update(
        classification="synthetic-test-data",
        contains_biometric_data=True,
        biometric_modalities_export_pending=[],
        permitted_use="software-testing-only",
    )
    invalid_cases.append(
        ("synthetic bundle claims real biometric data", synthetic_with_real_biometric_flag)
    )

    real_export_without_biometric_flag = copy.deepcopy(valid)
    _make_present(real_export_without_biometric_flag, "EEG", "streams/EEG.parquet")
    real_export_without_biometric_flag["privacy"]["biometric_modalities_export_pending"].remove(
        "EEG"
    )
    invalid_cases.append(
        ("real present EEG omits biometric data flag", real_export_without_biometric_flag)
    )

    for label, candidate in invalid_cases:
        with pytest.raises(ValidationError):
            SessionManifest.model_validate(candidate)
        assert list(validator.iter_errors(candidate)), f"JSON Schema accepted {label}"


def test_session_schema_accepts_complete_biometric_status_privacy_matrix() -> None:
    schema = json.loads(render_schemas()["session-manifest-0.1.0.schema.json"])
    validator = Draft202012Validator(schema)
    valid = json.loads((FIXTURES / "session_manifest_valid.json").read_text(encoding="utf-8"))

    for modality in ("G", "EEG", "ECG", "pilot_camera"):
        for status in ("present", "invalid", "export_pending", "missing", "not_applicable"):
            candidate = copy.deepcopy(valid)
            stream = candidate["streams"][modality]
            pending = candidate["privacy"]["biometric_modalities_export_pending"]
            if status in {"present", "invalid"}:
                _make_present(candidate, modality, f"streams/{modality}.parquet")
                stream["status"] = status
                pending.remove(modality)
                candidate["privacy"]["contains_biometric_data"] = True
            elif status != "export_pending":
                stream.update(
                    status=status,
                    required_for_import=False,
                    paths=[],
                    clock_sync=None,
                    quality_summary=None,
                    checksums={},
                )
                pending.remove(modality)

            SessionManifest.model_validate(candidate)
            validator.validate(candidate)


def test_session_schema_enforces_bundle_task_reference_ownership() -> None:
    schema = json.loads(render_schemas()["session-manifest-0.1.0.schema.json"])
    validator = Draft202012Validator(schema)
    valid = json.loads((FIXTURES / "session_manifest_valid.json").read_text(encoding="utf-8"))

    valid_bundle_reference = copy.deepcopy(valid)
    valid_bundle_reference["task"]["reference"] = {
        "source": "bundle",
        "reference_id": "commanded-path-v0.1",
        "stream_id": "task_reference",
    }
    valid_bundle_reference["streams"]["task_reference"] = _task_reference_descriptor(
        valid_bundle_reference
    )
    SessionManifest.model_validate(valid_bundle_reference)
    validator.validate(valid_bundle_reference)

    invalid_cases: list[tuple[str, dict[str, object]]] = []

    unowned_descriptor = copy.deepcopy(valid)
    unowned_descriptor["streams"]["task_reference"] = _task_reference_descriptor(unowned_descriptor)
    invalid_cases.append(("unowned task reference descriptor", unowned_descriptor))

    missing_descriptor = copy.deepcopy(valid)
    missing_descriptor["task"]["reference"] = {
        "source": "bundle",
        "reference_id": "commanded-path-v0.1",
        "stream_id": "task_reference",
    }
    invalid_cases.append(("bundle reference without descriptor", missing_descriptor))

    wrong_owner_stream = copy.deepcopy(valid)
    wrong_owner_stream["task"]["reference"] = {
        "source": "bundle",
        "reference_id": "commanded-path-v0.1",
        "stream_id": "X",
    }
    invalid_cases.append(("bundle reference points to X", wrong_owner_stream))

    outside_reference_directory = copy.deepcopy(valid_bundle_reference)
    outside_reference_directory["streams"]["task_reference"]["paths"] = [
        "streams/commanded_path.parquet"
    ]
    outside_reference_directory["streams"]["task_reference"]["checksums"] = {
        "streams/commanded_path.parquet": "d" * 64
    }
    invalid_cases.append(
        ("bundle reference artifact outside references", outside_reference_directory)
    )

    model_bundle_with_descriptor = copy.deepcopy(valid_bundle_reference)
    model_bundle_with_descriptor["task"]["reference"] = {
        "source": "model_bundle",
        "reference_id": "commanded-path-v0.1",
    }
    invalid_cases.append(
        ("model bundle reference owns local descriptor", model_bundle_with_descriptor)
    )

    for label, candidate in invalid_cases:
        with pytest.raises(ValidationError):
            SessionManifest.model_validate(candidate)
        assert list(validator.iter_errors(candidate)), f"JSON Schema accepted {label}"


def test_readiness_schema_rejects_public_contract_contradictions() -> None:
    schema = json.loads(render_schemas()["ingestion-readiness-report-0.1.0.schema.json"])
    validator = Draft202012Validator(schema)
    valid = json.loads((FIXTURES / "ingestion_readiness_ready.json").read_text(encoding="utf-8"))

    invalid_cases: list[tuple[str, dict[str, object]]] = []

    formal_authorization = copy.deepcopy(valid)
    formal_authorization["formal_run_authorized"] = True
    invalid_cases.append(("formal authorization", formal_authorization))

    missing_core = copy.deepcopy(valid)
    del missing_core["stream_results"]["ECG"]
    invalid_cases.append(("missing core result", missing_core))

    extra_core = copy.deepcopy(valid)
    extra_core["stream_results"]["THERMAL"] = copy.deepcopy(extra_core["stream_results"]["I"])
    extra_core["stream_results"]["THERMAL"]["modality"] = "THERMAL"
    invalid_cases.append(("extra core result", extra_core))

    unavailable_claim = copy.deepcopy(valid)
    unavailable_claim["stream_results"]["I"].update(
        declared_status="export_pending",
        readiness="unavailable",
        source_paths=[],
        source_checksums={},
    )
    unavailable_claim["disposition"] = "ready_partial"
    invalid_cases.append(("unavailable result claims inspection", unavailable_claim))

    missing_synthetic_provenance = copy.deepcopy(valid)
    missing_synthetic_provenance["synthetic_provenance"] = None
    invalid_cases.append(
        ("synthetic classification without provenance", missing_synthetic_provenance)
    )

    provenance_on_real_data = copy.deepcopy(valid)
    provenance_on_real_data["source_classification"] = "restricted-research-pseudonymous"
    invalid_cases.append(("synthetic provenance on real data", provenance_on_real_data))

    for label, candidate in invalid_cases:
        with pytest.raises(ValidationError):
            IngestionReadinessReport.model_validate(candidate)
        assert list(validator.iter_errors(candidate)), f"JSON Schema accepted {label}"


def test_readiness_schema_enforces_result_ownership_and_disposition_matrix() -> None:
    schema = json.loads(render_schemas()["ingestion-readiness-report-0.1.0.schema.json"])
    validator = Draft202012Validator(schema)
    valid = json.loads((FIXTURES / "ingestion_readiness_ready.json").read_text(encoding="utf-8"))

    invalid_cases: list[tuple[str, dict[str, object]]] = []

    wrong_core_owner = copy.deepcopy(valid)
    wrong_core_owner["stream_results"]["X"]["modality"] = "U"
    invalid_cases.append(("X result claims U modality", wrong_core_owner))

    wrong_reference_owner = copy.deepcopy(valid)
    wrong_reference_owner["task_reference_result"]["modality"] = "X"
    invalid_cases.append(("task reference result claims X modality", wrong_reference_owner))

    optional_unavailable_claims_ready = copy.deepcopy(valid)
    _make_uninspected_readiness_result(
        optional_unavailable_claims_ready["stream_results"]["I"],
        declared_status="export_pending",
        readiness="unavailable",
        required_for_import=False,
    )
    invalid_cases.append(
        ("optional unavailable core claims ready", optional_unavailable_claims_ready)
    )

    required_unavailable_claims_partial = copy.deepcopy(valid)
    _make_uninspected_readiness_result(
        required_unavailable_claims_partial["stream_results"]["I"],
        declared_status="missing",
        readiness="unavailable",
        required_for_import=True,
    )
    required_unavailable_claims_partial.update(
        disposition="ready_partial",
        can_continue_to_synchronization=True,
    )
    invalid_cases.append(
        ("required unavailable core claims partial", required_unavailable_claims_partial)
    )

    optional_not_applicable_claims_partial = copy.deepcopy(valid)
    _make_uninspected_readiness_result(
        optional_not_applicable_claims_partial["stream_results"]["I"],
        declared_status="not_applicable",
        readiness="not_applicable",
        required_for_import=False,
    )
    optional_not_applicable_claims_partial.update(
        disposition="ready_partial",
        can_continue_to_synchronization=True,
    )
    invalid_cases.append(
        ("optional not applicable core claims partial", optional_not_applicable_claims_partial)
    )

    optional_reference_unavailable_claims_ready = copy.deepcopy(valid)
    reference_result = optional_reference_unavailable_claims_ready["task_reference_result"]
    assert isinstance(reference_result, dict)
    _make_uninspected_readiness_result(
        reference_result,
        declared_status="missing",
        readiness="unavailable",
        required_for_import=False,
    )
    invalid_cases.append(
        (
            "optional unavailable task reference claims ready",
            optional_reference_unavailable_claims_ready,
        )
    )

    required_reference_unavailable_claims_partial = copy.deepcopy(valid)
    reference_result = required_reference_unavailable_claims_partial["task_reference_result"]
    assert isinstance(reference_result, dict)
    _make_uninspected_readiness_result(
        reference_result,
        declared_status="missing",
        readiness="unavailable",
        required_for_import=True,
    )
    required_reference_unavailable_claims_partial.update(
        disposition="ready_partial",
        can_continue_to_synchronization=True,
    )
    invalid_cases.append(
        (
            "required unavailable task reference claims partial",
            required_reference_unavailable_claims_partial,
        )
    )

    ready_cannot_stop_synchronization = copy.deepcopy(valid)
    ready_cannot_stop_synchronization["can_continue_to_synchronization"] = False
    invalid_cases.append(
        ("ready report cannot stop synchronization", ready_cannot_stop_synchronization)
    )

    for label, candidate in invalid_cases:
        with pytest.raises(ValidationError):
            IngestionReadinessReport.model_validate(candidate)
        assert list(validator.iter_errors(candidate)), f"JSON Schema accepted {label}"


def test_readiness_schema_accepts_complete_core_and_reference_state_matrix() -> None:
    schema = json.loads(render_schemas()["ingestion-readiness-report-0.1.0.schema.json"])
    validator = Draft202012Validator(schema)
    valid = json.loads((FIXTURES / "ingestion_readiness_ready.json").read_text(encoding="utf-8"))
    non_ready_states = (
        ("unavailable", "missing"),
        ("invalid", "invalid"),
        ("unsupported", "present"),
        ("not_applicable", "not_applicable"),
    )

    for modality in ("X", "U", "I", "G", "EEG", "ECG", "pilot_camera"):
        for readiness, declared_status in (("ready", "present"), *non_ready_states):
            for required in (False, True):
                candidate = copy.deepcopy(valid)
                result = candidate["stream_results"][modality]
                if readiness == "invalid":
                    result.update(
                        declared_status=declared_status,
                        required_for_import=required,
                        readiness=readiness,
                    )
                elif readiness != "ready":
                    _make_uninspected_readiness_result(
                        result,
                        declared_status=declared_status,
                        readiness=readiness,
                        required_for_import=required,
                    )
                else:
                    result["required_for_import"] = required

                blocked = required and readiness != "ready"
                degraded = readiness in {"unavailable", "invalid", "unsupported"}
                candidate["disposition"] = (
                    "blocked" if blocked else "ready_partial" if degraded else "ready"
                )
                candidate["can_continue_to_synchronization"] = not blocked
                IngestionReadinessReport.model_validate(candidate)
                validator.validate(candidate)

    for readiness, declared_status in (("ready", "present"), *non_ready_states):
        for required in (False, True):
            candidate = copy.deepcopy(valid)
            result = candidate["task_reference_result"]
            assert isinstance(result, dict)
            if readiness == "invalid":
                result.update(
                    declared_status=declared_status,
                    required_for_import=required,
                    readiness=readiness,
                )
            elif readiness != "ready":
                _make_uninspected_readiness_result(
                    result,
                    declared_status=declared_status,
                    readiness=readiness,
                    required_for_import=required,
                )
            else:
                result["required_for_import"] = required

            blocked = required and readiness != "ready"
            degraded = readiness != "ready"
            candidate["disposition"] = (
                "blocked" if blocked else "ready_partial" if degraded else "ready"
            )
            candidate["can_continue_to_synchronization"] = not blocked
            IngestionReadinessReport.model_validate(candidate)
            validator.validate(candidate)

    without_reference = copy.deepcopy(valid)
    without_reference["task_reference_result"] = None
    IngestionReadinessReport.model_validate(without_reference)
    validator.validate(without_reference)


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
