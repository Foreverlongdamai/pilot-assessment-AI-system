from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, NoReturn, cast

import polars as pl
import pytest

import pilot_assessment.synchronization.service as service
from pilot_assessment.contracts.errors import DomainErrorData, ErrorSeverity
from pilot_assessment.contracts.ingestion import StreamReadiness, StreamReadinessResult
from pilot_assessment.contracts.session import ClockSync, SessionManifest, StreamDescriptor
from pilot_assessment.contracts.synchronization import (
    AnnotationSynchronizationResult,
    SceneGazeMetrics,
    StreamSynchronizationResult,
    SynchronizationDisposition,
    SynchronizationItemStatus,
    TaskReferenceSynchronizationResult,
)
from pilot_assessment.ingestion.manifest_loader import LoadedManifest, ManifestLoader
from pilot_assessment.ingestion.models import NormalizedStream
from pilot_assessment.synchronization import (
    SynchronizationInput,
    load_builtin_temporal_catalog,
    synchronize_bundle,
    synchronize_session,
)
from pilot_assessment.synchronization.fingerprint import fingerprint_policy
from pilot_assessment.synchronization.models import SynchronizationOutcome
from pilot_assessment.synchronization.profiles import (
    PointBinding,
    builtin_temporal_catalog_fingerprint,
)
from pilot_assessment.synchronization.service import (
    _derive_disposition,
    _item_status_from_readiness,
)

from .test_models import _ready_parts


def _ready_input(tmp_path: Path) -> SynchronizationInput:
    loaded, report, prepared = _ready_parts(tmp_path)
    return SynchronizationInput(
        loaded_manifest=loaded,
        readiness_report=report,
        prepared_session=prepared,
    )


def _write_manifest(bundle: Path, manifest: dict[str, Any]) -> None:
    SessionManifest.model_validate(manifest)
    (bundle / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _rewrite_checksum_scope(bundle: Path, manifest: dict[str, Any]) -> None:
    paths = {
        path
        for descriptor in manifest["streams"].values()
        if descriptor["status"] in {"present", "invalid"}
        for path in descriptor["paths"]
    }
    annotations = manifest["annotations"]
    paths.update(
        {
            annotations["phases"],
            annotations["events"],
            annotations["baseline_intervals"],
        }
    )
    lines = []
    for relative_path in sorted(paths):
        payload = bundle.joinpath(*relative_path.split("/")).read_bytes()
        lines.append(f"{hashlib.sha256(payload).hexdigest()}  {relative_path}")
    (bundle / "integrity" / "checksums.sha256").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _mutate_manifest(bundle: Path, mutate: Any, *, rewrite_checksums: bool = False) -> None:
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    mutate(manifest)
    if rewrite_checksums:
        _rewrite_checksum_scope(bundle, manifest)
    _write_manifest(bundle, manifest)


def _set_clock(
    bundle: Path,
    modality: str,
    *,
    clock_id: str,
    scale: float,
    drift_ppm: float,
    offset_ns: int = 0,
    residual_rms_ms: float = 0.0,
    residual_max_ms: float = 0.0,
    method: str | None = None,
) -> None:
    def mutate(manifest: dict[str, Any]) -> None:
        descriptor = manifest["streams"][modality]
        prior_clock = descriptor["clock_sync"]
        descriptor["clock_id"] = clock_id
        descriptor["clock_sync"] = {
            "method": method or prior_clock["method"],
            "scale": scale,
            "offset_ns": offset_ns,
            "drift_ppm": drift_ppm,
            "residual_rms_ms": residual_rms_ms,
            "residual_max_ms": residual_max_ms,
            "extensions": {},
        }

    _mutate_manifest(bundle, mutate)


def _set_declared_status(
    bundle: Path,
    modality: str,
    status: str,
    *,
    required: bool,
    conflicting_export_pending_clock: bool = False,
) -> None:
    def mutate(manifest: dict[str, Any]) -> None:
        descriptor = manifest["streams"][modality]
        descriptor["status"] = status
        descriptor["required_for_import"] = required
        if status in {"export_pending", "missing", "not_applicable"}:
            descriptor["paths"] = []
            descriptor["checksums"] = {}
            descriptor["quality_summary"] = None
        if status in {"missing", "not_applicable"}:
            descriptor["clock_sync"] = None
        if conflicting_export_pending_clock:
            descriptor["clock_id"] = "sim_clock"
            descriptor["clock_sync"] = {
                "method": "conflicting-unused-v0.1",
                "scale": 1.0001,
                "offset_ns": 17,
                "drift_ppm": 100.0,
                "residual_rms_ms": 0.0,
                "residual_max_ms": 0.0,
                "extensions": {},
            }

    _mutate_manifest(bundle, mutate, rewrite_checksums=True)


def _replace_stream_table(
    sync_input: SynchronizationInput,
    modality: str,
    role: str,
    table: pl.DataFrame,
) -> SynchronizationInput:
    stream = sync_input.prepared_session.streams[modality]
    changed_stream = replace(stream, tables={**stream.tables, role: table})
    changed_prepared = replace(
        sync_input.prepared_session,
        streams={**sync_input.prepared_session.streams, modality: changed_stream},
    )
    return SynchronizationInput(
        loaded_manifest=sync_input.loaded_manifest,
        readiness_report=sync_input.readiness_report,
        prepared_session=changed_prepared,
    )


def _replace_prepared_stream(
    sync_input: SynchronizationInput,
    modality: str,
    stream: NormalizedStream,
) -> SynchronizationInput:
    changed_prepared = replace(
        sync_input.prepared_session,
        streams={**sync_input.prepared_session.streams, modality: stream},
    )
    return SynchronizationInput(
        loaded_manifest=sync_input.loaded_manifest,
        readiness_report=sync_input.readiness_report,
        prepared_session=changed_prepared,
    )


def _catalog_without(schema_id: str):  # type annotation would obscure the test intent
    catalog = load_builtin_temporal_catalog()
    return catalog.__class__(
        catalog_version=catalog.catalog_version,
        streams=tuple(
            profile for profile in catalog.streams if profile.stream_schema_id != schema_id
        ),
    )


def _issue(code: str, field: str) -> DomainErrorData:
    return DomainErrorData(
        error_code=code,
        severity=ErrorSeverity.WARNING,
        recoverable=True,
        message=f"bounded {code}",
        field_or_path=field,
        remediation="Use corrected fixture input.",
    )


def test_m2_blocked_returns_blocked_report_without_constructing_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_input = _ready_input(tmp_path)
    bundle = sync_input.loaded_manifest.bundle_root
    _set_declared_status(bundle, "I", "missing", required=True)

    def forbidden_input(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("blocked M2 must not construct SynchronizationInput")

    monkeypatch.setattr(service, "SynchronizationInput", forbidden_input)

    outcome = synchronize_bundle(bundle)

    assert outcome.report.disposition is SynchronizationDisposition.BLOCKED
    assert outcome.aligned_session is None
    assert set(outcome.report.stream_results) == {
        "X",
        "U",
        "I",
        "G",
        "EEG",
        "ECG",
        "pilot_camera",
    }
    assert outcome.report.formal_run_authorized is False


def test_synchronize_bundle_loads_manifest_exactly_once(tmp_path: Path) -> None:
    sync_input = _ready_input(tmp_path)

    class CountingLoader(ManifestLoader):
        calls = 0

        def load(self, bundle_root: str | Path) -> LoadedManifest:
            self.calls += 1
            return super().load(bundle_root)

    loader = CountingLoader()

    outcome = synchronize_bundle(sync_input.loaded_manifest.bundle_root, loader=loader)

    assert loader.calls == 1
    assert outcome.report.disposition is SynchronizationDisposition.READY


def test_m2_blocked_fingerprint_exception_uses_bounded_emergency_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_input = _ready_input(tmp_path)
    bundle = sync_input.loaded_manifest.bundle_root
    _set_declared_status(bundle, "I", "missing", required=True)

    def explode(**_kwargs: object) -> str:
        raise RuntimeError("SECRET blocked fingerprint path")

    monkeypatch.setattr(service, "fingerprint_synchronization", explode)

    outcome = synchronize_bundle(bundle)

    assert outcome.report.disposition is SynchronizationDisposition.BLOCKED
    assert outcome.aligned_session is None
    assert any(
        issue.error_code == "SYNCHRONIZATION_INTERNAL_ERROR"
        for issue in outcome.report.global_issues
    )
    assert "SECRET" not in outcome.report.model_dump_json()


def test_required_alignment_failure_blocks_and_returns_no_aligned_session(
    tmp_path: Path,
) -> None:
    sync_input = _ready_input(tmp_path)
    x = sync_input.prepared_session.streams["X"].tables["samples"]
    bad_x = x.with_columns(pl.col("source_time_s").cast(pl.String))
    corrupted = _replace_stream_table(sync_input, "X", "samples", bad_x)

    outcome = synchronize_session(corrupted)

    assert outcome.report.disposition is SynchronizationDisposition.BLOCKED
    assert outcome.aligned_session is None
    assert outcome.report.stream_results["X"].synchronization_status is (
        SynchronizationItemStatus.INVALID
    )
    assert outcome.report.stream_results["X"].clock is not None
    assert outcome.report.stream_results["X"].clock.declaration_consistent is True
    assert {issue.error_code for issue in outcome.report.stream_results["X"].issues} == {
        "TEMPORAL_ORDER_INVALID"
    }
    assert outcome.report.formal_run_authorized is False


def test_optional_alignment_failure_returns_ready_partial_and_excludes_failed_view(
    tmp_path: Path,
) -> None:
    sync_input = _ready_input(tmp_path)
    scene = sync_input.prepared_session.streams["I"].tables["frame_index"]
    bad_scene = scene.with_columns(pl.col("source_timestamp_s").cast(pl.String))
    corrupted = _replace_stream_table(sync_input, "I", "frame_index", bad_scene)

    outcome = synchronize_session(corrupted)

    assert outcome.report.disposition is SynchronizationDisposition.READY_PARTIAL
    assert outcome.aligned_session is not None
    assert "I" not in outcome.aligned_session.streams
    assert "G" not in outcome.aligned_session.streams
    assert outcome.report.stream_results["I"].synchronization_status is (
        SynchronizationItemStatus.INVALID
    )
    assert outcome.report.stream_results["I"].clock is not None
    assert outcome.report.stream_results["I"].clock.declaration_consistent is True
    assert outcome.report.stream_results["G"].synchronization_status is (
        SynchronizationItemStatus.INVALID
    )
    assert outcome.report.formal_run_authorized is False


def test_invalid_optional_stream_does_not_enter_fingerprint_time_parts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_input = _ready_input(tmp_path)
    scene = sync_input.prepared_session.streams["I"].tables["frame_index"]
    corrupted = _replace_stream_table(
        sync_input,
        "I",
        "frame_index",
        scene.with_columns(pl.col("source_timestamp_s").cast(pl.String)),
    )
    captured: dict[str, object] = {}
    original = service.fingerprint_synchronization

    def capture(
        *,
        source_snapshot_fingerprint: str,
        policy_fingerprint: str,
        binding_catalog_fingerprint: str,
        aligned_time_parts: Mapping[str, bytes],
        aligned_annotations_json: bytes,
        statuses_and_issues_json: bytes,
    ) -> str:
        captured["aligned_time_parts"] = dict(aligned_time_parts)
        return original(
            source_snapshot_fingerprint=source_snapshot_fingerprint,
            policy_fingerprint=policy_fingerprint,
            binding_catalog_fingerprint=binding_catalog_fingerprint,
            aligned_time_parts=aligned_time_parts,
            aligned_annotations_json=aligned_annotations_json,
            statuses_and_issues_json=statuses_and_issues_json,
        )

    monkeypatch.setattr(service, "fingerprint_synchronization", capture)

    synchronize_session(corrupted)

    parts = cast(dict[str, bytes], captured["aligned_time_parts"])
    assert not any(key.startswith("I/") for key in parts)


def test_annotation_semantics_failure_blocks(tmp_path: Path) -> None:
    sync_input = _ready_input(tmp_path)
    bundle = sync_input.loaded_manifest.bundle_root
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    phase_path = bundle.joinpath(*manifest["annotations"]["phases"].split("/"))
    phases = json.loads(phase_path.read_text(encoding="utf-8"))
    phases["phases"][1]["start_s"] = 0.0
    phase_path.write_text(
        json.dumps(phases, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _rewrite_checksum_scope(bundle, manifest)

    outcome = synchronize_bundle(bundle)

    assert outcome.report.disposition is SynchronizationDisposition.BLOCKED
    assert outcome.aligned_session is None
    assert outcome.report.annotation_result is not None
    assert outcome.report.annotation_result.synchronization_status is (
        SynchronizationItemStatus.INVALID
    )
    assert outcome.report.annotation_result.issues[0].error_code == "ANNOTATION_SEMANTICS_INVALID"


def test_clock_conflict_blocks_with_stable_error_code(tmp_path: Path) -> None:
    sync_input = _ready_input(tmp_path)
    bundle = sync_input.loaded_manifest.bundle_root
    _set_clock(
        bundle,
        "I",
        clock_id="sim_clock",
        scale=1.0001,
        drift_ppm=100.0,
    )

    outcome = synchronize_bundle(bundle)

    assert outcome.report.disposition is SynchronizationDisposition.BLOCKED
    assert outcome.aligned_session is None
    for modality in ("X", "U", "I"):
        result = outcome.report.stream_results[modality]
        assert result.synchronization_status is SynchronizationItemStatus.INVALID
        assert result.clock is not None
        assert result.clock.declaration_consistent is False
        assert {issue.error_code for issue in result.issues} == {"CLOCK_DECLARATION_INCONSISTENT"}


def test_nonready_optional_clock_conflict_does_not_pollute_ready_inventory(
    tmp_path: Path,
) -> None:
    sync_input = _ready_input(tmp_path)
    bundle = sync_input.loaded_manifest.bundle_root
    _set_declared_status(
        bundle,
        "I",
        "export_pending",
        required=False,
        conflicting_export_pending_clock=True,
    )

    outcome = synchronize_bundle(bundle)

    assert outcome.report.disposition is SynchronizationDisposition.READY_PARTIAL
    assert outcome.aligned_session is not None
    assert not any(
        issue.error_code == "CLOCK_DECLARATION_INCONSISTENT"
        for result in outcome.report.stream_results.values()
        for issue in result.issues
    )


def test_clock_inventory_validator_receives_only_ready_core_and_ready_bundle_reference(
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

    assert captured == sorted(captured)
    assert {modality for _clock_id, group in captured for modality in group} == {
        "X",
        "U",
        "I",
        "G",
        "EEG",
        "ECG",
        "pilot_camera",
        "task_reference",
    }


@pytest.mark.parametrize(
    ("schema_id", "modality", "expected_disposition"),
    [
        ("flight-state-normalized-v0.1", "X", SynchronizationDisposition.BLOCKED),
        ("vr-scene-source-bundle-v0.1", "I", SynchronizationDisposition.READY_PARTIAL),
    ],
)
def test_missing_binding_has_required_or_optional_disposition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    schema_id: str,
    modality: str,
    expected_disposition: SynchronizationDisposition,
) -> None:
    sync_input = _ready_input(tmp_path)
    catalog = _catalog_without(schema_id)
    monkeypatch.setattr(service, "load_builtin_temporal_catalog", lambda: catalog)

    outcome = synchronize_session(sync_input)

    assert outcome.report.disposition is expected_disposition
    assert outcome.report.stream_results[modality].synchronization_status is (
        SynchronizationItemStatus.UNSUPPORTED
    )
    assert outcome.report.stream_results[modality].issues[0].error_code == (
        "TEMPORAL_BINDING_NOT_FOUND"
    )
    result_clock = outcome.report.stream_results[modality].clock
    assert result_clock is not None
    assert result_clock.declaration_consistent is True
    if expected_disposition is SynchronizationDisposition.BLOCKED:
        assert outcome.aligned_session is None
    else:
        assert outcome.aligned_session is not None
        assert modality not in outcome.aligned_session.streams


def test_required_x_prepared_timestamp_metadata_mismatch_is_unsupported_and_blocked(
    tmp_path: Path,
) -> None:
    sync_input = _ready_input(tmp_path)
    x_stream = sync_input.prepared_session.streams["X"]
    corrupted = _replace_prepared_stream(
        sync_input,
        "X",
        replace(x_stream, source_timestamp_column="forged_source_time_s"),
    )

    outcome = synchronize_session(corrupted)

    result = outcome.report.stream_results["X"]
    assert outcome.report.disposition is SynchronizationDisposition.BLOCKED
    assert outcome.aligned_session is None
    assert result.synchronization_status is SynchronizationItemStatus.UNSUPPORTED
    assert result.issues[0].error_code == "TEMPORAL_BINDING_NOT_FOUND"


def test_optional_composite_prepared_primary_role_mismatch_is_partial(
    tmp_path: Path,
) -> None:
    sync_input = _ready_input(tmp_path)
    scene_stream = sync_input.prepared_session.streams["I"]
    changed_stream = replace(scene_stream, primary_table_role="aoi_instances")
    changed_prepared = replace(
        sync_input.prepared_session,
        streams={**sync_input.prepared_session.streams, "I": changed_stream},
    )
    readiness_results = dict(sync_input.readiness_report.stream_results)
    readiness_results["I"] = readiness_results["I"].model_copy(
        update={
            "row_count": changed_stream.primary_table.height,
            "canonical_fields": tuple(changed_stream.primary_table.columns),
        }
    )
    corrupted = SynchronizationInput(
        loaded_manifest=sync_input.loaded_manifest,
        readiness_report=sync_input.readiness_report.model_copy(
            update={"stream_results": readiness_results}
        ),
        prepared_session=changed_prepared,
    )

    outcome = synchronize_session(corrupted)

    result = outcome.report.stream_results["I"]
    assert outcome.report.disposition is SynchronizationDisposition.READY_PARTIAL
    assert outcome.aligned_session is not None
    assert "I" not in outcome.aligned_session.streams
    assert result.synchronization_status is SynchronizationItemStatus.UNSUPPORTED
    assert result.issues[0].error_code == "TEMPORAL_BINDING_NOT_FOUND"


def test_ready_outcome_has_aligned_session_and_anchor_continuation(tmp_path: Path) -> None:
    sync_input = _ready_input(tmp_path)

    outcome = synchronize_session(sync_input)

    assert isinstance(outcome, SynchronizationOutcome)
    assert outcome.report.disposition is SynchronizationDisposition.READY
    assert outcome.report.can_continue_to_anchor_availability is True
    assert outcome.report.formal_run_authorized is False
    assert outcome.aligned_session is not None
    assert set(outcome.aligned_session.streams) == {
        "X",
        "U",
        "I",
        "G",
        "EEG",
        "ECG",
        "pilot_camera",
    }
    assert outcome.report.synchronization_fingerprint == (
        outcome.aligned_session.synchronization_fingerprint
    )


def test_x_is_mapped_once_and_d011_shared_xu_views_remain_identical(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_input = _ready_input(tmp_path)
    calls = 0
    original = service.map_point_artifact

    def count(
        frame: pl.DataFrame,
        binding: PointBinding,
        clock: ClockSync,
    ) -> pl.DataFrame:
        nonlocal calls
        if getattr(binding, "expected_artifact_schema_id", None) == "flight-state-normalized-v0.1":
            calls += 1
        return original(frame, binding, clock)

    monkeypatch.setattr(service, "map_point_artifact", count)

    outcome = synchronize_session(sync_input)

    assert calls == 1
    assert outcome.aligned_session is not None
    x = outcome.aligned_session.streams["X"].tables["samples"]
    u = outcome.aligned_session.streams["U"].tables["samples"]
    columns = ["source_row_index", "source_time_s", "t_ns", "in_session"]
    assert x.select(columns).equals(u.select(columns))


def test_same_clock_mapping_keeps_independent_residual_evidence(tmp_path: Path) -> None:
    sync_input = _ready_input(tmp_path)
    bundle = sync_input.loaded_manifest.bundle_root
    _set_clock(
        bundle,
        "U",
        clock_id="sim_clock",
        scale=1.0,
        drift_ppm=0.0,
        residual_rms_ms=1.25,
        residual_max_ms=2.5,
    )

    outcome = synchronize_bundle(bundle)

    assert outcome.report.disposition is SynchronizationDisposition.READY
    x_clock = outcome.report.stream_results["X"].clock
    u_clock = outcome.report.stream_results["U"].clock
    assert x_clock is not None and u_clock is not None
    assert (x_clock.method, x_clock.scale, x_clock.offset_ns, x_clock.drift_ppm) == (
        u_clock.method,
        u_clock.scale,
        u_clock.offset_ns,
        u_clock.drift_ppm,
    )
    assert (u_clock.residual_rms_ms, u_clock.residual_max_ms) == (1.25, 2.5)


def test_global_issues_are_sorted_deterministically(tmp_path: Path) -> None:
    sync_input = _ready_input(tmp_path)
    changed_report = sync_input.readiness_report.model_copy(
        update={"global_issues": (_issue("Z_ISSUE", "z"), _issue("A_ISSUE", "a"))}
    )
    changed = SynchronizationInput(
        loaded_manifest=sync_input.loaded_manifest,
        readiness_report=changed_report,
        prepared_session=sync_input.prepared_session,
    )

    outcome = synchronize_session(changed)

    assert [issue.error_code for issue in outcome.report.global_issues] == [
        "A_ISSUE",
        "Z_ISSUE",
    ]


def test_unexpected_exception_is_bounded_and_never_leaks_raw_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_input = _ready_input(tmp_path)

    def explode(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("SECRET C:/participant/raw/path")

    monkeypatch.setattr(service, "align_annotations", explode)

    outcome = synchronize_session(sync_input)

    assert outcome.report.disposition is SynchronizationDisposition.BLOCKED
    assert outcome.aligned_session is None
    assert any(
        issue.error_code == "SYNCHRONIZATION_INTERNAL_ERROR"
        for issue in outcome.report.global_issues
    )
    serialized = outcome.report.model_dump_json()
    assert "SECRET" not in serialized
    assert "RuntimeError" not in serialized
    assert "participant/raw/path" not in serialized
    assert outcome.report.policy_fingerprint == fingerprint_policy(outcome.report.policy)
    assert outcome.report.binding_catalog_fingerprint == (builtin_temporal_catalog_fingerprint())


def test_unexpected_x_value_error_is_internal_not_session_window_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_input = _ready_input(tmp_path)
    original = service._aligned_core_result

    def explode_x(
        item: StreamReadinessResult,
        descriptor: StreamDescriptor,
        work: service._AlignedWork,
        *,
        scene_gaze_metrics: SceneGazeMetrics | None = None,
    ) -> StreamSynchronizationResult:
        if item.modality == "X":
            raise ValueError("SECRET unexpected X constructor failure")
        return original(
            item,
            descriptor,
            work,
            scene_gaze_metrics=scene_gaze_metrics,
        )

    monkeypatch.setattr(service, "_aligned_core_result", explode_x)

    outcome = synchronize_session(sync_input)

    assert outcome.report.disposition is SynchronizationDisposition.BLOCKED
    assert outcome.aligned_session is None
    assert any(
        issue.error_code == "SYNCHRONIZATION_INTERNAL_ERROR"
        for issue in outcome.report.global_issues
    )
    assert not any(
        issue.error_code == "SESSION_WINDOW_UNAVAILABLE"
        for issue in outcome.report.stream_results["X"].issues
    )
    assert "SECRET" not in outcome.report.model_dump_json()


def test_downstream_session_window_error_text_collision_is_internal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_input = _ready_input(tmp_path)
    original = service._aligned_core_result

    def collide(
        item: StreamReadinessResult,
        descriptor: StreamDescriptor,
        work: service._AlignedWork,
        *,
        scene_gaze_metrics: SceneGazeMetrics | None = None,
    ) -> StreamSynchronizationResult:
        if item.modality == "X":
            raise ValueError("SESSION_WINDOW_UNAVAILABLE")
        return original(
            item,
            descriptor,
            work,
            scene_gaze_metrics=scene_gaze_metrics,
        )

    monkeypatch.setattr(service, "_aligned_core_result", collide)

    outcome = synchronize_session(sync_input)

    assert outcome.report.disposition is SynchronizationDisposition.BLOCKED
    assert outcome.aligned_session is None
    assert any(
        issue.error_code == "SYNCHRONIZATION_INTERNAL_ERROR"
        for issue in outcome.report.global_issues
    )
    assert not any(
        issue.error_code == "SESSION_WINDOW_UNAVAILABLE"
        for issue in outcome.report.stream_results["X"].issues
    )


def test_unexpected_derive_window_value_error_is_internal_and_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_input = _ready_input(tmp_path)

    def explode(
        _sync_input: SynchronizationInput,
        _aligned_x: pl.DataFrame,
        _binding: PointBinding,
    ) -> NoReturn:
        raise ValueError("SECRET derive implementation bug")

    monkeypatch.setattr(service, "derive_session_window", explode)

    outcome = synchronize_session(sync_input)

    assert outcome.report.disposition is SynchronizationDisposition.BLOCKED
    assert outcome.aligned_session is None
    assert any(
        issue.error_code == "SYNCHRONIZATION_INTERNAL_ERROR"
        for issue in outcome.report.global_issues
    )
    assert not any(
        issue.error_code == "SESSION_WINDOW_UNAVAILABLE"
        for issue in outcome.report.stream_results["X"].issues
    )
    assert "SECRET" not in outcome.report.model_dump_json()


def test_declared_derive_window_unavailable_has_stable_item_issue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_input = _ready_input(tmp_path)

    def unavailable(
        _sync_input: SynchronizationInput,
        _aligned_x: pl.DataFrame,
        _binding: PointBinding,
    ) -> NoReturn:
        raise ValueError("SESSION_WINDOW_UNAVAILABLE")

    monkeypatch.setattr(service, "derive_session_window", unavailable)

    outcome = synchronize_session(sync_input)

    assert outcome.report.disposition is SynchronizationDisposition.BLOCKED
    assert outcome.aligned_session is None
    assert {issue.error_code for issue in outcome.report.stream_results["X"].issues} == {
        "SESSION_WINDOW_UNAVAILABLE"
    }
    assert not any(
        issue.error_code == "SYNCHRONIZATION_INTERNAL_ERROR"
        for issue in outcome.report.global_issues
    )


def test_annotation_source_change_uses_existing_second_digest_gate(tmp_path: Path) -> None:
    sync_input = _ready_input(tmp_path)
    phases = sync_input.loaded_manifest.manifest.annotations.phases
    path = sync_input.loaded_manifest.bundle_root.joinpath(*phases.split("/"))
    path.write_bytes(path.read_bytes() + b" ")

    outcome = synchronize_session(sync_input)

    assert outcome.report.disposition is SynchronizationDisposition.BLOCKED
    assert outcome.report.annotation_result is not None
    assert outcome.report.annotation_result.issues[0].error_code == (
        "SOURCE_CHANGED_DURING_SYNCHRONIZATION"
    )


def test_scene_gaze_structural_failure_is_optional_item_invalid_not_global_internal(
    tmp_path: Path,
) -> None:
    sync_input = _ready_input(tmp_path)
    gaze = sync_input.prepared_session.streams["G"].tables["gaze_samples"]
    bad_gaze = gaze.with_columns(pl.col("scene_frame_id").cast(pl.Int64))
    corrupted = _replace_stream_table(sync_input, "G", "gaze_samples", bad_gaze)

    outcome = synchronize_session(corrupted)

    assert outcome.report.disposition is SynchronizationDisposition.READY_PARTIAL
    assert outcome.aligned_session is not None
    assert "G" not in outcome.aligned_session.streams
    result = outcome.report.stream_results["G"]
    assert result.synchronization_status is SynchronizationItemStatus.INVALID
    assert result.issues[0].error_code == "TEMPORAL_PARENT_KEY_INVALID"
    assert not any(
        issue.error_code == "SYNCHRONIZATION_INTERNAL_ERROR"
        for issue in outcome.report.global_issues
    )


def test_fingerprint_helper_exception_still_returns_bounded_emergency_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync_input = _ready_input(tmp_path)

    def explode(**_kwargs: object) -> str:
        raise RuntimeError("SECRET fingerprint implementation path")

    monkeypatch.setattr(service, "fingerprint_synchronization", explode)

    outcome = synchronize_session(sync_input)

    assert outcome.report.disposition is SynchronizationDisposition.BLOCKED
    assert outcome.aligned_session is None
    assert any(
        issue.error_code == "SYNCHRONIZATION_INTERNAL_ERROR"
        for issue in outcome.report.global_issues
    )
    serialized = outcome.report.model_dump_json()
    assert "SECRET" not in serialized
    assert "RuntimeError" not in serialized


@pytest.mark.parametrize(
    ("readiness", "expected"),
    [
        (StreamReadiness.READY, SynchronizationItemStatus.NOT_ATTEMPTED),
        (StreamReadiness.UNAVAILABLE, SynchronizationItemStatus.UNAVAILABLE),
        (StreamReadiness.INVALID, SynchronizationItemStatus.INVALID),
        (StreamReadiness.UNSUPPORTED, SynchronizationItemStatus.UNSUPPORTED),
        (StreamReadiness.NOT_APPLICABLE, SynchronizationItemStatus.NOT_APPLICABLE),
    ],
)
def test_item_status_from_readiness_maps_unattempted_inventory(
    readiness: StreamReadiness,
    expected: SynchronizationItemStatus,
) -> None:
    assert _item_status_from_readiness(readiness, attempted=False) is expected


def test_item_status_requires_explicit_result_after_ready_attempt() -> None:
    with pytest.raises(ValueError, match="explicit M3 result"):
        _item_status_from_readiness(StreamReadiness.READY, attempted=True)


def _minimal_stream_result(
    modality: str,
    *,
    required: bool,
    status: SynchronizationItemStatus,
) -> StreamSynchronizationResult:
    return StreamSynchronizationResult.model_construct(
        modality=modality,
        required_for_import=required,
        synchronization_status=status,
    )


def _minimal_annotation(
    status: SynchronizationItemStatus,
) -> AnnotationSynchronizationResult:
    return AnnotationSynchronizationResult.model_construct(synchronization_status=status)


def test_derive_disposition_direct_branch_matrix() -> None:
    from pilot_assessment.contracts.synchronization import SessionWindow

    window = SessionWindow(
        end_t_ns=1,
        source="master-clock-x-mapped-coverage-v1",
    )
    aligned = {
        "X": _minimal_stream_result("X", required=True, status=SynchronizationItemStatus.ALIGNED),
        "I": _minimal_stream_result("I", required=False, status=SynchronizationItemStatus.ALIGNED),
    }
    annotations = _minimal_annotation(SynchronizationItemStatus.ALIGNED)
    assert (
        _derive_disposition(
            session_window=window,
            streams=aligned,
            task_reference=None,
            annotations=annotations,
            global_issues=(),
        )
        is SynchronizationDisposition.READY
    )

    optional_failed = {
        **aligned,
        "I": _minimal_stream_result("I", required=False, status=SynchronizationItemStatus.INVALID),
    }
    assert (
        _derive_disposition(
            session_window=window,
            streams=optional_failed,
            task_reference=None,
            annotations=annotations,
            global_issues=(),
        )
        is SynchronizationDisposition.READY_PARTIAL
    )

    required_failed = {
        **aligned,
        "X": _minimal_stream_result("X", required=True, status=SynchronizationItemStatus.INVALID),
    }
    assert (
        _derive_disposition(
            session_window=window,
            streams=required_failed,
            task_reference=None,
            annotations=annotations,
            global_issues=(),
        )
        is SynchronizationDisposition.BLOCKED
    )
    assert (
        _derive_disposition(
            session_window=None,
            streams=aligned,
            task_reference=None,
            annotations=annotations,
            global_issues=(),
        )
        is SynchronizationDisposition.BLOCKED
    )
    assert (
        _derive_disposition(
            session_window=window,
            streams=aligned,
            task_reference=None,
            annotations=_minimal_annotation(SynchronizationItemStatus.INVALID),
            global_issues=(),
        )
        is SynchronizationDisposition.BLOCKED
    )
    blocking_issue = _issue("SYNCHRONIZATION_INTERNAL_ERROR", "service")
    assert (
        _derive_disposition(
            session_window=window,
            streams=aligned,
            task_reference=None,
            annotations=annotations,
            global_issues=(blocking_issue,),
        )
        is SynchronizationDisposition.BLOCKED
    )

    optional_reference = TaskReferenceSynchronizationResult.model_construct(
        source="bundle",
        required_for_import=False,
        synchronization_status=SynchronizationItemStatus.INVALID,
    )
    assert (
        _derive_disposition(
            session_window=window,
            streams=aligned,
            task_reference=optional_reference,
            annotations=annotations,
            global_issues=(),
        )
        is SynchronizationDisposition.READY_PARTIAL
    )
    deferred_reference = TaskReferenceSynchronizationResult.model_construct(
        source="model_bundle",
        synchronization_status=SynchronizationItemStatus.DEFERRED_MODEL_BUNDLE_RESOLUTION,
    )
    assert (
        _derive_disposition(
            session_window=window,
            streams=aligned,
            task_reference=deferred_reference,
            annotations=annotations,
            global_issues=(),
        )
        is SynchronizationDisposition.READY
    )
