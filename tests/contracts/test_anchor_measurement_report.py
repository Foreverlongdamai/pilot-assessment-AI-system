from __future__ import annotations

import json
import math
import warnings
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, fields, replace
from inspect import signature
from pathlib import Path
from typing import Any, get_origin, get_type_hints

import polars as pl
import pytest
from pydantic import ValidationError

from pilot_assessment.anchors.models import ResolvedReference
from pilot_assessment.anchors.protocols import (
    AnchorArtifactEmitter,
    AnchorPlugin,
    AnchorPluginContext,
    ArtifactProducer,
    BlobArtifactPayload,
    PreprocessingArtifactIdentity,
    PreprocessingProducer,
    PreprocessingProvider,
    PreprocessingScope,
    ProjectedSemanticScope,
    ReadOnlyBlobPayload,
    ReadOnlyTabularPayload,
    ResolvedArtifactDependency,
    ResolvedDependencies,
    ResolvedPreprocessingDependency,
    TabularArtifactPayload,
)
from pilot_assessment.contracts.anchor import EvidenceLikelihood, EvidenceState
from pilot_assessment.contracts.anchor_execution import (
    AnchorCapabilityStatus,
    AnchorEvaluationDisposition,
    AnchorEvaluationReport,
    AnchorInventoryItem,
    AnchorInventoryStatus,
    AnchorPlanStatus,
    ReferenceResolutionStatus,
    ResolvedAlgorithmProfile,
    ResolvedReferenceDescriptor,
    ScientificValidationStatus,
)
from pilot_assessment.contracts.anchor_v2 import (
    AnchorArtifactRef,
    AnchorBreakdownMeasurement,
    AnchorCalculationStatusV2,
    AnchorMeasurement,
    AnchorResultProvenance,
    AnchorResultV2,
    ClassificationOverride,
    ComputationTrace,
    MetricValue,
)
from pilot_assessment.contracts.errors import DomainErrorData
from pilot_assessment.contracts.synchronization import SessionWindow
from pilot_assessment.synchronization.models import AlignedStreamView

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "anchor_evaluation_report_ready.json"


def _trace() -> ComputationTrace:
    return ComputationTrace(
        sample_count=1,
        source_start_t_ns=0,
        source_end_t_ns=1,
        analysis_start_t_ns=0,
        analysis_end_t_ns=1,
        grid_id="grid-1",
        window_ids=("window-1",),
        interpolation_method="none",
        matching_method="direct",
        diagnostics=(),
    )


def _metric(value: float = 1.0) -> MetricValue:
    return MetricValue(scalar_kind="float", value=value, unit="m")


def _result(
    anchor_id: str,
    status: AnchorCalculationStatusV2 = AnchorCalculationStatusV2.COMPUTED,
    *,
    fingerprint: str = SHA_A,
) -> AnchorResultV2:
    computed = status is AnchorCalculationStatusV2.COMPUTED
    return AnchorResultV2(
        anchor_id=anchor_id,
        calculation_status=status,
        evidence_state=EvidenceState.UNACCEPTABLE if computed else None,
        evidence_likelihood=(
            EvidenceLikelihood(
                state_order=("unacceptable", "adequate", "desired"),
                values=(1.0, 0.0, 0.0),
            )
            if computed
            else None
        ),
        continuous_score=0.0 if computed else None,
        primary_value=_metric() if computed else None,
        primary_value_reason=None,
        classification_override=None,
        raw_metrics={"error": _metric()} if computed else {},
        phase_results=(),
        event_results=(),
        derived_artifacts=(),
        diagnostics=(),
        provenance=AnchorResultProvenance(
            plugin_id=f"{anchor_id.lower()}-plugin",
            plugin_version="0.1.0",
            implementation_digest=SHA_B,
            parameter_hash=SHA_C,
            dependency_fingerprints=(),
            computation_trace=_trace(),
        ),
        result_fingerprint=fingerprint,
    )


def _inventory(result: AnchorResultV2) -> AnchorInventoryItem:
    return AnchorInventoryItem(
        anchor_id=result.anchor_id,
        capability_status=AnchorCapabilityStatus.AVAILABLE,
        evaluation_status=AnchorInventoryStatus.EXECUTED,
        result_fingerprint=result.result_fingerprint,
        global_block_reason=None,
        diagnostics=(),
    )


def _report(
    results: tuple[AnchorResultV2, ...],
    *,
    disposition: AnchorEvaluationDisposition | None = None,
) -> AnchorEvaluationReport:
    applicable = sum(
        result.calculation_status is not AnchorCalculationStatusV2.NOT_APPLICABLE
        for result in results
    )
    computed = sum(
        result.calculation_status is AnchorCalculationStatusV2.COMPUTED for result in results
    )
    inferred_disposition = (
        AnchorEvaluationDisposition.READY
        if computed == applicable
        else AnchorEvaluationDisposition.READY_PARTIAL
    )
    return AnchorEvaluationReport(
        session_id="session-1",
        disposition=disposition or inferred_disposition,
        inventory=tuple(_inventory(result) for result in results),
        results=results,
        expected_count=len(results),
        executed_count=len(results),
        applicable_count=applicable,
        computed_count=computed,
        raw_availability=None if applicable == 0 else computed / applicable,
        catalog_fingerprint=SHA_A,
        registry_fingerprint=SHA_B,
        execution_plan_fingerprint=SHA_C,
        evaluation_fingerprint=SHA_D,
        scientific_validation_status=ScientificValidationStatus.NOT_SUPPORTED,
        diagnostics=(),
    )


def test_status_namespaces_and_public_contract_fields_are_exact() -> None:
    assert {item.value for item in AnchorCapabilityStatus} == {
        "available",
        "plugin_unavailable",
        "not_implemented",
        "incompatible",
    }
    assert {item.value for item in AnchorPlanStatus} == {"compiled", "blocked"}
    assert {item.value for item in AnchorInventoryStatus} == {"executed", "not_attempted"}
    assert {item.value for item in AnchorEvaluationDisposition} == {
        "ready",
        "ready_partial",
        "blocked",
    }
    assert set(AnchorBreakdownMeasurement.model_fields) == {
        "breakdown_id",
        "calculation_status",
        "primary_value",
        "primary_value_reason",
        "raw_metrics",
        "classification_override_candidate",
        "trace",
        "diagnostics",
    }
    assert set(AnchorMeasurement.model_fields) == {
        "contract_id",
        "contract_version",
        "anchor_id",
        "calculation_status",
        "primary_value",
        "primary_value_reason",
        "raw_metrics",
        "phase_results",
        "event_results",
        "classification_override_candidate",
        "source_windows",
        "derived_artifacts",
        "trace",
        "diagnostics",
    }
    assert set(AnchorInventoryItem.model_fields) == {
        "anchor_id",
        "capability_status",
        "evaluation_status",
        "result_fingerprint",
        "global_block_reason",
        "diagnostics",
    }
    assert set(AnchorEvaluationReport.model_fields) == {
        "contract_id",
        "contract_version",
        "session_id",
        "disposition",
        "inventory",
        "results",
        "expected_count",
        "executed_count",
        "applicable_count",
        "computed_count",
        "raw_availability",
        "catalog_fingerprint",
        "registry_fingerprint",
        "execution_plan_fingerprint",
        "evaluation_fingerprint",
        "formal_run_authorized",
        "scientific_validation_status",
        "diagnostics",
    }


def test_measurement_status_matrix_preserves_negative_observations_without_quality_gate() -> None:
    computed = AnchorMeasurement(
        anchor_id="O1",
        calculation_status="computed",
        primary_value=None,
        primary_value_reason="capture_missed",
        raw_metrics={"observed_wait": _metric(10.0)},
        phase_results=(),
        event_results=(),
        classification_override_candidate=ClassificationOverride(code="capture_missed", details={}),
        source_windows=(),
        derived_artifacts=(),
        trace=_trace(),
        diagnostics=(),
    )
    assert computed.calculation_status is AnchorCalculationStatusV2.COMPUTED
    assert computed.primary_value is None

    with pytest.raises(ValidationError):
        AnchorMeasurement.model_validate(
            {
                **computed.model_dump(),
                "calculation_status": "missing_input",
                "classification_override_candidate": {"code": "capture_missed"},
            }
        )
    with pytest.raises(ValidationError):
        AnchorMeasurement.model_validate(
            {
                **computed.model_dump(),
                "primary_value_reason": None,
                "raw_metrics": {},
            }
        )
    with pytest.raises(ValidationError):
        AnchorMeasurement.model_validate({**computed.model_dump(), "invalid_quality": True})


def test_measurement_result_and_override_maps_cannot_mutate_after_validation() -> None:
    override = ClassificationOverride(code="capture_missed", details={"nested": {"observed": True}})
    measurement = AnchorMeasurement(
        anchor_id="O1",
        calculation_status="computed",
        primary_value=_metric(),
        primary_value_reason=None,
        raw_metrics={"error": _metric()},
        phase_results=(),
        event_results=(),
        classification_override_candidate=override,
        source_windows=(),
        derived_artifacts=(),
        trace=_trace(),
        diagnostics=(),
    )
    result = _result("O1")
    with pytest.raises(TypeError):
        measurement.raw_metrics["late"] = _metric()  # type: ignore[index]
    with pytest.raises(TypeError):
        result.raw_metrics["late"] = _metric()  # type: ignore[index]
    with pytest.raises(TypeError):
        override.details["late"] = True  # type: ignore[index]
    nested = override.details["nested"]
    assert isinstance(nested, Mapping)
    with pytest.raises(TypeError):
        nested["late"] = True  # type: ignore[index]


def test_breakdown_measurements_are_typed() -> None:
    breakdown = AnchorBreakdownMeasurement(
        breakdown_id="phase-1",
        calculation_status="computed",
        primary_value=_metric(),
        primary_value_reason=None,
        raw_metrics={"error": _metric()},
        classification_override_candidate=None,
        trace=_trace(),
        diagnostics=(),
    )
    measurement = AnchorMeasurement(
        anchor_id="O1",
        calculation_status="computed",
        primary_value=_metric(),
        primary_value_reason=None,
        raw_metrics={"error": _metric()},
        phase_results=(breakdown,),
        event_results=(),
        classification_override_candidate=None,
        source_windows=(),
        derived_artifacts=(),
        trace=_trace(),
        diagnostics=(),
    )
    assert measurement.phase_results == (breakdown,)


def test_inventory_status_matrix_is_closed() -> None:
    result = _result("O1")
    assert _inventory(result).result_fingerprint == result.result_fingerprint
    blocked = AnchorInventoryItem(
        anchor_id="O1",
        capability_status="incompatible",
        evaluation_status="not_attempted",
        result_fingerprint=None,
        global_block_reason="registry_incompatible",
        diagnostics=(),
    )
    assert blocked.global_block_reason == "registry_incompatible"
    for update in (
        {"result_fingerprint": SHA_A},
        {"global_block_reason": None},
    ):
        with pytest.raises(ValidationError):
            AnchorInventoryItem.model_validate({**blocked.model_dump(), **update})
    with pytest.raises(ValidationError):
        AnchorInventoryItem.model_validate(
            {
                **_inventory(result).model_dump(),
                "capability_status": "not_implemented",
            }
        )


def test_ready_report_exposes_canonical_exact_18_results_for_m5() -> None:
    ids = tuple(f"O{index}" for index in range(1, 14)) + tuple(f"H{index}" for index in range(1, 6))
    results = tuple(
        _result(anchor_id, fingerprint=f"{index:064x}")
        for index, anchor_id in enumerate(ids, start=1)
    )
    report = _report(results)
    assert report.disposition is AnchorEvaluationDisposition.READY
    assert tuple(result.anchor_id for result in report.results) == ids
    assert report.computed_count == report.applicable_count == 18
    assert report.raw_availability == 1.0
    assert report.formal_run_authorized is False


def test_computed_unacceptable_counts_as_available_evidence() -> None:
    report = _report((_result("O1"),))
    assert report.results[0].evidence_state is EvidenceState.UNACCEPTABLE
    assert report.computed_count == report.applicable_count == 1
    assert report.raw_availability == 1.0


def test_not_applicable_is_excluded_and_zero_denominator_is_null() -> None:
    report = _report((_result("O1", AnchorCalculationStatusV2.NOT_APPLICABLE),))
    assert report.disposition is AnchorEvaluationDisposition.READY
    assert report.applicable_count == report.computed_count == 0
    assert report.raw_availability is None


def test_ready_partial_has_complete_results_but_lower_raw_availability() -> None:
    report = _report(
        (
            _result("O1"),
            _result("O2", AnchorCalculationStatusV2.MISSING_INPUT, fingerprint=SHA_B),
        )
    )
    assert report.disposition is AnchorEvaluationDisposition.READY_PARTIAL
    assert report.expected_count == report.executed_count == len(report.results) == 2
    assert report.applicable_count == 2
    assert report.computed_count == 1
    assert report.raw_availability == 0.5


def test_blocked_report_has_expected_inventory_without_fabricated_results() -> None:
    inventory = tuple(
        AnchorInventoryItem(
            anchor_id=anchor_id,
            capability_status="incompatible",
            evaluation_status="not_attempted",
            result_fingerprint=None,
            global_block_reason="plan_blocked",
            diagnostics=(),
        )
        for anchor_id in ("O1", "O2")
    )
    report = AnchorEvaluationReport(
        session_id="session-1",
        disposition="blocked",
        inventory=inventory,
        results=(),
        expected_count=2,
        executed_count=0,
        applicable_count=0,
        computed_count=0,
        raw_availability=None,
        catalog_fingerprint=SHA_A,
        registry_fingerprint=SHA_B,
        execution_plan_fingerprint=SHA_C,
        evaluation_fingerprint=SHA_D,
        scientific_validation_status="not_supported",
        diagnostics=(),
    )
    assert report.results == ()
    assert all(
        item.evaluation_status is AnchorInventoryStatus.NOT_ATTEMPTED for item in report.inventory
    )


@pytest.mark.parametrize(
    "update",
    [
        {"expected_count": 2},
        {"executed_count": 0},
        {"applicable_count": 0},
        {"computed_count": 0},
        {"raw_availability": 0.0},
        {"disposition": "blocked"},
    ],
)
def test_report_recomputes_cardinality_disposition_and_availability(
    update: dict[str, object],
) -> None:
    report = _report((_result("O1"),))
    with pytest.raises(ValidationError):
        AnchorEvaluationReport.model_validate({**report.model_dump(), **update})


def test_report_inventory_and_results_are_one_to_one_in_canonical_order() -> None:
    first = _result("O1", fingerprint=SHA_A)
    second = _result("O2", fingerprint=SHA_B)
    report = _report((first, second))
    with pytest.raises(ValidationError):
        AnchorEvaluationReport.model_validate({**report.model_dump(), "results": (second, first)})
    with pytest.raises(ValidationError):
        AnchorEvaluationReport.model_validate(
            {
                **report.model_dump(),
                "inventory": (report.inventory[0], report.inventory[0]),
            }
        )

    stale = report.inventory[0].model_copy(update={"result_fingerprint": SHA_C})
    with pytest.raises(ValidationError):
        AnchorEvaluationReport.model_validate(
            {**report.model_dump(), "inventory": (stale, report.inventory[1])}
        )

    duplicate_fingerprint_results = (
        first,
        _result("O2", fingerprint=first.result_fingerprint),
    )
    with pytest.raises(ValidationError):
        _report(duplicate_fingerprint_results)


def test_nonblocked_reports_execute_every_inventory_item_and_never_authorize_formal_run() -> None:
    report = _report((_result("O1"),))
    not_attempted = AnchorInventoryItem(
        anchor_id="O1",
        capability_status="available",
        evaluation_status="not_attempted",
        result_fingerprint=None,
        global_block_reason="unexpected_skip",
        diagnostics=(),
    )
    with pytest.raises(ValidationError):
        AnchorEvaluationReport.model_validate(
            {
                **report.model_dump(),
                "inventory": (not_attempted,),
                "executed_count": 0,
                "results": (),
                "computed_count": 0,
                "raw_availability": 0.0,
            }
        )
    with pytest.raises(ValidationError):
        AnchorEvaluationReport.model_validate(
            {**report.model_dump(), "formal_run_authorized": True}
        )


def test_public_ready_report_fixture_round_trips() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    report = AnchorEvaluationReport.model_validate(payload)
    assert report.model_dump(mode="json") == payload
    assert report.disposition is AnchorEvaluationDisposition.READY
    assert len(report.results) == len(report.inventory) == 18
    assert report.scientific_validation_status is ScientificValidationStatus.NOT_SUPPORTED


def _descriptor() -> dict[str, object]:
    return {
        "type": "table",
        "fields": [
            {"name": "t_ns", "dtype": "i64", "unit": "ns", "nullable": False},
            {"name": "value", "dtype": "f64", "unit": "m", "nullable": False},
        ],
        "canonical_order_keys": ["t_ns"],
    }


def _artifact_ref() -> AnchorArtifactRef:
    return AnchorArtifactRef(
        artifact_id="trace",
        kind="sample_mask",
        schema_id="trace-v0.1",
        logical_content_sha256=SHA_A,
        storage_file_sha256=None,
        row_count=1,
        start_t_ns=0,
        end_t_ns=1,
        grid_hash=SHA_B,
        producer_anchor_id="O1",
        producer_plugin_id="o1-plugin",
        producer_plugin_version="0.1.0",
        parameter_hash=SHA_C,
        dependency_fingerprints=(),
    )


def test_runtime_context_and_dependency_maps_are_positive_read_only_projections() -> None:
    projected_context: dict[str, object] = {"context.flight_mode": "hover"}
    scope_values: dict[str, object] = {"semantic.phases": ("phase-1",)}
    source_frame = pl.DataFrame({"t_ns": [0], "value": [1.0]})
    source_view = AlignedStreamView(
        modality="X",
        source_schema_id="x-raw-v0.1",
        aligned_schema_id="x-aligned-v0.1",
        clock_id="sim-clock",
        tables={"samples": source_frame},
        json_artifacts={},
        file_artifacts={},
        source_checksums={"streams/x.parquet": SHA_A},
    )
    context = AnchorPluginContext(
        session_id="session-1",
        session_window=SessionWindow(end_t_ns=10, source="master-clock-x-mapped-coverage-v1"),
        streams={"X": source_view},
        context=projected_context,
        references={},
        semantic_scope=ProjectedSemanticScope(values=scope_values),
    )
    projected_context["context.undeclared"] = "hidden"
    scope_values["semantic.undeclared"] = True
    assert "context.undeclared" not in context.context
    assert "semantic.undeclared" not in context.semantic_scope.values
    assert context.streams["X"] is not source_view
    context.streams["X"].tables["samples"].insert_column(2, pl.Series("plugin-local", [2]))
    assert source_frame.columns == ["t_ns", "value"]
    with pytest.raises(TypeError):
        context.context["context.new"] = "x"  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        context.session_id = "other"  # type: ignore[misc]

    with pytest.raises((TypeError, ValueError)):
        AnchorPluginContext(
            session_id="session-1",
            session_window=context.session_window,
            streams={"U": source_view},
            context={},
            references={},
            semantic_scope=ProjectedSemanticScope(values={}),
        )

    absent_descriptor = ResolvedReferenceDescriptor.model_construct(
        reference_id="reference-1",
        resolution_status=ReferenceResolutionStatus.ABSENT,
    )
    absent_reference = ResolvedReference(descriptor=absent_descriptor, aligned_view=None)
    with pytest.raises((TypeError, ValueError)):
        AnchorPluginContext(
            session_id="session-1",
            session_window=context.session_window,
            streams={},
            context={},
            references={"wrong-reference": absent_reference},
            semantic_scope=ProjectedSemanticScope(values={}),
        )

    dependencies = ResolvedDependencies(
        results={}, artifacts={}, algorithm_profiles={}, preprocessing={}
    )
    with pytest.raises(TypeError):
        dependencies.results["O1"] = _result("O1")  # type: ignore[index]


@pytest.mark.parametrize("bad_value", [math.nan, object(), {"mutable"}])
def test_runtime_json_projections_reject_non_json_or_nonfinite_values(
    bad_value: object,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        ProjectedSemanticScope(values={"semantic.bad": bad_value})  # type: ignore[dict-item]


def test_runtime_json_projection_rejects_non_string_keys_without_aliasing() -> None:
    with pytest.raises((TypeError, ValueError)):
        ProjectedSemanticScope(values={1: "first", "1": "second"})  # type: ignore[dict-item]


def test_read_only_payloads_clone_content_and_keep_logical_identity() -> None:
    frame = pl.DataFrame({"t_ns": [0], "value": [1.0]})
    payload = TabularArtifactPayload(
        schema_id="trace-v0.1",
        schema_descriptor=_descriptor(),
        frame=frame,
        order_keys=("t_ns",),
        artifact_kind="sample_mask",
        grid_hash=SHA_B,
        start_t_ns=0,
        end_t_ns=1,
    )
    frozen = ReadOnlyTabularPayload(
        schema_id=payload.schema_id,
        schema_descriptor=payload.schema_descriptor,
        frame=payload.frame,
        order_keys=payload.order_keys,
        artifact_kind=payload.artifact_kind,
        grid_hash=payload.grid_hash,
        start_t_ns=payload.start_t_ns,
        end_t_ns=payload.end_t_ns,
        logical_content_sha256=SHA_A,
    )
    assert frozen.frame is not payload.frame
    payload.frame.insert_column(2, pl.Series("late", [2]))
    assert frozen.frame.columns == ["t_ns", "value"]
    exposed = frozen.frame
    exposed.insert_column(2, pl.Series("mutated", [3]))
    assert frozen.frame.columns == ["t_ns", "value"]
    with pytest.raises(TypeError):
        frozen.schema_descriptor["late"] = True  # type: ignore[index]

    blob = BlobArtifactPayload(
        schema_id="blob-v0.1",
        payload_bytes=b"abc",
        artifact_kind="diagnostic_blob",
        start_t_ns=None,
        end_t_ns=None,
    )
    read_only_blob = ReadOnlyBlobPayload(
        schema_id=blob.schema_id,
        payload_bytes=blob.payload_bytes,
        artifact_kind=blob.artifact_kind,
        start_t_ns=blob.start_t_ns,
        end_t_ns=blob.end_t_ns,
        logical_content_sha256=SHA_A,
    )
    assert read_only_blob.payload_bytes == b"abc"


def test_artifact_and_preprocessing_runtime_identity_fields_are_frozen() -> None:
    producer = ArtifactProducer(
        anchor_id="O1",
        plugin_id="o1-plugin",
        plugin_version="0.1.0",
        implementation_digest=SHA_A,
        parameter_hash=SHA_B,
        dependency_fingerprints=(),
    )
    scope = PreprocessingScope(
        kind="phase",
        scope_id="phase-1",
        start_t_ns=0,
        end_t_ns=10,
        phase_id="phase-1",
        event_id=None,
        window_id=None,
    )
    preprocessing_producer = PreprocessingProducer(
        recipe_id="movement-events-v1",
        recipe_version="0.1.0",
        provider_id="movement-events",
        provider_version="0.1.0",
        implementation_digest=SHA_A,
        parameter_schema_id="movement-events-parameters-v0.1",
        parameter_schema_sha256=SHA_B,
        parameter_hash=SHA_C,
        output_schema_id="movement-events-output-v0.1",
        output_schema_sha256=SHA_D,
        artifact_kind="movement-events-table",
        output_payload_kind="table",
        scope_kind=scope.kind,
        scope_id=scope.scope_id,
        scope_start_t_ns=scope.start_t_ns,
        scope_end_t_ns=scope.end_t_ns,
        phase_id=scope.phase_id,
        event_id=scope.event_id,
        window_id=scope.window_id,
        input_fingerprints=(("stream", "U", SHA_A),),
        dependency_fingerprints=(),
    )
    assert producer.anchor_id == "O1"
    assert preprocessing_producer.scope_id == "phase-1"
    with pytest.raises(FrozenInstanceError):
        scope.scope_id = "other"  # type: ignore[misc]

    mutable_fingerprints = [SHA_A]
    copied = ArtifactProducer(
        anchor_id="O1",
        plugin_id="o1-plugin",
        plugin_version="0.1.0",
        implementation_digest=SHA_A,
        parameter_hash=SHA_B,
        dependency_fingerprints=mutable_fingerprints,  # type: ignore[arg-type]
    )
    mutable_fingerprints.append(SHA_C)
    assert copied.dependency_fingerprints == (SHA_A,)
    with pytest.raises((TypeError, ValueError)):
        ArtifactProducer(
            anchor_id="",
            plugin_id="o1-plugin",
            plugin_version="0.1.0",
            implementation_digest="bad",
            parameter_hash=SHA_B,
            dependency_fingerprints=(),
        )
    with pytest.raises((TypeError, ValueError)):
        replace(preprocessing_producer, output_payload_kind="other")  # type: ignore[arg-type]


def test_resolved_payload_dependency_wrappers_preserve_complete_scope_identity() -> None:
    frame = pl.DataFrame({"t_ns": [0], "value": [1.0]})
    table = ReadOnlyTabularPayload(
        schema_id="derived-v0.1",
        schema_descriptor=_descriptor(),
        frame=frame,
        order_keys=("t_ns",),
        artifact_kind="derived-table",
        grid_hash=None,
        start_t_ns=0,
        end_t_ns=1,
        logical_content_sha256=SHA_A,
    )
    identity = PreprocessingArtifactIdentity(
        recipe_id="derived-v1",
        recipe_version="0.1.0",
        provider_id="derived",
        provider_version="0.1.0",
        implementation_digest=SHA_A,
        parameter_schema_id="derived-parameters-v0.1",
        parameter_schema_sha256=SHA_B,
        parameter_hash=SHA_C,
        scope_kind="window",
        scope_id="window-1",
        scope_start_t_ns=0,
        scope_end_t_ns=1,
        phase_id="phase-1",
        event_id=None,
        window_id="window-1",
        schema_id="derived-v0.1",
        schema_sha256=SHA_D,
        artifact_kind="derived-table",
        payload_kind="table",
        logical_content_sha256=SHA_A,
        input_fingerprints=(("stream", "U", SHA_A),),
        dependency_fingerprints=(),
    )
    preprocessing = ResolvedPreprocessingDependency(identity=identity, payload=table)
    artifact_table = ReadOnlyTabularPayload(
        schema_id="trace-v0.1",
        schema_descriptor=_descriptor(),
        frame=frame,
        order_keys=("t_ns",),
        artifact_kind="sample_mask",
        grid_hash=SHA_B,
        start_t_ns=0,
        end_t_ns=1,
        logical_content_sha256=SHA_A,
    )
    artifact = ResolvedArtifactDependency(ref=_artifact_ref(), payload=artifact_table)
    algorithm = ResolvedAlgorithmProfile(
        profile_id="filter-profile",
        profile_version="0.1.0",
        parameters={"cutoff": 1.0},
        parameter_hash=SHA_A,
        implementation_digest=SHA_B,
        output_schema_id="filter-output-v0.1",
    )
    dependencies = ResolvedDependencies(
        results={"O1": _result("O1")},
        artifacts={"trace": artifact},
        algorithm_profiles={"filter-profile": algorithm},
        preprocessing={"derived": preprocessing},
    )
    assert dependencies.preprocessing["derived"].identity.window_id == "window-1"
    with pytest.raises((TypeError, ValueError)):
        ResolvedArtifactDependency(ref=_artifact_ref(), payload=table)
    for inconsistent_ref in (
        _artifact_ref().model_copy(update={"row_count": 2}),
        _artifact_ref().model_copy(update={"end_t_ns": 2}),
        _artifact_ref().model_copy(update={"grid_hash": None}),
    ):
        with pytest.raises((TypeError, ValueError)):
            ResolvedArtifactDependency(ref=inconsistent_ref, payload=artifact_table)
    wrong_hash = replace(table, logical_content_sha256=SHA_B)
    with pytest.raises((TypeError, ValueError)):
        ResolvedPreprocessingDependency(identity=identity, payload=wrong_hash)


def test_nested_contract_maps_remain_immutable_through_runtime_dependencies_and_reports() -> None:
    profile = ResolvedAlgorithmProfile(
        profile_id="filter-profile",
        profile_version="0.1.0",
        parameters={"cutoff": 1.0, "bands": [1.0, 2.0]},
        parameter_hash=SHA_A,
        implementation_digest=SHA_B,
        output_schema_id="filter-output-v0.1",
    )
    dependencies = ResolvedDependencies(
        results={},
        artifacts={},
        algorithm_profiles={"slot": profile},
        preprocessing={},
    )
    with pytest.raises(TypeError):
        dependencies.algorithm_profiles["slot"].parameters["cutoff"] = 999.0
    with pytest.raises(TypeError):
        dependencies.algorithm_profiles["slot"].parameters["bands"].append(3.0)  # type: ignore[union-attr]

    diagnostic = DomainErrorData(
        error_code="test-diagnostic",
        severity="warning",
        recoverable=True,
        message="test diagnostic",
        remediation="none",
        diagnostics={"values": [1, 2]},
        extensions={"source": {"kind": "test"}},
    )
    report = _report((_result("O1"),)).model_copy(update={"diagnostics": (diagnostic,)})
    with pytest.raises(TypeError):
        report.diagnostics[0].diagnostics["late"] = 2
    with pytest.raises(TypeError):
        report.diagnostics[0].diagnostics["values"].append(3)  # type: ignore[union-attr]
    with pytest.raises(TypeError):
        report.diagnostics[0].extensions["source"]["kind"] = "changed"  # type: ignore[index]


def test_classification_override_preserves_json_array_shape_without_serialization_warnings() -> (
    None
):
    source = {"values": [1, 2], "nested": {"labels": ["a", "b"]}}
    override = ClassificationOverride(code="hard-limit", details=source)
    assert override.details == source
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert override.model_dump(mode="json")["details"] == source
    with pytest.raises(TypeError):
        override.details["values"].append(3)  # type: ignore[union-attr]


def test_plugin_provider_and_emitter_signatures_are_narrow_and_exact() -> None:
    assert tuple(signature(AnchorPlugin.definition).parameters) == ("self",)
    assert tuple(signature(AnchorPlugin.compute).parameters) == (
        "self",
        "context",
        "parameters",
        "temporal_recipe",
        "dependencies",
        "artifacts",
    )
    assert tuple(signature(PreprocessingProvider.definition).parameters) == ("self",)
    assert tuple(signature(PreprocessingProvider.compute).parameters) == (
        "self",
        "context",
        "recipe",
        "scope",
        "dependencies",
    )
    emitter_members = {name for name in AnchorArtifactEmitter.__dict__ if not name.startswith("_")}
    assert emitter_members == {"stage_table", "stage_blob"}
    assert tuple(signature(AnchorArtifactEmitter.stage_table).parameters) == (
        "self",
        "artifact_id",
        "payload",
    )
    assert tuple(signature(AnchorArtifactEmitter.stage_blob).parameters) == (
        "self",
        "artifact_id",
        "payload",
    )
    assert not {"commit", "abort", "resolve", "transaction", "cache"} & emitter_members

    plugin_hints = get_type_hints(AnchorPlugin.compute)
    assert plugin_hints["context"] is AnchorPluginContext
    assert get_origin(plugin_hints["parameters"]) is Mapping
    assert get_origin(plugin_hints["temporal_recipe"]) is Mapping
    assert plugin_hints["dependencies"] is ResolvedDependencies
    assert plugin_hints["artifacts"] is AnchorArtifactEmitter
    assert plugin_hints["return"] is AnchorMeasurement
    assert Any not in plugin_hints.values()

    provider_hints = get_type_hints(PreprocessingProvider.compute)
    assert provider_hints["context"] is AnchorPluginContext
    assert provider_hints["scope"] is PreprocessingScope
    assert get_origin(provider_hints["dependencies"]) is Mapping
    assert Any not in provider_hints.values()


def test_runtime_dataclass_field_sets_are_exact() -> None:
    expected = {
        ProjectedSemanticScope: ("values",),
        AnchorPluginContext: (
            "session_id",
            "session_window",
            "streams",
            "context",
            "references",
            "semantic_scope",
        ),
        ArtifactProducer: (
            "anchor_id",
            "plugin_id",
            "plugin_version",
            "implementation_digest",
            "parameter_hash",
            "dependency_fingerprints",
        ),
        PreprocessingScope: (
            "kind",
            "scope_id",
            "start_t_ns",
            "end_t_ns",
            "phase_id",
            "event_id",
            "window_id",
        ),
        PreprocessingProducer: (
            "recipe_id",
            "recipe_version",
            "provider_id",
            "provider_version",
            "implementation_digest",
            "parameter_schema_id",
            "parameter_schema_sha256",
            "parameter_hash",
            "output_schema_id",
            "output_schema_sha256",
            "artifact_kind",
            "output_payload_kind",
            "scope_kind",
            "scope_id",
            "scope_start_t_ns",
            "scope_end_t_ns",
            "phase_id",
            "event_id",
            "window_id",
            "input_fingerprints",
            "dependency_fingerprints",
        ),
        ResolvedArtifactDependency: ("ref", "payload"),
        PreprocessingArtifactIdentity: (
            "recipe_id",
            "recipe_version",
            "provider_id",
            "provider_version",
            "implementation_digest",
            "parameter_schema_id",
            "parameter_schema_sha256",
            "parameter_hash",
            "scope_kind",
            "scope_id",
            "scope_start_t_ns",
            "scope_end_t_ns",
            "phase_id",
            "event_id",
            "window_id",
            "schema_id",
            "schema_sha256",
            "artifact_kind",
            "payload_kind",
            "logical_content_sha256",
            "input_fingerprints",
            "dependency_fingerprints",
        ),
        ResolvedPreprocessingDependency: ("identity", "payload"),
        ResolvedDependencies: (
            "results",
            "artifacts",
            "algorithm_profiles",
            "preprocessing",
        ),
        TabularArtifactPayload: (
            "schema_id",
            "schema_descriptor",
            "frame",
            "order_keys",
            "artifact_kind",
            "grid_hash",
            "start_t_ns",
            "end_t_ns",
        ),
        BlobArtifactPayload: (
            "schema_id",
            "payload_bytes",
            "artifact_kind",
            "start_t_ns",
            "end_t_ns",
        ),
        ReadOnlyTabularPayload: (
            "schema_id",
            "schema_descriptor",
            "frame",
            "order_keys",
            "artifact_kind",
            "grid_hash",
            "start_t_ns",
            "end_t_ns",
            "logical_content_sha256",
        ),
        ReadOnlyBlobPayload: (
            "schema_id",
            "payload_bytes",
            "artifact_kind",
            "start_t_ns",
            "end_t_ns",
            "logical_content_sha256",
        ),
    }
    for runtime_type, field_names in expected.items():
        assert tuple(field.name for field in fields(runtime_type)) == field_names
