"""Recipe draft and immutable applied-revision persistence boundary for M4R."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from typing import Protocol, cast

from pilot_assessment.contracts.evidence_recipe import (
    EvidenceRecipe,
    RecipeLifecycle,
)
from pilot_assessment.synchronization.fingerprint import canonical_json_bytes

Clock = Callable[[], datetime]


class RecipeRepositoryError(RuntimeError):
    """Base class for technical recipe repository errors."""


class RecipeNotFoundError(RecipeRepositoryError):
    """Raised when a requested draft or applied revision does not exist."""


class RecipeAlreadyExistsError(RecipeRepositoryError):
    """Raised when a new draft would overwrite an existing recipe identity."""


class DraftRevisionConflictError(RecipeRepositoryError):
    """Raised when an autosave was based on an older draft revision."""


@dataclass(frozen=True, slots=True)
class RecipeDraftRecord:
    recipe: EvidenceRecipe
    draft_revision: int
    content_sha256: str
    previous_content_sha256: str | None
    changed_paths: tuple[str, ...]
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str


@dataclass(frozen=True, slots=True)
class AppliedRecipeRevision:
    revision_id: str
    recipe_id: str
    revision_number: int
    recipe: EvidenceRecipe
    content_sha256: str
    previous_revision_id: str | None
    previous_content_sha256: str | None
    changed_paths: tuple[str, ...]
    source_draft_revision: int
    applied_at: datetime
    applied_by: str
    note: str | None


class RecipeRepository(Protocol):
    """Persistence protocol retained when M6 replaces the in-memory adapter."""

    def create_draft(
        self,
        recipe: EvidenceRecipe,
        *,
        author_id: str,
    ) -> RecipeDraftRecord: ...

    def get_draft(self, recipe_id: str) -> RecipeDraftRecord: ...

    def save_draft(
        self,
        recipe: EvidenceRecipe,
        *,
        expected_draft_revision: int,
        author_id: str,
    ) -> RecipeDraftRecord: ...

    def clone_draft(
        self,
        source_recipe_id: str,
        new_recipe_id: str,
        *,
        author_id: str,
    ) -> RecipeDraftRecord: ...

    def set_lifecycle(
        self,
        recipe_id: str,
        lifecycle: RecipeLifecycle | str,
        *,
        author_id: str,
    ) -> RecipeDraftRecord: ...

    def create_applied_revision(
        self,
        recipe_id: str,
        *,
        author_id: str,
        note: str | None,
    ) -> AppliedRecipeRevision: ...

    def get_applied_revision(self, revision_id: str) -> AppliedRecipeRevision: ...

    def list_applied_revisions(
        self,
        recipe_id: str,
    ) -> tuple[AppliedRecipeRevision, ...]: ...


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _author(value: object) -> str:
    if type(value) is not str or not value:
        raise RecipeRepositoryError("author_id must be a non-empty string")
    return value


def _timestamp(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise RecipeRepositoryError("repository clock must return a timezone-aware datetime")
    return value


def _snapshot(recipe: EvidenceRecipe) -> EvidenceRecipe:
    if not isinstance(recipe, EvidenceRecipe):
        raise RecipeRepositoryError("recipe must use the canonical EvidenceRecipe contract")
    return EvidenceRecipe.model_validate(recipe.model_dump(mode="json"))


def recipe_content_sha256(recipe: EvidenceRecipe) -> str:
    """Return a deterministic identity over the canonical editable recipe DTO."""

    snapshot = _snapshot(recipe)
    return hashlib.sha256(
        canonical_json_bytes(snapshot.model_dump(mode="json"))
    ).hexdigest()


def _pointer_token(value: object) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")


def _changed_paths(
    before: object,
    after: object,
    *,
    path: str = "",
) -> tuple[str, ...]:
    if before == after:
        return ()
    changed: list[str] = []
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        before_mapping = cast(Mapping[object, object], before)
        after_mapping = cast(Mapping[object, object], after)
        keys = sorted(set(before_mapping) | set(after_mapping), key=str)
        for key in keys:
            nested_path = f"{path}/{_pointer_token(key)}"
            if key not in before_mapping or key not in after_mapping:
                changed.append(nested_path)
            else:
                changed.extend(
                    _changed_paths(
                        before_mapping[key],
                        after_mapping[key],
                        path=nested_path,
                    )
                )
    elif (
        isinstance(before, Sequence)
        and not isinstance(before, (str, bytes))
        and isinstance(after, Sequence)
        and not isinstance(after, (str, bytes))
    ):
        shared = min(len(before), len(after))
        for index in range(shared):
            changed.extend(
                _changed_paths(
                    before[index],
                    after[index],
                    path=f"{path}/{index}",
                )
            )
        for index in range(shared, max(len(before), len(after))):
            changed.append(f"{path}/{index}")
    else:
        changed.append(path or "/")
    return tuple(sorted(set(changed)))


class InMemoryRecipeRepository:
    """Thread-safe M4R repository; M6 can replace it behind the same protocol."""

    def __init__(self, *, clock: Clock = _utc_now) -> None:
        self._clock = clock
        self._drafts: dict[str, RecipeDraftRecord] = {}
        self._applied: dict[str, AppliedRecipeRevision] = {}
        self._applied_by_recipe: dict[str, list[str]] = {}
        self._lock = RLock()

    def _now(self) -> datetime:
        return _timestamp(self._clock())

    def create_draft(
        self,
        recipe: EvidenceRecipe,
        *,
        author_id: str,
    ) -> RecipeDraftRecord:
        author = _author(author_id)
        snapshot = _snapshot(recipe)
        with self._lock:
            if snapshot.recipe_id in self._drafts:
                raise RecipeAlreadyExistsError(
                    f"recipe draft {snapshot.recipe_id!r} already exists"
                )
            timestamp = self._now()
            record = RecipeDraftRecord(
                recipe=snapshot,
                draft_revision=1,
                content_sha256=recipe_content_sha256(snapshot),
                previous_content_sha256=None,
                changed_paths=("/",),
                created_at=timestamp,
                updated_at=timestamp,
                created_by=author,
                updated_by=author,
            )
            self._drafts[snapshot.recipe_id] = record
            return record

    def get_draft(self, recipe_id: str) -> RecipeDraftRecord:
        with self._lock:
            try:
                return self._drafts[recipe_id]
            except KeyError as error:
                raise RecipeNotFoundError(
                    f"recipe draft {recipe_id!r} does not exist"
                ) from error

    def save_draft(
        self,
        recipe: EvidenceRecipe,
        *,
        expected_draft_revision: int,
        author_id: str,
    ) -> RecipeDraftRecord:
        author = _author(author_id)
        if type(expected_draft_revision) is not int or expected_draft_revision < 1:
            raise RecipeRepositoryError(
                "expected_draft_revision must be a positive strict integer"
            )
        snapshot = _snapshot(recipe)
        with self._lock:
            current = self.get_draft(snapshot.recipe_id)
            if current.draft_revision != expected_draft_revision:
                raise DraftRevisionConflictError(
                    f"recipe {snapshot.recipe_id!r} is at draft revision "
                    f"{current.draft_revision}, not {expected_draft_revision}"
                )
            changed_paths = _changed_paths(
                current.recipe.model_dump(mode="json"),
                snapshot.model_dump(mode="json"),
            )
            record = RecipeDraftRecord(
                recipe=snapshot,
                draft_revision=current.draft_revision + 1,
                content_sha256=recipe_content_sha256(snapshot),
                previous_content_sha256=current.content_sha256,
                changed_paths=changed_paths,
                created_at=current.created_at,
                updated_at=self._now(),
                created_by=current.created_by,
                updated_by=author,
            )
            self._drafts[snapshot.recipe_id] = record
            return record

    def clone_draft(
        self,
        source_recipe_id: str,
        new_recipe_id: str,
        *,
        author_id: str,
    ) -> RecipeDraftRecord:
        with self._lock:
            source = self.get_draft(source_recipe_id)
            cloned = source.recipe.model_copy(
                update={"recipe_id": new_recipe_id, "recipe_version": 1}
            )
            return self.create_draft(cloned, author_id=author_id)

    def set_lifecycle(
        self,
        recipe_id: str,
        lifecycle: RecipeLifecycle | str,
        *,
        author_id: str,
    ) -> RecipeDraftRecord:
        try:
            normalized = RecipeLifecycle(lifecycle)
        except ValueError as error:
            raise RecipeRepositoryError(f"unsupported recipe lifecycle {lifecycle!r}") from error
        with self._lock:
            current = self.get_draft(recipe_id)
            changed = current.recipe.model_copy(
                update={
                    "anchor": current.recipe.anchor.model_copy(
                        update={"lifecycle": normalized}
                    )
                }
            )
            return self.save_draft(
                changed,
                expected_draft_revision=current.draft_revision,
                author_id=author_id,
            )

    def create_applied_revision(
        self,
        recipe_id: str,
        *,
        author_id: str,
        note: str | None,
    ) -> AppliedRecipeRevision:
        author = _author(author_id)
        if note is not None and type(note) is not str:
            raise RecipeRepositoryError("revision note must be a string or null")
        with self._lock:
            draft = self.get_draft(recipe_id)
            snapshot = _snapshot(draft.recipe)
            revision_ids = self._applied_by_recipe.setdefault(recipe_id, [])
            previous = self._applied[revision_ids[-1]] if revision_ids else None
            revision_number = len(revision_ids) + 1
            revision_id = f"{recipe_id}-applied-{revision_number:06d}"
            changed_paths = (
                ("/",)
                if previous is None
                else _changed_paths(
                    previous.recipe.model_dump(mode="json"),
                    snapshot.model_dump(mode="json"),
                )
            )
            revision = AppliedRecipeRevision(
                revision_id=revision_id,
                recipe_id=recipe_id,
                revision_number=revision_number,
                recipe=snapshot,
                content_sha256=recipe_content_sha256(snapshot),
                previous_revision_id=(
                    None if previous is None else previous.revision_id
                ),
                previous_content_sha256=(
                    None if previous is None else previous.content_sha256
                ),
                changed_paths=changed_paths,
                source_draft_revision=draft.draft_revision,
                applied_at=self._now(),
                applied_by=author,
                note=note,
            )
            self._applied[revision_id] = revision
            revision_ids.append(revision_id)
            return revision

    def get_applied_revision(self, revision_id: str) -> AppliedRecipeRevision:
        with self._lock:
            try:
                return self._applied[revision_id]
            except KeyError as error:
                raise RecipeNotFoundError(
                    f"applied recipe revision {revision_id!r} does not exist"
                ) from error

    def list_applied_revisions(
        self,
        recipe_id: str,
    ) -> tuple[AppliedRecipeRevision, ...]:
        with self._lock:
            return tuple(
                self._applied[revision_id]
                for revision_id in self._applied_by_recipe.get(recipe_id, ())
            )


__all__ = [
    "AppliedRecipeRevision",
    "Clock",
    "DraftRevisionConflictError",
    "InMemoryRecipeRepository",
    "RecipeAlreadyExistsError",
    "RecipeDraftRecord",
    "RecipeNotFoundError",
    "RecipeRepository",
    "RecipeRepositoryError",
    "recipe_content_sha256",
]
