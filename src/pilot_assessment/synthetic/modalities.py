"""Deterministic synthetic modality fixtures for software workflow validation only."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import polars as pl
from PIL import Image, ImageDraw
from pydantic import JsonValue

from pilot_assessment.synthetic.prng import float32, triangular_noise, uniform53
from pilot_assessment.synthetic.timelines import source_grid

_GENERATOR_ID = "synthetic-multimodal-generator-v0.1"
_EEG_CHANNELS = ("Fp1", "Fp2", "F3", "F4", "C3", "C4", "P3", "P4")


@dataclass(frozen=True, slots=True)
class SceneArtifacts:
    frame_index: pl.DataFrame
    aoi_instances: pl.DataFrame


@dataclass(frozen=True, slots=True)
class GazeArtifacts:
    samples: pl.DataFrame
    fixations: pl.DataFrame


@dataclass(frozen=True, slots=True)
class EegArtifacts:
    samples: pl.DataFrame
    sidecar: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class EcgArtifacts:
    samples: pl.DataFrame
    r_peaks: pl.DataFrame
    sidecar: dict[str, JsonValue]


def _phase_id(timestamp_s: float, duration_s: float) -> str:
    ratio = timestamp_s / duration_s
    if ratio < 0.35:
        return "translation"
    if ratio < 0.70:
        return "deceleration"
    return "hover_stabilization"


def _u64(name: str, values: list[int] | range) -> pl.Series:
    return pl.Series(name, values, dtype=pl.UInt64)


def _u32(name: str, values: list[int]) -> pl.Series:
    return pl.Series(name, values, dtype=pl.UInt32)


def _f64(name: str, values: tuple[float, ...] | list[float]) -> pl.Series:
    return pl.Series(name, values, dtype=pl.Float64)


def _f32(name: str, values: list[float]) -> pl.Series:
    return pl.Series(name, [float32(value) for value in values], dtype=pl.Float32)


def build_scene(*, duration_s: float, seed: int) -> SceneArtifacts:
    """Build 30 Hz first-person scene indices and two stable AOIs per frame."""

    times = source_grid(duration_s=duration_s, sample_rate_hz=30.0)
    count = len(times)
    frame_index = pl.DataFrame(
        {
            "frame_id": _u64("frame_id", range(count)),
            "source_timestamp_s": _f64("source_timestamp_s", times),
            "image_path": pl.Series(
                "image_path",
                [f"streams/vr_scene/frames/{index:06d}.png" for index in range(count)],
                dtype=pl.String,
            ),
            "width": _u32("width", [64] * count),
            "height": _u32("height", [36] * count),
            "head_x_m": _f32(
                "head_x_m", [0.01 * math.sin(0.7 * time) for time in times]
            ),
            "head_y_m": _f32("head_y_m", [0.0] * count),
            "head_z_m": _f32("head_z_m", [1.15] * count),
            "head_qx": _f32("head_qx", [0.0] * count),
            "head_qy": _f32("head_qy", [0.0] * count),
            "head_qz": _f32(
                "head_qz", [0.02 * math.sin(0.4 * time) for time in times]
            ),
            "head_qw": _f32(
                "head_qw",
                [
                    math.sqrt(max(0.0, 1.0 - (0.02 * math.sin(0.4 * time)) ** 2))
                    for time in times
                ],
            ),
            "horizontal_fov_deg": _f32("horizontal_fov_deg", [92.0] * count),
            "vertical_fov_deg": _f32("vertical_fov_deg", [58.0] * count),
            "phase_id": pl.Series(
                "phase_id", [_phase_id(time, duration_s) for time in times], dtype=pl.String
            ),
            "frame_valid": pl.Series("frame_valid", [True] * count, dtype=pl.Boolean),
            "generator_version": pl.Series(
                "generator_version", [_GENERATOR_ID] * count, dtype=pl.String
            ),
        }
    )

    aoi_ids = ("primary_flight_display", "outside_view")
    aoi_frames: list[int] = []
    aoi_names: list[str] = []
    for frame_id in range(count):
        for aoi_id in aoi_ids:
            aoi_frames.append(frame_id)
            aoi_names.append(aoi_id)
    aoi_count = len(aoi_frames)
    is_primary = [aoi_id == "primary_flight_display" for aoi_id in aoi_names]
    aoi_instances = pl.DataFrame(
        {
            "frame_id": _u64("frame_id", aoi_frames),
            "aoi_id": pl.Series("aoi_id", aoi_names, dtype=pl.String),
            "taxonomy_version": pl.Series(
                "taxonomy_version", ["synthetic-aoi-v0.1"] * aoi_count, dtype=pl.String
            ),
            "bbox_x_norm": _f32(
                "bbox_x_norm", [0.18 if primary else 0.58 for primary in is_primary]
            ),
            "bbox_y_norm": _f32(
                "bbox_y_norm", [0.42 if primary else 0.14 for primary in is_primary]
            ),
            "bbox_w_norm": _f32(
                "bbox_w_norm", [0.34 if primary else 0.36 for primary in is_primary]
            ),
            "bbox_h_norm": _f32(
                "bbox_h_norm", [0.42 if primary else 0.34 for primary in is_primary]
            ),
            "visible": pl.Series("visible", [True] * aoi_count, dtype=pl.Boolean),
            "confidence": _f32("confidence", [1.0] * aoi_count),
        }
    ).sort("frame_id", "aoi_id")
    return SceneArtifacts(frame_index=frame_index, aoi_instances=aoi_instances)


def build_gaze(
    *,
    duration_s: float,
    seed: int,
    scene: SceneArtifacts,
) -> GazeArtifacts:
    """Build 120 Hz gaze samples and deterministic half-second fixations."""

    times = source_grid(duration_s=duration_s, sample_rate_hz=120.0)
    count = len(times)
    last_frame_id = scene.frame_index.height - 1
    frame_ids = [min(int(time * 30.0), last_frame_id) for time in times]
    off_task = [int(time * 2.0) % 5 == 3 for time in times]
    x_values = [
        float32((0.72 if off else 0.35) + 0.015 * triangular_noise(seed, "G", "x", index))
        for index, off in enumerate(off_task)
    ]
    y_values = [
        float32((0.30 if off else 0.60) + 0.012 * triangular_noise(seed, "G", "y", index))
        for index, off in enumerate(off_task)
    ]
    rays: list[tuple[float, float, float]] = []
    for x_value, y_value in zip(x_values, y_values, strict=True):
        raw_x = (x_value - 0.5) * 0.7
        raw_y = (0.5 - y_value) * 0.5
        norm = math.sqrt(raw_x * raw_x + raw_y * raw_y + 1.0)
        rays.append((raw_x / norm, raw_y / norm, 1.0 / norm))

    samples = pl.DataFrame(
        {
            "gaze_sample_id": _u64("gaze_sample_id", range(count)),
            "source_timestamp_s": _f64("source_timestamp_s", times),
            "scene_frame_id": _u64("scene_frame_id", frame_ids),
            "viewport_x_norm": _f32("viewport_x_norm", x_values),
            "viewport_y_norm": _f32("viewport_y_norm", y_values),
            "origin_x_m": _f32("origin_x_m", [0.0] * count),
            "origin_y_m": _f32("origin_y_m", [0.0] * count),
            "origin_z_m": _f32("origin_z_m", [1.15] * count),
            "ray_x": _f32("ray_x", [ray[0] for ray in rays]),
            "ray_y": _f32("ray_y", [ray[1] for ray in rays]),
            "ray_z": _f32("ray_z", [ray[2] for ray in rays]),
            "left_pupil_mm": _f32(
                "left_pupil_mm",
                [
                    3.2 + 0.08 * triangular_noise(seed, "G", "left_pupil", index)
                    for index in range(count)
                ],
            ),
            "right_pupil_mm": _f32(
                "right_pupil_mm",
                [
                    3.2 + 0.08 * triangular_noise(seed, "G", "right_pupil", index)
                    for index in range(count)
                ],
            ),
            "binocular_valid": pl.Series(
                "binocular_valid", [True] * count, dtype=pl.Boolean
            ),
            "confidence": _f32("confidence", [0.98] * count),
            "blink": pl.Series(
                "blink", [index % 241 in {119, 120} for index in range(count)], dtype=pl.Boolean
            ),
            "assigned_aoi_id": pl.Series(
                "assigned_aoi_id",
                ["outside_view" if off else "primary_flight_display" for off in off_task],
                dtype=pl.String,
            ),
            "assignment_confidence": _f32("assignment_confidence", [0.96] * count),
        }
    )

    fixation_count = max(1, math.ceil(duration_s / 0.5))
    starts = [index * 0.5 for index in range(fixation_count)]
    ends = [min(duration_s, start + 0.5) for start in starts]
    fixation_off_task = [int(start * 2.0) % 5 == 3 for start in starts]
    fixations = pl.DataFrame(
        {
            "fixation_id": _u64("fixation_id", range(fixation_count)),
            "start_source_timestamp_s": _f64("start_source_timestamp_s", starts),
            "end_source_timestamp_s": _f64("end_source_timestamp_s", ends),
            "duration_ms": _f32(
                "duration_ms",
                [
                    (end - start) * 1000.0
                    for start, end in zip(starts, ends, strict=True)
                ],
            ),
            "centroid_x_norm": _f32(
                "centroid_x_norm", [0.72 if off else 0.35 for off in fixation_off_task]
            ),
            "centroid_y_norm": _f32(
                "centroid_y_norm", [0.30 if off else 0.60 for off in fixation_off_task]
            ),
            "ray_x": _f32("ray_x", [0.15 if off else -0.10 for off in fixation_off_task]),
            "ray_y": _f32("ray_y", [0.10 if off else -0.05 for off in fixation_off_task]),
            "ray_z": _f32("ray_z", [0.98] * fixation_count),
            "first_scene_frame_id": _u64(
                "first_scene_frame_id", [min(int(start * 30), last_frame_id) for start in starts]
            ),
            "last_scene_frame_id": _u64(
                "last_scene_frame_id", [min(int(end * 30), last_frame_id) for end in ends]
            ),
            "aoi_id": pl.Series(
                "aoi_id",
                ["outside_view" if off else "primary_flight_display" for off in fixation_off_task],
                dtype=pl.String,
            ),
            "fixation_valid": pl.Series(
                "fixation_valid", [True] * fixation_count, dtype=pl.Boolean
            ),
            "confidence": _f32("confidence", [0.95] * fixation_count),
            "detector_version": pl.Series(
                "detector_version", ["synthetic-fixation-v0.1"] * fixation_count, dtype=pl.String
            ),
        }
    )
    return GazeArtifacts(samples=samples, fixations=fixations)


def build_eeg(*, duration_s: float, seed: int) -> EegArtifacts:
    """Build deterministic 256 Hz multichannel software-test EEG-like data."""

    times = source_grid(duration_s=duration_s, sample_rate_hz=256.0)
    count = len(times)
    data: dict[str, pl.Series] = {
        "sample_index": _u64("sample_index", range(count)),
        "source_timestamp_s": _f64("source_timestamp_s", times),
    }
    for channel_index, channel in enumerate(_EEG_CHANNELS):
        frequency = 8.0 + channel_index * 0.75
        data[f"{channel}_uV"] = _f32(
            f"{channel}_uV",
            [
                12.0 * math.sin(2.0 * math.pi * frequency * time + channel_index * 0.2)
                + 1.5 * triangular_noise(seed, "EEG", channel, index)
                for index, time in enumerate(times)
            ],
        )
    data["signal_valid"] = pl.Series("signal_valid", [True] * count, dtype=pl.Boolean)
    data["artifact_code"] = pl.Series(
        "artifact_code", [None] * count, dtype=pl.String
    )
    sidecar: dict[str, JsonValue] = {
        "schema_id": "eeg-sidecar-v0.1",
        "montage_id": "synthetic-10-20-eight-channel-v0.1",
        "reference": "synthetic-common-average",
        "channel_order": list(_EEG_CHANNELS),
        "channel_units": {channel: "uV" for channel in _EEG_CHANNELS},
        "sample_rate_hz": 256.0,
        "clock_id": "eeg_clock",
        "generator_id": _GENERATOR_ID,
        "seed": seed,
        "synthetic_not_neurophysiological": True,
    }
    return EegArtifacts(samples=pl.DataFrame(data), sidecar=sidecar)


def build_ecg(
    *,
    duration_s: float,
    seed: int,
    control_activity: float,
) -> EcgArtifacts:
    """Build deterministic 250 Hz ECG-like data and derived synthetic R peaks."""

    if not 0.0 <= control_activity <= 1.0:
        raise ValueError("control_activity must be within [0, 1]")
    times = source_grid(duration_s=duration_s, sample_rate_hz=250.0)
    heart_rate_bpm = 70.0 + 20.0 * control_activity
    period_s = 60.0 / heart_rate_bpm
    values: list[float] = []
    for index, time in enumerate(times):
        phase = (time % period_s) / period_s
        r_wave = math.exp(-((phase - 0.08) / 0.018) ** 2)
        baseline = 0.08 * math.sin(2.0 * math.pi * 1.2 * time)
        noise = 0.008 * triangular_noise(seed, "ECG", "lead_ii", index)
        values.append(0.9 * r_wave + baseline + noise)
    count = len(times)
    samples = pl.DataFrame(
        {
            "sample_index": _u64("sample_index", range(count)),
            "source_timestamp_s": _f64("source_timestamp_s", times),
            "synthetic_lead_ii_mV": _f32("synthetic_lead_ii_mV", values),
            "signal_valid": pl.Series("signal_valid", [True] * count, dtype=pl.Boolean),
            "artifact_code": pl.Series(
                "artifact_code", [None] * count, dtype=pl.String
            ),
        }
    )
    peak_times: list[float] = []
    peak_time = 0.08 * period_s
    while peak_time <= duration_s:
        peak_times.append(peak_time)
        peak_time += period_s
    peak_count = len(peak_times)
    r_peaks = pl.DataFrame(
        {
            "peak_id": _u64("peak_id", range(peak_count)),
            "source_timestamp_s": _f64("source_timestamp_s", peak_times),
            "rr_interval_ms": _f32("rr_interval_ms", [period_s * 1000.0] * peak_count),
            "detection_confidence": _f32("detection_confidence", [1.0] * peak_count),
            "generator_version": pl.Series(
                "generator_version", [_GENERATOR_ID] * peak_count, dtype=pl.String
            ),
        }
    )
    return EcgArtifacts(
        samples=samples,
        r_peaks=r_peaks,
        sidecar={
            "schema_id": "synthetic-ecg-provenance-v0.1",
            "generator_id": _GENERATOR_ID,
            "seed": seed,
            "synthetic_not_physiological": True,
        },
    )


def build_pilot_camera(*, duration_s: float, seed: int) -> pl.DataFrame:
    """Build a 15 Hz index for geometric placeholder images with no identity."""

    del seed
    times = source_grid(duration_s=duration_s, sample_rate_hz=15.0)
    count = len(times)
    return pl.DataFrame(
        {
            "frame_id": _u64("frame_id", range(count)),
            "source_timestamp_s": _f64("source_timestamp_s", times),
            "image_path": pl.Series(
                "image_path",
                [f"streams/pilot_camera/frames/{index:06d}.png" for index in range(count)],
                dtype=pl.String,
            ),
            "width": _u32("width", [48] * count),
            "height": _u32("height", [48] * count),
            "head_bbox_x_norm": _f32("head_bbox_x_norm", [0.22] * count),
            "head_bbox_y_norm": _f32("head_bbox_y_norm", [0.10] * count),
            "head_bbox_w_norm": _f32("head_bbox_w_norm", [0.56] * count),
            "head_bbox_h_norm": _f32("head_bbox_h_norm", [0.80] * count),
            "left_eye_bbox_x_norm": _f32("left_eye_bbox_x_norm", [0.32] * count),
            "left_eye_bbox_y_norm": _f32("left_eye_bbox_y_norm", [0.36] * count),
            "left_eye_bbox_w_norm": _f32("left_eye_bbox_w_norm", [0.13] * count),
            "left_eye_bbox_h_norm": _f32("left_eye_bbox_h_norm", [0.08] * count),
            "right_eye_bbox_x_norm": _f32("right_eye_bbox_x_norm", [0.55] * count),
            "right_eye_bbox_y_norm": _f32("right_eye_bbox_y_norm", [0.36] * count),
            "right_eye_bbox_w_norm": _f32("right_eye_bbox_w_norm", [0.13] * count),
            "right_eye_bbox_h_norm": _f32("right_eye_bbox_h_norm", [0.08] * count),
            "frame_valid": pl.Series("frame_valid", [True] * count, dtype=pl.Boolean),
            "privacy_class": pl.Series(
                "privacy_class", ["synthetic-no-identity"] * count, dtype=pl.String
            ),
            "generator_version": pl.Series(
                "generator_version", [_GENERATOR_ID] * count, dtype=pl.String
            ),
        }
    )


def build_task_reference(
    *,
    source_times_s: tuple[float, ...],
    source_x_m: tuple[float, ...],
) -> pl.DataFrame:
    """Build a deterministic software-test commanded path on the X source grid."""

    if len(source_times_s) != len(source_x_m) or not source_times_s:
        raise ValueError("reference time and X arrays must have the same non-zero length")
    count = len(source_times_s)
    velocities = [0.0]
    velocities.extend(
        (right_x - left_x) / (right_t - left_t)
        for left_x, right_x, left_t, right_t in zip(
            source_x_m,
            source_x_m[1:],
            source_times_s,
            source_times_s[1:],
            strict=False,
        )
    )
    return pl.DataFrame(
        {
            "reference_sample_id": _u64("reference_sample_id", range(count)),
            "source_timestamp_s": _f64("source_timestamp_s", source_times_s),
            "target_x_m": _f32("target_x_m", list(source_x_m)),
            "target_y_m": _f32("target_y_m", [0.0] * count),
            "target_z_m": _f32("target_z_m", [-31.668] * count),
            "target_vx_m_s": _f32("target_vx_m_s", velocities),
            "target_vy_m_s": _f32("target_vy_m_s", [0.0] * count),
            "target_vz_m_s": _f32("target_vz_m_s", [0.0] * count),
            "target_roll_deg": _f32("target_roll_deg", [0.0] * count),
            "target_pitch_deg": _f32("target_pitch_deg", [0.0] * count),
            "target_yaw_deg": _f32("target_yaw_deg", [270.0] * count),
            "envelope_profile_id": pl.Series(
                "envelope_profile_id", ["synthetic-envelope-v0.1"] * count, dtype=pl.String
            ),
        }
    )


def build_annotations(*, duration_s: float, seed: int) -> dict[str, dict[str, JsonValue]]:
    """Build structural annotation fixtures whose semantics remain explicitly unvalidated."""

    common: dict[str, JsonValue] = {
        "generator_id": _GENERATOR_ID,
        "seed": seed,
        "synthetic_semantics_unvalidated": True,
    }
    phases: list[JsonValue] = [
        {"phase_id": "translation", "start_s": 0.0, "end_s": 0.35 * duration_s},
        {
            "phase_id": "deceleration",
            "start_s": 0.35 * duration_s,
            "end_s": 0.70 * duration_s,
        },
        {
            "phase_id": "hover_stabilization",
            "start_s": 0.70 * duration_s,
            "end_s": duration_s,
        },
    ]
    events: list[JsonValue] = [
        {"event_id": "disturbance-001", "event_type": "disturbance", "time_s": 0.45 * duration_s},
        {
            "event_id": "critical-monitoring-001",
            "event_type": "critical_monitoring",
            "time_s": 0.62 * duration_s,
        },
    ]
    baseline: list[JsonValue] = [
        {"interval_id": "baseline-001", "start_s": 0.0, "end_s": min(5.0, 0.15 * duration_s)}
    ]
    return {
        "phases": {**common, "schema_id": "phases-synthetic-v0.1", "phases": phases},
        "events": {**common, "schema_id": "events-synthetic-v0.1", "events": events},
        "baseline_intervals": {
            **common,
            "schema_id": "baseline-intervals-synthetic-v0.1",
            "baseline_intervals": baseline,
        },
    }


def write_rgb8_png(
    path: str | Path,
    *,
    width: int,
    height: int,
    seed: int,
    modality: str,
    index: int,
) -> None:
    """Write one deterministic RGB8 placeholder with no ancillary metadata."""

    if width <= 0 or height <= 0:
        raise ValueError("PNG dimensions must be positive")
    destination = Path(path)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    if destination.exists():
        raise FileExistsError(destination)
    base = tuple(
        int(uniform53(seed, modality, channel, index, 0) * 160.0) + 48
        for channel in ("red", "green", "blue")
    )
    with Image.new("RGB", (width, height), base) as image:
        draw = ImageDraw.Draw(image)
        draw.rectangle(
            (width // 5, height // 2, width // 2, height - 2),
            fill=(25, 65, 115),
        )
        draw.rectangle(
            (3 * width // 5, height // 5, width - 2, height // 2),
            fill=(170, 115, 35),
        )
        image.save(destination, format="PNG", compress_level=9, optimize=False)


__all__ = [
    "EcgArtifacts",
    "EegArtifacts",
    "GazeArtifacts",
    "SceneArtifacts",
    "build_annotations",
    "build_ecg",
    "build_eeg",
    "build_gaze",
    "build_pilot_camera",
    "build_scene",
    "build_task_reference",
    "write_rgb8_png",
]
