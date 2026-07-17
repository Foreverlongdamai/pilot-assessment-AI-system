using PilotAssessment.Desktop.Core.Contracts;

namespace PilotAssessment.Desktop.Core.ViewModels;

public sealed class EvidenceEditorCoordinator : IDisposable
{
    private readonly IModelNodeEditorGateway _gateway;
    private CancellationTokenSource? _previewCancellation;

    public EvidenceEditorCoordinator(IModelNodeEditorGateway gateway)
    {
        _gateway = gateway;
    }

    public Task<IReadOnlyList<OperatorDefinition>> ListOperatorsAsync(
        CancellationToken cancellationToken = default) =>
        _gateway.ListOperatorsAsync(cancellationToken);

    public Task<IReadOnlyList<ModelNodeUsage>> ListUsagesAsync(
        string nodeId,
        CancellationToken cancellationToken = default) =>
        _gateway.ListNodeUsagesAsync(nodeId, cancellationToken);

    public Task<IReadOnlyList<ModelChangeEvent>> ListHistoryAsync(
        string nodeId,
        CancellationToken cancellationToken = default) =>
        _gateway.ListNodeHistoryAsync(nodeId, cancellationToken);

    public Task<ModelNodeMutationResponse> UpdateAsync(
        ModelNode node,
        string actor,
        CancellationToken cancellationToken = default) =>
        _gateway.UpdateNodeAsync(
            node,
            node.SemanticRevision,
            node.LayoutRevision,
            actor,
            cancellationToken);

    public async Task<CurrentModelRunSnapshot?> PreviewAsync(
        string sessionRevisionId,
        string schemeId,
        string nodeId,
        CancellationToken cancellationToken = default)
    {
        var ownCancellation = new CancellationTokenSource();
        var previous = Interlocked.Exchange(ref _previewCancellation, ownCancellation);
        previous?.Cancel();
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            ownCancellation.Token);
        try
        {
            return await _gateway.PreviewNodeAsync(
                sessionRevisionId,
                schemeId,
                nodeId,
                new Dictionary<string, System.Text.Json.JsonElement>(StringComparer.Ordinal),
                linked.Token);
        }
        catch (OperationCanceledException) when (ownCancellation.IsCancellationRequested)
        {
            return null;
        }
        finally
        {
            Interlocked.CompareExchange(ref _previewCancellation, null, ownCancellation);
            ownCancellation.Dispose();
        }
    }

    public void CancelPreview() => Volatile.Read(ref _previewCancellation)?.Cancel();

    public void Dispose()
    {
        var cancellation = Interlocked.Exchange(ref _previewCancellation, null);
        cancellation?.Cancel();
    }
}
