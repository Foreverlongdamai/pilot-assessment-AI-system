"""One-way migration from bilingual M7 current content to D-055 content."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypeAlias, cast

from pydantic import JsonValue, ValidationError

from pilot_assessment.contracts.model_workspace import (
    ModelNode,
    ModelObjectKind,
    TaskScheme,
)
from pilot_assessment.contracts.model_workspace_legacy import (
    LegacyModelNodeV010,
    LegacyTaskSchemeV010,
)
from pilot_assessment.model_workspace.hashing import rehash_model_node, rehash_task_scheme
from pilot_assessment.persistence.database import (
    ProjectDatabase,
    decode_canonical_json,
    encode_canonical_json,
)

CurrentModelObject: TypeAlias = ModelNode | TaskScheme
LegacyModelObject: TypeAlias = LegacyModelNodeV010 | LegacyTaskSchemeV010
AnyModelObject: TypeAlias = CurrentModelObject | LegacyModelObject

ENGLISH_FALLBACK_DIAGNOSTIC = "MODEL_CONTENT_ENGLISH_FALLBACK_PRESERVED"


class CurrentModelContentMigrationError(RuntimeError):
    """Raised when current content cannot be migrated without guessing."""


@dataclass(frozen=True, slots=True)
class ModelContentMigrationDiagnostic:
    code: str
    fields: tuple[str, ...]

    def as_json(self) -> dict[str, JsonValue]:
        return {"code": self.code, "fields": list(self.fields)}


@dataclass(frozen=True, slots=True)
class NormalisedModelContent:
    item: CurrentModelObject
    legacy_item: LegacyModelObject
    diagnostics: tuple[ModelContentMigrationDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class NormalisedStoredModelRow:
    """One validated table row represented by the current content contract."""

    values: dict[str, object]
    before_item: AnyModelObject
    item: CurrentModelObject
    diagnostics: tuple[ModelContentMigrationDiagnostic, ...]
    migrated: bool


@dataclass(frozen=True, slots=True)
class ModelContentMigrationResult:
    migrated_node_count: int
    migrated_scheme_count: int
    before_fingerprint: str
    after_fingerprint: str
    before_state_hash: str
    after_state_hash: str
    compatible_predecessor_fingerprints: tuple[str, ...]

    @property
    def migrated_object_count(self) -> int:
        return self.migrated_node_count + self.migrated_scheme_count


@dataclass(frozen=True, slots=True)
class _RowSpec:
    object_kind: ModelObjectKind
    table: str
    id_column: str


@dataclass(frozen=True, slots=True)
class _Replacement:
    spec: _RowSpec
    object_id: str
    legacy_payload: bytes
    legacy_item: LegacyModelObject
    item: CurrentModelObject
    diagnostics: tuple[ModelContentMigrationDiagnostic, ...]


_ROW_SPECS = (
    _RowSpec(ModelObjectKind.NODE, "model_nodes", "node_id"),
    _RowSpec(ModelObjectKind.SCHEME, "task_schemes", "scheme_id"),
)


def _spec_for_kind(object_kind: ModelObjectKind) -> _RowSpec:
    return _ROW_SPECS[0] if object_kind is ModelObjectKind.NODE else _ROW_SPECS[1]


def _select_canonical_text(
    payload: Mapping[str, JsonValue],
    *,
    english_key: str,
    alternate_key: str,
) -> tuple[str, bool]:
    english = payload.get(english_key)
    if isinstance(english, str) and english.strip():
        return english.strip(), False
    alternate = payload.get(alternate_key)
    if isinstance(alternate, str) and alternate.strip():
        return alternate.strip(), True
    raise CurrentModelContentMigrationError(
        f"legacy payload has no nonblank {english_key!r} or {alternate_key!r}"
    )


def _fallback_diagnostic(fields: list[str]) -> tuple[ModelContentMigrationDiagnostic, ...]:
    if not fields:
        return ()
    return (
        ModelContentMigrationDiagnostic(
            code=ENGLISH_FALLBACK_DIAGNOSTIC,
            fields=tuple(sorted(fields)),
        ),
    )


def normalise_legacy_model_node(payload: Mapping[str, JsonValue]) -> NormalisedModelContent:
    """Prefer legacy English content and preserve the alternate when English is absent."""

    try:
        legacy = LegacyModelNodeV010.model_validate(payload)
    except ValidationError as error:
        raise CurrentModelContentMigrationError("legacy model-node payload is invalid") from error
    converted = cast(dict[str, JsonValue], legacy.model_dump(mode="json"))
    fallback_fields: list[str] = []
    for target, english, alternate in (
        ("name", "name_en", "name_zh"),
        ("short_name", "short_name_en", "short_name_zh"),
        ("description", "description_en", "description_zh"),
    ):
        value, used_fallback = _select_canonical_text(
            converted,
            english_key=english,
            alternate_key=alternate,
        )
        converted[target] = value
        converted.pop(english, None)
        converted.pop(alternate, None)
        if used_fallback:
            fallback_fields.append(target)

    raw_definition = converted.get("definition")
    if not isinstance(raw_definition, dict):
        raise CurrentModelContentMigrationError("legacy model-node definition is not an object")
    definition = cast(dict[str, JsonValue], raw_definition)
    help_text, used_fallback = _select_canonical_text(
        definition,
        english_key="help_text_en",
        alternate_key="help_text_zh",
    )
    definition["help_text"] = help_text
    definition.pop("help_text_en", None)
    definition.pop("help_text_zh", None)
    if used_fallback:
        fallback_fields.append("definition.help_text")
    converted["contract_version"] = "0.2.0"

    try:
        current = rehash_model_node(ModelNode.model_validate(converted))
    except ValidationError as error:
        raise CurrentModelContentMigrationError(
            "normalised model-node payload is invalid"
        ) from error
    return NormalisedModelContent(
        item=current,
        legacy_item=legacy,
        diagnostics=_fallback_diagnostic(fallback_fields),
    )


def normalise_legacy_task_scheme(payload: Mapping[str, JsonValue]) -> NormalisedModelContent:
    """Convert one legacy bilingual task scheme to the single-content contract."""

    try:
        legacy = LegacyTaskSchemeV010.model_validate(payload)
    except ValidationError as error:
        raise CurrentModelContentMigrationError("legacy task-scheme payload is invalid") from error
    converted = cast(dict[str, JsonValue], legacy.model_dump(mode="json"))
    fallback_fields: list[str] = []
    for target, english, alternate in (
        ("name", "name_en", "name_zh"),
        ("description", "description_en", "description_zh"),
    ):
        value, used_fallback = _select_canonical_text(
            converted,
            english_key=english,
            alternate_key=alternate,
        )
        converted[target] = value
        converted.pop(english, None)
        converted.pop(alternate, None)
        if used_fallback:
            fallback_fields.append(target)
    converted["contract_version"] = "0.2.0"

    try:
        current = rehash_task_scheme(TaskScheme.model_validate(converted))
    except ValidationError as error:
        raise CurrentModelContentMigrationError(
            "normalised task-scheme payload is invalid"
        ) from error
    return NormalisedModelContent(
        item=current,
        legacy_item=legacy,
        diagnostics=_fallback_diagnostic(fallback_fields),
    )


def _mapping(payload: bytes | Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
    decoded: JsonValue | Mapping[str, JsonValue]
    decoded = decode_canonical_json(payload) if isinstance(payload, bytes) else payload
    if not isinstance(decoded, dict):
        raise CurrentModelContentMigrationError("current-model payload must be a JSON object")
    return cast(Mapping[str, JsonValue], decoded)


def decode_current_model_object(
    payload: bytes | Mapping[str, JsonValue],
    *,
    object_kind: ModelObjectKind,
) -> CurrentModelObject:
    """Read current v0.2 content or adapt frozen v0.1 content without rewriting bytes."""

    decoded = _mapping(payload)
    version = decoded.get("contract_version")
    try:
        if version == "0.2.0":
            if object_kind is ModelObjectKind.NODE:
                return ModelNode.model_validate(decoded)
            return TaskScheme.model_validate(decoded)
        if version == "0.1.0":
            if object_kind is ModelObjectKind.NODE:
                return normalise_legacy_model_node(decoded).item
            return normalise_legacy_task_scheme(decoded).item
    except ValidationError as error:
        raise CurrentModelContentMigrationError("current-model payload is invalid") from error
    raise CurrentModelContentMigrationError(
        f"unsupported {object_kind.value} contract_version {version!r}"
    )


def _object_id(item: AnyModelObject) -> str:
    return item.node_id if isinstance(item, (ModelNode, LegacyModelNodeV010)) else item.scheme_id


def _object_state(item: AnyModelObject, *, include_revisions: bool) -> dict[str, JsonValue]:
    excluded = {"created_at", "updated_at"}
    if not include_revisions:
        excluded.update({"semantic_revision", "layout_revision"})
    return cast(dict[str, JsonValue], item.model_dump(mode="json", exclude=excluded))


def model_content_fingerprint(
    nodes: tuple[ModelNode | LegacyModelNodeV010, ...],
    schemes: tuple[TaskScheme | LegacyTaskSchemeV010, ...],
    *,
    include_revisions: bool,
) -> str:
    payload = {
        "nodes": [
            _object_state(item, include_revisions=include_revisions)
            for item in sorted(nodes, key=lambda value: value.node_id)
        ],
        "schemes": [
            _object_state(item, include_revisions=include_revisions)
            for item in sorted(schemes, key=lambda value: value.scheme_id)
        ],
    }
    return hashlib.sha256(encode_canonical_json(payload)).hexdigest()


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CurrentModelContentMigrationError("migration timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _validate_indexed_row(
    row: Mapping[str, object] | sqlite3.Row,
    item: AnyModelObject,
    spec: _RowSpec,
) -> None:
    expected_id = _object_id(item)
    matches = (
        row[spec.id_column] == expected_id
        and row["lifecycle"] == item.lifecycle.value
        and row["semantic_revision"] == item.semantic_revision
        and row["layout_revision"] == item.layout_revision
        and row["content_hash"] == item.content_hash
        and row["layout_hash"] == item.layout_hash
        and row["technical_status"] == item.technical_status.value
        and row["created_at"] == _utc_text(item.created_at)
        and row["updated_at"] == _utc_text(item.updated_at)
    )
    if not matches:
        raise CurrentModelContentMigrationError(
            f"stored {spec.object_kind.value} indexed columns do not match canonical JSON"
        )


def _normalise_row(
    row: Mapping[str, object] | sqlite3.Row,
    spec: _RowSpec,
) -> tuple[AnyModelObject, CurrentModelObject, _Replacement | None]:
    payload = row["canonical_json"]
    if not isinstance(payload, bytes):
        raise CurrentModelContentMigrationError("stored canonical_json must be bytes")
    decoded = _mapping(payload)
    version = decoded.get("contract_version")
    if version == "0.2.0":
        item = decode_current_model_object(decoded, object_kind=spec.object_kind)
        _validate_indexed_row(row, item, spec)
        expected = (
            rehash_model_node(item) if isinstance(item, ModelNode) else rehash_task_scheme(item)
        )
        if item.content_hash != expected.content_hash or item.layout_hash != expected.layout_hash:
            raise CurrentModelContentMigrationError(
                f"stored current {spec.object_kind.value} hash claim does not match"
            )
        return item, item, None
    if version != "0.1.0":
        raise CurrentModelContentMigrationError(
            f"unsupported stored {spec.object_kind.value} contract_version {version!r}"
        )
    normalised = (
        normalise_legacy_model_node(decoded)
        if spec.object_kind is ModelObjectKind.NODE
        else normalise_legacy_task_scheme(decoded)
    )
    _validate_indexed_row(row, normalised.legacy_item, spec)
    replacement = _Replacement(
        spec=spec,
        object_id=_object_id(normalised.item),
        legacy_payload=payload,
        legacy_item=normalised.legacy_item,
        item=normalised.item,
        diagnostics=normalised.diagnostics,
    )
    return normalised.legacy_item, normalised.item, replacement


def normalise_current_model_row(
    row: Mapping[str, object],
    *,
    object_kind: ModelObjectKind,
) -> NormalisedStoredModelRow:
    """Validate a stored row and return its current-contract representation.

    This pure helper also migrates rows embedded in edit-session snapshots. It
    leaves every non-content column unchanged and performs no database write.
    """

    spec = _spec_for_kind(object_kind)
    before, item, replacement = _normalise_row(row, spec)
    values = dict(row)
    diagnostics: tuple[ModelContentMigrationDiagnostic, ...] = ()
    if replacement is not None:
        values["canonical_json"] = encode_canonical_json(item.model_dump(mode="json"))
        values["content_hash"] = item.content_hash
        values["layout_hash"] = item.layout_hash
        diagnostics = replacement.diagnostics
    return NormalisedStoredModelRow(
        values=values,
        before_item=before,
        item=item,
        diagnostics=diagnostics,
        migrated=replacement is not None,
    )


def _event_id(replacement: _Replacement) -> str:
    identity = {
        "object_kind": replacement.spec.object_kind.value,
        "object_id": replacement.object_id,
        "from_contract_version": replacement.legacy_item.contract_version,
        "to_contract_version": replacement.item.contract_version,
        "old_content_hash": replacement.legacy_item.content_hash,
        "new_content_hash": replacement.item.content_hash,
        "old_layout_hash": replacement.legacy_item.layout_hash,
        "new_layout_hash": replacement.item.layout_hash,
    }
    return f"model-content-migration.{hashlib.sha256(encode_canonical_json(identity)).hexdigest()}"


def migrate_current_model_content(
    database: ProjectDatabase,
    *,
    migrated_at: datetime,
) -> ModelContentMigrationResult:
    """Atomically migrate all mutable current rows and record append-only lineage."""

    before_nodes: list[ModelNode | LegacyModelNodeV010] = []
    before_schemes: list[TaskScheme | LegacyTaskSchemeV010] = []
    after_nodes: list[ModelNode] = []
    after_schemes: list[TaskScheme] = []
    replacements: list[_Replacement] = []

    for spec in _ROW_SPECS:
        rows = database.fetchall(
            f"SELECT * FROM {spec.table} ORDER BY {spec.id_column}"  # noqa: S608
        )
        for row in rows:
            before, after, replacement = _normalise_row(row, spec)
            if spec.object_kind is ModelObjectKind.NODE:
                before_nodes.append(cast(ModelNode | LegacyModelNodeV010, before))
                after_nodes.append(cast(ModelNode, after))
            else:
                before_schemes.append(cast(TaskScheme | LegacyTaskSchemeV010, before))
                after_schemes.append(cast(TaskScheme, after))
            if replacement is not None:
                replacements.append(replacement)

    before_fingerprint = model_content_fingerprint(
        tuple(before_nodes), tuple(before_schemes), include_revisions=True
    )
    after_fingerprint = model_content_fingerprint(
        tuple(after_nodes), tuple(after_schemes), include_revisions=True
    )
    predecessor_rows = database.fetchall(
        """
        SELECT DISTINCT before_workspace_fingerprint
        FROM model_content_migration_events
        WHERE after_workspace_fingerprint = ?
        ORDER BY before_workspace_fingerprint
        """,
        (after_fingerprint,),
    )
    compatible_predecessors = {row["before_workspace_fingerprint"] for row in predecessor_rows}
    if replacements and before_fingerprint != after_fingerprint:
        compatible_predecessors.add(before_fingerprint)

    result = ModelContentMigrationResult(
        migrated_node_count=sum(
            item.spec.object_kind is ModelObjectKind.NODE for item in replacements
        ),
        migrated_scheme_count=sum(
            item.spec.object_kind is ModelObjectKind.SCHEME for item in replacements
        ),
        before_fingerprint=before_fingerprint,
        after_fingerprint=after_fingerprint,
        before_state_hash=model_content_fingerprint(
            tuple(before_nodes), tuple(before_schemes), include_revisions=False
        ),
        after_state_hash=model_content_fingerprint(
            tuple(after_nodes), tuple(after_schemes), include_revisions=False
        ),
        compatible_predecessor_fingerprints=tuple(sorted(compatible_predecessors)),
    )
    if not replacements:
        return result

    timestamp = _utc_text(migrated_at)
    with database.transaction() as connection:
        for replacement in replacements:
            item = replacement.item
            cursor = connection.execute(
                f"""
                UPDATE {replacement.spec.table}
                SET canonical_json = ?, content_hash = ?, layout_hash = ?
                WHERE {replacement.spec.id_column} = ? AND canonical_json = ?
                """,  # noqa: S608
                (
                    encode_canonical_json(item.model_dump(mode="json")),
                    item.content_hash,
                    item.layout_hash,
                    replacement.object_id,
                    replacement.legacy_payload,
                ),
            )
            if cursor.rowcount != 1:
                raise CurrentModelContentMigrationError(
                    f"stored {replacement.spec.object_kind.value} changed during migration"
                )
            connection.execute(
                """
                INSERT INTO model_content_migration_events(
                    migration_event_id, object_kind, object_id,
                    from_contract_version, to_contract_version,
                    old_content_hash, new_content_hash, old_layout_hash, new_layout_hash,
                    before_workspace_fingerprint, after_workspace_fingerprint,
                    legacy_payload, diagnostics_json, migrated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _event_id(replacement),
                    replacement.spec.object_kind.value,
                    replacement.object_id,
                    replacement.legacy_item.contract_version,
                    item.contract_version,
                    replacement.legacy_item.content_hash,
                    item.content_hash,
                    replacement.legacy_item.layout_hash,
                    item.layout_hash,
                    result.before_fingerprint,
                    result.after_fingerprint,
                    replacement.legacy_payload,
                    encode_canonical_json(
                        [diagnostic.as_json() for diagnostic in replacement.diagnostics]
                    ),
                    timestamp,
                ),
            )
    return result


__all__ = [
    "CurrentModelContentMigrationError",
    "ENGLISH_FALLBACK_DIAGNOSTIC",
    "ModelContentMigrationDiagnostic",
    "ModelContentMigrationResult",
    "NormalisedModelContent",
    "NormalisedStoredModelRow",
    "decode_current_model_object",
    "migrate_current_model_content",
    "model_content_fingerprint",
    "normalise_current_model_row",
    "normalise_legacy_model_node",
    "normalise_legacy_task_scheme",
]
