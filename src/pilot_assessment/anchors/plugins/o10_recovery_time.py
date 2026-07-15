"""O10 Recovery Time production plugin."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from itertools import pairwise
from typing import Literal, cast

import polars as pl
from pydantic import JsonValue

from pilot_assessment.anchors.catalog import load_packaged_catalog
from pilot_assessment.anchors.primitives.events import (
    CausalBooleanInterval,
    clip_boolean_intervals,
    clip_observation_end,
    confirmed_true_runs,
)
from pilot_assessment.anchors.protocols import (
    AnchorArtifactEmitter,
    AnchorPluginContext,
    ResolvedDependencies,
    TabularArtifactPayload,
)
from pilot_assessment.anchors.temporal import reconstruct_point_support
from pilot_assessment.contracts.anchor_execution import (
    AnchorPluginDefinition,
    EnvelopeDefinition,
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

_NANOSECONDS_PER_SECOND = 1_000_000_000
_NUMERIC_DTYPES = {"i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64", "f32", "f64"}
_STATUS_PRIORITY = {
    AnchorCalculationStatusV2.NOT_COMPUTABLE: 0,
    AnchorCalculationStatusV2.MISSING_INPUT: 1,
    AnchorCalculationStatusV2.DEPENDENCY_MISSING: 2,
    AnchorCalculationStatusV2.EXTRACTOR_ERROR: 3,
}
_TimelineStatus = Literal["computed", "missing_input", "not_computable"]


def _definition() -> AnchorPluginDefinition:
    catalog_entry = next(
        entry for entry in load_packaged_catalog().entries if entry.anchor_id == "O10"
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


def _strict_int(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be a strict integer of at least {minimum}")
    return value


def _strict_string(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


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


def _typed_sequence(
    value: object,
    model_type: type[SemanticEvent] | type[EnvelopeDefinition],
    label: str,
) -> tuple[SemanticEvent | EnvelopeDefinition, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{label} must be an ordered array")
    return tuple(model_type.model_validate(item) for item in value)


@dataclass(frozen=True, slots=True)
class _PhaseBinding:
    phase_id: str
    start_t_ns: int
    end_t_ns: int
    include_session_terminal_point: bool
    envelope_id: str


def _phase_bindings(
    temporal_recipe: Mapping[str, JsonValue], session_end_t_ns: int
) -> tuple[_PhaseBinding, ...]:
    raw = temporal_recipe.get("phase_bindings")
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise ValueError("temporal_recipe.phase_bindings must be an ordered array")
    bindings: list[_PhaseBinding] = []
    expected_keys = {
        "phase_id",
        "start_t_ns",
        "end_t_ns",
        "include_session_terminal_point",
        "envelope_id",
    }
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping) or set(item) != expected_keys:
            raise ValueError(f"phase binding {index} must use the exact five-key contract")
        typed_item = cast(Mapping[str, object], item)
        phase_id = _strict_string(typed_item["phase_id"], f"phase_bindings[{index}].phase_id")
        start = _strict_int(typed_item["start_t_ns"], f"phase_bindings[{index}].start_t_ns")
        end = _strict_int(typed_item["end_t_ns"], f"phase_bindings[{index}].end_t_ns", minimum=1)
        terminal = typed_item["include_session_terminal_point"]
        envelope_id = _strict_string(
            typed_item["envelope_id"], f"phase_bindings[{index}].envelope_id"
        )
        if type(terminal) is not bool:
            raise ValueError("include_session_terminal_point must be a strict boolean")
        if end <= start or end > session_end_t_ns:
            raise ValueError("phase binding must be a positive span within the session")
        if terminal and end != session_end_t_ns:
            raise ValueError("terminal phase binding must end at the session end")
        bindings.append(_PhaseBinding(phase_id, start, end, terminal, envelope_id))
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
        if item.modality.value == "X" and item.table_role == table_role
    )
    if len(matches) > 1:
        raise ValueError("input contracts contain duplicate X table roles")
    return matches[0] if matches else None


@dataclass(frozen=True, slots=True)
class _StateTimeline:
    status: _TimelineStatus
    reason: str | None
    phase: _PhaseBinding
    envelope_id: str
    desired: tuple[CausalBooleanInterval, ...]
    outside_adequate: tuple[CausalBooleanInterval, ...]
    sample_count: int
    source_start_t_ns: int | None
    source_end_t_ns: int | None


def _failed_timeline(
    status: _TimelineStatus,
    reason: str,
    phase: _PhaseBinding,
    envelope_id: str,
) -> _StateTimeline:
    return _StateTimeline(status, reason, phase, envelope_id, (), (), 0, None, None)


def _timeline(
    *,
    x_table: pl.DataFrame | None,
    x_aligned_schema_id: str | None,
    contract: ResolvedInputTableContract | None,
    phase: _PhaseBinding,
    envelope: EnvelopeDefinition,
    table_role: str,
    timestamp_column: str,
    in_session_column: str,
    stable_keys: tuple[str, ...],
    gap_threshold_ns: int,
) -> _StateTimeline:
    if contract is None or (
        x_aligned_schema_id is not None and contract.stream_aligned_schema_id != x_aligned_schema_id
    ):
        return _failed_timeline(
            "not_computable", "input-contract-mismatch", phase, envelope.envelope_id
        )
    if x_table is None:
        return _failed_timeline("missing_input", "no-temporal-support", phase, envelope.envelope_id)
    fields = {field.field_name: field for field in contract.fields}
    required = (timestamp_column, in_session_column, *stable_keys)
    if any(name not in fields or name not in x_table.columns for name in required):
        return _failed_timeline(
            "not_computable", "temporal-field-missing", phase, envelope.envelope_id
        )
    for limit in envelope.axis_limits:
        field = fields.get(limit.metric_id)
        if (
            field is None
            or limit.metric_id not in x_table.columns
            or field.dtype_id not in _NUMERIC_DTYPES
            or field.unit != limit.unit
        ):
            return _failed_timeline(
                "not_computable", "envelope-contract-mismatch", phase, envelope.envelope_id
            )

    end_operator = (
        pl.col(timestamp_column) <= phase.end_t_ns
        if phase.include_session_terminal_point
        else pl.col(timestamp_column) < phase.end_t_ns
    )
    active = x_table.filter(
        (pl.col(timestamp_column) >= phase.start_t_ns) & end_operator & pl.col(in_session_column)
    ).sort([timestamp_column, *stable_keys], maintain_order=True)
    if active.is_empty():
        return _failed_timeline("missing_input", "no-temporal-support", phase, envelope.envelope_id)
    support = reconstruct_point_support(
        active,
        timestamp_column=timestamp_column,
        stable_keys=stable_keys,
        in_session_column=in_session_column,
        gap_threshold_ns=gap_threshold_ns,
        semantic_end_t_ns=phase.end_t_ns,
    )
    if support.observed_duration_ns == 0:
        return _failed_timeline("missing_input", "no-temporal-support", phase, envelope.envelope_id)
    source_ids = active[stable_keys[0]].to_list()
    if any(type(value) is not int or value < 0 for value in source_ids):
        return _failed_timeline(
            "not_computable", "source-row-id-invalid", phase, envelope.envelope_id
        )
    desired_by_row: list[bool] = []
    adequate_by_row: list[bool] = []
    for row in active.iter_rows(named=True):
        desired = True
        adequate = True
        for limit in envelope.axis_limits:
            value = row[limit.metric_id]
            if value is None:
                return _failed_timeline(
                    "missing_input", "metric-value-missing", phase, envelope.envelope_id
                )
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return _failed_timeline(
                    "not_computable", "metric-value-nonnumeric", phase, envelope.envelope_id
                )
            numeric = float(value)
            if not math.isfinite(numeric):
                return _failed_timeline(
                    "not_computable", "metric-value-nonfinite", phase, envelope.envelope_id
                )
            desired = desired and abs(numeric) <= limit.desired_abs_max
            adequate = adequate and abs(numeric) <= limit.adequate_abs_max
        desired_by_row.append(desired)
        adequate_by_row.append(adequate)
    desired_intervals = tuple(
        CausalBooleanInterval(
            interval.start_t_ns,
            interval.end_t_ns,
            int(source_ids[interval.source_row_index]),
            desired_by_row[interval.source_row_index],
        )
        for interval in support.intervals
    )
    outside_intervals = tuple(
        CausalBooleanInterval(
            interval.start_t_ns,
            interval.end_t_ns,
            int(source_ids[interval.source_row_index]),
            not adequate_by_row[interval.source_row_index],
        )
        for interval in support.intervals
    )
    times = cast(list[int], active[timestamp_column].to_list())
    return _StateTimeline(
        "computed",
        None,
        phase,
        envelope.envelope_id,
        desired_intervals,
        outside_intervals,
        active.height,
        min(times),
        max(times),
    )


@dataclass(frozen=True, slots=True)
class _Opportunity:
    event_id: str
    onset_t_ns: int
    search_start_t_ns: int
    observation_end_t_ns: int
    phase: _PhaseBinding
    envelope_id: str

    @property
    def window(self) -> SourceWindowV2:
        identity = f"{self.event_id}\0{self.onset_t_ns}\0{self.observation_end_t_ns}".encode()
        return SourceWindowV2(
            window_id=f"o10-window-{sha256(identity).hexdigest()[:24]}",
            start_t_ns=self.onset_t_ns,
            end_t_ns=self.observation_end_t_ns,
            phase_id=self.phase.phase_id,
            event_id=self.event_id,
            include_session_terminal_point=False,
        )


@dataclass(frozen=True, slots=True)
class _RecoveryResult:
    status: _TimelineStatus
    reason: str | None
    opportunity: _Opportunity
    missed: bool
    latency_s: float | None
    observed_wait_s: float | None
    recovered_t_ns: int | None
    recovery_confirmed_t_ns: int | None
    observed_support_duration_ns: int
    sample_count: int
    source_start_t_ns: int | None
    source_end_t_ns: int | None
    gap_count: int
    max_gap_ns: int | None


def _event_phase(event: SemanticEvent, phases: tuple[_PhaseBinding, ...]) -> _PhaseBinding:
    if event.phase_id is not None:
        matches = tuple(item for item in phases if item.phase_id == event.phase_id)
    else:
        matches = tuple(item for item in phases if item.start_t_ns <= event.t_ns < item.end_t_ns)
    if len(matches) != 1:
        raise ValueError(f"event {event.event_id} must bind to exactly one phase")
    phase = matches[0]
    if not phase.start_t_ns <= event.t_ns < phase.end_t_ns:
        raise ValueError(f"event {event.event_id} lies outside its bound phase")
    return phase


def _marker_opportunities(
    *,
    events: tuple[SemanticEvent, ...],
    marker_ids: tuple[str, ...],
    phases: tuple[_PhaseBinding, ...],
    envelope_ids: set[str],
    horizon_ns: int,
    session_end_t_ns: int,
) -> tuple[_Opportunity, ...]:
    event_by_id = {item.event_id: item for item in events}
    if any(event_id not in event_by_id for event_id in marker_ids):
        raise ValueError("marker_event_ids reference an unknown semantic event")
    opportunities: list[_Opportunity] = []
    for event_id in marker_ids:
        event = event_by_id[event_id]
        phase = _event_phase(event, phases)
        envelope_id = event.envelope_id or phase.envelope_id
        if event.envelope_id is not None and event.envelope_id != phase.envelope_id:
            raise ValueError("event and phase envelope bindings disagree")
        if envelope_id not in envelope_ids:
            raise ValueError("event recovery envelope is not declared")
        end = clip_observation_end(
            onset_t_ns=event.t_ns,
            horizon_ns=horizon_ns,
            session_end_t_ns=session_end_t_ns,
            phase_end_t_ns=phase.end_t_ns,
            opportunity_end_t_ns=event.opportunity_end_t_ns,
        )
        opportunities.append(
            _Opportunity(event.event_id, event.t_ns, event.t_ns, end, phase, envelope_id)
        )
    return tuple(sorted(opportunities, key=lambda item: (item.onset_t_ns, item.event_id)))


def _implicit_opportunities(
    *,
    timelines: Mapping[tuple[str, str], _StateTimeline],
    confirmation_ns: int,
    horizon_ns: int,
    session_end_t_ns: int,
) -> tuple[_Opportunity, ...]:
    opportunities: list[_Opportunity] = []
    for key in sorted(timelines):
        timeline = timelines[key]
        if timeline.status != "computed":
            continue
        for run in confirmed_true_runs(
            timeline.outside_adequate,
            minimum_duration_ns=confirmation_ns,
        ):
            if run.onset_t_ns >= min(timeline.phase.end_t_ns, session_end_t_ns):
                continue
            event_id = (
                f"o10-exit-{run.onset_t_ns:019d}-"
                f"{sha256(timeline.phase.phase_id.encode('utf-8')).hexdigest()[:12]}"
            )
            opportunities.append(
                _Opportunity(
                    event_id=event_id,
                    onset_t_ns=run.onset_t_ns,
                    search_start_t_ns=run.confirmation_t_ns,
                    observation_end_t_ns=clip_observation_end(
                        onset_t_ns=run.onset_t_ns,
                        horizon_ns=horizon_ns,
                        session_end_t_ns=session_end_t_ns,
                        phase_end_t_ns=timeline.phase.end_t_ns,
                    ),
                    phase=timeline.phase,
                    envelope_id=timeline.envelope_id,
                )
            )
    return tuple(sorted(opportunities, key=lambda item: (item.onset_t_ns, item.event_id)))


def _result_from_timeline(
    timeline: _StateTimeline,
    opportunity: _Opportunity,
    desired_hold_ns: int,
) -> _RecoveryResult:
    if timeline.status != "computed":
        return _RecoveryResult(
            timeline.status,
            timeline.reason,
            opportunity,
            False,
            None,
            None,
            None,
            None,
            0,
            0,
            None,
            None,
            0,
            None,
        )
    observation = clip_boolean_intervals(
        timeline.desired,
        start_t_ns=opportunity.onset_t_ns,
        end_t_ns=opportunity.observation_end_t_ns,
    )
    observed_duration = sum(item.end_t_ns - item.start_t_ns for item in observation)
    if observed_duration == 0:
        return _RecoveryResult(
            "missing_input",
            "no-temporal-support",
            opportunity,
            False,
            None,
            None,
            None,
            None,
            0,
            0,
            None,
            None,
            0,
            None,
        )
    search = (
        ()
        if opportunity.search_start_t_ns >= opportunity.observation_end_t_ns
        else clip_boolean_intervals(
            timeline.desired,
            start_t_ns=opportunity.search_start_t_ns,
            end_t_ns=opportunity.observation_end_t_ns,
        )
    )
    runs = confirmed_true_runs(search, minimum_duration_ns=desired_hold_ns)
    recovery = runs[0] if runs else None
    source_ids = tuple(dict.fromkeys(item.source_row_id for item in observation))
    positive = tuple(item for item in observation if item.end_t_ns > item.start_t_ns)
    gaps = tuple(
        current.start_t_ns - previous.end_t_ns
        for previous, current in pairwise(positive)
        if current.start_t_ns > previous.end_t_ns
    )
    missed = recovery is None
    return _RecoveryResult(
        "computed",
        None,
        opportunity,
        missed,
        None
        if missed
        else (recovery.onset_t_ns - opportunity.onset_t_ns) / _NANOSECONDS_PER_SECOND,
        (opportunity.observation_end_t_ns - opportunity.onset_t_ns) / _NANOSECONDS_PER_SECOND
        if missed
        else None,
        None if missed else recovery.onset_t_ns,
        None if missed else recovery.confirmation_t_ns,
        observed_duration,
        len(source_ids),
        min((item.start_t_ns for item in observation), default=None),
        max((item.start_t_ns for item in observation), default=None),
        len(gaps),
        max(gaps) if gaps else None,
    )


def _diagnostic(result: _RecoveryResult) -> DomainErrorData:
    assert result.reason is not None
    missing = result.status == "missing_input"
    return DomainErrorData(
        error_code=f"anchor.o10.{result.reason}",
        severity=ErrorSeverity.WARNING,
        recoverable=True,
        message=(
            f"O10 event {result.opportunity.event_id} could not produce recovery evidence: "
            f"{result.reason}"
        ),
        field_or_path=("streams.X.samples" if missing else "execution_plan.entries.O10"),
        node_or_anchor_id="O10",
        remediation=(
            "Provide native X rows in the declared recovery span."
            if missing
            else "Bind compatible phase, envelope, temporal fields, and X metric contracts."
        ),
        diagnostics={"event_id": result.opportunity.event_id, "reason": result.reason},
    )


def _event_metrics(result: _RecoveryResult) -> dict[str, MetricValue]:
    metrics = {
        "observation-duration": MetricValue(
            scalar_kind="integer",
            value=result.opportunity.observation_end_t_ns - result.opportunity.onset_t_ns,
            unit="ns",
        ),
        "observed-support-duration": MetricValue(
            scalar_kind="integer", value=result.observed_support_duration_ns, unit="ns"
        ),
        "sample-count": MetricValue(scalar_kind="integer", value=result.sample_count, unit="count"),
    }
    if result.latency_s is not None:
        metrics["recovery_time"] = MetricValue(
            scalar_kind="float", value=result.latency_s, unit="s"
        )
    if result.observed_wait_s is not None:
        metrics["observed_wait"] = MetricValue(
            scalar_kind="float", value=result.observed_wait_s, unit="s"
        )
    if result.recovered_t_ns is not None and result.recovery_confirmed_t_ns is not None:
        metrics["recovery-hold-start-t-ns"] = MetricValue(
            scalar_kind="integer", value=result.recovered_t_ns, unit="ns"
        )
        metrics["recovery-hold-confirmed-t-ns"] = MetricValue(
            scalar_kind="integer", value=result.recovery_confirmed_t_ns, unit="ns"
        )
    return metrics


def _trace(
    result: _RecoveryResult,
    diagnostics: tuple[DomainErrorData, ...],
) -> ComputationTrace:
    return ComputationTrace(
        sample_count=result.sample_count,
        source_start_t_ns=result.source_start_t_ns,
        source_end_t_ns=result.source_end_t_ns,
        analysis_start_t_ns=result.opportunity.onset_t_ns,
        analysis_end_t_ns=result.opportunity.observation_end_t_ns,
        grid_id=None,
        window_ids=(result.opportunity.window.window_id,),
        interpolation_method="native-left-hold-v1",
        matching_method="marker-or-confirmed-adequate-exit-recovery-v1",
        diagnostics=diagnostics,
    )


def _breakdown(result: _RecoveryResult) -> AnchorBreakdownMeasurement:
    status = AnchorCalculationStatusV2(result.status)
    diagnostics = () if result.status == "computed" else (_diagnostic(result),)
    override = (
        ClassificationOverride(
            code="recovery_missed",
            details={
                "event_id": result.opportunity.event_id,
                "observation_end_t_ns": result.opportunity.observation_end_t_ns,
            },
        )
        if result.missed
        else None
    )
    return AnchorBreakdownMeasurement(
        breakdown_id=result.opportunity.event_id,
        calculation_status=status,
        primary_value=(
            MetricValue(scalar_kind="float", value=result.latency_s, unit="s")
            if result.latency_s is not None
            else None
        ),
        primary_value_reason="recovery_missed" if result.missed else None,
        raw_metrics=_event_metrics(result),
        classification_override_candidate=override,
        trace=_trace(result, diagnostics),
        diagnostics=diagnostics,
    )


def _artifact_payload(
    definition: AnchorPluginDefinition,
    results: tuple[_RecoveryResult, ...],
) -> TabularArtifactPayload | None:
    computed = tuple(item for item in results if item.status == "computed")
    if not computed:
        return None
    recipe = definition.artifact_recipes[0]
    ordered = tuple(
        sorted(computed, key=lambda item: (item.opportunity.event_id, item.opportunity.onset_t_ns))
    )
    frame = pl.DataFrame(
        {
            "event_id": pl.Series(
                "event_id", [item.opportunity.event_id for item in ordered], dtype=pl.String
            ),
            "onset_t_ns": pl.Series(
                "onset_t_ns", [item.opportunity.onset_t_ns for item in ordered], dtype=pl.Int64
            ),
            "recovered_t_ns": pl.Series(
                "recovered_t_ns", [item.recovered_t_ns for item in ordered], dtype=pl.Int64
            ),
            "latency_ms": pl.Series(
                "latency_ms",
                [
                    (
                        cast(float, item.observed_wait_s)
                        if item.missed
                        else cast(float, item.latency_s)
                    )
                    * 1000.0
                    for item in ordered
                ],
                dtype=pl.Float64,
            ),
            "missed": pl.Series("missed", [item.missed for item in ordered], dtype=pl.Boolean),
        }
    )
    return TabularArtifactPayload(
        schema_id=recipe.schema_id,
        schema_descriptor=recipe.schema_descriptor,
        frame=frame,
        order_keys=("event_id", "onset_t_ns"),
        artifact_kind=recipe.kind,
        grid_hash=None,
        start_t_ns=min(item.opportunity.onset_t_ns for item in ordered),
        end_t_ns=max(item.opportunity.observation_end_t_ns for item in ordered),
    )


def _empty_measurement(
    status: AnchorCalculationStatusV2,
    reason: str,
    diagnostics: tuple[DomainErrorData, ...] = (),
) -> AnchorMeasurement:
    return AnchorMeasurement(
        anchor_id="O10",
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
            interpolation_method="native-left-hold-v1",
            matching_method=reason,
            diagnostics=diagnostics,
        ),
        diagnostics=diagnostics,
    )


class O10RecoveryTimePlugin:
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
        expected_parameters = {
            "adequate_exit_confirmation_ns",
            "desired_hold_ns",
            "recovery_horizon_ns",
        }
        if not isinstance(parameters, Mapping) or set(parameters) != expected_parameters:
            raise ValueError("O10 v0.1 parameters require the exact three-key contract")
        confirmation_ns = _strict_int(
            parameters["adequate_exit_confirmation_ns"], "adequate_exit_confirmation_ns"
        )
        desired_hold_ns = _strict_int(parameters["desired_hold_ns"], "desired_hold_ns")
        horizon_ns = _strict_int(
            parameters["recovery_horizon_ns"], "recovery_horizon_ns", minimum=1
        )
        if not isinstance(temporal_recipe, Mapping):
            raise TypeError("temporal_recipe must be a mapping")
        if temporal_recipe.get("window_policy") != "marker-or-adequate-exit-v1":
            raise ValueError("O10 requires marker-or-adequate-exit-v1")
        session_end = context.session_window.end_t_ns
        phases = _phase_bindings(temporal_recipe, session_end)
        marker_ids = _strict_strings(
            temporal_recipe.get("marker_event_ids"),
            "temporal_recipe.marker_event_ids",
            allow_empty=True,
        )
        table_role = _strict_string(temporal_recipe.get("table_role"), "table_role")
        timestamp_column = _strict_string(
            temporal_recipe.get("timestamp_column"), "timestamp_column"
        )
        in_session_column = _strict_string(
            temporal_recipe.get("in_session_column"), "in_session_column"
        )
        stable_keys = _strict_strings(temporal_recipe.get("stable_keys"), "stable_keys")
        if len(stable_keys) != 1:
            raise ValueError("O10 v0.1 requires exactly one stable row key")
        gap_threshold_ns = _strict_int(temporal_recipe.get("gap_threshold_ns"), "gap_threshold_ns")
        events = cast(
            tuple[SemanticEvent, ...],
            _typed_sequence(
                context.semantic_scope.values.get("semantic.events"),
                SemanticEvent,
                "semantic.events",
            ),
        )
        envelopes = cast(
            tuple[EnvelopeDefinition, ...],
            _typed_sequence(
                context.semantic_scope.values.get("semantic.envelopes"),
                EnvelopeDefinition,
                "semantic.envelopes",
            ),
        )
        envelope_by_id = {item.envelope_id: item for item in envelopes}
        if any(phase.envelope_id not in envelope_by_id for phase in phases):
            raise ValueError("phase binding references an unknown recovery envelope")
        x_view = context.streams.get("X")
        x_table = None if x_view is None else x_view.tables.get(table_role)
        contract = _input_contract(context, table_role)
        timelines = {
            (phase.phase_id, phase.envelope_id): _timeline(
                x_table=x_table,
                x_aligned_schema_id=None if x_view is None else x_view.aligned_schema_id,
                contract=contract,
                phase=phase,
                envelope=envelope_by_id[phase.envelope_id],
                table_role=table_role,
                timestamp_column=timestamp_column,
                in_session_column=in_session_column,
                stable_keys=stable_keys,
                gap_threshold_ns=gap_threshold_ns,
            )
            for phase in phases
        }
        if marker_ids:
            opportunities = _marker_opportunities(
                events=events,
                marker_ids=marker_ids,
                phases=phases,
                envelope_ids=set(envelope_by_id),
                horizon_ns=horizon_ns,
                session_end_t_ns=session_end,
            )
        else:
            failed = tuple(item for item in timelines.values() if item.status != "computed")
            if failed:
                status = max(
                    (AnchorCalculationStatusV2(item.status) for item in failed),
                    key=_STATUS_PRIORITY.__getitem__,
                )
                diagnostic = DomainErrorData(
                    error_code=f"anchor.o10.{failed[0].reason}",
                    severity=ErrorSeverity.WARNING,
                    recoverable=True,
                    message="O10 could not determine whether a recovery opportunity occurred",
                    field_or_path="streams.X.samples",
                    node_or_anchor_id="O10",
                    remediation="Provide native X rows and compatible envelope metric bindings.",
                    diagnostics={"reason": failed[0].reason},
                )
                return _empty_measurement(
                    status, "opportunity-detection-unavailable-v1", (diagnostic,)
                )
            opportunities = _implicit_opportunities(
                timelines=timelines,
                confirmation_ns=confirmation_ns,
                horizon_ns=horizon_ns,
                session_end_t_ns=session_end,
            )
            if not opportunities:
                return _empty_measurement(
                    AnchorCalculationStatusV2.NOT_APPLICABLE,
                    "no-recovery-opportunity-v1",
                )

        results = tuple(
            _result_from_timeline(
                timelines[(item.phase.phase_id, item.envelope_id)],
                item,
                desired_hold_ns,
            )
            for item in opportunities
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
            "event-count": MetricValue(
                scalar_kind="integer", value=len(opportunities), unit="count"
            ),
            "computed-event-count": MetricValue(
                scalar_kind="integer", value=len(computed), unit="count"
            ),
            "missed-event-count": MetricValue(
                scalar_kind="integer", value=len(missed), unit="count"
            ),
        }
        primary = None
        primary_reason = None
        session_override = None
        if session_status is AnchorCalculationStatusV2.COMPUTED:
            if missed:
                primary_reason = "recovery_missed"
                raw_metrics["observed_wait"] = MetricValue(
                    scalar_kind="float",
                    value=max(cast(float, item.observed_wait_s) for item in missed),
                    unit="s",
                )
                session_override = ClassificationOverride(
                    code="recovery_missed",
                    details={"missed_event_ids": [item.opportunity.event_id for item in missed]},
                )
            else:
                worst = max(cast(float, item.latency_s) for item in computed)
                primary = MetricValue(scalar_kind="float", value=worst, unit="s")
                raw_metrics["recovery_time"] = MetricValue(
                    scalar_kind="float", value=worst, unit="s"
                )
        diagnostics = tuple(
            diagnostic for breakdown in breakdowns for diagnostic in breakdown.diagnostics
        )
        payload = _artifact_payload(self._definition, results)
        derived_artifacts = (
            () if payload is None else (artifacts.stage_table("recovery-events", payload),)
        )
        source_starts = tuple(
            item.source_start_t_ns for item in results if item.source_start_t_ns is not None
        )
        source_ends = tuple(
            item.source_end_t_ns for item in results if item.source_end_t_ns is not None
        )
        windows = tuple(item.window for item in opportunities)
        trace = ComputationTrace(
            sample_count=sum(item.sample_count for item in results),
            source_start_t_ns=min(source_starts) if source_starts else None,
            source_end_t_ns=max(source_ends) if source_ends else None,
            analysis_start_t_ns=min((item.onset_t_ns for item in opportunities), default=None),
            analysis_end_t_ns=max(
                (item.observation_end_t_ns for item in opportunities), default=None
            ),
            grid_id=None,
            window_ids=tuple(item.window_id for item in windows),
            interpolation_method="native-left-hold-v1",
            matching_method="marker-or-confirmed-adequate-exit-recovery-v1",
            diagnostics=diagnostics,
        )
        return AnchorMeasurement(
            anchor_id="O10",
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


def create_plugin() -> O10RecoveryTimePlugin:
    return O10RecoveryTimePlugin()


__all__ = ["O10RecoveryTimePlugin", "create_plugin"]
