from __future__ import annotations

import math

import pytest

from pilot_assessment.bayesian.validation import (
    CptDiagnosticSeverity,
    validate_cpt,
)
from pilot_assessment.contracts.assessment_scheme import AssessmentSchemeVersion
from pilot_assessment.contracts.model_components import CptMode, CptVersion
from pilot_assessment.model_library.repository import InMemoryComponentLibraryRepository
from pilot_assessment.schemes.validation import (
    SchemeValidationDisposition,
    validate_executable_scheme,
)
from tests.bayesian.support import cpt, node, state_space, variables
from tests.schemes.support import NOW, build_fixture, pin, rehash


def test_root_single_parent_and_multi_parent_tables_have_generic_valid_shapes() -> None:
    states = state_space("level", 3)
    left = node("variable.left", states)
    right = node("variable.right", states)
    root = node("variable.root", states)
    single = node("variable.single", states, parents=(root,))
    multi = node("variable.multi", states, parents=(left, right))
    root_cpt = cpt("cpt.variable.root", root, rows=((0.2, 0.3, 0.5),))
    single_cpt = cpt(
        "cpt.variable.single",
        single,
        parents=(root,),
        rows=((0.7, 0.2, 0.1), (0.2, 0.6, 0.2), (0.1, 0.2, 0.7)),
    )
    multi_cpt = cpt(
        "cpt.variable.multi",
        multi,
        parents=(left, right),
        rows=tuple((0.2, 0.3, 0.5) for _ in range(9)),
    )
    catalog = variables(root, single, left, right, multi)

    outcomes = tuple(validate_cpt(item, catalog) for item in (root_cpt, single_cpt, multi_cpt))

    assert all(outcome.executable for outcome in outcomes)
    assert [outcome.required_row_count for outcome in outcomes] == [1, 3, 9]
    assert [outcome.required_cell_count for outcome in outcomes] == [3, 9, 27]


@pytest.mark.parametrize(
    ("rows", "code"),
    (
        (((0.5, 0.5, 0.0),), "cpt.row_count_mismatch"),
        (((-0.1, 0.6, 0.5),) * 3, "cpt.probability_out_of_range"),
        (((1.1, 0.0, -0.1),) * 3, "cpt.probability_out_of_range"),
        (((math.nan, 0.5, 0.5),) * 3, "cpt.probability_non_finite"),
        (((0.2, 0.2, 0.2),) * 3, "cpt.row_not_normalized"),
    ),
)
def test_invalid_materialized_values_and_shape_are_blocking(rows, code: str) -> None:
    states = state_space("state", 3)
    parent = node("variable.parent", states)
    child = node("variable.child", states, parents=(parent,))
    valid = cpt(
        "cpt.variable.child",
        child,
        parents=(parent,),
        rows=((0.6, 0.3, 0.1),) * 3,
    )
    invalid = valid.model_copy(update={"materialized_probabilities": rows})

    outcome = validate_cpt(invalid, variables(parent, child))

    assert not outcome.executable
    assert code in {diagnostic.code for diagnostic in outcome.diagnostics}


def test_parent_order_state_order_incomplete_mode_and_cell_cap_are_blocking() -> None:
    states = state_space("state", 2)
    first = node("variable.first", states)
    second = node("variable.second", states)
    child = node("variable.child", states, parents=(first, second))
    valid = cpt(
        "cpt.variable.child",
        child,
        parents=(first, second),
        rows=((0.5, 0.5),) * 4,
    )
    reversed_parents = valid.model_copy(
        update={"ordered_parent_variable_ids": tuple(reversed(valid.ordered_parent_variable_ids))}
    )
    wrong_states = valid.model_copy(
        update={"ordered_parent_state_ids": (("wrong.0", "wrong.1"), states[0:2])}
    )
    incomplete = valid.model_copy(
        update={"mode": CptMode.INCOMPLETE, "materialized_probabilities": ()}
    )
    catalog = variables(first, second, child)

    order_outcome = validate_cpt(reversed_parents, catalog)
    state_outcome = validate_cpt(wrong_states, catalog)
    incomplete_outcome = validate_cpt(incomplete, catalog)
    capped_outcome = validate_cpt(valid, catalog, max_cells=7)

    assert "cpt.parent_order_mismatch" in {item.code for item in order_outcome.diagnostics}
    assert "cpt.parent_state_mismatch" in {item.code for item in state_outcome.diagnostics}
    assert "cpt.incomplete" in {item.code for item in incomplete_outcome.diagnostics}
    assert "cpt.cell_limit_exceeded" in {item.code for item in capped_outcome.diagnostics}


def test_valid_manual_non_monotonic_table_is_warning_only() -> None:
    states = state_space("state", 3)
    parent = node("variable.parent", states)
    child = node("variable.child", states, parents=(parent,))
    table = cpt(
        "cpt.variable.child",
        child,
        parents=(parent,),
        rows=((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    )

    outcome = validate_cpt(table, variables(parent, child))

    assert outcome.executable
    warning = next(item for item in outcome.diagnostics if item.code == "cpt.non_monotonic")
    assert warning.severity is CptDiagnosticSeverity.WARNING


def test_exact_scheme_validation_propagates_blocking_cpt_locations() -> None:
    fixture = build_fixture()
    original = next(
        item
        for item in fixture.components
        if isinstance(item, CptVersion) and not item.ordered_parent_variable_ids
    )
    invalid = rehash(original.model_copy(update={"materialized_probabilities": ((0.2, 0.2, 0.2),)}))
    assert isinstance(invalid, CptVersion)
    repository = InMemoryComponentLibraryRepository()
    for component in fixture.components:
        if not (
            isinstance(component, CptVersion)
            and component.cpt_version_id == original.cpt_version_id
        ):
            repository.add(component, recorded_at=NOW)
    repository.add(invalid, recorded_at=NOW)
    cpt_pins = tuple(
        pin(invalid) if reference.version_id == original.cpt_version_id else reference
        for reference in fixture.scheme.cpt_versions
    )
    scheme = fixture.scheme.model_copy(update={"cpt_versions": cpt_pins, "content_hash": "0" * 64})
    scheme = rehash(scheme)
    assert isinstance(scheme, AssessmentSchemeVersion)

    outcome = validate_executable_scheme(
        scheme,
        repository,
        fixture.source_catalog,
        fixture.operator_registry,
    )

    assert outcome.disposition is SchemeValidationDisposition.INVALID
    diagnostic = next(item for item in outcome.diagnostics if item.code == "cpt.row_not_normalized")
    assert diagnostic.location.startswith(
        f"/cpt_versions/{original.cpt_version_id}/materialized_probabilities/0"
    )
    assert diagnostic.component_id == original.cpt_version_id
