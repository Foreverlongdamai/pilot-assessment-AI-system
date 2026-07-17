using System.Collections.ObjectModel;
using System.Text.Json;

using CommunityToolkit.Mvvm.ComponentModel;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;

namespace PilotAssessment.Desktop.Core.ViewModels;

public sealed partial class TaskSchemeListItemViewModel : ObservableObject
{
    public TaskSchemeListItemViewModel(TaskScheme scheme)
    {
        Scheme = scheme;
    }

    public TaskScheme Scheme { get; }

    public string SchemeId => Scheme.SchemeId;

    public string DisplayName =>
        Scheme.NameEn ?? Scheme.NameZh ?? Scheme.SchemeId;

    public string LocalizedNames => string.Join(
        " / ",
        new[] { Scheme.NameZh, Scheme.NameEn }
            .Where(value => !string.IsNullOrWhiteSpace(value)));

    public string StatusLine =>
        $"{Scheme.TechnicalStatus} • rev {Scheme.SemanticRevision} • " +
        $"{Scheme.ComputedActiveClosure.Length} active";

    public string ClassificationLine
    {
        get
        {
            var values = new List<string>();
            if (!string.IsNullOrWhiteSpace(Scheme.Group))
            {
                values.Add(Scheme.Group);
            }

            values.AddRange(Scheme.Tags);
            if (Scheme.Lifecycle is ModelObjectLifecycle.Archived)
            {
                values.Add("Archived");
            }

            return values.Count == 0 ? "No group or tags" : string.Join(" • ", values);
        }
    }

    public bool IsArchived => Scheme.Lifecycle is ModelObjectLifecycle.Archived;
}

public sealed partial class TaskSchemeListViewModel : ObservableObject
{
    public const string AllTags = "All tags";
    public const string AllGroups = "All groups";

    private readonly IModelWorkspaceGateway _gateway;
    private readonly ApplicationShellState _shellState;
    private readonly List<TaskSchemeListItemViewModel> _allSchemes = [];
    private int _contextGeneration;
    private int _busyOperations;
    private string? _projectId;

    [ObservableProperty]
    public partial string SearchText { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string SelectedTagFilter { get; set; } = AllTags;

    [ObservableProperty]
    public partial string SelectedGroupFilter { get; set; } = AllGroups;

    [ObservableProperty]
    public partial string SelectedSort { get; set; } = "Name";

    [ObservableProperty]
    public partial bool ShowArchived { get; set; }

    [ObservableProperty]
    public partial TaskSchemeListItemViewModel? SelectedScheme { get; set; }

    [ObservableProperty]
    public partial bool IsBusy { get; private set; }

    [ObservableProperty]
    public partial bool HasError { get; private set; }

    [ObservableProperty]
    public partial string ErrorMessage { get; private set; } = string.Empty;

    [ObservableProperty]
    public partial string StatusMessage { get; private set; } =
        "Open a managed project to load its parallel task schemes.";

    public TaskSchemeListViewModel(
        IModelWorkspaceGateway gateway,
        ApplicationShellState shellState)
    {
        _gateway = gateway;
        _shellState = shellState;
        AvailableTags.Add(AllTags);
        AvailableGroups.Add(AllGroups);
    }

    public ObservableCollection<TaskSchemeListItemViewModel> Schemes { get; } = [];

    public ObservableCollection<string> AvailableTags { get; } = [];

    public ObservableCollection<string> AvailableGroups { get; } = [];

    public IReadOnlyList<string> SortOptions { get; } =
        ["Name", "Recently updated", "Identifier"];

    public bool HasSelection => SelectedScheme is not null;

    public bool CanMutate => !IsBusy &&
        SelectedScheme is { IsArchived: false } &&
        !string.IsNullOrWhiteSpace(_projectId);

    public async Task LoadAsync(
        string projectId,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(projectId);
        var generation = Interlocked.Increment(ref _contextGeneration);
        var preferredSchemeId =
            _projectId == projectId ? SelectedScheme?.SchemeId : _shellState.Snapshot.SchemeId;
        _projectId = projectId;
        BeginBusy();
        ClearError();
        StatusMessage = "Loading canonical task schemes…";
        try
        {
            var schemes = await _gateway.ListSchemesAsync(cancellationToken);
            if (!IsCurrentContext(generation, projectId))
            {
                return;
            }

            ReplaceAll(schemes);
            RefreshFiltered(preferredSchemeId);
            StatusMessage = $"Loaded {_allSchemes.Count} canonical task schemes.";
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception error)
        {
            if (IsCurrentContext(generation, projectId))
            {
                SetError(error, "Task schemes could not be loaded.");
            }
        }
        finally
        {
            EndBusy();
        }
    }

    public void Reset()
    {
        Interlocked.Increment(ref _contextGeneration);
        _projectId = null;
        _allSchemes.Clear();
        Schemes.Clear();
        ResetFilterOptions();
        SelectedScheme = null;
        StatusMessage = "Open a managed project to load its parallel task schemes.";
        ClearError();
    }

    public void Select(TaskSchemeListItemViewModel? scheme)
    {
        if (scheme is null || _allSchemes.Any(item => item.SchemeId == scheme.SchemeId))
        {
            SelectedScheme = scheme;
        }
    }

    public async Task<TaskScheme?> CreateAsync(
        string? nameEn,
        string? nameZh,
        CancellationToken cancellationToken = default)
    {
        EnsureProjectOpen();
        var normalizedEn = NormalizeOptional(nameEn);
        var normalizedZh = NormalizeOptional(nameZh);
        if (normalizedEn is null && normalizedZh is null)
        {
            throw new ArgumentException("A task scheme needs an English or Chinese name.");
        }

        var now = DateTime.UtcNow;
        var provisional = new TaskScheme(
            "task-scheme",
            "0.1.0",
            NewSchemeId(),
            normalizedZh,
            normalizedEn,
            null,
            null,
            [],
            null,
            ModelObjectLifecycle.Active,
            null,
            [],
            [],
            [],
            new Dictionary<string, JsonElement>(StringComparer.Ordinal),
            [],
            0,
            0,
            ModelTechnicalStatus.Incomplete,
            [],
            new string('0', 64),
            new string('0', 64),
            now,
            now);

        return await RunMutationAsync(
            token => _gateway.CreateSchemeAsync(provisional, "expert.local", token),
            selectCanonical: true,
            successMessage: "A new parallel task scheme was created.",
            cancellationToken);
    }

    public async Task<TaskScheme?> CopySelectedAsync(
        string? nameEn = null,
        string? nameZh = null,
        CancellationToken cancellationToken = default)
    {
        var source = RequireEditableSelection();
        var copyNameEn = NormalizeOptional(nameEn) ?? AppendCopy(source.Scheme.NameEn, "Copy");
        var copyNameZh = NormalizeOptional(nameZh) ?? AppendCopy(source.Scheme.NameZh, "副本");
        if (copyNameEn is null && copyNameZh is null)
        {
            copyNameEn = $"{source.SchemeId} Copy";
        }

        return await RunMutationAsync(
            token => _gateway.CopySchemeAsync(
                source.SchemeId,
                NewSchemeId(),
                copyNameZh,
                copyNameEn,
                "expert.local",
                token),
            selectCanonical: true,
            successMessage: "The copied scheme is now a separate editable task.",
            cancellationToken);
    }

    public async Task<TaskScheme?> RenameSelectedAsync(
        string? nameEn,
        string? nameZh,
        CancellationToken cancellationToken = default)
    {
        var selected = RequireEditableSelection();
        var normalizedEn = NormalizeOptional(nameEn);
        var normalizedZh = NormalizeOptional(nameZh);
        if (normalizedEn is null && normalizedZh is null)
        {
            throw new ArgumentException("A task scheme needs an English or Chinese name.");
        }

        var candidate = selected.Scheme with
        {
            NameEn = normalizedEn,
            NameZh = normalizedZh,
        };
        return await RunMutationAsync(
            token => _gateway.UpdateSchemeAsync(
                candidate,
                selected.Scheme.SemanticRevision,
                null,
                "expert.local",
                token),
            selectCanonical: false,
            successMessage: "The task scheme name was autosaved by the backend.",
            cancellationToken);
    }

    public async Task<TaskScheme?> ArchiveSelectedAsync(
        CancellationToken cancellationToken = default)
    {
        var selected = RequireEditableSelection();
        return await RunMutationAsync(
            token => _gateway.ArchiveSchemeAsync(
                selected.SchemeId,
                selected.Scheme.SemanticRevision,
                "expert.local",
                token),
            selectCanonical: false,
            successMessage: "The task scheme was archived; no other scheme was overwritten.",
            cancellationToken,
            selectReplacementWhenHidden: true);
    }

    partial void OnSearchTextChanged(string value) => RefreshFiltered();

    partial void OnSelectedTagFilterChanged(string value) => RefreshFiltered();

    partial void OnSelectedGroupFilterChanged(string value) => RefreshFiltered();

    partial void OnSelectedSortChanged(string value) => RefreshFiltered();

    partial void OnShowArchivedChanged(bool value) => RefreshFiltered();

    partial void OnSelectedSchemeChanged(TaskSchemeListItemViewModel? value)
    {
        OnPropertyChanged(nameof(HasSelection));
        OnPropertyChanged(nameof(CanMutate));
        var snapshot = _shellState.Snapshot;
        if (!string.IsNullOrWhiteSpace(snapshot.ProjectId) && snapshot.ProjectId == _projectId)
        {
            _shellState.SetProjectContext(snapshot.ProjectId, snapshot.SessionId, value?.SchemeId);
        }
    }

    partial void OnIsBusyChanged(bool value) => OnPropertyChanged(nameof(CanMutate));

    private async Task<TaskScheme?> RunMutationAsync(
        Func<CancellationToken, Task<TaskSchemeMutationResponse>> operation,
        bool selectCanonical,
        string successMessage,
        CancellationToken cancellationToken,
        bool selectReplacementWhenHidden = false)
    {
        ArgumentNullException.ThrowIfNull(operation);
        EnsureProjectOpen();
        var generation = Volatile.Read(ref _contextGeneration);
        var projectId = _projectId!;
        var previouslySelectedId = SelectedScheme?.SchemeId;
        BeginBusy();
        ClearError();
        StatusMessage = "Saving through the canonical backend…";
        try
        {
            var response = await operation(cancellationToken);
            if (!IsCurrentContext(generation, projectId))
            {
                return null;
            }

            Reconcile(response.Scheme);
            RefreshFilterOptions();
            RefreshFiltered();
            var canonicalItem = _allSchemes.Single(item => item.SchemeId == response.Scheme.SchemeId);
            if (selectCanonical)
            {
                SelectedScheme = canonicalItem;
            }
            else if (selectReplacementWhenHidden &&
                     canonicalItem.IsArchived &&
                     !ShowArchived)
            {
                SelectedScheme = Schemes.FirstOrDefault(item => !item.IsArchived);
            }
            else
            {
                SelectedScheme = _allSchemes.FirstOrDefault(
                    item => item.SchemeId == previouslySelectedId) ?? canonicalItem;
            }

            StatusMessage = successMessage;
            return response.Scheme;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception error)
        {
            if (IsCurrentContext(generation, projectId))
            {
                SetError(error, "The task-scheme change did not complete.");
            }

            return null;
        }
        finally
        {
            EndBusy();
        }
    }

    private void ReplaceAll(IEnumerable<TaskScheme> schemes)
    {
        _allSchemes.Clear();
        _allSchemes.AddRange(
            schemes
                .OrderBy(scheme => scheme.SchemeId, StringComparer.Ordinal)
                .Select(scheme => new TaskSchemeListItemViewModel(scheme)));
        RefreshFilterOptions();
    }

    private void Reconcile(TaskScheme canonical)
    {
        var index = _allSchemes.FindIndex(item => item.SchemeId == canonical.SchemeId);
        var replacement = new TaskSchemeListItemViewModel(canonical);
        if (index < 0)
        {
            _allSchemes.Add(replacement);
        }
        else
        {
            _allSchemes[index] = replacement;
        }
    }

    private void RefreshFiltered(string? preferredSchemeId = null)
    {
        if (_projectId is null)
        {
            return;
        }

        var selectedId = preferredSchemeId ?? SelectedScheme?.SchemeId;
        IEnumerable<TaskSchemeListItemViewModel> query = _allSchemes;
        if (!ShowArchived)
        {
            query = query.Where(item => !item.IsArchived);
        }

        if (!string.IsNullOrWhiteSpace(SearchText))
        {
            var search = SearchText.Trim();
            query = query.Where(item =>
                item.SchemeId.Contains(search, StringComparison.OrdinalIgnoreCase) ||
                (item.Scheme.NameEn?.Contains(search, StringComparison.OrdinalIgnoreCase) ?? false) ||
                (item.Scheme.NameZh?.Contains(search, StringComparison.OrdinalIgnoreCase) ?? false) ||
                item.Scheme.Tags.Any(tag => tag.Contains(search, StringComparison.OrdinalIgnoreCase)) ||
                (item.Scheme.Group?.Contains(search, StringComparison.OrdinalIgnoreCase) ?? false));
        }

        if (SelectedTagFilter != AllTags)
        {
            query = query.Where(item => item.Scheme.Tags.Contains(SelectedTagFilter));
        }

        if (SelectedGroupFilter != AllGroups)
        {
            query = query.Where(item => item.Scheme.Group == SelectedGroupFilter);
        }

        query = SelectedSort switch
        {
            "Recently updated" => query
                .OrderByDescending(item => item.Scheme.UpdatedAt)
                .ThenBy(item => item.DisplayName, StringComparer.OrdinalIgnoreCase),
            "Identifier" => query.OrderBy(item => item.SchemeId, StringComparer.Ordinal),
            _ => query
                .OrderBy(item => item.DisplayName, StringComparer.OrdinalIgnoreCase)
                .ThenBy(item => item.SchemeId, StringComparer.Ordinal),
        };

        Schemes.Clear();
        foreach (var item in query)
        {
            Schemes.Add(item);
        }

        var preferred = _allSchemes.FirstOrDefault(item => item.SchemeId == selectedId);
        SelectedScheme = preferred ?? Schemes.FirstOrDefault(item => !item.IsArchived) ?? Schemes.FirstOrDefault();
    }

    private void RefreshFilterOptions()
    {
        var selectedTag = SelectedTagFilter;
        var selectedGroup = SelectedGroupFilter;
        ReplaceOptions(
            AvailableTags,
            AllTags,
            _allSchemes.SelectMany(item => item.Scheme.Tags));
        ReplaceOptions(
            AvailableGroups,
            AllGroups,
            _allSchemes.Select(item => item.Scheme.Group).OfType<string>());
        SelectedTagFilter = AvailableTags.Contains(selectedTag) ? selectedTag : AllTags;
        SelectedGroupFilter = AvailableGroups.Contains(selectedGroup) ? selectedGroup : AllGroups;
    }

    private void ResetFilterOptions()
    {
        AvailableTags.Clear();
        AvailableTags.Add(AllTags);
        AvailableGroups.Clear();
        AvailableGroups.Add(AllGroups);
        SelectedTagFilter = AllTags;
        SelectedGroupFilter = AllGroups;
    }

    private static void ReplaceOptions(
        ObservableCollection<string> target,
        string allLabel,
        IEnumerable<string> values)
    {
        target.Clear();
        target.Add(allLabel);
        foreach (var value in values
                     .Where(item => !string.IsNullOrWhiteSpace(item))
                     .Distinct(StringComparer.Ordinal)
                     .OrderBy(item => item, StringComparer.Ordinal))
        {
            target.Add(value);
        }
    }

    private TaskSchemeListItemViewModel RequireEditableSelection()
    {
        EnsureProjectOpen();
        return SelectedScheme switch
        {
            null => throw new InvalidOperationException("Select a task scheme first."),
            { IsArchived: true } => throw new InvalidOperationException(
                "Archived task schemes are read-only."),
            var selected => selected,
        };
    }

    private void EnsureProjectOpen()
    {
        if (string.IsNullOrWhiteSpace(_projectId))
        {
            throw new InvalidOperationException("Open a managed project first.");
        }
    }

    private bool IsCurrentContext(int generation, string projectId) =>
        generation == Volatile.Read(ref _contextGeneration) &&
        string.Equals(_projectId, projectId, StringComparison.Ordinal) &&
        string.Equals(_shellState.Snapshot.ProjectId, projectId, StringComparison.Ordinal);

    private void BeginBusy()
    {
        _busyOperations++;
        IsBusy = true;
    }

    private void EndBusy()
    {
        _busyOperations = Math.Max(0, _busyOperations - 1);
        IsBusy = _busyOperations > 0;
    }

    private void ClearError()
    {
        HasError = false;
        ErrorMessage = string.Empty;
    }

    private void SetError(Exception error, string status)
    {
        HasError = true;
        ErrorMessage = error.Message;
        StatusMessage = status;
    }

    private static string NewSchemeId() => $"task-scheme.user.{Guid.NewGuid():N}";

    private static string? NormalizeOptional(string? value) =>
        string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static string? AppendCopy(string? value, string suffix) =>
        string.IsNullOrWhiteSpace(value) ? null : $"{value.Trim()} {suffix}";
}

public interface IModelWorkspaceGateway
{
    Task<IReadOnlyList<TaskScheme>> ListSchemesAsync(
        CancellationToken cancellationToken = default);

    Task<TaskSchemeMutationResponse> CreateSchemeAsync(
        TaskScheme scheme,
        string actor,
        CancellationToken cancellationToken = default);

    Task<TaskSchemeMutationResponse> CopySchemeAsync(
        string sourceSchemeId,
        string newSchemeId,
        string? nameZh,
        string? nameEn,
        string actor,
        CancellationToken cancellationToken = default);

    Task<TaskSchemeMutationResponse> UpdateSchemeAsync(
        TaskScheme scheme,
        int? expectedSemanticRevision,
        int? expectedLayoutRevision,
        string actor,
        CancellationToken cancellationToken = default);

    Task<TaskSchemeMutationResponse> ArchiveSchemeAsync(
        string schemeId,
        int expectedSemanticRevision,
        string actor,
        CancellationToken cancellationToken = default);
}
