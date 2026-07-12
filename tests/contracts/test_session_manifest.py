from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from pilot_assessment.contracts.session import (
    CORE_MODALITIES,
    SessionManifest,
    StreamStatus,
)

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "session_manifest_valid.json"


@pytest.fixture
def manifest_data() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _make_present(
    manifest_data: dict[str, Any],
    modality: str,
    path: str,
) -> None:
    stream = manifest_data["streams"][modality]
    stream.update(
        status="present",
        required_for_import=False,
        paths=[path],
        clock_sync=copy.deepcopy(manifest_data["streams"]["X"]["clock_sync"]),
        quality_summary=None,
        checksums={path: "c" * 64},
    )


def _task_reference_descriptor(manifest_data: dict[str, Any]) -> dict[str, Any]:
    descriptor = copy.deepcopy(manifest_data["streams"]["X"])
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


def _synthetic_provenance() -> dict[str, Any]:
    return {
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


def _make_synthetic(manifest_data: dict[str, Any]) -> None:
    for modality in ("G", "EEG", "ECG", "pilot_camera"):
        _make_present(manifest_data, modality, f"streams/{modality}.parquet")
    manifest_data["privacy"].update(
        classification="synthetic-test-data",
        contains_biometric_data=False,
        biometric_modalities_export_pending=[],
        permitted_use="software-testing-only",
    )
    manifest_data["extensions"]["synthetic"] = _synthetic_provenance()


def test_valid_manifest_round_trips_and_preserves_export_pending(
    manifest_data: dict[str, Any],
) -> None:
    manifest = SessionManifest.model_validate(manifest_data)

    assert set(CORE_MODALITIES).issubset(manifest.streams)
    assert manifest.streams["I"].status is StreamStatus.EXPORT_PENDING
    assert manifest.extensions == {"lab_note": "contract-fixture"}
    assert manifest.model_dump(mode="json")["streams"]["I"]["status"] == "export_pending"


def test_model_bundle_reference_remains_backward_compatible(
    manifest_data: dict[str, Any],
) -> None:
    manifest = SessionManifest.model_validate(manifest_data)

    assert manifest.task.reference is not None
    assert manifest.task.reference.source == "model_bundle"
    assert manifest.task.reference.stream_id is None


def test_bundle_reference_resolves_task_reference_stream(
    manifest_data: dict[str, Any],
) -> None:
    manifest_data["task"]["reference"] = {
        "source": "bundle",
        "reference_id": "commanded-path-v0.1",
        "stream_id": "task_reference",
    }
    manifest_data["streams"]["task_reference"] = _task_reference_descriptor(manifest_data)

    manifest = SessionManifest.model_validate(manifest_data)

    assert manifest.task.reference is not None
    assert manifest.task.reference.stream_id == "task_reference"
    assert manifest.streams["task_reference"].paths == ["references/commanded_path.parquet"]


@pytest.mark.parametrize(
    "reference",
    [
        {"source": "bundle", "reference_id": "commanded-path-v0.1"},
        {
            "source": "model_bundle",
            "reference_id": "commanded-path-v0.1",
            "stream_id": "task_reference",
        },
        {"source": "external", "reference_id": "commanded-path-v0.1"},
    ],
)
def test_task_reference_source_controls_stream_id(
    manifest_data: dict[str, Any], reference: dict[str, str]
) -> None:
    manifest_data["task"]["reference"] = reference

    with pytest.raises(ValidationError):
        SessionManifest.model_validate(manifest_data)


def test_bundle_reference_must_resolve_existing_task_reference_stream(
    manifest_data: dict[str, Any],
) -> None:
    manifest_data["task"]["reference"] = {
        "source": "bundle",
        "reference_id": "commanded-path-v0.1",
        "stream_id": "task_reference",
    }

    with pytest.raises(ValidationError):
        SessionManifest.model_validate(manifest_data)


def test_bundle_reference_artifacts_must_stay_below_references(
    manifest_data: dict[str, Any],
) -> None:
    descriptor = _task_reference_descriptor(manifest_data)
    descriptor["paths"] = ["streams/commanded_path.parquet"]
    descriptor["checksums"] = {"streams/commanded_path.parquet": "d" * 64}
    manifest_data["streams"]["task_reference"] = descriptor
    manifest_data["task"]["reference"] = {
        "source": "bundle",
        "reference_id": "commanded-path-v0.1",
        "stream_id": "task_reference",
    }

    with pytest.raises(ValidationError):
        SessionManifest.model_validate(manifest_data)


def test_unreferenced_task_reference_descriptor_is_rejected(
    manifest_data: dict[str, Any],
) -> None:
    manifest_data["streams"]["task_reference"] = _task_reference_descriptor(manifest_data)

    with pytest.raises(ValidationError):
        SessionManifest.model_validate(manifest_data)


@pytest.mark.parametrize("status", ["export_pending", "missing", "not_applicable"])
def test_bundle_reference_can_preserve_fileless_status(
    manifest_data: dict[str, Any], status: str
) -> None:
    descriptor = _task_reference_descriptor(manifest_data)
    descriptor.update(
        status=status,
        required_for_import=False,
        paths=[],
        clock_sync=None,
        quality_summary=None,
        checksums={},
    )
    manifest_data["streams"]["task_reference"] = descriptor
    manifest_data["task"]["reference"] = {
        "source": "bundle",
        "reference_id": "commanded-path-v0.1",
        "stream_id": "task_reference",
    }

    manifest = SessionManifest.model_validate(manifest_data)

    assert manifest.streams["task_reference"].status.value == status


@pytest.mark.parametrize("field", ["session_id", "task", "streams", "privacy"])
def test_required_top_level_fields_cannot_be_omitted(
    manifest_data: dict[str, Any], field: str
) -> None:
    del manifest_data[field]
    with pytest.raises(ValidationError):
        SessionManifest.model_validate(manifest_data)


def test_unknown_top_level_fields_must_be_inside_extensions(
    manifest_data: dict[str, Any],
) -> None:
    manifest_data["future_field"] = "not-namespaced"
    with pytest.raises(ValidationError):
        SessionManifest.model_validate(manifest_data)


@pytest.mark.parametrize("version", ["0.1", "v0.1.0", "1.0.0", "not-a-version"])
def test_schema_version_must_be_supported_semver(
    manifest_data: dict[str, Any], version: str
) -> None:
    manifest_data["bundle_schema_version"] = version
    with pytest.raises(ValidationError):
        SessionManifest.model_validate(manifest_data)


def test_created_at_requires_timezone(manifest_data: dict[str, Any]) -> None:
    manifest_data["created_at"] = "2026-07-10T14:00:00"
    with pytest.raises(ValidationError):
        SessionManifest.model_validate(manifest_data)


@pytest.mark.parametrize("modality", sorted(CORE_MODALITIES))
def test_every_core_stream_descriptor_is_required(
    manifest_data: dict[str, Any], modality: str
) -> None:
    del manifest_data["streams"][modality]
    with pytest.raises(ValidationError):
        SessionManifest.model_validate(manifest_data)


def test_p_is_a_concept_group_not_a_stream_key(manifest_data: dict[str, Any]) -> None:
    manifest_data["streams"]["P"] = copy.deepcopy(manifest_data["streams"]["I"])
    manifest_data["streams"]["P"]["modality"] = "P"
    with pytest.raises(ValidationError):
        SessionManifest.model_validate(manifest_data)


def test_same_major_optional_stream_is_preserved(manifest_data: dict[str, Any]) -> None:
    manifest_data["bundle_schema_version"] = "0.2.0"
    manifest_data["streams"]["THERMAL"] = copy.deepcopy(manifest_data["streams"]["I"])
    manifest_data["streams"]["THERMAL"]["modality"] = "THERMAL"

    manifest = SessionManifest.model_validate(manifest_data)

    assert manifest.streams["THERMAL"].modality == "THERMAL"
    assert "THERMAL" in manifest.model_dump(mode="json")["streams"]


def test_stream_key_must_match_descriptor_modality(manifest_data: dict[str, Any]) -> None:
    manifest_data["streams"]["X"]["modality"] = "U"
    with pytest.raises(ValidationError):
        SessionManifest.model_validate(manifest_data)


def test_present_stream_requires_paths_and_matching_checksums(
    manifest_data: dict[str, Any],
) -> None:
    without_path = copy.deepcopy(manifest_data)
    without_path["streams"]["X"]["paths"] = []
    without_path["streams"]["X"]["checksums"] = {}
    with pytest.raises(ValidationError):
        SessionManifest.model_validate(without_path)

    without_checksum = copy.deepcopy(manifest_data)
    without_checksum["streams"]["X"]["checksums"] = {}
    with pytest.raises(ValidationError):
        SessionManifest.model_validate(without_checksum)


def test_export_pending_requires_empty_paths_and_checksums(
    manifest_data: dict[str, Any],
) -> None:
    manifest_data["streams"]["I"]["paths"] = ["streams/scene.mp4"]
    manifest_data["streams"]["I"]["checksums"] = {"streams/scene.mp4": "c" * 64}
    with pytest.raises(ValidationError):
        SessionManifest.model_validate(manifest_data)


def test_invalid_stream_requires_paths_and_matching_checksums(
    manifest_data: dict[str, Any],
) -> None:
    valid_invalid = copy.deepcopy(manifest_data)
    valid_invalid["streams"]["X"].update(
        status="invalid",
        clock_sync=None,
        quality_summary=None,
    )
    manifest = SessionManifest.model_validate(valid_invalid)
    assert manifest.streams["X"].status is StreamStatus.INVALID

    without_files = copy.deepcopy(manifest_data)
    without_files["streams"]["X"].update(
        status="invalid",
        paths=[],
        clock_sync=None,
        quality_summary=None,
        checksums={},
    )
    with pytest.raises(ValidationError):
        SessionManifest.model_validate(without_files)


@pytest.mark.parametrize("status", ["export_pending", "missing", "not_applicable"])
def test_fileless_stream_statuses_reject_paths_and_checksums(
    manifest_data: dict[str, Any], status: str
) -> None:
    stream = manifest_data["streams"]["I"]
    stream.update(
        status=status,
        required_for_import=False,
        paths=["streams/scene.mp4"],
        clock_sync=None,
        quality_summary=None,
        checksums={"streams/scene.mp4": "c" * 64},
    )

    with pytest.raises(ValidationError):
        SessionManifest.model_validate(manifest_data)


@pytest.mark.parametrize("status", ["export_pending", "missing", "not_applicable"])
def test_fileless_stream_statuses_reject_quality_summary(
    manifest_data: dict[str, Any], status: str
) -> None:
    stream = manifest_data["streams"]["I"]
    stream.update(
        status=status,
        required_for_import=False,
        paths=[],
        clock_sync=None,
        quality_summary={"coverage_ratio": 0.5},
        checksums={},
    )

    with pytest.raises(ValidationError):
        SessionManifest.model_validate(manifest_data)


@pytest.mark.parametrize("status", ["missing", "not_applicable"])
def test_missing_and_not_applicable_reject_clock_sync(
    manifest_data: dict[str, Any], status: str
) -> None:
    stream = manifest_data["streams"]["I"]
    stream.update(
        status=status,
        required_for_import=False,
        paths=[],
        clock_sync=copy.deepcopy(manifest_data["streams"]["X"]["clock_sync"]),
        quality_summary=None,
        checksums={},
    )

    with pytest.raises(ValidationError):
        SessionManifest.model_validate(manifest_data)


def test_not_applicable_cannot_be_required_for_import(
    manifest_data: dict[str, Any],
) -> None:
    manifest_data["streams"]["I"].update(
        status="not_applicable",
        required_for_import=True,
        paths=[],
        clock_sync=None,
        quality_summary=None,
        checksums={},
    )

    with pytest.raises(ValidationError):
        SessionManifest.model_validate(manifest_data)


def test_pending_biometric_modalities_are_unique_and_match_stream_status(
    manifest_data: dict[str, Any],
) -> None:
    duplicate = copy.deepcopy(manifest_data)
    duplicate["privacy"]["biometric_modalities_export_pending"].append("EEG")
    with pytest.raises(ValidationError):
        SessionManifest.model_validate(duplicate)

    incomplete = copy.deepcopy(manifest_data)
    incomplete["privacy"]["biometric_modalities_export_pending"].remove("EEG")
    with pytest.raises(ValidationError):
        SessionManifest.model_validate(incomplete)


@pytest.mark.parametrize("status", ["present", "invalid"])
def test_non_synthetic_real_biometrics_require_privacy_flag(
    manifest_data: dict[str, Any], status: str
) -> None:
    _make_present(manifest_data, "EEG", "streams/eeg.parquet")
    manifest_data["streams"]["EEG"]["status"] = status
    if status == "invalid":
        manifest_data["streams"]["EEG"]["clock_sync"] = None
    manifest_data["privacy"]["biometric_modalities_export_pending"].remove("EEG")

    with pytest.raises(ValidationError):
        SessionManifest.model_validate(manifest_data)

    manifest_data["privacy"]["contains_biometric_data"] = True
    manifest = SessionManifest.model_validate(manifest_data)
    assert manifest.privacy.contains_biometric_data is True


def test_synthetic_present_biometrics_are_not_real_biometric_data(
    manifest_data: dict[str, Any],
) -> None:
    _make_synthetic(manifest_data)

    manifest = SessionManifest.model_validate(manifest_data)

    assert manifest.privacy.contains_biometric_data is False


@pytest.mark.parametrize(
    "invalid_value",
    [None, "not-an-object", []],
)
def test_synthetic_manifest_requires_provenance_object(
    manifest_data: dict[str, Any], invalid_value: object
) -> None:
    _make_synthetic(manifest_data)
    manifest_data["extensions"]["synthetic"] = invalid_value

    with pytest.raises(ValidationError, match="synthetic provenance"):
        SessionManifest.model_validate(manifest_data)


@pytest.mark.parametrize(
    "field_name",
    [
        "generator_id",
        "seed",
        "scientific_validation_status",
        "source_xu_sha256",
        "lock_fingerprint",
        "provenance_scope",
        "formal_assessment_supported",
    ],
)
def test_synthetic_manifest_requires_complete_provenance_fields(
    manifest_data: dict[str, Any], field_name: str
) -> None:
    _make_synthetic(manifest_data)
    del manifest_data["extensions"]["synthetic"][field_name]

    with pytest.raises(ValidationError, match="synthetic provenance"):
        SessionManifest.model_validate(manifest_data)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("generator_id", ""),
        ("seed", -1),
        ("scientific_validation_status", "expert_reviewed"),
        ("source_xu_sha256", "not-a-sha256"),
        ("lock_fingerprint", "not-a-sha256"),
        ("provenance_scope", ""),
        ("formal_assessment_supported", 0),
        ("formal_assessment_supported", 0.0),
        ("formal_assessment_supported", True),
        ("formal_assessment_supported", "false"),
    ],
)
def test_synthetic_manifest_rejects_invalid_provenance_fields(
    manifest_data: dict[str, Any], field_name: str, invalid_value: object
) -> None:
    _make_synthetic(manifest_data)
    manifest_data["extensions"]["synthetic"][field_name] = invalid_value

    with pytest.raises(ValidationError, match="synthetic provenance"):
        SessionManifest.model_validate(manifest_data)


def test_non_synthetic_manifest_does_not_interpret_synthetic_extension(
    manifest_data: dict[str, Any],
) -> None:
    manifest_data["extensions"]["synthetic"] = "legacy-non-authoritative-note"

    manifest = SessionManifest.model_validate(manifest_data)

    assert manifest.privacy.classification != "synthetic-test-data"


@pytest.mark.parametrize("sample_rate", [0, -1, math.inf, math.nan])
def test_sample_rate_is_null_or_positive_and_finite(
    manifest_data: dict[str, Any], sample_rate: float
) -> None:
    manifest_data["streams"]["X"]["sample_rate_hz"] = sample_rate
    with pytest.raises(ValidationError):
        SessionManifest.model_validate(manifest_data)


def test_clock_values_and_quality_are_finite_and_bounded(
    manifest_data: dict[str, Any],
) -> None:
    nonfinite = copy.deepcopy(manifest_data)
    nonfinite["streams"]["X"]["clock_sync"]["drift_ppm"] = math.inf
    with pytest.raises(ValidationError):
        SessionManifest.model_validate(nonfinite)

    out_of_range = copy.deepcopy(manifest_data)
    out_of_range["streams"]["X"]["quality_summary"]["coverage_ratio"] = 1.01
    with pytest.raises(ValidationError):
        SessionManifest.model_validate(out_of_range)


def test_annotation_paths_use_secure_relative_path_contract(
    manifest_data: dict[str, Any],
) -> None:
    manifest_data["annotations"]["phases"] = "../outside.json"
    with pytest.raises(ValidationError):
        SessionManifest.model_validate(manifest_data)


def test_participant_rejects_direct_identifier_fields(manifest_data: dict[str, Any]) -> None:
    manifest_data["participant"]["full_name"] = "Direct Identifier"
    with pytest.raises(ValidationError):
        SessionManifest.model_validate(manifest_data)


@pytest.mark.parametrize(
    ("field_path", "value"),
    [
        (("created_at",), 1_720_620_000),
        (("streams", "X", "required_for_import"), "false"),
        (("streams", "X", "clock_sync", "offset_ns"), "0"),
        (("streams", "X", "sample_rate_hz"), "100.0"),
        (("streams", "X", "quality_summary", "coverage_ratio"), "1.0"),
    ],
)
def test_json_scalar_types_are_not_silently_coerced(
    manifest_data: dict[str, Any], field_path: tuple[str, ...], value: object
) -> None:
    target: dict[str, Any] = manifest_data
    for key in field_path[:-1]:
        target = target[key]
    target[field_path[-1]] = value

    with pytest.raises(ValidationError):
        SessionManifest.model_validate(manifest_data)


@pytest.mark.parametrize("offset_ns", [-(2**63) - 1, 2**63])
def test_clock_offset_is_signed_int64(manifest_data: dict[str, Any], offset_ns: int) -> None:
    manifest_data["streams"]["X"]["clock_sync"]["offset_ns"] = offset_ns
    with pytest.raises(ValidationError):
        SessionManifest.model_validate(manifest_data)
