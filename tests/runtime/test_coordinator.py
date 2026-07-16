from __future__ import annotations

from datetime import UTC, datetime
from threading import Event, Lock

import pytest

from pilot_assessment.contracts.model_components import ComponentKind, PinnedComponentRef
from pilot_assessment.contracts.project import SessionRevisionRef
from pilot_assessment.contracts.run import (
    ExecutableIdentity,
    RunEvent,
    RunPurpose,
    RunSnapshot,
    RunStage,
    RunState,
)
from pilot_assessment.persistence.database import ProjectDatabase, encode_canonical_json
from pilot_assessment.runtime.coordinator import RunCoordinator, run_total_units
from pilot_assessment.runtime.pipeline import RunResultNotFoundError, RunResultRepository
from pilot_assessment.runtime.repository import RunRepository, run_snapshot_hash

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
ZERO_HASH = "0" * 64


def _identity(identity_id: str, digest: str = HASH_C) -> ExecutableIdentity:
    return ExecutableIdentity(identity_id=identity_id, version="0.1.0", content_hash=digest)


def _snapshot(run_id: str) -> RunSnapshot:
    provisional = RunSnapshot(
        run_id=run_id,
        purpose=RunPurpose.SOFTWARE_TEST,
        session_revision_ref=SessionRevisionRef(
            session_id="session.alpha",
            session_revision_id="revision.alpha",
            bundle_root_hash=HASH_A,
        ),
        scheme_ref=PinnedComponentRef(
            kind=ComponentKind.ASSESSMENT_SCHEME_VERSION,
            version_id="scheme.alpha",
            content_hash=HASH_B,
        ),
        locked_component_refs=(
            PinnedComponentRef(
                kind=ComponentKind.TASK_PROFILE_VERSION,
                version_id="task.alpha",
                content_hash=HASH_C,
            ),
            PinnedComponentRef(
                kind=ComponentKind.EVIDENCE_VERSION,
                version_id="evidence.alpha",
                content_hash=HASH_A,
            ),
        ),
        locked_source_refs=(
            PinnedComponentRef(
                kind=ComponentKind.SOURCE_DESCRIPTOR,
                version_id="source.X",
                content_hash=HASH_A,
            ),
        ),
        locked_operator_identities=(_identity("operator.mean"),),
        engine_identity=_identity("engine.bayesian", HASH_A),
        numeric_runtime_identities=(_identity("runtime.python", HASH_B),),
        runtime_parameters_hash=HASH_C,
        preflight_hash=HASH_B,
        snapshot_hash=ZERO_HASH,
    )
    return provisional.model_copy(update={"snapshot_hash": run_snapshot_hash(provisional)})


def _persist_preflight(database: ProjectDatabase) -> str:
    preflight_id = "preflight.alpha"
    database.execute(
        """
        INSERT INTO run_preflights(
            preflight_id, preflight_hash, report_json, created_at
        ) VALUES (?, ?, ?, ?)
        """,
        (
            preflight_id,
            HASH_B,
            encode_canonical_json({"test_fixture": True}),
            NOW.isoformat().replace("+00:00", "Z"),
        ),
    )
    return preflight_id


def _create_run(repository: RunRepository, preflight_id: str, run_id: str) -> RunSnapshot:
    snapshot = _snapshot(run_id)
    repository.create(snapshot, preflight_id=preflight_id, requested_at=NOW)
    return snapshot


class _RecordingPipeline:
    def __init__(self, *, fail_run_id: str | None = None) -> None:
        self.fail_run_id = fail_run_id
        self.calls: list[str] = []
        self.max_active = 0
        self._active = 0
        self._lock = Lock()

    def execute(self, snapshot, *, cancellation, progress):
        total = run_total_units(snapshot)
        with self._lock:
            self._active += 1
            self.max_active = max(self.max_active, self._active)
            self.calls.append(snapshot.run_id)
        try:
            progress(RunStage.SNAPSHOT_VALIDATION, 1, total, "Snapshot ready")
            cancellation()
            progress(RunStage.INGESTION, 2, total, "Managed input ready")
            cancellation()
            progress(RunStage.SYNCHRONIZATION, 3, total, "Aligned input ready")
            cancellation()
            progress(RunStage.EVIDENCE, 4, total, "Evidence ready")
            if snapshot.run_id == self.fail_run_id:
                raise ValueError("deliberate technical failure")
            cancellation()
            progress(RunStage.INFERENCE, 5, total, "Posterior ready")
            cancellation()
            progress(RunStage.REPORTING, 6, total, "Result ready")
            return object()
        finally:
            with self._lock:
                self._active -= 1


class _BlockingPipeline:
    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()
        self.calls: list[str] = []

    def execute(self, snapshot, *, cancellation, progress):
        total = run_total_units(snapshot)
        self.calls.append(snapshot.run_id)
        progress(RunStage.SNAPSHOT_VALIDATION, 1, total, "Snapshot ready")
        self.started.set()
        if not self.release.wait(5):
            raise TimeoutError("test did not release the fake operator")
        cancellation()
        return object()


def test_coordinator_runs_one_job_at_a_time_and_persists_before_notification(tmp_path) -> None:
    database = ProjectDatabase.connect(tmp_path / "project.sqlite3", clock=lambda: NOW)
    repository = RunRepository(database)
    preflight_id = _persist_preflight(database)
    first = _create_run(repository, preflight_id, "run.first")
    second = _create_run(repository, preflight_id, "run.second")
    failed = _create_run(repository, preflight_id, "run.failed")
    pipeline = _RecordingPipeline(fail_run_id=failed.run_id)
    notifications: list[RunEvent] = []
    durable_before_notify: list[bool] = []

    def notify(event: RunEvent) -> None:
        notifications.append(event)
        durable_before_notify.append(repository.list_events(event.run_id)[-1] == event)

    coordinator = RunCoordinator(repository, pipeline, clock=lambda: NOW, notify=notify)
    try:
        coordinator.enqueue(first.run_id)
        coordinator.enqueue(second.run_id)
        coordinator.enqueue(failed.run_id)

        assert coordinator.wait(first.run_id, timeout=5).state is RunState.COMPLETED
        assert coordinator.wait(second.run_id, timeout=5).state is RunState.COMPLETED
        failed_run = coordinator.wait(failed.run_id, timeout=5)

        assert failed_run.state is RunState.FAILED
        assert pipeline.calls == [first.run_id, second.run_id, failed.run_id]
        assert pipeline.max_active == 1
        assert notifications
        assert all(durable_before_notify)
        assert repository.list_events(first.run_id)[-1].state is RunState.COMPLETED
        assert repository.list_events(failed.run_id)[-1].details["error_code"] == (
            "runtime.unexpected_error"
        )
    finally:
        coordinator.close()
        database.close()


def test_running_and_queued_cancel_are_cooperative_durable_and_idempotent(tmp_path) -> None:
    database = ProjectDatabase.connect(tmp_path / "project.sqlite3", clock=lambda: NOW)
    repository = RunRepository(database)
    preflight_id = _persist_preflight(database)
    running = _create_run(repository, preflight_id, "run.running")
    queued = _create_run(repository, preflight_id, "run.queued")
    pipeline = _BlockingPipeline()
    coordinator = RunCoordinator(repository, pipeline, clock=lambda: NOW)
    try:
        coordinator.enqueue(running.run_id)
        assert pipeline.started.wait(5)
        coordinator.enqueue(queued.run_id)

        first_request = coordinator.cancel(running.run_id)
        second_request = coordinator.cancel(running.run_id)
        queued_cancelled = coordinator.cancel(queued.run_id)

        assert first_request.state is RunState.CANCELLING
        assert second_request == first_request
        assert queued_cancelled.state is RunState.CANCELLED
        assert len(repository.list_events(running.run_id)) == 3
        assert pipeline.calls == [running.run_id]

        pipeline.release.set()
        assert coordinator.wait(running.run_id, timeout=5).state is RunState.CANCELLED
        assert coordinator.wait(queued.run_id, timeout=5).state is RunState.CANCELLED
        assert pipeline.calls == [running.run_id]
    finally:
        pipeline.release.set()
        coordinator.close()
        database.close()


def test_reopen_marks_non_terminal_run_interrupted_without_fabricating_result(tmp_path) -> None:
    database_path = tmp_path / "project.sqlite3"
    database = ProjectDatabase.connect(database_path, clock=lambda: NOW)
    repository = RunRepository(database)
    preflight_id = _persist_preflight(database)
    snapshot = _create_run(repository, preflight_id, "run.interrupted")
    repository.start(
        snapshot.run_id,
        total_units=run_total_units(snapshot),
        occurred_at=NOW,
    )
    database.close()

    reopened = ProjectDatabase.connect(database_path, clock=lambda: NOW)
    reopened_runs = RunRepository(reopened)
    try:
        recovered = reopened_runs.recover_interrupted(occurred_at=NOW)
        assert tuple(run.run_id for run in recovered) == (snapshot.run_id,)
        assert recovered[0].state is RunState.INTERRUPTED
        with pytest.raises(RunResultNotFoundError):
            RunResultRepository(reopened).get_by_run(snapshot.run_id)
    finally:
        reopened.close()
