"""Explicit trusted registry for reusable evidence operators."""

from __future__ import annotations

from dataclasses import dataclass

from pilot_assessment.contracts.evidence_recipe import OperatorDefinition
from pilot_assessment.evidence.operators import OperatorImplementation


class OperatorRegistryError(ValueError):
    """Raised when a trusted operator identity cannot be registered or resolved."""


@dataclass(frozen=True, order=True, slots=True)
class OperatorKey:
    operator_id: str
    implementation_version: str


@dataclass(frozen=True, slots=True)
class RegisteredOperator:
    definition: OperatorDefinition
    implementation: OperatorImplementation


class OperatorRegistry:
    """In-process registry with no dynamic import or Anchor-ID fallback."""

    def __init__(self) -> None:
        self._entries: dict[OperatorKey, RegisteredOperator] = {}

    def register(
        self,
        definition: OperatorDefinition,
        implementation: OperatorImplementation,
    ) -> None:
        key = OperatorKey(
            definition.operator_id,
            definition.implementation_version,
        )
        if key in self._entries:
            raise OperatorRegistryError(
                "operator "
                f"{definition.operator_id}@{definition.implementation_version} "
                "is already registered"
            )
        implementation_identity = (
            implementation.operator_id,
            implementation.implementation_version,
            implementation.implementation_ref,
        )
        definition_identity = (
            definition.operator_id,
            definition.implementation_version,
            definition.implementation_ref,
        )
        if implementation_identity != definition_identity:
            raise OperatorRegistryError(
                "operator implementation identity does not match definition: "
                f"expected {definition_identity!r}, got {implementation_identity!r}"
            )
        self._entries[key] = RegisteredOperator(definition, implementation)

    def definition(
        self,
        operator_id: str,
        implementation_version: str,
    ) -> OperatorDefinition:
        return self._resolve(operator_id, implementation_version).definition

    def implementation(
        self,
        operator_id: str,
        implementation_version: str,
    ) -> OperatorImplementation:
        return self._resolve(operator_id, implementation_version).implementation

    def catalog(self) -> tuple[OperatorDefinition, ...]:
        return tuple(
            self._entries[key].definition
            for key in sorted(self._entries)
        )

    def _resolve(
        self,
        operator_id: str,
        implementation_version: str,
    ) -> RegisteredOperator:
        key = OperatorKey(operator_id, implementation_version)
        try:
            return self._entries[key]
        except KeyError as error:
            raise OperatorRegistryError(
                f"operator {operator_id}@{implementation_version} is not registered"
            ) from error


__all__ = [
    "OperatorKey",
    "OperatorRegistry",
    "OperatorRegistryError",
    "RegisteredOperator",
]
