using System.Text.Json;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;
using PilotAssessment.Desktop.Core.ViewModels;

namespace PilotAssessment.Desktop.UnitTests.ViewModels;

public sealed class TaskSchemeListViewModelTests
{
    private static readonly DateTime Now = new(2026, 7, 17, 14, 0, 0, DateTimeKind.Utc);

    [Fact]
    public async Task RapidSelectionChangesContextWithoutWritingAnyScheme()
    {
        var gateway = new FakeGateway([Task.FromResult<IReadOnlyList<TaskScheme>>(
            [Scheme("task-scheme.alpha", "Alpha"), Scheme("task-scheme.beta", "Beta")])]);
        var shell = new ApplicationShellState();
        shell.SetProjectContext("project.test", "session.test");
        var viewModel = new TaskSchemeListViewModel(gateway, shell);

        await viewModel.LoadAsync("project.test");
        viewModel.Select(viewModel.Schemes.Single(item => item.SchemeId == "task-scheme.beta"));
        viewModel.Select(viewModel.Schemes.Single(item => item.SchemeId == "task-scheme.alpha"));
        viewModel.Select(viewModel.Schemes.Single(item => item.SchemeId == "task-scheme.beta"));

        Assert.Equal("task-scheme.beta", shell.Snapshot.SchemeId);
        Assert.Equal("session.test", shell.Snapshot.SessionId);
        Assert.Equal(0, gateway.MutationCalls);
    }

    [Fact]
    public async Task SearchGroupTagSortAndArchivedVisibilityFilterOneCanonicalList()
    {
        var gateway = new FakeGateway([Task.FromResult<IReadOnlyList<TaskScheme>>(
            [
                Scheme("task-scheme.hover", "Hover", tags: ["precision"], group: "handling"),
                Scheme("task-scheme.line", "Straight line", tags: ["tracking"], group: "handling"),
                Scheme(
                    "task-scheme.archived",
                    "Old hover",
                    tags: ["precision"],
                    group: "legacy",
                    lifecycle: ModelObjectLifecycle.Archived),
            ])]);
        var shell = new ApplicationShellState();
        shell.SetProjectContext("project.test");
        var viewModel = new TaskSchemeListViewModel(gateway, shell);
        await viewModel.LoadAsync("project.test");

        Assert.Equal(2, viewModel.Schemes.Count);
        viewModel.SelectedTagFilter = "precision";
        Assert.Single(viewModel.Schemes);
        Assert.Equal("task-scheme.hover", viewModel.Schemes[0].SchemeId);

        viewModel.ShowArchived = true;
        Assert.Equal(2, viewModel.Schemes.Count);
        viewModel.SelectedTagFilter = TaskSchemeListViewModel.AllTags;
        viewModel.SelectedGroupFilter = "handling";
        viewModel.SearchText = "line";
        Assert.Single(viewModel.Schemes);
        Assert.Equal("task-scheme.line", viewModel.Schemes[0].SchemeId);
    }

    [Fact]
    public async Task CopyInsertsAndSelectsCanonicalParallelSchemeWithSharedNodes()
    {
        var source = Scheme(
            "task-scheme.base",
            "Base",
            explicitNodes: ["model-node.evidence.one"],
            closure: ["model-node.evidence.one", "model-node.raw.x"]);
        var gateway = new FakeGateway(
            [Task.FromResult<IReadOnlyList<TaskScheme>>([source])]);
        var shell = new ApplicationShellState();
        shell.SetProjectContext("project.test");
        var viewModel = new TaskSchemeListViewModel(gateway, shell);
        await viewModel.LoadAsync("project.test");

        var copied = await viewModel.CopySelectedAsync();

        Assert.NotNull(copied);
        Assert.Equal(2, viewModel.Schemes.Count);
        Assert.Equal(copied!.SchemeId, viewModel.SelectedScheme!.SchemeId);
        Assert.Equal(source.SchemeId, copied.CopiedFromSchemeId);
        Assert.Equal(source.ExplicitActiveNodeIds, copied.ExplicitActiveNodeIds);
        Assert.Equal(source.ComputedActiveClosure, copied.ComputedActiveClosure);
        Assert.Equal(new string('c', 64), copied.ContentHash);
        Assert.Equal(copied.SchemeId, shell.Snapshot.SchemeId);
        Assert.Equal("Base", viewModel.Schemes.Single(item => item.SchemeId == source.SchemeId).DisplayName);
    }

    [Fact]
    public async Task ReloadPreservesSelectionByStableSchemeId()
    {
        var first = new TaskCompletionSource<IReadOnlyList<TaskScheme>>(
            TaskCreationOptions.RunContinuationsAsynchronously);
        var second = new TaskCompletionSource<IReadOnlyList<TaskScheme>>(
            TaskCreationOptions.RunContinuationsAsynchronously);
        var gateway = new FakeGateway([first.Task, second.Task]);
        var shell = new ApplicationShellState();
        shell.SetProjectContext("project.test");
        var viewModel = new TaskSchemeListViewModel(gateway, shell);
        var initialLoad = viewModel.LoadAsync("project.test");
        first.SetResult([Scheme("task-scheme.alpha", "Alpha"), Scheme("task-scheme.beta", "Beta")]);
        await initialLoad;
        viewModel.Select(viewModel.Schemes.Single(item => item.SchemeId == "task-scheme.beta"));

        var reload = viewModel.LoadAsync("project.test");
        second.SetResult([Scheme("task-scheme.beta", "Beta canonical"), Scheme("task-scheme.alpha", "Alpha")]);
        await reload;

        Assert.Equal("task-scheme.beta", viewModel.SelectedScheme!.SchemeId);
        Assert.Equal("Beta canonical", viewModel.SelectedScheme.DisplayName);
        Assert.Equal("task-scheme.beta", shell.Snapshot.SchemeId);
    }

    [Fact]
    public async Task OlderProjectResponseCannotReplaceTheNewProjectSchemes()
    {
        var oldResponse = new TaskCompletionSource<IReadOnlyList<TaskScheme>>(
            TaskCreationOptions.RunContinuationsAsynchronously);
        var newResponse = new TaskCompletionSource<IReadOnlyList<TaskScheme>>(
            TaskCreationOptions.RunContinuationsAsynchronously);
        var gateway = new FakeGateway([oldResponse.Task, newResponse.Task]);
        var shell = new ApplicationShellState();
        shell.SetProjectContext("project.old");
        var viewModel = new TaskSchemeListViewModel(gateway, shell);

        var oldLoad = viewModel.LoadAsync("project.old");
        shell.SetProjectContext("project.new");
        var newLoad = viewModel.LoadAsync("project.new");
        newResponse.SetResult([Scheme("task-scheme.new", "New project")]);
        await newLoad;
        oldResponse.SetResult([Scheme("task-scheme.old", "Old project")]);
        await oldLoad;

        Assert.Single(viewModel.Schemes);
        Assert.Equal("task-scheme.new", viewModel.Schemes[0].SchemeId);
        Assert.Equal("task-scheme.new", shell.Snapshot.SchemeId);
    }

    [Fact]
    public async Task RenameAndArchiveReconcileCanonicalRevisionAndChooseAnotherActiveScheme()
    {
        var gateway = new FakeGateway([Task.FromResult<IReadOnlyList<TaskScheme>>(
            [Scheme("task-scheme.alpha", "Alpha"), Scheme("task-scheme.beta", "Beta")])]);
        var shell = new ApplicationShellState();
        shell.SetProjectContext("project.test");
        var viewModel = new TaskSchemeListViewModel(gateway, shell);
        await viewModel.LoadAsync("project.test");
        viewModel.Select(viewModel.Schemes.Single(item => item.SchemeId == "task-scheme.alpha"));

        var renamed = await viewModel.RenameSelectedAsync("Alpha edited", "Alpha 中文");
        var archived = await viewModel.ArchiveSelectedAsync();

        Assert.Equal(1, renamed!.SemanticRevision);
        Assert.Equal("Alpha edited", renamed.NameEn);
        Assert.Equal(ModelObjectLifecycle.Archived, archived!.Lifecycle);
        Assert.Single(viewModel.Schemes);
        Assert.Equal("task-scheme.beta", viewModel.SelectedScheme!.SchemeId);
        Assert.Equal("task-scheme.beta", shell.Snapshot.SchemeId);
    }

    private static TaskScheme Scheme(
        string id,
        string name,
        string[]? tags = null,
        string? group = null,
        ModelObjectLifecycle lifecycle = ModelObjectLifecycle.Active,
        string[]? explicitNodes = null,
        string[]? closure = null,
        int semanticRevision = 0,
        string? copiedFrom = null,
        char hashCharacter = 'a') => new(
            "task-scheme",
            "0.1.0",
            id,
            null,
            name,
            null,
            null,
            tags ?? [],
            group,
            lifecycle,
            copiedFrom,
            explicitNodes ?? [],
            closure ?? [],
            [],
            new Dictionary<string, JsonElement>(StringComparer.Ordinal),
            [],
            semanticRevision,
            0,
            ModelTechnicalStatus.Executable,
            [],
            new string(hashCharacter, 64),
            new string('b', 64),
            Now,
            Now.AddMinutes(semanticRevision));

    private static TaskSchemeMutationResponse Mutation(TaskScheme scheme) => new(
        scheme,
        new ModelGraphSnapshot(
            "model-graph-snapshot",
            "0.1.0",
            "project.test",
            scheme,
            [],
            [],
            Now,
            new string('d', 64)),
        scheme.SemanticRevision,
        scheme.LayoutRevision,
        scheme.TechnicalStatus,
        new CanonicalModelDiff(
            [],
            [],
            [],
            [],
            [],
            new Dictionary<string, JsonElement>(StringComparer.Ordinal)),
        "tx.test",
        "audit.test",
        false,
        "trace.test");

    private sealed class FakeGateway : IModelWorkspaceGateway
    {
        private readonly Queue<Task<IReadOnlyList<TaskScheme>>> _listResponses;
        private readonly Dictionary<string, TaskScheme> _canonical = new(StringComparer.Ordinal);

        public FakeGateway(IEnumerable<Task<IReadOnlyList<TaskScheme>>> listResponses)
        {
            _listResponses = new Queue<Task<IReadOnlyList<TaskScheme>>>(listResponses);
        }

        public int MutationCalls { get; private set; }

        public async Task<IReadOnlyList<TaskScheme>> ListSchemesAsync(
            CancellationToken cancellationToken = default)
        {
            var schemes = await _listResponses.Dequeue();
            foreach (var scheme in schemes)
            {
                Remember(scheme);
            }

            return schemes;
        }

        public Task<TaskSchemeMutationResponse> CreateSchemeAsync(
            TaskScheme scheme,
            string actor,
            CancellationToken cancellationToken = default)
        {
            MutationCalls++;
            return Task.FromResult(Mutation(Canonical(scheme)));
        }

        public Task<TaskSchemeMutationResponse> CopySchemeAsync(
            string sourceSchemeId,
            string newSchemeId,
            string? nameZh,
            string? nameEn,
            string actor,
            CancellationToken cancellationToken = default)
        {
            MutationCalls++;
            var source = Current(sourceSchemeId);
            var copy = Canonical(source with
            {
                SchemeId = newSchemeId,
                NameZh = nameZh,
                NameEn = nameEn,
                CopiedFromSchemeId = sourceSchemeId,
                SemanticRevision = 0,
            });
            Remember(copy);
            return Task.FromResult(Mutation(copy));
        }

        public Task<TaskSchemeMutationResponse> UpdateSchemeAsync(
            TaskScheme scheme,
            int? expectedSemanticRevision,
            int? expectedLayoutRevision,
            string actor,
            CancellationToken cancellationToken = default)
        {
            MutationCalls++;
            var updated = Canonical(scheme with
            {
                SemanticRevision = scheme.SemanticRevision + 1,
                UpdatedAt = scheme.UpdatedAt.AddMinutes(1),
            });
            Remember(updated);
            return Task.FromResult(Mutation(updated));
        }

        public Task<TaskSchemeMutationResponse> ArchiveSchemeAsync(
            string schemeId,
            int expectedSemanticRevision,
            string actor,
            CancellationToken cancellationToken = default)
        {
            MutationCalls++;
            var source = Current(schemeId);
            var archived = Canonical(source with
            {
                Lifecycle = ModelObjectLifecycle.Archived,
                SemanticRevision = source.SemanticRevision + 1,
                UpdatedAt = source.UpdatedAt.AddMinutes(1),
            });
            Remember(archived);
            return Task.FromResult(Mutation(archived));
        }

        private TaskScheme Current(string schemeId)
        {
            if (_canonical.TryGetValue(schemeId, out var scheme))
            {
                return scheme;
            }

            throw new InvalidOperationException($"Fake scheme {schemeId} was not loaded.");
        }

        private void Remember(TaskScheme scheme) => _canonical[scheme.SchemeId] = scheme;

        private TaskScheme Canonical(TaskScheme scheme) => scheme with
        {
            ContentHash = new string('c', 64),
            LayoutHash = new string('d', 64),
        };

    }
}
