using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.Contracts;

public enum SessionLifecycle
{
    [JsonStringEnumMemberName("active")]
    Active,
    [JsonStringEnumMemberName("archived")]
    Archived,
}

public enum SessionSourceKind
{
    [JsonStringEnumMemberName("managed_import")]
    ManagedImport,
}

public enum ArtifactLifecycle
{
    [JsonStringEnumMemberName("active")]
    Active,
    [JsonStringEnumMemberName("unreferenced")]
    Unreferenced,
    [JsonStringEnumMemberName("quarantined")]
    Quarantined,
}

public enum ArtifactOwnerKind
{
    [JsonStringEnumMemberName("session_revision")]
    SessionRevision,
    [JsonStringEnumMemberName("run_preflight")]
    RunPreflight,
    [JsonStringEnumMemberName("run")]
    Run,
    [JsonStringEnumMemberName("run_result")]
    RunResult,
    [JsonStringEnumMemberName("export")]
    Export,
}

public enum TransactionStatus
{
    [JsonStringEnumMemberName("prepared")]
    Prepared,
    [JsonStringEnumMemberName("completed")]
    Completed,
}

public sealed record ProjectDescriptor(
    string ContractId,
    string ContractVersion,
    string ProjectId,
    string FormatVersion,
    string Name,
    DateTime CreatedAt);

public sealed record SessionRecord(
    string ContractId,
    string ContractVersion,
    string SessionId,
    string ProjectId,
    string ParticipantId,
    SessionLifecycle Lifecycle,
    string CurrentSessionRevisionId,
    DateTime CreatedAt);

public sealed record SessionRevisionRef(
    string SessionId,
    string SessionRevisionId,
    string BundleRootHash);

public sealed record SessionRevision(
    string ContractId,
    string ContractVersion,
    string SessionRevisionId,
    string SessionId,
    string ManagedBundlePath,
    string ManifestHash,
    string BundleRootHash,
    string FileInventoryHash,
    SessionSourceKind SourceKind,
    DateTime ImportedAt,
    string ImportedBy,
    string IngestionReadinessRef,
    string? SynchronizationRef);

public sealed record ArtifactIdRef(string ArtifactId, string Sha256);

public sealed record ManagedArtifact(
    string ContractId,
    string ContractVersion,
    string ArtifactId,
    string Sha256,
    long ByteSize,
    string MediaType,
    string? SchemaId,
    string ManagedRelativePath,
    ArtifactLifecycle Lifecycle,
    DateTime CreatedAt);

public sealed record ArtifactReference(
    string ContractId,
    string ContractVersion,
    ArtifactOwnerKind OwnerKind,
    string OwnerId,
    string Role,
    string ArtifactId);

public sealed record TransactionReceipt(
    string ContractId,
    string ContractVersion,
    string TransactionId,
    string Method,
    string RequestHash,
    TransactionStatus Status,
    IReadOnlyDictionary<string, JsonElement>? ResponsePayload,
    string? AuditEventId,
    DateTime? CompletedAt);

public sealed record AuditEvent(
    string ContractId,
    string ContractVersion,
    string AuditEventId,
    string EventType,
    string ActorId,
    DateTime OccurredAt,
    string SubjectKind,
    string SubjectId,
    string? TransactionId,
    IReadOnlyDictionary<string, JsonNode?> Details);
