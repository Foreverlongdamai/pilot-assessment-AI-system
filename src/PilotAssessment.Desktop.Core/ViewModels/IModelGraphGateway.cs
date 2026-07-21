using PilotAssessment.Desktop.Core.Contracts;

namespace PilotAssessment.Desktop.Core.ViewModels;

public interface IModelGraphGateway
{
    Task<ModelGraphSnapshot> GetGraphAsync(
        string schemeId,
        CancellationToken cancellationToken = default);

    Task<ModelNodeMutationResponse> CreateNodeAsync(
        ModelNode node,
        string actor,
        CancellationToken cancellationToken = default);

    Task<TaskSchemeMutationResponse> ActivateNodeAsync(
        string schemeId,
        string nodeId,
        int expectedSemanticRevision,
        string actor,
        CancellationToken cancellationToken = default);

    Task<DeactivationImpact> PreviewDeactivationAsync(
        string schemeId,
        string nodeId,
        CancellationToken cancellationToken = default);

    Task<TaskSchemeMutationResponse> DeactivateNodeAsync(
        string schemeId,
        string nodeId,
        int expectedSemanticRevision,
        string impactHash,
        string actor,
        CancellationToken cancellationToken = default);

    Task<GraphBatchMutationResponse> ApplyGraphBatchAsync(
        string schemeId,
        IReadOnlyList<string> copyNodeIds,
        IReadOnlyList<string> activateNodeIds,
        IReadOnlyList<NodeLayout> layoutUpdates,
        int expectedSemanticRevision,
        int expectedLayoutRevision,
        string actor,
        CancellationToken cancellationToken = default);

    Task<GraphBatchMutationResponse> UpdateLayoutAsync(
        string schemeId,
        IReadOnlyList<NodeLayout> positions,
        int expectedSemanticRevision,
        int expectedLayoutRevision,
        string actor,
        CancellationToken cancellationToken = default);

    Task<CptMutationResponse> AddProbabilisticEdgeAsync(
        string childNodeId,
        string parentNodeId,
        string strategy,
        int expectedSemanticRevision,
        string actor,
        CancellationToken cancellationToken = default);

    Task<CptMutationResponse> RemoveProbabilisticEdgeAsync(
        string childNodeId,
        string parentNodeId,
        string strategy,
        double[]? marginalWeights,
        int expectedSemanticRevision,
        string actor,
        CancellationToken cancellationToken = default);

    Task<ModelNodeMutationResponse> AddExtractionEdgeAsync(
        string childNodeId,
        string parentNodeId,
        string recipeInputBindingId,
        EvidenceRecipe updatedRecipe,
        int expectedSemanticRevision,
        string actor,
        CancellationToken cancellationToken = default);

    Task<ModelNodeMutationResponse> RemoveExtractionEdgeAsync(
        string childNodeId,
        string recipeInputBindingId,
        EvidenceRecipe updatedRecipe,
        int expectedSemanticRevision,
        string actor,
        CancellationToken cancellationToken = default);
}

public interface IModelNodeEditorGateway
{
    Task<IReadOnlyList<OperatorDefinition>> ListOperatorsAsync(
        CancellationToken cancellationToken = default);

    Task<ModelNodeMutationResponse> UpdateNodeAsync(
        ModelNode node,
        int expectedSemanticRevision,
        int expectedLayoutRevision,
        string actor,
        string transactionId,
        CancellationToken cancellationToken = default);

    Task<IReadOnlyList<ModelNodeUsage>> ListNodeUsagesAsync(
        string nodeId,
        CancellationToken cancellationToken = default);

    Task<IReadOnlyList<ModelChangeEvent>> ListNodeHistoryAsync(
        string nodeId,
        CancellationToken cancellationToken = default);

    Task<CurrentModelRunSnapshotV3> PreviewNodeAsync(
        string sessionRevisionId,
        string schemeId,
        string nodeId,
        IReadOnlyDictionary<string, System.Text.Json.JsonElement> runtimeParameters,
        CancellationToken cancellationToken = default);
}

public interface IBayesianNodeEditorGateway
{
    Task<ModelGraphSnapshot> GetGraphAsync(
        string schemeId,
        CancellationToken cancellationToken = default);

    Task<CptInspectResponse> InspectCptAsync(
        string nodeId,
        CancellationToken cancellationToken = default);

    Task<CptMutationResponse> UpdateCptRowsAsync(
        string nodeId,
        IReadOnlyList<IReadOnlyList<double>> rows,
        int expectedSemanticRevision,
        string actor,
        CancellationToken cancellationToken = default);

    Task<CptMutationResponse> MaterializeCptAsync(
        string nodeId,
        string strategy,
        double[]? weights,
        double weakestLinkStrength,
        double sigma,
        int expectedSemanticRevision,
        string actor,
        CancellationToken cancellationToken = default);

    Task<CptMutationResponse> AddProbabilisticEdgeAsync(
        string childNodeId,
        string parentNodeId,
        string strategy,
        int expectedSemanticRevision,
        string actor,
        CancellationToken cancellationToken = default);

    Task<CptMutationResponse> RemoveProbabilisticEdgeAsync(
        string childNodeId,
        string parentNodeId,
        string strategy,
        double[]? marginalWeights,
        int expectedSemanticRevision,
        string actor,
        CancellationToken cancellationToken = default);

    Task<CptMutationResponse> ReorderProbabilisticParentsAsync(
        string childNodeId,
        IReadOnlyList<string> orderedParentNodeIds,
        int expectedSemanticRevision,
        string actor,
        CancellationToken cancellationToken = default);

    Task<ModelNodeStatesMutationResponse> ReplaceNodeStatesAsync(
        string nodeId,
        IReadOnlyList<VariableState> states,
        IReadOnlyDictionary<string, int> expectedSemanticRevisions,
        string actor,
        CancellationToken cancellationToken = default);
}
