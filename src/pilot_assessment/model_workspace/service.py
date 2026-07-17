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

from pilot_assessment.bayesian.validation import CptValidationOutcome
from pilot_assessment.contracts.evidence_recipe import EvidenceRecipe
from pilot_assessment.contracts.model_components import CptMode, VariableState
from pilot_assessment.contracts.model_workspace import (
    BnNodeDefinition,
    CanonicalModelDiff,
    DeactivationImpact,
    EvidenceDataBinding,
    EvidenceNodeDefinition,
    ModelChangeEvent,
    ModelDiagnostic,
    ModelDiagnosticSeverity,
    ModelGraphEdge,
    ModelGraphSnapshot,
    ModelNode,
    ModelNodeKind,
    ModelNodeRef,
    ModelObjectLifecycle,
    ModelTechnicalStatus,
    NodeLayout,
    RawInputNodeDefinition,
    TaskScheme,
)
from pilot_assessment.evidence.registry import OperatorRegistry
from pilot_assessment.model_library.sources import SourceCatalog
from pilot_assessment.model_workspace.activation import (
    ActivationPlanningError,
    plan_activation,
    plan_deactivation,
)
from pilot_assessment.model_workspace.cpt import (
    CptEditorState,
    CurrentCptError,
    add_parent_to_cpt,
    editor_state,
    invalidate_state_change_cpts,
    materialize_cpt,
    node_state_ids,
    remove_parent_from_cpt,
    reorder_cpt_parents,
    replace_definition_cpt,
    replace_definition_states,
    update_cpt_probabilities,
    validate_node_cpt,
)
from pilot_assessment.model_workspace.graph import (
    ModelGraphError,
    activation_closure,
    edge_activation,
    project_model_edges,
)
from pilot_assessment.model_workspace.hashing import (
    model_graph_semantic_hash,
    rehash_model_node,
    rehash_task_scheme,
)
from pilot_assessment.model_workspace.operations import (
    copy_complete_node,
    effective_scheme_layout,
    merge_scheme_layouts,
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


class CurrentActivationConflict(CurrentModelMutationConflict):
    """Raised when an activation intent cannot be represented safely."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CurrentDeactivationImpactConflict(CurrentModelMutationConflict):
    """Raised when a confirmation was computed from an older semantic graph."""

    def __init__(self, *, current_impact: DeactivationImpact) -> None:
        super().__init__("deactivation impact changed; preview and confirm again")
        self.current_impact = current_impact


class CurrentModelOperationError(CurrentModelMutationConflict):
    """Stable typed graph/CPT operation failure before canonical state is written."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


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


@dataclass(frozen=True, slots=True)
class GraphBatchResult:
    """One atomic current-scheme graph intent and its canonical reconciliation state."""

    copied_nodes: tuple[ModelNode, ...]
    scheme: TaskScheme
    graph: ModelGraphSnapshot
    diff: CanonicalModelDiff


@dataclass(frozen=True, slots=True)
class CptMutationResult:
    node: ModelNode
    affected_scheme_ids: tuple[str, ...]
    semantic_revision: int
    editor: CptEditorState
    diff: CanonicalModelDiff


@dataclass(frozen=True, slots=True)
class StateMutationResult:
    nodes: tuple[ModelNode, ...]
    affected_scheme_ids: tuple[str, ...]
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
        node_id_factory: Callable[[ModelNodeKind], str] | None = None,
    ) -> None:
        self.repository = repository
        self.project_id = project_id
        self.operator_registry = operator_registry
        self.source_catalog = source_catalog
        self._clock = clock
        self._event_id_factory = event_id_factory or (lambda: f"model-event.{uuid4().hex}")
        self._node_id_factory = node_id_factory or (
            lambda kind: f"model-node.{kind.value}.{uuid4().hex}"
        )

    @property
    def available_source_ids(self) -> frozenset[str]:
        return frozenset(descriptor.source_id for descriptor in self.source_catalog.descriptors())

    def _event_id(self) -> str:
        return self._event_id_factory()

    def _new_node_id(self, node_kind: ModelNodeKind) -> str:
        return self._node_id_factory(node_kind)

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
        return self._affected_active_schemes_for_nodes((node_id,))

    def _affected_active_schemes_for_nodes(
        self,
        node_ids: tuple[str, ...],
    ) -> tuple[TaskScheme, ...]:
        selected = set(node_ids)
        return tuple(
            scheme
            for scheme in self.repository.list_schemes(lifecycle=ModelObjectLifecycle.ACTIVE)
            if selected.intersection(scheme.computed_active_closure)
            or selected.intersection(scheme.explicit_active_node_ids)
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
        return self._revalidate_schemes_for_nodes(
            (node_id,),
            nodes=nodes,
            transaction_id=transaction_id,
            actor_id=actor_id,
            occurred_at=occurred_at,
        )

    def _revalidate_schemes_for_nodes(
        self,
        node_ids: tuple[str, ...],
        *,
        nodes: tuple[ModelNode, ...],
        transaction_id: str,
        actor_id: str,
        occurred_at: datetime,
    ) -> tuple[str, ...]:
        affected = self._affected_active_schemes_for_nodes(node_ids)
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
                        "changed_node_ids": list(node_ids),
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
                join_existing=True,
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

    def copy_node(
        self,
        source_node_id: str,
        *,
        transaction_id: str,
        actor_id: str,
        offset_x: float = 40.0,
        offset_y: float = 40.0,
    ) -> NodeMutationResult:
        source = self.repository.get_node(source_node_id)
        occurred_at = self._clock()
        copied = copy_complete_node(
            source,
            new_node_id=self._new_node_id(source.node_kind),
            offset_x=offset_x,
            offset_y=offset_y,
        ).model_copy(
            update={
                "created_at": occurred_at,
                "updated_at": occurred_at,
            }
        )
        before_nodes = self.repository.list_nodes()
        normalized, after_nodes = self._normalize_node(copied, before_nodes)
        diff = _node_diff(
            None,
            normalized,
            before_nodes=before_nodes,
            after_nodes=after_nodes,
            mutation="copy_node",
        ).model_copy(
            update={
                "metadata": {
                    "mutation": "copy_node",
                    "copied_from_node_id": source_node_id,
                }
            }
        )
        try:
            saved = self.repository.create_node(
                normalized,
                event_id=self._event_id(),
                actor_id=actor_id,
                transaction_id=transaction_id,
                occurred_at=occurred_at,
                diff=diff,
                join_existing=True,
            )
        except CurrentObjectConflictError as error:
            raise CurrentModelMutationConflict(str(error)) from error
        return self._result(saved, (), diff)

    def _validate_operation_candidate(
        self,
        candidate: ModelNode,
        *,
        allow_incomplete_cpt: bool,
    ) -> None:
        normalized, _ = self._normalize_node(candidate, self.repository.list_nodes())
        errors = tuple(
            diagnostic
            for diagnostic in normalized.diagnostics
            if diagnostic.severity is ModelDiagnosticSeverity.ERROR
            and (
                diagnostic.location.startswith(f"/nodes/{candidate.node_id}")
                or not diagnostic.location.startswith("/nodes/")
            )
        )
        if not errors:
            return
        if allow_incomplete_cpt and all(
            diagnostic.code == "model.cpt_incomplete" for diagnostic in errors
        ):
            return
        first = errors[0]
        raise CurrentModelOperationError(first.code, first.message)

    def _save_node_operation(
        self,
        candidate: ModelNode,
        *,
        expected_semantic_revision: int,
        transaction_id: str,
        actor_id: str,
        allow_incomplete_cpt: bool = False,
    ) -> NodeMutationResult:
        try:
            canonical_candidate = ModelNode.model_validate(candidate.model_dump(mode="json"))
        except ValueError as error:
            raise CurrentModelOperationError(
                "model.operation_contract_invalid",
                str(error),
            ) from error
        self._validate_operation_candidate(
            canonical_candidate,
            allow_incomplete_cpt=allow_incomplete_cpt,
        )
        return self.update_node(
            canonical_candidate,
            expected_semantic_revision=expected_semantic_revision,
            expected_layout_revision=None,
            transaction_id=transaction_id,
            actor_id=actor_id,
        )

    def _cpt_result(self, result: NodeMutationResult) -> CptMutationResult:
        return CptMutationResult(
            node=result.node,
            affected_scheme_ids=result.affected_scheme_ids,
            semantic_revision=result.semantic_revision,
            editor=editor_state(result.node, self.repository.list_nodes()),
            diff=result.diff,
        )

    def validate_current_cpt(self, node_id: str) -> CptValidationOutcome:
        node = self.repository.get_node(node_id)
        return validate_node_cpt(node, self.repository.list_nodes())

    def current_cpt_editor(self, node_id: str) -> CptEditorState:
        node = self.repository.get_node(node_id)
        return editor_state(node, self.repository.list_nodes())

    def update_cpt_rows(
        self,
        node_id: str,
        rows: tuple[tuple[float, ...], ...],
        *,
        expected_semantic_revision: int,
        transaction_id: str,
        actor_id: str,
    ) -> CptMutationResult:
        node = self.repository.get_node(node_id)
        definition = node.definition
        if not isinstance(definition, (EvidenceNodeDefinition, BnNodeDefinition)):
            raise CurrentModelOperationError(
                "model.cpt_raw_input_forbidden",
                "Raw Input nodes do not have a CPT",
            )
        try:
            cpt = update_cpt_probabilities(definition.cpt, rows)
        except CurrentCptError as error:
            raise CurrentModelOperationError("model.cpt_update_invalid", str(error)) from error
        result = self._save_node_operation(
            replace_definition_cpt(node, cpt),
            expected_semantic_revision=expected_semantic_revision,
            transaction_id=transaction_id,
            actor_id=actor_id,
        )
        return self._cpt_result(result)

    def materialize_current_cpt(
        self,
        node_id: str,
        *,
        strategy: str,
        weights: tuple[float, ...] | None = None,
        weakest_link_strength: float = 0.0,
        sigma: float = 0.8,
        expected_semantic_revision: int,
        transaction_id: str,
        actor_id: str,
    ) -> CptMutationResult:
        node = self.repository.get_node(node_id)
        definition = node.definition
        if not isinstance(definition, (EvidenceNodeDefinition, BnNodeDefinition)):
            raise CurrentModelOperationError(
                "model.cpt_raw_input_forbidden",
                "Raw Input nodes do not have a CPT",
            )
        try:
            cpt = materialize_cpt(
                definition.cpt,
                strategy=strategy,
                weights=weights,
                weakest_link_strength=weakest_link_strength,
                sigma=sigma,
            )
        except CurrentCptError as error:
            raise CurrentModelOperationError(
                "model.cpt_materialization_invalid",
                str(error),
            ) from error
        result = self._save_node_operation(
            replace_definition_cpt(node, cpt),
            expected_semantic_revision=expected_semantic_revision,
            transaction_id=transaction_id,
            actor_id=actor_id,
        )
        return self._cpt_result(result)

    def add_probabilistic_edge(
        self,
        child_node_id: str,
        parent_node_id: str,
        *,
        strategy: str,
        expected_semantic_revision: int,
        transaction_id: str,
        actor_id: str,
    ) -> CptMutationResult:
        child = self.repository.get_node(child_node_id)
        parent = self.repository.get_node(parent_node_id)
        definition = child.definition
        if not isinstance(definition, (EvidenceNodeDefinition, BnNodeDefinition)):
            raise CurrentModelOperationError(
                "model.probabilistic_child_kind_invalid",
                "probabilistic edge child must be Evidence or BN",
            )
        if parent.node_kind is ModelNodeKind.RAW_INPUT:
            raise CurrentModelOperationError(
                "model.probabilistic_parent_kind_invalid",
                "probabilistic parent cannot be Raw Input",
            )
        if (
            isinstance(definition, EvidenceNodeDefinition)
            and parent.node_kind is not ModelNodeKind.BN
        ):
            raise CurrentModelOperationError(
                "model.evidence_parent_kind_invalid",
                "Evidence probabilistic parents must be BN nodes",
            )
        parent_ref = ModelNodeRef(
            node_id=parent.node_id,
            node_kind=parent.node_kind,
        )
        if parent_ref in definition.ordered_probabilistic_parent_nodes:
            raise CurrentModelOperationError(
                "model.probabilistic_parent_duplicate",
                f"parent {parent_node_id!r} is already present",
            )
        try:
            cpt = add_parent_to_cpt(
                definition.cpt,
                parent_ref,
                node_state_ids(parent),
                strategy=strategy,
            )
        except CurrentCptError as error:
            raise CurrentModelOperationError(
                "model.cpt_parent_add_invalid",
                str(error),
            ) from error
        parents = (*definition.ordered_probabilistic_parent_nodes, parent_ref)
        candidate = child.model_copy(
            update={
                "definition": definition.model_copy(
                    update={
                        "ordered_probabilistic_parent_nodes": parents,
                        "cpt": cpt,
                    }
                )
            }
        )
        result = self._save_node_operation(
            candidate,
            expected_semantic_revision=expected_semantic_revision,
            transaction_id=transaction_id,
            actor_id=actor_id,
            allow_incomplete_cpt=strategy == "incomplete",
        )
        return self._cpt_result(result)

    def remove_probabilistic_edge(
        self,
        child_node_id: str,
        parent_node_id: str,
        *,
        strategy: str,
        marginal_weights: tuple[float, ...] | None = None,
        expected_semantic_revision: int,
        transaction_id: str,
        actor_id: str,
    ) -> CptMutationResult:
        child = self.repository.get_node(child_node_id)
        definition = child.definition
        if not isinstance(definition, (EvidenceNodeDefinition, BnNodeDefinition)):
            raise CurrentModelOperationError(
                "model.probabilistic_child_kind_invalid",
                "probabilistic edge child must be Evidence or BN",
            )
        parent_ref = next(
            (
                parent
                for parent in definition.ordered_probabilistic_parent_nodes
                if parent.node_id == parent_node_id
            ),
            None,
        )
        if parent_ref is None:
            raise CurrentModelOperationError(
                "model.probabilistic_parent_missing",
                f"parent {parent_node_id!r} is not present",
            )
        try:
            cpt = remove_parent_from_cpt(
                definition.cpt,
                parent_ref,
                strategy=strategy,
                marginal_weights=marginal_weights,
            )
        except CurrentCptError as error:
            raise CurrentModelOperationError(
                "model.cpt_parent_remove_invalid",
                str(error),
            ) from error
        parents = tuple(
            parent
            for parent in definition.ordered_probabilistic_parent_nodes
            if parent != parent_ref
        )
        candidate = child.model_copy(
            update={
                "definition": definition.model_copy(
                    update={
                        "ordered_probabilistic_parent_nodes": parents,
                        "cpt": cpt,
                    }
                )
            }
        )
        result = self._save_node_operation(
            candidate,
            expected_semantic_revision=expected_semantic_revision,
            transaction_id=transaction_id,
            actor_id=actor_id,
            allow_incomplete_cpt=strategy == "incomplete",
        )
        return self._cpt_result(result)

    def reorder_probabilistic_parents(
        self,
        child_node_id: str,
        ordered_parent_node_ids: tuple[str, ...],
        *,
        expected_semantic_revision: int,
        transaction_id: str,
        actor_id: str,
    ) -> CptMutationResult:
        child = self.repository.get_node(child_node_id)
        definition = child.definition
        if not isinstance(definition, (EvidenceNodeDefinition, BnNodeDefinition)):
            raise CurrentModelOperationError(
                "model.probabilistic_child_kind_invalid",
                "probabilistic edge child must be Evidence or BN",
            )
        parent_by_id = {
            parent.node_id: parent for parent in definition.ordered_probabilistic_parent_nodes
        }
        try:
            parents = tuple(parent_by_id[node_id] for node_id in ordered_parent_node_ids)
            cpt = reorder_cpt_parents(definition.cpt, parents)
        except (KeyError, CurrentCptError) as error:
            raise CurrentModelOperationError(
                "model.cpt_parent_reorder_invalid",
                str(error),
            ) from error
        candidate = child.model_copy(
            update={
                "definition": definition.model_copy(
                    update={
                        "ordered_probabilistic_parent_nodes": parents,
                        "cpt": cpt,
                    }
                )
            }
        )
        result = self._save_node_operation(
            candidate,
            expected_semantic_revision=expected_semantic_revision,
            transaction_id=transaction_id,
            actor_id=actor_id,
            allow_incomplete_cpt=cpt.mode is CptMode.INCOMPLETE,
        )
        return self._cpt_result(result)

    def add_extraction_edge(
        self,
        evidence_node_id: str,
        raw_input_node_id: str,
        recipe_input_binding_id: str,
        updated_recipe: EvidenceRecipe,
        *,
        expected_semantic_revision: int,
        transaction_id: str,
        actor_id: str,
    ) -> NodeMutationResult:
        evidence = self.repository.get_node(evidence_node_id)
        raw = self.repository.get_node(raw_input_node_id)
        definition = evidence.definition
        raw_definition = raw.definition
        if not isinstance(definition, EvidenceNodeDefinition) or not isinstance(
            raw_definition, RawInputNodeDefinition
        ):
            raise CurrentModelOperationError(
                "model.extraction_edge_kind_invalid",
                "extraction edge must connect Raw Input to Evidence",
            )
        if updated_recipe.recipe_id != definition.recipe.recipe_id:
            raise CurrentModelOperationError(
                "model.recipe_identity_changed",
                "edge editing cannot replace the Evidence recipe identity",
            )
        existing_ids = {item.binding_id for item in definition.recipe.inputs}
        new_ids = {item.binding_id for item in updated_recipe.inputs}
        if recipe_input_binding_id in existing_ids or new_ids != (
            existing_ids | {recipe_input_binding_id}
        ):
            raise CurrentModelOperationError(
                "model.recipe_input_add_mismatch",
                "updated recipe must add exactly the requested input binding",
            )
        recipe_input = next(
            item for item in updated_recipe.inputs if item.binding_id == recipe_input_binding_id
        )
        if recipe_input.source_id != raw_definition.source_descriptor.source_id:
            raise CurrentModelOperationError(
                "model.recipe_source_binding_mismatch",
                "new recipe input source does not match the Raw Input descriptor",
            )
        binding_by_id = {item.recipe_input_binding_id: item for item in definition.data_bindings}
        binding_by_id[recipe_input_binding_id] = EvidenceDataBinding(
            recipe_input_binding_id=recipe_input_binding_id,
            raw_input_node=ModelNodeRef(
                node_id=raw.node_id,
                node_kind=ModelNodeKind.RAW_INPUT,
            ),
        )
        bindings = tuple(
            binding_by_id[recipe_input.binding_id] for recipe_input in updated_recipe.inputs
        )
        candidate = evidence.model_copy(
            update={
                "definition": definition.model_copy(
                    update={
                        "recipe": updated_recipe,
                        "data_bindings": bindings,
                    }
                )
            }
        )
        return self._save_node_operation(
            candidate,
            expected_semantic_revision=expected_semantic_revision,
            transaction_id=transaction_id,
            actor_id=actor_id,
        )

    def remove_extraction_edge(
        self,
        evidence_node_id: str,
        recipe_input_binding_id: str,
        updated_recipe: EvidenceRecipe,
        *,
        expected_semantic_revision: int,
        transaction_id: str,
        actor_id: str,
    ) -> NodeMutationResult:
        evidence = self.repository.get_node(evidence_node_id)
        definition = evidence.definition
        if not isinstance(definition, EvidenceNodeDefinition):
            raise CurrentModelOperationError(
                "model.extraction_edge_kind_invalid",
                "extraction edge child must be Evidence",
            )
        if updated_recipe.recipe_id != definition.recipe.recipe_id:
            raise CurrentModelOperationError(
                "model.recipe_identity_changed",
                "edge editing cannot replace the Evidence recipe identity",
            )
        existing_ids = {item.binding_id for item in definition.recipe.inputs}
        new_ids = {item.binding_id for item in updated_recipe.inputs}
        if recipe_input_binding_id not in existing_ids or new_ids != (
            existing_ids - {recipe_input_binding_id}
        ):
            raise CurrentModelOperationError(
                "model.recipe_input_remove_mismatch",
                "updated recipe must remove exactly the requested input binding",
            )
        binding_by_id = {
            item.recipe_input_binding_id: item
            for item in definition.data_bindings
            if item.recipe_input_binding_id != recipe_input_binding_id
        }
        bindings = tuple(
            binding_by_id[recipe_input.binding_id] for recipe_input in updated_recipe.inputs
        )
        candidate = evidence.model_copy(
            update={
                "definition": definition.model_copy(
                    update={
                        "recipe": updated_recipe,
                        "data_bindings": bindings,
                    }
                )
            }
        )
        return self._save_node_operation(
            candidate,
            expected_semantic_revision=expected_semantic_revision,
            transaction_id=transaction_id,
            actor_id=actor_id,
        )

    def replace_node_states(
        self,
        node_id: str,
        states: tuple[VariableState, ...],
        *,
        outcome: str,
        expected_semantic_revisions: dict[str, int],
        transaction_id: str,
        actor_id: str,
    ) -> StateMutationResult:
        if outcome != "mark_incomplete":
            raise CurrentModelOperationError(
                "model.state_outcome_unsupported",
                "state replacement requires explicit mark_incomplete in this operation",
            )
        before_nodes = self.repository.list_nodes()
        node_index = {node.node_id: node for node in before_nodes}
        target = node_index.get(node_id)
        if target is None:
            raise CurrentModelOperationError(
                "model.state_node_missing",
                f"state-edit node {node_id!r} does not resolve",
            )
        if target.node_kind is ModelNodeKind.RAW_INPUT:
            raise CurrentModelOperationError(
                "model.state_raw_input_forbidden",
                "Raw Input nodes do not have Bayesian states",
            )
        new_state_ids = tuple(state.state_id for state in states)
        try:
            migrated_cpts = invalidate_state_change_cpts(
                before_nodes,
                ModelNodeRef(node_id=node_id, node_kind=target.node_kind),
                new_state_ids,
            )
        except CurrentCptError as error:
            raise CurrentModelOperationError(
                "model.state_cpt_invalidation_failed",
                str(error),
            ) from error

        proposed_by_id: dict[str, ModelNode] = {}
        for node in before_nodes:
            definition = node.definition
            if not isinstance(definition, (EvidenceNodeDefinition, BnNodeDefinition)):
                continue
            migrated_cpt = migrated_cpts[node.node_id]
            if node.node_id == node_id:
                proposed = replace_definition_states(node, states, migrated_cpt)
            elif migrated_cpt != definition.cpt:
                proposed = replace_definition_cpt(node, migrated_cpt)
            else:
                continue
            try:
                proposed_by_id[node.node_id] = ModelNode.model_validate(
                    proposed.model_dump(mode="json")
                )
            except ValueError as error:
                raise CurrentModelOperationError(
                    "model.state_contract_invalid",
                    str(error),
                ) from error

        changed_ids = tuple(sorted(proposed_by_id))
        if set(expected_semantic_revisions) != set(changed_ids):
            raise CurrentModelOperationError(
                "model.state_revision_set_mismatch",
                "expected revisions must exactly cover changed child and dependent CPT nodes: "
                + ", ".join(changed_ids),
            )
        candidates = before_nodes
        for changed_id in changed_ids:
            candidates = _replace_node(
                candidates,
                rehash_model_node(proposed_by_id[changed_id]),
            )
        normalized_by_id: dict[str, ModelNode] = {}
        for changed_id in changed_ids:
            normalized, candidates = self._normalize_node(
                next(node for node in candidates if node.node_id == changed_id),
                candidates,
            )
            normalized_by_id[changed_id] = normalized

        diff = CanonicalModelDiff(
            changed_paths=tuple(f"/nodes/{changed_id}/definition" for changed_id in changed_ids),
            added_node_ids=(),
            removed_node_ids=(),
            added_edge_ids=(),
            removed_edge_ids=(),
            metadata={
                "mutation": "replace_node_states",
                "changed_node_id": node_id,
                "new_state_ids": list(new_state_ids),
                "cpt_outcome": outcome,
                "dependent_node_ids": [
                    changed_id for changed_id in changed_ids if changed_id != node_id
                ],
            },
        )
        occurred_at = self._clock()
        try:
            with self.repository.database.transaction(join_existing=True):
                saved_nodes = tuple(
                    self.repository.update_node(
                        normalized_by_id[changed_id],
                        expected_semantic_revision=expected_semantic_revisions[changed_id],
                        expected_layout_revision=None,
                        event_id=self._event_id(),
                        actor_id=actor_id,
                        transaction_id=transaction_id,
                        occurred_at=occurred_at,
                        diff=diff,
                        join_existing=True,
                    )
                    for changed_id in changed_ids
                )
                final_nodes = self.repository.list_nodes()
                affected = self._revalidate_schemes_for_nodes(
                    changed_ids,
                    nodes=final_nodes,
                    transaction_id=transaction_id,
                    actor_id=actor_id,
                    occurred_at=occurred_at,
                )
        except CurrentObjectConflictError as error:
            raise CurrentModelOperationError(
                "model.state_revision_conflict",
                str(error),
            ) from error
        return StateMutationResult(
            nodes=saved_nodes,
            affected_scheme_ids=affected,
            diff=diff,
        )

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
            with self.repository.database.transaction(join_existing=True):
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
                join_existing=True,
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
            with self.repository.database.transaction(join_existing=True):
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
                join_existing=True,
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

    @staticmethod
    def _require_scheme_semantic_revision(
        scheme: TaskScheme,
        expected_semantic_revision: int,
    ) -> None:
        if (
            type(expected_semantic_revision) is not int
            or expected_semantic_revision < 0
            or scheme.semantic_revision != expected_semantic_revision
        ):
            raise CurrentSchemeRevisionConflict(
                "task scheme semantic revision conflict",
                current_scheme=scheme,
            )

    @staticmethod
    def _require_scheme_layout_revision(
        scheme: TaskScheme,
        expected_layout_revision: int,
    ) -> None:
        if (
            type(expected_layout_revision) is not int
            or expected_layout_revision < 0
            or scheme.layout_revision != expected_layout_revision
        ):
            raise CurrentSchemeRevisionConflict(
                "task scheme layout revision conflict",
                current_scheme=scheme,
            )

    def apply_graph_batch(
        self,
        scheme_id: str,
        *,
        copy_node_ids: tuple[str, ...] = (),
        activate_node_ids: tuple[str, ...] = (),
        layout_updates: tuple[NodeLayout, ...] = (),
        expected_semantic_revision: int,
        expected_layout_revision: int,
        transaction_id: str,
        actor_id: str,
    ) -> GraphBatchResult:
        if len(copy_node_ids) != len(set(copy_node_ids)):
            raise CurrentModelMutationConflict("batch copy node IDs must be unique")
        if len(activate_node_ids) != len(set(activate_node_ids)):
            raise CurrentModelMutationConflict("batch activation node IDs must be unique")
        layout_ids = tuple(layout.node_id for layout in layout_updates)
        if len(layout_ids) != len(set(layout_ids)):
            raise CurrentModelMutationConflict("batch layout node IDs must be unique")
        if not copy_node_ids and not activate_node_ids and not layout_updates:
            raise CurrentModelMutationConflict("graph batch must contain at least one intent")

        occurred_at = self._clock()
        try:
            with self.repository.database.transaction(join_existing=True):
                scheme = self.repository.get_scheme(scheme_id)
                if scheme.lifecycle is ModelObjectLifecycle.ARCHIVED:
                    raise CurrentModelMutationConflict("archived task schemes cannot be edited")
                self._require_scheme_semantic_revision(
                    scheme,
                    expected_semantic_revision,
                )
                self._require_scheme_layout_revision(
                    scheme,
                    expected_layout_revision,
                )
                before_nodes = self.repository.list_nodes()
                before_index = {node.node_id: node for node in before_nodes}
                for node_id in (*copy_node_ids, *activate_node_ids, *layout_ids):
                    if node_id not in before_index:
                        raise CurrentActivationConflict(
                            "model.batch_node_missing",
                            f"batch node {node_id!r} does not resolve",
                        )

                candidates = before_nodes
                prepared_copies: list[tuple[str, ModelNode]] = []
                generated_ids: set[str] = set()
                for index, source_node_id in enumerate(copy_node_ids, start=1):
                    source = before_index[source_node_id]
                    new_node_id = self._new_node_id(source.node_kind)
                    if new_node_id in before_index or new_node_id in generated_ids:
                        raise CurrentModelMutationConflict(
                            f"generated node ID {new_node_id!r} already exists"
                        )
                    generated_ids.add(new_node_id)
                    copied = copy_complete_node(
                        source,
                        new_node_id=new_node_id,
                        offset_x=40.0 * index,
                        offset_y=40.0 * index,
                    ).model_copy(
                        update={
                            "created_at": occurred_at,
                            "updated_at": occurred_at,
                        }
                    )
                    normalized, candidates = self._normalize_node(copied, candidates)
                    prepared_copies.append((source_node_id, normalized))

                copied_ids = tuple(node.node_id for _, node in prepared_copies)
                explicit = tuple(
                    sorted(
                        set(scheme.explicit_active_node_ids)
                        | set(activate_node_ids)
                        | set(copied_ids)
                    )
                )
                try:
                    closure = activation_closure(candidates, explicit)
                except ModelGraphError as error:
                    raise CurrentActivationConflict(error.code, str(error)) from error
                candidate_index = {node.node_id: node for node in candidates}
                archived = tuple(
                    node_id
                    for node_id in closure
                    if candidate_index[node_id].lifecycle is ModelObjectLifecycle.ARCHIVED
                )
                if archived:
                    raise CurrentActivationConflict(
                        "model.activation_archived_node",
                        "activation closure contains archived nodes: " + ", ".join(archived),
                    )

                copy_layouts: list[NodeLayout] = []
                for index, (source_node_id, copied) in enumerate(
                    prepared_copies,
                    start=1,
                ):
                    source_layout = effective_scheme_layout(
                        scheme,
                        before_index[source_node_id],
                    )
                    copy_layouts.append(
                        NodeLayout(
                            node_id=copied.node_id,
                            x=source_layout.x + 40.0 * index,
                            y=source_layout.y + 40.0 * index,
                        )
                    )
                layouts = merge_scheme_layouts(
                    scheme,
                    (*copy_layouts, *layout_updates),
                )
                semantic_changed = (
                    explicit != scheme.explicit_active_node_ids
                    or closure != scheme.computed_active_closure
                )
                layout_changed = layouts != scheme.layout_overrides
                if not semantic_changed and not layout_changed:
                    raise CurrentModelMutationConflict("graph batch does not change state")

                normalized_scheme = rehash_task_scheme(
                    self._normalize_scheme(
                        scheme.model_copy(
                            update={
                                "explicit_active_node_ids": explicit,
                                "computed_active_closure": closure,
                                "layout_overrides": layouts,
                            }
                        ),
                        candidates,
                    )
                )
                before_active_edge_ids = {
                    edge.edge_id
                    for edge in edge_activation(
                        _all_resolvable_edges(before_nodes),
                        scheme.computed_active_closure,
                    ).active_edges
                }
                after_active_edge_ids = {
                    edge.edge_id
                    for edge in edge_activation(
                        _all_resolvable_edges(candidates),
                        closure,
                    ).active_edges
                }
                added_node_ids = tuple(
                    sorted(set(copied_ids) | (set(closure) - set(scheme.computed_active_closure)))
                )
                changed_paths = [
                    *(f"/nodes/{node_id}" for node_id in copied_ids),
                ]
                if semantic_changed:
                    changed_paths.extend(
                        (
                            "/explicit_active_node_ids",
                            "/computed_active_closure",
                        )
                    )
                if layout_changed:
                    changed_paths.append("/layout_overrides")
                diff = CanonicalModelDiff(
                    changed_paths=tuple(changed_paths),
                    added_node_ids=added_node_ids,
                    removed_node_ids=(),
                    added_edge_ids=tuple(sorted(after_active_edge_ids - before_active_edge_ids)),
                    removed_edge_ids=tuple(sorted(before_active_edge_ids - after_active_edge_ids)),
                    metadata={
                        "mutation": "graph_batch_apply",
                        "copied_nodes": [
                            {
                                "source_node_id": source_node_id,
                                "new_node_id": copied.node_id,
                            }
                            for source_node_id, copied in prepared_copies
                        ],
                        "requested_activation_node_ids": list(activate_node_ids),
                    },
                )

                saved_copies = tuple(
                    self.repository.create_node(
                        copied,
                        event_id=self._event_id(),
                        actor_id=actor_id,
                        transaction_id=transaction_id,
                        occurred_at=occurred_at,
                        diff=diff,
                        join_existing=True,
                    )
                    for _, copied in prepared_copies
                )
                saved_scheme = self.repository.update_scheme(
                    normalized_scheme,
                    expected_semantic_revision=(
                        expected_semantic_revision if semantic_changed else None
                    ),
                    expected_layout_revision=(expected_layout_revision if layout_changed else None),
                    event_id=self._event_id(),
                    actor_id=actor_id,
                    transaction_id=transaction_id,
                    occurred_at=occurred_at,
                    diff=diff,
                    join_existing=True,
                )
        except CurrentObjectConflictError as error:
            canonical = self.repository.get_scheme(scheme_id)
            raise CurrentSchemeRevisionConflict(
                str(error),
                current_scheme=canonical,
            ) from error
        return GraphBatchResult(
            copied_nodes=saved_copies,
            scheme=saved_scheme,
            graph=self._graph_snapshot(saved_scheme),
            diff=diff,
        )

    def copy_node_to_scheme(
        self,
        source_node_id: str,
        scheme_id: str,
        *,
        expected_semantic_revision: int,
        expected_layout_revision: int,
        transaction_id: str,
        actor_id: str,
    ) -> GraphBatchResult:
        return self.apply_graph_batch(
            scheme_id,
            copy_node_ids=(source_node_id,),
            expected_semantic_revision=expected_semantic_revision,
            expected_layout_revision=expected_layout_revision,
            transaction_id=transaction_id,
            actor_id=actor_id,
        )

    def activate_node(
        self,
        scheme_id: str,
        node_id: str,
        *,
        expected_semantic_revision: int,
        transaction_id: str,
        actor_id: str,
    ) -> SchemeMutationResult:
        occurred_at = self._clock()
        try:
            with self.repository.database.transaction(join_existing=True):
                scheme = self.repository.get_scheme(scheme_id)
                self._require_scheme_semantic_revision(
                    scheme,
                    expected_semantic_revision,
                )
                nodes = self.repository.list_nodes()
                edges = _all_resolvable_edges(nodes)
                try:
                    activation = plan_activation(scheme, nodes, edges, node_id)
                except ActivationPlanningError as error:
                    raise CurrentActivationConflict(error.code, str(error)) from error
                node_index = {node.node_id: node for node in nodes}
                archived = tuple(
                    closure_node_id
                    for closure_node_id in activation.computed_closure
                    if node_index[closure_node_id].lifecycle is ModelObjectLifecycle.ARCHIVED
                )
                if archived:
                    raise CurrentActivationConflict(
                        "model.activation_archived_node",
                        "activation closure contains archived nodes: " + ", ".join(archived),
                    )
                normalized = rehash_task_scheme(
                    self._normalize_scheme(
                        scheme.model_copy(
                            update={
                                "explicit_active_node_ids": activation.explicit_node_ids,
                                "computed_active_closure": activation.computed_closure,
                            }
                        ),
                        nodes,
                    )
                )
                diff = CanonicalModelDiff(
                    changed_paths=(
                        "/explicit_active_node_ids",
                        "/computed_active_closure",
                    ),
                    added_node_ids=activation.added_node_ids,
                    removed_node_ids=(),
                    added_edge_ids=activation.added_edge_ids,
                    removed_edge_ids=(),
                    metadata={
                        "mutation": "activate_node",
                        "requested_node_id": node_id,
                        "auto_enabled_parent_ids": list(activation.auto_enabled_parent_ids),
                    },
                )
                saved = self.repository.update_scheme(
                    normalized,
                    expected_semantic_revision=expected_semantic_revision,
                    expected_layout_revision=None,
                    event_id=self._event_id(),
                    actor_id=actor_id,
                    transaction_id=transaction_id,
                    occurred_at=occurred_at,
                    diff=diff,
                    join_existing=True,
                )
        except CurrentObjectConflictError as error:
            canonical = self.repository.get_scheme(scheme_id)
            raise CurrentSchemeRevisionConflict(
                str(error),
                current_scheme=canonical,
            ) from error
        return self._scheme_result(saved, diff)

    def preview_deactivation(
        self,
        scheme_id: str,
        node_id: str,
    ) -> DeactivationImpact:
        with self.repository.database.transaction(immediate=False):
            scheme = self.repository.get_scheme(scheme_id)
            nodes = self.repository.list_nodes()
            try:
                return plan_deactivation(
                    scheme,
                    nodes,
                    _all_resolvable_edges(nodes),
                    node_id,
                ).impact
            except ActivationPlanningError as error:
                raise CurrentActivationConflict(error.code, str(error)) from error

    def deactivate_node(
        self,
        scheme_id: str,
        node_id: str,
        *,
        expected_semantic_revision: int,
        impact_hash: str,
        transaction_id: str,
        actor_id: str,
    ) -> SchemeMutationResult:
        occurred_at = self._clock()
        try:
            with self.repository.database.transaction(join_existing=True):
                scheme = self.repository.get_scheme(scheme_id)
                self._require_scheme_semantic_revision(
                    scheme,
                    expected_semantic_revision,
                )
                nodes = self.repository.list_nodes()
                edges = _all_resolvable_edges(nodes)
                try:
                    deactivation = plan_deactivation(
                        scheme,
                        nodes,
                        edges,
                        node_id,
                    )
                except ActivationPlanningError as error:
                    raise CurrentActivationConflict(error.code, str(error)) from error
                if deactivation.impact.impact_hash != impact_hash:
                    raise CurrentDeactivationImpactConflict(current_impact=deactivation.impact)
                normalized = rehash_task_scheme(
                    self._normalize_scheme(
                        scheme.model_copy(
                            update={
                                "explicit_active_node_ids": (
                                    deactivation.remaining_explicit_node_ids
                                ),
                                "computed_active_closure": deactivation.computed_closure,
                                "output_node_ids": deactivation.remaining_output_node_ids,
                            }
                        ),
                        nodes,
                    )
                )
                changed_paths = [
                    "/explicit_active_node_ids",
                    "/computed_active_closure",
                ]
                if normalized.output_node_ids != scheme.output_node_ids:
                    changed_paths.append("/output_node_ids")
                diff = CanonicalModelDiff(
                    changed_paths=tuple(changed_paths),
                    added_node_ids=(),
                    removed_node_ids=deactivation.impact.impacted_node_ids,
                    added_edge_ids=(),
                    removed_edge_ids=deactivation.impact.impacted_edge_ids,
                    metadata={
                        "mutation": "deactivate_node",
                        "requested_node_id": node_id,
                        "confirmed_impact_hash": impact_hash,
                    },
                )
                saved = self.repository.update_scheme(
                    normalized,
                    expected_semantic_revision=expected_semantic_revision,
                    expected_layout_revision=None,
                    event_id=self._event_id(),
                    actor_id=actor_id,
                    transaction_id=transaction_id,
                    occurred_at=occurred_at,
                    diff=diff,
                    join_existing=True,
                )
        except CurrentObjectConflictError as error:
            canonical = self.repository.get_scheme(scheme_id)
            raise CurrentSchemeRevisionConflict(
                str(error),
                current_scheme=canonical,
            ) from error
        return self._scheme_result(saved, diff)

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
                join_existing=True,
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
                join_existing=True,
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
                    join_existing=True,
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
                    join_existing=True,
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
    "CptMutationResult",
    "CurrentActivationConflict",
    "CurrentDeactivationImpactConflict",
    "CurrentModelArchiveConflict",
    "CurrentModelMutationConflict",
    "CurrentModelOperationError",
    "CurrentModelRevisionConflict",
    "CurrentModelServiceError",
    "CurrentModelWorkspaceService",
    "CurrentSchemeRevisionConflict",
    "GraphBatchResult",
    "NodeMutationResult",
    "NodeUsage",
    "SchemeMutationResult",
    "StateMutationResult",
]
