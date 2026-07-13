"""Immutable runtime containers used by M4 reference binding."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from pydantic import TypeAdapter

from pilot_assessment.contracts.anchor_execution import (
    ReferenceAlignmentContract,
    ReferenceSessionIdentity,
    ReferenceSourceKind,
    ReferenceTableContract,
    ResolvedReferenceDescriptor,
)
from pilot_assessment.contracts.common import Sha256Digest, StableId
from pilot_assessment.synchronization.models import AlignedStreamView

_STABLE_ID_ADAPTER = TypeAdapter(StableId)
_SHA256_ADAPTER = TypeAdapter(Sha256Digest)


def _strict_stable_id(value: object, *, field_name: str) -> str:
    try:
        return _STABLE_ID_ADAPTER.validate_python(value, strict=True)
    except ValueError as error:
        raise ValueError(f"{field_name} must be a valid stable ID") from error


def _strict_sha256(value: object, *, field_name: str) -> str:
    try:
        return _SHA256_ADAPTER.validate_python(value, strict=True)
    except ValueError as error:
        raise ValueError(f"{field_name} must be a SHA-256 digest") from error


@dataclass(frozen=True, slots=True)
class ReferenceViewCandidate:
    """One trusted, session-bound runtime reference candidate."""

    reference_id: StableId
    source_kind: ReferenceSourceKind
    session_identity: ReferenceSessionIdentity
    aligned_view: AlignedStreamView
    alignment_contract: ReferenceAlignmentContract
    table_contract: ReferenceTableContract
    resource_fingerprint: Sha256Digest
    aligned_content_fingerprint: Sha256Digest
    alignment_fingerprint: Sha256Digest

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reference_id",
            _strict_stable_id(self.reference_id, field_name="reference_id"),
        )
        if not isinstance(self.source_kind, ReferenceSourceKind):
            raise TypeError("source_kind must be a ReferenceSourceKind")
        if not isinstance(self.session_identity, ReferenceSessionIdentity):
            raise TypeError("session_identity must be a ReferenceSessionIdentity")
        if not isinstance(self.aligned_view, AlignedStreamView):
            raise TypeError("aligned_view must be an AlignedStreamView")
        if not isinstance(self.alignment_contract, ReferenceAlignmentContract):
            raise TypeError("alignment_contract must be a ReferenceAlignmentContract")
        if not isinstance(self.table_contract, ReferenceTableContract):
            raise TypeError("table_contract must be a ReferenceTableContract")
        for field_name in (
            "resource_fingerprint",
            "aligned_content_fingerprint",
            "alignment_fingerprint",
        ):
            object.__setattr__(
                self,
                field_name,
                _strict_sha256(getattr(self, field_name), field_name=field_name),
            )


@dataclass(frozen=True, slots=True)
class ResolvedReference:
    """One descriptor paired with its exact runtime view, when present."""

    descriptor: ResolvedReferenceDescriptor
    aligned_view: AlignedStreamView | None

    def __post_init__(self) -> None:
        if not isinstance(self.descriptor, ResolvedReferenceDescriptor):
            raise TypeError("descriptor must be a ResolvedReferenceDescriptor")
        if self.aligned_view is not None and not isinstance(self.aligned_view, AlignedStreamView):
            raise TypeError("aligned_view must be an AlignedStreamView or None")

        status = self.descriptor.resolution_status.value
        if (status == "present") != (self.aligned_view is not None):
            raise ValueError("present descriptors require a view and absent descriptors forbid one")


@dataclass(frozen=True, slots=True)
class ResolvedReferenceSet:
    """Frozen runtime reference inventory for one aligned session."""

    session_identity: ReferenceSessionIdentity
    entries: Mapping[str, ResolvedReference]
    reference_set_fingerprint: Sha256Digest

    def __post_init__(self) -> None:
        if not isinstance(self.session_identity, ReferenceSessionIdentity):
            raise TypeError("session_identity must be a ReferenceSessionIdentity")
        if not isinstance(self.entries, Mapping):
            raise TypeError("entries must be a mapping")

        frozen_entries: dict[str, ResolvedReference] = {}
        for raw_key, entry in self.entries.items():
            key = _strict_stable_id(raw_key, field_name="entries key")
            if not isinstance(entry, ResolvedReference):
                raise TypeError("entries values must be ResolvedReference instances")
            if key != entry.descriptor.reference_id:
                raise ValueError("entry key must equal descriptor reference_id")
            frozen_entries[key] = entry

        object.__setattr__(self, "entries", MappingProxyType(frozen_entries))
        object.__setattr__(
            self,
            "reference_set_fingerprint",
            _strict_sha256(
                self.reference_set_fingerprint,
                field_name="reference_set_fingerprint",
            ),
        )


__all__ = [
    "ReferenceViewCandidate",
    "ResolvedReference",
    "ResolvedReferenceSet",
]
