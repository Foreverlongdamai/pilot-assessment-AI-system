from __future__ import annotations

from importlib.resources import files

from pilot_assessment.evidence.catalog import load_packaged_starter_catalog
from pilot_assessment.model_library.migration import (
    MigrationDiagnosticCode,
    preflight_recipe_catalog,
    preflight_recipe_migration,
)
from pilot_assessment.model_library.sources import load_hover_source_catalog


def test_all_packaged_m4r_recipes_receive_generic_compatibility_reports() -> None:
    recipe_catalog = load_packaged_starter_catalog()
    source_catalog = load_hover_source_catalog()

    reports = preflight_recipe_catalog(recipe_catalog, source_catalog)

    assert len(reports) == len(recipe_catalog) == 18
    assert len([report for report in reports if report.compatible]) == 17
    incompatible = [report for report in reports if not report.compatible]
    assert len(incompatible) == 1
    legacy = incompatible[0]
    assert legacy.recipe_id == "starter.o8"
    assert legacy.legacy_only
    assert [diagnostic.code for diagnostic in legacy.diagnostics] == [
        MigrationDiagnosticCode.EVIDENCE_OBSERVATION_INPUT,
        MigrationDiagnosticCode.EVIDENCE_OBSERVATION_INPUT,
    ]
    assert [diagnostic.field_path for diagnostic in legacy.diagnostics] == [
        ("inputs", "0", "source_id"),
        ("inputs", "1", "source_id"),
    ]
    assert [diagnostic.source_path for diagnostic in legacy.diagnostics] == [
        ("anchor.O1-score",),
        ("anchor.O5-score",),
    ]


def test_evidence_observation_rejection_does_not_depend_on_recipe_or_anchor_id() -> None:
    recipe = load_packaged_starter_catalog().get("starter.o8")
    renamed = recipe.model_copy(
        update={
            "recipe_id": "expert.parallel-composite",
            "anchor": recipe.anchor.model_copy(update={"anchor_id": "EXPERT-COMPOSITE"}),
        }
    )

    report = preflight_recipe_migration(renamed, load_hover_source_catalog())

    assert not report.compatible
    assert report.legacy_only
    assert {diagnostic.source_id for diagnostic in report.diagnostics} == {
        "anchor.O1-score",
        "anchor.O5-score",
    }


def test_preflight_returns_lineage_metadata_without_mutating_legacy_recipe_bytes() -> None:
    package = files("pilot_assessment.evidence.profile_data")
    resource = package.joinpath("recipes", "o8.json")
    before = resource.read_bytes()
    recipe = load_packaged_starter_catalog().get("starter.o8")

    report = preflight_recipe_migration(recipe, load_hover_source_catalog())

    assert resource.read_bytes() == before
    assert report.lineage.source_recipe_id == "starter.o8"
    assert report.lineage.source_recipe_version == 1
    assert report.lineage.source_anchor_id == "O8"
    assert len(report.lineage.source_content_hash) == 64
    assert not hasattr(report, "migrated_recipe")


def test_unknown_binding_reports_the_recipe_field_path_and_source_path() -> None:
    recipe = load_packaged_starter_catalog().get("starter.o1")
    bad_input = recipe.inputs[0].model_copy(update={"source_id": "unknown.telemetry"})
    changed = recipe.model_copy(update={"inputs": (bad_input, *recipe.inputs[1:])})

    report = preflight_recipe_migration(changed, load_hover_source_catalog())

    assert not report.compatible
    assert report.diagnostics[0].code is MigrationDiagnosticCode.UNKNOWN_SOURCE
    assert report.diagnostics[0].field_path == ("inputs", "0", "source_id")
    assert report.diagnostics[0].source_path == ("unknown.telemetry",)
