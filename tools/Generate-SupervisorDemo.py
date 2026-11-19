"""Reproducible synthetic supervisor demonstration, isolated from blank defaults.

No simulator logs or fitted pilot distributions are used. Some A tolerances have
official FAA anchors; geometry, D bands, other tolerances, CPTs and case signals
remain explicit demonstration choices. See PARAMETER_BASIS_CN.md.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path

from pilot_assessment.scene_assessment.calculator import evaluate
from pilot_assessment.scene_assessment.catalog import load_catalog

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "examples" / "task-scope-2026-10-11"
CASES = {
    "01-proficient": (
        "熟练表现型（合成）",
        "A",
        "主要为 Desired，局部有自然的 Acceptable 波动；Pass。",
    ),
    "02-marginal": ("勉强合格表现型（合成）", "A", "较大但仍处于容差内的连贯波动，D/A交替；Pass。"),
    "03-unqualified": (
        "不合格表现型（合成）",
        "U",
        "较大振荡导致部分 Unacceptable，后续仍可恢复；Fail记录保留。",
    ),
}
METHOD = "sequential_bayes_compensation_v1"
MODEL_VERSION = "cpt-compensation-2026-09-23-v1"
HOVER_MODEL_VERSION = MODEL_VERSION
COMPENSATION_ALPHA = 0.2
CPT = [[0.10, 0.25, 0.65], [0.35, 0.63, 0.02], [0.90, 0.099, 0.001]]
BINARY_CPT = [[0.35, 0.65], [0.98, 0.02], [0.999, 0.001]]
STEP = 0.1
SIGNAL_VERSION = "continuous-multiscale-shared-speed-v3"
MICRO_COMPONENTS = ((0.43, 0.60), (0.79, 0.28), (1.27, 0.12))


def micro_motion(t: float, amplitude: float, phase: float = 0):
    """Bounded, repeatable continuous detail and its analytic velocity.

    Non-harmonic frequencies produce uneven corrections at 10 Hz sampling.
    These frequencies/amplitudes are illustration choices, not pilot statistics.
    Weights sum to one, so amplitude bounds displacement (not velocity).
    """
    value, rate = 0.0, 0.0
    for index, (frequency, weight) in enumerate(MICRO_COMPONENTS):
        omega = 2 * math.pi * frequency
        angle = omega * t + phase * (index + 1) + index * 0.71
        value += amplitude * weight * math.sin(angle)
        rate += amplitude * weight * omega * math.cos(angle)
    return value, rate


def balanced_speed_detail(t: float, duration: float, amplitude: float):
    """Smooth finite speed correction, antisymmetric and exactly zero-area.

    Integer cycles with a symmetric envelope cancel over the complete hold;
    both value and first derivative vanish at its boundaries.
    """
    f = t / duration
    if not 0 < f < 1:
        return 0.0
    # Keep corrections active throughout the hold, with smooth entry/exit.
    edge = min(t, duration - t) / min(0.8, duration / 2)
    envelope = math.sin(math.pi * min(1.0, edge) / 2) ** 2
    return (
        amplitude
        * envelope
        * sum(
            weight * math.sin(2 * math.pi * cycles * f)
            for cycles, weight in ((5, 0.50), (9, 0.30), (13, 0.20))
        )
    )


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def rounded(value):
    if isinstance(value, float):
        return round(value, 8)
    if isinstance(value, dict):
        return {key: rounded(item) for key, item in value.items()}
    return value


def wave(t: float, amplitude: float, phase: float = 0.0):
    """A smooth position/heading perturbation and its analytic derivative."""
    omega = 2 * math.pi / 12
    return amplitude * math.sin(omega * t + phase), amplitude * omega * math.cos(omega * t + phase)


def bump(t: float, start: float, duration: float, amplitude: float):
    """Finite pulse with continuous value and first derivative at each edge."""
    fraction = (t - start) / duration
    if fraction <= 0 or fraction >= 1:
        return 0.0, 0.0
    angle = math.pi * fraction
    return amplitude * math.sin(angle) ** 2, amplitude * math.pi / duration * math.sin(2 * angle)


def smooth_burst(t: float, start: float, duration: float, amplitude: float):
    """Higher-order pulse: position, velocity and acceleration join smoothly."""
    fraction = (t - start) / duration
    if fraction <= 0 or fraction >= 1:
        return 0.0, 0.0
    angle = math.pi * fraction
    return (
        amplitude * math.sin(angle) ** 4,
        4 * amplitude * math.pi / duration * math.sin(angle) ** 3 * math.cos(angle),
    )


def samples(duration: float):
    times = [round(index * STEP, 8) for index in range(math.floor(duration / STEP) + 1)]
    if not math.isclose(times[-1], duration, abs_tol=1e-8):
        times.append(round(duration, 8))
    return times


def configure(catalog):
    config = copy.deepcopy(catalog["configuration_template"])
    metrics = {metric["metric_id"]: metric for metric in catalog["metrics"]}
    targets = {
        "arrival_x_m": (0, 0.15, 0.4),
        "arrival_y_m": (0, 0.15, 0.4),
        "arrival_height_m": (6, 0.2, 0.6),
        "air_taxi_height_m": (6, 1, 3.048),
        "air_taxi_lateral_position_m": (0, 0.4, 1.2),
        "stop_x_m": (160, 1, 3),
        "stop_y_m": (0, 1, 3),
        "stop_height_m": (6, 0.3, 1),
        "quickstop_height_m": (6, 0.3, 1),
        "quickstop_lateral_position_m": (0, 0.4, 1.2),
        "hover_lower_height_m": (6, 0.5, 1.524),
        "hover_upper_height_m": (10, 0.5, 1.524),
        "hover_x_m": (0, 0.15, 0.4),
        "hover_y_m": (0, 0.15, 0.4),
        "transfer_x_m": (0, 0.15, 0.4),
        "transfer_y_m": (0, 0.15, 0.4),
    }
    for key, parameter in config["parameters"].items():
        metric = metrics[key]
        if metric.get("target_mode") == "item_profile":
            parameter.update(expected=None, reference_profile=[
                {"elapsed_s": 0, "expected": 0},
                {"elapsed_s": 6, "expected": 10},
                {"elapsed_s": 16.1, "expected": 10},
            ])
            desired, acceptable = 0.5, 1.5
        elif metric["comparison"] == "route_3d":
            parameter.update(
                expected=0,
                route_points=[
                    {"x_m": -120, "y_m": 0, "height_m": 12},
                    {"x_m": -60, "y_m": 0, "height_m": 9},
                    {"x_m": 0, "y_m": 0, "height_m": 6},
                ],
            )
            desired, acceptable = 0.6, 1.5
        elif metric["comparison"] == "radial":
            parameter.update(expected=0, center_u=0, center_v=0, target_radius=2)
            desired, acceptable = 0.3, 0.8
        elif metric["comparison"] == "angle_degrees":
            parameter["expected"] = 0
            desired, acceptable = {
                "hover_heading_deg": (3, 10),
                "quickstop_heading_deg": (2, 5),
            }.get(key, (3, 8))
        elif "_v" in key and key.endswith("_mps"):
            parameter["expected"] = 0
            desired, acceptable = 0.15, 0.5
        else:
            parameter["expected"], desired, acceptable = targets[key]
        radial = metric["comparison"] in ("radial", "route_3d")
        parameter["desired"].update(
            lower=0 if radial else -desired, upper=desired, unbounded_upper=False
        )
        parameter["acceptable"].update(
            lower=0 if radial else -acceptable, upper=acceptable, unbounded_upper=False
        )
    for model in config["skill_models"].values():
        model.pop("process_model", None)
        model.update(
            model_version=(
                HOVER_MODEL_VERSION if catalog["scene_id"] == "SCN-002" else MODEL_VERSION
            ),
            calibration="uncalibrated",
            parameter_source="demonstration",
            inference_method=METHOD,
            prior=[1 / 3] * 3,
            state_scores=[0, 50, 100],
            compensation={"alpha": COMPENSATION_ALPHA},
        )
        for checkpoint in model["checkpoint_models"].values():
            checkpoint["probabilities"] = copy.deepcopy(
                BINARY_CPT if checkpoint["states"] == ["D", "U"] else CPT
            )
    return config


def frame_builder(catalog, phase_schedule, state):
    data = copy.deepcopy(catalog["input_template"])
    metrics = {metric["metric_id"]: metric for metric in catalog["metrics"]}
    for item in catalog["items"]:
        keys = sorted(
            {key for checkpoint in item["checkpoints"] for key in checkpoint["metric_ids"]}
        )
        frames = []
        for phase in item["phases"]:
            phase_id = phase["phase_id"]
            origin, duration = phase_schedule[phase_id]
            for local in [0.0] if phase["single_frame"] else samples(duration):
                values = state(phase_id, local, origin + local)
                relevant = {
                    key: rounded(values[key])
                    for key in keys
                    if phase_id in metrics[key]["phase_ids"]
                }
                frames.append(
                    {
                        "timestamp_s": round(origin + local, 8),
                        "phase_id": phase_id,
                        "values": relevant,
                    }
                )
        data["items"][item["item_id"]] = {"frames": frames}
    return data


def scene_one_case(catalog, case):
    # Integral of speed is the declared longitudinal displacement: 0.5*v*6
    # during acceleration, v*T during hold, and 0.5*v*Tdec during braking.
    speed, hold = 10.0, 10.0
    stopping_x = 160.0
    braking = (stopping_x - 3 * speed - hold * speed) * 2 / speed
    schedule = {
        "preflight": (0, 0),
        "acceleration": (28.3, 6),
        "hold": (34.4, hold),
        "deceleration": (34.4 + hold + 0.2, braking),
        "stop": (34.4 + hold + 0.3 + braking, 5),
    }

    # Unrecorded 0.1s handoff gaps separate supplied phase slices. No trajectory
    # is reconstructed there. The stated distance integral refers to the named
    # manoeuvre phases; their gaps are not an extra scored motion assumption.
    def state(phase, local, timestamp):
        xy, vx = wave(timestamp, 0.035)
        yy, vy = wave(timestamp, 0.03, 0.4)
        zz, vz = wave(timestamp, 0.025, 1)
        heading = wave(timestamp, 0.35, 0.7)[0]
        if case == "02-marginal":
            omega = 2 * math.pi / 16
            xy, vx = 0.35 * math.sin(omega * timestamp), 0.35 * omega * math.cos(omega * timestamp)
            yy, vy = (
                0.35 * math.sin(omega * timestamp + 0.3),
                0.35 * omega * math.cos(omega * timestamp + 0.3),
            )
            zz, vz = (
                0.52 * math.sin(omega * timestamp + 0.6),
                0.52 * omega * math.cos(omega * timestamp + 0.6),
            )
            heading = 7.2 * math.sin(omega * timestamp + 0.3)
        elif case == "03-unqualified":
            xy, vx = wave(timestamp, 0.11)
            yy, vy = wave(timestamp, 0.11, 0.3)
            zz, vz = wave(timestamp, 0.15, 0.6)
            heading = wave(timestamp, 2.3, 0.3)[0]
        detail_scale = {"01-proficient": 1.0, "02-marginal": 1.3, "03-unqualified": 1.6}[case]
        dx, dvx = micro_motion(timestamp, 0.016 * detail_scale, 0.3)
        dy, dvy = micro_motion(timestamp, 0.012 * detail_scale, 1.2)
        dz, dvz = micro_motion(timestamp, 0.018 * detail_scale, 2.1)
        xy, vx, yy, vy, zz, vz = xy + dx, vx + dvx, yy + dy, vy + dvy, zz + dz, vz + dvz
        heading += micro_motion(timestamp, 0.32 * detail_scale, 0.8)[0]
        values = {
            metric["metric_id"]: True
            for metric in catalog["metrics"]
            if metric["rule"] == "must_be_true"
        }
        values.update(
            arrival_x_m=xy,
            arrival_y_m=yy,
            arrival_height_m=6 + zz,
            arrival_vx_mps=vx,
            arrival_vy_mps=vy,
            arrival_vz_mps=vz,
            arrival_heading_deg=heading % 360,
        )
        if phase in ("approach", "approach_deceleration"):
            progression = local + (12 if phase == "approach_deceleration" else 0)
            # Constant longitudinal deceleration from 10 m/s to zero across
            # 24 recorded seconds. Nodes define geometry, not this timing.
            x = -120 + 10 * progression - (5 / 24) * progression**2
            route_y = yy
            if case == "01-proficient":
                route_y += bump(progression, 9.5, 3.5, 0.85)[0]
            elif case == "02-marginal":
                fraction = max(0, min(1, (progression - 20) / 4))
                amplitude = 0.35 + 0.9 * (1 + math.cos(math.pi * fraction)) / 2
                route_y = amplitude * math.sin(2 * math.pi * timestamp / 16 + 0.3)
                route_y += micro_motion(timestamp, 0.08, 1.2)[0]
            elif case == "03-unqualified":
                route_y += bump(progression, 15, 5, 2.4)[0]
            values["approach_position_m"] = {
                "x_m": x + xy * progression / 24,
                "y_m": route_y,
                "height_m": 6 - x / 20 + zz,
            }
        air_height, air_y, air_heading = 6 + zz, yy, heading
        current_speed = speed
        if phase == "acceleration":
            f = local / 6
            pulse_amplitude = {
                "01-proficient": 0.7, "02-marginal": 1.6, "03-unqualified": 3.8,
            }[case]
            current_speed = speed * f
            if 0 < f < 1:
                current_speed += (
                    pulse_amplitude * math.sin(2 * math.pi * f) * math.sin(math.pi * f) ** 2
                    + balanced_speed_detail(local, 6, 0.12 * detail_scale)
                )
        if phase == "hold":
            # Odd smooth pulses have zero net longitudinal displacement:
            # overspeed and correction balance over their declared interval.
            if case == "01-proficient":
                f = (local - 2) / 4
                if 0 < f < 1:
                    current_speed += 1.2 * math.sin(2 * math.pi * f) * math.sin(math.pi * f) ** 2
                air_heading += bump(local, 4.1, 2.8, 4.3)[0]
                air_height += bump(local, 4.1, 2.8, 1.25)[0]
            elif case == "02-marginal":
                current_speed += 1.05 * math.sin(2 * math.pi * local / hold)
            else:
                f = (local - 2.5) / 5
                if 0 < f < 1:
                    current_speed += 3.2 * math.sin(2 * math.pi * f) * math.sin(math.pi * f) ** 2
            current_speed += balanced_speed_detail(local, hold, 0.32 * detail_scale)
        if case == "02-marginal":
            if phase == "acceleration":
                amplitude = 0.52 + (2.65 - 0.52) * (1 - math.cos(math.pi * local / 6)) / 2
            elif phase == "hold":
                fraction = max(0, min(1, (local - 7) / 3))
                amplitude = 0.88 + (2.65 - 0.88) * (1 + math.cos(math.pi * fraction)) / 2
            else:
                amplitude = 0.88
            air_height = 6 + amplitude * math.sin(2 * math.pi * timestamp / 16 + 0.6)
            if phase == "acceleration":
                lateral_amplitude = 0.35 + 0.73 * (1 - math.cos(math.pi * local / 6)) / 2
            elif phase == "hold":
                fraction = max(0, min(1, (local - 7) / 3))
                lateral_amplitude = 0.35 + 0.73 * (1 + math.cos(math.pi * fraction)) / 2
            else:
                lateral_amplitude = 0.35
            air_y = lateral_amplitude * math.sin(2 * math.pi * timestamp / 16 + 0.3)
        elif case == "03-unqualified" and phase == "hold":
            pulse = bump(local, 3, 5, 1)[0]
            air_height += 3.5 * pulse
            air_y += 1.5 * pulse
            air_heading += 10 * pulse
        # These airborne channels have no supplied velocity counterpart. Their
        # larger tolerance bands allow visibly larger continuous corrections.
        air_height += micro_motion(timestamp, 0.11 * detail_scale, 2.1)[0]
        air_y += micro_motion(timestamp, 0.05 * detail_scale, 1.2)[0]
        values.update(
            air_taxi_airspeed_mps=current_speed,
            air_taxi_height_m=air_height,
            air_taxi_lateral_position_m=air_y,
            air_taxi_heading_deg=air_heading % 360,
        )
        quick_height, quick_heading, quick_y = 6 + zz, heading, yy
        if case == "02-marginal":
            quick_height = 6 + 0.88 * math.sin(2 * math.pi * timestamp / 16 + 0.6)
            quick_heading = 4.6 * math.sin(2 * math.pi * timestamp / 16 + 0.3)
            quick_height += micro_motion(timestamp, 0.04, 2.1)[0]
            quick_heading += micro_motion(timestamp, 0.32, 0.8)[0]
        if case == "01-proficient" and phase == "deceleration":
            quick_height += bump(local, 2, 2.5, 0.34)[0]
            quick_heading += bump(local, 2, 2.5, 2.4)[0]
        if case == "03-unqualified" and phase == "deceleration":
            pulse = bump(local, 1, 3, 1)[0]
            quick_height += 1.3 * pulse
            quick_heading += 8 * pulse
            quick_y += 1.5 * pulse
            settling = max(0, min(1, (local - 4.5) / 1.5))
            factor = (1 + math.cos(math.pi * settling)) / 2
            quick_height = 6 + (quick_height - 6) * factor
            quick_heading *= factor
            quick_y *= factor
        if case == "03-unqualified" and phase == "stop":
            quick_height, quick_heading, quick_y = 6.0, 0.0, 0.0
        stop_x = stopping_x
        if phase == "stop":
            # Five seconds of supplied observations, not one selected best frame.
            # A smooth overshoot/correction plus smaller resolved movements;
            # all signals return to the target, while earlier U stays recorded.
            amplitude = {"01-proficient": 0.55, "02-marginal": 2.3,
                         "03-unqualified": 4.0}[case]
            stop_x += smooth_burst(local, 0, 5, amplitude)[0]
            stop_x += balanced_speed_detail(local, 5, 0.08 * detail_scale)
        values.update(
            stop_x_m=stop_x,
            stop_y_m=quick_y,
            stop_height_m=quick_height,
            quickstop_height_m=quick_height,
            quickstop_heading_deg=quick_heading % 360,
            quickstop_lateral_position_m=quick_y,
            quickstop_prohibited_event_count=0,
        )
        return values

    data = frame_builder(catalog, schedule, state)
    events = []
    if case == "03-unqualified":
        events = [
            {
                "item_id": "A-S2-05",
                "checkpoint_id": "A-S2-05-01/02/03",
                "phase": "hold",
                "injected_pulse": "加速阶段先超前再落后于参考速度；保速2.5–7.5s出现超调与反向修正，3–8s高度、横向及航向共同偏离，随后恢复。",  # noqa: E501
            },
            {
                "item_id": "A-S2-30",
                "checkpoint_id": "A-S2-30-03",
                "phase": "deceleration",
                "injected_pulse": "减速1–4s发生短暂高度、航向与横向偏离；末段恢复，停止位置通过。",
            },
        ]
    return data, {
        "phase_schedule": schedule,
        "injected_events": events,
        "kinematic_assumptions": {
            "hold_airspeed_mps": speed,
            "hold_duration_s": hold,
            "acceleration_duration_s": 6,
            "speed_reference_origin_phase": "acceleration",
            "speed_reference_end_elapsed_s": 16.1,
            "deceleration_duration_s": braking,
            "stop_observation_duration_s": 5,
            "stop_observation_frame_count": 51,
            "nominal_phase_distance_integral_m": stopping_x,
            "handoff_gap_policy": "0.1s未记录交接间隙，不据此推算位移；只展示已提供环节。",
        },
    }


HOVER_SCHEDULE = {
    "lower_1": (0, 5),
    "rise_1": (5.1, 5),
    "upper_1": (10.2, 5),
    "descend_1": (15.3, 5),
    "lower_2": (20.4, 5),
    "rise_2": (25.5, 5),
    "upper_2": (30.6, 5),
}


def hover_state(case, phase, local, timestamp):
    amplitudes = {
        "01-proficient": (0.04, -0.02, 0.05, 0.12),
        "02-marginal": (0.35, -0.18, 0.69, 0.26),
        "03-unqualified": (0.05, -0.02, 0.08, 0.12),
    }[case]
    omega = 2 * math.pi / 16
    envelope, envelope_rate = 1.0, 0.0
    position_factor = envelope * math.sin(omega * timestamp)
    velocity_factor = envelope_rate * math.sin(omega * timestamp) + envelope * omega * math.cos(
        omega * timestamp
    )
    if case == "02-marginal":
        # Broader excursions alternate with brief settled passages through
        # target. sin^3 keeps both displacement and drift speed low there.
        sin_t, cos_t = math.sin(omega * timestamp), math.cos(omega * timestamp)
        position_factor = sin_t**3
        velocity_factor = 3 * omega * sin_t**2 * cos_t
    x, y, height_error, desired_u = [amplitude * position_factor for amplitude in amplitudes]
    vx, vy, vz = [amplitude * velocity_factor for amplitude in amplitudes[:3]]
    detail_scale = {"01-proficient": 1.0, "02-marginal": 1.25, "03-unqualified": 1.5}[case]
    dx, dvx = micro_motion(timestamp, 0.016 * detail_scale, 0.3)
    dy, dvy = micro_motion(timestamp, 0.012 * detail_scale, 1.2)
    dz, dvz = micro_motion(timestamp, 0.020 * detail_scale, 2.1)
    x, vx, y, vy = x + dx, vx + dvx, y + dy, vy + dvy
    height_error, vz = height_error + dz, vz + dvz
    desired_u += micro_motion(timestamp, 0.035 * detail_scale, 0.8)[0]
    if case == "01-proficient" and phase == "upper_1":
        pulse, rate = bump(local, 0.25, 4.5, 1)
        x += 0.18 * pulse
        height_error += 0.60 * pulse
        desired_u += 0.23 * pulse
        vx += 0.18 * rate
        vz += 0.60 * rate
    elif case == "03-unqualified" and phase == "lower_2":
        pulse, rate = smooth_burst(local, 0.25, 4.5, 1)
        x += 0.75 * pulse
        height_error += 2.1 * pulse
        desired_u += 0.9 * pulse
        vx += 0.75 * rate
        vz += 2.1 * rate
    # Choose a correlated aim signal, then derive heading from the rigid-ray
    # geometry. The exported spot is recomputed below from that same heading.
    heading = math.degrees(math.atan2(desired_u - y, 20 - x))
    if phase in ("rise_1", "descend_1", "rise_2"):
        if case == "02-marginal":
            x += bump(local, 0, 5, 0.02)[0]
            heading += bump(local, 0, 5, 4)[0] * math.sin(omega * timestamp)
        elif case == "03-unqualified" and phase == "rise_1":
            x += bump(local, 1, 3, 0.8)[0]
            heading += bump(local, 1, 3, 11)[0]
        elif case == "01-proficient" and phase == "rise_1":
            x += bump(local, 1.0, 3.5, 0.22)[0]
    # The rigid forward-facing laser is level (pitch=0) and intersects the
    # world-fixed X=20m plane. u is world +Y; v is height above disc centre.
    u = y + (20 - x) * math.tan(math.radians(heading))
    v = height_error
    hit = math.hypot(u, v) <= 2
    laser = {
        "status": "hit" if hit else "miss",
        "u_m": u if hit else None,
        "v_m": v if hit else None,
    }
    return {
        "hover_lower_height_m": 6 + height_error,
        "hover_upper_height_m": 10 + height_error,
        "hover_x_m": x,
        "hover_y_m": y,
        "hover_vx_mps": vx,
        "hover_vy_mps": vy,
        "hover_vz_mps": vz,
        "hover_heading_deg": heading % 360,
        "laser_lower_spot": laser,
        "laser_upper_spot": laser,
        "transfer_x_m": x,
        "transfer_y_m": y,
        "transfer_heading_deg": heading % 360,
    }


def scene_two_case(catalog, case):
    data = frame_builder(
        catalog,
        HOVER_SCHEDULE,
        lambda phase, local, timestamp: hover_state(case, phase, local, timestamp),
    )
    events = []
    if case == "03-unqualified":
        events = [
            {
                "item_id": "SCENE-VERTICAL",
                "phase": "rise_1",
                "timestamp_s": [6.1, 9.1],
                "injected_pulse": "仅第一次上升1–4s发生一次横向漂移与航向超调，随后恢复；其余升降保持稳定。",  # noqa: E501
            },
            {
                "item_id": "A-S2-02",
                "phase": "lower_2",
                "timestamp_s": [20.65, 25.15],
                "injected_pulse": "仅第二次下点悬停0.25–4.75s发生一次关联的位置、高度、运动与指向失误，末段恢复；最后上点悬停稳定。",  # noqa: E501
            },
        ]
    return data, {
        "phase_schedule": HOVER_SCHEDULE,
        "injected_events": events,
        "kinematic_assumptions": {
            "velocity_source": "analytic derivative of the synthetic position signal",
            "laser_plane_x_m": 20,
            "laser_pitch_deg": 0,
            "laser_lower_center_world_m": [20, 0, 6],
            "laser_upper_center_world_m": [20, 0, 10],
            "laser_uv_axes": "u=world+Y; v=world+height relative to disc center",
        },
    }


def generate_case(scene_id, case):
    """Return configuration, input and external provenance for tests/presenters."""
    catalog = load_catalog(scene_id, "3.0")
    config = configure(catalog)
    data, details = (
        scene_one_case(catalog, case) if scene_id == "SCN-001" else scene_two_case(catalog, case)
    )
    label, expected_grade, description = CASES[case]
    return (
        config,
        data,
        {
            "case_id": case,
            "name": label,
            "description": description,
            "expected_grade": expected_grade,
            "expected_pass_fail": "Fail" if expected_grade == "U" else "Pass",
            "signal_version": SIGNAL_VERSION,
            "continuous_detail": {
                "components_hz_and_weights": MICRO_COMPONENTS,
                "construction": (
                    "bounded multi-frequency analytic position; corresponding velocity; "
                    "shared ray geometry"
                ),
                "speed_hold_detail": (
                    "symmetric envelope times integer-cycle sines; zero net displacement"
                ),
                "calibration": "synthetic illustration only; not fitted to real pilot recordings",
            },
            **details,
        },
    )


def diagnostics(scene_id, data, report):
    """Independent checks on exported raw fields, plus real-calculator summary."""
    result = {
        "schema_version": "external-demo-diagnostics-1.0",
        "scene_id": scene_id,
        "calculation_status": report["calculation_status"],
        "grade": report["grade"],
        "passed": report["passed"],
        "items": [],
        "motion_checks": {},
    }
    for item in report["items"]:
        quantity = item["skill_quantification"]
        record = {
            "item_id": item["item_id"],
            "name": item["name"],
            "grade": item["grade"],
            "frame_distribution": item["frame_distribution"],
            "score": quantity.get("score"),
            "posterior": quantity.get("posterior"),
            "checkpoints": [],
        }
        for point in item["checkpoints"]:
            metrics = []
            for metric in point["metrics"]:
                deviations = [
                    row["deviation"]
                    for row in metric["timeline"]
                    if row.get("deviation") is not None
                ]
                numeric = [
                    row["value"]
                    for row in metric["timeline"]
                    if type(row.get("value")) in (int, float)
                ]
                rates = [
                    abs(
                        (
                            ((right["value"] - left["value"] + 180) % 360 - 180)
                            if "heading" in metric["metric_id"]
                            else right["value"] - left["value"]
                        )
                        / (right["timestamp_s"] - left["timestamp_s"])
                    )
                    for left, right in zip(metric["timeline"], metric["timeline"][1:], strict=False)
                    if left["phase_id"] == right["phase_id"]
                    and type(left.get("value")) in (int, float)
                    and type(right.get("value")) in (int, float)
                ]
                metrics.append(
                    {
                        "metric_id": metric["metric_id"],
                        "frame_distribution": metric["frame_distribution"],
                        "minimum_raw": min(numeric) if numeric else None,
                        "maximum_raw": max(numeric) if numeric else None,
                        "maximum_absolute_deviation": max(map(abs, deviations))
                        if deviations
                        else None,
                        "maximum_sampled_raw_rate_per_s": max(rates) if rates else None,
                    }
                )
            record["checkpoints"].append(
                {
                    "checkpoint_id": point["checkpoint_id"],
                    "grade": point["grade"],
                    "frame_distribution": point["frame_distribution"],
                    "metrics": metrics,
                }
            )
        result["items"].append(record)
    pairs = []
    if scene_id == "SCN-001":
        stop = data["items"]["A-S2-30"]["frames"][-1]["values"]
        assert stop["stop_height_m"] == stop["quickstop_height_m"]
        assert stop["stop_y_m"] == stop["quickstop_lateral_position_m"]
        result["motion_checks"]["stop_duplicate_coordinates_identical"] = True
    else:
        combined = copy.deepcopy(data["items"]["A-S2-02"]["frames"])
        residuals, misses = [], 0
        for frame in combined:
            values = frame["values"]
            height_key = (
                "hover_lower_height_m"
                if frame["phase_id"].startswith("lower")
                else "hover_upper_height_m"
            )
            values["actual_height_m"] = values[height_key]
            values["height_error_m"] = values["actual_height_m"] - (
                6 if "lower" in height_key else 10
            )
            u = values["hover_y_m"] + (20 - values["hover_x_m"]) * math.tan(
                math.radians(values["hover_heading_deg"])
            )
            v = values["height_error_m"]
            spot = values["laser_lower_spot" if "lower" in height_key else "laser_upper_spot"]
            if spot["status"] == "hit":
                residuals.append(max(abs(u - spot["u_m"]), abs(v - spot["v_m"])))
                assert math.hypot(u, v) <= 2 + 1e-7
            else:
                misses += 1
                assert spot["u_m"] is None and spot["v_m"] is None and math.hypot(u, v) > 2
        assert max(residuals, default=0) < 1e-6, residuals
        result["motion_checks"].update(
            laser_maximum_forward_geometry_residual_m=max(residuals, default=0),
            laser_miss_frame_count=misses,
            laser_status_consistent=True,
        )
        for component, velocity in (
            ("hover_x_m", "hover_vx_mps"),
            ("hover_y_m", "hover_vy_mps"),
            ("actual_height_m", "hover_vz_mps"),
        ):
            pairs.append((component, velocity, combined))
    errors = {}
    for component, velocity, frames in pairs:
        residuals = []
        for left, middle, right in zip(frames, frames[1:], frames[2:], strict=False):
            if left["phase_id"] != right["phase_id"]:
                continue
            finite_difference = (right["values"][component] - left["values"][component]) / (
                right["timestamp_s"] - left["timestamp_s"]
            )
            residuals.append(abs(finite_difference - middle["values"][velocity]))
        errors[component] = max(residuals, default=0)
    result["motion_checks"]["central_difference_vs_exported_velocity_max_error_mps"] = errors
    # Analytic derivatives and central finite differences need not be exactly
    # equal. This bound catches unrelated velocity fields at 0.1s sampling.
    assert all(error < 0.03 for error in errors.values()), errors
    result["motion_checks"]["derivative_consistency_check"] = (
        "pass (<0.03m/s central-difference discrepancy)"
    )
    return result


def parameter_markdown(catalog, config):
    lines = [
        f"# {catalog['scene_id']} 演示参数",
        "",
        "全部配置用于本次导师演示，尚未经机型、专家或飞行样本校准。部分 A 外边界直接参考 FAA 数值，其余 D/A、三维航迹距离、激光与概率参数为工程设定；以下注明直接数值出处，其余不可称为官方默认值。",  # noqa: E501
        "",
        "D 与 A 都按闭区间处理，先判 D，再判 A；超出 A 为 U。角度比较使用最短角差。",
        "",
        "| 检查点 | 输入量 | 目标 | D 范围 | A 外边界 |",
        "|---|---|---|---|---|",
    ]
    metrics = {metric["metric_id"]: metric for metric in catalog["metrics"]}
    for item in catalog["items"]:
        for checkpoint in item["checkpoints"]:
            for key in checkpoint["metric_ids"]:
                metric = metrics[key]
                parameter = config["parameters"].get(key)
                if parameter is None:
                    target = "true" if metric["rule"] == "must_be_true" else "0次"
                    desired, acceptable = "满足目标", "无 A；不满足则 U"
                elif metric.get("target_mode") == "item_profile":
                    target = "；".join(
                        f"{node['elapsed_s']:g}s→{node['expected']:g}{metric['unit']}"
                        for node in parameter["reference_profile"]
                    )
                    desired = f"相对当时目标±{parameter['desired']['upper']:g} {metric['unit']}"
                    acceptable = (
                        f"相对当时目标±{parameter['acceptable']['upper']:g} {metric['unit']}"
                    )
                elif metric["comparison"] in ("radial", "route_3d"):
                    target = (
                        "到三维折线的空间距离=0"
                        if metric["comparison"] == "route_3d"
                        else "靶心(0,0)，圆盘半径2m"
                    )
                    desired = f"0–{parameter['desired']['upper']}m"
                    acceptable = f"≤{parameter['acceptable']['upper']}m"
                else:
                    target = f"{parameter['expected']:g} {metric['unit']}"
                    desired = f"±{parameter['desired']['upper']:g} {metric['unit']}"
                    acceptable = f"±{parameter['acceptable']['upper']:g} {metric['unit']}"
                lines.append(
                    f"| {checkpoint['name']} | {key} | {target} | {desired} | {acceptable} |"
                )
    lines += [
        "",
        "数值出处：[FAA-S-ACS-2 Commercial Pilot Powered-Lift ACS](https://www.faa.gov/training_testing/testing/acs/commercial_pl_acs_2.pdf)。CP.IV.C.S5 的空中滑行高度±10ft对应本包A±3.048m；CP.IV.A.S5 对高于10ft的悬停高度±5ft对应A±1.524m（本包6m/10m均以AGL定义）；CP.IV.A.S8 悬停航向±10°；CP.VI.A.S3快速减速航向±5°。",  # noqa: E501
        "",
        "悬停和到点X/Y各±0.4m形成的方框角点距中心约0.566m，小于2ft=0.6096m，是保守的几何适配，不是FAA逐轴原文。到点高度、垂直通道、D范围及其它未逐项列出来源的数字均是场景演示假设。",
        "",
        "## 贝叶斯演示配置",
        "",
        "每个飞行 item 使用独立三状态模型：Low / Middle / High；先验各1/3，状态分数0/50/100。起飞前检查单只给规则结果，不推断飞行能力。",  # noqa: E501
        "",
        "| 假设状态 | P(D) | P(A) | P(U) |",
        "|---|---:|---:|---:|",
        "| Low | 0.10 | 0.25 | 0.65 |",
        "| Middle | 0.35 | 0.63 | 0.02 |",
        "| High | 0.90 | 0.099 | 0.001 |",
        "",
        "二值禁止事件检查点使用 D/U：Low=[0.35,0.65]，Middle=[0.98,0.02]，High=[0.999,0.001]。这些是明确的假设分布；High 与 Middle 都很少出现 U，但 High 更常出现 D。",  # noqa: E501
        "",
        "贝叶斯网络继承上一帧状态，结合本帧CPT观测和更新系数计算新的概率：",
        "",
        "`q = normalize(prior × likelihood); p = (1-alpha) × q + alpha × target; "
        "score = sum(p × state_scores)`",
        "",
        "最后结果为末帧模型状态，不是整段平均质量。"
        "原有任何 U 仍使规则结果为 Fail，不由模型分数覆盖。",
        "",
        "所有检查点采用同一组 CPT 是演示假设；停止后提供5秒51帧连续观察。网络按有效帧更新，响应受采样率影响。",  # noqa: E501
        "",
        "## 贝叶斯网络参数与过程",
        "",
        "alpha=0.2 为每有效帧的更新系数，属于未标定演示参数。D/A/U分别对应高/中/低观测目标。",
        "",
        "阶段切换保留概率。检查点用自身CPT更新；item相乘同帧适用检查点的似然，采用条件独立假设，每帧更新一次。观测目标取最差等级。末帧与最终分一致。",  # noqa: E501
        "",
        "每帧保留更新前先验、CPT观测更新、观测目标、更新系数、概率调整量和更新后概率。",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument(
        "--with-reports",
        action="store_true",
        help="Evaluate and export reports using the current real calculator",
    )
    args = parser.parse_args()
    manifest = {
        "title": "双场景导师演示包",
        "schema_version": "external-demo-manifest-1.0",
        "synthetic": True,
        "validated": False,
        "parameter_status": (
            "official tolerance anchors plus engineering demonstration choices; CPT uncalibrated"
        ),
        "inference_method": METHOD,
        "compensation_alpha": COMPENSATION_ALPHA,
        "sampling_step_s": STEP,
        "signal_version": SIGNAL_VERSION,
        "scenes": [],
    }
    for scene_id in ("SCN-001", "SCN-002"):
        catalog = load_catalog(scene_id, "3.0")
        directory = args.output / scene_id
        scene = {
            "scene_id": scene_id,
            "name": catalog["name"],
            "configuration_file": f"{scene_id}/configuration.json",
            "cases": [],
        }
        config = configure(catalog)
        write_json(directory / "configuration.json", config)
        (directory / "PARAMETERS_CN.md").write_text(
            parameter_markdown(catalog, config), encoding="utf-8"
        )
        for case in CASES:
            _, data, details = generate_case(scene_id, case)
            write_json(directory / f"{case}.input.json", data)
            details.update(
                input_file=f"{scene_id}/{case}.input.json",
                frame_counts={key: len(value["frames"]) for key, value in data["items"].items()},
            )
            if args.with_reports:
                report = evaluate(config, data)
                if (
                    report["calculation_status"] != "complete"
                    or report["grade"] != details["expected_grade"]
                ):
                    raise RuntimeError(
                        f"{scene_id}/{case}: expected complete {details['expected_grade']}, "
                        f"got {report.get('grade')} / {report.get('issues')}"
                    )
                write_json(directory / f"{case}.report.json", report)
                details["report_file"] = f"{scene_id}/{case}.report.json"
                details["actual_grade"] = report["grade"]
                checked = diagnostics(scene_id, data, report)
                write_json(directory / f"{case}.diagnostics.json", checked)
                details["diagnostics_file"] = f"{scene_id}/{case}.diagnostics.json"
                details["item_summary"] = [
                    {
                        "item_id": item["item_id"],
                        "grade": item["grade"],
                        "frame_proportions": item["frame_distribution"]["proportions"],
                        "score": item["score"],
                    }
                    for item in checked["items"]
                ]
            scene["cases"].append(details)
            print(
                f"{scene_id}/{case}: {sum(details['frame_counts'].values())} item-frames; "
                f"expected {details['expected_grade']}"
            )
        manifest["scenes"].append(scene)
    write_json(args.output / "manifest.json", manifest)
    (args.output / "README_CN.md").write_text(
        """# 双场景导师演示包

本包包含两个场景各三组人工合成数据，全部使用同场景同一套参数，便于比较规则结果与量化结果。熟练、勉强合格和不合格均指合成案例的设计意图，没有使用真实飞行日志或真实学员标签。部分 A 容差采用 FAA powered-lift 条款的数值；D 内区间、其余场景参数和 CPT 均为明确标记的演示设定。

当前信号版本：`continuous-multiscale-shared-speed-v3`。SCN-001速度检查覆盖加速与保速，以加速第一帧为0秒，共用参考曲线0s→0m/s、6s→10m/s、16.1s→10m/s；数据含连续细节起伏。停止后观察为5秒51帧，展示到点后的偏移和恢复；这只是演示数据长度，不是系统新增采样要求。旧保速时长字段和hold_end阶段已移除，必须同时加载新configuration.json和新.input.json。已打开的结果窗口保留旧评估快照。[当前原值预览](CURRENT_FLIGHT_PREVIEW.svg)包含新速度曲线、停止位置和悬停位置。SIGNAL_PREVIEW为上轮历史图，不能代表本轮加速检查。

先在软件运行下面的演示步骤。[参数依据](PARAMETER_BASIS_CN.md)区分官方数值、工程适配与场景设定。当前使用贝叶斯网络，item/检查点共用同一套方法，分数最后由概率换算。

贝叶斯网络根据每帧观测更新状态概率，继承上一帧结果。更新系数alpha=0.2为未标定演示值，可在模型编辑器修改。已有旧配置导入时自动升级，先验、CPT和分值保留。

结果窗口显示全程概率换算分数与D/A/U色带（绿D、黄A、红U）；末帧模型分数等于过程终点，不是整段平均质量。明细保留先验、CPT观测更新、观测目标、系数和概率调整量。阶段变化保留概率；缺测不伪造完整结果。起飞前检查单只记录完成性。

建议演示顺序：熟练表现型 → 勉强合格表现型 → 不合格表现型。熟练表现型大部分为D，少量自然A波动；勉强合格表现型在D/A内较大幅度波动，二者均Pass。不合格表现型包含U并在后段恢复，仍为Fail。实际占比、极值与模型结果由计算器实算，案例名称不作为模型输入。

不合格表现型的U集中在局部片段，后段D恢复可使末帧模型分数重新接近100，但其Fail仍保留。末帧状态不是整段质量或真实飞行员能力排名，必须结合完整过程查看。

打开软件后先选择场景，加载该文件夹的 configuration.json，再导入同文件夹的 .input.json，点击开始评估。切换同场景案例时只需重新导入数据；切换场景时加载对应配置。默认模板也使用新方法，但先验和CPT需填写。

评估完成后点击 item 卡片，打开完整结果窗口。先看本项规则 P/F、末帧模型分数与状态概率，再查看item过程和各检查点完整原始曲线。原值图保留真实时刻、输入、目标及容差，便于定位偏离和恢复。模型跨阶段继承概率，完整报告的曲线末点与末帧结果相等。

每帧继承上帧更新后的概率。同帧item使用各检查点联合似然，不乘它们的后验。缺测后不伪造完整概率，任务整体不完整时末点不给最终分。任何已知U的规则Fail始终保留。

- SCN-001：起飞前检查单保留为准备项；飞行评分为加速与保速 → 快速减速／快速停止。当前任务没有正常进近至悬停，确认结束不单独计分。目标在配置中手工明确。X 朝前、Y 为横向、高度向上、航向0°朝+X。
- SCN-002：下点6m停留5秒 → 上升 → 上点10m停留5秒 → 下降 → 下点停留5秒 → 上升 → 上点停留5秒。圆盘在世界 X=20m，低/高圆心分别为(20,0,6)/(20,0,10)，半径2m；激光假定固定在机头、俯仰0°。光点由同一帧位置与航向计算，交点超出圆盘时明确为 miss。
- SCN-002 只有两个 item：定点悬停保持、垂直升降控制。定点悬停保持内分别检查水平位置、悬停高度、航向和激光。水平速度归入水平位置检查，垂直速度归入高度检查；速度阈值与激光属于项目适配，高度和水平位置不合成三维距离或使用同一容差。
- 两场景采样主要为0.1秒；item 内帧有精确 timestamp_s。环节由输入直接提供，系统不识别事件边界。四次悬停共204帧都只放在 A-S2-02 下，每帧同时提供位置、当前低/高点对应高度、速度、航向和光点，单独的高度 item 已取消。
- 横向/高度扰动是在慢漂移和局部失误上叠加0.43/0.79/1.27Hz连续细节，各通道相位不同，避免整齐重复和逐帧白噪声。输入中存在位置与速度的悬停环节，速度使用对应位置函数的解析导数。保速细节采用平滑包络内的整周期分量，正负面积抵消。频率、幅度是合成演示选择，没有使用实测飞行统计。未要求的完整动力学、操纵杆或升降高度字段不额外塞入输入 schema。
- 0.1秒环节交接间隙属于未记录数据，系统和本包都不对其补帧或推算运动。SCN-001 纵向距离积分仅用于说明已提供的加速、保速和减速环节的合成关系；不是连续全机仿真。

各场景 PARAMETERS_CN.md 列出所有检查点的实际目标、D/A阈值与 CPT。manifest.json 是外部演示说明，记录案例预期、帧数量、环节时间和人为注入偏差位置，不能作为训练输入导入。每例 diagnostics.json 记录实算 D/A/U 占比、原始量范围与采样变化率，并独立检查位置/速度导数关系及激光几何一致性。

勉强合格悬停案例没有把所有量同时推到各自A上限：本包激光水平安装，高度误差会直接变成靶面竖直误差。慢漂移高度振幅0.69m、横向光点0.26m，另叠加幅度上界分别0.025m和0.04375m的连续细节；两者的保守合成半径上界约0.777m，小于0.8m的A边界。位置与光点共同决定对应航向，不能把航向当作独立随机噪声填入。实际各量极值在 diagnostics.json 中记录。

用现有项目环境复现：

```powershell
.\\.venv\\Scripts\\python.exe tools/Generate-SupervisorDemo.py --with-reports
.\\.venv\\Scripts\\python.exe tools/Generate-LocalResponseSensitivity.py
.\\.venv\\Scripts\\python.exe tools/Build-SupervisorDemoPresentation.py
```

配置中的 calibration=uncalibrated 与 parameter_source=demonstration 会保留在结果中。该包用于展示系统机制；是否适合真实机型、任务难度和能力区分，之后需要独立专家审查与真实数据校准。
""",  # noqa: E501
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
