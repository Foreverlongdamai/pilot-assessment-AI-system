"""Generic CPT validation, deterministic materialization, and pure migrations."""

from __future__ import annotations

import itertools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias

from pilot_assessment.contracts.model_components import (
    BnNodeVersion,
    ComponentIdRef,
    ComponentKind,
    CptMode,
    CptVersion,
    EvidenceBindingVersion,
)
from pilot_assessment.model_library.repository import component_content_hash

DEFAULT_MAX_CPT_CELLS = 250_000
DEFAULT_ROW_SUM_TOLERANCE = 1e-9

BayesianVariable: TypeAlias = BnNodeVersion | EvidenceBindingVersion
VariableKey: TypeAlias = tuple[ComponentKind, str]
VariableCatalog: TypeAlias = Mapping[VariableKey, BayesianVariable]


class CptDiagnosticSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class CptDiagnostic:
    code: str
    severity: CptDiagnosticSeverity
    location: str
    message: str

    @property
    def blocking(self) -> bool:
        return self.severity is CptDiagnosticSeverity.ERROR


@dataclass(frozen=True, slots=True)
class CptValidationOutcome:
    executable: bool
    required_row_count: int
    required_cell_count: int
    diagnostics: tuple[CptDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class CptMaterialization:
    parent_assignments: tuple[tuple[str, ...], ...]
    probabilities: tuple[tuple[float, ...], ...]


class CptMaterializationError(ValueError):
    """Raised when explicit generator parameters cannot produce a bounded table."""


class CptMigrationError(ValueError):
    """Raised when a pure CPT migration lacks required technical information."""


def _variable_states(variable: BayesianVariable) -> tuple[str, ...]:
    states = (
        variable.ordered_states
        if isinstance(variable, BnNodeVersion)
        else variable.ordered_observation_states
    )
    return tuple(state.state_id for state in states)


def _key(reference: ComponentIdRef) -> VariableKey:
    return (reference.kind, reference.version_id)


def _diagnostic(
    diagnostics: list[CptDiagnostic],
    code: str,
    location: str,
    message: str,
    *,
    warning: bool = False,
) -> None:
    diagnostics.append(
        CptDiagnostic(
            code=code,
            severity=(CptDiagnosticSeverity.WARNING if warning else CptDiagnosticSeverity.ERROR),
            location=location,
            message=message,
        )
    )


def _strict_positive_limit(value: int) -> int:
    if type(value) is not int or value < 1:
        raise ValueError("max_cells must be a positive strict integer")
    return value


def _product(values: Sequence[int]) -> int:
    result = 1
    for value in values:
        result *= value
    return result


def _assignment_index(assignment: tuple[int, ...], cardinalities: tuple[int, ...]) -> int:
    index = 0
    for state_index, cardinality in zip(assignment, cardinalities, strict=True):
        index = index * cardinality + state_index
    return index


def _is_manual_non_monotonic(
    rows: tuple[tuple[float, ...], ...],
    parent_cardinalities: tuple[int, ...],
) -> bool:
    if not parent_cardinalities:
        return False
    expected_ranks = tuple(
        math.fsum(index * probability for index, probability in enumerate(row)) for row in rows
    )
    for assignment in itertools.product(
        *(range(cardinality) for cardinality in parent_cardinalities)
    ):
        current = expected_ranks[_assignment_index(assignment, parent_cardinalities)]
        for dimension, cardinality in enumerate(parent_cardinalities):
            if assignment[dimension] + 1 >= cardinality:
                continue
            adjacent = list(assignment)
            adjacent[dimension] += 1
            target = expected_ranks[_assignment_index(tuple(adjacent), parent_cardinalities)]
            if target + 1e-12 < current:
                return True
    return False


def validate_cpt(
    cpt: CptVersion,
    variables: VariableCatalog,
    *,
    max_cells: int = DEFAULT_MAX_CPT_CELLS,
    row_sum_tolerance: float = DEFAULT_ROW_SUM_TOLERANCE,
) -> CptValidationOutcome:
    """Validate only executable table invariants; scientific plausibility is non-gating."""

    _strict_positive_limit(max_cells)
    if (
        not isinstance(row_sum_tolerance, (int, float))
        or isinstance(row_sum_tolerance, bool)
        or not math.isfinite(row_sum_tolerance)
        or row_sum_tolerance < 0.0
    ):
        raise ValueError("row_sum_tolerance must be a finite non-negative number")
    diagnostics: list[CptDiagnostic] = []
    child = variables.get(_key(cpt.child_variable_id))
    child_state_ids = cpt.child_state_ids
    required_child_state_count = len(child_state_ids)
    if child is None:
        _diagnostic(
            diagnostics,
            "cpt.child_missing",
            "/child_variable_id",
            "CPT child variable is not present in the selected variable catalog",
        )
    else:
        expected_child_states = _variable_states(child)
        required_child_state_count = len(expected_child_states)
        if child_state_ids != expected_child_states:
            _diagnostic(
                diagnostics,
                "cpt.child_state_mismatch",
                "/child_state_ids",
                "CPT child state order does not match the exact child variable",
            )
        child_parents = tuple(_key(parent) for parent in child.ordered_probabilistic_parent_ids)
        cpt_parents = tuple(_key(parent) for parent in cpt.ordered_parent_variable_ids)
        if cpt_parents != child_parents:
            _diagnostic(
                diagnostics,
                "cpt.parent_order_mismatch",
                "/ordered_parent_variable_ids",
                "CPT ordered parents do not match the exact child variable",
            )

    parent_cardinalities: list[int] = []
    if len(cpt.ordered_parent_state_ids) != len(cpt.ordered_parent_variable_ids):
        _diagnostic(
            diagnostics,
            "cpt.parent_state_space_count_mismatch",
            "/ordered_parent_state_ids",
            "CPT must declare one ordered state space for every ordered parent",
        )
    for index, parent_reference in enumerate(cpt.ordered_parent_variable_ids):
        declared_states = (
            cpt.ordered_parent_state_ids[index] if index < len(cpt.ordered_parent_state_ids) else ()
        )
        parent = variables.get(_key(parent_reference))
        if parent is None:
            _diagnostic(
                diagnostics,
                "cpt.parent_missing",
                f"/ordered_parent_variable_ids/{index}",
                "CPT parent variable is not present in the selected variable catalog",
            )
            parent_cardinalities.append(len(declared_states))
            continue
        expected_states = _variable_states(parent)
        parent_cardinalities.append(len(expected_states))
        if declared_states != expected_states:
            _diagnostic(
                diagnostics,
                "cpt.parent_state_mismatch",
                f"/ordered_parent_state_ids/{index}",
                "CPT parent state order does not match the exact parent variable",
            )

    required_rows = _product(parent_cardinalities)
    required_cells = required_rows * required_child_state_count
    if required_cells > max_cells:
        _diagnostic(
            diagnostics,
            "cpt.cell_limit_exceeded",
            "/materialized_probabilities",
            f"CPT requires {required_cells} cells, above configured limit {max_cells}",
        )
    if cpt.mode is CptMode.INCOMPLETE:
        _diagnostic(
            diagnostics,
            "cpt.incomplete",
            "/mode",
            "CPT is intentionally incomplete and must be materialized before publication",
        )

    rows = cpt.materialized_probabilities
    if len(rows) != required_rows:
        _diagnostic(
            diagnostics,
            "cpt.row_count_mismatch",
            "/materialized_probabilities",
            f"CPT has {len(rows)} rows but requires {required_rows}",
        )
    materialized_shape_valid = len(rows) == required_rows
    materialized_values_valid = True
    for row_index, row in enumerate(rows):
        if len(row) != required_child_state_count:
            materialized_shape_valid = False
            _diagnostic(
                diagnostics,
                "cpt.column_count_mismatch",
                f"/materialized_probabilities/{row_index}",
                f"row has {len(row)} cells but child requires {required_child_state_count} states",
            )
            continue
        numeric_row: list[float] = []
        row_valid = True
        for column_index, value in enumerate(row):
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
            ):
                row_valid = False
                materialized_values_valid = False
                _diagnostic(
                    diagnostics,
                    "cpt.probability_non_finite",
                    f"/materialized_probabilities/{row_index}/{column_index}",
                    "CPT probabilities must be finite numeric values",
                )
                continue
            numeric = float(value)
            numeric_row.append(numeric)
            if numeric < 0.0 or numeric > 1.0:
                row_valid = False
                materialized_values_valid = False
                _diagnostic(
                    diagnostics,
                    "cpt.probability_out_of_range",
                    f"/materialized_probabilities/{row_index}/{column_index}",
                    "CPT probabilities must be between zero and one",
                )
        if row_valid and abs(math.fsum(numeric_row) - 1.0) > row_sum_tolerance:
            materialized_values_valid = False
            _diagnostic(
                diagnostics,
                "cpt.row_not_normalized",
                f"/materialized_probabilities/{row_index}",
                "CPT probability row does not sum to one within tolerance",
            )

    if materialized_shape_valid and materialized_values_valid and rows:
        non_monotonic = _is_manual_non_monotonic(
            rows,
            tuple(parent_cardinalities),
        )
        if non_monotonic and cpt.mode is CptMode.MANUAL:
            _diagnostic(
                diagnostics,
                "cpt.non_monotonic",
                "/materialized_probabilities",
                "manual CPT is non-monotonic; this is allowed and remains expert-owned",
                warning=True,
            )
        elif non_monotonic and cpt.generator_metadata.get("monotonic_contract") is True:
            _diagnostic(
                diagnostics,
                "cpt.generator_monotonicity_violation",
                "/materialized_probabilities",
                "generated CPT violates its explicitly declared monotonic contract",
            )

    ordered = tuple(
        sorted(
            diagnostics,
            key=lambda item: (item.location, item.code, item.message),
        )
    )
    return CptValidationOutcome(
        executable=not any(item.blocking for item in ordered),
        required_row_count=required_rows,
        required_cell_count=required_cells,
        diagnostics=ordered,
    )


def _validate_state_ids(state_ids: tuple[str, ...], label: str) -> None:
    if (
        len(state_ids) < 2
        or any(type(state_id) is not str or not state_id for state_id in state_ids)
        or len(state_ids) != len(set(state_ids))
    ):
        raise CptMaterializationError(f"{label} must contain at least two unique states")


def _validate_materialization_size(
    parent_state_ids: tuple[tuple[str, ...], ...],
    child_state_ids: tuple[str, ...],
    max_cells: int,
) -> None:
    _strict_positive_limit(max_cells)
    rows = _product([len(states) for states in parent_state_ids])
    cells = rows * len(child_state_ids)
    if cells > max_cells:
        raise CptMaterializationError(
            f"materialized CPT requires {cells} cells, above limit {max_cells}"
        )


def _gaussian_row(center: float, state_count: int, sigma: float) -> tuple[float, ...]:
    values = tuple(
        math.exp(-((state_index - center) ** 2) / (2.0 * sigma**2))
        for state_index in range(state_count)
    )
    total = math.fsum(values)
    return tuple(value / total for value in values)


def materialize_uniform_prior(
    child_state_ids: tuple[str, ...],
    *,
    max_cells: int = DEFAULT_MAX_CPT_CELLS,
) -> CptMaterialization:
    _validate_state_ids(child_state_ids, "child_state_ids")
    _validate_materialization_size((), child_state_ids, max_cells)
    probability = 1.0 / len(child_state_ids)
    return CptMaterialization(
        parent_assignments=((),),
        probabilities=(tuple(probability for _ in child_state_ids),),
    )


def materialize_ordered_single_parent(
    parent_state_ids: tuple[str, ...],
    child_state_ids: tuple[str, ...],
    *,
    sigma: float,
    max_cells: int = DEFAULT_MAX_CPT_CELLS,
) -> CptMaterialization:
    return materialize_ranked_cpt(
        (parent_state_ids,),
        child_state_ids,
        weights=(1.0,),
        weakest_link_strength=0.0,
        sigma=sigma,
        max_cells=max_cells,
    )


def materialize_ranked_cpt(
    ordered_parent_state_ids: tuple[tuple[str, ...], ...],
    child_state_ids: tuple[str, ...],
    *,
    weights: tuple[float, ...],
    weakest_link_strength: float,
    sigma: float,
    max_cells: int = DEFAULT_MAX_CPT_CELLS,
) -> CptMaterialization:
    if not ordered_parent_state_ids:
        raise CptMaterializationError("ranked CPT requires at least one parent")
    for index, states in enumerate(ordered_parent_state_ids):
        _validate_state_ids(states, f"ordered_parent_state_ids[{index}]")
    _validate_state_ids(child_state_ids, "child_state_ids")
    _validate_materialization_size(ordered_parent_state_ids, child_state_ids, max_cells)
    if len(weights) != len(ordered_parent_state_ids):
        raise CptMaterializationError("weights must align with ordered parents")
    if (
        any(
            not isinstance(weight, (int, float))
            or isinstance(weight, bool)
            or not math.isfinite(weight)
            or weight < 0.0
            for weight in weights
        )
        or abs(math.fsum(weights) - 1.0) > 1e-9
    ):
        raise CptMaterializationError("weights must be finite, non-negative, and sum to one")
    if (
        not isinstance(weakest_link_strength, (int, float))
        or isinstance(weakest_link_strength, bool)
        or not math.isfinite(weakest_link_strength)
        or weakest_link_strength < 0.0
        or weakest_link_strength > 1.0
    ):
        raise CptMaterializationError("weakest_link_strength must be within [0, 1]")
    if (
        not isinstance(sigma, (int, float))
        or isinstance(sigma, bool)
        or not math.isfinite(sigma)
        or sigma <= 0.0
    ):
        raise CptMaterializationError("sigma must be a finite positive number")

    assignments = tuple(itertools.product(*ordered_parent_state_ids))
    probabilities: list[tuple[float, ...]] = []
    child_max_rank = len(child_state_ids) - 1
    state_ranks = tuple(
        {
            state_id: index * child_max_rank / (len(states) - 1)
            for index, state_id in enumerate(states)
        }
        for states in ordered_parent_state_ids
    )
    strength = float(weakest_link_strength)
    for assignment in assignments:
        ranks = tuple(state_ranks[index][state_id] for index, state_id in enumerate(assignment))
        weighted_rank = math.fsum(
            float(weight) * rank for weight, rank in zip(weights, ranks, strict=True)
        )
        center = (1.0 - strength) * weighted_rank + strength * min(ranks)
        center = min(float(child_max_rank), max(0.0, center))
        probabilities.append(_gaussian_row(center, len(child_state_ids), float(sigma)))
    return CptMaterialization(
        parent_assignments=assignments,
        probabilities=tuple(probabilities),
    )


def _require_materialized_shape(cpt: CptVersion) -> tuple[int, ...]:
    cardinalities = tuple(len(states) for states in cpt.ordered_parent_state_ids)
    expected_rows = _product(cardinalities)
    if cpt.mode is CptMode.INCOMPLETE or len(cpt.materialized_probabilities) != expected_rows:
        raise CptMigrationError("source CPT must be complete before migration")
    if any(len(row) != len(cpt.child_state_ids) for row in cpt.materialized_probabilities):
        raise CptMigrationError("source CPT row width does not match child states")
    for row in cpt.materialized_probabilities:
        if (
            any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or value < 0.0
                or value > 1.0
                for value in row
            )
            or abs(math.fsum(row) - 1.0) > DEFAULT_ROW_SUM_TOLERANCE
        ):
            raise CptMigrationError(
                "source CPT probabilities must be finite, bounded, and normalized"
            )
    return cardinalities


def _rehash(cpt: CptVersion) -> CptVersion:
    provisional = cpt.model_copy(update={"content_hash": "0" * 64})
    return provisional.model_copy(update={"content_hash": component_content_hash(provisional)})


def add_parent_preserving_independence(
    cpt: CptVersion,
    parent: ComponentIdRef,
    parent_state_ids: tuple[str, ...],
) -> CptVersion:
    """Append a parent and replicate every old row for each new parent state."""

    if parent.kind not in {
        ComponentKind.BN_NODE_VERSION,
        ComponentKind.EVIDENCE_BINDING_VERSION,
    }:
        raise CptMigrationError("new parent must identify a BN variable")
    if parent in cpt.ordered_parent_variable_ids:
        raise CptMigrationError("new parent is already present")
    if len(parent_state_ids) < 2 or len(parent_state_ids) != len(set(parent_state_ids)):
        raise CptMigrationError("new parent states must contain at least two unique IDs")
    _require_materialized_shape(cpt)
    rows = tuple(
        row
        for old_row in cpt.materialized_probabilities
        for row in (old_row,) * len(parent_state_ids)
    )
    metadata = dict(cpt.generator_metadata)
    metadata["last_migration"] = "add_parent_preserving_independence_v1"
    return _rehash(
        cpt.model_copy(
            update={
                "ordered_parent_variable_ids": (
                    *cpt.ordered_parent_variable_ids,
                    parent,
                ),
                "ordered_parent_state_ids": (
                    *cpt.ordered_parent_state_ids,
                    parent_state_ids,
                ),
                "materialized_probabilities": rows,
                "generator_metadata": metadata,
                "mode": CptMode.MANUAL,
            }
        )
    )


def remove_parent_with_marginal_weights(
    cpt: CptVersion,
    parent: ComponentIdRef,
    *,
    weights: tuple[float, ...] | None,
) -> CptVersion:
    """Remove one parent by an explicit weighted marginal; never guess a prior."""

    try:
        removed_index = next(
            index
            for index, reference in enumerate(cpt.ordered_parent_variable_ids)
            if reference == parent
        )
    except StopIteration as error:
        raise CptMigrationError(
            f"parent {parent.kind.value}:{parent.version_id} does not exist"
        ) from error
    if weights is None:
        raise CptMigrationError("explicit marginal weights are required to remove a parent")
    removed_states = cpt.ordered_parent_state_ids[removed_index]
    if len(weights) != len(removed_states):
        raise CptMigrationError("marginal weights must align with removed parent states")
    if (
        any(
            not isinstance(weight, (int, float))
            or isinstance(weight, bool)
            or not math.isfinite(weight)
            or weight < 0.0
            for weight in weights
        )
        or abs(math.fsum(weights) - 1.0) > 1e-9
    ):
        raise CptMigrationError("marginal weights must be finite, non-negative, and sum to one")
    cardinalities = _require_materialized_shape(cpt)
    remaining_cardinalities = tuple(
        cardinality for index, cardinality in enumerate(cardinalities) if index != removed_index
    )
    new_rows: list[tuple[float, ...]] = []
    remaining_assignments = itertools.product(
        *(range(cardinality) for cardinality in remaining_cardinalities)
    )
    for remaining_assignment in remaining_assignments:
        result = [0.0] * len(cpt.child_state_ids)
        for removed_state_index, weight in enumerate(weights):
            full_assignment = list(remaining_assignment)
            full_assignment.insert(removed_index, removed_state_index)
            row = cpt.materialized_probabilities[
                _assignment_index(tuple(full_assignment), cardinalities)
            ]
            for child_index, probability in enumerate(row):
                result[child_index] += float(weight) * probability
        new_rows.append(tuple(result))
    metadata = dict(cpt.generator_metadata)
    metadata["last_migration"] = "remove_parent_explicit_marginal_v1"
    return _rehash(
        cpt.model_copy(
            update={
                "ordered_parent_variable_ids": tuple(
                    parent
                    for index, parent in enumerate(cpt.ordered_parent_variable_ids)
                    if index != removed_index
                ),
                "ordered_parent_state_ids": tuple(
                    states
                    for index, states in enumerate(cpt.ordered_parent_state_ids)
                    if index != removed_index
                ),
                "materialized_probabilities": tuple(new_rows),
                "generator_metadata": metadata,
                "mode": CptMode.MANUAL,
            }
        )
    )


def invalidate_cpts_for_state_change(
    cpts: tuple[CptVersion, ...],
    variable: ComponentIdRef,
    new_state_ids: tuple[str, ...],
) -> tuple[CptVersion, ...]:
    """Mark every child/dependent CPT incomplete after an ordered state-space edit."""

    if len(new_state_ids) < 2 or len(new_state_ids) != len(set(new_state_ids)):
        raise CptMigrationError("new state IDs must contain at least two unique values")
    migrated: list[CptVersion] = []
    for cpt in cpts:
        child_changed = cpt.child_variable_id == variable
        parent_indexes = tuple(
            index
            for index, parent in enumerate(cpt.ordered_parent_variable_ids)
            if parent == variable
        )
        if not child_changed and not parent_indexes:
            migrated.append(cpt)
            continue
        parent_states = list(cpt.ordered_parent_state_ids)
        for index in parent_indexes:
            parent_states[index] = new_state_ids
        metadata = dict(cpt.generator_metadata)
        metadata["incomplete_reason"] = "dependent_state_space_changed_v1"
        migrated.append(
            _rehash(
                cpt.model_copy(
                    update={
                        "child_state_ids": (
                            new_state_ids if child_changed else cpt.child_state_ids
                        ),
                        "ordered_parent_state_ids": tuple(parent_states),
                        "materialized_probabilities": (),
                        "mode": CptMode.INCOMPLETE,
                        "generator_metadata": metadata,
                    }
                )
            )
        )
    return tuple(migrated)


__all__ = [
    "DEFAULT_MAX_CPT_CELLS",
    "DEFAULT_ROW_SUM_TOLERANCE",
    "BayesianVariable",
    "CptDiagnostic",
    "CptDiagnosticSeverity",
    "CptMaterialization",
    "CptMaterializationError",
    "CptMigrationError",
    "CptValidationOutcome",
    "VariableCatalog",
    "add_parent_preserving_independence",
    "invalidate_cpts_for_state_change",
    "materialize_ordered_single_parent",
    "materialize_ranked_cpt",
    "materialize_uniform_prior",
    "remove_parent_with_marginal_weights",
    "validate_cpt",
]
