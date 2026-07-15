"""Generic executor for compiled evidence computation graphs."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from pilot_assessment.contracts.evidence_recipe import PortCardinality
from pilot_assessment.evidence.compiler import CompiledNode, CompiledRecipe
from pilot_assessment.evidence.operators import OperatorExecutionContext
from pilot_assessment.evidence.registry import OperatorRegistry, OperatorRegistryError


class RecipeExecutionError(RuntimeError):
    """Node-localized technical execution failure."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        node_id: str,
        operator_id: str,
        operator_version: str,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.node_id = node_id
        self.operator_id = operator_id
        self.operator_version = operator_version


@dataclass(frozen=True, slots=True)
class NodeExecutionTrace:
    node_id: str
    operator_id: str
    operator_version: str
    input_ports: tuple[str, ...]
    output_ports: tuple[str, ...]
    captured_inputs: Mapping[str, object] | None
    captured_outputs: Mapping[str, object] | None

    def __post_init__(self) -> None:
        if self.captured_inputs is not None:
            object.__setattr__(
                self,
                "captured_inputs",
                MappingProxyType(dict(self.captured_inputs)),
            )
        if self.captured_outputs is not None:
            object.__setattr__(
                self,
                "captured_outputs",
                MappingProxyType(dict(self.captured_outputs)),
            )


@dataclass(frozen=True, slots=True)
class RecipeExecutionResult:
    recipe_id: str
    recipe_version: int
    outputs: Mapping[str, object]
    scoring_input: object
    traces: tuple[NodeExecutionTrace, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "outputs", MappingProxyType(dict(self.outputs)))


def _fail(
    node: CompiledNode,
    code: str,
    message: str,
) -> RecipeExecutionError:
    return RecipeExecutionError(
        code,
        message,
        node_id=node.node.node_id,
        operator_id=node.node.operator_id,
        operator_version=node.node.operator_version,
    )


def _node_inputs(
    node: CompiledNode,
    values: Mapping[tuple[str, str], object],
) -> dict[str, object]:
    collected: dict[str, list[object]] = defaultdict(list)
    for edge in node.incoming_edges:
        key = (edge.source_node_id, edge.source_port_id)
        try:
            value = values[key]
        except KeyError as error:
            raise _fail(
                node,
                "recipe.execution.upstream_value_missing",
                f"upstream value {key!r} was not produced",
            ) from error
        collected[edge.target_port_id].append(value)

    port_types = {
        port.port_id: port.port_type for port in node.definition.input_ports
    }
    result: dict[str, object] = {}
    for port_id, port_values in collected.items():
        if port_types[port_id].cardinality is PortCardinality.MANY:
            result[port_id] = tuple(port_values)
        else:
            result[port_id] = port_values[0]
    return result


def _validated_outputs(
    node: CompiledNode,
    raw_outputs: object,
) -> dict[str, object]:
    if not isinstance(raw_outputs, Mapping):
        raise _fail(
            node,
            "recipe.execution.operator_output_not_mapping",
            "operator output must be a mapping keyed by output port ID",
        )
    outputs = dict(raw_outputs)
    if any(type(key) is not str for key in outputs):
        raise _fail(
            node,
            "recipe.execution.operator_output_key_invalid",
            "operator output port IDs must be strings",
        )
    declared = {port.port_id: port.port_type for port in node.definition.output_ports}
    extra = sorted(set(outputs) - set(declared))
    if extra:
        raise _fail(
            node,
            "recipe.execution.operator_output_undeclared",
            f"operator returned undeclared output ports: {extra!r}",
        )
    missing = sorted(
        port_id
        for port_id, port_type in declared.items()
        if port_type.cardinality is not PortCardinality.OPTIONAL
        and port_id not in outputs
    )
    if missing:
        raise _fail(
            node,
            "recipe.execution.operator_output_missing",
            f"operator did not return required output ports: {missing!r}",
        )
    return outputs


def execute_recipe(
    compiled: CompiledRecipe,
    registry: OperatorRegistry,
    *,
    binding_values: Mapping[str, object],
    trace_node_ids: Iterable[str] = (),
) -> RecipeExecutionResult:
    """Execute exactly the compiled recipe snapshot and return selected traces."""

    selected_traces = frozenset(trace_node_ids)
    node_values: dict[tuple[str, str], object] = {}
    traces: list[NodeExecutionTrace] = []
    for compiled_node in compiled.nodes:
        node = compiled_node.node
        if (
            node.input_binding_id is not None
            and node.input_binding_id not in binding_values
        ):
            raise _fail(
                compiled_node,
                "recipe.execution.binding_value_missing",
                f"execution value for input binding {node.input_binding_id!r} is missing",
            )
        inputs = _node_inputs(compiled_node, node_values)
        try:
            implementation = registry.implementation(
                node.operator_id,
                node.operator_version,
            )
        except OperatorRegistryError as error:
            raise _fail(
                compiled_node,
                "recipe.execution.operator_unavailable",
                str(error),
            ) from error
        context = OperatorExecutionContext(
            recipe_id=compiled.recipe.recipe_id,
            recipe_version=compiled.recipe.recipe_version,
            node_id=node.node_id,
            binding_values=binding_values,
            input_binding_id=node.input_binding_id,
            trace_requested=node.node_id in selected_traces,
        )
        try:
            raw_outputs = implementation.execute(inputs, node.parameters, context)
        except RecipeExecutionError:
            raise
        except Exception as error:
            raise _fail(
                compiled_node,
                "recipe.execution.operator_failed",
                f"operator raised {type(error).__name__}: {error}",
            ) from error
        outputs = _validated_outputs(compiled_node, raw_outputs)
        for port_id, value in outputs.items():
            node_values[(node.node_id, port_id)] = value
        capture = node.node_id in selected_traces
        traces.append(
            NodeExecutionTrace(
                node_id=node.node_id,
                operator_id=node.operator_id,
                operator_version=node.operator_version,
                input_ports=tuple(sorted(inputs)),
                output_ports=tuple(sorted(outputs)),
                captured_inputs=inputs if capture else None,
                captured_outputs=outputs if capture else None,
            )
        )

    result_outputs: dict[str, object] = {}
    for output in compiled.outputs:
        key = (output.source.node_id, output.source.port_id)
        try:
            result_outputs[output.output_id] = node_values[key]
        except KeyError as error:
            source_node = next(
                node for node in compiled.nodes if node.node.node_id == output.source.node_id
            )
            raise _fail(
                source_node,
                "recipe.execution.output_value_missing",
                f"recipe output {output.output_id!r} has no produced value",
            ) from error

    assert compiled.scoring.input is not None
    scoring_key = (
        compiled.scoring.input.node_id,
        compiled.scoring.input.port_id,
    )
    try:
        scoring_input = node_values[scoring_key]
    except KeyError as error:
        source_node = next(
            node
            for node in compiled.nodes
            if node.node.node_id == compiled.scoring.input.node_id
        )
        raise _fail(
            source_node,
            "recipe.execution.scoring_value_missing",
            "scoring input port did not produce a value",
        ) from error

    return RecipeExecutionResult(
        recipe_id=compiled.recipe.recipe_id,
        recipe_version=compiled.recipe.recipe_version,
        outputs=result_outputs,
        scoring_input=scoring_input,
        traces=tuple(traces),
    )


__all__ = [
    "NodeExecutionTrace",
    "RecipeExecutionError",
    "RecipeExecutionResult",
    "execute_recipe",
]
