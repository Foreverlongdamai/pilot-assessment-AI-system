from __future__ import annotations

from dataclasses import dataclass

import polars as pl
import pytest

from pilot_assessment.anchors.catalog import (
    REFERENCE_PREPROCESSING_IDENTITIES,
    load_parameter_schema,
)
from pilot_assessment.anchors.fingerprint import schema_descriptor_sha256
from pilot_assessment.anchors.plugins.h2_first_fixation_latency import create_plugin
from pilot_assessment.anchors.protocols import (
    AnchorPluginContext,
    PreprocessingArtifactIdentity,
    ProjectedSemanticScope,
    ReadOnlyTabularPayload,
    ResolvedDependencies,
    ResolvedPreprocessingDependency,
    TabularArtifactPayload,
)
from pilot_assessment.anchors.scoring import classify_computed_metrics, compile_scorer_policy
from pilot_assessment.contracts.anchor import EvidenceState
from pilot_assessment.contracts.anchor_execution import (
    AoiDefinition,
    AoiGeometryKind,
    SemanticEvent,
    SemanticVector,
)
from pilot_assessment.contracts.anchor_v2 import AnchorArtifactRef
from pilot_assessment.contracts.synchronization import SessionWindow
from pilot_assessment.synchronization.models import AlignedStreamView

NS = 1_000_000_000
SHA_A = "a" * 64
SHA_B = "b" * 64


def _aoi(aoi_id: str, role: str) -> AoiDefinition:
    return AoiDefinition(
        aoi_id=aoi_id,
        taxonomy_id="tax-1",
        role=role,
        geometry_kind=AoiGeometryKind.POLYGON_2D,
        priority=0,
        role_weight=1.0,
        off_task=False,
        vertices=(
            SemanticVector(coordinate_frame_id="viewport", unit="normalized", values=(0.0, 0.0)),
            SemanticVector(coordinate_frame_id="viewport", unit="normalized", values=(1.0, 0.0)),
            SemanticVector(coordinate_frame_id="viewport", unit="normalized", values=(1.0, 1.0)),
        ),
    )


def _event(
    event_id: str,
    t_ns: int,
    relevant_aoi_ids: tuple[str, ...],
    *,
    opportunity_end_t_ns: int | None = None,
) -> SemanticEvent:
    return SemanticEvent(
        event_id=event_id,
        event_type="visual-cue",
        t_ns=t_ns,
        opportunity_end_t_ns=opportunity_end_t_ns,
        relevant_aoi_ids=relevant_aoi_ids,
    )


def _frames(times: tuple[int, ...]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "frame_id": pl.Series(range(len(times)), dtype=pl.UInt64),
            "t_ns": pl.Series(times, dtype=pl.Int64),
            "in_session": pl.Series([True] * len(times), dtype=pl.Boolean),
        }
    )


def _empty_gaze() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "gaze_sample_id": pl.Series([], dtype=pl.UInt64),
            "t_ns": pl.Series([], dtype=pl.Int64),
            "in_session": pl.Series([], dtype=pl.Boolean),
        }
    )


def _fixations(rows: tuple[tuple[str, int, int, str, str], ...]) -> pl.DataFrame:
    return pl.DataFrame(
        rows,
        schema={
            "fixation_id": pl.String,
            "start_t_ns": pl.Int64,
            "end_t_ns": pl.Int64,
            "aoi_id": pl.String,
            "role_id": pl.String,
        },
        orient="row",
    ).sort(["start_t_ns", "end_t_ns", "fixation_id"], maintain_order=True)


def _context(
    events: tuple[SemanticEvent, ...],
    *,
    include_i: bool = True,
    include_g: bool = True,
    frame_times: tuple[int, ...] = (0,),
    end_t_ns: int = 3 * NS,
) -> AnchorPluginContext:
    streams = {}
    if include_i:
        streams["I"] = AlignedStreamView(
            modality="I",
            source_schema_id="vr-scene-source-bundle-v0.1",
            aligned_schema_id="vr-scene-aligned-v0.1",
            clock_id="master-clock",
            tables={"frame_index": _frames(frame_times)},
            json_artifacts={},
            file_artifacts={},
            source_checksums={"scene": SHA_A},
        )
    if include_g:
        streams["G"] = AlignedStreamView(
            modality="G",
            source_schema_id="gaze-source-bundle-v0.1",
            aligned_schema_id="gaze-aligned-v0.1",
            clock_id="master-clock",
            tables={
                "gaze_samples": _empty_gaze(),
                "fixations": pl.DataFrame({"aoi_id": ["deliberately-wrong"]}),
            },
            json_artifacts={},
            file_artifacts={},
            source_checksums={"gaze": SHA_B},
        )
    aois = (_aoi("display", "primary"), _aoi("warning", "secondary"))
    return AnchorPluginContext(
        session_id="session-1",
        session_window=SessionWindow(
            end_t_ns=end_t_ns,
            source="master-clock-x-mapped-coverage-v1",
        ),
        streams=streams,
        context={},
        references={},
        semantic_scope=ProjectedSemanticScope(
            values={
                "semantic.events": [item.model_dump(mode="json") for item in events],
                "semantic.aois": [item.model_dump(mode="json") for item in aois],
            }
        ),
    )


def _dependency(frame: pl.DataFrame, end_t_ns: int = 3 * NS) -> ResolvedPreprocessingDependency:
    identity = next(
        item
        for item in REFERENCE_PREPROCESSING_IDENTITIES
        if item["provider_id"] == "fixation-intervals-v1"
    )
    descriptor = identity["output_schema_descriptor"]
    assert isinstance(descriptor, dict)
    payload = ReadOnlyTabularPayload(
        schema_id="fixation-intervals-v1-output-v0.1",
        schema_descriptor=descriptor,
        frame=frame,
        order_keys=("start_t_ns", "end_t_ns", "fixation_id"),
        artifact_kind="fixation-intervals-table",
        grid_hash=None,
        start_t_ns=0,
        end_t_ns=end_t_ns,
        logical_content_sha256=SHA_A,
    )
    return ResolvedPreprocessingDependency(
        identity=PreprocessingArtifactIdentity(
            recipe_id="fixation-intervals-v1",
            recipe_version="0.1.0",
            provider_id="fixation-intervals-v1",
            provider_version="1.0.0",
            implementation_digest=SHA_A,
            parameter_schema_id="fixation-intervals-v1-parameters-0.1",
            parameter_schema_sha256=SHA_B,
            parameter_hash=SHA_A,
            scope_kind="session",
            scope_id="session-1",
            scope_start_t_ns=0,
            scope_end_t_ns=end_t_ns,
            phase_id=None,
            event_id=None,
            window_id=None,
            schema_id=payload.schema_id,
            schema_sha256=schema_descriptor_sha256(payload.schema_id, descriptor),
            artifact_kind=payload.artifact_kind,
            payload_kind="table",
            logical_content_sha256=SHA_A,
            input_fingerprints=(("stream", "G", SHA_A),),
            dependency_fingerprints=(),
        ),
        payload=payload,
    )


def _temporal(events: tuple[SemanticEvent, ...]) -> dict[str, object]:
    return {
        "window_policy": "bound-first-fixation-v1",
        "window_id_prefix": "h2",
        "event_ids": [event.event_id for event in events],
        "event_bindings": [
            {
                "event_id": event.event_id,
                "cue_available_t_ns": event.t_ns,
                "opportunity_end_t_ns": event.opportunity_end_t_ns,
                "relevant_aoi_ids": list(event.relevant_aoi_ids),
            }
            for event in events
        ],
        "aoi_ids": ["display", "warning"],
    }


@dataclass
class _Emitter:
    payloads: list[tuple[str, TabularArtifactPayload]]

    def stage_table(self, artifact_id: str, payload: TabularArtifactPayload) -> AnchorArtifactRef:
        self.payloads.append((artifact_id, payload))
        return AnchorArtifactRef(
            artifact_id=artifact_id,
            kind=payload.artifact_kind,
            schema_id=payload.schema_id,
            logical_content_sha256=SHA_A,
            storage_file_sha256=None,
            row_count=payload.frame.height,
            start_t_ns=payload.start_t_ns,
            end_t_ns=payload.end_t_ns,
            grid_hash=payload.grid_hash,
            producer_anchor_id="H2",
            producer_plugin_id="h2-first-fixation-latency",
            producer_plugin_version="0.1.0",
            parameter_hash=SHA_A,
            dependency_fingerprints=(SHA_A,),
        )

    def stage_blob(self, artifact_id, payload):  # pragma: no cover - H2 is table-only
        raise AssertionError((artifact_id, payload))


def _compute(
    events: tuple[SemanticEvent, ...],
    frame: pl.DataFrame,
    *,
    include_i: bool = True,
    include_g: bool = True,
    frame_times: tuple[int, ...] = (0,),
    end_t_ns: int = 3 * NS,
):
    emitter = _Emitter([])
    measurement = create_plugin().compute(
        _context(
            events,
            include_i=include_i,
            include_g=include_g,
            frame_times=frame_times,
            end_t_ns=end_t_ns,
        ),
        {"fixation_horizon_ns": 2 * NS},
        _temporal(events),
        ResolvedDependencies(
            results={},
            artifacts={},
            algorithm_profiles={},
            preprocessing={"fixation-intervals": _dependency(frame, end_t_ns)},
        ),
        emitter,
    )
    return measurement, emitter


def test_h2_definition_binds_fixation_dependency_and_event_trace() -> None:
    definition = create_plugin().definition()

    assert definition.anchor_id == "H2"
    assert definition.required_streams == ("I", "G")
    assert definition.required_semantic_paths == ("semantic.aois", "semantic.events")
    assert tuple(item.dependency_id for item in definition.dependencies) == ("fixation-intervals",)
    assert definition.artifact_recipes[0].schema_id == "event-fixation-trace-v0.1"


@pytest.mark.parametrize(
    ("latency_ms", "expected_state"),
    [
        (500, EvidenceState.DESIRED),
        (1000, EvidenceState.ADEQUATE),
        (1001, EvidenceState.UNACCEPTABLE),
    ],
)
def test_cue_available_time_is_the_latency_origin_and_thresholds_are_exact(
    latency_ms: int, expected_state: EvidenceState
) -> None:
    cue = 100_000_000
    event = _event("cue-1", cue, ("display",))
    start = cue + latency_ms * 1_000_000
    measurement, emitter = _compute(
        (event,),
        _fixations((("fix-1", start, start + 100_000_000, "display", "primary"),)),
    )

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is not None
    assert measurement.primary_value.value == latency_ms
    schema = load_parameter_schema("h2-parameters-0.1")
    policy = compile_scorer_policy(schema["x-scorer-policy-default"])
    state, _score, _likelihood = classify_computed_metrics(float(latency_ms), {}, None, policy)
    assert state is expected_state
    assert emitter.payloads[0][1].frame["start_t_ns"].to_list() == [start]


def test_fixation_after_two_second_horizon_is_finite_computed_miss() -> None:
    event = _event("cue-1", 0, ("display",))
    measurement, emitter = _compute(
        (event,),
        _fixations((("late", 2 * NS + 1, 2 * NS + 100_000_001, "display", "primary"),)),
    )

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is None
    assert measurement.primary_value_reason == "fixation_missed"
    assert measurement.classification_override_candidate is not None
    assert measurement.classification_override_candidate.code == "fixation_missed"
    assert measurement.raw_metrics["observed_wait"].value == 2000.0
    assert measurement.event_results[0].raw_metrics["observed_wait"].value == 2000.0
    assert emitter.payloads[0][1].frame.is_empty()


def test_multi_event_miss_vetoes_session_without_skipping_success_trace() -> None:
    events = (
        _event("cue-1", 0, ("display",)),
        _event("cue-2", NS, ("warning",)),
    )
    measurement, emitter = _compute(
        events,
        _fixations((("fix-1", 300_000_000, 500_000_000, "display", "primary"),)),
    )

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is None
    assert measurement.classification_override_candidate is not None
    assert measurement.classification_override_candidate.details["missed_event_ids"] == ["cue-2"]
    assert tuple(item.breakdown_id for item in measurement.event_results) == ("cue-1", "cue-2")
    assert emitter.payloads[0][1].frame["event_id"].to_list() == ["cue-1"]


def test_multi_event_without_miss_uses_worst_latency() -> None:
    events = (
        _event("cue-1", 0, ("display",)),
        _event("cue-2", NS, ("warning",)),
    )
    measurement, _emitter = _compute(
        events,
        _fixations(
            (
                ("fix-1", 200_000_000, 400_000_000, "display", "primary"),
                ("fix-2", 1_700_000_000, 1_900_000_000, "warning", "secondary"),
            )
        ),
    )

    assert measurement.primary_value is not None
    assert measurement.primary_value.value == 700.0


def test_missing_relevant_aoi_mapping_is_not_computable() -> None:
    event = _event("cue-1", 0, ())
    measurement, emitter = _compute((event,), _fixations(()))

    assert measurement.calculation_status.value == "not_computable"
    assert measurement.event_results[0].calculation_status.value == "not_computable"
    assert emitter.payloads == []


@pytest.mark.parametrize(("include_i", "include_g"), [(False, True), (True, False)])
def test_absent_required_stream_is_missing_input(include_i: bool, include_g: bool) -> None:
    event = _event("cue-1", 0, ("display",))
    measurement, emitter = _compute(
        (event,),
        _fixations(()),
        include_i=include_i,
        include_g=include_g,
    )

    assert measurement.calculation_status.value == "missing_input"
    assert emitter.payloads == []


def test_present_streams_and_cue_with_no_fixation_is_negative_evidence_not_missing() -> None:
    event = _event("cue-1", 0, ("display",))
    measurement, _emitter = _compute((event,), _fixations(()))

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value_reason == "fixation_missed"
    assert measurement.classification_override_candidate is not None


def test_no_scene_opportunity_support_is_missing_input_not_a_performance_failure() -> None:
    event = _event("cue-1", NS, ("display",))
    measurement, emitter = _compute(
        (event,),
        _fixations(()),
        frame_times=(),
    )

    assert measurement.calculation_status.value == "missing_input"
    assert measurement.event_results[0].calculation_status.value == "missing_input"
    assert emitter.payloads == []
