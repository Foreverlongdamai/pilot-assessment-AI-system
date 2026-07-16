"""Read-only compatibility preflight for importing M4R Evidence recipes into M5."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from importlib.resources import files
from pathlib import PurePosixPath
from typing import TypeVar, cast

from pydantic import ValidationError

from pilot_assessment.contracts.evidence_recipe import EvidenceRecipe
from pilot_assessment.contracts.model_components import (
    EvidenceConcept,
    EvidenceVersion,
    ModelScientificStatus,
    RawModality,
    VersionLineage,
)
from pilot_assessment.evidence.catalog import (
    RecipeCatalogLookupError,
    load_packaged_starter_catalog,
)
from pilot_assessment.model_library.identity import typed_content_sha256
from pilot_assessment.model_library.repository import component_content_hash
from pilot_assessment.model_library.sources import (
    SourceCatalog,
    SourceCatalogLookupError,
    SourceDiagnosticCode,
    load_hover_source_catalog,
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


class EvidenceMigrationError(ValueError):
    """Raised when packaged migration resources are incomplete or self-contradictory."""


@dataclass(frozen=True, slots=True)
class LegacyRecipeArtifact:
    concept_id: str
    source_applied_revision_id: str
    resource_path: str
    raw_sha256: str
    typed_content_hash: str
    recipe: EvidenceRecipe
    compatibility: RecipeMigrationCompatibilityReport


@dataclass(frozen=True, slots=True)
class EvidenceMigrationInventory:
    concepts: tuple[EvidenceConcept, ...]
    imported_versions: tuple[EvidenceVersion, ...]
    parallel_versions: tuple[EvidenceVersion, ...]
    legacy_artifacts: tuple[LegacyRecipeArtifact, ...]
    compatibility_reports: tuple[RecipeMigrationCompatibilityReport, ...]

    @property
    def active_versions(self) -> tuple[EvidenceVersion, ...]:
        return (*self.imported_versions, *self.parallel_versions)


@dataclass(frozen=True, slots=True)
class _MigrationEntry:
    source_recipe_id: str
    concept_id: str
    source_applied_revision_id: str
    evidence_version_id: str | None
    legacy_raw_sha256: str | None


@dataclass(frozen=True, slots=True)
class _ParallelEntry:
    concept_id: str
    evidence_version_id: str
    recipe_resource: str
    source_version_ids: tuple[str, ...]


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


def _resource_mapping(filename: str) -> dict[str, object]:
    resource = files("pilot_assessment.model_library").joinpath(
        "profile_data",
        "hover",
        filename,
    )
    try:
        value = json.loads(resource.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise EvidenceMigrationError(f"cannot load migration resource {filename!r}") from error
    if not isinstance(value, dict):
        raise EvidenceMigrationError(f"migration resource {filename!r} must be an object")
    return cast(dict[str, object], value)


def _string(mapping: dict[str, object], field: str) -> str:
    value = mapping.get(field)
    if type(value) is not str or not value:
        raise EvidenceMigrationError(f"migration field {field!r} must be a non-empty string")
    return value


def _optional_string(mapping: dict[str, object], field: str) -> str | None:
    value = mapping.get(field)
    if value is None:
        return None
    if type(value) is not str or not value:
        raise EvidenceMigrationError(f"migration field {field!r} must be null or a string")
    return value


def _array(mapping: dict[str, object], field: str) -> list[object]:
    value = mapping.get(field)
    if not isinstance(value, list):
        raise EvidenceMigrationError(f"migration field {field!r} must be an array")
    return cast(list[object], value)


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise EvidenceMigrationError(f"{label} must be an object")
    return cast(dict[str, object], value)


def _safe_json_resource(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts or path.suffix != ".json":
        raise EvidenceMigrationError(f"unsafe migration recipe resource {value!r}")
    return path


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise EvidenceMigrationError("migration created_at must be ISO-8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceMigrationError("migration created_at must be timezone-aware")
    return parsed


def _parse_entries(manifest: dict[str, object]) -> tuple[_MigrationEntry, ...]:
    result: list[_MigrationEntry] = []
    for index, value in enumerate(_array(manifest, "entries")):
        entry = _mapping(value, f"migration entries[{index}]")
        result.append(
            _MigrationEntry(
                source_recipe_id=_string(entry, "source_recipe_id"),
                concept_id=_string(entry, "concept_id"),
                source_applied_revision_id=_string(entry, "source_applied_revision_id"),
                evidence_version_id=_optional_string(entry, "evidence_version_id"),
                legacy_raw_sha256=_optional_string(entry, "legacy_raw_sha256"),
            )
        )
    if len({item.source_recipe_id for item in result}) != len(result):
        raise EvidenceMigrationError("migration source recipe IDs must be unique")
    return tuple(result)


def _parse_parallel_entries(manifest: dict[str, object]) -> tuple[_ParallelEntry, ...]:
    result: list[_ParallelEntry] = []
    for index, value in enumerate(_array(manifest, "parallel_versions")):
        entry = _mapping(value, f"parallel_versions[{index}]")
        raw_sources = _array(entry, "source_version_ids")
        if any(type(item) is not str or not item for item in raw_sources):
            raise EvidenceMigrationError("parallel source_version_ids must contain strings")
        result.append(
            _ParallelEntry(
                concept_id=_string(entry, "concept_id"),
                evidence_version_id=_string(entry, "evidence_version_id"),
                recipe_resource=_string(entry, "recipe_resource"),
                source_version_ids=cast(tuple[str, ...], tuple(raw_sources)),
            )
        )
    if len({item.evidence_version_id for item in result}) != len(result):
        raise EvidenceMigrationError("parallel Evidence version IDs must be unique")
    return tuple(result)


def _load_concepts() -> tuple[EvidenceConcept, ...]:
    resource = _resource_mapping("evidence-concepts.json")
    if resource.get("contract_id") != "evidence-concept-catalog":
        raise EvidenceMigrationError("Evidence concept catalog has an invalid contract_id")
    if resource.get("contract_version") != "0.1.0":
        raise EvidenceMigrationError("Evidence concept catalog has an unsupported version")
    try:
        concepts = tuple(
            EvidenceConcept.model_validate(item) for item in _array(resource, "concepts")
        )
    except (TypeError, ValidationError, ValueError) as error:
        raise EvidenceMigrationError(
            "Evidence concept catalog contains an invalid concept"
        ) from error
    if len({concept.concept_id for concept in concepts}) != len(concepts):
        raise EvidenceMigrationError("Evidence concept IDs must be unique")
    return tuple(sorted(concepts, key=lambda item: item.concept_id))


def _version_lineage(
    *,
    source_version_ids: tuple[str, ...],
    created_at: datetime,
    created_by: str,
    note: str,
) -> VersionLineage:
    return VersionLineage(
        source_version_ids=source_version_ids,
        created_at=created_at,
        created_by=created_by,
        note=note,
    )


def _evidence_version(
    *,
    version_id: str,
    concept_id: str,
    recipe: EvidenceRecipe,
    lineage: VersionLineage,
) -> EvidenceVersion:
    provisional = EvidenceVersion(
        evidence_version_id=version_id,
        concept_id=concept_id,
        recipe=recipe,
        scientific_status=ModelScientificStatus(recipe.anchor.scientific_status.value),
        lineage=lineage,
        content_hash="0" * 64,
    )
    return provisional.model_copy(update={"content_hash": component_content_hash(provisional)})


def _legacy_resource_bytes(recipe_id: str) -> tuple[str, bytes]:
    catalog = load_packaged_starter_catalog()
    try:
        source = catalog.source_for(recipe_id)
    except RecipeCatalogLookupError as error:
        raise EvidenceMigrationError(f"legacy recipe {recipe_id!r} is not packaged") from error
    if source is None:
        raise EvidenceMigrationError(f"legacy recipe {recipe_id!r} has no resource lineage")
    path = _safe_json_resource(source.recipe_resource)
    resource = files("pilot_assessment.evidence.profile_data").joinpath(*path.parts)
    try:
        return source.recipe_resource, resource.read_bytes()
    except FileNotFoundError as error:
        raise EvidenceMigrationError(
            f"legacy recipe resource {source.recipe_resource!r} is missing"
        ) from error


def _parallel_recipe(resource_name: str) -> EvidenceRecipe:
    path = _safe_json_resource(resource_name)
    resource = files("pilot_assessment.model_library").joinpath(
        "profile_data",
        "hover",
        *path.parts,
    )
    try:
        value = json.loads(resource.read_text(encoding="utf-8"))
        return EvidenceRecipe.model_validate(value)
    except (FileNotFoundError, json.JSONDecodeError, ValidationError, ValueError) as error:
        raise EvidenceMigrationError(
            f"parallel recipe resource {resource_name!r} is invalid"
        ) from error


def load_hover_evidence_inventory() -> EvidenceMigrationInventory:
    """Prepare compatible M4R versions plus D-040 parallel versions without mutation."""

    manifest = _resource_mapping("migration-manifest.json")
    if manifest.get("contract_id") != "m4r-evidence-migration-manifest":
        raise EvidenceMigrationError("migration manifest has an invalid contract_id")
    if manifest.get("contract_version") != "0.1.0":
        raise EvidenceMigrationError("migration manifest has an unsupported version")
    created_at = _parse_timestamp(_string(manifest, "created_at"))
    created_by = _string(manifest, "created_by")
    entries = _parse_entries(manifest)
    parallel_entries = _parse_parallel_entries(manifest)
    concepts = _load_concepts()
    concept_by_id = {concept.concept_id: concept for concept in concepts}
    catalog = load_packaged_starter_catalog()
    source_catalog = load_hover_source_catalog()
    catalog_recipe_ids = {recipe.recipe_id for recipe in catalog}
    entry_recipe_ids = {entry.source_recipe_id for entry in entries}
    if catalog_recipe_ids != entry_recipe_ids:
        raise EvidenceMigrationError(
            "migration manifest must cover the exact packaged M4R recipe inventory"
        )

    imported: list[EvidenceVersion] = []
    legacy: list[LegacyRecipeArtifact] = []
    reports: list[RecipeMigrationCompatibilityReport] = []
    for entry in entries:
        if entry.concept_id not in concept_by_id:
            raise EvidenceMigrationError(f"migration concept {entry.concept_id!r} is not declared")
        try:
            recipe = catalog.get(entry.source_recipe_id)
        except RecipeCatalogLookupError as error:
            raise EvidenceMigrationError(
                f"migration recipe {entry.source_recipe_id!r} is not packaged"
            ) from error
        report = preflight_recipe_migration(recipe, source_catalog)
        reports.append(report)
        note = (
            f"Imported from M4R recipe {recipe.recipe_id}@{recipe.recipe_version}; "
            f"content_hash={report.lineage.source_content_hash}; "
            f"applied_revision={entry.source_applied_revision_id}."
        )
        if report.compatible:
            if entry.evidence_version_id is None or entry.legacy_raw_sha256 is not None:
                raise EvidenceMigrationError(
                    f"compatible recipe {recipe.recipe_id!r} needs an active version ID only"
                )
            imported.append(
                _evidence_version(
                    version_id=entry.evidence_version_id,
                    concept_id=entry.concept_id,
                    recipe=recipe,
                    lineage=_version_lineage(
                        source_version_ids=(entry.source_applied_revision_id,),
                        created_at=created_at,
                        created_by=created_by,
                        note=note,
                    ),
                )
            )
            continue
        if entry.evidence_version_id is not None or entry.legacy_raw_sha256 is None:
            raise EvidenceMigrationError(
                f"incompatible recipe {recipe.recipe_id!r} must be legacy-only"
            )
        resource_path, raw_bytes = _legacy_resource_bytes(recipe.recipe_id)
        raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        if raw_sha256 != entry.legacy_raw_sha256:
            raise EvidenceMigrationError(
                f"legacy recipe {recipe.recipe_id!r} raw bytes no longer match the manifest"
            )
        legacy.append(
            LegacyRecipeArtifact(
                concept_id=entry.concept_id,
                source_applied_revision_id=entry.source_applied_revision_id,
                resource_path=resource_path,
                raw_sha256=raw_sha256,
                typed_content_hash=report.lineage.source_content_hash,
                recipe=recipe,
                compatibility=report,
            )
        )

    parallel: list[EvidenceVersion] = []
    active_ids = {version.evidence_version_id for version in imported}
    for entry in parallel_entries:
        if entry.concept_id not in concept_by_id:
            raise EvidenceMigrationError(f"parallel concept {entry.concept_id!r} is not declared")
        if entry.evidence_version_id in active_ids:
            raise EvidenceMigrationError(
                f"duplicate active Evidence version ID {entry.evidence_version_id!r}"
            )
        recipe = _parallel_recipe(entry.recipe_resource)
        report = preflight_recipe_migration(recipe, source_catalog)
        if not report.compatible:
            raise EvidenceMigrationError(
                f"parallel recipe {recipe.recipe_id!r} is not provenance-compatible"
            )
        version = _evidence_version(
            version_id=entry.evidence_version_id,
            concept_id=entry.concept_id,
            recipe=recipe,
            lineage=_version_lineage(
                source_version_ids=entry.source_version_ids,
                created_at=created_at,
                created_by=created_by,
                note=(
                    f"Created as D-040-compliant parallel recipe {recipe.recipe_id}@"
                    f"{recipe.recipe_version}; content_hash={report.lineage.source_content_hash}."
                ),
            ),
        )
        active_ids.add(version.evidence_version_id)
        parallel.append(version)

    concept_ids_with_active_versions = {version.concept_id for version in (*imported, *parallel)}
    if concept_ids_with_active_versions != set(concept_by_id):
        raise EvidenceMigrationError("every declared Evidence concept needs an active version")
    return EvidenceMigrationInventory(
        concepts=concepts,
        imported_versions=tuple(imported),
        parallel_versions=tuple(parallel),
        legacy_artifacts=tuple(legacy),
        compatibility_reports=tuple(reports),
    )


__all__ = [
    "EvidenceMigrationError",
    "EvidenceMigrationInventory",
    "LegacyRecipeArtifact",
    "MigrationCompatibilityDiagnostic",
    "MigrationDiagnosticCode",
    "MigrationLineageMetadata",
    "RecipeMigrationCompatibilityReport",
    "load_hover_evidence_inventory",
    "preflight_recipe_catalog",
    "preflight_recipe_migration",
]
