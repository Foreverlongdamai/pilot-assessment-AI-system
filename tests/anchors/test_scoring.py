from __future__ import annotations

import copy
import json
from collections.abc import Callable, Mapping
from typing import Any, cast

import pytest
from pydantic import JsonValue

from pilot_assessment.anchors.catalog import (
    REFERENCE_ANCHOR_PARAMETER_SCHEMA_IDS,
    load_parameter_schema_bytes,
)
from pilot_assessment.anchors.fingerprint import (
    anchor_result_fingerprint_payload,
    scorer_policy_fingerprint,
    typed_json_sha256,
)
from pilot_assessment.anchors.scoring import (
    ScoringError,
    classify_computed_metrics,
    compile_scorer_policy,
    score_measurement,
    validate_scorer_policy,
)
from pilot_assessment.contracts.anchor import EvidenceState
from pilot_assessment.contracts.anchor_execution import ScorerPolicy
from pilot_assessment.contracts.anchor_v2 import (
    AnchorBreakdownMeasurement,
    AnchorCalculationStatusV2,
    AnchorMeasurement,
    AnchorResultProvenance,
    ClassificationOverride,
    ComputationTrace,
    MetricValue,
)
from pilot_assessment.contracts.errors import DomainErrorData, ErrorSeverity

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _annotation(schema_id: str) -> dict[str, Any]:
    document = json.loads(load_parameter_schema_bytes(schema_id))
    return cast(dict[str, Any], document["x-scorer-policy-default"])


def _policy(schema_id: str) -> ScorerPolicy:
    return compile_scorer_policy(_annotation(schema_id))


def _diagnostic(
    code: str = "trace-note",
    *,
    diagnostics: dict[str, JsonValue] | None = None,
) -> DomainErrorData:
    return DomainErrorData(
        error_code=code,
        severity=ErrorSeverity.INFO,
        recoverable=True,
        message="audit-only diagnostic",
        remediation="none",
        diagnostics=diagnostics or {},
    )


def _trace(*, diagnostics: tuple[DomainErrorData, ...] = ()) -> ComputationTrace:
    return ComputationTrace(
        sample_count=2,
        source_start_t_ns=0,
        source_end_t_ns=2,
        analysis_start_t_ns=0,
        analysis_end_t_ns=2,
        grid_id="grid-1",
        window_ids=("window-1",),
        interpolation_method="none",
        matching_method="direct",
        diagnostics=diagnostics,
    )


def _metric(value: float, unit: str) -> MetricValue:
    return MetricValue(scalar_kind="float", value=value, unit=unit)


def _breakdown(
    breakdown_id: str,
    *,
    status: AnchorCalculationStatusV2 = AnchorCalculationStatusV2.COMPUTED,
    primary_value: float | None = 1.0,
    unit: str = "ft",
    raw_metrics: Mapping[str, MetricValue] | None = None,
    override: str | None = None,
    diagnostics: tuple[DomainErrorData, ...] = (),
) -> AnchorBreakdownMeasurement:
    computed = status is AnchorCalculationStatusV2.COMPUTED
    metrics = dict(raw_metrics or {})
    value = _metric(primary_value, unit) if computed and primary_value is not None else None
    reason = "controlled-null-primary" if computed and value is None else None
    if computed and value is None and not metrics:
        metrics["observed_wait"] = _metric(2.0, "s")
    return AnchorBreakdownMeasurement(
        breakdown_id=breakdown_id,
        calculation_status=status,
        primary_value=value,
        primary_value_reason=reason,
        raw_metrics=metrics,
        classification_override_candidate=(
            ClassificationOverride(code=override, details={})
            if computed and override is not None
            else None
        ),
        trace=_trace(diagnostics=diagnostics),
        diagnostics=diagnostics,
    )


def _measurement(
    *,
    anchor_id: str = "O2",
    status: AnchorCalculationStatusV2 = AnchorCalculationStatusV2.COMPUTED,
    primary_value: float | None = 1.0,
    unit: str = "ft",
    raw_metrics: Mapping[str, MetricValue] | None = None,
    phase_results: tuple[AnchorBreakdownMeasurement, ...] = (),
    event_results: tuple[AnchorBreakdownMeasurement, ...] = (),
    override: str | None = None,
    diagnostics: tuple[DomainErrorData, ...] = (),
) -> AnchorMeasurement:
    computed = status is AnchorCalculationStatusV2.COMPUTED
    metrics = dict(raw_metrics or {})
    value = _metric(primary_value, unit) if computed and primary_value is not None else None
    reason = "composite-conjunction" if computed and value is None else None
    if computed and value is None and not metrics:
        metrics["observed_wait"] = _metric(2.0, "s")
    trace = _trace(diagnostics=diagnostics)
    return AnchorMeasurement(
        anchor_id=anchor_id,
        calculation_status=status,
        primary_value=value,
        primary_value_reason=reason,
        raw_metrics=metrics,
        phase_results=phase_results,
        event_results=event_results,
        classification_override_candidate=(
            ClassificationOverride(code=override, details={})
            if computed and override is not None
            else None
        ),
        source_windows=(),
        derived_artifacts=(),
        trace=trace,
        diagnostics=diagnostics,
    )


def _provenance(trace: ComputationTrace | None = None) -> AnchorResultProvenance:
    return AnchorResultProvenance(
        plugin_id="test-plugin",
        plugin_version="0.1.0",
        implementation_digest=SHA_A,
        parameter_hash=SHA_B,
        dependency_fingerprints=(SHA_C,),
        computation_trace=trace or _trace(),
    )


def _state(
    policy: ScorerPolicy,
    value: float | None,
    *,
    raw_metrics: Mapping[str, float] | None = None,
    override: str | None = None,
) -> tuple[EvidenceState, float, tuple[float, float, float]]:
    return classify_computed_metrics(
        value,
        raw_metrics or {},
        override,
        policy,
    )


def test_all_packaged_annotations_compile_to_exact_frozen_policies() -> None:
    assert len(REFERENCE_ANCHOR_PARAMETER_SCHEMA_IDS) == 18
    for schema_id in REFERENCE_ANCHOR_PARAMETER_SCHEMA_IDS:
        annotation = _annotation(schema_id)
        policy = compile_scorer_policy(annotation)

        assert policy.model_dump(mode="json", exclude={"policy_hash"}) == annotation
        assert set(policy.parameters) == {
            "state_order",
            "evaluation_order",
            "rules",
            "fallback_state",
            "computed_u_overrides",
        }
        assert policy.parameters["state_order"] == [
            "unacceptable",
            "adequate",
            "desired",
        ]
        assert policy.parameters["evaluation_order"] == ["desired", "adequate"]
        rules = cast(list[dict[str, JsonValue]], policy.parameters["rules"])
        assert [rule["state"] for rule in rules] == ["desired", "adequate"]
        overrides = cast(list[str], policy.parameters["computed_u_overrides"])
        assert overrides == sorted(set(overrides))
        assert scorer_policy_fingerprint(policy) == policy.policy_hash
        validate_scorer_policy(policy)

        with pytest.raises(TypeError):
            policy.parameters["fallback_state"] = "desired"
        with pytest.raises(TypeError):
            rules.append({"state": "desired", "conditions": []})


def _extra_top(annotation: dict[str, Any]) -> None:
    annotation["extra"] = True


def _missing_parameter(annotation: dict[str, Any]) -> None:
    del annotation["parameters"]["fallback_state"]


def _reordered_rules(annotation: dict[str, Any]) -> None:
    annotation["parameters"]["rules"].reverse()


def _reordered_conditions(annotation: dict[str, Any]) -> None:
    annotation["parameters"]["rules"][0]["conditions"].reverse()


def _missing_condition_member(annotation: dict[str, Any]) -> None:
    del annotation["parameters"]["rules"][0]["conditions"][0]["unit"]


def _unknown_operator(annotation: dict[str, Any]) -> None:
    annotation["parameters"]["rules"][0]["conditions"][0]["operator"] = "=="


def _unknown_state(annotation: dict[str, Any]) -> None:
    annotation["parameters"]["rules"][0]["state"] = "excellent"


def _unknown_metric(annotation: dict[str, Any]) -> None:
    annotation["parameters"]["rules"][0]["conditions"][0]["metric_id"] = "coverage"


def _unknown_unit(annotation: dict[str, Any]) -> None:
    annotation["parameters"]["rules"][0]["conditions"][0]["unit"] = "quality"


def _extra_parameter(annotation: dict[str, Any]) -> None:
    annotation["parameters"]["quality_gates"] = []


@pytest.mark.parametrize(
    ("schema_id", "mutate"),
    [
        ("o2-parameters-0.1", _extra_top),
        ("o2-parameters-0.1", _missing_parameter),
        ("o2-parameters-0.1", _reordered_rules),
        ("o3-parameters-0.1", _reordered_conditions),
        ("o2-parameters-0.1", _missing_condition_member),
        ("o2-parameters-0.1", _unknown_operator),
        ("o2-parameters-0.1", _unknown_state),
        ("o2-parameters-0.1", _unknown_metric),
        ("o2-parameters-0.1", _unknown_unit),
        ("o2-parameters-0.1", _extra_parameter),
    ],
    ids=(
        "extra-top",
        "missing-parameter",
        "rule-order",
        "condition-order",
        "condition-shape",
        "operator",
        "state",
        "metric",
        "unit",
        "extra-parameter",
    ),
)
def test_policy_compiler_rejects_noncanonical_shape_and_vocabulary(
    schema_id: str,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    annotation = copy.deepcopy(_annotation(schema_id))
    mutate(annotation)
    with pytest.raises(ScoringError, match="policy"):
        compile_scorer_policy(annotation)


def test_stale_policy_hash_is_rejected_before_classification() -> None:
    policy = _policy("o2-parameters-0.1").model_copy(update={"policy_hash": SHA_A})
    with pytest.raises(ScoringError, match="fingerprint"):
        validate_scorer_policy(policy)
    with pytest.raises(ScoringError, match="fingerprint"):
        _state(policy, 1.0)


@pytest.mark.parametrize(
    ("schema_id", "value", "expected_state", "expected_score", "expected_likelihood"),
    [
        ("o1-parameters-0.1", 90.0, EvidenceState.DESIRED, 1.0, (0.0, 0.0, 1.0)),
        ("o1-parameters-0.1", 70.0, EvidenceState.ADEQUATE, 0.5, (0.0, 1.0, 0.0)),
        ("o1-parameters-0.1", 69.9, EvidenceState.UNACCEPTABLE, 0.0, (1.0, 0.0, 0.0)),
        ("o2-parameters-0.1", 2.0, EvidenceState.DESIRED, 1.0, (0.0, 0.0, 1.0)),
        ("o2-parameters-0.1", 5.0, EvidenceState.ADEQUATE, 0.5, (0.0, 1.0, 0.0)),
        ("o2-parameters-0.1", 5.1, EvidenceState.UNACCEPTABLE, 0.0, (1.0, 0.0, 0.0)),
        ("o7-parameters-0.1", 1.999, EvidenceState.DESIRED, 1.0, (0.0, 0.0, 1.0)),
        ("o7-parameters-0.1", 2.0, EvidenceState.ADEQUATE, 0.5, (0.0, 1.0, 0.0)),
        ("o7-parameters-0.1", 4.0, EvidenceState.UNACCEPTABLE, 0.0, (1.0, 0.0, 0.0)),
    ],
)
def test_hard_threshold_boundaries_and_one_hot_order_are_exact(
    schema_id: str,
    value: float,
    expected_state: EvidenceState,
    expected_score: float,
    expected_likelihood: tuple[float, float, float],
) -> None:
    assert _state(_policy(schema_id), value) == (
        expected_state,
        expected_score,
        expected_likelihood,
    )


@pytest.mark.parametrize(
    ("metrics", "expected"),
    [
        ({"overshoot": 2.0, "settling_time": 3.0}, EvidenceState.DESIRED),
        ({"overshoot": 2.0, "settling_time": 4.0}, EvidenceState.ADEQUATE),
        ({"overshoot": 6.0, "settling_time": 2.0}, EvidenceState.UNACCEPTABLE),
    ],
)
def test_conjunction_requires_every_condition(
    metrics: dict[str, float], expected: EvidenceState
) -> None:
    state, _, _ = _state(_policy("o3-parameters-0.1"), None, raw_metrics=metrics)
    assert state is expected


def test_override_allowlist_forces_computed_unacceptable_before_scalar_rules() -> None:
    policy = _policy("o10-parameters-0.1")
    assert _state(policy, None, override="recovery_missed") == (
        EvidenceState.UNACCEPTABLE,
        0.0,
        (1.0, 0.0, 0.0),
    )
    with pytest.raises(ScoringError, match="override"):
        _state(policy, 1.0, override="invented_override")


def test_score_measurement_scores_breakdowns_and_fingerprints_the_complete_result() -> None:
    measurement = _measurement(
        primary_value=5.0,
        phase_results=(
            _breakdown("phase-1", primary_value=1.0),
            _breakdown("phase-2", primary_value=5.0),
        ),
    )
    provenance = _provenance(measurement.trace)
    result = score_measurement(measurement, _policy("o2-parameters-0.1"), provenance)

    assert result.evidence_state is EvidenceState.ADEQUATE
    assert result.continuous_score == 0.5
    assert [item.evidence_state for item in result.phase_results] == [
        EvidenceState.DESIRED,
        EvidenceState.ADEQUATE,
    ]
    assert result.provenance == provenance
    assert result.result_fingerprint == typed_json_sha256(
        result.contract_id,
        result.contract_version,
        anchor_result_fingerprint_payload(result),
    )


def test_breakdown_override_vetoes_a_good_session_scalar() -> None:
    event = _breakdown(
        "event-2",
        primary_value=None,
        unit="s",
        override="recovery_missed",
    )
    measurement = _measurement(
        anchor_id="O10",
        primary_value=1.0,
        unit="s",
        event_results=(event,),
    )
    result = score_measurement(
        measurement,
        _policy("o10-parameters-0.1"),
        _provenance(measurement.trace),
    )

    assert result.calculation_status is AnchorCalculationStatusV2.COMPUTED
    assert result.evidence_state is EvidenceState.UNACCEPTABLE
    assert result.classification_override is not None
    assert result.classification_override.code == "recovery_missed"
    assert result.event_results[0].evidence_state is EvidenceState.UNACCEPTABLE


def test_pooled_session_primary_is_scored_instead_of_worst_breakdown() -> None:
    measurement = _measurement(
        anchor_id="H1",
        primary_value=75.0,
        unit="percent",
        raw_metrics={
            "pooled_numerator": _metric(150.0, "s"),
            "pooled_denominator": _metric(200.0, "s"),
        },
        phase_results=(
            _breakdown("phase-1", primary_value=100.0, unit="percent"),
            _breakdown("phase-2", primary_value=50.0, unit="percent"),
        ),
    )
    result = score_measurement(
        measurement,
        _policy("h1-parameters-0.1"),
        _provenance(measurement.trace),
    )

    assert result.evidence_state is EvidenceState.ADEQUATE
    assert result.phase_results[0].evidence_state is EvidenceState.DESIRED
    assert result.phase_results[1].evidence_state is EvidenceState.UNACCEPTABLE
    assert result.raw_metrics == measurement.raw_metrics


def test_any_applicable_noncomputed_breakdown_removes_session_likelihood_by_priority() -> None:
    measurement = _measurement(
        primary_value=1.0,
        phase_results=(
            _breakdown("computed", primary_value=1.0),
            _breakdown(
                "not-computable",
                status=AnchorCalculationStatusV2.NOT_COMPUTABLE,
                primary_value=None,
            ),
            _breakdown(
                "missing",
                status=AnchorCalculationStatusV2.MISSING_INPUT,
                primary_value=None,
            ),
            _breakdown(
                "dependency",
                status=AnchorCalculationStatusV2.DEPENDENCY_MISSING,
                primary_value=None,
            ),
            _breakdown(
                "error",
                status=AnchorCalculationStatusV2.EXTRACTOR_ERROR,
                primary_value=None,
            ),
            _breakdown(
                "not-applicable",
                status=AnchorCalculationStatusV2.NOT_APPLICABLE,
                primary_value=None,
            ),
        ),
    )
    result = score_measurement(
        measurement,
        _policy("o2-parameters-0.1"),
        _provenance(measurement.trace),
    )

    assert result.calculation_status is AnchorCalculationStatusV2.EXTRACTOR_ERROR
    assert result.evidence_state is None
    assert result.evidence_likelihood is None
    assert result.continuous_score is None
    assert result.primary_value is None
    assert result.classification_override is None
    assert result.phase_results[0].evidence_state is EvidenceState.DESIRED
    assert all(item.evidence_state is None for item in result.phase_results[1:])


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (
            (
                AnchorCalculationStatusV2.NOT_COMPUTABLE,
                AnchorCalculationStatusV2.MISSING_INPUT,
                AnchorCalculationStatusV2.DEPENDENCY_MISSING,
            ),
            AnchorCalculationStatusV2.DEPENDENCY_MISSING,
        ),
        (
            (AnchorCalculationStatusV2.NOT_COMPUTABLE, AnchorCalculationStatusV2.MISSING_INPUT),
            AnchorCalculationStatusV2.MISSING_INPUT,
        ),
        (
            (AnchorCalculationStatusV2.NOT_COMPUTABLE,),
            AnchorCalculationStatusV2.NOT_COMPUTABLE,
        ),
    ],
)
def test_noncomputed_priority_is_stable(
    statuses: tuple[AnchorCalculationStatusV2, ...],
    expected: AnchorCalculationStatusV2,
) -> None:
    breakdowns = tuple(
        _breakdown(f"item-{index}", status=status, primary_value=None)
        for index, status in enumerate(statuses)
    )
    measurement = _measurement(primary_value=1.0, phase_results=breakdowns)
    result = score_measurement(
        measurement,
        _policy("o2-parameters-0.1"),
        _provenance(measurement.trace),
    )
    assert result.calculation_status is expected
    assert result.evidence_likelihood is None


def test_all_not_applicable_breakdowns_keep_the_session_not_applicable() -> None:
    measurement = _measurement(
        status=AnchorCalculationStatusV2.NOT_APPLICABLE,
        primary_value=None,
        phase_results=(
            _breakdown(
                "phase-1",
                status=AnchorCalculationStatusV2.NOT_APPLICABLE,
                primary_value=None,
            ),
        ),
    )
    result = score_measurement(
        measurement,
        _policy("o2-parameters-0.1"),
        _provenance(measurement.trace),
    )
    assert result.calculation_status is AnchorCalculationStatusV2.NOT_APPLICABLE
    assert result.evidence_state is None


def test_diagnostics_coverage_gap_sync_and_unused_metrics_cannot_change_evidence() -> None:
    first_diagnostic = _diagnostic(
        diagnostics={"coverage": 0.01, "gap_count": 99, "sync_flag": False}
    )
    second_diagnostic = _diagnostic(
        diagnostics={"coverage": 1.0, "gap_count": 0, "sync_flag": True}
    )
    first = _measurement(
        primary_value=2.0,
        raw_metrics={"coverage": _metric(0.01, "ratio")},
        diagnostics=(first_diagnostic,),
    )
    second = _measurement(
        primary_value=2.0,
        raw_metrics={"coverage": _metric(1.0, "ratio")},
        diagnostics=(second_diagnostic,),
    )

    first_result = score_measurement(first, _policy("o2-parameters-0.1"), _provenance(first.trace))
    second_result = score_measurement(
        second, _policy("o2-parameters-0.1"), _provenance(second.trace)
    )
    assert (
        first_result.evidence_state,
        first_result.evidence_likelihood,
        first_result.continuous_score,
    ) == (
        second_result.evidence_state,
        second_result.evidence_likelihood,
        second_result.continuous_score,
    )
    assert first_result.result_fingerprint != second_result.result_fingerprint


def test_metric_unit_and_inventory_mismatches_are_rejected() -> None:
    wrong_unit = _measurement(primary_value=1.0, unit="m")
    with pytest.raises(ScoringError, match="unit"):
        score_measurement(
            wrong_unit,
            _policy("o2-parameters-0.1"),
            _provenance(wrong_unit.trace),
        )

    missing_metric = _measurement(
        anchor_id="O3",
        primary_value=None,
        raw_metrics={"overshoot": _metric(1.0, "ft")},
    )
    with pytest.raises(ScoringError, match="metric"):
        score_measurement(
            missing_metric,
            _policy("o3-parameters-0.1"),
            _provenance(missing_metric.trace),
        )
