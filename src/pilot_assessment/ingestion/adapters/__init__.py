"""Trusted adapter interfaces and exact-key registry."""

from pilot_assessment.ingestion.adapters.base import (
    AdapterArtifactSummary,
    AdapterInspectionError,
    AdapterRequest,
    AdapterResult,
    ArtifactAdapter,
)
from pilot_assessment.ingestion.adapters.composite import (
    COMPOSITE_KEYS,
    CompositeStreamAdapter,
)
from pilot_assessment.ingestion.adapters.image_sequence import (
    MAX_IMAGE_PIXELS,
    inspect_image_sequence,
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
    "COMPOSITE_KEYS",
    "CompositeStreamAdapter",
    "DuplicateAdapterRegistrationError",
    "InvalidAdapterRegistrationError",
    "MAX_IMAGE_PIXELS",
    "inspect_image_sequence",
]
