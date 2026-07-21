from __future__ import annotations

from pathlib import Path

import pytest

from pilot_assessment.model_workspace.service import (
    CurrentDeactivationImpactConflict,
)
from tests.model_workspace.support import seven_node_graph
from tests.model_workspace.test_scheme_service import _workspace


def _create_parallel_schemes(service):
    _, base = seven_node_graph()
    base_saved = service.create_scheme(
        base,
        transaction_id="tx.scheme.base.create",
        actor_id="expert.one",
    ).scheme
    parallel = service.copy_scheme(
        base.scheme_id,
        new_scheme_id="scheme.parallel",
        name="Parallel Scheme",
        transaction_id="tx.scheme.parallel.copy",
        actor_id="expert.one",
    ).scheme
    return base_saved, parallel


def test_child_activation_silently_enables_fixed_parents_in_current_scheme_only(
    tmp_path: Path,
) -> None:
    database, service, _ = _workspace(tmp_path / "project.sqlite3")
    try:
        base, parallel = _create_parallel_schemes(service)
        result = service.activate_node(
            base.scheme_id,
            "evidence.gaze",
            expected_semantic_revision=base.semantic_revision,
            transaction_id="tx.scheme.base.activate-gaze",
            actor_id="expert.one",
        )

        assert result.scheme.explicit_active_node_ids == (
            "evidence.gaze",
            "evidence.precision",
        )
        assert result.scheme.computed_active_closure == (
            "bn.competency",
            "bn.skill",
            "evidence.gaze",
            "evidence.precision",
            "raw.g",
            "raw.u",
            "raw.x",
        )
        assert result.diff.added_node_ids == ("evidence.gaze", "raw.g")
        assert result.diff.metadata["auto_enabled_parent_ids"] == ["raw.g"]
        assert len(result.diff.added_edge_ids) == 2
        assert service.get_scheme(parallel.scheme_id) == parallel
    finally:
        database.close()


def test_deactivation_preview_is_read_only_and_stale_shared_graph_hash_is_rejected(
    tmp_path: Path,
) -> None:
    database, service, _ = _workspace(tmp_path / "project.sqlite3")
    try:
        base, parallel = _create_parallel_schemes(service)
        activated = service.activate_node(
            base.scheme_id,
            "evidence.gaze",
            expected_semantic_revision=base.semantic_revision,
            transaction_id="tx.scheme.base.activate-gaze",
            actor_id="expert.one",
        ).scheme
        history_count = len(service.scheme_history(base.scheme_id))
        preview = service.preview_deactivation(base.scheme_id, "raw.x")
        assert preview.impacted_node_ids == (
            "evidence.precision",
            "raw.u",
            "raw.x",
        )
        assert len(preview.impacted_edge_ids) == 3
        assert len(service.scheme_history(base.scheme_id)) == history_count

        # A shared node edit changes the graph hash without cloning the scheme.
        raw_u = service.get_node("raw.u")
        service.update_node(
            raw_u.model_copy(update={"name": "Renamed control stream"}),
            expected_semantic_revision=raw_u.semantic_revision,
            expected_layout_revision=None,
            transaction_id="tx.node.raw-u.rename",
            actor_id="expert.two",
        )
        assert service.get_scheme(base.scheme_id).semantic_revision == activated.semantic_revision

        with pytest.raises(CurrentDeactivationImpactConflict) as captured:
            service.deactivate_node(
                base.scheme_id,
                "raw.x",
                expected_semantic_revision=activated.semantic_revision,
                impact_hash=preview.impact_hash,
                transaction_id="tx.scheme.base.deactivate-stale",
                actor_id="expert.one",
            )
        assert captured.value.current_impact.impact_hash != preview.impact_hash
        assert service.get_scheme(base.scheme_id).computed_active_closure == (
            "bn.competency",
            "bn.skill",
            "evidence.gaze",
            "evidence.precision",
            "raw.g",
            "raw.u",
            "raw.x",
        )

        current_preview = service.preview_deactivation(base.scheme_id, "raw.x")
        deactivated = service.deactivate_node(
            base.scheme_id,
            "raw.x",
            expected_semantic_revision=activated.semantic_revision,
            impact_hash=current_preview.impact_hash,
            transaction_id="tx.scheme.base.deactivate-raw-x",
            actor_id="expert.one",
        )
        assert deactivated.scheme.explicit_active_node_ids == ("evidence.gaze",)
        assert deactivated.scheme.computed_active_closure == (
            "bn.competency",
            "bn.skill",
            "evidence.gaze",
            "raw.g",
        )
        assert deactivated.diff.removed_node_ids == current_preview.impacted_node_ids
        assert set(deactivated.diff.removed_edge_ids) == set(current_preview.impacted_edge_ids)
        assert service.get_scheme(parallel.scheme_id) == parallel
    finally:
        database.close()


def test_parent_deactivation_cascades_atomically_and_clears_orphan_output(
    tmp_path: Path,
) -> None:
    database, service, _ = _workspace(tmp_path / "project.sqlite3")
    try:
        base, _ = _create_parallel_schemes(service)
        activated = service.activate_node(
            base.scheme_id,
            "evidence.gaze",
            expected_semantic_revision=base.semantic_revision,
            transaction_id="tx.scheme.base.activate-gaze",
            actor_id="expert.one",
        ).scheme
        preview = service.preview_deactivation(base.scheme_id, "bn.skill")
        assert preview.impacted_node_ids == activated.computed_active_closure

        result = service.deactivate_node(
            base.scheme_id,
            "bn.skill",
            expected_semantic_revision=activated.semantic_revision,
            impact_hash=preview.impact_hash,
            transaction_id="tx.scheme.base.deactivate-skill",
            actor_id="expert.one",
        )
        assert result.scheme.explicit_active_node_ids == ()
        assert result.scheme.computed_active_closure == ()
        assert result.scheme.output_node_ids == ()
        assert result.scheme.technical_status.value == "executable"
        assert result.diff.removed_node_ids == preview.impacted_node_ids
    finally:
        database.close()
