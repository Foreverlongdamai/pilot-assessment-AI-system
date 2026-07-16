from __future__ import annotations

from pilot_assessment.contracts.assessment_scheme import (
    DraftValidationState,
    SchemeDraft,
)
from pilot_assessment.schemes.validation import (
    SchemeDiagnosticSeverity,
    SchemeValidationDisposition,
    validate_executable_scheme,
    validate_scheme_draft,
)
from tests.schemes.support import (
    build_fixture,
    cyclic_recipe,
    recipe_with_unknown_operator,
)


def _codes(outcome) -> set[str]:
    return {diagnostic.code for diagnostic in outcome.diagnostics}


def test_unknown_operator_and_evidence_recipe_cycle_are_blocking() -> None:
    unknown = build_fixture(recipe=recipe_with_unknown_operator())
    cyclic = build_fixture(recipe=cyclic_recipe())

    unknown_outcome = validate_executable_scheme(
        unknown.scheme,
        unknown.repository,
        unknown.source_catalog,
        unknown.operator_registry,
    )
    cyclic_outcome = validate_executable_scheme(
        cyclic.scheme,
        cyclic.repository,
        cyclic.source_catalog,
        cyclic.operator_registry,
    )

    assert "recipe.operator_unknown" in _codes(unknown_outcome)
    assert "recipe.graph_cycle" in _codes(cyclic_outcome)
    assert unknown_outcome.disposition is SchemeValidationDisposition.INVALID
    assert cyclic_outcome.disposition is SchemeValidationDisposition.INVALID


def test_bayesian_cycle_is_the_second_independent_dag_blocker() -> None:
    fixture = build_fixture(bn_cycle=True)

    outcome = validate_executable_scheme(
        fixture.scheme,
        fixture.repository,
        fixture.source_catalog,
        fixture.operator_registry,
    )

    assert "scheme.bayesian_cycle" in _codes(outcome)
    assert outcome.disposition is SchemeValidationDisposition.INVALID


def test_unvalidated_scientific_status_and_non_monotonic_cpt_do_not_block() -> None:
    fixture = build_fixture(state_count=4)

    outcome = validate_executable_scheme(
        fixture.scheme,
        fixture.repository,
        fixture.source_catalog,
        fixture.operator_registry,
    )

    assert outcome.disposition is SchemeValidationDisposition.EXECUTABLE
    assert any(
        diagnostic.severity is SchemeDiagnosticSeverity.WARNING
        and diagnostic.code == "scheme.scientific_status_unvalidated"
        for diagnostic in outcome.diagnostics
    )
    assert not [diagnostic for diagnostic in outcome.diagnostics if diagnostic.blocking]


def test_incomplete_draft_is_persistable_but_not_executable() -> None:
    fixture = build_fixture()
    draft = SchemeDraft(
        draft_id="draft.generic",
        base_scheme_version_id=None,
        graph_version=0,
        layout_version=0,
        history_cursor=0,
        retained_component_refs=(),
        candidate_components=(),
        extraction_edges=(),
        bayesian_edges=(),
        output_node_ids=(),
        validation_state=DraftValidationState.INCOMPLETE,
        diagnostics=(),
    )

    outcome = validate_scheme_draft(draft, fixture.repository)

    assert outcome.disposition is SchemeValidationDisposition.DRAFT_INCOMPLETE
    assert "draft.output_missing" in _codes(outcome)
