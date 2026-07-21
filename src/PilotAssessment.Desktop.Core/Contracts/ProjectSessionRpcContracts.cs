using System.Text.Json;

namespace PilotAssessment.Desktop.Core.Contracts;

public sealed record ProjectCreateRequest(
    string TransactionId,
    string Actor,
    string Root,
    string? ProjectId,
    string Name);

public sealed record ProjectOpenRequest(string Root);

public sealed record LegacyModelImportResult(
    bool LegacyModelDetected,
    string? ImportFingerprint,
    bool Imported,
    bool Replayed,
    int InsertedNodeCount,
    int InsertedSchemeCount,
    int ReusedNodeCount,
    int ReusedSchemeCount,
    bool DirtyEditRecovered,
    IReadOnlyDictionary<string, string> NodeIdMapping,
    IReadOnlyDictionary<string, string> SchemeIdMapping);

public sealed record ProjectMutationResponse(
    ProjectDescriptor Project,
    LegacyModelImportResult LegacyModelImport,
    string TransactionId,
    string AuditEventId,
    bool Replayed,
    string TraceId);

public sealed record ProjectRecovery(
    IReadOnlyDictionary<string, int> Artifacts,
    IReadOnlyDictionary<string, int> Sessions,
    IReadOnlyList<string> InterruptedRuns,
    LegacyModelImportResult LegacyModelImport);

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

public enum SessionDataSourceKind
{
    [System.Text.Json.Serialization.JsonStringEnumMemberName("canonical_bundle")]
    CanonicalBundle,
    [System.Text.Json.Serialization.JsonStringEnumMemberName("simulator_raw")]
    SimulatorRaw,
}

public enum UnitProvenance
{
    [System.Text.Json.Serialization.JsonStringEnumMemberName("source")]
    Source,
    [System.Text.Json.Serialization.JsonStringEnumMemberName("profile")]
    Profile,
    [System.Text.Json.Serialization.JsonStringEnumMemberName("undeclared")]
    Undeclared,
}

public sealed record RawSourceFile(
    string RelativePath,
    long ByteSize,
    string Sha256);

public sealed record RawFieldMapping(
    string SourcePath,
    string SourceField,
    string CanonicalField,
    string Modality,
    string PhysicalDtype,
    string? DeclaredUnit,
    UnitProvenance UnitProvenance,
    string TimestampRole,
    string ResolutionStatus);

public sealed record RawModalityProposal(
    string Modality,
    StreamStatus Status,
    IReadOnlyList<string> Paths,
    string Format,
    string SchemaId,
    string ClockId,
    double? SampleRateHz,
    IReadOnlyDictionary<string, string> DeclaredUnits,
    string UnitHandling);

public sealed record RawAnnotationMapping(
    string RecordField,
    string? SourcePath,
    string CanonicalPath,
    string? SourceSchemaId,
    long RecordCount,
    string Disposition);

public sealed record RawRequiredInput(
    string InputId,
    string Label,
    string Reason);

public sealed record RawSessionInspection(
    string ContractVersion,
    string SourceSnapshotFingerprint,
    string DetectedProfileId,
    IReadOnlyList<string> ProfileCandidates,
    IReadOnlyList<RawSourceFile> Files,
    IReadOnlyList<RawFieldMapping> FieldMappings,
    IReadOnlyDictionary<string, RawModalityProposal> ModalityProposals,
    IReadOnlyList<RawAnnotationMapping> AnnotationMappings,
    IReadOnlyList<RawRequiredInput> RequiredUserInputs,
    IReadOnlyList<DomainIssue> Warnings,
    bool CanMaterialize);

public sealed record SessionSourceInspectRequest(string ExternalSource);

public sealed record SessionSourceInspectionResponse(
    string ContractVersion,
    SessionDataSourceKind SourceKind,
    IngestionReadinessReport? Report,
    RawSessionInspection? Raw,
    string TraceId);

public sealed record SessionSourceImportRequest(
    string TransactionId,
    string Actor,
    string ExternalSource,
    string InspectedFingerprint);

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
