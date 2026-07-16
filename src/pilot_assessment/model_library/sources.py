"""Typed source registry and extraction-provenance closure validation."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from importlib.resources import files
from typing import cast

from pydantic import JsonValue, ValidationError

from pilot_assessment.contracts.evidence_recipe import (
    PortCardinality,
    PortType,
    TemporalSemantics,
)
from pilot_assessment.contracts.model_components import (
    RawModality,
    SourceDescriptor,
    SourceKind,
)
from pilot_assessment.model_library.identity import typed_content_sha256


class SourceCatalogError(ValueError):
    """Raised when a source registry or packaged descriptor resource is invalid."""


class SourceCatalogLookupError(KeyError):
    """Raised when a source has neither an exact descriptor nor a diagnostic fallback."""


class SourceDiagnosticCode(StrEnum):
    UNKNOWN_SOURCE = "unknown_source"
    PROVENANCE_CYCLE = "provenance_cycle"
    DERIVED_SOURCE_WITHOUT_DEPENDENCIES = "derived_source_without_dependencies"
    EVIDENCE_OBSERVATION_INPUT = "evidence_observation_input"


@dataclass(frozen=True, slots=True)
class SourceDiagnostic:
    code: SourceDiagnosticCode
    source_id: str
    source_path: tuple[str, ...]
    message: str


@dataclass(frozen=True, slots=True)
class SourceClosureReport:
    requested_source_ids: tuple[str, ...]
    resolved_source_ids: tuple[str, ...]
    root_source_ids: tuple[str, ...]
    raw_modalities: tuple[RawModality, ...]
    diagnostics: tuple[SourceDiagnostic, ...]

    @property
    def compatible(self) -> bool:
        return not self.diagnostics


def source_descriptor_content_hash(descriptor: SourceDescriptor) -> str:
    """Return the typed content identity of a descriptor excluding its own hash field."""

    payload = descriptor.model_dump(mode="json", exclude={"content_hash"})
    return typed_content_sha256("source-descriptor", "0.1.0", payload)


def create_source_descriptor(
    *,
    source_id: str,
    kind: SourceKind,
    name: str,
    description: str,
    declared_type: PortType,
    raw_modality: RawModality | None = None,
    source_dependencies: tuple[str, ...] = (),
    metadata: Mapping[str, JsonValue] | None = None,
) -> SourceDescriptor:
    """Build one descriptor with a deterministic typed content identity."""

    payload: dict[str, object] = {
        "contract_id": "source-descriptor",
        "contract_version": "0.1.0",
        "source_id": source_id,
        "kind": kind.value,
        "name": name,
        "description": description,
        "declared_type": declared_type.model_dump(mode="json"),
        "raw_modality": raw_modality.value if raw_modality is not None else None,
        "source_dependencies": list(source_dependencies),
        "metadata": dict(metadata or {}),
    }
    content_hash = typed_content_sha256("source-descriptor", "0.1.0", payload)
    return SourceDescriptor.model_validate({**payload, "content_hash": content_hash})


def _evidence_observation_fallback(source_id: str) -> SourceDescriptor:
    return create_source_descriptor(
        source_id=source_id,
        kind=SourceKind.EVIDENCE_OBSERVATION,
        name=f"Legacy Evidence observation {source_id}",
        description=(
            "Namespace-classified observation produced by another scored Evidence. "
            "It is retained for migration diagnostics and cannot be an active extraction input."
        ),
        declared_type=PortType(
            value_type="number",
            cardinality=PortCardinality.ONE,
            temporal_semantics=TemporalSemantics.TIMELESS,
            unit=None,
        ),
        metadata={"resolution": "namespace_fallback", "legacy_only": True},
    )


class SourceCatalog:
    """Exact source descriptors plus narrow namespace classification for legacy evidence."""

    _EVIDENCE_OBSERVATION_PREFIXES = ("anchor.", "evidence-observation.")

    def __init__(self, descriptors: Iterable[SourceDescriptor] = ()) -> None:
        self._descriptors: dict[str, SourceDescriptor] = {}
        for descriptor in descriptors:
            self.register(descriptor)

    def register(self, descriptor: SourceDescriptor) -> None:
        if not isinstance(descriptor, SourceDescriptor):
            raise SourceCatalogError("source catalog entries must use SourceDescriptor")
        if descriptor.source_id in self._descriptors:
            raise SourceCatalogError(f"duplicate source descriptor {descriptor.source_id!r}")
        if descriptor.kind is not SourceKind.DERIVED_ARTIFACT and descriptor.source_dependencies:
            raise SourceCatalogError(
                f"root source {descriptor.source_id!r} cannot declare dependencies"
            )
        actual_hash = source_descriptor_content_hash(descriptor)
        if descriptor.content_hash != actual_hash:
            raise SourceCatalogError(
                f"source descriptor {descriptor.source_id!r} has an invalid content hash"
            )
        self._descriptors[descriptor.source_id] = descriptor

    def get(self, source_id: str) -> SourceDescriptor:
        """Return an explicitly registered descriptor."""

        try:
            return self._descriptors[source_id]
        except KeyError as error:
            raise SourceCatalogLookupError(source_id) from error

    def resolve(self, source_id: str) -> SourceDescriptor:
        """Resolve an exact descriptor or a narrow legacy-observation fallback."""

        descriptor = self._descriptors.get(source_id)
        if descriptor is not None:
            return descriptor
        if source_id.startswith(self._EVIDENCE_OBSERVATION_PREFIXES):
            return _evidence_observation_fallback(source_id)
        raise SourceCatalogLookupError(source_id)

    def descriptors(self) -> tuple[SourceDescriptor, ...]:
        return tuple(self._descriptors[key] for key in sorted(self._descriptors))

    def __len__(self) -> int:
        return len(self._descriptors)

    def validate_extraction_sources(
        self,
        source_ids: Iterable[str],
    ) -> SourceClosureReport:
        """Validate that each extraction source closes to raw/session/task roots."""

        requested = tuple(source_ids)
        resolved: list[str] = []
        resolved_seen: set[str] = set()
        roots: list[str] = []
        root_seen: set[str] = set()
        modalities: list[RawModality] = []
        modality_seen: set[RawModality] = set()
        diagnostics: list[SourceDiagnostic] = []
        completed: set[str] = set()

        def add_resolved(source_id: str) -> None:
            if source_id not in resolved_seen:
                resolved_seen.add(source_id)
                resolved.append(source_id)

        def visit(source_id: str, source_path: tuple[str, ...], active: tuple[str, ...]) -> None:
            if source_id in active:
                diagnostics.append(
                    SourceDiagnostic(
                        code=SourceDiagnosticCode.PROVENANCE_CYCLE,
                        source_id=source_id,
                        source_path=source_path,
                        message=f"source provenance cycle: {' -> '.join(source_path)}",
                    )
                )
                return
            if source_id in completed:
                return
            try:
                descriptor = self.resolve(source_id)
            except SourceCatalogLookupError:
                diagnostics.append(
                    SourceDiagnostic(
                        code=SourceDiagnosticCode.UNKNOWN_SOURCE,
                        source_id=source_id,
                        source_path=source_path,
                        message=f"source descriptor {source_id!r} is not registered",
                    )
                )
                return

            add_resolved(source_id)
            if descriptor.kind is SourceKind.EVIDENCE_OBSERVATION:
                diagnostics.append(
                    SourceDiagnostic(
                        code=SourceDiagnosticCode.EVIDENCE_OBSERVATION_INPUT,
                        source_id=source_id,
                        source_path=source_path,
                        message=(
                            "a scored Evidence observation cannot be used as an active "
                            "Evidence extraction input"
                        ),
                    )
                )
                completed.add(source_id)
                return

            if descriptor.kind is SourceKind.DERIVED_ARTIFACT:
                if not descriptor.source_dependencies:
                    diagnostics.append(
                        SourceDiagnostic(
                            code=SourceDiagnosticCode.DERIVED_SOURCE_WITHOUT_DEPENDENCIES,
                            source_id=source_id,
                            source_path=source_path,
                            message=(
                                f"derived source {source_id!r} has no declared provenance "
                                "dependencies"
                            ),
                        )
                    )
                else:
                    next_active = (*active, source_id)
                    for dependency in descriptor.source_dependencies:
                        visit(dependency, (*source_path, dependency), next_active)
                completed.add(source_id)
                return

            if source_id not in root_seen:
                root_seen.add(source_id)
                roots.append(source_id)
            if (
                descriptor.kind is SourceKind.RAW_STREAM
                and descriptor.raw_modality is not None
                and descriptor.raw_modality not in modality_seen
            ):
                modality_seen.add(descriptor.raw_modality)
                modalities.append(descriptor.raw_modality)
            completed.add(source_id)

        for source_id in requested:
            visit(source_id, (source_id,), ())

        return SourceClosureReport(
            requested_source_ids=requested,
            resolved_source_ids=tuple(resolved),
            root_source_ids=tuple(roots),
            raw_modalities=tuple(modalities),
            diagnostics=tuple(diagnostics),
        )


def load_hover_source_catalog() -> SourceCatalog:
    """Load the starter source registry used by M4R migration and the Hover template."""

    resource = files("pilot_assessment.model_library").joinpath(
        "profile_data", "hover", "source-descriptors.json"
    )
    try:
        raw = json.loads(resource.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise SourceCatalogError("cannot load Hover source descriptor resource") from error
    if not isinstance(raw, Mapping):
        raise SourceCatalogError("source descriptor resource must be a JSON object")
    mapping = cast(Mapping[str, object], raw)
    if mapping.get("contract_id") != "source-descriptor-catalog":
        raise SourceCatalogError("source descriptor resource has an invalid contract_id")
    if mapping.get("contract_version") != "0.1.0":
        raise SourceCatalogError("source descriptor resource has an unsupported version")
    entries = mapping.get("descriptors")
    if not isinstance(entries, list):
        raise SourceCatalogError("source descriptor resource must contain a descriptor array")
    try:
        descriptors = tuple(SourceDescriptor.model_validate(entry) for entry in entries)
    except (TypeError, ValidationError, ValueError) as error:
        raise SourceCatalogError("source descriptor resource contains an invalid entry") from error
    return SourceCatalog(descriptors)


__all__ = [
    "SourceCatalog",
    "SourceCatalogError",
    "SourceCatalogLookupError",
    "SourceClosureReport",
    "SourceDiagnostic",
    "SourceDiagnosticCode",
    "create_source_descriptor",
    "load_hover_source_catalog",
    "source_descriptor_content_hash",
]
