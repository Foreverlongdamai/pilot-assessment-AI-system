"""Read-only compatibility preflight for importing M4R Evidence recipes into M5."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeVar

from pilot_assessment.contracts.evidence_recipe import EvidenceRecipe
from pilot_assessment.contracts.model_components import RawModality
from pilot_assessment.model_library.identity import typed_content_sha256
from pilot_assessment.model_library.sources import (
    SourceCatalog,
    SourceCatalogLookupError,
    SourceDiagnosticCode,
)

_T = TypeVar("_T")


class MigrationDiagnosticCode(StrEnum):
    UNKNOWN_SOURCE = SourceDiagnosticCode.UNKNOWN_SOURCE.value
    PROVENANCE_CYCLE = SourceDiagnosticCode.PROVENANCE_CYCLE.value
    DERIVED_SOURCE_WITHOUT_DEPENDENCIES = (
        SourceDiagnosticCode.DERIVED_SOURCE_WITHOUT_DEPENDENCIES.value
    )
    EVIDENCE_OBSERVATION_INPUT = SourceDiagnosticCode.EVIDENCE_OBSERVATION_INPUT.value
    DECLARED_TYPE_MISMATCH = "declared_type_mismatch"


@dataclass(frozen=True, slots=True)
class MigrationLineageMetadata:
    source_contract_id: str
    source_contract_version: str
    source_recipe_id: str
    source_recipe_version: int
    source_anchor_id: str
    source_content_hash: str


@dataclass(frozen=True, slots=True)
class MigrationCompatibilityDiagnostic:
    code: MigrationDiagnosticCode
    source_id: str
    field_path: tuple[str, ...]
    source_path: tuple[str, ...]
    message: str


@dataclass(frozen=True, slots=True)
class RecipeMigrationCompatibilityReport:
    recipe_id: str
    anchor_id: str
    compatible: bool
    legacy_only: bool
    input_source_ids: tuple[str, ...]
    root_source_ids: tuple[str, ...]
    raw_modalities: tuple[RawModality, ...]
    lineage: MigrationLineageMetadata
    diagnostics: tuple[MigrationCompatibilityDiagnostic, ...]


def _lineage(recipe: EvidenceRecipe) -> MigrationLineageMetadata:
    payload = recipe.model_dump(mode="json")
    return MigrationLineageMetadata(
        source_contract_id=recipe.contract_id,
        source_contract_version=recipe.contract_version,
        source_recipe_id=recipe.recipe_id,
        source_recipe_version=recipe.recipe_version,
        source_anchor_id=recipe.anchor.anchor_id,
        source_content_hash=typed_content_sha256(
            recipe.contract_id,
            recipe.contract_version,
            payload,
        ),
    )


def _append_unique(values: list[_T], seen: set[_T], incoming: Iterable[_T]) -> None:
    for value in incoming:
        if value not in seen:
            seen.add(value)
            values.append(value)


def preflight_recipe_migration(
    recipe: EvidenceRecipe,
    source_catalog: SourceCatalog,
) -> RecipeMigrationCompatibilityReport:
    """Return compatibility and lineage metadata without rewriting the recipe."""

    diagnostics: list[MigrationCompatibilityDiagnostic] = []
    root_source_ids: list[str] = []
    root_seen: set[str] = set()
    raw_modalities: list[RawModality] = []
    modality_seen: set[RawModality] = set()

    for index, binding in enumerate(recipe.inputs):
        field_path = ("inputs", str(index), "source_id")
        closure = source_catalog.validate_extraction_sources((binding.source_id,))
        _append_unique(root_source_ids, root_seen, closure.root_source_ids)
        _append_unique(raw_modalities, modality_seen, closure.raw_modalities)
        for diagnostic in closure.diagnostics:
            diagnostics.append(
                MigrationCompatibilityDiagnostic(
                    code=MigrationDiagnosticCode(diagnostic.code.value),
                    source_id=diagnostic.source_id,
                    field_path=field_path,
                    source_path=diagnostic.source_path,
                    message=diagnostic.message,
                )
            )
        if closure.diagnostics:
            continue
        try:
            descriptor = source_catalog.resolve(binding.source_id)
        except SourceCatalogLookupError:
            continue
        if descriptor.declared_type != binding.declared_type:
            diagnostics.append(
                MigrationCompatibilityDiagnostic(
                    code=MigrationDiagnosticCode.DECLARED_TYPE_MISMATCH,
                    source_id=binding.source_id,
                    field_path=("inputs", str(index), "declared_type"),
                    source_path=(binding.source_id,),
                    message=(
                        f"recipe binding type for {binding.source_id!r} does not match its "
                        "source descriptor"
                    ),
                )
            )

    compatible = not diagnostics
    return RecipeMigrationCompatibilityReport(
        recipe_id=recipe.recipe_id,
        anchor_id=recipe.anchor.anchor_id,
        compatible=compatible,
        legacy_only=not compatible,
        input_source_ids=tuple(binding.source_id for binding in recipe.inputs),
        root_source_ids=tuple(root_source_ids),
        raw_modalities=tuple(raw_modalities),
        lineage=_lineage(recipe),
        diagnostics=tuple(diagnostics),
    )


def preflight_recipe_catalog(
    recipes: Iterable[EvidenceRecipe],
    source_catalog: SourceCatalog,
) -> tuple[RecipeMigrationCompatibilityReport, ...]:
    """Run the same source-driven preflight over an arbitrary recipe inventory."""

    return tuple(preflight_recipe_migration(recipe, source_catalog) for recipe in recipes)


__all__ = [
    "MigrationCompatibilityDiagnostic",
    "MigrationDiagnosticCode",
    "MigrationLineageMetadata",
    "RecipeMigrationCompatibilityReport",
    "preflight_recipe_catalog",
    "preflight_recipe_migration",
]
