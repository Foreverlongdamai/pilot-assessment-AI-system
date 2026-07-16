"""In-memory scheme draft history and atomic workspace publication boundary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from typing import Protocol

from pilot_assessment.contracts.assessment_scheme import SchemeDraft
from pilot_assessment.model_library.repository import (
    InMemoryComponentLibraryRepository,
    VersionLibraryItem,
)
from pilot_assessment.schemes.operations import OperationDiff

Clock = Callable[[], datetime]
FailureHook = Callable[[str], None]


class SchemeDraftRepositoryError(RuntimeError):
    """Base class for deterministic draft repository failures."""


class SchemeDraftNotFoundError(SchemeDraftRepositoryError):
    """Raised when an exact draft ID is absent."""


class SchemeDraftAlreadyExistsError(SchemeDraftRepositoryError):
    """Raised rather than overwriting another draft."""


class DraftRevisionConflictError(SchemeDraftRepositoryError):
    """Raised when a command was based on stale graph or layout state."""


class DraftHistoryBoundaryError(SchemeDraftRepositoryError):
    """Raised when undo or redo has no state in the requested direction."""


@dataclass(frozen=True, slots=True)
class SchemeDraftRecord:
    draft: SchemeDraft
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str
    last_diff: OperationDiff | None


@dataclass(frozen=True, slots=True)
class DraftHistoryEntry:
    diff: OperationDiff
    graph_changed: bool
    layout_changed: bool
    author_id: str
    recorded_at: datetime


@dataclass(slots=True)
class _Timeline:
    record: SchemeDraftRecord
    snapshots: list[SchemeDraft]
    transitions: list[DraftHistoryEntry]
    cursor: int


class SchemeDraftRepository(Protocol):
    def create(self, draft: SchemeDraft, *, author_id: str) -> SchemeDraftRecord: ...

    def get(self, draft_id: str) -> SchemeDraftRecord: ...

    def discard(self, draft_id: str) -> SchemeDraftRecord: ...

    def save(
        self,
        proposed: SchemeDraft,
        *,
        expected_graph_version: int | None,
        expected_layout_version: int | None,
        graph_changed: bool,
        layout_changed: bool,
        diff: OperationDiff,
        author_id: str,
    ) -> SchemeDraftRecord: ...

    def undo(
        self,
        draft_id: str,
        *,
        expected_graph_version: int,
        expected_layout_version: int,
        author_id: str,
    ) -> SchemeDraftRecord: ...

    def redo(
        self,
        draft_id: str,
        *,
        expected_graph_version: int,
        expected_layout_version: int,
        author_id: str,
    ) -> SchemeDraftRecord: ...


class WorkspaceUnitOfWork(Protocol):
    def publish_atomic(
        self,
        items: tuple[VersionLibraryItem, ...],
        *,
        recorded_at: datetime,
        draft_id: str,
        expected_graph_version: int,
        expected_layout_version: int,
        rebased_draft: SchemeDraft,
        author_id: str,
    ) -> SchemeDraftRecord: ...


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise SchemeDraftRepositoryError("repository clock must be timezone-aware")
    return value


def _author(value: str) -> str:
    if type(value) is not str or not value:
        raise SchemeDraftRepositoryError("author_id must be a non-empty string")
    return value


def _snapshot(draft: SchemeDraft) -> SchemeDraft:
    return SchemeDraft.model_validate(draft.model_dump(mode="json"))


def _check_expected(
    draft: SchemeDraft,
    *,
    expected_graph_version: int | None,
    expected_layout_version: int | None,
    require_graph: bool,
    require_layout: bool,
) -> None:
    for label, value in (
        ("expected_graph_version", expected_graph_version),
        ("expected_layout_version", expected_layout_version),
    ):
        if value is not None and (type(value) is not int or value < 0):
            raise DraftRevisionConflictError(f"{label} must be a non-negative strict integer")
    if require_graph and expected_graph_version is None:
        raise DraftRevisionConflictError("graph operation requires expected_graph_version")
    if require_layout and expected_layout_version is None:
        raise DraftRevisionConflictError("layout operation requires expected_layout_version")
    if expected_graph_version is not None and draft.graph_version != expected_graph_version:
        raise DraftRevisionConflictError(
            f"draft graph is at {draft.graph_version}, not {expected_graph_version}"
        )
    if expected_layout_version is not None and draft.layout_version != expected_layout_version:
        raise DraftRevisionConflictError(
            f"draft layout is at {draft.layout_version}, not {expected_layout_version}"
        )


class InMemorySchemeDraftRepository:
    """Autosaved canonical draft timelines with optimistic revisions and branching history."""

    def __init__(self, *, clock: Clock = _utc_now) -> None:
        self._clock = clock
        self._timelines: dict[str, _Timeline] = {}
        self._lock = RLock()

    def _now(self) -> datetime:
        return _aware(self._clock())

    def create(self, draft: SchemeDraft, *, author_id: str) -> SchemeDraftRecord:
        author = _author(author_id)
        snapshot = _snapshot(draft).model_copy(update={"history_cursor": 0})
        with self._lock:
            if snapshot.draft_id in self._timelines:
                raise SchemeDraftAlreadyExistsError(snapshot.draft_id)
            now = self._now()
            record = SchemeDraftRecord(
                draft=snapshot,
                created_at=now,
                updated_at=now,
                created_by=author,
                updated_by=author,
                last_diff=None,
            )
            self._timelines[snapshot.draft_id] = _Timeline(
                record=record,
                snapshots=[snapshot],
                transitions=[],
                cursor=0,
            )
            return record

    def get(self, draft_id: str) -> SchemeDraftRecord:
        with self._lock:
            try:
                return self._timelines[draft_id].record
            except KeyError as error:
                raise SchemeDraftNotFoundError(draft_id) from error

    def discard(self, draft_id: str) -> SchemeDraftRecord:
        with self._lock:
            try:
                timeline = self._timelines.pop(draft_id)
            except KeyError as error:
                raise SchemeDraftNotFoundError(draft_id) from error
            return timeline.record

    def save(
        self,
        proposed: SchemeDraft,
        *,
        expected_graph_version: int | None,
        expected_layout_version: int | None,
        graph_changed: bool,
        layout_changed: bool,
        diff: OperationDiff,
        author_id: str,
    ) -> SchemeDraftRecord:
        author = _author(author_id)
        if not graph_changed and not layout_changed:
            raise SchemeDraftRepositoryError("an operation must change graph or layout state")
        with self._lock:
            timeline = self._timelines.get(proposed.draft_id)
            if timeline is None:
                raise SchemeDraftNotFoundError(proposed.draft_id)
            current = timeline.record.draft
            _check_expected(
                current,
                expected_graph_version=expected_graph_version,
                expected_layout_version=expected_layout_version,
                require_graph=graph_changed,
                require_layout=layout_changed,
            )
            cursor = timeline.cursor + 1
            canonical = _snapshot(proposed).model_copy(
                update={
                    "graph_version": current.graph_version + int(graph_changed),
                    "layout_version": current.layout_version + int(layout_changed),
                    "history_cursor": cursor,
                }
            )
            timeline.snapshots = timeline.snapshots[: timeline.cursor + 1]
            timeline.transitions = timeline.transitions[: timeline.cursor]
            timeline.snapshots.append(canonical)
            entry = DraftHistoryEntry(
                diff=diff,
                graph_changed=graph_changed,
                layout_changed=layout_changed,
                author_id=author,
                recorded_at=self._now(),
            )
            timeline.transitions.append(entry)
            timeline.cursor = cursor
            timeline.record = SchemeDraftRecord(
                draft=canonical,
                created_at=timeline.record.created_at,
                updated_at=entry.recorded_at,
                created_by=timeline.record.created_by,
                updated_by=author,
                last_diff=diff,
            )
            return timeline.record

    def _travel(
        self,
        draft_id: str,
        *,
        direction: int,
        expected_graph_version: int,
        expected_layout_version: int,
        author_id: str,
    ) -> SchemeDraftRecord:
        author = _author(author_id)
        with self._lock:
            timeline = self._timelines.get(draft_id)
            if timeline is None:
                raise SchemeDraftNotFoundError(draft_id)
            current = timeline.record.draft
            _check_expected(
                current,
                expected_graph_version=expected_graph_version,
                expected_layout_version=expected_layout_version,
                require_graph=True,
                require_layout=True,
            )
            target_cursor = timeline.cursor + direction
            if target_cursor < 0 or target_cursor >= len(timeline.snapshots):
                label = "undo" if direction < 0 else "redo"
                raise DraftHistoryBoundaryError(f"draft has no {label} state")
            transition_index = timeline.cursor if direction > 0 else target_cursor
            transition = timeline.transitions[transition_index]
            target = timeline.snapshots[target_cursor]
            canonical = _snapshot(target).model_copy(
                update={
                    "graph_version": current.graph_version + int(transition.graph_changed),
                    "layout_version": current.layout_version + int(transition.layout_changed),
                    "history_cursor": target_cursor,
                }
            )
            timeline.cursor = target_cursor
            now = self._now()
            prefix = "undo" if direction < 0 else "redo"
            diff = OperationDiff(
                operation_type=f"{prefix}:{transition.diff.operation_type}",
                changed_paths=transition.diff.changed_paths,
                added_component_ids=transition.diff.removed_component_ids,
                removed_component_ids=transition.diff.added_component_ids,
            )
            timeline.record = SchemeDraftRecord(
                draft=canonical,
                created_at=timeline.record.created_at,
                updated_at=now,
                created_by=timeline.record.created_by,
                updated_by=author,
                last_diff=diff,
            )
            return timeline.record

    def undo(
        self,
        draft_id: str,
        *,
        expected_graph_version: int,
        expected_layout_version: int,
        author_id: str,
    ) -> SchemeDraftRecord:
        return self._travel(
            draft_id,
            direction=-1,
            expected_graph_version=expected_graph_version,
            expected_layout_version=expected_layout_version,
            author_id=author_id,
        )

    def redo(
        self,
        draft_id: str,
        *,
        expected_graph_version: int,
        expected_layout_version: int,
        author_id: str,
    ) -> SchemeDraftRecord:
        return self._travel(
            draft_id,
            direction=1,
            expected_graph_version=expected_graph_version,
            expected_layout_version=expected_layout_version,
            author_id=author_id,
        )

    def _replace_after_publication(
        self,
        draft: SchemeDraft,
        *,
        expected_graph_version: int,
        expected_layout_version: int,
        author_id: str,
    ) -> SchemeDraftRecord:
        author = _author(author_id)
        timeline = self._timelines.get(draft.draft_id)
        if timeline is None:
            raise SchemeDraftNotFoundError(draft.draft_id)
        _check_expected(
            timeline.record.draft,
            expected_graph_version=expected_graph_version,
            expected_layout_version=expected_layout_version,
            require_graph=True,
            require_layout=True,
        )
        canonical = _snapshot(draft).model_copy(update={"history_cursor": 0})
        now = self._now()
        diff = OperationDiff(operation_type="PublishScheme", changed_paths=("/",))
        record = SchemeDraftRecord(
            draft=canonical,
            created_at=timeline.record.created_at,
            updated_at=now,
            created_by=timeline.record.created_by,
            updated_by=author,
            last_diff=diff,
        )
        self._timelines[draft.draft_id] = _Timeline(
            record=record,
            snapshots=[canonical],
            transitions=[],
            cursor=0,
        )
        return record

    def clone(self) -> InMemorySchemeDraftRepository:
        cloned = InMemorySchemeDraftRepository(clock=self._clock)
        cloned._timelines = {
            draft_id: _Timeline(
                record=timeline.record,
                snapshots=list(timeline.snapshots),
                transitions=list(timeline.transitions),
                cursor=timeline.cursor,
            )
            for draft_id, timeline in self._timelines.items()
        }
        return cloned

    def replace_from(self, staged: InMemorySchemeDraftRepository) -> None:
        self._timelines = staged.clone()._timelines


class InMemoryWorkspaceUnitOfWork:
    """Stage component and draft maps, then swap both only after every step succeeds."""

    def __init__(
        self,
        components: InMemoryComponentLibraryRepository,
        drafts: InMemorySchemeDraftRepository,
        *,
        failure_hook: FailureHook | None = None,
    ) -> None:
        self._components = components
        self._drafts = drafts
        self._failure_hook = failure_hook
        self._lock = RLock()

    def publish_atomic(
        self,
        items: tuple[VersionLibraryItem, ...],
        *,
        recorded_at: datetime,
        draft_id: str,
        expected_graph_version: int,
        expected_layout_version: int,
        rebased_draft: SchemeDraft,
        author_id: str,
    ) -> SchemeDraftRecord:
        _aware(recorded_at)
        with self._lock:
            staged_components = self._components.clone()
            for item in items:
                staged_components.add(item, recorded_at=recorded_at)
            staged_drafts = self._drafts.clone()
            record = staged_drafts._replace_after_publication(
                rebased_draft,
                expected_graph_version=expected_graph_version,
                expected_layout_version=expected_layout_version,
                author_id=author_id,
            )
            if self._failure_hook is not None:
                self._failure_hook("before_commit")
            self._components.replace_from(staged_components)
            self._drafts.replace_from(staged_drafts)
            return record


__all__ = [
    "DraftHistoryBoundaryError",
    "DraftHistoryEntry",
    "DraftRevisionConflictError",
    "InMemorySchemeDraftRepository",
    "InMemoryWorkspaceUnitOfWork",
    "SchemeDraftAlreadyExistsError",
    "SchemeDraftNotFoundError",
    "SchemeDraftRecord",
    "SchemeDraftRepository",
    "SchemeDraftRepositoryError",
    "WorkspaceUnitOfWork",
]
