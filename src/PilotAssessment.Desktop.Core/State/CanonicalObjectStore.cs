using System.Collections.Concurrent;

namespace PilotAssessment.Desktop.Core.State;

public sealed class CanonicalObjectStore<TCanonical>
    where TCanonical : class
{
    private readonly ConcurrentDictionary<string, Entry> _entries =
        new(StringComparer.Ordinal);

    public void Set(string objectKey, TCanonical canonical)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(objectKey);
        ArgumentNullException.ThrowIfNull(canonical);
        _entries.GetOrAdd(objectKey, static _ => new Entry()).Canonical = canonical;
    }

    public bool TryGet(string objectKey, out TCanonical? canonical)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(objectKey);
        if (_entries.TryGetValue(objectKey, out var entry))
        {
            canonical = entry.Canonical;
            return canonical is not null;
        }

        canonical = null;
        return false;
    }

    public async Task<TCanonical> SerializeSaveAsync(
        string objectKey,
        Func<TCanonical?, CancellationToken, Task<TCanonical>> save,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(objectKey);
        ArgumentNullException.ThrowIfNull(save);
        var entry = _entries.GetOrAdd(objectKey, static _ => new Entry());
        await entry.WriteGate.WaitAsync(cancellationToken);
        try
        {
            var canonical = await save(entry.Canonical, cancellationToken);
            entry.Canonical = canonical;
            return canonical;
        }
        finally
        {
            entry.WriteGate.Release();
        }
    }

    private sealed class Entry
    {
        public SemaphoreSlim WriteGate { get; } = new(1, 1);

        public TCanonical? Canonical { get; set; }
    }
}
