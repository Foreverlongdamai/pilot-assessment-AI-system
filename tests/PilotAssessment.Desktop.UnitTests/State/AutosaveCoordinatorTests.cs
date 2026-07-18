using PilotAssessment.Desktop.Core.State;

namespace PilotAssessment.Desktop.UnitTests.State;

public sealed class AutosaveCoordinatorTests
{
    [Fact]
    public async Task DebounceCollapsesRapidEditsToNewestDraft()
    {
        var saved = new List<string>();
        var committed = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        await using var coordinator = Create(
            new CanonicalObjectStore<string>(),
            async (draft, _, _) =>
            {
                saved.Add(draft);
                await Task.Yield();
                return $"canonical:{draft}";
            },
            TimeSpan.FromMilliseconds(20));
        coordinator.Committed += (_, _) => committed.TrySetResult(true);

        coordinator.Queue("one");
        coordinator.Queue("two");
        coordinator.Queue("three");

        await committed.Task.WaitAsync(TimeSpan.FromSeconds(2));
        Assert.Equal(["three"], saved);
        Assert.Equal(AutosavePhase.Saved, coordinator.State.Phase);
    }

    [Fact]
    public async Task NewerEditWaitsForInFlightSaveAndIsRebasedAfterLateResponse()
    {
        var firstStarted = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var releaseFirst = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var saved = new List<string>();
        var saveCount = 0;
        await using var coordinator = Create(
            new CanonicalObjectStore<string>(),
            async (draft, _, cancellationToken) =>
            {
                saved.Add(draft);
                if (Interlocked.Increment(ref saveCount) == 1)
                {
                    firstStarted.TrySetResult(true);
                    await releaseFirst.Task.WaitAsync(cancellationToken);
                }
                return $"canonical:{draft}";
            },
            TimeSpan.FromHours(1));

        coordinator.Queue("first");
        var flush = coordinator.FlushAsync();
        await firstStarted.Task.WaitAsync(TimeSpan.FromSeconds(2));
        coordinator.Queue("second");
        releaseFirst.TrySetResult(true);
        await flush.WaitAsync(TimeSpan.FromSeconds(2));

        Assert.Equal(["first", "second|canonical:first"], saved);
        Assert.Equal(AutosavePhase.Saved, coordinator.State.Phase);
    }

    [Fact]
    public async Task OfflineRetryReusesExactTransactionAndPreparedDraft()
    {
        var attempts = new List<(string Draft, string TransactionId)>();
        var fail = true;
        await using var coordinator = Create(
            new CanonicalObjectStore<string>(),
            (draft, transactionId, _) =>
            {
                attempts.Add((draft, transactionId));
                if (fail)
                {
                    fail = false;
                    throw new IOException("response lost");
                }
                return Task.FromResult($"canonical:{draft}");
            },
            TimeSpan.FromHours(1));

        coordinator.Queue("draft");
        await coordinator.FlushAsync();
        Assert.Equal(AutosavePhase.OfflineRetry, coordinator.State.Phase);

        await coordinator.RetryAsync();

        Assert.Equal(2, attempts.Count);
        Assert.Equal(attempts[0], attempts[1]);
        Assert.Equal(AutosavePhase.Saved, coordinator.State.Phase);
    }

    [Fact]
    public async Task ConflictReapplyUsesCurrentCanonicalAndNewTransaction()
    {
        var attempts = new List<(string Draft, string TransactionId)>();
        var conflict = true;
        var store = new CanonicalObjectStore<string>();
        store.Set("node", "canonical-1");
        await using var coordinator = Create(
            store,
            (draft, transactionId, _) =>
            {
                attempts.Add((draft, transactionId));
                if (conflict)
                {
                    conflict = false;
                    throw new TestConflictException();
                }
                return Task.FromResult($"canonical:{draft}");
            },
            TimeSpan.FromHours(1));

        coordinator.Queue("draft");
        await coordinator.FlushAsync();
        Assert.Equal(AutosavePhase.Conflict, coordinator.State.Phase);

        await coordinator.ReapplyConflictAsync("canonical-2");

        Assert.Equal("draft|canonical-1", attempts[0].Draft);
        Assert.Equal("draft|canonical-2", attempts[1].Draft);
        Assert.NotEqual(attempts[0].TransactionId, attempts[1].TransactionId);
        Assert.Equal(AutosavePhase.Saved, coordinator.State.Phase);
    }

    [Fact]
    public async Task FlushSavesImmediatelyAndDisposeCancelsPendingDebounce()
    {
        var saves = 0;
        var store = new CanonicalObjectStore<string>();
        await using (var flushCoordinator = Create(
            store,
            (draft, _, _) =>
            {
                Interlocked.Increment(ref saves);
                return Task.FromResult(draft);
            },
            TimeSpan.FromHours(1)))
        {
            flushCoordinator.Queue("flush");
            await flushCoordinator.FlushAsync();
        }

        var cancelCoordinator = Create(
            store,
            (draft, _, _) =>
            {
                Interlocked.Increment(ref saves);
                return Task.FromResult(draft);
            },
            TimeSpan.FromHours(1));
        cancelCoordinator.Queue("cancel");
        await cancelCoordinator.DisposeAsync();

        Assert.Equal(1, saves);
    }

    [Fact]
    public async Task SharedStoreSerializesSameObjectButAllowsIndependentObjects()
    {
        var store = new CanonicalObjectStore<string>();
        var aStarted = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var bStarted = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        await using var a = CreateForKey("a", store, async (draft, _, token) =>
        {
            aStarted.TrySetResult(true);
            await release.Task.WaitAsync(token);
            return draft;
        });
        await using var b = CreateForKey("b", store, async (draft, _, token) =>
        {
            bStarted.TrySetResult(true);
            await release.Task.WaitAsync(token);
            return draft;
        });

        a.Queue("a1");
        b.Queue("b1");
        var flushA = a.FlushAsync();
        var flushB = b.FlushAsync();
        await Task.WhenAll(
            aStarted.Task.WaitAsync(TimeSpan.FromSeconds(2)),
            bStarted.Task.WaitAsync(TimeSpan.FromSeconds(2)));
        release.TrySetResult(true);
        await Task.WhenAll(flushA, flushB);

        Assert.True(store.TryGet("a", out var canonicalA));
        Assert.True(store.TryGet("b", out var canonicalB));
        Assert.Equal("a1", canonicalA);
        Assert.Equal("b1", canonicalB);
    }

    private static AutosaveCoordinator<string, string> Create(
        CanonicalObjectStore<string> store,
        Func<string, string, CancellationToken, Task<string>> save,
        TimeSpan debounce) =>
        CreateForKey("node", store, save, debounce);

    private static AutosaveCoordinator<string, string> CreateForKey(
        string key,
        CanonicalObjectStore<string> store,
        Func<string, string, CancellationToken, Task<string>> save,
        TimeSpan? debounce = null) =>
        new(
            key,
            store,
            static (draft, canonical) => $"{draft}|{canonical}",
            save,
            static error => error switch
            {
                IOException => AutosaveFailureKind.Offline,
                TestConflictException => AutosaveFailureKind.Conflict,
                _ => AutosaveFailureKind.Blocked,
            },
            () => $"tx.{Guid.NewGuid():N}",
            debounce ?? TimeSpan.FromHours(1));

    private sealed class TestConflictException : Exception;
}
