"""Build the single lightweight physical M4 workflow fixture."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import struct
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final, cast

import polars as pl
from pydantic import JsonValue

from pilot_assessment.contracts.session import (
    ClockSync,
    QualitySummary,
    SessionManifest,
    StreamDescriptor,
)
from pilot_assessment.ingestion.manifest_loader import ManifestLoader
from pilot_assessment.ingestion.parquet_io import write_profiled_parquet
from pilot_assessment.ingestion.profiles import CompositeProfile, load_builtin_profiles
from pilot_assessment.synchronization.clock import session_seconds_to_ns
from pilot_assessment.synthetic.modalities import (
    build_pilot_camera,
    build_scene,
    write_rgb8_png,
)
from pilot_assessment.synthetic.timelines import source_grid

FIXTURE_ID: Final = "m4-workflow-smoke-v0.1"
FIXTURE_CONTRACT: Final = "m4-workflow-smoke-fixture-v1"
GENERATOR_ID: Final = "m4-lightweight-workflow-builder-v1"
_CHECKSUM_PATH: Final = "integrity/checksums.sha256"
_ANCHOR_IDS: Final = frozenset(
    [f"O{index}" for index in range(1, 14)] + [f"H{index}" for index in range(1, 6)]
)
_RESULT_FIELDS: Final = frozenset(
    {
        "calculation_status",
        "evidence_likelihood",
        "evidence_state",
        "likelihood",
        "measurement_status",
        "primary_value",
        "result_fingerprint",
        "state",
    }
)
_PROHIBITED_KEYS: Final = frozenset(
    {
        "anchor_result_map",
        "expected_anchor_results",
        "expected_results",
        "o13_composite",
        "o8_composite",
        "plugin_artifacts",
        "production_output",
        "q_control",
        "serialized_anchor_measurement",
        "serialized_anchor_result",
    }
)
_CSV_HEADERS: Final = (
    "Simulation time",
    "Xe m",
    "Ye m",
    "Ze m",
    "Ground Elevation m",
    "V_ex m/s",
    "V_ey m/s",
    "V_ez m/s",
    "V_ex kts",
    "V_ey kts",
    "V_ez kts",
    "V_bx m/s",
    "V_by m/s",
    "V_bz m/s",
    "phi deg",
    "theta deg",
    "psi deg",
    "p deg/s",
    "q deg/s",
    "r deg/s",
    "ax m/s^2",
    "ay m/s^2",
    "az m/s^2",
    "alpha deg",
    "beta deg",
    "Control_Mode",
    "Pilot Yaw",
    "Pilot Lon",
    "Pilot Lat",
    "Pilot Heave",
    "Time Delay s",
    "Lon Frequency rad/s",
    "Long Damping",
)


def _answer_echo_error(path: tuple[str, ...], reason: str) -> ValueError:
    location = ".".join(path) if path else "<root>"
    return ValueError(f"answer echo is prohibited at {location}: {reason}")


def _reject_answer_echo(value: object, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, Mapping):
        string_keys = {str(key) for key in value}
        normalized_keys = {key.casefold() for key in string_keys}
        anchor_keys = string_keys & _ANCHOR_IDS
        if len(anchor_keys) > 1:
            raise _answer_echo_error(path, "multi-anchor keyed result map")
        prohibited = normalized_keys & _PROHIBITED_KEYS
        if prohibited:
            raise _answer_echo_error(path, f"prohibited key {sorted(prohibited)[0]}")
        contract_id = value.get("contract_id")
        if contract_id in {"anchor-result", "anchor-measurement"}:
            raise _answer_echo_error(path, "serialized production contract")
        if "anchor_id" in value and normalized_keys & _RESULT_FIELDS:
            raise _answer_echo_error(path, "result-like anchor object")
        for key, child in value.items():
            key_text = str(key)
            if key_text in _ANCHOR_IDS:
                if not isinstance(child, Mapping):
                    raise _answer_echo_error(path + (key_text,), "anchor-keyed scalar result")
                child_keys = {str(item).casefold() for item in child}
                result_shape_fields = _RESULT_FIELDS | {
                    "absolute_tolerance",
                    "classification_override",
                    "raw_metrics",
                    "trace",
                    "unit",
                    "value",
                }
                if child_keys & result_shape_fields:
                    raise _answer_echo_error(path + (key_text,), "anchor-keyed result map")
            _reject_answer_echo(child, path + (key_text,))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            _reject_answer_echo(child, path + (str(index),))


def _require_mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object with string keys")
    return cast(Mapping[str, object], value)


def _require_sequence(value: object, field: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def _finite_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be a finite number")
    return result


def _serialized_float32(value: float) -> float:
    """Round once to the physical Float32 representation used by Parquet references."""

    return struct.unpack("<f", struct.pack("<f", value))[0]


def _exact_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def _validate_finite_tree(value: object, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite recipe number at {'.'.join(path)}")
    if isinstance(value, Mapping):
        for key, child in value.items():
            _validate_finite_tree(child, path + (str(key),))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            _validate_finite_tree(child, path + (str(index),))


def validate_input_recipe(recipe: Mapping[str, object]) -> None:
    """Reject answer echo and validate the frozen physical-input contract."""

    _reject_answer_echo(recipe)
    _validate_finite_tree(recipe)
    if recipe.get("fixture_contract") != FIXTURE_CONTRACT:
        raise ValueError(f"fixture_contract must be {FIXTURE_CONTRACT}")
    if recipe.get("generator_id") != GENERATOR_ID:
        raise ValueError(f"generator_id must be {GENERATOR_ID}")
    if recipe.get("fixture_id") != FIXTURE_ID:
        raise ValueError(f"fixture_id must be {FIXTURE_ID}")
    if _exact_integer(recipe.get("seed"), "seed") != 20260713:
        raise ValueError("seed must be 20260713")

    session = _require_mapping(recipe.get("session"), "session")
    if dict(session) != {
        "start_s": 0,
        "end_s": 10,
        "baseline": [0, 4],
        "phases": [
            {"name": "Translation", "span_s": [4, 6]},
            {"name": "Deceleration", "span_s": [6, 8]},
            {"name": "Hover", "span_s": [8, 10]},
        ],
    }:
        raise ValueError("session must match the frozen 10-second smoke contract")

    expected_streams = {
        "xu": {
            "clock_mapping": "identity",
            "rate_hz": 100,
            "schema_id": "cranfield-simulator-combined-csv-raw-v0.1",
        },
        "task_reference": {
            "clock_mapping": "identity",
            "rate_hz": 100,
            "schema_id": "task-reference-path-raw-v0.1",
        },
        "vr_scene": {
            "clock_mapping": "identity",
            "image_height": 36,
            "image_mode": "RGB8",
            "image_width": 64,
            "rate_hz": 30,
            "schema_id": "vr-scene-source-bundle-v0.1",
        },
        "gaze": {
            "clock_mapping": "identity",
            "rate_hz": 120,
            "schema_id": "gaze-source-bundle-v0.1",
        },
        "eeg": {
            "clock_mapping": "identity",
            "mains_frequency_hz": 50,
            "rate_hz": 256,
            "schema_id": "eeg-source-bundle-v0.1",
        },
        "ecg": {
            "clock_mapping": "identity",
            "rate_hz": 250,
            "schema_id": "ecg-source-bundle-v0.1",
        },
        "pilot_camera": {
            "clock_mapping": "identity",
            "frame_valid": True,
            "image_height": 48,
            "image_mode": "RGB8",
            "image_width": 48,
            "privacy_class": "synthetic-no-identity",
            "rate_hz": 15,
            "schema_id": "pilot-camera-source-bundle-v0.1",
        },
    }
    streams = _require_mapping(recipe.get("streams"), "streams")
    if set(streams) != set(expected_streams):
        raise ValueError("streams must match the frozen modality inventory")
    for stream_name, expected_stream in expected_streams.items():
        stream = _require_mapping(streams.get(stream_name), f"streams.{stream_name}")
        if dict(stream) != expected_stream:
            raise ValueError(f"streams.{stream_name} must match its frozen profile")

    gaze = _require_mapping(recipe.get("gaze"), "gaze")
    expected_geometry = [
        {
            "bbox_norm": [0.1, 0.1, 0.8, 0.8],
            "catch_all": False,
            "confidence": 1.0,
            "priority": 1,
            "role": "primary_flight_display",
            "visible": True,
        },
        {
            "bbox_norm": [0.0, 0.0, 1.0, 1.0],
            "catch_all": True,
            "confidence": 1.0,
            "priority": 0,
            "role": "other_scene",
            "visible": True,
        },
    ]
    geometry = [
        dict(_require_mapping(item, "gaze.aoi_geometry item"))
        for item in _require_sequence(gaze.get("aoi_geometry"), "gaze.aoi_geometry")
    ]
    if geometry != expected_geometry:
        raise ValueError("gaze.aoi_geometry must match the frozen AOI geometry")
    if gaze.get("primary_role") != geometry[0]["role"]:
        raise ValueError("gaze.primary_role must bind the primary AOI geometry")
    if gaze.get("other_scene_role") != geometry[1]["role"]:
        raise ValueError("gaze.other_scene_role must bind the catch-all AOI geometry")
    scene = _require_mapping(gaze.get("scene"), "gaze.scene")
    if scene.get("frame_valid") is not True:
        raise ValueError("gaze.scene.frame_valid must be true")

    budget = _require_mapping(recipe.get("asset_budget"), "asset_budget")
    frozen_budget = {
        "png_files": 452,
        "declared_path_references": 468,
        "unique_artifacts": 467,
        "verified_paths": 466,
        "physical_source_table_rows": 9331,
        "max_physical_source_table_rows": 9500,
    }
    if dict(budget) != frozen_budget:
        raise ValueError("asset_budget must match the frozen lightweight budget")

    ecg = _require_mapping(recipe.get("ecg"), "ecg")
    peaks = _require_mapping(ecg.get("provided_r_peaks"), "ecg.provided_r_peaks")
    if peaks.get("task_peak_index_start") != 1:
        raise ValueError("task R-peak indices must start at 1")
    controls = _require_mapping(recipe.get("controls"), "controls")
    response = _require_mapping(controls.get("event_response"), "controls.event_response")
    pulses = _require_sequence(response.get("pulses_s"), "controls.event_response.pulses_s")
    event_ids = {str(item.get("event_id")) for item in map(_require_pulse, pulses)}
    if event_ids != {"disturbance-001", "envelope-exit-001"}:
        raise ValueError("raw response pulses must bind both frozen event IDs")


def _require_pulse(value: object) -> Mapping[str, object]:
    pulse = _require_mapping(value, "control pulse")
    required = {"event_id", "start_s", "end_s", "correct_sign"}
    if set(pulse) != required:
        raise ValueError("control pulse fields are incomplete")
    start = _finite_number(pulse["start_s"], "control pulse start_s")
    end = _finite_number(pulse["end_s"], "control pulse end_s")
    if not 0.0 <= start < end <= 10.0:
        raise ValueError("control pulse span is invalid")
    if pulse["correct_sign"] != 1:
        raise ValueError("control pulse correct_sign must be +1")
    return pulse


def _load_recipe(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("recipe root must be an object")
    recipe = cast(dict[str, object], payload)
    validate_input_recipe(recipe)
    return recipe


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _write_bytes(path: Path, payload: bytes) -> None:
    if not path.parent.is_dir():
        raise FileNotFoundError(path.parent)
    if path.exists():
        raise FileExistsError(path)
    path.write_bytes(payload)


def _write_json(path: Path, value: object) -> None:
    _write_bytes(path, _canonical_json_bytes(value))


def _write_recipe_image(
    path: Path,
    stream_recipe: Mapping[str, object],
    *,
    seed: int,
    modality: str,
    index: int,
) -> None:
    image_mode = str(stream_recipe["image_mode"])
    if image_mode != "RGB8":
        raise ValueError(f"unsupported frozen image mode: {image_mode}")
    write_rgb8_png(
        path,
        width=_exact_integer(stream_recipe["image_width"], "image width"),
        height=_exact_integer(stream_recipe["image_height"], "image height"),
        seed=seed,
        modality=modality,
        index=index,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prepare_output(output_root: Path) -> Path:
    if output_root.exists():
        if not output_root.is_dir() or any(output_root.iterdir()):
            raise FileExistsError("output_root must be a missing or empty directory")
    else:
        output_root.mkdir(parents=True)
    root = output_root.resolve(strict=True)
    for relative in (
        "streams/vr_scene/frames",
        "streams/gaze",
        "streams/eeg",
        "streams/ecg",
        "streams/pilot_camera/frames",
        "references",
        "annotations",
        "integrity",
    ):
        root.joinpath(*relative.split("/")).mkdir(parents=True)
    return root


def _phase_spans(recipe: Mapping[str, object]) -> tuple[tuple[str, float, float], ...]:
    session = _require_mapping(recipe["session"], "session")
    phases = _require_sequence(session["phases"], "session.phases")
    result: list[tuple[str, float, float]] = []
    for raw_phase in phases:
        phase = _require_mapping(raw_phase, "session phase")
        span = _require_sequence(phase["span_s"], "session phase span_s")
        result.append(
            (
                str(phase["name"]),
                _finite_number(span[0], "phase start"),
                _finite_number(span[1], "phase end"),
            )
        )
    return tuple(result)


def _phase_at(time_s: float, recipe: Mapping[str, object]) -> tuple[str, float, float] | None:
    for phase_name, start_s, end_s in _phase_spans(recipe):
        if start_s <= time_s < end_s:
            return phase_name, start_s, end_s
    return None


def _span_contains(time_s: float, span: Sequence[object]) -> bool:
    start = _finite_number(span[0], "span start")
    end = _finite_number(span[1], "span end")
    return start <= time_s < end


def _tracking_offset(time_s: float, recipe: Mapping[str, object]) -> float:
    trajectory = _require_mapping(recipe["trajectory"], "trajectory")
    spans_by_phase = _require_mapping(trajectory["offset_spans_s"], "trajectory.offset_spans_s")
    phase = _phase_at(time_s, recipe)
    if phase is None:
        return 0.0
    raw_spans = _require_sequence(spans_by_phase[phase[0]], "trajectory phase offsets")
    if any(_span_contains(time_s, _require_sequence(item, "offset span")) for item in raw_spans):
        magnitude = _finite_number(trajectory["tracking_offset_m"], "tracking_offset_m")
        sign = _exact_integer(trajectory["offset_sign"], "offset_sign")
        return sign * magnitude
    return 0.0


def _control_values(
    time_s: float,
    recipe: Mapping[str, object],
) -> tuple[float, float, float, float]:
    controls = _require_mapping(recipe["controls"], "controls")
    reversal = _require_mapping(controls["workload_reversal"], "workload_reversal")
    phase = _phase_at(time_s, recipe)
    yaw = 0.0
    if phase is not None:
        amplitude = _finite_number(reversal["amplitude_full_travel_fraction"], "workload amplitude")
        frequency = _finite_number(reversal["frequency_hz"], "workload frequency")
        yaw = amplitude * math.sin(2.0 * math.pi * frequency * (time_s - phase[1]))

    response = _require_mapping(controls["event_response"], "event_response")
    response_amplitude = _finite_number(
        response["amplitude_full_travel_fraction"], "response amplitude"
    )
    longitudinal = 0.0
    for raw_pulse in _require_sequence(response["pulses_s"], "response pulses"):
        pulse = _require_pulse(raw_pulse)
        if (
            _finite_number(pulse["start_s"], "pulse start")
            <= time_s
            < _finite_number(pulse["end_s"], "pulse end")
        ):
            longitudinal = response_amplitude * int(pulse["correct_sign"])

    magnitude = _require_mapping(controls["magnitude"], "magnitude")
    lateral = _finite_number(magnitude["constant_full_travel_fraction"], "magnitude fraction")

    hover = _require_mapping(controls["hover_trim"], "hover_trim")
    hover_span = _require_sequence(hover["span_s"], "hover span")
    heave = 0.0
    if _span_contains(time_s, hover_span):
        amplitude = _finite_number(hover["amplitude_full_travel_fraction"], "hover amplitude")
        frequency = _finite_number(hover["frequency_hz"], "hover frequency")
        start = _finite_number(hover_span[0], "hover start")
        heave = amplitude * math.sin(2.0 * math.pi * frequency * (time_s - start))
    return yaw, longitudinal, lateral, heave


def _simulator_csv(recipe: Mapping[str, object]) -> bytes:
    streams = _require_mapping(recipe["streams"], "streams")
    xu = _require_mapping(streams["xu"], "streams.xu")
    rate = _finite_number(xu["rate_hz"], "streams.xu.rate_hz")
    session = _require_mapping(recipe["session"], "session")
    duration = _finite_number(session["end_s"], "session.end_s")
    trajectory = _require_mapping(recipe["trajectory"], "trajectory")
    reference = _require_mapping(trajectory["commanded_reference"], "commanded_reference")
    target = _require_sequence(reference["position_m"], "commanded position")
    target_x = _serialized_float32(_finite_number(target[0], "target x"))
    target_y = _serialized_float32(_finite_number(target[1], "target y"))
    target_z = _serialized_float32(_finite_number(target[2], "target z"))
    offset_axis = _require_sequence(trajectory["offset_axis"], "trajectory.offset_axis")
    if len(offset_axis) != 3:
        raise ValueError("trajectory.offset_axis must have three components")
    axis = tuple(_finite_number(value, "offset axis component") for value in offset_axis)

    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(_CSV_HEADERS)
    for time_s in source_grid(duration_s=duration, sample_rate_hz=rate):
        yaw, longitudinal, lateral, heave = _control_values(time_s, recipe)
        tracking_offset = _tracking_offset(time_s, recipe)
        writer.writerow(
            [
                time_s,
                target_x + axis[0] * tracking_offset,
                target_y + axis[1] * tracking_offset,
                target_z + axis[2] * tracking_offset,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                1,
                yaw,
                longitudinal,
                lateral,
                heave,
                0.0,
                8.0,
                0.8,
            ]
        )
    return output.getvalue().encode("utf-8")


def _scene_tables(recipe: Mapping[str, object]) -> tuple[pl.DataFrame, pl.DataFrame]:
    session = _require_mapping(recipe["session"], "session")
    duration = _finite_number(session["end_s"], "session.end_s")
    seed = _exact_integer(recipe["seed"], "seed")
    scene = build_scene(duration_s=duration, seed=seed)
    streams = _require_mapping(recipe["streams"], "streams")
    stream_recipe = _require_mapping(streams["vr_scene"], "streams.vr_scene")
    width = _exact_integer(stream_recipe["image_width"], "VR image width")
    height = _exact_integer(stream_recipe["image_height"], "VR image height")
    gaze = _require_mapping(recipe["gaze"], "gaze")
    scene_recipe = _require_mapping(gaze["scene"], "gaze.scene")
    pose = _require_sequence(scene_recipe["head_pose_m"], "head pose")
    quaternion = _require_sequence(scene_recipe["head_quaternion_xyzw"], "head quaternion")
    times = cast(list[float], scene.frame_index["source_timestamp_s"].to_list())
    phases = [(_phase_at(time_s, recipe) or ("baseline", 0.0, 4.0))[0] for time_s in times]
    frame_index = scene.frame_index.with_columns(
        pl.Series("phase_id", phases, dtype=pl.String),
        pl.lit(width, dtype=pl.UInt32).alias("width"),
        pl.lit(height, dtype=pl.UInt32).alias("height"),
        pl.lit(_finite_number(pose[0], "head x"), dtype=pl.Float32).alias("head_x_m"),
        pl.lit(_finite_number(pose[1], "head y"), dtype=pl.Float32).alias("head_y_m"),
        pl.lit(_finite_number(pose[2], "head z"), dtype=pl.Float32).alias("head_z_m"),
        pl.lit(_finite_number(quaternion[0], "head qx"), dtype=pl.Float32).alias("head_qx"),
        pl.lit(_finite_number(quaternion[1], "head qy"), dtype=pl.Float32).alias("head_qy"),
        pl.lit(_finite_number(quaternion[2], "head qz"), dtype=pl.Float32).alias("head_qz"),
        pl.lit(_finite_number(quaternion[3], "head qw"), dtype=pl.Float32).alias("head_qw"),
        pl.lit(
            _finite_number(scene_recipe["horizontal_fov_deg"], "horizontal FOV"),
            dtype=pl.Float32,
        ).alias("horizontal_fov_deg"),
        pl.lit(
            _finite_number(scene_recipe["vertical_fov_deg"], "vertical FOV"),
            dtype=pl.Float32,
        ).alias("vertical_fov_deg"),
        pl.lit(bool(scene_recipe["frame_valid"]), dtype=pl.Boolean).alias("frame_valid"),
        pl.lit(GENERATOR_ID, dtype=pl.String).alias("generator_version"),
    )

    geometry = tuple(
        _require_mapping(item, "gaze.aoi_geometry item")
        for item in _require_sequence(gaze["aoi_geometry"], "gaze.aoi_geometry")
    )
    frame_ids: list[int] = []
    roles: list[str] = []
    bbox_x: list[float] = []
    bbox_y: list[float] = []
    bbox_w: list[float] = []
    bbox_h: list[float] = []
    visible: list[bool] = []
    confidence: list[float] = []
    for frame_id in cast(list[int], frame_index["frame_id"].to_list()):
        for item in geometry:
            bbox = _require_sequence(item["bbox_norm"], "AOI bbox_norm")
            frame_ids.append(frame_id)
            roles.append(str(item["role"]))
            bbox_x.append(_finite_number(bbox[0], "AOI bbox x"))
            bbox_y.append(_finite_number(bbox[1], "AOI bbox y"))
            bbox_w.append(_finite_number(bbox[2], "AOI bbox width"))
            bbox_h.append(_finite_number(bbox[3], "AOI bbox height"))
            visible.append(bool(item["visible"]))
            confidence.append(_finite_number(item["confidence"], "AOI confidence"))
    aoi_instances = pl.DataFrame(
        {
            "frame_id": pl.Series(frame_ids, dtype=pl.UInt64),
            "aoi_id": pl.Series(roles, dtype=pl.String),
            "taxonomy_version": pl.Series(
                [str(gaze["aoi_taxonomy_id"])] * len(frame_ids), dtype=pl.String
            ),
            "bbox_x_norm": pl.Series(bbox_x, dtype=pl.Float32),
            "bbox_y_norm": pl.Series(bbox_y, dtype=pl.Float32),
            "bbox_w_norm": pl.Series(bbox_w, dtype=pl.Float32),
            "bbox_h_norm": pl.Series(bbox_h, dtype=pl.Float32),
            "visible": pl.Series(visible, dtype=pl.Boolean),
            "confidence": pl.Series(confidence, dtype=pl.Float32),
        }
    ).sort("frame_id", "aoi_id")
    return frame_index, aoi_instances


def _gaze_tables(recipe: Mapping[str, object]) -> tuple[pl.DataFrame, pl.DataFrame]:
    streams = _require_mapping(recipe["streams"], "streams")
    gaze_stream = _require_mapping(streams["gaze"], "streams.gaze")
    rate = _finite_number(gaze_stream["rate_hz"], "gaze rate")
    scene_stream = _require_mapping(streams["vr_scene"], "streams.vr_scene")
    scene_rate = _exact_integer(scene_stream["rate_hz"], "VR scene rate")
    gaze_rate = _exact_integer(gaze_stream["rate_hz"], "gaze rate")
    duration = _finite_number(_require_mapping(recipe["session"], "session")["end_s"], "end")
    times = source_grid(duration_s=duration, sample_rate_hz=rate)
    last_scene_frame_id = (
        len(source_grid(duration_s=duration, sample_rate_hz=float(scene_rate))) - 1
    )
    gaze = _require_mapping(recipe["gaze"], "gaze")
    viewport = _require_mapping(gaze["raw_viewport"], "gaze.raw_viewport")
    on_task = _require_sequence(viewport["on_task_xy_norm"], "on-task viewport")
    off_task = _require_sequence(viewport["off_task_xy_norm"], "off-task viewport")
    motion_span = _require_sequence(viewport["cue_motion_span_s"], "cue motion span")
    motion_x = _require_sequence(viewport["cue_motion_x_norm"], "cue motion x")
    off_tail = _finite_number(gaze["off_task_tail_s_per_phase"], "off-task tail")
    primary_role = str(gaze["primary_role"])
    other_role = str(gaze["other_scene_role"])

    frame_ids: list[int] = []
    x_values: list[float] = []
    y_values: list[float] = []
    assigned_roles: list[str] = []
    rays: list[tuple[float, float, float]] = []
    for index, time_s in enumerate(times):
        phase = _phase_at(time_s, recipe)
        is_off_task = phase is not None and time_s >= phase[2] - off_tail
        x_value = _finite_number(off_task[0] if is_off_task else on_task[0], "viewport x")
        y_value = _finite_number(off_task[1] if is_off_task else on_task[1], "viewport y")
        if _span_contains(time_s, motion_span):
            x_value = _finite_number(motion_x[index % len(motion_x)], "motion x")
        raw_x = (x_value - 0.5) * 0.7
        raw_y = (0.5 - y_value) * 0.5
        norm = math.sqrt(raw_x * raw_x + raw_y * raw_y + 1.0)
        rays.append((raw_x / norm, raw_y / norm, 1.0 / norm))
        frame_ids.append(min((index * scene_rate) // gaze_rate, last_scene_frame_id))
        x_values.append(x_value)
        y_values.append(y_value)
        assigned_roles.append(other_role if is_off_task else primary_role)

    count = len(times)
    samples = pl.DataFrame(
        {
            "gaze_sample_id": pl.Series(range(count), dtype=pl.UInt64),
            "source_timestamp_s": pl.Series(times, dtype=pl.Float64),
            "scene_frame_id": pl.Series(frame_ids, dtype=pl.UInt64),
            "viewport_x_norm": pl.Series(x_values, dtype=pl.Float32),
            "viewport_y_norm": pl.Series(y_values, dtype=pl.Float32),
            "origin_x_m": pl.Series([0.0] * count, dtype=pl.Float32),
            "origin_y_m": pl.Series([0.0] * count, dtype=pl.Float32),
            "origin_z_m": pl.Series([1.15] * count, dtype=pl.Float32),
            "ray_x": pl.Series([ray[0] for ray in rays], dtype=pl.Float32),
            "ray_y": pl.Series([ray[1] for ray in rays], dtype=pl.Float32),
            "ray_z": pl.Series([ray[2] for ray in rays], dtype=pl.Float32),
            "left_pupil_mm": pl.Series([3.2] * count, dtype=pl.Float32),
            "right_pupil_mm": pl.Series([3.2] * count, dtype=pl.Float32),
            "binocular_valid": pl.Series([True] * count, dtype=pl.Boolean),
            "confidence": pl.Series([1.0] * count, dtype=pl.Float32),
            "blink": pl.Series([False] * count, dtype=pl.Boolean),
            "assigned_aoi_id": pl.Series(assigned_roles, dtype=pl.String),
            "assignment_confidence": pl.Series([1.0] * count, dtype=pl.Float32),
        }
    )
    compatibility = _require_mapping(gaze["compatibility_fixation"], "gaze.compatibility_fixation")
    fixation_span = _require_sequence(compatibility["span_s"], "compatibility span")
    start = _finite_number(fixation_span[0], "fixation start")
    end = _finite_number(fixation_span[1], "fixation end")
    fixations = pl.DataFrame(
        {
            "fixation_id": pl.Series([0], dtype=pl.UInt64),
            "start_source_timestamp_s": pl.Series([start], dtype=pl.Float64),
            "end_source_timestamp_s": pl.Series([end], dtype=pl.Float64),
            "duration_ms": pl.Series([(end - start) * 1000.0], dtype=pl.Float32),
            "centroid_x_norm": pl.Series([0.5], dtype=pl.Float32),
            "centroid_y_norm": pl.Series([0.5], dtype=pl.Float32),
            "ray_x": pl.Series([0.0], dtype=pl.Float32),
            "ray_y": pl.Series([0.0], dtype=pl.Float32),
            "ray_z": pl.Series([1.0], dtype=pl.Float32),
            "first_scene_frame_id": pl.Series([0], dtype=pl.UInt64),
            "last_scene_frame_id": pl.Series([3], dtype=pl.UInt64),
            "aoi_id": pl.Series([primary_role], dtype=pl.String),
            "fixation_valid": pl.Series([True], dtype=pl.Boolean),
            "confidence": pl.Series([1.0], dtype=pl.Float32),
            "detector_version": pl.Series(
                [str(compatibility["detector_version"])], dtype=pl.String
            ),
        }
    )
    return samples, fixations


def _eeg_table_and_sidecar(
    recipe: Mapping[str, object],
) -> tuple[pl.DataFrame, dict[str, JsonValue]]:
    streams = _require_mapping(recipe["streams"], "streams")
    stream = _require_mapping(streams["eeg"], "streams.eeg")
    rate = _finite_number(stream["rate_hz"], "EEG rate")
    duration = _finite_number(_require_mapping(recipe["session"], "session")["end_s"], "end")
    times = source_grid(duration_s=duration, sample_rate_hz=rate)
    eeg = _require_mapping(recipe["eeg"], "eeg")
    components = _require_mapping(eeg["components"], "eeg.components")
    theta = _require_mapping(components["theta"], "theta")
    alpha = _require_mapping(components["alpha"], "alpha")
    beta = _require_mapping(components["beta"], "beta")
    channels = tuple(
        str(value) for value in _require_sequence(eeg["engagement_channels"], "channels")
    )
    phases = tuple(
        _finite_number(value, "EEG channel phase")
        for value in _require_sequence(eeg["phase_radians"], "EEG phases")
    )
    if len(channels) != len(phases):
        raise ValueError("EEG channel and phase cardinalities must match")
    baseline_beta = _finite_number(beta["baseline_amplitude_uV"], "baseline beta")
    task_beta = baseline_beta * math.sqrt(_finite_number(beta["task_power_ratio"], "beta ratio"))
    theta_amp = _finite_number(theta["amplitude_uV"], "theta amplitude")
    alpha_amp = _finite_number(alpha["amplitude_uV"], "alpha amplitude")
    theta_hz = _finite_number(theta["frequency_hz"], "theta frequency")
    alpha_hz = _finite_number(alpha["frequency_hz"], "alpha frequency")
    beta_hz = _finite_number(beta["frequency_hz"], "beta frequency")

    data: dict[str, pl.Series] = {
        "sample_index": pl.Series(range(len(times)), dtype=pl.UInt64),
        "source_timestamp_s": pl.Series(times, dtype=pl.Float64),
    }
    selected = dict(zip(channels, phases, strict=True))
    for channel in ("Fp1", "Fp2", "F3", "F4", "C3", "C4", "P3", "P4"):
        if channel not in selected:
            values = [0.0] * len(times)
        else:
            channel_phase = selected[channel]
            values = [
                theta_amp * math.sin(2.0 * math.pi * theta_hz * time_s + channel_phase)
                + alpha_amp * math.sin(2.0 * math.pi * alpha_hz * time_s + channel_phase)
                + (baseline_beta if time_s < 4.0 else task_beta)
                * math.sin(2.0 * math.pi * beta_hz * time_s + channel_phase)
                for time_s in times
            ]
        data[f"{channel}_uV"] = pl.Series(values, dtype=pl.Float32)
    data["signal_valid"] = pl.Series([True] * len(times), dtype=pl.Boolean)
    data["artifact_code"] = pl.Series([None] * len(times), dtype=pl.String)
    physical_channels = ("Fp1", "Fp2", "F3", "F4", "C3", "C4", "P3", "P4")
    sidecar: dict[str, JsonValue] = {
        "schema_id": "eeg-sidecar-v0.1",
        "montage_id": "m4-smoke-eight-channel-v0.1",
        "reference": str(eeg["reference"]),
        "channel_order": list(physical_channels),
        "channel_units": {channel: str(eeg["unit"]) for channel in physical_channels},
        "sample_rate_hz": rate,
        "clock_id": "eeg_clock",
        "generator_id": GENERATOR_ID,
        "seed": _exact_integer(recipe["seed"], "seed"),
        "synthetic_not_neurophysiological": True,
    }
    return pl.DataFrame(data), sidecar


def _ecg_tables(recipe: Mapping[str, object]) -> tuple[pl.DataFrame, pl.DataFrame]:
    streams = _require_mapping(recipe["streams"], "streams")
    stream = _require_mapping(streams["ecg"], "streams.ecg")
    rate = _finite_number(stream["rate_hz"], "ECG rate")
    duration = _finite_number(_require_mapping(recipe["session"], "session")["end_s"], "end")
    times = source_grid(duration_s=duration, sample_rate_hz=rate)
    ecg = _require_mapping(recipe["ecg"], "ecg")
    raw_signal = _require_mapping(ecg["raw_signal"], "ecg.raw_signal")
    amplitude = _finite_number(raw_signal["amplitude_mV"], "ECG amplitude")
    frequency = _finite_number(raw_signal["frequency_hz"], "ECG frequency")
    values = [amplitude * math.sin(2.0 * math.pi * frequency * time_s) for time_s in times]
    samples = pl.DataFrame(
        {
            "sample_index": pl.Series(range(len(times)), dtype=pl.UInt64),
            "source_timestamp_s": pl.Series(times, dtype=pl.Float64),
            "synthetic_lead_ii_mV": pl.Series(values, dtype=pl.Float32),
            "signal_valid": pl.Series([True] * len(times), dtype=pl.Boolean),
            "artifact_code": pl.Series([None] * len(times), dtype=pl.String),
        }
    )
    peaks = _require_mapping(ecg["provided_r_peaks"], "provided_r_peaks")
    peak_times = [
        _finite_number(value, "baseline peak")
        for value in _require_sequence(peaks["baseline_peak_times_s"], "baseline peaks")
    ]
    first = _finite_number(peaks["task_first_peak_s"], "task first peak")
    start_index = _exact_integer(peaks["task_peak_index_start"], "task peak index start")
    count = _exact_integer(peaks["task_peak_count"], "task peak count")
    step = _finite_number(peaks["task_rr_step_s"], "task RR step")
    peak_times.extend(first + index * step for index in range(start_index, start_index + count))
    rr_values: list[float | None] = [None]
    rr_values.extend(
        (right - left) * 1000.0 for left, right in zip(peak_times, peak_times[1:], strict=False)
    )
    r_peaks = pl.DataFrame(
        {
            "peak_id": pl.Series(range(len(peak_times)), dtype=pl.UInt64),
            "source_timestamp_s": pl.Series(peak_times, dtype=pl.Float64),
            "rr_interval_ms": pl.Series(rr_values, dtype=pl.Float32),
            "detection_confidence": pl.Series([1.0] * len(peak_times), dtype=pl.Float32),
            "generator_version": pl.Series([GENERATOR_ID] * len(peak_times), dtype=pl.String),
        }
    )
    return samples, r_peaks


def _task_reference(recipe: Mapping[str, object]) -> pl.DataFrame:
    streams = _require_mapping(recipe["streams"], "streams")
    stream = _require_mapping(streams["task_reference"], "task_reference")
    rate = _finite_number(stream["rate_hz"], "task reference rate")
    duration = _finite_number(_require_mapping(recipe["session"], "session")["end_s"], "end")
    times = source_grid(duration_s=duration, sample_rate_hz=rate)
    trajectory = _require_mapping(recipe["trajectory"], "trajectory")
    reference = _require_mapping(trajectory["commanded_reference"], "commanded_reference")
    position = _require_sequence(reference["position_m"], "reference position")
    velocity = _require_sequence(reference["velocity_m_s"], "reference velocity")
    attitude = _require_sequence(reference["attitude_deg"], "reference attitude")
    semantic = _require_mapping(recipe["semantic_bindings"], "semantic_bindings")
    envelopes = [
        str(semantic["hover_envelope_id"])
        if (_phase_at(time_s, recipe) or ("", 0.0, 0.0))[0] == "Hover"
        else str(semantic["task_envelope_id"])
        for time_s in times
    ]
    count = len(times)
    return pl.DataFrame(
        {
            "reference_sample_id": pl.Series(range(count), dtype=pl.UInt64),
            "source_timestamp_s": pl.Series(times, dtype=pl.Float64),
            "target_x_m": pl.Series([float(position[0])] * count, dtype=pl.Float32),
            "target_y_m": pl.Series([float(position[1])] * count, dtype=pl.Float32),
            "target_z_m": pl.Series([float(position[2])] * count, dtype=pl.Float32),
            "target_vx_m_s": pl.Series([float(velocity[0])] * count, dtype=pl.Float32),
            "target_vy_m_s": pl.Series([float(velocity[1])] * count, dtype=pl.Float32),
            "target_vz_m_s": pl.Series([float(velocity[2])] * count, dtype=pl.Float32),
            "target_roll_deg": pl.Series([float(attitude[0])] * count, dtype=pl.Float32),
            "target_pitch_deg": pl.Series([float(attitude[1])] * count, dtype=pl.Float32),
            "target_yaw_deg": pl.Series([float(attitude[2])] * count, dtype=pl.Float32),
            "envelope_profile_id": pl.Series(envelopes, dtype=pl.String),
        }
    )


def _annotations(recipe: Mapping[str, object]) -> dict[str, dict[str, object]]:
    common: dict[str, object] = {
        "annotation_revision": "m4-smoke-semantics-v0.1",
        "timebase": {"origin": "session_start", "unit": "ns"},
        "annotation_source": "synthetic",
    }
    phases = [
        {
            "phase_id": name,
            "label": name,
            "start_t_ns": session_seconds_to_ns(start),
            "end_t_ns": session_seconds_to_ns(end),
            "source": "synthetic",
            "confidence": 1.0,
        }
        for name, start, end in _phase_spans(recipe)
    ]
    events: list[dict[str, object]] = []
    for raw_event in _require_sequence(recipe["events"], "events"):
        event = _require_mapping(raw_event, "event")
        record: dict[str, object] = {
            "event_id": str(event["event_id"]),
            "event_type": str(event["event_type"]),
            "t_ns": session_seconds_to_ns(_finite_number(event["time_s"], "event time")),
            "source": "synthetic",
            "confidence": 1.0,
        }
        if event["event_id"] in {"disturbance-001", "envelope-exit-001"}:
            record["response_mapping"] = {
                "response_mapping_id": f"{event['event_id']}-response-v1",
                "observation_horizon_ns": 2_000_000_000,
                "expected_channels": ["control.longitudinal_raw"],
                "response_aggregation": "earliest_any_mapped_correct",
            }
        events.append(record)
    baseline = _require_sequence(
        _require_mapping(recipe["session"], "session")["baseline"], "baseline"
    )
    baseline_record = {
        "interval_id": "baseline-001",
        "start_t_ns": session_seconds_to_ns(_finite_number(baseline[0], "baseline start")),
        "end_t_ns": session_seconds_to_ns(_finite_number(baseline[1], "baseline end")),
        "condition": "nominal",
        "valid": True,
    }
    return {
        "phases": {**common, "schema_id": "phases-session-time-v0.1", "phases": phases},
        "events": {**common, "schema_id": "events-session-time-v0.1", "events": events},
        "baseline_intervals": {
            **common,
            "schema_id": "baseline-intervals-session-time-v0.1",
            "baseline_intervals": [baseline_record],
        },
    }


def _clock_sync() -> ClockSync:
    return ClockSync(
        method="identity-declared-truth-v0.1",
        scale=1.0,
        offset_ns=0,
        drift_ppm=0.0,
        residual_rms_ms=0.0,
        residual_max_ms=0.0,
    )


def _quality_summary() -> QualitySummary:
    return QualitySummary(
        coverage_ratio=1.0,
        gap_count=0,
        validity_ratio=1.0,
        artifact_ratio=0.0,
    )


def _composite_roles(schema_id: str) -> dict[str, JsonValue]:
    profile = load_builtin_profiles()[schema_id]
    if not isinstance(profile, CompositeProfile):
        raise RuntimeError(f"packaged profile is not composite: {schema_id}")
    return {
        role: cast(JsonValue, definition.model_dump(mode="json"))
        for role, definition in profile.artifact_roles.items()
    }


def _descriptor(
    *,
    modality: str,
    paths: Sequence[str],
    format_name: str,
    schema_id: str,
    clock_id: str,
    rate_hz: float,
    units: str | dict[str, str],
    digests: Mapping[str, str],
    metadata: dict[str, JsonValue],
    required_for_import: bool = False,
) -> StreamDescriptor:
    ordered_paths = list(paths)
    return StreamDescriptor(
        modality=modality,
        status="present",
        required_for_import=required_for_import,
        paths=ordered_paths,
        format=format_name,
        schema_id=schema_id,
        clock_id=clock_id,
        clock_sync=_clock_sync(),
        sample_rate_hz=rate_hz,
        units=units,
        quality_summary=_quality_summary(),
        checksums={path: digests[path] for path in ordered_paths},
        metadata=metadata,
    )


def _lock_fingerprint() -> str:
    lock_path = Path(__file__).resolve().parents[2] / "uv.lock"
    if lock_path.is_file():
        return _sha256_file(lock_path)
    return hashlib.sha256(b"m4-lightweight-runtime-lock-unavailable\n").hexdigest()


def _build_manifest(
    recipe: Mapping[str, object],
    digests: Mapping[str, str],
    scene_images: Sequence[str],
    camera_images: Sequence[str],
) -> SessionManifest:
    seed = _exact_integer(recipe["seed"], "seed")
    stream_recipes = _require_mapping(recipe["streams"], "streams")
    xu_recipe = _require_mapping(stream_recipes["xu"], "streams.xu")
    vr_recipe = _require_mapping(stream_recipes["vr_scene"], "streams.vr_scene")
    gaze_recipe = _require_mapping(stream_recipes["gaze"], "streams.gaze")
    eeg_recipe = _require_mapping(stream_recipes["eeg"], "streams.eeg")
    ecg_recipe = _require_mapping(stream_recipes["ecg"], "streams.ecg")
    camera_recipe = _require_mapping(stream_recipes["pilot_camera"], "streams.pilot_camera")
    reference_recipe = _require_mapping(stream_recipes["task_reference"], "streams.task_reference")
    simulator_path = "streams/simulator.csv"
    csv_digest = digests[simulator_path]
    csv_metadata: dict[str, JsonValue] = {
        "adapter_profile_id": str(xu_recipe["schema_id"]),
        "shared_source_id": "m4-smoke-simulator-main",
    }
    streams: dict[str, StreamDescriptor] = {
        "X": _descriptor(
            modality="X",
            paths=(simulator_path,),
            format_name="csv",
            schema_id=str(xu_recipe["schema_id"]),
            clock_id="sim_clock",
            rate_hz=_finite_number(xu_recipe["rate_hz"], "X/U rate"),
            units="profile-defined-engineering-units",
            digests=digests,
            metadata={**csv_metadata, "view_id": "X"},
            required_for_import=True,
        ),
        "U": _descriptor(
            modality="U",
            paths=(simulator_path,),
            format_name="csv",
            schema_id=str(xu_recipe["schema_id"]),
            clock_id="sim_clock",
            rate_hz=_finite_number(xu_recipe["rate_hz"], "X/U rate"),
            units="profile-defined-engineering-units",
            digests=digests,
            metadata={**csv_metadata, "view_id": "U"},
            required_for_import=True,
        ),
        "I": _descriptor(
            modality="I",
            paths=(
                "streams/vr_scene/frame_index.parquet",
                "streams/vr_scene/aoi_instances.parquet",
                *scene_images,
            ),
            format_name="image_sequence+parquet_index",
            schema_id=str(vr_recipe["schema_id"]),
            clock_id="vr_scene_clock",
            rate_hz=_finite_number(vr_recipe["rate_hz"], "VR scene rate"),
            units="pixels-metres-quaternion-degrees",
            digests=digests,
            metadata={
                "artifact_roles": _composite_roles(str(vr_recipe["schema_id"])),
                "generator_id": GENERATOR_ID,
                "image_mode": str(vr_recipe["image_mode"]),
                "seed": seed,
            },
        ),
        "G": _descriptor(
            modality="G",
            paths=(
                "streams/gaze/gaze_samples.parquet",
                "streams/gaze/fixations.parquet",
            ),
            format_name="parquet",
            schema_id=str(gaze_recipe["schema_id"]),
            clock_id="gaze_clock",
            rate_hz=_finite_number(gaze_recipe["rate_hz"], "gaze rate"),
            units="normalized-viewport-metres-millimetres",
            digests=digests,
            metadata={
                "artifact_roles": _composite_roles(str(gaze_recipe["schema_id"])),
                "generator_id": GENERATOR_ID,
                "seed": seed,
                "scene_binding": "I.frame_id",
                "fixation_source": "compatibility-only-H2-recomputes-raw-G",
            },
        ),
        "EEG": _descriptor(
            modality="EEG",
            paths=(
                "streams/eeg/eeg_samples.parquet",
                "streams/eeg/eeg_sidecar.json",
            ),
            format_name="parquet+json_sidecar",
            schema_id=str(eeg_recipe["schema_id"]),
            clock_id="eeg_clock",
            rate_hz=_finite_number(eeg_recipe["rate_hz"], "EEG rate"),
            units="microvolt",
            digests=digests,
            metadata={
                "artifact_roles": _composite_roles(str(eeg_recipe["schema_id"])),
                "generator_id": GENERATOR_ID,
                "seed": seed,
                "mains_frequency_hz": _exact_integer(
                    eeg_recipe["mains_frequency_hz"], "EEG mains frequency"
                ),
            },
        ),
        "ECG": _descriptor(
            modality="ECG",
            paths=(
                "streams/ecg/ecg_samples.parquet",
                "streams/ecg/r_peaks.parquet",
            ),
            format_name="parquet",
            schema_id=str(ecg_recipe["schema_id"]),
            clock_id="ecg_clock",
            rate_hz=_finite_number(ecg_recipe["rate_hz"], "ECG rate"),
            units="millivolt",
            digests=digests,
            metadata={
                "artifact_roles": _composite_roles(str(ecg_recipe["schema_id"])),
                "generator_id": GENERATOR_ID,
                "seed": seed,
                "r_peak_mode": "provided_r_peaks_v1",
            },
        ),
        "pilot_camera": _descriptor(
            modality="pilot_camera",
            paths=("streams/pilot_camera/frame_index.parquet", *camera_images),
            format_name="image_sequence+parquet_index",
            schema_id=str(camera_recipe["schema_id"]),
            clock_id="pilot_camera_clock",
            rate_hz=_finite_number(camera_recipe["rate_hz"], "pilot-camera rate"),
            units="pixels-normalized-bbox",
            digests=digests,
            metadata={
                "artifact_roles": _composite_roles(str(camera_recipe["schema_id"])),
                "frame_valid": camera_recipe["frame_valid"],
                "generator_id": GENERATOR_ID,
                "image_mode": str(camera_recipe["image_mode"]),
                "seed": seed,
                "privacy_class": str(camera_recipe["privacy_class"]),
            },
        ),
        "task_reference": _descriptor(
            modality="task_reference",
            paths=("references/commanded_path.parquet",),
            format_name="parquet",
            schema_id=str(reference_recipe["schema_id"]),
            clock_id="sim_clock",
            rate_hz=_finite_number(reference_recipe["rate_hz"], "task-reference rate"),
            units="profile-defined-reference-units",
            digests=digests,
            metadata={
                "adapter_profile_id": str(reference_recipe["schema_id"]),
                "generator_id": GENERATOR_ID,
                "seed": seed,
                "reference_validity": "synthetic-format-fixture-only",
                "trajectory_standard_status": "not_asserted",
            },
            required_for_import=True,
        ),
    }
    return SessionManifest.model_validate(
        {
            "bundle_schema_version": "0.1.0",
            "session_id": FIXTURE_ID,
            "created_at": str(recipe["created_at"]),
            "source_session": {
                "system": GENERATOR_ID,
                "source_id": f"source-{csv_digest[:24]}",
                "campaign": "m4-lightweight-workflow-smoke",
                "extensions": {
                    "source_xu_sha256": csv_digest,
                    "source_artifact_role": "synthetic-raw-xu",
                    "task_validity": "not_asserted",
                    "ground_truth_status": "absent",
                },
            },
            "participant": {
                "pseudonymous_id": "synthetic-pilot",
                "research_attributes": {"synthetic_identity": True},
            },
            "task": {
                "task_profile_id": "m4-smoke-task-v0.1",
                "scenario_id": FIXTURE_ID,
                "expected_phases": ["Translation", "Deceleration", "Hover"],
                "reference": {
                    "source": "bundle",
                    "reference_id": "m4-smoke-commanded-path-v0.1",
                    "stream_id": "task_reference",
                },
            },
            "session_timebase": {
                "origin": "session_start",
                "unit": "ns",
                "master_clock_id": "sim_clock",
            },
            "streams": streams,
            "annotations": {
                "revision": "m4-smoke-semantics-v0.1",
                "phases": "annotations/phases.json",
                "events": "annotations/events.json",
                "baseline_intervals": "annotations/baseline_intervals.json",
            },
            "integrity": {
                "algorithm": "sha256",
                "manifest_canonicalization": "sorted-compact-json-lf-v0.1",
                "checksum_file": _CHECKSUM_PATH,
            },
            "privacy": {
                "classification": "synthetic-test-data",
                "direct_identifiers_removed": True,
                "contains_biometric_data": False,
                "biometric_modalities_export_pending": [],
                "permitted_use": "software-testing-only",
            },
            "extensions": {
                "synthetic": {
                    "generator_id": GENERATOR_ID,
                    "seed": seed,
                    "scientific_validation_status": "not_supported",
                    "source_xu_sha256": csv_digest,
                    "lock_fingerprint": _lock_fingerprint(),
                    "provenance_scope": "m4-lightweight-multimodal-workflow-smoke",
                    "formal_assessment_supported": False,
                    "duration_s": 10.0,
                    "mains_frequency_hz": 50,
                }
            },
        }
    )


def _write_checksum_manifest(root: Path, digests: Mapping[str, str]) -> None:
    payload = "".join(f"{digests[path]}  {path}\n" for path in sorted(digests))
    _write_bytes(root / _CHECKSUM_PATH, payload.encode("utf-8"))


def source_hash_manifest(bundle_root: Path) -> dict[str, str]:
    """Return verified input artifact hashes in bundle-relative lexical order."""

    loaded = ManifestLoader().load(Path(bundle_root))
    return {path: loaded.verified_digests[path] for path in sorted(loaded.verified_paths)}


def build_fixture(recipe_path: Path, case_id: str, output_root: Path) -> Path:
    """Build and M1-validate the exact lightweight workflow bundle."""

    if case_id != FIXTURE_ID:
        raise ValueError(f"only case_id={FIXTURE_ID!r} is supported")
    recipe = _load_recipe(Path(recipe_path))
    root = _prepare_output(Path(output_root))
    seed = _exact_integer(recipe["seed"], "seed")
    session = _require_mapping(recipe["session"], "session")
    duration = _finite_number(session["end_s"], "session.end_s")
    streams = _require_mapping(recipe["streams"], "streams")
    vr_recipe = _require_mapping(streams["vr_scene"], "streams.vr_scene")
    camera_recipe = _require_mapping(streams["pilot_camera"], "streams.pilot_camera")

    _write_bytes(root / "streams" / "simulator.csv", _simulator_csv(recipe))
    frame_index, aoi_instances = _scene_tables(recipe)
    gaze_samples, fixations = _gaze_tables(recipe)
    eeg_samples, eeg_sidecar = _eeg_table_and_sidecar(recipe)
    ecg_samples, r_peaks = _ecg_tables(recipe)
    pilot_camera = build_pilot_camera(duration_s=duration, seed=seed).with_columns(
        pl.lit(
            _exact_integer(camera_recipe["image_width"], "pilot-camera image width"),
            dtype=pl.UInt32,
        ).alias("width"),
        pl.lit(
            _exact_integer(camera_recipe["image_height"], "pilot-camera image height"),
            dtype=pl.UInt32,
        ).alias("height"),
        pl.lit(camera_recipe["frame_valid"], dtype=pl.Boolean).alias("frame_valid"),
        pl.lit(str(camera_recipe["privacy_class"]), dtype=pl.String).alias("privacy_class"),
        pl.lit(GENERATOR_ID, dtype=pl.String).alias("generator_version"),
    )
    commanded_path = _task_reference(recipe)

    write_profiled_parquet(
        frame_index,
        root / "streams" / "vr_scene" / "frame_index.parquet",
        schema_id="vr-frame-index-raw-v0.1",
    )
    write_profiled_parquet(
        aoi_instances,
        root / "streams" / "vr_scene" / "aoi_instances.parquet",
        schema_id="vr-aoi-instance-raw-v0.1",
    )
    scene_images = tuple(str(value) for value in frame_index["image_path"].to_list())
    for index, relative_path in enumerate(scene_images):
        _write_recipe_image(
            root.joinpath(*relative_path.split("/")),
            vr_recipe,
            seed=seed,
            modality="I",
            index=index,
        )

    write_profiled_parquet(
        gaze_samples,
        root / "streams" / "gaze" / "gaze_samples.parquet",
        schema_id="gaze-sample-raw-v0.1",
    )
    write_profiled_parquet(
        fixations,
        root / "streams" / "gaze" / "fixations.parquet",
        schema_id="gaze-fixation-raw-v0.1",
    )
    write_profiled_parquet(
        eeg_samples,
        root / "streams" / "eeg" / "eeg_samples.parquet",
        schema_id="eeg-sample-raw-v0.1",
    )
    _write_json(root / "streams" / "eeg" / "eeg_sidecar.json", eeg_sidecar)
    write_profiled_parquet(
        ecg_samples,
        root / "streams" / "ecg" / "ecg_samples.parquet",
        schema_id="ecg-sample-raw-v0.1",
    )
    write_profiled_parquet(
        r_peaks,
        root / "streams" / "ecg" / "r_peaks.parquet",
        schema_id="ecg-r-peak-raw-v0.1",
    )
    write_profiled_parquet(
        pilot_camera,
        root / "streams" / "pilot_camera" / "frame_index.parquet",
        schema_id="pilot-camera-frame-index-raw-v0.1",
    )
    camera_images = tuple(str(value) for value in pilot_camera["image_path"].to_list())
    for index, relative_path in enumerate(camera_images):
        _write_recipe_image(
            root.joinpath(*relative_path.split("/")),
            camera_recipe,
            seed=seed,
            modality="pilot_camera",
            index=index,
        )
    write_profiled_parquet(
        commanded_path,
        root / "references" / "commanded_path.parquet",
        schema_id="task-reference-path-raw-v0.1",
    )

    annotations = _annotations(recipe)
    for name in ("phases", "events", "baseline_intervals"):
        _write_json(root / "annotations" / f"{name}.json", annotations[name])

    source_paths = tuple(
        [
            "streams/simulator.csv",
            "streams/vr_scene/frame_index.parquet",
            "streams/vr_scene/aoi_instances.parquet",
            *scene_images,
            "streams/gaze/gaze_samples.parquet",
            "streams/gaze/fixations.parquet",
            "streams/eeg/eeg_samples.parquet",
            "streams/eeg/eeg_sidecar.json",
            "streams/ecg/ecg_samples.parquet",
            "streams/ecg/r_peaks.parquet",
            "streams/pilot_camera/frame_index.parquet",
            *camera_images,
            "references/commanded_path.parquet",
            "annotations/phases.json",
            "annotations/events.json",
            "annotations/baseline_intervals.json",
        ]
    )
    digests = {
        relative_path: _sha256_file(root.joinpath(*relative_path.split("/")))
        for relative_path in source_paths
    }
    _write_checksum_manifest(root, digests)
    manifest = _build_manifest(recipe, digests, scene_images, camera_images)
    _write_json(root / "manifest.json", manifest.model_dump(mode="json"))

    loaded = ManifestLoader().load(root)
    if loaded.manifest != manifest:
        raise RuntimeError("M1 self-validation did not reproduce the generated manifest")
    budget = _require_mapping(recipe["asset_budget"], "asset_budget")
    if loaded.declared_reference_count != int(budget["declared_path_references"]):
        raise RuntimeError("declared path budget mismatch")
    if loaded.unique_artifact_count != int(budget["unique_artifacts"]):
        raise RuntimeError("unique artifact budget mismatch")
    hashes = source_hash_manifest(root)
    if len(hashes) != int(budget["verified_paths"]):
        raise RuntimeError("verified source path budget mismatch")
    if len(list(root.rglob("*.png"))) != int(budget["png_files"]):
        raise RuntimeError("PNG asset budget mismatch")
    return root


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", required=True, type=Path)
    parser.add_argument("--case-id", default=FIXTURE_ID)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args(argv)
    print(build_fixture(args.recipe, args.case_id, args.output_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
