"""O2 Peak Tracking Excursion production plugin."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import polars as pl
from pydantic import JsonValue

from pilot_assessment.anchors.catalog import load_packaged_catalog
from pilot_assessment.anchors.primitives.reference_join import (
    O2KernelResult,
    O2KernelStatus,
    O2TrackingErrorRow,
    compute_o2_kernel,
)
from pilot_assessment.anchors.protocols import (
    AnchorArtifactEmitter,
    AnchorPluginContext,
    ResolvedDependencies,
    TabularArtifactPayload,
)
from pilot_assessment.anchors.temporal import build_semantic_windows_v1
from pilot_assessment.contracts.anchor_execution import (
    AnchorPluginDefinition,
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


def _definition() -> AnchorPluginDefinition:
    catalog_entry = next(
        entry for entry in load_packaged_catalog().entries if entry.anchor_id == "O2"
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


def _typed_phases(values: object) -> tuple[SemanticPhase, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError("semantic.phases must be an ordered array")
    return tuple(SemanticPhase.model_validate(item) for item in values)


def _input_contracts(
    temporal_recipe: Mapping[str, JsonValue],
) -> tuple[ResolvedInputTableContract, ...]:
    raw = temporal_recipe.get("input_table_contracts")
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise ValueError("temporal_recipe.input_table_contracts must be an ordered array")
    contracts = tuple(ResolvedInputTableContract.model_validate(item) for item in raw)
    if not contracts:
        raise ValueError("O2 requires at least one input table contract")
    return contracts


def _x_contract(
    contracts: tuple[ResolvedInputTableContract, ...], table_role: str
) -> ResolvedInputTableContract:
    matches = tuple(
        contract
        for contract in contracts
        if contract.modality.value == "X" and contract.table_role == table_role
    )
    if len(matches) != 1:
        raise ValueError("O2 requires exactly one declared X table contract")
    return matches[0]


def _missing_result(status: O2KernelStatus, reason: str) -> O2KernelResult:
    return O2KernelResult(
        status=status,
        reason=reason,
        peak_excursion_ft=None,
        peak_t_ns=None,
        peak_source_row_id=None,
        candidate_point_count=0,
        joined_point_count=0,
        source_start_t_ns=None,
        source_end_t_ns=None,
        reference_start_t_ns=None,
        reference_end_t_ns=None,
        trace_rows=(),
    )


def _diagnostic(result: O2KernelResult, phase_id: str) -> DomainErrorData:
    assert result.reason is not None
    if result.status == "missing_input":
        field_or_path = "streams.X.samples"
        remediation = "Provide the declared phase X rows."
    elif result.reason == "reference_not_present":
        field_or_path = "references.task_reference"
        remediation = "Resolve the independent commanded task reference."
    elif result.reason == "no_reference_overlap":
        field_or_path = "references.task_reference.commanded-path"
        remediation = "Provide commanded-reference support at applicable native X timestamps."
    else:
        field_or_path = "execution_plan.entries.O2.temporal_recipe"
        remediation = "Bind a compatible position/frame/unit contract and versioned transform."
    return DomainErrorData(
        error_code=f"anchor.o2.{result.reason}",
        severity=ErrorSeverity.WARNING,
        recoverable=True,
        message=f"O2 phase {phase_id} could not produce a tracking excursion: {result.reason}",
        field_or_path=field_or_path,
        node_or_anchor_id="O2",
        remediation=remediation,
        diagnostics={
            "phase_id": phase_id,
            "reason": result.reason,
            "candidate_point_count": result.candidate_point_count,
            "joined_point_count": result.joined_point_count,
        },
    )


def _raw_metrics(result: O2KernelResult) -> dict[str, MetricValue]:
    metrics = {
        "candidate-x-point-count": MetricValue(
            scalar_kind="integer", value=result.candidate_point_count, unit="count"
        ),
        "joined-point-count": MetricValue(
            scalar_kind="integer", value=result.joined_point_count, unit="count"
        ),
    }
    if result.peak_t_ns is not None and result.peak_source_row_id is not None:
        metrics.update(
            {
                "peak-t-ns": MetricValue(scalar_kind="integer", value=result.peak_t_ns, unit="ns"),
                "peak-source-row-id": MetricValue(
                    scalar_kind="integer", value=result.peak_source_row_id, unit="index"
                ),
            }
        )
    return metrics


def _kernel_trace(
    result: O2KernelResult,
    window: SourceWindowV2,
    diagnostics: tuple[DomainErrorData, ...],
) -> ComputationTrace:
    return ComputationTrace(
        sample_count=result.joined_point_count,
        source_start_t_ns=result.source_start_t_ns,
        source_end_t_ns=result.source_end_t_ns,
        analysis_start_t_ns=window.start_t_ns,
        analysis_end_t_ns=window.end_t_ns,
        grid_id=None,
        window_ids=(window.window_id,),
        interpolation_method="time-aligned-linear-v1",
        matching_method="commanded-reference-affine-3d-l2-v1",
        diagnostics=diagnostics,
    )


def _breakdown(result: O2KernelResult, window: SourceWindowV2) -> AnchorBreakdownMeasurement:
    status = AnchorCalculationStatusV2(result.status)
    diagnostics = (
        () if result.status == "computed" else (_diagnostic(result, window.phase_id or "unknown"),)
    )
    primary = (
        MetricValue(scalar_kind="float", value=result.peak_excursion_ft, unit="ft")
        if result.peak_excursion_ft is not None
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


def _artifact_payload(
    definition: AnchorPluginDefinition,
    rows: tuple[O2TrackingErrorRow, ...],
) -> TabularArtifactPayload | None:
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
            "error_x": pl.Series("error_x", [row.error_x_ft for row in rows], dtype=pl.Float64),
            "error_y": pl.Series("error_y", [row.error_y_ft for row in rows], dtype=pl.Float64),
            "error_z": pl.Series("error_z", [row.error_z_ft for row in rows], dtype=pl.Float64),
            "error_norm": pl.Series(
                "error_norm", [row.error_norm_ft for row in rows], dtype=pl.Float64
            ),
        }
    ).sort(["phase_id", "t_ns", "source_row_id"], maintain_order=True)
    return TabularArtifactPayload(
        schema_id=recipe.schema_id,
        schema_descriptor=recipe.schema_descriptor,
        frame=frame,
        order_keys=("phase_id", "t_ns", "source_row_id"),
        artifact_kind=recipe.kind,
        grid_hash=None,
        start_t_ns=min(row.t_ns for row in rows),
        end_t_ns=max(row.t_ns for row in rows),
    )


class O2PeakTrackingExcursionPlugin:
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
        if not isinstance(parameters, Mapping) or parameters:
            raise ValueError("O2 v0.1 parameters must be the exact empty object")
        phases = _typed_phases(context.semantic_scope.values.get("semantic.phases"))
        phase_by_id = {phase.phase_id: phase for phase in phases}
        windows = build_semantic_windows_v1(context.semantic_scope, temporal_recipe)
        contracts = _input_contracts(temporal_recipe)
        table_role = temporal_recipe.get("table_role")
        if type(table_role) is not str:
            raise ValueError("temporal_recipe.table_role must be a string")
        x_contract = _x_contract(contracts, table_role)
        x_view = context.streams.get("X")
        x_table = None if x_view is None else x_view.tables.get(table_role)

        resolved_reference = context.references.get("task_reference")
        reference_table = None
        reference_contract = None
        if resolved_reference is not None:
            reference_contract = resolved_reference.descriptor.table_contract
            if resolved_reference.aligned_view is not None:
                reference_table = resolved_reference.aligned_view.tables.get(
                    reference_contract.table_role
                )

        kernel_results: list[O2KernelResult] = []
        for window in windows:
            if window.phase_id is None or window.phase_id not in phase_by_id:
                raise ValueError("O2 semantic window is not bound to a declared phase")
            if x_table is None:
                kernel_results.append(_missing_result("missing_input", "no_temporal_support"))
                continue
            if reference_table is None or reference_contract is None:
                kernel_results.append(_missing_result("not_computable", "reference_not_present"))
                continue
            kernel_results.append(
                compute_o2_kernel(
                    x_table=x_table,
                    reference_table=reference_table,
                    phase=phase_by_id[window.phase_id],
                    x_contract=x_contract,
                    reference_contract=reference_contract,
                    scope_start_t_ns=window.start_t_ns,
                    scope_end_t_ns=window.end_t_ns,
                    temporal_recipe=temporal_recipe,
                )
            )
        results = tuple(kernel_results)
        breakdowns = tuple(
            _breakdown(result, window) for result, window in zip(results, windows, strict=True)
        )
        computed = tuple(result for result in results if result.status == "computed")
        if computed:
            session_status = AnchorCalculationStatusV2.COMPUTED
        elif results:
            session_status = max(
                (AnchorCalculationStatusV2(result.status) for result in results),
                key=_STATUS_PRIORITY.__getitem__,
            )
        else:
            session_status = AnchorCalculationStatusV2.NOT_COMPUTABLE

        all_rows = tuple(
            sorted(
                (row for result in computed for row in result.trace_rows),
                key=lambda row: (row.phase_id, row.t_ns, row.source_row_id),
            )
        )
        peak = None
        if all_rows:
            peak_value = max(row.error_norm_ft for row in all_rows)
            peak = min(
                (row for row in all_rows if row.error_norm_ft == peak_value),
                key=lambda row: (row.t_ns, row.source_row_id, row.phase_id),
            )
        primary = (
            MetricValue(scalar_kind="float", value=peak.error_norm_ft, unit="ft")
            if peak is not None
            else None
        )
        raw_metrics = {
            "phase-count": MetricValue(scalar_kind="integer", value=len(windows), unit="count"),
            "computed-phase-count": MetricValue(
                scalar_kind="integer", value=len(computed), unit="count"
            ),
            "joined-point-count": MetricValue(
                scalar_kind="integer", value=len(all_rows), unit="count"
            ),
        }
        if peak is not None:
            raw_metrics.update(
                {
                    "peak-t-ns": MetricValue(scalar_kind="integer", value=peak.t_ns, unit="ns"),
                    "peak-source-row-id": MetricValue(
                        scalar_kind="integer", value=peak.source_row_id, unit="index"
                    ),
                }
            )
        diagnostics = tuple(
            diagnostic for breakdown in breakdowns for diagnostic in breakdown.diagnostics
        )
        payload = _artifact_payload(self._definition, all_rows)
        derived_artifacts = (
            () if payload is None else (artifacts.stage_table("tracking-error-trace", payload),)
        )
        trace = ComputationTrace(
            sample_count=len(all_rows),
            source_start_t_ns=min((row.t_ns for row in all_rows), default=None),
            source_end_t_ns=max((row.t_ns for row in all_rows), default=None),
            analysis_start_t_ns=min((window.start_t_ns for window in windows), default=None),
            analysis_end_t_ns=max((window.end_t_ns for window in windows), default=None),
            grid_id=None,
            window_ids=tuple(window.window_id for window in windows),
            interpolation_method="time-aligned-linear-v1",
            matching_method="commanded-reference-affine-3d-l2-v1",
            diagnostics=diagnostics,
        )
        return AnchorMeasurement(
            anchor_id="O2",
            calculation_status=session_status,
            primary_value=primary,
            primary_value_reason=None,
            raw_metrics=raw_metrics,
            phase_results=breakdowns,
            event_results=(),
            classification_override_candidate=None,
            source_windows=windows,
            derived_artifacts=derived_artifacts,
            trace=trace,
            diagnostics=diagnostics,
        )


def create_plugin() -> O2PeakTrackingExcursionPlugin:
    return O2PeakTrackingExcursionPlugin()


__all__ = ["O2PeakTrackingExcursionPlugin", "create_plugin"]
