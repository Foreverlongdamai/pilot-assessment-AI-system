using System.Text.Json;
using System.Text.Json.Serialization.Metadata;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.Protocol;
using PilotAssessment.Desktop.Core.ViewModels;

namespace PilotAssessment.Desktop.Services.Backend;

public sealed class ModelWorkspaceClient :
    IModelWorkspaceGateway,
    IModelGraphGateway,
    IModelNodeEditorGateway,
    IBayesianNodeEditorGateway,
    IModelEditSessionGateway
{
    private readonly BackendConnectionService _backend;

    public ModelWorkspaceClient(BackendConnectionService backend)
    {
        _backend = backend;
    }

    public async Task<ModelEditSessionStatus> GetEditStatusAsync(
        CancellationToken cancellationToken = default)
    {
        var response = await InvokeAsync(
            "model.edit.status",
            PilotAssessmentJsonContext.Default.ModelEditSessionStatusResponse,
            cancellationToken);
        return response.EditSession;
    }

    public Task<ModelEditSessionMutationResponse> UndoEditAsync(
        string actor,
        CancellationToken cancellationToken = default) =>
        MutateEditSessionAsync("model.edit.undo", "edit-undo", actor, cancellationToken);

    public Task<ModelEditSessionMutationResponse> RedoEditAsync(
        string actor,
        CancellationToken cancellationToken = default) =>
        MutateEditSessionAsync("model.edit.redo", "edit-redo", actor, cancellationToken);

    public Task<ModelEditSessionMutationResponse> CommitEditAsync(
        string actor,
        CancellationToken cancellationToken = default) =>
        MutateEditSessionAsync("model.edit.commit", "edit-commit", actor, cancellationToken);

    public Task<ModelEditSessionMutationResponse> DiscardEditAsync(
        string actor,
        CancellationToken cancellationToken = default) =>
        MutateEditSessionAsync("model.edit.discard", "edit-discard", actor, cancellationToken);

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
        string? name,
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
                name,
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

    public async Task<ModelGraphSnapshot> GetGraphAsync(
        string schemeId,
        CancellationToken cancellationToken = default)
    {
        var response = await InvokeAsync(
            "model.graph.get",
            new ModelGraphGetRequest(schemeId),
            PilotAssessmentJsonContext.Default.ModelGraphGetRequest,
            PilotAssessmentJsonContext.Default.ModelGraphGetResponse,
            cancellationToken);
        return response.Graph;
    }

    public Task<ModelNodeMutationResponse> CreateNodeAsync(
        ModelNode node,
        string actor,
        CancellationToken cancellationToken = default)
    {
        var transactionId = NewTransactionId("node-create");
        return MutateAsync(
            "model.node.create",
            transactionId,
            new ModelNodeCreateRequest(node, actor, transactionId),
            PilotAssessmentJsonContext.Default.ModelNodeCreateRequest,
            PilotAssessmentJsonContext.Default.ModelNodeMutationResponse,
            cancellationToken);
    }

    public async Task<IReadOnlyList<OperatorDefinition>> ListOperatorsAsync(
        CancellationToken cancellationToken = default)
    {
        var response = await InvokeAsync(
            "operator.catalog.list",
            PilotAssessmentJsonContext.Default.OperatorCatalogListResponse,
            cancellationToken);
        return response.Operators;
    }

    public Task<ModelNodeMutationResponse> UpdateNodeAsync(
        ModelNode node,
        int expectedSemanticRevision,
        int expectedLayoutRevision,
        string actor,
        string transactionId,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(transactionId);
        return MutateAsync(
            "model.node.update",
            transactionId,
            new ModelNodeUpdateRequest(
                node,
                expectedSemanticRevision,
                expectedLayoutRevision,
                actor,
                transactionId),
            PilotAssessmentJsonContext.Default.ModelNodeUpdateRequest,
            PilotAssessmentJsonContext.Default.ModelNodeMutationResponse,
            cancellationToken);
    }

    public async Task<IReadOnlyList<ModelNodeUsage>> ListNodeUsagesAsync(
        string nodeId,
        CancellationToken cancellationToken = default)
    {
        var response = await InvokeAsync(
            "model.node.usage.list",
            new ModelNodeUsageListRequest(nodeId),
            PilotAssessmentJsonContext.Default.ModelNodeUsageListRequest,
            PilotAssessmentJsonContext.Default.ModelNodeUsageListResponse,
            cancellationToken);
        return response.Usages;
    }

    public async Task<IReadOnlyList<ModelChangeEvent>> ListNodeHistoryAsync(
        string nodeId,
        CancellationToken cancellationToken = default)
    {
        var response = await InvokeAsync(
            "model.node.history.list",
            new ModelNodeHistoryListRequest(nodeId),
            PilotAssessmentJsonContext.Default.ModelNodeHistoryListRequest,
            PilotAssessmentJsonContext.Default.ModelNodeHistoryListResponse,
            cancellationToken);
        return response.Events;
    }

    public async Task<CurrentModelRunSnapshotV3> PreviewNodeAsync(
        string sessionRevisionId,
        string schemeId,
        string nodeId,
        IReadOnlyDictionary<string, JsonElement> runtimeParameters,
        CancellationToken cancellationToken = default)
    {
        var previewId = $"preview.desktop.{Guid.NewGuid():N}";
        var response = await InvokeAsync(
            "model.preview.node",
            new ModelNodePreviewRequest(
                sessionRevisionId,
                schemeId,
                nodeId,
                runtimeParameters,
                previewId),
            PilotAssessmentJsonContext.Default.ModelNodePreviewRequest,
            PilotAssessmentJsonContext.Default.ModelNodePreviewResponse,
            cancellationToken);
        return response.Preview;
    }

    public Task<TaskSchemeMutationResponse> ActivateNodeAsync(
        string schemeId,
        string nodeId,
        int expectedSemanticRevision,
        string actor,
        CancellationToken cancellationToken = default)
    {
        var transactionId = NewTransactionId("scheme-activate");
        return MutateAsync(
            "model.scheme.activate",
            transactionId,
            new SchemeNodeActivationRequest(
                schemeId,
                nodeId,
                expectedSemanticRevision,
                actor,
                transactionId),
            PilotAssessmentJsonContext.Default.SchemeNodeActivationRequest,
            PilotAssessmentJsonContext.Default.TaskSchemeMutationResponse,
            cancellationToken);
    }

    public async Task<DeactivationImpact> PreviewDeactivationAsync(
        string schemeId,
        string nodeId,
        CancellationToken cancellationToken = default)
    {
        var response = await InvokeAsync(
            "model.scheme.deactivation.preview",
            new SchemeDeactivationPreviewRequest(schemeId, nodeId),
            PilotAssessmentJsonContext.Default.SchemeDeactivationPreviewRequest,
            PilotAssessmentJsonContext.Default.SchemeDeactivationPreviewResponse,
            cancellationToken);
        return response.Impact;
    }

    public Task<TaskSchemeMutationResponse> DeactivateNodeAsync(
        string schemeId,
        string nodeId,
        int expectedSemanticRevision,
        string impactHash,
        string actor,
        CancellationToken cancellationToken = default)
    {
        var transactionId = NewTransactionId("scheme-deactivate");
        return MutateAsync(
            "model.scheme.deactivate",
            transactionId,
            new SchemeNodeDeactivationRequest(
                schemeId,
                nodeId,
                expectedSemanticRevision,
                impactHash,
                actor,
                transactionId),
            PilotAssessmentJsonContext.Default.SchemeNodeDeactivationRequest,
            PilotAssessmentJsonContext.Default.TaskSchemeMutationResponse,
            cancellationToken);
    }

    public Task<GraphBatchMutationResponse> ApplyGraphBatchAsync(
        string schemeId,
        IReadOnlyList<string> copyNodeIds,
        IReadOnlyList<string> activateNodeIds,
        IReadOnlyList<NodeLayout> layoutUpdates,
        int expectedSemanticRevision,
        int expectedLayoutRevision,
        string actor,
        CancellationToken cancellationToken = default)
    {
        var transactionId = NewTransactionId("graph-batch");
        return MutateAsync(
            "model.graph.batch.apply",
            transactionId,
            new GraphBatchApplyRequest(
                schemeId,
                copyNodeIds.ToArray(),
                activateNodeIds.ToArray(),
                layoutUpdates.ToArray(),
                expectedSemanticRevision,
                expectedLayoutRevision,
                actor,
                transactionId),
            PilotAssessmentJsonContext.Default.GraphBatchApplyRequest,
            PilotAssessmentJsonContext.Default.GraphBatchMutationResponse,
            cancellationToken);
    }

    public Task<GraphBatchMutationResponse> UpdateLayoutAsync(
        string schemeId,
        IReadOnlyList<NodeLayout> positions,
        int expectedSemanticRevision,
        int expectedLayoutRevision,
        string actor,
        CancellationToken cancellationToken = default)
    {
        var transactionId = NewTransactionId("layout-update");
        return MutateAsync(
            "model.layout.update",
            transactionId,
            new LayoutUpdateRequest(
                schemeId,
                positions.ToArray(),
                expectedSemanticRevision,
                expectedLayoutRevision,
                actor,
                transactionId),
            PilotAssessmentJsonContext.Default.LayoutUpdateRequest,
            PilotAssessmentJsonContext.Default.GraphBatchMutationResponse,
            cancellationToken);
    }

    public Task<CptMutationResponse> AddProbabilisticEdgeAsync(
        string childNodeId,
        string parentNodeId,
        string strategy,
        int expectedSemanticRevision,
        string actor,
        CancellationToken cancellationToken = default)
    {
        var transactionId = NewTransactionId("edge-add-probabilistic");
        return MutateAsync(
            "model.edge.add",
            transactionId,
            new ProbabilisticEdgeAddRequest(
                "probabilistic",
                childNodeId,
                parentNodeId,
                strategy,
                expectedSemanticRevision,
                actor,
                transactionId),
            PilotAssessmentJsonContext.Default.ProbabilisticEdgeAddRequest,
            PilotAssessmentJsonContext.Default.CptMutationResponse,
            cancellationToken);
    }

    public Task<CptMutationResponse> RemoveProbabilisticEdgeAsync(
        string childNodeId,
        string parentNodeId,
        string strategy,
        double[]? marginalWeights,
        int expectedSemanticRevision,
        string actor,
        CancellationToken cancellationToken = default)
    {
        var transactionId = NewTransactionId("edge-remove-probabilistic");
        return MutateAsync(
            "model.edge.remove",
            transactionId,
            new ProbabilisticEdgeRemoveRequest(
                "probabilistic",
                childNodeId,
                parentNodeId,
                strategy,
                marginalWeights,
                expectedSemanticRevision,
                actor,
                transactionId),
            PilotAssessmentJsonContext.Default.ProbabilisticEdgeRemoveRequest,
            PilotAssessmentJsonContext.Default.CptMutationResponse,
            cancellationToken);
    }

    public async Task<CptInspectResponse> InspectCptAsync(
        string nodeId,
        CancellationToken cancellationToken = default) =>
        await InvokeAsync(
            "model.cpt.validate",
            new CptInspectRequest(nodeId),
            PilotAssessmentJsonContext.Default.CptInspectRequest,
            PilotAssessmentJsonContext.Default.CptInspectResponse,
            cancellationToken);

    public Task<CptMutationResponse> UpdateCptRowsAsync(
        string nodeId,
        IReadOnlyList<IReadOnlyList<double>> rows,
        int expectedSemanticRevision,
        string actor,
        CancellationToken cancellationToken = default)
    {
        var transactionId = NewTransactionId("cpt-update");
        return MutateAsync(
            "model.cpt.update",
            transactionId,
            new CptRowsUpdateRequest(
                nodeId,
                rows.Select(row => row.ToArray()).ToArray(),
                expectedSemanticRevision,
                actor,
                transactionId),
            PilotAssessmentJsonContext.Default.CptRowsUpdateRequest,
            PilotAssessmentJsonContext.Default.CptMutationResponse,
            cancellationToken);
    }

    public Task<CptMutationResponse> MaterializeCptAsync(
        string nodeId,
        string strategy,
        double[]? weights,
        double weakestLinkStrength,
        double sigma,
        int expectedSemanticRevision,
        string actor,
        CancellationToken cancellationToken = default)
    {
        var transactionId = NewTransactionId("cpt-materialize");
        return MutateAsync(
            "model.cpt.materialize",
            transactionId,
            new CptMaterializeRequest(
                nodeId,
                strategy,
                weights,
                weakestLinkStrength,
                sigma,
                expectedSemanticRevision,
                actor,
                transactionId),
            PilotAssessmentJsonContext.Default.CptMaterializeRequest,
            PilotAssessmentJsonContext.Default.CptMutationResponse,
            cancellationToken);
    }

    public Task<CptMutationResponse> ReorderProbabilisticParentsAsync(
        string childNodeId,
        IReadOnlyList<string> orderedParentNodeIds,
        int expectedSemanticRevision,
        string actor,
        CancellationToken cancellationToken = default)
    {
        var transactionId = NewTransactionId("edge-reorder-probabilistic");
        return MutateAsync(
            "model.edge.reorder",
            transactionId,
            new ProbabilisticParentReorderRequest(
                childNodeId,
                orderedParentNodeIds.ToArray(),
                expectedSemanticRevision,
                actor,
                transactionId),
            PilotAssessmentJsonContext.Default.ProbabilisticParentReorderRequest,
            PilotAssessmentJsonContext.Default.CptMutationResponse,
            cancellationToken);
    }

    public Task<ModelNodeStatesMutationResponse> ReplaceNodeStatesAsync(
        string nodeId,
        IReadOnlyList<VariableState> states,
        IReadOnlyDictionary<string, int> expectedSemanticRevisions,
        string actor,
        CancellationToken cancellationToken = default)
    {
        var transactionId = NewTransactionId("node-states-replace");
        return MutateAsync(
            "model.node.states.replace",
            transactionId,
            new ModelNodeStatesReplaceRequest(
                nodeId,
                states.ToArray(),
                "mark_incomplete",
                expectedSemanticRevisions,
                actor,
                transactionId),
            PilotAssessmentJsonContext.Default.ModelNodeStatesReplaceRequest,
            PilotAssessmentJsonContext.Default.ModelNodeStatesMutationResponse,
            cancellationToken);
    }

    public Task<ModelNodeMutationResponse> AddExtractionEdgeAsync(
        string childNodeId,
        string parentNodeId,
        string recipeInputBindingId,
        EvidenceRecipe updatedRecipe,
        int expectedSemanticRevision,
        string actor,
        CancellationToken cancellationToken = default)
    {
        var transactionId = NewTransactionId("edge-add-extraction");
        return MutateAsync(
            "model.edge.add",
            transactionId,
            new ExtractionEdgeAddRequest(
                "extraction",
                childNodeId,
                parentNodeId,
                recipeInputBindingId,
                updatedRecipe,
                expectedSemanticRevision,
                actor,
                transactionId),
            PilotAssessmentJsonContext.Default.ExtractionEdgeAddRequest,
            PilotAssessmentJsonContext.Default.ModelNodeMutationResponse,
            cancellationToken);
    }

    public Task<ModelNodeMutationResponse> RemoveExtractionEdgeAsync(
        string childNodeId,
        string recipeInputBindingId,
        EvidenceRecipe updatedRecipe,
        int expectedSemanticRevision,
        string actor,
        CancellationToken cancellationToken = default)
    {
        var transactionId = NewTransactionId("edge-remove-extraction");
        return MutateAsync(
            "model.edge.remove",
            transactionId,
            new ExtractionEdgeRemoveRequest(
                "extraction",
                childNodeId,
                null,
                recipeInputBindingId,
                updatedRecipe,
                expectedSemanticRevision,
                actor,
                transactionId),
            PilotAssessmentJsonContext.Default.ExtractionEdgeRemoveRequest,
            PilotAssessmentJsonContext.Default.ModelNodeMutationResponse,
            cancellationToken);
    }

    private JsonRpcClient Client => _backend.Client
        ?? throw new InvalidOperationException("The local assessment backend is not connected.");

    private Task<ModelEditSessionMutationResponse> MutateEditSessionAsync(
        string method,
        string operation,
        string actor,
        CancellationToken cancellationToken)
    {
        var transactionId = NewTransactionId(operation);
        return MutateAsync(
            method,
            transactionId,
            new ModelEditSessionMutationRequest(actor, transactionId),
            PilotAssessmentJsonContext.Default.ModelEditSessionMutationRequest,
            PilotAssessmentJsonContext.Default.ModelEditSessionMutationResponse,
            cancellationToken);
    }

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

    private Task<TResponse> MutateAsync<TRequest, TResponse>(
        string method,
        string transactionId,
        TRequest request,
        JsonTypeInfo<TRequest> requestType,
        JsonTypeInfo<TResponse> responseType,
        CancellationToken cancellationToken) =>
        IdempotentRequestRetry.ExecuteAsync(
            transactionId,
            (_, token) => InvokeAsync(method, request, requestType, responseType, token),
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
