from __future__ import annotations

import pytest

from pilot_assessment.contracts.anchor import EvidenceState
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
from pilot_assessment.evidence.builtins import (
    EventRecord,
    GazeFrame,
    register_builtin_operators,
)
from pilot_assessment.evidence.compiler import compile_recipe
from pilot_assessment.evidence.executor import RecipeExecutionResult, execute_recipe
from pilot_assessment.evidence.registry import OperatorRegistry

_VERSION = "0.1.0"


def _ref(node_id: str) -> NodePortReference:
    return NodePortReference(node_id=node_id, port_id="value")


def _edge(edge_id: str, source: str, target: str, target_port: str) -> RecipeEdge:
    return RecipeEdge(
        edge_id=edge_id,
        source=_ref(source),
        target=NodePortReference(node_id=target, port_id=target_port),
    )


def _binding(
    binding_id: str,
    source_id: str,
    value_type: str,
) -> RecipeInputBinding:
    return RecipeInputBinding(
        binding_id=binding_id,
        kind=InputBindingKind.STREAM,
        source_id=source_id,
        name=binding_id.replace("-", " ").title(),
        declared_type=PortType(
            value_type=value_type,
            cardinality=PortCardinality.ONE,
            temporal_semantics=TemporalSemantics.INTERVAL,
            unit=None,
        ),
        selector={},
    )


def _disturbance_aoi_recipe(
    *,
    expected_aoi: str = "instrument",
    window_end_offset_ns: int = 5_000_000_000,
    recipe_version: int = 1,
) -> EvidenceRecipe:
    nodes = (
        RecipeNode(
            node_id="events-input",
            operator_id="input.binding",
            operator_version=_VERSION,
            input_binding_id="events",
            parameters={},
        ),
        RecipeNode(
            node_id="event-select",
            operator_id="temporal.event-select",
            operator_version=_VERSION,
            parameters={"event_types": ["disturbance"]},
        ),
        RecipeNode(
            node_id="event-window",
            operator_id="temporal.event-window",
            operator_version=_VERSION,
            parameters={
                "start_offset_ns": 0,
                "end_offset_ns": window_end_offset_ns,
                "include_event_duration": False,
                "clamp_to_zero": True,
            },
        ),
        RecipeNode(
            node_id="gaze-input",
            operator_id="input.binding",
            operator_version=_VERSION,
            input_binding_id="gaze-frames",
            parameters={},
        ),
        RecipeNode(
            node_id="gaze-intervals",
            operator_id="gaze.aoi-intervals",
            operator_version=_VERSION,
            parameters={"mode": "assigned_label", "merge_adjacent": True},
        ),
        RecipeNode(
            node_id="windowed-gaze",
            operator_id="temporal.interval-intersect",
            operator_version=_VERSION,
            parameters={},
        ),
        RecipeNode(
            node_id="aoi-filter",
            operator_id="gaze.aoi-filter",
            operator_version=_VERSION,
            parameters={"aoi_ids": [expected_aoi]},
        ),
        RecipeNode(
            node_id="first-match",
            operator_id="gaze.first-match-latency",
            operator_version=_VERSION,
            parameters={
                "no_match_policy": "window_end",
                "fixed_latency_s": 0.0,
            },
        ),
        RecipeNode(
            node_id="dwell-ratio",
            operator_id="gaze.dwell-ratio",
            operator_version=_VERSION,
            parameters={},
        ),
        RecipeNode(
            node_id="latency-aggregate",
            operator_id="aggregation.event",
            operator_version=_VERSION,
            parameters={"mode": "worst", "direction": "lower_is_better"},
        ),
        RecipeNode(
            node_id="dwell-aggregate",
            operator_id="aggregation.event",
            operator_version=_VERSION,
            parameters={"mode": "worst", "direction": "higher_is_better"},
        ),
    )
    edges = (
        _edge("events-to-select", "events-input", "event-select", "events"),
        _edge("select-to-window", "event-select", "event-window", "events"),
        _edge("gaze-to-intervals", "gaze-input", "gaze-intervals", "frames"),
        _edge("window-to-intersection", "event-window", "windowed-gaze", "left"),
        _edge("gaze-to-intersection", "gaze-intervals", "windowed-gaze", "right"),
        _edge("intersection-to-filter", "windowed-gaze", "aoi-filter", "intervals"),
        _edge("window-to-latency", "event-window", "first-match", "windows"),
        _edge("matches-to-latency", "aoi-filter", "first-match", "matches"),
        _edge("window-to-dwell", "event-window", "dwell-ratio", "windows"),
        _edge("matches-to-dwell", "aoi-filter", "dwell-ratio", "matches"),
        _edge("latency-to-aggregate", "first-match", "latency-aggregate", "values"),
        _edge("dwell-to-aggregate", "dwell-ratio", "dwell-aggregate", "values"),
    )
    latency = _ref("latency-aggregate")
    return EvidenceRecipe(
        recipe_id="example.disturbance-aoi-attention",
        recipe_version=recipe_version,
        anchor=RecipeAnchor(
            anchor_id="EXAMPLE-DISTURBANCE-AOI",
            name="Disturbance AOI attention example",
            description="Editable platform example; not a scientifically approved Anchor.",
            lifecycle=RecipeLifecycle.ACTIVE,
            scientific_status=RecipeScientificStatus.STARTER_TEMPLATE,
        ),
        inputs=(
            _binding("events", "session-events", "event_collection"),
            _binding("gaze-frames", "G", "gaze_frame_collection"),
        ),
        graph=RecipeGraph(nodes=nodes, edges=edges),
        outputs=(
            RecipeOutputBinding(
                output_id="latency-s",
                role=OutputRole.PRIMARY_VALUE,
                name="Worst first-match latency",
                source=latency,
                unit="s",
            ),
            RecipeOutputBinding(
                output_id="dwell-ratio",
                role=OutputRole.RAW_METRIC,
                name="Worst dwell ratio",
                source=_ref("dwell-aggregate"),
                unit=None,
            ),
        ),
        scoring=RecipeScoring(
            mode=ScoringMode.ORDERED_DAU,
            input=latency,
            parameters={
                "direction": "lower_is_better",
                "desired_boundary": 1.5,
                "adequate_boundary": 3.0,
                "likelihood_strength": 0.9,
            },
            custom_operator_id=None,
            custom_operator_version=None,
        ),
        documentation=RecipeDocumentation(
            summary="Small editable recipe used only to prove platform composition.",
            assumptions=(),
            parameter_notes={},
            references=(),
        ),
        ui=RecipeUiMetadata(groups=(), preferred_layout={}),
    )


def _preview(recipe: EvidenceRecipe) -> RecipeExecutionResult:
    registry = OperatorRegistry()
    register_builtin_operators(registry)
    return execute_recipe(
        compile_recipe(recipe, registry),
        registry,
        binding_values={
            "events": (EventRecord("event-1", "disturbance", 1_000_000_000),),
            "gaze-frames": (
                GazeFrame("frame-1", 1_000_000_000, 2_000_000_000, "outside", {}),
                GazeFrame(
                    "frame-2",
                    2_000_000_000,
                    4_000_000_000,
                    "instrument",
                    {},
                ),
                GazeFrame("frame-3", 4_000_000_000, 6_000_000_000, "outside", {}),
            ),
        },
    )


def test_recipe_parameter_edits_mechanically_change_preview() -> None:
    matching = _preview(_disturbance_aoi_recipe())
    changed_aoi = _preview(
        _disturbance_aoi_recipe(
            expected_aoi="unobserved-aoi",
            recipe_version=2,
        )
    )
    shorter_window = _preview(
        _disturbance_aoi_recipe(
            window_end_offset_ns=3_000_000_000,
            recipe_version=3,
        )
    )

    assert matching.outputs == {
        "latency-s": 1.0,
        "dwell-ratio": pytest.approx(0.4),
    }
    assert matching.scoring_outputs["state"] is EvidenceState.DESIRED

    assert changed_aoi.outputs == {"latency-s": 5.0, "dwell-ratio": 0.0}
    assert changed_aoi.scoring_outputs["state"] is EvidenceState.UNACCEPTABLE

    assert shorter_window.outputs["latency-s"] == 1.0
    assert shorter_window.outputs["dwell-ratio"] == pytest.approx(2.0 / 3.0)
