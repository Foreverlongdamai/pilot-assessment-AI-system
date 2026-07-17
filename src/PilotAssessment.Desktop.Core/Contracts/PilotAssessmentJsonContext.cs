using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.Contracts;

[JsonSourceGenerationOptions(
    PropertyNamingPolicy = JsonKnownNamingPolicy.SnakeCaseLower,
    DefaultIgnoreCondition = JsonIgnoreCondition.Never,
    UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
    RespectRequiredConstructorParameters = true,
    UseStringEnumConverter = true)]
[JsonSerializable(typeof(ModelNode))]
[JsonSerializable(typeof(ModelGraphSnapshot))]
[JsonSerializable(typeof(ModelChangeEvent))]
[JsonSerializable(typeof(DeactivationImpact))]
[JsonSerializable(typeof(OperatorDefinition))]
[JsonSerializable(typeof(ProjectDescriptor))]
[JsonSerializable(typeof(SessionRecord))]
[JsonSerializable(typeof(SessionRevision))]
[JsonSerializable(typeof(IngestionReadinessReport))]
[JsonSerializable(typeof(ManagedArtifact))]
[JsonSerializable(typeof(ArtifactReference))]
[JsonSerializable(typeof(TransactionReceipt))]
[JsonSerializable(typeof(AuditEvent))]
[JsonSerializable(typeof(CurrentModelRunPreflightReport))]
[JsonSerializable(typeof(CurrentModelRunSnapshot))]
[JsonSerializable(typeof(AssessmentRun))]
[JsonSerializable(typeof(AssessmentRunV2))]
[JsonSerializable(typeof(RunEvent))]
[JsonSerializable(typeof(RunResultEnvelope))]
[JsonSerializable(typeof(JsonRpcRequest))]
[JsonSerializable(typeof(JsonRpcNotification))]
[JsonSerializable(typeof(JsonRpcResultResponse))]
[JsonSerializable(typeof(JsonRpcErrorResponse))]
[JsonSerializable(typeof(ProjectCreateRequest))]
[JsonSerializable(typeof(ProjectOpenRequest))]
[JsonSerializable(typeof(ProjectMutationResponse))]
[JsonSerializable(typeof(ProjectOpenResponse))]
[JsonSerializable(typeof(ProjectGetResponse))]
[JsonSerializable(typeof(ProjectCloseResponse))]
[JsonSerializable(typeof(SessionInspectRequest))]
[JsonSerializable(typeof(SessionInspectResponse))]
[JsonSerializable(typeof(SessionImportRequest))]
[JsonSerializable(typeof(SessionImportResponse))]
[JsonSerializable(typeof(SessionListResponse))]
[JsonSerializable(typeof(SessionGetRequest))]
[JsonSerializable(typeof(SessionGetResponse))]
[JsonSerializable(typeof(SessionReportRequest))]
[JsonSerializable(typeof(SessionReportResponse))]
[JsonSerializable(typeof(SessionArtifactRequest))]
[JsonSerializable(typeof(SessionArtifactLocation))]
public sealed partial class PilotAssessmentJsonContext : JsonSerializerContext;
