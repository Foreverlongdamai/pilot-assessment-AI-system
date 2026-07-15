from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pilot_assessment.contracts.evidence_recipe import (
    NodePortReference,
    RecipeGraph,
    RecipeNode,
    RecipeOutputBinding,
)
from pilot_assessment.evidence.builtins import register_builtin_operators
from pilot_assessment.evidence.registry import OperatorRegistry
from pilot_assessment.evidence.repository import InMemoryRecipeRepository
from pilot_assessment.evidence.service import EvidenceRecipeService, RecipeApplyError
from tests.evidence.runtime_support import constant_recipe


class _Clock:
    def __init__(self) -> None:
        self._value = datetime(2026, 7, 15, 13, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        value = self._value
        self._value += timedelta(seconds=1)
        return value


def _service() -> tuple[EvidenceRecipeService, InMemoryRecipeRepository]:
    registry = OperatorRegistry()
    register_builtin_operators(registry)
    repository = InMemoryRecipeRepository(clock=_Clock())
    return EvidenceRecipeService(repository, registry), repository


def test_preview_apply_edit_and_replay_use_exact_immutable_snapshots() -> None:
    service, repository = _service()
    recipe = constant_recipe(2.0)
    created = service.create_draft(recipe, author_id="expert-a")

    preview = service.preview(recipe.recipe_id, execution_inputs={})
    assert preview.succeeded is True
    assert preview.execution is not None
    assert preview.execution.outputs == {"primary": 2.0}
    assert repository.list_applied_revisions(recipe.recipe_id) == ()

    applied = service.apply(recipe.recipe_id, author_id="expert-a", note=None)
    changed = constant_recipe(9.0, recipe_version=2)
    service.save_draft(
        changed,
        expected_draft_revision=created.draft_revision,
        author_id="expert-b",
    )

    current = service.preview(recipe.recipe_id, execution_inputs={})
    replayed = service.replay(applied.revision_id, execution_inputs={})
    historical = service.get_applied_revision(applied.revision_id)

    assert current.execution is not None
    assert current.execution.outputs == {"primary": 9.0}
    assert replayed.outputs == {"primary": 2.0}
    assert historical.recipe.graph.nodes[0].parameters["value"] == 2.0
    assert historical.note is None
    assert historical.applied_by == "expert-a"


def test_incomplete_draft_can_autosave_but_preview_and_apply_return_technical_diagnostics() -> None:
    service, repository = _service()
    recipe = constant_recipe(2.0, recipe_id="runtime.incomplete")
    incomplete = recipe.model_copy(
        update={"graph": RecipeGraph(nodes=(), edges=())}
    )
    service.create_draft(incomplete, author_id="expert-a")

    preview = service.preview(incomplete.recipe_id, execution_inputs={})

    assert preview.succeeded is False
    assert preview.execution is None
    assert preview.diagnostics
    assert repository.list_applied_revisions(incomplete.recipe_id) == ()
    with pytest.raises(RecipeApplyError) as caught:
        service.apply(incomplete.recipe_id, author_id="expert-a", note="optional")
    assert caught.value.diagnostics


def test_preview_localizes_runtime_operator_errors_to_the_recipe_node() -> None:
    service, _repository = _service()
    base = constant_recipe(2.0, recipe_id="runtime.execution-error")
    formula = RecipeNode(
        node_id="formula",
        operator_id="composition.safe-formula",
        operator_version="0.1.0",
        parameters={"formula": "1 / zero", "constants": {"zero": 0.0}},
    )
    value_ref = NodePortReference(node_id="formula", port_id="value")
    assert base.scoring is not None
    recipe = base.model_copy(
        update={
            "graph": RecipeGraph(nodes=(formula,), edges=()),
            "outputs": (
                RecipeOutputBinding(
                    output_id="primary",
                    role=base.outputs[0].role,
                    name="Primary",
                    source=value_ref,
                    unit=None,
                ),
            ),
            "scoring": base.scoring.model_copy(update={"input": value_ref}),
        }
    )
    service.create_draft(recipe, author_id="expert-a")

    preview = service.preview(recipe.recipe_id, execution_inputs={})

    assert preview.succeeded is False
    assert preview.execution is None
    assert any(diagnostic.node_id == "formula" for diagnostic in preview.diagnostics)
