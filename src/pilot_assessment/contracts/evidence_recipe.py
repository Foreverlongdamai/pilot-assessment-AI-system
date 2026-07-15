"""Canonical contracts for expert-editable evidence computation recipes."""

from __future__ import annotations

import math
import re
from enum import StrEnum
from typing import Annotated, Literal, Self, cast

from pydantic import (
    AfterValidator,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)

from pilot_assessment.contracts.common import (
    StableId,
    StrictContractModel,
    freeze_json_mapping,
)

_JSON_POINTER_PATTERN = re.compile(r"^/(?:[^/~]|~[01])+(?:/(?:[^/~]|~[01])+)*$")

HumanLabel = Annotated[str, StringConstraints(min_length=1, max_length=256)]
HumanText = Annotated[str, StringConstraints(max_length=8000)]
UnitId = Annotated[str, StringConstraints(min_length=1, max_length=64)]
PositiveRecipeVersion = Annotated[int, Field(strict=True, ge=1)]


def _validate_json_pointer(value: str) -> str:
    if _JSON_POINTER_PATTERN.fullmatch(value) is None:
        raise ValueError("must be a non-empty canonical JSON pointer")
    return value


JsonPointer = Annotated[
    str,
    StringConstraints(min_length=2, max_length=1024),
    AfterValidator(_validate_json_pointer),
]


def _require_finite_json(value: JsonValue) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("JSON numbers must be finite")
    if isinstance(value, dict):
        for key, nested in value.items():
            if type(key) is not str:
                raise ValueError("JSON object keys must be strings")
            _require_finite_json(nested)
    elif isinstance(value, list):
        for nested in value:
            _require_finite_json(nested)


def _freeze_json_object(value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    _require_finite_json(value)
    return freeze_json_mapping(value)


def _require_unique(values: tuple[str, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


class RecipeLifecycle(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    RETIRED = "retired"


class RecipeScientificStatus(StrEnum):
    STARTER_TEMPLATE = "starter_template"
    EXPERT_DEFINED = "expert_defined"
    CALIBRATED = "calibrated"


class InputBindingKind(StrEnum):
    STREAM = "stream"
    SEMANTIC = "semantic"
    REFERENCE = "reference"


class OperatorFamily(StrEnum):
    INPUT = "input"
    TEMPORAL = "temporal"
    SIGNAL = "signal"
    EVENT = "event"
    GAZE_VISION = "gaze_vision"
    FLIGHT_GEOMETRY = "flight_geometry"
    STATISTICS = "statistics"
    COMPOSITION = "composition"
    AGGREGATION = "aggregation"
    SCORING = "scoring"


class PortCardinality(StrEnum):
    ONE = "one"
    OPTIONAL = "optional"
    MANY = "many"


class TemporalSemantics(StrEnum):
    TIMELESS = "timeless"
    SAMPLED = "sampled"
    POINT = "point"
    INTERVAL = "interval"
    MIXED = "mixed"


class TraceCapability(StrEnum):
    NONE = "none"
    SUMMARY = "summary"
    FULL = "full"


class OperatorImplementationSource(StrEnum):
    BUILT_IN = "built_in"
    TRUSTED_EXTENSION = "trusted_extension"


class ParameterControlKind(StrEnum):
    NUMBER = "number"
    SLIDER = "slider"
    TEXT = "text"
    SELECT = "select"
    MULTI_SELECT = "multi_select"
    CHECKBOX = "checkbox"
    FORMULA = "formula"


class OutputRole(StrEnum):
    PRIMARY_VALUE = "primary_value"
    RAW_METRIC = "raw_metric"
    BREAKDOWN = "breakdown"
    TRACE = "trace"


class ScoringMode(StrEnum):
    ORDERED_DAU = "ordered_dau"
    SOFT_LIKELIHOOD = "soft_likelihood"
    CUSTOM_OPERATOR = "custom_operator"


class PortType(StrictContractModel):
    """Type information shared by operator ports and external recipe bindings."""

    value_type: StableId
    cardinality: PortCardinality
    temporal_semantics: TemporalSemantics
    unit: UnitId | None


class OperatorPortDefinition(StrictContractModel):
    port_id: StableId
    name: HumanLabel
    description: HumanText
    port_type: PortType


class ParameterUiDefinition(StrictContractModel):
    parameter_path: JsonPointer
    label: HumanLabel
    group_id: StableId
    control: ParameterControlKind
    help_text: HumanText
    unit: UnitId | None


class OperatorDefinition(StrictContractModel):
    """Portable operator metadata paired with one trusted implementation."""

    contract_id: Literal["operator-definition"] = "operator-definition"
    contract_version: Literal["0.1.0"] = "0.1.0"
    operator_id: StableId
    implementation_version: StableId
    family: OperatorFamily
    name: HumanLabel
    description: HumanText
    pseudocode: HumanText | None
    input_ports: tuple[OperatorPortDefinition, ...]
    output_ports: tuple[OperatorPortDefinition, ...]
    parameter_schema: dict[str, JsonValue]
    parameter_ui: tuple[ParameterUiDefinition, ...]
    trace_capability: TraceCapability
    implementation_source: OperatorImplementationSource
    implementation_ref: StableId

    @field_validator("parameter_schema")
    @classmethod
    def freeze_parameter_schema(
        cls, value: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        return _freeze_json_object(value)

    @model_validator(mode="after")
    def validate_definition(self) -> Self:
        _require_unique(
            tuple(port.port_id for port in self.input_ports),
            "input port IDs",
        )
        _require_unique(
            tuple(port.port_id for port in self.output_ports),
            "output port IDs",
        )
        _require_unique(
            tuple(item.parameter_path for item in self.parameter_ui),
            "parameter UI paths",
        )
        if self.parameter_schema.get("type") != "object":
            raise ValueError("parameter_schema must describe an object")
        return self


class RecipeAnchor(StrictContractModel):
    anchor_id: StableId
    name: HumanLabel
    description: HumanText
    lifecycle: RecipeLifecycle
    scientific_status: RecipeScientificStatus


class RecipeInputBinding(StrictContractModel):
    binding_id: StableId
    kind: InputBindingKind
    source_id: StableId
    name: HumanLabel
    declared_type: PortType
    selector: dict[str, JsonValue]

    @field_validator("selector")
    @classmethod
    def freeze_selector(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return _freeze_json_object(value)


class NodePortReference(StrictContractModel):
    node_id: StableId
    port_id: StableId


class RecipeNode(StrictContractModel):
    node_id: StableId
    operator_id: StableId
    operator_version: StableId
    parameters: dict[str, JsonValue]

    @field_validator("parameters")
    @classmethod
    def freeze_parameters(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return _freeze_json_object(value)


class RecipeEdge(StrictContractModel):
    edge_id: StableId
    source: NodePortReference
    target: NodePortReference


class RecipeGraph(StrictContractModel):
    nodes: tuple[RecipeNode, ...]
    edges: tuple[RecipeEdge, ...]


class RecipeOutputBinding(StrictContractModel):
    output_id: StableId
    role: OutputRole
    name: HumanLabel
    source: NodePortReference
    unit: UnitId | None


class RecipeScoring(StrictContractModel):
    mode: ScoringMode
    input: NodePortReference | None
    parameters: dict[str, JsonValue]
    custom_operator_id: StableId | None
    custom_operator_version: StableId | None

    @field_validator("parameters")
    @classmethod
    def freeze_parameters(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return _freeze_json_object(value)


class RecipeDocumentation(StrictContractModel):
    summary: HumanText
    assumptions: tuple[HumanText, ...]
    parameter_notes: dict[str, str]
    references: tuple[HumanText, ...]

    @field_validator("parameter_notes")
    @classmethod
    def freeze_parameter_notes(cls, value: dict[str, str]) -> dict[str, str]:
        for path in value:
            _validate_json_pointer(path)
        frozen = _freeze_json_object(cast(dict[str, JsonValue], value))
        return cast(dict[str, str], frozen)


class RecipeUiGroup(StrictContractModel):
    group_id: StableId
    label: HumanLabel
    parameter_paths: tuple[JsonPointer, ...]


class RecipeUiMetadata(StrictContractModel):
    groups: tuple[RecipeUiGroup, ...]
    preferred_layout: dict[str, JsonValue]

    @field_validator("preferred_layout")
    @classmethod
    def freeze_preferred_layout(
        cls, value: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        return _freeze_json_object(value)


class EvidenceRecipe(StrictContractModel):
    """The sole editable source used for display, persistence and execution."""

    contract_id: Literal["evidence-recipe"] = "evidence-recipe"
    contract_version: Literal["0.1.0"] = "0.1.0"
    recipe_id: StableId
    recipe_version: PositiveRecipeVersion
    anchor: RecipeAnchor
    inputs: tuple[RecipeInputBinding, ...]
    graph: RecipeGraph
    outputs: tuple[RecipeOutputBinding, ...]
    scoring: RecipeScoring | None
    documentation: RecipeDocumentation
    ui: RecipeUiMetadata


__all__ = [
    "EvidenceRecipe",
    "InputBindingKind",
    "JsonPointer",
    "NodePortReference",
    "OperatorDefinition",
    "OperatorFamily",
    "OperatorImplementationSource",
    "OperatorPortDefinition",
    "OutputRole",
    "ParameterControlKind",
    "ParameterUiDefinition",
    "PortCardinality",
    "PortType",
    "RecipeAnchor",
    "RecipeDocumentation",
    "RecipeEdge",
    "RecipeGraph",
    "RecipeInputBinding",
    "RecipeLifecycle",
    "RecipeNode",
    "RecipeOutputBinding",
    "RecipeScientificStatus",
    "RecipeScoring",
    "RecipeUiGroup",
    "RecipeUiMetadata",
    "ScoringMode",
    "TemporalSemantics",
    "TraceCapability",
]
