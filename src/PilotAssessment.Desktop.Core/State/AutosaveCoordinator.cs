namespace PilotAssessment.Desktop.Core.State;

public enum AutosavePhase
{
    Saved,
    Pending,
    Saving,
    OfflineRetry,
    Conflict,
    Blocked,
    Stopped,
}

public enum AutosaveFailureKind
{
    Offline,
    Conflict,
    Blocked,
}

public sealed record AutosaveState(
    AutosavePhase Phase,
    string Message,
    string? TransactionId = null,
    Exception? Error = null);

public sealed class AutosaveStateChangedEventArgs(AutosaveState state) : EventArgs
{
    public AutosaveState State { get; } = state;
}

public sealed class AutosaveCommittedEventArgs<TDraft, TCanonical>(
    TCanonical canonical,
    TDraft? pendingDraft,
    long savedGeneration,
    string transactionId) : EventArgs
    where TDraft : class
    where TCanonical : class
{
    public TCanonical Canonical { get; } = canonical;

    public TDraft? PendingDraft { get; } = pendingDraft;

    public long SavedGeneration { get; } = savedGeneration;

    public string TransactionId { get; } = transactionId;
}

public sealed class AutosaveCoordinator<TDraft, TCanonical> : IAsyncDisposable
    where TDraft : class
    where TCanonical : class
{
    private readonly object _gate = new();
    private readonly SemaphoreSlim _drainGate = new(1, 1);
    private readonly CancellationTokenSource _lifetime = new();
    private readonly string _objectKey;
    private readonly CanonicalObjectStore<TCanonical> _canonicalStore;
    private readonly Func<TDraft, TCanonical, TDraft> _rebase;
    private readonly Func<TDraft, string, CancellationToken, Task<TCanonical>> _save;
    private readonly Func<Exception, AutosaveFailureKind> _classifyFailure;
    private readonly Func<string> _transactionIdFactory;
    private readonly TimeSpan _debounce;
    private CancellationTokenSource? _debounceCancellation;
    private Task _debounceTask = Task.CompletedTask;
    private TDraft? _latestDraft;
    private long _generation;
    private bool _pending;
    private SaveAttempt? _retryAttempt;
    private SaveAttempt? _conflictAttempt;
    private bool _disposed;
    private AutosaveState _state = new(AutosavePhase.Saved, "Saved");

    public AutosaveCoordinator(
        string objectKey,
        CanonicalObjectStore<TCanonical> canonicalStore,
        Func<TDraft, TCanonical, TDraft> rebase,
        Func<TDraft, string, CancellationToken, Task<TCanonical>> save,
        Func<Exception, AutosaveFailureKind> classifyFailure,
        Func<string> transactionIdFactory,
        TimeSpan? debounce = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(objectKey);
        ArgumentNullException.ThrowIfNull(canonicalStore);
        ArgumentNullException.ThrowIfNull(rebase);
        ArgumentNullException.ThrowIfNull(save);
        ArgumentNullException.ThrowIfNull(classifyFailure);
        ArgumentNullException.ThrowIfNull(transactionIdFactory);
        _objectKey = objectKey;
        _canonicalStore = canonicalStore;
        _rebase = rebase;
        _save = save;
        _classifyFailure = classifyFailure;
        _transactionIdFactory = transactionIdFactory;
        _debounce = debounce ?? TimeSpan.FromMilliseconds(350);
        if (_debounce < TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(nameof(debounce));
        }
    }

    public AutosaveState State
    {
        get
        {
            lock (_gate)
            {
                return _state;
            }
        }
    }

    public event EventHandler<AutosaveStateChangedEventArgs>? StateChanged;

    public event EventHandler<AutosaveCommittedEventArgs<TDraft, TCanonical>>? Committed;

    public void SeedCanonical(TCanonical canonical) =>
        _canonicalStore.Set(_objectKey, canonical);

    public void Queue(TDraft draft)
    {
        ArgumentNullException.ThrowIfNull(draft);
        AutosaveState state;
        var schedule = false;
        lock (_gate)
        {
            ThrowIfDisposed();
            _latestDraft = draft;
            _generation++;
            _pending = true;
            if (_retryAttempt is null && _conflictAttempt is null)
            {
                schedule = true;
                state = SetStateUnsafe(new AutosaveState(
                    AutosavePhase.Pending,
                    "Pending changes"));
            }
            else
            {
                state = SetStateUnsafe(_state with
                {
                    Message = _state.Phase is AutosavePhase.OfflineRetry
                        ? "Offline; retry the saved request before newer edits"
                        : "Revision conflict; reload or reapply the newest edits",
                });
            }
        }

        PublishState(state);
        if (schedule)
        {
            ScheduleDebounce();
        }
    }

    public void ReportBlocked(Exception error)
    {
        ArgumentNullException.ThrowIfNull(error);
        SetState(new AutosaveState(
            AutosavePhase.Blocked,
            $"Blocked: {error.Message}",
            Error: error));
    }

    public void AcceptExternalCanonical(TCanonical canonical)
    {
        ArgumentNullException.ThrowIfNull(canonical);
        _canonicalStore.Set(_objectKey, canonical);
    }

    public async Task FlushAsync(CancellationToken cancellationToken = default)
    {
        CancellationTokenSource? debounce;
        lock (_gate)
        {
            ThrowIfDisposed();
            debounce = _debounceCancellation;
            _debounceCancellation = null;
        }
        debounce?.Cancel();
        await DrainAsync(cancellationToken);
    }

    public async Task RetryAsync(CancellationToken cancellationToken = default)
    {
        SaveAttempt attempt;
        lock (_gate)
        {
            ThrowIfDisposed();
            attempt = _retryAttempt
                ?? throw new InvalidOperationException("There is no offline autosave request to retry.");
        }

        if (await ExecuteAttemptAsync(attempt, cancellationToken))
        {
            await DrainAsync(cancellationToken);
        }
    }

    public void ReloadConflict(TCanonical canonical)
    {
        ArgumentNullException.ThrowIfNull(canonical);
        _canonicalStore.Set(_objectKey, canonical);
        lock (_gate)
        {
            ThrowIfDisposed();
            _latestDraft = null;
            _pending = false;
            _retryAttempt = null;
            _conflictAttempt = null;
        }
        SetState(new AutosaveState(AutosavePhase.Saved, "Reloaded canonical state"));
    }

    public async Task ReapplyConflictAsync(
        TCanonical canonical,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(canonical);
        _canonicalStore.Set(_objectKey, canonical);
        AutosaveState state;
        lock (_gate)
        {
            ThrowIfDisposed();
            var draft = _latestDraft ?? _conflictAttempt?.OriginalDraft
                ?? throw new InvalidOperationException("There is no conflicted autosave intent to reapply.");
            _latestDraft = draft;
            _pending = true;
            _retryAttempt = null;
            _conflictAttempt = null;
            state = SetStateUnsafe(new AutosaveState(
                AutosavePhase.Pending,
                "Reapplying edits against the current canonical revision"));
        }
        PublishState(state);
        await DrainAsync(cancellationToken);
    }

    public async ValueTask DisposeAsync()
    {
        Task debounceTask;
        lock (_gate)
        {
            if (_disposed)
            {
                return;
            }
            _disposed = true;
            _debounceCancellation?.Cancel();
            _lifetime.Cancel();
            debounceTask = _debounceTask;
        }

        try
        {
            await debounceTask;
            await _drainGate.WaitAsync();
            _drainGate.Release();
        }
        catch (OperationCanceledException)
        {
        }
        finally
        {
            SetState(new AutosaveState(AutosavePhase.Stopped, "Autosave stopped"));
            _lifetime.Dispose();
            _debounceCancellation?.Dispose();
            _drainGate.Dispose();
        }
    }

    private void ScheduleDebounce()
    {
        CancellationTokenSource cancellation;
        lock (_gate)
        {
            if (_disposed)
            {
                return;
            }
            _debounceCancellation?.Cancel();
            _debounceCancellation?.Dispose();
            cancellation = CancellationTokenSource.CreateLinkedTokenSource(_lifetime.Token);
            _debounceCancellation = cancellation;
            _debounceTask = DebounceAndDrainAsync(cancellation.Token);
        }
    }

    private async Task DebounceAndDrainAsync(CancellationToken cancellationToken)
    {
        try
        {
            await Task.Delay(_debounce, cancellationToken);
            await DrainAsync(cancellationToken);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
        }
    }

    private async Task DrainAsync(CancellationToken cancellationToken)
    {
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken,
            _lifetime.Token);
        await _drainGate.WaitAsync(linked.Token);
        try
        {
            while (true)
            {
                SaveAttempt? attempt;
                lock (_gate)
                {
                    if (!_pending || _latestDraft is null ||
                        _retryAttempt is not null || _conflictAttempt is not null)
                    {
                        return;
                    }
                    attempt = new SaveAttempt(
                        _latestDraft,
                        _generation,
                        _transactionIdFactory());
                    _pending = false;
                }

                if (!await ExecuteAttemptAsync(attempt, linked.Token))
                {
                    return;
                }
            }
        }
        finally
        {
            _drainGate.Release();
        }
    }

    private async Task<bool> ExecuteAttemptAsync(
        SaveAttempt attempt,
        CancellationToken cancellationToken)
    {
        SetState(new AutosaveState(
            AutosavePhase.Saving,
            "Saving",
            attempt.TransactionId));
        try
        {
            var canonical = await _canonicalStore.SerializeSaveAsync(
                _objectKey,
                async (current, token) =>
                {
                    if (attempt.PreparedDraft is null)
                    {
                        attempt.PreparedDraft = current is null
                            ? attempt.OriginalDraft
                            : _rebase(attempt.OriginalDraft, current);
                    }
                    return await _save(attempt.PreparedDraft, attempt.TransactionId, token);
                },
                cancellationToken);

            TDraft? pendingDraft = null;
            AutosaveState state;
            lock (_gate)
            {
                _retryAttempt = null;
                _conflictAttempt = null;
                if (_pending && _latestDraft is not null)
                {
                    pendingDraft = _rebase(_latestDraft, canonical);
                }
                else
                {
                    _latestDraft = null;
                }
                state = SetStateUnsafe(new AutosaveState(
                    _pending ? AutosavePhase.Pending : AutosavePhase.Saved,
                    _pending ? "Newer edits pending" : "Saved",
                    attempt.TransactionId));
            }

            Committed?.Invoke(this, new AutosaveCommittedEventArgs<TDraft, TCanonical>(
                canonical,
                pendingDraft,
                attempt.Generation,
                attempt.TransactionId));
            PublishState(state);
            return true;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception error)
        {
            var kind = _classifyFailure(error);
            AutosaveState state;
            lock (_gate)
            {
                if (!_pending)
                {
                    _latestDraft = attempt.OriginalDraft;
                }
                switch (kind)
                {
                    case AutosaveFailureKind.Offline:
                        _retryAttempt = attempt;
                        state = SetStateUnsafe(new AutosaveState(
                            AutosavePhase.OfflineRetry,
                            $"Offline; retry available: {error.Message}",
                            attempt.TransactionId,
                            error));
                        break;
                    case AutosaveFailureKind.Conflict:
                        _conflictAttempt = attempt;
                        state = SetStateUnsafe(new AutosaveState(
                            AutosavePhase.Conflict,
                            $"Revision conflict: {error.Message}",
                            attempt.TransactionId,
                            error));
                        break;
                    default:
                        state = SetStateUnsafe(new AutosaveState(
                            AutosavePhase.Blocked,
                            $"Blocked: {error.Message}",
                            attempt.TransactionId,
                            error));
                        break;
                }
            }
            PublishState(state);
            return false;
        }
    }

    private void SetState(AutosaveState state)
    {
        lock (_gate)
        {
            SetStateUnsafe(state);
        }
        PublishState(state);
    }

    private AutosaveState SetStateUnsafe(AutosaveState state)
    {
        _state = state;
        return state;
    }

    private void PublishState(AutosaveState state) =>
        StateChanged?.Invoke(this, new AutosaveStateChangedEventArgs(state));

    private void ThrowIfDisposed()
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
    }

    private sealed class SaveAttempt(
        TDraft originalDraft,
        long generation,
        string transactionId)
    {
        public TDraft OriginalDraft { get; } = originalDraft;

        public long Generation { get; } = generation;

        public string TransactionId { get; } = transactionId;

        public TDraft? PreparedDraft { get; set; }
    }
}
