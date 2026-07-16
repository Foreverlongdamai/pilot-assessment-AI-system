from __future__ import annotations

import pytest

from pilot_assessment.bayesian.validation import (
    materialize_ordered_single_parent,
    materialize_ranked_cpt,
    materialize_uniform_prior,
)


def test_uniform_prior_and_ordered_single_parent_are_explicit_generic_helpers() -> None:
    prior = materialize_uniform_prior(("s0", "s1", "s2", "s3"))
    ordered = materialize_ordered_single_parent(
        ("p0", "p1", "p2"),
        ("c0", "c1", "c2"),
        sigma=0.6,
    )

    assert prior.parent_assignments == ((),)
    assert prior.probabilities == ((0.25, 0.25, 0.25, 0.25),)
    assert ordered.parent_assignments == (("p0",), ("p1",), ("p2",))
    assert [max(range(3), key=row.__getitem__) for row in ordered.probabilities] == [0, 1, 2]
    assert all(sum(row) == pytest.approx(1.0) for row in ordered.probabilities)


def test_ranked_materializer_uses_stable_product_order_and_matches_hand_calculation() -> None:
    materialized = materialize_ranked_cpt(
        (("low", "mid", "high"), ("low", "mid", "high")),
        ("low", "mid", "high"),
        weights=(0.5, 0.5),
        weakest_link_strength=0.5,
        sigma=0.6,
    )

    assert materialized.parent_assignments[:4] == (
        ("low", "low"),
        ("low", "mid"),
        ("low", "high"),
        ("mid", "low"),
    )
    assert materialized.parent_assignments[6] == ("high", "low")
    assert materialized.probabilities[6] == pytest.approx(
        (0.4849245388797158, 0.4849245388797158, 0.03015092224056833)
    )
    assert all(sum(row) == pytest.approx(1.0) for row in materialized.probabilities)
