"""O4 Sustained Hover Time production plugin."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

import polars as pl
from pydantic import JsonValue

from pilot_assessment.anchors.catalog import load_packaged_catalog
from pilot_assessment.anchors.primitives import envelopes
from pilot_assessment.anchors.primitives.envelopes import O4KernelResult, O4KernelStatus
from pilot_assessment.anchors.protocols import (
    AnchorArtifactEmitter,
    AnchorPluginContext,
    ResolvedDependencies,
    TabularArtifactPayload,
)
from pilot_assessment.contracts.anchor_execution import (
    AnchorPluginDefinition,
    EnvelopeDefinition,
    ResolvedInputTableContract,
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
        entry for entry in load_packaged_catalog().entries if entry.anchor_id == "O4"
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


def _strict_string(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _strict_int(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be a strict integer of at least {minimum}")
    return value


def _strings(value: object, label: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{label} must be an ordered string array")
    normalized = tuple(
        _strict_string(item, f"{label}[{index}]") for index, item in enumerate(value)
    )
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{label} must contain unique values")
    return normalized


def _input_contracts(
    temporal_recipe: Mapping[str, JsonValue],
) -> tuple[ResolvedInputTableContract, ...]:
    raw = temporal_recipe.get("input_table_contracts")
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise ValueError("temporal_recipe.input_table_contracts must be an ordered array")
    contracts = tuple(ResolvedInputTableContract.model_validate(item) for item in raw)
    if not contracts:
        raise ValueError("O4 requires at least one input table contract")
    return contracts


def _typed_envelopes(value: object) -> tuple[EnvelopeDefinition, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("semantic.envelopes must be an ordered array")
    return tuple(EnvelopeDefinition.model_validate(item) for item in value)


@dataclass(frozen=True, slots=True)
class _BoundPhase:
    phase_id: str
    envelope_id: str
    window: SourceWindowV2


def _bound_phases(
    context: AnchorPluginContext,
    temporal_recipe: Mapping[str, JsonValue],
) -> tuple[_BoundPhase, ...]:
    policy = _strict_string(temporal_recipe.get("window_policy"), "temporal_recipe.window_policy")
    if policy != "bound-phase-windows-v1":
        raise ValueError("O4 requires window_policy=bound-phase-windows-v1")
    prefix = _strict_string(
        temporal_recipe.get("window_id_prefix"), "temporal_recipe.window_id_prefix"
    )
    scope_ids = _strings(temporal_recipe.get("scope_ids"), "temporal_recipe.scope_ids")
    raw_bindings = temporal_recipe.get("phase_bindings")
    if isinstance(raw_bindings, (str, bytes)) or not isinstance(raw_bindings, Sequence):
        raise ValueError("temporal_recipe.phase_bindings must be an ordered array")
    parsed: list[_BoundPhase] = []
    for index, raw in enumerate(raw_bindings):
        if not isinstance(raw, Mapping):
            raise ValueError(f"temporal_recipe.phase_bindings[{index}] must be an object")
        binding = cast(Mapping[str, object], raw)
        if set(binding) != {
            "phase_id",
            "start_t_ns",
            "end_t_ns",
            "include_session_terminal_point",
            "envelope_id",
        }:
            raise ValueError("O4 phase bindings require the exact five-key contract")
        phase_id = _strict_string(binding["phase_id"], f"phase_bindings[{index}].phase_id")
        envelope_id = _strict_string(binding["envelope_id"], f"phase_bindings[{index}].envelope_id")
        start = _strict_int(binding["start_t_ns"], f"phase_bindings[{index}].start_t_ns")
        end = _strict_int(binding["end_t_ns"], f"phase_bindings[{index}].end_t_ns", minimum=1)
        terminal = binding["include_session_terminal_point"]
        if type(terminal) is not bool:
            raise ValueError("include_session_terminal_point must be a strict boolean")
        if end <= start:
            raise ValueError("O4 phase binding must have positive duration")
        if start < context.session_window.start_t_ns or end > context.session_window.end_t_ns:
            raise ValueError("O4 phase binding lies outside the immutable session window")
        parsed.append(
            _BoundPhase(
                phase_id=phase_id,
                envelope_id=envelope_id,
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
    ids = tuple(item.phase_id for item in parsed)
    if len(ids) != len(set(ids)) or set(ids) != set(scope_ids):
        raise ValueError("O4 phase bindings must exactly match unique scope_ids")
    ordered = tuple(
        sorted(
            parsed, key=lambda item: (item.window.start_t_ns, item.window.end_t_ns, item.phase_id)
        )
    )
    if any(
        current.window.start_t_ns < previous.window.end_t_ns
        for previous, current in zip(ordered, ordered[1:], strict=False)
    ):
        raise ValueError("O4 phase bindings must not overlap")
    return ordered


def _missing_result(
    status: O4KernelStatus,
    reason: str,
    phase_duration_ns: int,
) -> O4KernelResult:
    return O4KernelResult(
        status=status,
        reason=reason,
        longest_stable_duration_ns=None,
        total_stable_duration_ns=0,
        bridged_excursion_duration_ns=0,
        bridged_excursion_count=0,
        phase_duration_ns=phase_duration_ns,
        observed_support_duration_ns=0,
        sample_count=0,
        source_start_t_ns=None,
        source_end_t_ns=None,
        gap_count=0,
        max_gap_ns=None,
        mask_rows=(),
    )


def _diagnostic(result: O4KernelResult, phase_id: str) -> DomainErrorData:
    assert result.reason is not None
    missing = result.status == "missing_input"
    return DomainErrorData(
        error_code=f"anchor.o4.{result.reason}",
        severity=ErrorSeverity.WARNING,
        recoverable=True,
        message=f"O4 phase {phase_id} could not produce sustained-hover evidence: {result.reason}",
        field_or_path=(
            "streams.X.samples" if missing else "execution_plan.entries.O4.temporal_recipe"
        ),
        node_or_anchor_id="O4",
        remediation=(
            "Provide native X rows in the declared phase span."
            if missing
            else "Correct the bound phase, envelope, input contract, or O4 parameters."
        ),
        diagnostics={
            "phase_id": phase_id,
            "reason": result.reason,
            "sample_count": result.sample_count,
            "observed_support_duration_ns": result.observed_support_duration_ns,
        },
    )


def _raw_metrics(result: O4KernelResult) -> dict[str, MetricValue]:
    return {
        "phase-duration": MetricValue(
            scalar_kind="integer", value=result.phase_duration_ns, unit="ns"
        ),
        "observed-support-duration": MetricValue(
            scalar_kind="integer", value=result.observed_support_duration_ns, unit="ns"
        ),
        "total-stable-duration": MetricValue(
            scalar_kind="integer", value=result.total_stable_duration_ns, unit="ns"
        ),
        "bridged-excursion-duration": MetricValue(
            scalar_kind="integer", value=result.bridged_excursion_duration_ns, unit="ns"
        ),
        "bridged-excursion-count": MetricValue(
            scalar_kind="integer", value=result.bridged_excursion_count, unit="count"
        ),
        "sample-count": MetricValue(scalar_kind="integer", value=result.sample_count, unit="count"),
        "gap-count": MetricValue(scalar_kind="integer", value=result.gap_count, unit="count"),
    }


def _trace(
    result: O4KernelResult,
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
        matching_method="hover-envelope-behavioral-tolerance-v1",
        diagnostics=diagnostics,
    )


def _breakdown(result: O4KernelResult, window: SourceWindowV2) -> AnchorBreakdownMeasurement:
    diagnostics = (
        () if result.status == "computed" else (_diagnostic(result, window.phase_id or "unknown"),)
    )
    primary = (
        MetricValue(
            scalar_kind="float",
            value=result.longest_stable_duration_ns / _NANOSECONDS_PER_SECOND,
            unit="s",
        )
        if result.longest_stable_duration_ns is not None
        else None
    )
    return AnchorBreakdownMeasurement(
        breakdown_id=window.phase_id or window.window_id,
        calculation_status=AnchorCalculationStatusV2(result.status),
        primary_value=primary,
        primary_value_reason=None,
        raw_metrics=_raw_metrics(result),
        classification_override_candidate=None,
        trace=_trace(result, window, diagnostics),
        diagnostics=diagnostics,
    )


def _artifact_payload(
    definition: AnchorPluginDefinition,
    results: tuple[O4KernelResult, ...],
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
            "stable": pl.Series("stable", [row.stable for row in rows], dtype=pl.Boolean),
        }
    ).sort(["phase_id", "t_ns", "source_row_id"], maintain_order=True)
    populated = tuple(
        window for result, window in zip(results, windows, strict=True) if result.mask_rows
    )
    return TabularArtifactPayload(
        schema_id=recipe.schema_id,
        schema_descriptor=recipe.schema_descriptor,
        frame=frame,
        order_keys=("phase_id", "t_ns", "source_row_id"),
        artifact_kind=recipe.kind,
        grid_hash=None,
        start_t_ns=min(window.start_t_ns for window in populated),
        end_t_ns=max(window.end_t_ns for window in populated),
    )


class O4SustainedHoverTimePlugin:
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
        if not isinstance(parameters, Mapping) or set(parameters) != {
            "max_behavioral_excursion_ns"
        }:
            raise ValueError("O4 v0.1 parameters require exactly max_behavioral_excursion_ns")
        bound_phases = _bound_phases(context, temporal_recipe)
        envelopes_values = _typed_envelopes(context.semantic_scope.values.get("semantic.envelopes"))
        envelope_by_id = {item.envelope_id: item for item in envelopes_values}
        contracts = _input_contracts(temporal_recipe)
        table_role = _strict_string(temporal_recipe.get("table_role"), "temporal_recipe.table_role")
        x_view = context.streams.get("X")
        x_table = None if x_view is None else x_view.tables.get(table_role)

        results_list: list[O4KernelResult] = []
        for binding in bound_phases:
            duration = binding.window.end_t_ns - binding.window.start_t_ns
            if x_table is None:
                results_list.append(
                    _missing_result("missing_input", "no-temporal-support", duration)
                )
                continue
            envelope = envelope_by_id.get(binding.envelope_id)
            if envelope is None:
                results_list.append(
                    _missing_result("not_computable", "phase-envelope-missing", duration)
                )
                continue
            results_list.append(
                envelopes.compute_o4_kernel(
                    x_table=x_table,
                    phase_id=binding.phase_id,
                    envelope=envelope,
                    scope_start_t_ns=binding.window.start_t_ns,
                    scope_end_t_ns=binding.window.end_t_ns,
                    include_session_terminal_point=binding.window.include_session_terminal_point,
                    input_contracts=contracts,
                    parameters=parameters,
                    temporal_recipe=temporal_recipe,
                )
            )

        results = tuple(results_list)
        windows = tuple(item.window for item in bound_phases)
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

        primary = None
        if session_status is AnchorCalculationStatusV2.COMPUTED:
            longest = max(
                result.longest_stable_duration_ns
                for result in computed
                if result.longest_stable_duration_ns is not None
            )
            primary = MetricValue(
                scalar_kind="float", value=longest / _NANOSECONDS_PER_SECOND, unit="s"
            )
        diagnostics = tuple(
            diagnostic for breakdown in breakdowns for diagnostic in breakdown.diagnostics
        )
        payload = _artifact_payload(self._definition, results, windows)
        derived_artifacts = (
            () if payload is None else (artifacts.stage_table("stable-hover-mask", payload),)
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
            matching_method="hover-envelope-behavioral-tolerance-v1",
            diagnostics=diagnostics,
        )
        return AnchorMeasurement(
            anchor_id="O4",
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


def create_plugin() -> O4SustainedHoverTimePlugin:
    return O4SustainedHoverTimePlugin()


__all__ = ["O4SustainedHoverTimePlugin", "create_plugin"]
