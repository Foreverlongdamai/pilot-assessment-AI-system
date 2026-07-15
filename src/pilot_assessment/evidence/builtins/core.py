"""Core built-in operators for external bindings, constants and safe formulas."""

from __future__ import annotations

import ast
import math
import operator
from collections.abc import Mapping
from numbers import Real

from pydantic import JsonValue

from pilot_assessment.contracts.evidence_recipe import (
    OperatorDefinition,
    OperatorFamily,
    OperatorImplementationSource,
    OperatorPortDefinition,
    ParameterControlKind,
    ParameterUiDefinition,
    PortCardinality,
    PortType,
    TemporalSemantics,
    TraceCapability,
)
from pilot_assessment.evidence.operators import (
    OperatorExecutionContext,
    OperatorParameterDiagnostic,
    OperatorParameterValidationContext,
)
from pilot_assessment.evidence.registry import OperatorRegistry

_VERSION = "0.1.0"
_MAX_FORMULA_NODES = 256


class SafeFormulaError(ValueError):
    """Raised when a formula exceeds the deliberately small expression language."""


def _port(
    port_id: str,
    *,
    value_type: str,
    cardinality: PortCardinality,
    temporal: TemporalSemantics,
) -> OperatorPortDefinition:
    return OperatorPortDefinition(
        port_id=port_id,
        name=port_id.replace("_", " ").title(),
        description=f"Built-in {port_id} port.",
        port_type=PortType(
            value_type=value_type,
            cardinality=cardinality,
            temporal_semantics=temporal,
            unit=None,
        ),
    )


def input_binding_definition() -> OperatorDefinition:
    return OperatorDefinition(
        operator_id="input.binding",
        implementation_version=_VERSION,
        family=OperatorFamily.INPUT,
        name="Recipe input binding",
        description="Returns the execution value of the binding selected by the node.",
        pseudocode="value = execution_bindings[node.input_binding_id]",
        input_ports=(),
        output_ports=(
            _port(
                "value",
                value_type="any",
                cardinality=PortCardinality.ONE,
                temporal=TemporalSemantics.MIXED,
            ),
        ),
        parameter_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        parameter_ui=(),
        trace_capability=TraceCapability.SUMMARY,
        implementation_source=OperatorImplementationSource.BUILT_IN,
        implementation_ref="builtin.input.binding",
    )


def constant_number_definition() -> OperatorDefinition:
    return OperatorDefinition(
        operator_id="constant.number",
        implementation_version=_VERSION,
        family=OperatorFamily.INPUT,
        name="Number constant",
        description="Returns one finite expert-editable number.",
        pseudocode="value = parameters.value",
        input_ports=(),
        output_ports=(
            _port(
                "value",
                value_type="number",
                cardinality=PortCardinality.ONE,
                temporal=TemporalSemantics.TIMELESS,
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
                help_text="Finite number returned by this node.",
                unit=None,
            ),
        ),
        trace_capability=TraceCapability.SUMMARY,
        implementation_source=OperatorImplementationSource.BUILT_IN,
        implementation_ref="builtin.constant.number",
    )


def safe_formula_definition() -> OperatorDefinition:
    return OperatorDefinition(
        operator_id="composition.safe-formula",
        implementation_version=_VERSION,
        family=OperatorFamily.COMPOSITION,
        name="Safe formula",
        description=(
            "Evaluates a bounded expression over named incoming slots and constants; "
            "it never executes Python source."
        ),
        pseudocode="value = safe_expression(named_inputs | constants)",
        input_ports=(
            _port(
                "variables",
                value_type="any",
                cardinality=PortCardinality.MANY,
                temporal=TemporalSemantics.MIXED,
            ),
        ),
        output_ports=(
            _port(
                "value",
                value_type="any",
                cardinality=PortCardinality.ONE,
                temporal=TemporalSemantics.MIXED,
            ),
        ),
        parameter_schema={
            "type": "object",
            "properties": {
                "formula": {"type": "string", "minLength": 1, "maxLength": 2000},
                "constants": {
                    "type": "object",
                    "additionalProperties": {"type": ["number", "boolean"]},
                },
            },
            "required": ["formula", "constants"],
            "additionalProperties": False,
        },
        parameter_ui=(
            ParameterUiDefinition(
                parameter_path="/formula",
                label="Formula",
                group_id="formula",
                control=ParameterControlKind.FORMULA,
                help_text=("Supports arithmetic, comparisons, and/or/not, min, max, abs and clip."),
                unit=None,
            ),
        ),
        trace_capability=TraceCapability.FULL,
        implementation_source=OperatorImplementationSource.BUILT_IN,
        implementation_ref="builtin.composition.safe-formula",
    )


class InputBindingOperator:
    operator_id = "input.binding"
    implementation_version = _VERSION
    implementation_ref = "builtin.input.binding"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del inputs, parameters
        if context.input_binding_id is None:
            raise ValueError("input.binding requires node.input_binding_id")
        return {"value": context.binding_values[context.input_binding_id]}


class ConstantNumberOperator:
    operator_id = "constant.number"
    implementation_version = _VERSION
    implementation_ref = "builtin.constant.number"

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del inputs, context
        value = parameters["value"]
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError("constant number must be numeric")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError("constant number must be finite")
        return {"value": numeric}


def _formula_name(value: object, *, label: str) -> str:
    if type(value) is not str or not value.isidentifier():
        raise SafeFormulaError(f"{label} names must be Python-style identifiers")
    return value


def _finite_scalar(value: object) -> object:
    if isinstance(value, bool):
        return value
    if isinstance(value, Real):
        numeric = float(value)
        if not math.isfinite(numeric):
            raise SafeFormulaError("formula produced a non-finite number")
        return numeric
    raise SafeFormulaError("formula values must be finite numbers or booleans")


def _numeric(value: object) -> float:
    normalized = _finite_scalar(value)
    if isinstance(normalized, bool):
        raise SafeFormulaError("boolean cannot be used as a numeric operand")
    assert isinstance(normalized, float)
    return normalized


_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
}
_ALLOWED_BINARY_OPERATOR_TYPES = (*_BINARY_OPERATORS, ast.Pow)
_ALLOWED_COMPARISON_OPERATOR_TYPES = (
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
)
_ALLOWED_FUNCTION_ARITY = {
    "abs": (1, 1),
    "min": (1, None),
    "max": (1, None),
    "clip": (3, 3),
}


def _call_function(name: str, arguments: list[object]) -> object:
    if name == "abs" and len(arguments) == 1:
        return abs(_numeric(arguments[0]))
    if name in {"min", "max"} and arguments:
        values = [_numeric(value) for value in arguments]
        return min(values) if name == "min" else max(values)
    if name == "clip" and len(arguments) == 3:
        value, lower, upper = (_numeric(argument) for argument in arguments)
        if lower > upper:
            raise SafeFormulaError("clip lower bound cannot exceed upper bound")
        return min(max(value, lower), upper)
    raise SafeFormulaError(f"function {name!r} is not allowed or has invalid arguments")


def _compare(operator_node: ast.cmpop, left: object, right: object) -> bool:
    if isinstance(operator_node, ast.Eq):
        return left == right
    if isinstance(operator_node, ast.NotEq):
        return left != right
    left_number = _numeric(left)
    right_number = _numeric(right)
    if isinstance(operator_node, ast.Lt):
        return left_number < right_number
    if isinstance(operator_node, ast.LtE):
        return left_number <= right_number
    if isinstance(operator_node, ast.Gt):
        return left_number > right_number
    if isinstance(operator_node, ast.GtE):
        return left_number >= right_number
    raise SafeFormulaError(f"comparison {type(operator_node).__name__} is not allowed")


def _validate_formula_node(node: ast.AST, names: frozenset[str]) -> None:
    if isinstance(node, ast.Expression):
        _validate_formula_node(node.body, names)
        return
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (bool, int, float)):
            raise SafeFormulaError("only numeric and boolean constants are allowed")
        _finite_scalar(node.value)
        return
    if isinstance(node, ast.Name):
        if node.id not in names:
            raise SafeFormulaError(f"unknown name {node.id!r}")
        return
    if isinstance(node, ast.BinOp):
        if not isinstance(node.op, _ALLOWED_BINARY_OPERATOR_TYPES):
            raise SafeFormulaError(f"binary operator {type(node.op).__name__} is not allowed")
        _validate_formula_node(node.left, names)
        _validate_formula_node(node.right, names)
        return
    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, (ast.Not, ast.UAdd, ast.USub)):
            raise SafeFormulaError(f"unary operator {type(node.op).__name__} is not allowed")
        _validate_formula_node(node.operand, names)
        return
    if isinstance(node, ast.BoolOp):
        if not isinstance(node.op, (ast.And, ast.Or)):
            raise SafeFormulaError(f"boolean operator {type(node.op).__name__} is not allowed")
        for value in node.values:
            _validate_formula_node(value, names)
        return
    if isinstance(node, ast.Compare):
        if any(
            not isinstance(operator_node, _ALLOWED_COMPARISON_OPERATOR_TYPES)
            for operator_node in node.ops
        ):
            raise SafeFormulaError("formula contains an unsupported comparison")
        _validate_formula_node(node.left, names)
        for comparator in node.comparators:
            _validate_formula_node(comparator, names)
        return
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.keywords:
            raise SafeFormulaError("only direct calls to allowed named functions are valid")
        arity = _ALLOWED_FUNCTION_ARITY.get(node.func.id)
        if arity is None:
            raise SafeFormulaError(f"function {node.func.id!r} is not allowed")
        minimum, maximum = arity
        if len(node.args) < minimum or (maximum is not None and len(node.args) > maximum):
            raise SafeFormulaError(f"function {node.func.id!r} has invalid arguments")
        for argument in node.args:
            _validate_formula_node(argument, names)
        return
    raise SafeFormulaError(f"syntax {type(node).__name__} is not allowed")


def _parse_formula(formula: str, names: frozenset[str]) -> ast.Expression:
    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError as error:
        raise SafeFormulaError(f"formula syntax is invalid: {error.msg}") from error
    if sum(1 for _ in ast.walk(tree)) > _MAX_FORMULA_NODES:
        raise SafeFormulaError("formula exceeds the 256-node complexity limit")
    _validate_formula_node(tree, names)
    return tree


def _evaluate(node: ast.AST, environment: Mapping[str, object]) -> object:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body, environment)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (bool, int, float)):
            return _finite_scalar(node.value)
        raise SafeFormulaError("only numeric and boolean constants are allowed")
    if isinstance(node, ast.Name):
        try:
            return environment[node.id]
        except KeyError as error:
            raise SafeFormulaError(f"unknown name {node.id!r}") from error
    if isinstance(node, ast.BinOp):
        left = _numeric(_evaluate(node.left, environment))
        right = _numeric(_evaluate(node.right, environment))
        if isinstance(node.op, ast.Pow):
            if abs(right) > 16:
                raise SafeFormulaError("formula exponent magnitude cannot exceed 16")
            return _finite_scalar(left**right)
        function = _BINARY_OPERATORS.get(type(node.op))
        if function is None:
            raise SafeFormulaError(f"binary operator {type(node.op).__name__} is not allowed")
        return _finite_scalar(function(left, right))
    if isinstance(node, ast.UnaryOp):
        operand = _evaluate(node.operand, environment)
        if isinstance(node.op, ast.Not):
            if not isinstance(operand, bool):
                raise SafeFormulaError("not requires a boolean operand")
            return not operand
        if isinstance(node.op, ast.UAdd):
            return _numeric(operand)
        if isinstance(node.op, ast.USub):
            return -_numeric(operand)
        raise SafeFormulaError(f"unary operator {type(node.op).__name__} is not allowed")
    if isinstance(node, ast.BoolOp):
        values = [_evaluate(value, environment) for value in node.values]
        if any(not isinstance(value, bool) for value in values):
            raise SafeFormulaError("and/or require boolean operands")
        return all(values) if isinstance(node.op, ast.And) else any(values)
    if isinstance(node, ast.Compare):
        left = _evaluate(node.left, environment)
        for operator_node, comparator in zip(node.ops, node.comparators, strict=True):
            right = _evaluate(comparator, environment)
            if not _compare(operator_node, left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.keywords:
            raise SafeFormulaError("only direct calls to allowed named functions are valid")
        return _call_function(
            node.func.id,
            [_evaluate(argument, environment) for argument in node.args],
        )
    raise SafeFormulaError(f"syntax {type(node).__name__} is not allowed")


class SafeFormulaOperator:
    operator_id = "composition.safe-formula"
    implementation_version = _VERSION
    implementation_ref = "builtin.composition.safe-formula"

    def validate_parameters(
        self,
        parameters: Mapping[str, JsonValue],
        context: OperatorParameterValidationContext,
    ) -> tuple[OperatorParameterDiagnostic, ...]:
        formula = parameters.get("formula")
        constants = parameters.get("constants")
        if type(formula) is not str or not isinstance(constants, Mapping):
            return ()
        try:
            names: set[str] = set()
            for slot_id in context.input_slots.get("variables", ()):
                name = _formula_name(slot_id, label="variable")
                if name in names:
                    raise SafeFormulaError(f"name {name!r} is defined twice")
                names.add(name)
            for raw_name in constants:
                name = _formula_name(raw_name, label="constant")
                if name in names:
                    raise SafeFormulaError(f"name {name!r} is defined twice")
                names.add(name)
            _parse_formula(formula, frozenset(names))
        except SafeFormulaError as error:
            return (
                OperatorParameterDiagnostic(
                    parameter_path="/formula",
                    message=str(error),
                ),
            )
        return ()

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        variables = inputs.get("variables", {})
        constants = parameters.get("constants", {})
        formula = parameters.get("formula")
        if not isinstance(variables, Mapping) or not isinstance(constants, Mapping):
            raise SafeFormulaError("variables and constants must be mappings")
        if type(formula) is not str:
            raise SafeFormulaError("formula must be a string")

        environment: dict[str, object] = {}
        for source, label in ((variables, "variable"), (constants, "constant")):
            for raw_name, raw_value in source.items():
                name = _formula_name(raw_name, label=label)
                if name in environment:
                    raise SafeFormulaError(f"name {name!r} is defined twice")
                environment[name] = _finite_scalar(raw_value)
        tree = _parse_formula(formula, frozenset(environment))
        try:
            value = _evaluate(tree, environment)
        except SafeFormulaError:
            raise
        except (ArithmeticError, OverflowError, ValueError) as error:
            raise SafeFormulaError(f"formula evaluation failed: {error}") from error
        return {"value": _finite_scalar(value)}


def register_core_operators(registry: OperatorRegistry) -> None:
    """Register the minimal reusable operator vertical slice."""

    registry.register(input_binding_definition(), InputBindingOperator())
    registry.register(constant_number_definition(), ConstantNumberOperator())
    registry.register(safe_formula_definition(), SafeFormulaOperator())


__all__ = [
    "ConstantNumberOperator",
    "InputBindingOperator",
    "SafeFormulaError",
    "SafeFormulaOperator",
    "constant_number_definition",
    "input_binding_definition",
    "register_core_operators",
    "safe_formula_definition",
]
