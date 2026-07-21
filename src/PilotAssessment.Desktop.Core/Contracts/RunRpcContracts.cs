using System.Text.Json;
using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.Contracts;

public sealed record CurrentModelRunPreflightRequest(
    string SessionRevisionId,
    string SchemeId,
    RunPurpose Purpose,
    IReadOnlyDictionary<string, JsonElement> RuntimeParameters);

public sealed record CurrentModelRunPreflightResponse(
    CurrentModelRunPreflightReport Preflight,
    string TraceId);

public sealed record CurrentModelRunStartRequest(
    string PreflightId,
    string RunId,
    int ExpectedSchemeRevision,
    string Actor,
    string TransactionId);

public sealed record CurrentModelRunMutationResponse(
    AssessmentRunV2 Run,
    string TransactionId,
    string AuditEventId,
    bool Replayed,
    string TraceId);

public sealed record CurrentModelRunListItem(
    AssessmentRunV2 Run,
    string? ResultId);

public sealed record CurrentModelRunListResponse(
    CurrentModelRunListItem[] Runs,
    string TraceId);

public sealed record RunStatusRequest(string RunId);

public sealed record CurrentModelRunStatusResponse(
    AssessmentRunV2 Run,
    string? ResultId,
    string TraceId);

public sealed record RunEventsListRequest(
    string RunId,
    int AfterSequence);

public sealed record RunEventsListResponse(
    RunEvent[] Events,
    string TraceId);

public sealed record RunCancelRequest(
    string RunId,
    string Actor,
    string TransactionId);

public sealed record CurrentModelRunCancelResponse(
    AssessmentRunV2 Run,
    string TransactionId,
    string AuditEventId,
    bool Replayed,
    string TraceId);

public sealed record RunResultGetRequest(
    string? ResultId,
    string? RunId);

public sealed record RunResultGetResponse(
    RunResultEnvelope Result,
    string TraceId);

public sealed record RunResultArtifactGetRequest(
    string ResultId,
    string ArtifactId);

public sealed record RunResultArtifactGetResponse(
    ManagedArtifact Artifact,
    bool ReadOnly,
    string TraceId);

public sealed record SystemModelRuntimeStatus(
    string ModelLibraryId,
    string ModelIdentitySha256,
    string FormatVersion,
    int DatabaseSchemaVersion,
    int NodeCount,
    int SchemeCount,
    bool EditSessionDirty,
    string[] RecoveryDiagnostics);

public sealed record ProjectCompatibilityStatus(
    string ProjectId,
    string FormatVersion,
    int DatabaseSchemaVersion,
    string Compatibility,
    string[] RecoveryDiagnostics,
    int RecoveredRunCount);

public sealed record RuntimeStatusResponse(
    string State,
    bool ProjectOpen,
    string? ProjectId,
    string[] ActiveRunIds,
    string TraceId,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    bool? SystemReady = null,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    string? ModelLibraryId = null,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    BackendSourceDiskStatus? BackendSource = null,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    SystemModelRuntimeStatus? SystemModel = null,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    ProjectCompatibilityStatus? ProjectCompatibility = null);

public sealed record CapabilityCatalogResponse(
    string[] Capabilities,
    string[] Methods,
    IReadOnlyDictionary<string, string[]> MethodFamilies,
    int MaxParallelAssessmentRuns,
    string TraceId);

public sealed record AuditEventsListRequest(
    string? EventType,
    string? SubjectKind,
    string? SubjectId,
    string? TransactionId,
    int Limit,
    int Offset);

public sealed record AuditEventsListResponse(
    AuditEvent[] Events,
    string TraceId);

public sealed record ComponentVersionGetRequest(
    ComponentKind Kind,
    string VersionId);

public sealed record ComponentVersionGetResponse(
    JsonElement Version,
    string TraceId);

public sealed record ComponentIdRef(
    ComponentKind Kind,
    string VersionId);

public enum ObservationKind
{
    [JsonStringEnumMemberName("hard")]
    Hard,
    [JsonStringEnumMemberName("virtual")]
    Virtual,
    [JsonStringEnumMemberName("omitted")]
    Omitted,
}

public sealed record BayesianObservation(
    ComponentIdRef VariableId,
    ObservationKind Kind,
    string? HardStateId,
    double[]? Likelihood);

public sealed record ObservationSet(
    string ContractId,
    string ContractVersion,
    string PlanHash,
    BayesianObservation[] Observations,
    string ObservationSetHash);

public sealed record PosteriorDistribution(
    ComponentIdRef VariableId,
    string[] OrderedStateIds,
    double[] Probabilities);

public sealed record PosteriorResult(
    string ContractId,
    string ContractVersion,
    PinnedComponentRef SchemeRef,
    string PlanHash,
    string ObservationSetHash,
    PosteriorDistribution[] Priors,
    PosteriorDistribution[] Posteriors,
    string ResultHash);

public sealed record InferenceFactorScope(ComponentIdRef[] VariableIds);

public sealed record InferenceInfluenceEdge(
    string EdgeKind,
    string EdgeId,
    ComponentIdRef ObservedVariableId,
    ComponentIdRef QueriedVariableId,
    string MethodId,
    double L1Delta,
    string[] CanonicalPath);

public sealed record InferenceTrace(
    string ContractId,
    string ContractVersion,
    PinnedComponentRef SchemeRef,
    string PlanHash,
    string ObservationSetHash,
    ComponentIdRef[] QueryVariableIds,
    ComponentIdRef[] ObservedVariableIds,
    ComponentIdRef[] EliminationOrder,
    InferenceFactorScope[] FactorScopes,
    InferenceInfluenceEdge[] InfluenceEdges,
    string TraceHash);

public sealed record EvidenceRuntimeResult(
    string ContractId,
    string ContractVersion,
    string EvidenceVersionId,
    string[] EvidenceBindingVersionIds,
    string CalculationStatus,
    JsonElement? PrimaryValue,
    IReadOnlyDictionary<string, JsonElement> ScoringOutputs,
    string[]? OmittedBindingIds = null);
