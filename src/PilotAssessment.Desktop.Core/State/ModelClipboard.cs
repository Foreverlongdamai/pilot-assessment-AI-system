namespace PilotAssessment.Desktop.Core.State;

public sealed record ModelClipboardPayload(
    string ProjectId,
    string[] SourceNodeIds,
    DateTime CopiedAtUtc);

public sealed class ModelClipboard
{
    private readonly object _gate = new();
    private ModelClipboardPayload? _payload;

    public void Copy(string projectId, IEnumerable<string> sourceNodeIds)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(projectId);
        ArgumentNullException.ThrowIfNull(sourceNodeIds);
        var canonicalIds = sourceNodeIds
            .Where(nodeId => !string.IsNullOrWhiteSpace(nodeId))
            .Distinct(StringComparer.Ordinal)
            .OrderBy(nodeId => nodeId, StringComparer.Ordinal)
            .ToArray();
        if (canonicalIds.Length == 0)
        {
            throw new ArgumentException("Copy requires at least one model node.", nameof(sourceNodeIds));
        }

        lock (_gate)
        {
            _payload = new ModelClipboardPayload(projectId, canonicalIds, DateTime.UtcNow);
        }
    }

    public bool TryRead(string projectId, out ModelClipboardPayload? payload)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(projectId);
        lock (_gate)
        {
            payload = _payload is not null &&
                      string.Equals(_payload.ProjectId, projectId, StringComparison.Ordinal)
                ? _payload with { SourceNodeIds = [.. _payload.SourceNodeIds] }
                : null;
            return payload is not null;
        }
    }

    public void Clear()
    {
        lock (_gate)
        {
            _payload = null;
        }
    }
}
