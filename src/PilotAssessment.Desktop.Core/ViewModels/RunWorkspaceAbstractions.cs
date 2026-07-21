using PilotAssessment.Desktop.Core.Contracts;

namespace PilotAssessment.Desktop.Core.ViewModels;

public sealed class RunEventReceivedEventArgs : EventArgs
{
    public RunEventReceivedEventArgs(RunEvent runEvent)
    {
        RunEvent = runEvent;
    }

    public RunEvent RunEvent { get; }
}

public interface IRunGateway
{
    event EventHandler<RunEventReceivedEventArgs>? RunEventReceived;

    Task<CurrentModelRunPreflightReport> PreflightAsync(
        string sessionRevisionId,
        string schemeId,
        RunPurpose purpose,
        IReadOnlyDictionary<string, System.Text.Json.JsonElement> runtimeParameters,
        CancellationToken cancellationToken = default);

    Task<IReadOnlyList<CurrentModelRunListItem>> ListCurrentRunsAsync(
        CancellationToken cancellationToken = default);

    Task<AssessmentRunV3> StartAsync(
        string preflightId,
        string runId,
        int expectedSchemeRevision,
        string actor,
        string transactionId,
        CancellationToken cancellationToken = default);

    Task<CurrentModelRunStatusResponse> GetStatusAsync(
        string runId,
        CancellationToken cancellationToken = default);

    Task<IReadOnlyList<RunEvent>> ListEventsAsync(
        string runId,
        int afterSequence,
        CancellationToken cancellationToken = default);

    Task<AssessmentRunV3> CancelAsync(
        string runId,
        string actor,
        string transactionId,
        CancellationToken cancellationToken = default);

    Task<RunResultEnvelope> GetResultAsync(
        string? resultId,
        string? runId,
        CancellationToken cancellationToken = default);

    Task<ManagedArtifact> GetArtifactAsync(
        string resultId,
        string artifactId,
        CancellationToken cancellationToken = default);

    Task<IReadOnlyList<string>> GetComponentSourceIdsAsync(
        ComponentIdRef component,
        CancellationToken cancellationToken = default);

    Task<RuntimeStatusResponse> GetRuntimeStatusAsync(
        CancellationToken cancellationToken = default);

    Task<CapabilityCatalogResponse> GetCapabilitiesAsync(
        CancellationToken cancellationToken = default);

    Task<IReadOnlyList<AuditEvent>> ListAuditEventsAsync(
        int limit,
        CancellationToken cancellationToken = default);
}

public interface IManagedArtifactReader
{
    Task<string> ReadTextAsync(
        ManagedArtifact artifact,
        long maxBytes,
        CancellationToken cancellationToken = default);

    string ResolvePath(ManagedArtifact artifact);

    Task OpenAsync(
        ManagedArtifact artifact,
        CancellationToken cancellationToken = default);
}
