using System.Text.Json.Nodes;
using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.Contracts;

public enum ComponentKind
{
    [JsonStringEnumMemberName("evidence_concept")]
    EvidenceConcept,
    [JsonStringEnumMemberName("evidence_version")]
    EvidenceVersion,
    [JsonStringEnumMemberName("bn_node_concept")]
    BnNodeConcept,
    [JsonStringEnumMemberName("bn_node_version")]
    BnNodeVersion,
    [JsonStringEnumMemberName("evidence_binding_version")]
    EvidenceBindingVersion,
    [JsonStringEnumMemberName("cpt_version")]
    CptVersion,
    [JsonStringEnumMemberName("task_profile_version")]
    TaskProfileVersion,
    [JsonStringEnumMemberName("coverage_reporting_policy_version")]
    CoverageReportingPolicyVersion,
    [JsonStringEnumMemberName("layout_version")]
    LayoutVersion,
    [JsonStringEnumMemberName("assessment_scheme_version")]
    AssessmentSchemeVersion,
    [JsonStringEnumMemberName("source_descriptor")]
    SourceDescriptor,
}

public enum RunPurpose
{
    [JsonStringEnumMemberName("preview")]
    Preview,
    [JsonStringEnumMemberName("software_test")]
    SoftwareTest,
    [JsonStringEnumMemberName("assessment")]
    Assessment,
}

public enum TechnicalDisposition
{
    [JsonStringEnumMemberName("ready")]
    Ready,
    [JsonStringEnumMemberName("blocked")]
    Blocked,
}

public enum RunDiagnosticSeverity
{
    [JsonStringEnumMemberName("info")]
    Info,
    [JsonStringEnumMemberName("warning")]
    Warning,
    [JsonStringEnumMemberName("error")]
    Error,
}

public enum RunState
{
    [JsonStringEnumMemberName("queued")]
    Queued,
    [JsonStringEnumMemberName("running")]
    Running,
    [JsonStringEnumMemberName("cancelling")]
    Cancelling,
    [JsonStringEnumMemberName("cancelled")]
    Cancelled,
    [JsonStringEnumMemberName("completed")]
    Completed,
    [JsonStringEnumMemberName("failed")]
    Failed,
    [JsonStringEnumMemberName("interrupted")]
    Interrupted,
}

public enum RunStage
{
    [JsonStringEnumMemberName("queued")]
    Queued,
    [JsonStringEnumMemberName("snapshot_validation")]
    SnapshotValidation,
    [JsonStringEnumMemberName("ingestion")]
    Ingestion,
    [JsonStringEnumMemberName("synchronization")]
    Synchronization,
    [JsonStringEnumMemberName("evidence")]
    Evidence,
    [JsonStringEnumMemberName("inference")]
    Inference,
    [JsonStringEnumMemberName("reporting")]
    Reporting,
    [JsonStringEnumMemberName("completed")]
    Completed,
}

public enum RunScientificStatus
{
    [JsonStringEnumMemberName("not_supported")]
    NotSupported,
    [JsonStringEnumMemberName("engineering_default")]
    EngineeringDefault,
    [JsonStringEnumMemberName("expert_reviewed")]
    ExpertReviewed,
    [JsonStringEnumMemberName("calibrated")]
    Calibrated,
    [JsonStringEnumMemberName("internally_validated")]
    InternallyValidated,
    [JsonStringEnumMemberName("externally_validated")]
    ExternallyValidated,
}

public sealed record PinnedComponentRef(
    ComponentKind Kind,
    string VersionId,
    string ContentHash);

public sealed record RunDiagnostic(
    string Code,
    RunDiagnosticSeverity Severity,
    string Location,
    string Message,
    IReadOnlyDictionary<string, JsonNode?> Details);

public sealed record ExecutableIdentity(
    string IdentityId,
    string Version,
    string ContentHash);

public sealed record SourceChangeSummary(
    string[] Added,
    string[] Modified,
    string[] Deleted);

public sealed record PythonRuntimeIdentity(
    string Implementation,
    string Version,
    string ExecutableName,
    string ExecutableSha256,
    bool PrivateRuntime,
    string IdentitySha256);

public sealed record DependencyManifestIdentity(
    int PackageCount,
    string ManifestSha256);

public sealed record OperatorCatalogIdentity(
    int OperatorCount,
    string CatalogSha256);

public sealed record BackendSourceIdentity(
    string ContractId,
    string ContractVersion,
    string IdentityAlgorithm,
    string TreeAlgorithm,
    string ActiveSourceRoot,
    string SourceTreeSha256,
    int SourceFileCount,
    string? ReleaseBaselineSha256,
    bool BaselineAvailable,
    bool? LocallyModified,
    SourceChangeSummary BaselineChanges,
    string PyprojectSha256,
    string UvLockSha256,
    PythonRuntimeIdentity PythonRuntime,
    DependencyManifestIdentity Dependencies,
    OperatorCatalogIdentity OperatorCatalog,
    string IdentitySha256);

public sealed record BackendSourceDiskStatus(
    string ContractId,
    string ContractVersion,
    BackendSourceIdentity LoadedIdentity,
    string DiskSourceTreeSha256,
    string DiskPyprojectSha256,
    string DiskUvLockSha256,
    SourceChangeSummary LoadedToDiskChanges,
    bool RuntimeRestartRequired);

public sealed record ModelNodeSnapshotRef(
    string NodeId,
    ModelNodeKind NodeKind,
    int SemanticRevision,
    string ContentHash);

public sealed record RunPreflightReport(
    string ContractId,
    string ContractVersion,
    string PreflightId,
    SessionRevisionRef SessionRevisionRef,
    PinnedComponentRef SchemeRef,
    TechnicalDisposition TechnicalDisposition,
    bool FormalRunAuthorized,
    bool SyntheticData,
    PinnedComponentRef[] LockedComponentRefs,
    RunDiagnostic[] Diagnostics,
    string PreflightHash);

public sealed record CurrentModelRunPreflightReport(
    string ContractId,
    string ContractVersion,
    string PreflightId,
    SessionRevisionRef SessionRevisionRef,
    string SchemeId,
    int SchemeSemanticRevision,
    string SchemeContentHash,
    ModelNodeSnapshotRef[] ActiveNodeRefs,
    TechnicalDisposition TechnicalDisposition,
    bool FormalRunAuthorized,
    bool SyntheticData,
    RunDiagnostic[] Diagnostics,
    RunPreflightReport? ExecutionPreflight,
    string PreflightHash,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    BackendSourceIdentity? BackendSourceIdentity = null,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    ArtifactIdRef? SourceSnapshotRef = null);

public sealed record RunSnapshot(
    string ContractId,
    string ContractVersion,
    string RunId,
    RunPurpose Purpose,
    SessionRevisionRef SessionRevisionRef,
    PinnedComponentRef SchemeRef,
    PinnedComponentRef[] LockedComponentRefs,
    PinnedComponentRef[] LockedSourceRefs,
    ExecutableIdentity[] LockedOperatorIdentities,
    ExecutableIdentity EngineIdentity,
    ExecutableIdentity[] NumericRuntimeIdentities,
    string RuntimeParametersHash,
    string PreflightHash,
    string SnapshotHash);

public sealed record CurrentModelRunSnapshot(
    string ContractId,
    string ContractVersion,
    string RunId,
    RunPurpose Purpose,
    SessionRevisionRef SessionRevisionRef,
    TaskScheme Scheme,
    ModelNode[] ActiveNodes,
    ExecutableIdentity[] LockedOperatorIdentities,
    ExecutableIdentity EngineIdentity,
    ExecutableIdentity[] NumericRuntimeIdentities,
    string RuntimeParametersHash,
    string PreflightHash,
    RunSnapshot ExecutionSnapshot,
    string SnapshotHash,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    BackendSourceIdentity? BackendSourceIdentity = null,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    ArtifactIdRef? SourceSnapshotRef = null);

public sealed record AssessmentRun(
    string ContractId,
    string ContractVersion,
    string RunId,
    RunSnapshot Snapshot,
    RunState State,
    RunStage Stage,
    int ProgressSequence,
    DateTime RequestedAt,
    DateTime? StartedAt,
    DateTime? FinishedAt,
    DateTime? CancellationRequestedAt);

public sealed record AssessmentRunV2(
    string ContractId,
    string ContractVersion,
    string RunId,
    CurrentModelRunSnapshot Snapshot,
    RunState State,
    RunStage Stage,
    int ProgressSequence,
    DateTime RequestedAt,
    DateTime? StartedAt,
    DateTime? FinishedAt,
    DateTime? CancellationRequestedAt);

public sealed record RunEvent(
    string ContractId,
    string ContractVersion,
    string EventId,
    string RunId,
    int Sequence,
    RunState State,
    RunStage Stage,
    int CompletedUnits,
    int TotalUnits,
    string Message,
    DateTime OccurredAt,
    IReadOnlyDictionary<string, JsonNode?> Details);

public sealed record RunResultEnvelope(
    string ContractId,
    string ContractVersion,
    string ResultId,
    string RunId,
    string SnapshotHash,
    ArtifactIdRef[] EvidenceResultRefs,
    ArtifactIdRef[] EvidenceTraceRefs,
    ArtifactIdRef ObservationSetRef,
    ArtifactIdRef PosteriorRef,
    ArtifactIdRef InferenceTraceRef,
    ArtifactIdRef[] ReportingRefs,
    ArtifactIdRef[] CoverageRefs,
    RunScientificStatus ScientificStatus,
    string ResultHash);
