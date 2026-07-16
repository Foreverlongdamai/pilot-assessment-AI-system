"""Generic checksum-bound loader for packaged model-profile resources."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import TypeAlias, cast

from pydantic import ValidationError

from pilot_assessment.contracts.assessment_scheme import (
    AssessmentSchemeVersion,
    CoverageReportingPolicyVersion,
    LayoutVersion,
    TaskProfileVersion,
)
from pilot_assessment.contracts.model_components import (
    BnNodeConcept,
    BnNodeVersion,
    ComponentKind,
    CptVersion,
    EvidenceBindingVersion,
    EvidenceConcept,
    PinnedComponentRef,
    SourceDescriptor,
)
from pilot_assessment.model_library.identity import typed_content_sha256
from pilot_assessment.model_library.migration import load_hover_evidence_inventory
from pilot_assessment.model_library.repository import (
    InMemoryComponentLibraryRepository,
    LibraryItem,
    VersionLibraryItem,
    component_content_hash,
    component_kind,
    component_record_id,
)
from pilot_assessment.model_library.sources import SourceCatalog

_RecordKey: TypeAlias = tuple[ComponentKind, str]
_Parser: TypeAlias = Callable[[Mapping[str, object]], tuple[LibraryItem, ...]]


class ProfilePackageError(ValueError):
    """Raised when a profile manifest, resource, or exact dependency is invalid."""


@dataclass(frozen=True, slots=True)
class _ResourceEntry:
    path: str
    type_id: str
    schema_id: str
    sha256: str
    record_refs: tuple[_RecordKey, ...]
    dependency_refs: tuple[_RecordKey, ...]


@dataclass(frozen=True, slots=True)
class LoadedModelProfile:
    profile_id: str
    manifest_hash: str
    library_items: tuple[LibraryItem, ...]
    scheme: AssessmentSchemeVersion
    source_catalog: SourceCatalog

    def to_repository(
        self,
        *,
        recorded_at: datetime,
    ) -> InMemoryComponentLibraryRepository:
        repository = InMemoryComponentLibraryRepository()
        for item in self.library_items:
            repository.add(item, recorded_at=recorded_at)
        return repository


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProfilePackageError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _json_object(payload: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(payload, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProfilePackageError(f"{label} must be strict UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ProfilePackageError(f"{label} must contain one JSON object")
    return cast(dict[str, object], value)


def _string(mapping: Mapping[str, object], field: str, label: str) -> str:
    value = mapping.get(field)
    if type(value) is not str or not value:
        raise ProfilePackageError(f"{label}.{field} must be a non-empty string")
    return value


def _array(mapping: Mapping[str, object], field: str, label: str) -> list[object]:
    value = mapping.get(field)
    if not isinstance(value, list):
        raise ProfilePackageError(f"{label}.{field} must be an array")
    return cast(list[object], value)


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ProfilePackageError(f"{label} must be an object")
    return cast(dict[str, object], value)


def _safe_resource_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or len(path.parts) != 1
        or path.name in {".", "..", "manifest.json"}
        or path.suffix != ".json"
    ):
        raise ProfilePackageError(f"unsafe profile resource path {value!r}")
    return path.name


def _record_ref(value: object, label: str) -> _RecordKey:
    mapping = _mapping(value, label)
    try:
        kind = ComponentKind(_string(mapping, "kind", label))
    except ValueError as error:
        raise ProfilePackageError(f"{label}.kind is unknown") from error
    return (kind, _string(mapping, "record_id", label))


def _record_refs(mapping: Mapping[str, object], field: str, label: str) -> tuple[_RecordKey, ...]:
    refs = tuple(
        _record_ref(item, f"{label}.{field}[{index}]")
        for index, item in enumerate(_array(mapping, field, label))
    )
    if len(refs) != len(set(refs)):
        raise ProfilePackageError(f"{label}.{field} contains duplicate record refs")
    return refs


def _parse_entries(manifest: Mapping[str, object]) -> tuple[_ResourceEntry, ...]:
    entries: list[_ResourceEntry] = []
    for index, value in enumerate(_array(manifest, "resources", "manifest")):
        label = f"manifest.resources[{index}]"
        mapping = _mapping(value, label)
        sha256 = _string(mapping, "sha256", label).lower()
        if len(sha256) != 64 or any(character not in "0123456789abcdef" for character in sha256):
            raise ProfilePackageError(f"{label}.sha256 must be a SHA-256 digest")
        entries.append(
            _ResourceEntry(
                path=_safe_resource_path(_string(mapping, "path", label)),
                type_id=_string(mapping, "type_id", label),
                schema_id=_string(mapping, "schema_id", label),
                sha256=sha256,
                record_refs=_record_refs(mapping, "record_refs", label),
                dependency_refs=_record_refs(mapping, "dependency_refs", label),
            )
        )
    paths = tuple(entry.path for entry in entries)
    if len(paths) != len(set(paths)):
        raise ProfilePackageError("manifest contains duplicate resource paths")
    return tuple(entries)


def _validate_catalog_header(
    value: Mapping[str, object],
    *,
    contract_id: str,
) -> None:
    if value.get("contract_id") != contract_id or value.get("contract_version") != "0.1.0":
        raise ProfilePackageError(f"resource does not match {contract_id} v0.1.0")


def _model_catalog_parser(
    model_type: type[LibraryItem],
    *,
    contract_id: str,
    field: str,
) -> _Parser:
    def parse(value: Mapping[str, object]) -> tuple[LibraryItem, ...]:
        _validate_catalog_header(value, contract_id=contract_id)
        try:
            return tuple(
                model_type.model_validate(item) for item in _array(value, field, contract_id)
            )
        except (TypeError, ValidationError, ValueError) as error:
            raise ProfilePackageError(f"invalid {contract_id} member") from error

    return parse


def _single_parser(model_type: type[LibraryItem]) -> _Parser:
    def parse(value: Mapping[str, object]) -> tuple[LibraryItem, ...]:
        try:
            return (model_type.model_validate(value),)
        except (ValidationError, ValueError) as error:
            raise ProfilePackageError(f"invalid {model_type.__name__} resource") from error

    return parse


def _support_parser(_value: Mapping[str, object]) -> tuple[LibraryItem, ...]:
    return ()


_PARSERS: dict[str, tuple[str, _Parser]] = {
    "source-descriptor-catalog-v0.1": (
        "source_descriptor_catalog",
        _model_catalog_parser(
            SourceDescriptor,
            contract_id="source-descriptor-catalog",
            field="descriptors",
        ),
    ),
    "evidence-concept-catalog-v0.1": (
        "evidence_concept_catalog",
        _model_catalog_parser(
            EvidenceConcept,
            contract_id="evidence-concept-catalog",
            field="concepts",
        ),
    ),
    "bn-node-concept-catalog-v0.1": (
        "bn_node_concept_catalog",
        _model_catalog_parser(
            BnNodeConcept,
            contract_id="bn-node-concept-catalog",
            field="concepts",
        ),
    ),
    "bn-node-version-catalog-v0.1": (
        "bn_node_version_catalog",
        _model_catalog_parser(
            BnNodeVersion,
            contract_id="bn-node-version-catalog",
            field="versions",
        ),
    ),
    "evidence-binding-version-catalog-v0.1": (
        "evidence_binding_version_catalog",
        _model_catalog_parser(
            EvidenceBindingVersion,
            contract_id="evidence-binding-version-catalog",
            field="bindings",
        ),
    ),
    "cpt-version-catalog-v0.1": (
        "cpt_version_catalog",
        _model_catalog_parser(
            CptVersion,
            contract_id="cpt-version-catalog",
            field="cpts",
        ),
    ),
    "task-profile-version-v0.1": (
        "task_profile_version",
        _single_parser(TaskProfileVersion),
    ),
    "coverage-reporting-policy-version-v0.1": (
        "coverage_reporting_policy_version",
        _single_parser(CoverageReportingPolicyVersion),
    ),
    "layout-version-v0.1": ("layout_version", _single_parser(LayoutVersion)),
    "assessment-scheme-version-v0.1": (
        "assessment_scheme_version",
        _single_parser(AssessmentSchemeVersion),
    ),
    "m4r-evidence-migration-manifest-v0.1": (
        "migration_support",
        _support_parser,
    ),
    "evidence-recipe-support-v0.1": (
        "evidence_recipe_support",
        _support_parser,
    ),
}


def _key(item: LibraryItem) -> _RecordKey:
    return (component_kind(item), component_record_id(item))


def _pin_key(reference: PinnedComponentRef) -> _RecordKey:
    return (reference.kind, reference.version_id)


def _external_index(items: Iterable[LibraryItem]) -> dict[_RecordKey, LibraryItem]:
    result: dict[_RecordKey, LibraryItem] = {}
    for item in items:
        key = _key(item)
        if key in result:
            raise ProfilePackageError(f"duplicate external component {key[0].value}:{key[1]}")
        result[key] = item
    return result


def _manifest_hash(manifest: Mapping[str, object]) -> str:
    payload = dict(manifest)
    claimed = payload.pop("manifest_hash", None)
    if type(claimed) is not str:
        raise ProfilePackageError("manifest.manifest_hash must be a string")
    actual = typed_content_sha256("model-profile-manifest", "0.1.0", payload)
    if claimed != actual:
        raise ProfilePackageError("manifest content hash does not match")
    return claimed


def _read_directory_resource(root: Path, name: str) -> bytes:
    try:
        return (root / name).read_bytes()
    except FileNotFoundError as error:
        raise ProfilePackageError(f"profile resource {name!r} is missing") from error


def load_model_profile_directory(
    root: Path,
    *,
    external_items: Iterable[LibraryItem] = (),
) -> LoadedModelProfile:
    """Load one directory only through its checksummed manifest and schema dispatch."""

    root = root.resolve()
    manifest = _json_object(_read_directory_resource(root, "manifest.json"), "manifest")
    if (
        manifest.get("contract_id") != "model-profile-manifest"
        or manifest.get("contract_version") != "0.1.0"
    ):
        raise ProfilePackageError("manifest contract must be model-profile-manifest v0.1.0")
    profile_id = _string(manifest, "profile_id", "manifest")
    manifest_hash = _manifest_hash(manifest)
    entries = _parse_entries(manifest)
    declared_paths = {entry.path for entry in entries}
    actual_paths = {
        path.name for path in root.iterdir() if path.is_file() and path.suffix == ".json"
    }
    if actual_paths != declared_paths | {"manifest.json"}:
        raise ProfilePackageError("manifest must enumerate the exact profile JSON resources")

    local_items: list[LibraryItem] = []
    for entry in entries:
        payload = _read_directory_resource(root, entry.path)
        if hashlib.sha256(payload).hexdigest() != entry.sha256:
            raise ProfilePackageError(f"resource checksum mismatch for {entry.path!r}")
        dispatch = _PARSERS.get(entry.schema_id)
        if dispatch is None:
            raise ProfilePackageError(f"unsupported profile schema_id {entry.schema_id!r}")
        expected_type_id, parser = dispatch
        if entry.type_id != expected_type_id:
            raise ProfilePackageError(
                f"resource {entry.path!r} type_id does not match its schema dispatch"
            )
        parsed = parser(_json_object(payload, entry.path))
        actual_refs = tuple(_key(item) for item in parsed)
        if len(actual_refs) != len(set(actual_refs)) or set(actual_refs) != set(entry.record_refs):
            raise ProfilePackageError(
                f"manifest record refs do not match parsed resource {entry.path!r}"
            )
        local_items.extend(parsed)

    local_by_key: dict[_RecordKey, LibraryItem] = {}
    for item in local_items:
        key = _key(item)
        if key in local_by_key:
            raise ProfilePackageError(f"duplicate local component {key[0].value}:{key[1]}")
        local_by_key[key] = item
    external_by_key = _external_index(external_items)
    try:
        external_refs = tuple(
            PinnedComponentRef.model_validate(value)
            for value in _array(manifest, "external_component_refs", "manifest")
        )
        entry_scheme_ref = PinnedComponentRef.model_validate(manifest.get("entry_scheme_ref"))
    except (ValidationError, ValueError) as error:
        raise ProfilePackageError("manifest contains an invalid exact component ref") from error
    selected_external: list[LibraryItem] = []
    for reference in external_refs:
        key = _pin_key(reference)
        item = external_by_key.get(key)
        if item is None:
            raise ProfilePackageError(
                f"external exact component {reference.kind.value}:{reference.version_id} is missing"
            )
        if (
            not hasattr(item, "content_hash")
            or component_content_hash(cast(VersionLibraryItem, item)) != reference.content_hash
        ):
            raise ProfilePackageError(
                f"external exact component {reference.kind.value}:{reference.version_id} "
                "does not match its pinned hash"
            )
        selected_external.append(item)

    closure_keys = set(local_by_key) | {_key(item) for item in selected_external}
    for entry in entries:
        for dependency in entry.dependency_refs:
            if dependency not in closure_keys:
                raise ProfilePackageError(
                    f"resource {entry.path!r} has an unresolved component dependency "
                    f"{dependency[0].value}:{dependency[1]}"
                )
    scheme_item = local_by_key.get(_pin_key(entry_scheme_ref))
    if not isinstance(scheme_item, AssessmentSchemeVersion):
        raise ProfilePackageError("entry scheme ref does not identify a local scheme")
    if scheme_item.content_hash != entry_scheme_ref.content_hash:
        raise ProfilePackageError("entry scheme ref hash does not match the local scheme")

    library_items = (*local_items, *selected_external)
    source_catalog = SourceCatalog(
        item for item in library_items if isinstance(item, SourceDescriptor)
    )
    return LoadedModelProfile(
        profile_id=profile_id,
        manifest_hash=manifest_hash,
        library_items=library_items,
        scheme=scheme_item,
        source_catalog=source_catalog,
    )


def load_model_profile(
    package_name: str,
    *,
    external_items: Iterable[LibraryItem] = (),
) -> LoadedModelProfile:
    """Load a named packaged profile without branching on model IDs or node IDs."""

    path = PurePosixPath(package_name)
    if path.is_absolute() or len(path.parts) != 1 or path.name in {".", ".."}:
        raise ProfilePackageError("package_name must be one safe resource-directory name")
    root = files("pilot_assessment.model_library.profile_data").joinpath(path.name)
    return load_model_profile_directory(Path(str(root)), external_items=external_items)


def load_hover_starter_package() -> LoadedModelProfile:
    """Convenience composition of the generic loader and Task 9 migration inventory."""

    inventory = load_hover_evidence_inventory()
    return load_model_profile("hover", external_items=inventory.active_versions)


__all__ = [
    "LoadedModelProfile",
    "ProfilePackageError",
    "load_hover_starter_package",
    "load_model_profile",
    "load_model_profile_directory",
]
