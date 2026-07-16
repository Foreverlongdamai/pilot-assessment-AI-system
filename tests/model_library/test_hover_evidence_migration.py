from __future__ import annotations

from importlib.resources import files

from pilot_assessment.contracts.model_components import ComponentKind
from pilot_assessment.model_library.migration import load_hover_evidence_inventory
from pilot_assessment.model_library.repository import (
    InMemoryComponentLibraryRepository,
    component_content_hash,
)
from tests.schemes.support import NOW


def test_m4r_inventory_imports_only_compatible_recipes_and_preserves_legacy_bytes() -> None:
    resource = files("pilot_assessment.evidence.profile_data").joinpath("recipes", "o8.json")
    before = resource.read_bytes()

    inventory = load_hover_evidence_inventory()

    assert resource.read_bytes() == before
    assert len(inventory.concepts) == 18
    assert len(inventory.imported_versions) == 17
    assert len(inventory.parallel_versions) == 1
    assert len(inventory.active_versions) == 18
    assert len(inventory.legacy_artifacts) == 1
    legacy = inventory.legacy_artifacts[0]
    assert legacy.recipe.recipe_id == "starter.o8"
    assert legacy.compatibility.legacy_only
    assert legacy.raw_sha256 == "ceec4439a2769a0aef78b3e4a9852e8b836d8df0adf58241ecd6d6a8a8a1372d"
    assert legacy.typed_content_hash == (
        "eeb8b1959049a2f2c762662a6a52ccdfb3cb42b262e3d7868d90e5b814043dc8"
    )
    assert all(version.recipe.recipe_id != "starter.o8" for version in inventory.imported_versions)
    assert inventory.parallel_versions[0].concept_id == legacy.concept_id


def test_imported_versions_keep_exact_recipe_and_applied_revision_lineage() -> None:
    inventory = load_hover_evidence_inventory()
    repository = InMemoryComponentLibraryRepository()
    for concept in inventory.concepts:
        repository.add(concept, recorded_at=NOW)
    for version in inventory.active_versions:
        assert version.content_hash == component_content_hash(version)
        assert version.lineage.source_version_ids
        assert version.recipe.recipe_id in (version.lineage.note or "")
        repository.add(version, recorded_at=NOW)

    assert len(repository.list_records()) == len(inventory.concepts) + len(
        inventory.active_versions
    )
    first = inventory.imported_versions[0]
    assert repository.get_exact(ComponentKind.EVIDENCE_VERSION, first.evidence_version_id) == first
