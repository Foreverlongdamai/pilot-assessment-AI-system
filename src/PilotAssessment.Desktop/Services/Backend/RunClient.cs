using System.Text.Json;
using System.Text.Json.Serialization.Metadata;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.Protocol;
using PilotAssessment.Desktop.Core.ViewModels;

namespace PilotAssessment.Desktop.Services.Backend;

public sealed class RunClient : IRunGateway, IDisposable
{
    private readonly BackendConnectionService _backend;
    private readonly object _clientGate = new();
    private JsonRpcClient? _subscribedClient;
    private int _disposed;

    public RunClient(BackendConnectionService backend)
    {
        _backend = backend;
        _backend.ClientChanged += OnClientChanged;
        BindClient(_backend.Client);
    }

    public event EventHandler<RunEventReceivedEventArgs>? RunEventReceived;

    public async Task<CurrentModelRunPreflightReport> PreflightAsync(
        string sessionRevisionId,
        string schemeId,
        RunPurpose purpose,
        IReadOnlyDictionary<string, JsonElement> runtimeParameters,
        CancellationToken cancellationToken = default)
    {
        var response = await InvokeAsync(
            "model.run.preflight",
            new CurrentModelRunPreflightRequest(
                sessionRevisionId,
                schemeId,
                purpose,
                runtimeParameters),
            PilotAssessmentJsonContext.Default.CurrentModelRunPreflightRequest,
            PilotAssessmentJsonContext.Default.CurrentModelRunPreflightResponse,
            cancellationToken);
        return response.Preflight;
    }

    public async Task<IReadOnlyList<CurrentModelRunListItem>> ListCurrentRunsAsync(
        CancellationToken cancellationToken = default)
    {
        var response = await InvokeAsync(
            "model.run.list",
            PilotAssessmentJsonContext.Default.CurrentModelRunListResponse,
            cancellationToken);
        return response.Runs;
    }

    public async Task<AssessmentRunV2> StartAsync(
        string preflightId,
        string runId,
        int expectedSchemeRevision,
        string actor,
        string transactionId,
        CancellationToken cancellationToken = default)
    {
        var request = new CurrentModelRunStartRequest(
            preflightId,
            runId,
            expectedSchemeRevision,
            actor,
            transactionId);
        var response = await IdempotentRequestRetry.ExecuteAsync(
            transactionId,
            (_, token) => InvokeAsync(
                "model.run.start",
                request,
                PilotAssessmentJsonContext.Default.CurrentModelRunStartRequest,
                PilotAssessmentJsonContext.Default.CurrentModelRunMutationResponse,
                token),
            cancellationToken: cancellationToken);
        return response.Run;
    }

    public Task<CurrentModelRunStatusResponse> GetStatusAsync(
        string runId,
        CancellationToken cancellationToken = default) =>
        InvokeAsync(
            "run.status",
            new RunStatusRequest(runId),
            PilotAssessmentJsonContext.Default.RunStatusRequest,
            PilotAssessmentJsonContext.Default.CurrentModelRunStatusResponse,
            cancellationToken);

    public async Task<IReadOnlyList<RunEvent>> ListEventsAsync(
        string runId,
        int afterSequence,
        CancellationToken cancellationToken = default)
    {
        var response = await InvokeAsync(
            "run.events.list",
            new RunEventsListRequest(runId, afterSequence),
            PilotAssessmentJsonContext.Default.RunEventsListRequest,
            PilotAssessmentJsonContext.Default.RunEventsListResponse,
            cancellationToken);
        return response.Events;
    }

    public async Task<AssessmentRunV2> CancelAsync(
        string runId,
        string actor,
        string transactionId,
        CancellationToken cancellationToken = default)
    {
        var request = new RunCancelRequest(runId, actor, transactionId);
        var response = await IdempotentRequestRetry.ExecuteAsync(
            transactionId,
            (_, token) => InvokeAsync(
                "run.cancel",
                request,
                PilotAssessmentJsonContext.Default.RunCancelRequest,
                PilotAssessmentJsonContext.Default.CurrentModelRunCancelResponse,
                token),
            cancellationToken: cancellationToken);
        return response.Run;
    }

    public async Task<RunResultEnvelope> GetResultAsync(
        string? resultId,
        string? runId,
        CancellationToken cancellationToken = default)
    {
        if ((resultId is null) == (runId is null))
        {
            throw new ArgumentException("Provide exactly one result ID or run ID.");
        }

        var response = await InvokeAsync(
            "result.get",
            new RunResultGetRequest(resultId, runId),
            PilotAssessmentJsonContext.Default.RunResultGetRequest,
            PilotAssessmentJsonContext.Default.RunResultGetResponse,
            cancellationToken);
        return response.Result;
    }

    public async Task<ManagedArtifact> GetArtifactAsync(
        string resultId,
        string artifactId,
        CancellationToken cancellationToken = default)
    {
        var response = await InvokeAsync(
            "result.artifact.get",
            new RunResultArtifactGetRequest(resultId, artifactId),
            PilotAssessmentJsonContext.Default.RunResultArtifactGetRequest,
            PilotAssessmentJsonContext.Default.RunResultArtifactGetResponse,
            cancellationToken);
        if (!response.ReadOnly)
        {
            throw new InvalidDataException("Run result artifacts must be read-only.");
        }

        return response.Artifact;
    }

    public async Task<IReadOnlyList<string>> GetComponentSourceIdsAsync(
        ComponentIdRef component,
        CancellationToken cancellationToken = default)
    {
        var response = await InvokeAsync(
            "component.version.get",
            new ComponentVersionGetRequest(component.Kind, component.VersionId),
            PilotAssessmentJsonContext.Default.ComponentVersionGetRequest,
            PilotAssessmentJsonContext.Default.ComponentVersionGetResponse,
            cancellationToken);
        if (!response.Version.TryGetProperty("lineage", out var lineage) ||
            !lineage.TryGetProperty("source_version_ids", out var sources) ||
            sources.ValueKind is not JsonValueKind.Array)
        {
            return [];
        }

        return sources.EnumerateArray()
            .Where(item => item.ValueKind is JsonValueKind.String)
            .Select(item => item.GetString())
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .Cast<string>()
            .ToArray();
    }

    public Task<RuntimeStatusResponse> GetRuntimeStatusAsync(
        CancellationToken cancellationToken = default) =>
        InvokeAsync(
            "runtime.status",
            PilotAssessmentJsonContext.Default.RuntimeStatusResponse,
            cancellationToken);

    public Task<CapabilityCatalogResponse> GetCapabilitiesAsync(
        CancellationToken cancellationToken = default) =>
        InvokeAsync(
            "capabilities.list",
            PilotAssessmentJsonContext.Default.CapabilityCatalogResponse,
            cancellationToken);

    public async Task<IReadOnlyList<AuditEvent>> ListAuditEventsAsync(
        int limit,
        CancellationToken cancellationToken = default)
    {
        var response = await InvokeAsync(
            "audit.events.list",
            new AuditEventsListRequest(null, null, null, null, limit, 0),
            PilotAssessmentJsonContext.Default.AuditEventsListRequest,
            PilotAssessmentJsonContext.Default.AuditEventsListResponse,
            cancellationToken);
        return response.Events;
    }

    public void Dispose()
    {
        if (Interlocked.Exchange(ref _disposed, 1) != 0)
        {
            return;
        }

        _backend.ClientChanged -= OnClientChanged;
        BindClient(null);
    }

    private JsonRpcClient Client =>
        _backend.Client ?? throw new InvalidOperationException("The assessment backend is not connected.");

    private async Task<TResponse> InvokeAsync<TRequest, TResponse>(
        string method,
        TRequest request,
        JsonTypeInfo<TRequest> requestType,
        JsonTypeInfo<TResponse> responseType,
        CancellationToken cancellationToken)
    {
        var parameters = JsonSerializer.SerializeToElement(request, requestType);
        var result = await Client.InvokeAsync(method, parameters, cancellationToken)
            .ConfigureAwait(false);
        return JsonSerializer.Deserialize(result, responseType)
            ?? throw new JsonException($"The {method} response was empty.");
    }

    private async Task<TResponse> InvokeAsync<TResponse>(
        string method,
        JsonTypeInfo<TResponse> responseType,
        CancellationToken cancellationToken)
    {
        var result = await Client.InvokeAsync(method, cancellationToken: cancellationToken)
            .ConfigureAwait(false);
        return JsonSerializer.Deserialize(result, responseType)
            ?? throw new JsonException($"The {method} response was empty.");
    }

    private void OnClientChanged(object? sender, BackendClientChangedEventArgs args) =>
        BindClient(args.Client);

    private void BindClient(JsonRpcClient? client)
    {
        lock (_clientGate)
        {
            if (ReferenceEquals(_subscribedClient, client))
            {
                return;
            }

            if (_subscribedClient is not null)
            {
                _subscribedClient.NotificationReceived -= OnNotificationReceived;
            }

            _subscribedClient = client;
            if (_subscribedClient is not null)
            {
                _subscribedClient.NotificationReceived += OnNotificationReceived;
            }
        }
    }

    private void OnNotificationReceived(object? sender, JsonRpcNotificationMessage notification)
    {
        if (notification.Method is not (
                "run.progress" or
                "run.completed" or
                "run.failed" or
                "run.cancelled" or
                "run.interrupted") ||
            notification.Params is not { } parameters)
        {
            return;
        }

        try
        {
            var runEvent = JsonSerializer.Deserialize(
                parameters,
                PilotAssessmentJsonContext.Default.RunEvent);
            if (runEvent is not null)
            {
                RunEventReceived?.Invoke(this, new RunEventReceivedEventArgs(runEvent));
            }
        }
        catch (JsonException)
        {
            // Invalid notifications are visible through the protocol diagnostics;
            // they must not terminate the client reader or mutate UI state.
        }
    }
}
