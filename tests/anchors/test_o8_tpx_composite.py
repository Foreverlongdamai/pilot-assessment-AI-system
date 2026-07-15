from __future__ import annotations

from dataclasses import dataclass

import pytest

from pilot_assessment.anchors.catalog import load_parameter_schema
from pilot_assessment.anchors.plugins.o8_tpx_composite import (
    compute_tpx_composite,
    create_plugin,
)
from pilot_assessment.anchors.protocols import (
    AnchorPluginContext,
    ProjectedSemanticScope,
    ResolvedDependencies,
    TabularArtifactPayload,
)
from pilot_assessment.anchors.scoring import classify_computed_metrics, compile_scorer_policy
from pilot_assessment.contracts.anchor import EvidenceLikelihood, EvidenceState
from pilot_assessment.contracts.anchor_v2 import (
    AnchorArtifactRef,
    AnchorCalculationStatusV2,
    AnchorResultProvenance,
    AnchorResultV2,
    ComputationTrace,
    MetricValue,
)
from pilot_assessment.contracts.synchronization import SessionWindow

SHA_A = "a" * 64
SHA_B = "b" * 64


def _trace() -> ComputationTrace:
    return ComputationTrace(
        sample_count=1,
        source_start_t_ns=0,
        source_end_t_ns=1_000_000_000,
        analysis_start_t_ns=0,
        analysis_end_t_ns=1_000_000_000,
        grid_id=None,
        window_ids=(),
        interpolation_method=None,
        matching_method="test-source-v1",
        diagnostics=(),
    )


def _result(
    anchor_id: str,
    value: float | None,
    unit: str,
    state: EvidenceState | None,
    fingerprint: str,
    *,
    status: AnchorCalculationStatusV2 = AnchorCalculationStatusV2.COMPUTED,
) -> AnchorResultV2:
    scores = {
        EvidenceState.UNACCEPTABLE: (0.0, (1.0, 0.0, 0.0)),
        EvidenceState.ADEQUATE: (0.5, (0.0, 1.0, 0.0)),
        EvidenceState.DESIRED: (1.0, (0.0, 0.0, 1.0)),
    }
    score, likelihood = (None, None) if state is None else scores[state]
    return AnchorResultV2(
        anchor_id=anchor_id,
        calculation_status=status,
        evidence_state=state,
        evidence_likelihood=(
            None
            if likelihood is None
            else EvidenceLikelihood(
                state_order=("unacceptable", "adequate", "desired"), values=likelihood
            )
        ),
        continuous_score=score,
        primary_value=(
            None if value is None else MetricValue(scalar_kind="float", value=value, unit=unit)
        ),
        primary_value_reason=None,
        classification_override=None,
        raw_metrics={},
        phase_results=(),
        event_results=(),
        derived_artifacts=(),
        diagnostics=(),
        provenance=AnchorResultProvenance(
            plugin_id=f"{anchor_id.lower()}-test-plugin",
            plugin_version="0.1.0",
            implementation_digest=fingerprint,
            parameter_hash=fingerprint,
            dependency_fingerprints=(),
            computation_trace=_trace(),
        ),
        result_fingerprint=fingerprint,
    )


def _dependencies(
    *,
    precision_percent: float = 80.0,
    workload_ratio: float = 1.0,
    precision_state: EvidenceState = EvidenceState.DESIRED,
    workload_state: EvidenceState = EvidenceState.DESIRED,
) -> ResolvedDependencies:
    return ResolvedDependencies(
        results={
            "o1-result": _result("O1", precision_percent, "percent", precision_state, SHA_A),
            "o5-result": _result("O5", workload_ratio, "ratio", workload_state, SHA_B),
        },
        artifacts={},
        algorithm_profiles={},
        preprocessing={},
    )


def _context() -> AnchorPluginContext:
    return AnchorPluginContext(
        session_id="session-1",
        session_window=SessionWindow(
            end_t_ns=1_000_000_000, source="master-clock-x-mapped-coverage-v1"
        ),
        streams={},
        context={},
        references={},
        semantic_scope=ProjectedSemanticScope(values={}),
    )


@dataclass
class _Emitter:
    payloads: list[tuple[str, TabularArtifactPayload]]

    def stage_table(self, artifact_id: str, payload: TabularArtifactPayload) -> AnchorArtifactRef:
        self.payloads.append((artifact_id, payload))
        return AnchorArtifactRef(
            artifact_id=artifact_id,
            kind=payload.artifact_kind,
            schema_id=payload.schema_id,
            logical_content_sha256=SHA_A,
            storage_file_sha256=None,
            row_count=payload.frame.height,
            start_t_ns=payload.start_t_ns,
            end_t_ns=payload.end_t_ns,
            grid_hash=payload.grid_hash,
            producer_anchor_id="O8",
            producer_plugin_id="o8-tpx-composite",
            producer_plugin_version="0.1.0",
            parameter_hash=SHA_A,
            dependency_fingerprints=(SHA_A, SHA_B),
        )

    def stage_blob(self, artifact_id, payload):  # pragma: no cover - O8 is table-only
        raise AssertionError((artifact_id, payload))


def _compute(dependencies: ResolvedDependencies):
    emitter = _Emitter([])
    measurement = create_plugin().compute(_context(), {}, {}, dependencies, emitter)
    return measurement, emitter


def _state(value: float) -> EvidenceState:
    annotation = load_parameter_schema("o8-parameters-0.1")["x-scorer-policy-default"]
    assert isinstance(annotation, dict)
    state, _score, _likelihood = classify_computed_metrics(
        value, {}, None, compile_scorer_policy(annotation)
    )
    return state


def test_o8_definition_declares_only_the_two_typed_result_dependencies() -> None:
    definition = create_plugin().definition()

    assert definition.anchor_id == "O8"
    assert definition.required_streams == ()
    assert definition.required_context_paths == ()
    assert tuple(item.dependency_id for item in definition.dependencies) == (
        "o1-result",
        "o5-result",
    )
    assert definition.artifact_recipes[0].artifact_id == "tpx-component-trace"


@pytest.mark.parametrize(
    ("precision", "workload", "precision_state", "workload_state", "expected_tpx", "state"),
    (
        (80.0, 1.0, EvidenceState.DESIRED, EvidenceState.ADEQUATE, 0.64, EvidenceState.DESIRED),
        (70.0, 1.0, EvidenceState.ADEQUATE, EvidenceState.DESIRED, 0.49, EvidenceState.ADEQUATE),
        (
            50.0,
            1.0,
            EvidenceState.UNACCEPTABLE,
            EvidenceState.UNACCEPTABLE,
            0.25,
            EvidenceState.UNACCEPTABLE,
        ),
    ),
)
def test_o8_uses_computed_metrics_even_when_upstream_evidence_is_unacceptable(
    precision: float,
    workload: float,
    precision_state: EvidenceState,
    workload_state: EvidenceState,
    expected_tpx: float,
    state: EvidenceState,
) -> None:
    measurement, _emitter = _compute(
        _dependencies(
            precision_percent=precision,
            workload_ratio=workload,
            precision_state=precision_state,
            workload_state=workload_state,
        )
    )

    assert measurement.calculation_status is AnchorCalculationStatusV2.COMPUTED
    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(expected_tpx)
    assert _state(measurement.primary_value.value) is state


def test_o8_formula_and_scorer_lock_exact_point_four_and_point_six_boundaries() -> None:
    adequate_boundary = compute_tpx_composite(100.0, 6.25)
    desired_boundary = compute_tpx_composite(100.0, 25.0 / 9.0)

    assert adequate_boundary == pytest.approx(0.4)
    assert desired_boundary == pytest.approx(0.6)
    assert _state(adequate_boundary) is EvidenceState.ADEQUATE
    assert _state(desired_boundary) is EvidenceState.DESIRED
    assert _state(0.4 - 1e-12) is EvidenceState.UNACCEPTABLE
    assert _state(0.6 - 1e-12) is EvidenceState.ADEQUATE


def test_o8_formula_defined_clip_bounds_extreme_finite_inputs_without_a_quality_gate() -> None:
    assert compute_tpx_composite(200.0, 0.0) == pytest.approx(1.0)
    assert 0.0 <= compute_tpx_composite(100.0, 1e308) <= 1.0
    assert compute_tpx_composite(0.0, 1.0) == pytest.approx(0.0)


def test_o8_noncomputed_upstream_result_is_dependency_missing() -> None:
    dependencies = _dependencies()
    missing_o5 = _result(
        "O5",
        None,
        "ratio",
        None,
        SHA_B,
        status=AnchorCalculationStatusV2.MISSING_INPUT,
    )
    dependencies = ResolvedDependencies(
        results={**dependencies.results, "o5-result": missing_o5},
        artifacts={},
        algorithm_profiles={},
        preprocessing={},
    )

    measurement, emitter = _compute(dependencies)

    assert measurement.calculation_status is AnchorCalculationStatusV2.DEPENDENCY_MISSING
    assert measurement.primary_value is None
    assert measurement.derived_artifacts == ()
    assert measurement.diagnostics[0].error_code == "anchor.o8.dependency_missing"
    assert emitter.payloads == []


def test_o8_component_trace_references_canonical_upstream_result_identity() -> None:
    measurement, emitter = _compute(
        _dependencies(
            precision_state=EvidenceState.ADEQUATE,
            workload_state=EvidenceState.UNACCEPTABLE,
        )
    )

    assert len(emitter.payloads) == 1
    artifact_id, payload = emitter.payloads[0]
    assert artifact_id == "tpx-component-trace"
    assert payload.schema_id == "tpx-component-trace-v0.1"
    assert payload.order_keys == ("component_id",)
    assert payload.frame.to_dicts() == [
        {
            "component_id": "o1-result",
            "source_anchor_id": "O1",
            "source_result_fingerprint": SHA_A,
            "state": "adequate",
            "score": 0.5,
        },
        {
            "component_id": "o5-result",
            "source_anchor_id": "O5",
            "source_result_fingerprint": SHA_B,
            "state": "unacceptable",
            "score": 0.0,
        },
    ]
    assert len(measurement.derived_artifacts) == 1
    assert measurement.derived_artifacts[0].artifact_id == "tpx-component-trace"
    assert measurement.raw_metrics["precision-percent"].value == pytest.approx(80.0)
    assert measurement.raw_metrics["workload-ratio"].value == pytest.approx(1.0)
