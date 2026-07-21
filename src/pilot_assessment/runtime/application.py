"""Composition root for one optional user project bound to the shared system model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Self

from pilot_assessment.evidence.registry import OperatorRegistry
from pilot_assessment.model_library.service import ModelLibraryService
from pilot_assessment.model_library.sources import SourceCatalog
from pilot_assessment.model_workspace.edit_session import ModelEditSessionManager
from pilot_assessment.model_workspace.execution import CurrentModelExecutionMaterializer
from pilot_assessment.model_workspace.legacy_import import LegacyModelImportResult
from pilot_assessment.model_workspace.service import CurrentModelWorkspaceService
from pilot_assessment.persistence.artifacts import ArtifactRecoveryReport, ManagedArtifactStore
from pilot_assessment.persistence.audit import AuditRepository
from pilot_assessment.persistence.database import Clock
from pilot_assessment.persistence.draft_repository import (
    SqliteSchemeDraftRepository,
    SqliteWorkspaceUnitOfWork,
)
from pilot_assessment.persistence.model_repository import SqliteComponentLibraryRepository
from pilot_assessment.persistence.project import ProjectStore
from pilot_assessment.persistence.sessions import SessionImportService, SessionRecoveryReport
from pilot_assessment.persistence.transactions import IdempotencyStore
from pilot_assessment.runtime.coordinator import RunCoordinator
from pilot_assessment.runtime.current_preflight import CurrentRunPreflightService
from pilot_assessment.runtime.pipeline import AssessmentPipeline, RunResultRepository
from pilot_assessment.runtime.preflight import RunPreflightService
from pilot_assessment.runtime.repository import AssessmentRunRecord, RunRepository
from pilot_assessment.runtime.sources import RuntimeSourceProviderRegistry
from pilot_assessment.runtime.system_application import (
    CURRENT_HOVER_STARTER_SEED_ID,
    HOVER_STARTER_SEED_ID,
    CurrentStarterSeedResult,
    RuntimeCompositionError,
    StarterSeedError,
    StarterSeedResult,
    SystemApplication,
    UuidComponentIdFactory,
)
from pilot_assessment.runtime.system_execution import SystemSchemeExecutionMaterializer
from pilot_assessment.schemes.service import SchemeWorkspaceService


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class ProjectApplication:
    """Session/run services for one project using one injected system model owner."""

    project: ProjectStore
    system: SystemApplication
    components: SqliteComponentLibraryRepository
    execution_materializer: CurrentModelExecutionMaterializer
    system_execution: SystemSchemeExecutionMaterializer
    artifacts: ManagedArtifactStore
    sessions: SessionImportService
    runs: RunRepository
    preflight: RunPreflightService
    current_preflight: CurrentRunPreflightService
    results: RunResultRepository
    pipeline: AssessmentPipeline
    coordinator: RunCoordinator
    audit: AuditRepository
    idempotency: IdempotencyStore
    artifact_recovery: ArtifactRecoveryReport
    session_recovery: SessionRecoveryReport
    run_recovery: tuple[AssessmentRunRecord, ...]
    legacy_model_import: LegacyModelImportResult
    _clock: Clock = field(repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    @classmethod
    def create(
        cls,
        root: str | Path,
        *,
        system: SystemApplication,
        project_id: str,
        name: str,
        created_at: datetime,
        clock: Clock = _utc_now,
    ) -> Self:
        cls._require_system(system)
        project = ProjectStore.create(
            root,
            project_id=project_id,
            name=name,
            created_at=created_at,
            clock=clock,
        )
        try:
            return cls._compose(project, system=system, clock=clock)
        except BaseException:
            project.close()
            raise

    @classmethod
    def open(
        cls,
        root: str | Path,
        *,
        system: SystemApplication,
        clock: Clock = _utc_now,
    ) -> Self:
        cls._require_system(system)
        project = ProjectStore.open(root, clock=clock)
        try:
            return cls._compose(project, system=system, clock=clock)
        except BaseException:
            project.close()
            raise

    @staticmethod
    def _require_system(system: SystemApplication) -> None:
        if system.closed:
            raise RuntimeCompositionError("project cannot bind a closed system application")

    @classmethod
    def _compose(
        cls,
        project: ProjectStore,
        *,
        system: SystemApplication,
        clock: Clock,
    ) -> Self:
        database = project.database
        legacy_model_import = system.legacy_model_importer.import_project(project)
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
        execution_materializer = CurrentModelExecutionMaterializer(
            database,
            components,
            system.current_model,
            clock=clock,
        )
        system_execution = SystemSchemeExecutionMaterializer(
            database,
            components,
            system.components,
            clock=clock,
        )
        runs = RunRepository(database)
        run_recovery = runs.recover_interrupted(occurred_at=clock())
        preflight = RunPreflightService(
            database,
            components,
            sessions,
            source_catalog=system.source_catalog,
            operator_registry=system.operator_registry,
            clock=clock,
            scheme_materializer=system_execution,
        )
        current_preflight = CurrentRunPreflightService(
            database,
            system.current_model,
            execution_materializer,
            preflight,
            runs,
            artifacts,
            system.source_provenance,
            clock=clock,
        )
        results = RunResultRepository(database)
        pipeline = AssessmentPipeline(
            components,
            artifacts,
            preflight,
            results,
            operator_registry=system.operator_registry,
            source_provider_registry=system.source_provider_registry,
        )
        coordinator = RunCoordinator(runs, pipeline, clock=clock)
        return cls(
            project=project,
            system=system,
            components=components,
            execution_materializer=execution_materializer,
            system_execution=system_execution,
            artifacts=artifacts,
            sessions=sessions,
            runs=runs,
            preflight=preflight,
            current_preflight=current_preflight,
            results=results,
            pipeline=pipeline,
            coordinator=coordinator,
            audit=audit,
            idempotency=idempotency,
            artifact_recovery=artifact_recovery,
            session_recovery=session_recovery,
            run_recovery=run_recovery,
            legacy_model_import=legacy_model_import,
            _clock=clock,
        )

    @property
    def closed(self) -> bool:
        return self._closed

    # Transitional read-only service aliases keep project callers source-compatible while
    # ownership is unambiguously held and closed by SystemApplication.
    @property
    def current_model(self) -> CurrentModelWorkspaceService:
        return self.system.current_model

    @property
    def editable_model(self) -> CurrentModelWorkspaceService:
        return self.system.editable_model

    @property
    def model_edits(self) -> ModelEditSessionManager:
        return self.system.model_edits

    @property
    def model_library(self) -> ModelLibraryService:
        return self.system.model_library

    @property
    def drafts(self) -> SqliteSchemeDraftRepository:
        return self.system.drafts

    @property
    def unit_of_work(self) -> SqliteWorkspaceUnitOfWork:
        return self.system.unit_of_work

    @property
    def schemes(self) -> SchemeWorkspaceService:
        return self.system.schemes

    @property
    def operator_registry(self) -> OperatorRegistry:
        return self.system.operator_registry

    @property
    def source_provider_registry(self) -> RuntimeSourceProviderRegistry:
        return self.system.source_provider_registry

    @property
    def source_catalog(self) -> SourceCatalog:
        return self.system.source_catalog

    @property
    def starter_scheme_id(self) -> str:
        return self.system.starter_scheme_id

    @property
    def current_starter_scheme_id(self) -> str:
        return self.system.current_starter_scheme_id

    @property
    def seed_result(self) -> StarterSeedResult:
        return self.system.seed_result

    @property
    def current_seed_result(self) -> CurrentStarterSeedResult:
        return self.system.current_seed_result

    def close(self) -> None:
        if self._closed:
            return
        self.coordinator.close()
        self.project.close()
        self._closed = True

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


__all__ = [
    "CURRENT_HOVER_STARTER_SEED_ID",
    "HOVER_STARTER_SEED_ID",
    "CurrentStarterSeedResult",
    "ProjectApplication",
    "RuntimeCompositionError",
    "StarterSeedError",
    "StarterSeedResult",
    "SystemApplication",
    "UuidComponentIdFactory",
]
