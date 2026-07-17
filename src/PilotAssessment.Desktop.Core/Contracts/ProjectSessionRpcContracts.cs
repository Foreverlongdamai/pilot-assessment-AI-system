using System.Text.Json;

namespace PilotAssessment.Desktop.Core.Contracts;

public sealed record ProjectCreateRequest(
    string TransactionId,
    string Actor,
    string Root,
    string ProjectId,
    string Name);

public sealed record ProjectOpenRequest(string Root);

public sealed record ProjectMutationResponse(
    ProjectDescriptor Project,
    string TransactionId,
    string AuditEventId,
    bool Replayed,
    string TraceId);

public sealed record ProjectRecovery(
    IReadOnlyDictionary<string, int> Artifacts,
    IReadOnlyDictionary<string, int> Sessions,
    IReadOnlyList<string> InterruptedRuns);

public sealed record ProjectOpenResponse(
    ProjectDescriptor Project,
    ProjectRecovery Recovery,
    string TraceId);

public sealed record ProjectGetResponse(ProjectDescriptor Project, string TraceId);

public sealed record ProjectCloseResponse(bool Closed, string? ProjectId, string TraceId);

public sealed record SessionInspectRequest(string ExternalBundle);

public sealed record SessionInspectResponse(IngestionReadinessReport Report, string TraceId);

public sealed record SessionImportRequest(
    string TransactionId,
    string Actor,
    string ExternalBundle);

public sealed record SessionImportResponse(
    SessionRecord Session,
    SessionRevision Revision,
    string TransactionId,
    string AuditEventId,
    bool Replayed,
    string TraceId);

public sealed record SessionCollectionItem(
    SessionRecord Session,
    IReadOnlyList<SessionRevision> Revisions);

public sealed record SessionListResponse(
    IReadOnlyList<SessionCollectionItem> Sessions,
    string TraceId);

public sealed record SessionGetRequest(string SessionId);

public sealed record SessionGetResponse(
    SessionRecord Session,
    IReadOnlyList<SessionRevision> Revisions,
    string TraceId);

public sealed record SessionReportRequest(string SessionRevisionId, string ReportKind);

public sealed record SessionReportResponse(
    string SessionRevisionId,
    string ReportKind,
    ManagedArtifact? Artifact,
    bool InlineAvailable,
    JsonElement? Report,
    string TraceId);

public sealed record SessionArtifactRequest(string SessionRevisionId, string RelativePath);

public sealed record SessionArtifactLocation(
    string SessionRevisionId,
    string ProjectRelativePath,
    string RelativePath,
    long ByteSize,
    string Sha256,
    string MediaType,
    bool ReadOnly,
    string TraceId);
