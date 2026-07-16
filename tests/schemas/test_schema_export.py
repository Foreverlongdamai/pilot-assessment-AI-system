from __future__ import annotations

import copy
import hashlib
import importlib
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
from pilot_assessment.contracts.synchronization import (
    MAX_SESSION_END_NS_V0_1,
    SynchronizationReport,
)
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

LEGACY_SCHEMA_SHA256 = {
    "anchor-result-0.1.0.schema.json": (
        "c8b6cea319c377b8a61923c5f1122c3e70a79b59f054637ff0334082b2deb5f5"
    ),
    "ingestion-readiness-report-0.1.0.schema.json": (
        "0c91ba0e26819af8d90bd8e7ca661cdd71b9e57fd62eb0fbb489d5ffb49e94d7"
    ),
    "session-manifest-0.1.0.schema.json": (
        "939d12c86bbdc0e337b125e1fddffd189369340f3a4556594efecbe360e08f58"
    ),
    "synchronization-report-0.1.0.schema.json": (
        "f43a55f0666ddafd09a88f8c08c63929f22b6ddd69caea47e52d0492b4234bb8"
    ),
}

M4_SCHEMA_METADATA = {
    "anchor-result-0.2.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:anchor-result:0.2.0",
        "Pilot Assessment Anchor Result 0.2.0",
        "0.2.0",
    ),
    "anchor-measurement-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:anchor-measurement:0.1.0",
        "Pilot Assessment Anchor Measurement 0.1.0",
        "0.1.0",
    ),
    "anchor-plugin-definition-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:anchor-plugin-definition:0.1.0",
        "Pilot Assessment Anchor Plugin Definition 0.1.0",
        "0.1.0",
    ),
    "preprocessing-provider-definition-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:preprocessing-provider-definition:0.1.0",
        "Pilot Assessment Preprocessing Provider Definition 0.1.0",
        "0.1.0",
    ),
    "anchor-catalog-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:anchor-catalog:0.1.0",
        "Pilot Assessment Anchor Catalog 0.1.0",
        "0.1.0",
    ),
    "anchor-runtime-registry-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:anchor-runtime-registry:0.1.0",
        "Pilot Assessment Anchor Runtime Registry 0.1.0",
        "0.1.0",
    ),
    "anchor-execution-plan-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:anchor-execution-plan:0.1.0",
        "Pilot Assessment Anchor Execution Plan 0.1.0",
        "0.1.0",
    ),
    "session-semantic-snapshot-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:session-semantic-snapshot:0.1.0",
        "Pilot Assessment Session Semantic Snapshot 0.1.0",
        "0.1.0",
    ),
    "resolved-reference-set-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:resolved-reference-set:0.1.0",
        "Pilot Assessment Resolved Reference Set 0.1.0",
        "0.1.0",
    ),
    "anchor-evaluation-report-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:anchor-evaluation-report:0.1.0",
        "Pilot Assessment Anchor Evaluation Report 0.1.0",
        "0.1.0",
    ),
    "evidence-recipe-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:evidence-recipe:0.1.0",
        "Pilot Assessment Evidence Recipe 0.1.0",
        "0.1.0",
    ),
    "operator-definition-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:operator-definition:0.1.0",
        "Pilot Assessment Operator Definition 0.1.0",
        "0.1.0",
    ),
}

M5_SCHEMA_METADATA = {
    "evidence-concept-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:evidence-concept:0.1.0",
        "Pilot Assessment Evidence Concept 0.1.0",
        "0.1.0",
    ),
    "evidence-version-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:evidence-version:0.1.0",
        "Pilot Assessment Evidence Version 0.1.0",
        "0.1.0",
    ),
    "bn-node-concept-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:bn-node-concept:0.1.0",
        "Pilot Assessment BN Node Concept 0.1.0",
        "0.1.0",
    ),
    "bn-node-version-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:bn-node-version:0.1.0",
        "Pilot Assessment BN Node Version 0.1.0",
        "0.1.0",
    ),
    "evidence-binding-version-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:evidence-binding-version:0.1.0",
        "Pilot Assessment Evidence Binding Version 0.1.0",
        "0.1.0",
    ),
    "cpt-version-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:cpt-version:0.1.0",
        "Pilot Assessment CPT Version 0.1.0",
        "0.1.0",
    ),
    "task-profile-version-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:task-profile-version:0.1.0",
        "Pilot Assessment Task Profile Version 0.1.0",
        "0.1.0",
    ),
    "coverage-reporting-policy-version-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:coverage-reporting-policy-version:0.1.0",
        "Pilot Assessment Coverage Reporting Policy Version 0.1.0",
        "0.1.0",
    ),
    "layout-version-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:layout-version:0.1.0",
        "Pilot Assessment Layout Version 0.1.0",
        "0.1.0",
    ),
    "assessment-scheme-version-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:assessment-scheme-version:0.1.0",
        "Pilot Assessment Scheme Version 0.1.0",
        "0.1.0",
    ),
    "source-descriptor-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:source-descriptor:0.1.0",
        "Pilot Assessment Source Descriptor 0.1.0",
        "0.1.0",
    ),
    "scheme-draft-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:scheme-draft:0.1.0",
        "Pilot Assessment Scheme Draft 0.1.0",
        "0.1.0",
    ),
    "inference-plan-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:inference-plan:0.1.0",
        "Pilot Assessment Inference Plan 0.1.0",
        "0.1.0",
    ),
    "observation-set-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:observation-set:0.1.0",
        "Pilot Assessment Observation Set 0.1.0",
        "0.1.0",
    ),
    "posterior-result-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:posterior-result:0.1.0",
        "Pilot Assessment Posterior Result 0.1.0",
        "0.1.0",
    ),
    "inference-trace-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:inference-trace:0.1.0",
        "Pilot Assessment Inference Trace 0.1.0",
        "0.1.0",
    ),
}

M6_SCHEMA_METADATA = {
    "project-descriptor-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:project-descriptor:0.1.0",
        "Pilot Assessment Project Descriptor 0.1.0",
        "0.1.0",
    ),
    "session-record-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:session-record:0.1.0",
        "Pilot Assessment Session Record 0.1.0",
        "0.1.0",
    ),
    "session-revision-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:session-revision:0.1.0",
        "Pilot Assessment Session Revision 0.1.0",
        "0.1.0",
    ),
    "managed-artifact-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:managed-artifact:0.1.0",
        "Pilot Assessment Managed Artifact 0.1.0",
        "0.1.0",
    ),
    "artifact-reference-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:artifact-reference:0.1.0",
        "Pilot Assessment Artifact Reference 0.1.0",
        "0.1.0",
    ),
    "transaction-receipt-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:transaction-receipt:0.1.0",
        "Pilot Assessment Transaction Receipt 0.1.0",
        "0.1.0",
    ),
    "audit-event-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:audit-event:0.1.0",
        "Pilot Assessment Audit Event 0.1.0",
        "0.1.0",
    ),
    "run-preflight-report-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:run-preflight-report:0.1.0",
        "Pilot Assessment Run Preflight Report 0.1.0",
        "0.1.0",
    ),
    "run-snapshot-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:run-snapshot:0.1.0",
        "Pilot Assessment Run Snapshot 0.1.0",
        "0.1.0",
    ),
    "assessment-run-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:assessment-run:0.1.0",
        "Pilot Assessment Run 0.1.0",
        "0.1.0",
    ),
    "run-event-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:run-event:0.1.0",
        "Pilot Assessment Run Event 0.1.0",
        "0.1.0",
    ),
    "run-result-envelope-0.1.0.schema.json": (
        "urn:cranfield:pilot-assessment:schema:run-result-envelope:0.1.0",
        "Pilot Assessment Run Result Envelope 0.1.0",
        "0.1.0",
    ),
}

ALL_SCHEMA_NAMES = (
    frozenset(LEGACY_SCHEMA_SHA256)
    | frozenset(M4_SCHEMA_METADATA)
    | frozenset(M5_SCHEMA_METADATA)
    | frozenset(M6_SCHEMA_METADATA)
)
QUALITY_GATE_FIELD_NAMES = {
    "quality",
    "quality_gate",
    "quality_gates",
    "quality_transform",
    "min_valid_coverage",
    "failed_quality",
    "invalid_quality",
    "binary_quality_v1",
}


def _synchronization_fixture() -> dict[str, object]:
    return json.loads((FIXTURES / "synchronization_report_ready.json").read_text(encoding="utf-8"))


def _assert_synchronization_valid(
    candidate: dict[str, object], validator: Draft202012Validator
) -> None:
    SynchronizationReport.model_validate(candidate)
    validator.validate(candidate)


def _assert_synchronization_invalid(
    candidate: dict[str, object], validator: Draft202012Validator
) -> None:
    with pytest.raises(ValidationError):
        SynchronizationReport.model_validate(candidate)
    assert list(validator.iter_errors(candidate))


def _make_core_unaligned(
    candidate: dict[str, object],
    modality: str,
    *,
    status: str,
    readiness: str,
    required: bool,
) -> None:
    stream_results = candidate["stream_results"]
    assert isinstance(stream_results, dict)
    result = stream_results[modality]
    assert isinstance(result, dict)
    result.update(
        declared_status="invalid" if readiness == "invalid" else "missing",
        required_for_import=required,
        input_readiness=readiness,
        synchronization_status=status,
        aligned_schema_id=None,
        artifacts={},
        scene_gaze_metrics=None,
    )


def _make_bundle_reference_unaligned(candidate: dict[str, object], *, required: bool) -> None:
    result = candidate["task_reference_result"]
    assert isinstance(result, dict)
    result.update(
        declared_status="invalid",
        required_for_import=required,
        input_readiness="invalid",
        synchronization_status="invalid",
        aligned_schema_id=None,
        artifacts={},
    )


def _make_annotation_invalid(candidate: dict[str, object]) -> None:
    result = candidate["annotation_result"]
    assert isinstance(result, dict)
    result.update(
        synchronization_status="invalid",
        revision=None,
        phase_schema_id=None,
        event_schema_id=None,
        baseline_schema_id=None,
        phase_count=None,
        event_count=None,
        baseline_count=None,
        unannotated_intervals=[],
        synthetic_semantics_unvalidated=None,
    )


def _model_bundle_reference() -> dict[str, object]:
    return {
        "reference_id": "model-bundle-commanded-path-v0.1",
        "source": "model_bundle",
        "declared_status": None,
        "required_for_import": None,
        "input_readiness": None,
        "synchronization_status": "deferred_model_bundle_resolution",
        "clock": None,
        "source_schema_id": None,
        "aligned_schema_id": None,
        "source_checksums": {},
        "artifacts": {},
        "issues": [],
    }


def _blocking_synchronization_issue() -> dict[str, object]:
    return {
        "error_code": "SYNCHRONIZATION_INPUT_BLOCKED",
        "severity": "fatal",
        "recoverable": False,
        "message": "fixture blocking issue",
        "field_or_path": None,
        "node_or_anchor_id": None,
        "remediation": "repair the fixture",
        "request_id": None,
        "trace_id": None,
        "transaction_id": None,
        "diagnostics": {},
        "extensions": {},
    }


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


def _make_synthetic_manifest(manifest: dict[str, object]) -> None:
    for modality in ("G", "EEG", "ECG", "pilot_camera"):
        _make_present(manifest, modality, f"streams/{modality}.parquet")
    privacy = manifest["privacy"]
    extensions = manifest["extensions"]
    assert isinstance(privacy, dict) and isinstance(extensions, dict)
    privacy.update(
        classification="synthetic-test-data",
        contains_biometric_data=False,
        biometric_modalities_export_pending=[],
        permitted_use="software-testing-only",
    )
    extensions["synthetic"] = {
        "generator_id": "synthetic-multimodal-generator-v0.1",
        "seed": 20260711,
        "scientific_validation_status": "not_supported",
        "source_xu_sha256": "a" * 64,
        "lock_fingerprint": "b" * 64,
        "provenance_scope": "captured-format-sample-xu-plus-synthetic-modalities",
        "formal_assessment_supported": False,
        "duration_s": 2.0,
        "parameters": {"fixture": True},
    }


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
    assert set(first) == ALL_SCHEMA_NAMES
    for payload in first.values():
        schema = json.loads(payload)
        assert schema["$schema"] == SCHEMA_DIALECT
        Draft202012Validator.check_schema(schema)


def test_legacy_schema_bytes_and_hashes_remain_frozen() -> None:
    rendered = render_schemas()

    for name, expected_sha256 in LEGACY_SCHEMA_SHA256.items():
        payload = rendered[name]
        assert hashlib.sha256(payload).hexdigest() == expected_sha256
        assert (PROJECT_ROOT / "schemas" / name).read_bytes() == payload


def test_m4_schema_ids_titles_and_contract_versions_are_frozen() -> None:
    rendered = render_schemas()

    for name, (schema_id, title, contract_version) in M4_SCHEMA_METADATA.items():
        schema = json.loads(rendered[name])
        assert schema["$schema"] == SCHEMA_DIALECT
        assert schema["$id"] == schema_id
        assert schema["title"] == title
        assert schema["x-contract-version"] == contract_version
        assert schema["x-runtime-invariants"]
        Draft202012Validator.check_schema(schema)


def test_m5_schema_ids_titles_and_contract_versions_are_frozen() -> None:
    rendered = render_schemas()

    for name, (schema_id, title, contract_version) in M5_SCHEMA_METADATA.items():
        schema = json.loads(rendered[name])
        assert schema["$schema"] == SCHEMA_DIALECT
        assert schema["$id"] == schema_id
        assert schema["title"] == title
        assert schema["x-contract-version"] == contract_version
        assert schema["x-runtime-invariants"]
        Draft202012Validator.check_schema(schema)


def test_m6_schema_ids_titles_and_contract_versions_are_frozen() -> None:
    rendered = render_schemas()

    for name, (schema_id, title, contract_version) in M6_SCHEMA_METADATA.items():
        schema = json.loads(rendered[name])
        assert schema["$schema"] == SCHEMA_DIALECT
        assert schema["$id"] == schema_id
        assert schema["title"] == title
        assert schema["x-contract-version"] == contract_version
        assert schema["x-runtime-invariants"]
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
        (
            "synchronization-report-0.1.0.schema.json",
            "synchronization_report_ready.json",
        ),
    ]
    for schema_name, fixture_name in pairs:
        schema = json.loads(rendered[schema_name])
        fixture = json.loads((FIXTURES / fixture_name).read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(fixture)


def _measurement_fixture_from_result(result: dict[str, object]) -> dict[str, object]:
    provenance = result["provenance"]
    assert isinstance(provenance, dict)
    return {
        "contract_id": "anchor-measurement",
        "contract_version": "0.1.0",
        "anchor_id": result["anchor_id"],
        "calculation_status": result["calculation_status"],
        "primary_value": result["primary_value"],
        "primary_value_reason": result["primary_value_reason"],
        "raw_metrics": result["raw_metrics"],
        "phase_results": [],
        "event_results": [],
        "classification_override_candidate": result["classification_override"],
        "source_windows": [],
        "derived_artifacts": result["derived_artifacts"],
        "trace": provenance["computation_trace"],
        "diagnostics": [],
    }


def test_m4_public_fixtures_validate_against_published_schemas() -> None:
    rendered = render_schemas()
    pairs = (
        ("anchor-result-0.2.0.schema.json", "anchor_result_v2_computed.json"),
        ("anchor-evaluation-report-0.1.0.schema.json", "anchor_evaluation_report_ready.json"),
    )
    for schema_name, fixture_name in pairs:
        schema = json.loads(rendered[schema_name])
        fixture = json.loads((FIXTURES / fixture_name).read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(fixture)

    result_fixture = json.loads(
        (FIXTURES / "anchor_result_v2_computed.json").read_text(encoding="utf-8")
    )
    measurement = _measurement_fixture_from_result(result_fixture)
    measurement_schema = json.loads(rendered["anchor-measurement-0.1.0.schema.json"])
    Draft202012Validator(measurement_schema).validate(measurement)


def test_m4_schemas_reject_formal_authorization_and_quality_gate_fields() -> None:
    rendered = render_schemas()

    report = json.loads(
        (FIXTURES / "anchor_evaluation_report_ready.json").read_text(encoding="utf-8")
    )
    report["formal_run_authorized"] = True
    report_schema = json.loads(rendered["anchor-evaluation-report-0.1.0.schema.json"])
    assert list(Draft202012Validator(report_schema).iter_errors(report))

    result = json.loads((FIXTURES / "anchor_result_v2_computed.json").read_text(encoding="utf-8"))
    result["calculation_status"] = "invalid_quality"
    result_schema = json.loads(rendered["anchor-result-0.2.0.schema.json"])
    assert list(Draft202012Validator(result_schema).iter_errors(result))

    measurement = _measurement_fixture_from_result(
        json.loads((FIXTURES / "anchor_result_v2_computed.json").read_text(encoding="utf-8"))
    )
    measurement["quality_gate"] = {"passed": False}
    measurement_schema = json.loads(rendered["anchor-measurement-0.1.0.schema.json"])
    assert list(Draft202012Validator(measurement_schema).iter_errors(measurement))

    plan_schema = json.loads(rendered["anchor-execution-plan-0.1.0.schema.json"])
    profile_schema = {
        "$schema": SCHEMA_DIALECT,
        "$defs": plan_schema["$defs"],
        **plan_schema["$defs"]["ResolvedAlgorithmProfile"],
    }
    profile = {
        "profile_id": "filter-profile",
        "profile_version": "0.1.0",
        "parameters": {},
        "parameter_hash": "a" * 64,
        "implementation_digest": "b" * 64,
        "output_schema_id": "filter-output-v0.1",
    }
    validator = Draft202012Validator(profile_schema)
    validator.validate(profile)
    for field_name in QUALITY_GATE_FIELD_NAMES:
        for parameters in ({field_name: 1}, {"nested": {field_name: 1}}):
            candidate = copy.deepcopy(profile)
            candidate["parameters"] = parameters
            assert list(validator.iter_errors(candidate)), (field_name, parameters)


def test_exported_root_and_package_schemas_are_byte_symmetric(tmp_path: Path) -> None:
    root_output = tmp_path / "schemas"
    package_output = tmp_path / "schema_resources"
    written = export_schemas(root_output, package_output)
    rendered = render_schemas()

    assert len(written) == 2 * len(rendered)
    assert {path.name for path in written} == set(rendered)
    for name, payload in rendered.items():
        assert (root_output / name).read_bytes() == payload
        assert (package_output / name).read_bytes() == payload
        assert (PROJECT_ROOT / "schemas" / name).read_bytes() == payload
        assert (
            PROJECT_ROOT / "src" / "pilot_assessment" / "schema_resources" / name
        ).read_bytes() == payload

    first_bytes = {path: path.read_bytes() for path in written}
    assert export_schemas(root_output, package_output) == written
    assert {path: path.read_bytes() for path in written} == first_bytes


def test_export_schemas_preserves_the_legacy_single_target_api(tmp_path: Path) -> None:
    output = tmp_path / "legacy-single-target"
    written = export_schemas(output)

    assert len(written) == len(render_schemas())
    assert {path.parent for path in written} == {output}


def test_export_rejects_two_names_for_the_same_target_before_writing(tmp_path: Path) -> None:
    target = tmp_path / "same-target"
    alias = target / ".." / target.name

    with pytest.raises(ValueError, match="targets must be distinct"):
        export_schemas(target, alias)

    assert not target.exists()


@pytest.mark.parametrize("failure_type", [OSError, KeyboardInterrupt])
def test_dual_target_export_rolls_back_every_destination_after_publish_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_type: type[BaseException],
) -> None:
    root_output = tmp_path / "schemas"
    package_output = tmp_path / "schema_resources"
    original = render_schemas()
    export_schemas(root_output, package_output)
    original_bytes = {
        path: path.read_bytes()
        for output in (root_output, package_output)
        for path in output.glob("*.schema.json")
    }

    module = importlib.import_module("pilot_assessment.schemas.export")
    changed = {name: payload + b" " for name, payload in original.items()}
    monkeypatch.setattr(module, "render_schemas", lambda: changed)
    real_replace = Path.replace
    replacement_count = 0

    def fail_once_during_publish(source: Path, target: Path) -> Path:
        nonlocal replacement_count
        replacement_count += 1
        if replacement_count == len(original) + 2:
            raise failure_type("injected publish failure")
        return real_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_once_during_publish)
    with pytest.raises(failure_type):
        export_schemas(root_output, package_output)

    assert {path: path.read_bytes() for path in original_bytes} == original_bytes
    assert not tuple(tmp_path.rglob("*.tmp"))


def test_export_cleans_the_current_temporary_file_after_stage_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "schemas"
    real_write_bytes = Path.write_bytes
    write_count = 0

    def fail_once_during_stage(path: Path, payload: bytes) -> int:
        nonlocal write_count
        write_count += 1
        if write_count == 2:
            real_write_bytes(path, payload[: max(1, len(payload) // 2)])
            raise OSError("injected stage failure")
        return real_write_bytes(path, payload)

    monkeypatch.setattr(Path, "write_bytes", fail_once_during_stage)
    with pytest.raises(OSError, match="injected stage failure"):
        export_schemas(output)

    assert not tuple(tmp_path.rglob("*.tmp"))


def test_synchronization_report_schema_matches_checked_in_artifact() -> None:
    rendered = render_schemas()["synchronization-report-0.1.0.schema.json"]
    checked_in = PROJECT_ROOT / "schemas" / "synchronization-report-0.1.0.schema.json"
    assert rendered == checked_in.read_bytes()


def test_schema_and_pydantic_agree_on_exact_core_inventory() -> None:
    schema = json.loads(render_schemas()["synchronization-report-0.1.0.schema.json"])
    validator = Draft202012Validator(schema)
    valid = _synchronization_fixture()
    _assert_synchronization_valid(valid, validator)

    missing = copy.deepcopy(valid)
    stream_results = missing["stream_results"]
    assert isinstance(stream_results, dict)
    del stream_results["ECG"]

    extra = copy.deepcopy(valid)
    stream_results = extra["stream_results"]
    assert isinstance(stream_results, dict)
    extra_result = copy.deepcopy(stream_results["I"])
    assert isinstance(extra_result, dict)
    extra_result["modality"] = "THERMAL"
    stream_results["THERMAL"] = extra_result

    wrong_owner = copy.deepcopy(valid)
    stream_results = wrong_owner["stream_results"]
    assert isinstance(stream_results, dict)
    x_result = stream_results["X"]
    assert isinstance(x_result, dict)
    x_result["modality"] = "U"

    deferred = copy.deepcopy(valid)
    _make_core_unaligned(
        deferred,
        "I",
        status="deferred_model_bundle_resolution",
        readiness="unavailable",
        required=False,
    )
    deferred["disposition"] = "ready_partial"

    for candidate in (missing, extra, wrong_owner, deferred):
        _assert_synchronization_invalid(candidate, validator)


def test_schema_and_pydantic_agree_on_aligned_payload_invariants() -> None:
    schema = json.loads(render_schemas()["synchronization-report-0.1.0.schema.json"])
    validator = Draft202012Validator(schema)
    valid = _synchronization_fixture()
    _assert_synchronization_valid(valid, validator)

    aligned_missing = copy.deepcopy(valid)
    stream_results = aligned_missing["stream_results"]
    assert isinstance(stream_results, dict)
    x_result = stream_results["X"]
    assert isinstance(x_result, dict)
    x_result["declared_status"] = "missing"

    aligned_without_artifacts = copy.deepcopy(valid)
    stream_results = aligned_without_artifacts["stream_results"]
    assert isinstance(stream_results, dict)
    x_result = stream_results["X"]
    assert isinstance(x_result, dict)
    x_result["artifacts"] = {}

    gaze_without_relationship = copy.deepcopy(valid)
    stream_results = gaze_without_relationship["stream_results"]
    assert isinstance(stream_results, dict)
    gaze_result = stream_results["G"]
    assert isinstance(gaze_result, dict)
    gaze_result["scene_gaze_metrics"] = None

    non_aligned_claims_output = copy.deepcopy(valid)
    stream_results = non_aligned_claims_output["stream_results"]
    assert isinstance(stream_results, dict)
    scene_result = stream_results["I"]
    assert isinstance(scene_result, dict)
    scene_result.update(
        declared_status="invalid",
        input_readiness="invalid",
        synchronization_status="invalid",
    )
    non_aligned_claims_output["disposition"] = "ready_partial"

    non_gaze_relationship = copy.deepcopy(valid)
    _make_core_unaligned(
        non_gaze_relationship,
        "I",
        status="invalid",
        readiness="invalid",
        required=False,
    )
    stream_results = non_gaze_relationship["stream_results"]
    assert isinstance(stream_results, dict)
    scene_result = stream_results["I"]
    gaze_result = stream_results["G"]
    assert isinstance(scene_result, dict)
    assert isinstance(gaze_result, dict)
    scene_result["scene_gaze_metrics"] = copy.deepcopy(gaze_result["scene_gaze_metrics"])
    non_gaze_relationship["disposition"] = "ready_partial"

    point_interpolation_boolean = copy.deepcopy(valid)
    stream_results = point_interpolation_boolean["stream_results"]
    assert isinstance(stream_results, dict)
    x_result = stream_results["X"]
    assert isinstance(x_result, dict)
    x_artifacts = x_result["artifacts"]
    assert isinstance(x_artifacts, dict)
    x_samples = x_artifacts["samples"]
    assert isinstance(x_samples, dict)
    x_samples["interpolated_rows"] = False

    interval_interpolation_boolean = copy.deepcopy(valid)
    stream_results = interval_interpolation_boolean["stream_results"]
    assert isinstance(stream_results, dict)
    gaze_result = stream_results["G"]
    assert isinstance(gaze_result, dict)
    gaze_artifacts = gaze_result["artifacts"]
    assert isinstance(gaze_artifacts, dict)
    fixations = gaze_artifacts["fixations"]
    assert isinstance(fixations, dict)
    fixations["interpolated_rows"] = False

    for candidate in (
        aligned_missing,
        aligned_without_artifacts,
        gaze_without_relationship,
        non_aligned_claims_output,
        non_gaze_relationship,
        point_interpolation_boolean,
        interval_interpolation_boolean,
    ):
        _assert_synchronization_invalid(candidate, validator)

    invalid_gaze_with_diagnostics = copy.deepcopy(valid)
    stream_results = invalid_gaze_with_diagnostics["stream_results"]
    assert isinstance(stream_results, dict)
    gaze_result = stream_results["G"]
    assert isinstance(gaze_result, dict)
    retained_metrics = gaze_result["scene_gaze_metrics"]
    _make_core_unaligned(
        invalid_gaze_with_diagnostics,
        "G",
        status="invalid",
        readiness="invalid",
        required=False,
    )
    gaze_result = stream_results["G"]
    assert isinstance(gaze_result, dict)
    gaze_result["scene_gaze_metrics"] = retained_metrics
    invalid_gaze_with_diagnostics["disposition"] = "ready_partial"
    _assert_synchronization_valid(invalid_gaze_with_diagnostics, validator)


def test_schema_and_pydantic_agree_on_synthetic_provenance_coupling() -> None:
    schema = json.loads(render_schemas()["synchronization-report-0.1.0.schema.json"])
    validator = Draft202012Validator(schema)
    valid = _synchronization_fixture()
    _assert_synchronization_valid(valid, validator)

    real_source = copy.deepcopy(valid)
    real_source["source_classification"] = "restricted-research-pseudonymous"
    real_source["synthetic_provenance"] = None
    _assert_synchronization_valid(real_source, validator)

    synthetic_without_provenance = copy.deepcopy(valid)
    synthetic_without_provenance["synthetic_provenance"] = None
    _assert_synchronization_invalid(synthetic_without_provenance, validator)

    real_with_provenance = copy.deepcopy(valid)
    real_with_provenance["source_classification"] = "restricted-research-pseudonymous"
    _assert_synchronization_invalid(real_with_provenance, validator)


def test_schema_and_pydantic_agree_on_window_and_continuation() -> None:
    schema = json.loads(render_schemas()["synchronization-report-0.1.0.schema.json"])
    validator = Draft202012Validator(schema)
    valid = _synchronization_fixture()
    _assert_synchronization_valid(valid, validator)

    blocked = copy.deepcopy(valid)
    _make_annotation_invalid(blocked)
    blocked.update(
        session_window=None,
        disposition="blocked",
        can_continue_to_anchor_availability=False,
    )
    _assert_synchronization_valid(blocked, validator)

    ready_without_window = copy.deepcopy(valid)
    ready_without_window["session_window"] = None

    boolean_window_start = copy.deepcopy(valid)
    session_window = boolean_window_start["session_window"]
    assert isinstance(session_window, dict)
    session_window["start_t_ns"] = False

    zero_window_end = copy.deepcopy(valid)
    session_window = zero_window_end["session_window"]
    assert isinstance(session_window, dict)
    session_window["end_t_ns"] = 0

    maximum_window_end = copy.deepcopy(valid)
    session_window = maximum_window_end["session_window"]
    assert isinstance(session_window, dict)
    session_window["end_t_ns"] = MAX_SESSION_END_NS_V0_1
    _assert_synchronization_valid(maximum_window_end, validator)

    oversized_window_end = copy.deepcopy(valid)
    session_window = oversized_window_end["session_window"]
    assert isinstance(session_window, dict)
    session_window["end_t_ns"] = MAX_SESSION_END_NS_V0_1 + 1

    boolean_window_end = copy.deepcopy(valid)
    session_window = boolean_window_end["session_window"]
    assert isinstance(session_window, dict)
    session_window["end_t_ns"] = True

    blocked_but_continuing = copy.deepcopy(blocked)
    blocked_but_continuing["can_continue_to_anchor_availability"] = True

    ready_but_stopped = copy.deepcopy(valid)
    ready_but_stopped["can_continue_to_anchor_availability"] = False

    formal_authorization = copy.deepcopy(valid)
    formal_authorization["formal_run_authorized"] = True

    integer_formal_authorization = copy.deepcopy(valid)
    integer_formal_authorization["formal_run_authorized"] = 0

    for candidate in (
        ready_without_window,
        boolean_window_start,
        zero_window_end,
        oversized_window_end,
        boolean_window_end,
        blocked_but_continuing,
        ready_but_stopped,
        formal_authorization,
        integer_formal_authorization,
    ):
        _assert_synchronization_invalid(candidate, validator)


def test_schema_and_pydantic_agree_on_reference_annotation_disposition() -> None:
    schema = json.loads(render_schemas()["synchronization-report-0.1.0.schema.json"])
    validator = Draft202012Validator(schema)
    valid = _synchronization_fixture()
    _assert_synchronization_valid(valid, validator)

    ready_annotation_invalid = copy.deepcopy(valid)
    _make_annotation_invalid(ready_annotation_invalid)
    _assert_synchronization_invalid(ready_annotation_invalid, validator)
    ready_annotation_invalid.update(
        disposition="blocked",
        can_continue_to_anchor_availability=False,
    )
    _assert_synchronization_valid(ready_annotation_invalid, validator)

    ready_required_reference_invalid = copy.deepcopy(valid)
    _make_bundle_reference_unaligned(ready_required_reference_invalid, required=True)
    _assert_synchronization_invalid(ready_required_reference_invalid, validator)
    ready_required_reference_invalid.update(
        disposition="blocked",
        can_continue_to_anchor_availability=False,
    )
    _assert_synchronization_valid(ready_required_reference_invalid, validator)

    ready_model_reference_deferred = copy.deepcopy(valid)
    ready_model_reference_deferred["task_reference_result"] = _model_bundle_reference()
    _assert_synchronization_valid(ready_model_reference_deferred, validator)

    partial_optional_reference_invalid = copy.deepcopy(valid)
    _make_bundle_reference_unaligned(partial_optional_reference_invalid, required=False)
    partial_optional_reference_invalid["disposition"] = "ready_partial"
    _assert_synchronization_valid(partial_optional_reference_invalid, validator)

    ready_blocking_global_error = copy.deepcopy(valid)
    ready_blocking_global_error["global_issues"] = [_blocking_synchronization_issue()]
    _assert_synchronization_invalid(ready_blocking_global_error, validator)
    ready_blocking_global_error.update(
        disposition="blocked",
        can_continue_to_anchor_availability=False,
    )
    _assert_synchronization_valid(ready_blocking_global_error, validator)

    partial_optional_core_invalid = copy.deepcopy(valid)
    _make_core_unaligned(
        partial_optional_core_invalid,
        "I",
        status="invalid",
        readiness="invalid",
        required=False,
    )
    partial_optional_core_invalid["disposition"] = "ready_partial"
    _assert_synchronization_valid(partial_optional_core_invalid, validator)

    blocked_required_core_invalid = copy.deepcopy(valid)
    _make_core_unaligned(
        blocked_required_core_invalid,
        "X",
        status="invalid",
        readiness="invalid",
        required=True,
    )
    blocked_required_core_invalid.update(
        disposition="blocked",
        can_continue_to_anchor_availability=False,
    )
    _assert_synchronization_valid(blocked_required_core_invalid, validator)


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
    _make_synthetic_manifest(candidate)

    SessionManifest.model_validate(candidate)
    Draft202012Validator(schema).validate(candidate)


def test_session_schema_requires_complete_synthetic_provenance() -> None:
    schema = json.loads(render_schemas()["session-manifest-0.1.0.schema.json"])
    validator = Draft202012Validator(schema)
    valid = json.loads((FIXTURES / "session_manifest_valid.json").read_text(encoding="utf-8"))
    _make_synthetic_manifest(valid)

    invalid_cases: list[tuple[str, dict[str, object]]] = []
    missing_object = copy.deepcopy(valid)
    del missing_object["extensions"]["synthetic"]
    invalid_cases.append(("missing synthetic object", missing_object))

    scalar_object = copy.deepcopy(valid)
    scalar_object["extensions"]["synthetic"] = "not-an-object"
    invalid_cases.append(("scalar synthetic object", scalar_object))

    for field_name in (
        "generator_id",
        "seed",
        "scientific_validation_status",
        "source_xu_sha256",
        "lock_fingerprint",
        "provenance_scope",
        "formal_assessment_supported",
    ):
        missing_field = copy.deepcopy(valid)
        del missing_field["extensions"]["synthetic"][field_name]
        invalid_cases.append((f"missing {field_name}", missing_field))

    for label, invalid_value in (
        ("integer zero", 0),
        ("float zero", 0.0),
        ("boolean true", True),
        ("string false", "false"),
    ):
        invalid_formal_support = copy.deepcopy(valid)
        invalid_formal_support["extensions"]["synthetic"]["formal_assessment_supported"] = (
            invalid_value
        )
        invalid_cases.append((f"formal assessment support {label}", invalid_formal_support))

    for label, candidate in invalid_cases:
        with pytest.raises(ValidationError):
            SessionManifest.model_validate(candidate)
        assert list(validator.iter_errors(candidate)), f"JSON Schema accepted {label}"


def test_session_schema_leaves_non_synthetic_extensions_backward_compatible() -> None:
    schema = json.loads(render_schemas()["session-manifest-0.1.0.schema.json"])
    candidate = json.loads((FIXTURES / "session_manifest_valid.json").read_text(encoding="utf-8"))
    candidate["extensions"]["synthetic"] = "legacy-non-authoritative-note"

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
