"""H2 First Fixation Latency production plugin."""

from __future__ import annotations

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
from pilot_assessment.anchors.temporal import SupportInterval, reconstruct_point_support
from pilot_assessment.contracts.anchor_execution import (
    AnchorPluginDefinition,
    AoiDefinition,
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

_FIXATION_SCHEMA = {
    "fixation_id": pl.String,
    "start_t_ns": pl.Int64,
    "end_t_ns": pl.Int64,
    "aoi_id": pl.String,
    "role_id": pl.String,
}
_STATUS_PRIORITY = {
    AnchorCalculationStatusV2.NOT_COMPUTABLE: 0,
    AnchorCalculationStatusV2.MISSING_INPUT: 1,
    AnchorCalculationStatusV2.DEPENDENCY_MISSING: 2,
    AnchorCalculationStatusV2.EXTRACTOR_ERROR: 3,
}


@dataclass(frozen=True, slots=True)
class _Parameters:
    fixation_horizon_ns: int


@dataclass(frozen=True, slots=True)
class _EventBinding:
    event_id: str
    cue_available_t_ns: int
    opportunity_end_t_ns: int | None
    relevant_aoi_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Fixation:
    fixation_id: str
    start_t_ns: int
    end_t_ns: int
    aoi_id: str
    role_id: str


@dataclass(frozen=True, slots=True)
class _EventResult:
    binding: _EventBinding
    event: SemanticEvent | None
    window: SourceWindowV2
    status: AnchorCalculationStatusV2
    reason: str | None
    fixation: _Fixation | None
    latency_ms: float | None
    observed_wait_ms: float | None
    scene_support_duration_ns: int

    @property
    def missed(self) -> bool:
        return self.status is AnchorCalculationStatusV2.COMPUTED and self.fixation is None


def _definition() -> AnchorPluginDefinition:
    catalog_entry = next(
        entry for entry in load_packaged_catalog().entries if entry.anchor_id == "H2"
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


def _strict_strings(
    value: object,
    label: str,
    *,
    allow_empty: bool = False,
    canonical: bool = False,
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{label} must be an ordered string array")
    normalized = tuple(
        _strict_string(item, f"{label}[{index}]") for index, item in enumerate(value)
    )
    if (not normalized and not allow_empty) or len(normalized) != len(set(normalized)):
        raise ValueError(f"{label} must be unique and satisfy its cardinality")
    if canonical and normalized != tuple(sorted(normalized)):
        raise ValueError(f"{label} must use canonical lexical order")
    return normalized


def _parameters(values: Mapping[str, JsonValue]) -> _Parameters:
    if not isinstance(values, Mapping) or set(values) != {"fixation_horizon_ns"}:
        raise ValueError("H2 v0.1 requires the exact fixation_horizon_ns parameter")
    return _Parameters(
        fixation_horizon_ns=_strict_int(
            values["fixation_horizon_ns"], "fixation_horizon_ns", minimum=1
        )
    )


def _event_bindings(temporal_recipe: Mapping[str, JsonValue]) -> tuple[_EventBinding, ...]:
    if temporal_recipe.get("window_policy") != "bound-first-fixation-v1":
        raise ValueError("H2 requires window_policy=bound-first-fixation-v1")
    event_ids = _strict_strings(temporal_recipe.get("event_ids"), "event_ids", allow_empty=True)
    raw = temporal_recipe.get("event_bindings")
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise ValueError("event_bindings must be an ordered array")
    bindings: list[_EventBinding] = []
    expected = {
        "event_id",
        "cue_available_t_ns",
        "opportunity_end_t_ns",
        "relevant_aoi_ids",
    }
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping) or set(item) != expected:
            raise ValueError(f"event_bindings[{index}] must use the exact four-key contract")
        typed = cast(Mapping[str, object], item)
        opportunity = typed["opportunity_end_t_ns"]
        if opportunity is not None:
            opportunity = _strict_int(
                opportunity,
                f"event_bindings[{index}].opportunity_end_t_ns",
                minimum=1,
            )
        binding = _EventBinding(
            event_id=_strict_string(typed["event_id"], f"event_bindings[{index}].event_id"),
            cue_available_t_ns=_strict_int(
                typed["cue_available_t_ns"],
                f"event_bindings[{index}].cue_available_t_ns",
            ),
            opportunity_end_t_ns=opportunity,
            relevant_aoi_ids=_strict_strings(
                typed["relevant_aoi_ids"],
                f"event_bindings[{index}].relevant_aoi_ids",
                allow_empty=True,
                canonical=True,
            ),
        )
        if (
            binding.opportunity_end_t_ns is not None
            and binding.opportunity_end_t_ns <= binding.cue_available_t_ns
        ):
            raise ValueError("event opportunity end must follow cue availability")
        bindings.append(binding)
    normalized = tuple(bindings)
    if tuple(item.event_id for item in normalized) != event_ids:
        raise ValueError("event bindings must exactly match ordered event_ids")
    if normalized != tuple(
        sorted(normalized, key=lambda item: (item.cue_available_t_ns, item.event_id))
    ):
        raise ValueError("event bindings must use canonical temporal order")
    return normalized


def _typed_events(value: object) -> tuple[SemanticEvent, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("semantic.events must be an ordered array")
    events = tuple(SemanticEvent.model_validate(item) for item in value)
    if len(events) != len({item.event_id for item in events}):
        raise ValueError("semantic event IDs must be unique")
    return events


def _typed_aois(value: object) -> tuple[AoiDefinition, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("semantic.aois must be an ordered array")
    aois = tuple(AoiDefinition.model_validate(item) for item in value)
    if len(aois) != len({item.aoi_id for item in aois}):
        raise ValueError("semantic AOI IDs must be unique")
    return aois


def _validate_bound_semantics(
    context: AnchorPluginContext,
    temporal_recipe: Mapping[str, JsonValue],
    bindings: tuple[_EventBinding, ...],
) -> tuple[Mapping[str, SemanticEvent], set[str]]:
    events = _typed_events(context.semantic_scope.values.get("semantic.events"))
    aois = _typed_aois(context.semantic_scope.values.get("semantic.aois"))
    event_by_id = {item.event_id: item for item in events}
    semantic_aoi_ids = {item.aoi_id for item in aois}
    selected_aoi_ids = set(
        _strict_strings(temporal_recipe.get("aoi_ids"), "aoi_ids", canonical=True)
    )
    if selected_aoi_ids != semantic_aoi_ids:
        raise ValueError("H2 aoi_ids must exactly bind the projected AOI inventory")
    for binding in bindings:
        event = event_by_id.get(binding.event_id)
        if event is None:
            continue
        if (
            event.t_ns != binding.cue_available_t_ns
            or event.opportunity_end_t_ns != binding.opportunity_end_t_ns
            or event.relevant_aoi_ids != binding.relevant_aoi_ids
        ):
            raise ValueError(f"H2 event binding {binding.event_id} diverges from semantics")
    return event_by_id, selected_aoi_ids


def _fixations(dependencies: ResolvedDependencies) -> tuple[_Fixation, ...] | None:
    dependency = dependencies.preprocessing.get("fixation-intervals")
    if dependency is None:
        return None
    if not isinstance(dependency.payload, ReadOnlyTabularPayload):
        raise ValueError("H2 requires a tabular fixation-interval dependency")
    frame = dependency.payload.frame
    if frame.schema != _FIXATION_SCHEMA or any(
        frame[column].null_count() for column in frame.columns
    ):
        raise ValueError("H2 fixation dependency has an invalid exact schema")
    ordered = frame.sort(["start_t_ns", "end_t_ns", "fixation_id"], maintain_order=True)
    if not ordered.equals(frame) or frame.select("fixation_id").is_duplicated().any():
        raise ValueError("H2 fixation dependency must use canonical unique order")
    result: list[_Fixation] = []
    for row in frame.iter_rows(named=True):
        start_t_ns = row["start_t_ns"]
        end_t_ns = row["end_t_ns"]
        if (
            type(start_t_ns) is not int
            or type(end_t_ns) is not int
            or start_t_ns < 0
            or end_t_ns <= start_t_ns
        ):
            raise ValueError("H2 fixation dependency requires positive ordered intervals")
        result.append(
            _Fixation(
                fixation_id=cast(str, row["fixation_id"]),
                start_t_ns=start_t_ns,
                end_t_ns=end_t_ns,
                aoi_id=cast(str, row["aoi_id"]),
                role_id=cast(str, row["role_id"]),
            )
        )
    return tuple(result)


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


def _scene_support(context: AnchorPluginContext) -> tuple[SupportInterval, ...] | None:
    scene = context.streams.get("I")
    table = None if scene is None else scene.tables.get("frame_index")
    if table is None:
        return None
    if not {"frame_id", "t_ns", "in_session"} <= set(table.columns):
        return None
    if (
        table.schema["frame_id"] != pl.UInt64
        or table.schema["t_ns"] != pl.Int64
        or table.schema["in_session"] != pl.Boolean
        or any(table[column].null_count() for column in ("frame_id", "t_ns", "in_session"))
    ):
        return None
    times = cast(list[int], table.filter(pl.col("in_session"))["t_ns"].to_list())
    return reconstruct_point_support(
        table,
        timestamp_column="t_ns",
        stable_keys=("frame_id",),
        in_session_column="in_session",
        gap_threshold_ns=_gap_threshold(times),
        semantic_end_t_ns=context.session_window.end_t_ns,
    ).intervals


def _support_duration(
    support: tuple[SupportInterval, ...] | None,
    start_t_ns: int,
    end_t_ns: int,
) -> int:
    if support is None:
        return 0
    return sum(
        max(0, min(item.end_t_ns, end_t_ns) - max(item.start_t_ns, start_t_ns)) for item in support
    )


def _window(
    binding: _EventBinding,
    event: SemanticEvent | None,
    parameters: _Parameters,
    session_end_t_ns: int,
    prefix: str,
) -> SourceWindowV2:
    end_t_ns = min(
        binding.cue_available_t_ns + parameters.fixation_horizon_ns,
        session_end_t_ns,
        binding.opportunity_end_t_ns
        if binding.opportunity_end_t_ns is not None
        else session_end_t_ns,
    )
    if end_t_ns <= binding.cue_available_t_ns:
        raise ValueError("H2 cue must precede its observation end")
    return SourceWindowV2(
        window_id=f"{prefix}-{binding.event_id}",
        start_t_ns=binding.cue_available_t_ns,
        end_t_ns=end_t_ns,
        phase_id=None if event is None else event.phase_id,
        event_id=binding.event_id,
        include_session_terminal_point=end_t_ns == session_end_t_ns,
    )


def _event_result(
    *,
    binding: _EventBinding,
    event: SemanticEvent | None,
    selected_aoi_ids: set[str],
    fixations: tuple[_Fixation, ...] | None,
    streams_present: bool,
    scene_support: tuple[SupportInterval, ...] | None,
    parameters: _Parameters,
    session_end_t_ns: int,
    prefix: str,
) -> _EventResult:
    window = _window(binding, event, parameters, session_end_t_ns, prefix)
    scene_duration = _support_duration(scene_support, window.start_t_ns, window.end_t_ns)
    if not streams_present:
        return _EventResult(
            binding,
            event,
            window,
            AnchorCalculationStatusV2.MISSING_INPUT,
            "required-stream-absent",
            None,
            None,
            None,
            scene_duration,
        )
    if (
        event is None
        or not binding.relevant_aoi_ids
        or not set(binding.relevant_aoi_ids) <= selected_aoi_ids
    ):
        return _EventResult(
            binding,
            event,
            window,
            AnchorCalculationStatusV2.NOT_COMPUTABLE,
            "cue-aoi-mapping-missing",
            None,
            None,
            None,
            scene_duration,
        )
    if fixations is None:
        return _EventResult(
            binding,
            event,
            window,
            AnchorCalculationStatusV2.DEPENDENCY_MISSING,
            "fixation-dependency-missing",
            None,
            None,
            None,
            scene_duration,
        )
    if scene_duration == 0:
        return _EventResult(
            binding,
            event,
            window,
            AnchorCalculationStatusV2.MISSING_INPUT,
            "no-scene-opportunity",
            None,
            None,
            None,
            scene_duration,
        )
    candidates = tuple(
        (
            max(item.start_t_ns, binding.cue_available_t_ns),
            item.fixation_id,
            item,
        )
        for item in fixations
        if item.aoi_id in binding.relevant_aoi_ids
        and item.end_t_ns > binding.cue_available_t_ns
        and item.start_t_ns < window.end_t_ns
    )
    selected = min(candidates, default=None)
    if selected is None:
        wait_ms = (window.end_t_ns - binding.cue_available_t_ns) / 1_000_000.0
        return _EventResult(
            binding,
            event,
            window,
            AnchorCalculationStatusV2.COMPUTED,
            None,
            None,
            None,
            wait_ms,
            scene_duration,
        )
    onset_t_ns, _fixation_id, fixation = selected
    return _EventResult(
        binding,
        event,
        window,
        AnchorCalculationStatusV2.COMPUTED,
        None,
        fixation,
        (onset_t_ns - binding.cue_available_t_ns) / 1_000_000.0,
        None,
        scene_duration,
    )


def _diagnostic(result: _EventResult) -> DomainErrorData:
    assert result.reason is not None
    missing = result.status is AnchorCalculationStatusV2.MISSING_INPUT
    dependency = result.status is AnchorCalculationStatusV2.DEPENDENCY_MISSING
    return DomainErrorData(
        error_code=f"anchor.h2.{result.reason}",
        severity=ErrorSeverity.WARNING,
        recoverable=True,
        message=f"H2 event {result.binding.event_id} could not produce fixation evidence.",
        field_or_path=(
            "dependencies.fixation-intervals"
            if dependency
            else "streams.I/G"
            if missing
            else "execution_plan.entries.H2"
        ),
        node_or_anchor_id="H2",
        remediation=(
            "Provide aligned I/G streams and scene opportunity support."
            if missing
            else "Resolve the registered fixation provider product."
            if dependency
            else "Bind a cue event to at least one AOI in the projected inventory."
        ),
        diagnostics={"event_id": result.binding.event_id, "reason": result.reason},
    )


def _breakdown(result: _EventResult) -> AnchorBreakdownMeasurement:
    diagnostics = (
        () if result.status is AnchorCalculationStatusV2.COMPUTED else (_diagnostic(result),)
    )
    override = (
        ClassificationOverride(
            code="fixation_missed",
            details={
                "event_id": result.binding.event_id,
                "observation_end_t_ns": result.window.end_t_ns,
            },
        )
        if result.missed
        else None
    )
    raw_metrics: dict[str, MetricValue] = {
        "scene-support-duration": MetricValue(
            scalar_kind="integer", value=result.scene_support_duration_ns, unit="ns"
        )
    }
    if result.latency_ms is not None:
        raw_metrics["first_fixation_latency"] = MetricValue(
            scalar_kind="float", value=result.latency_ms, unit="ms"
        )
    if result.observed_wait_ms is not None:
        raw_metrics["observed_wait"] = MetricValue(
            scalar_kind="float", value=result.observed_wait_ms, unit="ms"
        )
    return AnchorBreakdownMeasurement(
        breakdown_id=result.binding.event_id,
        calculation_status=result.status,
        primary_value=(
            MetricValue(scalar_kind="float", value=result.latency_ms, unit="ms")
            if result.latency_ms is not None
            else None
        ),
        primary_value_reason="fixation_missed" if result.missed else None,
        raw_metrics=raw_metrics,
        classification_override_candidate=override,
        trace=ComputationTrace(
            sample_count=1 if result.fixation is not None else 0,
            source_start_t_ns=None if result.fixation is None else result.fixation.start_t_ns,
            source_end_t_ns=None if result.fixation is None else result.fixation.end_t_ns,
            analysis_start_t_ns=result.window.start_t_ns,
            analysis_end_t_ns=result.window.end_t_ns,
            grid_id=None,
            window_ids=(result.window.window_id,),
            interpolation_method="raw-gaze-i-vt-v1",
            matching_method="earliest-relevant-aoi-fixation-v1",
            diagnostics=diagnostics,
        ),
        diagnostics=diagnostics,
    )


def _artifact_payload(
    definition: AnchorPluginDefinition,
    results: tuple[_EventResult, ...],
) -> TabularArtifactPayload | None:
    computed = tuple(item for item in results if item.status is AnchorCalculationStatusV2.COMPUTED)
    if not computed:
        return None
    successful = tuple(item for item in computed if item.fixation is not None)
    recipe = definition.artifact_recipes[0]
    frame = pl.DataFrame(
        {
            "event_id": pl.Series([item.binding.event_id for item in successful], dtype=pl.String),
            "fixation_id": pl.Series(
                [cast(_Fixation, item.fixation).fixation_id for item in successful],
                dtype=pl.String,
            ),
            "start_t_ns": pl.Series(
                [cast(_Fixation, item.fixation).start_t_ns for item in successful],
                dtype=pl.Int64,
            ),
            "end_t_ns": pl.Series(
                [cast(_Fixation, item.fixation).end_t_ns for item in successful],
                dtype=pl.Int64,
            ),
            "aoi_id": pl.Series(
                [cast(_Fixation, item.fixation).aoi_id for item in successful],
                dtype=pl.String,
            ),
            "latency_ms": pl.Series(
                [cast(float, item.latency_ms) for item in successful], dtype=pl.Float64
            ),
        }
    ).sort(["event_id", "start_t_ns", "fixation_id"], maintain_order=True)
    return TabularArtifactPayload(
        schema_id=recipe.schema_id,
        schema_descriptor=recipe.schema_descriptor,
        frame=frame,
        order_keys=("event_id", "start_t_ns", "fixation_id"),
        artifact_kind=recipe.kind,
        grid_hash=None,
        start_t_ns=min(item.window.start_t_ns for item in computed),
        end_t_ns=max(item.window.end_t_ns for item in computed),
    )


def _empty_measurement(status: AnchorCalculationStatusV2, reason: str) -> AnchorMeasurement:
    return AnchorMeasurement(
        anchor_id="H2",
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
            interpolation_method="raw-gaze-i-vt-v1",
            matching_method=reason,
            diagnostics=(),
        ),
        diagnostics=(),
    )


class H2FirstFixationLatencyPlugin:
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
        parsed = _parameters(parameters)
        if not isinstance(temporal_recipe, Mapping):
            raise TypeError("temporal_recipe must be a mapping")
        prefix = _strict_string(temporal_recipe.get("window_id_prefix"), "window_id_prefix")
        bindings = _event_bindings(temporal_recipe)
        if not bindings:
            return _empty_measurement(
                AnchorCalculationStatusV2.NOT_APPLICABLE,
                "no-visual-cue-opportunity-v1",
            )
        event_by_id, selected_aoi_ids = _validate_bound_semantics(
            context, temporal_recipe, bindings
        )
        i_view = context.streams.get("I")
        g_view = context.streams.get("G")
        streams_present = (
            i_view is not None
            and "frame_index" in i_view.tables
            and g_view is not None
            and "gaze_samples" in g_view.tables
        )
        scene_support = _scene_support(context) if streams_present else None
        fixation_rows = _fixations(dependencies) if streams_present else None
        results = tuple(
            _event_result(
                binding=binding,
                event=event_by_id.get(binding.event_id),
                selected_aoi_ids=selected_aoi_ids,
                fixations=fixation_rows,
                streams_present=streams_present,
                scene_support=scene_support,
                parameters=parsed,
                session_end_t_ns=context.session_window.end_t_ns,
                prefix=prefix,
            )
            for binding in bindings
        )
        breakdowns = tuple(_breakdown(item) for item in results)
        noncomputed = tuple(
            item.status for item in results if item.status is not AnchorCalculationStatusV2.COMPUTED
        )
        status = (
            max(noncomputed, key=_STATUS_PRIORITY.__getitem__)
            if noncomputed
            else AnchorCalculationStatusV2.COMPUTED
        )
        computed = tuple(
            item for item in results if item.status is AnchorCalculationStatusV2.COMPUTED
        )
        missed = tuple(item for item in computed if item.missed)
        primary = None
        primary_reason = None
        override = None
        raw_metrics: dict[str, MetricValue] = {
            "event-count": MetricValue(scalar_kind="integer", value=len(results), unit="count"),
            "computed-event-count": MetricValue(
                scalar_kind="integer", value=len(computed), unit="count"
            ),
            "missed-event-count": MetricValue(
                scalar_kind="integer", value=len(missed), unit="count"
            ),
            "fixation-count": MetricValue(
                scalar_kind="integer",
                value=0 if fixation_rows is None else len(fixation_rows),
                unit="count",
            ),
        }
        if status is AnchorCalculationStatusV2.COMPUTED:
            if missed:
                primary_reason = "fixation_missed"
                raw_metrics["observed_wait"] = MetricValue(
                    scalar_kind="float",
                    value=max(cast(float, item.observed_wait_ms) for item in missed),
                    unit="ms",
                )
                override = ClassificationOverride(
                    code="fixation_missed",
                    details={
                        "missed_event_ids": [item.binding.event_id for item in missed],
                    },
                )
            else:
                worst = max(cast(float, item.latency_ms) for item in computed)
                primary = MetricValue(scalar_kind="float", value=worst, unit="ms")
                raw_metrics["first_fixation_latency"] = MetricValue(
                    scalar_kind="float", value=worst, unit="ms"
                )
        diagnostics = tuple(
            diagnostic for breakdown in breakdowns for diagnostic in breakdown.diagnostics
        )
        payload = _artifact_payload(self._definition, results)
        derived_artifacts = (
            () if payload is None else (artifacts.stage_table("event-fixation-trace", payload),)
        )
        fixation_starts = tuple(item.start_t_ns for item in fixation_rows or ())
        fixation_ends = tuple(item.end_t_ns for item in fixation_rows or ())
        windows = tuple(item.window for item in results)
        return AnchorMeasurement(
            anchor_id="H2",
            calculation_status=status,
            primary_value=primary,
            primary_value_reason=primary_reason,
            raw_metrics=raw_metrics,
            phase_results=(),
            event_results=breakdowns,
            classification_override_candidate=override,
            source_windows=windows,
            derived_artifacts=derived_artifacts,
            trace=ComputationTrace(
                sample_count=0 if fixation_rows is None else len(fixation_rows),
                source_start_t_ns=min(fixation_starts) if fixation_starts else None,
                source_end_t_ns=max(fixation_ends) if fixation_ends else None,
                analysis_start_t_ns=min(item.window.start_t_ns for item in results),
                analysis_end_t_ns=max(item.window.end_t_ns for item in results),
                grid_id=None,
                window_ids=tuple(item.window.window_id for item in results),
                interpolation_method="raw-gaze-i-vt-v1",
                matching_method="earliest-relevant-aoi-fixation-v1",
                diagnostics=diagnostics,
            ),
            diagnostics=diagnostics,
        )


def create_plugin() -> H2FirstFixationLatencyPlugin:
    return H2FirstFixationLatencyPlugin()


__all__ = ["H2FirstFixationLatencyPlugin", "create_plugin"]
