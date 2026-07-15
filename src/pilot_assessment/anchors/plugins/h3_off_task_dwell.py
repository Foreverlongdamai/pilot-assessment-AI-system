"""H3 Off-task Dwell production plugin."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

import polars as pl
from pydantic import JsonValue

from pilot_assessment.anchors.catalog import load_packaged_catalog
from pilot_assessment.anchors.plugins.h1_aoi_dwell import (
    _STATUS_PRIORITY,
    _bound_phases,
    _BoundPhase,
    _interval_frame,
    _scene_support_duration,
    _selected_aois,
)
from pilot_assessment.anchors.protocols import (
    AnchorArtifactEmitter,
    AnchorPluginContext,
    ResolvedDependencies,
    TabularArtifactPayload,
)
from pilot_assessment.contracts.anchor_execution import AnchorPluginDefinition, AoiDefinition
from pilot_assessment.contracts.anchor_v2 import (
    AnchorBreakdownMeasurement,
    AnchorCalculationStatusV2,
    AnchorMeasurement,
    ClassificationOverride,
    ComputationTrace,
    MetricValue,
)
from pilot_assessment.contracts.errors import DomainErrorData, ErrorSeverity


@dataclass(frozen=True, slots=True)
class _RoleDwell:
    role_id: str
    off_task: bool
    dwell_ns: int


@dataclass(frozen=True, slots=True)
class _PhaseDwell:
    phase: _BoundPhase
    status: AnchorCalculationStatusV2
    reason: str | None
    role_dwells: tuple[_RoleDwell, ...]
    total_dwell_ns: int
    off_task_dwell_ns: int
    interval_count: int
    invalid_association_count: int
    source_start_t_ns: int | None
    source_end_t_ns: int | None
    scene_support_duration_ns: int


def _definition() -> AnchorPluginDefinition:
    catalog_entry = next(
        entry for entry in load_packaged_catalog().entries if entry.anchor_id == "H3"
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


def _role_contract(aois: tuple[AoiDefinition, ...]) -> dict[str, bool]:
    role_flags: dict[str, bool] = {}
    for aoi in aois:
        existing = role_flags.setdefault(aoi.role, aoi.off_task)
        if existing is not aoi.off_task:
            raise ValueError("H3 requires one stable off_task flag per AOI role")
    return role_flags


def _diagnostic(phase: _PhaseDwell) -> DomainErrorData:
    if phase.status is AnchorCalculationStatusV2.MISSING_INPUT:
        message = f"H3 phase {phase.phase.phase_id} lacks an observed I/G assessment opportunity."
        path = "streams.I.frame_index"
        remediation = "Provide aligned I and G streams with scene support in the bound phase."
    else:
        message = f"H3 phase {phase.phase.phase_id} contains no nonzero gaze dwell."
        path = "dependencies.gaze-aoi-intervals"
        remediation = (
            "No filtering was applied; inspect the gaze interval trace and simulator export."
        )
    return DomainErrorData(
        error_code=f"anchor.h3.{phase.reason or 'unknown'}",
        severity=ErrorSeverity.WARNING,
        recoverable=True,
        message=message,
        field_or_path=path,
        node_or_anchor_id="H3",
        remediation=remediation,
        diagnostics={
            "phase_id": phase.phase.phase_id,
            "reason": phase.reason or "unknown",
            "scene_support_duration_ns": phase.scene_support_duration_ns,
            "total_gaze_dwell_ns": phase.total_dwell_ns,
            "off_task_gaze_dwell_ns": phase.off_task_dwell_ns,
        },
    )


def _raw_metrics(phase: _PhaseDwell) -> dict[str, MetricValue]:
    return {
        "total-gaze-dwell": MetricValue(
            scalar_kind="integer", value=phase.total_dwell_ns, unit="ns"
        ),
        "off-task-gaze-dwell": MetricValue(
            scalar_kind="integer", value=phase.off_task_dwell_ns, unit="ns"
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
            value=float(100.0 * phase.off_task_dwell_ns / phase.total_dwell_ns),
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
    role_flags = _role_contract(aois)
    empty_roles = tuple(
        _RoleDwell(role_id, role_flags[role_id], 0) for role_id in sorted(role_flags)
    )
    if not streams_present or scene_support == 0:
        return _PhaseDwell(
            phase=phase,
            status=AnchorCalculationStatusV2.MISSING_INPUT,
            reason="required-stream-absent" if not streams_present else "no-scene-support",
            role_dwells=empty_roles,
            total_dwell_ns=0,
            off_task_dwell_ns=0,
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
                raise ValueError("H3 gaze-AOI dependency role disagrees with AOI semantics")
        positive = selected.filter(pl.col("end_t_ns") > pl.col("start_t_ns"))
        previous_end: int | None = None
        for start, end in positive.select("start_t_ns", "end_t_ns").iter_rows():
            if previous_end is not None and start < previous_end:
                raise ValueError("H3 selected taxonomy intervals must not overlap")
            previous_end = end

    dwell_by_role = {role_id: 0 for role_id in role_flags}
    off_task_dwell = 0
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
        if aoi.off_task:
            off_task_dwell += duration
        interval_count += 1
        invalid_count += int(row["association_valid"] is False)
        starts.append(start)
        ends.append(end)

    role_dwells = tuple(
        _RoleDwell(role_id, role_flags[role_id], dwell_by_role[role_id])
        for role_id in sorted(role_flags)
    )
    total = sum(item.dwell_ns for item in role_dwells)
    return _PhaseDwell(
        phase=phase,
        status=AnchorCalculationStatusV2.COMPUTED,
        reason="no-gaze-dwell" if total == 0 else None,
        role_dwells=role_dwells,
        total_dwell_ns=total,
        off_task_dwell_ns=off_task_dwell,
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
            "off_task": role.off_task,
            "dwell_ns": role.dwell_ns,
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
            "off_task": pl.Boolean,
            "dwell_ns": pl.Int64,
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


class H3OffTaskDwellPlugin:
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
            raise ValueError("H3 v0.1 requires its exact empty parameter profile")
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
        off_task = sum(phase.off_task_dwell_ns for phase in phase_dwells)
        no_gaze = session_status is AnchorCalculationStatusV2.COMPUTED and total == 0
        primary = (
            MetricValue(
                scalar_kind="float",
                value=float(100.0 * off_task / total),
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
            () if payload is None else (artifacts.stage_table("phase-off-task-dwell", payload),)
        )
        windows = tuple(phase.window for phase in phases)
        source_starts = tuple(
            phase.source_start_t_ns for phase in phase_dwells if phase.source_start_t_ns is not None
        )
        source_ends = tuple(
            phase.source_end_t_ns for phase in phase_dwells if phase.source_end_t_ns is not None
        )
        return AnchorMeasurement(
            anchor_id="H3",
            calculation_status=session_status,
            primary_value=primary,
            primary_value_reason="no_gaze_dwell" if no_gaze else None,
            raw_metrics={
                "total-gaze-dwell": MetricValue(scalar_kind="integer", value=total, unit="ns"),
                "off-task-gaze-dwell": MetricValue(
                    scalar_kind="integer", value=off_task, unit="ns"
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


def create_plugin() -> H3OffTaskDwellPlugin:
    return H3OffTaskDwellPlugin()


__all__ = ["H3OffTaskDwellPlugin", "create_plugin"]
