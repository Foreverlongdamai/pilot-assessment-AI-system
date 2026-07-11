"""Trusted adapter interfaces and exact-key registry."""

from pilot_assessment.ingestion.adapters.base import (
    AdapterArtifactSummary,
    AdapterInspectionError,
    AdapterRequest,
    AdapterResult,
    ArtifactAdapter,
)
from pilot_assessment.ingestion.adapters.registry import (
    AdapterKey,
    AdapterNotFoundError,
    AdapterRegistry,
    AdapterRegistryError,
    DuplicateAdapterRegistrationError,
    InvalidAdapterRegistrationError,
)

__all__ = [
    "AdapterArtifactSummary",
    "AdapterInspectionError",
    "AdapterKey",
    "AdapterNotFoundError",
    "AdapterRegistry",
    "AdapterRegistryError",
    "AdapterRequest",
    "AdapterResult",
    "ArtifactAdapter",
    "DuplicateAdapterRegistrationError",
    "InvalidAdapterRegistrationError",
]
