from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from pilot_assessment.contracts import (
    CORE_MODALITIES,
    IngestionReadinessReport,
    ReadinessDisposition,
    StreamReadiness,
)

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "ingestion_readiness_ready.json"


@pytest.fixture
def readiness_data() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _make_unavailable_optional(candidate: dict[str, Any], modality: str = "I") -> None:
    result = candidate["stream_results"][modality]
    result.update(
        {
            "declared_status": "export_pending",
            "required_for_import": False,
            "readiness": "unavailable",
            "adapter_id": None,
            "adapter_version": None,
            "source_paths": [],
            "source_checksums": {},
            "normalized_schema_id": None,
            "row_count": None,
            "artifact_row_counts": {},
            "source_time_start_s": None,
            "source_time_end_s": None,
            "observed_sample_rate_hz": None,
            "canonical_fields": [],
            "units": {},
            "quality_summary": {},
            "assumptions": [],
            "issues": [],
        }
    )


def test_ready_fixture_round_trips_with_all_core_modalities_and_reference(
    readiness_data: dict[str, Any],
) -> None:
    report = IngestionReadinessReport.model_validate(readiness_data)

    assert report.disposition is ReadinessDisposition.READY
    assert report.can_continue_to_synchronization is True
    assert report.formal_run_authorized is False
    assert set(report.stream_results) == set(CORE_MODALITIES)
    assert report.task_reference_result is not None
    assert report.task_reference_result.modality == "task_reference"
    assert report.stream_results["I"].artifact_row_counts == {
        "frame_index": 871,
        "aoi_instances": 1742,
    }
    assert report.model_dump(mode="json") == readiness_data


def test_formal_run_authorized_cannot_be_true(readiness_data: dict[str, Any]) -> None:
    readiness_data["formal_run_authorized"] = True

    with pytest.raises(ValidationError):
        IngestionReadinessReport.model_validate(readiness_data)


@pytest.mark.parametrize("change", ["missing", "extra"])
def test_report_requires_exactly_the_seven_core_result_keys(
    readiness_data: dict[str, Any], change: str
) -> None:
    if change == "missing":
        del readiness_data["stream_results"]["ECG"]
    else:
        extra = copy.deepcopy(readiness_data["stream_results"]["I"])
        extra["modality"] = "THERMAL"
        readiness_data["stream_results"]["THERMAL"] = extra

    with pytest.raises(ValidationError):
        IngestionReadinessReport.model_validate(readiness_data)


def test_stream_result_key_must_match_modality(readiness_data: dict[str, Any]) -> None:
    readiness_data["stream_results"]["X"]["modality"] = "U"

    with pytest.raises(ValidationError):
        IngestionReadinessReport.model_validate(readiness_data)


def test_task_reference_result_uses_reserved_modality(readiness_data: dict[str, Any]) -> None:
    readiness_data["task_reference_result"]["modality"] = "X"

    with pytest.raises(ValidationError):
        IngestionReadinessReport.model_validate(readiness_data)


def test_task_reference_result_is_optional(readiness_data: dict[str, Any]) -> None:
    readiness_data["task_reference_result"] = None

    report = IngestionReadinessReport.model_validate(readiness_data)

    assert report.disposition is ReadinessDisposition.READY


@pytest.mark.parametrize(
    "field",
    ["adapter_id", "adapter_version", "normalized_schema_id", "row_count"],
)
def test_ready_result_requires_adapter_and_normalized_content_identity(
    readiness_data: dict[str, Any], field: str
) -> None:
    readiness_data["stream_results"]["X"][field] = None

    with pytest.raises(ValidationError):
        IngestionReadinessReport.model_validate(readiness_data)


@pytest.mark.parametrize(
    ("field", "claimed_value"),
    [
        ("adapter_id", "unexpected-adapter"),
        ("adapter_version", "0.1.0"),
        ("normalized_schema_id", "unexpected-normalized-v0.1"),
        ("row_count", 1),
        ("artifact_row_counts", {"unexpected_artifact": 1}),
        ("source_time_start_s", 0.0),
        ("source_time_end_s", 1.0),
        ("observed_sample_rate_hz", 1.0),
    ],
)
def test_uninspected_result_cannot_claim_normalized_content(
    readiness_data: dict[str, Any], field: str, claimed_value: object
) -> None:
    _make_unavailable_optional(readiness_data)
    readiness_data["disposition"] = "ready_partial"
    readiness_data["stream_results"]["I"][field] = claimed_value

    with pytest.raises(ValidationError):
        IngestionReadinessReport.model_validate(readiness_data)


@pytest.mark.parametrize("bad_count", [-1, "1"])
def test_artifact_row_counts_are_strict_nonnegative_integers(
    readiness_data: dict[str, Any], bad_count: object
) -> None:
    readiness_data["stream_results"]["I"]["artifact_row_counts"]["frame_index"] = (
        bad_count
    )

    with pytest.raises(ValidationError):
        IngestionReadinessReport.model_validate(readiness_data)


def test_disposition_must_match_all_ready_results(readiness_data: dict[str, Any]) -> None:
    readiness_data["disposition"] = "ready_partial"

    with pytest.raises(ValidationError):
        IngestionReadinessReport.model_validate(readiness_data)


def test_ready_report_must_continue_to_synchronization(
    readiness_data: dict[str, Any],
) -> None:
    readiness_data["can_continue_to_synchronization"] = False

    with pytest.raises(ValidationError):
        IngestionReadinessReport.model_validate(readiness_data)


def test_optional_unavailable_result_requires_partial_but_can_continue(
    readiness_data: dict[str, Any],
) -> None:
    _make_unavailable_optional(readiness_data)
    readiness_data["disposition"] = "ready_partial"

    report = IngestionReadinessReport.model_validate(readiness_data)

    assert report.disposition is ReadinessDisposition.READY_PARTIAL
    assert report.can_continue_to_synchronization is True
    assert report.stream_results["I"].readiness is StreamReadiness.UNAVAILABLE


def test_required_unavailable_result_requires_blocked_and_cannot_continue(
    readiness_data: dict[str, Any],
) -> None:
    _make_unavailable_optional(readiness_data)
    readiness_data["stream_results"]["I"]["required_for_import"] = True
    readiness_data["disposition"] = "blocked"
    readiness_data["can_continue_to_synchronization"] = False

    report = IngestionReadinessReport.model_validate(readiness_data)

    assert report.disposition is ReadinessDisposition.BLOCKED
    assert report.can_continue_to_synchronization is False


def test_required_unavailable_result_rejects_partial_continuation(
    readiness_data: dict[str, Any],
) -> None:
    _make_unavailable_optional(readiness_data)
    readiness_data["stream_results"]["I"]["required_for_import"] = True
    readiness_data["disposition"] = "ready_partial"

    with pytest.raises(ValidationError):
        IngestionReadinessReport.model_validate(readiness_data)


def test_optional_not_applicable_result_does_not_degrade_disposition(
    readiness_data: dict[str, Any],
) -> None:
    _make_unavailable_optional(readiness_data)
    result = readiness_data["stream_results"]["I"]
    result["declared_status"] = "not_applicable"
    result["readiness"] = "not_applicable"

    report = IngestionReadinessReport.model_validate(readiness_data)

    assert report.disposition is ReadinessDisposition.READY


def test_required_unavailable_task_reference_blocks_report(
    readiness_data: dict[str, Any],
) -> None:
    result = readiness_data["task_reference_result"]
    result.update(
        {
            "declared_status": "missing",
            "readiness": "unavailable",
            "adapter_id": None,
            "adapter_version": None,
            "source_paths": [],
            "source_checksums": {},
            "normalized_schema_id": None,
            "row_count": None,
            "artifact_row_counts": {},
            "source_time_start_s": None,
            "source_time_end_s": None,
            "observed_sample_rate_hz": None,
            "canonical_fields": [],
            "units": {},
            "quality_summary": {},
            "assumptions": [],
            "issues": [],
        }
    )
    readiness_data["disposition"] = "blocked"
    readiness_data["can_continue_to_synchronization"] = False

    report = IngestionReadinessReport.model_validate(readiness_data)

    assert report.disposition is ReadinessDisposition.BLOCKED


@pytest.mark.parametrize(
    ("field_path", "value"),
    [
        (("can_continue_to_synchronization",), "true"),
        (("stream_results", "X", "required_for_import"), "true"),
        (("stream_results", "X", "row_count"), "2902"),
        (("stream_results", "X", "observed_sample_rate_hz"), "100.0"),
    ],
)
def test_json_scalar_types_are_not_silently_coerced(
    readiness_data: dict[str, Any], field_path: tuple[str, ...], value: object
) -> None:
    target: dict[str, Any] = readiness_data
    for key in field_path[:-1]:
        target = target[key]
    target[field_path[-1]] = value

    with pytest.raises(ValidationError):
        IngestionReadinessReport.model_validate(readiness_data)
