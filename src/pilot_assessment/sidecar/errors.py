"""Stable JSON-RPC and domain faults for the local sidecar boundary."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import TypeAlias

from pydantic import JsonValue

RpcId: TypeAlias = str | int | None
JsonRpcMessage: TypeAlias = dict[str, JsonValue]


class DomainErrorCode(StrEnum):
    PROTOCOL_HANDSHAKE_REQUIRED = "PROTOCOL_HANDSHAKE_REQUIRED"
    PROTOCOL_VERSION_UNSUPPORTED = "PROTOCOL_VERSION_UNSUPPORTED"
    PROJECT_NOT_OPEN = "PROJECT_NOT_OPEN"
    PROJECT_ALREADY_OPEN = "PROJECT_ALREADY_OPEN"
    PROJECT_ALREADY_EXISTS = "PROJECT_ALREADY_EXISTS"
    PROJECT_FORMAT_UNSUPPORTED = "PROJECT_FORMAT_UNSUPPORTED"
    PROJECT_RECOVERY_FAILED = "PROJECT_RECOVERY_FAILED"
    TRANSACTION_REUSE_MISMATCH = "TRANSACTION_REUSE_MISMATCH"
    SESSION_IMPORT_INVALID = "SESSION_IMPORT_INVALID"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    MANAGED_SESSION_CHANGED = "MANAGED_SESSION_CHANGED"
    CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
    ARTIFACT_NOT_FOUND = "ARTIFACT_NOT_FOUND"
    ARTIFACT_INTEGRITY_FAILED = "ARTIFACT_INTEGRITY_FAILED"
    GRAPH_VERSION_CONFLICT = "GRAPH_VERSION_CONFLICT"
    LAYOUT_VERSION_CONFLICT = "LAYOUT_VERSION_CONFLICT"
    DRAFT_NOT_FOUND = "DRAFT_NOT_FOUND"
    DRAFT_ALREADY_EXISTS = "DRAFT_ALREADY_EXISTS"
    SCHEME_NOT_FOUND = "SCHEME_NOT_FOUND"
    SCHEME_VALIDATION_FAILED = "SCHEME_VALIDATION_FAILED"
    COMPONENT_NOT_FOUND = "COMPONENT_NOT_FOUND"
    OPERATOR_NOT_FOUND = "OPERATOR_NOT_FOUND"
    MODEL_NODE_NOT_FOUND = "MODEL_NODE_NOT_FOUND"
    MODEL_SCHEME_NOT_FOUND = "MODEL_SCHEME_NOT_FOUND"
    MODEL_REVISION_CONFLICT = "MODEL_REVISION_CONFLICT"
    MODEL_DEACTIVATION_STALE = "MODEL_DEACTIVATION_STALE"
    MODEL_DEPENDENCY_INVALID = "MODEL_DEPENDENCY_INVALID"
    MODEL_CPT_INVALID = "MODEL_CPT_INVALID"
    MODEL_ACTIVE_CLOSURE_INCOMPLETE = "MODEL_ACTIVE_CLOSURE_INCOMPLETE"
    MODEL_OPERATOR_UNSUPPORTED = "MODEL_OPERATOR_UNSUPPORTED"
    RUN_PREFLIGHT_FAILED = "RUN_PREFLIGHT_FAILED"
    RUN_NOT_FOUND = "RUN_NOT_FOUND"
    RUN_ALREADY_TERMINAL = "RUN_ALREADY_TERMINAL"
    RUN_CANCEL_REJECTED = "RUN_CANCEL_REJECTED"
    RUN_INTERRUPTED = "RUN_INTERRUPTED"
    INFERENCE_FAILED = "INFERENCE_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


_DOMAIN_RPC_CODES = {
    DomainErrorCode.PROTOCOL_HANDSHAKE_REQUIRED: -32000,
    DomainErrorCode.PROTOCOL_VERSION_UNSUPPORTED: -32000,
    DomainErrorCode.PROJECT_NOT_OPEN: -32001,
    DomainErrorCode.PROJECT_ALREADY_OPEN: -32001,
    DomainErrorCode.PROJECT_ALREADY_EXISTS: -32001,
    DomainErrorCode.PROJECT_FORMAT_UNSUPPORTED: -32001,
    DomainErrorCode.PROJECT_RECOVERY_FAILED: -32001,
    DomainErrorCode.TRANSACTION_REUSE_MISMATCH: -32002,
    DomainErrorCode.SESSION_IMPORT_INVALID: -32003,
    DomainErrorCode.SESSION_NOT_FOUND: -32003,
    DomainErrorCode.MANAGED_SESSION_CHANGED: -32003,
    DomainErrorCode.CHECKSUM_MISMATCH: -32003,
    DomainErrorCode.ARTIFACT_NOT_FOUND: -32004,
    DomainErrorCode.ARTIFACT_INTEGRITY_FAILED: -32004,
    DomainErrorCode.GRAPH_VERSION_CONFLICT: -32020,
    DomainErrorCode.LAYOUT_VERSION_CONFLICT: -32020,
    DomainErrorCode.DRAFT_NOT_FOUND: -32021,
    DomainErrorCode.DRAFT_ALREADY_EXISTS: -32021,
    DomainErrorCode.SCHEME_NOT_FOUND: -32021,
    DomainErrorCode.SCHEME_VALIDATION_FAILED: -32022,
    DomainErrorCode.COMPONENT_NOT_FOUND: -32021,
    DomainErrorCode.OPERATOR_NOT_FOUND: -32021,
    DomainErrorCode.MODEL_NODE_NOT_FOUND: -32021,
    DomainErrorCode.MODEL_SCHEME_NOT_FOUND: -32021,
    DomainErrorCode.MODEL_REVISION_CONFLICT: -32020,
    DomainErrorCode.MODEL_DEACTIVATION_STALE: -32020,
    DomainErrorCode.MODEL_DEPENDENCY_INVALID: -32022,
    DomainErrorCode.MODEL_CPT_INVALID: -32022,
    DomainErrorCode.MODEL_ACTIVE_CLOSURE_INCOMPLETE: -32022,
    DomainErrorCode.MODEL_OPERATOR_UNSUPPORTED: -32022,
    DomainErrorCode.RUN_PREFLIGHT_FAILED: -32030,
    DomainErrorCode.RUN_NOT_FOUND: -32030,
    DomainErrorCode.RUN_ALREADY_TERMINAL: -32030,
    DomainErrorCode.RUN_CANCEL_REJECTED: -32030,
    DomainErrorCode.RUN_INTERRUPTED: -32030,
    DomainErrorCode.INFERENCE_FAILED: -32040,
    DomainErrorCode.INTERNAL_ERROR: -32099,
}


def domain_rpc_code(error_code: DomainErrorCode | str) -> int:
    """Map stable machine codes to a reserved JSON-RPC server-error category."""

    try:
        known = DomainErrorCode(str(error_code))
    except ValueError:
        return -32099
    return _DOMAIN_RPC_CODES[known]


class JsonRpcFault(RuntimeError):
    """A safe fault that can be serialized without leaking backend internals."""

    def __init__(
        self,
        rpc_code: int,
        message: str,
        error_code: str,
        *,
        data: Mapping[str, JsonValue] | None = None,
    ) -> None:
        super().__init__(message)
        self.rpc_code = rpc_code
        self.message = message
        self.error_code = error_code
        self.data = dict(data or {})

    def error_data(self, *, trace_id: str) -> dict[str, JsonValue]:
        return {"error_code": self.error_code, "trace_id": trace_id, **self.data}


class ParseErrorFault(JsonRpcFault):
    def __init__(self) -> None:
        super().__init__(-32700, "Parse error", "PARSE_ERROR")


class InvalidRequestFault(JsonRpcFault):
    def __init__(self, _detail: str | None = None) -> None:
        super().__init__(-32600, "Invalid Request", "INVALID_REQUEST")


class MessageTooLargeFault(JsonRpcFault):
    def __init__(self, max_message_bytes: int) -> None:
        super().__init__(
            -32600,
            f"Message exceeds maximum of {max_message_bytes} bytes",
            "MESSAGE_TOO_LARGE",
            data={"max_message_bytes": max_message_bytes},
        )


class MethodNotFoundFault(JsonRpcFault):
    def __init__(self, method: str) -> None:
        super().__init__(
            -32601,
            "Method not found",
            "METHOD_NOT_FOUND",
            data={"method": method},
        )


class InvalidParamsFault(JsonRpcFault):
    def __init__(self, detail: str, *, path: str | None = None) -> None:
        data: dict[str, JsonValue] = {"detail": detail}
        if path is not None:
            data["path"] = path
        super().__init__(-32602, "Invalid params", "INVALID_PARAMS", data=data)


class InternalErrorFault(JsonRpcFault):
    def __init__(self) -> None:
        super().__init__(-32603, "Internal error", "INTERNAL_ERROR")


class DomainRpcError(JsonRpcFault):
    """Transport-safe domain failure with the M6 typed recovery fields."""

    def __init__(
        self,
        error_code: DomainErrorCode | str,
        message: str,
        *,
        recoverable: bool,
        transaction_id: str | None = None,
        path: str | None = None,
        current_revision: str | int | None = None,
        diagnostics: JsonValue | None = None,
    ) -> None:
        code_text = str(error_code)
        if not code_text:
            raise ValueError("domain error_code must not be empty")
        data: dict[str, JsonValue] = {
            "message": message,
            "recoverable": recoverable,
        }
        if transaction_id is not None:
            data["transaction_id"] = transaction_id
        if path is not None:
            data["path"] = path
        if current_revision is not None:
            data["current_revision"] = current_revision
        if diagnostics is not None:
            data["diagnostics"] = diagnostics
        super().__init__(
            domain_rpc_code(code_text),
            message,
            code_text,
            data=data,
        )

    def error_data(self, *, trace_id: str) -> dict[str, JsonValue]:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "recoverable": self.data["recoverable"],
            "trace_id": trace_id,
            **{
                key: value
                for key, value in self.data.items()
                if key not in {"message", "recoverable"}
            },
        }


def error_response(
    fault: JsonRpcFault,
    *,
    request_id: RpcId,
    trace_id: str,
) -> JsonRpcMessage:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": fault.rpc_code,
            "message": fault.message,
            "data": fault.error_data(trace_id=trace_id),
        },
    }


__all__ = [
    "DomainErrorCode",
    "DomainRpcError",
    "InternalErrorFault",
    "InvalidParamsFault",
    "InvalidRequestFault",
    "JsonRpcFault",
    "JsonRpcMessage",
    "MessageTooLargeFault",
    "MethodNotFoundFault",
    "ParseErrorFault",
    "RpcId",
    "domain_rpc_code",
    "error_response",
]
