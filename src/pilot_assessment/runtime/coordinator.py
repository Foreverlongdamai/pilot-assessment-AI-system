"""Single-worker durable assessment scheduling and cooperative cancellation."""

from __future__ import annotations

import logging
from collections.abc import Callable
from queue import Queue
from threading import Event, RLock, Thread
from typing import Protocol

from pydantic import JsonValue

from pilot_assessment.contracts.model_components import ComponentKind
from pilot_assessment.contracts.run import (
    CurrentModelRunSnapshot,
    RunEvent,
    RunResultEnvelope,
    RunStage,
    RunState,
)
from pilot_assessment.persistence.database import Clock
from pilot_assessment.runtime.repository import (
    AssessmentRunRecord,
    RunRepository,
    RunSnapshotRecord,
)

_LOGGER = logging.getLogger(__name__)
_TERMINAL_STATES = frozenset(
    {
        RunState.CANCELLED,
        RunState.COMPLETED,
        RunState.FAILED,
        RunState.INTERRUPTED,
    }
)
_FIXED_STAGE_UNITS = 5

RunEventSink = Callable[[RunEvent], None]


class AssessmentRunExecutor(Protocol):
    """Minimal pipeline surface consumed by the scheduler."""

    def execute(
        self,
        snapshot: RunSnapshotRecord,
        *,
        cancellation: Callable[[], None],
        progress: Callable[[RunStage, int, int, str], None],
    ) -> RunResultEnvelope: ...


class RunCoordinatorError(RuntimeError):
    """Base class for project-scoped scheduling failures."""


class RunCoordinatorClosedError(RunCoordinatorError):
    """Raised when a new run is submitted after coordinator shutdown."""


class RunNotScheduledError(RunCoordinatorError):
    """Raised when waiting for a non-terminal run that was never enqueued."""


class RunCancelledError(RuntimeError):
    """Internal cooperative cancellation signal raised only at safe boundaries."""


def run_total_units(snapshot: RunSnapshotRecord) -> int:
    """Derive display progress total from the frozen dynamic execution closure."""

    execution = (
        snapshot.execution_snapshot if isinstance(snapshot, CurrentModelRunSnapshot) else snapshot
    )
    evidence_count = sum(
        reference.kind is ComponentKind.EVIDENCE_VERSION
        for reference in execution.locked_component_refs
    )
    return evidence_count + _FIXED_STAGE_UNITS


class _CancellationToken:
    def __init__(self) -> None:
        self._requested = Event()

    def request(self) -> None:
        self._requested.set()

    def raise_if_requested(self) -> None:
        if self._requested.is_set():
            raise RunCancelledError("run cancellation was requested")


class RunCoordinator:
    """Execute queued runs sequentially while keeping durable state authoritative."""

    def __init__(
        self,
        runs: RunRepository,
        executor: AssessmentRunExecutor,
        *,
        clock: Clock,
        notify: RunEventSink | None = None,
    ) -> None:
        self.runs = runs
        self.executor = executor
        self.clock = clock
        self.notify = notify
        self._queue: Queue[str | None] = Queue()
        self._lock = RLock()
        self._tokens: dict[str, _CancellationToken] = {}
        self._terminal_events: dict[str, Event] = {}
        self._scheduled: set[str] = set()
        self._accepting = True
        self._closed = False
        self._worker = Thread(
            target=self._work_loop,
            name="pilot-assessment-run-worker",
            daemon=True,
        )
        self._worker.start()

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    def enqueue(self, run_id: str) -> AssessmentRunRecord:
        """Schedule one already-persisted queued run exactly once."""

        with self._lock:
            if not self._accepting:
                raise RunCoordinatorClosedError("run coordinator is closed to new work")
            current = self.runs.get(run_id)
            if current.state in _TERMINAL_STATES or run_id in self._scheduled:
                return current
            if current.state is not RunState.QUEUED:
                raise RunCoordinatorError(
                    f"run {run_id!r} cannot be enqueued from {current.state.value!r}"
                )
            self._scheduled.add(run_id)
            self._tokens[run_id] = _CancellationToken()
            self._terminal_events[run_id] = Event()
            self._queue.put(run_id)
            return current

    def cancel(self, run_id: str) -> AssessmentRunRecord:
        """Persist a cancellation request and return the current durable state."""

        with self._lock:
            current = self.runs.get(run_id)
            if current.state in _TERMINAL_STATES:
                self._signal_terminal(run_id)
                return current
            cancelled_before_execution = current.state is RunState.QUEUED
            token = self._tokens.setdefault(run_id, _CancellationToken())
            done = self._terminal_events.setdefault(run_id, Event())
            token.request()
            if current.state is RunState.QUEUED:
                # Preserve the published queued -> running -> cancelling -> cancelled state graph.
                current = self._persist_and_notify(
                    self.runs.start(
                        run_id,
                        total_units=run_total_units(current.snapshot),
                        occurred_at=self.clock(),
                    )
                )
            if current.state is RunState.RUNNING:
                current = self._persist_and_notify(
                    self.runs.request_cancel(run_id, occurred_at=self.clock())
                )
            if current.state is RunState.CANCELLING and cancelled_before_execution:
                # A queued job cancelled before executor entry has no in-flight operator to await.
                current = self._persist_and_notify(
                    self.runs.cancel(
                        run_id,
                        message="Run cancelled before pipeline execution",
                        occurred_at=self.clock(),
                    )
                )
                done.set()
            return current

    def wait(self, run_id: str, *, timeout: float | None = None) -> AssessmentRunRecord:
        """Wait for one scheduled run to reach a durable terminal state."""

        with self._lock:
            current = self.runs.get(run_id)
            if current.state in _TERMINAL_STATES:
                return current
            done = self._terminal_events.get(run_id)
            if done is None:
                raise RunNotScheduledError(run_id)
        if not done.wait(timeout):
            raise TimeoutError(f"run {run_id!r} did not reach a terminal state in time")
        return self.runs.get(run_id)

    def close(self) -> None:
        """Stop accepting work, cooperatively cancel scheduled jobs, and join the worker."""

        with self._lock:
            if self._closed:
                return
            self._accepting = False
            for token in self._tokens.values():
                token.request()
            self._queue.put(None)
        self._worker.join()
        with self._lock:
            self._closed = True

    def _work_loop(self) -> None:
        while True:
            run_id = self._queue.get()
            try:
                if run_id is None:
                    return
                self._execute(run_id)
            finally:
                self._queue.task_done()

    def _execute(self, run_id: str) -> None:
        with self._lock:
            token = self._tokens[run_id]
            current = self.runs.get(run_id)
            if current.state in _TERMINAL_STATES:
                self._signal_terminal(run_id)
                return
            if current.state is not RunState.QUEUED:
                self._fail_if_active(
                    run_id,
                    RunCoordinatorError(
                        f"scheduled run entered unexpected state {current.state.value!r}"
                    ),
                )
                return
            current = self._persist_and_notify(
                self.runs.start(
                    run_id,
                    total_units=run_total_units(current.snapshot),
                    occurred_at=self.clock(),
                )
            )
            snapshot = current.snapshot

        try:
            token.raise_if_requested()
            self.executor.execute(
                snapshot,
                cancellation=token.raise_if_requested,
                progress=lambda stage, completed, total, message: self._record_progress(
                    run_id,
                    token,
                    stage,
                    completed,
                    total,
                    message,
                ),
            )
            with self._lock:
                current = self.runs.get(run_id)
                if current.state not in _TERMINAL_STATES:
                    self._persist_and_notify(
                        self.runs.complete(
                            run_id,
                            total_units=run_total_units(snapshot),
                            message="Run completed with a durable result",
                            occurred_at=self.clock(),
                        )
                    )
        except RunCancelledError:
            self._cancel_if_active(run_id)
        except BaseException as error:
            self._fail_if_active(run_id, error)
        finally:
            self._signal_terminal(run_id)

    def _record_progress(
        self,
        run_id: str,
        token: _CancellationToken,
        stage: RunStage,
        completed_units: int,
        total_units: int,
        message: str,
    ) -> None:
        if stage is not RunStage.REPORTING:
            token.raise_if_requested()
        with self._lock:
            current = self.runs.get(run_id)
            expected_total = run_total_units(current.snapshot)
            if total_units != expected_total:
                raise RunCoordinatorError(
                    "pipeline progress total differs from the frozen execution closure"
                )
            previous = self.runs.list_events(
                run_id,
                after_sequence=max(current.progress_sequence - 1, 0),
            )
            if previous and completed_units < previous[0].completed_units:
                raise RunCoordinatorError("pipeline completed units cannot regress")
            self._persist_and_notify(
                self.runs.advance(
                    run_id,
                    stage=stage,
                    completed_units=completed_units,
                    total_units=total_units,
                    message=message,
                    occurred_at=self.clock(),
                )
            )
        if stage is not RunStage.REPORTING:
            token.raise_if_requested()

    def _cancel_if_active(self, run_id: str) -> None:
        with self._lock:
            current = self.runs.get(run_id)
            if current.state is RunState.RUNNING:
                current = self._persist_and_notify(
                    self.runs.request_cancel(run_id, occurred_at=self.clock())
                )
            if current.state is RunState.CANCELLING:
                self._persist_and_notify(
                    self.runs.cancel(
                        run_id,
                        message="Run cancelled at a cooperative execution boundary",
                        occurred_at=self.clock(),
                    )
                )

    def _fail_if_active(self, run_id: str, error: BaseException) -> None:
        with self._lock:
            current = self.runs.get(run_id)
            if current.state in _TERMINAL_STATES:
                return
            error_code = getattr(error, "code", "runtime.unexpected_error")
            if type(error_code) is not str or not error_code:
                error_code = "runtime.unexpected_error"
            details: dict[str, JsonValue] = {
                "error_code": error_code,
                "error_type": type(error).__name__,
                "error_message": str(error)[:1000],
            }
            evidence_version_id = getattr(error, "evidence_version_id", None)
            if type(evidence_version_id) is str and evidence_version_id:
                details["evidence_version_id"] = evidence_version_id
            self._persist_and_notify(
                self.runs.fail(
                    run_id,
                    message=f"Run failed with {type(error).__name__}",
                    occurred_at=self.clock(),
                    details=details,
                )
            )

    def _persist_and_notify(self, updated: AssessmentRunRecord) -> AssessmentRunRecord:
        events = self.runs.list_events(
            updated.run_id,
            after_sequence=updated.progress_sequence - 1,
        )
        event = next(
            (item for item in events if item.sequence == updated.progress_sequence),
            None,
        )
        if event is None:
            raise RunCoordinatorError("persisted run transition has no matching durable event")
        if self.notify is not None:
            try:
                self.notify(event)
            except Exception:
                _LOGGER.exception("run event notification failed after durable persistence")
        return updated

    def _signal_terminal(self, run_id: str) -> None:
        with self._lock:
            current = self.runs.get(run_id)
            if current.state in _TERMINAL_STATES:
                self._terminal_events.setdefault(run_id, Event()).set()


__all__ = [
    "AssessmentRunExecutor",
    "RunCancelledError",
    "RunCoordinator",
    "RunCoordinatorClosedError",
    "RunCoordinatorError",
    "RunEventSink",
    "RunNotScheduledError",
    "run_total_units",
]
