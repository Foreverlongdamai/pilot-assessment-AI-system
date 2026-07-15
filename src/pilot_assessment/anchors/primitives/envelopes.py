"""Native-rate envelope kernels shared by O1 and later O13 windows."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import cast

import polars as pl
from pydantic import JsonValue

from pilot_assessment.anchors.primitives.models import (
    O1AxisSummary,
    O1KernelResult,
    O1KernelStatus,
    O1MaskRow,
)
from pilot_assessment.anchors.temporal import (
    left_hold_integral_v1,
    reconstruct_point_support,
)
from pilot_assessment.contracts.anchor_execution import (
    EnvelopeDefinition,
    ResolvedInputTableContract,
    SemanticPhase,
)

_SIGNED_INT64_MAX = 2**63 - 1


def _strict_int(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be a strict integer of at least {minimum}")
    return value


def _recipe_string(recipe: Mapping[str, JsonValue], key: str) -> str:
    value = recipe.get(key)
    if type(value) is not str or not value:
        raise ValueError(f"temporal_recipe.{key} must be a non-empty string")
    return value


def _recipe_strings(recipe: Mapping[str, JsonValue], key: str) -> tuple[str, ...]:
    value = recipe.get(key)
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"temporal_recipe.{key} must be an ordered string array")
    normalized = tuple(value)
    if not normalized or any(type(item) is not str or not item for item in normalized):
        raise ValueError(f"temporal_recipe.{key} must contain non-empty strings")
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"temporal_recipe.{key} must be unique")
    return cast(tuple[str, ...], normalized)


def _noncomputed(
    *,
    status: O1KernelStatus,
    reason: str,
    phase_duration_ns: int,
    sample_count: int = 0,
    source_start_t_ns: int | None = None,
    source_end_t_ns: int | None = None,
    gap_count: int = 0,
    max_gap_ns: int | None = None,
    observed_support_duration_ns: int = 0,
    mask_rows: tuple[O1MaskRow, ...] = (),
) -> O1KernelResult:
    return O1KernelResult(
        status=status,
        reason=reason,
        precision_percent=None,
        phase_duration_ns=phase_duration_ns,
        observed_support_duration_ns=observed_support_duration_ns,
        desired_joint_duration_ns=0,
        sample_count=sample_count,
        source_start_t_ns=source_start_t_ns,
        source_end_t_ns=source_end_t_ns,
        gap_count=gap_count,
        max_gap_ns=max_gap_ns,
        axis_summaries=(),
        mask_rows=mask_rows,
    )


def _x_contract(
    input_contracts: tuple[ResolvedInputTableContract, ...], table_role: str
) -> ResolvedInputTableContract | None:
    matches = tuple(
        contract
        for contract in input_contracts
        if contract.modality.value == "X" and contract.table_role == table_role
    )
    if len(matches) > 1:
        raise ValueError("input contracts contain duplicate X table roles")
    return matches[0] if matches else None


def compute_o1_kernel(
    x_table: pl.DataFrame,
    phase: SemanticPhase,
    envelope: EnvelopeDefinition,
    scope_start_t_ns: int,
    scope_end_t_ns: int,
    input_contracts: tuple[ResolvedInputTableContract, ...],
    parameters: Mapping[str, JsonValue],
    temporal_recipe: Mapping[str, JsonValue],
) -> O1KernelResult:
    """Compute desired-envelope precision without staging artifacts or scoring.

    Finite values are always assessed, including arbitrarily poor values.  The
    only absent-data outcome is a true lack of mathematical temporal support;
    no coverage threshold or data-quality classification is applied.
    """

    if not isinstance(x_table, pl.DataFrame):
        raise TypeError("x_table must be a Polars DataFrame")
    if not isinstance(phase, SemanticPhase) or not isinstance(envelope, EnvelopeDefinition):
        raise TypeError("phase and envelope must use the typed semantic contracts")
    if not isinstance(input_contracts, tuple) or any(
        not isinstance(item, ResolvedInputTableContract) for item in input_contracts
    ):
        raise TypeError("input_contracts must be a typed tuple")
    if not isinstance(parameters, Mapping) or parameters:
        raise ValueError("O1 v0.1 parameters must be the exact empty object")
    if not isinstance(temporal_recipe, Mapping):
        raise TypeError("temporal_recipe must be a mapping")

    scope_start = _strict_int(scope_start_t_ns, "scope_start_t_ns")
    scope_end = _strict_int(scope_end_t_ns, "scope_end_t_ns", minimum=1)
    start = max(scope_start, phase.start_t_ns)
    end = min(scope_end, phase.end_t_ns)
    if end <= start:
        raise ValueError("O1 scope must overlap the semantic phase")
    phase_duration = end - start

    table_role = _recipe_string(temporal_recipe, "table_role")
    timestamp_column = _recipe_string(temporal_recipe, "timestamp_column")
    in_session_column = _recipe_string(temporal_recipe, "in_session_column")
    stable_keys = _recipe_strings(temporal_recipe, "stable_keys")
    gap_threshold = _strict_int(
        temporal_recipe.get("gap_threshold_ns"), "temporal_recipe.gap_threshold_ns"
    )
    contract = _x_contract(input_contracts, table_role)
    if contract is None:
        return _noncomputed(
            status="not_computable",
            reason="input-contract-missing",
            phase_duration_ns=phase_duration,
        )

    fields = {field.field_name: field for field in contract.fields}
    structural_columns = (timestamp_column, in_session_column, *stable_keys)
    if any(column not in fields or column not in x_table.columns for column in structural_columns):
        return _noncomputed(
            status="not_computable",
            reason="temporal-field-missing",
            phase_duration_ns=phase_duration,
        )
    for limit in envelope.axis_limits:
        field = fields.get(limit.metric_id)
        if field is None or limit.metric_id not in x_table.columns or field.unit != limit.unit:
            return _noncomputed(
                status="not_computable",
                reason="envelope-contract-mismatch",
                phase_duration_ns=phase_duration,
            )

    terminal = phase.include_session_terminal_point and end == phase.end_t_ns
    time_expression = (pl.col(timestamp_column) >= start) & (
        (pl.col(timestamp_column) <= end) if terminal else (pl.col(timestamp_column) < end)
    )
    active = (
        x_table.filter(time_expression & pl.col(in_session_column))
        .sort([timestamp_column, *stable_keys], maintain_order=True)
        .select(x_table.columns)
    )
    if active.is_empty():
        return _noncomputed(
            status="missing_input",
            reason="no-temporal-support",
            phase_duration_ns=phase_duration,
        )

    times = cast(list[int], active[timestamp_column].to_list())
    source_start, source_end = min(times), max(times)
    support = reconstruct_point_support(
        active,
        timestamp_column=timestamp_column,
        stable_keys=stable_keys,
        in_session_column=in_session_column,
        gap_threshold_ns=gap_threshold,
        semantic_end_t_ns=end,
    )
    if support.observed_duration_ns == 0:
        return _noncomputed(
            status="missing_input",
            reason="no-temporal-support",
            phase_duration_ns=phase_duration,
            sample_count=active.height,
            source_start_t_ns=source_start,
            source_end_t_ns=source_end,
            gap_count=support.gap_count,
            max_gap_ns=support.max_gap_ns,
        )

    source_ids_raw = active[stable_keys[0]].to_list()
    source_ids: list[int] = []
    for value in source_ids_raw:
        if type(value) is not int or value < 0 or value > _SIGNED_INT64_MAX:
            return _noncomputed(
                status="not_computable",
                reason="source-row-id-invalid",
                phase_duration_ns=phase_duration,
                sample_count=active.height,
                source_start_t_ns=source_start,
                source_end_t_ns=source_end,
                gap_count=support.gap_count,
                max_gap_ns=support.max_gap_ns,
                observed_support_duration_ns=support.observed_duration_ns,
            )
        source_ids.append(value)

    axis_masks: list[tuple[str, int, tuple[bool, ...]]] = []
    for axis_order, limit in enumerate(envelope.axis_limits):
        raw_values = active[limit.metric_id].to_list()
        if any(value is None for value in raw_values):
            return _noncomputed(
                status="missing_input",
                reason="metric-value-missing",
                phase_duration_ns=phase_duration,
                sample_count=active.height,
                source_start_t_ns=source_start,
                source_end_t_ns=source_end,
                gap_count=support.gap_count,
                max_gap_ns=support.max_gap_ns,
                observed_support_duration_ns=support.observed_duration_ns,
            )
        values: list[float] = []
        for value in raw_values:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return _noncomputed(
                    status="not_computable",
                    reason="metric-value-nonnumeric",
                    phase_duration_ns=phase_duration,
                    sample_count=active.height,
                    source_start_t_ns=source_start,
                    source_end_t_ns=source_end,
                    gap_count=support.gap_count,
                    max_gap_ns=support.max_gap_ns,
                    observed_support_duration_ns=support.observed_duration_ns,
                )
            numeric = float(value)
            if not math.isfinite(numeric):
                return _noncomputed(
                    status="not_computable",
                    reason="metric-value-nonfinite",
                    phase_duration_ns=phase_duration,
                    sample_count=active.height,
                    source_start_t_ns=source_start,
                    source_end_t_ns=source_end,
                    gap_count=support.gap_count,
                    max_gap_ns=support.max_gap_ns,
                    observed_support_duration_ns=support.observed_duration_ns,
                )
            values.append(numeric)
        axis_masks.append(
            (
                limit.metric_id,
                axis_order,
                tuple(abs(value) <= limit.desired_abs_max for value in values),
            )
        )

    joint_mask = tuple(
        all(axis_mask[row_index] for _axis_id, _axis_order, axis_mask in axis_masks)
        for row_index in range(active.height)
    )
    axis_summaries = tuple(
        O1AxisSummary(
            axis_id=axis_id,
            axis_order=axis_order,
            desired_duration_ns=int(
                left_hold_integral_v1(
                    tuple(1.0 if inside else 0.0 for inside in axis_mask), support
                )
            ),
        )
        for axis_id, axis_order, axis_mask in axis_masks
    )
    joint_duration = int(
        left_hold_integral_v1(tuple(1.0 if inside else 0.0 for inside in joint_mask), support)
    )
    mask_rows = tuple(
        O1MaskRow(
            phase_id=phase.phase_id,
            t_ns=timestamp,
            source_row_id=source_id,
            axis_order=axis_order,
            axis_id=axis_id,
            inside=axis_mask[row_index],
        )
        for row_index, (timestamp, source_id) in enumerate(zip(times, source_ids, strict=True))
        for axis_id, axis_order, axis_mask in (
            *axis_masks,
            ("joint", len(axis_masks), joint_mask),
        )
    )
    return O1KernelResult(
        status="computed",
        reason=None,
        precision_percent=100.0 * joint_duration / phase_duration,
        phase_duration_ns=phase_duration,
        observed_support_duration_ns=support.observed_duration_ns,
        desired_joint_duration_ns=joint_duration,
        sample_count=active.height,
        source_start_t_ns=source_start,
        source_end_t_ns=source_end,
        gap_count=support.gap_count,
        max_gap_ns=support.max_gap_ns,
        axis_summaries=axis_summaries,
        mask_rows=mask_rows,
    )


__all__ = ["compute_o1_kernel"]
