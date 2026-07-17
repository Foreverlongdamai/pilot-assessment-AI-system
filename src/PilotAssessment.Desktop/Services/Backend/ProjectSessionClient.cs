using System.Text.Json;
using System.Text.Json.Serialization.Metadata;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.Protocol;
using PilotAssessment.Desktop.Core.ViewModels;

namespace PilotAssessment.Desktop.Services.Backend;

public sealed class ProjectSessionClient : IProjectSessionGateway
{
    private readonly BackendConnectionService _backend;

    public ProjectSessionClient(BackendConnectionService backend)
    {
        _backend = backend;
    }

    public async Task<ProjectDescriptor> CreateProjectAsync(
        string root,
        string projectId,
        string name,
        string actor,
        CancellationToken cancellationToken = default)
    {
        var transactionId = NewTransactionId("project-create");
        var response = await IdempotentRequestRetry.ExecuteAsync(
            transactionId,
            (stableTransactionId, token) => InvokeAsync(
                "project.create",
                new ProjectCreateRequest(stableTransactionId, actor, root, projectId, name),
                PilotAssessmentJsonContext.Default.ProjectCreateRequest,
                PilotAssessmentJsonContext.Default.ProjectMutationResponse,
                token),
            cancellationToken: cancellationToken);
        return response.Project;
    }

    public async Task<ProjectDescriptor> OpenProjectAsync(
        string root,
        CancellationToken cancellationToken = default)
    {
        var response = await InvokeAsync(
            "project.open",
            new ProjectOpenRequest(root),
            PilotAssessmentJsonContext.Default.ProjectOpenRequest,
            PilotAssessmentJsonContext.Default.ProjectOpenResponse,
            cancellationToken);
        return response.Project;
    }

    public async Task CloseProjectAsync(CancellationToken cancellationToken = default)
    {
        _ = await InvokeAsync(
            "project.close",
            PilotAssessmentJsonContext.Default.ProjectCloseResponse,
            cancellationToken);
    }

    public async Task<IngestionReadinessReport> InspectSessionAsync(
        string externalBundle,
        CancellationToken cancellationToken = default)
    {
        var response = await InvokeAsync(
            "session.inspect",
            new SessionInspectRequest(externalBundle),
            PilotAssessmentJsonContext.Default.SessionInspectRequest,
            PilotAssessmentJsonContext.Default.SessionInspectResponse,
            cancellationToken);
        return response.Report;
    }

    public Task<SessionImportResponse> ImportSessionAsync(
        string externalBundle,
        string actor,
        CancellationToken cancellationToken = default)
    {
        var transactionId = NewTransactionId("session-import");
        return IdempotentRequestRetry.ExecuteAsync(
            transactionId,
            (stableTransactionId, token) => InvokeAsync(
                "session.import",
                new SessionImportRequest(stableTransactionId, actor, externalBundle),
                PilotAssessmentJsonContext.Default.SessionImportRequest,
                PilotAssessmentJsonContext.Default.SessionImportResponse,
                token),
            cancellationToken: cancellationToken);
    }

    public async Task<IReadOnlyList<SessionCollectionItem>> ListSessionsAsync(
        CancellationToken cancellationToken = default)
    {
        var response = await InvokeAsync(
            "session.list",
            PilotAssessmentJsonContext.Default.SessionListResponse,
            cancellationToken);
        return response.Sessions;
    }

    public async Task<StoredIngestionReport> GetIngestionReportAsync(
        string sessionRevisionId,
        CancellationToken cancellationToken = default)
    {
        var response = await InvokeAsync(
            "session.report.get",
            new SessionReportRequest(sessionRevisionId, "ingestion_readiness"),
            PilotAssessmentJsonContext.Default.SessionReportRequest,
            PilotAssessmentJsonContext.Default.SessionReportResponse,
            cancellationToken);
        IngestionReadinessReport? report = null;
        if (response.Report is JsonElement { ValueKind: JsonValueKind.Object } reportElement)
        {
            report = reportElement.Deserialize(
                PilotAssessmentJsonContext.Default.IngestionReadinessReport)
                ?? throw new JsonException("The stored ingestion report was empty.");
        }

        return new StoredIngestionReport(
            response.SessionRevisionId,
            response.Artifact,
            response.InlineAvailable,
            report);
    }

    private JsonRpcClient Client => _backend.Client
        ?? throw new InvalidOperationException("The local assessment backend is not connected.");

    private async Task<TResponse> InvokeAsync<TRequest, TResponse>(
        string method,
        TRequest request,
        JsonTypeInfo<TRequest> requestType,
        JsonTypeInfo<TResponse> responseType,
        CancellationToken cancellationToken)
    {
        var parameters = JsonSerializer.SerializeToElement(request, requestType);
        var result = await Client.InvokeAsync(method, parameters, cancellationToken);
        return result.Deserialize(responseType)
            ?? throw new JsonException($"The {method} response was empty.");
    }

    private async Task<TResponse> InvokeAsync<TResponse>(
        string method,
        JsonTypeInfo<TResponse> responseType,
        CancellationToken cancellationToken)
    {
        var result = await Client.InvokeAsync(method, cancellationToken: cancellationToken);
        return result.Deserialize(responseType)
            ?? throw new JsonException($"The {method} response was empty.");
    }

    private static string NewTransactionId(string operation) =>
        $"tx.desktop.{operation}.{Guid.NewGuid():N}";
}
