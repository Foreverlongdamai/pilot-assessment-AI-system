from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest

import pilot_assessment.synchronization.service as service
from pilot_assessment.contracts.session import StreamDescriptor
from pilot_assessment.contracts.synchronization import (
    SynchronizationDisposition,
    SynchronizationItemStatus,
)
from pilot_assessment.synchronization import synchronize_bundle, synchronize_session

from .test_service import (
    _mutate_manifest,
    _ready_input,
    _set_clock,
)


def test_bundle_reference_uses_own_clock_checksum_and_separate_result(tmp_path: Path) -> None:
    sync_input = _ready_input(tmp_path)
    bundle = sync_input.loaded_manifest.bundle_root
    _set_clock(
        bundle,
        "task_reference",
        clock_id="reference_clock",
        scale=1.0,
        drift_ppm=0.0,
        offset_ns=50_000_000,
        residual_rms_ms=0.25,
        residual_max_ms=0.75,
        method="fixture-declared-v0.1",
    )

    outcome = synchronize_bundle(bundle)

    result = outcome.report.task_reference_result
    assert outcome.aligned_session is not None
    assert outcome.aligned_session.task_reference is not None
    assert result is not None
    assert result.synchronization_status is SynchronizationItemStatus.ALIGNED
    assert result.clock is not None
    assert result.clock.model_dump(mode="json") == {
        "clock_id": "reference_clock",
        "method": "fixture-declared-v0.1",
        "scale": 1.0,
        "offset_ns": 50_000_000,
        "drift_ppm": 0.0,
        "residual_rms_ms": 0.25,
        "residual_max_ms": 0.75,
        "declaration_consistent": True,
    }
    assert result.source_checksums == dict(outcome.aligned_session.task_reference.source_checksums)
    assert "task_reference" not in outcome.report.stream_results
    assert outcome.aligned_session is not None
    assert "task_reference" not in outcome.aligned_session.streams
    assert outcome.aligned_session.task_reference is not None


def test_required_bundle_reference_without_in_session_rows_blocks(tmp_path: Path) -> None:
    sync_input = _ready_input(tmp_path)
    bundle = sync_input.loaded_manifest.bundle_root
    _set_clock(
        bundle,
        "task_reference",
        clock_id="reference_clock",
        scale=1.0,
        drift_ppm=0.0,
        offset_ns=3_000_000_000,
        method="fixture-declared-v0.1",
    )

    outcome = synchronize_bundle(bundle)

    result = outcome.report.task_reference_result
    assert outcome.report.disposition is SynchronizationDisposition.BLOCKED
    assert outcome.aligned_session is None
    assert result is not None
    assert result.synchronization_status is SynchronizationItemStatus.INVALID
    assert result.clock is not None
    assert result.clock.declaration_consistent is True
    assert result.issues[0].error_code == "REFERENCE_ALIGNMENT_FAILED"
    assert result.artifacts == {}


def test_required_bundle_reference_clock_failure_blocks(tmp_path: Path) -> None:
    sync_input = _ready_input(tmp_path)
    bundle = sync_input.loaded_manifest.bundle_root
    _set_clock(
        bundle,
        "task_reference",
        clock_id="reference_clock",
        scale=1.0001,
        drift_ppm=0.0,
        method="fixture-declared-v0.1",
    )

    outcome = synchronize_bundle(bundle)

    result = outcome.report.task_reference_result
    assert outcome.report.disposition is SynchronizationDisposition.BLOCKED
    assert outcome.aligned_session is None
    assert result is not None
    assert result.synchronization_status is SynchronizationItemStatus.INVALID
    assert result.clock is not None
    assert result.clock.declaration_consistent is False
    assert result.issues[0].error_code == "CLOCK_DECLARATION_INCONSISTENT"


def test_same_clock_conflict_marks_reference_invalid_when_x_window_is_unavailable(
    tmp_path: Path,
) -> None:
    sync_input = _ready_input(tmp_path)
    bundle = sync_input.loaded_manifest.bundle_root
    _set_clock(
        bundle,
        "task_reference",
        clock_id="sim_clock",
        scale=1.0001,
        drift_ppm=100.0,
    )

    outcome = synchronize_bundle(bundle)

    result = outcome.report.task_reference_result
    assert outcome.report.disposition is SynchronizationDisposition.BLOCKED
    assert outcome.aligned_session is None
    assert result is not None
    assert result.synchronization_status is SynchronizationItemStatus.INVALID
    assert result.clock is not None
    assert result.clock.declaration_consistent is False
    assert {issue.error_code for issue in result.issues} == {"CLOCK_DECLARATION_INCONSISTENT"}


def test_model_bundle_reference_is_deferred_and_neutral(tmp_path: Path) -> None:
    sync_input = _ready_input(tmp_path)
    bundle = sync_input.loaded_manifest.bundle_root

    def mutate(manifest: dict[str, Any]) -> None:
        task = manifest["task"]
        streams = manifest["streams"]
        assert isinstance(task, dict) and isinstance(streams, dict)
        task["reference"] = {
            "source": "model_bundle",
            "reference_id": "model-reference-fixture-v0.1",
            "extensions": {},
        }
        streams.pop("task_reference")

    _mutate_manifest(bundle, mutate, rewrite_checksums=True)

    outcome = synchronize_bundle(bundle)

    result = outcome.report.task_reference_result
    assert outcome.report.disposition is SynchronizationDisposition.READY
    assert outcome.aligned_session is not None
    assert outcome.aligned_session.task_reference is None
    assert result is not None
    assert result.source == "model_bundle"
    assert result.synchronization_status is (
        SynchronizationItemStatus.DEFERRED_MODEL_BUNDLE_RESOLUTION
    )
    assert result.artifacts == {}
    assert result.source_checksums == {}


def test_bundle_reference_uses_prepared_memory_and_snapshot_checksum_without_reread(
    tmp_path: Path,
) -> None:
    sync_input = _ready_input(tmp_path)
    reference = sync_input.prepared_session.task_reference
    assert reference is not None
    expected_checksums = dict(reference.source_checksums)
    assert expected_checksums
    assert expected_checksums == {
        path: sync_input.loaded_manifest.verified_digests[path] for path in reference.source_paths
    }
    source = sync_input.loaded_manifest.bundle_root.joinpath(*reference.source_paths[0].split("/"))
    source.write_bytes(b"not parquet anymore")

    outcome = synchronize_session(sync_input)

    assert outcome.report.disposition is SynchronizationDisposition.READY
    assert outcome.aligned_session is not None
    assert outcome.aligned_session.task_reference is not None
    assert dict(outcome.aligned_session.task_reference.source_checksums) == expected_checksums
    assert outcome.report.task_reference_result is not None
    assert outcome.report.task_reference_result.source_checksums == expected_checksums


def test_ready_bundle_reference_is_included_in_ready_clock_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_input = _ready_input(tmp_path)
    captured: list[tuple[str, tuple[str, ...]]] = []
    original = service.validate_same_clock_mappings

    def record(descriptors: Iterable[StreamDescriptor]) -> None:
        values = tuple(descriptors)
        clock_ids = {descriptor.clock_id for descriptor in values}
        assert len(clock_ids) == 1
        captured.append(
            (next(iter(clock_ids)), tuple(descriptor.modality for descriptor in values))
        )
        original(values)

    monkeypatch.setattr(service, "validate_same_clock_mappings", record)

    synchronize_session(sync_input)

    assert any("task_reference" in group for _clock_id, group in captured)


def test_optional_bundle_reference_failure_is_partial_and_keeps_core_session(
    tmp_path: Path,
) -> None:
    sync_input = _ready_input(tmp_path)
    bundle = sync_input.loaded_manifest.bundle_root

    def make_optional(manifest: dict[str, Any]) -> None:
        streams = manifest["streams"]
        assert isinstance(streams, dict)
        descriptor = streams["task_reference"]
        assert isinstance(descriptor, dict)
        descriptor["required_for_import"] = False

    _mutate_manifest(bundle, make_optional)
    _set_clock(
        bundle,
        "task_reference",
        clock_id="reference_clock",
        scale=1.0,
        drift_ppm=0.0,
        offset_ns=3_000_000_000,
        method="fixture-declared-v0.1",
    )

    outcome = synchronize_bundle(bundle)

    assert outcome.report.disposition is SynchronizationDisposition.READY_PARTIAL
    assert outcome.aligned_session is not None
    assert outcome.aligned_session.task_reference is None
    assert outcome.report.task_reference_result is not None
    assert outcome.report.task_reference_result.synchronization_status is (
        SynchronizationItemStatus.INVALID
    )
