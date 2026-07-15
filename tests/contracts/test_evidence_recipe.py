from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from pilot_assessment.contracts.evidence_recipe import (
    EvidenceRecipe,
    InputBindingKind,
    NodePortReference,
    OperatorDefinition,
    OperatorFamily,
    OperatorImplementationSource,
    OperatorPortDefinition,
    OutputRole,
    ParameterControlKind,
    ParameterUiDefinition,
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
    RecipeUiGroup,
    RecipeUiMetadata,
    ScoringMode,
    TemporalSemantics,
    TraceCapability,
)


def _number_type(*, unit: str | None = None) -> PortType:
    return PortType(
        value_type="number",
        cardinality=PortCardinality.ONE,
        temporal_semantics=TemporalSemantics.TIMELESS,
        unit=unit,
    )


def _operator_definition() -> OperatorDefinition:
    return OperatorDefinition(
        operator_id="constant.number",
        implementation_version="0.1.0",
        family=OperatorFamily.INPUT,
        name="Number constant",
        description="Produces one finite number configured by the recipe.",
        pseudocode="output = parameters.value",
        input_ports=(),
        output_ports=(
            OperatorPortDefinition(
                port_id="value",
                name="Value",
                description="Configured numeric value.",
                port_type=_number_type(),
            ),
        ),
        parameter_schema={
            "type": "object",
            "properties": {"value": {"type": "number"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        parameter_ui=(
            ParameterUiDefinition(
                parameter_path="/value",
                label="Value",
                group_id="main",
                control=ParameterControlKind.NUMBER,
                help_text="Finite number emitted by this node.",
                unit=None,
            ),
        ),
        trace_capability=TraceCapability.SUMMARY,
        implementation_source=OperatorImplementationSource.BUILT_IN,
        implementation_ref="builtin.constant.number",
    )


def _recipe() -> EvidenceRecipe:
    node = RecipeNode(
        node_id="configured-value",
        operator_id="constant.number",
        operator_version="0.1.0",
        parameters={"value": 3.5},
    )
    value_ref = NodePortReference(node_id=node.node_id, port_id="value")
    return EvidenceRecipe(
        recipe_id="starter.example",
        recipe_version=1,
        anchor=RecipeAnchor(
            anchor_id="EXAMPLE",
            name="Editable example",
            description="A deliberately provisional starter recipe.",
            lifecycle=RecipeLifecycle.ACTIVE,
            scientific_status=RecipeScientificStatus.STARTER_TEMPLATE,
        ),
        inputs=(
            RecipeInputBinding(
                binding_id="flight-x",
                kind=InputBindingKind.STREAM,
                source_id="X",
                name="Flight state",
                declared_type=PortType(
                    value_type="table",
                    cardinality=PortCardinality.ONE,
                    temporal_semantics=TemporalSemantics.SAMPLED,
                    unit=None,
                ),
                selector={"table_role": "samples"},
            ),
        ),
        graph=RecipeGraph(nodes=(node,), edges=()),
        outputs=(
            RecipeOutputBinding(
                output_id="primary",
                role=OutputRole.PRIMARY_VALUE,
                name="Primary value",
                source=value_ref,
                unit=None,
            ),
        ),
        scoring=RecipeScoring(
            mode=ScoringMode.ORDERED_DAU,
            input=value_ref,
            parameters={"desired_min": 3.0, "adequate_min": 2.0},
            custom_operator_id=None,
            custom_operator_version=None,
        ),
        documentation=RecipeDocumentation(
            summary="Starter-only example.",
            assumptions=("Thresholds require expert review.",),
            parameter_notes={"/scoring/desired_min": "Provisional engineering value."},
            references=(),
        ),
        ui=RecipeUiMetadata(
            groups=(
                RecipeUiGroup(
                    group_id="main",
                    label="Main parameters",
                    parameter_paths=("/graph/nodes/configured-value/parameters/value",),
                ),
            ),
            preferred_layout={
                "nodes": {"configured-value": {"x": 10.0, "y": 20.0}},
            },
        ),
    )


def test_recipe_and_operator_definition_round_trip_as_canonical_json() -> None:
    recipe = _recipe()
    definition = _operator_definition()

    recipe_payload = recipe.model_dump(mode="json")
    definition_payload = definition.model_dump(mode="json")

    assert EvidenceRecipe.model_validate(recipe_payload).model_dump(mode="json") == recipe_payload
    assert (
        OperatorDefinition.model_validate(definition_payload).model_dump(mode="json")
        == definition_payload
    )
    assert recipe.contract_id == "evidence-recipe"
    assert definition.contract_id == "operator-definition"


def test_nested_recipe_and_definition_json_are_immutable_snapshots() -> None:
    recipe = _recipe()
    definition = _operator_definition()

    with pytest.raises(TypeError):
        recipe.graph.nodes[0].parameters["value"] = 9.0
    with pytest.raises(TypeError):
        recipe.ui.preferred_layout["nodes"]["configured-value"]["x"] = 99.0  # type: ignore[index]
    with pytest.raises(TypeError):
        definition.parameter_schema["properties"]["value"]["minimum"] = 0.0  # type: ignore[index]


def test_incomplete_graph_is_a_valid_autosave_contract() -> None:
    recipe = _recipe()
    dangling = RecipeEdge(
        edge_id="unfinished-edge",
        source=NodePortReference(node_id="missing-source", port_id="value"),
        target=NodePortReference(node_id="missing-target", port_id="input"),
    )

    incomplete = recipe.model_copy(
        update={
            "graph": RecipeGraph(nodes=recipe.graph.nodes, edges=(dangling,)),
            "outputs": (),
            "scoring": None,
        }
    )

    assert incomplete.graph.edges == (dangling,)
    assert incomplete.outputs == ()
    assert incomplete.scoring is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("recipe_id", "bad id"),
        ("recipe_version", 0),
    ],
)
def test_recipe_rejects_structurally_invalid_identity(field: str, value: object) -> None:
    payload = _recipe().model_dump(mode="json")
    payload[field] = value

    with pytest.raises(ValidationError):
        EvidenceRecipe.model_validate(payload)


def test_recipe_rejects_nonfinite_or_extra_parameter_data() -> None:
    payload = _recipe().model_dump(mode="json")
    payload["graph"]["nodes"][0]["parameters"]["value"] = math.nan

    with pytest.raises(ValidationError):
        EvidenceRecipe.model_validate(payload)

    payload = _recipe().model_dump(mode="json")
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        EvidenceRecipe.model_validate(payload)


def test_operator_definition_rejects_duplicate_port_and_ui_paths() -> None:
    definition = _operator_definition()
    duplicate_port = definition.model_copy(update={"output_ports": definition.output_ports * 2})
    duplicate_ui = definition.model_copy(update={"parameter_ui": definition.parameter_ui * 2})

    with pytest.raises(ValidationError):
        OperatorDefinition.model_validate(duplicate_port.model_dump(mode="json"))
    with pytest.raises(ValidationError):
        OperatorDefinition.model_validate(duplicate_ui.model_dump(mode="json"))
