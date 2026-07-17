"""Project-scoped lifecycle service for mutable M7 complete nodes.

The service is deliberately a thin technical consistency boundary.  It does not
judge whether an expert's Evidence algorithm, thresholds or CPT are scientifically
good; it only keeps the editable current graph internally coherent and auditable.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final
from uuid import uuid4

from pilot_assessment.contracts.model_workspace import (
    CanonicalModelDiff,
    ModelChangeEvent,
    ModelDiagnostic,
    ModelDiagnosticSeverity,
    ModelGraphEdge,
    ModelGraphSnapshot,
    ModelNode,
    ModelObjectLifecycle,
    ModelTechnicalStatus,
    TaskScheme,
)
from pilot_assessment.evidence.registry import OperatorRegistry
from pilot_assessment.model_library.sources import SourceCatalog
from pilot_assessment.model_workspace.graph import (
    ModelGraphError,
    activation_closure,
    project_model_edges,
)
from pilot_assessment.model_workspace.hashing import (
    model_graph_semantic_hash,
    rehash_model_node,
    rehash_task_scheme,
)
from pilot_assessment.model_workspace.validation import validate_model_graph
from pilot_assessment.persistence.database import Clock
from pilot_assessment.persistence.model_workspace_repository import (
    CurrentObjectConflictError,
    CurrentObjectNotFoundError,
    SqliteModelWorkspaceRepository,
)

_NODE_BOOKKEEPING_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "semantic_revision",
        "layout_revision",
        "technical_status",
        "diagnostics",
        "content_hash",
        "layout_hash",
        "created_at",
        "updated_at",
    }
)
_SCHEME_BOOKKEEPING_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "semantic_revision",
        "layout_revision",
        "technical_status",
        "diagnostics",
        "content_hash",
        "layout_hash",
        "created_at",
        "updated_at",
    }
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CurrentModelServiceError(RuntimeError):
    """Base error for current model lifecycle operations."""


class CurrentModelMutationConflict(CurrentModelServiceError):
    """Raised when a current-object mutation cannot be applied atomically."""


class CurrentModelRevisionConflict(CurrentModelMutationConflict):
    """Optimistic conflict carrying the canonical node the editor must reconcile."""

    def __init__(self, message: str, *, current_node: ModelNode) -> None:
        super().__init__(message)
        self.current_node = current_node


class CurrentModelArchiveConflict(CurrentModelMutationConflict):
    """Raised when archiving would leave a physical tombstone in an active graph."""

    def __init__(self, node_id: str, *, active_scheme_ids: tuple[str, ...]) -> None:
        super().__init__(
            f"node {node_id!r} remains active in task schemes: " + ", ".join(active_scheme_ids)
        )
        self.node_id = node_id
        self.active_scheme_ids = active_scheme_ids


class CurrentSchemeRevisionConflict(CurrentModelMutationConflict):
    """Optimistic conflict carrying the canonical scheme for UI reconciliation."""

    def __init__(self, message: str, *, current_scheme: TaskScheme) -> None:
        super().__init__(message)
        self.current_scheme = current_scheme


@dataclass(frozen=True, slots=True)
class NodeUsage:
    """One task-scheme relationship shown by node usage inspection."""

    scheme_id: str
    scheme_lifecycle: ModelObjectLifecycle
    explicitly_active: bool
    active_in_closure: bool
    selected_as_output: bool


@dataclass(frozen=True, slots=True)
class NodeMutationResult:
    """Canonical response for every node mutation."""

    node: ModelNode
    affected_scheme_ids: tuple[str, ...]
    semantic_revision: int
    layout_revision: int
    technical_status: ModelTechnicalStatus
    diff: CanonicalModelDiff


@dataclass(frozen=True, slots=True)
class SchemeMutationResult:
    """Canonical task-scheme mutation plus the regenerated visible graph."""

    scheme: TaskScheme
    graph: ModelGraphSnapshot
    semantic_revision: int
    layout_revision: int
    technical_status: ModelTechnicalStatus
    diff: CanonicalModelDiff


def _graph_error_diagnostic(error: ModelGraphError) -> ModelDiagnostic:
    return ModelDiagnostic(
        code=error.code,
        severity=ModelDiagnosticSeverity.ERROR,
        location=error.location,
        message=str(error),
        details={},
    )


def _scheme_output_diagnostic(scheme: TaskScheme) -> ModelDiagnostic:
    missing = tuple(sorted(set(scheme.output_node_ids) - set(scheme.computed_active_closure)))
    return ModelDiagnostic(
        code="model.scheme_output_inactive",
        severity=ModelDiagnosticSeverity.ERROR,
        location=f"/schemes/{scheme.scheme_id}/output_node_ids",
        message="task scheme output nodes must resolve inside its active dependency closure",
        details={"missing_node_ids": list(missing)},
    )


def _canonical_changed_paths(before: ModelNode, after: ModelNode) -> tuple[str, ...]:
    before_payload = before.model_dump(mode="json")
    after_payload = after.model_dump(mode="json")
    return tuple(
        f"/{key}"
        for key in sorted(before_payload)
        if key not in _NODE_BOOKKEEPING_FIELDS and before_payload[key] != after_payload[key]
    )


def _canonical_scheme_changed_paths(
    before: TaskScheme,
    after: TaskScheme,
) -> tuple[str, ...]:
    before_payload = before.model_dump(mode="json")
    after_payload = after.model_dump(mode="json")
    return tuple(
        f"/{key}"
        for key in sorted(before_payload)
        if key not in _SCHEME_BOOKKEEPING_FIELDS and before_payload[key] != after_payload[key]
    )


def _replace_node(nodes: Iterable[ModelNode], candidate: ModelNode) -> tuple[ModelNode, ...]:
    index = {node.node_id: node for node in nodes}
    index[candidate.node_id] = candidate
    return tuple(index[node_id] for node_id in sorted(index))


def _child_edges(nodes: tuple[ModelNode, ...], node_id: str) -> tuple[ModelGraphEdge, ...]:
    """Best-effort resolvable edge projection used only for mutation diffs."""

    try:
        closure = activation_closure(nodes, (node_id,))
        edges = project_model_edges(nodes, node_ids=closure)
    except ModelGraphError:
        return ()
    return tuple(edge for edge in edges if edge.child.node_id == node_id)


def _all_resolvable_edges(nodes: tuple[ModelNode, ...]) -> tuple[ModelGraphEdge, ...]:
    """Project every currently resolvable edge while preserving incomplete experiments."""

    edges = {edge.edge_id: edge for node in nodes for edge in _child_edges(nodes, node.node_id)}
    return tuple(edges[edge_id] for edge_id in sorted(edges))


def _node_diff(
    before: ModelNode | None,
    after: ModelNode,
    *,
    before_nodes: tuple[ModelNode, ...],
    after_nodes: tuple[ModelNode, ...],
    mutation: str,
) -> CanonicalModelDiff:
    before_edges = () if before is None else _child_edges(before_nodes, before.node_id)
    after_edges = _child_edges(after_nodes, after.node_id)
    before_ids = {edge.edge_id for edge in before_edges}
    after_ids = {edge.edge_id for edge in after_edges}
    return CanonicalModelDiff(
        changed_paths=(
            (f"/nodes/{after.node_id}",)
            if before is None
            else _canonical_changed_paths(before, after)
        ),
        added_node_ids=((after.node_id,) if before is None else ()),
        removed_node_ids=(),
        added_edge_ids=tuple(sorted(after_ids - before_ids)),
        removed_edge_ids=tuple(sorted(before_ids - after_ids)),
        metadata={"mutation": mutation},
    )


class CurrentModelWorkspaceService:
    """Technical node workspace for one open managed project."""

    def __init__(
        self,
        repository: SqliteModelWorkspaceRepository,
        *,
        project_id: str,
        operator_registry: OperatorRegistry,
        source_catalog: SourceCatalog,
        clock: Clock = _utc_now,
        event_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.repository = repository
        self.project_id = project_id
        self.operator_registry = operator_registry
        self.source_catalog = source_catalog
        self._clock = clock
        self._event_id_factory = event_id_factory or (lambda: f"model-event.{uuid4().hex}")

    @property
    def available_source_ids(self) -> frozenset[str]:
        return frozenset(descriptor.source_id for descriptor in self.source_catalog.descriptors())

    def _event_id(self) -> str:
        return self._event_id_factory()

    def list_nodes(
        self,
        *,
        lifecycle: ModelObjectLifecycle | None = None,
    ) -> tuple[ModelNode, ...]:
        return self.repository.list_nodes(lifecycle=lifecycle)

    def get_node(self, node_id: str) -> ModelNode:
        return self.repository.get_node(node_id)

    def node_history(self, node_id: str) -> tuple[ModelChangeEvent, ...]:
        return self.repository.node_history(node_id)

    def node_usage_list(self, node_id: str) -> tuple[NodeUsage, ...]:
        self.repository.get_node(node_id)
        usages = (
            NodeUsage(
                scheme_id=scheme.scheme_id,
                scheme_lifecycle=scheme.lifecycle,
                explicitly_active=node_id in scheme.explicit_active_node_ids,
                active_in_closure=node_id in scheme.computed_active_closure,
                selected_as_output=node_id in scheme.output_node_ids,
            )
            for scheme in self.repository.list_schemes()
            if node_id in scheme.computed_active_closure
            or node_id in scheme.explicit_active_node_ids
            or node_id in scheme.output_node_ids
        )
        return tuple(sorted(usages, key=lambda item: item.scheme_id))

    def list_schemes(
        self,
        *,
        lifecycle: ModelObjectLifecycle | None = None,
    ) -> tuple[TaskScheme, ...]:
        return self.repository.list_schemes(lifecycle=lifecycle)

    def get_scheme(self, scheme_id: str) -> TaskScheme:
        return self.repository.get_scheme(scheme_id)

    def scheme_history(self, scheme_id: str) -> tuple[ModelChangeEvent, ...]:
        return self.repository.scheme_history(scheme_id)

    def graph_snapshot(self, scheme_id: str) -> ModelGraphSnapshot:
        return self._graph_snapshot(self.repository.get_scheme(scheme_id))

    def _graph_snapshot(self, scheme: TaskScheme) -> ModelGraphSnapshot:
        nodes = tuple(sorted(self.repository.list_nodes(), key=lambda item: item.node_id))
        edges = _all_resolvable_edges(nodes)
        return ModelGraphSnapshot(
            project_id=self.project_id,
            scheme=scheme,
            nodes=nodes,
            edges=edges,
            generated_at=self._clock(),
            graph_hash=model_graph_semantic_hash(
                self.project_id,
                scheme,
                nodes,
                edges,
            ),
        )

    def _normalize_node(
        self,
        proposed: ModelNode,
        nodes: tuple[ModelNode, ...],
    ) -> tuple[ModelNode, tuple[ModelNode, ...]]:
        candidate = rehash_model_node(proposed)
        candidates = _replace_node(nodes, candidate)
        try:
            closure = activation_closure(candidates, (candidate.node_id,))
        except ModelGraphError as error:
            diagnostics = (_graph_error_diagnostic(error),)
            status = ModelTechnicalStatus.INCOMPLETE
        else:
            outcome = validate_model_graph(
                candidates,
                active_node_ids=closure,
                operator_registry=self.operator_registry,
                available_source_ids=self.available_source_ids,
            )
            diagnostics = outcome.diagnostics
            status = (
                ModelTechnicalStatus.INCOMPLETE
                if outcome.technical_status is ModelTechnicalStatus.BLOCKED
                else ModelTechnicalStatus.EXECUTABLE
            )
        normalized = rehash_model_node(
            candidate.model_copy(
                update={
                    "technical_status": status,
                    "diagnostics": diagnostics,
                }
            )
        )
        return normalized, _replace_node(nodes, normalized)

    def _normalize_scheme(
        self,
        scheme: TaskScheme,
        nodes: tuple[ModelNode, ...],
    ) -> TaskScheme:
        try:
            closure = activation_closure(nodes, scheme.explicit_active_node_ids)
        except ModelGraphError as error:
            diagnostics = (_graph_error_diagnostic(error),)
            return scheme.model_copy(
                update={
                    "technical_status": ModelTechnicalStatus.BLOCKED,
                    "diagnostics": diagnostics,
                }
            )

        if not set(scheme.output_node_ids).issubset(closure):
            provisional = scheme.model_copy(update={"computed_active_closure": closure})
            diagnostic = _scheme_output_diagnostic(provisional)
            return scheme.model_copy(
                update={
                    "technical_status": ModelTechnicalStatus.BLOCKED,
                    "diagnostics": (diagnostic,),
                }
            )

        outcome = validate_model_graph(
            nodes,
            active_node_ids=closure,
            operator_registry=self.operator_registry,
            available_source_ids=self.available_source_ids,
        )
        return scheme.model_copy(
            update={
                "computed_active_closure": closure,
                "technical_status": outcome.technical_status,
                "diagnostics": outcome.diagnostics,
            }
        )

    def _affected_active_schemes(self, node_id: str) -> tuple[TaskScheme, ...]:
        return tuple(
            scheme
            for scheme in self.repository.list_schemes(lifecycle=ModelObjectLifecycle.ACTIVE)
            if node_id in scheme.computed_active_closure
            or node_id in scheme.explicit_active_node_ids
        )

    def _revalidate_affected_schemes(
        self,
        node_id: str,
        *,
        nodes: tuple[ModelNode, ...],
        transaction_id: str,
        actor_id: str,
        occurred_at: datetime,
    ) -> tuple[str, ...]:
        affected = self._affected_active_schemes(node_id)
        for scheme in affected:
            normalized = self._normalize_scheme(scheme, nodes)
            changed_paths = tuple(
                path
                for path, changed in (
                    (
                        "/computed_active_closure",
                        normalized.computed_active_closure != scheme.computed_active_closure,
                    ),
                    ("/technical_status", normalized.technical_status != scheme.technical_status),
                    ("/diagnostics", normalized.diagnostics != scheme.diagnostics),
                )
                if changed
            )
            if not changed_paths:
                continue
            self.repository.update_scheme(
                normalized,
                expected_semantic_revision=scheme.semantic_revision,
                expected_layout_revision=None,
                event_id=self._event_id(),
                actor_id=actor_id,
                transaction_id=transaction_id,
                occurred_at=occurred_at,
                diff=CanonicalModelDiff(
                    changed_paths=changed_paths,
                    added_node_ids=(),
                    removed_node_ids=(),
                    added_edge_ids=(),
                    removed_edge_ids=(),
                    metadata={
                        "mutation": "revalidate_after_shared_node_change",
                        "changed_node_id": node_id,
                    },
                ),
                join_existing=True,
            )
        return tuple(scheme.scheme_id for scheme in affected)

    def _result(
        self,
        node: ModelNode,
        affected_scheme_ids: tuple[str, ...],
        diff: CanonicalModelDiff,
    ) -> NodeMutationResult:
        return NodeMutationResult(
            node=node,
            affected_scheme_ids=affected_scheme_ids,
            semantic_revision=node.semantic_revision,
            layout_revision=node.layout_revision,
            technical_status=node.technical_status,
            diff=diff,
        )

    def create_node(
        self,
        node: ModelNode,
        *,
        transaction_id: str,
        actor_id: str,
    ) -> NodeMutationResult:
        occurred_at = self._clock()
        proposed = node.model_copy(
            update={
                "semantic_revision": 0,
                "layout_revision": 0,
                "created_at": occurred_at,
                "updated_at": occurred_at,
            }
        )
        before_nodes = self.repository.list_nodes()
        normalized, after_nodes = self._normalize_node(proposed, before_nodes)
        diff = _node_diff(
            None,
            normalized,
            before_nodes=before_nodes,
            after_nodes=after_nodes,
            mutation="create_node",
        )
        try:
            saved = self.repository.create_node(
                normalized,
                event_id=self._event_id(),
                actor_id=actor_id,
                transaction_id=transaction_id,
                occurred_at=occurred_at,
                diff=diff,
            )
        except CurrentObjectConflictError as error:
            try:
                current = self.repository.get_node(node.node_id)
            except CurrentObjectNotFoundError:
                raise CurrentModelMutationConflict(str(error)) from error
            raise CurrentModelRevisionConflict(
                str(error),
                current_node=current,
            ) from error
        return self._result(saved, (), diff)

    def update_node(
        self,
        node: ModelNode,
        *,
        expected_semantic_revision: int | None,
        expected_layout_revision: int | None,
        transaction_id: str,
        actor_id: str,
    ) -> NodeMutationResult:
        current = self.repository.get_node(node.node_id)
        if current.lifecycle is ModelObjectLifecycle.ARCHIVED:
            raise CurrentModelMutationConflict("archived nodes cannot be edited")
        if expected_semantic_revision is None and expected_layout_revision is None:
            raise CurrentModelMutationConflict("a node update requires an expected revision")

        # Each revision channel owns its fields.  A stale copy submitted for a
        # layout-only move therefore cannot overwrite newer semantic content.
        if expected_semantic_revision is None:
            channel_proposal = current.model_copy(update={"global_layout": node.global_layout})
        elif expected_layout_revision is None:
            channel_proposal = node.model_copy(update={"global_layout": current.global_layout})
        else:
            channel_proposal = node

        before_nodes = self.repository.list_nodes()
        if expected_semantic_revision is None:
            normalized = rehash_model_node(channel_proposal)
            after_nodes = _replace_node(before_nodes, normalized)
        else:
            normalized, after_nodes = self._normalize_node(channel_proposal, before_nodes)
        diff = _node_diff(
            current,
            normalized,
            before_nodes=before_nodes,
            after_nodes=after_nodes,
            mutation="update_node",
        )
        occurred_at = self._clock()
        try:
            with self.repository.database.transaction():
                saved = self.repository.update_node(
                    normalized,
                    expected_semantic_revision=expected_semantic_revision,
                    expected_layout_revision=expected_layout_revision,
                    event_id=self._event_id(),
                    actor_id=actor_id,
                    transaction_id=transaction_id,
                    occurred_at=occurred_at,
                    diff=diff,
                    join_existing=True,
                )
                affected = (
                    ()
                    if expected_semantic_revision is None
                    else self._revalidate_affected_schemes(
                        node.node_id,
                        nodes=_replace_node(before_nodes, saved),
                        transaction_id=transaction_id,
                        actor_id=actor_id,
                        occurred_at=occurred_at,
                    )
                )
        except CurrentObjectConflictError as error:
            canonical = self.repository.get_node(node.node_id)
            raise CurrentModelRevisionConflict(
                str(error),
                current_node=canonical,
            ) from error
        return self._result(saved, affected, diff)

    def archive_node(
        self,
        node_id: str,
        *,
        expected_semantic_revision: int,
        transaction_id: str,
        actor_id: str,
    ) -> NodeMutationResult:
        self.repository.get_node(node_id)
        active_scheme_ids = tuple(
            scheme.scheme_id for scheme in self._affected_active_schemes(node_id)
        )
        if active_scheme_ids:
            raise CurrentModelArchiveConflict(
                node_id,
                active_scheme_ids=active_scheme_ids,
            )
        diff = CanonicalModelDiff(
            changed_paths=("/lifecycle",),
            added_node_ids=(),
            removed_node_ids=(node_id,),
            added_edge_ids=(),
            removed_edge_ids=tuple(
                edge.edge_id for edge in _child_edges(self.repository.list_nodes(), node_id)
            ),
            metadata={"mutation": "archive_node"},
        )
        try:
            saved = self.repository.archive_node(
                node_id,
                expected_semantic_revision=expected_semantic_revision,
                event_id=self._event_id(),
                actor_id=actor_id,
                transaction_id=transaction_id,
                occurred_at=self._clock(),
                diff=diff,
            )
        except CurrentObjectConflictError as error:
            canonical = self.repository.get_node(node_id)
            raise CurrentModelRevisionConflict(
                str(error),
                current_node=canonical,
            ) from error
        return self._result(saved, (), diff)

    def _travel_node(
        self,
        node_id: str,
        *,
        direction: str,
        expected_semantic_revision: int,
        expected_layout_revision: int,
        transaction_id: str,
        actor_id: str,
    ) -> NodeMutationResult:
        occurred_at = self._clock()
        try:
            with self.repository.database.transaction():
                if direction == "undo":
                    saved = self.repository.undo_node(
                        node_id,
                        expected_semantic_revision=expected_semantic_revision,
                        expected_layout_revision=expected_layout_revision,
                        event_id=self._event_id(),
                        actor_id=actor_id,
                        transaction_id=transaction_id,
                        occurred_at=occurred_at,
                        join_existing=True,
                    )
                else:
                    saved = self.repository.redo_node(
                        node_id,
                        expected_semantic_revision=expected_semantic_revision,
                        expected_layout_revision=expected_layout_revision,
                        event_id=self._event_id(),
                        actor_id=actor_id,
                        transaction_id=transaction_id,
                        occurred_at=occurred_at,
                        join_existing=True,
                    )
                affected = self._revalidate_affected_schemes(
                    node_id,
                    nodes=_replace_node(self.repository.list_nodes(), saved),
                    transaction_id=transaction_id,
                    actor_id=actor_id,
                    occurred_at=occurred_at,
                )
                diff = self.repository.node_history(node_id)[-1].diff
        except CurrentObjectConflictError as error:
            canonical = self.repository.get_node(node_id)
            raise CurrentModelRevisionConflict(
                str(error),
                current_node=canonical,
            ) from error
        return self._result(saved, affected, diff)

    def undo_node(
        self,
        node_id: str,
        *,
        expected_semantic_revision: int,
        expected_layout_revision: int,
        transaction_id: str,
        actor_id: str,
    ) -> NodeMutationResult:
        return self._travel_node(
            node_id,
            direction="undo",
            expected_semantic_revision=expected_semantic_revision,
            expected_layout_revision=expected_layout_revision,
            transaction_id=transaction_id,
            actor_id=actor_id,
        )

    def redo_node(
        self,
        node_id: str,
        *,
        expected_semantic_revision: int,
        expected_layout_revision: int,
        transaction_id: str,
        actor_id: str,
    ) -> NodeMutationResult:
        return self._travel_node(
            node_id,
            direction="redo",
            expected_semantic_revision=expected_semantic_revision,
            expected_layout_revision=expected_layout_revision,
            transaction_id=transaction_id,
            actor_id=actor_id,
        )

    def _scheme_diff(
        self,
        before: TaskScheme | None,
        after: TaskScheme,
        *,
        mutation: str,
        copied_from_scheme_id: str | None = None,
    ) -> CanonicalModelDiff:
        metadata: dict[str, str] = {"mutation": mutation}
        if copied_from_scheme_id is not None:
            metadata["copied_from_scheme_id"] = copied_from_scheme_id
        return CanonicalModelDiff(
            changed_paths=(
                (f"/schemes/{after.scheme_id}",)
                if before is None
                else _canonical_scheme_changed_paths(before, after)
            ),
            added_node_ids=(),
            removed_node_ids=(),
            added_edge_ids=(),
            removed_edge_ids=(),
            metadata=metadata,
        )

    def _scheme_result(
        self,
        scheme: TaskScheme,
        diff: CanonicalModelDiff,
    ) -> SchemeMutationResult:
        return SchemeMutationResult(
            scheme=scheme,
            graph=self._graph_snapshot(scheme),
            semantic_revision=scheme.semantic_revision,
            layout_revision=scheme.layout_revision,
            technical_status=scheme.technical_status,
            diff=diff,
        )

    def _create_scheme(
        self,
        scheme: TaskScheme,
        *,
        transaction_id: str,
        actor_id: str,
        mutation: str,
        copied_from_scheme_id: str | None = None,
    ) -> SchemeMutationResult:
        occurred_at = self._clock()
        proposed = scheme.model_copy(
            update={
                "semantic_revision": 0,
                "layout_revision": 0,
                "created_at": occurred_at,
                "updated_at": occurred_at,
            }
        )
        normalized = rehash_task_scheme(
            self._normalize_scheme(proposed, self.repository.list_nodes())
        )
        diff = self._scheme_diff(
            None,
            normalized,
            mutation=mutation,
            copied_from_scheme_id=copied_from_scheme_id,
        )
        try:
            saved = self.repository.create_scheme(
                normalized,
                event_id=self._event_id(),
                actor_id=actor_id,
                transaction_id=transaction_id,
                occurred_at=occurred_at,
                diff=diff,
            )
        except CurrentObjectConflictError as error:
            try:
                current = self.repository.get_scheme(scheme.scheme_id)
            except CurrentObjectNotFoundError:
                raise CurrentModelMutationConflict(str(error)) from error
            raise CurrentSchemeRevisionConflict(
                str(error),
                current_scheme=current,
            ) from error
        return self._scheme_result(saved, diff)

    def create_scheme(
        self,
        scheme: TaskScheme,
        *,
        transaction_id: str,
        actor_id: str,
    ) -> SchemeMutationResult:
        return self._create_scheme(
            scheme,
            transaction_id=transaction_id,
            actor_id=actor_id,
            mutation="create_scheme",
        )

    def copy_scheme(
        self,
        source_scheme_id: str,
        *,
        new_scheme_id: str,
        name_zh: str | None,
        name_en: str | None,
        transaction_id: str,
        actor_id: str,
    ) -> SchemeMutationResult:
        source = self.repository.get_scheme(source_scheme_id)
        copy = source.model_copy(
            update={
                "scheme_id": new_scheme_id,
                "name_zh": source.name_zh if name_zh is None else name_zh,
                "name_en": source.name_en if name_en is None else name_en,
                "lifecycle": ModelObjectLifecycle.ACTIVE,
                "copied_from_scheme_id": source.scheme_id,
            }
        )
        return self._create_scheme(
            copy,
            transaction_id=transaction_id,
            actor_id=actor_id,
            mutation="copy_scheme",
            copied_from_scheme_id=source.scheme_id,
        )

    def update_scheme(
        self,
        scheme: TaskScheme,
        *,
        expected_semantic_revision: int | None,
        expected_layout_revision: int | None,
        transaction_id: str,
        actor_id: str,
    ) -> SchemeMutationResult:
        current = self.repository.get_scheme(scheme.scheme_id)
        if current.lifecycle is ModelObjectLifecycle.ARCHIVED:
            raise CurrentModelMutationConflict("archived task schemes cannot be edited")
        if expected_semantic_revision is None and expected_layout_revision is None:
            raise CurrentModelMutationConflict("a scheme update requires an expected revision")
        if expected_semantic_revision is None:
            channel_proposal = current.model_copy(
                update={"layout_overrides": scheme.layout_overrides}
            )
        elif expected_layout_revision is None:
            channel_proposal = scheme.model_copy(
                update={"layout_overrides": current.layout_overrides}
            )
        else:
            channel_proposal = scheme
        normalized = (
            rehash_task_scheme(channel_proposal)
            if expected_semantic_revision is None
            else rehash_task_scheme(
                self._normalize_scheme(channel_proposal, self.repository.list_nodes())
            )
        )
        diff = self._scheme_diff(current, normalized, mutation="update_scheme")
        try:
            saved = self.repository.update_scheme(
                normalized,
                expected_semantic_revision=expected_semantic_revision,
                expected_layout_revision=expected_layout_revision,
                event_id=self._event_id(),
                actor_id=actor_id,
                transaction_id=transaction_id,
                occurred_at=self._clock(),
                diff=diff,
            )
        except CurrentObjectConflictError as error:
            canonical = self.repository.get_scheme(scheme.scheme_id)
            raise CurrentSchemeRevisionConflict(
                str(error),
                current_scheme=canonical,
            ) from error
        return self._scheme_result(saved, diff)

    def archive_scheme(
        self,
        scheme_id: str,
        *,
        expected_semantic_revision: int,
        transaction_id: str,
        actor_id: str,
    ) -> SchemeMutationResult:
        self.repository.get_scheme(scheme_id)
        diff = CanonicalModelDiff(
            changed_paths=("/lifecycle",),
            added_node_ids=(),
            removed_node_ids=(),
            added_edge_ids=(),
            removed_edge_ids=(),
            metadata={"mutation": "archive_scheme"},
        )
        try:
            saved = self.repository.archive_scheme(
                scheme_id,
                expected_semantic_revision=expected_semantic_revision,
                event_id=self._event_id(),
                actor_id=actor_id,
                transaction_id=transaction_id,
                occurred_at=self._clock(),
                diff=diff,
            )
        except CurrentObjectConflictError as error:
            canonical = self.repository.get_scheme(scheme_id)
            raise CurrentSchemeRevisionConflict(
                str(error),
                current_scheme=canonical,
            ) from error
        return self._scheme_result(saved, diff)

    def _travel_scheme(
        self,
        scheme_id: str,
        *,
        direction: str,
        expected_semantic_revision: int,
        expected_layout_revision: int,
        transaction_id: str,
        actor_id: str,
    ) -> SchemeMutationResult:
        occurred_at = self._clock()
        try:
            if direction == "undo":
                saved = self.repository.undo_scheme(
                    scheme_id,
                    expected_semantic_revision=expected_semantic_revision,
                    expected_layout_revision=expected_layout_revision,
                    event_id=self._event_id(),
                    actor_id=actor_id,
                    transaction_id=transaction_id,
                    occurred_at=occurred_at,
                )
            else:
                saved = self.repository.redo_scheme(
                    scheme_id,
                    expected_semantic_revision=expected_semantic_revision,
                    expected_layout_revision=expected_layout_revision,
                    event_id=self._event_id(),
                    actor_id=actor_id,
                    transaction_id=transaction_id,
                    occurred_at=occurred_at,
                )
            diff = self.repository.scheme_history(scheme_id)[-1].diff
        except CurrentObjectConflictError as error:
            canonical = self.repository.get_scheme(scheme_id)
            raise CurrentSchemeRevisionConflict(
                str(error),
                current_scheme=canonical,
            ) from error
        return self._scheme_result(saved, diff)

    def undo_scheme(
        self,
        scheme_id: str,
        *,
        expected_semantic_revision: int,
        expected_layout_revision: int,
        transaction_id: str,
        actor_id: str,
    ) -> SchemeMutationResult:
        return self._travel_scheme(
            scheme_id,
            direction="undo",
            expected_semantic_revision=expected_semantic_revision,
            expected_layout_revision=expected_layout_revision,
            transaction_id=transaction_id,
            actor_id=actor_id,
        )

    def redo_scheme(
        self,
        scheme_id: str,
        *,
        expected_semantic_revision: int,
        expected_layout_revision: int,
        transaction_id: str,
        actor_id: str,
    ) -> SchemeMutationResult:
        return self._travel_scheme(
            scheme_id,
            direction="redo",
            expected_semantic_revision=expected_semantic_revision,
            expected_layout_revision=expected_layout_revision,
            transaction_id=transaction_id,
            actor_id=actor_id,
        )


__all__ = [
    "CurrentModelArchiveConflict",
    "CurrentModelMutationConflict",
    "CurrentModelRevisionConflict",
    "CurrentModelServiceError",
    "CurrentModelWorkspaceService",
    "CurrentSchemeRevisionConflict",
    "NodeMutationResult",
    "NodeUsage",
    "SchemeMutationResult",
]
