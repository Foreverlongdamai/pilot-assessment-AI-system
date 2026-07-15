from __future__ import annotations

import math
from collections.abc import Sequence

import polars as pl

from pilot_assessment.anchors.catalog import parameter_schema_sha256
from pilot_assessment.anchors.fingerprint import (
    parameter_snapshot_fingerprint,
    preprocessing_definition_fingerprint,
    schema_descriptor_sha256,
)
from pilot_assessment.anchors.primitives.fixation import create_provider
from pilot_assessment.anchors.protocols import (
    AnchorPluginContext,
    PreprocessingScope,
    ProjectedSemanticScope,
)
from pilot_assessment.contracts.anchor_execution import (
    AoiDefinition,
    AoiGeometryKind,
    ResolvedPreprocessingRecipe,
    SemanticVector,
)
from pilot_assessment.contracts.synchronization import SessionWindow
from pilot_assessment.synchronization.models import AlignedStreamView

NS = 1_000_000_000
SHA_A = "a" * 64


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


def _ray(degrees: float) -> tuple[float, float, float]:
    radians = math.radians(degrees)
    return (math.sin(radians), 0.0, math.cos(radians))


def _gaze(
    rows: Sequence[tuple[int, int, tuple[float, float, float], str, bool, bool, float]],
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "gaze_sample_id": pl.Series([row[0] for row in rows], dtype=pl.UInt64),
            "t_ns": pl.Series([row[1] for row in rows], dtype=pl.Int64),
            "in_session": pl.Series([True] * len(rows), dtype=pl.Boolean),
            "ray_x": pl.Series([row[2][0] for row in rows], dtype=pl.Float64),
            "ray_y": pl.Series([row[2][1] for row in rows], dtype=pl.Float64),
            "ray_z": pl.Series([row[2][2] for row in rows], dtype=pl.Float64),
            "binocular_valid": pl.Series([row[4] for row in rows], dtype=pl.Boolean),
            "blink": pl.Series([row[5] for row in rows], dtype=pl.Boolean),
            "confidence": pl.Series([row[6] for row in rows], dtype=pl.Float64),
            "assigned_aoi_id": pl.Series([row[3] for row in rows], dtype=pl.String),
        }
    )


def _context(gaze: pl.DataFrame, *, end_t_ns: int = NS) -> AnchorPluginContext:
    return AnchorPluginContext(
        session_id="session-1",
        session_window=SessionWindow(
            end_t_ns=end_t_ns,
            source="master-clock-x-mapped-coverage-v1",
        ),
        streams={
            "G": AlignedStreamView(
                modality="G",
                source_schema_id="gaze-source-bundle-v0.1",
                aligned_schema_id="gaze-aligned-v0.1",
                clock_id="master-clock",
                tables={
                    "gaze_samples": gaze,
                    "fixations": pl.DataFrame(
                        {
                            "fixation_id": ["device-wrong"],
                            "start_t_ns": [0],
                            "end_t_ns": [NS],
                            "aoi_id": ["other-scene"],
                        }
                    ),
                },
                json_artifacts={},
                file_artifacts={},
                source_checksums={"gaze": SHA_A},
            )
        },
        context={},
        references={},
        semantic_scope=ProjectedSemanticScope(
            values={"semantic.aois": [item.model_dump(mode="json") for item in _aois()]}
        ),
    )


def _recipe(
    *, threshold: float = 100.0, minimum_duration_ns: int = 100_000_000
) -> ResolvedPreprocessingRecipe:
    definition = create_provider().definition()
    parameters = {
        "angular_velocity_threshold_deg_s": threshold,
        "minimum_fixation_duration_ns": minimum_duration_ns,
    }
    return ResolvedPreprocessingRecipe(
        recipe_id="fixation-intervals-v1",
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


def _compute(
    gaze: pl.DataFrame,
    *,
    end_t_ns: int = NS,
    threshold: float = 100.0,
    minimum_duration_ns: int = 100_000_000,
) -> pl.DataFrame:
    return (
        create_provider()
        .compute(
            _context(gaze, end_t_ns=end_t_ns),
            _recipe(threshold=threshold, minimum_duration_ns=minimum_duration_ns),
            PreprocessingScope(
                kind="session",
                scope_id="session-1",
                start_t_ns=0,
                end_t_ns=end_t_ns,
                phase_id=None,
                event_id=None,
                window_id=None,
            ),
            {},
        )
        .frame
    )


def test_provider_definition_declares_raw_gaze_and_aoi_semantics_only() -> None:
    definition = create_provider().definition()

    assert definition.provider_id == "fixation-intervals-v1"
    assert definition.provider_version == "1.0.0"
    assert definition.required_streams == ("G",)
    assert definition.required_semantic_paths == ("semantic.aois",)
    assert definition.dependencies == ()
    assert definition.output_schema_id == "fixation-intervals-v1-output-v0.1"


def test_shortest_sphere_velocity_recomputes_raw_gaze_and_ignores_device_fixations() -> None:
    frame = _compute(
        _gaze(
            (
                (0, 0, _ray(179.0), "display", True, False, 0.01),
                (1, 50_000_000, _ray(180.0), "display", True, False, 0.01),
                (2, 100_000_000, _ray(-179.0), "display", True, False, 0.01),
            )
        )
    )

    assert frame.select("start_t_ns", "end_t_ns", "aoi_id", "role_id").rows() == [
        (0, 100_000_000, "display", "primary")
    ]
    assert frame["fixation_id"].to_list() != ["device-wrong"]


def test_exact_100_deg_per_second_and_100_ms_duration_are_inclusive() -> None:
    frame = _compute(
        _gaze(
            (
                (0, 0, _ray(0.0), "display", True, False, 1.0),
                (1, 50_000_000, _ray(5.0), "display", True, False, 1.0),
                (2, 100_000_000, _ray(10.0), "display", True, False, 1.0),
            )
        )
    )

    assert frame.select("start_t_ns", "end_t_ns").rows() == [(0, 100_000_000)]


def test_subminimum_99_ms_run_is_not_promoted_to_a_fixation() -> None:
    frame = _compute(
        _gaze(
            (
                (0, 0, _ray(0.0), "display", True, False, 1.0),
                (1, 99_000_000, _ray(0.0), "display", True, False, 1.0),
            )
        )
    )

    assert frame.is_empty()


def test_duplicate_timestamp_keeps_stable_first_row_before_velocity_detection() -> None:
    frame = _compute(
        _gaze(
            (
                (2, 0, _ray(90.0), "other-scene", True, False, 1.0),
                (1, 0, _ray(0.0), "display", True, False, 1.0),
                (3, 50_000_000, _ray(0.0), "display", True, False, 1.0),
                (4, 100_000_000, _ray(0.0), "display", True, False, 1.0),
            )
        )
    )

    assert frame.select("start_t_ns", "end_t_ns", "aoi_id").rows() == [(0, 100_000_000, "display")]


def test_gap_and_blink_cut_runs_but_low_confidence_does_not_filter_valid_gaze() -> None:
    gap = _compute(
        _gaze(
            (
                (0, 0, _ray(0.0), "display", True, False, 0.0),
                (1, 40_000_000, _ray(0.0), "display", True, False, 0.0),
                (2, 100_000_000, _ray(0.0), "display", True, False, 0.0),
            )
        )
    )
    blink = _compute(
        _gaze(
            (
                (0, 0, _ray(0.0), "display", True, False, 0.0),
                (1, 50_000_000, _ray(0.0), "display", True, True, 0.0),
                (2, 100_000_000, _ray(0.0), "display", True, False, 0.0),
            )
        )
    )
    valid = _compute(
        _gaze(
            (
                (0, 0, _ray(0.0), "display", True, False, 0.0),
                (1, 50_000_000, _ray(0.0), "display", True, False, 0.0),
                (2, 100_000_000, _ray(0.0), "display", True, False, 0.0),
            )
        )
    )

    assert gap.is_empty()
    assert blink.is_empty()
    assert valid.height == 1
