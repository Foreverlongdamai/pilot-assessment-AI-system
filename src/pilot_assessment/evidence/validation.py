"""Only-technical validation for editable evidence recipe drafts."""

from __future__ import annotations

import heapq
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import JsonValue

from pilot_assessment.contracts.evidence_recipe import (
    EvidenceRecipe,
    NodePortReference,
    OperatorDefinition,
    OperatorFamily,
    OutputRole,
    PortCardinality,
    PortType,
    RecipeNode,
    ScoringMode,
    TemporalSemantics,
)
from pilot_assessment.evidence.operators import (
    OperatorParameterValidationContext,
    OperatorParameterValidator,
)
from pilot_assessment.evidence.registry import OperatorRegistry, OperatorRegistryError
from pilot_assessment.evidence.scoring import scoring_operator_identity


class RecipeValidationDisposition(StrEnum):
    INCOMPLETE = "incomplete"
    EXECUTABLE = "executable"


class RecipeDiagnosticSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class RecipeDiagnostic:
    code: str
    severity: RecipeDiagnosticSeverity
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class RecipeValidationOutcome:
    disposition: RecipeValidationDisposition
    diagnostics: tuple[RecipeDiagnostic, ...]


def _pointer_token(value: object) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")


def _error(
    diagnostics: list[RecipeDiagnostic],
    code: str,
    location: str,
    message: str,
) -> None:
    diagnostics.append(
        RecipeDiagnostic(
            code=code,
            severity=RecipeDiagnosticSeverity.ERROR,
            location=location,
            message=message,
        )
    )


def _report_duplicates(
    diagnostics: list[RecipeDiagnostic],
    values: tuple[str, ...],
    *,
    code: str,
    location: str,
    label: str,
) -> None:
    for value, count in sorted(Counter(values).items()):
        if count > 1:
            _error(
                diagnostics,
                code,
                f"{location}/{_pointer_token(value)}",
                f"{label} {value!r} occurs {count} times",
            )


def _validate_parameters(
    diagnostics: list[RecipeDiagnostic],
    definition: OperatorDefinition,
    parameters: Mapping[str, JsonValue],
    *,
    location: str,
    invalid_code: str,
) -> None:
    try:
        Draft202012Validator.check_schema(definition.parameter_schema)
    except SchemaError as error:
        _error(
            diagnostics,
            "recipe.operator_parameter_schema_invalid",
            location,
            f"trusted operator parameter schema is invalid: {error.message}",
        )
        return

    validator = Draft202012Validator(definition.parameter_schema)
    for error in sorted(
        validator.iter_errors(parameters),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    ):
        suffix = "".join(f"/{_pointer_token(part)}" for part in error.absolute_path)
        _error(
            diagnostics,
            invalid_code,
            f"{location}{suffix}",
            error.message,
        )


def _validate_operator_parameter_hook(
    diagnostics: list[RecipeDiagnostic],
    registry: OperatorRegistry,
    definition: OperatorDefinition,
    parameters: Mapping[str, JsonValue],
    *,
    input_slots: dict[str, tuple[str, ...]],
    location: str,
) -> None:
    try:
        implementation = registry.implementation(
            definition.operator_id,
            definition.implementation_version,
        )
    except OperatorRegistryError:
        return
    if not isinstance(implementation, OperatorParameterValidator):
        return
    try:
        issues = implementation.validate_parameters(
            parameters,
            OperatorParameterValidationContext(input_slots=input_slots),
        )
    except Exception as error:
        _error(
            diagnostics,
            "recipe.operator_parameter_validator_failed",
            location,
            f"trusted technical parameter validator failed: {error}",
        )
        return
    for issue in issues:
        suffix = issue.parameter_path if issue.parameter_path.startswith("/") else ""
        _error(
            diagnostics,
            "recipe.operator_parameters_invalid",
            f"{location}{suffix}",
            issue.message,
        )


def _port_map(
    definition: OperatorDefinition,
    *,
    output: bool,
) -> dict[str, PortType]:
    ports = definition.output_ports if output else definition.input_ports
    return {port.port_id: port.port_type for port in ports}


def _validate_port_compatibility(
    diagnostics: list[RecipeDiagnostic],
    source: PortType,
    target: PortType,
    *,
    location: str,
) -> None:
    if (
        source.value_type != target.value_type
        and source.value_type != "any"
        and target.value_type != "any"
    ):
        _error(
            diagnostics,
            "recipe.port_type_mismatch",
            location,
            f"value types are incompatible: {source.value_type} -> {target.value_type}",
        )
    if source.unit is not None and target.unit is not None and source.unit != target.unit:
        _error(
            diagnostics,
            "recipe.port_unit_mismatch",
            location,
            f"units are incompatible: {source.unit} -> {target.unit}",
        )
    if (
        source.temporal_semantics is not target.temporal_semantics
        and source.temporal_semantics is not TemporalSemantics.MIXED
        and target.temporal_semantics is not TemporalSemantics.MIXED
    ):
        _error(
            diagnostics,
            "recipe.port_temporal_mismatch",
            location,
            "temporal semantics are incompatible: "
            f"{source.temporal_semantics.value} -> {target.temporal_semantics.value}",
        )


def _first_nodes(nodes: tuple[RecipeNode, ...]) -> dict[str, RecipeNode]:
    result: dict[str, RecipeNode] = {}
    for node in nodes:
        result.setdefault(node.node_id, node)
    return result


def _has_cycle(
    node_ids: set[str],
    edges: list[tuple[str, str]],
) -> bool:
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    indegree = dict.fromkeys(node_ids, 0)
    for source_id, target_id in edges:
        adjacency[source_id].append(target_id)
        indegree[target_id] += 1
    for targets in adjacency.values():
        targets.sort()

    queue = [node_id for node_id, degree in indegree.items() if degree == 0]
    heapq.heapify(queue)
    visited = 0
    while queue:
        source_id = heapq.heappop(queue)
        visited += 1
        for target_id in adjacency[source_id]:
            indegree[target_id] -= 1
            if indegree[target_id] == 0:
                heapq.heappush(queue, target_id)
    return visited != len(node_ids)


def _validate_output_reference(
    diagnostics: list[RecipeDiagnostic],
    reference: NodePortReference,
    nodes: dict[str, RecipeNode],
    definitions: dict[str, OperatorDefinition],
    *,
    location: str,
    node_code: str,
    port_code: str,
) -> None:
    if reference.node_id not in nodes:
        _error(
            diagnostics,
            node_code,
            f"{location}/node_id",
            f"node {reference.node_id!r} does not exist",
        )
        return
    definition = definitions.get(reference.node_id)
    if definition is None:
        return
    if reference.port_id not in _port_map(definition, output=True):
        _error(
            diagnostics,
            port_code,
            f"{location}/port_id",
            f"output port {reference.port_id!r} is not declared",
        )


def validate_recipe(
    recipe: EvidenceRecipe,
    registry: OperatorRegistry,
) -> RecipeValidationOutcome:
    """Return executable only when the draft is technically runnable."""

    diagnostics: list[RecipeDiagnostic] = []
    _report_duplicates(
        diagnostics,
        tuple(item.binding_id for item in recipe.inputs),
        code="recipe.input_binding_id_duplicate",
        location="/inputs",
        label="input binding ID",
    )
    _report_duplicates(
        diagnostics,
        tuple(item.node_id for item in recipe.graph.nodes),
        code="recipe.node_id_duplicate",
        location="/graph/nodes",
        label="node ID",
    )
    _report_duplicates(
        diagnostics,
        tuple(item.edge_id for item in recipe.graph.edges),
        code="recipe.edge_id_duplicate",
        location="/graph/edges",
        label="edge ID",
    )
    _report_duplicates(
        diagnostics,
        tuple(item.output_id for item in recipe.outputs),
        code="recipe.output_id_duplicate",
        location="/outputs",
        label="output ID",
    )

    binding_ids = {item.binding_id for item in recipe.inputs}
    nodes = _first_nodes(recipe.graph.nodes)
    definitions: dict[str, OperatorDefinition] = {}
    for node_id, node in nodes.items():
        node_location = f"/graph/nodes/{_pointer_token(node_id)}"
        if node.input_binding_id is not None and node.input_binding_id not in binding_ids:
            _error(
                diagnostics,
                "recipe.input_binding_missing",
                f"{node_location}/input_binding_id",
                f"input binding {node.input_binding_id!r} does not exist",
            )
        try:
            definition = registry.definition(node.operator_id, node.operator_version)
        except OperatorRegistryError:
            _error(
                diagnostics,
                "recipe.operator_unknown",
                f"{node_location}/operator_id",
                f"operator {node.operator_id}@{node.operator_version} is not registered",
            )
            continue
        definitions[node_id] = definition
        _validate_parameters(
            diagnostics,
            definition,
            node.parameters,
            location=f"{node_location}/parameters",
            invalid_code="recipe.parameters_invalid",
        )

    incoming: dict[tuple[str, str], list[tuple[str, str | None]]] = defaultdict(list)
    graph_edges: list[tuple[str, str]] = []
    for edge in recipe.graph.edges:
        edge_location = f"/graph/edges/{_pointer_token(edge.edge_id)}"
        source_node = nodes.get(edge.source.node_id)
        target_node = nodes.get(edge.target.node_id)
        if source_node is None:
            _error(
                diagnostics,
                "recipe.edge.source_node_missing",
                f"{edge_location}/source/node_id",
                f"source node {edge.source.node_id!r} does not exist",
            )
        if target_node is None:
            _error(
                diagnostics,
                "recipe.edge.target_node_missing",
                f"{edge_location}/target/node_id",
                f"target node {edge.target.node_id!r} does not exist",
            )
        if source_node is None or target_node is None:
            continue

        graph_edges.append((source_node.node_id, target_node.node_id))
        source_definition = definitions.get(source_node.node_id)
        target_definition = definitions.get(target_node.node_id)
        if source_definition is None or target_definition is None:
            continue
        source_ports = _port_map(source_definition, output=True)
        target_ports = _port_map(target_definition, output=False)
        source_type = source_ports.get(edge.source.port_id)
        target_type = target_ports.get(edge.target.port_id)
        if source_type is None:
            _error(
                diagnostics,
                "recipe.edge.source_port_missing",
                f"{edge_location}/source/port_id",
                f"source output port {edge.source.port_id!r} is not declared",
            )
        if target_type is None:
            _error(
                diagnostics,
                "recipe.edge.target_port_missing",
                f"{edge_location}/target/port_id",
                f"target input port {edge.target.port_id!r} is not declared",
            )
        if source_type is None or target_type is None:
            continue
        incoming[(target_node.node_id, edge.target.port_id)].append(
            (edge.edge_id, edge.target_slot_id)
        )
        if target_type.cardinality is PortCardinality.MANY and edge.target_slot_id is None:
            _error(
                diagnostics,
                "recipe.many_input_slot_missing",
                f"{edge_location}/target_slot_id",
                "an edge into a many input requires a stable target slot ID",
            )
        if target_type.cardinality is not PortCardinality.MANY and edge.target_slot_id is not None:
            _error(
                diagnostics,
                "recipe.single_input_slot_unexpected",
                f"{edge_location}/target_slot_id",
                "target slot IDs are only valid for many input ports",
            )
        _validate_port_compatibility(
            diagnostics,
            source_type,
            target_type,
            location=edge_location,
        )

    for node_id, definition in definitions.items():
        for port in definition.input_ports:
            incoming_edges = incoming.get((node_id, port.port_id), [])
            port_location = (
                f"/graph/nodes/{_pointer_token(node_id)}/inputs/{_pointer_token(port.port_id)}"
            )
            if port.port_type.cardinality is PortCardinality.ONE and not incoming_edges:
                _error(
                    diagnostics,
                    "recipe.required_input_missing",
                    port_location,
                    "required input has no incoming edge",
                )
            if (
                port.port_type.cardinality in {PortCardinality.ONE, PortCardinality.OPTIONAL}
                and len(incoming_edges) > 1
            ):
                _error(
                    diagnostics,
                    "recipe.input_cardinality_exceeded",
                    port_location,
                    f"input accepts at most one edge but received {len(incoming_edges)}",
                )
            if port.port_type.cardinality is PortCardinality.MANY:
                slots = tuple(slot_id for _, slot_id in incoming_edges if slot_id is not None)
                duplicate_slots = sorted(
                    slot_id for slot_id, count in Counter(slots).items() if count > 1
                )
                for slot_id in duplicate_slots:
                    _error(
                        diagnostics,
                        "recipe.many_input_slot_duplicate",
                        f"{port_location}/{_pointer_token(slot_id)}",
                        f"many input slot {slot_id!r} is connected more than once",
                    )

    for node_id, definition in definitions.items():
        input_slots = {
            port.port_id: tuple(
                sorted(
                    slot_id
                    for _, slot_id in incoming.get((node_id, port.port_id), [])
                    if slot_id is not None
                )
            )
            for port in definition.input_ports
        }
        _validate_operator_parameter_hook(
            diagnostics,
            registry,
            definition,
            nodes[node_id].parameters,
            input_slots=input_slots,
            location=f"/graph/nodes/{_pointer_token(node_id)}/parameters",
        )

    if nodes and _has_cycle(set(nodes), graph_edges):
        _error(
            diagnostics,
            "recipe.graph_cycle",
            "/graph/edges",
            "computation graph contains a cycle",
        )

    primary_outputs = tuple(
        output for output in recipe.outputs if output.role is OutputRole.PRIMARY_VALUE
    )
    if not primary_outputs:
        _error(
            diagnostics,
            "recipe.primary_output_missing",
            "/outputs",
            "exactly one primary_value output is required",
        )
    elif len(primary_outputs) > 1:
        _error(
            diagnostics,
            "recipe.primary_output_multiple",
            "/outputs",
            "only one primary_value output is allowed",
        )
    for output in recipe.outputs:
        _validate_output_reference(
            diagnostics,
            output.source,
            nodes,
            definitions,
            location=f"/outputs/{_pointer_token(output.output_id)}/source",
            node_code="recipe.output_node_missing",
            port_code="recipe.output_port_missing",
        )

    scoring = recipe.scoring
    if scoring is None:
        _error(
            diagnostics,
            "recipe.scoring_missing",
            "/scoring",
            "scoring must be configured before apply",
        )
    else:
        if scoring.input is None:
            _error(
                diagnostics,
                "recipe.scoring_input_missing",
                "/scoring/input",
                "scoring input is required",
            )
        else:
            _validate_output_reference(
                diagnostics,
                scoring.input,
                nodes,
                definitions,
                location="/scoring/input",
                node_code="recipe.scoring_input_node_missing",
                port_code="recipe.scoring_input_port_missing",
            )
        custom_identity = (
            scoring.custom_operator_id,
            scoring.custom_operator_version,
        )
        if scoring.mode is ScoringMode.CUSTOM_OPERATOR and any(
            value is None for value in custom_identity
        ):
            _error(
                diagnostics,
                "recipe.custom_scorer_identity_missing",
                "/scoring",
                "custom scoring requires operator ID and version",
            )
        if scoring.mode is not ScoringMode.CUSTOM_OPERATOR and any(
            value is not None for value in custom_identity
        ):
            _error(
                diagnostics,
                "recipe.custom_scorer_identity_unexpected",
                "/scoring",
                "built-in scoring mode cannot carry a custom operator identity",
            )
        scorer_identity = scoring_operator_identity(scoring)
        if scorer_identity is not None:
            operator_id, operator_version = scorer_identity
            try:
                scorer_definition = registry.definition(operator_id, operator_version)
            except OperatorRegistryError:
                _error(
                    diagnostics,
                    "recipe.scorer_unknown",
                    "/scoring",
                    f"scorer {operator_id}@{operator_version} is not registered",
                )
            else:
                if scorer_definition.family is not OperatorFamily.SCORING:
                    _error(
                        diagnostics,
                        "recipe.scorer_family_mismatch",
                        "/scoring",
                        "scorer must reference a scoring-family operator",
                    )
                _validate_parameters(
                    diagnostics,
                    scorer_definition,
                    scoring.parameters,
                    location="/scoring/parameters",
                    invalid_code="recipe.scoring_parameters_invalid",
                )
                _validate_operator_parameter_hook(
                    diagnostics,
                    registry,
                    scorer_definition,
                    scoring.parameters,
                    input_slots={},
                    location="/scoring/parameters",
                )
                scorer_inputs = _port_map(scorer_definition, output=False)
                scorer_input_type = scorer_inputs.get("value")
                if scorer_input_type is None:
                    _error(
                        diagnostics,
                        "recipe.scorer_value_port_missing",
                        "/scoring",
                        "scoring operator must declare an input port named 'value'",
                    )
                elif scoring.input is not None:
                    source_definition = definitions.get(scoring.input.node_id)
                    if source_definition is not None:
                        source_type = _port_map(
                            source_definition,
                            output=True,
                        ).get(scoring.input.port_id)
                        if source_type is not None:
                            _validate_port_compatibility(
                                diagnostics,
                                source_type,
                                scorer_input_type,
                                location="/scoring/input",
                            )

    ordered = tuple(
        sorted(
            diagnostics,
            key=lambda item: (item.location, item.code, item.message),
        )
    )
    disposition = (
        RecipeValidationDisposition.EXECUTABLE
        if not ordered
        else RecipeValidationDisposition.INCOMPLETE
    )
    return RecipeValidationOutcome(
        disposition=disposition,
        diagnostics=ordered,
    )


__all__ = [
    "RecipeDiagnostic",
    "RecipeDiagnosticSeverity",
    "RecipeValidationDisposition",
    "RecipeValidationOutcome",
    "validate_recipe",
]
