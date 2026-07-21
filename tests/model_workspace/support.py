"""Tiny task-neutral M7 graph fixtures shared by focused workspace tests."""

from __future__ import annotations

from datetime import UTC, datetime

from pilot_assessment.contracts.evidence_recipe import (
    EvidenceRecipe,
    InputBindingKind,
    NodePortReference,
    OutputRole,
    PortCardinality,
    PortType,
    RecipeAnchor,
    RecipeDocumentation,
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
from pilot_assessment.contracts.model_components import (
    BnNodeRole,
    ComponentSource,
    CptMode,
    ModelScientificStatus,
    ObservationPolicy,
    RawModality,
    SourceDescriptor,
    SourceKind,
    VariableState,
)
from pilot_assessment.contracts.model_workspace import (
    BnNodeDefinition,
    EvidenceDataBinding,
    EvidenceNodeDefinition,
    ModelNode,
    ModelNodeKind,
    ModelNodeRef,
    ModelObjectLifecycle,
    ModelTechnicalStatus,
    NodeCpt,
    NodeLayout,
    RawInputFamily,
    RawInputNodeDefinition,
    RawResourceRole,
    TaskScheme,
)
from pilot_assessment.evidence.builtins import register_builtin_operators
from pilot_assessment.evidence.registry import OperatorRegistry
from pilot_assessment.model_workspace.hashing import rehash_model_node, rehash_task_scheme

NOW = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
ZERO_HASH = "0" * 64
SOURCE_HASH = "a" * 64
STATE_IDS = ("low", "medium", "high")
OBSERVATION_STATE_IDS = ("unacceptable", "adequate", "desired")


def operator_registry() -> OperatorRegistry:
    registry = OperatorRegistry()
    register_builtin_operators(registry)
    return registry


def _port_type() -> PortType:
    return PortType(
        value_type="number",
        cardinality=PortCardinality.ONE,
        temporal_semantics=TemporalSemantics.SAMPLED,
        unit=None,
    )


def _source(source_id: str, modality: RawModality) -> SourceDescriptor:
    return SourceDescriptor(
        source_id=source_id,
        kind=SourceKind.RAW_STREAM,
        name=source_id,
        description=f"Task-neutral {modality.value} fixture source.",
        declared_type=_port_type(),
        raw_modality=modality,
        source_dependencies=(),
        metadata={},
        content_hash=SOURCE_HASH,
    )


def _state(state_id: str) -> VariableState:
    return VariableState(
        state_id=state_id,
        label=state_id.title(),
        description=f"{state_id.title()} fixture state.",
    )


def _ref(kind: ModelNodeKind, node_id: str) -> ModelNodeRef:
    return ModelNodeRef(node_id=node_id, node_kind=kind)


def _layout(node_id: str, x: float, y: float) -> NodeLayout:
    return NodeLayout(node_id=node_id, x=x, y=y)


def _node_fields(
    node_id: str,
    kind: ModelNodeKind,
    *,
    x: float,
    y: float,
) -> dict[str, object]:
    return {
        "node_id": node_id,
        "node_kind": kind,
        "name": node_id,
        "short_name": node_id,
        "description": f"Task-neutral {kind.value} fixture.",
        "tags": ("fixture",),
        "group": "fixture",
        "lifecycle": ModelObjectLifecycle.ACTIVE,
        "copied_from_node_id": None,
        "global_layout": _layout(node_id, x, y),
        "semantic_revision": 0,
        "layout_revision": 0,
        "technical_status": ModelTechnicalStatus.EXECUTABLE,
        "diagnostics": (),
        "content_hash": ZERO_HASH,
        "layout_hash": ZERO_HASH,
        "created_at": NOW,
        "updated_at": NOW,
    }


def _raw_node(
    node_id: str,
    family: RawInputFamily,
    source_id: str,
    modality: RawModality,
    *,
    x: float,
) -> ModelNode:
    provisional = ModelNode(
        **_node_fields(node_id, ModelNodeKind.RAW_INPUT, x=x, y=400.0),
        definition=RawInputNodeDefinition(
            family=family,
            resource_role=RawResourceRole.STREAM,
            source_descriptor=_source(source_id, modality),
            metadata={},
            help_text="Fixture raw input.",
        ),
    )
    return rehash_model_node(provisional)


def _recipe(recipe_id: str, bindings: tuple[tuple[str, str], ...]) -> EvidenceRecipe:
    inputs = tuple(
        RecipeInputBinding(
            binding_id=binding_id,
            kind=InputBindingKind.STREAM,
            source_id=source_id,
            name=binding_id,
            declared_type=_port_type(),
            selector={},
        )
        for binding_id, source_id in bindings
    )
    nodes = tuple(
        RecipeNode(
            node_id=f"input-{binding_id}",
            operator_id="input.binding",
            operator_version="0.1.0",
            input_binding_id=binding_id,
            parameters={},
        )
        for binding_id, _ in bindings
    )
    primary = NodePortReference(node_id=nodes[0].node_id, port_id="value")
    return EvidenceRecipe(
        recipe_id=recipe_id,
        recipe_version=1,
        anchor=RecipeAnchor(
            anchor_id=recipe_id,
            name=recipe_id,
            description="Task-neutral engineering fixture.",
            lifecycle=RecipeLifecycle.ACTIVE,
            scientific_status=RecipeScientificStatus.STARTER_TEMPLATE,
        ),
        inputs=inputs,
        graph=RecipeGraph(nodes=nodes, edges=()),
        outputs=(
            RecipeOutputBinding(
                output_id="primary",
                role=OutputRole.PRIMARY_VALUE,
                name="Primary",
                source=primary,
                unit=None,
            ),
        ),
        scoring=RecipeScoring(
            mode=ScoringMode.ORDERED_DAU,
            input=primary,
            parameters={
                "direction": "lower_is_better",
                "desired_boundary": 0.5,
                "adequate_boundary": 1.0,
                "likelihood_strength": 0.9,
            },
            custom_operator_id=None,
            custom_operator_version=None,
        ),
        documentation=RecipeDocumentation(
            summary="Fixture recipe; not a scientific claim.",
            assumptions=(),
            parameter_notes={},
            references=(),
        ),
        ui=RecipeUiMetadata(groups=(), preferred_layout={}),
    )


def _cpt(
    child: ModelNodeRef,
    parents: tuple[ModelNodeRef, ...],
    child_states: tuple[str, ...],
    parent_states: tuple[tuple[str, ...], ...],
) -> NodeCpt:
    if not parents:
        rows = ((0.33, 0.34, 0.33),)
    else:
        rows = (
            (0.70, 0.20, 0.10),
            (0.20, 0.60, 0.20),
            (0.10, 0.20, 0.70),
        )
    return NodeCpt(
        cpt_id=f"cpt.{child.node_id}",
        child_node=child,
        ordered_parent_nodes=parents,
        child_state_ids=child_states,
        ordered_parent_state_ids=parent_states,
        materialized_probabilities=rows,
        mode=CptMode.MANUAL,
        generator_metadata={"fixture": True},
        source=ComponentSource.ENGINEERING_DEFAULT,
    )


def _bn_node(
    node_id: str,
    role: BnNodeRole,
    parents: tuple[ModelNodeRef, ...],
    *,
    x: float,
    y: float,
) -> ModelNode:
    states = tuple(_state(state_id) for state_id in STATE_IDS)
    provisional = ModelNode(
        **_node_fields(node_id, ModelNodeKind.BN, x=x, y=y),
        definition=BnNodeDefinition(
            node_role=role,
            ordered_states=states,
            ordered_probabilistic_parent_nodes=parents,
            cpt=_cpt(
                _ref(ModelNodeKind.BN, node_id),
                parents,
                STATE_IDS,
                tuple(STATE_IDS for _ in parents),
            ),
            documentation="Task-neutral BN fixture.",
            scientific_status=ModelScientificStatus.STARTER_TEMPLATE,
            reporting_metadata={},
            provenance={"fixture": True},
            help_text="Fixture BN node.",
        ),
    )
    return rehash_model_node(provisional)


def _evidence_node(
    node_id: str,
    bindings: tuple[tuple[str, str, str], ...],
    parent_id: str,
    modality_weights: dict[str, float],
    *,
    x: float,
) -> ModelNode:
    parent = _ref(ModelNodeKind.BN, parent_id)
    recipe = _recipe(
        f"recipe.{node_id}",
        tuple((binding_id, source_id) for binding_id, source_id, _ in bindings),
    )
    states = tuple(_state(state_id) for state_id in OBSERVATION_STATE_IDS)
    provisional = ModelNode(
        **_node_fields(node_id, ModelNodeKind.EVIDENCE, x=x, y=300.0),
        definition=EvidenceNodeDefinition(
            recipe=recipe,
            data_bindings=tuple(
                EvidenceDataBinding(
                    recipe_input_binding_id=binding_id,
                    raw_input_node=_ref(ModelNodeKind.RAW_INPUT, raw_node_id),
                )
                for binding_id, _, raw_node_id in bindings
            ),
            ordered_observation_states=states,
            observation_mapping={
                state_id: {"state_id": state_id} for state_id in OBSERVATION_STATE_IDS
            },
            ordered_probabilistic_parent_nodes=(parent,),
            cpt=_cpt(
                _ref(ModelNodeKind.EVIDENCE, node_id),
                (parent,),
                OBSERVATION_STATE_IDS,
                (STATE_IDS,),
            ),
            observation_policy=ObservationPolicy.HARD_OR_VIRTUAL,
            modality_attribution_weights=modality_weights,
            scientific_status=ModelScientificStatus.STARTER_TEMPLATE,
            provenance={"fixture": True},
            help_text="Fixture Evidence node.",
        ),
    )
    return rehash_model_node(provisional)


def seven_node_graph() -> tuple[tuple[ModelNode, ...], TaskScheme]:
    """Return 3 Raw + 2 Evidence + 2 BN nodes and one partially active scheme."""

    raw_x = _raw_node("raw.x", RawInputFamily.X, "source.X", RawModality.X, x=50.0)
    raw_u = _raw_node("raw.u", RawInputFamily.U, "source.U", RawModality.U, x=150.0)
    raw_g = _raw_node("raw.g", RawInputFamily.G, "source.G", RawModality.G, x=250.0)
    competency = _bn_node(
        "bn.competency",
        BnNodeRole.AGGREGATE_COMPETENCY,
        (),
        x=150.0,
        y=50.0,
    )
    skill = _bn_node(
        "bn.skill",
        BnNodeRole.SUB_SKILL,
        (_ref(ModelNodeKind.BN, "bn.competency"),),
        x=150.0,
        y=150.0,
    )
    precision = _evidence_node(
        "evidence.precision",
        (
            ("flight-x", "source.X", "raw.x"),
            ("control-u", "source.U", "raw.u"),
        ),
        "bn.skill",
        {"X": 0.5, "U": 0.5},
        x=100.0,
    )
    gaze = _evidence_node(
        "evidence.gaze",
        (("gaze-g", "source.G", "raw.g"),),
        "bn.skill",
        {"G": 1.0},
        x=250.0,
    )
    nodes = (raw_x, raw_u, raw_g, competency, skill, precision, gaze)
    provisional_scheme = TaskScheme(
        scheme_id="scheme.base",
        name="Base Scheme",
        description="Task-neutral partially active fixture scheme.",
        tags=("fixture",),
        group="fixture",
        lifecycle=ModelObjectLifecycle.ACTIVE,
        copied_from_scheme_id=None,
        explicit_active_node_ids=("evidence.precision",),
        computed_active_closure=(
            "bn.competency",
            "bn.skill",
            "evidence.precision",
            "raw.u",
            "raw.x",
        ),
        output_node_ids=("bn.competency",),
        task_bindings={"task": "fixture"},
        layout_overrides=(_layout("evidence.precision", 110.0, 310.0),),
        semantic_revision=0,
        layout_revision=0,
        technical_status=ModelTechnicalStatus.EXECUTABLE,
        diagnostics=(),
        content_hash=ZERO_HASH,
        layout_hash=ZERO_HASH,
        created_at=NOW,
        updated_at=NOW,
    )
    return nodes, rehash_task_scheme(provisional_scheme)


def available_source_ids() -> frozenset[str]:
    return frozenset({"source.X", "source.U", "source.G"})


__all__ = [
    "NOW",
    "OBSERVATION_STATE_IDS",
    "STATE_IDS",
    "available_source_ids",
    "operator_registry",
    "seven_node_graph",
]
