"""O8 TPX Composite production plugin."""

from __future__ import annotations

import math
import sys
from collections.abc import Mapping

import polars as pl
from pydantic import JsonValue

from pilot_assessment.anchors.catalog import load_packaged_catalog
from pilot_assessment.anchors.protocols import (
    AnchorArtifactEmitter,
    AnchorPluginContext,
    ResolvedDependencies,
    TabularArtifactPayload,
)
from pilot_assessment.contracts.anchor_execution import AnchorPluginDefinition
from pilot_assessment.contracts.anchor_v2 import (
    AnchorCalculationStatusV2,
    AnchorMeasurement,
    AnchorResultV2,
    ComputationTrace,
    MetricValue,
)
from pilot_assessment.contracts.errors import DomainErrorData, ErrorSeverity

_DEPENDENCY_IDS = ("o1-result", "o5-result")
_MAX_SAFE_SQUARE_ROOT = math.sqrt(sys.float_info.max)


def _definition() -> AnchorPluginDefinition:
    catalog_entry = next(
        entry for entry in load_packaged_catalog().entries if entry.anchor_id == "O8"
    )
    return AnchorPluginDefinition(
        anchor_id=catalog_entry.anchor_id,
        definition_version=catalog_entry.definition_version,
        plugin_id=catalog_entry.plugin_id,
        plugin_version=catalog_entry.plugin_version,
        api_version="0.1.0",
        required_streams=tuple(
            value.removeprefix("stream.")
            for value in catalog_entry.required_inputs
            if value.startswith("stream.")
        ),
        required_context_paths=tuple(
            sorted(value for value in catalog_entry.required_inputs if value.startswith("context."))
        ),
        required_semantic_paths=tuple(
            sorted(
                value for value in catalog_entry.required_inputs if value.startswith("semantic.")
            )
        ),
        required_reference_ids=tuple(
            sorted(
                value.removeprefix("reference.")
                for value in catalog_entry.required_inputs
                if value.startswith("reference.")
            )
        ),
        dependencies=catalog_entry.dependencies,
        parameter_schema_id=catalog_entry.parameter_schema_id,
        measurement_schema_id="anchor-measurement-0.1.0",
        artifact_recipes=catalog_entry.artifact_recipes,
    )


def _finite_nonnegative(value: object, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise ValueError(f"{label} must be finite and non-negative")
    return float(value)


def compute_tpx_composite(precision_percent: float, workload_ratio: float) -> float:
    """Return the formula-defined, bounded TPX value.

    O5 publishes ``workload_ratio = W / W_min``. Therefore
    ``sqrt(W_min / max(W, W_min))`` is exactly
    ``1 / sqrt(max(workload_ratio, 1))``. Keeping that normalized value as the
    dependency contract avoids duplicating O5's fixed ``w_min_hz`` parameter.
    """

    precision = _finite_nonnegative(precision_percent, "precision_percent")
    workload = _finite_nonnegative(workload_ratio, "workload_ratio")
    scaled_precision = precision / 100.0
    denominator = math.sqrt(max(workload, 1.0))
    if scaled_precision > _MAX_SAFE_SQUARE_ROOT:
        return 1.0
    value = scaled_precision * scaled_precision / denominator
    return min(1.0, max(0.0, value))


def _dependency_missing(
    context: AnchorPluginContext,
    missing: tuple[tuple[str, str], ...],
) -> AnchorMeasurement:
    diagnostics = (
        DomainErrorData(
            error_code="anchor.o8.dependency_missing",
            severity=ErrorSeverity.WARNING,
            recoverable=True,
            message="O8 requires computed O1 and O5 results before TPX can be calculated.",
            field_or_path="dependencies.results",
            node_or_anchor_id="O8",
            remediation="Compute O1 and O5 successfully, then evaluate O8 again.",
            diagnostics={
                "missing_dependencies": [
                    {"dependency_id": dependency_id, "status": status}
                    for dependency_id, status in missing
                ]
            },
        ),
    )
    return AnchorMeasurement(
        anchor_id="O8",
        calculation_status=AnchorCalculationStatusV2.DEPENDENCY_MISSING,
        primary_value=None,
        primary_value_reason=None,
        raw_metrics={},
        phase_results=(),
        event_results=(),
        classification_override_candidate=None,
        source_windows=(),
        derived_artifacts=(),
        trace=ComputationTrace(
            sample_count=0,
            source_start_t_ns=None,
            source_end_t_ns=None,
            analysis_start_t_ns=context.session_window.start_t_ns,
            analysis_end_t_ns=context.session_window.end_t_ns,
            grid_id=None,
            window_ids=(),
            interpolation_method=None,
            matching_method="o1-o5-result-composite-v1",
            diagnostics=diagnostics,
        ),
        diagnostics=diagnostics,
    )


def _computed_dependencies(
    context: AnchorPluginContext, dependencies: ResolvedDependencies
) -> tuple[AnchorResultV2, AnchorResultV2] | AnchorMeasurement:
    missing: list[tuple[str, str]] = []
    for dependency_id in _DEPENDENCY_IDS:
        result = dependencies.results.get(dependency_id)
        if result is None:
            missing.append((dependency_id, "absent"))
        elif result.calculation_status is not AnchorCalculationStatusV2.COMPUTED:
            missing.append((dependency_id, result.calculation_status.value))
    if missing:
        return _dependency_missing(context, tuple(missing))
    o1 = dependencies.results["o1-result"]
    o5 = dependencies.results["o5-result"]
    if o1.anchor_id != "O1" or o5.anchor_id != "O5":
        raise ValueError("O8 result dependency anchor identities are invalid")
    return o1, o5


def _metric(result: AnchorResultV2, expected_unit: str, label: str) -> float:
    metric = result.primary_value
    if metric is None or metric.scalar_kind != "float" or metric.unit != expected_unit:
        raise ValueError(f"{label} must be a computed float metric in {expected_unit}")
    return _finite_nonnegative(metric.value, label)


def _component_trace(
    definition: AnchorPluginDefinition,
    context: AnchorPluginContext,
    o1: AnchorResultV2,
    o5: AnchorResultV2,
) -> TabularArtifactPayload:
    rows = []
    for dependency_id, result in (("o1-result", o1), ("o5-result", o5)):
        assert result.evidence_state is not None
        assert result.continuous_score is not None
        rows.append(
            {
                "component_id": dependency_id,
                "source_anchor_id": result.anchor_id,
                "source_result_fingerprint": result.result_fingerprint,
                "state": result.evidence_state.value,
                "score": float(result.continuous_score),
            }
        )
    frame = pl.DataFrame(
        rows,
        schema={
            "component_id": pl.String,
            "source_anchor_id": pl.String,
            "source_result_fingerprint": pl.String,
            "state": pl.String,
            "score": pl.Float64,
        },
    ).sort("component_id", maintain_order=True)
    recipe = definition.artifact_recipes[0]
    return TabularArtifactPayload(
        schema_id=recipe.schema_id,
        schema_descriptor=recipe.schema_descriptor,
        frame=frame,
        order_keys=("component_id",),
        artifact_kind=recipe.kind,
        grid_hash=None,
        start_t_ns=context.session_window.start_t_ns,
        end_t_ns=context.session_window.end_t_ns,
    )


class O8TPXCompositePlugin:
    def __init__(self) -> None:
        self._definition = _definition()

    def definition(self) -> AnchorPluginDefinition:
        return self._definition

    def compute(
        self,
        context: AnchorPluginContext,
        parameters: Mapping[str, JsonValue],
        temporal_recipe: Mapping[str, JsonValue],
        dependencies: ResolvedDependencies,
        artifacts: AnchorArtifactEmitter,
    ) -> AnchorMeasurement:
        if not isinstance(parameters, Mapping) or parameters:
            raise ValueError("O8 v0.1 parameters must be the exact empty object")
        if not isinstance(temporal_recipe, Mapping):
            raise TypeError("O8 temporal_recipe must be a mapping")
        resolved = _computed_dependencies(context, dependencies)
        if isinstance(resolved, AnchorMeasurement):
            return resolved
        o1, o5 = resolved
        precision_percent = _metric(o1, "percent", "O1 precision")
        workload_ratio = _metric(o5, "ratio", "O5 workload ratio")
        tpx = compute_tpx_composite(precision_percent, workload_ratio)
        artifact_ref = artifacts.stage_table(
            "tpx-component-trace",
            _component_trace(self._definition, context, o1, o5),
        )
        return AnchorMeasurement(
            anchor_id="O8",
            calculation_status=AnchorCalculationStatusV2.COMPUTED,
            primary_value=MetricValue(scalar_kind="float", value=tpx, unit="ratio"),
            primary_value_reason=None,
            raw_metrics={
                "precision-percent": MetricValue(
                    scalar_kind="float", value=precision_percent, unit="percent"
                ),
                "workload-ratio": MetricValue(
                    scalar_kind="float", value=workload_ratio, unit="ratio"
                ),
            },
            phase_results=(),
            event_results=(),
            classification_override_candidate=None,
            source_windows=(),
            derived_artifacts=(artifact_ref,),
            trace=ComputationTrace(
                sample_count=2,
                source_start_t_ns=context.session_window.start_t_ns,
                source_end_t_ns=context.session_window.end_t_ns,
                analysis_start_t_ns=context.session_window.start_t_ns,
                analysis_end_t_ns=context.session_window.end_t_ns,
                grid_id=None,
                window_ids=(),
                interpolation_method=None,
                matching_method="o1-o5-result-composite-v1",
                diagnostics=(),
            ),
            diagnostics=(),
        )


def create_plugin() -> O8TPXCompositePlugin:
    return O8TPXCompositePlugin()


__all__ = ["O8TPXCompositePlugin", "compute_tpx_composite", "create_plugin"]
