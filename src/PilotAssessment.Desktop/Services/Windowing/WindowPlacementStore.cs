using PilotAssessment.Desktop.Core.State;
using PilotAssessment.Desktop.Services.Preferences;

namespace PilotAssessment.Desktop.Services.Windowing;

public sealed class WindowPlacementStore
{
    private readonly LocalPreferencesStore _preferences;
    private readonly object _gate = new();
    private readonly SemaphoreSlim _flushGate = new(1, 1);
    private readonly Dictionary<NodeWindowKey, NodeWindowPlacement> _placements = [];
    private bool _initialized;

    public WindowPlacementStore(LocalPreferencesStore preferences)
    {
        _preferences = preferences;
    }

    public async Task InitializeAsync(CancellationToken cancellationToken = default)
    {
        var preferences = await _preferences.LoadAsync(cancellationToken).ConfigureAwait(false);
        lock (_gate)
        {
            _placements.Clear();
            foreach (var placement in preferences.NodeWindows ?? [])
            {
                try
                {
                    var key = new NodeWindowKey(
                        placement.ProjectId,
                        placement.SchemeId,
                        placement.NodeId);
                    _placements[key] = new NodeWindowPlacement(
                        placement.X,
                        placement.Y,
                        placement.Width,
                        placement.Height,
                        placement.IsMaximized);
                }
                catch (ArgumentException)
                {
                    // Ignore stale or manually corrupted UI-only entries.
                }
            }

            _initialized = true;
        }
    }

    public NodeWindowPlacement? Get(NodeWindowKey key)
    {
        ArgumentNullException.ThrowIfNull(key);
        lock (_gate)
        {
            EnsureInitialized();
            return _placements.GetValueOrDefault(key);
        }
    }

    public void Remember(NodeWindowKey key, NodeWindowPlacement placement)
    {
        ArgumentNullException.ThrowIfNull(key);
        ArgumentNullException.ThrowIfNull(placement);
        lock (_gate)
        {
            EnsureInitialized();
            _placements[key] = placement;
        }
    }

    public async Task FlushAsync(CancellationToken cancellationToken = default)
    {
        await _flushGate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            NodeWindowPlacementPreference[] snapshot;
            lock (_gate)
            {
                EnsureInitialized();
                snapshot = _placements
                    .OrderBy(item => item.Key.ProjectId, StringComparer.Ordinal)
                    .ThenBy(item => item.Key.SchemeId, StringComparer.Ordinal)
                    .ThenBy(item => item.Key.NodeId, StringComparer.Ordinal)
                    .Select(item => new NodeWindowPlacementPreference(
                        item.Key.ProjectId,
                        item.Key.SchemeId,
                        item.Key.NodeId,
                        item.Value.X,
                        item.Value.Y,
                        item.Value.Width,
                        item.Value.Height,
                        item.Value.IsMaximized))
                    .ToArray();
            }

            await _preferences.UpdateAsync(
                current => current with { NodeWindows = snapshot },
                cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            _flushGate.Release();
        }
    }

    private void EnsureInitialized()
    {
        if (!_initialized)
        {
            throw new InvalidOperationException("Window placement storage has not been initialized.");
        }
    }
}
