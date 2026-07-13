"""Independent numerical oracle for the lightweight M4 input recipe."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Final, cast

import numpy as np
import rfc8785
import scipy
from scipy import signal

_FIXTURE_ID: Final = "m4-workflow-smoke-v0.1"
_ORACLE_ID: Final = "m4-lightweight-numerical-oracle-v1"
_ANCHOR_IDS: Final = tuple(
    [f"O{index}" for index in range(1, 14)] + [f"H{index}" for index in range(1, 6)]
)
_NANOSECONDS_PER_SECOND: Final = Decimal(1_000_000_000)


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be a finite number")
    return result


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def _phases(recipe: Mapping[str, object]) -> tuple[tuple[str, float, float], ...]:
    session = _mapping(recipe["session"], "session")
    result: list[tuple[str, float, float]] = []
    for raw_phase in _sequence(session["phases"], "session.phases"):
        phase = _mapping(raw_phase, "phase")
        span = _sequence(phase["span_s"], "phase.span_s")
        result.append(
            (
                str(phase["name"]),
                _number(span[0], "phase start"),
                _number(span[1], "phase end"),
            )
        )
    return tuple(result)


def _seconds_to_ns(value: object, field: str) -> int:
    seconds = _number(value, field)
    return int(
        (Decimal(str(seconds)) * _NANOSECONDS_PER_SECOND).to_integral_value(
            rounding=ROUND_HALF_EVEN
        )
    )


def _merged_spans_ns(
    start_t_ns: int,
    end_t_ns: int,
    spans: Sequence[object],
) -> tuple[tuple[int, int], ...]:
    clipped: list[tuple[int, int]] = []
    for raw_span in spans:
        span = _sequence(raw_span, "span")
        left = max(start_t_ns, _seconds_to_ns(span[0], "span start"))
        right = min(end_t_ns, _seconds_to_ns(span[1], "span end"))
        if left < right:
            clipped.append((left, right))
    clipped.sort()
    merged: list[tuple[int, int]] = []
    for left, right in clipped:
        if merged and left <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], right))
        else:
            merged.append((left, right))
    return tuple(merged)


def _inside_intervals_ns(
    phase_start_s: float,
    phase_end_s: float,
    spans: Sequence[object],
    *,
    offset_outside: bool,
) -> tuple[tuple[int, int], ...]:
    phase_start_ns = _seconds_to_ns(phase_start_s, "phase start")
    phase_end_ns = _seconds_to_ns(phase_end_s, "phase end")
    outside = _merged_spans_ns(phase_start_ns, phase_end_ns, spans) if offset_outside else ()
    cursor = phase_start_ns
    inside: list[tuple[int, int]] = []
    for left, right in outside:
        if cursor < left:
            inside.append((cursor, left))
        cursor = max(cursor, right)
    if cursor < phase_end_ns:
        inside.append((cursor, phase_end_ns))
    return tuple(inside)


def _state_higher(value: float, desired: float, adequate: float) -> str:
    if value >= desired:
        return "desired"
    if value >= adequate:
        return "adequate"
    return "unacceptable"


def _state_lower_inclusive(value: float, desired: float, adequate: float) -> str:
    if value <= desired:
        return "desired"
    if value <= adequate:
        return "adequate"
    return "unacceptable"


def _metric(value: int | float, unit: str) -> dict[str, object]:
    return {"unit": unit, "value": value}


def _entry(
    anchor_id: str,
    *,
    primary: dict[str, object] | None,
    state: str,
    raw_metrics: Mapping[str, object],
    trace: Mapping[str, object],
    absolute_tolerance: float = 0.0,
    override: Mapping[str, object] | None = None,
    primary_reason: str | None = None,
) -> dict[str, object]:
    return {
        "absolute_tolerance": absolute_tolerance,
        "anchor_id": anchor_id,
        "calculation_status": "computed",
        "classification_override": dict(override) if override is not None else None,
        "evidence_state": state,
        "primary_value": primary,
        "primary_value_reason": primary_reason,
        "raw_metrics": dict(raw_metrics),
        "trace": dict(trace),
    }


def _not_applicable_entry(anchor_id: str, trace: Mapping[str, object]) -> dict[str, object]:
    return {
        "absolute_tolerance": 0.0,
        "anchor_id": anchor_id,
        "calculation_status": "not_applicable",
        "classification_override": None,
        "evidence_state": None,
        "primary_value": None,
        "primary_value_reason": "no_applicable_event",
        "raw_metrics": {},
        "trace": dict(trace),
    }


def _vector_norm(raw: object, field: str) -> float:
    values = [_number(value, field) for value in _sequence(raw, field)]
    return math.sqrt(sum(value * value for value in values))


def _phase_inside_intervals(
    recipe: Mapping[str, object],
    phase_id: str,
) -> tuple[tuple[int, int], ...]:
    trajectory = _mapping(recipe["trajectory"], "trajectory")
    spans_by_phase = _mapping(trajectory["offset_spans_s"], "offset spans")
    offset_outside = abs(_number(trajectory["tracking_offset_m"], "tracking offset")) > _number(
        trajectory["envelope_radius_m"], "envelope radius"
    )
    _name, start, end = next(phase for phase in _phases(recipe) if phase[0] == phase_id)
    return _inside_intervals_ns(
        start,
        end,
        _sequence(spans_by_phase[phase_id], f"{phase_id} offset spans"),
        offset_outside=offset_outside,
    )


def _movement_phase_rows(
    recipe: Mapping[str, object],
) -> tuple[list[dict[str, object]], int, int, float]:
    """Run the approved short-sine movement/reversal detector independently."""

    controls = _mapping(recipe["controls"], "controls")
    movement = _mapping(controls["workload_reversal"], "workload reversal")
    streams = _mapping(recipe["streams"], "streams")
    fs = _number(_mapping(streams["xu"], "streams.xu")["rate_hz"], "X/U rate")
    amplitude = _number(movement["amplitude_full_travel_fraction"], "movement amplitude")
    frequency = _number(movement["frequency_hz"], "movement frequency")
    filter_order = 4
    cutoff_hz = 5.0
    derivative_deadband = 0.005
    minimum_run_s = 0.05
    movement_amplitude_threshold = 0.005
    reversal_amplitude_threshold = 0.02
    reversal_interval_s = 0.15
    sos = signal.butter(filter_order, cutoff_hz, btype="lowpass", fs=fs, output="sos")

    rows: list[dict[str, object]] = []
    total_movements = 0
    total_reversals = 0
    total_duration = 0.0
    for phase_id, start, end in _phases(recipe):
        duration = end - start
        sample_count = int(
            (Decimal(str(duration)) * Decimal(str(fs))).to_integral_value(rounding=ROUND_HALF_EVEN)
        )
        local_times = np.arange(sample_count, dtype=np.float64) / fs
        raw = amplitude * np.sin(2.0 * np.pi * frequency * local_times)
        filtered = signal.sosfiltfilt(
            sos,
            raw,
            padtype="odd",
            padlen=min(15, sample_count - 1),
        )
        derivative = np.empty_like(filtered)
        if sample_count == 1:
            derivative[0] = 0.0
        else:
            derivative[0] = (filtered[1] - filtered[0]) * fs
            derivative[-1] = (filtered[-1] - filtered[-2]) * fs
            derivative[1:-1] = (filtered[2:] - filtered[:-2]) * (fs / 2.0)
        signs = np.where(
            derivative > derivative_deadband,
            1,
            np.where(derivative < -derivative_deadband, -1, 0),
        )

        runs: list[tuple[int, int, int]] = []
        index = 0
        while index < sample_count:
            sign_value = int(signs[index])
            if sign_value == 0:
                index += 1
                continue
            end_index = index
            while end_index + 1 < sample_count and int(signs[end_index + 1]) == sign_value:
                end_index += 1
            interval_count = max(0, min(end_index, sample_count - 2) - index + 1)
            if interval_count / fs >= minimum_run_s:
                runs.append((sign_value, index, end_index))
            index = end_index + 1

        turning_points: list[tuple[int, float]] = []
        for left_run, right_run in zip(runs, runs[1:], strict=False):
            left_sign, _left_start, left_end = left_run
            right_sign, right_start, _right_end = right_run
            if left_sign == right_sign:
                continue
            region = filtered[left_end : right_start + 1]
            extreme = float(np.max(region) if left_sign > 0 else np.min(region))
            matching = np.flatnonzero(region == extreme)
            first_index = left_end + int(matching[0])
            last_index = left_end + int(matching[-1])
            midpoint = int(
                (Decimal(first_index + last_index) / Decimal(2)).to_integral_value(
                    rounding=ROUND_HALF_EVEN
                )
            )
            turning_points.append((midpoint, extreme))

        movement_count = 0
        reversal_count = 0
        for (left_index, left_value), (right_index, right_value) in zip(
            turning_points, turning_points[1:], strict=False
        ):
            excursion = abs(right_value - left_value)
            if excursion >= movement_amplitude_threshold:
                movement_count += 1
            if (
                excursion >= reversal_amplitude_threshold
                and (right_index - left_index) / fs >= reversal_interval_s
            ):
                reversal_count += 1
        workload_rate = movement_count / duration
        workload_ratio = workload_rate / _number(movement["w_min_hz"], "W_min")
        reversal_rate = reversal_count / duration
        rows.append(
            {
                "duration_ns": _seconds_to_ns(duration, "phase duration"),
                "movement_count": movement_count,
                "phase_id": phase_id,
                "reversal_count": reversal_count,
                "reversal_state": (
                    "desired"
                    if reversal_rate < 2.0
                    else ("adequate" if reversal_rate < 4.0 else "unacceptable")
                ),
                "turning_point_count": len(turning_points),
                "workload_state": _state_lower_inclusive(workload_ratio, 2.0, 4.0),
            }
        )
        total_movements += movement_count
        total_reversals += reversal_count
        total_duration += duration
    return rows, total_movements, total_reversals, total_duration


def _trajectory_values(
    recipe: Mapping[str, object],
) -> tuple[list[dict[str, object]], float, float, float]:
    trajectory = _mapping(recipe["trajectory"], "trajectory")
    spans_by_phase = _mapping(trajectory["offset_spans_s"], "trajectory.offset_spans_s")
    radius = _number(trajectory["envelope_radius_m"], "envelope radius")
    offset = abs(_number(trajectory["tracking_offset_m"], "tracking offset"))
    metres_per_foot = _number(
        _mapping(recipe["semantic_bindings"], "semantic_bindings")["metres_per_foot"],
        "metres per foot",
    )
    phase_rows: list[dict[str, object]] = []
    stable_by_phase: dict[str, float] = {}
    for name, start, end in _phases(recipe):
        spans = _sequence(spans_by_phase[name], f"trajectory offsets for {name}")
        inside_intervals = _inside_intervals_ns(
            start,
            end,
            spans,
            offset_outside=offset > radius,
        )
        inside_t_ns = sum(right - left for left, right in inside_intervals)
        duration_t_ns = _seconds_to_ns(end, "phase end") - _seconds_to_ns(start, "phase start")
        percent = float(Decimal(100) * Decimal(inside_t_ns) / Decimal(duration_t_ns))
        stable_by_phase[name] = inside_t_ns / 1_000_000_000
        phase_rows.append(
            {
                "end_t_ns": _seconds_to_ns(end, "phase end"),
                "inside_duration_ns": inside_t_ns,
                "phase_id": name,
                "precision_percent": percent,
                "start_t_ns": _seconds_to_ns(start, "phase start"),
                "state": _state_higher(percent, 90.0, 70.0),
            }
        )
    session_precision = min(float(row["precision_percent"]) for row in phase_rows)
    return phase_rows, session_precision, offset / metres_per_foot, stable_by_phase["Hover"]


def _rr_values(
    recipe: Mapping[str, object],
) -> tuple[float, list[dict[str, object]], float]:
    ecg = _mapping(recipe["ecg"], "ecg")
    peaks_recipe = _mapping(ecg["provided_r_peaks"], "provided_r_peaks")
    peak_times = [
        _number(value, "baseline peak")
        for value in _sequence(peaks_recipe["baseline_peak_times_s"], "baseline peaks")
    ]
    first = _number(peaks_recipe["task_first_peak_s"], "task first peak")
    first_index = _integer(peaks_recipe["task_peak_index_start"], "task first index")
    count = _integer(peaks_recipe["task_peak_count"], "task peak count")
    step = _number(peaks_recipe["task_rr_step_s"], "task RR step")
    peak_times.extend(first + index * step for index in range(first_index, first_index + count))
    rr = [
        (right, 60.0 / (right - left))
        for left, right in zip(peak_times, peak_times[1:], strict=False)
    ]
    baseline_span = _sequence(_mapping(recipe["session"], "session")["baseline"], "baseline")
    baseline_start = _number(baseline_span[0], "baseline start")
    baseline_end = _number(baseline_span[1], "baseline end")
    baseline_hr = [value for timestamp, value in rr if baseline_start <= timestamp < baseline_end]
    hr0 = float(statistics.median(baseline_hr))
    windows: list[dict[str, object]] = []
    for phase_id, start, end in _phases(recipe):
        values = [value for timestamp, value in rr if start <= timestamp < end]
        median_hr = float(statistics.median(values))
        signed_delta = 100.0 * (median_hr / hr0 - 1.0)
        windows.append(
            {
                "end_t_ns": round(end * 1_000_000_000),
                "median_hr_bpm": median_hr,
                "phase_id": phase_id,
                "signed_delta_hr_percent": signed_delta,
                "start_t_ns": round(start * 1_000_000_000),
            }
        )
    maximum = max(abs(float(row["signed_delta_hr_percent"])) for row in windows)
    return hr0, windows, maximum


def _grid_t_ns(start_s: float, index: int, fs: float) -> int:
    timestamp = Decimal(str(start_s)) + Decimal(index) / Decimal(str(fs))
    return int((timestamp * _NANOSECONDS_PER_SECOND).to_integral_value(rounding=ROUND_HALF_EVEN))


def _viewport_at(
    recipe: Mapping[str, object],
    time_s: float,
    sample_index: int,
) -> tuple[float, float]:
    gaze = _mapping(recipe["gaze"], "gaze")
    viewport = _mapping(gaze["raw_viewport"], "raw viewport")
    phase = next(
        (item for item in _phases(recipe) if item[1] <= time_s < item[2]),
        None,
    )
    off_task = phase is not None and time_s >= phase[2] - _number(
        gaze["off_task_tail_s_per_phase"], "off-task tail"
    )
    coordinates = _sequence(
        viewport["off_task_xy_norm"] if off_task else viewport["on_task_xy_norm"],
        "viewport coordinates",
    )
    x_value = _number(coordinates[0], "viewport x")
    y_value = _number(coordinates[1], "viewport y")
    motion_span = _sequence(viewport["cue_motion_span_s"], "cue motion span")
    if _number(motion_span[0], "motion start") <= time_s < _number(motion_span[1], "motion end"):
        motion_x = _sequence(viewport["cue_motion_x_norm"], "cue motion x")
        x_value = _number(motion_x[sample_index % len(motion_x)], "cue motion x")
    return x_value, y_value


def _aoi_role(recipe: Mapping[str, object], x_value: float, y_value: float) -> str:
    gaze = _mapping(recipe["gaze"], "gaze")
    candidates: list[tuple[int, str]] = []
    for raw_geometry in _sequence(gaze["aoi_geometry"], "AOI geometry"):
        geometry = _mapping(raw_geometry, "AOI geometry")
        bbox = _sequence(geometry["bbox_norm"], "AOI bbox")
        left = _number(bbox[0], "AOI left")
        top = _number(bbox[1], "AOI top")
        width = _number(bbox[2], "AOI width")
        height = _number(bbox[3], "AOI height")
        if left <= x_value <= left + width and top <= y_value <= top + height:
            candidates.append(
                (_integer(geometry["priority"], "AOI priority"), str(geometry["role"]))
            )
    if not candidates:
        return str(gaze["other_scene_role"])
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][1]


def _viewport_ray(x_value: float, y_value: float) -> np.ndarray:
    raw = np.asarray([(x_value - 0.5) * 0.7, (0.5 - y_value) * 0.5, 1.0])
    return raw / np.linalg.norm(raw)


def _gaze_values(recipe: Mapping[str, object]) -> tuple[int, int, int | None, int]:
    streams = _mapping(recipe["streams"], "streams")
    fs = _number(_mapping(streams["gaze"], "gaze stream")["rate_hz"], "gaze rate")
    gaze = _mapping(recipe["gaze"], "gaze")
    primary_role = str(gaze["primary_role"])
    on_task_ns = 0
    off_task_ns = 0
    for _phase_id, start, end in _phases(recipe):
        count = int(
            (Decimal(str(end - start)) * Decimal(str(fs))).to_integral_value(
                rounding=ROUND_HALF_EVEN
            )
        )
        global_start = int(
            (Decimal(str(start)) * Decimal(str(fs))).to_integral_value(rounding=ROUND_HALF_EVEN)
        )
        for local_index in range(count):
            left_ns = _grid_t_ns(start, local_index, fs)
            right_ns = _grid_t_ns(start, local_index + 1, fs)
            time_s = left_ns / 1_000_000_000
            x_value, y_value = _viewport_at(recipe, time_s, global_start + local_index)
            if _aoi_role(recipe, x_value, y_value) == primary_role:
                on_task_ns += right_ns - left_ns
            else:
                off_task_ns += right_ns - left_ns

    events = {
        str(event["event_id"]): _number(event["time_s"], "event time")
        for event in map(
            lambda item: _mapping(item, "event"), _sequence(recipe["events"], "events")
        )
    }
    cue_s = events["visual-cue-001"]
    cue_t_ns = _seconds_to_ns(cue_s, "cue time")
    horizon_end_s = min(10.0, cue_s + 2.0)
    start_index = int(
        (Decimal(str(cue_s)) * Decimal(str(fs))).to_integral_value(rounding=ROUND_HALF_EVEN)
    )
    end_index = int(
        (Decimal(str(horizon_end_s)) * Decimal(str(fs))).to_integral_value(rounding=ROUND_HALF_EVEN)
    )
    minimum_duration_ns = 100_000_000
    velocity_threshold_deg_s = 100.0
    run_start_ns: int | None = None
    run_duration_ns = 0
    fixation_start_ns: int | None = None
    for sample_index in range(start_index, end_index):
        left_ns = _grid_t_ns(0.0, sample_index, fs)
        right_ns = _grid_t_ns(0.0, sample_index + 1, fs)
        left_s = left_ns / 1_000_000_000
        right_s = right_ns / 1_000_000_000
        left_xy = _viewport_at(recipe, left_s, sample_index)
        right_xy = _viewport_at(recipe, right_s, sample_index + 1)
        dot = float(np.clip(np.dot(_viewport_ray(*left_xy), _viewport_ray(*right_xy)), -1.0, 1.0))
        velocity = math.degrees(math.acos(dot)) / ((right_ns - left_ns) / 1e9)
        relevant = _aoi_role(recipe, *left_xy) == primary_role
        if relevant and velocity <= velocity_threshold_deg_s:
            if run_start_ns is None:
                run_start_ns = left_ns
                run_duration_ns = 0
            run_duration_ns += right_ns - left_ns
            if run_duration_ns >= minimum_duration_ns:
                fixation_start_ns = run_start_ns
                break
        else:
            run_start_ns = None
            run_duration_ns = 0
    return on_task_ns, off_task_ns, fixation_start_ns, cue_t_ns


def _preprocess_eeg_segment(
    values: np.ndarray,
    fs: float,
    mains_hz: float,
    *,
    bandpass_hz: tuple[float, float],
    bandpass_order: int,
    notch_q: float,
    common_average: bool,
) -> np.ndarray:
    processed_channels: list[np.ndarray] = []
    sos = signal.butter(
        bandpass_order,
        bandpass_hz,
        btype="bandpass",
        fs=fs,
        output="sos",
    )
    notch_b, notch_a = signal.iirnotch(mains_hz, notch_q, fs=fs)
    for channel in values:
        current = signal.detrend(channel.astype(np.float64), type="constant")
        current = signal.detrend(current, type="linear")
        current = signal.sosfiltfilt(
            sos,
            current,
            padtype="odd",
            padlen=min(27, current.size - 1),
        )
        if mains_hz < fs / 2.0:
            current = signal.filtfilt(
                notch_b,
                notch_a,
                current,
                padtype="odd",
                padlen=min(6, current.size - 1),
            )
        processed_channels.append(current)
    stacked = np.stack(processed_channels)
    if common_average:
        return stacked - np.mean(stacked, axis=0, keepdims=True)
    return stacked


def _engagement(
    processed: np.ndarray,
    fs: float,
    epsilon: float,
    *,
    welch_segment_s: float,
) -> float:
    channel_values: list[float] = []
    for channel in processed:
        nperseg = min(
            int(
                (Decimal(str(welch_segment_s)) * Decimal(str(fs))).to_integral_value(
                    rounding=ROUND_HALF_EVEN
                )
            ),
            channel.size,
        )
        frequencies, density = signal.welch(
            channel,
            fs=fs,
            window=signal.get_window("hann", nperseg, fftbins=True),
            nperseg=nperseg,
            noverlap=math.floor(nperseg / 2),
            nfft=1 << (nperseg - 1).bit_length(),
            detrend=False,
            return_onesided=True,
            scaling="density",
        )
        theta_mask = (frequencies >= 4.0) & (frequencies < 8.0)
        alpha_mask = (frequencies >= 8.0) & (frequencies < 13.0)
        beta_mask = (frequencies >= 13.0) & (frequencies <= 30.0)
        if min(theta_mask.sum(), alpha_mask.sum(), beta_mask.sum()) < 2:
            raise ValueError("configured EEG band has fewer than two bins")
        theta = float(np.trapezoid(density[theta_mask], frequencies[theta_mask]))
        alpha = float(np.trapezoid(density[alpha_mask], frequencies[alpha_mask]))
        beta = float(np.trapezoid(density[beta_mask], frequencies[beta_mask]))
        channel_values.append(beta / (alpha + theta + epsilon))
    return float(np.median(np.asarray(channel_values, dtype=np.float64)))


def _eeg_values(
    recipe: Mapping[str, object],
) -> tuple[float, list[dict[str, object]], float]:
    streams = _mapping(recipe["streams"], "streams")
    eeg_stream = _mapping(streams["eeg"], "streams.eeg")
    fs = _number(eeg_stream["rate_hz"], "EEG rate")
    mains_hz = _number(eeg_stream["mains_frequency_hz"], "mains frequency")
    eeg = _mapping(recipe["eeg"], "eeg")
    components = _mapping(eeg["components"], "eeg.components")
    theta = _mapping(components["theta"], "theta")
    alpha = _mapping(components["alpha"], "alpha")
    beta = _mapping(components["beta"], "beta")
    phases = np.asarray(
        [_number(value, "channel phase") for value in _sequence(eeg["phase_radians"], "phases")],
        dtype=np.float64,
    )
    theta_amp = _number(theta["amplitude_uV"], "theta amplitude")
    alpha_amp = _number(alpha["amplitude_uV"], "alpha amplitude")
    baseline_beta = _number(beta["baseline_amplitude_uV"], "baseline beta")
    task_beta = baseline_beta * math.sqrt(_number(beta["task_power_ratio"], "beta ratio"))
    theta_hz = _number(theta["frequency_hz"], "theta frequency")
    alpha_hz = _number(alpha["frequency_hz"], "alpha frequency")
    beta_hz = _number(beta["frequency_hz"], "beta frequency")
    epsilon = _number(eeg["epsilon"], "epsilon")
    scale_to_volts = _number(eeg["scale_to_volts"], "EEG scale to volts")
    pipeline = _mapping(eeg["pipeline"], "EEG pipeline")
    bandpass = _sequence(pipeline["bandpass_hz"], "EEG bandpass")
    bandpass_hz = (
        _number(bandpass[0], "bandpass lower"),
        _number(bandpass[1], "bandpass upper"),
    )
    bandpass_order = _integer(pipeline["bandpass_order"], "bandpass order")
    notch_q = _number(pipeline["mains_notch_q"], "notch Q")
    common_average = pipeline["common_average"]
    if type(common_average) is not bool:
        raise ValueError("common_average must be a boolean")
    window_s = _number(pipeline["window_s"], "EEG window length")
    window_step_s = _number(pipeline["window_step_s"], "EEG window step")
    welch_segment_s = _number(pipeline["welch_segment_s"], "Welch segment length")

    def raw_segment(start: float, end: float, beta_amplitude: float) -> np.ndarray:
        start_index = int(
            (Decimal(str(start)) * Decimal(str(fs))).to_integral_value(rounding=ROUND_HALF_EVEN)
        )
        end_index = int(
            (Decimal(str(end)) * Decimal(str(fs))).to_integral_value(rounding=ROUND_HALF_EVEN)
        )
        rows = []
        for phase in phases:
            waveform = np.asarray(
                [
                    theta_amp * math.sin(2.0 * math.pi * theta_hz * (index / fs) + phase)
                    + alpha_amp * math.sin(2.0 * math.pi * alpha_hz * (index / fs) + phase)
                    + beta_amplitude * math.sin(2.0 * math.pi * beta_hz * (index / fs) + phase)
                    for index in range(start_index, end_index)
                ],
                dtype=np.float32,
            )
            rows.append(waveform)
        return np.stack(rows).astype(np.float64) * scale_to_volts

    def analysis_windows(start: float, end: float) -> tuple[tuple[float, float], ...]:
        if end - start < window_s:
            return ((start, end),)
        windows: list[tuple[float, float]] = []
        cursor = start
        while cursor + window_s <= end:
            windows.append((cursor, cursor + window_s))
            cursor += window_step_s
        if not windows or windows[-1][1] < end:
            tail = (end - window_s, end)
            if tail not in windows:
                windows.append(tail)
        return tuple(windows)

    def process_segment(values: np.ndarray) -> np.ndarray:
        return _preprocess_eeg_segment(
            values,
            fs,
            mains_hz,
            bandpass_hz=bandpass_hz,
            bandpass_order=bandpass_order,
            notch_q=notch_q,
            common_average=common_average,
        )

    def window_engagement(
        processed: np.ndarray,
        segment_start: float,
        window_start: float,
        window_end: float,
    ) -> float:
        left = int(
            (Decimal(str(window_start - segment_start)) * Decimal(str(fs))).to_integral_value(
                rounding=ROUND_HALF_EVEN
            )
        )
        right = int(
            (Decimal(str(window_end - segment_start)) * Decimal(str(fs))).to_integral_value(
                rounding=ROUND_HALF_EVEN
            )
        )
        return _engagement(
            processed[:, left:right],
            fs,
            epsilon,
            welch_segment_s=welch_segment_s,
        )

    baseline_span = _sequence(_mapping(recipe["session"], "session")["baseline"], "baseline")
    baseline_start = _number(baseline_span[0], "baseline start")
    baseline_end = _number(baseline_span[1], "baseline end")
    baseline_processed = process_segment(raw_segment(baseline_start, baseline_end, baseline_beta))
    baseline_values = [
        window_engagement(baseline_processed, baseline_start, start, end)
        for start, end in analysis_windows(baseline_start, baseline_end)
    ]
    baseline_engagement = float(np.median(np.asarray(baseline_values, dtype=np.float64)))

    windows: list[dict[str, object]] = []
    for phase_id, start, end in _phases(recipe):
        processed = process_segment(raw_segment(start, end, task_beta))
        for window_start, window_end in analysis_windows(start, end):
            engagement = window_engagement(
                processed,
                start,
                window_start,
                window_end,
            )
            delta = 100.0 * ((engagement + epsilon) / (baseline_engagement + epsilon) - 1.0)
            windows.append(
                {
                    "delta_engagement_percent": delta,
                    "end_t_ns": _seconds_to_ns(window_end, "EEG window end"),
                    "engagement_ratio": engagement,
                    "phase_id": phase_id,
                    "sample_count": int(
                        (
                            Decimal(str(window_end - window_start)) * Decimal(str(fs))
                        ).to_integral_value(rounding=ROUND_HALF_EVEN)
                    ),
                    "start_t_ns": _seconds_to_ns(window_start, "EEG window start"),
                }
            )
    maximum = max(abs(float(row["delta_engagement_percent"])) for row in windows)
    return baseline_engagement, windows, maximum


def _window_id(phase_id: str, start_t_ns: int, end_t_ns: int) -> tuple[str, str]:
    payload = ["control-physio-grid-v2", phase_id, start_t_ns, end_t_ns]
    digest = hashlib.sha256(rfc8785.dumps(payload)).hexdigest()
    return f"cpw-{digest[:24]}", digest


def evaluate_recipe(recipe: Mapping[str, object]) -> dict[str, object]:
    """Mechanically derive the frozen 18-anchor sentinel vector from raw inputs."""

    if recipe.get("fixture_id") != _FIXTURE_ID:
        raise ValueError(f"fixture_id must be {_FIXTURE_ID}")
    if recipe.get("fixture_contract") != "m4-workflow-smoke-fixture-v1":
        raise ValueError("unsupported recipe contract")

    phase_precision, o1_value, tracking_error_ft, hover_stable_s = _trajectory_values(recipe)
    o1 = _entry(
        "O1",
        primary=_metric(o1_value, "percent"),
        state=_state_higher(o1_value, 90.0, 70.0),
        raw_metrics={"worst_phase_precision": _metric(o1_value, "percent")},
        trace={"phase_results": phase_precision},
        absolute_tolerance=1e-12,
    )

    trajectory = _mapping(recipe["trajectory"], "trajectory")
    spans_by_phase = _mapping(trajectory["offset_spans_s"], "offset spans")
    first_offset = min(
        _number(_sequence(raw_span, "offset span")[0], "offset start")
        for raw_spans in spans_by_phase.values()
        for raw_span in _sequence(raw_spans, "phase offset spans")
    )
    o2 = _entry(
        "O2",
        primary=_metric(tracking_error_ft, "ft"),
        state=_state_lower_inclusive(tracking_error_ft, 2.0, 5.0),
        raw_metrics={"peak_tracking_excursion": _metric(tracking_error_ft, "ft")},
        trace={"peak_t_ns": round(first_offset * 1_000_000_000)},
        absolute_tolerance=1e-12,
    )

    hover_start = next(start for name, start, _end in _phases(recipe) if name == "Hover")
    hover_end = next(end for name, _start, end in _phases(recipe) if name == "Hover")
    hover_inside = _phase_inside_intervals(recipe, "Hover")
    longest_hover_interval = max(hover_inside, key=lambda item: item[1] - item[0])
    longest_hover_ns = longest_hover_interval[1] - longest_hover_interval[0]
    capture_interval = next(
        (interval for interval in hover_inside if interval[1] - interval[0] >= 2_000_000_000),
        None,
    )
    hover_start_ns = _seconds_to_ns(hover_start, "hover start")
    hover_end_ns = _seconds_to_ns(hover_end, "hover end")
    if capture_interval is None:
        o3 = _entry(
            "O3",
            primary=None,
            state="unacceptable",
            raw_metrics={
                "observed_wait": _metric((hover_end_ns - hover_start_ns) / 1e9, "s"),
                "overshoot": _metric(tracking_error_ft, "ft"),
            },
            trace={
                "capture_confirmation_required_ns": 2_000_000_000,
                "longest_inside_hold_ns": longest_hover_ns,
                "observation_end_t_ns": hover_end_ns,
                "observation_start_t_ns": hover_start_ns,
            },
            override={"code": "capture_missed", "details": {}},
            primary_reason="composite_conjunction",
        )
    else:
        settling_s = (capture_interval[0] - hover_start_ns) / 1e9
        capture_state = (
            "desired"
            if tracking_error_ft <= 2.0 and settling_s <= 3.0
            else ("adequate" if tracking_error_ft <= 5.0 and settling_s <= 5.0 else "unacceptable")
        )
        o3 = _entry(
            "O3",
            primary=None,
            state=capture_state,
            raw_metrics={
                "overshoot": _metric(tracking_error_ft, "ft"),
                "settling_time": _metric(settling_s, "s"),
            },
            trace={
                "capture_confirmation_required_ns": 2_000_000_000,
                "capture_hold_end_t_ns": capture_interval[0] + 2_000_000_000,
                "capture_hold_start_t_ns": capture_interval[0],
                "observation_end_t_ns": hover_end_ns,
                "observation_start_t_ns": hover_start_ns,
            },
            primary_reason="composite_conjunction",
        )

    kinematics = _mapping(trajectory["kinematics"], "trajectory kinematics")
    speed_m_s = _vector_norm(kinematics["velocity_earth_m_s"], "earth velocity")
    angular_rate_deg_s = _vector_norm(kinematics["angular_rate_body_deg_s"], "body angular rate")
    speed_limit_m_s = 1.0
    angular_rate_limit_deg_s = 5.0
    stable_intervals = (
        hover_inside
        if speed_m_s <= speed_limit_m_s and angular_rate_deg_s <= angular_rate_limit_deg_s
        else ()
    )
    longest_stable = max(
        stable_intervals,
        key=lambda item: item[1] - item[0],
        default=(hover_start_ns, hover_start_ns),
    )
    hover_stable_s = (longest_stable[1] - longest_stable[0]) / 1e9
    o4 = _entry(
        "O4",
        primary=_metric(hover_stable_s, "s"),
        state=_state_higher(hover_stable_s, 10.0, 5.0),
        raw_metrics={"longest_stable_hover": _metric(hover_stable_s, "s")},
        trace={
            "angular_rate_deg_s": angular_rate_deg_s,
            "angular_rate_limit_deg_s": angular_rate_limit_deg_s,
            "end_t_ns": longest_stable[1],
            "speed_limit_m_s": speed_limit_m_s,
            "speed_m_s": speed_m_s,
            "start_t_ns": longest_stable[0],
        },
        absolute_tolerance=1e-12,
    )

    controls = _mapping(recipe["controls"], "controls")
    reversal = _mapping(controls["workload_reversal"], "workload_reversal")
    movement_phase_rows, total_movements, total_reversals, total_duration = _movement_phase_rows(
        recipe
    )
    workload_rate = total_movements / total_duration
    w_min = _number(reversal["w_min_hz"], "W_min")
    workload_ratio = workload_rate / w_min
    o5 = _entry(
        "O5",
        primary=_metric(workload_ratio, "ratio"),
        state=_state_lower_inclusive(workload_ratio, 2.0, 4.0),
        raw_metrics={
            "movement_count": _metric(total_movements, "count"),
            "observed_support": _metric(total_duration, "s"),
            "workload_rate": _metric(workload_rate, "Hz"),
        },
        trace={"phase_results": movement_phase_rows},
        absolute_tolerance=1e-12,
    )

    magnitude = _mapping(controls["magnitude"], "magnitude")
    calibration = _mapping(controls["full_travel"], "full travel")
    lower = _number(calibration["lower"], "lower endpoint")
    trim = _number(calibration["trim"], "trim")
    upper = _number(calibration["upper"], "upper endpoint")
    if not lower < trim < upper:
        raise ValueError("full-travel calibration must satisfy lower < trim < upper")
    magnitude_value = _number(magnitude["constant_full_travel_fraction"], "magnitude fraction")
    normalized_magnitude = (
        (magnitude_value - trim) / (upper - trim)
        if magnitude_value >= trim
        else (magnitude_value - trim) / (trim - lower)
    )
    weight = _number(magnitude["weight"], "magnitude weight")
    o6_value = 100.0 * math.sqrt(weight * normalized_magnitude**2)
    o6 = _entry(
        "O6",
        primary=_metric(o6_value, "percent_full_travel"),
        state=_state_lower_inclusive(o6_value, 30.0, 50.0),
        raw_metrics={"weighted_rms": _metric(o6_value, "percent_full_travel")},
        trace={
            "channel_count": 1,
            "lower": lower,
            "observed_support_ns": _seconds_to_ns(total_duration, "control support"),
            "trim": trim,
            "upper": upper,
            "weight": weight,
        },
        absolute_tolerance=1e-12,
    )
    reversal_rate = total_reversals / total_duration
    o7_state = (
        "desired"
        if reversal_rate < 2.0
        else ("adequate" if reversal_rate < 4.0 else "unacceptable")
    )
    o7 = _entry(
        "O7",
        primary=_metric(reversal_rate, "Hz"),
        state=o7_state,
        raw_metrics={
            "observed_support": _metric(total_duration, "s"),
            "reversal_count": _metric(total_reversals, "count"),
        },
        trace={"phase_results": movement_phase_rows},
        absolute_tolerance=1e-12,
    )

    o8_value = (o1_value / 100.0) ** 2 * math.sqrt(w_min / max(workload_rate, w_min))
    o8 = _entry(
        "O8",
        primary=_metric(o8_value, "ratio"),
        state=_state_higher(o8_value, 0.6, 0.4),
        raw_metrics={
            "phase_state_precision": _metric(o1_value, "percent"),
            "workload_rate": _metric(workload_rate, "Hz"),
            "workload_reference_rate": _metric(w_min, "Hz"),
        },
        trace={"dependency_ids": ["O1", "O5"]},
        absolute_tolerance=1e-15,
    )

    hover_trim = _mapping(controls["hover_trim"], "hover_trim")
    hover_span = _sequence(hover_trim["span_s"], "hover trim span")
    hover_trim_duration = _number(hover_span[1], "hover trim end") - _number(
        hover_span[0], "hover trim start"
    )
    hover_turning_points = int(
        round(2.0 * _number(hover_trim["frequency_hz"], "hover frequency") * hover_trim_duration)
    )
    micro_movements = max(0, hover_turning_points - 1)
    o9_value = micro_movements / hover_trim_duration
    o9_state = "desired" if o9_value < 1.0 else ("adequate" if o9_value < 2.0 else "unacceptable")
    o9 = _entry(
        "O9",
        primary=_metric(o9_value, "Hz"),
        state=o9_state,
        raw_metrics={
            "micro_movement_count": _metric(micro_movements, "count"),
            "stable_hover_duration": _metric(hover_trim_duration, "s"),
        },
        trace={
            "end_t_ns": round(_number(hover_span[1], "hover trim end") * 1e9),
            "start_t_ns": round(_number(hover_span[0], "hover trim start") * 1e9),
        },
        absolute_tolerance=1e-12,
    )

    translation = next(row for row in phase_precision if row["phase_id"] == "Translation")
    translation_start = int(translation["start_t_ns"])
    translation_end = int(translation["end_t_ns"])
    translation_spans = _sequence(spans_by_phase["Translation"], "translation offsets")
    offset_outside = abs(_number(trajectory["tracking_offset_m"], "tracking offset")) > _number(
        trajectory["envelope_radius_m"], "envelope radius"
    )
    translation_outside = (
        _merged_spans_ns(translation_start, translation_end, translation_spans)
        if offset_outside
        else ()
    )
    if not translation_outside:
        o10 = _not_applicable_entry(
            "O10",
            {
                "phase_end_t_ns": translation_end,
                "phase_start_t_ns": translation_start,
                "reason": "no_adequate_envelope_exit",
            },
        )
    else:
        recovery_start_ns = translation_outside[0][0]
        translation_inside = _phase_inside_intervals(recipe, "Translation")
        recovery_intervals = [
            interval for interval in translation_inside if interval[0] >= translation_outside[0][1]
        ]
        qualifying_recovery = next(
            (
                interval
                for interval in recovery_intervals
                if interval[1] - interval[0] >= 2_000_000_000
            ),
            None,
        )
        recovered_hold_ns = max(
            (right - left for left, right in recovery_intervals),
            default=0,
        )
        if qualifying_recovery is None:
            o10 = _entry(
                "O10",
                primary=None,
                state="unacceptable",
                raw_metrics={
                    "observed_wait": _metric((translation_end - recovery_start_ns) / 1e9, "s")
                },
                trace={
                    "event_t_ns": recovery_start_ns,
                    "observation_end_t_ns": translation_end,
                    "phase_start_t_ns": translation_start,
                    "recovered_hold_ns": recovered_hold_ns,
                    "required_hold_ns": 2_000_000_000,
                },
                override={"code": "recovery_missed", "details": {}},
                primary_reason="recovery_missed",
            )
        else:
            recovery_latency_s = (qualifying_recovery[0] - recovery_start_ns) / 1e9
            o10 = _entry(
                "O10",
                primary=_metric(recovery_latency_s, "s"),
                state=_state_lower_inclusive(recovery_latency_s, 5.0, 10.0),
                raw_metrics={"recovery_time": _metric(recovery_latency_s, "s")},
                trace={
                    "event_t_ns": recovery_start_ns,
                    "recovery_hold_start_t_ns": qualifying_recovery[0],
                    "required_hold_ns": 2_000_000_000,
                },
                absolute_tolerance=1e-12,
            )

    events = {
        str(event["event_id"]): _number(event["time_s"], "event time")
        for event in map(
            lambda item: _mapping(item, "event"), _sequence(recipe["events"], "events")
        )
    }
    response = _mapping(controls["event_response"], "event_response")
    pulses = {
        str(pulse["event_id"]): pulse
        for pulse in map(
            lambda item: _mapping(item, "control pulse"),
            _sequence(response["pulses_s"], "response pulses"),
        )
    }
    xu_rate = _number(
        _mapping(_mapping(recipe["streams"], "streams")["xu"], "xu")["rate_hz"],
        "X/U rate",
    )
    median_window_samples = (
        int((Decimal("0.020") * Decimal(str(xu_rate))).to_integral_value(rounding=ROUND_HALF_EVEN))
        + 1
    )
    detector_delay_samples = median_window_samples // 2
    response_amplitude = _number(response["amplitude_full_travel_fraction"], "response amplitude")

    def response_entry(
        anchor_id: str,
        event_id: str,
        *,
        desired_ms: float,
        adequate_ms: float,
        metric_id: str,
        miss_code: str,
    ) -> dict[str, object]:
        pulse = pulses[event_id]
        start_t_ns = _seconds_to_ns(pulse["start_s"], "pulse start")
        end_t_ns = _seconds_to_ns(pulse["end_s"], "pulse end")
        event_t_ns = _seconds_to_ns(events[event_id], "event time")
        correct_sign = _integer(pulse["correct_sign"], "correct sign")
        detected_t_ns = start_t_ns + _seconds_to_ns(
            detector_delay_samples / xu_rate, "median detector delay"
        )
        qualifying = (
            response_amplitude > 0.05 and correct_sign == 1 and end_t_ns - start_t_ns >= 100_000_000
        )
        trace = {
            "correct_sign": correct_sign,
            "detector_threshold_fraction": 0.05,
            "event_t_ns": event_t_ns,
            "median_window_ms": 20,
            "pulse_amplitude_fraction": response_amplitude,
            "pulse_end_t_ns": end_t_ns,
            "pulse_start_t_ns": start_t_ns,
            "required_duration_ns": 100_000_000,
        }
        if not qualifying:
            return _entry(
                anchor_id,
                primary=None,
                state="unacceptable",
                raw_metrics={
                    "observed_wait": _metric(min(2.0, (10_000_000_000 - event_t_ns) / 1e9), "s")
                },
                trace=trace,
                override={"code": miss_code, "details": {}},
                primary_reason=miss_code,
            )
        latency_ms = (detected_t_ns - event_t_ns) / 1e6
        return _entry(
            anchor_id,
            primary=_metric(latency_ms, "ms"),
            state=_state_lower_inclusive(latency_ms, desired_ms, adequate_ms),
            raw_metrics={metric_id: _metric(latency_ms, "ms")},
            trace={**trace, "detected_onset_t_ns": detected_t_ns},
            absolute_tolerance=1e-9,
        )

    o11 = response_entry(
        "O11",
        "disturbance-001",
        desired_ms=500.0,
        adequate_ms=1000.0,
        metric_id="disturbance_latency",
        miss_code="response_missed",
    )
    o12 = response_entry(
        "O12",
        "envelope-exit-001",
        desired_ms=300.0,
        adequate_ms=800.0,
        metric_id="envelope_drift_latency",
        miss_code="correction_missed",
    )

    hr0, hr_windows, h4_value = _rr_values(recipe)
    phase_states = {str(row["phase_id"]): str(row["state"]) for row in phase_precision}
    movement_states = {
        str(row["phase_id"]): (
            str(row["workload_state"]),
            str(row["reversal_state"]),
        )
        for row in movement_phase_rows
    }
    evidence_state_score = {"desired": 1.0, "adequate": 0.5, "unacceptable": 0.0}
    coupling_windows: list[dict[str, object]] = []
    for hr_window in hr_windows:
        phase_id = str(hr_window["phase_id"])
        workload_state, reversal_state = movement_states[phase_id]
        q_value = (
            0.5 * evidence_state_score[phase_states[phase_id]]
            + 0.25 * evidence_state_score[workload_state]
            + 0.25 * evidence_state_score[reversal_state]
        )
        signed_hr = float(hr_window["signed_delta_hr_percent"])
        activation = min(1.0, max(0.0, (signed_hr - 10.0) / 10.0))
        loss = 100.0 * activation * (1.0 - q_value)
        start_t_ns = int(hr_window["start_t_ns"])
        end_t_ns = int(hr_window["end_t_ns"])
        window_id, full_hash = _window_id(phase_id, start_t_ns, end_t_ns)
        coupling_windows.append(
            {
                "activation": activation,
                "control_score": q_value,
                "coupling_loss_percent": loss,
                "end_t_ns": end_t_ns,
                "phase_id": phase_id,
                "phase_precision_state": phase_states[phase_id],
                "reversal_state": reversal_state,
                "signed_delta_hr_percent": signed_hr,
                "start_t_ns": start_t_ns,
                "window_hash": full_hash,
                "window_id": window_id,
                "workload_state": workload_state,
            }
        )
    o13_value = max(float(row["coupling_loss_percent"]) for row in coupling_windows)
    o13_state = (
        "desired" if o13_value < 5.0 else ("adequate" if o13_value < 20.0 else "unacceptable")
    )
    o13 = _entry(
        "O13",
        primary=_metric(o13_value, "percent"),
        state=o13_state,
        raw_metrics={"maximum_coupling_loss": _metric(o13_value, "percent")},
        trace={"windows": coupling_windows},
        absolute_tolerance=1e-12,
    )

    gaze = _mapping(recipe["gaze"], "gaze")
    on_task_ns, off_task_ns, fixation_start_ns, cue_t_ns = _gaze_values(recipe)
    total_gaze_ns = on_task_ns + off_task_ns
    on_task_percent = float(Decimal(100) * Decimal(on_task_ns) / Decimal(total_gaze_ns))
    off_task_percent = float(Decimal(100) * Decimal(off_task_ns) / Decimal(total_gaze_ns))
    h1 = _entry(
        "H1",
        primary=_metric(on_task_percent, "percent"),
        state=_state_higher(on_task_percent, 85.0, 70.0),
        raw_metrics={
            "on_task_dwell": _metric(on_task_ns / 1e9, "s"),
            "total_gaze_dwell": _metric(total_gaze_ns / 1e9, "s"),
        },
        trace={
            "phase_count": len(_phases(recipe)),
            "primary_role": str(gaze["primary_role"]),
            "support_duration_ns": total_gaze_ns,
        },
        absolute_tolerance=1e-12,
    )
    if fixation_start_ns is None:
        h2 = _entry(
            "H2",
            primary=None,
            state="unacceptable",
            raw_metrics={"observed_wait": _metric(2.0, "s")},
            trace={
                "cue_t_ns": cue_t_ns,
                "fixation_horizon_ns": 2_000_000_000,
                "minimum_fixation_duration_ns": 100_000_000,
                "velocity_threshold_deg_s": 100.0,
            },
            override={"code": "fixation_missed", "details": {}},
            primary_reason="fixation_missed",
        )
    else:
        h2_value = (fixation_start_ns - cue_t_ns) / 1e6
        h2 = _entry(
            "H2",
            primary=_metric(h2_value, "ms"),
            state=_state_lower_inclusive(h2_value, 500.0, 1000.0),
            raw_metrics={"first_fixation_latency": _metric(h2_value, "ms")},
            trace={
                "cue_t_ns": cue_t_ns,
                "minimum_fixation_duration_ns": 100_000_000,
                "raw_fixation_start_t_ns": fixation_start_ns,
                "velocity_threshold_deg_s": 100.0,
            },
            absolute_tolerance=1e-9,
        )
    h3_state = (
        "desired"
        if off_task_percent < 5.0
        else ("adequate" if off_task_percent < 15.0 else "unacceptable")
    )
    h3 = _entry(
        "H3",
        primary=_metric(off_task_percent, "percent"),
        state=h3_state,
        raw_metrics={
            "off_task_dwell": _metric(off_task_ns / 1e9, "s"),
            "total_gaze_dwell": _metric(total_gaze_ns / 1e9, "s"),
        },
        trace={
            "other_scene_role": str(gaze["other_scene_role"]),
            "phase_count": len(_phases(recipe)),
            "support_duration_ns": total_gaze_ns,
        },
        absolute_tolerance=1e-12,
    )

    h4_state = "desired" if h4_value < 20.0 else ("adequate" if h4_value < 40.0 else "unacceptable")
    h4 = _entry(
        "H4",
        primary=_metric(h4_value, "percent"),
        state=h4_state,
        raw_metrics={"baseline_hr": _metric(hr0, "bpm")},
        trace={"windows": hr_windows},
        absolute_tolerance=1e-12,
    )
    baseline_engagement, eeg_windows, h5_value = _eeg_values(recipe)
    h5 = _entry(
        "H5",
        primary=_metric(h5_value, "percent"),
        state=_state_lower_inclusive(h5_value, 20.0, 50.0),
        raw_metrics={"baseline_engagement": _metric(baseline_engagement, "ratio")},
        trace={
            "channels": list(
                _sequence(_mapping(recipe["eeg"], "eeg")["engagement_channels"], "channels")
            ),
            "mains_frequency_hz": _number(
                _mapping(_mapping(recipe["streams"], "streams")["eeg"], "eeg stream")[
                    "mains_frequency_hz"
                ],
                "mains frequency",
            ),
            "windows": eeg_windows,
        },
        absolute_tolerance=1e-9,
    )

    by_id = {
        entry["anchor_id"]: entry
        for entry in (
            o1,
            o2,
            o3,
            o4,
            o5,
            o6,
            o7,
            o8,
            o9,
            o10,
            o11,
            o12,
            o13,
            h1,
            h2,
            h3,
            h4,
            h5,
        )
    }
    return {
        "anchors": [by_id[anchor_id] for anchor_id in _ANCHOR_IDS],
        "fixture_id": _FIXTURE_ID,
        "formal_run_authorized": False,
        "numeric_runtime": {
            "canonicalization": "rfc8785-jcs",
            "numpy_version": np.__version__,
            "scipy_version": scipy.__version__,
        },
        "oracle_id": _ORACLE_ID,
        "scientific_validation_status": "not_supported",
    }


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    raw = json.loads(args.recipe.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("recipe root must be an object")
    result = evaluate_recipe(cast(dict[str, object], raw))
    payload = rfc8785.dumps(result) + b"\n"
    if args.output is None:
        sys.stdout.buffer.write(payload)
    else:
        args.output.write_bytes(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
