from __future__ import annotations

import pytest

from pilot_assessment.contracts.model_components import RawModality, SourceKind
from pilot_assessment.model_library.sources import create_source_descriptor
from pilot_assessment.schemes.validation import (
    SchemeValidationDisposition,
    validate_executable_scheme,
)
from tests.schemes.support import NOW, build_fixture, number_type, pin, revise_scheme


def _codes(outcome) -> set[str]:
    return {diagnostic.code for diagnostic in outcome.diagnostics}


@pytest.mark.parametrize(
    ("field", "expected_code"),
    (
        ("bn_node_versions", "scheme.parent_missing"),
        ("cpt_versions", "scheme.cpt_missing"),
        ("evidence_versions", "scheme.evidence_missing"),
        ("evidence_binding_versions", "scheme.binding_missing"),
        ("source_descriptors", "scheme.source_missing"),
    ),
)
def test_missing_exact_dependency_is_reported_at_a_stable_scheme_location(
    field: str,
    expected_code: str,
) -> None:
    fixture = build_fixture()
    scheme = revise_scheme(fixture, **{field: ()})

    outcome = validate_executable_scheme(
        scheme,
        fixture.repository,
        fixture.source_catalog,
        fixture.operator_registry,
    )

    assert outcome.disposition is SchemeValidationDisposition.INVALID
    assert expected_code in _codes(outcome)
    diagnostic = next(item for item in outcome.diagnostics if item.code == expected_code)
    assert diagnostic.location.startswith("/")
    assert diagnostic.component_id is not None


def test_pin_hash_mismatch_and_unknown_output_are_blocking_exact_closure_errors() -> None:
    fixture = build_fixture()
    evidence_pin = fixture.scheme.evidence_versions[0].model_copy(update={"content_hash": "f" * 64})
    missing_output = fixture.scheme.output_node_ids[0].model_copy(
        update={"version_id": "bn-version.not-present"}
    )
    scheme = revise_scheme(
        fixture,
        evidence_versions=(evidence_pin,),
        output_node_ids=(missing_output,),
    )

    outcome = validate_executable_scheme(
        scheme,
        fixture.repository,
        fixture.source_catalog,
        fixture.operator_registry,
    )

    assert {"scheme.pin_hash_mismatch", "scheme.output_missing"}.issubset(_codes(outcome))


def test_duplicate_variable_pin_is_rejected_even_if_dto_validation_was_bypassed() -> None:
    fixture = build_fixture()
    duplicate = fixture.scheme.bn_node_versions[0]
    scheme = revise_scheme(fixture, bn_node_versions=(duplicate, duplicate))

    outcome = validate_executable_scheme(
        scheme,
        fixture.repository,
        fixture.source_catalog,
        fixture.operator_registry,
    )

    assert "scheme.variable_duplicate" in _codes(outcome)


def test_required_task_semantic_must_be_declared_by_the_exact_task_profile() -> None:
    fixture = build_fixture(require_task_semantic=False)

    outcome = validate_executable_scheme(
        fixture.scheme,
        fixture.repository,
        fixture.source_catalog,
        fixture.operator_registry,
    )

    assert "scheme.task_semantic_missing" in _codes(outcome)


def test_orphan_pin_is_rejected_instead_of_silently_expanding_the_scheme() -> None:
    fixture = build_fixture()
    orphan = create_source_descriptor(
        source_id="X.unused",
        kind=SourceKind.RAW_STREAM,
        name="Unused exact source",
        description="Valid but unused source for orphan-closure validation.",
        declared_type=number_type(),
        raw_modality=RawModality.X,
        metadata={"fixture": True},
    )
    fixture.repository.add(orphan, recorded_at=NOW)
    fixture.source_catalog.register(orphan)
    scheme = revise_scheme(
        fixture,
        source_descriptors=(*fixture.scheme.source_descriptors, pin(orphan)),
    )

    outcome = validate_executable_scheme(
        scheme,
        fixture.repository,
        fixture.source_catalog,
        fixture.operator_registry,
    )

    assert "scheme.orphan_pin" in _codes(outcome)
    diagnostic = next(
        item
        for item in outcome.diagnostics
        if item.code == "scheme.orphan_pin" and item.component_id == "X.unused"
    )
    assert diagnostic.location == "/source_descriptors"


@pytest.mark.parametrize("state_count", (2, 4))
def test_exact_valid_closure_accepts_arbitrary_state_count_and_ids(state_count: int) -> None:
    fixture = build_fixture(state_count=state_count)

    outcome = validate_executable_scheme(
        fixture.scheme,
        fixture.repository,
        fixture.source_catalog,
        fixture.operator_registry,
    )

    assert outcome.disposition is SchemeValidationDisposition.EXECUTABLE
    assert not [diagnostic for diagnostic in outcome.diagnostics if diagnostic.blocking]
