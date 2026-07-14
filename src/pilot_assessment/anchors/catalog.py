"""Strict package-resource loaders for the M4 reference anchor catalog."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from importlib.resources import files
from typing import Any, NoReturn, cast

from pydantic import JsonValue, TypeAdapter, ValidationError

from pilot_assessment.contracts.anchor_execution import AnchorCatalog
from pilot_assessment.contracts.common import Sha256Digest, StableId, freeze_json_mapping

REFERENCE_PROFILE_ID = "reference-model-v0.1"
REFERENCE_ANCHOR_IDS = (
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
REFERENCE_ANCHOR_PARAMETER_SCHEMA_IDS = tuple(
    f"{anchor_id.lower()}-parameters-0.1" for anchor_id in REFERENCE_ANCHOR_IDS
)
REFERENCE_PROVIDER_PARAMETER_SCHEMA_IDS = (
    "movement-events-v1-parameters-0.1",
    "gaze-aoi-intervals-v1-parameters-0.1",
    "fixation-intervals-v1-parameters-0.1",
    "control-physio-windows-v2-parameters-0.1",
    "ecg-hr-trace-v1-parameters-0.1",
    "eeg-engagement-windows-v1-parameters-0.1",
)
REFERENCE_PARAMETER_SCHEMA_IDS = (
    *REFERENCE_ANCHOR_PARAMETER_SCHEMA_IDS,
    *REFERENCE_PROVIDER_PARAMETER_SCHEMA_IDS,
)

_TASK8_UNCOMPUTED_SENTINEL = "0" * 64
_DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"
_SOURCE_SPEC = "m4-anchor-evidence-availability-design-2026-07-13"
_STABLE_ID_ADAPTER = TypeAdapter(StableId)
_PARAMETER_ID_SET = frozenset(REFERENCE_PARAMETER_SCHEMA_IDS)
_ANCHOR_PARAMETER_ID_SET = frozenset(REFERENCE_ANCHOR_PARAMETER_SCHEMA_IDS)
_EXPECTED_PARAMETER_RESOURCE_SHA256 = {
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
_PROHIBITED_KEYS = frozenset(
    {
        "quality",
        "quality_gate",
        "quality_gates",
        "quality_transform",
        "min_valid_coverage",
        "failed_quality",
        "invalid_quality",
        "binary_quality_v1",
    }
)
_COMMON_ROOT_KEYS = frozenset(
    {
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
)
_FIXED_ALGORITHMS = {
    **{
        schema_id: (plugin_id, "0.1.0", f"12.{index}")
        for index, (schema_id, plugin_id) in enumerate(
            zip(
                REFERENCE_ANCHOR_PARAMETER_SCHEMA_IDS,
                (
                    "o1-phase-state-precision",
                    "o2-peak-tracking-excursion",
                    "o3-terminal-capture-quality",
                    "o4-sustained-hover-time",
                    "o5-workload-rate",
                    "o6-control-magnitude-rms",
                    "o7-control-reversal-rate",
                    "o8-tpx-composite",
                    "o9-dead-band-activity",
                    "o10-recovery-time",
                    "o11-disturbance-latency",
                    "o12-envelope-drift-latency",
                    "o13-physio-control-coupling",
                    "h1-aoi-dwell",
                    "h2-first-fixation-latency",
                    "h3-off-task-dwell",
                    "h4-ecg-fluctuation",
                    "h5-eeg-fluctuation",
                ),
                strict=True,
            ),
            start=1,
        )
    },
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
_REFERENCE_ENTRY_SHAPES = (
    (
        "O1",
        "o1-phase-state-precision",
        ("stream.X", "semantic.phases", "semantic.envelopes"),
        (),
        "desired-envelope-mask",
        "sample_mask",
        "desired-envelope-mask-v0.1",
    ),
    (
        "O2",
        "o2-peak-tracking-excursion",
        ("stream.X", "reference.task_reference", "semantic.phases"),
        (),
        "tracking-error-trace",
        "sample_trace",
        "tracking-error-trace-v0.1",
    ),
    (
        "O3",
        "o3-terminal-capture-quality",
        ("stream.X", "semantic.targets", "semantic.events", "semantic.envelopes"),
        (),
        "capture-trace",
        "event_trace",
        "capture-trace-v0.1",
    ),
    (
        "O4",
        "o4-sustained-hover-time",
        ("stream.X", "semantic.envelopes"),
        (),
        "stable-hover-mask",
        "sample_mask",
        "stable-hover-mask-v0.1",
    ),
    (
        "O5",
        "o5-workload-rate",
        ("stream.U", "semantic.control_mappings"),
        ("movement-events",),
        "movement-events",
        "event_trace",
        "movement-events-v0.1",
    ),
    (
        "O6",
        "o6-control-magnitude-rms",
        ("stream.U", "semantic.control_mappings"),
        (),
        "rms-contribution-trace",
        "component_trace",
        "rms-contribution-trace-v0.1",
    ),
    (
        "O7",
        "o7-control-reversal-rate",
        ("stream.U", "semantic.control_mappings"),
        ("movement-events",),
        "reversal-events",
        "event_trace",
        "reversal-events-v0.1",
    ),
    (
        "O8",
        "o8-tpx-composite",
        (),
        ("o1-result", "o5-result"),
        "tpx-component-trace",
        "component_trace",
        "tpx-component-trace-v0.1",
    ),
    (
        "O9",
        "o9-dead-band-activity",
        ("stream.U",),
        ("o1-mask", "o4-mask", "movement-events"),
        "micro-movement-events",
        "event_trace",
        "micro-movement-events-v0.1",
    ),
    (
        "O10",
        "o10-recovery-time",
        ("stream.X", "semantic.events", "semantic.envelopes"),
        (),
        "recovery-events",
        "event_trace",
        "recovery-events-v0.1",
    ),
    (
        "O11",
        "o11-disturbance-latency",
        ("stream.U", "semantic.events", "semantic.control_mappings"),
        (),
        "response-events",
        "event_trace",
        "response-events-v0.1",
    ),
    (
        "O12",
        "o12-envelope-drift-latency",
        ("stream.X", "stream.U", "semantic.envelopes", "semantic.control_mappings"),
        (),
        "correction-events",
        "event_trace",
        "correction-events-v0.1",
    ),
    (
        "O13",
        "o13-physio-control-coupling",
        ("stream.X", "stream.U", "stream.ECG", "semantic.phases"),
        ("o1-profile", "o5-profile", "o7-profile", "h4-result", "h4-trace"),
        "joined-coupling-windows",
        "window_trace",
        "joined-coupling-windows-v0.1",
    ),
    (
        "H1",
        "h1-aoi-dwell",
        ("stream.I", "stream.G", "semantic.aois", "semantic.phases"),
        ("gaze-aoi-intervals",),
        "phase-dwell",
        "phase_trace",
        "phase-dwell-v0.1",
    ),
    (
        "H2",
        "h2-first-fixation-latency",
        ("stream.I", "stream.G", "semantic.events", "semantic.aois"),
        ("fixation-intervals",),
        "event-fixation-trace",
        "event_trace",
        "event-fixation-trace-v0.1",
    ),
    (
        "H3",
        "h3-off-task-dwell",
        ("stream.I", "stream.G", "semantic.aois", "semantic.phases"),
        ("gaze-aoi-intervals",),
        "phase-off-task-dwell",
        "phase_trace",
        "phase-off-task-dwell-v0.1",
    ),
    (
        "H4",
        "h4-ecg-fluctuation",
        ("stream.ECG", "semantic.baselines", "semantic.phases"),
        ("control-physio-windows", "ecg-hr-trace"),
        "control-physio-trace",
        "window_trace",
        "control-physio-trace-v0.1",
    ),
    (
        "H5",
        "h5-eeg-fluctuation",
        ("stream.EEG", "semantic.baselines", "semantic.phases"),
        ("eeg-engagement-windows",),
        "engagement-trace",
        "window_trace",
        "engagement-trace-v0.1",
    ),
)
_REFERENCE_DEPENDENCY_SHAPES = {
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
_REFERENCE_DESCRIPTOR_ENCODINGS = {
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
_REFERENCE_PROVIDER_OUTPUT_ENCODINGS = {
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
_REFERENCE_PROVIDER_IDENTITIES = (
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


class CatalogResourceError(ValueError):
    """Raised when a packaged M4 catalog resource violates its frozen contract."""


class _DuplicateJsonKey(ValueError):
    pass


def _object_without_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"non-standard JSON constant: {value}")


def _canonical_json_bytes(document: object) -> bytes:
    return (
        json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def _table_descriptor_from_encoding(
    encodings: Mapping[str, tuple[str, str]], schema_id: str
) -> dict[str, JsonValue]:
    fields_text, order_text = encodings[schema_id]
    fields: list[JsonValue] = []
    for encoded in fields_text.split(","):
        name, dtype, unit = encoded.split(":")
        nullable = name.endswith("?")
        fields.append(
            {
                "name": name.removesuffix("?"),
                "dtype": dtype,
                "unit": unit,
                "nullable": nullable,
            }
        )
    return {
        "type": "table",
        "fields": fields,
        "canonical_order_keys": order_text.split(","),
    }


def _expected_table_descriptor(schema_id: str) -> dict[str, JsonValue]:
    return _table_descriptor_from_encoding(_REFERENCE_DESCRIPTOR_ENCODINGS, schema_id)


REFERENCE_PREPROCESSING_IDENTITIES: tuple[Mapping[str, JsonValue], ...] = tuple(
    freeze_json_mapping(
        {
            "provider_id": provider_id,
            "provider_version": provider_version,
            "parameter_schema_id": parameter_schema_id,
            "output_schema_id": output_schema_id,
            "artifact_kind": artifact_kind,
            "output_payload_kind": "table",
            "output_schema_descriptor": _table_descriptor_from_encoding(
                _REFERENCE_PROVIDER_OUTPUT_ENCODINGS, output_schema_id
            ),
        }
    )
    for (
        provider_id,
        provider_version,
        parameter_schema_id,
        output_schema_id,
        artifact_kind,
    ) in _REFERENCE_PROVIDER_IDENTITIES
)
REFERENCE_ALGORITHM_PROFILE_IDENTITIES: tuple[Mapping[str, JsonValue], ...] = tuple(
    freeze_json_mapping(
        {
            "profile_id": f"{anchor_id.lower()}-algorithm-profile",
            "profile_version": "0.1.0",
            "source_anchor_id": anchor_id,
            "output_schema_id": f"{anchor_id.lower()}-algorithm-profile-output-v0.1",
        }
    )
    for anchor_id in ("O1", "O5", "O7")
)


def _parse_canonical_object(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8", errors="strict")
        parsed = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
        if not isinstance(parsed, dict):
            raise ValueError("root must be a JSON object")
        if raw != _canonical_json_bytes(parsed):
            raise ValueError("resource bytes are not canonical Task 7 JSON")
        return parsed
    except (UnicodeDecodeError, json.JSONDecodeError, _DuplicateJsonKey, ValueError) as error:
        raise CatalogResourceError(f"invalid {label}: {error}") from error


def _read_parameter_resource(schema_id: str) -> bytes:
    if type(schema_id) is not str:
        raise CatalogResourceError("parameter schema ID must be a string")
    try:
        stable_id = _STABLE_ID_ADAPTER.validate_python(schema_id)
    except ValidationError as error:
        raise CatalogResourceError(
            "parameter schema ID is not a separator-free StableId"
        ) from error
    if stable_id not in _PARAMETER_ID_SET:
        raise CatalogResourceError(f"unknown parameter schema ID: {stable_id}")
    resource = files("pilot_assessment.anchors.profile_data.parameters").joinpath(
        f"{stable_id}.json"
    )
    try:
        return resource.read_bytes()
    except (FileNotFoundError, ModuleNotFoundError, OSError) as error:
        raise CatalogResourceError(f"missing packaged parameter schema: {stable_id}") from error


def _walk_and_reject_prohibited(value: object) -> None:
    if isinstance(value, dict):
        prohibited = _PROHIBITED_KEYS.intersection(value)
        if prohibited:
            raise ValueError(f"prohibited parameter-schema keys: {sorted(prohibited)}")
        for nested in value.values():
            _walk_and_reject_prohibited(nested)
    elif isinstance(value, list):
        for nested in value:
            _walk_and_reject_prohibited(nested)


def _validate_leaf(fragment: object, *, owner: str, nested: bool) -> None:
    if not isinstance(fragment, dict):
        raise ValueError("parameter property must be an object")
    mapping = cast(dict[str, Any], fragment)
    property_type = mapping.get("type")
    if property_type not in {"number", "integer", "string"}:
        raise ValueError("parameter leaf has an unsupported type")
    required_keys = {"type", "x-unit", "x-owner", "x-comparison"}
    allowed_keys = required_keys | {
        "default",
        "x-default-source",
        "minimum",
        "exclusiveMinimum",
        "maximum",
        "exclusiveMaximum",
        "enum",
        "pattern",
    }
    if not required_keys <= set(mapping) or not set(mapping) <= allowed_keys:
        raise ValueError("parameter leaf keys violate the exact fragment grammar")
    if mapping["x-owner"] != owner:
        raise ValueError("parameter property owner is inconsistent")
    has_default = "default" in mapping
    has_source = "x-default-source" in mapping
    if nested and (has_default or has_source):
        raise ValueError("nested materialized leaves forbid defaults")
    if not nested and has_default == has_source:
        raise ValueError("top-level properties require exactly one default source")


def _validate_property(fragment: object, *, owner: str) -> None:
    if not isinstance(fragment, dict):
        raise ValueError("parameter property must be an object")
    mapping = cast(dict[str, Any], fragment)
    if mapping.get("type") != "array":
        _validate_leaf(mapping, owner=owner, nested=False)
        return
    expected_keys = {
        "type",
        "minItems",
        "items",
        "x-owner",
        "x-default-source",
        "x-unit",
        "x-comparison",
    }
    if set(mapping) != expected_keys or mapping["x-owner"] != owner:
        raise ValueError("session-shaped array violates the exact fragment grammar")
    items = mapping["items"]
    if not isinstance(items, dict) or set(items) != {
        "type",
        "properties",
        "required",
        "additionalProperties",
    }:
        raise ValueError("array item schema violates the exact object grammar")
    item_mapping = cast(dict[str, Any], items)
    properties = item_mapping.get("properties")
    if (
        item_mapping.get("type") != "object"
        or item_mapping.get("additionalProperties") is not False
        or not isinstance(properties, dict)
        or item_mapping.get("required") != sorted(properties)
    ):
        raise ValueError("array item properties are not closed and complete")
    for nested in properties.values():
        _validate_leaf(nested, owner=owner, nested=True)


def _validate_scorer_annotation(value: object) -> None:
    if not isinstance(value, dict) or set(value) != {
        "scorer_id",
        "scorer_version",
        "policy_schema_id",
        "parameters",
    }:
        raise ValueError("scorer annotation must have the exact four-key shape")
    annotation = cast(dict[str, Any], value)
    if annotation["scorer_id"] != "hard_threshold_v1" or annotation["scorer_version"] != "0.1.0":
        raise ValueError("scorer identity is inconsistent")
    parameters = annotation["parameters"]
    if not isinstance(parameters, dict) or set(parameters) != {
        "state_order",
        "evaluation_order",
        "rules",
        "fallback_state",
        "computed_u_overrides",
    }:
        raise ValueError("scorer parameters must have the exact five-key shape")
    policy = cast(dict[str, Any], parameters)
    if policy["state_order"] != ["unacceptable", "adequate", "desired"]:
        raise ValueError("scorer state order is inconsistent")
    if policy["evaluation_order"] != ["desired", "adequate"]:
        raise ValueError("scorer evaluation order is inconsistent")
    if policy["fallback_state"] != "unacceptable":
        raise ValueError("scorer fallback state is inconsistent")
    overrides = policy["computed_u_overrides"]
    if not isinstance(overrides, list) or overrides != sorted(set(overrides)):
        raise ValueError("computed-U overrides must be unique and sorted")
    rules = policy["rules"]
    if not isinstance(rules, list) or any(not isinstance(rule, dict) for rule in rules):
        raise ValueError("scorer rules must use desired-then-adequate order")
    typed_rules = cast(list[dict[str, Any]], rules)
    if [rule.get("state") for rule in typed_rules] != ["desired", "adequate"]:
        raise ValueError("scorer rules must use desired-then-adequate order")
    for rule in typed_rules:
        if set(rule) != {"state", "conditions"}:
            raise ValueError("scorer rule has an invalid shape")
        conditions = rule["conditions"]
        if not isinstance(conditions, list) or not conditions:
            raise ValueError("scorer rules require conditions")
        if any(not isinstance(condition, dict) for condition in conditions):
            raise ValueError("scorer condition has an invalid shape")
        for condition in cast(list[dict[str, Any]], conditions):
            if set(condition) != {
                "metric_id",
                "operator",
                "value",
                "unit",
            }:
                raise ValueError("scorer condition has an invalid shape")
            numeric = condition["value"]
            if type(numeric) not in {int, float}:
                raise ValueError("scorer condition value must be finite")
            if not math.isfinite(float(numeric)):
                raise ValueError("scorer condition value must be finite")
            if condition["operator"] not in {"<", "<=", ">", ">="}:
                raise ValueError("scorer condition operator is unsupported")


def _validate_parameter_document(schema_id: str, document: dict[str, Any]) -> None:
    is_anchor = schema_id in _ANCHOR_PARAMETER_ID_SET
    expected_root = _COMMON_ROOT_KEYS | ({"x-scorer-policy-default"} if is_anchor else set())
    if set(document) != expected_root:
        raise ValueError("parameter schema root keys are not exact")
    if document["$schema"] != _DRAFT_2020_12:
        raise ValueError("parameter schema dialect is inconsistent")
    if document["$id"] != f"urn:cranfield:pilot-assessment:parameters:{schema_id}":
        raise ValueError("parameter schema URN is inconsistent")
    if document["x-schema-id"] != schema_id:
        raise ValueError("parameter schema ID does not match its resource name")
    if document["x-scientific-status"] != "engineering_default":
        raise ValueError("parameter schema scientific status is inconsistent")
    properties = document["properties"]
    if (
        document["type"] != "object"
        or document["additionalProperties"] is not False
        or not isinstance(properties, dict)
        or document["required"] != sorted(properties)
    ):
        raise ValueError("parameter schema must be a closed complete object")
    expected_fixed = _FIXED_ALGORITHMS[schema_id]
    fixed = document["x-fixed-algorithm"]
    if fixed != {
        "implementation_id": expected_fixed[0],
        "implementation_version": expected_fixed[1],
        "source_spec": _SOURCE_SPEC,
        "source_section": expected_fixed[2],
    }:
        raise ValueError("fixed algorithm identity is inconsistent")
    owner = "anchor_plugin" if is_anchor else "preprocessing_provider"
    for fragment in properties.values():
        _validate_property(fragment, owner=owner)
    if is_anchor:
        _validate_scorer_annotation(document["x-scorer-policy-default"])
    _walk_and_reject_prohibited(document)


def load_parameter_schema_bytes(schema_id: str) -> bytes:
    """Return validated, authoritative UTF-8 bytes for one exact schema ID."""

    raw = _read_parameter_resource(schema_id)
    document = _parse_canonical_object(raw, label=f"parameter schema {schema_id}")
    try:
        _validate_parameter_document(schema_id, document)
        resource_sha256 = hashlib.sha256(raw).hexdigest()
        if resource_sha256 != _EXPECTED_PARAMETER_RESOURCE_SHA256[schema_id]:
            raise ValueError("parameter schema bytes differ from the frozen Task 7 resource")
    except (KeyError, TypeError, ValueError) as error:
        raise CatalogResourceError(f"invalid parameter schema {schema_id}: {error}") from error
    return raw


def load_parameter_schema(schema_id: str) -> Mapping[str, JsonValue]:
    """Return a recursively immutable snapshot of one packaged parameter schema."""

    raw = load_parameter_schema_bytes(schema_id)
    document = _parse_canonical_object(raw, label=f"parameter schema {schema_id}")
    return freeze_json_mapping(document)


def parameter_schema_sha256(schema_id: str) -> Sha256Digest:
    """Hash the exact authoritative resource bytes without Task 8 typed framing."""

    return hashlib.sha256(load_parameter_schema_bytes(schema_id)).hexdigest()


def _validate_reference_catalog(catalog: AnchorCatalog) -> None:
    if (
        catalog.contract_id != "anchor-catalog"
        or catalog.contract_version != "0.1.0"
        or catalog.profile_id != REFERENCE_PROFILE_ID
        or catalog.profile_version != "0.1.0"
        or catalog.scientific_validation_status.value != "engineering_default"
        or len(catalog.entries) != len(_REFERENCE_ENTRY_SHAPES)
    ):
        raise ValueError("reference catalog global identity is inconsistent")
    if catalog.catalog_fingerprint == _TASK8_UNCOMPUTED_SENTINEL:
        raise ValueError("reference catalog still carries the Task 8 sentinel")
    for order, (entry, expected) in enumerate(
        zip(catalog.entries, _REFERENCE_ENTRY_SHAPES, strict=True)
    ):
        anchor_id, plugin_id, inputs, dependency_ids, artifact_id, kind, schema_id = expected
        if (
            entry.anchor_id != anchor_id
            or entry.definition_version != "0.1.0"
            or entry.lifecycle.value != "active"
            or entry.required is not True
            or entry.canonical_order != order
            or entry.plugin_id != plugin_id
            or entry.plugin_version != "0.1.0"
            or entry.parameter_schema_id != f"{anchor_id.lower()}-parameters-0.1"
            or entry.scorer_id != "hard_threshold_v1"
            or entry.required_inputs != inputs
            or tuple(item.dependency_id for item in entry.dependencies) != dependency_ids
            or len(entry.artifact_recipes) != 1
        ):
            raise ValueError(f"reference catalog entry {anchor_id} is inconsistent")
        artifact = entry.artifact_recipes[0]
        if (
            artifact.artifact_id != artifact_id
            or artifact.kind != kind
            or artifact.schema_id != schema_id
            or artifact.payload_kind != "table"
            or artifact.schema_descriptor != _expected_table_descriptor(schema_id)
        ):
            raise ValueError(f"reference catalog artifact {anchor_id} is inconsistent")
        for dependency in entry.dependencies:
            actual_dependency = (
                dependency.kind.value,
                dependency.target_anchor_id,
                dependency.target_resource_id,
                dependency.expected_schema_id,
                dependency.expected_artifact_kind,
                dependency.required,
            )
            if actual_dependency != _REFERENCE_DEPENDENCY_SHAPES[dependency.dependency_id]:
                raise ValueError(
                    f"reference catalog dependency {dependency.dependency_id} is inconsistent"
                )

    from pilot_assessment.anchors.fingerprint import (
        catalog_fingerprint_payload,
        typed_json_sha256,
    )

    expected_fingerprint = typed_json_sha256(
        catalog.contract_id,
        catalog.contract_version,
        catalog_fingerprint_payload(catalog),
    )
    if catalog.catalog_fingerprint != expected_fingerprint:
        raise ValueError("reference catalog fingerprint is stale or inconsistent")


def load_packaged_catalog(profile_id: str = REFERENCE_PROFILE_ID) -> AnchorCatalog:
    """Load and exact-validate the only packaged Task 7 reference catalog."""

    if type(profile_id) is not str:
        raise CatalogResourceError("catalog profile ID must be a string")
    try:
        stable_id = _STABLE_ID_ADAPTER.validate_python(profile_id)
    except ValidationError as error:
        raise CatalogResourceError("catalog profile ID is not a separator-free StableId") from error
    if stable_id != REFERENCE_PROFILE_ID:
        raise CatalogResourceError(f"unknown catalog profile ID: {stable_id}")
    resource = files("pilot_assessment.anchors.profile_data").joinpath(
        "reference-model-v0.1-anchor-catalog.json"
    )
    try:
        raw = resource.read_bytes()
        document = _parse_canonical_object(raw, label="reference anchor catalog")
        catalog = AnchorCatalog.model_validate(document)
        _validate_reference_catalog(catalog)
        return catalog
    except (FileNotFoundError, ModuleNotFoundError, OSError, ValidationError, ValueError) as error:
        if isinstance(error, CatalogResourceError):
            raise
        raise CatalogResourceError(f"invalid packaged reference catalog: {error}") from error


__all__ = [
    "CatalogResourceError",
    "REFERENCE_ALGORITHM_PROFILE_IDENTITIES",
    "REFERENCE_ANCHOR_IDS",
    "REFERENCE_ANCHOR_PARAMETER_SCHEMA_IDS",
    "REFERENCE_PARAMETER_SCHEMA_IDS",
    "REFERENCE_PREPROCESSING_IDENTITIES",
    "REFERENCE_PROFILE_ID",
    "REFERENCE_PROVIDER_PARAMETER_SCHEMA_IDS",
    "load_packaged_catalog",
    "load_parameter_schema",
    "load_parameter_schema_bytes",
    "parameter_schema_sha256",
]
