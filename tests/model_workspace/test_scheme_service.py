from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from pilot_assessment.contracts.model_workspace import (
    ModelNode,
    ModelNodeKind,
    ModelObjectLifecycle,
    NodeLayout,
)
from pilot_assessment.model_library.sources import SourceCatalog, create_source_descriptor
from pilot_assessment.model_workspace.service import (
    CurrentModelWorkspaceService,
    CurrentSchemeRevisionConflict,
)
from pilot_assessment.persistence.database import ProjectDatabase
from pilot_assessment.persistence.model_workspace_repository import (
    SqliteModelWorkspaceRepository,
)
from tests.model_workspace.support import operator_registry, seven_node_graph

NOW = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


def _catalog(nodes: tuple[ModelNode, ...]) -> SourceCatalog:
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


def _workspace(
    path: Path,
) -> tuple[ProjectDatabase, CurrentModelWorkspaceService, tuple[ModelNode, ...]]:
    nodes, _ = seven_node_graph()
    database = ProjectDatabase.connect(path, clock=lambda: NOW)
    service = CurrentModelWorkspaceService(
        SqliteModelWorkspaceRepository(database),
        project_id="project.test",
        operator_registry=operator_registry(),
        source_catalog=_catalog(nodes),
        clock=lambda: NOW,
    )
    for index, node_id in enumerate(
        (
            "raw.x",
            "raw.u",
            "raw.g",
            "bn.competency",
            "bn.skill",
            "evidence.precision",
            "evidence.gaze",
        )
    ):
        node = next(item for item in nodes if item.node_id == node_id)
        service.create_node(
            node,
            transaction_id=f"tx.seed.node-{index}",
            actor_id="system.seed",
        )
    return database, service, nodes


def test_scheme_create_copy_and_graph_snapshot_share_nodes_without_publish_state(
    tmp_path: Path,
) -> None:
    database, service, _ = _workspace(tmp_path / "project.sqlite3")
    _, base = seven_node_graph()
    try:
        created = service.create_scheme(
            base,
            transaction_id="tx.scheme.base.create",
            actor_id="expert.one",
        )
        assert created.scheme.scheme_id == "scheme.base"
        assert created.scheme.technical_status.value == "executable"
        assert created.semantic_revision == 0
        assert len(created.graph.nodes) == 7
        assert len(created.graph.edges) == 6
        assert created.graph.project_id == "project.test"
        assert not hasattr(created.scheme, "published")
        assert not hasattr(created.scheme, "draft")

        copied = service.copy_scheme(
            "scheme.base",
            new_scheme_id="scheme.parallel",
            name_zh="并行任务方案",
            name_en="Parallel Task Scheme",
            transaction_id="tx.scheme.parallel.copy",
            actor_id="expert.one",
        )
        assert copied.scheme.copied_from_scheme_id == "scheme.base"
        assert copied.scheme.explicit_active_node_ids == base.explicit_active_node_ids
        assert copied.scheme.computed_active_closure == base.computed_active_closure
        assert copied.scheme.output_node_ids == base.output_node_ids
        assert copied.scheme.task_bindings == base.task_bindings
        assert copied.scheme.layout_overrides == base.layout_overrides
        assert tuple(node.node_id for node in copied.graph.nodes) == tuple(
            node.node_id for node in created.graph.nodes
        )
        assert len(service.list_nodes()) == 7
        assert tuple(item.scheme_id for item in service.list_schemes()) == (
            "scheme.base",
            "scheme.parallel",
        )
    finally:
        database.close()


def test_scheme_semantic_and_layout_edits_are_isolated_between_parallel_schemes(
    tmp_path: Path,
) -> None:
    database, service, _ = _workspace(tmp_path / "project.sqlite3")
    _, base = seven_node_graph()
    try:
        base_saved = service.create_scheme(
            base,
            transaction_id="tx.scheme.base.create",
            actor_id="expert.one",
        ).scheme
        parallel = service.copy_scheme(
            base.scheme_id,
            new_scheme_id="scheme.parallel",
            name_zh=None,
            name_en="Parallel Scheme",
            transaction_id="tx.scheme.parallel.copy",
            actor_id="expert.one",
        ).scheme

        edited = parallel.model_copy(
            update={
                "name_en": "Straight Task Scheme",
                "task_bindings": {"task": "straight"},
            }
        )
        semantic = service.update_scheme(
            edited,
            expected_semantic_revision=parallel.semantic_revision,
            expected_layout_revision=None,
            transaction_id="tx.scheme.parallel.semantic",
            actor_id="expert.one",
        )
        assert semantic.scheme.name_en == "Straight Task Scheme"
        assert semantic.scheme.task_bindings == {"task": "straight"}
        assert semantic.semantic_revision == 1
        assert service.get_scheme(base.scheme_id) == base_saved

        stale = parallel.model_copy(
            update={
                "layout_overrides": (NodeLayout(node_id="evidence.precision", x=555.0, y=666.0),)
            }
        )
        layout = service.update_scheme(
            stale,
            expected_semantic_revision=None,
            expected_layout_revision=parallel.layout_revision,
            transaction_id="tx.scheme.parallel.layout",
            actor_id="expert.one",
        )
        assert layout.scheme.name_en == "Straight Task Scheme"
        assert layout.scheme.task_bindings == {"task": "straight"}
        assert layout.semantic_revision == 1
        assert layout.layout_revision == 1
        assert layout.scheme.layout_overrides[0].x == 555.0
        assert service.get_scheme(base.scheme_id).layout_overrides == base.layout_overrides

        with pytest.raises(CurrentSchemeRevisionConflict) as captured:
            service.update_scheme(
                edited.model_copy(update={"name_en": "Stale name"}),
                expected_semantic_revision=0,
                expected_layout_revision=None,
                transaction_id="tx.scheme.parallel.stale",
                actor_id="expert.one",
            )
        assert captured.value.current_scheme == layout.scheme
    finally:
        database.close()


def test_scheme_archive_history_undo_and_redo_are_durable(tmp_path: Path) -> None:
    path = tmp_path / "project.sqlite3"
    database, service, _ = _workspace(path)
    _, base = seven_node_graph()
    try:
        current = service.create_scheme(
            base,
            transaction_id="tx.scheme.base.create",
            actor_id="expert.one",
        ).scheme
        archived = service.archive_scheme(
            current.scheme_id,
            expected_semantic_revision=current.semantic_revision,
            transaction_id="tx.scheme.base.archive",
            actor_id="expert.one",
        )
        assert archived.scheme.lifecycle is ModelObjectLifecycle.ARCHIVED
        assert service.list_schemes(lifecycle=ModelObjectLifecycle.ACTIVE) == ()

        undone = service.undo_scheme(
            current.scheme_id,
            expected_semantic_revision=archived.semantic_revision,
            expected_layout_revision=archived.layout_revision,
            transaction_id="tx.scheme.base.undo",
            actor_id="expert.one",
        )
        assert undone.scheme.lifecycle is ModelObjectLifecycle.ACTIVE
        redone = service.redo_scheme(
            current.scheme_id,
            expected_semantic_revision=undone.semantic_revision,
            expected_layout_revision=undone.layout_revision,
            transaction_id="tx.scheme.base.redo",
            actor_id="expert.one",
        )
        assert redone.scheme.lifecycle is ModelObjectLifecycle.ARCHIVED
        assert [event.event_kind.value for event in service.scheme_history(base.scheme_id)] == [
            "create",
            "archive",
            "undo",
            "redo",
        ]
    finally:
        database.close()

    reopened = ProjectDatabase.connect(path, clock=lambda: NOW)
    try:
        durable = CurrentModelWorkspaceService(
            SqliteModelWorkspaceRepository(reopened),
            project_id="project.test",
            operator_registry=operator_registry(),
            source_catalog=_catalog(seven_node_graph()[0]),
            clock=lambda: NOW,
        )
        assert durable.get_scheme(base.scheme_id).lifecycle is ModelObjectLifecycle.ARCHIVED
        assert len(durable.list_nodes()) == 7
    finally:
        reopened.close()
