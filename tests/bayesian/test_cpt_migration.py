from __future__ import annotations

import pytest

from pilot_assessment.bayesian.validation import (
    CptMigrationError,
    add_parent_preserving_independence,
    invalidate_cpts_for_state_change,
    remove_parent_with_marginal_weights,
)
from pilot_assessment.contracts.model_components import ComponentIdRef, ComponentKind, CptMode
from tests.bayesian.support import cpt, node, state_space


def test_add_parent_replicates_rows_and_remove_parent_requires_explicit_weights() -> None:
    states = state_space("state", 2)
    old_parent = node("variable.old-parent", states)
    new_parent = node("variable.new-parent", state_space("new", 3))
    child = node("variable.child", states, parents=(old_parent,))
    original = cpt(
        "cpt.variable.child",
        child,
        parents=(old_parent,),
        rows=((0.8, 0.2), (0.3, 0.7)),
    )

    expanded = add_parent_preserving_independence(
        original,
        ComponentIdRef(
            kind=ComponentKind.BN_NODE_VERSION,
            version_id=new_parent.bn_node_version_id,
        ),
        tuple(state.state_id for state in new_parent.ordered_states),
    )

    assert expanded.materialized_probabilities == (
        (0.8, 0.2),
        (0.8, 0.2),
        (0.8, 0.2),
        (0.3, 0.7),
        (0.3, 0.7),
        (0.3, 0.7),
    )
    with pytest.raises(CptMigrationError, match="weights"):
        remove_parent_with_marginal_weights(
            expanded,
            ComponentIdRef(
                kind=ComponentKind.BN_NODE_VERSION,
                version_id=new_parent.bn_node_version_id,
            ),
            weights=None,
        )
    restored = remove_parent_with_marginal_weights(
        expanded,
        ComponentIdRef(
            kind=ComponentKind.BN_NODE_VERSION,
            version_id=new_parent.bn_node_version_id,
        ),
        weights=(0.2, 0.3, 0.5),
    )
    assert restored.ordered_parent_variable_ids == original.ordered_parent_variable_ids
    for actual, expected in zip(
        restored.materialized_probabilities,
        original.materialized_probabilities,
        strict=True,
    ):
        assert actual == pytest.approx(expected)


def test_remove_parent_uses_the_supplied_marginal_weights_in_stable_row_order() -> None:
    states = state_space("state", 2)
    first = node("variable.first", states)
    removed = node("variable.removed", states)
    child = node("variable.child", states, parents=(first, removed))
    table = cpt(
        "cpt.variable.child",
        child,
        parents=(first, removed),
        rows=((0.9, 0.1), (0.5, 0.5), (0.4, 0.6), (0.0, 1.0)),
    )

    migrated = remove_parent_with_marginal_weights(
        table,
        ComponentIdRef(
            kind=ComponentKind.BN_NODE_VERSION,
            version_id=removed.bn_node_version_id,
        ),
        weights=(0.25, 0.75),
    )

    for actual, expected in zip(
        migrated.materialized_probabilities,
        ((0.6, 0.4), (0.1, 0.9)),
        strict=True,
    ):
        assert actual == pytest.approx(expected)


def test_state_edit_marks_child_and_dependent_cpts_incomplete_without_touching_others() -> None:
    old_states = state_space("old", 2)
    changed = node("variable.changed", old_states)
    dependent = node("variable.dependent", old_states, parents=(changed,))
    unrelated = node("variable.unrelated", old_states)
    changed_cpt = cpt(
        "cpt.variable.changed",
        changed,
        rows=((0.5, 0.5),),
    )
    dependent_cpt = cpt(
        "cpt.variable.dependent",
        dependent,
        parents=(changed,),
        rows=((0.8, 0.2), (0.2, 0.8)),
    )
    unrelated_cpt = cpt(
        "cpt.variable.unrelated",
        unrelated,
        rows=((0.5, 0.5),),
    )
    new_state_ids = ("new.low", "new.mid", "new.high")

    migrated = invalidate_cpts_for_state_change(
        (changed_cpt, dependent_cpt, unrelated_cpt),
        ComponentIdRef(
            kind=ComponentKind.BN_NODE_VERSION,
            version_id=changed.bn_node_version_id,
        ),
        new_state_ids,
    )

    assert migrated[0].mode is CptMode.INCOMPLETE
    assert migrated[0].child_state_ids == new_state_ids
    assert migrated[1].mode is CptMode.INCOMPLETE
    assert migrated[1].ordered_parent_state_ids == (new_state_ids,)
    assert migrated[0].materialized_probabilities == ()
    assert migrated[1].materialized_probabilities == ()
    assert migrated[2] is unrelated_cpt
