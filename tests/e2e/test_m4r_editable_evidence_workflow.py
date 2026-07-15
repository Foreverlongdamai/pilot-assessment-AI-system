from __future__ import annotations

from importlib.resources import files

import pytest

from pilot_assessment.contracts.evidence_recipe import RecipeGraph, RecipeLifecycle
from pilot_assessment.evidence.builtins import register_builtin_operators
from pilot_assessment.evidence.registry import OperatorRegistry
from pilot_assessment.evidence.repository import InMemoryRecipeRepository
from pilot_assessment.evidence.service import EvidenceRecipeService
from tests.evidence.test_disturbance_aoi_recipe import (
    disturbance_aoi_inputs,
    disturbance_aoi_recipe,
)


def _service() -> tuple[EvidenceRecipeService, InMemoryRecipeRepository]:
    registry = OperatorRegistry()
    register_builtin_operators(registry)
    repository = InMemoryRecipeRepository()
    return EvidenceRecipeService(repository, registry), repository


def test_expert_recipe_draft_preview_apply_replay_clone_and_disable_workflow() -> None:
    service, repository = _service()
    full = disturbance_aoi_recipe()
    incomplete = full.model_copy(
        update={
            "graph": RecipeGraph(
                nodes=full.graph.nodes,
                edges=full.graph.edges[:-1],
            )
        }
    )

    created = service.create_draft(incomplete, author_id="expert-a")
    incomplete_preview = service.preview(
        full.recipe_id,
        execution_inputs=disturbance_aoi_inputs(),
    )
    completed = service.save_draft(
        full,
        expected_draft_revision=created.draft_revision,
        author_id="expert-a",
    )
    preview_a = service.preview(
        full.recipe_id,
        execution_inputs=disturbance_aoi_inputs(),
        trace_node_ids=("event-window", "aoi-filter"),
    )
    revision_a = service.apply(
        full.recipe_id,
        author_id="expert-a",
        note="initial editable starter",
    )

    changed = disturbance_aoi_recipe(
        expected_aoi="unobserved-aoi",
        window_end_offset_ns=3_000_000_000,
        recipe_version=2,
    )
    assert changed.scoring is not None
    changed = changed.model_copy(
        update={
            "scoring": changed.scoring.model_copy(
                update={
                    "parameters": {
                        "direction": "lower_is_better",
                        "desired_boundary": 0.5,
                        "adequate_boundary": 1.0,
                        "likelihood_strength": 0.8,
                    }
                }
            )
        }
    )
    saved_b = service.save_draft(
        changed,
        expected_draft_revision=completed.draft_revision,
        author_id="expert-b",
    )
    preview_b = service.preview(
        full.recipe_id,
        execution_inputs=disturbance_aoi_inputs(),
    )
    revision_b = service.apply(
        full.recipe_id,
        author_id="expert-b",
        note="AOI window and scorer edited in recipe data",
    )
    replay_a = service.replay(
        revision_a.revision_id,
        execution_inputs=disturbance_aoi_inputs(),
        trace_node_ids=("event-window", "aoi-filter"),
    )

    cloned = service.clone_draft(
        full.recipe_id,
        "expert.disturbance-aoi-copy",
        author_id="expert-c",
    )
    cloned_as_new_anchor = cloned.recipe.model_copy(
        update={
            "anchor": cloned.recipe.anchor.model_copy(
                update={
                    "anchor_id": "EXPERT-DISTURBANCE-AOI-COPY",
                    "name": "Expert disturbance AOI copy",
                }
            )
        }
    )
    renamed = service.save_draft(
        cloned_as_new_anchor,
        expected_draft_revision=cloned.draft_revision,
        author_id="expert-c",
    )
    disabled = service.set_lifecycle(
        cloned.recipe.recipe_id,
        RecipeLifecycle.DISABLED,
        author_id="expert-c",
    )

    assert incomplete_preview.succeeded is False
    assert preview_a.succeeded is True
    assert preview_a.execution is not None
    assert preview_a.execution.outputs == {
        "latency-s": 1.0,
        "dwell-ratio": pytest.approx(0.4),
    }
    assert preview_b.succeeded is True
    assert preview_b.execution is not None
    assert preview_b.execution.outputs == {
        "latency-s": 3.0,
        "dwell-ratio": 0.0,
    }
    assert replay_a.outputs == preview_a.execution.outputs
    assert tuple(trace.operator_id for trace in replay_a.traces) == tuple(
        trace.operator_id for trace in preview_a.execution.traces
    )
    assert revision_a.content_sha256 != revision_b.content_sha256
    assert repository.list_applied_revisions(full.recipe_id) == (
        revision_a,
        revision_b,
    )
    assert renamed.recipe.anchor.anchor_id == "EXPERT-DISTURBANCE-AOI-COPY"
    assert disabled.recipe.anchor.lifecycle is RecipeLifecycle.DISABLED
    assert service.get_applied_revision(revision_a.revision_id) == revision_a

    legacy_plugin_files = tuple(
        resource.name
        for resource in files("pilot_assessment.anchors.plugins").iterdir()
        if resource.name.endswith(".py") and resource.name != "__init__.py"
    )
    assert len(legacy_plugin_files) == 15
    assert saved_b.recipe.recipe_version == 2
