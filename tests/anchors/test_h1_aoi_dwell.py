from __future__ import annotations

from dataclasses import dataclass

import polars as pl
import pytest

from pilot_assessment.anchors.catalog import (
    REFERENCE_PREPROCESSING_IDENTITIES,
    load_parameter_schema,
)
from pilot_assessment.anchors.fingerprint import schema_descriptor_sha256
from pilot_assessment.anchors.plugins.h1_aoi_dwell import create_plugin
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
    SemanticPhase,
    SemanticVector,
)
from pilot_assessment.contracts.anchor_v2 import AnchorArtifactRef
from pilot_assessment.contracts.synchronization import SessionWindow
from pilot_assessment.synchronization.models import AlignedStreamView

NS = 1_000_000_000
SHA_A = "a" * 64
SHA_B = "b" * 64


def _phase(phase_id: str, start_t_ns: int, end_t_ns: int) -> SemanticPhase:
    return SemanticPhase(
        phase_id=phase_id,
        phase_type="task",
        start_t_ns=start_t_ns,
        end_t_ns=end_t_ns,
        include_session_terminal_point=False,
    )


def _aois() -> tuple[AoiDefinition, ...]:
    return (
        AoiDefinition(
            aoi_id="display",
            taxonomy_id="tax-1",
            role="primary",
            geometry_kind=AoiGeometryKind.POLYGON_2D,
            priority=1,
            role_weight=1.0,
            off_task=False,
            vertices=(
                SemanticVector(
                    coordinate_frame_id="viewport", unit="normalized", values=(0.0, 0.0)
                ),
                SemanticVector(
                    coordinate_frame_id="viewport", unit="normalized", values=(1.0, 0.0)
                ),
                SemanticVector(
                    coordinate_frame_id="viewport", unit="normalized", values=(1.0, 1.0)
                ),
            ),
        ),
        AoiDefinition(
            aoi_id="other-scene",
            taxonomy_id="tax-1",
            role="other_scene",
            geometry_kind=AoiGeometryKind.CATCH_ALL,
            priority=0,
            role_weight=0.0,
            off_task=True,
        ),
    )


def _empty_gaze() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "gaze_sample_id": pl.Series([], dtype=pl.UInt64),
            "t_ns": pl.Series([], dtype=pl.Int64),
            "in_session": pl.Series([], dtype=pl.Boolean),
        }
    )


def _frames(times: tuple[int, ...]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "frame_id": pl.Series(range(len(times)), dtype=pl.UInt64),
            "t_ns": pl.Series(times, dtype=pl.Int64),
            "in_session": pl.Series([True] * len(times), dtype=pl.Boolean),
        }
    )


def _context(
    phases: tuple[SemanticPhase, ...],
    *,
    include_i: bool = True,
    include_g: bool = True,
    frame_times: tuple[int, ...] = (0,),
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
                # H1 must use the resolved raw-gaze interval product, not this compatibility table.
                "fixations": pl.DataFrame({"aoi_id": ["deliberately-wrong"]}),
            },
            json_artifacts={},
            file_artifacts={},
            source_checksums={"gaze": SHA_B},
        )
    return AnchorPluginContext(
        session_id="session-1",
        session_window=SessionWindow(
            end_t_ns=max(phase.end_t_ns for phase in phases),
            source="master-clock-x-mapped-coverage-v1",
        ),
        streams=streams,
        context={},
        references={},
        semantic_scope=ProjectedSemanticScope(
            values={
                "semantic.aois": [item.model_dump(mode="json") for item in _aois()],
                "semantic.phases": [item.model_dump(mode="json") for item in phases],
            }
        ),
    )


def _intervals(rows: tuple[tuple[str, int, int, int, str, str, str, bool], ...]) -> pl.DataFrame:
    return pl.DataFrame(
        rows,
        schema={
            "interval_id": pl.String,
            "start_t_ns": pl.Int64,
            "end_t_ns": pl.Int64,
            "gaze_source_row_id": pl.Int64,
            "frame_id": pl.String,
            "aoi_id": pl.String,
            "role_id": pl.String,
            "association_valid": pl.Boolean,
        },
        orient="row",
    ).sort(["start_t_ns", "end_t_ns", "interval_id"], maintain_order=True)


def _empty_intervals() -> pl.DataFrame:
    return _intervals(())


def _dependency(frame: pl.DataFrame, end_t_ns: int) -> ResolvedPreprocessingDependency:
    identity = next(
        item
        for item in REFERENCE_PREPROCESSING_IDENTITIES
        if item["provider_id"] == "gaze-aoi-intervals-v1"
    )
    descriptor = identity["output_schema_descriptor"]
    assert isinstance(descriptor, dict)
    payload = ReadOnlyTabularPayload(
        schema_id="gaze-aoi-intervals-v1-output-v0.1",
        schema_descriptor=descriptor,
        frame=frame,
        order_keys=("start_t_ns", "end_t_ns", "interval_id"),
        artifact_kind="gaze-aoi-intervals-table",
        grid_hash=None,
        start_t_ns=0,
        end_t_ns=end_t_ns,
        logical_content_sha256=SHA_A,
    )
    return ResolvedPreprocessingDependency(
        identity=PreprocessingArtifactIdentity(
            recipe_id="gaze-aoi-intervals-v1",
            recipe_version="0.1.0",
            provider_id="gaze-aoi-intervals-v1",
            provider_version="1.0.0",
            implementation_digest=SHA_A,
            parameter_schema_id="gaze-aoi-intervals-v1-parameters-0.1",
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
            input_fingerprints=(("stream", "G", SHA_A), ("stream", "I", SHA_B)),
            dependency_fingerprints=(),
        ),
        payload=payload,
    )


def _temporal(phases: tuple[SemanticPhase, ...]) -> dict[str, object]:
    return {
        "window_policy": "bound-phase-windows-v1",
        "window_id_prefix": "h1",
        "scope_ids": [phase.phase_id for phase in phases],
        "phase_bindings": [
            {
                "phase_id": phase.phase_id,
                "start_t_ns": phase.start_t_ns,
                "end_t_ns": phase.end_t_ns,
                "include_session_terminal_point": phase.include_session_terminal_point,
            }
            for phase in phases
        ],
        "aoi_ids": ["display", "other-scene"],
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
            producer_anchor_id="H1",
            producer_plugin_id="h1-aoi-dwell",
            producer_plugin_version="0.1.0",
            parameter_hash=SHA_A,
            dependency_fingerprints=(SHA_A,),
        )

    def stage_blob(self, artifact_id, payload):  # pragma: no cover - H1 is table-only
        raise AssertionError((artifact_id, payload))


def _compute(
    phases: tuple[SemanticPhase, ...],
    frame: pl.DataFrame,
    *,
    include_i: bool = True,
    include_g: bool = True,
    frame_times: tuple[int, ...] = (0,),
):
    emitter = _Emitter([])
    end_t_ns = max(phase.end_t_ns for phase in phases)
    measurement = create_plugin().compute(
        _context(
            phases,
            include_i=include_i,
            include_g=include_g,
            frame_times=frame_times,
        ),
        {},
        _temporal(phases),
        ResolvedDependencies(
            results={},
            artifacts={},
            algorithm_profiles={},
            preprocessing={"gaze-aoi-intervals": _dependency(frame, end_t_ns)},
        ),
        emitter,
    )
    return measurement, emitter


def test_h1_definition_binds_gaze_interval_dependency_and_phase_dwell_artifact() -> None:
    definition = create_plugin().definition()

    assert definition.anchor_id == "H1"
    assert definition.required_streams == ("I", "G")
    assert definition.required_semantic_paths == ("semantic.aois", "semantic.phases")
    assert tuple(item.dependency_id for item in definition.dependencies) == ("gaze-aoi-intervals",)
    assert definition.artifact_recipes[0].schema_id == "phase-dwell-v0.1"


def test_h1_pools_phase_numerators_and_denominators_instead_of_averaging_percentages() -> None:
    phases = (_phase("phase-1", 0, NS), _phase("phase-2", NS, 4 * NS))
    frame = _intervals(
        (
            ("i-1", 0, 800_000_000, 0, "0", "display", "primary", True),
            ("i-2", 800_000_000, NS, 1, "0", "other-scene", "other_scene", True),
            ("i-3", NS, 3_700_000_000, 2, "0", "display", "primary", True),
            (
                "i-4",
                3_700_000_000,
                4 * NS,
                3,
                "0",
                "other-scene",
                "other_scene",
                True,
            ),
        )
    )

    measurement, emitter = _compute(phases, frame)

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is not None
    assert measurement.primary_value.unit == "percent"
    assert measurement.primary_value.value == pytest.approx(87.5)
    assert [item.primary_value.value for item in measurement.phase_results] == pytest.approx(
        [80.0, 90.0]
    )
    assert measurement.raw_metrics["total-gaze-dwell"].value == 4 * NS
    assert measurement.raw_metrics["weighted-gaze-dwell"].value == pytest.approx(3.5 * NS)

    assert len(emitter.payloads) == 1
    artifact_id, payload = emitter.payloads[0]
    assert artifact_id == "phase-dwell"
    assert payload.frame.select(
        "phase_id", "role_id", "dwell_ns", "weighted_dwell_ns", "total_dwell_ns"
    ).rows() == [
        ("phase-1", "other_scene", 200_000_000, 0.0, NS),
        ("phase-1", "primary", 800_000_000, 800_000_000.0, NS),
        ("phase-2", "other_scene", 300_000_000, 0.0, 3 * NS),
        ("phase-2", "primary", 2_700_000_000, 2_700_000_000.0, 3 * NS),
    ]


def test_complete_off_task_gaze_is_computed_zero_evidence_not_filtered_or_missing() -> None:
    phases = (_phase("phase-1", 0, NS),)
    frame = _intervals((("i-1", 0, NS, 0, "0", "other-scene", "other_scene", False),))

    measurement, _emitter = _compute(phases, frame)

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is not None
    assert measurement.primary_value.value == 0.0
    assert measurement.classification_override_candidate is None
    schema = load_parameter_schema("h1-parameters-0.1")
    policy = compile_scorer_policy(schema["x-scorer-policy-default"])
    state, _score, _likelihood = classify_computed_metrics(0.0, {}, None, policy)
    assert state is EvidenceState.UNACCEPTABLE


def test_present_i_g_with_no_nonzero_gaze_dwell_is_controlled_computed_u() -> None:
    phases = (_phase("phase-1", 0, NS),)

    measurement, emitter = _compute(phases, _empty_intervals())

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is None
    assert measurement.primary_value_reason == "no_gaze_dwell"
    assert measurement.classification_override_candidate is not None
    assert measurement.classification_override_candidate.code == "no_gaze_dwell"
    assert measurement.raw_metrics["total-gaze-dwell"].value == 0
    assert len(emitter.payloads) == 1
    assert emitter.payloads[0][1].frame["total_dwell_ns"].to_list() == [0, 0]


@pytest.mark.parametrize(("include_i", "include_g"), [(False, True), (True, False)])
def test_truly_absent_required_stream_is_missing_input(include_i: bool, include_g: bool) -> None:
    phases = (_phase("phase-1", 0, NS),)

    measurement, emitter = _compute(
        phases,
        _empty_intervals(),
        include_i=include_i,
        include_g=include_g,
    )

    assert measurement.calculation_status.value == "missing_input"
    assert measurement.primary_value is None
    assert measurement.classification_override_candidate is None
    assert emitter.payloads == []


def test_scene_gap_makes_only_the_unobserved_phase_missing_without_skipping_breakdowns() -> None:
    phases = (_phase("phase-1", 0, 500_000_000), _phase("phase-2", NS, 2 * NS))
    frame = _intervals((("i-1", 0, 500_000_000, 0, "0", "display", "primary", True),))

    measurement, _emitter = _compute(
        phases,
        frame,
        frame_times=(0, 100_000_000, 200_000_000, 2 * NS),
    )

    assert measurement.calculation_status.value == "missing_input"
    assert tuple(item.calculation_status.value for item in measurement.phase_results) == (
        "computed",
        "missing_input",
    )
    assert measurement.primary_value is None
