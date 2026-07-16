from __future__ import annotations

import pytest

from pilot_assessment.bayesian.inference import (
    ImpossibleEvidenceError,
    InferenceEngine,
    ObservationValidationError,
)
from pilot_assessment.contracts.bayesian import Observation, ObservationKind
from tests.bayesian.inference_support import hard_observation, two_node_fixture
from tests.schemes.support import variable_ref


def test_virtual_likelihood_is_unnormalized_and_omitted_observation_adds_no_factor() -> None:
    fixture = two_node_fixture()
    engine = InferenceEngine(fixture.repository)
    plan = engine.compile(fixture.scheme)
    virtual = Observation(
        variable_id=variable_ref(fixture.observed),
        kind=ObservationKind.VIRTUAL,
        hard_state_id=None,
        likelihood=(2.0, 8.0),
    )
    omitted = Observation(
        variable_id=variable_ref(fixture.observed),
        kind=ObservationKind.OMITTED,
        hard_state_id=None,
        likelihood=None,
    )

    virtual_result = engine.infer(
        plan,
        engine.observe(plan, (virtual,)),
        (variable_ref(fixture.root),),
    )
    omitted_result = engine.infer(
        plan,
        engine.observe(plan, (omitted,)),
        (variable_ref(fixture.root),),
    )

    assert virtual_result.posteriors[0].probabilities == pytest.approx(
        (0.3644859813084112, 0.6355140186915889)
    )
    assert omitted_result.posteriors[0].probabilities == pytest.approx((0.6, 0.4))


def test_computed_unacceptable_is_a_normal_directional_hard_observation() -> None:
    fixture = two_node_fixture()
    engine = InferenceEngine(fixture.repository)
    plan = engine.compile(fixture.scheme)
    unacceptable = fixture.observed.ordered_observation_states[0].state_id

    result = engine.infer(
        plan,
        engine.observe(plan, (hard_observation(fixture.observed, unacceptable),)),
        (variable_ref(fixture.root),),
    )

    assert result.posteriors[0].probabilities == pytest.approx(
        (0.8709677419354839, 0.12903225806451613)
    )


def test_observation_state_length_unknown_state_and_impossible_evidence_are_rejected() -> None:
    fixture = two_node_fixture(
        root_prior=(1.0, 0.0),
        observed_rows=((1.0, 0.0), (1.0, 0.0)),
    )
    engine = InferenceEngine(fixture.repository)
    plan = engine.compile(fixture.scheme)
    with pytest.raises(ObservationValidationError, match="state order"):
        engine.observe(
            plan,
            (
                Observation(
                    variable_id=variable_ref(fixture.observed),
                    kind=ObservationKind.VIRTUAL,
                    hard_state_id=None,
                    likelihood=(1.0, 2.0, 3.0),
                ),
            ),
        )
    with pytest.raises(ObservationValidationError, match="unknown hard state"):
        engine.observe(
            plan,
            (
                Observation(
                    variable_id=variable_ref(fixture.observed),
                    kind=ObservationKind.HARD,
                    hard_state_id="state.not-declared",
                    likelihood=None,
                ),
            ),
        )

    impossible = engine.observe(
        plan,
        (
            hard_observation(
                fixture.observed,
                fixture.observed.ordered_observation_states[1].state_id,
            ),
        ),
    )
    with pytest.raises(ImpossibleEvidenceError) as caught:
        engine.infer(plan, impossible, (variable_ref(fixture.root),))
    assert caught.value.code == "inference.impossible_evidence"
