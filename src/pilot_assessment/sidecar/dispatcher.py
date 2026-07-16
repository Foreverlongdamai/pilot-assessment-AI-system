"""Stateful JSON-RPC 2.0 dispatch with mandatory local protocol negotiation."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from threading import RLock
from typing import Protocol, cast
from uuid import uuid4

from pydantic import JsonValue

from pilot_assessment.sidecar.errors import (
    DomainErrorCode,
    DomainRpcError,
    InternalErrorFault,
    InvalidParamsFault,
    InvalidRequestFault,
    JsonRpcFault,
    JsonRpcMessage,
    MethodNotFoundFault,
    RpcId,
    error_response,
)
from pilot_assessment.sidecar.framing import DEFAULT_MAX_MESSAGE_BYTES

SUPPORTED_PROTOCOL_VERSIONS = ("1.0",)
DEFAULT_CAPABILITIES = (
    "runtime.protocol.v1",
    "project.persistence.v1",
    "session.managed-import.v1",
    "component.library.v1",
    "scheme.workspace.v1",
    "operator.catalog.v1",
    "assessment.run.v1",
    "artifact.read.v1",
    "audit.read.v1",
)


@dataclass(frozen=True, slots=True)
class RpcRequestContext:
    trace_id: str
    request_id: RpcId
    transaction_id: str | None
    protocol_version: str


class RpcMethodHandler(Protocol):
    def __call__(
        self,
        params: dict[str, JsonValue],
        context: RpcRequestContext,
    ) -> Mapping[str, JsonValue]: ...


@dataclass(frozen=True, slots=True)
class _Request:
    request_id: RpcId
    is_notification: bool
    method: str
    params: dict[str, JsonValue]


def _default_trace_id() -> str:
    return f"trace.{uuid4().hex}"


def _safe_request_id(message: object) -> RpcId:
    if not isinstance(message, Mapping) or "id" not in message:
        return None
    value = message.get("id")
    if value is None or type(value) in {str, int}:
        return cast(RpcId, value)
    return None


def _notification_candidate(message: object) -> bool:
    return (
        isinstance(message, Mapping)
        and "id" not in message
        and message.get("jsonrpc") == "2.0"
        and type(message.get("method")) is str
        and bool(message.get("method"))
    )


def _parse_request(message: object) -> _Request:
    if not isinstance(message, Mapping):
        raise InvalidRequestFault("JSON-RPC request must be an object")
    if message.get("jsonrpc") != "2.0":
        raise InvalidRequestFault("jsonrpc must equal '2.0'")
    method = message.get("method")
    if type(method) is not str or not method:
        raise InvalidRequestFault("method must be a non-empty string")
    has_id = "id" in message
    request_id = message.get("id")
    if has_id and request_id is not None and type(request_id) not in {str, int}:
        raise InvalidRequestFault("id must be a string, integer, or null")
    params = message.get("params", {})
    if not isinstance(params, Mapping):
        raise InvalidParamsFault("sidecar methods require object params")
    if any(type(key) is not str for key in params):
        raise InvalidParamsFault("parameter names must be strings")
    return _Request(
        request_id=cast(RpcId, request_id),
        is_notification=not has_id,
        method=method,
        params=cast(dict[str, JsonValue], dict(params)),
    )


class JsonRpcDispatcher:
    """Validate envelopes and context, then call registered application adapters."""

    def __init__(
        self,
        *,
        runtime_id: str | None = None,
        backend_version: str = "0.1.0",
        supported_protocol_versions: tuple[str, ...] = SUPPORTED_PROTOCOL_VERSIONS,
        capabilities: tuple[str, ...] = DEFAULT_CAPABILITIES,
        trace_id_factory: Callable[[], str] = _default_trace_id,
        logger: logging.Logger | None = None,
    ) -> None:
        if not supported_protocol_versions or any(
            type(version) is not str or not version for version in supported_protocol_versions
        ):
            raise ValueError("supported protocol versions must be non-empty strings")
        if len(supported_protocol_versions) != len(set(supported_protocol_versions)):
            raise ValueError("supported protocol versions must be unique")
        if len(capabilities) != len(set(capabilities)):
            raise ValueError("capabilities must be unique")
        self.runtime_id = runtime_id or f"runtime.{uuid4().hex}"
        self.backend_version = backend_version
        self.supported_protocol_versions = supported_protocol_versions
        self.capabilities = capabilities
        self.trace_id_factory = trace_id_factory
        self.logger = logger or logging.getLogger(__name__)
        self._handlers: dict[str, RpcMethodHandler] = {}
        self._lock = RLock()
        self._negotiated_protocol_version: str | None = None

    @property
    def negotiated_protocol_version(self) -> str | None:
        with self._lock:
            return self._negotiated_protocol_version

    def register(self, method: str, handler: RpcMethodHandler) -> None:
        if type(method) is not str or not method:
            raise ValueError("RPC method name must be a non-empty string")
        if method == "runtime.hello":
            raise ValueError("runtime.hello is reserved by the dispatcher")
        if not callable(handler):
            raise TypeError("RPC handler must be callable")
        with self._lock:
            if method in self._handlers:
                raise ValueError(f"RPC method {method!r} is already registered")
            self._handlers[method] = handler

    def dispatch(self, message: object) -> JsonRpcMessage | None:
        trace_id = self.trace_id_factory()
        try:
            request = _parse_request(message)
        except JsonRpcFault as fault:
            if _notification_candidate(message):
                return None
            return error_response(
                fault,
                request_id=_safe_request_id(message),
                trace_id=trace_id,
            )

        if request.method == "runtime.hello" and request.is_notification:
            return None
        try:
            if request.method == "runtime.hello":
                result = self._hello(request.params, trace_id=trace_id)
            else:
                protocol_version = self.negotiated_protocol_version
                if protocol_version is None:
                    raise DomainRpcError(
                        DomainErrorCode.PROTOCOL_HANDSHAKE_REQUIRED,
                        "runtime.hello must succeed before business methods",
                        recoverable=True,
                    )
                with self._lock:
                    handler = self._handlers.get(request.method)
                if handler is None:
                    raise MethodNotFoundFault(request.method)
                transaction_id = request.params.get("transaction_id")
                context = RpcRequestContext(
                    trace_id=trace_id,
                    request_id=request.request_id,
                    transaction_id=(transaction_id if type(transaction_id) is str else None),
                    protocol_version=protocol_version,
                )
                result = handler(request.params, context)
            safe_result = self._safe_result(result, trace_id=trace_id)
        except JsonRpcFault as fault:
            if request.is_notification:
                return None
            return error_response(
                fault,
                request_id=request.request_id,
                trace_id=trace_id,
            )
        except Exception:
            self.logger.exception(
                "RPC handler failed",
                extra={"trace_id": trace_id, "rpc_method": request.method},
            )
            if request.is_notification:
                return None
            return error_response(
                InternalErrorFault(),
                request_id=request.request_id,
                trace_id=trace_id,
            )

        if request.is_notification:
            return None
        return {
            "jsonrpc": "2.0",
            "id": request.request_id,
            "result": safe_result,
        }

    def _hello(
        self,
        params: dict[str, JsonValue],
        *,
        trace_id: str,
    ) -> dict[str, JsonValue]:
        supported = params.get("supported_protocols")
        if (
            not isinstance(supported, list)
            or not supported
            or any(type(item) is not str or not item for item in supported)
        ):
            raise InvalidParamsFault(
                "supported_protocols must be a non-empty string array",
                path="/supported_protocols",
            )
        requested = params.get("protocol_version")
        if requested is not None and (type(requested) is not str or not requested):
            raise InvalidParamsFault(
                "protocol_version must be a non-empty string",
                path="/protocol_version",
            )
        client = params.get("client")
        if client is not None and not isinstance(client, Mapping):
            raise InvalidParamsFault("client must be an object", path="/client")
        client_protocols = cast(list[str], supported)
        common = tuple(
            version for version in self.supported_protocol_versions if version in client_protocols
        )
        if not common:
            raise DomainRpcError(
                DomainErrorCode.PROTOCOL_VERSION_UNSUPPORTED,
                "No mutually supported sidecar protocol version",
                recoverable=False,
                diagnostics={
                    "server_supported_protocols": list(self.supported_protocol_versions),
                    "client_supported_protocols": client_protocols,
                },
            )
        selected = requested if requested in common else common[0]
        with self._lock:
            self._negotiated_protocol_version = selected
        return {
            "protocol_version": selected,
            "runtime_id": self.runtime_id,
            "backend_version": self.backend_version,
            "engine": {"name": "assessment-core", "version": self.backend_version},
            "capabilities": list(self.capabilities),
            "state": "ready",
            "max_message_bytes": DEFAULT_MAX_MESSAGE_BYTES,
            "trace_id": trace_id,
        }

    @staticmethod
    def _safe_result(
        result: Mapping[str, JsonValue],
        *,
        trace_id: str,
    ) -> dict[str, JsonValue]:
        if not isinstance(result, Mapping):
            raise InternalErrorFault()
        payload = dict(result)
        payload.setdefault("trace_id", trace_id)
        try:
            json.dumps(payload, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise InternalErrorFault() from error
        return cast(dict[str, JsonValue], payload)


__all__ = [
    "DEFAULT_CAPABILITIES",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "JsonRpcDispatcher",
    "RpcMethodHandler",
    "RpcRequestContext",
]
