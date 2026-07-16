from __future__ import annotations

import numpy as np
import pytest

from pilot_assessment.bayesian.factors import Factor, FactorError, multiply_factors


def test_factor_algebra_matches_a_hand_calculated_two_node_posterior() -> None:
    prior = Factor(("skill",), (2,), (0.6, 0.4))
    conditional = Factor(
        ("skill", "evidence"),
        (2, 2),
        ((0.9, 0.1), (0.2, 0.8)),
    )

    joint = multiply_factors((prior, conditional))
    high_evidence = joint.condition("evidence", 1)
    posterior = high_evidence.normalize()

    assert joint.variables == ("evidence", "skill")
    assert high_evidence.variables == ("skill",)
    assert posterior.values == pytest.approx((0.15789473684210525, 0.8421052631578948))
    assert joint.marginal(("evidence",)).values == pytest.approx((0.62, 0.38))


def test_sum_out_reorder_and_zero_mass_are_explicit() -> None:
    factor = Factor(("z", "a"), (2, 2), ((0.1, 0.2), (0.3, 0.4)))

    assert factor.sum_out("z").variables == ("a",)
    assert factor.sum_out("z").values == pytest.approx((0.4, 0.6))
    assert factor.marginal(("a", "z")).variables == ("a", "z")
    assert np.asarray(factor.marginal(("a", "z")).values).shape == (2, 2)
    with pytest.raises(FactorError, match="zero probability mass"):
        Factor(("x",), (2,), (0.0, 0.0)).normalize()
