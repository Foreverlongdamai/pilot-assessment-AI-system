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


def test_scene_gaze_and_camera_tables_have_frozen_rates_and_foreign_keys() -> None:
    scene = build_scene(duration_s=2.0, seed=20260711)
    gaze = build_gaze(duration_s=2.0, seed=20260711, scene=scene)
    camera = build_pilot_camera(duration_s=2.0, seed=20260711)

    assert scene.frame_index.height == 61
    assert scene.aoi_instances.height == 122
    assert scene.frame_index.schema["frame_id"] == pl.UInt64
    assert scene.frame_index.schema["head_qw"] == pl.Float32
    assert set(scene.aoi_instances["frame_id"]) <= set(scene.frame_index["frame_id"])
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


def test_reference_and_annotations_have_stable_software_test_semantics() -> None:
    reference = build_task_reference(
        source_times_s=(0.0, 0.01, 0.02),
        source_x_m=(0.0, 0.1, 0.2),
    )
    annotations = build_annotations(duration_s=2.0, seed=20260711)

    assert reference.schema["reference_sample_id"] == pl.UInt64
    assert reference["target_x_m"].to_list() == pytest.approx([0.0, 0.1, 0.2])
    assert set(annotations) == {"phases", "events", "baseline_intervals"}
    assert annotations["phases"]["synthetic_semantics_unvalidated"] is True
    phases = cast(list[dict[str, object]], annotations["phases"]["phases"])
    assert [phase["phase_id"] for phase in phases] == [
        "translation",
        "deceleration",
        "hover_stabilization",
    ]
    assert phases[-1]["end_s"] == 2.0


def test_png_writer_is_byte_deterministic_rgb8_and_metadata_free(tmp_path: Path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    write_rgb8_png(first, width=64, height=36, seed=20260711, modality="I", index=3)
    write_rgb8_png(second, width=64, height=36, seed=20260711, modality="I", index=3)

    assert hashlib.sha256(first.read_bytes()).digest() == hashlib.sha256(
        second.read_bytes()
    ).digest()
    with Image.open(first) as image:
        assert image.mode == "RGB"
        assert image.size == (64, 36)
        assert getattr(image, "n_frames", 1) == 1
        assert image.info == {}
