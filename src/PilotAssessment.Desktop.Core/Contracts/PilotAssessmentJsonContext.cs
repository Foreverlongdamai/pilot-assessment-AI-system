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
public sealed partial class PilotAssessmentJsonContext : JsonSerializerContext;
