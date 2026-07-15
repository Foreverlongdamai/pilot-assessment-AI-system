"""H1 AOI Dwell production plugin."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from itertools import pairwise
from typing import cast

import polars as pl
from pydantic import JsonValue

from pilot_assessment.anchors.catalog import load_packaged_catalog
from pilot_assessment.anchors.protocols import (
    AnchorArtifactEmitter,
    AnchorPluginContext,
    ReadOnlyTabularPayload,
    ResolvedDependencies,
    TabularArtifactPayload,
)
from pilot_assessment.anchors.temporal import reconstruct_point_support
from pilot_assessment.contracts.anchor_execution import (
    AnchorPluginDefinition,
    AoiDefinition,
    AoiGeometryKind,
    SemanticPhase,
)
from pilot_assessment.contracts.anchor_v2 import (
    AnchorBreakdownMeasurement,
    AnchorCalculationStatusV2,
    AnchorMeasurement,
    ClassificationOverride,
    ComputationTrace,
    MetricValue,
    SourceWindowV2,
)
from pilot_assessment.contracts.errors import DomainErrorData, ErrorSeverity

_INTERVAL_SCHEMA = {
    "interval_id": pl.String,
    "start_t_ns": pl.Int64,
    "end_t_ns": pl.Int64,
    "gaze_source_row_id": pl.Int64,
    "frame_id": pl.String,
    "aoi_id": pl.String,
    "role_id": pl.String,
    "association_valid": pl.Boolean,
}
_STATUS_PRIORITY = {
    AnchorCalculationStatusV2.NOT_COMPUTABLE: 0,
    AnchorCalculationStatusV2.MISSING_INPUT: 1,
    AnchorCalculationStatusV2.DEPENDENCY_MISSING: 2,
    AnchorCalculationStatusV2.EXTRACTOR_ERROR: 3,
}


@dataclass(frozen=True, slots=True)
class _BoundPhase:
    phase_id: str
    window: SourceWindowV2


@dataclass(frozen=True, slots=True)
class _RoleDwell:
    role_id: str
    dwell_ns: int
    weighted_dwell_ns: float


@dataclass(frozen=True, slots=True)
class _PhaseDwell:
    phase: _BoundPhase
    status: AnchorCalculationStatusV2
    reason: str | None
    role_dwells: tuple[_RoleDwell, ...]
    total_dwell_ns: int
    weighted_dwell_ns: float
    interval_count: int
    invalid_association_count: int
    source_start_t_ns: int | None
    source_end_t_ns: int | None
    scene_support_duration_ns: int


def _definition() -> AnchorPluginDefinition:
    catalog_entry = next(
        entry for entry in load_packaged_catalog().entries if entry.anchor_id == "H1"
    )
    return AnchorPluginDefinition(
        anchor_id=catalog_entry.anchor_id,
        definition_version=catalog_entry.definition_version,
        plugin_id=catalog_entry.plugin_id,
        plugin_version=catalog_entry.plugin_version,
        api_version="0.1.0",
        required_streams=tuple(
            value.removeprefix("stream.")
            for value in catalog_entry.required_inputs
            if value.startswith("stream.")
        ),
        required_context_paths=tuple(
            sorted(value for value in catalog_entry.required_inputs if value.startswith("context."))
        ),
        required_semantic_paths=tuple(
            sorted(
                value for value in catalog_entry.required_inputs if value.startswith("semantic.")
            )
        ),
        required_reference_ids=tuple(
            sorted(
                value.removeprefix("reference.")
                for value in catalog_entry.required_inputs
                if value.startswith("reference.")
            )
        ),
        dependencies=catalog_entry.dependencies,
        parameter_schema_id=catalog_entry.parameter_schema_id,
        measurement_schema_id="anchor-measurement-0.1.0",
        artifact_recipes=catalog_entry.artifact_recipes,
    )


def _strict_string(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _strict_int(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be a strict integer of at least {minimum}")
    return value


def _strings(value: object, label: str, *, canonical: bool = False) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{label} must be an ordered string array")
    result = tuple(_strict_string(item, f"{label}[{index}]") for index, item in enumerate(value))
    if len(result) != len(set(result)) or (canonical and result != tuple(sorted(result))):
        raise ValueError(f"{label} must be unique and canonical")
    return result


def _typed_phases(value: object) -> tuple[SemanticPhase, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("semantic.phases must be an ordered array")
    return tuple(SemanticPhase.model_validate(item) for item in value)


def _typed_aois(value: object) -> tuple[AoiDefinition, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("semantic.aois must be an ordered array")
    return tuple(AoiDefinition.model_validate(item) for item in value)


def _bound_phases(
    context: AnchorPluginContext, temporal_recipe: Mapping[str, JsonValue]
) -> tuple[_BoundPhase, ...]:
    if temporal_recipe.get("window_policy") != "bound-phase-windows-v1":
        raise ValueError("H1 requires window_policy=bound-phase-windows-v1")
    prefix = _strict_string(temporal_recipe.get("window_id_prefix"), "window_id_prefix")
    scope_ids = _strings(temporal_recipe.get("scope_ids"), "scope_ids")
    raw = temporal_recipe.get("phase_bindings")
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise ValueError("phase_bindings must be an ordered array")
    semantic_by_id = {
        phase.phase_id: phase
        for phase in _typed_phases(context.semantic_scope.values.get("semantic.phases"))
    }
    parsed: list[_BoundPhase] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping) or set(item) != {
            "phase_id",
            "start_t_ns",
            "end_t_ns",
            "include_session_terminal_point",
        }:
            raise ValueError("H1 phase bindings require the exact four-key contract")
        binding = cast(Mapping[str, object], item)
        phase_id = _strict_string(binding["phase_id"], f"phase_bindings[{index}].phase_id")
        start = _strict_int(binding["start_t_ns"], f"phase_bindings[{index}].start_t_ns")
        end = _strict_int(binding["end_t_ns"], f"phase_bindings[{index}].end_t_ns", minimum=1)
        terminal = binding["include_session_terminal_point"]
        if type(terminal) is not bool or end <= start:
            raise ValueError("H1 phase bindings require a positive span and strict terminal flag")
        semantic = semantic_by_id.get(phase_id)
        if semantic is None or (
            semantic.start_t_ns,
            semantic.end_t_ns,
            semantic.include_session_terminal_point,
        ) != (start, end, terminal):
            raise ValueError("H1 phase binding disagrees with immutable phase semantics")
        if start < context.session_window.start_t_ns or end > context.session_window.end_t_ns:
            raise ValueError("H1 phase binding lies outside the immutable session window")
        parsed.append(
            _BoundPhase(
                phase_id=phase_id,
                window=SourceWindowV2(
                    window_id=f"{prefix}-{phase_id}",
                    start_t_ns=start,
                    end_t_ns=end,
                    phase_id=phase_id,
                    event_id=None,
                    include_session_terminal_point=terminal,
                ),
            )
        )
    if tuple(item.phase_id for item in parsed) != scope_ids:
        raise ValueError("H1 phase bindings must exactly match ordered scope_ids")
    if any(
        current.window.start_t_ns < previous.window.end_t_ns
        for previous, current in zip(parsed, parsed[1:], strict=False)
    ):
        raise ValueError("H1 phase bindings must not overlap")
    return tuple(parsed)


def _selected_aois(
    context: AnchorPluginContext, temporal_recipe: Mapping[str, JsonValue]
) -> tuple[AoiDefinition, ...]:
    aoi_ids = _strings(temporal_recipe.get("aoi_ids"), "aoi_ids", canonical=True)
    all_aois = _typed_aois(context.semantic_scope.values.get("semantic.aois"))
    by_id = {aoi.aoi_id: aoi for aoi in all_aois}
    if len(by_id) != len(all_aois) or any(aoi_id not in by_id for aoi_id in aoi_ids):
        raise ValueError("H1 aoi_ids do not resolve exactly")
    selected = tuple(by_id[aoi_id] for aoi_id in aoi_ids)
    taxonomy_ids = {aoi.taxonomy_id for aoi in selected}
    if len(taxonomy_ids) != 1:
        raise ValueError("H1 v0.1 requires one exact AOI taxonomy")
    taxonomy_id = next(iter(taxonomy_ids))
    full_taxonomy = {aoi.aoi_id for aoi in all_aois if aoi.taxonomy_id == taxonomy_id}
    if set(aoi_ids) != full_taxonomy:
        raise ValueError("H1 aoi_ids must contain the complete selected taxonomy")
    if sum(aoi.geometry_kind is AoiGeometryKind.CATCH_ALL for aoi in selected) != 1:
        raise ValueError("H1 AOI taxonomy requires exactly one catch-all")
    return selected


def _interval_frame(dependencies: ResolvedDependencies) -> pl.DataFrame:
    dependency = dependencies.preprocessing.get("gaze-aoi-intervals")
    if dependency is None or not isinstance(dependency.payload, ReadOnlyTabularPayload):
        raise ValueError("H1 requires its resolved gaze-AOI interval table dependency")
    frame = dependency.payload.frame
    if frame.schema != _INTERVAL_SCHEMA or any(
        frame[column].null_count() for column in frame.columns
    ):
        raise ValueError("H1 gaze-AOI interval dependency has an invalid exact schema")
    ordered = frame.sort(["start_t_ns", "end_t_ns", "interval_id"], maintain_order=True)
    if not ordered.equals(frame) or frame.select("interval_id").is_duplicated().any():
        raise ValueError("H1 gaze-AOI intervals must use canonical unique order")
    starts = cast(list[int], frame["start_t_ns"].to_list())
    ends = cast(list[int], frame["end_t_ns"].to_list())
    if any(start < 0 or end < start for start, end in zip(starts, ends, strict=True)):
        raise ValueError("H1 gaze-AOI intervals require ordered non-negative bounds")
    return frame


def _gap_threshold(times: Sequence[int]) -> int | None:
    deltas = sorted(
        current - previous for previous, current in pairwise(sorted(times)) if current > previous
    )
    if not deltas:
        return None
    middle = len(deltas) // 2
    median = (
        Decimal(deltas[middle])
        if len(deltas) % 2
        else (Decimal(deltas[middle - 1]) + Decimal(deltas[middle])) / Decimal(2)
    )
    return int((median * Decimal("5.0")).to_integral_value(rounding=ROUND_HALF_EVEN))


def _scene_support_duration(context: AnchorPluginContext, phase: _BoundPhase) -> int:
    scene = context.streams.get("I")
    table = None if scene is None else scene.tables.get("frame_index")
    if table is None or not {"frame_id", "t_ns", "in_session"} <= set(table.columns):
        return 0
    if (
        table.schema["frame_id"] != pl.UInt64
        or table.schema["t_ns"] != pl.Int64
        or table.schema["in_session"] != pl.Boolean
        or any(table[column].null_count() for column in ("frame_id", "t_ns", "in_session"))
    ):
        return 0
    times = cast(list[int], table.filter(pl.col("in_session"))["t_ns"].to_list())
    support = reconstruct_point_support(
        table,
        timestamp_column="t_ns",
        stable_keys=("frame_id",),
        in_session_column="in_session",
        gap_threshold_ns=_gap_threshold(times),
        semantic_end_t_ns=context.session_window.end_t_ns,
    )
    return sum(
        max(
            0,
            min(interval.end_t_ns, phase.window.end_t_ns)
            - max(interval.start_t_ns, phase.window.start_t_ns),
        )
        for interval in support.intervals
    )


def _diagnostic(phase: _PhaseDwell) -> DomainErrorData:
    if phase.status is AnchorCalculationStatusV2.MISSING_INPUT:
        message = f"H1 phase {phase.phase.phase_id} lacks an observed I/G assessment opportunity."
        path = "streams.I.frame_index"
        remediation = "Provide aligned I and G streams with scene support in the bound phase."
    else:
        message = f"H1 phase {phase.phase.phase_id} contains no nonzero gaze dwell."
        path = "dependencies.gaze-aoi-intervals"
        remediation = (
            "No filtering was applied; inspect the gaze interval trace and simulator export."
        )
    return DomainErrorData(
        error_code=f"anchor.h1.{phase.reason or 'unknown'}",
        severity=ErrorSeverity.WARNING,
        recoverable=True,
        message=message,
        field_or_path=path,
        node_or_anchor_id="H1",
        remediation=remediation,
        diagnostics={
            "phase_id": phase.phase.phase_id,
            "reason": phase.reason or "unknown",
            "scene_support_duration_ns": phase.scene_support_duration_ns,
            "total_gaze_dwell_ns": phase.total_dwell_ns,
        },
    )


def _raw_metrics(phase: _PhaseDwell) -> dict[str, MetricValue]:
    return {
        "total-gaze-dwell": MetricValue(
            scalar_kind="integer", value=phase.total_dwell_ns, unit="ns"
        ),
        "weighted-gaze-dwell": MetricValue(
            scalar_kind="float", value=float(phase.weighted_dwell_ns), unit="ns"
        ),
        "gaze-interval-count": MetricValue(
            scalar_kind="integer", value=phase.interval_count, unit="count"
        ),
        "invalid-association-count": MetricValue(
            scalar_kind="integer", value=phase.invalid_association_count, unit="count"
        ),
        "scene-support-duration": MetricValue(
            scalar_kind="integer", value=phase.scene_support_duration_ns, unit="ns"
        ),
    }


def _trace(phase: _PhaseDwell, diagnostics: tuple[DomainErrorData, ...]) -> ComputationTrace:
    return ComputationTrace(
        sample_count=phase.interval_count,
        source_start_t_ns=phase.source_start_t_ns,
        source_end_t_ns=phase.source_end_t_ns,
        analysis_start_t_ns=phase.phase.window.start_t_ns,
        analysis_end_t_ns=phase.phase.window.end_t_ns,
        grid_id=None,
        window_ids=(phase.phase.window.window_id,),
        interpolation_method="native-gaze-left-hold-v1",
        matching_method="first-person-gaze-aoi-intersection-v1",
        diagnostics=diagnostics,
    )


def _breakdown(phase: _PhaseDwell) -> AnchorBreakdownMeasurement:
    diagnostics = () if phase.reason is None else (_diagnostic(phase),)
    no_gaze = phase.status is AnchorCalculationStatusV2.COMPUTED and phase.total_dwell_ns == 0
    primary = (
        MetricValue(
            scalar_kind="float",
            value=float(100.0 * phase.weighted_dwell_ns / phase.total_dwell_ns),
            unit="percent",
        )
        if phase.status is AnchorCalculationStatusV2.COMPUTED and phase.total_dwell_ns > 0
        else None
    )
    override = (
        ClassificationOverride(
            code="no_gaze_dwell",
            details={"phase_id": phase.phase.phase_id},
        )
        if no_gaze
        else None
    )
    return AnchorBreakdownMeasurement(
        breakdown_id=phase.phase.phase_id,
        calculation_status=phase.status,
        primary_value=primary,
        primary_value_reason="no_gaze_dwell" if no_gaze else None,
        raw_metrics=_raw_metrics(phase),
        classification_override_candidate=override,
        trace=_trace(phase, diagnostics),
        diagnostics=diagnostics,
    )


def _phase_dwell(
    context: AnchorPluginContext,
    phase: _BoundPhase,
    intervals: pl.DataFrame,
    aois: tuple[AoiDefinition, ...],
    *,
    streams_present: bool,
) -> _PhaseDwell:
    scene_support = _scene_support_duration(context, phase) if streams_present else 0
    role_ids = tuple(sorted({aoi.role for aoi in aois}))
    empty_roles = tuple(_RoleDwell(role_id, 0, 0.0) for role_id in role_ids)
    if not streams_present or scene_support == 0:
        return _PhaseDwell(
            phase=phase,
            status=AnchorCalculationStatusV2.MISSING_INPUT,
            reason="required-stream-absent" if not streams_present else "no-scene-support",
            role_dwells=empty_roles,
            total_dwell_ns=0,
            weighted_dwell_ns=0.0,
            interval_count=0,
            invalid_association_count=0,
            source_start_t_ns=None,
            source_end_t_ns=None,
            scene_support_duration_ns=scene_support,
        )

    aoi_by_id = {aoi.aoi_id: aoi for aoi in aois}
    selected = intervals.filter(
        pl.col("aoi_id").is_in(tuple(aoi_by_id))
        & (pl.col("start_t_ns") < phase.window.end_t_ns)
        & (pl.col("end_t_ns") > phase.window.start_t_ns)
    )
    if not selected.is_empty():
        for row in selected.iter_rows(named=True):
            aoi = aoi_by_id[cast(str, row["aoi_id"])]
            if row["role_id"] != aoi.role:
                raise ValueError("H1 gaze-AOI dependency role disagrees with AOI semantics")
        positive = selected.filter(pl.col("end_t_ns") > pl.col("start_t_ns"))
        previous_end: int | None = None
        for start, end in positive.select("start_t_ns", "end_t_ns").iter_rows():
            if previous_end is not None and start < previous_end:
                raise ValueError("H1 selected taxonomy intervals must not overlap")
            previous_end = end

    dwell_by_role = {role_id: 0 for role_id in role_ids}
    weighted_by_role = {role_id: 0.0 for role_id in role_ids}
    interval_count = 0
    invalid_count = 0
    starts: list[int] = []
    ends: list[int] = []
    for row in selected.iter_rows(named=True):
        start = max(cast(int, row["start_t_ns"]), phase.window.start_t_ns)
        end = min(cast(int, row["end_t_ns"]), phase.window.end_t_ns)
        duration = max(0, end - start)
        if duration == 0:
            continue
        aoi = aoi_by_id[cast(str, row["aoi_id"])]
        dwell_by_role[aoi.role] += duration
        weighted_by_role[aoi.role] += duration * aoi.role_weight
        interval_count += 1
        invalid_count += int(row["association_valid"] is False)
        starts.append(start)
        ends.append(end)
    role_dwells = tuple(
        _RoleDwell(role_id, dwell_by_role[role_id], float(weighted_by_role[role_id]))
        for role_id in role_ids
    )
    total = sum(item.dwell_ns for item in role_dwells)
    weighted = math.fsum(item.weighted_dwell_ns for item in role_dwells)
    return _PhaseDwell(
        phase=phase,
        status=AnchorCalculationStatusV2.COMPUTED,
        reason="no-gaze-dwell" if total == 0 else None,
        role_dwells=role_dwells,
        total_dwell_ns=total,
        weighted_dwell_ns=weighted,
        interval_count=interval_count,
        invalid_association_count=invalid_count,
        source_start_t_ns=min(starts) if starts else None,
        source_end_t_ns=max(ends) if ends else None,
        scene_support_duration_ns=scene_support,
    )


def _artifact_payload(
    definition: AnchorPluginDefinition, phases: tuple[_PhaseDwell, ...]
) -> TabularArtifactPayload | None:
    computed = tuple(
        phase for phase in phases if phase.status is AnchorCalculationStatusV2.COMPUTED
    )
    if not computed:
        return None
    rows = tuple(
        {
            "phase_id": phase.phase.phase_id,
            "role_id": role.role_id,
            "dwell_ns": role.dwell_ns,
            "weighted_dwell_ns": role.weighted_dwell_ns,
            "total_dwell_ns": phase.total_dwell_ns,
        }
        for phase in computed
        for role in phase.role_dwells
    )
    recipe = definition.artifact_recipes[0]
    frame = pl.DataFrame(
        rows,
        schema={
            "phase_id": pl.String,
            "role_id": pl.String,
            "dwell_ns": pl.Int64,
            "weighted_dwell_ns": pl.Float64,
            "total_dwell_ns": pl.Int64,
        },
    ).sort(["phase_id", "role_id"], maintain_order=True)
    return TabularArtifactPayload(
        schema_id=recipe.schema_id,
        schema_descriptor=recipe.schema_descriptor,
        frame=frame,
        order_keys=("phase_id", "role_id"),
        artifact_kind=recipe.kind,
        grid_hash=None,
        start_t_ns=min(phase.phase.window.start_t_ns for phase in computed),
        end_t_ns=max(phase.phase.window.end_t_ns for phase in computed),
    )


class H1AoiDwellPlugin:
    def __init__(self) -> None:
        self._definition = _definition()

    def definition(self) -> AnchorPluginDefinition:
        return self._definition

    def compute(
        self,
        context: AnchorPluginContext,
        parameters: Mapping[str, JsonValue],
        temporal_recipe: Mapping[str, JsonValue],
        dependencies: ResolvedDependencies,
        artifacts: AnchorArtifactEmitter,
    ) -> AnchorMeasurement:
        if not isinstance(parameters, Mapping) or parameters:
            raise ValueError("H1 v0.1 requires its exact empty parameter profile")
        phases = _bound_phases(context, temporal_recipe)
        aois = _selected_aois(context, temporal_recipe)
        intervals = _interval_frame(dependencies)
        i_view = context.streams.get("I")
        g_view = context.streams.get("G")
        streams_present = (
            i_view is not None
            and "frame_index" in i_view.tables
            and g_view is not None
            and "gaze_samples" in g_view.tables
        )
        phase_dwells = tuple(
            _phase_dwell(
                context,
                phase,
                intervals,
                aois,
                streams_present=streams_present,
            )
            for phase in phases
        )
        breakdowns = tuple(_breakdown(phase) for phase in phase_dwells)
        noncomputed = tuple(
            phase.status
            for phase in phase_dwells
            if phase.status is not AnchorCalculationStatusV2.COMPUTED
        )
        if not phases:
            session_status = AnchorCalculationStatusV2.NOT_COMPUTABLE
        elif noncomputed:
            session_status = max(noncomputed, key=_STATUS_PRIORITY.__getitem__)
        else:
            session_status = AnchorCalculationStatusV2.COMPUTED

        total = sum(phase.total_dwell_ns for phase in phase_dwells)
        weighted = math.fsum(phase.weighted_dwell_ns for phase in phase_dwells)
        no_gaze = session_status is AnchorCalculationStatusV2.COMPUTED and total == 0
        primary = (
            MetricValue(
                scalar_kind="float",
                value=float(100.0 * weighted / total),
                unit="percent",
            )
            if session_status is AnchorCalculationStatusV2.COMPUTED and total > 0
            else None
        )
        override = (
            ClassificationOverride(
                code="no_gaze_dwell",
                details={"phase_ids": [phase.phase_id for phase in phases]},
            )
            if no_gaze
            else None
        )
        diagnostics = tuple(
            diagnostic for breakdown in breakdowns for diagnostic in breakdown.diagnostics
        )
        payload = _artifact_payload(self._definition, phase_dwells)
        derived_artifacts = (
            () if payload is None else (artifacts.stage_table("phase-dwell", payload),)
        )
        windows = tuple(phase.window for phase in phases)
        source_starts = tuple(
            phase.source_start_t_ns for phase in phase_dwells if phase.source_start_t_ns is not None
        )
        source_ends = tuple(
            phase.source_end_t_ns for phase in phase_dwells if phase.source_end_t_ns is not None
        )
        return AnchorMeasurement(
            anchor_id="H1",
            calculation_status=session_status,
            primary_value=primary,
            primary_value_reason="no_gaze_dwell" if no_gaze else None,
            raw_metrics={
                "total-gaze-dwell": MetricValue(scalar_kind="integer", value=total, unit="ns"),
                "weighted-gaze-dwell": MetricValue(
                    scalar_kind="float", value=float(weighted), unit="ns"
                ),
                "gaze-interval-count": MetricValue(
                    scalar_kind="integer",
                    value=sum(phase.interval_count for phase in phase_dwells),
                    unit="count",
                ),
                "invalid-association-count": MetricValue(
                    scalar_kind="integer",
                    value=sum(phase.invalid_association_count for phase in phase_dwells),
                    unit="count",
                ),
                "phase-count": MetricValue(scalar_kind="integer", value=len(phases), unit="count"),
            },
            phase_results=breakdowns,
            event_results=(),
            classification_override_candidate=override,
            source_windows=windows,
            derived_artifacts=derived_artifacts,
            trace=ComputationTrace(
                sample_count=sum(phase.interval_count for phase in phase_dwells),
                source_start_t_ns=min(source_starts) if source_starts else None,
                source_end_t_ns=max(source_ends) if source_ends else None,
                analysis_start_t_ns=min((window.start_t_ns for window in windows), default=None),
                analysis_end_t_ns=max((window.end_t_ns for window in windows), default=None),
                grid_id=None,
                window_ids=tuple(window.window_id for window in windows),
                interpolation_method="native-gaze-left-hold-v1",
                matching_method="first-person-gaze-aoi-intersection-v1",
                diagnostics=diagnostics,
            ),
            diagnostics=diagnostics,
        )


def create_plugin() -> H1AoiDwellPlugin:
    return H1AoiDwellPlugin()


__all__ = ["H1AoiDwellPlugin", "create_plugin"]
