"""Trusted in-process adapter boundary for M2 ingestion."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import ClassVar, Protocol, runtime_checkable

from pydantic import JsonValue

from pilot_assessment.contracts.errors import DomainErrorData
from pilot_assessment.contracts.session import StreamDescriptor
from pilot_assessment.ingestion.models import NormalizedStream
from pilot_assessment.ingestion.profiles import ArtifactProfile


@dataclass(frozen=True, slots=True)
class AdapterRequest:
    """A verified physical source group dispatched to one trusted adapter."""

    bundle_root: Path
    descriptors: Mapping[str, StreamDescriptor]
    source_paths: tuple[str, ...]
    verified_digests: Mapping[str, str]
    profile: ArtifactProfile

    def __post_init__(self) -> None:
        if not self.descriptors:
            raise ValueError("adapter requests require at least one stream descriptor")
        mismatched = [
            stream_id
            for stream_id, descriptor in self.descriptors.items()
            if stream_id != descriptor.modality
        ]
        if mismatched:
            raise ValueError(f"descriptor keys must match modality: {sorted(mismatched)}")
        folded = [path.casefold() for path in self.source_paths]
        if len(folded) != len(set(folded)):
            raise ValueError("adapter source paths must be unique under Windows case folding")
        if set(self.source_paths) != set(self.verified_digests):
            raise ValueError("verified digest keys must match adapter source paths")
        object.__setattr__(self, "bundle_root", Path(self.bundle_root))
        object.__setattr__(self, "descriptors", MappingProxyType(dict(self.descriptors)))
        object.__setattr__(self, "source_paths", tuple(self.source_paths))
        object.__setattr__(
            self,
            "verified_digests",
            MappingProxyType(dict(self.verified_digests)),
        )


@dataclass(frozen=True, slots=True)
class AdapterArtifactSummary:
    """Small report-facing summary of one inspected artifact role."""

    role: str
    paths: tuple[str, ...]
    row_count: int | None

    def __post_init__(self) -> None:
        if not self.role:
            raise ValueError("artifact summary role must be non-empty")
        if self.row_count is not None and self.row_count < 0:
            raise ValueError("artifact row_count must be non-negative")
        object.__setattr__(self, "paths", tuple(self.paths))


@dataclass(frozen=True, slots=True)
class AdapterResult:
    """Normalized adapter output plus bounded issues and summaries."""

    streams: Mapping[str, NormalizedStream]
    context: Mapping[str, JsonValue]
    artifact_summaries: tuple[AdapterArtifactSummary, ...]
    issues: tuple[DomainErrorData, ...] = ()

    def __post_init__(self) -> None:
        mismatched = [
            stream_id for stream_id, stream in self.streams.items() if stream_id != stream.modality
        ]
        if mismatched:
            raise ValueError(f"adapter stream keys must match modality: {sorted(mismatched)}")
        object.__setattr__(self, "streams", MappingProxyType(dict(self.streams)))
        object.__setattr__(self, "context", MappingProxyType(dict(self.context)))
        object.__setattr__(self, "artifact_summaries", tuple(self.artifact_summaries))
        object.__setattr__(self, "issues", tuple(self.issues))


class AdapterInspectionError(Exception):
    """Typed adapter failure that never exposes a raw library exception."""

    def __init__(self, issue: DomainErrorData) -> None:
        super().__init__(issue.message)
        self.issue = issue


@runtime_checkable
class ArtifactAdapter(Protocol):
    """Protocol implemented only by adapters registered in trusted code."""

    adapter_id: ClassVar[str]
    adapter_version: ClassVar[str]
    keys: ClassVar[frozenset[tuple[str, str]]]

    def inspect(self, request: AdapterRequest) -> AdapterResult: ...


__all__ = [
    "AdapterArtifactSummary",
    "AdapterInspectionError",
    "AdapterRequest",
    "AdapterResult",
    "ArtifactAdapter",
]
