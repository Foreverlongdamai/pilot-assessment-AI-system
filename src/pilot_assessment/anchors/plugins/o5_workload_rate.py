"""O5 Workload Rate production plugin."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

import polars as pl
from pydantic import JsonValue

from pilot_assessment.anchors.catalog import load_packaged_catalog
from pilot_assessment.anchors.primitives.movement import (
    MovementKernelResult,
    O5KernelResult,
    compute_o5_kernel,
    movement_kernel_from_table,
)
from pilot_assessment.anchors.protocols import (
    AnchorArtifactEmitter,
    AnchorPluginContext,
    ReadOnlyTabularPayload,
    ResolvedDependencies,
    TabularArtifactPayload,
)
from pilot_assessment.contracts.anchor_execution import (
    AnchorPluginDefinition,
    ControlEffectMapping,
)
from pilot_assessment.contracts.anchor_v2 import (
    AnchorBreakdownMeasurement,
    AnchorCalculationStatusV2,
    AnchorMeasurement,
    ComputationTrace,
    MetricValue,
    SourceWindowV2,
)
from pilot_assessment.contracts.errors import DomainErrorData, ErrorSeverity

_NANOSECONDS_PER_SECOND = 1_000_000_000
_STATUS_PRIORITY = {
    AnchorCalculationStatusV2.NOT_COMPUTABLE: 0,
    AnchorCalculationStatusV2.MISSING_INPUT: 1,
    AnchorCalculationStatusV2.DEPENDENCY_MISSING: 2,
    AnchorCalculationStatusV2.EXTRACTOR_ERROR: 3,
}


def _definition() -> AnchorPluginDefinition:
    catalog_entry = next(
        entry for entry in load_packaged_catalog().entries if entry.anchor_id == "O5"
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


@dataclass(frozen=True, slots=True)
class _BoundPhase:
    phase_id: str
    window: SourceWindowV2


def _bound_phases(
    context: AnchorPluginContext, temporal_recipe: Mapping[str, JsonValue]
) -> tuple[_BoundPhase, ...]:
    if _strict_string(temporal_recipe.get("window_policy"), "window_policy") != (
        "bound-phase-windows-v1"
    ):
        raise ValueError("O5 requires window_policy=bound-phase-windows-v1")
    prefix = _strict_string(temporal_recipe.get("window_id_prefix"), "window_id_prefix")
    scope_ids = _strings(temporal_recipe.get("scope_ids"), "scope_ids")
    raw = temporal_recipe.get("phase_bindings")
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise ValueError("phase_bindings must be an ordered array")
    parsed: list[_BoundPhase] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping) or set(item) != {
            "phase_id",
            "start_t_ns",
            "end_t_ns",
            "include_session_terminal_point",
        }:
            raise ValueError("O5 phase bindings require the exact four-key contract")
        binding = cast(Mapping[str, object], item)
        phase_id = _strict_string(binding["phase_id"], f"phase_bindings[{index}].phase_id")
        start = _strict_int(binding["start_t_ns"], f"phase_bindings[{index}].start_t_ns")
        end = _strict_int(binding["end_t_ns"], f"phase_bindings[{index}].end_t_ns", minimum=1)
        terminal = binding["include_session_terminal_point"]
        if type(terminal) is not bool or end <= start:
            raise ValueError("O5 phase bindings require a positive span and strict terminal flag")
        if start < context.session_window.start_t_ns or end > context.session_window.end_t_ns:
            raise ValueError("O5 phase binding lies outside the immutable session window")
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
        raise ValueError("O5 phase bindings must exactly match ordered scope_ids")
    if any(
        current.window.start_t_ns < previous.window.end_t_ns
        for previous, current in zip(parsed, parsed[1:], strict=False)
    ):
        raise ValueError("O5 phase bindings must not overlap")
    return tuple(parsed)


def _control_channels(
    context: AnchorPluginContext, temporal_recipe: Mapping[str, JsonValue]
) -> tuple[str, ...]:
    mapping_ids = _strings(
        temporal_recipe.get("control_mapping_ids"), "control_mapping_ids", canonical=True
    )
    raw = context.semantic_scope.values.get("semantic.control_mappings")
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise ValueError("semantic.control_mappings must be an ordered array")
    mappings = tuple(ControlEffectMapping.model_validate(item) for item in raw)
    by_id = {item.control_mapping_id: item for item in mappings}
    if len(by_id) != len(mappings) or any(mapping_id not in by_id for mapping_id in mapping_ids):
        raise ValueError("O5 control mapping projection is incomplete")
    selected = tuple(by_id[mapping_id] for mapping_id in mapping_ids)
    calibration_by_channel: dict[str, tuple[str, float, float, float]] = {}
    for mapping in selected:
        calibration = (mapping.control_unit, mapping.lower, mapping.trim, mapping.upper)
        previous = calibration_by_channel.setdefault(mapping.control_channel_id, calibration)
        if previous != calibration:
            raise ValueError("O5 selected mappings disagree on one channel calibration")
    channels = tuple(sorted(calibration_by_channel))
    if not channels:
        raise ValueError("O5 requires at least one configured active channel")
    return channels


def _diagnostic(
    *, phase_id: str, status: str, reason: str, bypass_count: int = 0
) -> DomainErrorData:
    if status == "computed":
        return DomainErrorData(
            error_code="anchor.o5.short-filter-bypass",
            severity=ErrorSeverity.WARNING,
            recoverable=True,
            message=f"O5 phase {phase_id} retained short movement segments without filtering.",
            field_or_path="dependencies.movement-events",
            node_or_anchor_id="O5",
            remediation="No remediation is required; the declared short-segment rule was applied.",
            diagnostics={"phase_id": phase_id, "short_filter_bypass_count": bypass_count},
        )
    return DomainErrorData(
        error_code=f"anchor.o5.{reason}",
        severity=ErrorSeverity.WARNING,
        recoverable=True,
        message=f"O5 phase {phase_id} could not produce workload-rate evidence: {reason}",
        field_or_path="dependencies.movement-events",
        node_or_anchor_id="O5",
        remediation="Provide temporal U support for every configured phase and control channel.",
        diagnostics={"phase_id": phase_id, "reason": reason},
    )


def _raw_metrics(result: O5KernelResult) -> dict[str, MetricValue]:
    if result.status != "computed":
        return {}
    assert result.workload_rate_hz is not None
    return {
        "workload-rate": MetricValue(scalar_kind="float", value=result.workload_rate_hz, unit="Hz"),
        "movement-count": MetricValue(
            scalar_kind="integer", value=result.total_movement_count, unit="count"
        ),
        "channel-count": MetricValue(
            scalar_kind="integer", value=len(result.channel_rates), unit="count"
        ),
        "observed-support-duration": MetricValue(
            scalar_kind="integer",
            value=min(item.observed_support_duration_ns for item in result.channel_rates),
            unit="ns",
        ),
    }


def _breakdown(
    phase: _BoundPhase,
    movement: MovementKernelResult,
    result: O5KernelResult,
) -> AnchorBreakdownMeasurement:
    bypass_count = sum(item.short_filter_bypass_count for item in movement.channels)
    diagnostics: tuple[DomainErrorData, ...]
    if result.status != "computed":
        diagnostics = (
            _diagnostic(
                phase_id=phase.phase_id,
                status=result.status,
                reason=result.reason or "unknown",
            ),
        )
    elif bypass_count:
        diagnostics = (
            _diagnostic(
                phase_id=phase.phase_id,
                status="computed",
                reason="short-filter-bypass",
                bypass_count=bypass_count,
            ),
        )
    else:
        diagnostics = ()
    return AnchorBreakdownMeasurement(
        breakdown_id=phase.phase_id,
        calculation_status=AnchorCalculationStatusV2(result.status),
        primary_value=(
            MetricValue(scalar_kind="float", value=result.workload_ratio, unit="ratio")
            if result.workload_ratio is not None
            else None
        ),
        primary_value_reason=None,
        raw_metrics=_raw_metrics(result),
        classification_override_candidate=None,
        trace=ComputationTrace(
            sample_count=movement.sample_count,
            source_start_t_ns=movement.source_start_t_ns,
            source_end_t_ns=movement.source_end_t_ns,
            analysis_start_t_ns=phase.window.start_t_ns,
            analysis_end_t_ns=phase.window.end_t_ns,
            grid_id="movement-grid-100hz-phase-start-v1",
            window_ids=(phase.window.window_id,),
            interpolation_method="same-segment-linear-v1",
            matching_method="movement-events-v1",
            diagnostics=diagnostics,
        ),
        diagnostics=diagnostics,
    )


def _movement_artifact(
    definition: AnchorPluginDefinition,
    frame: pl.DataFrame,
    phase_ids: tuple[str, ...],
    channel_ids: tuple[str, ...],
    windows: tuple[SourceWindowV2, ...],
) -> TabularArtifactPayload | None:
    selected = frame.filter(
        pl.col("phase_id").is_in(phase_ids)
        & pl.col("channel_id").is_in(channel_ids)
        & (pl.col("event_kind") == "movement")
    ).sort(["phase_id", "channel_id", "event_t_ns", "event_id"], maintain_order=True)
    if selected.is_empty():
        return None
    recipe = definition.artifact_recipes[0]
    return TabularArtifactPayload(
        schema_id=recipe.schema_id,
        schema_descriptor=recipe.schema_descriptor,
        frame=selected,
        order_keys=("phase_id", "channel_id", "event_t_ns", "event_id"),
        artifact_kind=recipe.kind,
        grid_hash=None,
        start_t_ns=min(window.start_t_ns for window in windows),
        end_t_ns=max(window.end_t_ns for window in windows),
    )


class O5WorkloadRatePlugin:
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
        if not isinstance(parameters, Mapping) or set(parameters) != {"w_min_hz"}:
            raise ValueError("O5 v0.1 parameters require exactly w_min_hz")
        w_min = parameters["w_min_hz"]
        if (
            isinstance(w_min, bool)
            or not isinstance(w_min, (int, float))
            or not math.isfinite(float(w_min))
            or float(w_min) <= 0.0
        ):
            raise ValueError("O5 w_min_hz must be finite and positive")
        phases = _bound_phases(context, temporal_recipe)
        channel_ids = _control_channels(context, temporal_recipe)
        dependency = dependencies.preprocessing.get("movement-events")
        if dependency is None or not isinstance(dependency.payload, ReadOnlyTabularPayload):
            raise ValueError("O5 requires its resolved movement-events table dependency")
        frame = dependency.payload.frame
        phase_kernels: list[MovementKernelResult] = []
        phase_results: list[O5KernelResult] = []
        for phase in phases:
            kernel = movement_kernel_from_table(
                frame, phase_ids=(phase.phase_id,), channel_ids=channel_ids
            )
            phase_kernels.append(kernel)
            phase_results.append(compute_o5_kernel(kernel, channel_ids, float(w_min)))
        breakdowns = tuple(
            _breakdown(phase, kernel, result)
            for phase, kernel, result in zip(phases, phase_kernels, phase_results, strict=True)
        )
        noncomputed = tuple(
            AnchorCalculationStatusV2(result.status)
            for result in phase_results
            if result.status != "computed"
        )
        if not phases:
            session_status = AnchorCalculationStatusV2.NOT_COMPUTABLE
        elif noncomputed:
            session_status = max(noncomputed, key=_STATUS_PRIORITY.__getitem__)
        else:
            session_status = AnchorCalculationStatusV2.COMPUTED
        session_kernel: MovementKernelResult | None = None
        session_result: O5KernelResult | None = None
        if session_status is AnchorCalculationStatusV2.COMPUTED:
            session_kernel = movement_kernel_from_table(
                frame,
                phase_ids=tuple(phase.phase_id for phase in phases),
                channel_ids=channel_ids,
            )
            session_result = compute_o5_kernel(session_kernel, channel_ids, float(w_min))
        diagnostics = tuple(
            diagnostic for breakdown in breakdowns for diagnostic in breakdown.diagnostics
        )
        windows = tuple(phase.window for phase in phases)
        payload = (
            _movement_artifact(
                self._definition,
                frame,
                tuple(phase.phase_id for phase in phases),
                channel_ids,
                windows,
            )
            if session_status is AnchorCalculationStatusV2.COMPUTED
            else None
        )
        derived_artifacts = (
            () if payload is None else (artifacts.stage_table("movement-events", payload),)
        )
        primary = (
            MetricValue(
                scalar_kind="float",
                value=cast(float, session_result.workload_ratio),
                unit="ratio",
            )
            if session_result is not None
            else None
        )
        session_raw = _raw_metrics(session_result) if session_result is not None else {}
        return AnchorMeasurement(
            anchor_id="O5",
            calculation_status=session_status,
            primary_value=primary,
            primary_value_reason=None,
            raw_metrics=session_raw,
            phase_results=breakdowns,
            event_results=(),
            classification_override_candidate=None,
            source_windows=windows,
            derived_artifacts=derived_artifacts,
            trace=ComputationTrace(
                sample_count=0 if session_kernel is None else session_kernel.sample_count,
                source_start_t_ns=(
                    None if session_kernel is None else session_kernel.source_start_t_ns
                ),
                source_end_t_ns=None if session_kernel is None else session_kernel.source_end_t_ns,
                analysis_start_t_ns=min((window.start_t_ns for window in windows), default=None),
                analysis_end_t_ns=max((window.end_t_ns for window in windows), default=None),
                grid_id="movement-grid-100hz-phase-start-v1",
                window_ids=tuple(window.window_id for window in windows),
                interpolation_method="same-segment-linear-v1",
                matching_method="movement-events-v1",
                diagnostics=diagnostics,
            ),
            diagnostics=diagnostics,
        )


def create_plugin() -> O5WorkloadRatePlugin:
    return O5WorkloadRatePlugin()


__all__ = ["O5WorkloadRatePlugin", "create_plugin"]
