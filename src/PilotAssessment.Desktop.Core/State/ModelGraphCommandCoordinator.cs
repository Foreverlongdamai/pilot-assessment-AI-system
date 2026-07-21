using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.ViewModels;

namespace PilotAssessment.Desktop.Core.State;

public sealed class ModelGraphCommandCoordinator
{
    private const string Actor = "expert.local";
    private readonly IModelGraphGateway _gateway;
    private readonly ModelClipboard _clipboard;

    public ModelGraphCommandCoordinator(IModelGraphGateway gateway, ModelClipboard clipboard)
    {
        _gateway = gateway;
        _clipboard = clipboard;
    }

    public Task<ModelGraphSnapshot> GetGraphAsync(
        string schemeId,
        CancellationToken cancellationToken = default) =>
        _gateway.GetGraphAsync(schemeId, cancellationToken);

    public Task<ModelNodeMutationResponse> CreateNodeAsync(
        ModelNodeDraftRequest request,
        CancellationToken cancellationToken = default) =>
        _gateway.CreateNodeAsync(ModelNodeDraftFactory.Create(request), Actor, cancellationToken);

    public Task<ModelNodeMutationResponse> ArchiveNodeAsync(
        ModelNode node,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(node);
        return _gateway.ArchiveNodeAsync(
            node.NodeId,
            node.SemanticRevision,
            Actor,
            cancellationToken);
    }

    public Task<TaskSchemeMutationResponse> ActivateNodeAsync(
        TaskScheme scheme,
        string nodeId,
        CancellationToken cancellationToken = default) =>
        _gateway.ActivateNodeAsync(
            scheme.SchemeId,
            nodeId,
            scheme.SemanticRevision,
            Actor,
            cancellationToken);

    public Task<DeactivationImpact> PreviewDeactivationAsync(
        TaskScheme scheme,
        string nodeId,
        CancellationToken cancellationToken = default) =>
        _gateway.PreviewDeactivationAsync(scheme.SchemeId, nodeId, cancellationToken);

    public Task<TaskSchemeMutationResponse?> CompleteDeactivationAsync(
        TaskScheme scheme,
        string nodeId,
        DeactivationImpact impact,
        bool continueRequested,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(scheme);
        ArgumentNullException.ThrowIfNull(impact);
        if (!continueRequested)
        {
            return Task.FromResult<TaskSchemeMutationResponse?>(null);
        }

        if (impact.SchemeId != scheme.SchemeId || impact.RequestedNodeId != nodeId)
        {
            throw new ArgumentException("The deactivation preview does not match this task and node.");
        }

        return CompleteAsync();

        async Task<TaskSchemeMutationResponse?> CompleteAsync() =>
            await _gateway.DeactivateNodeAsync(
                scheme.SchemeId,
                nodeId,
                scheme.SemanticRevision,
                impact.ImpactHash,
                Actor,
                cancellationToken);
    }

    public void Copy(string projectId, IEnumerable<string> nodeIds) =>
        _clipboard.Copy(projectId, nodeIds);

    public bool CanPaste(string projectId) => _clipboard.TryRead(projectId, out _);

    public Task<GraphBatchMutationResponse> PasteAsync(
        string projectId,
        TaskScheme scheme,
        CancellationToken cancellationToken = default)
    {
        if (!_clipboard.TryRead(projectId, out var payload) || payload is null)
        {
            throw new InvalidOperationException("The in-app model clipboard is empty for this project.");
        }

        return _gateway.ApplyGraphBatchAsync(
            scheme.SchemeId,
            payload.SourceNodeIds,
            [],
            [],
            scheme.SemanticRevision,
            scheme.LayoutRevision,
            Actor,
            cancellationToken);
    }

    public Task<GraphBatchMutationResponse> UpdateLayoutAsync(
        TaskScheme scheme,
        IReadOnlyList<NodeLayout> positions,
        CancellationToken cancellationToken = default) =>
        _gateway.UpdateLayoutAsync(
            scheme.SchemeId,
            positions,
            scheme.SemanticRevision,
            scheme.LayoutRevision,
            Actor,
            cancellationToken);

    public async Task AddEdgeAsync(
        ModelNode source,
        ModelNode target,
        bool markCptIncomplete,
        CancellationToken cancellationToken = default)
    {
        if (source.NodeKind is ModelNodeKind.RawInput)
        {
            var edit = EvidenceRecipeEdgeEditor.AddRawInput(target, source);
            await _gateway.AddExtractionEdgeAsync(
                target.NodeId,
                source.NodeId,
                edit.RecipeInputBindingId,
                edit.UpdatedRecipe,
                target.SemanticRevision,
                Actor,
                cancellationToken);
            return;
        }

        await _gateway.AddProbabilisticEdgeAsync(
            target.NodeId,
            source.NodeId,
            markCptIncomplete ? "incomplete" : "preserve_independence",
            target.SemanticRevision,
            Actor,
            cancellationToken);
    }

    public async Task RemoveEdgeAsync(
        ModelGraphEdge edge,
        ModelNode source,
        ModelNode target,
        bool markCptIncomplete,
        CancellationToken cancellationToken = default)
    {
        if (edge.EdgeKind is ModelGraphEdgeKind.Extraction)
        {
            if (target.Definition is not EvidenceNodeDefinition definition ||
                string.IsNullOrWhiteSpace(edge.RecipeInputBindingId))
            {
                throw new InvalidOperationException("The extraction edge has no editable recipe binding.");
            }

            await _gateway.RemoveExtractionEdgeAsync(
                target.NodeId,
                edge.RecipeInputBindingId,
                EvidenceRecipeEdgeEditor.RemoveRawInput(definition, edge.RecipeInputBindingId),
                target.SemanticRevision,
                Actor,
                cancellationToken);
            return;
        }

        await _gateway.RemoveProbabilisticEdgeAsync(
            target.NodeId,
            source.NodeId,
            markCptIncomplete ? "incomplete" : "marginalize",
            markCptIncomplete ? null : EvidenceRecipeEdgeEditor.UniformStateWeights(source),
            target.SemanticRevision,
            Actor,
            cancellationToken);
    }
}
