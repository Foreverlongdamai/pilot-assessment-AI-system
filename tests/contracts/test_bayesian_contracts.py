from __future__ import annotations

import pytest
from pydantic import ValidationError

from pilot_assessment.contracts.bayesian import (
    BayesianDependencyEdge,
    ExtractionEdge,
    FactorScope,
    InferenceInfluenceEdge,
    InferencePlan,
    InferenceTrace,
    InferenceVariable,
    Observation,
    ObservationKind,
    ObservationSet,
    PosteriorDistribution,
    PosteriorResult,
)
from pilot_assessment.contracts.model_components import (
    ComponentIdRef,
    ComponentKind,
    PinnedComponentRef,
    VariableState,
)

SHA_A = "a" * 64
SHA_B = "b" * 64


def _ref(kind: ComponentKind, version_id: str) -> ComponentIdRef:
    return ComponentIdRef(kind=kind, version_id=version_id)


def _pinned(kind: ComponentKind, version_id: str, content_hash: str = SHA_A):
    return PinnedComponentRef(
        kind=kind,
        version_id=version_id,
        content_hash=content_hash,
    )


def _states() -> tuple[VariableState, ...]:
    return (
        VariableState(state_id="low", label="Low", description="Low state"),
        VariableState(state_id="high", label="High", description="High state"),
    )


def _plan() -> InferencePlan:
    root_id = "bn-version.root-v1"
    child_id = "binding.evidence-v1"
    return InferencePlan(
        plan_id="inference-plan.mini-v1",
        scheme_ref=_pinned(
            ComponentKind.ASSESSMENT_SCHEME_VERSION,
            "scheme.mini-v1",
        ),
        variables=(
            InferenceVariable(
                variable_id=_ref(ComponentKind.BN_NODE_VERSION, root_id),
                ordered_states=_states(),
                ordered_parent_ids=(),
                cpt_ref=_pinned(ComponentKind.CPT_VERSION, "cpt.root-v1"),
            ),
            InferenceVariable(
                variable_id=_ref(ComponentKind.EVIDENCE_BINDING_VERSION, child_id),
                ordered_states=_states(),
                ordered_parent_ids=(_ref(ComponentKind.BN_NODE_VERSION, root_id),),
                cpt_ref=_pinned(ComponentKind.CPT_VERSION, "cpt.evidence-v1", SHA_B),
            ),
        ),
        queryable_variable_ids=(
            _ref(ComponentKind.BN_NODE_VERSION, root_id),
            _ref(ComponentKind.EVIDENCE_BINDING_VERSION, child_id),
        ),
        component_refs=(
            _pinned(ComponentKind.BN_NODE_VERSION, root_id),
            _pinned(ComponentKind.EVIDENCE_BINDING_VERSION, child_id),
            _pinned(ComponentKind.CPT_VERSION, "cpt.root-v1"),
            _pinned(ComponentKind.CPT_VERSION, "cpt.evidence-v1", SHA_B),
        ),
        plan_hash=SHA_A,
    )


def test_extraction_and_bayesian_edges_are_not_interchangeable() -> None:
    extraction = ExtractionEdge(
        edge_id="edge.raw-to-evidence",
        source_descriptor_id="X.state-vector",
        target_evidence_version_id="evidence-version.trajectory-v1",
        input_binding_id="input.state",
    )
    bayesian = BayesianDependencyEdge(
        edge_id="edge.skill-to-evidence",
        parent_variable_id=_ref(ComponentKind.BN_NODE_VERSION, "bn-version.skill-v1"),
        child_variable_id=_ref(ComponentKind.EVIDENCE_BINDING_VERSION, "binding.trajectory-v1"),
    )

    assert extraction.edge_kind == "extraction"
    assert bayesian.edge_kind == "bayesian_dependency"
    with pytest.raises(ValidationError):
        ExtractionEdge.model_validate(bayesian.model_dump())
    with pytest.raises(ValidationError):
        BayesianDependencyEdge.model_validate(extraction.model_dump())
    with pytest.raises(ValidationError, match="variable"):
        BayesianDependencyEdge(
            edge_id="edge.invalid",
            parent_variable_id=_ref(ComponentKind.CPT_VERSION, "cpt.not-variable"),
            child_variable_id=_ref(ComponentKind.BN_NODE_VERSION, "bn-version.skill-v1"),
        )


def test_inference_plan_round_trips_and_rejects_duplicate_variables() -> None:
    plan = _plan()

    assert InferencePlan.model_validate_json(plan.model_dump_json()) == plan
    with pytest.raises(ValidationError, match="variable IDs"):
        InferencePlan.model_validate(
            {
                **plan.model_dump(),
                "variables": (plan.variables[0], plan.variables[0]),
            }
        )
    with pytest.raises(ValidationError, match="queryable"):
        InferencePlan.model_validate(
            {
                **plan.model_dump(),
                "queryable_variable_ids": (
                    _ref(ComponentKind.BN_NODE_VERSION, "bn-version.unknown"),
                ),
            }
        )


def test_observation_union_enforces_hard_virtual_and_omitted_shapes() -> None:
    variable = _ref(ComponentKind.EVIDENCE_BINDING_VERSION, "binding.evidence-hard-v1")
    virtual_variable = _ref(ComponentKind.EVIDENCE_BINDING_VERSION, "binding.evidence-virtual-v1")
    omitted_variable = _ref(ComponentKind.EVIDENCE_BINDING_VERSION, "binding.evidence-omitted-v1")
    hard = Observation(
        variable_id=variable,
        kind=ObservationKind.HARD,
        hard_state_id="high",
        likelihood=None,
    )
    virtual = Observation(
        variable_id=virtual_variable,
        kind=ObservationKind.VIRTUAL,
        hard_state_id=None,
        likelihood=(0.25, 0.75),
    )
    omitted = Observation(
        variable_id=omitted_variable,
        kind=ObservationKind.OMITTED,
        hard_state_id=None,
        likelihood=None,
    )
    observation_set = ObservationSet(
        plan_hash=SHA_A,
        observations=(hard, virtual, omitted),
        observation_set_hash=SHA_B,
    )

    assert ObservationSet.model_validate_json(observation_set.model_dump_json()) == observation_set
    with pytest.raises(ValidationError, match="hard observation"):
        Observation(
            variable_id=variable,
            kind=ObservationKind.HARD,
            hard_state_id=None,
            likelihood=(1.0, 0.0),
        )
    with pytest.raises(ValidationError):
        Observation(
            variable_id=variable,
            kind=ObservationKind.VIRTUAL,
            hard_state_id=None,
            likelihood=(float("nan"), 1.0),
        )
    with pytest.raises(ValidationError, match="duplicate"):
        ObservationSet(
            plan_hash=SHA_A,
            observations=(hard, hard),
            observation_set_hash=SHA_B,
        )


def test_posterior_and_trace_keep_influence_read_only_and_finite() -> None:
    scheme_ref = _pinned(ComponentKind.ASSESSMENT_SCHEME_VERSION, "scheme.mini-v1")
    root = _ref(ComponentKind.BN_NODE_VERSION, "bn-version.root-v1")
    observed = _ref(
        ComponentKind.EVIDENCE_BINDING_VERSION,
        "binding.evidence-v1",
    )
    prior = PosteriorDistribution(
        variable_id=root,
        ordered_state_ids=("low", "high"),
        probabilities=(0.5, 0.5),
    )
    posterior = PosteriorDistribution(
        variable_id=root,
        ordered_state_ids=("low", "high"),
        probabilities=(0.2, 0.8),
    )
    result = PosteriorResult(
        scheme_ref=scheme_ref,
        plan_hash=SHA_A,
        observation_set_hash=SHA_B,
        priors=(prior,),
        posteriors=(posterior,),
        result_hash="c" * 64,
    )
    influence = InferenceInfluenceEdge(
        edge_id="influence.evidence-to-root",
        observed_variable_id=observed,
        queried_variable_id=root,
        method_id="leave-one-observation-out-v1",
        l1_delta=0.6,
        canonical_path=(observed.version_id, root.version_id),
    )
    trace = InferenceTrace(
        scheme_ref=scheme_ref,
        plan_hash=SHA_A,
        observation_set_hash=SHA_B,
        query_variable_ids=(root,),
        observed_variable_ids=(observed,),
        elimination_order=(observed,),
        factor_scopes=(FactorScope(variable_ids=(root, observed)),),
        influence_edges=(influence,),
        trace_hash="d" * 64,
    )

    assert PosteriorResult.model_validate_json(result.model_dump_json()) == result
    assert InferenceTrace.model_validate_json(trace.model_dump_json()) == trace
    with pytest.raises(ValidationError, match="sum to 1"):
        PosteriorDistribution(
            variable_id=root,
            ordered_state_ids=("low", "high"),
            probabilities=(0.1, 0.1),
        )
    with pytest.raises(ValidationError):
        InferenceInfluenceEdge.model_validate({**influence.model_dump(), "l1_delta": float("inf")})
