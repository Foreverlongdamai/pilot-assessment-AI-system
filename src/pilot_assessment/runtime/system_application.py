"""Composition root for one software copy's shared model system."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Self
from uuid import uuid4

from pilot_assessment.contracts.model_components import ComponentKind, SourceDescriptor
from pilot_assessment.evidence.builtins import register_builtin_operators
from pilot_assessment.evidence.extensions import register_extension_operators
from pilot_assessment.evidence.registry import OperatorRegistry
from pilot_assessment.model_library.profile import LoadedModelProfile, load_hover_starter_package
from pilot_assessment.model_library.repository import (
    LibraryQuery,
    component_kind,
    component_record_id,
)
from pilot_assessment.model_library.service import ModelLibraryService
from pilot_assessment.model_library.sources import SourceCatalog
from pilot_assessment.model_workspace.content_migration import migrate_current_model_content
from pilot_assessment.model_workspace.edit_session import ModelEditSessionManager
from pilot_assessment.model_workspace.legacy_import import LegacyProjectModelImporter
from pilot_assessment.model_workspace.migration import (
    CURRENT_HOVER_STARTER_SEED_ID,
    CurrentStarterSeedResult,
    seed_current_starter,
)
from pilot_assessment.model_workspace.service import CurrentModelWorkspaceService
from pilot_assessment.persistence.audit import AuditRepository
from pilot_assessment.persistence.database import Clock, ProjectDatabase
from pilot_assessment.persistence.draft_repository import (
    SqliteSchemeDraftRepository,
    SqliteWorkspaceUnitOfWork,
)
from pilot_assessment.persistence.model_repository import SqliteComponentLibraryRepository
from pilot_assessment.persistence.model_workspace_repository import SqliteModelWorkspaceRepository
from pilot_assessment.persistence.system import SystemStore
from pilot_assessment.persistence.transactions import IdempotencyStore
from pilot_assessment.runtime.source_provenance import BackendSourceProvenance
from pilot_assessment.runtime.sources import (
    RuntimeSourceProviderRegistry,
    register_hover_source_providers,
)
from pilot_assessment.schemes.service import SchemeWorkspaceService

PRODUCT_VERSION = "0.1.0"
HOVER_STARTER_SEED_ID = "starter.hover.package.0.1.0"


class RuntimeCompositionError(RuntimeError):
    """Raised when one application graph cannot share a coherent owner boundary."""


class StarterSeedError(RuntimeCompositionError):
    """Raised when an existing seed marker or exact starter record is inconsistent."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise StarterSeedError("starter seed timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class StarterSeedResult:
    seed_id: str
    manifest_hash: str
    applied: bool
    inserted_records: int
    total_records: int


@dataclass(frozen=True, slots=True)
class _ServiceClock:
    read: Clock = field(repr=False)

    def now(self) -> datetime:
        return self.read()


class UuidComponentIdFactory:
    """Generate opaque component IDs without task- or node-specific branching."""

    def new_id(self, kind: ComponentKind) -> str:
        return f"{kind.value}.{uuid4().hex}"


@dataclass(slots=True)
class SystemApplication:
    """All shared model, operator, and edit services for one software copy."""

    store: SystemStore
    components: SqliteComponentLibraryRepository
    drafts: SqliteSchemeDraftRepository
    unit_of_work: SqliteWorkspaceUnitOfWork
    model_library: ModelLibraryService
    schemes: SchemeWorkspaceService
    current_model: CurrentModelWorkspaceService
    model_edits: ModelEditSessionManager
    legacy_model_importer: LegacyProjectModelImporter
    operator_registry: OperatorRegistry
    source_provenance: BackendSourceProvenance
    source_provider_registry: RuntimeSourceProviderRegistry
    source_catalog: SourceCatalog
    audit: AuditRepository
    idempotency: IdempotencyStore
    starter_scheme_id: str
    current_starter_scheme_id: str
    seed_result: StarterSeedResult
    current_seed_result: CurrentStarterSeedResult
    _starter_profile: LoadedModelProfile = field(repr=False)
    _clock: Clock = field(repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    @classmethod
    def open_or_create(
        cls,
        root: str | Path,
        *,
        clock: Clock = _utc_now,
        product_version: str = PRODUCT_VERSION,
        model_library_id: str | None = None,
        product_root: str | Path | None = None,
    ) -> Self:
        profile = load_hover_starter_package()
        store = SystemStore.open_or_create(
            root,
            created_from_product_version=product_version,
            starter_seed_id=HOVER_STARTER_SEED_ID,
            starter_seed_hash=profile.manifest_hash,
            model_library_id=model_library_id,
            clock=clock,
        )
        try:
            return cls._compose(
                store,
                profile=profile,
                clock=clock,
                product_root=product_root,
            )
        except BaseException:
            store.close()
            raise

    @classmethod
    def _compose(
        cls,
        store: SystemStore,
        *,
        profile: LoadedModelProfile,
        clock: Clock,
        product_root: str | Path | None,
    ) -> Self:
        database = store.database
        content_migration = migrate_current_model_content(database, migrated_at=clock())
        audit = AuditRepository(database)
        idempotency = IdempotencyStore(database, audit, clock=clock)
        components = SqliteComponentLibraryRepository(database)
        seed_result = _seed_profile(database, components, profile, recorded_at=clock())
        source_catalog = _source_catalog_from_repository(components)

        operator_registry = OperatorRegistry()
        register_builtin_operators(operator_registry)
        register_extension_operators(operator_registry)
        source_provenance = BackendSourceProvenance.capture(
            operator_registry,
            product_root=product_root,
        )
        source_provider_registry = RuntimeSourceProviderRegistry()
        register_hover_source_providers(source_provider_registry)
        drafts = SqliteSchemeDraftRepository(database, clock=clock)
        unit_of_work = SqliteWorkspaceUnitOfWork(database, components, drafts)
        service_clock = _ServiceClock(clock)
        ids = UuidComponentIdFactory()
        model_library = ModelLibraryService(components, clock=service_clock, ids=ids)
        schemes = SchemeWorkspaceService(
            components,
            drafts,
            unit_of_work,
            source_catalog=source_catalog,
            operator_registry=operator_registry,
            clock=service_clock,
            ids=ids,
        )
        current_model = CurrentModelWorkspaceService(
            SqliteModelWorkspaceRepository(database),
            model_library_id=store.descriptor.model_library_id,
            operator_registry=operator_registry,
            source_catalog=source_catalog,
            clock=clock,
        )
        current_seed_result = seed_current_starter(
            profile,
            current_model,
            recorded_at=clock(),
            seed_id=CURRENT_HOVER_STARTER_SEED_ID,
        )
        model_edits = ModelEditSessionManager(
            model_root=store.root,
            model_library_id=store.descriptor.model_library_id,
            canonical_database=database,
            canonical_workspace=current_model,
            canonical_idempotency=idempotency,
            operator_registry=operator_registry,
            source_catalog=source_catalog,
            canonical_content_migration=content_migration,
            clock=clock,
        )
        legacy_model_importer = LegacyProjectModelImporter(
            database,
            current_model,
            model_edits,
            clock=clock,
        )
        return cls(
            store=store,
            components=components,
            drafts=drafts,
            unit_of_work=unit_of_work,
            model_library=model_library,
            schemes=schemes,
            current_model=current_model,
            model_edits=model_edits,
            legacy_model_importer=legacy_model_importer,
            operator_registry=operator_registry,
            source_provenance=source_provenance,
            source_provider_registry=source_provider_registry,
            source_catalog=source_catalog,
            audit=audit,
            idempotency=idempotency,
            starter_scheme_id=profile.scheme.scheme_version_id,
            current_starter_scheme_id=current_seed_result.scheme_id,
            seed_result=seed_result,
            current_seed_result=current_seed_result,
            _starter_profile=profile,
            _clock=clock,
        )

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def model_library_id(self) -> str:
        return self.store.descriptor.model_library_id

    @property
    def editable_model(self) -> CurrentModelWorkspaceService:
        if self._closed:
            raise RuntimeCompositionError("system application is closed")
        return self.model_edits.workspace

    def initialize_starter(self) -> StarterSeedResult:
        if self._closed:
            raise RuntimeCompositionError("system application is closed")
        result = _seed_profile(
            self.store.database,
            self.components,
            self._starter_profile,
            recorded_at=self._clock(),
        )
        current_result = seed_current_starter(
            self._starter_profile,
            self.current_model,
            recorded_at=self._clock(),
            seed_id=CURRENT_HOVER_STARTER_SEED_ID,
        )
        self.seed_result = result
        self.current_seed_result = current_result
        self.current_starter_scheme_id = current_result.scheme_id
        return result

    def close(self) -> None:
        if self._closed:
            return
        self.model_edits.close()
        self.store.close()
        self._closed = True

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _seed_profile(
    database: ProjectDatabase,
    components: SqliteComponentLibraryRepository,
    profile: LoadedModelProfile,
    *,
    recorded_at: datetime,
) -> StarterSeedResult:
    inserted = 0
    applied = False
    with database.transaction() as connection:
        marker = connection.execute(
            "SELECT seed_hash FROM project_seed_markers WHERE seed_id = ?",
            (HOVER_STARTER_SEED_ID,),
        ).fetchone()
        if marker is not None:
            if marker["seed_hash"] != profile.manifest_hash:
                raise StarterSeedError("Hover starter seed marker hash does not match the package")
        else:
            for item in profile.library_items:
                kind = component_kind(item)
                record_id = component_record_id(item)
                exists = connection.execute(
                    "SELECT 1 FROM library_records WHERE kind = ? AND record_id = ?",
                    (kind.value, record_id),
                ).fetchone()
                if exists is None:
                    components.add_in_transaction(connection, item, recorded_at=recorded_at)
                    inserted += 1
                elif components.get_exact(kind, record_id) != item:
                    raise StarterSeedError(
                        f"existing starter identity conflicts with {kind.value}:{record_id}"
                    )
            connection.execute(
                """
                INSERT INTO project_seed_markers(seed_id, seed_hash, applied_at)
                VALUES (?, ?, ?)
                """,
                (HOVER_STARTER_SEED_ID, profile.manifest_hash, _utc_text(recorded_at)),
            )
            applied = True

    for item in profile.library_items:
        kind = component_kind(item)
        record_id = component_record_id(item)
        if components.get_exact(kind, record_id) != item:
            raise StarterSeedError(
                f"persisted starter record does not match {kind.value}:{record_id}"
            )
    return StarterSeedResult(
        seed_id=HOVER_STARTER_SEED_ID,
        manifest_hash=profile.manifest_hash,
        applied=applied,
        inserted_records=inserted,
        total_records=len(profile.library_items),
    )


def _source_catalog_from_repository(
    components: SqliteComponentLibraryRepository,
) -> SourceCatalog:
    records = components.list_records(LibraryQuery(kind=ComponentKind.SOURCE_DESCRIPTOR))
    descriptors = tuple(
        record.item for record in records if isinstance(record.item, SourceDescriptor)
    )
    if len(descriptors) != len(records):
        raise RuntimeCompositionError("source-descriptor query returned another component kind")
    return SourceCatalog(descriptors)


__all__ = [
    "CURRENT_HOVER_STARTER_SEED_ID",
    "HOVER_STARTER_SEED_ID",
    "CurrentStarterSeedResult",
    "RuntimeCompositionError",
    "StarterSeedError",
    "StarterSeedResult",
    "SystemApplication",
    "UuidComponentIdFactory",
]
