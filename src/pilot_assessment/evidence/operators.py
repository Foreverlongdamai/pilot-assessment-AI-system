"""Runtime protocol shared by built-in and trusted evidence operators."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

from pydantic import JsonValue


@dataclass(frozen=True, slots=True)
class OperatorExecutionContext:
    """Read-only execution metadata and external values for one recipe node."""

    recipe_id: str
    recipe_version: int
    node_id: str
    binding_values: Mapping[str, object]
    trace_requested: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "binding_values",
            MappingProxyType(dict(self.binding_values)),
        )


class OperatorImplementation(Protocol):
    """Trusted executable paired one-to-one with an OperatorDefinition."""

    operator_id: str
    implementation_version: str
    implementation_ref: str

    def execute(
        self,
        inputs: Mapping[str, object],
        parameters: Mapping[str, JsonValue],
        context: OperatorExecutionContext,
    ) -> Mapping[str, object]:
        """Return values keyed by declared output port ID."""


__all__ = ["OperatorExecutionContext", "OperatorImplementation"]
