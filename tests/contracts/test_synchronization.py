from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from pilot_assessment.contracts import (
    CORE_MODALITIES,
    MAX_SESSION_END_NS_V0_1,
    SynchronizationDisposition,
    SynchronizationPolicy,
    SynchronizationReport,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "synchronization_report_ready.json"

ArtifactFixtureSpec = tuple[str, str, str, str]
StreamFixtureSpec = tuple[str, str, bool, str, tuple[ArtifactFixtureSpec, ...]]

STREAM_FIXTURE_SPECS: dict[str, StreamFixtureSpec] = {
    "X": (
        "flight-state-normalized-v0.1",
        "flight-state-aligned-v0.1",
        True,
        "sim_clock",
        (("samples", "point", "flight-state-normalized-v0.1", "flight-state-aligned-v0.1"),),
    ),
    "U": (
        "control-input-normalized-v0.1",
        "control-input-aligned-v0.1",
        True,
        "sim_clock",
        (
            (
                "samples",
                "point",
                "control-input-normalized-v0.1",
                "control-input-aligned-v0.1",
            ),
        ),
    ),
    "I": (
        "vr-scene-source-bundle-v0.1",
        "vr-scene-aligned-v0.1",
        False,
        "vr_scene_clock",
        (
            (
                "frame_index",
                "point",
                "vr-frame-index-raw-v0.1",
                "vr-frame-index-aligned-v0.1",
            ),
            (
                "aoi_instances",
                "inherit",
                "vr-aoi-instance-raw-v0.1",
                "vr-aoi-instance-aligned-v0.1",
            ),
        ),
    ),
    "G": (
        "gaze-source-bundle-v0.1",
        "gaze-aligned-v0.1",
        False,
        "gaze_clock",
        (
            (
                "gaze_samples",
                "point",
                "gaze-sample-raw-v0.1",
                "gaze-sample-aligned-v0.1",
            ),
            (
                "fixations",
                "interval",
                "gaze-fixation-raw-v0.1",
                "gaze-fixation-aligned-v0.1",
            ),
        ),
    ),
    "EEG": (
        "eeg-source-bundle-v0.1",
        "eeg-aligned-v0.1",
        False,
        "eeg_clock",
        (("samples", "point", "eeg-sample-raw-v0.1", "eeg-sample-aligned-v0.1"),),
    ),
    "ECG": (
        "ecg-source-bundle-v0.1",
        "ecg-aligned-v0.1",
        False,
        "ecg_clock",
        (
            ("samples", "point", "ecg-sample-raw-v0.1", "ecg-sample-aligned-v0.1"),
            ("r_peaks", "point", "ecg-r-peak-raw-v0.1", "ecg-r-peak-aligned-v0.1"),
        ),
    ),
    "pilot_camera": (
        "pilot-camera-source-bundle-v0.1",
        "pilot-camera-aligned-v0.1",
        False,
        "pilot_camera_clock",
        (
            (
                "frame_index",
                "point",
                "pilot-camera-frame-index-raw-v0.1",
                "pilot-camera-frame-index-aligned-v0.1",
            ),
        ),
    ),
}


def _clock(clock_id: str) -> dict[str, Any]:
    return {
        "clock_id": clock_id,
        "method": "fixture-declared-v0.1",
        "scale": 1.0,
        "offset_ns": 0,
        "drift_ppm": 0.0,
        "residual_rms_ms": 0.0,
        "residual_max_ms": 0.0,
        "declaration_consistent": True,
    }


def _point(role: str, mode: str, source: str, aligned: str) -> dict[str, Any]:
    return {
        "artifact_role": role,
        "binding_mode": mode,
        "source_schema_id": source,
        "aligned_schema_id": aligned,
        "total_rows": 1,
        "in_session_rows": 1,
        "before_session_rows": 0,
        "after_session_rows": 0,
        "first_mapped_t_ns": 0,
        "last_mapped_t_ns": 0,
        "in_session_start_t_ns": 0,
        "in_session_end_t_ns": 0,
        "in_session_span_ns": 0,
        "session_span_ratio": 0.0,
        "duplicate_timestamp_groups": 0,
        "duplicate_timestamp_rows": 0,
        "median_period_ns": None,
        "gap_threshold_ns": None,
        "gap_count": 0,
        "max_gap_ns": None,
        "interpolated_rows": 0,
    }


def _interval(role: str, source: str, aligned: str) -> dict[str, Any]:
    return {
        "artifact_role": role,
        "binding_mode": "interval",
        "source_schema_id": source,
        "aligned_schema_id": aligned,
        "total_rows": 1,
        "before_session_rows": 0,
        "after_session_rows": 0,
        "overlapping_session_rows": 1,
        "fully_in_session_rows": 1,
        "first_start_t_ns": 0,
        "last_end_t_ns": 1_000_000_000,
        "interpolated_rows": 0,
    }


def _stream(modality: str) -> dict[str, Any]:
    source, aligned, required, clock_id, artifact_specs = STREAM_FIXTURE_SPECS[modality]
    artifacts = {
        role: (
            _interval(role, artifact_source, artifact_aligned)
            if mode == "interval"
            else _point(role, mode, artifact_source, artifact_aligned)
        )
        for role, mode, artifact_source, artifact_aligned in artifact_specs
    }
    result: dict[str, Any] = {
        "modality": modality,
        "declared_status": "present",
        "required_for_import": required,
        "input_readiness": "ready",
        "synchronization_status": "aligned",
        "clock": _clock(clock_id),
        "source_schema_id": source,
        "aligned_schema_id": aligned,
        "artifacts": artifacts,
        "issues": [],
    }
    if modality == "G":
        result["scene_gaze_metrics"] = {
            "evaluated_in_session_gaze_rows": 1,
            "valid_association_rows": 1,
            "invalid_association_count": 0,
            "gaze_minus_frame_start_min_ns": 0,
            "gaze_minus_frame_start_max_ns": 0,
            "bounded_invalid_gaze_sample_ids": [],
        }
    return result


def ready_fixture_data() -> dict[str, Any]:
    return {
        "contract_version": "0.1.0",
        "validation_scope": "native_rate_session_time_alignment_v1",
        "session_id": "synthetic-session-20260711-001",
        "source_snapshot_fingerprint": "1" * 64,
        "source_classification": "synthetic-test-data",
        "synthetic_provenance": {
            "generator_id": "synthetic-multimodal-generator-v0.1",
            "seed": 20260711,
            "scientific_validation_status": "not_supported",
            "source_xu_sha256": "a" * 64,
            "lock_fingerprint": "b" * 64,
            "provenance_scope": "captured-format-sample-xu-plus-synthetic-modalities",
            "formal_assessment_supported": False,
        },
        "policy": {
            "contract_version": "0.1.0",
            "policy_id": "native-alignment-engineering-v0.1",
            "gap_detection_multiplier": 5.0,
            "clock_consistency_tolerance_ppm": 0.000001,
        },
        "policy_fingerprint": "2" * 64,
        "binding_catalog_fingerprint": "3" * 64,
        "session_window": {
            "start_t_ns": 0,
            "end_t_ns": 2_000_000_000,
            "source": "master-clock-x-mapped-coverage-v1",
        },
        "disposition": "ready",
        "can_continue_to_anchor_availability": True,
        "formal_run_authorized": False,
        "stream_results": {modality: _stream(modality) for modality in sorted(CORE_MODALITIES)},
        "task_reference_result": {
            "reference_id": "synthetic-format-fixture-path-v0.1",
            "source": "bundle",
            "declared_status": "present",
            "required_for_import": True,
            "input_readiness": "ready",
            "synchronization_status": "aligned",
            "clock": _clock("sim_clock"),
            "source_schema_id": "task-reference-normalized-v0.1",
            "aligned_schema_id": "task-reference-path-aligned-v0.1",
            "source_checksums": {"references/commanded_path.parquet": "c" * 64},
            "artifacts": {
                "commanded_path": _point(
                    "commanded_path",
                    "point",
                    "task-reference-path-raw-v0.1",
                    "task-reference-path-aligned-v0.1",
                )
            },
            "issues": [],
        },
        "annotation_result": {
            "synchronization_status": "aligned",
            "revision": "synthetic-unvalidated-v0.1",
            "phase_schema_id": "phases-synthetic-v0.1",
            "event_schema_id": "events-synthetic-v0.1",
            "baseline_schema_id": "baseline-intervals-synthetic-v0.1",
            "phase_count": 3,
            "event_count": 2,
            "baseline_count": 1,
            "unannotated_intervals": [],
            "synthetic_semantics_unvalidated": True,
            "issues": [],
        },
        "global_issues": [],
        "synchronization_fingerprint": "4" * 64,
    }


def ready_report_data() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(FIXTURE.read_text(encoding="utf-8")),
    )


def test_ready_fixture_matches_canonical_builder() -> None:
    assert ready_report_data() == ready_fixture_data()
    SynchronizationReport.model_validate(ready_report_data())


def test_default_synchronization_policy_matches_v0_1() -> None:
    policy = SynchronizationPolicy()
    assert policy.contract_version == "0.1.0"
    assert policy.policy_id == "native-alignment-engineering-v0.1"
    assert policy.gap_detection_multiplier == 5.0
    assert policy.clock_consistency_tolerance_ppm == 0.000001


def test_ready_synchronization_fixture_round_trips() -> None:
    payload = ready_report_data()
    report = SynchronizationReport.model_validate(payload)
    assert report.disposition is SynchronizationDisposition.READY
    assert report.can_continue_to_anchor_availability is True
    assert report.formal_run_authorized is False
    assert set(report.stream_results) == set(CORE_MODALITIES)


def test_report_requires_exact_seven_core_stream_result_keys() -> None:
    payload = ready_report_data()
    payload["stream_results"]["task_reference"] = payload["stream_results"]["X"]
    with pytest.raises(ValidationError):
        SynchronizationReport.model_validate(payload)


@pytest.mark.parametrize(
    ("disposition", "can_continue"),
    [("ready", False), ("blocked", True)],
)
def test_disposition_and_continuation_cannot_contradict(
    disposition: str, can_continue: bool
) -> None:
    payload = ready_report_data()
    payload["disposition"] = disposition
    payload["can_continue_to_anchor_availability"] = can_continue
    if disposition == "blocked":
        payload["session_window"] = None
    with pytest.raises(ValidationError):
        SynchronizationReport.model_validate(payload)


def test_non_blocked_report_requires_session_window() -> None:
    payload = ready_report_data()
    payload["session_window"] = None
    with pytest.raises(ValidationError):
        SynchronizationReport.model_validate(payload)


def test_core_stream_cannot_defer_model_bundle_resolution() -> None:
    payload = ready_report_data()
    result = payload["stream_results"]["I"]
    result.update(
        synchronization_status="deferred_model_bundle_resolution",
        aligned_schema_id=None,
        artifacts={},
        scene_gaze_metrics=None,
    )
    payload["disposition"] = "ready_partial"
    with pytest.raises(ValidationError):
        SynchronizationReport.model_validate(payload)


def test_task_reference_cannot_be_mixed_into_core_results() -> None:
    payload = ready_report_data()
    payload["stream_results"]["task_reference"] = copy.deepcopy(payload["stream_results"]["X"])
    payload["stream_results"]["task_reference"]["modality"] = "task_reference"
    with pytest.raises(ValidationError):
        SynchronizationReport.model_validate(payload)


@pytest.mark.parametrize(
    ("field_path", "value"),
    [
        (("stream_results", "X", "declared_status"), "missing"),
        (("stream_results", "X", "input_readiness"), "unavailable"),
        (("stream_results", "X", "clock", "declaration_consistent"), False),
        (("task_reference_result", "declared_status"), "missing"),
        (("task_reference_result", "input_readiness"), "unavailable"),
        (("task_reference_result", "clock", "declaration_consistent"), False),
    ],
)
def test_aligned_input_requires_present_ready_consistent_declaration(
    field_path: tuple[str, ...], value: object
) -> None:
    payload = ready_report_data()
    target: dict[str, Any] = payload
    for key in field_path[:-1]:
        target = target[key]
    target[field_path[-1]] = value
    with pytest.raises(ValidationError):
        SynchronizationReport.model_validate(payload)


def test_formal_run_authorized_cannot_be_true() -> None:
    payload = ready_report_data()
    payload["formal_run_authorized"] = True
    with pytest.raises(ValidationError):
        SynchronizationReport.model_validate(payload)


@pytest.mark.parametrize("value", [0, 0.0])
def test_formal_run_authorized_requires_an_actual_boolean(value: object) -> None:
    payload = ready_report_data()
    payload["formal_run_authorized"] = value
    with pytest.raises(ValidationError):
        SynchronizationReport.model_validate(payload)


@pytest.mark.parametrize("value", [False, 0.0])
def test_session_window_start_requires_an_actual_integer_zero(value: object) -> None:
    payload = ready_report_data()
    payload["session_window"]["start_t_ns"] = value
    with pytest.raises(ValidationError):
        SynchronizationReport.model_validate(payload)


def test_session_window_end_must_be_positive() -> None:
    payload = ready_report_data()
    payload["session_window"]["end_t_ns"] = 0
    with pytest.raises(ValidationError):
        SynchronizationReport.model_validate(payload)


def test_session_window_accepts_largest_exact_v0_1_end() -> None:
    payload = ready_report_data()
    payload["session_window"]["end_t_ns"] = MAX_SESSION_END_NS_V0_1

    report = SynchronizationReport.model_validate(payload)

    assert report.session_window is not None
    assert report.session_window.end_t_ns == MAX_SESSION_END_NS_V0_1


def test_session_window_rejects_end_beyond_exact_v0_1_limit() -> None:
    payload = ready_report_data()
    payload["session_window"]["end_t_ns"] = MAX_SESSION_END_NS_V0_1 + 1

    with pytest.raises(ValidationError):
        SynchronizationReport.model_validate(payload)


@pytest.mark.parametrize("value", [True, 1.0, float(MAX_SESSION_END_NS_V0_1)])
def test_session_window_end_remains_a_strict_integer(value: object) -> None:
    payload = ready_report_data()
    payload["session_window"]["end_t_ns"] = value

    with pytest.raises(ValidationError):
        SynchronizationReport.model_validate(payload)


@pytest.mark.parametrize(
    ("modality", "artifact_role", "value"),
    [
        ("X", "samples", False),
        ("X", "samples", 0.0),
        ("G", "fixations", False),
        ("G", "fixations", 0.0),
    ],
)
def test_interpolated_rows_requires_an_actual_integer_zero(
    modality: str, artifact_role: str, value: object
) -> None:
    payload = ready_report_data()
    payload["stream_results"][modality]["artifacts"][artifact_role]["interpolated_rows"] = value
    with pytest.raises(ValidationError):
        SynchronizationReport.model_validate(payload)


@pytest.mark.parametrize(
    ("field_path", "value"),
    [
        (("can_continue_to_anchor_availability",), "true"),
        (("stream_results", "X", "required_for_import"), "true"),
        (("stream_results", "X", "artifacts", "samples", "total_rows"), "1"),
        (("stream_results", "X", "clock", "scale"), "1.0"),
    ],
)
def test_json_scalar_types_are_not_silently_coerced(
    field_path: tuple[str, ...], value: object
) -> None:
    payload = ready_report_data()
    target: dict[str, Any] = payload
    for key in field_path[:-1]:
        target = target[key]
    target[field_path[-1]] = value
    with pytest.raises(ValidationError):
        SynchronizationReport.model_validate(payload)
