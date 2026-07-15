from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import JsonValue

from pilot_assessment.contracts.evidence_recipe import (
    EvidenceRecipe,
    NodePortReference,
    OperatorDefinition,
    OperatorFamily,
    OperatorImplementationSource,
    OperatorPortDefinition,
    OutputRole,
    PortCardinality,
    PortType,
    RecipeAnchor,
    RecipeDocumentation,
    RecipeEdge,
    RecipeGraph,
    RecipeLifecycle,
    RecipeNode,
    RecipeOutputBinding,
    RecipeScientificStatus,
    RecipeScoring,
    RecipeUiMetadata,
    ScoringMode,
    TemporalSemantics,
    TraceCapability,
)
from pilot_assessment.evidence.operators import OperatorExecutionContext
from pilot_assessment.evidence.registry import OperatorRegistry
from pilot_assessment.evidence.validation import (
    RecipeValidationDisposition,
    validate_recipe,
)


def _port(
    port_id: str,
    *,
    value_type: str = "number",
    cardinality: PortCardinality = PortCardinality.ONE,
    unit: str | None = None,
    temporal: TemporalSemantics = TemporalSemantics.TIMELESS,
) -> OperatorPortDefinition:
    return OperatorPortDefinition(
        port_id=port_id,
        name=port_id,
        description="Test port.",
        port_type=PortType(
            value_type=value_type,
            cardinality=cardinality,
            temporal_semantics=temporal,
            unit=unit,
        ),
    )


def _definition(
    operator_id: str,
    *,
    family: OperatorFamily = OperatorFamily.COMPOSITION,
    inputs: tuple[OperatorPortDefinition, ...] = (),
    outputs: tuple[OperatorPortDefinition, ...] = (_port("value"),),
    parameter_schema: dict[str, JsonValue] | None = None,
) -> OperatorDefinition:
    return OperatorDefinition(
        operator_id=operator_id,
        implementation_version="0.1.0",
        family=family,
        name=operator_id,
        description="Test definition.",
        pseudocode=None,
        input_ports=inputs,
        output_ports=outputs,
        parameter_schema=parameter_schema
        or {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        parameter_ui=(),
        trace_capability=TraceCapability.NONE,
        implementation_source=OperatorImplementationSource.BUILT_IN,
        implementation_ref=f"builtin.{operator_id}",
    )


@dataclass(frozen=True)
class _Implementation:
    operator_id: str
    implementation_version: str = "0.1.0"

    @property
    def implementation_ref(self) -> str:
        return f"builtin.{self.operator_id}"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del inputs, parameters, context
        return {"value": 1.0}


def _registry(*definitions: OperatorDefinition) -> OperatorRegistry:
    registry = OperatorRegistry()
    all_definitions = list(definitions)
    if not any(item.operator_id == "scoring.ordered-dau" for item in all_definitions):
        all_definitions.append(
            _definition(
                "scoring.ordered-dau",
                family=OperatorFamily.SCORING,
                inputs=(_port("value"),),
            )
        )
    for definition_item in all_definitions:
        registry.register(
            definition_item,
            _Implementation(definition_item.operator_id),
        )
    return registry


def _valid_recipe() -> EvidenceRecipe:
    source = RecipeNode(
        node_id="source",
        operator_id="constant.number",
        operator_version="0.1.0",
        parameters={"value": 1.0},
    )
    sink = RecipeNode(
        node_id="sink",
        operator_id="identity.number",
        operator_version="0.1.0",
        parameters={},
    )
    sink_value = NodePortReference(node_id="sink", port_id="value")
    return EvidenceRecipe(
        recipe_id="validation.example",
        recipe_version=1,
        anchor=RecipeAnchor(
            anchor_id="EXAMPLE",
            name="Validation example",
            description="Platform-only test recipe.",
            lifecycle=RecipeLifecycle.ACTIVE,
            scientific_status=RecipeScientificStatus.STARTER_TEMPLATE,
        ),
        inputs=(),
        graph=RecipeGraph(
            nodes=(source, sink),
            edges=(
                RecipeEdge(
                    edge_id="source-to-sink",
                    source=NodePortReference(node_id="source", port_id="value"),
                    target=NodePortReference(node_id="sink", port_id="input"),
                ),
            ),
        ),
        outputs=(
            RecipeOutputBinding(
                output_id="primary",
                role=OutputRole.PRIMARY_VALUE,
                name="Primary",
                source=sink_value,
                unit=None,
            ),
        ),
        scoring=RecipeScoring(
            mode=ScoringMode.ORDERED_DAU,
            input=sink_value,
            parameters={},
            custom_operator_id=None,
            custom_operator_version=None,
        ),
        documentation=RecipeDocumentation(
            summary="",
            assumptions=(),
            parameter_notes={},
            references=(),
        ),
        ui=RecipeUiMetadata(groups=(), preferred_layout={}),
    )


def _base_registry() -> OperatorRegistry:
    return _registry(
        _definition(
            "constant.number",
            parameter_schema={
                "type": "object",
                "properties": {"value": {"type": "number"}},
                "required": ["value"],
                "additionalProperties": False,
            },
        ),
        _definition("identity.number", inputs=(_port("input"),)),
    )


def _codes(recipe: EvidenceRecipe, registry: OperatorRegistry) -> set[str]:
    return {item.code for item in validate_recipe(recipe, registry).diagnostics}


def test_valid_recipe_is_executable_without_scientific_gate() -> None:
    outcome = validate_recipe(_valid_recipe(), _base_registry())

    assert outcome.disposition is RecipeValidationDisposition.EXECUTABLE
    assert outcome.diagnostics == ()


def test_incomplete_recipe_reports_dangling_graph_output_and_scorer() -> None:
    recipe = _valid_recipe().model_copy(
        update={
            "graph": RecipeGraph(
                nodes=(),
                edges=(
                    RecipeEdge(
                        edge_id="unfinished",
                        source=NodePortReference(node_id="missing-a", port_id="value"),
                        target=NodePortReference(node_id="missing-b", port_id="input"),
                    ),
                ),
            ),
            "outputs": (),
            "scoring": None,
        }
    )

    outcome = validate_recipe(recipe, _base_registry())

    assert outcome.disposition is RecipeValidationDisposition.INCOMPLETE
    assert {
        "recipe.edge.source_node_missing",
        "recipe.edge.target_node_missing",
        "recipe.primary_output_missing",
        "recipe.scoring_missing",
    } <= {item.code for item in outcome.diagnostics}


def test_unknown_operator_and_invalid_parameters_are_localized() -> None:
    recipe = _valid_recipe()
    source, sink = recipe.graph.nodes
    invalid_source = source.model_copy(update={"parameters": {"value": "not-a-number"}})
    unknown_sink = sink.model_copy(update={"operator_id": "unknown.operator"})
    candidate = recipe.model_copy(
        update={
            "graph": RecipeGraph(
                nodes=(invalid_source, unknown_sink),
                edges=recipe.graph.edges,
            )
        }
    )

    outcome = validate_recipe(candidate, _base_registry())

    assert {
        "recipe.operator_unknown",
        "recipe.parameters_invalid",
    } <= {item.code for item in outcome.diagnostics}
    assert any(
        item.location.startswith("/graph/nodes/source/parameters")
        for item in outcome.diagnostics
    )
    assert any(
        item.location == "/graph/nodes/sink/operator_id"
        for item in outcome.diagnostics
    )


def test_duplicate_ids_are_technical_errors_not_parse_errors() -> None:
    recipe = _valid_recipe()
    candidate = recipe.model_copy(
        update={
            "graph": RecipeGraph(
                nodes=recipe.graph.nodes + (recipe.graph.nodes[0],),
                edges=recipe.graph.edges + (recipe.graph.edges[0],),
            ),
            "outputs": recipe.outputs + (recipe.outputs[0],),
        }
    )

    assert {
        "recipe.node_id_duplicate",
        "recipe.edge_id_duplicate",
        "recipe.output_id_duplicate",
    } <= _codes(candidate, _base_registry())


def test_cycle_and_required_input_are_reported_without_execution() -> None:
    recipe = _valid_recipe()
    reverse = RecipeEdge(
        edge_id="sink-to-source",
        source=NodePortReference(node_id="sink", port_id="value"),
        target=NodePortReference(node_id="source", port_id="input"),
    )
    source_definition = _definition(
        "constant.number",
        inputs=(_port("input"),),
        parameter_schema={
            "type": "object",
            "properties": {"value": {"type": "number"}},
            "required": ["value"],
            "additionalProperties": False,
        },
    )
    registry = _registry(
        source_definition,
        _definition("identity.number", inputs=(_port("input"),)),
    )
    cyclic = recipe.model_copy(
        update={
            "graph": RecipeGraph(
                nodes=recipe.graph.nodes,
                edges=recipe.graph.edges + (reverse,),
            )
        }
    )

    assert "recipe.graph_cycle" in _codes(cyclic, registry)

    disconnected = recipe.model_copy(
        update={"graph": RecipeGraph(nodes=recipe.graph.nodes, edges=())}
    )
    assert "recipe.required_input_missing" in _codes(disconnected, _base_registry())


def test_port_type_unit_temporal_and_cardinality_mismatches_are_reported() -> None:
    recipe = _valid_recipe()
    text_source = _definition(
        "constant.number",
        outputs=(
            _port(
                "value",
                value_type="text",
                unit="deg",
                temporal=TemporalSemantics.SAMPLED,
            ),
        ),
        parameter_schema={
            "type": "object",
            "properties": {"value": {"type": "number"}},
            "required": ["value"],
            "additionalProperties": False,
        },
    )
    number_sink = _definition(
        "identity.number",
        inputs=(
            _port(
                "input",
                value_type="number",
                unit="rad",
                temporal=TemporalSemantics.TIMELESS,
            ),
        ),
    )
    mismatch_codes = _codes(recipe, _registry(text_source, number_sink))

    assert {
        "recipe.port_type_mismatch",
        "recipe.port_unit_mismatch",
        "recipe.port_temporal_mismatch",
    } <= mismatch_codes

    extra_edge = RecipeEdge(
        edge_id="second-source-to-sink",
        source=NodePortReference(node_id="source", port_id="value"),
        target=NodePortReference(node_id="sink", port_id="input"),
    )
    too_many = recipe.model_copy(
        update={
            "graph": RecipeGraph(
                nodes=recipe.graph.nodes,
                edges=recipe.graph.edges + (extra_edge,),
            )
        }
    )
    assert "recipe.input_cardinality_exceeded" in _codes(
        too_many, _base_registry()
    )


def test_output_and_custom_scorer_must_resolve_declared_output_ports() -> None:
    recipe = _valid_recipe()
    bad_ref = NodePortReference(node_id="sink", port_id="missing")
    candidate = recipe.model_copy(
        update={
            "outputs": (
                recipe.outputs[0].model_copy(update={"source": bad_ref}),
            ),
            "scoring": RecipeScoring(
                mode=ScoringMode.CUSTOM_OPERATOR,
                input=bad_ref,
                parameters={},
                custom_operator_id=None,
                custom_operator_version=None,
            ),
        }
    )

    assert {
        "recipe.output_port_missing",
        "recipe.scoring_input_port_missing",
        "recipe.custom_scorer_identity_missing",
    } <= _codes(candidate, _base_registry())


def test_node_external_input_binding_must_resolve_by_stable_id() -> None:
    recipe = _valid_recipe()
    source, sink = recipe.graph.nodes
    bound_source = source.model_copy(
        update={"input_binding_id": "missing-binding"}
    )
    candidate = recipe.model_copy(
        update={
            "graph": RecipeGraph(
                nodes=(bound_source, sink),
                edges=recipe.graph.edges,
            )
        }
    )

    assert "recipe.input_binding_missing" in _codes(candidate, _base_registry())


def test_many_input_edges_require_unique_stable_target_slots() -> None:
    recipe = _valid_recipe()
    source, sink = recipe.graph.nodes
    many_sink = _definition(
        "identity.number",
        inputs=(_port("input", cardinality=PortCardinality.MANY),),
    )
    registry = _registry(
        _definition(
            "constant.number",
            parameter_schema={
                "type": "object",
                "properties": {"value": {"type": "number"}},
                "required": ["value"],
                "additionalProperties": False,
            },
        ),
        many_sink,
    )
    first = recipe.graph.edges[0].model_copy(update={"target_slot_id": "x"})
    second = RecipeEdge(
        edge_id="second-slot",
        source=NodePortReference(node_id=source.node_id, port_id="value"),
        target=NodePortReference(node_id=sink.node_id, port_id="input"),
        target_slot_id="y",
    )
    valid = recipe.model_copy(
        update={"graph": RecipeGraph(nodes=(source, sink), edges=(first, second))}
    )
    assert validate_recipe(valid, registry).disposition == "executable"

    missing_slot = first.model_copy(update={"target_slot_id": None})
    missing = valid.model_copy(
        update={"graph": RecipeGraph(nodes=(source, sink), edges=(missing_slot, second))}
    )
    assert "recipe.many_input_slot_missing" in _codes(missing, registry)

    duplicate_slot = second.model_copy(update={"target_slot_id": "x"})
    duplicate = valid.model_copy(
        update={"graph": RecipeGraph(nodes=(source, sink), edges=(first, duplicate_slot))}
    )
    assert "recipe.many_input_slot_duplicate" in _codes(duplicate, registry)
