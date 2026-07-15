"""O3 Terminal Capture Quality production plugin."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeVar

import polars as pl
from pydantic import JsonValue

from pilot_assessment.anchors.catalog import load_packaged_catalog
from pilot_assessment.anchors.primitives import envelopes
from pilot_assessment.anchors.primitives.envelopes import O3KernelResult, O3KernelStatus
from pilot_assessment.anchors.protocols import (
    AnchorArtifactEmitter,
    AnchorPluginContext,
    ResolvedDependencies,
    TabularArtifactPayload,
)
from pilot_assessment.anchors.temporal import build_semantic_windows_v1
from pilot_assessment.contracts.anchor_execution import (
    AnchorPluginDefinition,
    EnvelopeDefinition,
    ResolvedInputTableContract,
    SemanticEvent,
    TaskTargetDefinition,
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

_STATUS_PRIORITY = {
    AnchorCalculationStatusV2.NOT_COMPUTABLE: 0,
    AnchorCalculationStatusV2.MISSING_INPUT: 1,
    AnchorCalculationStatusV2.DEPENDENCY_MISSING: 2,
    AnchorCalculationStatusV2.EXTRACTOR_ERROR: 3,
}
_SemanticT = TypeVar("_SemanticT", SemanticEvent, TaskTargetDefinition, EnvelopeDefinition)


def _definition() -> AnchorPluginDefinition:
    catalog_entry = next(
        entry for entry in load_packaged_catalog().entries if entry.anchor_id == "O3"
    )
    streams = tuple(
        value.removeprefix("stream.")
        for value in catalog_entry.required_inputs
        if value.startswith("stream.")
    )
    semantic_paths = tuple(
        sorted(value for value in catalog_entry.required_inputs if value.startswith("semantic."))
    )
    context_paths = tuple(
        sorted(value for value in catalog_entry.required_inputs if value.startswith("context."))
    )
    reference_ids = tuple(
        sorted(
            value.removeprefix("reference.")
            for value in catalog_entry.required_inputs
            if value.startswith("reference.")
        )
    )
    return AnchorPluginDefinition(
        anchor_id=catalog_entry.anchor_id,
        definition_version=catalog_entry.definition_version,
        plugin_id=catalog_entry.plugin_id,
        plugin_version=catalog_entry.plugin_version,
        api_version="0.1.0",
        required_streams=streams,
        required_context_paths=context_paths,
        required_semantic_paths=semantic_paths,
        required_reference_ids=reference_ids,
        dependencies=catalog_entry.dependencies,
        parameter_schema_id=catalog_entry.parameter_schema_id,
        measurement_schema_id="anchor-measurement-0.1.0",
        artifact_recipes=catalog_entry.artifact_recipes,
    )


def _typed_sequence(
    values: object,
    model_type: type[_SemanticT],
    label: str,
) -> tuple[_SemanticT, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError(f"{label} must be an ordered array")
    return tuple(model_type.model_validate(item) for item in values)


def _input_contracts(
    temporal_recipe: Mapping[str, JsonValue],
) -> tuple[ResolvedInputTableContract, ...]:
    raw = temporal_recipe.get("input_table_contracts")
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise ValueError("temporal_recipe.input_table_contracts must be an ordered array")
    contracts = tuple(ResolvedInputTableContract.model_validate(item) for item in raw)
    if not contracts:
        raise ValueError("O3 requires at least one input table contract")
    return contracts


def _missing_result(
    status: O3KernelStatus,
    reason: str,
    observation_duration_ns: int,
) -> O3KernelResult:
    return O3KernelResult(
        status=status,
        reason=reason,
        overshoot_ft=None,
        settling_time_s=None,
        observed_wait_s=None,
        capture_missed=False,
        capture_hold_start_t_ns=None,
        capture_hold_end_t_ns=None,
        observation_duration_ns=observation_duration_ns,
        observed_support_duration_ns=0,
        sample_count=0,
        source_start_t_ns=None,
        source_end_t_ns=None,
        gap_count=0,
        max_gap_ns=None,
        trace_rows=(),
    )


def _diagnostic(result: O3KernelResult, event_id: str) -> DomainErrorData:
    assert result.reason is not None
    missing = result.status == "missing_input"
    return DomainErrorData(
        error_code=f"anchor.o3.{result.reason}",
        severity=ErrorSeverity.WARNING,
        recoverable=True,
        message=f"O3 event {event_id} could not produce capture evidence: {result.reason}",
        field_or_path=(
            "streams.X.samples" if missing else "execution_plan.entries.O3.temporal_recipe"
        ),
        node_or_anchor_id="O3",
        remediation=(
            "Provide native X rows in the declared event span."
            if missing
            else "Bind an event target, arrival axis, hover envelope, frame, and position fields."
        ),
        diagnostics={
            "event_id": event_id,
            "reason": result.reason,
            "sample_count": result.sample_count,
            "observed_support_duration_ns": result.observed_support_duration_ns,
        },
    )


def _raw_metrics(result: O3KernelResult) -> dict[str, MetricValue]:
    metrics = {
        "observation-duration": MetricValue(
            scalar_kind="integer", value=result.observation_duration_ns, unit="ns"
        ),
        "observed-support-duration": MetricValue(
            scalar_kind="integer", value=result.observed_support_duration_ns, unit="ns"
        ),
        "sample-count": MetricValue(scalar_kind="integer", value=result.sample_count, unit="count"),
        "gap-count": MetricValue(scalar_kind="integer", value=result.gap_count, unit="count"),
    }
    if result.overshoot_ft is not None:
        metrics["overshoot"] = MetricValue(
            scalar_kind="float", value=result.overshoot_ft, unit="ft"
        )
    if result.settling_time_s is not None:
        metrics["settling_time"] = MetricValue(
            scalar_kind="float", value=result.settling_time_s, unit="s"
        )
    if result.observed_wait_s is not None:
        metrics["observed_wait"] = MetricValue(
            scalar_kind="float", value=result.observed_wait_s, unit="s"
        )
    if result.capture_hold_start_t_ns is not None and result.capture_hold_end_t_ns is not None:
        metrics.update(
            {
                "capture-hold-start-t-ns": MetricValue(
                    scalar_kind="integer", value=result.capture_hold_start_t_ns, unit="ns"
                ),
                "capture-hold-end-t-ns": MetricValue(
                    scalar_kind="integer", value=result.capture_hold_end_t_ns, unit="ns"
                ),
            }
        )
    return metrics


def _override(result: O3KernelResult, event_id: str) -> ClassificationOverride | None:
    if not result.capture_missed:
        return None
    return ClassificationOverride(
        code="capture_missed",
        details={
            "event_id": event_id,
            "observation_duration_ns": result.observation_duration_ns,
        },
    )


def _kernel_trace(
    result: O3KernelResult,
    window: SourceWindowV2,
    diagnostics: tuple[DomainErrorData, ...],
) -> ComputationTrace:
    return ComputationTrace(
        sample_count=result.sample_count,
        source_start_t_ns=result.source_start_t_ns,
        source_end_t_ns=result.source_end_t_ns,
        analysis_start_t_ns=window.start_t_ns,
        analysis_end_t_ns=window.end_t_ns,
        grid_id=None,
        window_ids=(window.window_id,),
        interpolation_method="native-left-hold-v1",
        matching_method="arrival-axis-target-envelope-conjunction-v1",
        diagnostics=diagnostics,
    )


def _breakdown(result: O3KernelResult, window: SourceWindowV2) -> AnchorBreakdownMeasurement:
    status = AnchorCalculationStatusV2(result.status)
    event_id = window.event_id or window.window_id
    diagnostics = () if result.status == "computed" else (_diagnostic(result, event_id),)
    return AnchorBreakdownMeasurement(
        breakdown_id=event_id,
        calculation_status=status,
        primary_value=None,
        primary_value_reason="composite_conjunction" if result.status == "computed" else None,
        raw_metrics=_raw_metrics(result),
        classification_override_candidate=_override(result, event_id),
        trace=_kernel_trace(result, window, diagnostics),
        diagnostics=diagnostics,
    )


def _artifact_payload(
    definition: AnchorPluginDefinition,
    rows: tuple[envelopes.O3CaptureTraceRow, ...],
) -> TabularArtifactPayload | None:
    if not rows:
        return None
    recipe = definition.artifact_recipes[0]
    frame = pl.DataFrame(
        {
            "event_id": pl.Series("event_id", [row.event_id for row in rows], dtype=pl.String),
            "t_ns": pl.Series("t_ns", [row.t_ns for row in rows], dtype=pl.Int64),
            "source_row_id": pl.Series(
                "source_row_id", [row.source_row_id for row in rows], dtype=pl.Int64
            ),
            "overshoot": pl.Series(
                "overshoot", [row.overshoot_ft for row in rows], dtype=pl.Float64
            ),
            "inside_hover": pl.Series(
                "inside_hover", [row.inside_hover for row in rows], dtype=pl.Boolean
            ),
        }
    ).sort(["event_id", "t_ns", "source_row_id"], maintain_order=True)
    return TabularArtifactPayload(
        schema_id=recipe.schema_id,
        schema_descriptor=recipe.schema_descriptor,
        frame=frame,
        order_keys=("event_id", "t_ns", "source_row_id"),
        artifact_kind=recipe.kind,
        grid_hash=None,
        start_t_ns=min(row.t_ns for row in rows),
        end_t_ns=max(row.t_ns for row in rows),
    )


class O3TerminalCaptureQualityPlugin:
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
        del dependencies
        if not isinstance(parameters, Mapping) or set(parameters) != {"capture_hold_ns"}:
            raise ValueError("O3 v0.1 parameters require exactly capture_hold_ns")
        events = _typed_sequence(
            context.semantic_scope.values.get("semantic.events"),
            SemanticEvent,
            "semantic.events",
        )
        targets = _typed_sequence(
            context.semantic_scope.values.get("semantic.targets"),
            TaskTargetDefinition,
            "semantic.targets",
        )
        envelope_values = _typed_sequence(
            context.semantic_scope.values.get("semantic.envelopes"),
            EnvelopeDefinition,
            "semantic.envelopes",
        )
        event_by_id = {event.event_id: event for event in events}
        target_by_id = {target.target_id: target for target in targets}
        envelope_by_id = {envelope.envelope_id: envelope for envelope in envelope_values}
        windows = build_semantic_windows_v1(context.semantic_scope, temporal_recipe)
        contracts = _input_contracts(temporal_recipe)
        table_role = temporal_recipe.get("table_role")
        if type(table_role) is not str:
            raise ValueError("temporal_recipe.table_role must be a string")
        x_view = context.streams.get("X")
        x_table = None if x_view is None else x_view.tables.get(table_role)

        kernel_results: list[O3KernelResult] = []
        for window in windows:
            if window.event_id is None or window.event_id not in event_by_id:
                raise ValueError("O3 semantic window is not bound to a declared event")
            event = event_by_id[window.event_id]
            duration = window.end_t_ns - window.start_t_ns
            if x_table is None:
                kernel_results.append(
                    _missing_result("missing_input", "no-temporal-support", duration)
                )
                continue
            if event.target_id is None:
                kernel_results.append(
                    _missing_result("not_computable", "event-target-missing", duration)
                )
                continue
            if event.envelope_id is None:
                kernel_results.append(
                    _missing_result("not_computable", "event-envelope-missing", duration)
                )
                continue
            target = target_by_id.get(event.target_id)
            envelope = envelope_by_id.get(event.envelope_id)
            if target is None:
                kernel_results.append(
                    _missing_result("not_computable", "event-target-missing", duration)
                )
                continue
            if envelope is None:
                kernel_results.append(
                    _missing_result("not_computable", "event-envelope-missing", duration)
                )
                continue
            kernel_results.append(
                envelopes.compute_o3_kernel(
                    x_table=x_table,
                    event=event,
                    target=target,
                    envelope=envelope,
                    scope_start_t_ns=window.start_t_ns,
                    scope_end_t_ns=window.end_t_ns,
                    input_contracts=contracts,
                    parameters=parameters,
                    temporal_recipe=temporal_recipe,
                )
            )

        results = tuple(kernel_results)
        breakdowns = tuple(
            _breakdown(result, window) for result, window in zip(results, windows, strict=True)
        )
        computed = tuple(result for result in results if result.status == "computed")
        noncomputed = tuple(
            AnchorCalculationStatusV2(result.status)
            for result in results
            if result.status != "computed"
        )
        if not windows:
            session_status = AnchorCalculationStatusV2.NOT_COMPUTABLE
        elif noncomputed:
            session_status = max(noncomputed, key=_STATUS_PRIORITY.__getitem__)
        else:
            session_status = AnchorCalculationStatusV2.COMPUTED

        raw_metrics: dict[str, MetricValue] = {
            "event-count": MetricValue(scalar_kind="integer", value=len(windows), unit="count"),
            "computed-event-count": MetricValue(
                scalar_kind="integer", value=len(computed), unit="count"
            ),
        }
        session_override = None
        primary_reason = None
        if session_status is AnchorCalculationStatusV2.COMPUTED:
            primary_reason = "composite_conjunction"
            raw_metrics["overshoot"] = MetricValue(
                scalar_kind="float",
                value=max(
                    result.overshoot_ft for result in computed if result.overshoot_ft is not None
                ),
                unit="ft",
            )
            missed = tuple(result for result in computed if result.capture_missed)
            if missed:
                raw_metrics["observed_wait"] = MetricValue(
                    scalar_kind="float",
                    value=max(
                        result.observed_wait_s
                        for result in missed
                        if result.observed_wait_s is not None
                    ),
                    unit="s",
                )
                session_override = ClassificationOverride(
                    code="capture_missed",
                    details={
                        "missed_event_ids": [
                            window.event_id
                            for result, window in zip(results, windows, strict=True)
                            if result.capture_missed
                        ]
                    },
                )
            else:
                raw_metrics["settling_time"] = MetricValue(
                    scalar_kind="float",
                    value=max(
                        result.settling_time_s
                        for result in computed
                        if result.settling_time_s is not None
                    ),
                    unit="s",
                )

        all_rows = tuple(
            sorted(
                (row for result in computed for row in result.trace_rows),
                key=lambda row: (row.event_id, row.t_ns, row.source_row_id),
            )
        )
        payload = _artifact_payload(self._definition, all_rows)
        derived_artifacts = (
            () if payload is None else (artifacts.stage_table("capture-trace", payload),)
        )
        diagnostics = tuple(
            diagnostic for breakdown in breakdowns for diagnostic in breakdown.diagnostics
        )
        source_starts = tuple(
            result.source_start_t_ns for result in results if result.source_start_t_ns is not None
        )
        source_ends = tuple(
            result.source_end_t_ns for result in results if result.source_end_t_ns is not None
        )
        trace = ComputationTrace(
            sample_count=sum(result.sample_count for result in results),
            source_start_t_ns=min(source_starts) if source_starts else None,
            source_end_t_ns=max(source_ends) if source_ends else None,
            analysis_start_t_ns=min((window.start_t_ns for window in windows), default=None),
            analysis_end_t_ns=max((window.end_t_ns for window in windows), default=None),
            grid_id=None,
            window_ids=tuple(window.window_id for window in windows),
            interpolation_method="native-left-hold-v1",
            matching_method="arrival-axis-target-envelope-conjunction-v1",
            diagnostics=diagnostics,
        )
        return AnchorMeasurement(
            anchor_id="O3",
            calculation_status=session_status,
            primary_value=None,
            primary_value_reason=primary_reason,
            raw_metrics=raw_metrics,
            phase_results=(),
            event_results=breakdowns,
            classification_override_candidate=session_override,
            source_windows=windows,
            derived_artifacts=derived_artifacts,
            trace=trace,
            diagnostics=diagnostics,
        )


def create_plugin() -> O3TerminalCaptureQualityPlugin:
    return O3TerminalCaptureQualityPlugin()


__all__ = ["O3TerminalCaptureQualityPlugin", "create_plugin"]
