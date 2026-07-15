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
from pilot_assessment.evidence.scoring import scoring_operator_identity


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
    scoring_outputs: Mapping[str, object]
    traces: tuple[NodeExecutionTrace, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "outputs", MappingProxyType(dict(self.outputs)))
        object.__setattr__(
            self,
            "scoring_outputs",
            MappingProxyType(dict(self.scoring_outputs)),
        )


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
    collected: dict[str, list[tuple[str | None, object]]] = defaultdict(list)
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
        collected[edge.target_port_id].append((edge.target_slot_id, value))

    port_types = {port.port_id: port.port_type for port in node.definition.input_ports}
    result: dict[str, object] = {}
    for port_id, slotted_values in collected.items():
        if port_types[port_id].cardinality is PortCardinality.MANY:
            named_values: dict[str, object] = {}
            for slot_id, value in slotted_values:
                assert slot_id is not None
                named_values[slot_id] = value
            result[port_id] = MappingProxyType(named_values)
        else:
            result[port_id] = slotted_values[0][1]
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
        if port_type.cardinality is not PortCardinality.OPTIONAL and port_id not in outputs
    )
    if missing:
        raise _fail(
            node,
            "recipe.execution.operator_output_missing",
            f"operator did not return required output ports: {missing!r}",
        )
    return outputs


def _scoring_error(
    code: str,
    message: str,
    operator_id: str,
    operator_version: str,
) -> RecipeExecutionError:
    return RecipeExecutionError(
        code,
        message,
        node_id="scoring",
        operator_id=operator_id,
        operator_version=operator_version,
    )


def _validated_scoring_outputs(
    raw_outputs: object,
    declared_ports: Mapping[str, PortCardinality],
    *,
    operator_id: str,
    operator_version: str,
) -> dict[str, object]:
    if not isinstance(raw_outputs, Mapping):
        raise _scoring_error(
            "recipe.execution.scorer_output_not_mapping",
            "scorer output must be a mapping keyed by output port ID",
            operator_id,
            operator_version,
        )
    outputs = dict(raw_outputs)
    extra = sorted(set(outputs) - set(declared_ports))
    if extra:
        raise _scoring_error(
            "recipe.execution.scorer_output_undeclared",
            f"scorer returned undeclared output ports: {extra!r}",
            operator_id,
            operator_version,
        )
    missing = sorted(
        port_id
        for port_id, cardinality in declared_ports.items()
        if cardinality is not PortCardinality.OPTIONAL and port_id not in outputs
    )
    if missing:
        raise _scoring_error(
            "recipe.execution.scorer_output_missing",
            f"scorer did not return required output ports: {missing!r}",
            operator_id,
            operator_version,
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
        if node.input_binding_id is not None and node.input_binding_id not in binding_values:
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
            node for node in compiled.nodes if node.node.node_id == compiled.scoring.input.node_id
        )
        raise _fail(
            source_node,
            "recipe.execution.scoring_value_missing",
            "scoring input port did not produce a value",
        ) from error

    scorer_identity = scoring_operator_identity(compiled.scoring)
    assert scorer_identity is not None
    scorer_id, scorer_version = scorer_identity
    try:
        scorer_definition = registry.definition(scorer_id, scorer_version)
        scorer_implementation = registry.implementation(scorer_id, scorer_version)
    except OperatorRegistryError as error:
        raise _scoring_error(
            "recipe.execution.scorer_unavailable",
            str(error),
            scorer_id,
            scorer_version,
        ) from error
    scoring_context = OperatorExecutionContext(
        recipe_id=compiled.recipe.recipe_id,
        recipe_version=compiled.recipe.recipe_version,
        node_id="scoring",
        binding_values=binding_values,
        trace_requested=False,
    )
    try:
        raw_scoring_outputs = scorer_implementation.execute(
            {"value": scoring_input},
            compiled.scoring.parameters,
            scoring_context,
        )
    except Exception as error:
        raise _scoring_error(
            "recipe.execution.scorer_failed",
            f"scorer raised {type(error).__name__}: {error}",
            scorer_id,
            scorer_version,
        ) from error
    scoring_outputs = _validated_scoring_outputs(
        raw_scoring_outputs,
        {port.port_id: port.port_type.cardinality for port in scorer_definition.output_ports},
        operator_id=scorer_id,
        operator_version=scorer_version,
    )

    return RecipeExecutionResult(
        recipe_id=compiled.recipe.recipe_id,
        recipe_version=compiled.recipe.recipe_version,
        outputs=result_outputs,
        scoring_input=scoring_input,
        scoring_outputs=scoring_outputs,
        traces=tuple(traces),
    )


__all__ = [
    "NodeExecutionTrace",
    "RecipeExecutionError",
    "RecipeExecutionResult",
    "execute_recipe",
]
