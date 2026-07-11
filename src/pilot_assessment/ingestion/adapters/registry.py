"""Exact, in-process registry for trusted ingestion adapter instances."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from pydantic import TypeAdapter, ValidationError

from pilot_assessment.contracts.common import StableId
from pilot_assessment.ingestion.adapters.base import ArtifactAdapter

AdapterKey = tuple[str, str]
_STABLE_ID_ADAPTER = TypeAdapter(StableId)


class AdapterRegistryError(ValueError):
    """Base error for invalid or unresolved trusted adapter registrations."""


class AdapterNotFoundError(AdapterRegistryError):
    def __init__(self, format_name: str, schema_id: str) -> None:
        super().__init__(f"no trusted adapter for ({format_name!r}, {schema_id!r})")
        self.format_name = format_name
        self.schema_id = schema_id


class DuplicateAdapterRegistrationError(AdapterRegistryError):
    def __init__(self, key: AdapterKey) -> None:
        super().__init__(f"trusted adapter key is already registered: {key!r}")
        self.key = key


class InvalidAdapterRegistrationError(AdapterRegistryError):
    """Raised when an object does not satisfy the trusted adapter contract."""


class AdapterRegistry:
    """Registry populated from application code, never from manifest class names."""

    def __init__(self) -> None:
        self._adapters: dict[AdapterKey, ArtifactAdapter] = {}

    def register(self, adapter: ArtifactAdapter) -> None:
        if not isinstance(adapter, ArtifactAdapter):
            raise InvalidAdapterRegistrationError("adapter does not implement ArtifactAdapter")
        try:
            _STABLE_ID_ADAPTER.validate_python(adapter.adapter_id)
            _STABLE_ID_ADAPTER.validate_python(adapter.adapter_version)
        except ValidationError as error:
            raise InvalidAdapterRegistrationError("adapter identity must use stable IDs") from error
        if not adapter.keys:
            raise InvalidAdapterRegistrationError("adapter must declare at least one exact key")

        keys = tuple(adapter.keys)
        for key in keys:
            if len(key) != 2 or not key[0] or not key[1]:
                raise InvalidAdapterRegistrationError(
                    "adapter keys must be non-empty (format, schema_id) pairs"
                )
            try:
                _STABLE_ID_ADAPTER.validate_python(key[1])
            except ValidationError as error:
                raise InvalidAdapterRegistrationError(
                    "adapter schema IDs must be stable IDs"
                ) from error
            if key in self._adapters:
                raise DuplicateAdapterRegistrationError(key)

        for key in keys:
            self._adapters[key] = adapter

    def resolve(self, format_name: str, schema_id: str) -> ArtifactAdapter:
        try:
            return self._adapters[(format_name, schema_id)]
        except KeyError as error:
            raise AdapterNotFoundError(format_name, schema_id) from error

    @property
    def registrations(self) -> Mapping[AdapterKey, ArtifactAdapter]:
        return MappingProxyType(dict(self._adapters))


__all__ = [
    "AdapterKey",
    "AdapterNotFoundError",
    "AdapterRegistry",
    "AdapterRegistryError",
    "DuplicateAdapterRegistrationError",
    "InvalidAdapterRegistrationError",
]
