"""Exact finite-discrete Bayesian inference over immutable M5 component pins."""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypeAlias, cast

import numpy as np

from pilot_assessment.bayesian.factors import Factor, FactorError, multiply_factors
from pilot_assessment.bayesian.validation import validate_cpt
from pilot_assessment.contracts.assessment_scheme import AssessmentSchemeVersion
from pilot_assessment.contracts.bayesian import (
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
    BnNodeVersion,
    ComponentIdRef,
    ComponentKind,
    CptVersion,
    EvidenceBindingVersion,
    PinnedComponentRef,
)
from pilot_assessment.model_library.identity import typed_content_sha256
from pilot_assessment.model_library.repository import (
    ComponentLibraryRepository,
    VersionLibraryItem,
    component_content_hash,
    component_kind,
    component_record_id,
)

ZERO_HASH = "0" * 64
DEFAULT_INFLUENCE_TOLERANCE = 1e-12

VariableComponent = BnNodeVersion | EvidenceBindingVersion
HashableInferenceContract: TypeAlias = (
    InferencePlan | ObservationSet | PosteriorResult | InferenceTrace
)


class InferenceError(ValueError):
    """Base class carrying a stable machine-readable inference error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class InferenceCompileError(InferenceError):
    """Raised when exact immutable inference closure cannot be compiled."""


class InferencePlanError(InferenceError):
    """Raised when a plan is forged, stale, or not compiled by this engine."""


class ObservationValidationError(InferenceError):
    """Raised when observations do not align with the compiled state spaces."""


class QueryValidationError(InferenceError):
    """Raised when query variables are absent, duplicated, or not queryable."""


class ImpossibleEvidenceError(InferenceError):
    """Raised when supplied likelihoods have zero probability under the BN."""


@dataclass(frozen=True, slots=True)
class _CompiledNetwork:
    plan: InferencePlan
    variable_by_key: dict[str, InferenceVariable]
    reference_by_key: dict[str, ComponentIdRef]
    state_ids_by_key: dict[str, tuple[str, ...]]
    base_factors: tuple[Factor, ...]
    adjacency: dict[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class _QueryExecution:
    joint: Factor
    elimination_order: tuple[str, ...]
    factor_scopes: tuple[tuple[str, ...], ...]


def _ref_key(reference: ComponentIdRef | PinnedComponentRef) -> str:
    return f"{reference.kind.value}:{reference.version_id}"


def _pin_key(reference: PinnedComponentRef) -> tuple[ComponentKind, str]:
    return (reference.kind, reference.version_id)


def _component_ref(component: VariableComponent) -> ComponentIdRef:
    if isinstance(component, BnNodeVersion):
        return ComponentIdRef(
            kind=ComponentKind.BN_NODE_VERSION,
            version_id=component.bn_node_version_id,
        )
    return ComponentIdRef(
        kind=ComponentKind.EVIDENCE_BINDING_VERSION,
        version_id=component.evidence_binding_version_id,
    )


def _component_states(component: VariableComponent):
    return (
        component.ordered_states
        if isinstance(component, BnNodeVersion)
        else component.ordered_observation_states
    )


def _component_parents(component: VariableComponent) -> tuple[ComponentIdRef, ...]:
    return component.ordered_probabilistic_parent_ids


def _component_cpt_ref(component: VariableComponent) -> ComponentIdRef:
    return component.cpt_version_id


def _contract_hash(model: HashableInferenceContract, hash_field: str) -> str:
    contract_id = model.contract_id
    contract_version = model.contract_version
    payload = model.model_dump(mode="json", exclude={hash_field})
    return typed_content_sha256(contract_id, contract_version, payload)


def _scheme_component_refs(scheme: AssessmentSchemeVersion) -> tuple[PinnedComponentRef, ...]:
    references = (
        scheme.task_profile,
        *scheme.source_descriptors,
        *scheme.evidence_versions,
        *scheme.evidence_binding_versions,
        *scheme.bn_node_versions,
        *scheme.cpt_versions,
        scheme.reporting_policy,
        scheme.layout,
    )
    return tuple(sorted(references, key=_ref_key))


def _topology_adjacency(
    variables: Sequence[InferenceVariable],
) -> dict[str, tuple[str, ...]]:
    mutable = {_ref_key(variable.variable_id): set() for variable in variables}
    for variable in variables:
        child = _ref_key(variable.variable_id)
        for parent_reference in variable.ordered_parent_ids:
            parent = _ref_key(parent_reference)
            if parent not in mutable:
                raise InferenceCompileError(
                    "inference.parent_missing",
                    f"probabilistic parent {parent} is outside the compiled variable closure",
                )
            mutable[parent].add(child)
            mutable[child].add(parent)
    return {key: tuple(sorted(neighbors)) for key, neighbors in mutable.items()}


def _validate_acyclic(variables: Sequence[InferenceVariable]) -> None:
    children = {_ref_key(variable.variable_id): set() for variable in variables}
    indegree = dict.fromkeys(children, 0)
    for variable in variables:
        child = _ref_key(variable.variable_id)
        for parent_reference in variable.ordered_parent_ids:
            parent = _ref_key(parent_reference)
            if parent not in children:
                raise InferenceCompileError(
                    "inference.parent_missing",
                    f"probabilistic parent {parent} is outside the compiled variable closure",
                )
            if child not in children[parent]:
                children[parent].add(child)
                indegree[child] += 1
    ready = sorted(key for key, degree in indegree.items() if degree == 0)
    visited: list[str] = []
    while ready:
        current = ready.pop(0)
        visited.append(current)
        for child in sorted(children[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort()
    if len(visited) != len(variables):
        raise InferenceCompileError(
            "inference.graph_cycle",
            "Bayesian variable closure contains a directed cycle",
        )


def _minimum_fill_order(
    factors: Sequence[Factor],
    query_keys: tuple[str, ...],
) -> tuple[str, ...]:
    graph: dict[str, set[str]] = {}
    for factor in factors:
        for variable in factor.variables:
            graph.setdefault(variable, set())
        for left_index, left in enumerate(factor.variables):
            for right in factor.variables[left_index + 1 :]:
                graph[left].add(right)
                graph[right].add(left)
    protected = set(query_keys)
    candidates = set(graph) - protected
    order: list[str] = []
    while candidates:
        ranked: list[tuple[int, str]] = []
        for candidate in candidates:
            neighbors = sorted(graph[candidate])
            missing_edges = sum(
                1
                for index, left in enumerate(neighbors)
                for right in neighbors[index + 1 :]
                if right not in graph[left]
            )
            ranked.append((missing_edges, candidate))
        _, selected = min(ranked)
        neighbors = sorted(graph[selected])
        for index, left in enumerate(neighbors):
            for right in neighbors[index + 1 :]:
                graph[left].add(right)
                graph[right].add(left)
        for neighbor in neighbors:
            graph[neighbor].discard(selected)
        del graph[selected]
        candidates.remove(selected)
        order.append(selected)
    return tuple(order)


def _execute_query(
    factors: tuple[Factor, ...],
    query_keys: tuple[str, ...],
) -> _QueryExecution:
    elimination_order = _minimum_fill_order(factors, query_keys)
    working = list(factors)
    scopes: list[tuple[str, ...]] = [factor.variables for factor in working if factor.variables]
    for variable in elimination_order:
        containing = [factor for factor in working if variable in factor.variables]
        working = [factor for factor in working if variable not in factor.variables]
        if not containing:
            continue
        product = multiply_factors(containing)
        if product.variables:
            scopes.append(product.variables)
        reduced = product.sum_out(variable)
        if reduced.variables:
            scopes.append(reduced.variables)
        working.append(reduced)
    try:
        joint = multiply_factors(working).marginal(query_keys).normalize()
    except FactorError as error:
        if "zero probability mass" in str(error):
            raise ImpossibleEvidenceError(
                "inference.impossible_evidence",
                "observations have zero probability under the compiled Bayesian network",
            ) from error
        raise InferenceError("inference.factor_failure", str(error)) from error
    if joint.variables:
        scopes.append(joint.variables)
    return _QueryExecution(
        joint=joint,
        elimination_order=elimination_order,
        factor_scopes=tuple(scopes),
    )


def _distribution(
    network: _CompiledNetwork,
    joint: Factor,
    query_key: str,
) -> PosteriorDistribution:
    marginal = joint.marginal((query_key,)).normalize()
    return PosteriorDistribution(
        variable_id=network.reference_by_key[query_key],
        ordered_state_ids=network.state_ids_by_key[query_key],
        probabilities=tuple(float(value) for value in marginal.values),
    )


class InferenceEngine:
    """Compile exact component pins and perform deterministic variable elimination."""

    def __init__(
        self,
        repository: ComponentLibraryRepository,
        *,
        influence_tolerance: float = DEFAULT_INFLUENCE_TOLERANCE,
    ) -> None:
        if (
            not isinstance(influence_tolerance, (int, float))
            or isinstance(influence_tolerance, bool)
            or not np.isfinite(influence_tolerance)
            or influence_tolerance < 0.0
        ):
            raise ValueError("influence_tolerance must be finite and non-negative")
        self._repository = repository
        self._influence_tolerance = float(influence_tolerance)
        self._compiled_by_hash: dict[str, _CompiledNetwork] = {}

    def compile(self, scheme_version: AssessmentSchemeVersion) -> InferencePlan:
        if scheme_version.content_hash != component_content_hash(scheme_version):
            raise InferenceCompileError(
                "inference.scheme_hash_mismatch",
                "assessment scheme content hash does not match its immutable content",
            )
        all_refs = _scheme_component_refs(scheme_version)
        if len({_ref_key(reference) for reference in all_refs}) != len(all_refs):
            raise InferenceCompileError(
                "inference.duplicate_component_pin",
                "assessment scheme inference closure contains duplicate exact pins",
            )
        resolved: dict[tuple[ComponentKind, str], VersionLibraryItem] = {}
        for reference in all_refs:
            try:
                item = self._repository.get_exact(reference.kind, reference.version_id)
            except KeyError as error:
                raise InferenceCompileError(
                    "inference.component_missing",
                    f"exact pinned component {_ref_key(reference)} is missing",
                ) from error
            version_item = cast(VersionLibraryItem, item)
            if (
                component_kind(version_item) is not reference.kind
                or component_record_id(version_item) != reference.version_id
                or component_content_hash(version_item) != reference.content_hash
            ):
                raise InferenceCompileError(
                    "inference.component_pin_mismatch",
                    f"exact pinned component {_ref_key(reference)} does not match its hash",
                )
            resolved[_pin_key(reference)] = version_item

        variable_components: list[VariableComponent] = []
        for reference in (
            *scheme_version.bn_node_versions,
            *scheme_version.evidence_binding_versions,
        ):
            item = resolved[_pin_key(reference)]
            if not isinstance(item, (BnNodeVersion, EvidenceBindingVersion)):
                raise InferenceCompileError(
                    "inference.variable_type_mismatch",
                    f"component {_ref_key(reference)} is not a Bayesian variable",
                )
            variable_components.append(item)
        variable_components.sort(key=lambda item: _ref_key(_component_ref(item)))
        variable_catalog = {
            (_component_ref(item).kind, _component_ref(item).version_id): item
            for item in variable_components
        }

        cpt_by_id: dict[str, CptVersion] = {}
        cpt_pin_by_id: dict[str, PinnedComponentRef] = {}
        for reference in scheme_version.cpt_versions:
            item = resolved[_pin_key(reference)]
            if not isinstance(item, CptVersion):
                raise InferenceCompileError(
                    "inference.cpt_type_mismatch",
                    f"component {_ref_key(reference)} is not a CPT",
                )
            cpt_by_id[item.cpt_version_id] = item
            cpt_pin_by_id[item.cpt_version_id] = reference

        variables: list[InferenceVariable] = []
        used_cpt_ids: set[str] = set()
        base_factors: list[Factor] = []
        for component in variable_components:
            cpt_reference = _component_cpt_ref(component)
            cpt = cpt_by_id.get(cpt_reference.version_id)
            pin = cpt_pin_by_id.get(cpt_reference.version_id)
            if cpt is None or pin is None:
                raise InferenceCompileError(
                    "inference.cpt_missing",
                    f"variable {_ref_key(_component_ref(component))} has no exact selected CPT",
                )
            outcome = validate_cpt(cpt, variable_catalog)
            blocking = tuple(item for item in outcome.diagnostics if item.blocking)
            if blocking:
                first = blocking[0]
                raise InferenceCompileError(
                    first.code,
                    f"CPT {cpt.cpt_version_id}{first.location}: {first.message}",
                )
            used_cpt_ids.add(cpt.cpt_version_id)
            states = _component_states(component)
            variable = InferenceVariable(
                variable_id=_component_ref(component),
                ordered_states=states,
                ordered_parent_ids=_component_parents(component),
                cpt_ref=pin,
            )
            variables.append(variable)
            cardinalities = tuple(len(states) for states in cpt.ordered_parent_state_ids) + (
                len(cpt.child_state_ids),
            )
            factor_values = np.asarray(
                cpt.materialized_probabilities,
                dtype=np.float64,
            ).reshape(cardinalities)
            base_factors.append(
                Factor(
                    tuple(_ref_key(parent) for parent in cpt.ordered_parent_variable_ids)
                    + (_ref_key(cpt.child_variable_id),),
                    cardinalities,
                    factor_values,
                )
            )
        if used_cpt_ids != set(cpt_by_id):
            orphaned = sorted(set(cpt_by_id) - used_cpt_ids)
            raise InferenceCompileError(
                "inference.orphan_cpt",
                f"selected CPTs are not owned by variables: {', '.join(orphaned)}",
            )
        _validate_acyclic(variables)

        variable_refs = tuple(variable.variable_id for variable in variables)
        variable_keys = {_ref_key(reference) for reference in variable_refs}
        missing_outputs = tuple(
            _ref_key(reference)
            for reference in scheme_version.output_node_ids
            if _ref_key(reference) not in variable_keys
        )
        if missing_outputs:
            raise InferenceCompileError(
                "inference.output_missing",
                f"scheme outputs are outside the inference closure: {', '.join(missing_outputs)}",
            )
        scheme_ref = PinnedComponentRef(
            kind=ComponentKind.ASSESSMENT_SCHEME_VERSION,
            version_id=scheme_version.scheme_version_id,
            content_hash=scheme_version.content_hash,
        )
        provisional = InferencePlan(
            plan_id=f"inference-plan.{scheme_version.content_hash[:24]}",
            scheme_ref=scheme_ref,
            variables=tuple(variables),
            queryable_variable_ids=variable_refs,
            component_refs=all_refs,
            plan_hash=ZERO_HASH,
        )
        plan = provisional.model_copy(
            update={"plan_hash": _contract_hash(provisional, "plan_hash")}
        )
        state_ids_by_key = {
            _ref_key(variable.variable_id): tuple(
                state.state_id for state in variable.ordered_states
            )
            for variable in variables
        }
        reference_by_key = {
            _ref_key(variable.variable_id): variable.variable_id for variable in variables
        }
        network = _CompiledNetwork(
            plan=plan,
            variable_by_key={_ref_key(variable.variable_id): variable for variable in variables},
            reference_by_key=reference_by_key,
            state_ids_by_key=state_ids_by_key,
            base_factors=tuple(base_factors),
            adjacency=_topology_adjacency(variables),
        )
        self._compiled_by_hash[plan.plan_hash] = network
        return plan

    def _network(self, plan: InferencePlan) -> _CompiledNetwork:
        actual_hash = _contract_hash(plan, "plan_hash")
        if actual_hash != plan.plan_hash:
            raise InferencePlanError(
                "inference.plan_hash_mismatch",
                "inference plan hash does not match its immutable content",
            )
        network = self._compiled_by_hash.get(plan.plan_hash)
        if network is None or network.plan != plan:
            raise InferencePlanError(
                "inference.plan_not_compiled",
                "inference plan must be compiled against this engine repository",
            )
        return network

    def _validate_observations(
        self,
        network: _CompiledNetwork,
        observations: Sequence[Observation],
    ) -> tuple[Observation, ...]:
        ordered = tuple(sorted(observations, key=lambda item: _ref_key(item.variable_id)))
        keys = tuple(_ref_key(item.variable_id) for item in ordered)
        if len(keys) != len(set(keys)):
            raise ObservationValidationError(
                "inference.duplicate_observation",
                "only one observation is allowed for each exact variable",
            )
        for observation, key in zip(ordered, keys, strict=True):
            state_ids = network.state_ids_by_key.get(key)
            if state_ids is None:
                raise ObservationValidationError(
                    "inference.observation_variable_missing",
                    f"observation variable {key} is outside the compiled plan",
                )
            if observation.kind is ObservationKind.HARD:
                if observation.hard_state_id not in state_ids:
                    raise ObservationValidationError(
                        "inference.hard_state_unknown",
                        f"unknown hard state for observation variable {key}",
                    )
            elif observation.kind is ObservationKind.VIRTUAL and (
                observation.likelihood is None or len(observation.likelihood) != len(state_ids)
            ):
                raise ObservationValidationError(
                    "inference.virtual_state_order_mismatch",
                    f"virtual likelihood must align with the exact state order for {key}",
                )
        return ordered

    def observe(
        self,
        plan: InferencePlan,
        evidence_observations: Sequence[Observation],
    ) -> ObservationSet:
        network = self._network(plan)
        ordered = self._validate_observations(network, evidence_observations)
        provisional = ObservationSet(
            plan_hash=plan.plan_hash,
            observations=ordered,
            observation_set_hash=ZERO_HASH,
        )
        return provisional.model_copy(
            update={
                "observation_set_hash": _contract_hash(
                    provisional,
                    "observation_set_hash",
                )
            }
        )

    def _observation_factors(
        self,
        network: _CompiledNetwork,
        observations: Sequence[Observation],
    ) -> tuple[Factor, ...]:
        factors: list[Factor] = []
        for observation in observations:
            if observation.kind is ObservationKind.OMITTED:
                continue
            key = _ref_key(observation.variable_id)
            states = network.state_ids_by_key[key]
            if observation.kind is ObservationKind.HARD:
                values = [0.0] * len(states)
                assert observation.hard_state_id is not None
                values[states.index(observation.hard_state_id)] = 1.0
            else:
                assert observation.likelihood is not None
                values = list(observation.likelihood)
            factors.append(Factor((key,), (len(states),), values))
        return tuple(factors)

    def _validated_set(
        self,
        network: _CompiledNetwork,
        observations: ObservationSet,
    ) -> tuple[Observation, ...]:
        if observations.plan_hash != network.plan.plan_hash:
            raise ObservationValidationError(
                "inference.observation_plan_mismatch",
                "observation set belongs to a different inference plan",
            )
        actual_hash = _contract_hash(observations, "observation_set_hash")
        if actual_hash != observations.observation_set_hash:
            raise ObservationValidationError(
                "inference.observation_hash_mismatch",
                "observation set hash does not match its immutable content",
            )
        return self._validate_observations(network, observations.observations)

    def _query_keys(
        self,
        network: _CompiledNetwork,
        query_node_ids: Sequence[ComponentIdRef],
    ) -> tuple[str, ...]:
        keys = tuple(_ref_key(reference) for reference in query_node_ids)
        if not keys:
            raise QueryValidationError(
                "inference.query_empty",
                "at least one query variable is required",
            )
        if len(keys) != len(set(keys)):
            raise QueryValidationError(
                "inference.query_duplicate",
                "query variables must be unique",
            )
        queryable = {_ref_key(reference) for reference in network.plan.queryable_variable_ids}
        missing = tuple(key for key in keys if key not in queryable)
        if missing:
            raise QueryValidationError(
                "inference.query_not_available",
                f"query variables are outside the compiled plan: {', '.join(missing)}",
            )
        return keys

    def _infer_distributions(
        self,
        network: _CompiledNetwork,
        observations: tuple[Observation, ...],
        query_keys: tuple[str, ...],
    ) -> tuple[
        tuple[PosteriorDistribution, ...],
        tuple[PosteriorDistribution, ...],
        _QueryExecution,
    ]:
        prior_execution = _execute_query(network.base_factors, query_keys)
        posterior_execution = _execute_query(
            (*network.base_factors, *self._observation_factors(network, observations)),
            query_keys,
        )
        priors = tuple(
            _distribution(network, prior_execution.joint, query_key) for query_key in query_keys
        )
        posteriors = tuple(
            _distribution(network, posterior_execution.joint, query_key) for query_key in query_keys
        )
        return priors, posteriors, posterior_execution

    def infer(
        self,
        plan: InferencePlan,
        observations: ObservationSet,
        query_node_ids: Sequence[ComponentIdRef],
    ) -> PosteriorResult:
        network = self._network(plan)
        validated_observations = self._validated_set(network, observations)
        query_keys = self._query_keys(network, query_node_ids)
        priors, posteriors, _ = self._infer_distributions(
            network,
            validated_observations,
            query_keys,
        )
        provisional = PosteriorResult(
            scheme_ref=plan.scheme_ref,
            plan_hash=plan.plan_hash,
            observation_set_hash=observations.observation_set_hash,
            priors=priors,
            posteriors=posteriors,
            result_hash=ZERO_HASH,
        )
        return provisional.model_copy(
            update={"result_hash": _contract_hash(provisional, "result_hash")}
        )

    def _canonical_path(
        self,
        network: _CompiledNetwork,
        start: str,
        target: str,
    ) -> tuple[str, ...]:
        if start == target:
            version_id = network.reference_by_key[start].version_id
            return (version_id, version_id)
        queue: deque[tuple[str, tuple[str, ...]]] = deque([(start, (start,))])
        visited = {start}
        while queue:
            current, path = queue.popleft()
            for neighbor in network.adjacency[current]:
                if neighbor in visited:
                    continue
                candidate = (*path, neighbor)
                if neighbor == target:
                    return tuple(network.reference_by_key[key].version_id for key in candidate)
                visited.add(neighbor)
                queue.append((neighbor, candidate))
        raise InferenceError(
            "inference.influence_path_missing",
            f"no Bayesian path connects {start} and {target}",
        )

    def explain(
        self,
        plan: InferencePlan,
        observations: ObservationSet,
        query_node_ids: Sequence[ComponentIdRef],
    ) -> InferenceTrace:
        network = self._network(plan)
        validated_observations = self._validated_set(network, observations)
        query_keys = self._query_keys(network, query_node_ids)
        _, full_posteriors, execution = self._infer_distributions(
            network,
            validated_observations,
            query_keys,
        )
        full_by_key = {
            _ref_key(distribution.variable_id): distribution for distribution in full_posteriors
        }
        active = tuple(
            observation
            for observation in validated_observations
            if observation.kind is not ObservationKind.OMITTED
        )
        influence_edges: list[InferenceInfluenceEdge] = []
        for observation in active:
            observation_key = _ref_key(observation.variable_id)
            remaining = tuple(
                item for item in active if item.variable_id != observation.variable_id
            )
            loo_execution = _execute_query(
                (*network.base_factors, *self._observation_factors(network, remaining)),
                query_keys,
            )
            for query_key in query_keys:
                loo = _distribution(network, loo_execution.joint, query_key)
                full = full_by_key[query_key]
                delta = float(
                    np.sum(
                        np.abs(
                            np.asarray(full.probabilities, dtype=np.float64)
                            - np.asarray(loo.probabilities, dtype=np.float64)
                        ),
                        dtype=np.float64,
                    )
                )
                if delta <= self._influence_tolerance:
                    continue
                edge_digest = typed_content_sha256(
                    "inference-influence-edge",
                    "0.1.0",
                    {
                        "plan_hash": plan.plan_hash,
                        "observation_set_hash": observations.observation_set_hash,
                        "observed": observation_key,
                        "queried": query_key,
                    },
                )
                influence_edges.append(
                    InferenceInfluenceEdge(
                        edge_id=f"influence.{edge_digest[:24]}",
                        observed_variable_id=observation.variable_id,
                        queried_variable_id=network.reference_by_key[query_key],
                        method_id="leave-one-observation-out-v1",
                        l1_delta=min(2.0, max(0.0, delta)),
                        canonical_path=self._canonical_path(
                            network,
                            observation_key,
                            query_key,
                        ),
                    )
                )
        factor_scopes = tuple(
            FactorScope(
                variable_ids=tuple(network.reference_by_key[key] for key in scope),
            )
            for scope in execution.factor_scopes
            if scope
        )
        provisional = InferenceTrace(
            scheme_ref=plan.scheme_ref,
            plan_hash=plan.plan_hash,
            observation_set_hash=observations.observation_set_hash,
            query_variable_ids=tuple(network.reference_by_key[key] for key in query_keys),
            observed_variable_ids=tuple(observation.variable_id for observation in active),
            elimination_order=tuple(
                network.reference_by_key[key] for key in execution.elimination_order
            ),
            factor_scopes=factor_scopes,
            influence_edges=tuple(influence_edges),
            trace_hash=ZERO_HASH,
        )
        return provisional.model_copy(
            update={"trace_hash": _contract_hash(provisional, "trace_hash")}
        )


__all__ = [
    "DEFAULT_INFLUENCE_TOLERANCE",
    "ImpossibleEvidenceError",
    "InferenceCompileError",
    "InferenceEngine",
    "InferenceError",
    "InferencePlanError",
    "ObservationValidationError",
    "QueryValidationError",
]
