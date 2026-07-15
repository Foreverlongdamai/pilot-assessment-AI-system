"""Dynamic catalog for packaged and expert-created evidence recipes."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from importlib.resources import files
from pathlib import PurePosixPath
from typing import Literal, cast

from pilot_assessment.contracts.evidence_recipe import (
    EvidenceRecipe,
    RecipeScientificStatus,
)

MigrationKind = Literal["legacy_operator_migration", "operator_composition"]


class RecipeCatalogError(ValueError):
    """Raised when recipe inventory is malformed or contains duplicate identities."""


class RecipeCatalogLookupError(KeyError):
    """Raised when a recipe or anchor is absent from the catalog."""


@dataclass(frozen=True, slots=True)
class StarterRecipeSource:
    """Machine-readable provenance for one packaged engineering starter."""

    anchor_id: str
    recipe_resource: str
    migration_kind: MigrationKind
    legacy_parameter_resource: str
    legacy_plugin_id: str | None
    legacy_plugin_version: str | None
    legacy_status: str
    scientific_status: RecipeScientificStatus


def _require_string(mapping: Mapping[str, object], field: str) -> str:
    value = mapping.get(field)
    if type(value) is not str or not value:
        raise RecipeCatalogError(f"catalog entry field {field!r} must be a string")
    return value


def _parse_source(value: object) -> StarterRecipeSource:
    if not isinstance(value, Mapping):
        raise RecipeCatalogError("catalog entries must be JSON objects")
    mapping = cast(Mapping[str, object], value)
    migration_kind = _require_string(mapping, "migration_kind")
    if migration_kind not in {"legacy_operator_migration", "operator_composition"}:
        raise RecipeCatalogError(f"unsupported starter recipe migration_kind {migration_kind!r}")
    try:
        scientific_status = RecipeScientificStatus(_require_string(mapping, "scientific_status"))
    except ValueError as error:
        raise RecipeCatalogError("invalid starter recipe scientific_status") from error
    legacy_plugin_id = mapping.get("legacy_plugin_id")
    legacy_plugin_version = mapping.get("legacy_plugin_version")
    if legacy_plugin_id is not None and (type(legacy_plugin_id) is not str or not legacy_plugin_id):
        raise RecipeCatalogError("legacy_plugin_id must be null or a non-empty string")
    if legacy_plugin_version is not None and (
        type(legacy_plugin_version) is not str or not legacy_plugin_version
    ):
        raise RecipeCatalogError("legacy_plugin_version must be null or a non-empty string")
    if (legacy_plugin_id is None) is not (legacy_plugin_version is None):
        raise RecipeCatalogError(
            "legacy_plugin_id and legacy_plugin_version must both be set or null"
        )
    return StarterRecipeSource(
        anchor_id=_require_string(mapping, "anchor_id"),
        recipe_resource=_require_string(mapping, "recipe_resource"),
        migration_kind=cast(MigrationKind, migration_kind),
        legacy_parameter_resource=_require_string(mapping, "legacy_parameter_resource"),
        legacy_plugin_id=legacy_plugin_id,
        legacy_plugin_version=legacy_plugin_version,
        legacy_status=_require_string(mapping, "legacy_status"),
        scientific_status=scientific_status,
    )


def _safe_resource_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise RecipeCatalogError(f"unsafe recipe resource path {value!r}")
    if path.suffix != ".json":
        raise RecipeCatalogError(f"recipe resource must be JSON: {value!r}")
    return path


class EvidenceRecipeCatalog:
    """Runtime-sized inventory with no built-in assumption about anchor count."""

    def __init__(self, recipes: Iterable[EvidenceRecipe] = ()) -> None:
        self._recipes_by_id: dict[str, EvidenceRecipe] = {}
        self._recipe_ids_by_anchor: dict[str, str] = {}
        self._sources_by_recipe_id: dict[str, StarterRecipeSource] = {}
        for recipe in recipes:
            self.register(recipe)

    def register(
        self,
        recipe: EvidenceRecipe,
        *,
        source: StarterRecipeSource | None = None,
    ) -> None:
        """Register any contract-valid recipe without Anchor-ID branching."""

        if not isinstance(recipe, EvidenceRecipe):
            raise RecipeCatalogError("recipe must use the canonical EvidenceRecipe contract")
        recipe_id = recipe.recipe_id
        anchor_id = recipe.anchor.anchor_id
        if recipe_id in self._recipes_by_id:
            raise RecipeCatalogError(f"duplicate evidence recipe ID {recipe_id!r}")
        if anchor_id in self._recipe_ids_by_anchor:
            raise RecipeCatalogError(f"duplicate evidence anchor ID {anchor_id!r}")
        if source is not None:
            if source.anchor_id != anchor_id:
                raise RecipeCatalogError(
                    f"source anchor {source.anchor_id!r} does not match recipe {anchor_id!r}"
                )
            if source.scientific_status is not recipe.anchor.scientific_status:
                raise RecipeCatalogError(
                    f"source scientific status does not match recipe {recipe_id!r}"
                )
        self._recipes_by_id[recipe_id] = recipe
        self._recipe_ids_by_anchor[anchor_id] = recipe_id
        if source is not None:
            self._sources_by_recipe_id[recipe_id] = source

    def get(self, recipe_id: str) -> EvidenceRecipe:
        try:
            return self._recipes_by_id[recipe_id]
        except KeyError as error:
            raise RecipeCatalogLookupError(recipe_id) from error

    def get_by_anchor(self, anchor_id: str) -> EvidenceRecipe:
        try:
            recipe_id = self._recipe_ids_by_anchor[anchor_id]
        except KeyError as error:
            raise RecipeCatalogLookupError(anchor_id) from error
        return self._recipes_by_id[recipe_id]

    def source_for(self, recipe_id: str) -> StarterRecipeSource | None:
        if recipe_id not in self._recipes_by_id:
            raise RecipeCatalogLookupError(recipe_id)
        return self._sources_by_recipe_id.get(recipe_id)

    def recipes(self) -> tuple[EvidenceRecipe, ...]:
        return tuple(self._recipes_by_id[key] for key in sorted(self._recipes_by_id))

    def __iter__(self) -> Iterator[EvidenceRecipe]:
        return iter(self.recipes())

    def __len__(self) -> int:
        return len(self._recipes_by_id)


def load_packaged_starter_catalog() -> EvidenceRecipeCatalog:
    """Load the editable packaged inventory; its current size is not a platform limit."""

    package = files("pilot_assessment.evidence.profile_data")
    raw_manifest = json.loads(package.joinpath("catalog.json").read_text(encoding="utf-8"))
    if not isinstance(raw_manifest, Mapping):
        raise RecipeCatalogError("starter recipe catalog must be a JSON object")
    manifest = cast(Mapping[str, object], raw_manifest)
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise RecipeCatalogError("starter recipe catalog entries must be a JSON array")

    catalog = EvidenceRecipeCatalog()
    for raw_entry in entries:
        source = _parse_source(raw_entry)
        resource_path = _safe_resource_path(source.recipe_resource)
        resource = package.joinpath(*resource_path.parts)
        try:
            raw_recipe = json.loads(resource.read_text(encoding="utf-8"))
            recipe = EvidenceRecipe.model_validate(raw_recipe)
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as error:
            raise RecipeCatalogError(
                f"cannot load starter recipe resource {source.recipe_resource!r}"
            ) from error
        catalog.register(recipe, source=source)
    return catalog


__all__ = [
    "EvidenceRecipeCatalog",
    "MigrationKind",
    "RecipeCatalogError",
    "RecipeCatalogLookupError",
    "StarterRecipeSource",
    "load_packaged_starter_catalog",
]
