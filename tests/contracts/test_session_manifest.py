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


def test_valid_manifest_round_trips_and_preserves_export_pending(
    manifest_data: dict[str, Any],
) -> None:
    manifest = SessionManifest.model_validate(manifest_data)

    assert set(CORE_MODALITIES).issubset(manifest.streams)
    assert manifest.streams["I"].status is StreamStatus.EXPORT_PENDING
    assert manifest.extensions == {"lab_note": "contract-fixture"}
    assert manifest.model_dump(mode="json")["streams"]["I"]["status"] == "export_pending"


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
