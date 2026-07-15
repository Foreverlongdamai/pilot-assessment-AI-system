from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pilot_assessment.contracts.evidence_recipe import RecipeGraph, RecipeLifecycle
from pilot_assessment.evidence.repository import (
    DraftRevisionConflictError,
    InMemoryRecipeRepository,
    recipe_content_sha256,
)
from tests.evidence.runtime_support import constant_recipe


class _Clock:
    def __init__(self) -> None:
        self._value = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        value = self._value
        self._value += timedelta(seconds=1)
        return value


def test_incomplete_draft_autosave_uses_optimistic_revision_and_structured_diff() -> None:
    repository = InMemoryRecipeRepository(clock=_Clock())
    base = constant_recipe(2.0)
    incomplete = base.model_copy(update={"graph": RecipeGraph(nodes=(), edges=())})

    created = repository.create_draft(incomplete, author_id="expert-a")
    edited = incomplete.model_copy(
        update={
            "recipe_version": 2,
            "documentation": incomplete.documentation.model_copy(
                update={"summary": "autosaved incomplete graph"}
            ),
        }
    )
    saved = repository.save_draft(
        edited,
        expected_draft_revision=1,
        author_id="expert-b",
    )

    assert created.draft_revision == 1
    assert saved.draft_revision == 2
    assert saved.previous_content_sha256 == created.content_sha256
    assert saved.content_sha256 == recipe_content_sha256(edited)
    assert "/recipe_version" in saved.changed_paths
    assert "/documentation/summary" in saved.changed_paths
    assert saved.updated_by == "expert-b"

    with pytest.raises(DraftRevisionConflictError):
        repository.save_draft(
            edited,
            expected_draft_revision=1,
            author_id="stale-editor",
        )


def test_clone_and_lifecycle_edits_do_not_rewrite_applied_history() -> None:
    repository = InMemoryRecipeRepository(clock=_Clock())
    original = repository.create_draft(
        constant_recipe(2.0, recipe_id="recipe.original"),
        author_id="expert-a",
    )
    applied = repository.create_applied_revision(
        original.recipe.recipe_id,
        author_id="expert-a",
        note=None,
    )
    cloned = repository.clone_draft(
        original.recipe.recipe_id,
        "recipe.clone",
        author_id="expert-b",
    )

    repository.set_lifecycle(
        original.recipe.recipe_id,
        RecipeLifecycle.DISABLED,
        author_id="expert-a",
    )
    repository.set_lifecycle(
        original.recipe.recipe_id,
        RecipeLifecycle.RETIRED,
        author_id="expert-a",
    )

    historical = repository.get_applied_revision(applied.revision_id)
    assert cloned.recipe.recipe_id == "recipe.clone"
    assert cloned.recipe.recipe_version == 1
    assert cloned.content_sha256 != original.content_sha256
    assert historical.recipe.anchor.lifecycle is RecipeLifecycle.ACTIVE
    assert repository.list_applied_revisions(original.recipe.recipe_id) == (applied,)
