"""O1 Phase-state Precision production plugin."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeVar

import polars as pl
from pydantic import JsonValue

from pilot_assessment.anchors.catalog import load_packaged_catalog
from pilot_assessment.anchors.primitives import envelopes
from pilot_assessment.anchors.primitives.models import O1KernelResult
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
    SemanticPhase,
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

_STATUS_PRIORITY = {
    AnchorCalculationStatusV2.NOT_COMPUTABLE: 0,
    AnchorCalculationStatusV2.MISSING_INPUT: 1,
    AnchorCalculationStatusV2.DEPENDENCY_MISSING: 2,
    AnchorCalculationStatusV2.EXTRACTOR_ERROR: 3,
}
_SemanticModelT = TypeVar("_SemanticModelT", SemanticPhase, EnvelopeDefinition)


def _definition() -> AnchorPluginDefinition:
    catalog_entry = next(
        entry for entry in load_packaged_catalog().entries if entry.anchor_id == "O1"
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
    model_type: type[_SemanticModelT],
    label: str,
) -> tuple[_SemanticModelT, ...]:
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
        raise ValueError("O1 requires at least one input table contract")
    return contracts


def _diagnostic(result: O1KernelResult, phase_id: str) -> DomainErrorData:
    assert result.reason is not None
    missing = result.status == "missing_input"
    return DomainErrorData(
        error_code=f"anchor.o1.{result.reason}",
        severity=ErrorSeverity.WARNING,
        recoverable=True,
        message=f"O1 phase {phase_id} could not produce a numeric precision: {result.reason}",
        field_or_path=("streams.X.samples" if missing else "semantic.envelopes"),
        node_or_anchor_id="O1",
        remediation=(
            "Provide the declared phase X rows."
            if missing
            else "Correct the task-profile envelope or input contract."
        ),
        diagnostics={
            "phase_id": phase_id,
            "reason": result.reason,
            "sample_count": result.sample_count,
            "observed_support_duration_ns": result.observed_support_duration_ns,
        },
    )


def _kernel_trace(
    result: O1KernelResult,
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
        matching_method="direct-envelope-field-v1",
        diagnostics=diagnostics,
    )


def _raw_metrics(result: O1KernelResult) -> dict[str, MetricValue]:
    values = {
        "phase-duration": MetricValue(
            scalar_kind="integer", value=result.phase_duration_ns, unit="ns"
        ),
        "observed-support-duration": MetricValue(
            scalar_kind="integer", value=result.observed_support_duration_ns, unit="ns"
        ),
        "desired-joint-duration": MetricValue(
            scalar_kind="integer", value=result.desired_joint_duration_ns, unit="ns"
        ),
        "gap-count": MetricValue(scalar_kind="integer", value=result.gap_count, unit="count"),
    }
    for summary in result.axis_summaries:
        values[f"desired-duration-{summary.axis_id}"] = MetricValue(
            scalar_kind="integer", value=summary.desired_duration_ns, unit="ns"
        )
    return values


def _breakdown(
    result: O1KernelResult,
    window: SourceWindowV2,
) -> AnchorBreakdownMeasurement:
    status = AnchorCalculationStatusV2(result.status)
    diagnostics = (
        () if result.status == "computed" else (_diagnostic(result, window.phase_id or "unknown"),)
    )
    primary = (
        MetricValue(scalar_kind="float", value=result.precision_percent, unit="percent")
        if result.precision_percent is not None
        else None
    )
    return AnchorBreakdownMeasurement(
        breakdown_id=window.phase_id or window.window_id,
        calculation_status=status,
        primary_value=primary,
        primary_value_reason=None,
        raw_metrics=_raw_metrics(result),
        classification_override_candidate=None,
        trace=_kernel_trace(result, window, diagnostics),
        diagnostics=diagnostics,
    )


def _missing_kernel(phase_duration_ns: int, reason: str) -> O1KernelResult:
    return O1KernelResult(
        status="missing_input" if reason == "no-temporal-support" else "not_computable",
        reason=reason,
        precision_percent=None,
        phase_duration_ns=phase_duration_ns,
        observed_support_duration_ns=0,
        desired_joint_duration_ns=0,
        sample_count=0,
        source_start_t_ns=None,
        source_end_t_ns=None,
        gap_count=0,
        max_gap_ns=None,
        axis_summaries=(),
        mask_rows=(),
    )


def _artifact_payload(
    definition: AnchorPluginDefinition,
    results: tuple[O1KernelResult, ...],
    windows: tuple[SourceWindowV2, ...],
) -> TabularArtifactPayload | None:
    rows = tuple(row for result in results for row in result.mask_rows)
    if not rows:
        return None
    recipe = definition.artifact_recipes[0]
    frame = pl.DataFrame(
        {
            "phase_id": pl.Series("phase_id", [row.phase_id for row in rows], dtype=pl.String),
            "t_ns": pl.Series("t_ns", [row.t_ns for row in rows], dtype=pl.Int64),
            "source_row_id": pl.Series(
                "source_row_id", [row.source_row_id for row in rows], dtype=pl.Int64
            ),
            "axis_order": pl.Series("axis_order", [row.axis_order for row in rows], dtype=pl.Int64),
            "axis_id": pl.Series("axis_id", [row.axis_id for row in rows], dtype=pl.String),
            "inside": pl.Series("inside", [row.inside for row in rows], dtype=pl.Boolean),
        }
    ).sort(["phase_id", "t_ns", "source_row_id", "axis_order", "axis_id"])
    populated_windows = tuple(
        window for result, window in zip(results, windows, strict=True) if result.mask_rows
    )
    return TabularArtifactPayload(
        schema_id=recipe.schema_id,
        schema_descriptor=recipe.schema_descriptor,
        frame=frame,
        order_keys=("phase_id", "t_ns", "source_row_id", "axis_order", "axis_id"),
        artifact_kind=recipe.kind,
        grid_hash=None,
        start_t_ns=min(window.start_t_ns for window in populated_windows),
        end_t_ns=max(window.end_t_ns for window in populated_windows),
    )


class O1PhaseStatePrecisionPlugin:
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
        raw_phases = context.semantic_scope.values.get("semantic.phases")
        raw_envelopes = context.semantic_scope.values.get("semantic.envelopes")
        phases = _typed_sequence(raw_phases, SemanticPhase, "semantic.phases")
        envelope_values = _typed_sequence(raw_envelopes, EnvelopeDefinition, "semantic.envelopes")
        phase_by_id = {phase.phase_id: phase for phase in phases}
        envelope_by_id = {envelope.envelope_id: envelope for envelope in envelope_values}
        windows = build_semantic_windows_v1(context.semantic_scope, temporal_recipe)
        contracts = _input_contracts(temporal_recipe)
        table_role = temporal_recipe.get("table_role")
        if type(table_role) is not str:
            raise ValueError("temporal_recipe.table_role must be a string")
        x_view = context.streams.get("X")
        x_table = None if x_view is None else x_view.tables.get(table_role)

        kernel_results: list[O1KernelResult] = []
        for window in windows:
            if window.phase_id is None or window.phase_id not in phase_by_id:
                raise ValueError("O1 semantic window is not bound to a declared phase")
            phase = phase_by_id[window.phase_id]
            envelope = None if phase.envelope_id is None else envelope_by_id.get(phase.envelope_id)
            if envelope is None:
                kernel_results.append(
                    _missing_kernel(window.end_t_ns - window.start_t_ns, "phase-envelope-missing")
                )
                continue
            if x_table is None:
                kernel_results.append(
                    _missing_kernel(window.end_t_ns - window.start_t_ns, "no-temporal-support")
                )
                continue
            kernel_results.append(
                envelopes.compute_o1_kernel(
                    x_table=x_table,
                    phase=phase,
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
        computed = tuple(
            result for result in results if result.status == AnchorCalculationStatusV2.COMPUTED
        )
        noncomputed_statuses = tuple(
            AnchorCalculationStatusV2(result.status)
            for result in results
            if result.status != AnchorCalculationStatusV2.COMPUTED
        )
        if not windows:
            session_status = AnchorCalculationStatusV2.NOT_COMPUTABLE
        elif noncomputed_statuses:
            session_status = max(noncomputed_statuses, key=_STATUS_PRIORITY.__getitem__)
        else:
            session_status = AnchorCalculationStatusV2.COMPUTED

        primary = None
        if session_status is AnchorCalculationStatusV2.COMPUTED:
            precision_values = tuple(
                result.precision_percent
                for result in computed
                if result.precision_percent is not None
            )
            primary = MetricValue(scalar_kind="float", value=min(precision_values), unit="percent")
        diagnostics = tuple(
            diagnostic for breakdown in breakdowns for diagnostic in breakdown.diagnostics
        )
        payload = _artifact_payload(self._definition, results, windows)
        derived_artifacts = (
            () if payload is None else (artifacts.stage_table("desired-envelope-mask", payload),)
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
            matching_method="direct-envelope-field-v1",
            diagnostics=diagnostics,
        )
        return AnchorMeasurement(
            anchor_id="O1",
            calculation_status=session_status,
            primary_value=primary,
            primary_value_reason=None,
            raw_metrics={
                "phase-count": MetricValue(scalar_kind="integer", value=len(windows), unit="count"),
                "computed-phase-count": MetricValue(
                    scalar_kind="integer", value=len(computed), unit="count"
                ),
            },
            phase_results=breakdowns,
            event_results=(),
            classification_override_candidate=None,
            source_windows=windows,
            derived_artifacts=derived_artifacts,
            trace=trace,
            diagnostics=diagnostics,
        )


def create_plugin() -> O1PhaseStatePrecisionPlugin:
    return O1PhaseStatePrecisionPlugin()


__all__ = ["O1PhaseStatePrecisionPlugin", "create_plugin"]
