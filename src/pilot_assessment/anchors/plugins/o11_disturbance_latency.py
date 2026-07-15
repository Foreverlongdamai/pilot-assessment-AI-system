"""O11 Disturbance Latency production plugin."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from statistics import median
from typing import Literal, cast

import polars as pl
from pydantic import JsonValue

from pilot_assessment.anchors.catalog import load_packaged_catalog
from pilot_assessment.anchors.primitives.events import (
    CausalBooleanInterval,
    CausalNumericSample,
    ConfirmedBooleanRun,
    clip_boolean_intervals,
    clip_observation_end,
    confirmed_true_runs,
    trailing_causal_median,
)
from pilot_assessment.anchors.protocols import (
    AnchorArtifactEmitter,
    AnchorPluginContext,
    ResolvedDependencies,
    TabularArtifactPayload,
)
from pilot_assessment.anchors.temporal import SupportInterval, reconstruct_point_support
from pilot_assessment.contracts.anchor_execution import (
    AnchorPluginDefinition,
    ControlEffectMapping,
    ResolvedInputTableContract,
    SemanticEvent,
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

_NUMERIC_DTYPES = {"i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64", "f32", "f64"}
_STATUS_PRIORITY = {
    AnchorCalculationStatusV2.NOT_COMPUTABLE: 0,
    AnchorCalculationStatusV2.MISSING_INPUT: 1,
    AnchorCalculationStatusV2.DEPENDENCY_MISSING: 2,
    AnchorCalculationStatusV2.EXTRACTOR_ERROR: 3,
}
_ResultStatus = Literal["computed", "missing_input", "not_computable"]


def _definition() -> AnchorPluginDefinition:
    catalog_entry = next(
        entry for entry in load_packaged_catalog().entries if entry.anchor_id == "O11"
    )
    return AnchorPluginDefinition(
        anchor_id=catalog_entry.anchor_id,
        definition_version=catalog_entry.definition_version,
        plugin_id=catalog_entry.plugin_id,
        plugin_version=catalog_entry.plugin_version,
        api_version="0.1.0",
        required_streams=tuple(
            item.removeprefix("stream.")
            for item in catalog_entry.required_inputs
            if item.startswith("stream.")
        ),
        required_context_paths=tuple(
            sorted(item for item in catalog_entry.required_inputs if item.startswith("context."))
        ),
        required_semantic_paths=tuple(
            sorted(item for item in catalog_entry.required_inputs if item.startswith("semantic."))
        ),
        required_reference_ids=tuple(
            sorted(
                item.removeprefix("reference.")
                for item in catalog_entry.required_inputs
                if item.startswith("reference.")
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


def _strict_float(value: object, label: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < minimum:
        raise ValueError(f"{label} must be a finite number of at least {minimum}")
    return normalized


def _strict_strings(value: object, label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{label} must be an ordered string array")
    normalized = tuple(value)
    if (not normalized and not allow_empty) or any(
        type(item) is not str or not item for item in normalized
    ):
        raise ValueError(f"{label} contains an invalid string")
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{label} must be unique")
    return cast(tuple[str, ...], normalized)


@dataclass(frozen=True, slots=True)
class _Parameters:
    baseline_lookback_ns: int
    causal_median_window_ns: int
    control_excursion_threshold_pct: float
    minimum_excursion_duration_ns: int
    response_horizon_ns: int


def _parameters(parameters: Mapping[str, JsonValue]) -> _Parameters:
    expected = {
        "baseline_lookback_ns",
        "causal_median_window_ns",
        "control_excursion_threshold_pct",
        "minimum_excursion_duration_ns",
        "response_horizon_ns",
    }
    if not isinstance(parameters, Mapping) or set(parameters) != expected:
        raise ValueError("O11 v0.1 parameters require the exact five-key contract")
    return _Parameters(
        baseline_lookback_ns=_strict_int(
            parameters["baseline_lookback_ns"], "baseline_lookback_ns", minimum=1
        ),
        causal_median_window_ns=_strict_int(
            parameters["causal_median_window_ns"], "causal_median_window_ns", minimum=1
        ),
        control_excursion_threshold_pct=_strict_float(
            parameters["control_excursion_threshold_pct"],
            "control_excursion_threshold_pct",
        ),
        minimum_excursion_duration_ns=_strict_int(
            parameters["minimum_excursion_duration_ns"], "minimum_excursion_duration_ns"
        ),
        response_horizon_ns=_strict_int(
            parameters["response_horizon_ns"], "response_horizon_ns", minimum=1
        ),
    )


@dataclass(frozen=True, slots=True)
class _PhaseBinding:
    phase_id: str
    start_t_ns: int
    end_t_ns: int
    include_session_terminal_point: bool


def _phase_bindings(
    temporal_recipe: Mapping[str, JsonValue], session_end_t_ns: int
) -> tuple[_PhaseBinding, ...]:
    raw = temporal_recipe.get("phase_bindings")
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise ValueError("temporal_recipe.phase_bindings must be an ordered array")
    bindings: list[_PhaseBinding] = []
    expected = {
        "phase_id",
        "start_t_ns",
        "end_t_ns",
        "include_session_terminal_point",
    }
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping) or set(item) != expected:
            raise ValueError(f"phase binding {index} must use the exact four-key contract")
        typed = cast(Mapping[str, object], item)
        phase_id = _strict_string(typed["phase_id"], f"phase_bindings[{index}].phase_id")
        start = _strict_int(typed["start_t_ns"], f"phase_bindings[{index}].start_t_ns")
        end = _strict_int(typed["end_t_ns"], f"phase_bindings[{index}].end_t_ns", minimum=1)
        terminal = typed["include_session_terminal_point"]
        if type(terminal) is not bool:
            raise ValueError("include_session_terminal_point must be a strict boolean")
        if end <= start or end > session_end_t_ns:
            raise ValueError("phase binding must be a positive span within the session")
        if terminal and end != session_end_t_ns:
            raise ValueError("terminal phase binding must end at the session end")
        bindings.append(_PhaseBinding(phase_id, start, end, terminal))
    normalized = tuple(bindings)
    if normalized != tuple(
        sorted(normalized, key=lambda item: (item.start_t_ns, item.end_t_ns, item.phase_id))
    ):
        raise ValueError("phase bindings must use canonical temporal order")
    if any(current.start_t_ns < previous.end_t_ns for previous, current in pairwise(normalized)):
        raise ValueError("phase bindings must not overlap")
    ids = tuple(item.phase_id for item in normalized)
    if len(ids) != len(set(ids)):
        raise ValueError("phase binding IDs must be unique")
    return normalized


def _input_contract(
    context: AnchorPluginContext, table_role: str
) -> ResolvedInputTableContract | None:
    matches = tuple(
        item
        for item in context.input_table_contracts
        if item.modality.value == "U" and item.table_role == table_role
    )
    if len(matches) > 1:
        raise ValueError("input contracts contain duplicate U table roles")
    return matches[0] if matches else None


@dataclass(frozen=True, slots=True)
class _PreparedPhase:
    status: _ResultStatus
    reason: str | None
    binding: _PhaseBinding
    frame: pl.DataFrame | None
    support_intervals: tuple[SupportInterval, ...]
    sample_count: int
    source_start_t_ns: int | None
    source_end_t_ns: int | None
    gap_count: int
    max_gap_ns: int | None


def _failed_phase(status: _ResultStatus, reason: str, binding: _PhaseBinding) -> _PreparedPhase:
    return _PreparedPhase(status, reason, binding, None, (), 0, None, None, 0, None)


def _prepare_phase(
    *,
    u_table: pl.DataFrame | None,
    u_aligned_schema_id: str | None,
    contract: ResolvedInputTableContract | None,
    binding: _PhaseBinding,
    timestamp_column: str,
    in_session_column: str,
    stable_keys: tuple[str, ...],
    gap_threshold_ns: int,
) -> _PreparedPhase:
    if contract is None or (
        u_aligned_schema_id is not None and contract.stream_aligned_schema_id != u_aligned_schema_id
    ):
        return _failed_phase("not_computable", "input-contract-mismatch", binding)
    if u_table is None:
        return _failed_phase("missing_input", "no-temporal-support", binding)
    fields = {field.field_name: field for field in contract.fields}
    required = (timestamp_column, in_session_column, *stable_keys)
    if any(name not in fields or name not in u_table.columns for name in required):
        return _failed_phase("not_computable", "temporal-field-missing", binding)
    if fields[timestamp_column].unit != "ns" or fields[in_session_column].unit != "bool":
        return _failed_phase("not_computable", "temporal-contract-mismatch", binding)
    end_filter = (
        pl.col(timestamp_column) <= binding.end_t_ns
        if binding.include_session_terminal_point
        else pl.col(timestamp_column) < binding.end_t_ns
    )
    try:
        active = u_table.filter(
            (pl.col(timestamp_column) >= binding.start_t_ns)
            & end_filter
            & pl.col(in_session_column)
        ).sort([timestamp_column, *stable_keys], maintain_order=True)
    except (TypeError, ValueError, pl.exceptions.PolarsError):
        return _failed_phase("not_computable", "temporal-table-invalid", binding)
    if active.is_empty():
        return _failed_phase("missing_input", "no-temporal-support", binding)
    try:
        support = reconstruct_point_support(
            active,
            timestamp_column=timestamp_column,
            stable_keys=stable_keys,
            in_session_column=in_session_column,
            gap_threshold_ns=gap_threshold_ns,
            semantic_end_t_ns=binding.end_t_ns,
        )
    except (TypeError, ValueError, pl.exceptions.PolarsError):
        return _failed_phase("not_computable", "temporal-support-invalid", binding)
    times = active[timestamp_column].to_list()
    if support.observed_duration_ns == 0:
        return _PreparedPhase(
            "missing_input",
            "no-temporal-support",
            binding,
            active,
            support.intervals,
            active.height,
            min(times),
            max(times),
            support.gap_count,
            support.max_gap_ns,
        )
    return _PreparedPhase(
        "computed",
        None,
        binding,
        active,
        support.intervals,
        active.height,
        min(times),
        max(times),
        support.gap_count,
        support.max_gap_ns,
    )


@dataclass(frozen=True, slots=True)
class _ChannelTimeline:
    status: _ResultStatus
    reason: str | None
    mapping: ControlEffectMapping
    samples: tuple[CausalNumericSample, ...]
    intervals: tuple[tuple[int, int, int, float], ...]


def _normalize_control(value: float, mapping: ControlEffectMapping) -> float:
    denominator = (
        mapping.upper - mapping.trim if value >= mapping.trim else mapping.trim - mapping.lower
    )
    return 100.0 * (value - mapping.trim) / denominator


def _channel_timeline(
    phase: _PreparedPhase,
    mapping: ControlEffectMapping,
    contract: ResolvedInputTableContract | None,
    causal_window_ns: int,
) -> _ChannelTimeline:
    if phase.status != "computed" or phase.frame is None or contract is None:
        return _ChannelTimeline(phase.status, phase.reason, mapping, (), ())
    fields = {field.field_name: field for field in contract.fields}
    field = fields.get(mapping.control_channel_id)
    if (
        field is None
        or field.dtype_id not in _NUMERIC_DTYPES
        or field.unit != mapping.control_unit
        or mapping.control_channel_id not in phase.frame.columns
    ):
        return _ChannelTimeline("not_computable", "control-contract-mismatch", mapping, (), ())
    raw_values = phase.frame[mapping.control_channel_id].to_list()
    if any(
        value is None
        or isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        for value in raw_values
    ):
        return _ChannelTimeline("not_computable", "control-value-invalid", mapping, (), ())
    samples: list[CausalNumericSample] = []
    intervals: list[tuple[int, int, int, float]] = []
    segment_id = 0
    previous_end: int | None = None
    for raw_interval in phase.support_intervals:
        start_t_ns = raw_interval.start_t_ns
        end_t_ns = raw_interval.end_t_ns
        source_row_id = raw_interval.source_row_index
        if previous_end is not None and start_t_ns > previous_end:
            segment_id += 1
        previous_end = end_t_ns
        normalized = _normalize_control(float(raw_values[source_row_id]), mapping)
        samples.append(CausalNumericSample(start_t_ns, source_row_id, segment_id, normalized))
        intervals.append((start_t_ns, end_t_ns, source_row_id, normalized))
    filtered = trailing_causal_median(samples, window_ns=causal_window_ns)
    by_source = {item.source_row_id: item.value for item in filtered}
    filtered_intervals = tuple(
        (start, end, source, by_source[source]) for start, end, source, _value in intervals
    )
    return _ChannelTimeline("computed", None, mapping, filtered, filtered_intervals)


@dataclass(frozen=True, slots=True)
class _ChannelResponse:
    channel_id: str
    baseline_pct: float
    baseline_source: str
    correct_run: ConfirmedBooleanRun | None
    wrong_run: ConfirmedBooleanRun | None
    observed_support_duration_ns: int

    @property
    def selected_run(self) -> tuple[ConfirmedBooleanRun | None, bool]:
        if self.correct_run is None:
            return self.wrong_run, False
        if self.wrong_run is None or self.correct_run.onset_t_ns <= self.wrong_run.onset_t_ns:
            return self.correct_run, True
        return self.wrong_run, False


@dataclass(frozen=True, slots=True)
class _Opportunity:
    event: SemanticEvent
    phase: _PhaseBinding
    observation_end_t_ns: int
    window: SourceWindowV2


@dataclass(frozen=True, slots=True)
class _EventResult:
    status: _ResultStatus
    reason: str | None
    opportunity: _Opportunity
    missed: bool
    wrong_direction: bool
    latency_ms: float | None
    observed_wait_ms: float | None
    channels: tuple[_ChannelResponse, ...]
    sample_count: int
    source_start_t_ns: int | None
    source_end_t_ns: int | None
    gap_count: int
    max_gap_ns: int | None


def _failed_result(
    status: _ResultStatus,
    reason: str,
    opportunity: _Opportunity,
    phase: _PreparedPhase,
) -> _EventResult:
    return _EventResult(
        status,
        reason,
        opportunity,
        False,
        False,
        None,
        None,
        (),
        phase.sample_count,
        phase.source_start_t_ns,
        phase.source_end_t_ns,
        phase.gap_count,
        phase.max_gap_ns,
    )


def _channel_response(
    timeline: _ChannelTimeline,
    opportunity: _Opportunity,
    parameters: _Parameters,
) -> _ChannelResponse | None:
    if timeline.status != "computed":
        return None
    baseline_values = tuple(
        float(item.value)
        for item in timeline.samples
        if max(
            opportunity.phase.start_t_ns,
            opportunity.event.t_ns - parameters.baseline_lookback_ns,
        )
        <= item.t_ns
        < opportunity.event.t_ns
    )
    baseline = float(median(baseline_values)) if baseline_values else 0.0
    baseline_source = "phase-pre-event-median-v1" if baseline_values else "mapping-trim-v1"
    correct_intervals = clip_boolean_intervals(
        tuple(
            CausalBooleanInterval(
                start,
                end,
                source,
                timeline.mapping.correct_sign * (value - baseline)
                > parameters.control_excursion_threshold_pct,
            )
            for start, end, source, value in timeline.intervals
        ),
        start_t_ns=opportunity.event.t_ns,
        end_t_ns=opportunity.observation_end_t_ns,
    )
    wrong_intervals = clip_boolean_intervals(
        tuple(
            CausalBooleanInterval(
                start,
                end,
                source,
                timeline.mapping.correct_sign * (value - baseline)
                < -parameters.control_excursion_threshold_pct,
            )
            for start, end, source, value in timeline.intervals
        ),
        start_t_ns=opportunity.event.t_ns,
        end_t_ns=opportunity.observation_end_t_ns,
    )
    correct = confirmed_true_runs(
        correct_intervals,
        minimum_duration_ns=parameters.minimum_excursion_duration_ns,
    )
    wrong = confirmed_true_runs(
        wrong_intervals,
        minimum_duration_ns=parameters.minimum_excursion_duration_ns,
    )
    observed = sum(item.end_t_ns - item.start_t_ns for item in correct_intervals)
    return _ChannelResponse(
        timeline.mapping.control_channel_id,
        baseline,
        baseline_source,
        correct[0] if correct else None,
        wrong[0] if wrong else None,
        observed,
    )


def _event_result(
    *,
    opportunity: _Opportunity,
    prepared_phase: _PreparedPhase,
    mapping_by_id: Mapping[str, ControlEffectMapping],
    contract: ResolvedInputTableContract | None,
    parameters: _Parameters,
) -> _EventResult:
    if prepared_phase.status != "computed":
        return _failed_result(
            prepared_phase.status,
            prepared_phase.reason or "unknown",
            opportunity,
            prepared_phase,
        )
    mapping_ids = opportunity.event.control_mapping_ids
    if not mapping_ids or any(mapping_id not in mapping_by_id for mapping_id in mapping_ids):
        return _failed_result(
            "not_computable", "control-mapping-missing", opportunity, prepared_phase
        )
    mappings = tuple(mapping_by_id[mapping_id] for mapping_id in mapping_ids)
    channels = tuple(
        _channel_timeline(
            prepared_phase,
            mapping,
            contract,
            parameters.causal_median_window_ns,
        )
        for mapping in mappings
    )
    failed = next((item for item in channels if item.status != "computed"), None)
    if failed is not None:
        return _failed_result(
            failed.status,
            failed.reason or "unknown",
            opportunity,
            prepared_phase,
        )
    responses = tuple(
        cast(_ChannelResponse, _channel_response(item, opportunity, parameters))
        for item in channels
    )
    if not responses or any(item.observed_support_duration_ns == 0 for item in responses):
        return _failed_result("missing_input", "no-temporal-support", opportunity, prepared_phase)
    correct_runs = tuple(
        (item.correct_run.onset_t_ns, item.channel_id, item.correct_run)
        for item in responses
        if item.correct_run is not None
    )
    wrong_runs = tuple(
        (item.wrong_run.onset_t_ns, item.channel_id, item.wrong_run)
        for item in responses
        if item.wrong_run is not None
    )
    first_correct = min(correct_runs, default=None)
    first_wrong = min(wrong_runs, default=None)
    wrong_first = first_wrong is not None and (
        first_correct is None or first_wrong[0] < first_correct[0]
    )
    missed = wrong_first or first_correct is None
    latency_ms = None if missed else (first_correct[0] - opportunity.event.t_ns) / 1_000_000.0
    observed_wait_ms = (
        (opportunity.observation_end_t_ns - opportunity.event.t_ns) / 1_000_000.0
        if missed
        else None
    )
    return _EventResult(
        "computed",
        None,
        opportunity,
        missed,
        wrong_first,
        latency_ms,
        observed_wait_ms,
        responses,
        prepared_phase.sample_count,
        prepared_phase.source_start_t_ns,
        prepared_phase.source_end_t_ns,
        prepared_phase.gap_count,
        prepared_phase.max_gap_ns,
    )


def _diagnostic(result: _EventResult) -> DomainErrorData:
    assert result.reason is not None
    missing = result.status == "missing_input"
    return DomainErrorData(
        error_code=f"anchor.o11.{result.reason}",
        severity=ErrorSeverity.WARNING,
        recoverable=True,
        message=(
            f"O11 event {result.opportunity.event.event_id} could not produce response evidence: "
            f"{result.reason}"
        ),
        field_or_path=("streams.U.samples" if missing else "execution_plan.entries.O11"),
        node_or_anchor_id="O11",
        remediation=(
            "Provide native U rows in the declared response span."
            if missing
            else "Bind the event to compatible control mappings, phase, and U contracts."
        ),
        diagnostics={"event_id": result.opportunity.event.event_id, "reason": result.reason},
    )


def _breakdown(result: _EventResult) -> AnchorBreakdownMeasurement:
    diagnostics = () if result.status == "computed" else (_diagnostic(result),)
    override = (
        ClassificationOverride(
            code="response_missed",
            details={
                "event_id": result.opportunity.event.event_id,
                "wrong_direction": result.wrong_direction,
                "observation_end_t_ns": result.opportunity.observation_end_t_ns,
            },
        )
        if result.missed
        else None
    )
    raw_metrics: dict[str, MetricValue] = {
        "observation-duration": MetricValue(
            scalar_kind="integer",
            value=result.opportunity.observation_end_t_ns - result.opportunity.event.t_ns,
            unit="ns",
        ),
        "channel-count": MetricValue(
            scalar_kind="integer", value=len(result.channels), unit="count"
        ),
    }
    if result.latency_ms is not None:
        raw_metrics["disturbance_latency"] = MetricValue(
            scalar_kind="float", value=result.latency_ms, unit="ms"
        )
    if result.observed_wait_ms is not None:
        raw_metrics["observed_wait"] = MetricValue(
            scalar_kind="float", value=result.observed_wait_ms, unit="ms"
        )
    return AnchorBreakdownMeasurement(
        breakdown_id=result.opportunity.event.event_id,
        calculation_status=AnchorCalculationStatusV2(result.status),
        primary_value=(
            MetricValue(scalar_kind="float", value=result.latency_ms, unit="ms")
            if result.latency_ms is not None
            else None
        ),
        primary_value_reason="response_missed" if result.missed else None,
        raw_metrics=raw_metrics,
        classification_override_candidate=override,
        trace=ComputationTrace(
            sample_count=result.sample_count,
            source_start_t_ns=result.source_start_t_ns,
            source_end_t_ns=result.source_end_t_ns,
            analysis_start_t_ns=result.opportunity.event.t_ns,
            analysis_end_t_ns=result.opportunity.observation_end_t_ns,
            grid_id=None,
            window_ids=(result.opportunity.window.window_id,),
            interpolation_method="trailing-causal-median-20ms-v1",
            matching_method="earliest-any-mapped-correct-v1",
            diagnostics=diagnostics,
        ),
        diagnostics=diagnostics,
    )


def _artifact_payload(
    definition: AnchorPluginDefinition,
    results: tuple[_EventResult, ...],
) -> TabularArtifactPayload | None:
    computed = tuple(item for item in results if item.status == "computed")
    if not computed:
        return None
    rows: list[dict[str, object]] = []
    for result in computed:
        for channel in result.channels:
            selected, selected_correct = channel.selected_run
            rows.append(
                {
                    "event_id": result.opportunity.event.event_id,
                    "channel_id": channel.channel_id,
                    "onset_t_ns": None if selected is None else selected.onset_t_ns,
                    "latency_ms": cast(float, result.observed_wait_ms)
                    if result.missed
                    else cast(float, result.latency_ms),
                    "correct_sign": selected_correct,
                    "missed": result.missed,
                }
            )
    ordered = sorted(
        rows,
        key=lambda row: (cast(str, row["event_id"]), cast(str, row["channel_id"])),
    )
    recipe = definition.artifact_recipes[0]
    frame = pl.DataFrame(
        {
            "event_id": pl.Series(
                "event_id", [row["event_id"] for row in ordered], dtype=pl.String
            ),
            "channel_id": pl.Series(
                "channel_id", [row["channel_id"] for row in ordered], dtype=pl.String
            ),
            "onset_t_ns": pl.Series(
                "onset_t_ns", [row["onset_t_ns"] for row in ordered], dtype=pl.Int64
            ),
            "latency_ms": pl.Series(
                "latency_ms", [row["latency_ms"] for row in ordered], dtype=pl.Float64
            ),
            "correct_sign": pl.Series(
                "correct_sign", [row["correct_sign"] for row in ordered], dtype=pl.Boolean
            ),
            "missed": pl.Series("missed", [row["missed"] for row in ordered], dtype=pl.Boolean),
        }
    )
    return TabularArtifactPayload(
        schema_id=recipe.schema_id,
        schema_descriptor=recipe.schema_descriptor,
        frame=frame,
        order_keys=("event_id", "channel_id"),
        artifact_kind=recipe.kind,
        grid_hash=None,
        start_t_ns=min(item.opportunity.event.t_ns for item in computed),
        end_t_ns=max(item.opportunity.observation_end_t_ns for item in computed),
    )


def _empty_measurement(
    status: AnchorCalculationStatusV2,
    reason: str,
    diagnostics: tuple[DomainErrorData, ...] = (),
) -> AnchorMeasurement:
    return AnchorMeasurement(
        anchor_id="O11",
        calculation_status=status,
        primary_value=None,
        primary_value_reason=None,
        raw_metrics={"event-count": MetricValue(scalar_kind="integer", value=0, unit="count")},
        phase_results=(),
        event_results=(),
        classification_override_candidate=None,
        source_windows=(),
        derived_artifacts=(),
        trace=ComputationTrace(
            sample_count=0,
            source_start_t_ns=None,
            source_end_t_ns=None,
            analysis_start_t_ns=None,
            analysis_end_t_ns=None,
            grid_id=None,
            window_ids=(),
            interpolation_method="trailing-causal-median-v1",
            matching_method=reason,
            diagnostics=diagnostics,
        ),
        diagnostics=diagnostics,
    )


class O11DisturbanceLatencyPlugin:
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
        parsed = _parameters(parameters)
        if not isinstance(temporal_recipe, Mapping):
            raise TypeError("temporal_recipe must be a mapping")
        if temporal_recipe.get("window_policy") != "bound-disturbance-response-v1":
            raise ValueError("O11 requires bound-disturbance-response-v1")
        prefix = _strict_string(temporal_recipe.get("window_id_prefix"), "window_id_prefix")
        event_ids = _strict_strings(temporal_recipe.get("event_ids"), "event_ids", allow_empty=True)
        phases = _phase_bindings(temporal_recipe, context.session_window.end_t_ns)
        table_role = _strict_string(temporal_recipe.get("table_role"), "table_role")
        timestamp_column = _strict_string(
            temporal_recipe.get("timestamp_column"), "timestamp_column"
        )
        in_session_column = _strict_string(
            temporal_recipe.get("in_session_column"), "in_session_column"
        )
        stable_keys = _strict_strings(temporal_recipe.get("stable_keys"), "stable_keys")
        gap_threshold_ns = _strict_int(temporal_recipe.get("gap_threshold_ns"), "gap_threshold_ns")
        if not event_ids:
            return _empty_measurement(
                AnchorCalculationStatusV2.NOT_APPLICABLE,
                "no-disturbance-opportunity-v1",
            )
        raw_events = context.semantic_scope.values.get("semantic.events")
        raw_mappings = context.semantic_scope.values.get("semantic.control_mappings")
        if isinstance(raw_events, (str, bytes)) or not isinstance(raw_events, Sequence):
            raise ValueError("semantic.events must be an ordered array")
        if isinstance(raw_mappings, (str, bytes)) or not isinstance(raw_mappings, Sequence):
            raise ValueError("semantic.control_mappings must be an ordered array")
        events = tuple(SemanticEvent.model_validate(item) for item in raw_events)
        mappings = tuple(ControlEffectMapping.model_validate(item) for item in raw_mappings)
        event_by_id = {item.event_id: item for item in events}
        mapping_by_id = {item.control_mapping_id: item for item in mappings}
        if len(event_by_id) != len(events) or len(mapping_by_id) != len(mappings):
            raise ValueError("semantic event and control-mapping IDs must be unique")
        if any(event_id not in event_by_id for event_id in event_ids):
            raise ValueError("O11 event projection is incomplete")
        phase_by_id = {item.phase_id: item for item in phases}
        u_view = context.streams.get("U")
        u_table = None if u_view is None else u_view.tables.get(table_role)
        contract = _input_contract(context, table_role)
        prepared_by_phase = {
            phase.phase_id: _prepare_phase(
                u_table=u_table,
                u_aligned_schema_id=None if u_view is None else u_view.aligned_schema_id,
                contract=contract,
                binding=phase,
                timestamp_column=timestamp_column,
                in_session_column=in_session_column,
                stable_keys=stable_keys,
                gap_threshold_ns=gap_threshold_ns,
            )
            for phase in phases
        }
        opportunities: list[_Opportunity] = []
        pre_results: list[_EventResult] = []
        for event_id in event_ids:
            event = event_by_id[event_id]
            phase = phase_by_id.get(event.phase_id or "")
            if phase is None or not phase.start_t_ns <= event.t_ns < phase.end_t_ns:
                fallback_phase = phases[0]
                observation_end = min(
                    event.t_ns + parsed.response_horizon_ns,
                    context.session_window.end_t_ns,
                )
                if observation_end <= event.t_ns:
                    raise ValueError("O11 event must precede the session end")
                opportunity = _Opportunity(
                    event,
                    fallback_phase,
                    observation_end,
                    SourceWindowV2(
                        window_id=f"{prefix}-{event.event_id}",
                        start_t_ns=event.t_ns,
                        end_t_ns=observation_end,
                        phase_id=event.phase_id,
                        event_id=event.event_id,
                        include_session_terminal_point=observation_end
                        == context.session_window.end_t_ns,
                    ),
                )
                pre_results.append(
                    _failed_result(
                        "not_computable",
                        "event-phase-binding-missing",
                        opportunity,
                        prepared_by_phase[fallback_phase.phase_id],
                    )
                )
                continue
            observation_end = clip_observation_end(
                onset_t_ns=event.t_ns,
                horizon_ns=parsed.response_horizon_ns,
                session_end_t_ns=context.session_window.end_t_ns,
                phase_end_t_ns=phase.end_t_ns,
                opportunity_end_t_ns=event.opportunity_end_t_ns,
            )
            opportunities.append(
                _Opportunity(
                    event,
                    phase,
                    observation_end,
                    SourceWindowV2(
                        window_id=f"{prefix}-{event.event_id}",
                        start_t_ns=event.t_ns,
                        end_t_ns=observation_end,
                        phase_id=phase.phase_id,
                        event_id=event.event_id,
                        include_session_terminal_point=observation_end
                        == context.session_window.end_t_ns,
                    ),
                )
            )
        results = tuple(pre_results) + tuple(
            _event_result(
                opportunity=opportunity,
                prepared_phase=prepared_by_phase[opportunity.phase.phase_id],
                mapping_by_id=mapping_by_id,
                contract=contract,
                parameters=parsed,
            )
            for opportunity in opportunities
        )
        results = tuple(
            sorted(
                results,
                key=lambda item: (
                    item.opportunity.event.t_ns,
                    item.opportunity.event.event_id,
                ),
            )
        )
        breakdowns = tuple(_breakdown(item) for item in results)
        noncomputed = tuple(
            AnchorCalculationStatusV2(item.status) for item in results if item.status != "computed"
        )
        session_status = (
            max(noncomputed, key=_STATUS_PRIORITY.__getitem__)
            if noncomputed
            else AnchorCalculationStatusV2.COMPUTED
        )
        computed = tuple(item for item in results if item.status == "computed")
        missed = tuple(item for item in computed if item.missed)
        raw_metrics: dict[str, MetricValue] = {
            "event-count": MetricValue(scalar_kind="integer", value=len(results), unit="count"),
            "computed-event-count": MetricValue(
                scalar_kind="integer", value=len(computed), unit="count"
            ),
            "missed-event-count": MetricValue(
                scalar_kind="integer", value=len(missed), unit="count"
            ),
            "wrong-direction-event-count": MetricValue(
                scalar_kind="integer",
                value=sum(item.wrong_direction for item in computed),
                unit="count",
            ),
        }
        primary = None
        primary_reason = None
        session_override = None
        if session_status is AnchorCalculationStatusV2.COMPUTED:
            if missed:
                primary_reason = "response_missed"
                raw_metrics["observed_wait"] = MetricValue(
                    scalar_kind="float",
                    value=max(cast(float, item.observed_wait_ms) for item in missed),
                    unit="ms",
                )
                session_override = ClassificationOverride(
                    code="response_missed",
                    details={
                        "missed_event_ids": [item.opportunity.event.event_id for item in missed],
                        "wrong_direction_event_ids": [
                            item.opportunity.event.event_id
                            for item in missed
                            if item.wrong_direction
                        ],
                    },
                )
            else:
                worst = max(cast(float, item.latency_ms) for item in computed)
                primary = MetricValue(scalar_kind="float", value=worst, unit="ms")
                raw_metrics["disturbance_latency"] = MetricValue(
                    scalar_kind="float", value=worst, unit="ms"
                )
        diagnostics = tuple(
            diagnostic for breakdown in breakdowns for diagnostic in breakdown.diagnostics
        )
        payload = _artifact_payload(self._definition, results)
        derived_artifacts = (
            () if payload is None else (artifacts.stage_table("response-events", payload),)
        )
        windows = tuple(item.opportunity.window for item in results)
        source_starts = tuple(
            item.source_start_t_ns for item in results if item.source_start_t_ns is not None
        )
        source_ends = tuple(
            item.source_end_t_ns for item in results if item.source_end_t_ns is not None
        )
        trace = ComputationTrace(
            sample_count=sum(item.sample_count for item in results),
            source_start_t_ns=min(source_starts) if source_starts else None,
            source_end_t_ns=max(source_ends) if source_ends else None,
            analysis_start_t_ns=min(
                (item.opportunity.event.t_ns for item in results), default=None
            ),
            analysis_end_t_ns=max(
                (item.opportunity.observation_end_t_ns for item in results), default=None
            ),
            grid_id=None,
            window_ids=tuple(item.window_id for item in windows),
            interpolation_method="trailing-causal-median-v1",
            matching_method="earliest-any-mapped-correct-v1",
            diagnostics=diagnostics,
        )
        return AnchorMeasurement(
            anchor_id="O11",
            calculation_status=session_status,
            primary_value=primary,
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


def create_plugin() -> O11DisturbanceLatencyPlugin:
    return O11DisturbanceLatencyPlugin()


__all__ = ["O11DisturbanceLatencyPlugin", "create_plugin"]
