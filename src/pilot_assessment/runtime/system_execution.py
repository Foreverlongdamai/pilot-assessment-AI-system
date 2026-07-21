"""Freeze system-owned immutable scheme records into one project for execution."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from pilot_assessment.contracts.assessment_scheme import AssessmentSchemeVersion
from pilot_assessment.contracts.model_components import ComponentKind, PinnedComponentRef
from pilot_assessment.model_library.repository import (
    ComponentLibraryRepository,
    DuplicateLibraryItemError,
    LibraryItem,
    LibraryItemNotFoundError,
    component_kind,
    component_record_id,
)
from pilot_assessment.persistence.database import Clock, ProjectDatabase
from pilot_assessment.persistence.model_repository import SqliteComponentLibraryRepository


class SystemSchemeMaterializationError(RuntimeError):
    """A system-owned immutable scheme cannot be frozen into a project."""


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise SystemSchemeMaterializationError(
            "system scheme materialization clock must be timezone-aware"
        )
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _scheme_pins(scheme: AssessmentSchemeVersion) -> tuple[PinnedComponentRef, ...]:
    return (
        scheme.task_profile,
        scheme.reporting_policy,
        scheme.layout,
        *scheme.source_descriptors,
        *scheme.evidence_versions,
        *scheme.evidence_binding_versions,
        *scheme.bn_node_versions,
        *scheme.cpt_versions,
    )


class SystemSchemeExecutionMaterializer:
    """Copy one exact execution closure without making a project a model owner.

    The project copy is immutable run material.  Editing and scheme discovery remain
    system-owned; this bridge only makes old M5/M6 execution contracts portable.
    """

    def __init__(
        self,
        database: ProjectDatabase,
        destination: SqliteComponentLibraryRepository,
        source: ComponentLibraryRepository,
        *,
        clock: Clock,
    ) -> None:
        self.database = database
        self.destination = destination
        self.source = source
        self.clock = clock

    def ensure_available(self, scheme_version_id: str) -> AssessmentSchemeVersion:
        try:
            local = self.destination.get_exact(
                ComponentKind.ASSESSMENT_SCHEME_VERSION,
                scheme_version_id,
            )
        except LibraryItemNotFoundError:
            local = None

        if local is not None and not isinstance(local, AssessmentSchemeVersion):
            raise SystemSchemeMaterializationError(
                f"local scheme identity {scheme_version_id!r} has an invalid record type"
            )
        if isinstance(local, AssessmentSchemeVersion):
            scheme = local
        else:
            try:
                source_scheme = self.source.get_exact(
                    ComponentKind.ASSESSMENT_SCHEME_VERSION,
                    scheme_version_id,
                )
            except LibraryItemNotFoundError as error:
                raise SystemSchemeMaterializationError(
                    f"system scheme {scheme_version_id!r} does not exist"
                ) from error
            if not isinstance(source_scheme, AssessmentSchemeVersion):
                raise SystemSchemeMaterializationError(
                    f"system scheme identity {scheme_version_id!r} has an invalid record type"
                )
            scheme = source_scheme

        records: list[LibraryItem] = []
        for reference in _scheme_pins(scheme):
            try:
                self.destination.get_exact(reference.kind, reference.version_id)
                continue
            except LibraryItemNotFoundError:
                pass
            try:
                item = self.source.get_exact(reference.kind, reference.version_id)
            except LibraryItemNotFoundError as error:
                raise SystemSchemeMaterializationError(
                    "scheme dependency is absent from both project execution storage and "
                    f"the system model library: {reference.kind.value}:{reference.version_id}"
                ) from error
            if getattr(item, "content_hash", None) != reference.content_hash:
                raise SystemSchemeMaterializationError(
                    "system scheme dependency disagrees with its exact pin: "
                    f"{reference.kind.value}:{reference.version_id}"
                )
            records.append(item)
        if local is None:
            records.append(scheme)

        if not records:
            return scheme

        timestamp = _utc_text(self.clock())
        try:
            with self.database.transaction() as connection:
                for item in records:
                    kind = component_kind(item)
                    record_id = component_record_id(item)
                    exists = connection.execute(
                        "SELECT 1 FROM library_records WHERE kind = ? AND record_id = ?",
                        (kind.value, record_id),
                    ).fetchone()
                    if exists is None:
                        self.destination.add_in_transaction(
                            connection,
                            item,
                            recorded_at_text=timestamp,
                        )
                    elif self.destination.get_exact(kind, record_id) != item:
                        raise SystemSchemeMaterializationError(
                            "immutable project execution identity collides with system record "
                            f"{kind.value}:{record_id}"
                        )
        except (sqlite3.IntegrityError, DuplicateLibraryItemError) as error:
            raise SystemSchemeMaterializationError(
                "system scheme execution closure could not be frozen atomically"
            ) from error
        return scheme


__all__ = ["SystemSchemeExecutionMaterializer", "SystemSchemeMaterializationError"]
