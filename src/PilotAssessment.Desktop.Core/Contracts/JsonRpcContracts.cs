using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.Contracts;

public enum DomainErrorCode
{
    [JsonStringEnumMemberName("PARSE_ERROR")]
    ParseError,
    [JsonStringEnumMemberName("INVALID_REQUEST")]
    InvalidRequest,
    [JsonStringEnumMemberName("MESSAGE_TOO_LARGE")]
    MessageTooLarge,
    [JsonStringEnumMemberName("METHOD_NOT_FOUND")]
    MethodNotFound,
    [JsonStringEnumMemberName("INVALID_PARAMS")]
    InvalidParams,
    [JsonStringEnumMemberName("PROTOCOL_HANDSHAKE_REQUIRED")]
    ProtocolHandshakeRequired,
    [JsonStringEnumMemberName("PROTOCOL_VERSION_UNSUPPORTED")]
    ProtocolVersionUnsupported,
    [JsonStringEnumMemberName("PROJECT_NOT_OPEN")]
    ProjectNotOpen,
    [JsonStringEnumMemberName("PROJECT_ALREADY_OPEN")]
    ProjectAlreadyOpen,
    [JsonStringEnumMemberName("PROJECT_ALREADY_EXISTS")]
    ProjectAlreadyExists,
    [JsonStringEnumMemberName("PROJECT_FORMAT_UNSUPPORTED")]
    ProjectFormatUnsupported,
    [JsonStringEnumMemberName("PROJECT_RECOVERY_FAILED")]
    ProjectRecoveryFailed,
    [JsonStringEnumMemberName("TRANSACTION_REUSE_MISMATCH")]
    TransactionReuseMismatch,
    [JsonStringEnumMemberName("SESSION_IMPORT_INVALID")]
    SessionImportInvalid,
    [JsonStringEnumMemberName("SESSION_NOT_FOUND")]
    SessionNotFound,
    [JsonStringEnumMemberName("MANAGED_SESSION_CHANGED")]
    ManagedSessionChanged,
    [JsonStringEnumMemberName("CHECKSUM_MISMATCH")]
    ChecksumMismatch,
    [JsonStringEnumMemberName("ARTIFACT_NOT_FOUND")]
    ArtifactNotFound,
    [JsonStringEnumMemberName("ARTIFACT_INTEGRITY_FAILED")]
    ArtifactIntegrityFailed,
    [JsonStringEnumMemberName("GRAPH_VERSION_CONFLICT")]
    GraphVersionConflict,
    [JsonStringEnumMemberName("LAYOUT_VERSION_CONFLICT")]
    LayoutVersionConflict,
    [JsonStringEnumMemberName("DRAFT_NOT_FOUND")]
    DraftNotFound,
    [JsonStringEnumMemberName("DRAFT_ALREADY_EXISTS")]
    DraftAlreadyExists,
    [JsonStringEnumMemberName("SCHEME_NOT_FOUND")]
    SchemeNotFound,
    [JsonStringEnumMemberName("SCHEME_VALIDATION_FAILED")]
    SchemeValidationFailed,
    [JsonStringEnumMemberName("COMPONENT_NOT_FOUND")]
    ComponentNotFound,
    [JsonStringEnumMemberName("OPERATOR_NOT_FOUND")]
    OperatorNotFound,
    [JsonStringEnumMemberName("MODEL_NODE_NOT_FOUND")]
    ModelNodeNotFound,
    [JsonStringEnumMemberName("MODEL_SCHEME_NOT_FOUND")]
    ModelSchemeNotFound,
    [JsonStringEnumMemberName("MODEL_REVISION_CONFLICT")]
    ModelRevisionConflict,
    [JsonStringEnumMemberName("MODEL_DEACTIVATION_STALE")]
    ModelDeactivationStale,
    [JsonStringEnumMemberName("MODEL_DEPENDENCY_INVALID")]
    ModelDependencyInvalid,
    [JsonStringEnumMemberName("MODEL_CPT_INVALID")]
    ModelCptInvalid,
    [JsonStringEnumMemberName("MODEL_ACTIVE_CLOSURE_INCOMPLETE")]
    ModelActiveClosureIncomplete,
    [JsonStringEnumMemberName("MODEL_OPERATOR_UNSUPPORTED")]
    ModelOperatorUnsupported,
    [JsonStringEnumMemberName("RUN_PREFLIGHT_FAILED")]
    RunPreflightFailed,
    [JsonStringEnumMemberName("RUN_NOT_FOUND")]
    RunNotFound,
    [JsonStringEnumMemberName("RUN_ALREADY_TERMINAL")]
    RunAlreadyTerminal,
    [JsonStringEnumMemberName("RUN_CANCEL_REJECTED")]
    RunCancelRejected,
    [JsonStringEnumMemberName("RUN_INTERRUPTED")]
    RunInterrupted,
    [JsonStringEnumMemberName("INFERENCE_FAILED")]
    InferenceFailed,
    [JsonStringEnumMemberName("INTERNAL_ERROR")]
    InternalError,
}

public sealed record JsonRpcErrorData(
    DomainErrorCode ErrorCode,
    string TraceId,
    string? Message = null,
    bool? Recoverable = null,
    string? TransactionId = null,
    string? Path = null,
    JsonElement? CurrentRevision = null,
    JsonNode? Diagnostics = null,
    int? MaxMessageBytes = null,
    string? Method = null,
    string? Detail = null);

public sealed record JsonRpcError(
    int Code,
    string Message,
    JsonRpcErrorData Data);

public sealed record JsonRpcErrorResponse(
    string Jsonrpc,
    JsonElement? Id,
    JsonRpcError Error);

public sealed record JsonRpcRequest(
    string Jsonrpc,
    JsonElement Id,
    string Method,
    JsonElement? Params);

public sealed record JsonRpcNotification(
    string Jsonrpc,
    string Method,
    JsonElement? Params);

public sealed record JsonRpcResultResponse(
    string Jsonrpc,
    JsonElement Id,
    JsonElement Result);
