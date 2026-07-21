"""Deterministic, non-overwriting import of legacy project-owned current models."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from pilot_assessment.contracts.model_workspace import (
    BnNodeDefinition,
    EvidenceNodeDefinition,
    ModelNode,
    ModelNodeRef,
    RawInputNodeDefinition,
    TaskScheme,
)
from pilot_assessment.model_workspace.edit_session import ModelEditSessionManager
from pilot_assessment.model_workspace.hashing import rehash_model_node, rehash_task_scheme
from pilot_assessment.model_workspace.service import CurrentModelWorkspaceService
from pilot_assessment.persistence.database import (
    Clock,
    ProjectDatabase,
    decode_canonical_json,
    encode_canonical_json,
)
from pilot_assessment.persistence.model_workspace_repository import (
    CurrentObjectNotFoundError,
    SqliteModelWorkspaceRepository,
)
from pilot_assessment.persistence.project import ProjectStore


class LegacyModelImportError(RuntimeError):
    """A legacy project model could not be safely merged into the system library."""


class LegacyModelImportConflictError(LegacyModelImportError):
    """The import must wait for the current system edit session to be resolved."""


@dataclass(frozen=True, slots=True)
class LegacyModelImportResult:
    legacy_model_detected: bool
    import_fingerprint: str | None
    imported: bool
    replayed: bool
    inserted_node_count: int
    inserted_scheme_count: int
    reused_node_count: int
    reused_scheme_count: int
    dirty_edit_recovered: bool
    node_id_mapping: dict[str, str]
    scheme_id_mapping: dict[str, str]


@dataclass(frozen=True, slots=True)
class _LegacyEditSnapshot:
    fingerprint: str
    nodes: tuple[ModelNode, ...]
    schemes: tuple[TaskScheme, ...]


@dataclass(frozen=True, slots=True)
class _MergePlan:
    node_mapping: dict[str, str]
    scheme_mapping: dict[str, str]
    nodes: tuple[ModelNode, ...]
    schemes: tuple[TaskScheme, ...]
    insert_node_ids: tuple[str, ...]
    insert_scheme_ids: tuple[str, ...]
    reused_node_count: int
    reused_scheme_count: int


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise LegacyModelImportError("legacy import clock must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _fingerprint(
    nodes: tuple[ModelNode, ...],
    schemes: tuple[TaskScheme, ...],
    *,
    include_revisions: bool = True,
) -> str:
    excluded = {"created_at", "updated_at"}
    if not include_revisions:
        excluded.update({"semantic_revision", "layout_revision"})
    payload = {
        "nodes": [
            item.model_dump(mode="json", exclude=excluded)
            for item in sorted(nodes, key=lambda value: value.node_id)
        ],
        "schemes": [
            item.model_dump(mode="json", exclude=excluded)
            for item in sorted(schemes, key=lambda value: value.scheme_id)
        ],
    }
    return hashlib.sha256(encode_canonical_json(payload)).hexdigest()


def _import_fingerprint(canonical: str, legacy_edit: str | None) -> str:
    return hashlib.sha256(
        encode_canonical_json(
            {"canonical_fingerprint": canonical, "legacy_edit_fingerprint": legacy_edit}
        )
    ).hexdigest()


def _deterministic_id(kind: str, source_id: str, fingerprint: str) -> str:
    digest = hashlib.sha256(f"{kind}\0{source_id}\0{fingerprint}".encode()).hexdigest()[:32]
    return f"{kind}.imported.{digest}"


def _map_ref(reference: ModelNodeRef, mapping: dict[str, str]) -> ModelNodeRef:
    return reference.model_copy(
        update={"node_id": mapping.get(reference.node_id, reference.node_id)}
    )


def _transform_node(node: ModelNode, mapping: dict[str, str]) -> ModelNode:
    node_id = mapping.get(node.node_id, node.node_id)
    definition = node.definition
    if isinstance(definition, EvidenceNodeDefinition):
        parents = tuple(
            _map_ref(item, mapping) for item in definition.ordered_probabilistic_parent_nodes
        )
        definition = definition.model_copy(
            update={
                "data_bindings": tuple(
                    item.model_copy(
                        update={"raw_input_node": _map_ref(item.raw_input_node, mapping)}
                    )
                    for item in definition.data_bindings
                ),
                "ordered_probabilistic_parent_nodes": parents,
                "cpt": definition.cpt.model_copy(
                    update={
                        "child_node": ModelNodeRef(node_id=node_id, node_kind=node.node_kind),
                        "ordered_parent_nodes": parents,
                    }
                ),
            }
        )
    elif isinstance(definition, BnNodeDefinition):
        parents = tuple(
            _map_ref(item, mapping) for item in definition.ordered_probabilistic_parent_nodes
        )
        definition = definition.model_copy(
            update={
                "ordered_probabilistic_parent_nodes": parents,
                "cpt": definition.cpt.model_copy(
                    update={
                        "child_node": ModelNodeRef(node_id=node_id, node_kind=node.node_kind),
                        "ordered_parent_nodes": parents,
                    }
                ),
            }
        )
    elif not isinstance(definition, RawInputNodeDefinition):
        raise LegacyModelImportError(
            f"unsupported model node definition {type(definition).__name__}"
        )
    return rehash_model_node(
        node.model_copy(
            update={
                "node_id": node_id,
                "copied_from_node_id": (
                    None
                    if node.copied_from_node_id is None
                    else mapping.get(node.copied_from_node_id, node.copied_from_node_id)
                ),
                "definition": definition,
                "global_layout": node.global_layout.model_copy(update={"node_id": node_id}),
            }
        )
    )


def _contains_remapped_reference(value: object, mapping: dict[str, str]) -> bool:
    if isinstance(value, str):
        return value in mapping and mapping[value] != value
    if isinstance(value, dict):
        return any(_contains_remapped_reference(item, mapping) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_remapped_reference(item, mapping) for item in value)
    return False


def _transform_scheme(
    scheme: TaskScheme,
    node_mapping: dict[str, str],
    scheme_mapping: dict[str, str],
) -> TaskScheme:
    if _contains_remapped_reference(scheme.task_bindings, node_mapping):
        raise LegacyModelImportError(
            f"scheme {scheme.scheme_id!r} contains an untyped task-binding reference to a "
            "remapped node; automatic text replacement is forbidden"
        )
    scheme_id = scheme_mapping.get(scheme.scheme_id, scheme.scheme_id)
    return rehash_task_scheme(
        scheme.model_copy(
            update={
                "scheme_id": scheme_id,
                "copied_from_scheme_id": (
                    None
                    if scheme.copied_from_scheme_id is None
                    else scheme_mapping.get(
                        scheme.copied_from_scheme_id,
                        scheme.copied_from_scheme_id,
                    )
                ),
                "explicit_active_node_ids": tuple(
                    sorted(node_mapping.get(item, item) for item in scheme.explicit_active_node_ids)
                ),
                "computed_active_closure": tuple(
                    sorted(node_mapping.get(item, item) for item in scheme.computed_active_closure)
                ),
                "output_node_ids": tuple(
                    sorted(node_mapping.get(item, item) for item in scheme.output_node_ids)
                ),
                "layout_overrides": tuple(
                    sorted(
                        (
                            item.model_copy(
                                update={"node_id": node_mapping.get(item.node_id, item.node_id)}
                            )
                            for item in scheme.layout_overrides
                        ),
                        key=lambda item: item.node_id,
                    )
                ),
            }
        )
    )


def _same_node(left: ModelNode, right: ModelNode) -> bool:
    return left.node_kind is right.node_kind and (
        left.content_hash,
        left.layout_hash,
    ) == (right.content_hash, right.layout_hash)


def _same_scheme(left: TaskScheme, right: TaskScheme) -> bool:
    return (left.content_hash, left.layout_hash) == (right.content_hash, right.layout_hash)


def _parent_ids(node: ModelNode) -> tuple[str, ...]:
    definition = node.definition
    result: list[str] = []
    if isinstance(definition, EvidenceNodeDefinition):
        result.extend(item.raw_input_node.node_id for item in definition.data_bindings)
        result.extend(item.node_id for item in definition.ordered_probabilistic_parent_nodes)
    elif isinstance(definition, BnNodeDefinition):
        result.extend(item.node_id for item in definition.ordered_probabilistic_parent_nodes)
    return tuple(dict.fromkeys(result))


def _ordered_new_nodes(
    nodes: tuple[ModelNode, ...],
    *,
    existing_ids: set[str],
) -> tuple[ModelNode, ...]:
    pending = {item.node_id: item for item in nodes}
    ordered: list[ModelNode] = []
    available = set(existing_ids)
    while pending:
        ready = sorted(
            (item for item in pending.values() if set(_parent_ids(item)).issubset(available)),
            key=lambda item: item.node_id,
        )
        if not ready:
            unresolved = ", ".join(sorted(pending))
            raise LegacyModelImportError(
                f"legacy model contains missing or cyclic dependencies: {unresolved}"
            )
        for item in ready:
            ordered.append(item)
            available.add(item.node_id)
            pending.pop(item.node_id)
    return tuple(ordered)


class LegacyProjectModelImporter:
    """Merge old project-owned current state into one shared system model."""

    def __init__(
        self,
        database: ProjectDatabase,
        workspace: CurrentModelWorkspaceService,
        edit_session: ModelEditSessionManager,
        *,
        clock: Clock,
    ) -> None:
        self.database = database
        self.workspace = workspace
        self.edit_session = edit_session
        self.clock = clock

    def import_project(self, project: ProjectStore) -> LegacyModelImportResult:
        legacy = CurrentModelWorkspaceService(
            SqliteModelWorkspaceRepository(project.database),
            model_library_id=project.descriptor.project_id,
            operator_registry=self.workspace.operator_registry,
            source_catalog=self.workspace.source_catalog,
            clock=self.clock,
        )
        nodes = legacy.list_nodes()
        schemes = legacy.list_schemes()
        if not nodes and not schemes:
            return LegacyModelImportResult(False, None, False, False, 0, 0, 0, 0, False, {}, {})

        canonical_fingerprint = _fingerprint(nodes, schemes)
        dirty = self._read_dirty_edit(project.root)
        fingerprint = _import_fingerprint(
            canonical_fingerprint,
            None if dirty is None else dirty.fingerprint,
        )
        replay = self._read_receipt(fingerprint)
        if replay is not None:
            return replay
        if self.edit_session.status().dirty:
            raise LegacyModelImportConflictError(
                "save or discard the current system model edits before importing a legacy "
                "project-owned model"
            )

        plan = self._plan(nodes, schemes, fingerprint=fingerprint)
        inserted_nodes, inserted_schemes = self._apply_canonical(plan, fingerprint=fingerprint)
        if inserted_nodes or inserted_schemes:
            self.edit_session.refresh_clean_from_canonical()
        dirty_recovered = False
        if dirty is not None:
            self._recover_dirty_edit(dirty, plan, fingerprint=fingerprint)
            dirty_recovered = True

        result = LegacyModelImportResult(
            legacy_model_detected=True,
            import_fingerprint=fingerprint,
            imported=bool(inserted_nodes or inserted_schemes or dirty_recovered),
            replayed=False,
            inserted_node_count=inserted_nodes,
            inserted_scheme_count=inserted_schemes,
            reused_node_count=plan.reused_node_count,
            reused_scheme_count=plan.reused_scheme_count,
            dirty_edit_recovered=dirty_recovered,
            node_id_mapping=dict(plan.node_mapping),
            scheme_id_mapping=dict(plan.scheme_mapping),
        )
        self._write_receipt(
            result,
            source_project_id=project.descriptor.project_id,
            canonical_fingerprint=canonical_fingerprint,
            legacy_edit_fingerprint=None if dirty is None else dirty.fingerprint,
        )
        return result

    def _plan(
        self,
        nodes: tuple[ModelNode, ...],
        schemes: tuple[TaskScheme, ...],
        *,
        fingerprint: str,
    ) -> _MergePlan:
        existing_nodes = {item.node_id: item for item in self.workspace.list_nodes()}
        node_mapping = {item.node_id: item.node_id for item in nodes}
        changed = True
        while changed:
            changed = False
            for source in sorted(nodes, key=lambda item: item.node_id):
                target_id = node_mapping[source.node_id]
                candidate = _transform_node(source, node_mapping)
                existing = existing_nodes.get(target_id)
                if existing is None or _same_node(existing, candidate):
                    continue
                if target_id != source.node_id:
                    raise LegacyModelImportError(
                        f"deterministic imported node identity {target_id!r} collides"
                    )
                node_mapping[source.node_id] = _deterministic_id(
                    "model-node", source.node_id, fingerprint
                )
                changed = True

        transformed_nodes = tuple(
            _transform_node(item, node_mapping)
            for item in sorted(nodes, key=lambda value: value.node_id)
        )
        for item in transformed_nodes:
            existing = existing_nodes.get(item.node_id)
            if existing is not None and not _same_node(existing, item):
                raise LegacyModelImportError(
                    f"node collision remains after deterministic remap: {item.node_id!r}"
                )

        existing_schemes = {item.scheme_id: item for item in self.workspace.list_schemes()}
        scheme_mapping = {item.scheme_id: item.scheme_id for item in schemes}
        changed = True
        while changed:
            changed = False
            for source in sorted(schemes, key=lambda item: item.scheme_id):
                target_id = scheme_mapping[source.scheme_id]
                candidate = _transform_scheme(source, node_mapping, scheme_mapping)
                existing = existing_schemes.get(target_id)
                if existing is None or _same_scheme(existing, candidate):
                    continue
                if target_id != source.scheme_id:
                    raise LegacyModelImportError(
                        f"deterministic imported scheme identity {target_id!r} collides"
                    )
                scheme_mapping[source.scheme_id] = _deterministic_id(
                    "task-scheme", source.scheme_id, fingerprint
                )
                changed = True

        transformed_schemes = tuple(
            _transform_scheme(item, node_mapping, scheme_mapping)
            for item in sorted(schemes, key=lambda value: value.scheme_id)
        )
        insert_node_ids = tuple(
            item.node_id for item in transformed_nodes if item.node_id not in existing_nodes
        )
        insert_scheme_ids = tuple(
            item.scheme_id for item in transformed_schemes if item.scheme_id not in existing_schemes
        )
        return _MergePlan(
            node_mapping=node_mapping,
            scheme_mapping=scheme_mapping,
            nodes=transformed_nodes,
            schemes=transformed_schemes,
            insert_node_ids=insert_node_ids,
            insert_scheme_ids=insert_scheme_ids,
            reused_node_count=len(transformed_nodes) - len(insert_node_ids),
            reused_scheme_count=len(transformed_schemes) - len(insert_scheme_ids),
        )

    def _apply_canonical(self, plan: _MergePlan, *, fingerprint: str) -> tuple[int, int]:
        new_nodes = tuple(item for item in plan.nodes if item.node_id in plan.insert_node_ids)
        ordered = _ordered_new_nodes(
            new_nodes,
            existing_ids={item.node_id for item in self.workspace.list_nodes()},
        )
        with self.database.transaction():
            for index, node in enumerate(ordered):
                saved = self.workspace.create_node(
                    node,
                    transaction_id=f"tx.legacy-import.{fingerprint[:20]}.node.{index}",
                    actor_id="system.legacy-model-import",
                ).node
                if (saved.content_hash, saved.layout_hash) != (
                    node.content_hash,
                    node.layout_hash,
                ):
                    raise LegacyModelImportError(
                        f"imported node {node.node_id!r} changed semantic or layout identity"
                    )
            for index, scheme in enumerate(
                item for item in plan.schemes if item.scheme_id in plan.insert_scheme_ids
            ):
                saved = self.workspace.create_scheme(
                    scheme,
                    transaction_id=f"tx.legacy-import.{fingerprint[:20]}.scheme.{index}",
                    actor_id="system.legacy-model-import",
                ).scheme
                if (saved.content_hash, saved.layout_hash) != (
                    scheme.content_hash,
                    scheme.layout_hash,
                ):
                    raise LegacyModelImportError(
                        f"imported scheme {scheme.scheme_id!r} changed semantic or layout identity"
                    )
        return len(ordered), len(plan.insert_scheme_ids)

    def _read_dirty_edit(self, project_root: Path) -> _LegacyEditSnapshot | None:
        path = project_root / "staging" / "model-edit" / "workspace.sqlite3"
        if not path.is_file():
            return None
        database = ProjectDatabase.connect(path, clock=self.clock)
        try:
            state = database.fetchone(
                "SELECT baseline_state_hash FROM model_edit_session_state WHERE singleton = 1"
            )
            if state is None:
                return None
            repository = SqliteModelWorkspaceRepository(database)
            nodes = repository.list_nodes()
            schemes = repository.list_schemes()
            if (
                _fingerprint(nodes, schemes, include_revisions=False)
                == state["baseline_state_hash"]
            ):
                return None
            return _LegacyEditSnapshot(_fingerprint(nodes, schemes), nodes, schemes)
        finally:
            database.close()

    def _recover_dirty_edit(
        self,
        dirty: _LegacyEditSnapshot,
        canonical: _MergePlan,
        *,
        fingerprint: str,
    ) -> None:
        node_mapping = dict(canonical.node_mapping)
        scheme_mapping = dict(canonical.scheme_mapping)
        canonical_node_ids = set(node_mapping)
        canonical_scheme_ids = set(scheme_mapping)
        for node in dirty.nodes:
            node_mapping.setdefault(node.node_id, node.node_id)
        for scheme in dirty.schemes:
            scheme_mapping.setdefault(scheme.scheme_id, scheme.scheme_id)

        editable_nodes = {item.node_id: item for item in self.edit_session.workspace.list_nodes()}
        changed = True
        while changed:
            changed = False
            for source in sorted(dirty.nodes, key=lambda item: item.node_id):
                if source.node_id in canonical_node_ids:
                    continue
                candidate = _transform_node(source, node_mapping)
                existing = editable_nodes.get(candidate.node_id)
                if existing is None or _same_node(existing, candidate):
                    continue
                if node_mapping[source.node_id] != source.node_id:
                    raise LegacyModelImportError(
                        f"dirty imported node identity {candidate.node_id!r} collides"
                    )
                node_mapping[source.node_id] = _deterministic_id(
                    "model-node", source.node_id, dirty.fingerprint
                )
                changed = True

        editable_schemes = {
            item.scheme_id: item for item in self.edit_session.workspace.list_schemes()
        }
        changed = True
        while changed:
            changed = False
            for source in sorted(dirty.schemes, key=lambda item: item.scheme_id):
                if source.scheme_id in canonical_scheme_ids:
                    continue
                candidate = _transform_scheme(source, node_mapping, scheme_mapping)
                existing = editable_schemes.get(candidate.scheme_id)
                if existing is None or _same_scheme(existing, candidate):
                    continue
                if scheme_mapping[source.scheme_id] != source.scheme_id:
                    raise LegacyModelImportError(
                        f"dirty imported scheme identity {candidate.scheme_id!r} collides"
                    )
                scheme_mapping[source.scheme_id] = _deterministic_id(
                    "task-scheme", source.scheme_id, dirty.fingerprint
                )
                changed = True

        nodes = tuple(_transform_node(item, node_mapping) for item in dirty.nodes)
        schemes = tuple(
            _transform_scheme(item, node_mapping, scheme_mapping) for item in dirty.schemes
        )
        transaction_id = f"tx.legacy-dirty-recovery.{fingerprint[:24]}"
        with self.edit_session.database.transaction() as connection:
            existing_ids = {item.node_id for item in self.edit_session.workspace.list_nodes()}
            new_nodes = tuple(item for item in nodes if item.node_id not in existing_ids)
            for node in _ordered_new_nodes(new_nodes, existing_ids=existing_ids):
                self.edit_session.workspace.create_node(
                    node,
                    transaction_id=transaction_id,
                    actor_id="system.legacy-model-import",
                )
                existing_ids.add(node.node_id)
            for node in nodes:
                try:
                    current = self.edit_session.workspace.get_node(node.node_id)
                except CurrentObjectNotFoundError:
                    continue
                semantic = current.content_hash != node.content_hash
                layout = current.layout_hash != node.layout_hash
                if semantic or layout:
                    self.edit_session.workspace.update_node(
                        node,
                        expected_semantic_revision=current.semantic_revision if semantic else None,
                        expected_layout_revision=current.layout_revision if layout else None,
                        transaction_id=transaction_id,
                        actor_id="system.legacy-model-import",
                    )
            for scheme in schemes:
                try:
                    current = self.edit_session.workspace.get_scheme(scheme.scheme_id)
                except CurrentObjectNotFoundError:
                    self.edit_session.workspace.create_scheme(
                        scheme,
                        transaction_id=transaction_id,
                        actor_id="system.legacy-model-import",
                    )
                    continue
                semantic = current.content_hash != scheme.content_hash
                layout = current.layout_hash != scheme.layout_hash
                if semantic or layout:
                    self.edit_session.workspace.update_scheme(
                        scheme,
                        expected_semantic_revision=current.semantic_revision if semantic else None,
                        expected_layout_revision=current.layout_revision if layout else None,
                        transaction_id=transaction_id,
                        actor_id="system.legacy-model-import",
                    )
            self.edit_session.capture_checkpoint(
                connection,
                transaction_id=transaction_id,
                method="model.legacy-dirty-edit.recover",
            )
        if not self.edit_session.status().dirty:
            raise LegacyModelImportError("legacy dirty edit recovery produced no staged difference")

    def _read_receipt(self, fingerprint: str) -> LegacyModelImportResult | None:
        row = self.database.fetchone(
            "SELECT * FROM legacy_system_model_import_receipts WHERE import_fingerprint = ?",
            (fingerprint,),
        )
        if row is None:
            return None
        node_mapping = decode_canonical_json(row["node_mapping_json"])
        scheme_mapping = decode_canonical_json(row["scheme_mapping_json"])
        if not isinstance(node_mapping, dict) or not isinstance(scheme_mapping, dict):
            raise LegacyModelImportError("stored legacy import mapping is invalid")
        return LegacyModelImportResult(
            legacy_model_detected=True,
            import_fingerprint=fingerprint,
            imported=False,
            replayed=True,
            inserted_node_count=int(row["inserted_node_count"]),
            inserted_scheme_count=int(row["inserted_scheme_count"]),
            reused_node_count=int(row["reused_node_count"]),
            reused_scheme_count=int(row["reused_scheme_count"]),
            dirty_edit_recovered=bool(row["dirty_edit_recovered"]),
            node_id_mapping={str(key): str(value) for key, value in node_mapping.items()},
            scheme_id_mapping={str(key): str(value) for key, value in scheme_mapping.items()},
        )

    def _write_receipt(
        self,
        result: LegacyModelImportResult,
        *,
        source_project_id: str,
        canonical_fingerprint: str,
        legacy_edit_fingerprint: str | None,
    ) -> None:
        if result.import_fingerprint is None:
            return
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO legacy_system_model_import_receipts(
                    import_fingerprint, source_project_id, canonical_fingerprint,
                    legacy_edit_fingerprint, node_mapping_json, scheme_mapping_json,
                    inserted_node_count, inserted_scheme_count, reused_node_count,
                    reused_scheme_count, dirty_edit_recovered, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.import_fingerprint,
                    source_project_id,
                    canonical_fingerprint,
                    legacy_edit_fingerprint,
                    encode_canonical_json(result.node_id_mapping),
                    encode_canonical_json(result.scheme_id_mapping),
                    result.inserted_node_count,
                    result.inserted_scheme_count,
                    result.reused_node_count,
                    result.reused_scheme_count,
                    int(result.dirty_edit_recovered),
                    _utc_text(self.clock()),
                ),
            )


def import_result_payload(result: LegacyModelImportResult) -> dict[str, object]:
    return asdict(result)


__all__ = [
    "LegacyModelImportConflictError",
    "LegacyModelImportError",
    "LegacyModelImportResult",
    "LegacyProjectModelImporter",
    "import_result_payload",
]
