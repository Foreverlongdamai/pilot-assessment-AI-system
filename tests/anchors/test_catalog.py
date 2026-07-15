from __future__ import annotations

import json
import struct
from copy import deepcopy
from hashlib import sha256
from importlib import import_module
from importlib.resources import files
from pathlib import Path
from typing import Any, cast

import pytest
import rfc8785
from jsonschema.validators import Draft202012Validator
from pydantic import JsonValue

from pilot_assessment.contracts.anchor_execution import AnchorCatalog, AnchorRuntimeRegistry

ANCHOR_IDS = (
    "O1",
    "O2",
    "O3",
    "O4",
    "O5",
    "O6",
    "O7",
    "O8",
    "O9",
    "O10",
    "O11",
    "O12",
    "O13",
    "H1",
    "H2",
    "H3",
    "H4",
    "H5",
)
PROVIDER_IDS = (
    "movement-events-v1",
    "gaze-aoi-intervals-v1",
    "fixation-intervals-v1",
    "control-physio-windows-v2",
    "ecg-hr-trace-v1",
    "eeg-engagement-windows-v1",
)
PARAMETER_SCHEMA_IDS = tuple(f"{item.lower()}-parameters-0.1" for item in ANCHOR_IDS) + tuple(
    f"{item}-parameters-0.1" for item in PROVIDER_IDS
)

# anchor_id: plugin, required inputs, dependency IDs, artifact id/kind/schema
ENTRY_MATRIX = {
    "O1": (
        "o1-phase-state-precision",
        ("stream.X", "semantic.phases", "semantic.envelopes"),
        (),
        "desired-envelope-mask",
        "sample_mask",
        "desired-envelope-mask-v0.1",
    ),
    "O2": (
        "o2-peak-tracking-excursion",
        ("stream.X", "reference.task_reference", "semantic.phases"),
        (),
        "tracking-error-trace",
        "sample_trace",
        "tracking-error-trace-v0.1",
    ),
    "O3": (
        "o3-terminal-capture-quality",
        ("stream.X", "semantic.targets", "semantic.events", "semantic.envelopes"),
        (),
        "capture-trace",
        "event_trace",
        "capture-trace-v0.1",
    ),
    "O4": (
        "o4-sustained-hover-time",
        ("stream.X", "semantic.envelopes"),
        (),
        "stable-hover-mask",
        "sample_mask",
        "stable-hover-mask-v0.1",
    ),
    "O5": (
        "o5-workload-rate",
        ("stream.U", "semantic.control_mappings"),
        ("movement-events",),
        "movement-events",
        "event_trace",
        "movement-events-v0.1",
    ),
    "O6": (
        "o6-control-magnitude-rms",
        ("stream.U", "semantic.control_mappings"),
        (),
        "rms-contribution-trace",
        "component_trace",
        "rms-contribution-trace-v0.1",
    ),
    "O7": (
        "o7-control-reversal-rate",
        ("stream.U", "semantic.control_mappings"),
        ("movement-events",),
        "reversal-events",
        "event_trace",
        "reversal-events-v0.1",
    ),
    "O8": (
        "o8-tpx-composite",
        (),
        ("o1-result", "o5-result"),
        "tpx-component-trace",
        "component_trace",
        "tpx-component-trace-v0.1",
    ),
    "O9": (
        "o9-dead-band-activity",
        ("stream.U",),
        ("o1-mask", "o4-mask", "movement-events"),
        "micro-movement-events",
        "event_trace",
        "micro-movement-events-v0.1",
    ),
    "O10": (
        "o10-recovery-time",
        ("stream.X", "semantic.events", "semantic.envelopes"),
        (),
        "recovery-events",
        "event_trace",
        "recovery-events-v0.1",
    ),
    "O11": (
        "o11-disturbance-latency",
        ("stream.U", "semantic.events", "semantic.control_mappings"),
        (),
        "response-events",
        "event_trace",
        "response-events-v0.1",
    ),
    "O12": (
        "o12-envelope-drift-latency",
        ("stream.X", "stream.U", "semantic.envelopes", "semantic.control_mappings"),
        (),
        "correction-events",
        "event_trace",
        "correction-events-v0.1",
    ),
    "O13": (
        "o13-physio-control-coupling",
        ("stream.X", "stream.U", "stream.ECG", "semantic.phases"),
        ("o1-profile", "o5-profile", "o7-profile", "h4-result", "h4-trace"),
        "joined-coupling-windows",
        "window_trace",
        "joined-coupling-windows-v0.1",
    ),
    "H1": (
        "h1-aoi-dwell",
        ("stream.I", "stream.G", "semantic.aois", "semantic.phases"),
        ("gaze-aoi-intervals",),
        "phase-dwell",
        "phase_trace",
        "phase-dwell-v0.1",
    ),
    "H2": (
        "h2-first-fixation-latency",
        ("stream.I", "stream.G", "semantic.events", "semantic.aois"),
        ("fixation-intervals",),
        "event-fixation-trace",
        "event_trace",
        "event-fixation-trace-v0.1",
    ),
    "H3": (
        "h3-off-task-dwell",
        ("stream.I", "stream.G", "semantic.aois", "semantic.phases"),
        ("gaze-aoi-intervals",),
        "phase-off-task-dwell",
        "phase_trace",
        "phase-off-task-dwell-v0.1",
    ),
    "H4": (
        "h4-ecg-fluctuation",
        ("stream.ECG", "semantic.baselines", "semantic.phases"),
        ("control-physio-windows", "ecg-hr-trace"),
        "control-physio-trace",
        "window_trace",
        "control-physio-trace-v0.1",
    ),
    "H5": (
        "h5-eeg-fluctuation",
        ("stream.EEG", "semantic.baselines", "semantic.phases"),
        ("eeg-engagement-windows",),
        "engagement-trace",
        "window_trace",
        "engagement-trace-v0.1",
    ),
}

# dependency_id: kind, anchor, resource, schema, artifact kind, required
DEPENDENCY_MATRIX = {
    "movement-events": (
        "preprocessing_dependency",
        None,
        "movement-events-v1",
        "movement-events-v1-output-v0.1",
        "movement-events-table",
        True,
    ),
    "o1-result": ("result_dependency", "O1", None, "anchor-result-0.2.0", None, True),
    "o5-result": ("result_dependency", "O5", None, "anchor-result-0.2.0", None, True),
    "o1-mask": (
        "artifact_dependency",
        "O1",
        "desired-envelope-mask",
        "desired-envelope-mask-v0.1",
        "sample_mask",
        True,
    ),
    "o4-mask": (
        "artifact_dependency",
        "O4",
        "stable-hover-mask",
        "stable-hover-mask-v0.1",
        "sample_mask",
        True,
    ),
    "o1-profile": (
        "algorithm_profile_dependency",
        None,
        "o1-algorithm-profile",
        "o1-algorithm-profile-output-v0.1",
        None,
        True,
    ),
    "o5-profile": (
        "algorithm_profile_dependency",
        None,
        "o5-algorithm-profile",
        "o5-algorithm-profile-output-v0.1",
        None,
        True,
    ),
    "o7-profile": (
        "algorithm_profile_dependency",
        None,
        "o7-algorithm-profile",
        "o7-algorithm-profile-output-v0.1",
        None,
        True,
    ),
    "h4-result": ("result_dependency", "H4", None, "anchor-result-0.2.0", None, True),
    "h4-trace": (
        "artifact_dependency",
        "H4",
        "control-physio-trace",
        "control-physio-trace-v0.1",
        "window_trace",
        False,
    ),
    "gaze-aoi-intervals": (
        "preprocessing_dependency",
        None,
        "gaze-aoi-intervals-v1",
        "gaze-aoi-intervals-v1-output-v0.1",
        "gaze-aoi-intervals-table",
        True,
    ),
    "fixation-intervals": (
        "preprocessing_dependency",
        None,
        "fixation-intervals-v1",
        "fixation-intervals-v1-output-v0.1",
        "fixation-intervals-table",
        True,
    ),
    "control-physio-windows": (
        "preprocessing_dependency",
        None,
        "control-physio-windows-v2",
        "control-physio-windows-v2-output-v0.1",
        "control-physio-windows-table",
        True,
    ),
    "ecg-hr-trace": (
        "preprocessing_dependency",
        None,
        "ecg-hr-trace-v1",
        "ecg-hr-trace-v1-output-v0.1",
        "ecg-hr-trace-table",
        True,
    ),
    "eeg-engagement-windows": (
        "preprocessing_dependency",
        None,
        "eeg-engagement-windows-v1",
        "eeg-engagement-windows-v1-output-v0.1",
        "eeg-engagement-windows-table",
        True,
    ),
}

# anchor: policy schema, D conditions, A conditions, sorted computed-U overrides
SCORER_MATRIX = {
    "O1": (
        "ordered-dau-threshold-policy-v0.1",
        (("primary_value", ">=", 90, "percent"),),
        (("primary_value", ">=", 70, "percent"),),
        (),
    ),
    "O2": (
        "ordered-dau-threshold-policy-v0.1",
        (("primary_value", "<=", 2, "ft"),),
        (("primary_value", "<=", 5, "ft"),),
        (),
    ),
    "O3": (
        "dau-conjunction-policy-v0.1",
        (("overshoot", "<=", 2, "ft"), ("settling_time", "<=", 3, "s")),
        (("overshoot", "<=", 5, "ft"), ("settling_time", "<=", 5, "s")),
        ("capture_missed",),
    ),
    "O4": (
        "ordered-dau-threshold-policy-v0.1",
        (("primary_value", ">=", 10, "s"),),
        (("primary_value", ">=", 5, "s"),),
        (),
    ),
    "O5": (
        "ordered-dau-threshold-policy-v0.1",
        (("primary_value", "<=", 2, "ratio"),),
        (("primary_value", "<=", 4, "ratio"),),
        (),
    ),
    "O6": (
        "ordered-dau-threshold-policy-v0.1",
        (("primary_value", "<=", 30, "percent_full_travel"),),
        (("primary_value", "<=", 50, "percent_full_travel"),),
        (),
    ),
    "O7": (
        "ordered-dau-threshold-policy-v0.1",
        (("primary_value", "<", 2, "Hz"),),
        (("primary_value", "<", 4, "Hz"),),
        (),
    ),
    "O8": (
        "ordered-dau-threshold-policy-v0.1",
        (("primary_value", ">=", 0.6, "ratio"),),
        (("primary_value", ">=", 0.4, "ratio"),),
        (),
    ),
    "O9": (
        "ordered-dau-threshold-policy-v0.1",
        (("primary_value", "<", 1, "Hz"),),
        (("primary_value", "<", 2, "Hz"),),
        ("no_stable_hover",),
    ),
    "O10": (
        "ordered-dau-threshold-policy-v0.1",
        (("primary_value", "<=", 5, "s"),),
        (("primary_value", "<=", 10, "s"),),
        ("recovery_missed",),
    ),
    "O11": (
        "ordered-dau-threshold-policy-v0.1",
        (("primary_value", "<=", 500, "ms"),),
        (("primary_value", "<=", 1000, "ms"),),
        ("response_missed",),
    ),
    "O12": (
        "ordered-dau-threshold-policy-v0.1",
        (("primary_value", "<=", 300, "ms"),),
        (("primary_value", "<=", 800, "ms"),),
        ("correction_missed",),
    ),
    "O13": (
        "ordered-dau-threshold-policy-v0.1",
        (("primary_value", "<", 5, "percent"),),
        (("primary_value", "<", 20, "percent"),),
        ("physio_trace_unavailable",),
    ),
    "H1": (
        "ordered-dau-threshold-policy-v0.1",
        (("primary_value", ">=", 85, "percent"),),
        (("primary_value", ">=", 70, "percent"),),
        ("no_gaze_dwell",),
    ),
    "H2": (
        "ordered-dau-threshold-policy-v0.1",
        (("primary_value", "<=", 500, "ms"),),
        (("primary_value", "<=", 1000, "ms"),),
        ("fixation_missed",),
    ),
    "H3": (
        "ordered-dau-threshold-policy-v0.1",
        (("primary_value", "<", 5, "percent"),),
        (("primary_value", "<", 15, "percent"),),
        ("no_gaze_dwell",),
    ),
    "H4": (
        "ordered-dau-threshold-policy-v0.1",
        (("primary_value", "<", 20, "percent"),),
        (("primary_value", "<", 40, "percent"),),
        ("ecg_baseline_nonpositive", "ecg_rr_unavailable", "physio_trace_unavailable"),
    ),
    "H5": (
        "ordered-dau-threshold-policy-v0.1",
        (("primary_value", "<=", 20, "percent"),),
        (("primary_value", "<=", 50, "percent"),),
        ("eeg_baseline_degenerate", "eeg_spectrum_degenerate"),
    ),
}

# schema_id: ordered ``name:dtype:unit`` fields, order keys. A trailing ? is nullable.
DESCRIPTOR_MATRIX = {
    "desired-envelope-mask-v0.1": (
        "phase_id:utf8:id,t_ns:i64:ns,source_row_id:i64:index,axis_order:i64:index,axis_id:utf8:id,inside:bool:bool",
        "phase_id,t_ns,source_row_id,axis_order,axis_id",
    ),
    "tracking-error-trace-v0.1": (
        "phase_id:utf8:id,t_ns:i64:ns,source_row_id:i64:index,error_x:f64:ft,error_y:f64:ft,error_z:f64:ft,error_norm:f64:ft",
        "phase_id,t_ns,source_row_id",
    ),
    "capture-trace-v0.1": (
        "event_id:utf8:id,t_ns:i64:ns,source_row_id:i64:index,overshoot:f64:ft,inside_hover:bool:bool",
        "event_id,t_ns,source_row_id",
    ),
    "stable-hover-mask-v0.1": (
        "phase_id:utf8:id,t_ns:i64:ns,source_row_id:i64:index,stable:bool:bool",
        "phase_id,t_ns,source_row_id",
    ),
    "movement-events-v0.1": (
        "phase_id:utf8:id,channel_id:utf8:id,event_t_ns:i64:ns,event_id:utf8:id,event_kind:utf8:id,amplitude:f64:percent_full_travel",
        "phase_id,channel_id,event_t_ns,event_id",
    ),
    "rms-contribution-trace-v0.1": (
        "phase_id:utf8:id,channel_id:utf8:id,start_t_ns:i64:ns,end_t_ns:i64:ns,rms:f64:percent_full_travel,weight:f64:ratio",
        "phase_id,channel_id,start_t_ns,end_t_ns",
    ),
    "reversal-events-v0.1": (
        "phase_id:utf8:id,channel_id:utf8:id,event_t_ns:i64:ns,event_id:utf8:id,amplitude:f64:percent_full_travel",
        "phase_id,channel_id,event_t_ns,event_id",
    ),
    "tpx-component-trace-v0.1": (
        "component_id:utf8:id,source_anchor_id:utf8:id,source_result_fingerprint:utf8:hex,state:utf8:id,score:f64:ratio",
        "component_id",
    ),
    "micro-movement-events-v0.1": (
        "phase_id:utf8:id,channel_id:utf8:id,event_t_ns:i64:ns,event_id:utf8:id,amplitude:f64:percent_full_travel",
        "phase_id,channel_id,event_t_ns,event_id",
    ),
    "recovery-events-v0.1": (
        "event_id:utf8:id,onset_t_ns:i64:ns,recovered_t_ns?:i64:ns,latency_ms:f64:ms,missed:bool:bool",
        "event_id,onset_t_ns",
    ),
    "response-events-v0.1": (
        "event_id:utf8:id,channel_id:utf8:id,onset_t_ns?:i64:ns,latency_ms:f64:ms,correct_sign:bool:bool,missed:bool:bool",
        "event_id,channel_id",
    ),
    "correction-events-v0.1": (
        "event_id:utf8:id,channel_id:utf8:id,exit_t_ns:i64:ns,onset_t_ns?:i64:ns,latency_ms:f64:ms,correct_sign:bool:bool,missed:bool:bool",
        "event_id,exit_t_ns,channel_id",
    ),
    "joined-coupling-windows-v0.1": (
        "window_id:utf8:id,start_t_ns:i64:ns,end_t_ns:i64:ns,phase_id:utf8:id,signed_delta_hr:f64:percent,control_score:f64:ratio,coupling_loss:f64:percent,window_hash:utf8:hex",
        "start_t_ns,end_t_ns,window_id",
    ),
    "phase-dwell-v0.1": (
        "phase_id:utf8:id,role_id:utf8:id,dwell_ns:i64:ns,weighted_dwell_ns:f64:ns,total_dwell_ns:i64:ns",
        "phase_id,role_id",
    ),
    "event-fixation-trace-v0.1": (
        "event_id:utf8:id,fixation_id:utf8:id,start_t_ns:i64:ns,end_t_ns:i64:ns,aoi_id:utf8:id,latency_ms:f64:ms",
        "event_id,start_t_ns,fixation_id",
    ),
    "phase-off-task-dwell-v0.1": (
        "phase_id:utf8:id,role_id:utf8:id,off_task:bool:bool,dwell_ns:i64:ns,total_dwell_ns:i64:ns",
        "phase_id,role_id",
    ),
    "control-physio-trace-v0.1": (
        "window_id:utf8:id,start_t_ns:i64:ns,end_t_ns:i64:ns,phase_id:utf8:id,median_hr_bpm:f64:bpm,signed_delta_hr:f64:percent,window_hash:utf8:hex",
        "start_t_ns,end_t_ns,window_id",
    ),
    "engagement-trace-v0.1": (
        "window_id:utf8:id,start_t_ns:i64:ns,end_t_ns:i64:ns,phase_id:utf8:id,channel_id:utf8:id,engagement_ratio:f64:ratio,delta_engagement:f64:percent,window_hash:utf8:hex",
        "start_t_ns,end_t_ns,window_id,channel_id",
    ),
}
PROVIDER_OUTPUT_DESCRIPTOR_MATRIX = {
    "movement-events-v1-output-v0.1": (
        "phase_id:utf8:id,channel_id:utf8:id,event_t_ns:i64:ns,event_id:utf8:id,event_kind:utf8:id,amplitude:f64:percent_full_travel",
        "phase_id,channel_id,event_t_ns,event_id",
    ),
    "gaze-aoi-intervals-v1-output-v0.1": (
        "interval_id:utf8:id,start_t_ns:i64:ns,end_t_ns:i64:ns,gaze_source_row_id:i64:index,frame_id:utf8:id,aoi_id:utf8:id,role_id:utf8:id,association_valid:bool:bool",
        "start_t_ns,end_t_ns,interval_id",
    ),
    "fixation-intervals-v1-output-v0.1": (
        "fixation_id:utf8:id,start_t_ns:i64:ns,end_t_ns:i64:ns,aoi_id:utf8:id,role_id:utf8:id",
        "start_t_ns,end_t_ns,fixation_id",
    ),
    "control-physio-windows-v2-output-v0.1": (
        "window_id:utf8:id,start_t_ns:i64:ns,end_t_ns:i64:ns,phase_id:utf8:id,window_hash:utf8:hex",
        "start_t_ns,end_t_ns,window_id",
    ),
    "ecg-hr-trace-v1-output-v0.1": (
        "second_peak_id:utf8:id,second_peak_t_ns:i64:ns,rr_seconds:f64:s,hr_bpm:f64:bpm",
        "second_peak_t_ns,second_peak_id",
    ),
    "eeg-engagement-windows-v1-output-v0.1": (
        "window_id:utf8:id,start_t_ns:i64:ns,end_t_ns:i64:ns,phase_id:utf8:id,channel_id:utf8:id,engagement_ratio:f64:ratio,epsilon_used:f64:V^2,window_hash:utf8:hex",
        "start_t_ns,end_t_ns,window_id,channel_id",
    ),
}
PROVIDER_IDENTITY_MATRIX = (
    (
        "movement-events-v1",
        "1.0.0",
        "movement-events-v1-parameters-0.1",
        "movement-events-v1-output-v0.1",
        "movement-events-table",
    ),
    (
        "gaze-aoi-intervals-v1",
        "1.0.0",
        "gaze-aoi-intervals-v1-parameters-0.1",
        "gaze-aoi-intervals-v1-output-v0.1",
        "gaze-aoi-intervals-table",
    ),
    (
        "fixation-intervals-v1",
        "1.0.0",
        "fixation-intervals-v1-parameters-0.1",
        "fixation-intervals-v1-output-v0.1",
        "fixation-intervals-table",
    ),
    (
        "control-physio-windows-v2",
        "2.0.0",
        "control-physio-windows-v2-parameters-0.1",
        "control-physio-windows-v2-output-v0.1",
        "control-physio-windows-table",
    ),
    (
        "ecg-hr-trace-v1",
        "1.0.0",
        "ecg-hr-trace-v1-parameters-0.1",
        "ecg-hr-trace-v1-output-v0.1",
        "ecg-hr-trace-table",
    ),
    (
        "eeg-engagement-windows-v1",
        "1.0.0",
        "eeg-engagement-windows-v1-parameters-0.1",
        "eeg-engagement-windows-v1-output-v0.1",
        "eeg-engagement-windows-table",
    ),
)

EMPTY_PARAMETER_SCHEMAS = {
    "o1-parameters-0.1",
    "o2-parameters-0.1",
    "o8-parameters-0.1",
    "h1-parameters-0.1",
    "h3-parameters-0.1",
    "h4-parameters-0.1",
    "h5-parameters-0.1",
    "gaze-aoi-intervals-v1-parameters-0.1",
    "ecg-hr-trace-v1-parameters-0.1",
}
EXPECTED_PROPERTY_NAMES = {
    "o3-parameters-0.1": ("capture_hold_ns",),
    "o4-parameters-0.1": ("max_behavioral_excursion_ns",),
    "o5-parameters-0.1": ("w_min_hz",),
    "o6-parameters-0.1": ("channel_weights",),
    "o7-parameters-0.1": ("minimum_reversal_amplitude_pct", "minimum_reversal_separation_ns"),
    "o9-parameters-0.1": ("micro_movement_max_amplitude_pct", "nearest_match_tolerance_ns"),
    "o10-parameters-0.1": (
        "adequate_exit_confirmation_ns",
        "desired_hold_ns",
        "recovery_horizon_ns",
    ),
    "o11-parameters-0.1": (
        "baseline_lookback_ns",
        "causal_median_window_ns",
        "control_excursion_threshold_pct",
        "minimum_excursion_duration_ns",
        "response_horizon_ns",
    ),
    "o12-parameters-0.1": (
        "baseline_lookback_ns",
        "causal_median_window_ns",
        "control_excursion_threshold_pct",
        "correction_horizon_ns",
        "exit_confirmation_ns",
        "minimum_excursion_duration_ns",
    ),
    "o13-parameters-0.1": (
        "control_weight_o1",
        "control_weight_o5",
        "control_weight_o7",
        "signed_hr_activation_full_pct",
        "signed_hr_activation_start_pct",
    ),
    "h2-parameters-0.1": ("fixation_horizon_ns",),
    "movement-events-v1-parameters-0.1": (
        "derivative_deadband_pct_per_s",
        "filtfilt_padlen_cap_samples",
        "filtfilt_padtype",
        "grid_period_ns",
        "lowpass_cutoff_hz",
        "lowpass_order",
        "minimum_filter_sample_count",
        "minimum_movement_amplitude_pct",
        "minimum_sign_run_ns",
    ),
    "fixation-intervals-v1-parameters-0.1": (
        "angular_velocity_threshold_deg_s",
        "minimum_fixation_duration_ns",
    ),
    "control-physio-windows-v2-parameters-0.1": ("window_length_ns", "window_step_ns"),
    "eeg-engagement-windows-v1-parameters-0.1": (
        "alpha_high_hz",
        "alpha_low_hz",
        "bandpass_high_hz",
        "bandpass_low_hz",
        "bandpass_order",
        "bandpass_padlen_cap_samples",
        "bandpass_padtype",
        "beta_high_hz",
        "beta_low_hz",
        "channel_conversions",
        "epsilon",
        "mains_frequency_hz",
        "minimum_filter_sample_count",
        "minimum_finite_bins_per_band",
        "minimum_psd_sample_count",
        "notch_padlen_cap_samples",
        "notch_padtype",
        "notch_q",
        "theta_high_hz",
        "theta_low_hz",
        "welch_overlap_fraction",
        "welch_segment_length_ns",
        "window_length_ns",
        "window_step_ns",
    ),
}

PROPERTY_DEFAULTS = {
    "o3-parameters-0.1": {"capture_hold_ns": 2_000_000_000},
    "o4-parameters-0.1": {"max_behavioral_excursion_ns": 0},
    "o5-parameters-0.1": {"w_min_hz": 1.0},
    "o7-parameters-0.1": {
        "minimum_reversal_amplitude_pct": 2.0,
        "minimum_reversal_separation_ns": 150_000_000,
    },
    "o9-parameters-0.1": {
        "micro_movement_max_amplitude_pct": 5.0,
        "nearest_match_tolerance_ns": 20_000_000,
    },
    "o10-parameters-0.1": {
        "adequate_exit_confirmation_ns": 100_000_000,
        "desired_hold_ns": 2_000_000_000,
        "recovery_horizon_ns": 15_000_000_000,
    },
    "o11-parameters-0.1": {
        "baseline_lookback_ns": 1_000_000_000,
        "causal_median_window_ns": 20_000_000,
        "control_excursion_threshold_pct": 5.0,
        "minimum_excursion_duration_ns": 100_000_000,
        "response_horizon_ns": 2_000_000_000,
    },
    "o12-parameters-0.1": {
        "baseline_lookback_ns": 1_000_000_000,
        "causal_median_window_ns": 20_000_000,
        "control_excursion_threshold_pct": 5.0,
        "correction_horizon_ns": 2_000_000_000,
        "exit_confirmation_ns": 100_000_000,
        "minimum_excursion_duration_ns": 100_000_000,
    },
    "o13-parameters-0.1": {
        "control_weight_o1": 0.5,
        "control_weight_o5": 0.25,
        "control_weight_o7": 0.25,
        "signed_hr_activation_full_pct": 20.0,
        "signed_hr_activation_start_pct": 10.0,
    },
    "h2-parameters-0.1": {"fixation_horizon_ns": 2_000_000_000},
    "movement-events-v1-parameters-0.1": {
        "derivative_deadband_pct_per_s": 0.5,
        "filtfilt_padlen_cap_samples": 15,
        "filtfilt_padtype": "odd",
        "grid_period_ns": 10_000_000,
        "lowpass_cutoff_hz": 5.0,
        "lowpass_order": 4,
        "minimum_filter_sample_count": 3,
        "minimum_movement_amplitude_pct": 0.5,
        "minimum_sign_run_ns": 50_000_000,
    },
    "fixation-intervals-v1-parameters-0.1": {
        "angular_velocity_threshold_deg_s": 100.0,
        "minimum_fixation_duration_ns": 100_000_000,
    },
    "control-physio-windows-v2-parameters-0.1": {
        "window_length_ns": 30_000_000_000,
        "window_step_ns": 5_000_000_000,
    },
    "eeg-engagement-windows-v1-parameters-0.1": {
        "alpha_high_hz": 13.0,
        "alpha_low_hz": 8.0,
        "bandpass_high_hz": 35.0,
        "bandpass_low_hz": 3.0,
        "bandpass_order": 4,
        "bandpass_padlen_cap_samples": 27,
        "bandpass_padtype": "odd",
        "beta_high_hz": 30.0,
        "beta_low_hz": 13.0,
        "epsilon": 1e-12,
        "mains_frequency_hz": 50.0,
        "minimum_filter_sample_count": 4,
        "minimum_finite_bins_per_band": 2,
        "minimum_psd_sample_count": 2,
        "notch_padlen_cap_samples": 6,
        "notch_padtype": "odd",
        "notch_q": 30.0,
        "theta_high_hz": 8.0,
        "theta_low_hz": 4.0,
        "welch_overlap_fraction": 0.5,
        "welch_segment_length_ns": 2_000_000_000,
        "window_length_ns": 4_000_000_000,
        "window_step_ns": 2_000_000_000,
    },
}
EXPECTED_PARAMETER_SHA256 = {
    "control-physio-windows-v2-parameters-0.1": (
        "130b16643fd8df5ead13c60658aade87f319883769f3a20c7eccd7ff8c89cde2"
    ),
    "ecg-hr-trace-v1-parameters-0.1": (
        "6515527e84f8d63d2c785255c2a73ff70f5a8c4f8dcd87a2db63e8d6df2b5b3b"
    ),
    "eeg-engagement-windows-v1-parameters-0.1": (
        "1bab00c1366802e9364f2870aab1dabb49f4ab25a41288d35b851ed8bd06691a"
    ),
    "fixation-intervals-v1-parameters-0.1": (
        "858b9f33219e1d9005100adde0e5e74c7dc10c7394932078b12cf9c64efc0b48"
    ),
    "gaze-aoi-intervals-v1-parameters-0.1": (
        "48374620dc6344bbf721e490cde4941ac141e19e8f1bef755d5959a0d23c9148"
    ),
    "h1-parameters-0.1": "6163cfb66a4a7b950362c063ac6edb5ce97fb2929747281b9a4caebe8965584a",
    "h2-parameters-0.1": "57b47ded04807752234e26e1c1f94fbb416f4d0dbd053a438a47fd7c4b7bb167",
    "h3-parameters-0.1": "41ff613d08a3045cb3bf8d4add5afd2493d10a113a7d6864cd233231b5cc2998",
    "h4-parameters-0.1": "84babef21edca40c72775525f234be4642fb087198120fdcee1a345eb0c69aa7",
    "h5-parameters-0.1": "6e893055a8849352c62d52b307e969aab421f11b2e966db94db50f18ebf96947",
    "movement-events-v1-parameters-0.1": (
        "25c64e03d742a5c46c2b85db954faf26636fad387a513eced0823057935196a0"
    ),
    "o1-parameters-0.1": "f633b20ef02553b62ad4ecf3e7c4f086a15bf7e2372471044bb9debafe3facb2",
    "o10-parameters-0.1": "191a434f48425f6fe1e5d650861f920b22def8e622d57c4b018f547941a23dca",
    "o11-parameters-0.1": "d983932fb19d043465afceca8932c455769c496109594e90e236aa471951e1ab",
    "o12-parameters-0.1": "68c5fbc7a6e3f7c437e23f62ca36c5a7bb3125a1f6207f869871c30dec9b2df0",
    "o13-parameters-0.1": "029c3a9e074ea644086a36d68f96c5bb609e64a86d3c8e49b5bd7a97c111afa6",
    "o2-parameters-0.1": "45d70f70fb3fb947ac4f8eb680fe99c7ccc95fa0ed7f52c5e80858186cb24199",
    "o3-parameters-0.1": "af287d3f3519a8758a677713722b63d35a0769f5f640a4fba999111f618c581f",
    "o4-parameters-0.1": "1cca21d3c6689ca09e8cef8a3c2f65440d67cf5a9311e06f855463bf8b8dbf32",
    "o5-parameters-0.1": "de03ec6e38bc581462a301d1f3a1717b05649fdd11642e2e79d4885313447df2",
    "o6-parameters-0.1": "b212253d02670533af7b6e6d3adc10089f6555d36a0b3ba9c768f6ecb3243975",
    "o7-parameters-0.1": "b34f7c14027eac47e928b2400cb7bb54a090c353940e2ca29311c5a8e930dc50",
    "o8-parameters-0.1": "ed844324cb560cdc61ad5d47ca68b0fa3a87c4d0f88acf62445feb96f246e26e",
    "o9-parameters-0.1": "cad6eee5191adfadcec0853cce3d19ddea6007cb9c51aed0805eebe09491b597",
}
FIXED_PROVIDER_ALGORITHM_MATRIX = {
    "movement-events-v1-parameters-0.1": ("movement-events-v1", "1.0.0", "12.5"),
    "gaze-aoi-intervals-v1-parameters-0.1": (
        "gaze-aoi-intervals-v1",
        "1.0.0",
        "12.14",
    ),
    "fixation-intervals-v1-parameters-0.1": (
        "fixation-intervals-v1",
        "1.0.0",
        "12.15",
    ),
    "control-physio-windows-v2-parameters-0.1": (
        "control-physio-windows-v2",
        "2.0.0",
        "12.13",
    ),
    "ecg-hr-trace-v1-parameters-0.1": ("ecg-hr-trace-v1", "1.0.0", "12.17"),
    "eeg-engagement-windows-v1-parameters-0.1": (
        "eeg-engagement-windows-v1",
        "1.0.0",
        "12.18",
    ),
}

ROOT_KEYS = {
    "$schema",
    "$id",
    "x-schema-id",
    "x-scientific-status",
    "x-fixed-algorithm",
    "type",
    "properties",
    "required",
    "additionalProperties",
}
PROHIBITED_KEYS = {
    "quality",
    "quality_gate",
    "quality_gates",
    "quality_transform",
    "min_valid_coverage",
    "failed_quality",
    "invalid_quality",
    "binary_quality_v1",
}


def _catalog_api() -> Any:
    return import_module("pilot_assessment.anchors.catalog")


def _descriptor(
    schema_id: str, matrix: dict[str, tuple[str, str]] = DESCRIPTOR_MATRIX
) -> dict[str, object]:
    fields_text, order_text = matrix[schema_id]
    fields = []
    for encoded in fields_text.split(","):
        name, dtype, unit = encoded.split(":")
        nullable = name.endswith("?")
        fields.append(
            {"name": name.removesuffix("?"), "dtype": dtype, "unit": unit, "nullable": nullable}
        )
    return {"type": "table", "fields": fields, "canonical_order_keys": order_text.split(",")}


def _walk_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        mapping = cast(dict[str, object], value)
        return set(mapping) | set().union(*(_walk_keys(item) for item in mapping.values()), set())
    if isinstance(value, list):
        return set().union(*(_walk_keys(item) for item in value), set())
    return set()


def _condition_dicts(
    conditions: tuple[tuple[str, str, int | float, str], ...],
) -> list[dict[str, object]]:
    return [
        {"metric_id": metric, "operator": operator, "value": value, "unit": unit}
        for metric, operator, value, unit in conditions
    ]


def _catalog_typed_fingerprint(document: dict[str, Any]) -> str:
    payload = AnchorCatalog.model_validate(document).model_dump(mode="json")
    payload.pop("catalog_fingerprint", None)
    canonical = rfc8785.dumps(cast(JsonValue, payload))
    framed = b"anchor-catalog\0" + b"0.1.0\0" + struct.pack(">Q", len(canonical)) + canonical
    return sha256(framed).hexdigest()


def _refresh_catalog_claim(document: dict[str, Any]) -> None:
    document["catalog_fingerprint"] = _catalog_typed_fingerprint(document)


def _mutate_17(document: dict[str, Any]) -> None:
    document["entries"].pop()
    _refresh_catalog_claim(document)


def _mutate_19(document: dict[str, Any]) -> None:
    extra = deepcopy(document["entries"][-1])
    extra.update(
        {
            "anchor_id": "H6",
            "canonical_order": 18,
            "plugin_id": "h6-test-only",
            "parameter_schema_id": "h6-parameters-0.1",
        }
    )
    document["entries"].append(extra)
    _refresh_catalog_claim(document)


def _mutate_duplicate(document: dict[str, Any]) -> None:
    duplicate = deepcopy(document["entries"][0])
    duplicate["canonical_order"] = 17
    document["entries"][-1] = duplicate


def _mutate_reordered(document: dict[str, Any]) -> None:
    document["entries"][0], document["entries"][1] = (
        document["entries"][1],
        document["entries"][0],
    )


def _mutate_gapped_order(document: dict[str, Any]) -> None:
    document["entries"][-1]["canonical_order"] = 19
    _refresh_catalog_claim(document)


def _mutate_task8_sentinel(document: dict[str, Any]) -> None:
    document["catalog_fingerprint"] = "0" * 64


def _mutate_stale_catalog_claim(document: dict[str, Any]) -> None:
    current = str(document["catalog_fingerprint"])
    replacement = "0" if current[0] != "0" else "1"
    document["catalog_fingerprint"] = replacement + current[1:]


def _mutate_non_active(document: dict[str, Any]) -> None:
    document["entries"][0]["lifecycle"] = "deprecated"
    _refresh_catalog_claim(document)


def _mutate_missing_sentinel(document: dict[str, Any]) -> None:
    del document["catalog_fingerprint"]


def _mutate_dependency_schema(document: dict[str, Any]) -> None:
    document["entries"][4]["dependencies"][0]["expected_schema_id"] = "altered-output-v0.1"
    _refresh_catalog_claim(document)


def _mutate_descriptor_unit(document: dict[str, Any]) -> None:
    document["entries"][0]["artifact_recipes"][0]["schema_descriptor"]["fields"][0]["unit"] = (
        "changed_unit"
    )
    _refresh_catalog_claim(document)


def _mutate_self_consistent_plugin_identity(document: dict[str, Any]) -> None:
    document["entries"][0]["plugin_version"] = "0.2.0"
    _refresh_catalog_claim(document)


def test_packaged_reference_catalog_is_the_exact_task7_matrix() -> None:
    catalog = _catalog_api().load_packaged_catalog()
    assert catalog.contract_id == "anchor-catalog"
    assert catalog.contract_version == "0.1.0"
    assert catalog.profile_id == "reference-model-v0.1"
    assert catalog.profile_version == "0.1.0"
    assert catalog.scientific_validation_status.value == "engineering_default"
    document = catalog.model_dump(mode="json")
    expected_fingerprint = _catalog_typed_fingerprint(document)
    assert catalog.catalog_fingerprint == expected_fingerprint
    assert expected_fingerprint != "0" * 64
    assert tuple(entry.anchor_id for entry in catalog.entries) == ANCHOR_IDS

    for order, entry in enumerate(catalog.entries):
        plugin, inputs, dependency_ids, artifact_id, kind, schema_id = ENTRY_MATRIX[entry.anchor_id]
        assert (
            entry.canonical_order,
            entry.definition_version,
            entry.lifecycle.value,
            entry.required,
        ) == (order, "0.1.0", "active", True)
        assert (
            entry.plugin_id,
            entry.plugin_version,
            entry.parameter_schema_id,
            entry.scorer_id,
        ) == (plugin, "0.1.0", f"{entry.anchor_id.lower()}-parameters-0.1", "hard_threshold_v1")
        assert entry.required_inputs == inputs
        assert tuple(item.dependency_id for item in entry.dependencies) == dependency_ids
        for dependency in entry.dependencies:
            assert (
                dependency.kind.value,
                dependency.target_anchor_id,
                dependency.target_resource_id,
                dependency.expected_schema_id,
                dependency.expected_artifact_kind,
                dependency.required,
            ) == DEPENDENCY_MATRIX[dependency.dependency_id]
        assert len(entry.artifact_recipes) == 1
        artifact = entry.artifact_recipes[0]
        assert (artifact.artifact_id, artifact.kind, artifact.schema_id, artifact.payload_kind) == (
            artifact_id,
            kind,
            schema_id,
            "table",
        )
        assert artifact.schema_descriptor == _descriptor(schema_id)


def test_reference_provider_and_algorithm_profile_identities_are_exact() -> None:
    api = _catalog_api()
    assert len(api.REFERENCE_PREPROCESSING_IDENTITIES) == 6
    for identity, expected in zip(
        api.REFERENCE_PREPROCESSING_IDENTITIES, PROVIDER_IDENTITY_MATRIX, strict=True
    ):
        provider_id, version, parameter_schema_id, output_schema_id, artifact_kind = expected
        assert dict(identity) == {
            "provider_id": provider_id,
            "provider_version": version,
            "parameter_schema_id": parameter_schema_id,
            "output_schema_id": output_schema_id,
            "artifact_kind": artifact_kind,
            "output_payload_kind": "table",
            "output_schema_descriptor": _descriptor(
                output_schema_id, PROVIDER_OUTPUT_DESCRIPTOR_MATRIX
            ),
        }
    assert tuple(dict(identity) for identity in api.REFERENCE_ALGORITHM_PROFILE_IDENTITIES) == (
        {
            "profile_id": "o1-algorithm-profile",
            "profile_version": "0.1.0",
            "source_anchor_id": "O1",
            "output_schema_id": "o1-algorithm-profile-output-v0.1",
        },
        {
            "profile_id": "o5-algorithm-profile",
            "profile_version": "0.1.0",
            "source_anchor_id": "O5",
            "output_schema_id": "o5-algorithm-profile-output-v0.1",
        },
        {
            "profile_id": "o7-algorithm-profile",
            "profile_version": "0.1.0",
            "source_anchor_id": "O7",
            "output_schema_id": "o7-algorithm-profile-output-v0.1",
        },
    )
    with pytest.raises(TypeError, match="immutable"):
        api.REFERENCE_PREPROCESSING_IDENTITIES[0]["output_schema_descriptor"]["fields"][0][
            "unit"
        ] = "mutated"


def test_all_parameter_resources_have_canonical_bytes_hashes_and_meta_contracts() -> None:
    api = _catalog_api()
    for schema_id in PARAMETER_SCHEMA_IDS:
        raw = api.load_parameter_schema_bytes(schema_id)
        document = json.loads(raw)
        loaded = api.load_parameter_schema(schema_id)
        expected_bytes = (
            json.dumps(document, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
            + "\n"
        ).encode()

        assert raw == expected_bytes
        assert not raw.startswith(b"\xef\xbb\xbf") and raw.endswith(b"\n")
        assert not raw.endswith(b"\n\n") and b"\r" not in raw
        assert api.parameter_schema_sha256(schema_id) == EXPECTED_PARAMETER_SHA256[schema_id]
        assert EXPECTED_PARAMETER_SHA256[schema_id] == sha256(raw).hexdigest()
        assert dict(loaded) == document
        assert document["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert document["$id"] == f"urn:cranfield:pilot-assessment:parameters:{schema_id}"
        assert document["x-schema-id"] == schema_id
        assert document["x-scientific-status"] == "engineering_default"
        assert document["type"] == "object" and document["additionalProperties"] is False
        assert set(document) == ROOT_KEYS | (
            {"x-scorer-policy-default"}
            if schema_id.startswith(("o", "h"))
            and schema_id not in {item + "-parameters-0.1" for item in PROVIDER_IDS}
            else set()
        )
        expected_names = (
            () if schema_id in EMPTY_PARAMETER_SCHEMAS else EXPECTED_PROPERTY_NAMES[schema_id]
        )
        assert tuple(sorted(document["properties"])) == expected_names
        assert document["required"] == list(expected_names)
        assert not (_walk_keys(document) & PROHIBITED_KEYS)
        Draft202012Validator.check_schema(document)

        fixed = document["x-fixed-algorithm"]
        assert set(fixed) == {
            "implementation_id",
            "implementation_version",
            "source_spec",
            "source_section",
        }
        if "x-scorer-policy-default" in document:
            anchor_id = schema_id.removesuffix("-parameters-0.1").upper()
            expected_fixed = (
                ENTRY_MATRIX[anchor_id][0],
                "0.1.0",
                f"12.{ANCHOR_IDS.index(anchor_id) + 1}",
            )
        else:
            expected_fixed = FIXED_PROVIDER_ALGORITHM_MATRIX[schema_id]
        assert fixed == {
            "implementation_id": expected_fixed[0],
            "implementation_version": expected_fixed[1],
            "source_spec": "m4-anchor-evidence-availability-design-2026-07-13",
            "source_section": expected_fixed[2],
        }
        if "x-scorer-policy-default" in document:
            scorer = document["x-scorer-policy-default"]
            assert set(scorer) == {"scorer_id", "scorer_version", "policy_schema_id", "parameters"}
            assert set(scorer["parameters"]) == {
                "state_order",
                "evaluation_order",
                "rules",
                "fallback_state",
                "computed_u_overrides",
            }
            assert scorer["parameters"]["state_order"] == ["unacceptable", "adequate", "desired"]
            assert scorer["parameters"]["evaluation_order"] == ["desired", "adequate"]
            assert [rule["state"] for rule in scorer["parameters"]["rules"]] == [
                "desired",
                "adequate",
            ]
            assert scorer["parameters"]["fallback_state"] == "unacceptable"
            policy_schema, desired, adequate, overrides = SCORER_MATRIX[anchor_id]
            assert scorer["scorer_id"] == "hard_threshold_v1"
            assert scorer["scorer_version"] == "0.1.0"
            assert scorer["policy_schema_id"] == policy_schema
            assert scorer["parameters"]["rules"] == [
                {"state": "desired", "conditions": _condition_dicts(desired)},
                {"state": "adequate", "conditions": _condition_dicts(adequate)},
            ]
            assert scorer["parameters"]["computed_u_overrides"] == list(overrides)

        defaults = {
            name: fragment["default"]
            for name, fragment in document["properties"].items()
            if "default" in fragment
        }
        assert defaults == PROPERTY_DEFAULTS.get(schema_id, {})
        expected_owner = (
            "anchor_plugin" if "x-scorer-policy-default" in document else "preprocessing_provider"
        )
        for fragment in document["properties"].values():
            assert fragment["x-owner"] == expected_owner
            assert isinstance(fragment["x-unit"], str)
            assert fragment["x-comparison"] in {
                "gt",
                "gte",
                "lt",
                "lte",
                "closed_interval",
                "left_closed_right_open",
                "abs_lte",
                "enum",
                "exact",
                "cross_field",
            }
            assert ("default" in fragment) ^ ("x-default-source" in fragment)
        if schema_id == "o6-parameters-0.1":
            assert document["properties"]["channel_weights"]["minItems"] == 0
            assert (
                document["properties"]["channel_weights"]["x-default-source"]
                == "equal_weights_over_o6_applicability_control_mappings_v1"
            )
        if schema_id == "eeg-engagement-windows-v1-parameters-0.1":
            assert document["properties"]["channel_conversions"]["minItems"] == 1
            assert (
                document["properties"]["channel_conversions"]["x-default-source"]
                == "selected_baseline_channels_uV_to_V_v1"
            )


@pytest.mark.parametrize(
    "bad_id",
    (
        "../o1-parameters-0.1",
        "parameters/o1-parameters-0.1",
        r"..\o1-parameters-0.1",
        "/o1-parameters-0.1",
        "o1-parameters-v0.1",
        "unknown-parameters-0.1",
    ),
)
@pytest.mark.parametrize(
    "loader_name",
    ("load_parameter_schema", "load_parameter_schema_bytes", "parameter_schema_sha256"),
)
def test_parameter_resource_loaders_reject_paths_aliases_and_unknown_ids(
    bad_id: str, loader_name: str
) -> None:
    with pytest.raises(ValueError):
        getattr(_catalog_api(), loader_name)(bad_id)


@pytest.mark.parametrize(
    "profile_id", ("../reference-model-v0.1", "reference/model-v0.1", "reference-model-v0.2")
)
def test_catalog_loader_rejects_paths_and_unknown_profiles(profile_id: str) -> None:
    with pytest.raises(ValueError):
        _catalog_api().load_packaged_catalog(profile_id)


@pytest.mark.parametrize(
    "mutation",
    (
        _mutate_17,
        _mutate_19,
        _mutate_duplicate,
        _mutate_reordered,
        _mutate_gapped_order,
        _mutate_task8_sentinel,
        _mutate_stale_catalog_claim,
        _mutate_non_active,
        _mutate_missing_sentinel,
        _mutate_dependency_schema,
        _mutate_descriptor_unit,
        _mutate_self_consistent_plugin_identity,
    ),
    ids=(
        "17-entries",
        "19-entries",
        "duplicate",
        "reordered",
        "gapped-order",
        "task8-sentinel",
        "stale-catalog-claim",
        "non-active",
        "missing-sentinel",
        "dependency-schema",
        "descriptor-unit",
        "self-consistent-plugin-identity",
    ),
)
def test_reference_profile_loader_rejects_mutated_catalog_resources(
    mutation: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    api = _catalog_api()
    cache_clear = getattr(api.load_packaged_catalog, "cache_clear", lambda: None)
    cache_clear()
    document = api.load_packaged_catalog().model_dump(mode="json")
    mutation(document)
    cache_clear()

    resource = tmp_path / "reference-model-v0.1-anchor-catalog.json"
    resource.write_bytes(
        (
            json.dumps(document, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
            + "\n"
        ).encode("utf-8")
    )
    monkeypatch.setattr(api, "files", lambda _package: tmp_path)

    with pytest.raises(ValueError):
        api.load_packaged_catalog()
    cache_clear()


@pytest.mark.parametrize(
    ("schema_id", "mutation"),
    (
        (
            "o3-parameters-0.1",
            lambda document: document["properties"]["capture_hold_ns"].update({"default": 123}),
        ),
        (
            "o3-parameters-0.1",
            lambda document: document["properties"]["capture_hold_ns"].update(
                {"x-comparison": "lte"}
            ),
        ),
        (
            "o3-parameters-0.1",
            lambda document: document["properties"]["capture_hold_ns"].update(
                {"minimum": "not-a-number"}
            ),
        ),
        (
            "o1-parameters-0.1",
            lambda document: document["x-scorer-policy-default"].update(
                {"policy_schema_id": "changed-policy-v0.1"}
            ),
        ),
        (
            "o1-parameters-0.1",
            lambda document: document["x-scorer-policy-default"]["parameters"]["rules"][0][
                "conditions"
            ][0].update({"value": 1}),
        ),
        (
            "o1-parameters-0.1",
            lambda document: document["x-scorer-policy-default"]["parameters"].update(
                {"computed_u_overrides": ["invented_override"]}
            ),
        ),
    ),
    ids=(
        "default",
        "comparison",
        "draft-invalid-bound",
        "policy-schema",
        "threshold",
        "override",
    ),
)
def test_parameter_loader_rejects_canonical_semantic_mutations(
    schema_id: str,
    mutation: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    api = _catalog_api()
    package = files("pilot_assessment.anchors.profile_data.parameters")
    document = json.loads(package.joinpath(f"{schema_id}.json").read_bytes())
    mutation(document)
    resource = tmp_path / f"{schema_id}.json"
    resource.write_bytes(
        (
            json.dumps(document, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
            + "\n"
        ).encode("utf-8")
    )
    monkeypatch.setattr(api, "files", lambda _package: tmp_path)

    with pytest.raises(ValueError):
        api.load_parameter_schema_bytes(schema_id)


@pytest.mark.parametrize("corruption", ("duplicate-key", "non-canonical"))
def test_parameter_loader_rejects_structural_byte_corruption(
    corruption: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    api = _catalog_api()
    schema_id = "o1-parameters-0.1"
    package = files("pilot_assessment.anchors.profile_data.parameters")
    raw = package.joinpath(f"{schema_id}.json").read_bytes()
    if corruption == "duplicate-key":
        raw = b'{"type":"object","type":"array"}\n'
    else:
        raw = raw.rstrip(b"\n") + b" \n"
    (tmp_path / f"{schema_id}.json").write_bytes(raw)
    monkeypatch.setattr(api, "files", lambda _package: tmp_path)

    with pytest.raises(ValueError):
        api.load_parameter_schema_bytes(schema_id)


def test_registry_resource_honestly_declares_o1_through_o12_h1_and_two_providers() -> None:
    raw = files("pilot_assessment.anchors").joinpath("registry-v1.json").read_bytes()
    document = json.loads(raw)
    assert document["contract_id"] == "anchor-runtime-registry"
    assert document["contract_version"] == "0.1.0"
    assert [entry["anchor_id"] for entry in document["entries"]] == [
        "H1",
        "O1",
        "O10",
        "O11",
        "O12",
        "O2",
        "O3",
        "O4",
        "O5",
        "O6",
        "O7",
        "O8",
        "O9",
    ]
    assert [entry["provider_id"] for entry in document["preprocessors"]] == [
        "gaze-aoi-intervals-v1",
        "movement-events-v1",
    ]
    registry = AnchorRuntimeRegistry.model_validate_json(raw)
    assert tuple(entry.anchor_id for entry in registry.entries) == (
        "H1",
        "O1",
        "O10",
        "O11",
        "O12",
        "O2",
        "O3",
        "O4",
        "O5",
        "O6",
        "O7",
        "O8",
        "O9",
    )
    assert tuple(entry.provider_id for entry in registry.preprocessors) == (
        "gaze-aoi-intervals-v1",
        "movement-events-v1",
    )


def test_loaded_parameter_schema_is_recursively_immutable() -> None:
    schema = _catalog_api().load_parameter_schema("movement-events-v1-parameters-0.1")
    with pytest.raises(TypeError, match="immutable"):
        schema["properties"]["grid_period_ns"]["default"] = 1


def test_loaded_catalog_descriptors_are_recursively_immutable() -> None:
    descriptor = (
        _catalog_api().load_packaged_catalog().entries[0].artifact_recipes[0].schema_descriptor
    )
    with pytest.raises(TypeError, match="immutable"):
        descriptor["fields"][0]["unit"] = "mutated"
