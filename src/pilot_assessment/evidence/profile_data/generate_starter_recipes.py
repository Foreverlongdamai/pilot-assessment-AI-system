"""Regenerate the packaged M4R starter recipes from typed contracts."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import JsonValue

from pilot_assessment.contracts.evidence_recipe import (
    EvidenceRecipe,
    InputBindingKind,
    NodePortReference,
    OutputRole,
    PortCardinality,
    PortType,
    RecipeAnchor,
    RecipeDocumentation,
    RecipeEdge,
    RecipeGraph,
    RecipeInputBinding,
    RecipeLifecycle,
    RecipeNode,
    RecipeOutputBinding,
    RecipeScientificStatus,
    RecipeScoring,
    RecipeUiMetadata,
    ScoringMode,
    TemporalSemantics,
)
from pilot_assessment.evidence.builtins import register_builtin_operators
from pilot_assessment.evidence.compiler import compile_recipe
from pilot_assessment.evidence.registry import OperatorRegistry

_VERSION = "0.1.0"
_SESSION_END_NS = 90_000_000_000

_NAMES = {
    "O1": "Phase-state precision",
    "O2": "Peak tracking excursion",
    "O3": "Terminal capture quality",
    "O4": "Sustained hover time",
    "O5": "Workload rate",
    "O6": "Control magnitude RMS",
    "O7": "Control reversal rate",
    "O8": "TPX composite",
    "O9": "Dead-band activity",
    "O10": "Recovery time",
    "O11": "Disturbance latency",
    "O12": "Envelope-drift latency",
    "O13": "Physio-control coupling",
    "H1": "AOI dwell",
    "H2": "First fixation latency",
    "H3": "Off-task dwell",
    "H4": "ECG fluctuation",
    "H5": "EEG fluctuation",
}

_LEGACY_IMPLEMENTATION_IDS = {
    "O1": "o1-phase-state-precision",
    "O2": "o2-peak-tracking-excursion",
    "O3": "o3-terminal-capture-quality",
    "O4": "o4-sustained-hover-time",
    "O5": "o5-workload-rate",
    "O6": "o6-control-magnitude-rms",
    "O7": "o7-control-reversal-rate",
    "O8": "o8-tpx-composite",
    "O9": "o9-dead-band-activity",
    "O10": "o10-recovery-time",
    "O11": "o11-disturbance-latency",
    "O12": "o12-envelope-drift-latency",
    "O13": "o13-physio-control-coupling",
    "H1": "h1-aoi-dwell",
    "H2": "h2-first-fixation-latency",
    "H3": "h3-off-task-dwell",
    "H4": "h4-ecg-fluctuation",
    "H5": "h5-eeg-fluctuation",
}
_LEGACY_PLUGIN_ANCHORS = frozenset(
    {*(f"O{index}" for index in range(1, 13)), *(f"H{index}" for index in range(1, 4))}
)

_TEMPORAL = {
    "number": TemporalSemantics.TIMELESS,
    "signal_bundle": TemporalSemantics.SAMPLED,
    "signal_series": TemporalSemantics.SAMPLED,
    "vector_series": TemporalSemantics.SAMPLED,
    "gaze_frame_collection": TemporalSemantics.INTERVAL,
    "event_collection": TemporalSemantics.POINT,
}


class _RecipeBuilder:
    def __init__(
        self,
        anchor_id: str,
        *,
        direction: str,
        desired_boundary: float,
        adequate_boundary: float,
    ) -> None:
        self.anchor_id = anchor_id
        self.direction = direction
        self.desired_boundary = desired_boundary
        self.adequate_boundary = adequate_boundary
        self.inputs: list[RecipeInputBinding] = []
        self.nodes: list[RecipeNode] = []
        self.edges: list[RecipeEdge] = []

    def input(
        self,
        binding_id: str,
        source_id: str,
        value_type: str,
        *,
        kind: InputBindingKind = InputBindingKind.STREAM,
    ) -> str:
        self.inputs.append(
            RecipeInputBinding(
                binding_id=binding_id,
                kind=kind,
                source_id=source_id,
                name=binding_id.replace("-", " ").title(),
                declared_type=PortType(
                    value_type=value_type,
                    cardinality=PortCardinality.ONE,
                    temporal_semantics=_TEMPORAL[value_type],
                    unit=None,
                ),
                selector={},
            )
        )
        node_id = f"{binding_id}-input"
        self.nodes.append(
            RecipeNode(
                node_id=node_id,
                operator_id="input.binding",
                operator_version=_VERSION,
                input_binding_id=binding_id,
                parameters={},
            )
        )
        return node_id

    def node(
        self,
        node_id: str,
        operator_id: str,
        parameters: dict[str, JsonValue],
    ) -> str:
        self.nodes.append(
            RecipeNode(
                node_id=node_id,
                operator_id=operator_id,
                operator_version=_VERSION,
                parameters=parameters,
            )
        )
        return node_id

    def edge(
        self,
        source: str,
        target: str,
        target_port: str,
        *,
        slot: str | None = None,
    ) -> None:
        edge_id = f"e-{len(self.edges):03d}-{source}-{target}"
        self.edges.append(
            RecipeEdge(
                edge_id=edge_id,
                source=NodePortReference(node_id=source, port_id="value"),
                target=NodePortReference(node_id=target, port_id=target_port),
                target_slot_id=slot,
            )
        )

    def finish(self, primary_node: str, *, unit: str | None) -> EvidenceRecipe:
        anchor_id = self.anchor_id
        primary = NodePortReference(node_id=primary_node, port_id="value")
        implementation_id = _LEGACY_IMPLEMENTATION_IDS[anchor_id]
        legacy_reference = (
            f"legacy-reference-plugin:{implementation_id}@0.1.0"
            if anchor_id in _LEGACY_PLUGIN_ANCHORS
            else f"legacy-reference-definition:{implementation_id}@0.1.0"
        )
        return EvidenceRecipe(
            recipe_id=f"starter.{anchor_id.lower()}",
            recipe_version=1,
            anchor=RecipeAnchor(
                anchor_id=anchor_id,
                name=_NAMES[anchor_id],
                description=(
                    "Editable initial computation template. Experts may change, replace, "
                    "disable or clone every node and parameter."
                ),
                lifecycle=RecipeLifecycle.ACTIVE,
                scientific_status=RecipeScientificStatus.STARTER_TEMPLATE,
            ),
            inputs=tuple(self.inputs),
            graph=RecipeGraph(nodes=tuple(self.nodes), edges=tuple(self.edges)),
            outputs=(
                RecipeOutputBinding(
                    output_id="primary",
                    role=OutputRole.PRIMARY_VALUE,
                    name=f"{anchor_id} primary value",
                    source=primary,
                    unit=unit,
                ),
            ),
            scoring=RecipeScoring(
                mode=ScoringMode.ORDERED_DAU,
                input=primary,
                parameters={
                    "direction": self.direction,
                    "desired_boundary": self.desired_boundary,
                    "adequate_boundary": self.adequate_boundary,
                    "likelihood_strength": 0.9,
                },
                custom_operator_id=None,
                custom_operator_version=None,
            ),
            documentation=RecipeDocumentation(
                summary=(
                    "Engineering starter only; this recipe and every default parameter "
                    "remain open to expert replacement."
                ),
                assumptions=(
                    "Finite poor-performance values remain evidence and are not quality-filtered.",
                    "Bindings use normalized ideal interfaces and may be adapted to final exports.",
                ),
                parameter_notes={},
                references=(
                    legacy_reference,
                    f"legacy-parameter-resource:{anchor_id.lower()}-parameters-0.1",
                ),
            ),
            ui=RecipeUiMetadata(
                groups=(),
                preferred_layout={"layout": "left-to-right", "generated": True},
            ),
        )


def _session_duration(builder: _RecipeBuilder) -> str:
    return builder.input(
        "session-duration-s",
        "session.duration-s",
        "number",
        kind=InputBindingKind.SEMANTIC,
    )


def _channel(
    builder: _RecipeBuilder,
    *,
    prefix: str,
    source_id: str,
    channel_id: str,
) -> str:
    bundle = builder.input(f"{prefix}-bundle", source_id, "signal_bundle")
    selected = builder.node(
        f"{prefix}-select",
        "signal.channel-select",
        {"channel_id": channel_id},
    )
    builder.edge(bundle, selected, "channels")
    return selected


def _percent_formula(
    builder: _RecipeBuilder,
    numerator: str,
    denominator: str,
    *,
    prefix: str,
) -> str:
    ratio = builder.node(
        f"{prefix}-ratio",
        "statistics.ratio",
        {"zero_denominator": "zero"},
    )
    builder.edge(numerator, ratio, "numerator")
    builder.edge(denominator, ratio, "denominator")
    percent = builder.node(
        f"{prefix}-percent",
        "composition.safe-formula",
        {"formula": "ratio * 100", "constants": {}},
    )
    builder.edge(ratio, percent, "variables", slot="ratio")
    return percent


def _o1() -> EvidenceRecipe:
    b = _RecipeBuilder(
        "O1", direction="higher_is_better", desired_boundary=90, adequate_boundary=70
    )
    state = b.input("flight-state", "X.state-vector", "vector_series")
    envelope = b.node(
        "desired-envelope",
        "flight.envelope-membership",
        {"lower_bounds": [-1.0, -1.0, -1.0], "upper_bounds": [1.0, 1.0, 1.0], "inclusive": True},
    )
    b.edge(state, envelope, "vectors")
    runs = b.node(
        "inside-runs",
        "event.mask-run",
        {
            "minimum_duration_ns": 0,
            "observation_end_ns": _SESSION_END_NS,
            "interval_type": "inside-desired-envelope",
        },
    )
    b.edge(envelope, runs, "mask")
    duration = b.node(
        "inside-duration",
        "statistics.duration",
        {"unit": "seconds", "union_overlaps": True},
    )
    b.edge(runs, duration, "intervals")
    primary = _percent_formula(b, duration, _session_duration(b), prefix="precision")
    return b.finish(primary, unit="percent")


def _o2() -> EvidenceRecipe:
    b = _RecipeBuilder("O2", direction="lower_is_better", desired_boundary=2, adequate_boundary=5)
    actual = b.input("actual-path", "X.position-vector", "vector_series")
    reference = b.input(
        "commanded-path",
        "task-reference.commanded-path",
        "vector_series",
        kind=InputBindingKind.REFERENCE,
    )
    distance = b.node("tracking-error", "flight.distance", {})
    b.edge(actual, distance, "left")
    b.edge(reference, distance, "right")
    peak = b.node("peak-error", "statistics.percentile", {"percentile": 100.0})
    b.edge(distance, peak, "values")
    return b.finish(peak, unit="ft")


def _o3() -> EvidenceRecipe:
    b = _RecipeBuilder("O3", direction="lower_is_better", desired_boundary=3, adequate_boundary=5)
    error = b.input("terminal-error", "derived.terminal-error", "signal_series")
    capture = b.node(
        "capture",
        "flight.capture",
        {
            "tolerance": 2.0,
            "hold_duration_ns": 2_000_000_000,
            "observation_start_ns": 0,
            "observation_end_ns": 15_000_000_000,
        },
    )
    b.edge(error, capture, "error")
    latency = b.node("capture-latency", "statistics.named-select", {"key": "capture_latency_s"})
    b.edge(capture, latency, "values")
    return b.finish(latency, unit="s")


def _o4() -> EvidenceRecipe:
    b = _RecipeBuilder("O4", direction="higher_is_better", desired_boundary=10, adequate_boundary=5)
    state = b.input("hover-state", "X.hover-vector", "vector_series")
    envelope = b.node(
        "hover-envelope",
        "flight.envelope-membership",
        {"lower_bounds": [-1.0, -1.0, -1.0], "upper_bounds": [1.0, 1.0, 1.0], "inclusive": True},
    )
    b.edge(state, envelope, "vectors")
    runs = b.node(
        "stable-hover-runs",
        "event.mask-run",
        {
            "minimum_duration_ns": 0,
            "observation_end_ns": _SESSION_END_NS,
            "interval_type": "stable-hover",
        },
    )
    b.edge(envelope, runs, "mask")
    duration = b.node(
        "stable-hover-duration", "statistics.duration", {"unit": "seconds", "union_overlaps": True}
    )
    b.edge(runs, duration, "intervals")
    return b.finish(duration, unit="s")


def _movement_rate(
    anchor_id: str, *, threshold: float, adequate: float, minimum: float
) -> EvidenceRecipe:
    b = _RecipeBuilder(
        anchor_id,
        direction="lower_is_better",
        desired_boundary=threshold,
        adequate_boundary=adequate,
    )
    signal = _channel(b, prefix="control", source_id="U.channels", channel_id="primary")
    turning = b.node(
        "turning-points",
        "event.turning-point",
        {"minimum_delta": 0.0, "event_type": "turning-point"},
    )
    b.edge(signal, turning, "signal")
    movement = b.node(
        "movements",
        "event.movement",
        {"minimum_amplitude": minimum, "minimum_separation_ns": 0, "event_type": "movement"},
    )
    b.edge(turning, movement, "turning_points")
    count = b.node("movement-count", "statistics.count", {})
    b.edge(movement, count, "values")
    rate = b.node(
        "movement-rate", "statistics.rate", {"duration_unit": "seconds", "zero_duration": "zero"}
    )
    b.edge(count, rate, "count")
    b.edge(_session_duration(b), rate, "duration")
    return b.finish(rate, unit="Hz" if anchor_id == "O9" else "ratio")


def _o5() -> EvidenceRecipe:
    return _movement_rate("O5", threshold=2, adequate=4, minimum=1.0)


def _o6() -> EvidenceRecipe:
    b = _RecipeBuilder("O6", direction="lower_is_better", desired_boundary=30, adequate_boundary=50)
    signal = _channel(b, prefix="control", source_id="U.channels", channel_id="primary")
    rms = b.node("control-rms", "statistics.rms", {})
    b.edge(signal, rms, "values")
    return b.finish(rms, unit="percent_full_travel")


def _o7() -> EvidenceRecipe:
    b = _RecipeBuilder("O7", direction="lower_is_better", desired_boundary=2, adequate_boundary=4)
    signal = _channel(b, prefix="control", source_id="U.channels", channel_id="primary")
    turning = b.node(
        "turning-points",
        "event.turning-point",
        {"minimum_delta": 0.0, "event_type": "turning-point"},
    )
    b.edge(signal, turning, "signal")
    reversal = b.node(
        "reversals",
        "event.reversal",
        {
            "channel_id": "primary",
            "support_start_t_ns": 0,
            "support_end_t_ns": _SESSION_END_NS,
            "minimum_amplitude": 2.0,
            "minimum_separation_ns": 150_000_000,
            "event_type": "reversal",
        },
    )
    b.edge(turning, reversal, "turning_points")
    count = b.node("reversal-count", "statistics.count", {})
    b.edge(reversal, count, "values")
    rate = b.node(
        "reversal-rate", "statistics.rate", {"duration_unit": "seconds", "zero_duration": "zero"}
    )
    b.edge(count, rate, "count")
    b.edge(_session_duration(b), rate, "duration")
    return b.finish(rate, unit="Hz")


def _o8() -> EvidenceRecipe:
    b = _RecipeBuilder(
        "O8", direction="higher_is_better", desired_boundary=0.6, adequate_boundary=0.4
    )
    o1 = b.input("o1-score", "anchor.O1-score", "number", kind=InputBindingKind.SEMANTIC)
    o5 = b.input("o5-score", "anchor.O5-score", "number", kind=InputBindingKind.SEMANTIC)
    formula = b.node(
        "tpx", "composition.safe-formula", {"formula": "(o1 + o5) / 2", "constants": {}}
    )
    b.edge(o1, formula, "variables", slot="o1")
    b.edge(o5, formula, "variables", slot="o5")
    return b.finish(formula, unit="ratio")


def _o9() -> EvidenceRecipe:
    return _movement_rate("O9", threshold=1, adequate=2, minimum=0.0)


def _o10() -> EvidenceRecipe:
    b = _RecipeBuilder("O10", direction="lower_is_better", desired_boundary=5, adequate_boundary=10)
    error = b.input("flight-error", "derived.flight-error", "signal_series")
    events = b.input(
        "disturbances", "semantic.disturbances", "event_collection", kind=InputBindingKind.SEMANTIC
    )
    recovery = b.node(
        "recovery",
        "event.recovery",
        {
            "target": 0.0,
            "tolerance": 1.0,
            "hold_duration_ns": 2_000_000_000,
            "horizon_ns": 15_000_000_000,
        },
    )
    b.edge(error, recovery, "signal")
    b.edge(events, recovery, "events")
    aggregate = b.node(
        "worst-recovery", "aggregation.event", {"mode": "worst", "direction": "lower_is_better"}
    )
    b.edge(recovery, aggregate, "values")
    return b.finish(aggregate, unit="s")


def _latency_recipe(
    anchor_id: str,
    *,
    desired: float,
    adequate: float,
    signal_source: str,
    trigger_source: str,
    threshold: float,
    horizon_ns: int,
) -> EvidenceRecipe:
    b = _RecipeBuilder(
        anchor_id, direction="lower_is_better", desired_boundary=desired, adequate_boundary=adequate
    )
    signal = b.input("response-signal", signal_source, "signal_series")
    triggers = b.input(
        "trigger-events", trigger_source, "event_collection", kind=InputBindingKind.SEMANTIC
    )
    responses = b.node(
        "response-events",
        "event.threshold-crossing",
        {"threshold": threshold, "direction": "either", "event_type": "response"},
    )
    b.edge(signal, responses, "signal")
    latency = b.node(
        "event-latency",
        "event.latency",
        {"horizon_ns": horizon_ns, "no_match_policy": "horizon", "fixed_latency_s": 0.0},
    )
    b.edge(triggers, latency, "triggers")
    b.edge(responses, latency, "responses")
    aggregate = b.node(
        "worst-latency", "aggregation.event", {"mode": "worst", "direction": "lower_is_better"}
    )
    b.edge(latency, aggregate, "values")
    return b.finish(aggregate, unit="s")


def _o11() -> EvidenceRecipe:
    return _latency_recipe(
        "O11",
        desired=0.5,
        adequate=1.0,
        signal_source="U.primary-control",
        trigger_source="semantic.disturbances",
        threshold=5.0,
        horizon_ns=2_000_000_000,
    )


def _o12() -> EvidenceRecipe:
    return _latency_recipe(
        "O12",
        desired=0.3,
        adequate=0.8,
        signal_source="derived.envelope-error",
        trigger_source="semantic.control-excursions",
        threshold=1.0,
        horizon_ns=2_000_000_000,
    )


def _o13() -> EvidenceRecipe:
    b = _RecipeBuilder("O13", direction="lower_is_better", desired_boundary=5, adequate_boundary=20)
    control = _channel(b, prefix="control", source_id="U.channels", channel_id="primary")
    heart = _channel(b, prefix="ecg", source_id="ECG.channels", channel_id="heart-rate")
    correlation = b.node(
        "control-ecg-correlation",
        "statistics.correlation",
        {"absolute": True, "degenerate": "zero"},
    )
    b.edge(control, correlation, "left")
    b.edge(heart, correlation, "right")
    percent = b.node(
        "coupling-percent",
        "composition.safe-formula",
        {"formula": "correlation * 100", "constants": {}},
    )
    b.edge(correlation, percent, "variables", slot="correlation")
    return b.finish(percent, unit="percent")


def _h1() -> EvidenceRecipe:
    b = _RecipeBuilder(
        "H1", direction="higher_is_better", desired_boundary=85, adequate_boundary=70
    )
    gaze = b.input("gaze-frames", "G.frames", "gaze_frame_collection")
    intervals = b.node(
        "gaze-aoi", "gaze.aoi-intervals", {"mode": "assigned_label", "merge_adjacent": True}
    )
    b.edge(gaze, intervals, "frames")
    filtered = b.node("expected-aoi", "gaze.aoi-filter", {"aoi_ids": ["instrument"]})
    b.edge(intervals, filtered, "intervals")
    duration = b.node(
        "aoi-duration", "statistics.duration", {"unit": "seconds", "union_overlaps": True}
    )
    b.edge(filtered, duration, "intervals")
    primary = _percent_formula(b, duration, _session_duration(b), prefix="dwell")
    return b.finish(primary, unit="percent")


def _h2() -> EvidenceRecipe:
    b = _RecipeBuilder(
        "H2", direction="lower_is_better", desired_boundary=0.5, adequate_boundary=1.0
    )
    events = b.input(
        "events", "semantic.attention-events", "event_collection", kind=InputBindingKind.SEMANTIC
    )
    gaze = b.input("gaze-frames", "G.frames", "gaze_frame_collection")
    windows = b.node(
        "event-windows",
        "temporal.event-window",
        {
            "start_offset_ns": 0,
            "end_offset_ns": 2_000_000_000,
            "include_event_duration": False,
            "clamp_to_zero": True,
        },
    )
    b.edge(events, windows, "events")
    intervals = b.node(
        "gaze-aoi", "gaze.aoi-intervals", {"mode": "assigned_label", "merge_adjacent": True}
    )
    b.edge(gaze, intervals, "frames")
    intersection = b.node("windowed-gaze", "temporal.interval-intersect", {})
    b.edge(windows, intersection, "left")
    b.edge(intervals, intersection, "right")
    filtered = b.node("expected-aoi", "gaze.aoi-filter", {"aoi_ids": ["instrument"]})
    b.edge(intersection, filtered, "intervals")
    latency = b.node(
        "first-fixation",
        "gaze.first-match-latency",
        {"no_match_policy": "window_end", "fixed_latency_s": 0.0},
    )
    b.edge(windows, latency, "windows")
    b.edge(filtered, latency, "matches")
    aggregate = b.node(
        "worst-fixation", "aggregation.event", {"mode": "worst", "direction": "lower_is_better"}
    )
    b.edge(latency, aggregate, "values")
    return b.finish(aggregate, unit="s")


def _h3() -> EvidenceRecipe:
    b = _RecipeBuilder("H3", direction="lower_is_better", desired_boundary=5, adequate_boundary=15)
    gaze = b.input("gaze-frames", "G.frames", "gaze_frame_collection")
    intervals = b.node(
        "gaze-aoi", "gaze.aoi-intervals", {"mode": "assigned_label", "merge_adjacent": True}
    )
    b.edge(gaze, intervals, "frames")
    filtered = b.node("off-task-aoi", "gaze.aoi-filter", {"aoi_ids": ["off-task"]})
    b.edge(intervals, filtered, "intervals")
    duration = b.node(
        "off-task-duration", "statistics.duration", {"unit": "seconds", "union_overlaps": True}
    )
    b.edge(filtered, duration, "intervals")
    primary = _percent_formula(b, duration, _session_duration(b), prefix="off-task")
    return b.finish(primary, unit="percent")


def _physiology(
    anchor_id: str, *, source_id: str, channel_id: str, desired: float, adequate: float
) -> EvidenceRecipe:
    b = _RecipeBuilder(
        anchor_id, direction="lower_is_better", desired_boundary=desired, adequate_boundary=adequate
    )
    signal = _channel(b, prefix=anchor_id.lower(), source_id=source_id, channel_id=channel_id)
    detrended = b.node("detrended", "signal.detrend", {"method": "mean"})
    b.edge(signal, detrended, "signal")
    rms = b.node("fluctuation-rms", "statistics.rms", {})
    b.edge(detrended, rms, "values")
    return b.finish(rms, unit="percent")


def _h4() -> EvidenceRecipe:
    return _physiology(
        "H4", source_id="ECG.channels", channel_id="heart-rate", desired=20, adequate=40
    )


def _h5() -> EvidenceRecipe:
    return _physiology(
        "H5", source_id="EEG.channels", channel_id="engagement", desired=20, adequate=50
    )


def build_starter_recipes() -> tuple[EvidenceRecipe, ...]:
    """Build the packaged inventory without fixing future catalog cardinality."""

    return (
        _o1(),
        _o2(),
        _o3(),
        _o4(),
        _o5(),
        _o6(),
        _o7(),
        _o8(),
        _o9(),
        _o10(),
        _o11(),
        _o12(),
        _o13(),
        _h1(),
        _h2(),
        _h3(),
        _h4(),
        _h5(),
    )


def _manifest(recipes: tuple[EvidenceRecipe, ...]) -> dict[str, object]:
    entries = []
    for recipe in recipes:
        anchor_id = recipe.anchor.anchor_id
        has_legacy_plugin = anchor_id in _LEGACY_PLUGIN_ANCHORS
        entries.append(
            {
                "anchor_id": anchor_id,
                "legacy_parameter_resource": (f"{anchor_id.lower()}-parameters-0.1.json"),
                "legacy_plugin_id": (
                    _LEGACY_IMPLEMENTATION_IDS[anchor_id] if has_legacy_plugin else None
                ),
                "legacy_plugin_version": "0.1.0" if has_legacy_plugin else None,
                "legacy_status": (
                    "retained_reference_replay_source"
                    if has_legacy_plugin
                    else "parameter_resource_only_no_legacy_plugin"
                ),
                "migration_kind": (
                    "operator_composition"
                    if anchor_id in {"O13", "H4", "H5"}
                    else "legacy_operator_migration"
                ),
                "recipe_resource": f"recipes/{anchor_id.lower()}.json",
                "scientific_status": "starter_template",
            }
        )
    return {
        "contract_id": "starter-evidence-recipe-catalog",
        "contract_version": "0.1.0",
        "entries": entries,
        "inventory_note": (
            "Packaged defaults only. Expert models may add, disable or retire any number "
            "of recipes without changing the catalog implementation."
        ),
    }


def write_resources(root: Path | None = None) -> tuple[Path, ...]:
    """Validate and write deterministic human-readable package resources."""

    profile_root = root or Path(__file__).resolve().parent
    recipes_root = profile_root / "recipes"
    recipes_root.mkdir(parents=True, exist_ok=True)
    recipes = build_starter_recipes()
    registry = OperatorRegistry()
    register_builtin_operators(registry)
    paths: list[Path] = []
    for recipe in recipes:
        compile_recipe(recipe, registry)
        path = recipes_root / f"{recipe.anchor.anchor_id.lower()}.json"
        path.write_text(
            json.dumps(
                recipe.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        paths.append(path)
    manifest_path = profile_root / "catalog.json"
    manifest_path.write_text(
        json.dumps(_manifest(recipes), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    paths.append(manifest_path)
    return tuple(paths)


if __name__ == "__main__":
    write_resources()
