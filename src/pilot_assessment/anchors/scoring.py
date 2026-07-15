"""Versioned, anchor-agnostic M4 evidence scoring.

Plugins own scientific measurement and anchor-specific numeric aggregation.
This module owns strict scorer-policy compilation, D/A/U classification,
breakdown status aggregation, and canonical result construction.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, NoReturn, cast

from pydantic import JsonValue, TypeAdapter, ValidationError

from pilot_assessment.anchors.fingerprint import (
    anchor_result_fingerprint_payload,
    scorer_policy_fingerprint,
    typed_json_sha256,
)
from pilot_assessment.contracts.anchor import EvidenceLikelihood, EvidenceState
from pilot_assessment.contracts.anchor_execution import ScorerPolicy
from pilot_assessment.contracts.anchor_v2 import (
    AnchorBreakdownMeasurement,
    AnchorBreakdownResult,
    AnchorCalculationStatusV2,
    AnchorMeasurement,
    AnchorResultProvenance,
    AnchorResultV2,
    ClassificationOverride,
    MetricValue,
)
from pilot_assessment.contracts.common import StableId

_EXPECTED_SCORER_ID = "hard_threshold_v1"
_EXPECTED_SCORER_VERSION = "0.1.0"
_ORDERED_POLICY_SCHEMA = "ordered-dau-threshold-policy-v0.1"
_CONJUNCTION_POLICY_SCHEMA = "dau-conjunction-policy-v0.1"
_STATE_ORDER = ("unacceptable", "adequate", "desired")
_EVALUATION_ORDER = ("desired", "adequate")
_OPERATORS = frozenset({"<", "<=", ">", ">="})
_METRIC_IDS = frozenset({"primary_value", "overshoot", "settling_time"})
_UNITS = frozenset({"Hz", "ft", "ms", "percent", "percent_full_travel", "ratio", "s"})
_STABLE_ID_ADAPTER = TypeAdapter(StableId)
_PLACEHOLDER_SHA256 = "0" * 64
_NONCOMPUTED_PRIORITY = {
    AnchorCalculationStatusV2.NOT_COMPUTABLE: 0,
    AnchorCalculationStatusV2.MISSING_INPUT: 1,
    AnchorCalculationStatusV2.DEPENDENCY_MISSING: 2,
    AnchorCalculationStatusV2.EXTRACTOR_ERROR: 3,
}


class ScoringError(ValueError):
    """Stable failure at scorer-policy or measurement interpretation boundaries."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _fail(code: str, message: str) -> NoReturn:
    raise ScoringError(code, message)


@dataclass(frozen=True, slots=True)
class _Condition:
    metric_id: str
    operator: Literal["<", "<=", ">", ">="]
    value: float
    unit: str


@dataclass(frozen=True, slots=True)
class _Rule:
    state: EvidenceState
    conditions: tuple[_Condition, ...]


@dataclass(frozen=True, slots=True)
class _CompiledPolicy:
    rules: tuple[_Rule, _Rule]
    computed_u_overrides: frozenset[str]


def _strict_sequence(value: object, *, label: str) -> Sequence[object]:
    if not isinstance(value, (list, tuple)):
        _fail("scorer_policy_invalid", f"scorer policy {label} must be an ordered array")
    return cast(Sequence[object], value)


def _strict_stable_id(value: object, *, label: str) -> str:
    try:
        return _STABLE_ID_ADAPTER.validate_python(value, strict=True)
    except ValidationError as error:
        raise ScoringError(
            "scorer_policy_invalid",
            f"scorer policy {label} must be a stable ID",
        ) from error


def _condition_from_mapping(value: object) -> _Condition:
    if not isinstance(value, Mapping) or set(value) != {
        "metric_id",
        "operator",
        "value",
        "unit",
    }:
        _fail("scorer_policy_invalid", "scorer policy condition has an invalid shape")
    condition = cast(Mapping[str, object], value)
    metric_id = _strict_stable_id(condition["metric_id"], label="metric_id")
    operator = condition["operator"]
    unit = _strict_stable_id(condition["unit"], label="unit")
    threshold = condition["value"]
    if metric_id not in _METRIC_IDS:
        _fail("scorer_policy_invalid", "scorer policy uses an unknown metric")
    if type(operator) is not str or operator not in _OPERATORS:
        _fail("scorer_policy_invalid", "scorer policy uses an unknown operator")
    if unit not in _UNITS:
        _fail("scorer_policy_invalid", "scorer policy uses an unknown unit")
    if (
        isinstance(threshold, bool)
        or not isinstance(threshold, (int, float))
        or not math.isfinite(float(threshold))
    ):
        _fail("scorer_policy_invalid", "scorer policy threshold must be finite")
    return _Condition(
        metric_id=metric_id,
        operator=cast(Literal["<", "<=", ">", ">="], operator),
        value=float(threshold),
        unit=unit,
    )


def _parse_policy_parameters(
    policy_schema_id: str,
    parameters: object,
) -> _CompiledPolicy:
    if not isinstance(parameters, Mapping) or set(parameters) != {
        "state_order",
        "evaluation_order",
        "rules",
        "fallback_state",
        "computed_u_overrides",
    }:
        _fail("scorer_policy_invalid", "scorer policy parameters have an invalid shape")
    values = cast(Mapping[str, object], parameters)
    if tuple(_strict_sequence(values["state_order"], label="state_order")) != _STATE_ORDER:
        _fail("scorer_policy_invalid", "scorer policy state order is not canonical")
    if (
        tuple(_strict_sequence(values["evaluation_order"], label="evaluation_order"))
        != _EVALUATION_ORDER
    ):
        _fail("scorer_policy_invalid", "scorer policy evaluation order is not canonical")
    if values["fallback_state"] != "unacceptable":
        _fail("scorer_policy_invalid", "scorer policy fallback state is not canonical")

    raw_overrides = _strict_sequence(values["computed_u_overrides"], label="computed_u_overrides")
    overrides = tuple(
        _strict_stable_id(value, label="computed_u_overrides item") for value in raw_overrides
    )
    if overrides != tuple(sorted(set(overrides))):
        _fail("scorer_policy_invalid", "scorer policy overrides must be unique and sorted")

    raw_rules = _strict_sequence(values["rules"], label="rules")
    if len(raw_rules) != 2:
        _fail("scorer_policy_invalid", "scorer policy requires exactly two rules")
    rules: list[_Rule] = []
    for expected_state, raw_rule in zip(_EVALUATION_ORDER, raw_rules, strict=True):
        if not isinstance(raw_rule, Mapping) or set(raw_rule) != {"state", "conditions"}:
            _fail("scorer_policy_invalid", "scorer policy rule has an invalid shape")
        rule = cast(Mapping[str, object], raw_rule)
        if rule["state"] != expected_state:
            _fail("scorer_policy_invalid", "scorer policy rules are not desired-then-adequate")
        raw_conditions = _strict_sequence(rule["conditions"], label="conditions")
        expected_count = 2 if policy_schema_id == _CONJUNCTION_POLICY_SCHEMA else 1
        if len(raw_conditions) != expected_count:
            _fail(
                "scorer_policy_invalid",
                "scorer policy condition count does not match its policy schema",
            )
        conditions = tuple(_condition_from_mapping(value) for value in raw_conditions)
        metric_ids = tuple(condition.metric_id for condition in conditions)
        if metric_ids != tuple(sorted(set(metric_ids))):
            _fail(
                "scorer_policy_invalid",
                "scorer policy condition order must be unique and canonical",
            )
        rules.append(_Rule(state=EvidenceState(expected_state), conditions=conditions))

    desired, adequate = rules
    desired_signature = tuple(
        (condition.metric_id, condition.operator, condition.unit)
        for condition in desired.conditions
    )
    adequate_signature = tuple(
        (condition.metric_id, condition.operator, condition.unit)
        for condition in adequate.conditions
    )
    if desired_signature != adequate_signature:
        _fail(
            "scorer_policy_invalid",
            "scorer policy desired and adequate conditions must address the same metrics",
        )
    for desired_condition, adequate_condition in zip(
        desired.conditions, adequate.conditions, strict=True
    ):
        if desired_condition.operator in {"<", "<="}:
            ordered = desired_condition.value <= adequate_condition.value
        else:
            ordered = desired_condition.value >= adequate_condition.value
        if not ordered:
            _fail("scorer_policy_invalid", "scorer policy thresholds are not nested")
    return _CompiledPolicy(
        rules=(rules[0], rules[1]),
        computed_u_overrides=frozenset(overrides),
    )


def _parse_policy(policy: ScorerPolicy) -> _CompiledPolicy:
    if not isinstance(policy, ScorerPolicy):
        raise TypeError("policy must be a ScorerPolicy")
    if policy.scorer_id != _EXPECTED_SCORER_ID or policy.scorer_version != _EXPECTED_SCORER_VERSION:
        _fail("scorer_policy_unsupported", "scorer policy identity is unsupported")
    if policy.policy_schema_id not in {
        _ORDERED_POLICY_SCHEMA,
        _CONJUNCTION_POLICY_SCHEMA,
    }:
        _fail("scorer_policy_unsupported", "scorer policy schema is unsupported")
    compiled = _parse_policy_parameters(policy.policy_schema_id, policy.parameters)
    if scorer_policy_fingerprint(policy) != policy.policy_hash:
        _fail("scorer_policy_fingerprint_mismatch", "scorer policy fingerprint is stale")
    return compiled


def compile_scorer_policy(annotation: Mapping[str, JsonValue]) -> ScorerPolicy:
    """Compile one exact Task 7 four-field annotation into a strict frozen policy."""

    if not isinstance(annotation, Mapping) or set(annotation) != {
        "scorer_id",
        "scorer_version",
        "policy_schema_id",
        "parameters",
    }:
        _fail("scorer_policy_invalid", "scorer policy annotation has an invalid shape")
    raw = cast(Mapping[str, object], annotation)
    scorer_id = raw["scorer_id"]
    scorer_version = raw["scorer_version"]
    policy_schema_id = raw["policy_schema_id"]
    parameters = raw["parameters"]
    if scorer_id != _EXPECTED_SCORER_ID or scorer_version != _EXPECTED_SCORER_VERSION:
        _fail("scorer_policy_unsupported", "scorer policy identity is unsupported")
    if policy_schema_id not in {_ORDERED_POLICY_SCHEMA, _CONJUNCTION_POLICY_SCHEMA}:
        _fail("scorer_policy_unsupported", "scorer policy schema is unsupported")
    assert isinstance(policy_schema_id, str)
    _parse_policy_parameters(policy_schema_id, parameters)
    if not isinstance(parameters, Mapping):  # pragma: no cover - parsed above
        _fail("scorer_policy_invalid", "scorer policy parameters must be an object")
    try:
        policy = ScorerPolicy(
            scorer_id=cast(str, scorer_id),
            scorer_version=cast(str, scorer_version),
            policy_schema_id=policy_schema_id,
            parameters=cast(dict[str, JsonValue], dict(parameters)),
            policy_hash=typed_json_sha256(
                "scorer-policy",
                "0.1.0",
                [scorer_id, scorer_version, policy_schema_id, parameters],
            ),
        )
    except (TypeError, ValidationError, ValueError) as error:
        raise ScoringError(
            "scorer_policy_invalid",
            "scorer policy annotation cannot form the strict policy contract",
        ) from error
    _parse_policy(policy)
    return policy


def validate_scorer_policy(policy: ScorerPolicy) -> None:
    """Recompute structural and fingerprint closure immediately before policy use."""

    _parse_policy(policy)


def _numeric_value(value: object, *, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        _fail("scorer_metric_invalid", f"scorer metric {label} must be finite")
    return float(value)


def _evaluate(condition: _Condition, actual: float) -> bool:
    if condition.operator == "<":
        return actual < condition.value
    if condition.operator == "<=":
        return actual <= condition.value
    if condition.operator == ">":
        return actual > condition.value
    return actual >= condition.value


def _observation(state: EvidenceState) -> tuple[EvidenceState, float, tuple[float, float, float]]:
    values = {
        EvidenceState.UNACCEPTABLE: (1.0, 0.0, 0.0),
        EvidenceState.ADEQUATE: (0.0, 1.0, 0.0),
        EvidenceState.DESIRED: (0.0, 0.0, 1.0),
    }[state]
    score = (values[1] + 2.0 * values[2]) / 2.0
    return state, score, values


def classify_computed_metrics(
    primary_value: float | None,
    raw_metrics: Mapping[str, float],
    classification_override: str | None,
    policy: ScorerPolicy,
) -> tuple[EvidenceState, float, tuple[float, float, float]]:
    """Classify finite logical metrics using one validated versioned policy."""

    compiled = _parse_policy(policy)
    if not isinstance(raw_metrics, Mapping):
        raise TypeError("raw_metrics must be a mapping")
    if classification_override is not None:
        override = _strict_stable_id(classification_override, label="override")
        if override not in compiled.computed_u_overrides:
            _fail("scorer_override_not_allowed", "classification override is not allowed")
        return _observation(EvidenceState.UNACCEPTABLE)

    values: dict[str, float] = {}
    if primary_value is not None:
        values["primary_value"] = _numeric_value(primary_value, label="primary_value")
    for raw_key, raw_value in raw_metrics.items():
        metric_id = _strict_stable_id(raw_key, label="raw metric ID")
        if metric_id == "primary_value" and primary_value is not None:
            _fail("scorer_metric_ambiguous", "raw metric cannot shadow primary_value")
        values[metric_id] = _numeric_value(raw_value, label=metric_id)

    for rule in compiled.rules:
        matches = True
        for condition in rule.conditions:
            actual = values.get(condition.metric_id)
            if actual is None:
                _fail(
                    "scorer_metric_missing",
                    f"scorer metric {condition.metric_id} is missing",
                )
            if not _evaluate(condition, actual):
                matches = False
                break
        if matches:
            return _observation(rule.state)
    return _observation(EvidenceState.UNACCEPTABLE)


def _metric_inputs(
    primary_value: MetricValue | None,
    raw_metrics: Mapping[str, MetricValue],
    policy: ScorerPolicy,
    override: ClassificationOverride | None,
) -> tuple[float | None, dict[str, float], str | None]:
    if override is not None:
        return None, {}, override.code
    compiled = _parse_policy(policy)
    required = {condition.metric_id for rule in compiled.rules for condition in rule.conditions}
    values: dict[str, float] = {}
    primary: float | None = None
    for metric_id in required:
        metric = primary_value if metric_id == "primary_value" else raw_metrics.get(metric_id)
        if metric is None:
            _fail("scorer_metric_missing", f"scorer metric {metric_id} is missing")
        expected_units = {
            condition.unit
            for rule in compiled.rules
            for condition in rule.conditions
            if condition.metric_id == metric_id
        }
        if expected_units != {metric.unit}:
            _fail(
                "scorer_metric_unit_mismatch",
                f"scorer metric {metric_id} unit does not match the policy",
            )
        numeric = float(metric.value)
        if metric_id == "primary_value":
            primary = numeric
        else:
            values[metric_id] = numeric
    return primary, values, None


def _likelihood(values: tuple[float, float, float]) -> EvidenceLikelihood:
    return EvidenceLikelihood(state_order=_STATE_ORDER, values=values)


def _score_breakdown(
    measurement: AnchorBreakdownMeasurement,
    policy: ScorerPolicy,
) -> AnchorBreakdownResult:
    if measurement.calculation_status is AnchorCalculationStatusV2.COMPUTED:
        primary, metrics, override_code = _metric_inputs(
            measurement.primary_value,
            measurement.raw_metrics,
            policy,
            measurement.classification_override_candidate,
        )
        state, score, likelihood_values = classify_computed_metrics(
            primary,
            metrics,
            override_code,
            policy,
        )
        likelihood = _likelihood(likelihood_values)
        primary_value = measurement.primary_value
        primary_value_reason = measurement.primary_value_reason
        override = measurement.classification_override_candidate
    else:
        state = None
        score = None
        likelihood = None
        primary_value = None
        primary_value_reason = None
        override = None
    return AnchorBreakdownResult(
        breakdown_id=measurement.breakdown_id,
        calculation_status=measurement.calculation_status,
        evidence_state=state,
        evidence_likelihood=likelihood,
        continuous_score=score,
        primary_value=primary_value,
        primary_value_reason=primary_value_reason,
        raw_metrics=measurement.raw_metrics,
        classification_override=override,
        trace=measurement.trace,
        diagnostics=measurement.diagnostics,
    )


def _aggregate_status(
    measurement: AnchorMeasurement,
    breakdowns: tuple[AnchorBreakdownResult, ...],
) -> AnchorCalculationStatusV2:
    if not breakdowns:
        return measurement.calculation_status
    applicable = tuple(
        item
        for item in breakdowns
        if item.calculation_status is not AnchorCalculationStatusV2.NOT_APPLICABLE
    )
    if not applicable:
        if measurement.calculation_status is not AnchorCalculationStatusV2.NOT_APPLICABLE:
            _fail(
                "scorer_measurement_aggregation_invalid",
                "all not-applicable breakdowns require a not-applicable session measurement",
            )
        return AnchorCalculationStatusV2.NOT_APPLICABLE
    noncomputed = [
        item.calculation_status
        for item in applicable
        if item.calculation_status is not AnchorCalculationStatusV2.COMPUTED
    ]
    if measurement.calculation_status in _NONCOMPUTED_PRIORITY:
        noncomputed.append(measurement.calculation_status)
    if noncomputed:
        return max(noncomputed, key=_NONCOMPUTED_PRIORITY.__getitem__)
    if measurement.calculation_status is not AnchorCalculationStatusV2.COMPUTED:
        _fail(
            "scorer_measurement_aggregation_invalid",
            "computed applicable breakdowns require a computed session measurement",
        )
    return AnchorCalculationStatusV2.COMPUTED


def _breakdown_override(
    measurement: AnchorMeasurement,
    breakdowns: tuple[AnchorBreakdownResult, ...],
) -> ClassificationOverride | None:
    candidates = tuple(
        item.classification_override
        for item in breakdowns
        if item.classification_override is not None
    )
    session_candidate = measurement.classification_override_candidate
    if (
        session_candidate is not None
        and candidates
        and session_candidate.code not in {candidate.code for candidate in candidates}
    ):
        _fail(
            "scorer_measurement_aggregation_invalid",
            "session and breakdown classification overrides disagree",
        )
    if session_candidate is not None:
        return session_candidate
    return candidates[0] if candidates else None


def score_measurement(
    measurement: AnchorMeasurement,
    policy: ScorerPolicy,
    provenance: AnchorResultProvenance,
) -> AnchorResultV2:
    """Score one immutable plugin measurement and all ordered breakdowns."""

    if not isinstance(measurement, AnchorMeasurement):
        raise TypeError("measurement must be an AnchorMeasurement")
    if not isinstance(provenance, AnchorResultProvenance):
        raise TypeError("provenance must be an AnchorResultProvenance")
    _parse_policy(policy)
    if provenance.computation_trace != measurement.trace:
        _fail(
            "scorer_provenance_mismatch",
            "result provenance computation trace must equal the measurement trace",
        )

    phase_results = tuple(_score_breakdown(item, policy) for item in measurement.phase_results)
    event_results = tuple(_score_breakdown(item, policy) for item in measurement.event_results)
    all_breakdowns = phase_results + event_results
    status = _aggregate_status(measurement, all_breakdowns)

    if status is AnchorCalculationStatusV2.COMPUTED:
        override = _breakdown_override(measurement, all_breakdowns)
        primary, metrics, override_code = _metric_inputs(
            measurement.primary_value,
            measurement.raw_metrics,
            policy,
            override,
        )
        state, score, likelihood_values = classify_computed_metrics(
            primary,
            metrics,
            override_code,
            policy,
        )
        likelihood = _likelihood(likelihood_values)
        primary_value = measurement.primary_value
        primary_value_reason = measurement.primary_value_reason
    else:
        state = None
        score = None
        likelihood = None
        override = None
        primary_value = None
        primary_value_reason = None

    draft = AnchorResultV2(
        anchor_id=measurement.anchor_id,
        calculation_status=status,
        evidence_state=state,
        evidence_likelihood=likelihood,
        continuous_score=score,
        primary_value=primary_value,
        primary_value_reason=primary_value_reason,
        classification_override=override,
        raw_metrics=measurement.raw_metrics,
        phase_results=phase_results,
        event_results=event_results,
        derived_artifacts=measurement.derived_artifacts,
        diagnostics=measurement.diagnostics,
        provenance=provenance,
        result_fingerprint=_PLACEHOLDER_SHA256,
    )
    result_data = cast(dict[str, Any], draft.model_dump(mode="python"))
    result_data["result_fingerprint"] = typed_json_sha256(
        draft.contract_id,
        draft.contract_version,
        anchor_result_fingerprint_payload(draft),
    )
    return AnchorResultV2.model_validate(result_data)


__all__ = [
    "ScoringError",
    "classify_computed_metrics",
    "compile_scorer_policy",
    "score_measurement",
    "validate_scorer_policy",
]
