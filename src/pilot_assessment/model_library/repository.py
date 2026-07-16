"""Transport-neutral repository for immutable global model-library records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, cast

from pilot_assessment.contracts.assessment_scheme import (
    AssessmentSchemeVersion,
    CoverageReportingPolicyVersion,
    LayoutVersion,
    TaskProfileVersion,
)
from pilot_assessment.contracts.model_components import (
    BnNodeConcept,
    BnNodeVersion,
    ComponentKind,
    ComponentLifecycle,
    CptVersion,
    EvidenceBindingVersion,
    EvidenceConcept,
    EvidenceVersion,
    SourceDescriptor,
    VersionLineage,
)
from pilot_assessment.model_library.identity import typed_content_sha256

ConceptLibraryItem = EvidenceConcept | BnNodeConcept
VersionLibraryItem = (
    EvidenceVersion
    | BnNodeVersion
    | EvidenceBindingVersion
    | CptVersion
    | TaskProfileVersion
    | CoverageReportingPolicyVersion
    | LayoutVersion
    | AssessmentSchemeVersion
    | SourceDescriptor
)
LibraryItem = ConceptLibraryItem | VersionLibraryItem

_KIND_BY_TYPE: dict[type[object], ComponentKind] = {
    EvidenceConcept: ComponentKind.EVIDENCE_CONCEPT,
    EvidenceVersion: ComponentKind.EVIDENCE_VERSION,
    BnNodeConcept: ComponentKind.BN_NODE_CONCEPT,
    BnNodeVersion: ComponentKind.BN_NODE_VERSION,
    EvidenceBindingVersion: ComponentKind.EVIDENCE_BINDING_VERSION,
    CptVersion: ComponentKind.CPT_VERSION,
    TaskProfileVersion: ComponentKind.TASK_PROFILE_VERSION,
    CoverageReportingPolicyVersion: ComponentKind.COVERAGE_REPORTING_POLICY_VERSION,
    LayoutVersion: ComponentKind.LAYOUT_VERSION,
    AssessmentSchemeVersion: ComponentKind.ASSESSMENT_SCHEME_VERSION,
    SourceDescriptor: ComponentKind.SOURCE_DESCRIPTOR,
}

_ID_FIELD_BY_KIND: dict[ComponentKind, str] = {
    ComponentKind.EVIDENCE_CONCEPT: "concept_id",
    ComponentKind.EVIDENCE_VERSION: "evidence_version_id",
    ComponentKind.BN_NODE_CONCEPT: "concept_id",
    ComponentKind.BN_NODE_VERSION: "bn_node_version_id",
    ComponentKind.EVIDENCE_BINDING_VERSION: "evidence_binding_version_id",
    ComponentKind.CPT_VERSION: "cpt_version_id",
    ComponentKind.TASK_PROFILE_VERSION: "task_profile_version_id",
    ComponentKind.COVERAGE_REPORTING_POLICY_VERSION: "policy_version_id",
    ComponentKind.LAYOUT_VERSION: "layout_version_id",
    ComponentKind.ASSESSMENT_SCHEME_VERSION: "scheme_version_id",
    ComponentKind.SOURCE_DESCRIPTOR: "source_id",
}

_OUTER_VERSION_ID_FIELDS: dict[ComponentKind, str] = {
    kind: field
    for kind, field in _ID_FIELD_BY_KIND.items()
    if kind
    not in {
        ComponentKind.EVIDENCE_CONCEPT,
        ComponentKind.BN_NODE_CONCEPT,
        ComponentKind.SOURCE_DESCRIPTOR,
    }
}

_HASH_BEARING_TYPES = (
    EvidenceVersion,
    BnNodeVersion,
    EvidenceBindingVersion,
    CptVersion,
    TaskProfileVersion,
    CoverageReportingPolicyVersion,
    LayoutVersion,
    AssessmentSchemeVersion,
    SourceDescriptor,
)


class ComponentLibraryError(ValueError):
    """Base class for deterministic library failures."""


class UnsupportedLibraryItemError(ComponentLibraryError):
    """Raised when an object is not one of the frozen public component contracts."""


class DuplicateLibraryItemError(ComponentLibraryError):
    """Raised when the same kind and exact ID are written more than once."""


class ComponentHashMismatchError(ComponentLibraryError):
    """Raised when a published component's content-hash claim is false."""


class LibraryItemNotFoundError(KeyError):
    """Raised when an exact kind/ID pair does not exist."""


@dataclass(frozen=True, slots=True)
class LibraryRecordMetadata:
    created_at: datetime
    lifecycle: ComponentLifecycle
    changed_at: datetime | None = None
    changed_by: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class LibraryRecord:
    kind: ComponentKind
    record_id: str
    concept_id: str | None
    tags: tuple[str, ...]
    item: LibraryItem
    metadata: LibraryRecordMetadata


@dataclass(frozen=True, slots=True)
class LibraryQuery:
    kind: ComponentKind | None = None
    concept_id: str | None = None
    lifecycle: ComponentLifecycle | None = None
    tags: tuple[str, ...] = ()


class ComponentLibraryRepository(Protocol):
    def add(self, item: LibraryItem, *, recorded_at: datetime) -> None: ...

    def get_exact(self, kind: ComponentKind, record_id: str) -> LibraryItem: ...

    def get_record(self, kind: ComponentKind, record_id: str) -> LibraryRecord: ...

    def list_records(self, query: LibraryQuery | None = None) -> tuple[LibraryRecord, ...]: ...

    def set_lifecycle(
        self,
        kind: ComponentKind,
        record_id: str,
        *,
        lifecycle: ComponentLifecycle,
        changed_at: datetime,
        changed_by: str,
        reason: str,
    ) -> LibraryRecordMetadata: ...

    def get_lineage(self, kind: ComponentKind, record_id: str) -> VersionLineage | None: ...


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ComponentLibraryError(f"{label} must be timezone-aware")


def component_kind(item: LibraryItem) -> ComponentKind:
    try:
        return _KIND_BY_TYPE[type(item)]
    except KeyError as error:
        raise UnsupportedLibraryItemError(type(item).__name__) from error


def component_record_id(item: LibraryItem) -> str:
    kind = component_kind(item)
    return cast(str, getattr(item, _ID_FIELD_BY_KIND[kind]))


def component_concept_id(item: LibraryItem) -> str | None:
    if isinstance(item, (EvidenceConcept, BnNodeConcept)):
        return item.concept_id
    if isinstance(item, (EvidenceVersion, BnNodeVersion)):
        return item.concept_id
    if isinstance(item, TaskProfileVersion):
        return item.task_concept_id
    if isinstance(item, AssessmentSchemeVersion):
        return item.scheme_concept_id
    return None


def component_lineage(item: LibraryItem) -> VersionLineage | None:
    if isinstance(
        item,
        (
            EvidenceVersion,
            BnNodeVersion,
            EvidenceBindingVersion,
            CptVersion,
            TaskProfileVersion,
            CoverageReportingPolicyVersion,
            LayoutVersion,
            AssessmentSchemeVersion,
        ),
    ):
        return item.lineage
    return None


def component_content_hash(item: VersionLibraryItem) -> str:
    """Hash semantic/execution content, excluding outer version identity and lineage audit."""

    kind = component_kind(item)
    if not isinstance(item, _HASH_BEARING_TYPES):
        raise UnsupportedLibraryItemError(f"{kind.value} does not carry content_hash")
    excluded = {"content_hash", "lineage"}
    outer_id_field = _OUTER_VERSION_ID_FIELDS.get(kind)
    if outer_id_field is not None:
        excluded.add(outer_id_field)
    payload = item.model_dump(mode="json", exclude=excluded)
    return typed_content_sha256(item.contract_id, item.contract_version, payload)


def _snapshot(item: LibraryItem) -> LibraryItem:
    return item.model_copy(deep=True)


class InMemoryComponentLibraryRepository:
    """Process-local immutable store; durable transactions remain M6 ownership."""

    def __init__(self) -> None:
        self._items: dict[tuple[ComponentKind, str], LibraryItem] = {}
        self._metadata: dict[tuple[ComponentKind, str], LibraryRecordMetadata] = {}

    def add(self, item: LibraryItem, *, recorded_at: datetime) -> None:
        _require_aware(recorded_at, "recorded_at")
        kind = component_kind(item)
        record_id = component_record_id(item)
        key = (kind, record_id)
        if key in self._items:
            raise DuplicateLibraryItemError(
                f"library item {kind.value}:{record_id} already exists and cannot be overwritten"
            )
        if isinstance(item, _HASH_BEARING_TYPES):
            actual = component_content_hash(item)
            if item.content_hash != actual:
                raise ComponentHashMismatchError(
                    f"component {kind.value}:{record_id} content hash claim does not match"
                )
        lifecycle = (
            item.lifecycle
            if isinstance(item, (EvidenceConcept, BnNodeConcept))
            else ComponentLifecycle.ACTIVE
        )
        self._items[key] = _snapshot(item)
        self._metadata[key] = LibraryRecordMetadata(
            created_at=recorded_at,
            lifecycle=lifecycle,
        )

    def get_exact(self, kind: ComponentKind, record_id: str) -> LibraryItem:
        try:
            return _snapshot(self._items[(kind, record_id)])
        except KeyError as error:
            raise LibraryItemNotFoundError(f"{kind.value}:{record_id}") from error

    def _tags_for(self, item: LibraryItem) -> tuple[str, ...]:
        if isinstance(item, (EvidenceConcept, BnNodeConcept)):
            return item.tags
        concept_id = component_concept_id(item)
        concept_kind = {
            ComponentKind.EVIDENCE_VERSION: ComponentKind.EVIDENCE_CONCEPT,
            ComponentKind.BN_NODE_VERSION: ComponentKind.BN_NODE_CONCEPT,
        }.get(component_kind(item))
        if concept_id is None or concept_kind is None:
            return ()
        concept = self._items.get((concept_kind, concept_id))
        if isinstance(concept, (EvidenceConcept, BnNodeConcept)):
            return concept.tags
        return ()

    def get_record(self, kind: ComponentKind, record_id: str) -> LibraryRecord:
        item = self.get_exact(kind, record_id)
        metadata = self._metadata[(kind, record_id)]
        return LibraryRecord(
            kind=kind,
            record_id=record_id,
            concept_id=component_concept_id(item),
            tags=self._tags_for(item),
            item=item,
            metadata=metadata,
        )

    def list_records(self, query: LibraryQuery | None = None) -> tuple[LibraryRecord, ...]:
        selected = query or LibraryQuery()
        required_tags = frozenset(selected.tags)
        records: list[LibraryRecord] = []
        for kind, record_id in self._items:
            record = self.get_record(kind, record_id)
            if selected.kind is not None and record.kind is not selected.kind:
                continue
            if selected.concept_id is not None and record.concept_id != selected.concept_id:
                continue
            if (
                selected.lifecycle is not None
                and record.metadata.lifecycle is not selected.lifecycle
            ):
                continue
            if not required_tags.issubset(record.tags):
                continue
            records.append(record)
        records.sort(
            key=lambda record: (
                record.metadata.created_at,
                record.record_id,
                record.kind.value,
            )
        )
        return tuple(records)

    def set_lifecycle(
        self,
        kind: ComponentKind,
        record_id: str,
        *,
        lifecycle: ComponentLifecycle,
        changed_at: datetime,
        changed_by: str,
        reason: str,
    ) -> LibraryRecordMetadata:
        _require_aware(changed_at, "changed_at")
        if not changed_by:
            raise ComponentLibraryError("changed_by must not be empty")
        if not reason:
            raise ComponentLibraryError("lifecycle reason must not be empty")
        key = (kind, record_id)
        try:
            previous = self._metadata[key]
        except KeyError as error:
            raise LibraryItemNotFoundError(f"{kind.value}:{record_id}") from error
        updated = LibraryRecordMetadata(
            created_at=previous.created_at,
            lifecycle=lifecycle,
            changed_at=changed_at,
            changed_by=changed_by,
            reason=reason,
        )
        self._metadata[key] = updated
        return updated

    def get_lineage(self, kind: ComponentKind, record_id: str) -> VersionLineage | None:
        return component_lineage(self.get_exact(kind, record_id))

    def clone(self) -> InMemoryComponentLibraryRepository:
        """Return an isolated staging copy for an in-memory workspace transaction."""

        cloned = InMemoryComponentLibraryRepository()
        cloned._items = {key: _snapshot(item) for key, item in self._items.items()}
        cloned._metadata = dict(self._metadata)
        return cloned

    def replace_from(self, staged: InMemoryComponentLibraryRepository) -> None:
        """Commit a fully validated staging copy using two non-failing assignments."""

        if not isinstance(staged, InMemoryComponentLibraryRepository):
            raise ComponentLibraryError("staged repository must use the in-memory adapter")
        self._items = {key: _snapshot(item) for key, item in staged._items.items()}
        self._metadata = dict(staged._metadata)


__all__ = [
    "ComponentHashMismatchError",
    "ComponentLibraryError",
    "ComponentLibraryRepository",
    "ConceptLibraryItem",
    "DuplicateLibraryItemError",
    "InMemoryComponentLibraryRepository",
    "LibraryItem",
    "LibraryItemNotFoundError",
    "LibraryQuery",
    "LibraryRecord",
    "LibraryRecordMetadata",
    "UnsupportedLibraryItemError",
    "VersionLibraryItem",
    "component_concept_id",
    "component_content_hash",
    "component_kind",
    "component_lineage",
    "component_record_id",
]
