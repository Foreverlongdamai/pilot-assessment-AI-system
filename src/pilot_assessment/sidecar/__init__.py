"""Local stdio JSON-RPC sidecar protocol primitives."""

from pilot_assessment.sidecar.dispatcher import (
    DEFAULT_CAPABILITIES,
    SUPPORTED_PROTOCOL_VERSIONS,
    JsonRpcDispatcher,
    RpcMethodHandler,
    RpcRequestContext,
)
from pilot_assessment.sidecar.errors import (
    DomainErrorCode,
    DomainRpcError,
    InternalErrorFault,
    InvalidParamsFault,
    InvalidRequestFault,
    JsonRpcFault,
    JsonRpcMessage,
    MessageTooLargeFault,
    MethodNotFoundFault,
    ParseErrorFault,
    RpcId,
    domain_rpc_code,
    error_response,
)
from pilot_assessment.sidecar.framing import (
    DEFAULT_MAX_MESSAGE_BYTES,
    JsonLineWriter,
    decode_json_line,
    read_json_line,
)

__all__ = [
    "DEFAULT_CAPABILITIES",
    "DEFAULT_MAX_MESSAGE_BYTES",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "DomainErrorCode",
    "DomainRpcError",
    "InternalErrorFault",
    "InvalidParamsFault",
    "InvalidRequestFault",
    "JsonLineWriter",
    "JsonRpcDispatcher",
    "JsonRpcFault",
    "JsonRpcMessage",
    "MessageTooLargeFault",
    "MethodNotFoundFault",
    "ParseErrorFault",
    "RpcId",
    "RpcMethodHandler",
    "RpcRequestContext",
    "decode_json_line",
    "domain_rpc_code",
    "error_response",
    "read_json_line",
]
