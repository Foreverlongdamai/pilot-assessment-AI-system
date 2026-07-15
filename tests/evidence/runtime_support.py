from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

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


def number_port(
    port_id: str,
    *,
    cardinality: PortCardinality = PortCardinality.ONE,
) -> OperatorPortDefinition:
    return OperatorPortDefinition(
        port_id=port_id,
        name=port_id,
        description="Runtime test port.",
        port_type=PortType(
            value_type="number",
            cardinality=cardinality,
            temporal_semantics=TemporalSemantics.TIMELESS,
            unit=None,
        ),
    )


def definition(
    operator_id: str,
    *,
    inputs: tuple[OperatorPortDefinition, ...] = (),
    outputs: tuple[OperatorPortDefinition, ...] = (number_port("value"),),
    parameter_schema: dict[str, JsonValue] | None = None,
) -> OperatorDefinition:
    return OperatorDefinition(
        operator_id=operator_id,
        implementation_version="0.1.0",
        family=OperatorFamily.COMPOSITION,
        name=operator_id,
        description="Runtime test definition.",
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
        trace_capability=TraceCapability.FULL,
        implementation_source=OperatorImplementationSource.BUILT_IN,
        implementation_ref=f"builtin.{operator_id}",
    )


ExecuteFunction = Callable[
    [Mapping[str, object], Mapping[str, JsonValue], OperatorExecutionContext],
    Mapping[str, object],
]


@dataclass
class RuntimeImplementation:
    operator_id: str
    function: ExecuteFunction
    implementation_version: str = "0.1.0"
    calls: list[tuple[Mapping[str, object], Mapping[str, JsonValue]]] = field(
        default_factory=list
    )

    @property
    def implementation_ref(self) -> str:
        return f"builtin.{self.operator_id}"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        self.calls.append((inputs, parameters))
        return self.function(inputs, parameters, context)


def registry_with(
    *entries: tuple[OperatorDefinition, RuntimeImplementation],
) -> OperatorRegistry:
    registry = OperatorRegistry()
    for operator_definition, implementation in entries:
        registry.register(operator_definition, implementation)
    return registry


def arithmetic_runtime() -> tuple[
    OperatorRegistry,
    dict[str, RuntimeImplementation],
]:
    constant_definition = definition(
        "constant.number",
        parameter_schema={
            "type": "object",
            "properties": {"value": {"type": "number"}},
            "required": ["value"],
            "additionalProperties": False,
        },
    )
    add_definition = definition(
        "math.add",
        inputs=(number_port("left"), number_port("right")),
    )
    left_right = RuntimeImplementation(
        "constant.number",
        lambda _inputs, parameters, _context: {"value": parameters["value"]},
    )
    add = RuntimeImplementation(
        "math.add",
        lambda inputs, _parameters, _context: {
            "value": float(inputs["left"]) + float(inputs["right"])
        },
    )
    return (
        registry_with(
            (constant_definition, left_right),
            (add_definition, add),
        ),
        {"constant.number": left_right, "math.add": add},
    )


def arithmetic_recipe() -> EvidenceRecipe:
    left = RecipeNode(
        node_id="left",
        operator_id="constant.number",
        operator_version="0.1.0",
        parameters={"value": 2.0},
    )
    right = RecipeNode(
        node_id="right",
        operator_id="constant.number",
        operator_version="0.1.0",
        parameters={"value": 3.0},
    )
    total = RecipeNode(
        node_id="sum",
        operator_id="math.add",
        operator_version="0.1.0",
        parameters={},
    )
    total_value = NodePortReference(node_id="sum", port_id="value")
    return EvidenceRecipe(
        recipe_id="runtime.arithmetic",
        recipe_version=1,
        anchor=RecipeAnchor(
            anchor_id="RUNTIME",
            name="Runtime arithmetic",
            description="Platform-only runtime fixture.",
            lifecycle=RecipeLifecycle.ACTIVE,
            scientific_status=RecipeScientificStatus.STARTER_TEMPLATE,
        ),
        inputs=(),
        graph=RecipeGraph(
            nodes=(total, right, left),
            edges=(
                RecipeEdge(
                    edge_id="right-to-sum",
                    source=NodePortReference(node_id="right", port_id="value"),
                    target=NodePortReference(node_id="sum", port_id="right"),
                ),
                RecipeEdge(
                    edge_id="left-to-sum",
                    source=NodePortReference(node_id="left", port_id="value"),
                    target=NodePortReference(node_id="sum", port_id="left"),
                ),
            ),
        ),
        outputs=(
            RecipeOutputBinding(
                output_id="primary",
                role=OutputRole.PRIMARY_VALUE,
                name="Primary",
                source=total_value,
                unit=None,
            ),
        ),
        scoring=RecipeScoring(
            mode=ScoringMode.ORDERED_DAU,
            input=total_value,
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
