"""Application service for exact, copy-on-write global component versions."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol, cast

from pydantic import BaseModel

from pilot_assessment.contracts.assessment_scheme import (
    AssessmentSchemeVersion,
    CoverageReportingPolicyVersion,
    LayoutVersion,
    TaskProfileVersion,
)
from pilot_assessment.contracts.model_components import (
    BnNodeConcept,
    BnNodeRole,
    BnNodeVersion,
    ComponentKind,
    ComponentLifecycle,
    CptVersion,
    EvidenceBindingVersion,
    EvidenceConcept,
    EvidenceVersion,
    VersionLineage,
)
from pilot_assessment.model_library.repository import (
    ComponentLibraryRepository,
    LibraryItem,
    LibraryQuery,
    LibraryRecord,
    LibraryRecordMetadata,
    VersionLibraryItem,
    component_content_hash,
    component_kind,
    component_lineage,
    component_record_id,
)

ZERO_HASH = "0" * 64


class Clock(Protocol):
    def now(self) -> datetime: ...


class IdFactory(Protocol):
    def new_id(self, kind: ComponentKind) -> str: ...


class ModelLibraryServiceError(ValueError):
    """Raised when a create request tries to bypass canonical identity fields."""


_VERSION_MODELS: dict[ComponentKind, type[BaseModel]] = {
    ComponentKind.EVIDENCE_VERSION: EvidenceVersion,
    ComponentKind.BN_NODE_VERSION: BnNodeVersion,
    ComponentKind.EVIDENCE_BINDING_VERSION: EvidenceBindingVersion,
    ComponentKind.CPT_VERSION: CptVersion,
    ComponentKind.TASK_PROFILE_VERSION: TaskProfileVersion,
    ComponentKind.COVERAGE_REPORTING_POLICY_VERSION: CoverageReportingPolicyVersion,
    ComponentKind.LAYOUT_VERSION: LayoutVersion,
    ComponentKind.ASSESSMENT_SCHEME_VERSION: AssessmentSchemeVersion,
}

_VERSION_ID_FIELDS: dict[ComponentKind, str] = {
    ComponentKind.EVIDENCE_VERSION: "evidence_version_id",
    ComponentKind.BN_NODE_VERSION: "bn_node_version_id",
    ComponentKind.EVIDENCE_BINDING_VERSION: "evidence_binding_version_id",
    ComponentKind.CPT_VERSION: "cpt_version_id",
    ComponentKind.TASK_PROFILE_VERSION: "task_profile_version_id",
    ComponentKind.COVERAGE_REPORTING_POLICY_VERSION: "policy_version_id",
    ComponentKind.LAYOUT_VERSION: "layout_version_id",
    ComponentKind.ASSESSMENT_SCHEME_VERSION: "scheme_version_id",
}

_RESERVED_CREATE_FIELDS = frozenset(
    {
        "contract_id",
        "contract_version",
        "content_hash",
        "lineage",
        *(field for field in _VERSION_ID_FIELDS.values()),
    }
)


class ModelLibraryService:
    """Create and query exact records without implicit version selection."""

    def __init__(
        self,
        repository: ComponentLibraryRepository,
        *,
        clock: Clock,
        ids: IdFactory,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._ids = ids

    def create_evidence_concept(
        self,
        *,
        name: str,
        description: str,
        tags: tuple[str, ...] = (),
    ) -> EvidenceConcept:
        concept = EvidenceConcept(
            concept_id=self._ids.new_id(ComponentKind.EVIDENCE_CONCEPT),
            name=name,
            description=description,
            tags=tags,
            lifecycle=ComponentLifecycle.ACTIVE,
        )
        self._repository.add(concept, recorded_at=self._clock.now())
        return concept

    def create_bn_node_concept(
        self,
        *,
        name: str,
        description: str,
        node_role: BnNodeRole,
        tags: tuple[str, ...] = (),
    ) -> BnNodeConcept:
        concept = BnNodeConcept(
            concept_id=self._ids.new_id(ComponentKind.BN_NODE_CONCEPT),
            name=name,
            description=description,
            node_role=node_role,
            tags=tags,
            lifecycle=ComponentLifecycle.ACTIVE,
        )
        self._repository.add(concept, recorded_at=self._clock.now())
        return concept

    def _require_concept(self, kind: ComponentKind, payload: Mapping[str, object]) -> None:
        relationship = {
            ComponentKind.EVIDENCE_VERSION: (
                ComponentKind.EVIDENCE_CONCEPT,
                "concept_id",
            ),
            ComponentKind.BN_NODE_VERSION: (
                ComponentKind.BN_NODE_CONCEPT,
                "concept_id",
            ),
        }.get(kind)
        if relationship is None:
            return
        concept_kind, field = relationship
        value = payload.get(field)
        if type(value) is not str:
            raise ModelLibraryServiceError(f"{kind.value} requires a string {field}")
        self._repository.get_exact(concept_kind, value)

    def create_version(
        self,
        kind: ComponentKind,
        payload: Mapping[str, object],
        *,
        created_by: str,
        source_version_ids: tuple[str, ...] = (),
        note: str | None = None,
    ) -> VersionLibraryItem:
        model_type = _VERSION_MODELS.get(kind)
        id_field = _VERSION_ID_FIELDS.get(kind)
        if model_type is None or id_field is None:
            raise ModelLibraryServiceError(f"{kind.value} is not creatable as a version")
        forbidden = _RESERVED_CREATE_FIELDS.intersection(payload)
        if forbidden:
            fields = ", ".join(sorted(forbidden))
            raise ModelLibraryServiceError(f"version payload contains reserved fields: {fields}")
        self._require_concept(kind, payload)
        created_at = self._clock.now()
        lineage = VersionLineage(
            source_version_ids=source_version_ids,
            created_at=created_at,
            created_by=created_by,
            note=note,
        )
        provisional = model_type.model_validate(
            {
                **dict(payload),
                id_field: self._ids.new_id(kind),
                "lineage": lineage,
                "content_hash": ZERO_HASH,
            }
        )
        version = cast(VersionLibraryItem, provisional)
        materialized = model_type.model_validate(
            {
                **version.model_dump(),
                "content_hash": component_content_hash(version),
            }
        )
        result = cast(VersionLibraryItem, materialized)
        self._repository.add(result, recorded_at=created_at)
        return result

    def publish_existing(self, item: LibraryItem) -> LibraryItem:
        """Import a frozen record while preserving its existing ID/hash/lineage."""

        lineage = component_lineage(item)
        recorded_at = lineage.created_at if lineage is not None else self._clock.now()
        self._repository.add(item, recorded_at=recorded_at)
        return self._repository.get_exact(component_kind(item), component_record_id(item))

    def get_exact(self, kind: ComponentKind, record_id: str) -> LibraryItem:
        return self._repository.get_exact(kind, record_id)

    def list_records(self, query: LibraryQuery | None = None) -> tuple[LibraryRecord, ...]:
        return self._repository.list_records(query)

    def get_lineage(self, kind: ComponentKind, record_id: str) -> VersionLineage | None:
        return self._repository.get_lineage(kind, record_id)

    def archive(
        self,
        kind: ComponentKind,
        record_id: str,
        *,
        changed_by: str,
        reason: str,
    ) -> LibraryRecordMetadata:
        return self._repository.set_lifecycle(
            kind,
            record_id,
            lifecycle=ComponentLifecycle.ARCHIVED,
            changed_at=self._clock.now(),
            changed_by=changed_by,
            reason=reason,
        )


__all__ = [
    "Clock",
    "IdFactory",
    "ModelLibraryService",
    "ModelLibraryServiceError",
]
