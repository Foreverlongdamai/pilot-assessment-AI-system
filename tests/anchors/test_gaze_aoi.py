from __future__ import annotations

from collections.abc import Sequence

import polars as pl

from pilot_assessment.anchors.catalog import parameter_schema_sha256
from pilot_assessment.anchors.fingerprint import (
    parameter_snapshot_fingerprint,
    preprocessing_definition_fingerprint,
    schema_descriptor_sha256,
)
from pilot_assessment.anchors.primitives.gaze_aoi import create_provider
from pilot_assessment.anchors.protocols import (
    AnchorPluginContext,
    PreprocessingScope,
    ProjectedSemanticScope,
)
from pilot_assessment.contracts.anchor_execution import (
    AoiDefinition,
    AoiGeometryKind,
    DynamicAoiSource,
    ResolvedInputFieldContract,
    ResolvedInputTableContract,
    ResolvedPreprocessingRecipe,
    SemanticPhase,
    SemanticVector,
)
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


def _catch_all(taxonomy_id: str = "tax-1") -> AoiDefinition:
    return AoiDefinition(
        aoi_id="other-scene",
        taxonomy_id=taxonomy_id,
        role="other_scene",
        geometry_kind=AoiGeometryKind.CATCH_ALL,
        priority=0,
        role_weight=0.0,
        off_task=True,
    )


def _dynamic_2d(
    aoi_id: str,
    *,
    priority: int = 1,
    role: str = "primary",
    taxonomy_id: str = "tax-1",
) -> AoiDefinition:
    return AoiDefinition(
        aoi_id=aoi_id,
        taxonomy_id=taxonomy_id,
        role=role,
        geometry_kind=AoiGeometryKind.DYNAMIC_2D,
        priority=priority,
        role_weight=1.0,
        off_task=False,
        dynamic_source=DynamicAoiSource(
            table_role="aoi_instances",
            aligned_schema_id="vr-aoi-instance-aligned-v0.1",
            coordinate_frame_id="viewport",
            unit="normalized",
            frame_id_field="frame_id",
            aoi_id_field="aoi_id",
            geometry_field_ids=(
                "bbox_x_norm",
                "bbox_y_norm",
                "bbox_w_norm",
                "bbox_h_norm",
            ),
        ),
    )


def _polygon(
    aoi_id: str,
    *,
    priority: int,
    taxonomy_id: str = "tax-1",
) -> AoiDefinition:
    return AoiDefinition(
        aoi_id=aoi_id,
        taxonomy_id=taxonomy_id,
        role="primary",
        geometry_kind=AoiGeometryKind.POLYGON_2D,
        priority=priority,
        role_weight=1.0,
        off_task=False,
        vertices=(
            SemanticVector(coordinate_frame_id="viewport", unit="normalized", values=(0.1, 0.1)),
            SemanticVector(coordinate_frame_id="viewport", unit="normalized", values=(0.9, 0.1)),
            SemanticVector(coordinate_frame_id="viewport", unit="normalized", values=(0.9, 0.9)),
            SemanticVector(coordinate_frame_id="viewport", unit="normalized", values=(0.1, 0.9)),
        ),
    )


def _box(aoi_id: str, z_min: float, z_max: float, *, priority: int) -> AoiDefinition:
    return AoiDefinition(
        aoi_id=aoi_id,
        taxonomy_id="tax-1",
        role="primary",
        geometry_kind=AoiGeometryKind.BOX_3D,
        priority=priority,
        role_weight=1.0,
        off_task=False,
        vertices=(
            SemanticVector(coordinate_frame_id="world", unit="m", values=(-0.5, -0.5, z_min)),
            SemanticVector(coordinate_frame_id="world", unit="m", values=(0.5, 0.5, z_max)),
        ),
    )


def _frames(
    timestamps_ns: Sequence[int],
    *,
    frame_ids: Sequence[int] | None = None,
    valid: Sequence[bool] | None = None,
) -> pl.DataFrame:
    ids = tuple(range(len(timestamps_ns))) if frame_ids is None else tuple(frame_ids)
    flags = tuple(True for _ in timestamps_ns) if valid is None else tuple(valid)
    count = len(timestamps_ns)
    return pl.DataFrame(
        {
            "frame_id": pl.Series(ids, dtype=pl.UInt64),
            "t_ns": pl.Series(timestamps_ns, dtype=pl.Int64),
            "in_session": pl.Series([True] * count, dtype=pl.Boolean),
            "width": pl.Series([100] * count, dtype=pl.UInt32),
            "height": pl.Series([100] * count, dtype=pl.UInt32),
            "head_x_m": pl.Series([0.0] * count, dtype=pl.Float32),
            "head_y_m": pl.Series([0.0] * count, dtype=pl.Float32),
            "head_z_m": pl.Series([0.0] * count, dtype=pl.Float32),
            "head_qx": pl.Series([0.0] * count, dtype=pl.Float32),
            "head_qy": pl.Series([0.0] * count, dtype=pl.Float32),
            "head_qz": pl.Series([0.0] * count, dtype=pl.Float32),
            "head_qw": pl.Series([1.0] * count, dtype=pl.Float32),
            "horizontal_fov_deg": pl.Series([90.0] * count, dtype=pl.Float32),
            "vertical_fov_deg": pl.Series([90.0] * count, dtype=pl.Float32),
            "frame_valid": pl.Series(flags, dtype=pl.Boolean),
        }
    )


def _gaze(
    timestamps_ns: Sequence[int],
    *,
    sample_ids: Sequence[int] | None = None,
    scene_frame_ids: Sequence[int] | None = None,
    x: Sequence[float | None] | None = None,
    y: Sequence[float | None] | None = None,
    origins: Sequence[tuple[float | None, float | None, float | None]] | None = None,
    rays: Sequence[tuple[float | None, float | None, float | None]] | None = None,
    binocular_valid: Sequence[bool] | None = None,
    confidence: Sequence[float] | None = None,
    blink: Sequence[bool] | None = None,
    in_session: Sequence[bool] | None = None,
) -> pl.DataFrame:
    count = len(timestamps_ns)
    ids = tuple(range(count)) if sample_ids is None else tuple(sample_ids)
    frames = tuple(0 for _ in range(count)) if scene_frame_ids is None else tuple(scene_frame_ids)
    xs = tuple(0.5 for _ in range(count)) if x is None else tuple(x)
    ys = tuple(0.5 for _ in range(count)) if y is None else tuple(y)
    origins = tuple((0.0, 0.0, 0.0) for _ in range(count)) if origins is None else tuple(origins)
    rays = tuple((0.0, 0.0, 1.0) for _ in range(count)) if rays is None else tuple(rays)
    valid = tuple(True for _ in range(count)) if binocular_valid is None else tuple(binocular_valid)
    confidences = tuple(1.0 for _ in range(count)) if confidence is None else tuple(confidence)
    blinks = tuple(False for _ in range(count)) if blink is None else tuple(blink)
    masks = tuple(True for _ in range(count)) if in_session is None else tuple(in_session)
    return pl.DataFrame(
        {
            "gaze_sample_id": pl.Series(ids, dtype=pl.UInt64),
            "t_ns": pl.Series(timestamps_ns, dtype=pl.Int64),
            "in_session": pl.Series(masks, dtype=pl.Boolean),
            "scene_frame_id": pl.Series(frames, dtype=pl.UInt64),
            "viewport_x_norm": pl.Series(xs, dtype=pl.Float32),
            "viewport_y_norm": pl.Series(ys, dtype=pl.Float32),
            "origin_x_m": pl.Series([item[0] for item in origins], dtype=pl.Float32),
            "origin_y_m": pl.Series([item[1] for item in origins], dtype=pl.Float32),
            "origin_z_m": pl.Series([item[2] for item in origins], dtype=pl.Float32),
            "ray_x": pl.Series([item[0] for item in rays], dtype=pl.Float32),
            "ray_y": pl.Series([item[1] for item in rays], dtype=pl.Float32),
            "ray_z": pl.Series([item[2] for item in rays], dtype=pl.Float32),
            "binocular_valid": pl.Series(valid, dtype=pl.Boolean),
            "confidence": pl.Series(confidences, dtype=pl.Float32),
            "blink": pl.Series(blinks, dtype=pl.Boolean),
            "assigned_aoi_id": pl.Series(["deliberately-wrong"] * count, dtype=pl.String),
            "assignment_confidence": pl.Series([1.0] * count, dtype=pl.Float32),
        }
    )


def _dynamic_rows(rows: Sequence[tuple[int, str, float, float, float, float]]) -> pl.DataFrame:
    return pl.DataFrame(
        rows,
        schema={
            "frame_id": pl.UInt64,
            "aoi_id": pl.String,
            "bbox_x_norm": pl.Float64,
            "bbox_y_norm": pl.Float64,
            "bbox_w_norm": pl.Float64,
            "bbox_h_norm": pl.Float64,
        },
        orient="row",
    )


def _aoi_contract() -> ResolvedInputTableContract:
    return ResolvedInputTableContract(
        modality="I",
        table_role="aoi_instances",
        stream_aligned_schema_id="vr-scene-aligned-v0.1",
        table_aligned_schema_id="vr-aoi-instance-aligned-v0.1",
        coordinate_frame_id="viewport",
        fields=(
            ResolvedInputFieldContract(
                field_name="frame_id", dtype_id="u64", unit="index", nullable=False
            ),
            ResolvedInputFieldContract(
                field_name="aoi_id", dtype_id="utf8", unit="id", nullable=False
            ),
            *tuple(
                ResolvedInputFieldContract(
                    field_name=name, dtype_id="f64", unit="normalized", nullable=False
                )
                for name in (
                    "bbox_x_norm",
                    "bbox_y_norm",
                    "bbox_w_norm",
                    "bbox_h_norm",
                )
            ),
        ),
    )


def _context(
    *,
    aois: Sequence[AoiDefinition],
    phases: Sequence[SemanticPhase],
    frames: pl.DataFrame,
    gaze: pl.DataFrame,
    dynamic_rows: pl.DataFrame | None = None,
) -> AnchorPluginContext:
    i_tables = {"frame_index": frames}
    if dynamic_rows is not None:
        i_tables["aoi_instances"] = dynamic_rows
    return AnchorPluginContext(
        session_id="session-1",
        session_window=SessionWindow(
            end_t_ns=max(phase.end_t_ns for phase in phases),
            source="master-clock-x-mapped-coverage-v1",
        ),
        streams={
            "I": AlignedStreamView(
                modality="I",
                source_schema_id="vr-scene-source-bundle-v0.1",
                aligned_schema_id="vr-scene-aligned-v0.1",
                clock_id="master-clock",
                tables=i_tables,
                json_artifacts={},
                file_artifacts={},
                source_checksums={"scene": SHA_A},
            ),
            "G": AlignedStreamView(
                modality="G",
                source_schema_id="gaze-source-bundle-v0.1",
                aligned_schema_id="gaze-aligned-v0.1",
                clock_id="master-clock",
                tables={"gaze_samples": gaze},
                json_artifacts={},
                file_artifacts={},
                source_checksums={"gaze": SHA_B},
            ),
        },
        context={},
        references={},
        semantic_scope=ProjectedSemanticScope(
            values={
                "semantic.aois": [item.model_dump(mode="json") for item in aois],
                "semantic.phases": [item.model_dump(mode="json") for item in phases],
            }
        ),
        input_table_contracts=(_aoi_contract(),) if dynamic_rows is not None else (),
    )


def _recipe() -> ResolvedPreprocessingRecipe:
    definition = create_provider().definition()
    parameters: dict[str, object] = {}
    return ResolvedPreprocessingRecipe(
        recipe_id="gaze-aoi-intervals-v1",
        recipe_version="0.1.0",
        provider_id=definition.provider_id,
        provider_version=definition.provider_version,
        api_version="0.1.0",
        definition_fingerprint=preprocessing_definition_fingerprint(definition),
        implementation_digest=SHA_A,
        parameter_schema_id=definition.parameter_schema_id,
        parameter_schema_sha256=parameter_schema_sha256(definition.parameter_schema_id),
        parameters=parameters,
        parameter_hash=parameter_snapshot_fingerprint(parameters),
        required_streams=definition.required_streams,
        required_context_paths=definition.required_context_paths,
        required_semantic_paths=definition.required_semantic_paths,
        required_reference_ids=definition.required_reference_ids,
        dependency_specs=definition.dependencies,
        dependency_bindings=(),
        output_schema_id=definition.output_schema_id,
        output_schema_descriptor=definition.output_schema_descriptor,
        output_schema_sha256=schema_descriptor_sha256(
            definition.output_schema_id, definition.output_schema_descriptor
        ),
        artifact_kind=definition.artifact_kind,
        output_payload_kind="table",
        scope_policy="session",
    )


def _compute(context: AnchorPluginContext) -> pl.DataFrame:
    return (
        create_provider()
        .compute(
            context,
            _recipe(),
            PreprocessingScope(
                kind="session",
                scope_id="session-1",
                start_t_ns=0,
                end_t_ns=context.session_window.end_t_ns,
                phase_id=None,
                event_id=None,
                window_id=None,
            ),
            {},
        )
        .frame
    )


def test_provider_definition_declares_only_i_g_and_aoi_phase_semantics() -> None:
    definition = create_provider().definition()

    assert definition.provider_id == "gaze-aoi-intervals-v1"
    assert definition.provider_version == "1.0.0"
    assert definition.required_streams == ("I", "G")
    assert definition.required_semantic_paths == ("semantic.aois", "semantic.phases")
    assert definition.dependencies == ()
    assert definition.output_schema_id == "gaze-aoi-intervals-v1-output-v0.1"


def test_dynamic_2d_uses_the_first_person_frame_at_gaze_time_not_preassigned_aoi() -> None:
    phases = (_phase("phase-1", 0, 2 * NS),)
    aois = (_dynamic_2d("display"), _catch_all())
    frame = _compute(
        _context(
            aois=aois,
            phases=phases,
            frames=_frames((0, NS)),
            gaze=_gaze(
                (100_000_000, 1_100_000_000),
                scene_frame_ids=(0, 1),
                x=(0.2, 0.8),
                y=(0.5, 0.5),
            ),
            dynamic_rows=_dynamic_rows(
                (
                    (0, "display", 0.0, 0.0, 0.4, 1.0),
                    (1, "display", 0.6, 0.0, 0.4, 1.0),
                )
            ),
        )
    )

    assert frame["aoi_id"].to_list() == ["display", "display"]
    assert frame["frame_id"].to_list() == ["0", "1"]
    assert frame["gaze_source_row_id"].to_list() == [0, 1]
    assert frame["association_valid"].to_list() == [True, True]


def test_3d_hit_uses_nearest_positive_depth_then_priority_then_stable_id() -> None:
    aois = (
        _box("far-high", 3.0, 4.0, priority=99),
        _box("near-b", 1.0, 2.0, priority=3),
        _box("near-c", 1.0, 2.0, priority=3),
        _box("near-low", 1.0, 2.0, priority=2),
        _catch_all(),
    )
    frame = _compute(
        _context(
            aois=aois,
            phases=(_phase("phase-1", 0, NS),),
            frames=_frames((0,)),
            gaze=_gaze((0,), origins=((0.0, 0.0, 0.0),), rays=((0.0, 0.0, 1.0),)),
        )
    )

    assert frame["aoi_id"].to_list() == ["near-b"]


def test_overlapping_2d_aoi_uses_highest_priority_then_lexical_stable_id() -> None:
    aois = (
        _polygon("high-a", priority=5),
        _polygon("high-z", priority=5),
        _polygon("low", priority=1),
        _catch_all(),
    )
    frame = _compute(
        _context(
            aois=aois,
            phases=(_phase("phase-1", 0, NS),),
            frames=_frames((0,)),
            gaze=_gaze((0,), x=(0.5,), y=(0.5,)),
        )
    )

    assert frame["aoi_id"].to_list() == ["high-a"]


def test_low_confidence_is_retained_while_tracking_blink_and_unprojectable_map_to_other() -> None:
    step = 100_000_000
    frame = _compute(
        _context(
            aois=(_polygon("display", priority=1), _catch_all()),
            phases=(_phase("phase-1", 0, 4 * step),),
            frames=_frames((0,)),
            gaze=_gaze(
                (0, step, 2 * step, 3 * step),
                x=(0.5, 0.5, 0.5, None),
                y=(0.5, 0.5, 0.5, None),
                rays=((0.0, 0.0, 1.0), (0.0, 0.0, 1.0), (0.0, 0.0, 1.0), (None, None, None)),
                binocular_valid=(True, False, True, True),
                confidence=(0.01, 1.0, 1.0, 1.0),
                blink=(False, False, True, False),
            ),
        )
    )

    assert frame["aoi_id"].to_list() == [
        "display",
        "other-scene",
        "other-scene",
        "other-scene",
    ]
    assert frame["association_valid"].to_list() == [True, False, False, False]
    assert sum(frame["end_t_ns"] - frame["start_t_ns"]) == 4 * step


def test_stable_gaze_order_phase_clipping_and_gap_split_do_not_invent_support() -> None:
    # Positive deltas are 100, 100 and 800 ms, so the M3 5x-median threshold is 500 ms.
    frame = _compute(
        _context(
            aois=(_polygon("display", priority=1), _catch_all()),
            phases=(
                _phase("phase-1", 0, 150_000_000),
                _phase("phase-2", 150_000_000, 1_100_000_000),
            ),
            frames=_frames((0,)),
            gaze=_gaze(
                (100_000_000, 0, 0, 200_000_000, 1_000_000_000),
                sample_ids=(2, 1, 0, 3, 4),
            ),
        )
    )

    assert frame.select("start_t_ns", "end_t_ns", "gaze_source_row_id").rows() == [
        (0, 0, 0),
        (0, 100_000_000, 1),
        (100_000_000, 150_000_000, 2),
        (200_000_000, 200_000_000, 3),
        (1_000_000_000, 1_100_000_000, 4),
    ]
    assert frame.filter(
        (pl.col("start_t_ns") < 1_000_000_000) & (pl.col("end_t_ns") > 200_000_000)
    ).is_empty()


def test_world_ray_is_projected_through_current_head_pose_and_fov_when_viewport_is_null() -> None:
    frame = _compute(
        _context(
            aois=(_polygon("display", priority=1), _catch_all()),
            phases=(_phase("phase-1", 0, NS),),
            frames=_frames((0,)),
            gaze=_gaze(
                (0,),
                x=(None,),
                y=(None,),
                origins=((0.0, 0.0, 0.0),),
                rays=((0.0, 0.0, 1.0),),
            ),
        )
    )

    assert frame["aoi_id"].to_list() == ["display"]
    assert frame["association_valid"].to_list() == [True]
