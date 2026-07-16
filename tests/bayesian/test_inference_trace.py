from __future__ import annotations

from typing import get_args

import pytest

from pilot_assessment.bayesian.inference import InferenceEngine
from pilot_assessment.contracts.bayesian import InferenceInfluenceEdge
from pilot_assessment.schemes.operations import SchemeOperation
from tests.bayesian.inference_support import (
    hard_observation,
    independent_fixture,
    two_node_fixture,
)
from tests.schemes.support import variable_ref


def test_leave_one_observation_out_delta_and_canonical_reverse_path_are_exact() -> None:
    fixture = two_node_fixture()
    engine = InferenceEngine(fixture.repository)
    plan = engine.compile(fixture.scheme)
    high_state = fixture.observed.ordered_observation_states[1].state_id
    observations = engine.observe(plan, (hard_observation(fixture.observed, high_state),))

    trace = engine.explain(plan, observations, (variable_ref(fixture.root),))

    assert len(trace.influence_edges) == 1
    edge = trace.influence_edges[0]
    assert edge.l1_delta == pytest.approx(0.8842105263157896)
    assert edge.canonical_path == (
        fixture.observed.evidence_binding_version_id,
        fixture.root.bn_node_version_id,
    )
    assert engine.explain(plan, observations, (variable_ref(fixture.root),)) == trace
    assert InferenceInfluenceEdge not in get_args(SchemeOperation)


def test_zero_delta_does_not_create_an_inference_overlay_edge() -> None:
    fixture = independent_fixture()
    assert fixture.other_root is not None
    engine = InferenceEngine(fixture.repository)
    plan = engine.compile(fixture.scheme)
    high_state = fixture.observed.ordered_observation_states[1].state_id
    observations = engine.observe(plan, (hard_observation(fixture.observed, high_state),))

    trace = engine.explain(plan, observations, (variable_ref(fixture.other_root),))

    assert trace.influence_edges == ()
