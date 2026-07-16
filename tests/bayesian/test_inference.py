from __future__ import annotations

from typing import cast

import pytest

from pilot_assessment.bayesian.inference import (
    InferenceCompileError,
    InferenceEngine,
    InferencePlanError,
)
from pilot_assessment.contracts.assessment_scheme import AssessmentSchemeVersion
from pilot_assessment.contracts.bayesian import Observation, ObservationKind
from pilot_assessment.contracts.model_components import CptVersion
from pilot_assessment.model_library.repository import (
    InMemoryComponentLibraryRepository,
    VersionLibraryItem,
)
from tests.bayesian.inference_support import collider_fixture, hard_observation, two_node_fixture
from tests.schemes.support import NOW, pin, rehash, variable_ref


def test_two_node_hard_evidence_propagates_backward_and_supports_multi_query() -> None:
    fixture = two_node_fixture()
    engine = InferenceEngine(fixture.repository)
    plan = engine.compile(fixture.scheme)
    high_state = fixture.observed.ordered_observation_states[1].state_id
    observations = engine.observe(plan, (hard_observation(fixture.observed, high_state),))

    result = engine.infer(
        plan,
        observations,
        (variable_ref(fixture.root), variable_ref(fixture.observed)),
    )

    assert result.priors[0].probabilities == pytest.approx((0.6, 0.4))
    assert result.posteriors[0].probabilities == pytest.approx(
        (0.15789473684210525, 0.8421052631578948)
    )
    assert result.posteriors[1].probabilities == pytest.approx((0.0, 1.0))
    assert result.plan_hash == plan.plan_hash
    assert result.scheme_ref == plan.scheme_ref
    assert engine.compile(fixture.scheme) == plan
    assert (
        engine.infer(
            plan,
            observations,
            (variable_ref(fixture.root), variable_ref(fixture.observed)),
        )
        == result
    )


def test_collider_posterior_and_min_fill_order_are_deterministic() -> None:
    fixture = collider_fixture()
    assert fixture.other_root is not None
    engine = InferenceEngine(fixture.repository)
    plan = engine.compile(fixture.scheme)
    observed = Observation(
        variable_id=variable_ref(fixture.observed),
        kind=ObservationKind.HARD,
        hard_state_id=fixture.observed.ordered_observation_states[1].state_id,
        likelihood=None,
    )
    observation_set = engine.observe(plan, (observed,))

    result = engine.infer(
        plan,
        observation_set,
        (variable_ref(fixture.root), variable_ref(fixture.other_root)),
    )
    trace = engine.explain(plan, observation_set, (variable_ref(fixture.observed),))

    # P(C=high)=0.625; summing the matching two joint cells gives each marginal.
    assert result.posteriors[0].probabilities == pytest.approx((0.36, 0.64))
    assert result.posteriors[1].probabilities == pytest.approx((0.32, 0.68))
    assert tuple(item.version_id for item in trace.elimination_order) == (
        fixture.root.bn_node_version_id,
        fixture.other_root.bn_node_version_id,
    )


def test_compile_requires_valid_cpt_closure_and_runtime_rejects_a_forged_plan() -> None:
    fixture = two_node_fixture()
    original = cast(
        CptVersion,
        fixture.repository.get_exact(
            fixture.observed.cpt_version_id.kind,
            fixture.observed.cpt_version_id.version_id,
        ),
    )
    invalid = cast(
        CptVersion,
        rehash(
            original.model_copy(
                update={
                    "materialized_probabilities": ((0.2, 0.2), (0.3, 0.3)),
                    "content_hash": "0" * 64,
                }
            )
        ),
    )
    repository = InMemoryComponentLibraryRepository()
    for record in fixture.repository.list_records():
        item = cast(VersionLibraryItem, record.item)
        repository.add(
            invalid
            if isinstance(item, CptVersion) and item.cpt_version_id == invalid.cpt_version_id
            else item,
            recorded_at=NOW,
        )
    pins = tuple(
        pin(invalid) if reference.version_id == invalid.cpt_version_id else reference
        for reference in fixture.scheme.cpt_versions
    )
    invalid_scheme = cast(
        AssessmentSchemeVersion,
        rehash(fixture.scheme.model_copy(update={"cpt_versions": pins, "content_hash": "0" * 64})),
    )

    with pytest.raises(InferenceCompileError) as caught:
        InferenceEngine(repository).compile(invalid_scheme)
    assert caught.value.code == "cpt.row_not_normalized"

    engine = InferenceEngine(fixture.repository)
    plan = engine.compile(fixture.scheme)
    forged = plan.model_copy(update={"plan_id": "inference-plan.forged"})
    with pytest.raises(InferencePlanError) as forged_error:
        engine.observe(forged, ())
    assert forged_error.value.code == "inference.plan_hash_mismatch"
