from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pilot_assessment.contracts.model_components import ComponentKind, PinnedComponentRef
from pilot_assessment.contracts.project import SessionRevisionRef
from pilot_assessment.contracts.run import (
    ExecutableIdentity,
    RunPurpose,
    RunSnapshot,
    RunStage,
    RunState,
)
from pilot_assessment.persistence.database import ProjectDatabase, encode_canonical_json
from pilot_assessment.runtime.repository import (
    RunRepository,
    RunTransitionError,
    run_snapshot_hash,
)

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


def test_run_repository_enforces_transitions_terminal_immutability_and_event_order(
    tmp_path,
) -> None:
    database = ProjectDatabase.connect(tmp_path / "project.sqlite3", clock=lambda: NOW)
    repository = RunRepository(database)
    try:
        preflight_id = _persist_preflight(database)
        created = repository.create(
            _snapshot("run.alpha"), preflight_id=preflight_id, requested_at=NOW
        )
        assert created.state is RunState.QUEUED
        assert created.progress_sequence == 0
        with pytest.raises(RunTransitionError, match="queued"):
            repository.advance(
                "run.alpha",
                stage=RunStage.INGESTION,
                completed_units=1,
                total_units=3,
                message="illegal",
                occurred_at=NOW,
            )

        running = repository.start(
            "run.alpha",
            total_units=3,
            occurred_at=NOW + timedelta(seconds=1),
        )
        assert running.state is RunState.RUNNING
        repository.advance(
            "run.alpha",
            stage=RunStage.INGESTION,
            completed_units=1,
            total_units=3,
            message="Ingestion ready",
            occurred_at=NOW + timedelta(seconds=2),
        )
        with pytest.raises(RunTransitionError, match="regress"):
            repository.advance(
                "run.alpha",
                stage=RunStage.SNAPSHOT_VALIDATION,
                completed_units=1,
                total_units=3,
                message="regression",
                occurred_at=NOW + timedelta(seconds=3),
            )
        completed = repository.complete(
            "run.alpha",
            total_units=3,
            message="Completed",
            occurred_at=NOW + timedelta(seconds=4),
        )

        assert completed.state is RunState.COMPLETED
        assert completed.progress_sequence == 3
        events = repository.list_events("run.alpha")
        assert tuple(event.sequence for event in events) == (1, 2, 3)
        assert tuple(event.state for event in events) == (
            RunState.RUNNING,
            RunState.RUNNING,
            RunState.COMPLETED,
        )
        with pytest.raises(RunTransitionError, match="terminal"):
            repository.advance(
                "run.alpha",
                stage=RunStage.REPORTING,
                completed_units=3,
                total_units=3,
                message="late",
                occurred_at=NOW + timedelta(seconds=5),
            )
        assert (
            repository.request_cancel("run.alpha", occurred_at=NOW + timedelta(seconds=5))
            == completed
        )
        assert len(repository.list_events("run.alpha")) == 3
    finally:
        database.close()


def test_recovery_interrupts_only_running_and_cancelling_runs(tmp_path) -> None:
    database = ProjectDatabase.connect(tmp_path / "project.sqlite3", clock=lambda: NOW)
    repository = RunRepository(database)
    try:
        preflight_id = _persist_preflight(database)
        for run_id in ("run.running", "run.cancelling", "run.queued"):
            repository.create(_snapshot(run_id), preflight_id=preflight_id, requested_at=NOW)
        repository.start("run.running", total_units=2, occurred_at=NOW)
        repository.start("run.cancelling", total_units=2, occurred_at=NOW)
        repository.request_cancel("run.cancelling", occurred_at=NOW + timedelta(seconds=1))

        recovered = repository.recover_interrupted(occurred_at=NOW + timedelta(seconds=2))

        assert {run.run_id for run in recovered} == {"run.running", "run.cancelling"}
        assert all(run.state is RunState.INTERRUPTED for run in recovered)
        assert repository.get("run.queued").state is RunState.QUEUED
        assert repository.list_events("run.running")[-1].state is RunState.INTERRUPTED
        assert repository.list_events("run.cancelling")[-1].state is RunState.INTERRUPTED
    finally:
        database.close()
