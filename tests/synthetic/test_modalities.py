from __future__ import annotations

import hashlib
from pathlib import Path
from typing import cast

import polars as pl
import pytest
from PIL import Image

from pilot_assessment.synthetic.modalities import (
    build_annotations,
    build_ecg,
    build_eeg,
    build_gaze,
    build_pilot_camera,
    build_scene,
    build_task_reference,
    write_rgb8_png,
)
from pilot_assessment.synthetic.prng import float32, triangular_noise


def test_scene_gaze_and_camera_tables_have_frozen_rates_and_foreign_keys() -> None:
    scene = build_scene(duration_s=2.0, seed=20260711)
    gaze = build_gaze(duration_s=2.0, seed=20260711, scene=scene)
    camera = build_pilot_camera(duration_s=2.0, seed=20260711)

    assert scene.frame_index.height == 61
    assert scene.aoi_instances.height == 122
    assert scene.frame_index.schema["frame_id"] == pl.UInt64
    assert scene.frame_index.schema["head_qw"] == pl.Float32
    assert set(scene.aoi_instances["frame_id"]) <= set(scene.frame_index["frame_id"])
    assert scene.aoi_instances.select("frame_id", "aoi_id").equals(
        scene.aoi_instances.sort("frame_id", "aoi_id").select("frame_id", "aoi_id")
    )
    assert gaze.samples.height == 241
    assert gaze.samples.schema["viewport_x_norm"] == pl.Float32
    assert set(gaze.samples["scene_frame_id"]) <= set(scene.frame_index["frame_id"])
    assert set(gaze.samples["assigned_aoi_id"].drop_nulls()) <= {
        "primary_flight_display",
        "outside_view",
    }
    fixation_end = gaze.fixations["end_source_timestamp_s"].max()
    assert isinstance(fixation_end, (int, float))
    assert fixation_end <= 2.0
    assert camera.height == 31
    assert camera.schema["image_path"] == pl.String
    assert camera["privacy_class"].unique().to_list() == ["synthetic-no-identity"]


def test_fixations_end_on_the_retained_gaze_grid_for_fractional_duration() -> None:
    scene = build_scene(duration_s=29.01, seed=20260711)
    gaze = build_gaze(duration_s=29.01, seed=20260711, scene=scene)

    assert gaze.fixations["end_source_timestamp_s"].max() == pytest.approx(
        gaze.samples["source_timestamp_s"].max()
    )


def test_gaze_frame_binding_uses_exact_rate_indices_at_scene_boundaries() -> None:
    scene = build_scene(duration_s=29.01, seed=20260711)
    gaze = build_gaze(duration_s=29.01, seed=20260711, scene=scene)

    boundary = gaze.samples.filter(pl.col("gaze_sample_id") == 492).row(0, named=True)
    assert boundary["source_timestamp_s"] == 4.1
    assert boundary["scene_frame_id"] == 123

    expected = [
        min((sample_id * 30) // 120, scene.frame_index.height - 1)
        for sample_id in gaze.samples["gaze_sample_id"].to_list()
    ]
    assert gaze.samples["scene_frame_id"].to_list() == expected


def test_eeg_and_ecg_are_deterministic_typed_and_explicitly_synthetic() -> None:
    first_eeg = build_eeg(duration_s=2.0, seed=20260711)
    second_eeg = build_eeg(duration_s=2.0, seed=20260711)
    ecg = build_ecg(duration_s=2.0, seed=20260711, control_activity=0.5)

    assert first_eeg.samples.equals(second_eeg.samples)
    assert first_eeg.samples.height == 513
    assert first_eeg.samples.schema["Fp1_uV"] == pl.Float32
    assert first_eeg.sidecar["channel_order"] == [
        "Fp1",
        "Fp2",
        "F3",
        "F4",
        "C3",
        "C4",
        "P3",
        "P4",
    ]
    assert first_eeg.sidecar["synthetic_not_neurophysiological"] is True
    assert ecg.samples.height == 501
    assert ecg.samples.schema["synthetic_lead_ii_mV"] == pl.Float32
    assert ecg.sidecar["synthetic_not_physiological"] is True
    peak_end = ecg.r_peaks["source_timestamp_s"].max()
    assert isinstance(peak_end, (int, float))
    assert peak_end <= 2.0


def test_eeg_and_ecg_follow_interpolated_time_varying_synthetic_driver() -> None:
    source_times = tuple(index / 100.0 for index in range(801))
    activity = tuple(0.0 if time < 4.0 else 1.0 for time in source_times)

    eeg = build_eeg(
        duration_s=8.0,
        seed=20260711,
        control_source_times_s=source_times,
        control_activity=activity,
    )
    repeated_eeg = build_eeg(
        duration_s=8.0,
        seed=20260711,
        control_source_times_s=source_times,
        control_activity=activity,
    )
    ecg = build_ecg(
        duration_s=8.0,
        seed=20260711,
        control_source_times_s=source_times,
        control_activity=activity,
    )
    repeated_ecg = build_ecg(
        duration_s=8.0,
        seed=20260711,
        control_source_times_s=source_times,
        control_activity=activity,
    )

    assert eeg.samples.equals(repeated_eeg.samples)
    assert ecg.samples.equals(repeated_ecg.samples)
    assert ecg.r_peaks.equals(repeated_ecg.r_peaks)
    assert eeg.samples.schema["Fp1_uV"] == pl.Float32
    assert ecg.r_peaks.schema["rr_interval_ms"] == pl.Float32
    assert eeg.sidecar["synthetic_not_neurophysiological"] is True
    assert ecg.sidecar["synthetic_not_physiological"] is True

    low_eeg = eeg.samples.filter(pl.col("source_timestamp_s").is_between(1.0, 3.0, closed="both"))[
        "Fp1_uV"
    ]
    high_eeg = eeg.samples.filter(pl.col("source_timestamp_s").is_between(5.0, 7.0, closed="both"))[
        "Fp1_uV"
    ]
    low_rms = float((low_eeg.cast(pl.Float64).pow(2).mean()) ** 0.5)
    high_rms = float((high_eeg.cast(pl.Float64).pow(2).mean()) ** 0.5)
    assert high_rms > 2.0 * low_rms

    low_rr = ecg.r_peaks.filter(pl.col("source_timestamp_s") < 3.5)["rr_interval_ms"]
    high_rr = ecg.r_peaks.filter(pl.col("source_timestamp_s") > 4.5)["rr_interval_ms"]
    assert low_rr.len() >= 3
    assert high_rr.len() >= 3
    assert float(low_rr.mean()) == pytest.approx(60_000.0 / 70.0, abs=1.0)
    assert float(high_rr.mean()) == pytest.approx(60_000.0 / 90.0, abs=1.0)


def test_synthetic_driver_trace_is_linearly_interpolated_on_the_eeg_grid() -> None:
    eeg = build_eeg(
        duration_s=2.0,
        seed=20260711,
        control_source_times_s=(0.0, 1.0, 2.0),
        control_activity=(0.0, 1.0, 0.0),
    )

    # At t=0.53125 s (sample 136), activity is 0.53125 and the 8 Hz carrier is +1.
    expected = float32(8.0 + 12.0 * 0.53125 + 1.5 * triangular_noise(20260711, "EEG", "Fp1", 136))
    assert eeg.samples["Fp1_uV"][136] == expected


def test_reference_and_annotations_have_stable_software_test_semantics() -> None:
    reference = build_task_reference(
        source_times_s=(0.0, 0.01, 0.02),
        source_x_m=(0.0, 0.1, 0.2),
    )
    annotations = build_annotations(duration_s=2.0, seed=20260711)

    assert reference.schema["reference_sample_id"] == pl.UInt64
    assert reference["target_x_m"].to_list() == pytest.approx([0.0, 0.1, 0.2])
    assert (
        reference["envelope_profile_id"].to_list() == ["synthetic-format-fixture-envelope-v0.1"] * 3
    )
    assert set(annotations) == {"phases", "events", "baseline_intervals"}
    assert annotations["phases"]["synthetic_semantics_unvalidated"] is True
    phases = cast(list[dict[str, object]], annotations["phases"]["phases"])
    assert [phase["phase_id"] for phase in phases] == [
        "translation",
        "deceleration",
        "hover_stabilization",
    ]
    assert phases[-1]["end_s"] == 2.0
    events = cast(list[dict[str, object]], annotations["events"]["events"])
    assert [event["event_type"] for event in events] == ["disturbance", "attention_cue"]


def test_png_writer_is_byte_deterministic_rgb8_and_metadata_free(tmp_path: Path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    write_rgb8_png(first, width=64, height=36, seed=20260711, modality="I", index=3)
    write_rgb8_png(second, width=64, height=36, seed=20260711, modality="I", index=3)

    assert (
        hashlib.sha256(first.read_bytes()).digest() == hashlib.sha256(second.read_bytes()).digest()
    )
    with Image.open(first) as image:
        assert image.mode == "RGB"
        assert image.size == (64, 36)
        assert getattr(image, "n_frames", 1) == 1
        assert image.info == {}
