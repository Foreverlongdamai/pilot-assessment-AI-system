using System.Text.Json;
using System.Text.Json.Serialization.Metadata;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.Protocol;
using PilotAssessment.Desktop.Core.ViewModels;

namespace PilotAssessment.Desktop.Services.Backend;

public sealed class ModelWorkspaceClient : IModelWorkspaceGateway
{
    private readonly BackendConnectionService _backend;

    public ModelWorkspaceClient(BackendConnectionService backend)
    {
        _backend = backend;
    }

    public async Task<IReadOnlyList<TaskScheme>> ListSchemesAsync(
        CancellationToken cancellationToken = default)
    {
        var response = await InvokeAsync(
            "model.scheme.list",
            PilotAssessmentJsonContext.Default.TaskSchemeListResponse,
            cancellationToken);
        return response.Schemes;
    }

    public Task<TaskSchemeMutationResponse> CreateSchemeAsync(
        TaskScheme scheme,
        string actor,
        CancellationToken cancellationToken = default)
    {
        var transactionId = NewTransactionId("scheme-create");
        return MutateAsync(
            "model.scheme.create",
            transactionId,
            new TaskSchemeCreateRequest(scheme, actor, transactionId),
            PilotAssessmentJsonContext.Default.TaskSchemeCreateRequest,
            cancellationToken);
    }

    public Task<TaskSchemeMutationResponse> CopySchemeAsync(
        string sourceSchemeId,
        string newSchemeId,
        string? nameZh,
        string? nameEn,
        string actor,
        CancellationToken cancellationToken = default)
    {
        var transactionId = NewTransactionId("scheme-copy");
        return MutateAsync(
            "model.scheme.copy",
            transactionId,
            new TaskSchemeCopyRequest(
                sourceSchemeId,
                newSchemeId,
                nameZh,
                nameEn,
                actor,
                transactionId),
            PilotAssessmentJsonContext.Default.TaskSchemeCopyRequest,
            cancellationToken);
    }

    public Task<TaskSchemeMutationResponse> UpdateSchemeAsync(
        TaskScheme scheme,
        int? expectedSemanticRevision,
        int? expectedLayoutRevision,
        string actor,
        CancellationToken cancellationToken = default)
    {
        var transactionId = NewTransactionId("scheme-update");
        return MutateAsync(
            "model.scheme.update",
            transactionId,
            new TaskSchemeUpdateRequest(
                scheme,
                expectedSemanticRevision,
                expectedLayoutRevision,
                actor,
                transactionId),
            PilotAssessmentJsonContext.Default.TaskSchemeUpdateRequest,
            cancellationToken);
    }

    public Task<TaskSchemeMutationResponse> ArchiveSchemeAsync(
        string schemeId,
        int expectedSemanticRevision,
        string actor,
        CancellationToken cancellationToken = default)
    {
        var transactionId = NewTransactionId("scheme-archive");
        return MutateAsync(
            "model.scheme.archive",
            transactionId,
            new TaskSchemeArchiveRequest(
                schemeId,
                expectedSemanticRevision,
                actor,
                transactionId),
            PilotAssessmentJsonContext.Default.TaskSchemeArchiveRequest,
            cancellationToken);
    }

    private JsonRpcClient Client => _backend.Client
        ?? throw new InvalidOperationException("The local assessment backend is not connected.");

    private Task<TaskSchemeMutationResponse> MutateAsync<TRequest>(
        string method,
        string transactionId,
        TRequest request,
        JsonTypeInfo<TRequest> requestType,
        CancellationToken cancellationToken) =>
        IdempotentRequestRetry.ExecuteAsync(
            transactionId,
            (_, token) => InvokeAsync(
                method,
                request,
                requestType,
                PilotAssessmentJsonContext.Default.TaskSchemeMutationResponse,
                token),
            cancellationToken: cancellationToken);

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
