from __future__ import annotations

import hashlib
from importlib.resources import files
from typing import cast

import pytest
from pydantic import ValidationError

from pilot_assessment.ingestion.profiles import (
    CompositeProfile,
    TableProfile,
    load_builtin_profiles,
)
from pilot_assessment.synchronization import profiles as temporal_profiles
from pilot_assessment.synchronization.profiles import (
    InheritBinding,
    IntervalBinding,
    PointBinding,
    TemporalBindingCatalog,
    TemporalCatalogLoadError,
    TemporalStreamProfile,
    UntimedBinding,
    builtin_temporal_catalog_fingerprint,
    load_builtin_temporal_catalog,
    parse_temporal_binding_catalog,
)

EXPECTED_STREAM_ALIGNED_SCHEMAS = {
    "flight-state-normalized-v0.1": "flight-state-aligned-v0.1",
    "control-input-normalized-v0.1": "control-input-aligned-v0.1",
    "vr-scene-source-bundle-v0.1": "vr-scene-aligned-v0.1",
    "gaze-source-bundle-v0.1": "gaze-aligned-v0.1",
    "eeg-source-bundle-v0.1": "eeg-aligned-v0.1",
    "ecg-source-bundle-v0.1": "ecg-aligned-v0.1",
    "pilot-camera-source-bundle-v0.1": "pilot-camera-aligned-v0.1",
    "task-reference-normalized-v0.1": "task-reference-path-aligned-v0.1",
}

EXPECTED_BINDINGS = {
    ("flight-state-normalized-v0.1", "samples"): (
        "point",
        "flight-state-normalized-v0.1",
        "flight-state-aligned-v0.1",
        "source_time_s",
        ("source_row_index",),
    ),
    ("control-input-normalized-v0.1", "samples"): (
        "point",
        "control-input-normalized-v0.1",
        "control-input-aligned-v0.1",
        "source_time_s",
        ("source_row_index",),
    ),
    ("vr-scene-source-bundle-v0.1", "frame_index"): (
        "point",
        "vr-frame-index-raw-v0.1",
        "vr-frame-index-aligned-v0.1",
        "source_timestamp_s",
        ("frame_id",),
    ),
    ("vr-scene-source-bundle-v0.1", "aoi_instances"): (
        "inherit",
        "vr-aoi-instance-raw-v0.1",
        "vr-aoi-instance-aligned-v0.1",
        "frame_index",
        ("frame_id", "aoi_id"),
    ),
    ("vr-scene-source-bundle-v0.1", "frame_images"): (
        "untimed",
        "png-rgb8-v0.1",
        None,
        None,
        None,
    ),
    ("gaze-source-bundle-v0.1", "gaze_samples"): (
        "point",
        "gaze-sample-raw-v0.1",
        "gaze-sample-aligned-v0.1",
        "source_timestamp_s",
        ("gaze_sample_id",),
    ),
    ("gaze-source-bundle-v0.1", "fixations"): (
        "interval",
        "gaze-fixation-raw-v0.1",
        "gaze-fixation-aligned-v0.1",
        ("start_source_timestamp_s", "end_source_timestamp_s"),
        ("fixation_id",),
    ),
    ("eeg-source-bundle-v0.1", "samples"): (
        "point",
        "eeg-sample-raw-v0.1",
        "eeg-sample-aligned-v0.1",
        "source_timestamp_s",
        ("sample_index",),
    ),
    ("eeg-source-bundle-v0.1", "sidecar"): (
        "untimed",
        "eeg-sidecar-v0.1",
        None,
        None,
        None,
    ),
    ("ecg-source-bundle-v0.1", "samples"): (
        "point",
        "ecg-sample-raw-v0.1",
        "ecg-sample-aligned-v0.1",
        "source_timestamp_s",
        ("sample_index",),
    ),
    ("ecg-source-bundle-v0.1", "r_peaks"): (
        "point",
        "ecg-r-peak-raw-v0.1",
        "ecg-r-peak-aligned-v0.1",
        "source_timestamp_s",
        ("peak_id",),
    ),
    ("pilot-camera-source-bundle-v0.1", "frame_index"): (
        "point",
        "pilot-camera-frame-index-raw-v0.1",
        "pilot-camera-frame-index-aligned-v0.1",
        "source_timestamp_s",
        ("frame_id",),
    ),
    ("pilot-camera-source-bundle-v0.1", "frame_images"): (
        "untimed",
        "png-rgb8-v0.1",
        None,
        None,
        None,
    ),
    ("task-reference-normalized-v0.1", "commanded_path"): (
        "point",
        "task-reference-path-raw-v0.1",
        "task-reference-path-aligned-v0.1",
        "source_timestamp_s",
        ("reference_sample_id",),
    ),
}


def test_builtin_temporal_catalog_covers_every_m2_artifact_role() -> None:
    catalog = load_builtin_temporal_catalog()
    assert set(catalog.streams_by_schema) == set(EXPECTED_STREAM_ALIGNED_SCHEMAS)
    actual_roles = {
        (profile.stream_schema_id, binding.artifact_role)
        for profile in catalog.streams
        for binding in profile.bindings
    }
    assert actual_roles == set(EXPECTED_BINDINGS)
    assert (
        sum(
            binding.mode != "untimed" for profile in catalog.streams for binding in profile.bindings
        )
        == 11
    )
    assert (
        sum(
            binding.mode == "untimed" for profile in catalog.streams for binding in profile.bindings
        )
        == 3
    )


def test_task_reference_binding_uses_commanded_path_role_from_m2() -> None:
    profile = load_builtin_temporal_catalog().streams_by_schema["task-reference-normalized-v0.1"]
    assert profile.bindings_by_role["commanded_path"].expected_artifact_schema_id == (
        "task-reference-path-raw-v0.1"
    )


def test_temporal_catalog_freezes_every_binding_and_aligned_stream_schema() -> None:
    catalog = load_builtin_temporal_catalog()
    assert {
        profile.stream_schema_id: profile.aligned_stream_schema_id for profile in catalog.streams
    } == EXPECTED_STREAM_ALIGNED_SCHEMAS

    for (schema_id, role), expected in EXPECTED_BINDINGS.items():
        binding = catalog.streams_by_schema[schema_id].bindings_by_role[role]
        assert binding.mode == expected[0]
        assert binding.expected_artifact_schema_id == expected[1]
        if isinstance(binding, PointBinding):
            assert (
                binding.aligned_artifact_schema_id,
                binding.source_timestamp_column,
                binding.stable_keys,
            ) == (expected[2], expected[3], expected[4])
            assert binding.target_timestamp_column == "t_ns"
            assert binding.in_session_column == "in_session"
        elif isinstance(binding, IntervalBinding):
            assert (
                binding.aligned_artifact_schema_id,
                (binding.source_start_column, binding.source_end_column),
                binding.stable_keys,
            ) == (expected[2], expected[3], expected[4])
            assert binding.target_start_column == "start_t_ns"
            assert binding.target_end_column == "end_t_ns"
            assert binding.overlaps_session_column == "overlaps_session"
            assert binding.fully_in_session_column == "fully_in_session"
        elif isinstance(binding, InheritBinding):
            assert (
                binding.aligned_artifact_schema_id,
                binding.parent_role,
                binding.stable_keys,
            ) == (expected[2], expected[3], expected[4])
            assert binding.parent_key_columns == ("frame_id",)
            assert binding.foreign_key_columns == ("frame_id",)
            assert binding.target_timestamp_column == "t_ns"
            assert binding.in_session_column == "in_session"
        else:
            assert isinstance(binding, UntimedBinding)
            assert not hasattr(binding, "aligned_artifact_schema_id")


def test_temporal_catalog_matches_m2_profile_artifact_roles() -> None:
    temporal = load_builtin_temporal_catalog()
    m2 = load_builtin_profiles()

    composite_schema_ids = {
        "vr-scene-source-bundle-v0.1",
        "gaze-source-bundle-v0.1",
        "eeg-source-bundle-v0.1",
        "ecg-source-bundle-v0.1",
        "pilot-camera-source-bundle-v0.1",
    }
    for schema_id in composite_schema_ids:
        m2_profile = m2[schema_id]
        assert isinstance(m2_profile, CompositeProfile)
        bindings = temporal.streams_by_schema[schema_id].bindings_by_role
        assert set(bindings) == set(m2_profile.artifact_roles)
        assert {
            role: binding.expected_artifact_schema_id for role, binding in bindings.items()
        } == {role: artifact.schema_id for role, artifact in m2_profile.artifact_roles.items()}

    for schema_id in ("flight-state-normalized-v0.1", "control-input-normalized-v0.1"):
        binding = temporal.streams_by_schema[schema_id].bindings_by_role["samples"]
        assert binding.expected_artifact_schema_id == schema_id

    task_reference = m2["task-reference-path-raw-v0.1"]
    assert isinstance(task_reference, TableProfile)
    reference_binding = temporal.streams_by_schema[
        "task-reference-normalized-v0.1"
    ].bindings_by_role["commanded_path"]
    assert reference_binding.expected_artifact_schema_id == task_reference.schema_id


def _point_binding() -> dict[str, object]:
    return {
        "mode": "point",
        "artifact_role": "samples",
        "expected_artifact_schema_id": "fixture-raw-v0.1",
        "aligned_artifact_schema_id": "fixture-aligned-v0.1",
        "source_timestamp_column": "source_timestamp_s",
        "stable_keys": ["sample_id"],
    }


def test_catalog_rejects_duplicate_stream_schema_ids_and_binding_roles() -> None:
    stream = {
        "stream_schema_id": "fixture-source-v0.1",
        "aligned_stream_schema_id": "fixture-aligned-v0.1",
        "bindings": [_point_binding()],
    }
    with pytest.raises(ValidationError, match="stream schema IDs must be non-empty and unique"):
        TemporalBindingCatalog.model_validate(
            {"catalog_version": "0.1.0", "streams": [stream, stream]}
        )

    duplicated_binding_stream = {**stream, "bindings": [_point_binding(), _point_binding()]}
    with pytest.raises(ValidationError, match="binding roles must be non-empty and unique"):
        TemporalStreamProfile.model_validate(duplicated_binding_stream)


def test_binding_models_reject_bad_keys_and_non_aligned_output_ids() -> None:
    with pytest.raises(ValidationError, match="stable_keys must be non-empty and unique"):
        PointBinding.model_validate({**_point_binding(), "stable_keys": []})
    with pytest.raises(ValidationError, match="must end with -aligned-v0.1"):
        PointBinding.model_validate(
            {**_point_binding(), "aligned_artifact_schema_id": "fixture-output-v0.1"}
        )
    with pytest.raises(ValidationError, match="non-empty, unique, and paired"):
        InheritBinding.model_validate(
            {
                "mode": "inherit",
                "artifact_role": "children",
                "expected_artifact_schema_id": "child-raw-v0.1",
                "aligned_artifact_schema_id": "child-aligned-v0.1",
                "parent_role": "parent",
                "parent_key_columns": ["parent_id"],
                "foreign_key_columns": [],
                "stable_keys": ["parent_id", "child_id"],
            }
        )


def test_catalog_has_no_unknown_schema_or_role_fallback_and_lookups_are_immutable() -> None:
    catalog = load_builtin_temporal_catalog()
    with pytest.raises(KeyError):
        _ = catalog.streams_by_schema["flight-state-typo-v0.1"]
    with pytest.raises(KeyError):
        _ = catalog.streams_by_schema["flight-state-normalized-v0.1"].bindings_by_role["sample"]
    with pytest.raises(TypeError):
        cast(dict[str, object], catalog.streams_by_schema)["fallback-v0.1"] = object()
    bindings = catalog.streams_by_schema["flight-state-normalized-v0.1"].bindings_by_role
    with pytest.raises(TypeError):
        cast(dict[str, object], bindings)["fallback"] = object()


@pytest.mark.parametrize("mutation", ["extra", "missing"])
def test_builtin_cross_validation_requires_exact_runtime_stream_inventory(mutation: str) -> None:
    catalog = load_builtin_temporal_catalog()
    if mutation == "extra":
        invented = TemporalStreamProfile.model_validate(
            {
                "stream_schema_id": "invented-source-v0.1",
                "aligned_stream_schema_id": "invented-aligned-v0.1",
                "bindings": [_point_binding()],
            }
        )
        streams = (*catalog.streams, invented)
    else:
        streams = catalog.streams[:-1]
    mutated = catalog.model_copy(update={"streams": streams})

    with pytest.raises(
        TemporalCatalogLoadError,
        match="runtime stream schema IDs must exactly match",
    ):
        temporal_profiles._cross_validate_with_m2(mutated)


def test_builtin_loader_rejects_drift_in_packaged_m2_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authority = dict(load_builtin_profiles())
    scene = authority["vr-scene-source-bundle-v0.1"]
    assert isinstance(scene, CompositeProfile)
    roles = dict(scene.artifact_roles)
    roles["frame_index"] = roles["frame_index"].model_copy(
        update={"schema_id": "invented-frame-index-raw-v0.1"}
    )
    authority[scene.schema_id] = scene.model_copy(update={"artifact_roles": roles})
    monkeypatch.setattr(temporal_profiles, "load_builtin_profiles", lambda: authority)
    temporal_profiles._builtin_catalog.cache_clear()
    try:
        with pytest.raises(TemporalCatalogLoadError, match="roles disagree with M2 profile"):
            load_builtin_temporal_catalog()
    finally:
        temporal_profiles._builtin_catalog.cache_clear()


def test_catalog_parser_rejects_duplicate_keys_nan_and_non_utf8() -> None:
    payload = (
        files("pilot_assessment.synchronization.profile_data")
        .joinpath("m3-temporal-bindings-0.1.json")
        .read_bytes()
    )
    catalog_version = b'"catalog_version": "0.1.0",'
    duplicate = payload.replace(catalog_version, catalog_version + catalog_version, 1)
    with pytest.raises(
        TemporalCatalogLoadError,
        match="duplicate JSON key: catalog_version",
    ):
        parse_temporal_binding_catalog(duplicate)

    nan = payload.replace(b'"catalog_version": "0.1.0"', b'"catalog_version": NaN', 1)
    with pytest.raises(
        TemporalCatalogLoadError,
        match="non-standard JSON constant: NaN",
    ):
        parse_temporal_binding_catalog(nan)

    with pytest.raises(ValueError, match="invalid temporal binding catalog"):
        parse_temporal_binding_catalog(b"\xff")


def test_builtin_temporal_catalog_fingerprint_hashes_exact_packaged_bytes() -> None:
    payload = (
        files("pilot_assessment.synchronization.profile_data")
        .joinpath("m3-temporal-bindings-0.1.json")
        .read_bytes()
    )
    fingerprint = hashlib.sha256(payload).hexdigest()
    assert builtin_temporal_catalog_fingerprint() == fingerprint
    assert fingerprint == "1f5b23aad8dc11c3a58ffe42bfdc4f0f90d155107a07c1fab37d5aac54159250"
