using System.Text.Json;
using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.Contracts;

public enum StreamStatus
{
    [JsonStringEnumMemberName("present")]
    Present,
    [JsonStringEnumMemberName("export_pending")]
    ExportPending,
    [JsonStringEnumMemberName("missing")]
    Missing,
    [JsonStringEnumMemberName("invalid")]
    Invalid,
    [JsonStringEnumMemberName("not_applicable")]
    NotApplicable,
}

public enum StreamReadiness
{
    [JsonStringEnumMemberName("ready")]
    Ready,
    [JsonStringEnumMemberName("unavailable")]
    Unavailable,
    [JsonStringEnumMemberName("invalid")]
    Invalid,
    [JsonStringEnumMemberName("unsupported")]
    Unsupported,
    [JsonStringEnumMemberName("not_applicable")]
    NotApplicable,
}

public enum ReadinessDisposition
{
    [JsonStringEnumMemberName("ready")]
    Ready,
    [JsonStringEnumMemberName("ready_partial")]
    ReadyPartial,
    [JsonStringEnumMemberName("blocked")]
    Blocked,
}

public enum ErrorSeverity
{
    [JsonStringEnumMemberName("info")]
    Info,
    [JsonStringEnumMemberName("warning")]
    Warning,
    [JsonStringEnumMemberName("error")]
    Error,
    [JsonStringEnumMemberName("fatal")]
    Fatal,
}

public sealed record DomainIssue(
    string ErrorCode,
    ErrorSeverity Severity,
    bool Recoverable,
    string Message,
    string? FieldOrPath,
    string? NodeOrAnchorId,
    string Remediation,
    string? RequestId,
    string? TraceId,
    string? TransactionId,
    IReadOnlyDictionary<string, JsonElement> Diagnostics,
    IReadOnlyDictionary<string, JsonElement> Extensions);

public sealed record SyntheticSourceProvenance(
    string GeneratorId,
    long Seed,
    string ScientificValidationStatus,
    string SourceXuSha256,
    string LockFingerprint,
    string ProvenanceScope,
    bool FormalAssessmentSupported);

public sealed record StreamReadinessResult(
    string Modality,
    StreamStatus DeclaredStatus,
    bool RequiredForImport,
    StreamReadiness Readiness,
    string? AdapterId,
    string? AdapterVersion,
    IReadOnlyList<string> SourcePaths,
    IReadOnlyDictionary<string, string> SourceChecksums,
    string? NormalizedSchemaId,
    long? RowCount,
    IReadOnlyDictionary<string, long> ArtifactRowCounts,
    double? SourceTimeStartS,
    double? SourceTimeEndS,
    double? ObservedSampleRateHz,
    IReadOnlyList<string> CanonicalFields,
    IReadOnlyDictionary<string, string> Units,
    IReadOnlyDictionary<string, JsonElement> QualitySummary,
    IReadOnlyList<string> Assumptions,
    IReadOnlyList<DomainIssue> Issues);

public sealed record IngestionReadinessReport(
    string ContractVersion,
    string ValidationScope,
    string SessionId,
    string ManifestVersion,
    string SourceClassification,
    SyntheticSourceProvenance? SyntheticProvenance,
    ReadinessDisposition Disposition,
    bool CanContinueToSynchronization,
    bool FormalRunAuthorized,
    IReadOnlyDictionary<string, StreamReadinessResult> StreamResults,
    StreamReadinessResult? TaskReferenceResult,
    IReadOnlyList<DomainIssue> GlobalIssues,
    IReadOnlyList<string> DeferredChecks,
    string SourceSnapshotFingerprint);
