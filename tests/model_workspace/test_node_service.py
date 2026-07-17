from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from pilot_assessment.contracts.model_workspace import (
    CanonicalModelDiff,
    EvidenceDataBinding,
    EvidenceNodeDefinition,
    ModelNode,
    ModelNodeKind,
    ModelNodeRef,
    ModelObjectLifecycle,
    ModelTechnicalStatus,
)
from pilot_assessment.model_library.sources import SourceCatalog, create_source_descriptor
from pilot_assessment.model_workspace.service import (
    CurrentModelArchiveConflict,
    CurrentModelRevisionConflict,
    CurrentModelWorkspaceService,
)
from pilot_assessment.persistence.database import ProjectDatabase
from pilot_assessment.persistence.model_workspace_repository import (
    SqliteModelWorkspaceRepository,
)
from tests.model_workspace.support import operator_registry, seven_node_graph

NOW = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


def _node(nodes: tuple[ModelNode, ...], node_id: str) -> ModelNode:
    return next(node for node in nodes if node.node_id == node_id)


def _source_catalog(nodes: tuple[ModelNode, ...]) -> SourceCatalog:
    return SourceCatalog(
        tuple(
            create_source_descriptor(
                source_id=node.definition.source_descriptor.source_id,
                kind=node.definition.source_descriptor.kind,
                name=node.definition.source_descriptor.name,
                description=node.definition.source_descriptor.description,
                declared_type=node.definition.source_descriptor.declared_type,
                raw_modality=node.definition.source_descriptor.raw_modality,
                source_dependencies=node.definition.source_descriptor.source_dependencies,
                metadata=node.definition.source_descriptor.metadata,
            )
            for node in nodes
            if node.node_kind is ModelNodeKind.RAW_INPUT
        )
    )


def _service(
    path: Path,
) -> tuple[ProjectDatabase, SqliteModelWorkspaceRepository, CurrentModelWorkspaceService]:
    nodes, _ = seven_node_graph()
    database = ProjectDatabase.connect(path, clock=lambda: NOW)
    repository = SqliteModelWorkspaceRepository(database)
    return (
        database,
        repository,
        CurrentModelWorkspaceService(
            repository,
            operator_registry=operator_registry(),
            source_catalog=_source_catalog(nodes),
            clock=lambda: NOW,
        ),
    )


def _create(
    service: CurrentModelWorkspaceService,
    node: ModelNode,
    suffix: str,
) -> ModelNode:
    return service.create_node(
        node,
        transaction_id=f"tx.create.{suffix}",
        actor_id="expert.one",
    ).node


def _seed_valid_precision_graph(
    service: CurrentModelWorkspaceService,
) -> tuple[ModelNode, ...]:
    nodes, _ = seven_node_graph()
    for node_id in (
        "raw.x",
        "raw.u",
        "bn.competency",
        "bn.skill",
        "evidence.precision",
    ):
        _create(service, _node(nodes, node_id), node_id)
    return nodes


def _empty_diff(path: str) -> CanonicalModelDiff:
    return CanonicalModelDiff(
        changed_paths=(path,),
        added_node_ids=(),
        removed_node_ids=(),
        added_edge_ids=(),
        removed_edge_ids=(),
        metadata={},
    )


def test_inactive_incomplete_node_is_saved_with_diagnostics_and_survives_reopen(
    tmp_path: Path,
) -> None:
    path = tmp_path / "project.sqlite3"
    database, _, service = _service(path)
    nodes, _ = seven_node_graph()
    try:
        # The gaze Evidence deliberately arrives before its fixed Raw/BN parents.
        result = service.create_node(
            _node(nodes, "evidence.gaze"),
            transaction_id="tx.create.incomplete-gaze",
            actor_id="expert.one",
        )

        assert result.node.technical_status is ModelTechnicalStatus.INCOMPLETE
        assert result.affected_scheme_ids == ()
        assert result.semantic_revision == 0
        assert result.diff.added_node_ids == ("evidence.gaze",)
        assert {item.code for item in result.node.diagnostics} == {"model.node_reference_missing"}
        assert service.get_node("evidence.gaze") == result.node
        assert service.list_nodes() == (result.node,)
    finally:
        database.close()

    reopened, _, durable = _service(path)
    try:
        assert durable.get_node("evidence.gaze") == result.node
        assert len(durable.node_history("evidence.gaze")) == 1
    finally:
        reopened.close()


def test_semantic_layout_conflict_history_undo_and_redo_return_canonical_state(
    tmp_path: Path,
) -> None:
    database, _, service = _service(tmp_path / "project.sqlite3")
    nodes, _ = seven_node_graph()
    try:
        original = _create(service, _node(nodes, "raw.x"), "raw-x")
        renamed = original.model_copy(update={"name_en": "Flight-state stream"})
        semantic = service.update_node(
            renamed,
            expected_semantic_revision=0,
            expected_layout_revision=None,
            transaction_id="tx.rename.raw-x",
            actor_id="expert.one",
        )
        assert semantic.node.name_en == "Flight-state stream"
        assert semantic.semantic_revision == 1
        assert semantic.layout_revision == 0
        assert "/name_en" in semantic.diff.changed_paths

        stale_layout_copy = original.model_copy(
            update={
                "global_layout": original.global_layout.model_copy(update={"x": 999.0, "y": 777.0})
            }
        )
        moved = service.update_node(
            stale_layout_copy,
            expected_semantic_revision=None,
            expected_layout_revision=0,
            transaction_id="tx.move.raw-x",
            actor_id="expert.one",
        )
        assert moved.node.name_en == "Flight-state stream"
        assert moved.semantic_revision == 1
        assert moved.layout_revision == 1
        assert moved.node.global_layout.x == 999.0

        with pytest.raises(CurrentModelRevisionConflict) as captured:
            service.update_node(
                renamed.model_copy(update={"name_en": "Stale edit"}),
                expected_semantic_revision=0,
                expected_layout_revision=None,
                transaction_id="tx.stale.raw-x",
                actor_id="expert.one",
            )
        assert captured.value.current_node == moved.node

        undone = service.undo_node(
            "raw.x",
            expected_semantic_revision=1,
            expected_layout_revision=1,
            transaction_id="tx.undo.raw-x",
            actor_id="expert.one",
        )
        assert undone.node.global_layout == original.global_layout
        assert undone.node.name_en == "Flight-state stream"
        redone = service.redo_node(
            "raw.x",
            expected_semantic_revision=1,
            expected_layout_revision=2,
            transaction_id="tx.redo.raw-x",
            actor_id="expert.one",
        )
        assert redone.node.global_layout.x == 999.0
        assert [event.event_kind.value for event in service.node_history("raw.x")] == [
            "create",
            "update",
            "update",
            "undo",
            "redo",
        ]
    finally:
        database.close()


def test_shared_node_update_revalidates_using_scheme_and_active_node_cannot_archive(
    tmp_path: Path,
) -> None:
    database, repository, service = _service(tmp_path / "project.sqlite3")
    nodes = _seed_valid_precision_graph(service)
    _, scheme = seven_node_graph()
    repository.create_scheme(
        scheme,
        event_id="event.scheme.base.create",
        actor_id="expert.one",
        transaction_id="tx.scheme.base.create",
        occurred_at=NOW,
        diff=_empty_diff("/schemes/scheme.base"),
    )
    try:
        current = service.get_node("evidence.precision")
        definition = current.definition
        assert isinstance(definition, EvidenceNodeDefinition)
        broken_definition = definition.model_copy(
            update={
                "data_bindings": (
                    EvidenceDataBinding(
                        recipe_input_binding_id="flight-x",
                        raw_input_node=ModelNodeRef(
                            node_id="raw.missing",
                            node_kind=ModelNodeKind.RAW_INPUT,
                        ),
                    ),
                    definition.data_bindings[1],
                )
            }
        )
        result = service.update_node(
            current.model_copy(update={"definition": broken_definition}),
            expected_semantic_revision=current.semantic_revision,
            expected_layout_revision=None,
            transaction_id="tx.break.shared-precision",
            actor_id="expert.one",
        )

        assert result.node.technical_status is ModelTechnicalStatus.INCOMPLETE
        assert result.affected_scheme_ids == ("scheme.base",)
        blocked = repository.get_scheme("scheme.base")
        assert blocked.technical_status is ModelTechnicalStatus.BLOCKED
        assert "model.node_reference_missing" in {
            diagnostic.code for diagnostic in blocked.diagnostics
        }
        usage = service.node_usage_list("bn.skill")
        assert len(usage) == 1
        assert usage[0].scheme_id == "scheme.base"
        assert usage[0].active_in_closure is True

        active_skill = service.get_node("bn.skill")
        with pytest.raises(CurrentModelArchiveConflict) as captured:
            service.archive_node(
                "bn.skill",
                expected_semantic_revision=active_skill.semantic_revision,
                transaction_id="tx.archive.active-skill",
                actor_id="expert.one",
            )
        assert captured.value.active_scheme_ids == ("scheme.base",)
        assert service.get_node("bn.skill").lifecycle is ModelObjectLifecycle.ACTIVE

        # The unrelated inactive node remains freely archivable.
        raw_g = _create(service, _node(nodes, "raw.g"), "raw-g")
        archived = service.archive_node(
            raw_g.node_id,
            expected_semantic_revision=raw_g.semantic_revision,
            transaction_id="tx.archive.unused-raw-g",
            actor_id="expert.one",
        )
        assert archived.node.lifecycle is ModelObjectLifecycle.ARCHIVED
    finally:
        database.close()
