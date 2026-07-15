"""Editable scoring operators that turn computed values into evidence states."""

from __future__ import annotations

import math
from collections.abc import Mapping
from numbers import Real

from pydantic import JsonValue

from pilot_assessment.contracts.anchor import EvidenceLikelihood, EvidenceState
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
from pilot_assessment.evidence.scoring import ORDERED_DAU_OPERATOR_IDENTITY

_OPERATOR_ID, _VERSION = ORDERED_DAU_OPERATOR_IDENTITY
_STATE_ORDER = ("unacceptable", "adequate", "desired")


class OrderedDauScoringError(ValueError):
    """Technical error in an editable ordered D/A/U scorer configuration."""


def _port(port_id: str, value_type: str) -> OperatorPortDefinition:
    return OperatorPortDefinition(
        port_id=port_id,
        name=port_id.replace("_", " ").title(),
        description=f"Ordered D/A/U {port_id} port.",
        port_type=PortType(
            value_type=value_type,
            cardinality=PortCardinality.ONE,
            temporal_semantics=TemporalSemantics.MIXED,
            unit=None,
        ),
    )


def ordered_dau_definition() -> OperatorDefinition:
    return OperatorDefinition(
        operator_id=_OPERATOR_ID,
        implementation_version=_VERSION,
        family=OperatorFamily.SCORING,
        name="Ordered Desired/Adequate/Unacceptable",
        description=(
            "Classifies one finite numeric value using editable ordered boundaries. "
            "The default values are engineering examples, not scientific standards."
        ),
        pseudocode="compare value with desired and adequate boundaries in selected direction",
        input_ports=(_port("value", "number"),),
        output_ports=(
            _port("state", "evidence_state"),
            _port("likelihood", "evidence_likelihood"),
            _port("score", "number"),
        ),
        parameter_schema={
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["higher_is_better", "lower_is_better"],
                },
                "desired_boundary": {"type": "number"},
                "adequate_boundary": {"type": "number"},
                "likelihood_strength": {
                    "type": "number",
                    "minimum": 0.3333333333333333,
                    "maximum": 1.0,
                },
            },
            "required": [
                "direction",
                "desired_boundary",
                "adequate_boundary",
                "likelihood_strength",
            ],
            "additionalProperties": False,
        },
        parameter_ui=(
            ParameterUiDefinition(
                parameter_path="/direction",
                label="Direction",
                group_id="boundaries",
                control=ParameterControlKind.SELECT,
                help_text="Choose whether larger or smaller values indicate better performance.",
                unit=None,
            ),
            ParameterUiDefinition(
                parameter_path="/desired_boundary",
                label="Desired boundary",
                group_id="boundaries",
                control=ParameterControlKind.NUMBER,
                help_text="Editable boundary between desired and adequate evidence.",
                unit=None,
            ),
            ParameterUiDefinition(
                parameter_path="/adequate_boundary",
                label="Adequate boundary",
                group_id="boundaries",
                control=ParameterControlKind.NUMBER,
                help_text="Editable boundary between adequate and unacceptable evidence.",
                unit=None,
            ),
            ParameterUiDefinition(
                parameter_path="/likelihood_strength",
                label="Likelihood strength",
                group_id="likelihood",
                control=ParameterControlKind.SLIDER,
                help_text="Probability assigned to the selected evidence state.",
                unit=None,
            ),
        ),
        trace_capability=TraceCapability.SUMMARY,
        implementation_source=OperatorImplementationSource.BUILT_IN,
        implementation_ref="builtin.scoring.ordered-dau",
    )


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise OrderedDauScoringError(f"{label} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise OrderedDauScoringError(f"{label} must be finite")
    return numeric


def _likelihood(state: EvidenceState, strength: float) -> EvidenceLikelihood:
    other = round((1.0 - strength) / 2.0, 15)
    selected = 1.0 - 2.0 * other
    values = [other, other, other]
    values[_STATE_ORDER.index(state.value)] = selected
    return EvidenceLikelihood(
        state_order=_STATE_ORDER,
        values=tuple(values),
    )


class OrderedDauScoringOperator:
    operator_id = _OPERATOR_ID
    implementation_version = _VERSION
    implementation_ref = "builtin.scoring.ordered-dau"

    def validate_parameters(
        self,
        parameters: Mapping[str, JsonValue],
        context: OperatorParameterValidationContext,
    ) -> tuple[OperatorParameterDiagnostic, ...]:
        del context
        try:
            desired = _finite_number(
                parameters.get("desired_boundary"),
                "desired boundary",
            )
            adequate = _finite_number(
                parameters.get("adequate_boundary"),
                "adequate boundary",
            )
        except OrderedDauScoringError:
            return ()
        direction = parameters.get("direction")
        invalid = (direction == "higher_is_better" and desired < adequate) or (
            direction == "lower_is_better" and desired > adequate
        )
        if not invalid:
            return ()
        return (
            OperatorParameterDiagnostic(
                parameter_path="/desired_boundary",
                message="desired and adequate boundaries are reversed for direction",
            ),
        )

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        del context
        value = _finite_number(inputs.get("value"), "scoring input")
        desired = _finite_number(
            parameters.get("desired_boundary"),
            "desired boundary",
        )
        adequate = _finite_number(
            parameters.get("adequate_boundary"),
            "adequate boundary",
        )
        strength = _finite_number(
            parameters.get("likelihood_strength"),
            "likelihood strength",
        )
        if not 1.0 / 3.0 <= strength <= 1.0:
            raise OrderedDauScoringError("likelihood strength must be between one third and one")
        direction = parameters.get("direction")
        if direction == "higher_is_better":
            if desired < adequate:
                raise OrderedDauScoringError(
                    "higher-is-better desired boundary cannot be below adequate boundary"
                )
            state = (
                EvidenceState.DESIRED
                if value >= desired
                else EvidenceState.ADEQUATE
                if value >= adequate
                else EvidenceState.UNACCEPTABLE
            )
        elif direction == "lower_is_better":
            if desired > adequate:
                raise OrderedDauScoringError(
                    "lower-is-better desired boundary cannot exceed adequate boundary"
                )
            state = (
                EvidenceState.DESIRED
                if value <= desired
                else EvidenceState.ADEQUATE
                if value <= adequate
                else EvidenceState.UNACCEPTABLE
            )
        else:
            raise OrderedDauScoringError("direction is not supported")
        score = {
            EvidenceState.UNACCEPTABLE: 0.0,
            EvidenceState.ADEQUATE: 0.5,
            EvidenceState.DESIRED: 1.0,
        }[state]
        return {
            "state": state,
            "likelihood": _likelihood(state, strength),
            "score": score,
        }


def register_scoring_operators(registry: OperatorRegistry) -> None:
    registry.register(ordered_dau_definition(), OrderedDauScoringOperator())


__all__ = [
    "OrderedDauScoringError",
    "OrderedDauScoringOperator",
    "ordered_dau_definition",
    "register_scoring_operators",
]
