"""Single composition root for one open, portable assessment project."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Self
from uuid import uuid4

from pilot_assessment.contracts.model_components import (
    ComponentKind,
    SourceDescriptor,
)
from pilot_assessment.contracts.run import AssessmentRun
from pilot_assessment.evidence.builtins import register_builtin_operators
from pilot_assessment.evidence.registry import OperatorRegistry
from pilot_assessment.model_library.profile import (
    LoadedModelProfile,
    load_hover_starter_package,
)
from pilot_assessment.model_library.repository import (
    LibraryQuery,
    component_kind,
    component_record_id,
)
from pilot_assessment.model_library.service import ModelLibraryService
from pilot_assessment.model_library.sources import SourceCatalog
from pilot_assessment.persistence.artifacts import (
    ArtifactRecoveryReport,
    ManagedArtifactStore,
)
from pilot_assessment.persistence.audit import AuditRepository
from pilot_assessment.persistence.database import Clock, ProjectDatabase
from pilot_assessment.persistence.draft_repository import (
    SqliteSchemeDraftRepository,
    SqliteWorkspaceUnitOfWork,
)
from pilot_assessment.persistence.model_repository import SqliteComponentLibraryRepository
from pilot_assessment.persistence.project import ProjectStore
from pilot_assessment.persistence.sessions import (
    SessionImportService,
    SessionRecoveryReport,
)
from pilot_assessment.persistence.transactions import IdempotencyStore
from pilot_assessment.runtime.pipeline import AssessmentPipeline, RunResultRepository
from pilot_assessment.runtime.preflight import RunPreflightService
from pilot_assessment.runtime.repository import RunRepository
from pilot_assessment.runtime.sources import (
    RuntimeSourceProviderRegistry,
    register_hover_source_providers,
)
from pilot_assessment.schemes.service import SchemeWorkspaceService

HOVER_STARTER_SEED_ID = "starter.hover.package.0.1.0"


class RuntimeCompositionError(RuntimeError):
    """Raised when one application graph cannot share a coherent project boundary."""


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
    """Generate opaque new component IDs without task- or node-specific branching."""

    def new_id(self, kind: ComponentKind) -> str:
        return f"{kind.value}.{uuid4().hex}"


@dataclass(slots=True)
class ProjectApplication:
    """All durable domain services for the single currently open project."""

    project: ProjectStore
    components: SqliteComponentLibraryRepository
    drafts: SqliteSchemeDraftRepository
    unit_of_work: SqliteWorkspaceUnitOfWork
    model_library: ModelLibraryService
    schemes: SchemeWorkspaceService
    operator_registry: OperatorRegistry
    source_provider_registry: RuntimeSourceProviderRegistry
    source_catalog: SourceCatalog
    artifacts: ManagedArtifactStore
    sessions: SessionImportService
    runs: RunRepository
    preflight: RunPreflightService
    results: RunResultRepository
    pipeline: AssessmentPipeline
    audit: AuditRepository
    idempotency: IdempotencyStore
    starter_scheme_id: str
    seed_result: StarterSeedResult
    artifact_recovery: ArtifactRecoveryReport
    session_recovery: SessionRecoveryReport
    run_recovery: tuple[AssessmentRun, ...]
    _starter_profile: LoadedModelProfile = field(repr=False)
    _clock: Clock = field(repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    @classmethod
    def create(
        cls,
        root: str | Path,
        *,
        project_id: str,
        name: str,
        created_at: datetime,
        clock: Clock = _utc_now,
    ) -> Self:
        project = ProjectStore.create(
            root,
            project_id=project_id,
            name=name,
            created_at=created_at,
            clock=clock,
        )
        try:
            return cls._compose(project, clock=clock)
        except BaseException:
            project.close()
            raise

    @classmethod
    def open(
        cls,
        root: str | Path,
        *,
        clock: Clock = _utc_now,
    ) -> Self:
        project = ProjectStore.open(root, clock=clock)
        try:
            return cls._compose(project, clock=clock)
        except BaseException:
            project.close()
            raise

    @classmethod
    def _compose(cls, project: ProjectStore, *, clock: Clock) -> Self:
        database = project.database
        artifacts = ManagedArtifactStore(project.root, database, clock=clock)
        audit = AuditRepository(database)
        idempotency = IdempotencyStore(database, audit, clock=clock)
        sessions = SessionImportService(
            project.root,
            database,
            project_id=project.descriptor.project_id,
            artifact_store=artifacts,
            idempotency=idempotency,
            clock=clock,
        )
        artifact_recovery = artifacts.recover()
        session_recovery = sessions.recover()

        components = SqliteComponentLibraryRepository(database)
        profile = load_hover_starter_package()
        seed_result = _seed_profile(
            database,
            components,
            profile,
            recorded_at=clock(),
        )
        source_catalog = _source_catalog_from_repository(components)
        operator_registry = OperatorRegistry()
        register_builtin_operators(operator_registry)
        source_provider_registry = RuntimeSourceProviderRegistry()
        register_hover_source_providers(source_provider_registry)
        drafts = SqliteSchemeDraftRepository(database, clock=clock)
        unit_of_work = SqliteWorkspaceUnitOfWork(
            database,
            components,
            drafts,
        )
        service_clock = _ServiceClock(clock)
        ids = UuidComponentIdFactory()
        model_library = ModelLibraryService(
            components,
            clock=service_clock,
            ids=ids,
        )
        schemes = SchemeWorkspaceService(
            components,
            drafts,
            unit_of_work,
            source_catalog=source_catalog,
            operator_registry=operator_registry,
            clock=service_clock,
            ids=ids,
        )
        runs = RunRepository(database)
        run_recovery = runs.recover_interrupted(occurred_at=clock())
        preflight = RunPreflightService(
            database,
            components,
            sessions,
            source_catalog=source_catalog,
            operator_registry=operator_registry,
            clock=clock,
        )
        results = RunResultRepository(database)
        pipeline = AssessmentPipeline(
            components,
            artifacts,
            preflight,
            results,
            operator_registry=operator_registry,
            source_provider_registry=source_provider_registry,
        )
        return cls(
            project=project,
            components=components,
            drafts=drafts,
            unit_of_work=unit_of_work,
            model_library=model_library,
            schemes=schemes,
            operator_registry=operator_registry,
            source_provider_registry=source_provider_registry,
            source_catalog=source_catalog,
            artifacts=artifacts,
            sessions=sessions,
            runs=runs,
            preflight=preflight,
            results=results,
            pipeline=pipeline,
            audit=audit,
            idempotency=idempotency,
            starter_scheme_id=profile.scheme.scheme_version_id,
            seed_result=seed_result,
            artifact_recovery=artifact_recovery,
            session_recovery=session_recovery,
            run_recovery=run_recovery,
            _starter_profile=profile,
            _clock=clock,
        )

    @property
    def closed(self) -> bool:
        return self._closed

    def initialize_starter(self) -> StarterSeedResult:
        """Idempotently verify or install the ordinary editable starter records."""

        if self._closed:
            raise RuntimeCompositionError("project application is closed")
        result = _seed_profile(
            self.project.database,
            self.components,
            self._starter_profile,
            recorded_at=self._clock(),
        )
        self.seed_result = result
        return result

    def close(self) -> None:
        if self._closed:
            return
        self.project.close()
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
                    components.add_in_transaction(
                        connection,
                        item,
                        recorded_at=recorded_at,
                    )
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
                (
                    HOVER_STARTER_SEED_ID,
                    profile.manifest_hash,
                    _utc_text(recorded_at),
                ),
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
    "HOVER_STARTER_SEED_ID",
    "ProjectApplication",
    "RuntimeCompositionError",
    "StarterSeedError",
    "StarterSeedResult",
    "UuidComponentIdFactory",
]
