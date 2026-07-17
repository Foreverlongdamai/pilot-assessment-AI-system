from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from importlib.util import find_spec

import pytest
from pydantic import ValidationError

import pilot_assessment.contracts as public_contracts
import pilot_assessment.contracts.model_workspace as current
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

NOW = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def _port_type() -> PortType:
    return PortType(
        value_type="table",
        cardinality=PortCardinality.ONE,
        temporal_semantics=TemporalSemantics.SAMPLED,
        unit=None,
    )


def _source() -> SourceDescriptor:
    return SourceDescriptor(
        source_id="source.X",
        kind=SourceKind.RAW_STREAM,
        name="Flight state",
        description="Aligned X state stream.",
        declared_type=_port_type(),
        raw_modality=RawModality.X,
        source_dependencies=(),
        metadata={"clock": "master"},
        content_hash=HASH_A,
    )


def _recipe() -> EvidenceRecipe:
    node = RecipeNode(
        node_id="input-x",
        operator_id="input.binding",
        operator_version="0.1.0",
        input_binding_id="flight-x",
        parameters={},
    )
    output = NodePortReference(node_id="input-x", port_id="value")
    return EvidenceRecipe(
        recipe_id="recipe.precision",
        recipe_version=1,
        anchor=RecipeAnchor(
            anchor_id="precision",
            name="Trajectory precision",
            description="Provisional starter evidence.",
            lifecycle=RecipeLifecycle.ACTIVE,
            scientific_status=RecipeScientificStatus.STARTER_TEMPLATE,
        ),
        inputs=(
            RecipeInputBinding(
                binding_id="flight-x",
                kind=InputBindingKind.STREAM,
                source_id="source.X",
                name="Flight state",
                declared_type=_port_type(),
                selector={},
            ),
        ),
        graph=RecipeGraph(nodes=(node,), edges=()),
        outputs=(
            RecipeOutputBinding(
                output_id="primary",
                role=OutputRole.PRIMARY_VALUE,
                name="Precision",
                source=output,
                unit=None,
            ),
        ),
        scoring=RecipeScoring(
            mode=ScoringMode.ORDERED_DAU,
            input=output,
            parameters={"desired_max": 0.5, "adequate_max": 1.0},
            custom_operator_id=None,
            custom_operator_version=None,
        ),
        documentation=RecipeDocumentation(
            summary="Editable starter method.",
            assumptions=("Requires expert review.",),
            parameter_notes={},
            references=(),
        ),
        ui=RecipeUiMetadata(groups=(), preferred_layout={}),
    )


def _state(state_id: str) -> VariableState:
    return VariableState(
        state_id=state_id,
        label=state_id.title(),
        description=f"{state_id.title()} state.",
    )


def _ref(kind: current.ModelNodeKind, node_id: str) -> current.ModelNodeRef:
    return current.ModelNodeRef(node_id=node_id, node_kind=kind)


def _cpt(
    *,
    child: current.ModelNodeRef,
    parents: tuple[current.ModelNodeRef, ...],
    child_states: tuple[str, ...],
    parent_states: tuple[tuple[str, ...], ...],
    probabilities: tuple[tuple[float, ...], ...],
) -> current.NodeCpt:
    return current.NodeCpt(
        cpt_id=f"cpt.{child.node_id}",
        child_node=child,
        ordered_parent_nodes=parents,
        child_state_ids=child_states,
        ordered_parent_state_ids=parent_states,
        materialized_probabilities=probabilities,
        mode=CptMode.MANUAL,
        generator_metadata={},
        source=ComponentSource.ENGINEERING_DEFAULT,
    )


def _layout(node_id: str, *, x: float) -> current.NodeLayout:
    return current.NodeLayout(node_id=node_id, x=x, y=20.0)


def _node_fields(node_id: str, kind: current.ModelNodeKind, *, x: float) -> dict[str, object]:
    return {
        "node_id": node_id,
        "node_kind": kind,
        "name_zh": None,
        "name_en": node_id,
        "short_name_zh": None,
        "short_name_en": node_id,
        "description_zh": None,
        "description_en": f"Current complete {kind.value} node.",
        "tags": ("starter",),
        "group": None,
        "lifecycle": current.ModelObjectLifecycle.ACTIVE,
        "copied_from_node_id": None,
        "global_layout": _layout(node_id, x=x),
        "semantic_revision": 0,
        "layout_revision": 0,
        "technical_status": current.ModelTechnicalStatus.EXECUTABLE,
        "diagnostics": (),
        "content_hash": HASH_A,
        "layout_hash": HASH_B,
        "created_at": NOW,
        "updated_at": NOW,
    }


def _raw_node() -> current.ModelNode:
    node_id = "raw.x"
    return current.ModelNode(
        **_node_fields(node_id, current.ModelNodeKind.RAW_INPUT, x=10.0),
        definition=current.RawInputNodeDefinition(
            definition_kind="raw_input",
            family=current.RawInputFamily.X,
            resource_role=current.RawResourceRole.STREAM,
            source_descriptor=_source(),
            metadata={"display_group": "flight"},
            help_text_zh=None,
            help_text_en="Flight state fields and units.",
        ),
    )


def _bn_node() -> current.ModelNode:
    node_id = "bn.skill"
    child = _ref(current.ModelNodeKind.BN, node_id)
    states = (_state("good"), _state("poor"))
    return current.ModelNode(
        **_node_fields(node_id, current.ModelNodeKind.BN, x=200.0),
        definition=current.BnNodeDefinition(
            definition_kind="bn",
            node_role=BnNodeRole.SUB_SKILL,
            ordered_states=states,
            ordered_probabilistic_parent_nodes=(),
            cpt=_cpt(
                child=child,
                parents=(),
                child_states=tuple(state.state_id for state in states),
                parent_states=(),
                probabilities=((0.5, 0.5),),
            ),
            documentation="Editable sub-skill starter.",
            scientific_status=ModelScientificStatus.STARTER_TEMPLATE,
            reporting_metadata={},
            provenance={"origin": "starter"},
            help_text_zh=None,
            help_text_en="Latent BN node.",
        ),
    )


def _evidence_node() -> current.ModelNode:
    node_id = "evidence.precision"
    child = _ref(current.ModelNodeKind.EVIDENCE, node_id)
    parent = _ref(current.ModelNodeKind.BN, "bn.skill")
    states = (_state("desired"), _state("adequate"), _state("unacceptable"))
    return current.ModelNode(
        **_node_fields(node_id, current.ModelNodeKind.EVIDENCE, x=400.0),
        definition=current.EvidenceNodeDefinition(
            definition_kind="evidence",
            recipe=_recipe(),
            data_bindings=(
                current.EvidenceDataBinding(
                    recipe_input_binding_id="flight-x",
                    raw_input_node=_ref(current.ModelNodeKind.RAW_INPUT, "raw.x"),
                ),
            ),
            ordered_observation_states=states,
            observation_mapping={
                "desired": {"state_id": "desired"},
                "adequate": {"state_id": "adequate"},
                "unacceptable": {"state_id": "unacceptable"},
            },
            ordered_probabilistic_parent_nodes=(parent,),
            cpt=_cpt(
                child=child,
                parents=(parent,),
                child_states=tuple(state.state_id for state in states),
                parent_states=(("good", "poor"),),
                probabilities=((0.8, 0.15, 0.05), (0.1, 0.3, 0.6)),
            ),
            observation_policy=ObservationPolicy.HARD_OR_VIRTUAL,
            modality_attribution_weights={"X": 1.0},
            scientific_status=ModelScientificStatus.STARTER_TEMPLATE,
            provenance={"origin": "starter"},
            help_text_zh=None,
            help_text_en="Computed from the raw X stream.",
        ),
    )


def _scheme() -> current.TaskScheme:
    return current.TaskScheme(
        scheme_id="scheme.base",
        name_zh=None,
        name_en="Base Scheme",
        description_zh=None,
        description_en="Editable starter task scheme.",
        tags=("starter",),
        group=None,
        lifecycle=current.ModelObjectLifecycle.ACTIVE,
        copied_from_scheme_id=None,
        explicit_active_node_ids=("evidence.precision",),
        computed_active_closure=("bn.skill", "evidence.precision", "raw.x"),
        output_node_ids=("bn.skill",),
        task_bindings={"task_kind": "starter"},
        layout_overrides=(_layout("evidence.precision", x=450.0),),
        semantic_revision=0,
        layout_revision=0,
        technical_status=current.ModelTechnicalStatus.EXECUTABLE,
        diagnostics=(),
        content_hash=HASH_A,
        layout_hash=HASH_B,
        created_at=NOW,
        updated_at=NOW,
    )


def test_current_model_workspace_contract_module_exists() -> None:
    assert find_spec("pilot_assessment.contracts.model_workspace") is not None


def test_current_model_contracts_are_exported_from_public_package() -> None:
    assert public_contracts.ModelNode is current.ModelNode
    assert public_contracts.TaskScheme is current.TaskScheme
    assert public_contracts.ModelGraphSnapshot is current.ModelGraphSnapshot


def test_complete_nodes_round_trip_with_discriminated_definitions() -> None:
    raw = _raw_node()
    evidence = _evidence_node()
    bn = _bn_node()

    for node in (raw, evidence, bn):
        assert current.ModelNode.model_validate_json(node.model_dump_json()) == node
        assert node.global_layout.node_id == node.node_id

    assert evidence.definition.definition_kind == "evidence"
    assert tuple(
        binding.raw_input_node.node_kind for binding in evidence.definition.data_bindings
    ) == (current.ModelNodeKind.RAW_INPUT,)
    assert bn.definition.definition_kind == "bn"


def test_node_identity_requires_bilingual_fallback_and_matching_definition_kind() -> None:
    raw = _raw_node()

    missing_name = raw.model_dump(mode="json")
    missing_name.update(name_zh=None, name_en=None)
    with pytest.raises(ValidationError, match="name"):
        current.ModelNode.model_validate(missing_name)

    wrong_definition = raw.model_dump(mode="json")
    wrong_definition["node_kind"] = "evidence"
    with pytest.raises(ValidationError, match="definition"):
        current.ModelNode.model_validate(wrong_definition)

    wrong_layout = raw.model_dump(mode="json")
    wrong_layout["global_layout"]["node_id"] = "raw.other"
    with pytest.raises(ValidationError, match="layout"):
        current.ModelNode.model_validate(wrong_layout)

    non_utc = raw.model_dump(mode="python")
    non_utc["updated_at"] = NOW.astimezone(timezone(timedelta(hours=1)))
    with pytest.raises(ValidationError, match="UTC"):
        current.ModelNode.model_validate(non_utc)

    invalid_identity = raw.model_dump(mode="json")
    invalid_identity.update(node_id="invalid node id", content_hash="not-a-sha256")
    with pytest.raises(ValidationError):
        current.ModelNode.model_validate(invalid_identity)


def test_evidence_data_and_probabilistic_parents_are_typed_separately() -> None:
    with pytest.raises(ValidationError, match="Raw Input"):
        current.EvidenceDataBinding(
            recipe_input_binding_id="flight-x",
            raw_input_node=_ref(current.ModelNodeKind.EVIDENCE, "evidence.other"),
        )

    evidence = _evidence_node()
    payload = evidence.model_dump(mode="json")
    payload["definition"]["ordered_probabilistic_parent_nodes"][0]["node_kind"] = "raw_input"
    payload["definition"]["cpt"]["ordered_parent_nodes"][0]["node_kind"] = "raw_input"
    with pytest.raises(ValidationError, match="probabilistic parent"):
        current.ModelNode.model_validate(payload)

    extra_recipe = _bn_node().model_dump(mode="json")
    extra_recipe["definition"]["recipe"] = _recipe().model_dump(mode="json")
    with pytest.raises(ValidationError):
        current.ModelNode.model_validate(extra_recipe)

    raw_with_cpt = _raw_node().model_dump(mode="json")
    raw_with_cpt["definition"]["cpt"] = _bn_node().definition.cpt.model_dump(mode="json")
    with pytest.raises(ValidationError):
        current.ModelNode.model_validate(raw_with_cpt)


def test_evidence_bindings_cover_recipe_inputs_exactly() -> None:
    evidence = _evidence_node()
    payload = evidence.model_dump(mode="json")
    payload["definition"]["data_bindings"] = []

    with pytest.raises(ValidationError, match="recipe input"):
        current.ModelNode.model_validate(payload)


def test_node_cpt_enforces_parent_axes_shape_finite_values_and_row_sums() -> None:
    cpt = _evidence_node().definition.cpt
    assert current.NodeCpt.model_validate_json(cpt.model_dump_json()) == cpt

    wrong_rows = cpt.model_dump(mode="json")
    wrong_rows["materialized_probabilities"] = [wrong_rows["materialized_probabilities"][0]]
    with pytest.raises(ValidationError, match="row count"):
        current.NodeCpt.model_validate(wrong_rows)

    wrong_sum = cpt.model_dump(mode="json")
    wrong_sum["materialized_probabilities"][0] = [0.8, 0.15, 0.15]
    with pytest.raises(ValidationError, match="sum"):
        current.NodeCpt.model_validate(wrong_sum)

    nonfinite = cpt.model_dump(mode="json")
    nonfinite["materialized_probabilities"][0][0] = float("nan")
    with pytest.raises(ValidationError):
        current.NodeCpt.model_validate(nonfinite)

    incomplete = cpt.model_dump(mode="json")
    incomplete.update(mode="incomplete", materialized_probabilities=[])
    assert current.NodeCpt.model_validate(incomplete).materialized_probabilities == ()

    duplicate_parent = cpt.model_dump(mode="json")
    duplicate_parent["ordered_parent_nodes"].append(duplicate_parent["ordered_parent_nodes"][0])
    duplicate_parent["ordered_parent_state_ids"].append(["low", "high"])
    with pytest.raises(ValidationError, match="parent nodes"):
        current.NodeCpt.model_validate(duplicate_parent)

    duplicate_state = cpt.model_dump(mode="json")
    duplicate_state["child_state_ids"] = ["desired", "desired", "undesired"]
    with pytest.raises(ValidationError, match="state IDs"):
        current.NodeCpt.model_validate(duplicate_state)


def test_nested_current_node_json_is_an_immutable_snapshot() -> None:
    evidence = _evidence_node()

    with pytest.raises(TypeError):
        evidence.definition.observation_mapping["desired"] = {"state_id": "changed"}
    with pytest.raises(TypeError):
        evidence.definition.provenance["origin"] = "changed"
    with pytest.raises(TypeError):
        evidence.definition.recipe.graph.nodes[0].parameters["x"] = 1


def test_task_scheme_enforces_activation_closure_outputs_and_canonical_sets() -> None:
    scheme = _scheme()

    assert current.TaskScheme.model_validate_json(scheme.model_dump_json()) == scheme
    assert scheme.semantic_revision == 0
    assert scheme.layout_revision == 0

    missing_explicit = scheme.model_dump(mode="json")
    missing_explicit["computed_active_closure"] = ["bn.skill", "raw.x"]
    with pytest.raises(ValidationError, match="explicit"):
        current.TaskScheme.model_validate(missing_explicit)

    inactive_output = scheme.model_dump(mode="json")
    inactive_output["output_node_ids"] = ["bn.not-active"]
    with pytest.raises(ValidationError, match="output"):
        current.TaskScheme.model_validate(inactive_output)

    noncanonical = scheme.model_dump(mode="json")
    noncanonical["computed_active_closure"] = ["raw.x", "bn.skill", "evidence.precision"]
    with pytest.raises(ValidationError, match="canonical"):
        current.TaskScheme.model_validate(noncanonical)

    noncanonical_outputs = scheme.model_dump(mode="json")
    noncanonical_outputs["output_node_ids"] = ["evidence.precision", "bn.skill"]
    with pytest.raises(ValidationError, match="canonical"):
        current.TaskScheme.model_validate(noncanonical_outputs)

    with pytest.raises(TypeError):
        scheme.task_bindings["task_kind"] = "changed"


def test_graph_snapshot_uses_unique_current_nodes_and_typed_edges() -> None:
    nodes = (_bn_node(), _evidence_node(), _raw_node())
    extraction = current.ModelGraphEdge(
        edge_id="edge.raw-x.precision",
        edge_kind=current.ModelGraphEdgeKind.EXTRACTION,
        parent=_ref(current.ModelNodeKind.RAW_INPUT, "raw.x"),
        child=_ref(current.ModelNodeKind.EVIDENCE, "evidence.precision"),
        recipe_input_binding_id="flight-x",
    )
    probabilistic = current.ModelGraphEdge(
        edge_id="edge.skill.precision",
        edge_kind=current.ModelGraphEdgeKind.PROBABILISTIC,
        parent=_ref(current.ModelNodeKind.BN, "bn.skill"),
        child=_ref(current.ModelNodeKind.EVIDENCE, "evidence.precision"),
        recipe_input_binding_id=None,
    )
    snapshot = current.ModelGraphSnapshot(
        project_id="project.alpha",
        scheme=_scheme(),
        nodes=nodes,
        edges=(extraction, probabilistic),
        generated_at=NOW,
        graph_hash=HASH_C,
    )

    assert current.ModelGraphSnapshot.model_validate_json(snapshot.model_dump_json()) == snapshot
    duplicate = snapshot.model_dump(mode="json")
    duplicate["nodes"].append(duplicate["nodes"][0])
    with pytest.raises(ValidationError, match="node"):
        current.ModelGraphSnapshot.model_validate(duplicate)


def test_change_event_and_deactivation_impact_are_strict_frozen_contracts() -> None:
    diff = current.CanonicalModelDiff(
        changed_paths=("/explicit_active_node_ids",),
        added_node_ids=(),
        removed_node_ids=("bn.skill", "evidence.precision"),
        added_edge_ids=(),
        removed_edge_ids=("edge.skill.precision",),
        metadata={"reason": "cascade"},
    )
    impact = current.DeactivationImpact(
        scheme_id="scheme.base",
        scheme_semantic_revision=0,
        requested_node_id="bn.skill",
        impacted_node_ids=("bn.skill", "evidence.precision"),
        impacted_edge_ids=("edge.skill.precision",),
        impact_hash=HASH_A,
    )
    event = current.ModelChangeEvent(
        event_id="event.one",
        object_kind=current.ModelObjectKind.SCHEME,
        object_id="scheme.base",
        event_kind=current.ModelChangeKind.UPDATE,
        parent_event_id=None,
        semantic_revision=1,
        layout_revision=0,
        before_hash=HASH_A,
        after_hash=HASH_B,
        diff=diff,
        transaction_id="tx.one",
        actor_id="expert.one",
        occurred_at=NOW,
    )

    assert current.DeactivationImpact.model_validate_json(impact.model_dump_json()) == impact
    assert current.ModelChangeEvent.model_validate_json(event.model_dump_json()) == event
    with pytest.raises(TypeError):
        event.diff.metadata["reason"] = "changed"
