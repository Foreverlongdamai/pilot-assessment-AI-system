"""Durable exact run snapshots, lifecycle transitions, and progress events."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime

from pydantic import JsonValue, ValidationError

from pilot_assessment.contracts.run import (
    AssessmentRun,
    RunEvent,
    RunSnapshot,
    RunStage,
    RunState,
)
from pilot_assessment.model_library.identity import typed_content_sha256
from pilot_assessment.persistence.database import (
    ProjectDatabase,
    decode_canonical_json,
    encode_canonical_json,
)

_TERMINAL_STATES = frozenset(
    {
        RunState.CANCELLED,
        RunState.COMPLETED,
        RunState.FAILED,
        RunState.INTERRUPTED,
    }
)
_STAGE_ORDER = {
    RunStage.QUEUED: 0,
    RunStage.SNAPSHOT_VALIDATION: 1,
    RunStage.INGESTION: 2,
    RunStage.SYNCHRONIZATION: 3,
    RunStage.EVIDENCE: 4,
    RunStage.INFERENCE: 5,
    RunStage.REPORTING: 6,
    RunStage.COMPLETED: 7,
}


class RunRepositoryError(RuntimeError):
    """Base class for deterministic run persistence failures."""


class RunNotFoundError(RunRepositoryError):
    """Raised when an exact run ID is absent."""


class RunAlreadyExistsError(RunRepositoryError):
    """Raised rather than replacing an existing run snapshot."""


class RunIntegrityError(RunRepositoryError):
    """Raised when stored run or event content disagrees with indexed state."""


class RunTransitionError(RunRepositoryError):
    """Raised when a requested run state or stage transition is illegal."""


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise RunRepositoryError("run timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def run_snapshot_hash(snapshot: RunSnapshot) -> str:
    """Hash only the portable frozen snapshot fields, excluding its hash claim."""

    payload = snapshot.model_dump(mode="json")
    payload.pop("snapshot_hash")
    return typed_content_sha256(snapshot.contract_id, snapshot.contract_version, payload)


class RunRepository:
    """Project-scoped run storage with monotonic durable event sequences."""

    def __init__(self, database: ProjectDatabase) -> None:
        self.database = database

    def create(
        self,
        snapshot: RunSnapshot,
        *,
        preflight_id: str,
        requested_at: datetime,
    ) -> AssessmentRun:
        if run_snapshot_hash(snapshot) != snapshot.snapshot_hash:
            raise RunIntegrityError("run snapshot hash does not match its canonical content")
        run = AssessmentRun(
            run_id=snapshot.run_id,
            snapshot=snapshot,
            state=RunState.QUEUED,
            stage=RunStage.QUEUED,
            progress_sequence=0,
            requested_at=requested_at,
            started_at=None,
            finished_at=None,
            cancellation_requested_at=None,
        )
        try:
            with self.database.transaction() as connection:
                preflight = connection.execute(
                    "SELECT preflight_hash FROM run_preflights WHERE preflight_id = ?",
                    (preflight_id,),
                ).fetchone()
                if preflight is None:
                    raise RunIntegrityError(f"run preflight {preflight_id!r} does not exist")
                if preflight["preflight_hash"] != snapshot.preflight_hash:
                    raise RunIntegrityError(
                        "run snapshot preflight hash does not match the persisted preflight"
                    )
                connection.execute(
                    """
                    INSERT INTO runs(
                        run_id, preflight_id, snapshot_hash, snapshot_json,
                        state, stage, progress_sequence, requested_at,
                        started_at, finished_at, cancellation_requested_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, NULL, NULL, NULL)
                    """,
                    (
                        run.run_id,
                        preflight_id,
                        snapshot.snapshot_hash,
                        encode_canonical_json(snapshot.model_dump(mode="json")),
                        run.state.value,
                        run.stage.value,
                        _utc_text(requested_at),
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise RunAlreadyExistsError(
                f"run or snapshot {snapshot.run_id!r} already exists"
            ) from error
        return run

    def get(self, run_id: str) -> AssessmentRun:
        row = self.database.fetchone("SELECT * FROM runs WHERE run_id = ?", (run_id,))
        if row is None:
            raise RunNotFoundError(run_id)
        return self._run_from_row(row)

    def list_runs(self) -> tuple[AssessmentRun, ...]:
        rows = self.database.fetchall("SELECT * FROM runs ORDER BY requested_at, rowid")
        return tuple(self._run_from_row(row) for row in rows)

    def list_events(
        self,
        run_id: str,
        *,
        after_sequence: int = 0,
    ) -> tuple[RunEvent, ...]:
        if type(after_sequence) is not int or after_sequence < 0:
            raise RunRepositoryError("after_sequence must be a non-negative strict integer")
        self.get(run_id)
        rows = self.database.fetchall(
            """
            SELECT * FROM run_events
            WHERE run_id = ? AND sequence > ? ORDER BY sequence
            """,
            (run_id, after_sequence),
        )
        return tuple(self._event_from_row(row) for row in rows)

    def start(
        self,
        run_id: str,
        *,
        total_units: int,
        occurred_at: datetime,
    ) -> AssessmentRun:
        return self._apply(
            run_id,
            allowed_states=(RunState.QUEUED,),
            target_state=RunState.RUNNING,
            target_stage=RunStage.SNAPSHOT_VALIDATION,
            completed_units=0,
            total_units=total_units,
            message="Run started",
            occurred_at=occurred_at,
            set_started=True,
        )

    def advance(
        self,
        run_id: str,
        *,
        stage: RunStage,
        completed_units: int,
        total_units: int,
        message: str,
        occurred_at: datetime,
        details: Mapping[str, JsonValue] | None = None,
    ) -> AssessmentRun:
        if stage in {RunStage.QUEUED, RunStage.COMPLETED}:
            raise RunTransitionError("running progress requires a non-terminal execution stage")
        return self._apply(
            run_id,
            allowed_states=(RunState.RUNNING, RunState.CANCELLING),
            target_state=None,
            target_stage=stage,
            completed_units=completed_units,
            total_units=total_units,
            message=message,
            occurred_at=occurred_at,
            details=details,
        )

    def request_cancel(self, run_id: str, *, occurred_at: datetime) -> AssessmentRun:
        current = self.get(run_id)
        if current.state in _TERMINAL_STATES or current.state is RunState.CANCELLING:
            return current
        completed_units, total_units = self._last_progress(current)
        return self._apply(
            run_id,
            allowed_states=(RunState.RUNNING,),
            target_state=RunState.CANCELLING,
            target_stage=None,
            completed_units=completed_units,
            total_units=total_units,
            message="Cancellation requested",
            occurred_at=occurred_at,
            set_cancel=True,
        )

    def complete(
        self,
        run_id: str,
        *,
        total_units: int,
        message: str,
        occurred_at: datetime,
    ) -> AssessmentRun:
        return self._apply(
            run_id,
            allowed_states=(RunState.RUNNING, RunState.CANCELLING),
            target_state=RunState.COMPLETED,
            target_stage=RunStage.COMPLETED,
            completed_units=total_units,
            total_units=total_units,
            message=message,
            occurred_at=occurred_at,
            set_finished=True,
        )

    def fail(
        self,
        run_id: str,
        *,
        message: str,
        occurred_at: datetime,
        details: Mapping[str, JsonValue] | None = None,
    ) -> AssessmentRun:
        current = self.get(run_id)
        completed_units, total_units = self._last_progress(current)
        return self._apply(
            run_id,
            allowed_states=(RunState.RUNNING, RunState.CANCELLING),
            target_state=RunState.FAILED,
            target_stage=None,
            completed_units=completed_units,
            total_units=total_units,
            message=message,
            occurred_at=occurred_at,
            details=details,
            set_finished=True,
        )

    def cancel(
        self,
        run_id: str,
        *,
        message: str,
        occurred_at: datetime,
    ) -> AssessmentRun:
        current = self.get(run_id)
        completed_units, total_units = self._last_progress(current)
        return self._apply(
            run_id,
            allowed_states=(RunState.CANCELLING,),
            target_state=RunState.CANCELLED,
            target_stage=None,
            completed_units=completed_units,
            total_units=total_units,
            message=message,
            occurred_at=occurred_at,
            set_finished=True,
        )

    def interrupt(self, run_id: str, *, occurred_at: datetime) -> AssessmentRun:
        current = self.get(run_id)
        completed_units, total_units = self._last_progress(current)
        return self._apply(
            run_id,
            allowed_states=(RunState.RUNNING, RunState.CANCELLING),
            target_state=RunState.INTERRUPTED,
            target_stage=None,
            completed_units=completed_units,
            total_units=total_units,
            message="Run interrupted during runtime recovery",
            occurred_at=occurred_at,
            details={"reason": "previous_runtime_ended_before_terminal_state"},
            set_finished=True,
        )

    def recover_interrupted(self, *, occurred_at: datetime) -> tuple[AssessmentRun, ...]:
        rows = self.database.fetchall(
            """
            SELECT run_id FROM runs
            WHERE state IN (?, ?) ORDER BY requested_at, rowid
            """,
            (RunState.RUNNING.value, RunState.CANCELLING.value),
        )
        return tuple(self.interrupt(row["run_id"], occurred_at=occurred_at) for row in rows)

    def _last_progress(self, current: AssessmentRun) -> tuple[int, int]:
        if current.progress_sequence == 0:
            return (0, 0)
        events = self.list_events(
            current.run_id,
            after_sequence=current.progress_sequence - 1,
        )
        event = next(
            (item for item in events if item.sequence == current.progress_sequence),
            None,
        )
        if event is None:
            raise RunIntegrityError("run progress sequence has no matching durable event")
        return (event.completed_units, event.total_units)

    def _apply(
        self,
        run_id: str,
        *,
        allowed_states: tuple[RunState, ...],
        target_state: RunState | None,
        target_stage: RunStage | None,
        completed_units: int,
        total_units: int,
        message: str,
        occurred_at: datetime,
        details: Mapping[str, JsonValue] | None = None,
        set_started: bool = False,
        set_finished: bool = False,
        set_cancel: bool = False,
    ) -> AssessmentRun:
        occurred_text = _utc_text(occurred_at)
        with self.database.transaction() as connection:
            row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                raise RunNotFoundError(run_id)
            current = self._run_from_row(row)
            if current.state in _TERMINAL_STATES:
                raise RunTransitionError(f"terminal run {run_id!r} is immutable")
            if current.state not in allowed_states:
                raise RunTransitionError(
                    f"run state {current.state.value!r} is not allowed for this transition"
                )
            stage = current.stage if target_stage is None else target_stage
            if _STAGE_ORDER[stage] < _STAGE_ORDER[current.stage]:
                raise RunTransitionError("run stage cannot regress")
            state = current.state if target_state is None else target_state
            sequence = current.progress_sequence + 1
            started_at = occurred_at if set_started else current.started_at
            finished_at = occurred_at if set_finished else current.finished_at
            cancellation_at = occurred_at if set_cancel else current.cancellation_requested_at
            updated = AssessmentRun(
                run_id=current.run_id,
                snapshot=current.snapshot,
                state=state,
                stage=stage,
                progress_sequence=sequence,
                requested_at=current.requested_at,
                started_at=started_at,
                finished_at=finished_at,
                cancellation_requested_at=cancellation_at,
            )
            event = RunEvent(
                event_id=(
                    "run-event."
                    + hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:16]
                    + f".{sequence}"
                ),
                run_id=run_id,
                sequence=sequence,
                state=state,
                stage=stage,
                completed_units=completed_units,
                total_units=total_units,
                message=message,
                occurred_at=occurred_at,
                details=dict(details or {}),
            )
            connection.execute(
                """
                INSERT INTO run_events(run_id, sequence, event_id, event_json, occurred_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    sequence,
                    event.event_id,
                    encode_canonical_json(event.model_dump(mode="json")),
                    occurred_text,
                ),
            )
            connection.execute(
                """
                UPDATE runs SET
                    state = ?, stage = ?, progress_sequence = ?,
                    started_at = ?, finished_at = ?, cancellation_requested_at = ?
                WHERE run_id = ?
                """,
                (
                    state.value,
                    stage.value,
                    sequence,
                    None if started_at is None else _utc_text(started_at),
                    None if finished_at is None else _utc_text(finished_at),
                    None if cancellation_at is None else _utc_text(cancellation_at),
                    run_id,
                ),
            )
        return updated

    def _run_from_row(self, row: sqlite3.Row) -> AssessmentRun:
        try:
            snapshot = RunSnapshot.model_validate(decode_canonical_json(row["snapshot_json"]))
        except (ValueError, ValidationError) as error:
            raise RunIntegrityError("stored run snapshot JSON is invalid") from error
        preflight = self.database.fetchone(
            "SELECT preflight_hash FROM run_preflights WHERE preflight_id = ?",
            (row["preflight_id"],),
        )
        if (
            preflight is None
            or snapshot.run_id != row["run_id"]
            or snapshot.snapshot_hash != row["snapshot_hash"]
            or snapshot.preflight_hash != preflight["preflight_hash"]
            or run_snapshot_hash(snapshot) != snapshot.snapshot_hash
        ):
            raise RunIntegrityError("stored run snapshot identity columns disagree")
        try:
            return AssessmentRun(
                run_id=row["run_id"],
                snapshot=snapshot,
                state=row["state"],
                stage=row["stage"],
                progress_sequence=int(row["progress_sequence"]),
                requested_at=row["requested_at"],
                started_at=row["started_at"],
                finished_at=row["finished_at"],
                cancellation_requested_at=row["cancellation_requested_at"],
            )
        except ValidationError as error:
            raise RunIntegrityError("stored run lifecycle fields are invalid") from error

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> RunEvent:
        try:
            event = RunEvent.model_validate(decode_canonical_json(row["event_json"]))
        except (ValueError, ValidationError) as error:
            raise RunIntegrityError("stored run event JSON is invalid") from error
        if (
            event.run_id != row["run_id"]
            or event.sequence != int(row["sequence"])
            or event.event_id != row["event_id"]
        ):
            raise RunIntegrityError("stored run event identity columns disagree")
        return event


__all__ = [
    "RunAlreadyExistsError",
    "RunIntegrityError",
    "RunNotFoundError",
    "RunRepository",
    "RunRepositoryError",
    "RunTransitionError",
    "run_snapshot_hash",
]
