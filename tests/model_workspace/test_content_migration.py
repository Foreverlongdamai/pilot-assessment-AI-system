from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from pilot_assessment.contracts.evidence_recipe import (
    PortCardinality,
    PortType,
    TemporalSemantics,
)
from pilot_assessment.contracts.model_components import (
    RawModality,
    SourceDescriptor,
    SourceKind,
)
from pilot_assessment.contracts.model_workspace import (
    CanonicalModelDiff,
    ModelNode,
    ModelNodeKind,
    ModelObjectKind,
    ModelObjectLifecycle,
    ModelTechnicalStatus,
    NodeLayout,
    RawInputFamily,
    RawInputNodeDefinition,
    RawResourceRole,
    TaskScheme,
)
from pilot_assessment.model_workspace.content_migration import (
    ENGLISH_FALLBACK_DIAGNOSTIC,
    CurrentModelContentMigrationError,
    decode_current_model_object,
    migrate_current_model_content,
    normalise_legacy_model_node,
    normalise_legacy_task_scheme,
)
from pilot_assessment.model_workspace.hashing import rehash_model_node
from pilot_assessment.persistence.database import (
    ProjectDatabase,
    encode_canonical_json,
)
from pilot_assessment.persistence.model_workspace_repository import (
    SqliteModelWorkspaceRepository,
)

NOW = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
ZERO_HASH = "0" * 64


def _current_raw_node() -> ModelNode:
    descriptor = SourceDescriptor(
        source_id="source.X",
        kind=SourceKind.RAW_STREAM,
        name="Flight state",
        description="Task-neutral flight-state input.",
        declared_type=PortType(
            value_type="number",
            cardinality=PortCardinality.ONE,
            temporal_semantics=TemporalSemantics.SAMPLED,
            unit=None,
        ),
        raw_modality=RawModality.X,
        source_dependencies=(),
        metadata={},
        content_hash="a" * 64,
    )
    return ModelNode(
        node_id="raw.x",
        node_kind=ModelNodeKind.RAW_INPUT,
        name="Flight State",
        short_name="X",
        description="Canonical flight-state input.",
        tags=("fixture",),
        group="fixture",
        lifecycle=ModelObjectLifecycle.ACTIVE,
        copied_from_node_id=None,
        definition=RawInputNodeDefinition(
            family=RawInputFamily.X,
            resource_role=RawResourceRole.STREAM,
            source_descriptor=descriptor,
            metadata={},
            help_text="Provides X(t) to Evidence recipes.",
        ),
        global_layout=NodeLayout(node_id="raw.x", x=10.0, y=20.0),
        semantic_revision=3,
        layout_revision=2,
        technical_status=ModelTechnicalStatus.EXECUTABLE,
        diagnostics=(),
        content_hash=ZERO_HASH,
        layout_hash=ZERO_HASH,
        created_at=NOW,
        updated_at=NOW,
    )


def _current_scheme() -> TaskScheme:
    return TaskScheme(
        scheme_id="scheme.base",
        name="Base Scheme",
        description="Task-neutral starter scheme.",
        tags=("fixture",),
        group="fixture",
        lifecycle=ModelObjectLifecycle.ACTIVE,
        copied_from_scheme_id=None,
        explicit_active_node_ids=("raw.x",),
        computed_active_closure=("raw.x",),
        output_node_ids=("raw.x",),
        task_bindings={},
        layout_overrides=(),
        semantic_revision=1,
        layout_revision=0,
        technical_status=ModelTechnicalStatus.EXECUTABLE,
        diagnostics=(),
        content_hash=ZERO_HASH,
        layout_hash=ZERO_HASH,
        created_at=NOW,
        updated_at=NOW,
    )


def _legacy_node_payload(*, english: bool = True) -> dict[str, object]:
    payload = _current_raw_node().model_dump(mode="json")
    payload["contract_version"] = "0.1.0"
    payload["name_en"] = "  Flight State  " if english else None
    payload["name_zh"] = "Flight State Fallback" if not english else "飞行状态"
    payload["short_name_en"] = " X " if english else None
    payload["short_name_zh"] = "X Fallback" if not english else "状态"
    payload["description_en"] = "  Canonical flight-state input.  " if english else None
    payload["description_zh"] = (
        "Fallback flight-state description." if not english else "飞行状态输入。"
    )
    for key in ("name", "short_name", "description"):
        payload.pop(key)
    definition = payload["definition"]
    assert isinstance(definition, dict)
    definition["help_text_en"] = "  Provides X(t) to Evidence recipes.  " if english else None
    definition["help_text_zh"] = "Fallback raw-input help." if not english else "输入帮助。"
    definition.pop("help_text")
    payload["content_hash"] = "1" * 64
    payload["layout_hash"] = "2" * 64
    return payload


def _legacy_scheme_payload(*, english: bool = True) -> dict[str, object]:
    payload = _current_scheme().model_dump(mode="json")
    payload["contract_version"] = "0.1.0"
    payload["name_en"] = "  Base Scheme  " if english else None
    payload["name_zh"] = "Fallback Scheme" if not english else "基础方案"
    payload["description_en"] = "  Task-neutral starter scheme.  " if english else None
    payload["description_zh"] = "Fallback scheme description." if not english else "基础方案。"
    payload.pop("name")
    payload.pop("description")
    payload["content_hash"] = "3" * 64
    payload["layout_hash"] = "4" * 64
    return payload


def _insert_current_row(
    database: ProjectDatabase,
    *,
    table: str,
    id_column: str,
    payload: dict[str, object],
) -> None:
    database.execute(
        f"""
        INSERT INTO {table}(
            {id_column}, canonical_json, lifecycle, semantic_revision, layout_revision,
            content_hash, layout_hash, technical_status, head_event_id, redo_event_id,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
        """,  # noqa: S608 - closed test-only table and column names
        (
            payload[id_column],
            encode_canonical_json(payload),
            payload["lifecycle"],
            payload["semantic_revision"],
            payload["layout_revision"],
            payload["content_hash"],
            payload["layout_hash"],
            payload["technical_status"],
            "2026-07-21T12:00:00Z",
            "2026-07-21T12:00:00Z",
        ),
    )


def test_normalisers_prefer_nonblank_english_and_trim_it() -> None:
    node = normalise_legacy_model_node(_legacy_node_payload())
    scheme = normalise_legacy_task_scheme(_legacy_scheme_payload())

    assert node.item.name == "Flight State"
    assert node.item.short_name == "X"
    assert node.item.description == "Canonical flight-state input."
    assert node.item.definition.help_text == "Provides X(t) to Evidence recipes."
    assert node.diagnostics == ()
    assert scheme.item.name == "Base Scheme"
    assert scheme.item.description == "Task-neutral starter scheme."
    assert scheme.diagnostics == ()


def test_normalisers_preserve_only_available_alternate_text_with_diagnostic() -> None:
    node = normalise_legacy_model_node(_legacy_node_payload(english=False))
    scheme = normalise_legacy_task_scheme(_legacy_scheme_payload(english=False))

    assert node.item.name == "Flight State Fallback"
    assert node.item.definition.help_text == "Fallback raw-input help."
    assert node.diagnostics[0].code == ENGLISH_FALLBACK_DIAGNOSTIC
    assert node.diagnostics[0].fields == (
        "definition.help_text",
        "description",
        "name",
        "short_name",
    )
    assert scheme.diagnostics[0].code == ENGLISH_FALLBACK_DIAGNOSTIC
    assert scheme.diagnostics[0].fields == ("description", "name")


def test_content_migration_is_atomic_idempotent_and_retains_legacy_bytes(
    tmp_path: Path,
) -> None:
    database = ProjectDatabase.connect(tmp_path / "system.sqlite3", clock=lambda: NOW)
    node_payload = _legacy_node_payload()
    scheme_payload = _legacy_scheme_payload()
    old_node_bytes = encode_canonical_json(node_payload)
    try:
        _insert_current_row(
            database,
            table="model_nodes",
            id_column="node_id",
            payload=node_payload,
        )
        _insert_current_row(
            database,
            table="task_schemes",
            id_column="scheme_id",
            payload=scheme_payload,
        )

        first = migrate_current_model_content(database, migrated_at=NOW)
        assert first.migrated_node_count == 1
        assert first.migrated_scheme_count == 1
        assert first.before_fingerprint in first.compatible_predecessor_fingerprints
        assert first.before_fingerprint != first.after_fingerprint

        stored = database.fetchone("SELECT canonical_json FROM model_nodes WHERE node_id = 'raw.x'")
        assert stored is not None
        current_node = decode_current_model_object(
            stored["canonical_json"],
            object_kind=ModelObjectKind.NODE,
        )
        assert current_node.contract_version == "0.2.0"
        assert current_node.name == "Flight State"
        lineage = database.fetchone(
            "SELECT * FROM model_content_migration_events WHERE object_id = 'raw.x'"
        )
        assert lineage is not None
        assert lineage["legacy_payload"] == old_node_bytes
        assert lineage["before_workspace_fingerprint"] == first.before_fingerprint
        assert lineage["after_workspace_fingerprint"] == first.after_fingerprint

        second = migrate_current_model_content(database, migrated_at=NOW)
        assert second.migrated_object_count == 0
        assert second.compatible_predecessor_fingerprints == (first.before_fingerprint,)
        assert (
            database.fetchone("SELECT COUNT(*) AS count FROM model_content_migration_events")[
                "count"
            ]
            == 2
        )
    finally:
        database.close()


def test_invalid_row_aborts_before_any_current_row_is_rewritten(tmp_path: Path) -> None:
    database = ProjectDatabase.connect(tmp_path / "system.sqlite3", clock=lambda: NOW)
    node_payload = _legacy_node_payload()
    invalid_scheme = _legacy_scheme_payload()
    invalid_scheme["name_en"] = None
    invalid_scheme["name_zh"] = None
    try:
        _insert_current_row(
            database,
            table="model_nodes",
            id_column="node_id",
            payload=node_payload,
        )
        _insert_current_row(
            database,
            table="task_schemes",
            id_column="scheme_id",
            payload=invalid_scheme,
        )
        original = database.fetchone(
            "SELECT canonical_json FROM model_nodes WHERE node_id = 'raw.x'"
        )["canonical_json"]

        with pytest.raises(CurrentModelContentMigrationError):
            migrate_current_model_content(database, migrated_at=NOW)

        assert (
            database.fetchone("SELECT canonical_json FROM model_nodes WHERE node_id = 'raw.x'")[
                "canonical_json"
            ]
            == original
        )
        assert (
            database.fetchone("SELECT COUNT(*) AS count FROM model_content_migration_events")[
                "count"
            ]
            == 0
        )
    finally:
        database.close()


def test_repository_undo_reads_legacy_snapshot_without_rewriting_event_bytes(
    tmp_path: Path,
) -> None:
    database = ProjectDatabase.connect(tmp_path / "system.sqlite3", clock=lambda: NOW)
    legacy_payload = _legacy_node_payload()
    legacy_bytes = encode_canonical_json(legacy_payload)
    before = normalise_legacy_model_node(legacy_payload).item
    assert isinstance(before, ModelNode)
    after = rehash_model_node(
        before.model_copy(
            update={
                "name": "Updated Flight State",
                "semantic_revision": before.semantic_revision + 1,
            }
        )
    )
    diff = CanonicalModelDiff(
        changed_paths=("/name",),
        added_node_ids=(),
        removed_node_ids=(),
        added_edge_ids=(),
        removed_edge_ids=(),
        metadata={"fixture": "legacy-event"},
    )
    try:
        with database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO model_change_events(
                    event_id, object_kind, object_id, event_kind, parent_event_id,
                    semantic_revision, layout_revision, before_hash, after_hash,
                    before_json, after_json, diff_json, transaction_id, actor_id, occurred_at
                ) VALUES (?, 'node', ?, 'update', NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "event.legacy-update",
                    after.node_id,
                    after.semantic_revision,
                    after.layout_revision,
                    legacy_payload["content_hash"],
                    after.content_hash,
                    legacy_bytes,
                    encode_canonical_json(after.model_dump(mode="json")),
                    encode_canonical_json(diff.model_dump(mode="json")),
                    "tx.legacy-update",
                    "expert.legacy",
                    "2026-07-21T12:00:00Z",
                ),
            )
            connection.execute(
                """
                INSERT INTO model_nodes(
                    node_id, canonical_json, lifecycle, semantic_revision, layout_revision,
                    content_hash, layout_hash, technical_status, head_event_id, redo_event_id,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'event.legacy-update', NULL, ?, ?)
                """,
                (
                    after.node_id,
                    encode_canonical_json(after.model_dump(mode="json")),
                    after.lifecycle.value,
                    after.semantic_revision,
                    after.layout_revision,
                    after.content_hash,
                    after.layout_hash,
                    after.technical_status.value,
                    "2026-07-21T12:00:00Z",
                    "2026-07-21T12:00:00Z",
                ),
            )

        restored = SqliteModelWorkspaceRepository(database).undo_node(
            after.node_id,
            expected_semantic_revision=after.semantic_revision,
            expected_layout_revision=after.layout_revision,
            event_id="event.undo-legacy-update",
            actor_id="expert.current",
            transaction_id="tx.undo-legacy-update",
            occurred_at=NOW,
        )

        assert restored.name == "Flight State"
        assert (
            database.fetchone(
                "SELECT before_json FROM model_change_events WHERE event_id = 'event.legacy-update'"
            )["before_json"]
            == legacy_bytes
        )
    finally:
        database.close()
