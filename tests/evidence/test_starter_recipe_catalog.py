from __future__ import annotations

import json
from importlib.resources import files

from pilot_assessment.evidence.builtins import register_builtin_operators
from pilot_assessment.evidence.catalog import (
    EvidenceRecipeCatalog,
    load_packaged_starter_catalog,
)
from pilot_assessment.evidence.compiler import compile_recipe
from pilot_assessment.evidence.registry import OperatorRegistry
from pilot_assessment.evidence.repository import InMemoryRecipeRepository
from pilot_assessment.evidence.service import EvidenceRecipeService
from tests.evidence.runtime_support import constant_recipe

_PACKAGED_ANCHORS = {
    *(f"O{index}" for index in range(1, 14)),
    *(f"H{index}" for index in range(1, 6)),
}


def _registry() -> OperatorRegistry:
    registry = OperatorRegistry()
    register_builtin_operators(registry)
    return registry


def test_all_current_starters_load_and_compile_as_editable_templates() -> None:
    catalog = load_packaged_starter_catalog()
    registry = _registry()

    assert {recipe.anchor.anchor_id for recipe in catalog} == _PACKAGED_ANCHORS
    assert len({recipe.recipe_id for recipe in catalog}) == len(catalog)
    for recipe in catalog:
        assert recipe.anchor.scientific_status.value == "starter_template"
        compile_recipe(recipe, registry)


def test_migration_provenance_does_not_invent_missing_legacy_plugins() -> None:
    catalog = load_packaged_starter_catalog()
    old_registry = json.loads(
        files("pilot_assessment.anchors").joinpath("registry-v1.json").read_text(encoding="utf-8")
    )
    registered_legacy_plugins = {entry["plugin_id"] for entry in old_registry["entries"]}
    parameter_package = files("pilot_assessment.anchors.profile_data.parameters")

    for recipe in catalog:
        source = catalog.source_for(recipe.recipe_id)
        assert source is not None
        assert parameter_package.joinpath(source.legacy_parameter_resource).is_file()
        if recipe.anchor.anchor_id in {"O13", "H4", "H5"}:
            assert source.migration_kind == "operator_composition"
            assert source.legacy_plugin_id is None
            assert source.legacy_plugin_version is None
            assert source.legacy_status == "parameter_resource_only_no_legacy_plugin"
        else:
            assert source.migration_kind == "legacy_operator_migration"
            assert source.legacy_plugin_id in registered_legacy_plugins
            assert source.legacy_status == "retained_reference_replay_source"


def test_arbitrary_nineteenth_recipe_registers_previews_and_applies_without_id_branch() -> None:
    catalog = load_packaged_starter_catalog()
    base = constant_recipe(7.0, recipe_id="expert.custom.nineteen")
    custom = base.model_copy(
        update={
            "anchor": base.anchor.model_copy(
                update={
                    "anchor_id": "EXPERT-19",
                    "name": "Expert-created anchor",
                }
            )
        }
    )
    catalog.register(custom)

    registry = _registry()
    compile_recipe(catalog.get_by_anchor("EXPERT-19"), registry)
    repository = InMemoryRecipeRepository()
    service = EvidenceRecipeService(repository, registry)
    service.create_draft(custom, author_id="expert")

    preview = service.preview(custom.recipe_id, execution_inputs={})
    applied = service.apply(custom.recipe_id, author_id="expert", note="new anchor")

    assert isinstance(catalog, EvidenceRecipeCatalog)
    assert len(catalog) == len(_PACKAGED_ANCHORS) + 1
    assert preview.succeeded is True
    assert preview.execution is not None
    assert preview.execution.outputs["primary"] == 7.0
    assert applied.recipe.anchor.anchor_id == "EXPERT-19"
