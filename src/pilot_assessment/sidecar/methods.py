"""Thin JSON-RPC adapters over the durable M6 application and M5 domain services."""

from __future__ import annotations

import hashlib
import json
import math
import mimetypes
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from importlib.resources import files
from pathlib import Path
from typing import TypeAlias, cast

from pydantic import BaseModel, JsonValue, ValidationError

from pilot_assessment.contracts.assessment_scheme import AssessmentSchemeVersion
from pilot_assessment.contracts.bayesian import (
    BayesianDependencyEdge,
    ExtractionEdge,
    Observation,
)
from pilot_assessment.contracts.evidence_recipe import (
    EvidenceRecipe,
    RecipeInputBinding,
    RecipeScoring,
)
from pilot_assessment.contracts.model_components import (
    ComponentIdRef,
    ComponentKind,
    ComponentLifecycle,
    PinnedComponentRef,
    VariableState,
)
from pilot_assessment.contracts.project import AuditEvent
from pilot_assessment.contracts.run import RunPurpose, RunState
from pilot_assessment.evidence.registry import OperatorRegistryError
from pilot_assessment.model_library.repository import (
    ComponentHashMismatchError,
    ComponentLibraryError,
    LibraryItemNotFoundError,
    LibraryQuery,
)
from pilot_assessment.persistence.artifacts import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    ArtifactStoreError,
)
from pilot_assessment.persistence.audit import AuditQuery
from pilot_assessment.persistence.project import (
    ProjectAlreadyExistsError,
    ProjectError,
    ProjectFormatError,
    ProjectIntegrityError,
)
from pilot_assessment.persistence.sessions import (
    ManagedSessionChangedError,
    SessionImportError,
    SessionNotFoundError,
    SessionRevisionNotFoundError,
)
from pilot_assessment.persistence.transactions import (
    MutationResult,
    TransactionReuseMismatchError,
)
from pilot_assessment.runtime.application import ProjectApplication
from pilot_assessment.runtime.coordinator import RunCoordinatorError
from pilot_assessment.runtime.pipeline import RunResultNotFoundError
from pilot_assessment.runtime.preflight import (
    RunPreflightBlockedError,
    RunPreflightError,
    RunPreflightNotFoundError,
)
from pilot_assessment.runtime.repository import (
    RunAlreadyExistsError,
    RunNotFoundError,
    RunRepositoryError,
    RunTransitionError,
)
from pilot_assessment.schemes.operations import (
    AddBayesianDependency,
    AddExistingComponent,
    AddExtractionDependency,
    CloneComponentVersion,
    MoveLayoutNode,
    RemoveBayesianDependency,
    RemoveComponent,
    RemoveExtractionDependency,
    ReplaceBnStates,
    ReplaceCptProbabilities,
    ReplaceEvidenceRecipe,
    ReplaceEvidenceScoring,
    ReplaceReportingPolicyRules,
    SchemeOperation,
    SchemeOperationError,
    SetOutputNodes,
    StageNewComponentVersion,
)
from pilot_assessment.schemes.repository import (
    DraftHistoryBoundaryError,
    DraftRevisionConflictError,
    SchemeDraftAlreadyExistsError,
    SchemeDraftNotFoundError,
    SchemeDraftRepositoryError,
)
from pilot_assessment.schemes.service import SchemePublicationError
from pilot_assessment.sidecar.dispatcher import (
    DEFAULT_CAPABILITIES,
    JsonRpcDispatcher,
    RpcMethodHandler,
    RpcRequestContext,
)
from pilot_assessment.sidecar.errors import (
    DomainErrorCode,
    DomainRpcError,
    InvalidParamsFault,
    JsonRpcFault,
    JsonRpcMessage,
)

RpcResult: TypeAlias = dict[str, JsonValue]
RunNotificationSink: TypeAlias = Callable[[JsonRpcMessage], None]
Mutation = Callable[[], Mapping[str, JsonValue]]

_CONCEPT_KINDS = frozenset({ComponentKind.EVIDENCE_CONCEPT, ComponentKind.BN_NODE_CONCEPT})
_METHOD_NAMES = (
    "runtime.status",
    "runtime.shutdown",
    "capabilities.list",
    "schema.get",
    "project.create",
    "project.open",
    "project.get",
    "project.close",
    "session.inspect",
    "session.import",
    "session.list",
    "session.get",
    "session.artifact.get",
    "component.concept.list",
    "component.concept.get",
    "component.version.list",
    "component.version.get",
    "component.version.diff",
    "operator.catalog.list",
    "operator.definition.get",
    "scheme.version.list",
    "scheme.version.get",
    "scheme.version.diff",
    "scheme.draft.create",
    "scheme.draft.get",
    "scheme.draft.discard",
    "scheme.draft.publish",
    "graph.snapshot.get",
    "graph.operations.apply",
    "graph.undo",
    "graph.redo",
    "layout.update",
    "graph.validate",
    "run.preflight",
    "run.start",
    "run.preview",
    "run.status",
    "run.events.list",
    "run.cancel",
    "result.get",
    "result.artifact.get",
    "audit.events.list",
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _jsonable(value: object) -> JsonValue:
    if value is None or type(value) in {str, bool, int}:
        return cast(JsonValue, value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite values cannot cross JSON-RPC")
        return value
    if isinstance(value, Enum):
        return _jsonable(value.value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("transport datetime must be timezone-aware")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, BaseModel):
        return _jsonable(value.model_dump(mode="json"))
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _jsonable(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for key, nested in value.items():
            if type(key) is not str:
                raise ValueError("transport mapping keys must be strings")
            result[key] = _jsonable(nested)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_jsonable(nested) for nested in value]
    raise ValueError(f"unsupported transport value {type(value).__name__}")


def _json_object(value: object, label: str) -> RpcResult:
    payload = _jsonable(value)
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must serialize as a JSON object")
    return payload


def _required_str(params: Mapping[str, JsonValue], field: str) -> str:
    value = params.get(field)
    if type(value) is not str or not value:
        raise InvalidParamsFault(f"{field} must be a non-empty string", path=f"/{field}")
    return value


def _optional_str(params: Mapping[str, JsonValue], field: str) -> str | None:
    value = params.get(field)
    if value is None:
        return None
    if type(value) is not str or not value:
        raise InvalidParamsFault(f"{field} must be a non-empty string", path=f"/{field}")
    return value


def _required_int(params: Mapping[str, JsonValue], field: str) -> int:
    value = params.get(field)
    if type(value) is not int or value < 0:
        raise InvalidParamsFault(
            f"{field} must be a non-negative strict integer",
            path=f"/{field}",
        )
    return value


def _optional_int(
    params: Mapping[str, JsonValue],
    field: str,
    *,
    default: int,
) -> int:
    if field not in params:
        return default
    return _required_int(params, field)


def _optional_bool(
    params: Mapping[str, JsonValue],
    field: str,
    *,
    default: bool,
) -> bool:
    if field not in params:
        return default
    value = params[field]
    if type(value) is not bool:
        raise InvalidParamsFault(f"{field} must be a boolean", path=f"/{field}")
    return value


def _mapping(value: JsonValue | None, field: str) -> dict[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise InvalidParamsFault(f"{field} must be an object", path=f"/{field}")
    return cast(dict[str, JsonValue], dict(value))


def _list(value: JsonValue | None, field: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise InvalidParamsFault(f"{field} must be an array", path=f"/{field}")
    return value


def _number(value: JsonValue | None, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidParamsFault(f"{field} must be a finite number", path=f"/{field}")
    number = float(value)
    if not math.isfinite(number):
        raise InvalidParamsFault(f"{field} must be a finite number", path=f"/{field}")
    return number


def _component_kind(params: Mapping[str, JsonValue], field: str = "kind") -> ComponentKind:
    value = _required_str(params, field)
    try:
        return ComponentKind(value)
    except ValueError as error:
        raise InvalidParamsFault(f"unknown component kind {value!r}", path=f"/{field}") from error


def _operation(payload: JsonValue) -> SchemeOperation:
    data = _mapping(payload, "operations[]")
    operation_type = _required_str(data, "type")

    def graph() -> int:
        return _required_int(data, "expected_graph_version")

    def layout() -> int:
        return _required_int(data, "expected_layout_version")

    if operation_type == "clone_component_version":
        return CloneComponentVersion(
            expected_graph_version=graph(),
            source=ComponentIdRef.model_validate(_mapping(data.get("source"), "source")),
            candidate_id=_required_str(data, "candidate_id"),
            replace_source=_optional_bool(data, "replace_source", default=True),
        )
    if operation_type == "stage_new_component_version":
        return StageNewComponentVersion(
            expected_graph_version=graph(),
            kind=_component_kind(data),
            candidate_id=_required_str(data, "candidate_id"),
            payload=_mapping(data.get("payload"), "payload"),
        )
    if operation_type == "add_existing_component":
        return AddExistingComponent(
            expected_graph_version=graph(),
            reference=PinnedComponentRef.model_validate(
                _mapping(data.get("reference"), "reference")
            ),
        )
    if operation_type == "remove_component":
        return RemoveComponent(
            expected_graph_version=graph(),
            target=ComponentIdRef.model_validate(_mapping(data.get("target"), "target")),
        )
    if operation_type == "replace_evidence_recipe":
        return ReplaceEvidenceRecipe(
            expected_graph_version=graph(),
            candidate_id=_required_str(data, "candidate_id"),
            recipe=EvidenceRecipe.model_validate(_mapping(data.get("recipe"), "recipe")),
        )
    if operation_type == "replace_evidence_scoring":
        raw_scoring = data.get("scoring")
        return ReplaceEvidenceScoring(
            expected_graph_version=graph(),
            candidate_id=_required_str(data, "candidate_id"),
            scoring=(
                None
                if raw_scoring is None
                else RecipeScoring.model_validate(_mapping(raw_scoring, "scoring"))
            ),
        )
    if operation_type == "replace_bn_states":
        return ReplaceBnStates(
            expected_graph_version=graph(),
            candidate_id=_required_str(data, "candidate_id"),
            ordered_states=tuple(
                VariableState.model_validate(_mapping(item, "ordered_states[]"))
                for item in _list(data.get("ordered_states"), "ordered_states")
            ),
        )
    if operation_type == "replace_cpt_probabilities":
        rows = _list(data.get("probabilities"), "probabilities")
        return ReplaceCptProbabilities(
            expected_graph_version=graph(),
            candidate_id=_required_str(data, "candidate_id"),
            probabilities=tuple(
                tuple(_number(item, "probabilities[][]") for item in _list(row, "probabilities[]"))
                for row in rows
            ),
        )
    if operation_type == "replace_reporting_policy_rules":
        return ReplaceReportingPolicyRules(
            expected_graph_version=graph(),
            candidate_id=_required_str(data, "candidate_id"),
            applicability_rules=_mapping(data.get("applicability_rules"), "applicability_rules"),
            coverage_rules=_mapping(data.get("coverage_rules"), "coverage_rules"),
            output_rules=_mapping(data.get("output_rules"), "output_rules"),
        )
    if operation_type == "add_extraction_dependency":
        return AddExtractionDependency(
            expected_graph_version=graph(),
            edge=ExtractionEdge.model_validate(_mapping(data.get("edge"), "edge")),
            binding=RecipeInputBinding.model_validate(_mapping(data.get("binding"), "binding")),
        )
    if operation_type == "remove_extraction_dependency":
        return RemoveExtractionDependency(
            expected_graph_version=graph(),
            edge_id=_required_str(data, "edge_id"),
        )
    if operation_type == "add_bayesian_dependency":
        return AddBayesianDependency(
            expected_graph_version=graph(),
            edge=BayesianDependencyEdge.model_validate(_mapping(data.get("edge"), "edge")),
        )
    if operation_type == "remove_bayesian_dependency":
        return RemoveBayesianDependency(
            expected_graph_version=graph(),
            edge_id=_required_str(data, "edge_id"),
        )
    if operation_type == "set_output_nodes":
        return SetOutputNodes(
            expected_graph_version=graph(),
            output_node_ids=tuple(
                ComponentIdRef.model_validate(_mapping(item, "output_node_ids[]"))
                for item in _list(data.get("output_node_ids"), "output_node_ids")
            ),
        )
    if operation_type == "move_layout_node":
        return MoveLayoutNode(
            expected_layout_version=layout(),
            candidate_id=_required_str(data, "candidate_id"),
            node_id=_required_str(data, "node_id"),
            x=_number(data.get("x"), "x"),
            y=_number(data.get("y"), "y"),
        )
    raise InvalidParamsFault(f"unsupported operation type {operation_type!r}", path="/type")


def _diff_values(left: JsonValue, right: JsonValue, path: str = "") -> list[JsonValue]:
    if left == right:
        return []
    if isinstance(left, dict) and isinstance(right, dict):
        changes: list[JsonValue] = []
        for key in sorted(set(left) | set(right)):
            escaped = key.replace("~", "~0").replace("/", "~1")
            child = f"{path}/{escaped}"
            if key not in left:
                changes.append({"path": child, "left": None, "right": right[key]})
            elif key not in right:
                changes.append({"path": child, "left": left[key], "right": None})
            else:
                changes.extend(_diff_values(left[key], right[key], child))
        return changes
    if isinstance(left, list) and isinstance(right, list):
        changes = []
        for index in range(max(len(left), len(right))):
            child = f"{path}/{index}"
            if index >= len(left):
                changes.append({"path": child, "left": None, "right": right[index]})
            elif index >= len(right):
                changes.append({"path": child, "left": left[index], "right": None})
            else:
                changes.extend(_diff_values(left[index], right[index], child))
        return changes
    return [{"path": path or "/", "left": left, "right": right}]


class SidecarMethods:
    """Own one optional project and expose transport-only adapters for it."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = _utc_now,
        notification_sink: RunNotificationSink | None = None,
    ) -> None:
        self.clock = clock
        self.notification_sink = notification_sink
        self.application: ProjectApplication | None = None
        self.shutdown_requested = False

    @property
    def registered_methods(self) -> tuple[str, ...]:
        return _METHOD_NAMES

    def register(self, dispatcher: JsonRpcDispatcher) -> None:
        for method_name in _METHOD_NAMES:
            attribute = "_" + method_name.replace(".", "_")
            handler = cast(RpcMethodHandler, getattr(self, attribute))
            dispatcher.register(method_name, self._guard(handler))

    def close(self) -> None:
        if self.application is not None:
            self.application.close()
            self.application = None

    def _guard(self, handler: RpcMethodHandler) -> RpcMethodHandler:
        def guarded(
            params: dict[str, JsonValue],
            context: RpcRequestContext,
        ) -> Mapping[str, JsonValue]:
            try:
                return handler(params, context)
            except JsonRpcFault:
                raise
            except Exception as error:
                raise self._mapped_error(error, context) from error

        return guarded

    @staticmethod
    def _mapped_error(error: Exception, context: RpcRequestContext) -> JsonRpcFault:
        transaction_id = context.transaction_id
        if isinstance(error, TransactionReuseMismatchError):
            return DomainRpcError(
                DomainErrorCode.TRANSACTION_REUSE_MISMATCH,
                str(error),
                recoverable=False,
                transaction_id=transaction_id,
            )
        if isinstance(error, (SessionNotFoundError, SessionRevisionNotFoundError)):
            return DomainRpcError(
                DomainErrorCode.SESSION_NOT_FOUND,
                str(error),
                recoverable=True,
            )
        if isinstance(error, ManagedSessionChangedError):
            return DomainRpcError(
                DomainErrorCode.MANAGED_SESSION_CHANGED,
                str(error),
                recoverable=False,
            )
        if isinstance(error, SessionImportError):
            return DomainRpcError(
                DomainErrorCode.SESSION_IMPORT_INVALID,
                str(error),
                recoverable=True,
                transaction_id=transaction_id,
            )
        if isinstance(error, ArtifactNotFoundError):
            return DomainRpcError(
                DomainErrorCode.ARTIFACT_NOT_FOUND,
                str(error),
                recoverable=True,
            )
        if isinstance(error, (ArtifactIntegrityError, ComponentHashMismatchError)):
            return DomainRpcError(
                DomainErrorCode.ARTIFACT_INTEGRITY_FAILED,
                str(error),
                recoverable=False,
            )
        if isinstance(error, ArtifactStoreError):
            return DomainRpcError(
                DomainErrorCode.ARTIFACT_INTEGRITY_FAILED,
                str(error),
                recoverable=False,
            )
        if isinstance(error, SchemeDraftNotFoundError):
            return DomainRpcError(
                DomainErrorCode.DRAFT_NOT_FOUND,
                str(error),
                recoverable=True,
            )
        if isinstance(error, SchemeDraftAlreadyExistsError):
            return DomainRpcError(
                DomainErrorCode.DRAFT_ALREADY_EXISTS,
                str(error),
                recoverable=True,
                transaction_id=transaction_id,
            )
        if isinstance(error, DraftRevisionConflictError):
            code = (
                DomainErrorCode.LAYOUT_VERSION_CONFLICT
                if "layout" in str(error).lower() and "graph" not in str(error).lower()
                else DomainErrorCode.GRAPH_VERSION_CONFLICT
            )
            return DomainRpcError(
                code,
                str(error),
                recoverable=True,
                transaction_id=transaction_id,
            )
        if isinstance(error, DraftHistoryBoundaryError):
            return DomainRpcError(
                DomainErrorCode.GRAPH_VERSION_CONFLICT,
                str(error),
                recoverable=True,
                transaction_id=transaction_id,
            )
        if isinstance(error, SchemePublicationError):
            return DomainRpcError(
                DomainErrorCode.SCHEME_VALIDATION_FAILED,
                str(error),
                recoverable=True,
                transaction_id=transaction_id,
                diagnostics=_jsonable(error.diagnostics),
            )
        if isinstance(error, LibraryItemNotFoundError):
            return DomainRpcError(
                DomainErrorCode.COMPONENT_NOT_FOUND,
                str(error),
                recoverable=True,
            )
        if isinstance(error, OperatorRegistryError):
            return DomainRpcError(
                DomainErrorCode.OPERATOR_NOT_FOUND,
                str(error),
                recoverable=True,
            )
        if isinstance(error, RunPreflightNotFoundError):
            return DomainRpcError(
                DomainErrorCode.RUN_PREFLIGHT_FAILED,
                str(error),
                recoverable=True,
            )
        if isinstance(error, (RunPreflightBlockedError, RunPreflightError)):
            return DomainRpcError(
                DomainErrorCode.RUN_PREFLIGHT_FAILED,
                str(error),
                recoverable=True,
            )
        if isinstance(error, (RunNotFoundError, RunResultNotFoundError)):
            return DomainRpcError(
                DomainErrorCode.RUN_NOT_FOUND,
                str(error),
                recoverable=True,
            )
        if isinstance(error, RunTransitionError):
            return DomainRpcError(
                DomainErrorCode.RUN_ALREADY_TERMINAL,
                str(error),
                recoverable=True,
                transaction_id=transaction_id,
            )
        if isinstance(error, (RunAlreadyExistsError, RunCoordinatorError, RunRepositoryError)):
            return DomainRpcError(
                DomainErrorCode.RUN_CANCEL_REJECTED,
                str(error),
                recoverable=True,
                transaction_id=transaction_id,
            )
        if isinstance(error, ProjectAlreadyExistsError):
            return DomainRpcError(
                DomainErrorCode.PROJECT_ALREADY_EXISTS,
                str(error),
                recoverable=True,
                transaction_id=transaction_id,
            )
        if isinstance(error, ProjectFormatError):
            return DomainRpcError(
                DomainErrorCode.PROJECT_FORMAT_UNSUPPORTED,
                str(error),
                recoverable=False,
            )
        if isinstance(error, ProjectIntegrityError):
            return DomainRpcError(
                DomainErrorCode.PROJECT_RECOVERY_FAILED,
                str(error),
                recoverable=False,
            )
        if isinstance(error, ProjectError):
            return DomainRpcError(
                DomainErrorCode.PROJECT_RECOVERY_FAILED,
                str(error),
                recoverable=True,
            )
        if isinstance(
            error,
            (
                ValidationError,
                ComponentLibraryError,
                SchemeDraftRepositoryError,
                SchemeOperationError,
                TypeError,
                ValueError,
            ),
        ):
            return InvalidParamsFault(str(error))
        raise error

    def _app(self) -> ProjectApplication:
        if self.application is None or self.application.closed:
            raise DomainRpcError(
                DomainErrorCode.PROJECT_NOT_OPEN,
                "No assessment project is currently open",
                recoverable=True,
            )
        return self.application

    def _attach(self, application: ProjectApplication) -> None:
        self.application = application
        application.coordinator.notify = self._notify_run_event

    def _notify_run_event(self, event) -> None:
        if self.notification_sink is None:
            return
        method = {
            RunState.COMPLETED: "run.completed",
            RunState.FAILED: "run.failed",
            RunState.CANCELLED: "run.cancelled",
            RunState.INTERRUPTED: "run.interrupted",
        }.get(event.state, "run.progress")
        self.notification_sink(
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": _jsonable(event),
            }
        )

    def _mutate(
        self,
        app: ProjectApplication,
        method: str,
        params: dict[str, JsonValue],
        context: RpcRequestContext,
        *,
        subject_kind: str,
        subject_id: str,
        audit_details: Mapping[str, JsonValue],
        mutation: Mutation,
    ) -> RpcResult:
        transaction_id = _required_str(params, "transaction_id")
        actor = _required_str(params, "actor")
        if context.transaction_id != transaction_id:
            raise InvalidParamsFault("transaction_id context mismatch", path="/transaction_id")
        audit_digest = hashlib.sha256(f"{method}\0{transaction_id}".encode()).hexdigest()

        def apply(_connection: sqlite3.Connection) -> MutationResult:
            response = _json_object(mutation(), "mutation response")
            event = AuditEvent(
                audit_event_id=f"audit.{audit_digest[:32]}",
                event_type=method,
                actor_id=actor,
                occurred_at=self.clock(),
                subject_kind=subject_kind,
                subject_id=subject_id,
                transaction_id=transaction_id,
                details={"method": method, **dict(audit_details)},
            )
            return MutationResult(response_payload=response, audit_event=event)

        outcome = app.idempotency.execute(
            transaction_id=transaction_id,
            method=method,
            params=params,
            mutation=apply,
        )
        response = dict(outcome.receipt.response_payload or {})
        return {
            **response,
            "transaction_id": transaction_id,
            "audit_event_id": outcome.receipt.audit_event_id,
            "replayed": outcome.replayed,
        }

    def _runtime_status(self, _params, _context) -> RpcResult:
        app = self.application
        active_runs = []
        if app is not None and not app.closed:
            active_runs = [
                run.run_id
                for run in app.runs.list_runs()
                if run.state in {RunState.RUNNING, RunState.CANCELLING}
            ]
        return {
            "state": "busy" if active_runs else "ready",
            "project_open": app is not None and not app.closed,
            "project_id": None if app is None or app.closed else app.project.descriptor.project_id,
            "active_run_ids": active_runs,
        }

    def _runtime_shutdown(self, _params, _context) -> RpcResult:
        self.shutdown_requested = True
        return {"state": "stopping"}

    def _capabilities_list(self, _params, _context) -> RpcResult:
        return {
            "capabilities": list(DEFAULT_CAPABILITIES),
            "methods": ["runtime.hello", *_METHOD_NAMES],
            "max_parallel_assessment_runs": 1,
        }

    def _schema_get(self, params, _context) -> RpcResult:
        schema_id = _required_str(params, "schema_id")
        if any(separator in schema_id for separator in ("/", "\\", "..")):
            raise InvalidParamsFault("schema_id must be a packaged schema ID", path="/schema_id")
        resource_name = (
            schema_id if schema_id.endswith(".schema.json") else f"{schema_id}.schema.json"
        )
        resource = files("pilot_assessment.schema_resources").joinpath(resource_name)
        if not resource.is_file():
            raise InvalidParamsFault(f"schema {schema_id!r} is not packaged", path="/schema_id")
        schema = json.loads(resource.read_text(encoding="utf-8"))
        return {"schema_id": resource_name.removesuffix(".schema.json"), "schema": schema}

    def _project_create(self, params, context) -> RpcResult:
        _required_str(params, "transaction_id")
        _required_str(params, "actor")
        if context.transaction_id != params["transaction_id"]:
            raise InvalidParamsFault("transaction_id context mismatch", path="/transaction_id")
        root = Path(_required_str(params, "root")).expanduser().resolve()
        project_id = _required_str(params, "project_id")
        name = _required_str(params, "name")
        if self.application is None:
            application = (
                ProjectApplication.open(root, clock=self.clock)
                if (root / "project.json").is_file()
                else ProjectApplication.create(
                    root,
                    project_id=project_id,
                    name=name,
                    created_at=self.clock(),
                    clock=self.clock,
                )
            )
            if (
                application.project.descriptor.project_id != project_id
                or application.project.descriptor.name != name
            ):
                application.close()
                raise DomainRpcError(
                    DomainErrorCode.PROJECT_ALREADY_EXISTS,
                    "The existing project descriptor differs from the requested project",
                    recoverable=True,
                    transaction_id=context.transaction_id,
                )
            self._attach(application)
        app = self._app()
        if (
            app.project.root != root
            or app.project.descriptor.project_id != project_id
            or app.project.descriptor.name != name
        ):
            raise DomainRpcError(
                DomainErrorCode.PROJECT_ALREADY_OPEN,
                "Another project is already open or the existing descriptor differs",
                recoverable=True,
                transaction_id=context.transaction_id,
            )
        return self._mutate(
            app,
            "project.create",
            params,
            context,
            subject_kind="project",
            subject_id=project_id,
            audit_details={"project_id": project_id},
            mutation=lambda: {"project": _jsonable(app.project.descriptor)},
        )

    def _project_open(self, params, _context) -> RpcResult:
        root = Path(_required_str(params, "root")).expanduser().resolve()
        if self.application is not None and not self.application.closed:
            if self.application.project.root != root:
                raise DomainRpcError(
                    DomainErrorCode.PROJECT_ALREADY_OPEN,
                    "Close the current project before opening another",
                    recoverable=True,
                )
            return {"project": _jsonable(self.application.project.descriptor)}
        application = ProjectApplication.open(root, clock=self.clock)
        self._attach(application)
        return {
            "project": _jsonable(application.project.descriptor),
            "recovery": {
                "artifacts": _jsonable(application.artifact_recovery),
                "sessions": _jsonable(application.session_recovery),
                "interrupted_runs": [run.run_id for run in application.run_recovery],
            },
        }

    def _project_get(self, _params, _context) -> RpcResult:
        return {"project": _jsonable(self._app().project.descriptor)}

    def _project_close(self, _params, _context) -> RpcResult:
        if self.application is None:
            return {"closed": True, "project_id": None}
        project_id = self.application.project.descriptor.project_id
        self.application.close()
        self.application = None
        return {"closed": True, "project_id": project_id}

    def _session_inspect(self, params, _context) -> RpcResult:
        report = self._app().sessions.inspect(_required_str(params, "external_bundle"))
        return {"report": _jsonable(report)}

    def _session_import(self, params, _context) -> RpcResult:
        result = self._app().sessions.import_bundle(
            _required_str(params, "external_bundle"),
            transaction_id=_required_str(params, "transaction_id"),
            imported_by=_required_str(params, "actor"),
        )
        return {
            "session": _jsonable(result.session),
            "revision": _jsonable(result.revision),
            "transaction_id": result.receipt.transaction_id,
            "audit_event_id": result.receipt.audit_event_id,
            "replayed": result.replayed,
        }

    def _session_list(self, _params, _context) -> RpcResult:
        app = self._app()
        return {
            "sessions": [
                {
                    "session": _jsonable(session),
                    "revisions": [
                        _jsonable(revision)
                        for revision in app.sessions.list_revisions(session.session_id)
                    ],
                }
                for session in app.sessions.list_sessions()
            ]
        }

    def _session_get(self, params, _context) -> RpcResult:
        app = self._app()
        session = app.sessions.get(_required_str(params, "session_id"))
        return {
            "session": _jsonable(session),
            "revisions": [
                _jsonable(revision) for revision in app.sessions.list_revisions(session.session_id)
            ],
        }

    def _session_artifact_get(self, params, _context) -> RpcResult:
        app = self._app()
        revision_id = _required_str(params, "session_revision_id")
        relative_path = _required_str(params, "relative_path").replace("\\", "/")
        app.sessions.verify_managed_revision(revision_id)
        row = app.project.database.fetchone(
            """
            SELECT relative_path, byte_size, sha256 FROM session_files
            WHERE session_revision_id = ? AND relative_path = ?
            """,
            (revision_id, relative_path),
        )
        if row is None:
            raise ArtifactNotFoundError(relative_path)
        revision = app.sessions.get_revision(revision_id)
        return {
            "session_revision_id": revision_id,
            "project_relative_path": f"{revision.managed_bundle_path}/{relative_path}",
            "relative_path": relative_path,
            "byte_size": int(row["byte_size"]),
            "sha256": row["sha256"],
            "media_type": mimetypes.guess_type(relative_path)[0] or "application/octet-stream",
            "read_only": True,
        }

    def _component_concept_list(self, params, _context) -> RpcResult:
        app = self._app()
        selected_kind = params.get("kind")
        kinds = tuple(_CONCEPT_KINDS) if selected_kind is None else (_component_kind(params),)
        if any(kind not in _CONCEPT_KINDS for kind in kinds):
            raise InvalidParamsFault("kind must identify a concept", path="/kind")
        records = [
            record
            for kind in sorted(kinds, key=lambda item: item.value)
            for record in app.model_library.list_records(LibraryQuery(kind=kind))
        ]
        return {"concepts": [_jsonable(record) for record in records]}

    def _component_concept_get(self, params, _context) -> RpcResult:
        kind = _component_kind(params)
        if kind not in _CONCEPT_KINDS:
            raise InvalidParamsFault("kind must identify a concept", path="/kind")
        item = self._app().model_library.get_exact(kind, _required_str(params, "concept_id"))
        return {"concept": _jsonable(item)}

    def _component_version_list(self, params, _context) -> RpcResult:
        app = self._app()
        kind = None if params.get("kind") is None else _component_kind(params)
        if kind in _CONCEPT_KINDS:
            raise InvalidParamsFault("kind must identify a version", path="/kind")
        concept_id = _optional_str(params, "concept_id")
        lifecycle_raw = _optional_str(params, "lifecycle")
        lifecycle = None if lifecycle_raw is None else ComponentLifecycle(lifecycle_raw)
        raw_tags = _list(params.get("tags", []), "tags")
        if any(type(item) is not str or not item for item in raw_tags):
            raise InvalidParamsFault("tags must contain non-empty strings", path="/tags")
        tags = tuple(item for item in raw_tags if isinstance(item, str))
        records = app.model_library.list_records(
            LibraryQuery(
                kind=kind,
                concept_id=concept_id,
                lifecycle=lifecycle,
                tags=tags,
            )
        )
        summaries = [
            {
                "kind": record.kind.value,
                "version_id": record.record_id,
                "concept_id": record.concept_id,
                "tags": list(record.tags),
                "lifecycle": record.metadata.lifecycle.value,
                "created_at": _jsonable(record.metadata.created_at),
                "content_hash": getattr(record.item, "content_hash", None),
            }
            for record in records
            if record.kind not in _CONCEPT_KINDS
        ]
        return {"versions": summaries}

    def _component_version_get(self, params, _context) -> RpcResult:
        kind = _component_kind(params)
        if kind in _CONCEPT_KINDS:
            raise InvalidParamsFault("kind must identify a version", path="/kind")
        item = self._app().model_library.get_exact(kind, _required_str(params, "version_id"))
        return {"version": _jsonable(item)}

    def _component_version_diff(self, params, _context) -> RpcResult:
        kind = _component_kind(params)
        app = self._app()
        left = _jsonable(
            app.model_library.get_exact(kind, _required_str(params, "left_version_id"))
        )
        right = _jsonable(
            app.model_library.get_exact(kind, _required_str(params, "right_version_id"))
        )
        return {"kind": kind.value, "changes": _diff_values(left, right)}

    def _operator_catalog_list(self, _params, _context) -> RpcResult:
        return {
            "operators": [
                _jsonable(definition) for definition in self._app().operator_registry.catalog()
            ]
        }

    def _operator_definition_get(self, params, _context) -> RpcResult:
        definition = self._app().operator_registry.definition(
            _required_str(params, "operator_id"),
            _required_str(params, "implementation_version"),
        )
        return {"operator": _jsonable(definition)}

    def _scheme_version_list(self, _params, _context) -> RpcResult:
        records = self._app().model_library.list_records(
            LibraryQuery(kind=ComponentKind.ASSESSMENT_SCHEME_VERSION)
        )
        return {
            "schemes": [
                {
                    "scheme_version_id": record.record_id,
                    "concept_id": record.concept_id,
                    "name": getattr(record.item, "name", record.record_id),
                    "content_hash": getattr(record.item, "content_hash", None),
                    "created_at": _jsonable(record.metadata.created_at),
                }
                for record in records
            ]
        }

    def _scheme_version_get(self, params, _context) -> RpcResult:
        item = self._app().model_library.get_exact(
            ComponentKind.ASSESSMENT_SCHEME_VERSION,
            _required_str(params, "scheme_version_id"),
        )
        if not isinstance(item, AssessmentSchemeVersion):
            raise ValueError("scheme identity resolved to another component kind")
        return {"scheme": _jsonable(item)}

    def _scheme_version_diff(self, params, _context) -> RpcResult:
        app = self._app()
        left = _jsonable(
            app.model_library.get_exact(
                ComponentKind.ASSESSMENT_SCHEME_VERSION,
                _required_str(params, "left_scheme_version_id"),
            )
        )
        right = _jsonable(
            app.model_library.get_exact(
                ComponentKind.ASSESSMENT_SCHEME_VERSION,
                _required_str(params, "right_scheme_version_id"),
            )
        )
        return {"changes": _diff_values(left, right)}

    def _scheme_draft_create(self, params, context) -> RpcResult:
        app = self._app()
        draft_id = _required_str(params, "draft_id")
        scheme_id = _required_str(params, "scheme_version_id")
        return self._mutate(
            app,
            "scheme.draft.create",
            params,
            context,
            subject_kind="scheme_draft",
            subject_id=draft_id,
            audit_details={"base_scheme_version_id": scheme_id},
            mutation=lambda: {
                "draft_record": _jsonable(
                    app.schemes.create_draft_from_scheme(
                        scheme_id,
                        draft_id=draft_id,
                        author_id=_required_str(params, "actor"),
                    )
                )
            },
        )

    def _scheme_draft_get(self, params, _context) -> RpcResult:
        record = self._app().drafts.get(_required_str(params, "draft_id"))
        return {"draft_record": _jsonable(record)}

    def _scheme_draft_discard(self, params, context) -> RpcResult:
        app = self._app()
        draft_id = _required_str(params, "draft_id")
        return self._mutate(
            app,
            "scheme.draft.discard",
            params,
            context,
            subject_kind="scheme_draft",
            subject_id=draft_id,
            audit_details={},
            mutation=lambda: {
                "discarded_draft_id": app.schemes.discard_draft(draft_id).draft.draft_id
            },
        )

    def _scheme_draft_publish(self, params, context) -> RpcResult:
        app = self._app()
        draft_id = _required_str(params, "draft_id")
        return self._mutate(
            app,
            "scheme.draft.publish",
            params,
            context,
            subject_kind="scheme_draft",
            subject_id=draft_id,
            audit_details={
                "expected_graph_version": _required_int(params, "expected_graph_version"),
                "expected_layout_version": _required_int(params, "expected_layout_version"),
            },
            mutation=lambda: {
                "publication": _jsonable(
                    app.schemes.publish(
                        draft_id,
                        expected_graph_version=_required_int(params, "expected_graph_version"),
                        expected_layout_version=_required_int(params, "expected_layout_version"),
                        author_id=_required_str(params, "actor"),
                        note=_optional_str(params, "note"),
                    )
                )
            },
        )

    def _graph_snapshot_get(self, params, _context) -> RpcResult:
        record = self._app().drafts.get(_required_str(params, "draft_id"))
        return {"draft_record": _jsonable(record)}

    def _graph_operations_apply(self, params, context) -> RpcResult:
        app = self._app()
        draft_id = _required_str(params, "draft_id")
        operations = tuple(
            _operation(item) for item in _list(params.get("operations"), "operations")
        )
        return self._mutate(
            app,
            "graph.operations.apply",
            params,
            context,
            subject_kind="scheme_draft",
            subject_id=draft_id,
            audit_details={"operation_count": len(operations)},
            mutation=lambda: {
                "draft_record": _jsonable(
                    app.schemes.apply_operations(
                        draft_id,
                        operations,
                        author_id=_required_str(params, "actor"),
                    )
                )
            },
        )

    def _graph_undo(self, params, context) -> RpcResult:
        return self._history_travel("graph.undo", params, context, redo=False)

    def _graph_redo(self, params, context) -> RpcResult:
        return self._history_travel("graph.redo", params, context, redo=True)

    def _history_travel(
        self,
        method: str,
        params: dict[str, JsonValue],
        context: RpcRequestContext,
        *,
        redo: bool,
    ) -> RpcResult:
        app = self._app()
        draft_id = _required_str(params, "draft_id")
        action = app.schemes.redo if redo else app.schemes.undo
        return self._mutate(
            app,
            method,
            params,
            context,
            subject_kind="scheme_draft",
            subject_id=draft_id,
            audit_details={},
            mutation=lambda: {
                "draft_record": _jsonable(
                    action(
                        draft_id,
                        expected_graph_version=_required_int(params, "expected_graph_version"),
                        expected_layout_version=_required_int(params, "expected_layout_version"),
                        author_id=_required_str(params, "actor"),
                    )
                )
            },
        )

    def _layout_update(self, params, context) -> RpcResult:
        app = self._app()
        draft_id = _required_str(params, "draft_id")
        candidate_id = _required_str(params, "candidate_id")
        expected_layout = _required_int(params, "expected_layout_version")
        operations = tuple(
            MoveLayoutNode(
                expected_layout_version=expected_layout,
                candidate_id=candidate_id,
                node_id=_required_str(_mapping(item, "positions[]"), "node_id"),
                x=_number(_mapping(item, "positions[]").get("x"), "x"),
                y=_number(_mapping(item, "positions[]").get("y"), "y"),
            )
            for item in _list(params.get("positions"), "positions")
        )
        return self._mutate(
            app,
            "layout.update",
            params,
            context,
            subject_kind="scheme_draft",
            subject_id=draft_id,
            audit_details={"position_count": len(operations)},
            mutation=lambda: {
                "draft_record": _jsonable(
                    app.schemes.apply_operations(
                        draft_id,
                        operations,
                        author_id=_required_str(params, "actor"),
                    )
                )
            },
        )

    def _graph_validate(self, params, _context) -> RpcResult:
        draft = self._app().drafts.get(_required_str(params, "draft_id")).draft
        return {
            "draft_id": draft.draft_id,
            "graph_version": draft.graph_version,
            "layout_version": draft.layout_version,
            "validation_state": draft.validation_state.value,
            "diagnostics": _jsonable(draft.diagnostics),
        }

    def _run_preflight(self, params, _context) -> RpcResult:
        app = self._app()
        runtime_parameters = _mapping(params.get("runtime_parameters", {}), "runtime_parameters")
        prepared = app.preflight.prepare(
            session_revision_id=_required_str(params, "session_revision_id"),
            scheme_version_id=_required_str(params, "scheme_version_id"),
            purpose=RunPurpose(_required_str(params, "purpose")),
            runtime_parameters=runtime_parameters,
        )
        return {"preflight": _jsonable(prepared.report)}

    def _run_start(self, params, context) -> RpcResult:
        app = self._app()
        preflight_id = _required_str(params, "preflight_id")
        run_id = _required_str(params, "run_id")
        snapshot = app.preflight.build_snapshot(preflight_id, run_id=run_id)
        response = self._mutate(
            app,
            "run.start",
            params,
            context,
            subject_kind="run",
            subject_id=run_id,
            audit_details={
                "preflight_id": preflight_id,
                "snapshot_hash": snapshot.snapshot_hash,
            },
            mutation=lambda: {
                "run": _jsonable(
                    app.runs.create(
                        snapshot,
                        preflight_id=preflight_id,
                        requested_at=self.clock(),
                    )
                )
            },
        )
        app.coordinator.enqueue(run_id)
        return response

    def _run_preview(self, params, _context) -> RpcResult:
        app = self._app()
        observations = tuple(
            Observation.model_validate(_mapping(item, "observations[]"))
            for item in _list(params.get("observations", []), "observations")
        )
        query_node_ids = tuple(
            ComponentIdRef.model_validate(_mapping(item, "query_node_ids[]"))
            for item in _list(params.get("query_node_ids", []), "query_node_ids")
        )
        preview = app.schemes.preview(
            _required_str(params, "draft_id"),
            expected_graph_version=_required_int(params, "expected_graph_version"),
            expected_layout_version=_required_int(params, "expected_layout_version"),
            observations=observations,
            query_node_ids=query_node_ids if query_node_ids else None,
        )
        return {"preview": _jsonable(preview)}

    def _run_status(self, params, _context) -> RpcResult:
        app = self._app()
        run = app.runs.get(_required_str(params, "run_id"))
        result_id = None
        with suppress(RunResultNotFoundError):
            result_id = app.results.get_by_run(run.run_id).result_id
        return {"run": _jsonable(run), "result_id": result_id}

    def _run_events_list(self, params, _context) -> RpcResult:
        events = self._app().runs.list_events(
            _required_str(params, "run_id"),
            after_sequence=_optional_int(params, "after_sequence", default=0),
        )
        return {"events": [_jsonable(event) for event in events]}

    def _run_cancel(self, params, context) -> RpcResult:
        app = self._app()
        run_id = _required_str(params, "run_id")
        return self._mutate(
            app,
            "run.cancel",
            params,
            context,
            subject_kind="run",
            subject_id=run_id,
            audit_details={},
            mutation=lambda: {"run": _jsonable(app.coordinator.cancel(run_id))},
        )

    def _result_get(self, params, _context) -> RpcResult:
        app = self._app()
        result_id = _optional_str(params, "result_id")
        run_id = _optional_str(params, "run_id")
        if (result_id is None) == (run_id is None):
            raise InvalidParamsFault("provide exactly one of result_id or run_id")
        result = (
            app.results.get(cast(str, result_id))
            if result_id
            else app.results.get_by_run(cast(str, run_id))
        )
        return {"result": _jsonable(result)}

    def _result_artifact_get(self, params, _context) -> RpcResult:
        app = self._app()
        result_id = _required_str(params, "result_id")
        artifact_id = _required_str(params, "artifact_id")
        app.results.get(result_id)
        reference = app.project.database.fetchone(
            """
            SELECT 1 FROM artifact_references
            WHERE owner_kind = 'run_result' AND owner_id = ? AND artifact_id = ?
            """,
            (result_id, artifact_id),
        )
        if reference is None:
            raise ArtifactNotFoundError(artifact_id)
        with app.artifacts.open_verified(artifact_id):
            pass
        artifact = app.artifacts.get(artifact_id)
        return {"artifact": _jsonable(artifact), "read_only": True}

    def _audit_events_list(self, params, _context) -> RpcResult:
        query = AuditQuery(
            event_type=_optional_str(params, "event_type"),
            subject_kind=_optional_str(params, "subject_kind"),
            subject_id=_optional_str(params, "subject_id"),
            transaction_id=_optional_str(params, "transaction_id"),
        )
        events = self._app().audit.list_events(
            query,
            limit=_optional_int(params, "limit", default=100),
            offset=_optional_int(params, "offset", default=0),
        )
        return {"events": [_jsonable(event) for event in events]}


__all__ = ["SidecarMethods"]
