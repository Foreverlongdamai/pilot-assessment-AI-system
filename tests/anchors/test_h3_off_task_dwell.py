from __future__ import annotations

from dataclasses import dataclass

import polars as pl
import pytest

from pilot_assessment.anchors.artifacts import InMemoryDerivedArtifactSink
from pilot_assessment.anchors.catalog import load_parameter_schema
from pilot_assessment.anchors.plugins.h1_aoi_dwell import create_plugin as create_h1_plugin
from pilot_assessment.anchors.plugins.h3_off_task_dwell import create_plugin
from pilot_assessment.anchors.preprocessing import (
    PreprocessingResolutionContext,
    PreprocessingResolver,
    preprocessing_dependency_fingerprint,
)
from pilot_assessment.anchors.primitives.gaze_aoi import create_provider as create_gaze_provider
from pilot_assessment.anchors.protocols import (
    AnchorPluginContext,
    PreprocessingScope,
    ProjectedSemanticScope,
    ResolvedDependencies,
    TabularArtifactPayload,
)
from pilot_assessment.anchors.registry import PluginRegistry
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
from tests.anchors.test_gaze_aoi import (
    _catch_all as _provider_catch_all,
)
from tests.anchors.test_gaze_aoi import (
    _context as _provider_context,
)
from tests.anchors.test_gaze_aoi import (
    _frames as _provider_frames,
)
from tests.anchors.test_gaze_aoi import (
    _gaze as _provider_gaze,
)
from tests.anchors.test_gaze_aoi import (
    _phase as _provider_phase,
)
from tests.anchors.test_gaze_aoi import (
    _polygon as _provider_polygon,
)
from tests.anchors.test_gaze_aoi import (
    _recipe as _provider_recipe,
)
from tests.anchors.test_h1_aoi_dwell import (
    _dependency as _gaze_dependency,
)
from tests.anchors.test_h1_aoi_dwell import (
    _empty_gaze,
    _frames,
    _intervals,
)

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


def _polygon(
    aoi_id: str,
    *,
    role: str,
    role_weight: float,
    off_task: bool,
) -> AoiDefinition:
    return AoiDefinition(
        aoi_id=aoi_id,
        taxonomy_id="tax-1",
        role=role,
        geometry_kind=AoiGeometryKind.POLYGON_2D,
        priority=1,
        role_weight=role_weight,
        off_task=off_task,
        vertices=(
            SemanticVector(coordinate_frame_id="viewport", unit="normalized", values=(0.0, 0.0)),
            SemanticVector(coordinate_frame_id="viewport", unit="normalized", values=(1.0, 0.0)),
            SemanticVector(coordinate_frame_id="viewport", unit="normalized", values=(1.0, 1.0)),
        ),
    )


def _aois() -> tuple[AoiDefinition, ...]:
    return (
        _polygon("display", role="primary", role_weight=1.0, off_task=False),
        _polygon("off-task-panel", role="off_task", role_weight=0.0, off_task=True),
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


def _context(
    phases: tuple[SemanticPhase, ...],
    *,
    include_i: bool = True,
    include_g: bool = True,
    frame_times: tuple[int, ...] = (0,),
) -> AnchorPluginContext:
    streams: dict[str, AlignedStreamView] = {}
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
            tables={"gaze_samples": _empty_gaze()},
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


def _temporal(phases: tuple[SemanticPhase, ...]) -> dict[str, object]:
    return {
        "window_policy": "bound-phase-windows-v1",
        "window_id_prefix": "h3",
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
        "aoi_ids": ["display", "off-task-panel", "other-scene"],
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
            producer_anchor_id="H3",
            producer_plugin_id="h3-off-task-dwell",
            producer_plugin_version="0.1.0",
            parameter_hash=SHA_A,
            dependency_fingerprints=(SHA_A,),
        )

    def stage_blob(self, artifact_id, payload):  # pragma: no cover - H3 is table-only
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
            preprocessing={"gaze-aoi-intervals": _gaze_dependency(frame, end_t_ns)},
        ),
        emitter,
    )
    return measurement, emitter


class _CountingGazeProvider:
    def __init__(self, calls: list[PreprocessingScope]) -> None:
        self._provider = create_gaze_provider()
        self._calls = calls

    def definition(self):
        return self._provider.definition()

    def compute(self, context, recipe, scope, dependencies):
        self._calls.append(scope)
        return self._provider.compute(context, recipe, scope, dependencies)


def test_h3_and_h1_bind_one_exact_memoized_gaze_allocation_product() -> None:
    h1_dependency = create_h1_plugin().definition().dependencies[0]
    h3_dependency = create_plugin().definition().dependencies[0]
    recipe = _provider_recipe()

    assert h3_dependency == h1_dependency
    assert h3_dependency.target_resource_id == recipe.recipe_id == "gaze-aoi-intervals-v1"

    context = _provider_context(
        aois=(_provider_polygon("display", priority=1), _provider_catch_all()),
        phases=(_provider_phase("phase-1", 0, NS),),
        frames=_provider_frames((0,)),
        gaze=_provider_gaze((0,)),
    )
    calls: list[PreprocessingScope] = []
    definition = create_gaze_provider().definition()
    registry = PluginRegistry.from_factories_for_testing(
        {},
        {
            (definition.provider_id, definition.provider_version): lambda: _CountingGazeProvider(
                calls
            )
        },
    )
    resolver = PreprocessingResolver(registry, (recipe,))
    resolution_context = PreprocessingResolutionContext(
        provider_contexts={recipe.recipe_id: context},
        input_fingerprints={recipe.recipe_id: (("stream", "G", SHA_A), ("stream", "I", SHA_B))},
    )
    scope = PreprocessingScope(
        kind="session",
        scope_id="session-1",
        start_t_ns=0,
        end_t_ns=NS,
        phase_id=None,
        event_id=None,
        window_id=None,
    )
    transaction = InMemoryDerivedArtifactSink().begin_evaluation("h1-h3-shared-gaze")

    for_h1 = resolver.resolve(recipe, resolution_context, scope, transaction)
    for_h3 = resolver.resolve(recipe, resolution_context, scope, transaction)

    assert for_h1 is for_h3
    assert len(calls) == 1
    assert for_h1.identity.logical_content_sha256 == for_h3.identity.logical_content_sha256
    assert preprocessing_dependency_fingerprint(for_h1) == preprocessing_dependency_fingerprint(
        for_h3
    )


def test_h3_definition_binds_off_task_artifact_contract() -> None:
    definition = create_plugin().definition()

    assert definition.anchor_id == "H3"
    assert definition.required_streams == ("I", "G")
    assert definition.required_semantic_paths == ("semantic.aois", "semantic.phases")
    assert tuple(item.dependency_id for item in definition.dependencies) == ("gaze-aoi-intervals",)
    assert definition.artifact_recipes[0].artifact_id == "phase-off-task-dwell"
    assert definition.artifact_recipes[0].schema_id == "phase-off-task-dwell-v0.1"


def test_h3_counts_other_scene_and_pools_phase_durations_before_division() -> None:
    phases = (_phase("phase-1", 0, NS), _phase("phase-2", NS, 5 * NS))
    frame = _intervals(
        (
            ("i-1", 0, 900_000_000, 0, "0", "display", "primary", True),
            (
                "i-2",
                900_000_000,
                NS,
                1,
                "0",
                "other-scene",
                "other_scene",
                False,
            ),
            ("i-3", NS, 4_920_000_000, 2, "0", "display", "primary", True),
            (
                "i-4",
                4_920_000_000,
                5 * NS,
                3,
                "0",
                "off-task-panel",
                "off_task",
                True,
            ),
        )
    )

    measurement, emitter = _compute(phases, frame)

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(3.6)
    assert [item.primary_value.value for item in measurement.phase_results] == pytest.approx(
        [10.0, 2.0]
    )
    assert measurement.raw_metrics["off-task-gaze-dwell"].value == 180_000_000
    assert measurement.raw_metrics["total-gaze-dwell"].value == 5 * NS
    assert measurement.raw_metrics["invalid-association-count"].value == 1

    assert len(emitter.payloads) == 1
    artifact_id, payload = emitter.payloads[0]
    assert artifact_id == "phase-off-task-dwell"
    assert payload.frame.rows() == [
        ("phase-1", "off_task", True, 0, NS),
        ("phase-1", "other_scene", True, 100_000_000, NS),
        ("phase-1", "primary", False, 900_000_000, NS),
        ("phase-2", "off_task", True, 80_000_000, 4 * NS),
        ("phase-2", "other_scene", True, 0, 4 * NS),
        ("phase-2", "primary", False, 3_920_000_000, 4 * NS),
    ]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (4.999, EvidenceState.DESIRED),
        (5.0, EvidenceState.ADEQUATE),
        (14.999, EvidenceState.ADEQUATE),
        (15.0, EvidenceState.UNACCEPTABLE),
    ],
)
def test_h3_threshold_boundaries_are_exact(value: float, expected: EvidenceState) -> None:
    schema = load_parameter_schema("h3-parameters-0.1")
    policy = compile_scorer_policy(schema["x-scorer-policy-default"])

    state, _score, _likelihood = classify_computed_metrics(value, {}, None, policy)

    assert state is expected


def test_complete_finite_off_task_gaze_is_computed_unacceptable_not_filtered() -> None:
    phases = (_phase("phase-1", 0, NS),)
    frame = _intervals((("i-1", 0, NS, 0, "0", "other-scene", "other_scene", False),))

    measurement, _emitter = _compute(phases, frame)

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is not None
    assert measurement.primary_value.value == 100.0
    assert measurement.classification_override_candidate is None
    schema = load_parameter_schema("h3-parameters-0.1")
    policy = compile_scorer_policy(schema["x-scorer-policy-default"])
    state, _score, _likelihood = classify_computed_metrics(100.0, {}, None, policy)
    assert state is EvidenceState.UNACCEPTABLE


def test_present_i_g_with_zero_dwell_is_computed_u_not_zero_percent_desired() -> None:
    phases = (_phase("phase-1", 0, NS),)

    measurement, emitter = _compute(phases, _intervals(()))

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is None
    assert measurement.primary_value_reason == "no_gaze_dwell"
    assert measurement.classification_override_candidate is not None
    assert measurement.classification_override_candidate.code == "no_gaze_dwell"
    assert measurement.raw_metrics["total-gaze-dwell"].value == 0
    assert len(emitter.payloads) == 1
    assert emitter.payloads[0][1].frame["total_dwell_ns"].to_list() == [0, 0, 0]

    schema = load_parameter_schema("h3-parameters-0.1")
    policy = compile_scorer_policy(schema["x-scorer-policy-default"])
    state, _score, _likelihood = classify_computed_metrics(None, {}, "no_gaze_dwell", policy)
    assert state is EvidenceState.UNACCEPTABLE


@pytest.mark.parametrize(("include_i", "include_g"), [(False, True), (True, False)])
def test_truly_absent_required_stream_is_missing_input(include_i: bool, include_g: bool) -> None:
    phases = (_phase("phase-1", 0, NS),)

    measurement, emitter = _compute(
        phases,
        _intervals(()),
        include_i=include_i,
        include_g=include_g,
    )

    assert measurement.calculation_status.value == "missing_input"
    assert measurement.primary_value is None
    assert measurement.classification_override_candidate is None
    assert emitter.payloads == []


def test_scene_gap_preserves_all_phase_breakdowns_and_marks_missing_opportunity() -> None:
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
