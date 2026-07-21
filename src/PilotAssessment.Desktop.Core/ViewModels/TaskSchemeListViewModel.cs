using System.Collections.ObjectModel;
using System.Text.Json;

using CommunityToolkit.Mvvm.ComponentModel;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;

namespace PilotAssessment.Desktop.Core.ViewModels;

public sealed partial class TaskSchemeListItemViewModel : ObservableObject
{
    private readonly ILocalizationLookup? _localization;

    public TaskSchemeListItemViewModel(
        TaskScheme scheme,
        ILocalizationLookup? localization = null)
    {
        Scheme = scheme;
        _localization = localization;
    }

    public TaskScheme Scheme { get; private set; }

    public string SchemeId => Scheme.SchemeId;

    public string DisplayName => ModelDisplayNameResolver.ForScheme(Scheme);

    public string LocalizedNames => DisplayName;

    public string StatusLine => _localization?.Format(
            "Task_StatusLine",
            Scheme.TechnicalStatus,
            Scheme.SemanticRevision,
            Scheme.ComputedActiveClosure.Length)
        ?? $"{Scheme.TechnicalStatus} • rev {Scheme.SemanticRevision} • " +
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
                values.Add(_localization?["Task_Archived"] ?? "Archived");
            }

            return values.Count == 0
                ? _localization?["Task_NoGroupTags"] ?? "No group or tags"
                : string.Join(" • ", values);
        }
    }

    public bool IsArchived => Scheme.Lifecycle is ModelObjectLifecycle.Archived;

    public void Reconcile(TaskScheme canonical)
    {
        ArgumentNullException.ThrowIfNull(canonical);
        if (!string.Equals(SchemeId, canonical.SchemeId, StringComparison.Ordinal))
        {
            throw new ArgumentException("Canonical scheme identity cannot change.", nameof(canonical));
        }

        Scheme = canonical;
        OnPropertyChanged(nameof(Scheme));
        OnPropertyChanged(nameof(DisplayName));
        OnPropertyChanged(nameof(LocalizedNames));
        OnPropertyChanged(nameof(StatusLine));
        OnPropertyChanged(nameof(ClassificationLine));
        OnPropertyChanged(nameof(IsArchived));
    }

    public void RefreshPresentation()
    {
        OnPropertyChanged(nameof(DisplayName));
        OnPropertyChanged(nameof(LocalizedNames));
        OnPropertyChanged(nameof(StatusLine));
        OnPropertyChanged(nameof(ClassificationLine));
    }
}

public sealed partial class TaskSchemeListViewModel : ObservableObject
{
    public const string AllTags = "All tags";
    public const string AllGroups = "All groups";

    private readonly IModelWorkspaceGateway _gateway;
    private readonly ApplicationShellState _shellState;
    private readonly ILocalizationLookup? _localization;
    private readonly List<TaskSchemeListItemViewModel> _allSchemes = [];
    private int _contextGeneration;
    private int _busyOperations;
    private string? _projectId;
    private string _allTagsLabel = AllTags;
    private string _allGroupsLabel = AllGroups;
    private string _sortNameLabel = "Name";
    private string _sortUpdatedLabel = "Recently updated";
    private string _sortIdentifierLabel = "Identifier";
    private string _statusKey = "Task_StatusStart";
    private object?[] _statusArguments = [];

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
        "Connect to the local backend to load the shared system task schemes.";

    public TaskSchemeListViewModel(
        IModelWorkspaceGateway gateway,
        ApplicationShellState shellState,
        ILocalizationLookup? localization = null)
    {
        _gateway = gateway;
        _shellState = shellState;
        _localization = localization;
        RefreshLocalizedLabels();
        AvailableTags.Add(_allTagsLabel);
        AvailableGroups.Add(_allGroupsLabel);
        SelectedTagFilter = _allTagsLabel;
        SelectedGroupFilter = _allGroupsLabel;
        SelectedSort = _sortNameLabel;
        _localization?.LanguageChanged += OnLanguageChanged;
        SetStatus(
            "Task_StatusStart",
            "Connect to the local backend to load the shared system task schemes.");
    }

    public ObservableCollection<TaskSchemeListItemViewModel> Schemes { get; } = [];

    public ObservableCollection<string> AvailableTags { get; } = [];

    public ObservableCollection<string> AvailableGroups { get; } = [];

    public ObservableCollection<string> SortOptions { get; } = [];

    public bool HasSelection => SelectedScheme is not null;

    public bool CanMutate => !IsBusy &&
        SelectedScheme is { IsArchived: false } &&
        !string.IsNullOrWhiteSpace(_projectId);

    public TaskScheme? FindScheme(string schemeId)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(schemeId);
        return _allSchemes
            .FirstOrDefault(item => item.SchemeId == schemeId)
            ?.Scheme;
    }

    public int CountCurrentSchemesUsingNode(string nodeId)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(nodeId);
        return _allSchemes.Count(item =>
            !item.IsArchived &&
            item.Scheme.ComputedActiveClosure.Contains(nodeId, StringComparer.Ordinal));
    }

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
        SetStatus("Task_StatusLoading", "Loading canonical task schemes…");
        try
        {
            var schemes = await _gateway.ListSchemesAsync(cancellationToken);
            if (!IsCurrentContext(generation, projectId))
            {
                return;
            }

            ReplaceAll(schemes);
            RefreshFiltered(preferredSchemeId);
            SetStatus("Task_StatusLoaded", "Loaded {0} canonical task schemes.", _allSchemes.Count);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception error)
        {
            if (IsCurrentContext(generation, projectId))
            {
                SetError(error, "Task_StatusLoadFailed", "Task schemes could not be loaded.");
            }
        }
        finally
        {
            EndBusy();
        }
    }

    public Task LoadSystemAsync(CancellationToken cancellationToken = default) =>
        LoadAsync(SystemModelContext.Key, cancellationToken);

    public void Reset()
    {
        Interlocked.Increment(ref _contextGeneration);
        _projectId = null;
        _allSchemes.Clear();
        Schemes.Clear();
        ResetFilterOptions();
        SelectedScheme = null;
        SetStatus(
            "Task_StatusStart",
            "Connect to the local backend to load the shared system task schemes.");
        ClearError();
    }

    public void Select(TaskSchemeListItemViewModel? scheme)
    {
        if (scheme is null || _allSchemes.Any(item => item.SchemeId == scheme.SchemeId))
        {
            SelectedScheme = scheme;
        }
    }

    public void ApplyCanonical(TaskScheme canonical)
    {
        ArgumentNullException.ThrowIfNull(canonical);
        var selectedId = SelectedScheme?.SchemeId;
        Reconcile(canonical);
        RefreshFilterOptions();
        RefreshFiltered(selectedId);
    }

    public async Task<TaskScheme?> CreateAsync(
        string name,
        CancellationToken cancellationToken = default)
    {
        EnsureProjectOpen();
        var canonicalName = NormalizeOptional(name)
            ?? throw new ArgumentException("A task scheme needs a canonical English name.");

        var now = DateTime.UtcNow;
        var provisional = new TaskScheme(
            "task-scheme",
            "0.2.0",
            NewSchemeId(),
            canonicalName,
            "Expert-created editable task scheme.",
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
            successKey: "Task_StatusCreated",
            successFallback: "A new parallel task scheme was created.",
            cancellationToken);
    }

    public async Task<TaskScheme?> CopySelectedAsync(
        string? name = null,
        CancellationToken cancellationToken = default)
    {
        var source = RequireEditableSelection();
        var copyName = NormalizeOptional(name) ?? AppendCopy(source.Scheme.Name, "Copy")
            ?? $"{source.SchemeId} Copy";

        return await RunMutationAsync(
            token => _gateway.CopySchemeAsync(
                source.SchemeId,
                NewSchemeId(),
                copyName,
                "expert.local",
                token),
            selectCanonical: true,
            successKey: "Task_StatusCopied",
            successFallback: "The copied scheme is now a separate editable task.",
            cancellationToken);
    }

    public async Task<TaskScheme?> RenameSelectedAsync(
        string name,
        CancellationToken cancellationToken = default)
    {
        var selected = RequireEditableSelection();
        var canonicalName = NormalizeOptional(name)
            ?? throw new ArgumentException("A task scheme needs a canonical English name.");

        var candidate = selected.Scheme with
        {
            Name = canonicalName,
        };
        return await RunMutationAsync(
            token => _gateway.UpdateSchemeAsync(
                candidate,
                selected.Scheme.SemanticRevision,
                null,
                "expert.local",
                token),
            selectCanonical: false,
            successKey: "Task_StatusRenamed",
            successFallback: "The task scheme name was autosaved by the backend.",
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
            successKey: "Task_StatusArchived",
            successFallback: "The task scheme was archived; no other scheme was overwritten.",
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
        _shellState.SetSchemeContext(value?.SchemeId);
    }

    partial void OnIsBusyChanged(bool value) => OnPropertyChanged(nameof(CanMutate));

    private async Task<TaskScheme?> RunMutationAsync(
        Func<CancellationToken, Task<TaskSchemeMutationResponse>> operation,
        bool selectCanonical,
        string successKey,
        string successFallback,
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
        SetStatus("Task_StatusSaving", "Saving through the canonical backend…");
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

            SetStatus(successKey, successFallback);
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
                SetError(error, "Task_StatusChangeFailed", "The task-scheme change did not complete.");
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
                .Select(scheme => new TaskSchemeListItemViewModel(scheme, _localization)));
        RefreshFilterOptions();
    }

    private void Reconcile(TaskScheme canonical)
    {
        var index = _allSchemes.FindIndex(item => item.SchemeId == canonical.SchemeId);
        if (index < 0)
        {
            _allSchemes.Add(new TaskSchemeListItemViewModel(canonical, _localization));
        }
        else
        {
            _allSchemes[index].Reconcile(canonical);
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
                item.Scheme.Name.Contains(search, StringComparison.OrdinalIgnoreCase) ||
                item.Scheme.Description.Contains(search, StringComparison.OrdinalIgnoreCase) ||
                item.Scheme.Tags.Any(tag => tag.Contains(search, StringComparison.OrdinalIgnoreCase)) ||
                (item.Scheme.Group?.Contains(search, StringComparison.OrdinalIgnoreCase) ?? false));
        }

        if (SelectedTagFilter != _allTagsLabel)
        {
            query = query.Where(item => item.Scheme.Tags.Contains(SelectedTagFilter));
        }

        if (SelectedGroupFilter != _allGroupsLabel)
        {
            query = query.Where(item => item.Scheme.Group == SelectedGroupFilter);
        }

        query = SelectedSort switch
        {
            var value when value == _sortUpdatedLabel => query
                .OrderByDescending(item => item.Scheme.UpdatedAt)
                .ThenBy(item => item.DisplayName, StringComparer.OrdinalIgnoreCase),
            var value when value == _sortIdentifierLabel =>
                query.OrderBy(item => item.SchemeId, StringComparer.Ordinal),
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
            _allTagsLabel,
            _allSchemes.SelectMany(item => item.Scheme.Tags));
        ReplaceOptions(
            AvailableGroups,
            _allGroupsLabel,
            _allSchemes.Select(item => item.Scheme.Group).OfType<string>());
        SelectedTagFilter = AvailableTags.Contains(selectedTag) ? selectedTag : _allTagsLabel;
        SelectedGroupFilter = AvailableGroups.Contains(selectedGroup) ? selectedGroup : _allGroupsLabel;
    }

    private void ResetFilterOptions()
    {
        AvailableTags.Clear();
        AvailableTags.Add(_allTagsLabel);
        AvailableGroups.Clear();
        AvailableGroups.Add(_allGroupsLabel);
        SelectedTagFilter = _allTagsLabel;
        SelectedGroupFilter = _allGroupsLabel;
    }

    private void OnLanguageChanged(object? sender, EventArgs args)
    {
        var tagWasAll = SelectedTagFilter == _allTagsLabel;
        var groupWasAll = SelectedGroupFilter == _allGroupsLabel;
        var sortWasUpdated = SelectedSort == _sortUpdatedLabel;
        var sortWasIdentifier = SelectedSort == _sortIdentifierLabel;
        var selectedId = SelectedScheme?.SchemeId;

        RefreshLocalizedLabels();
        SelectedTagFilter = tagWasAll ? _allTagsLabel : SelectedTagFilter;
        SelectedGroupFilter = groupWasAll ? _allGroupsLabel : SelectedGroupFilter;
        SelectedSort = sortWasUpdated
            ? _sortUpdatedLabel
            : sortWasIdentifier
                ? _sortIdentifierLabel
                : _sortNameLabel;
        foreach (var scheme in _allSchemes)
        {
            scheme.RefreshPresentation();
        }

        RefreshFilterOptions();
        RefreshFiltered(selectedId);
        StatusMessage = _localization?.Format(_statusKey, _statusArguments) ?? StatusMessage;
    }

    private void RefreshLocalizedLabels()
    {
        _allTagsLabel = _localization?["Task_AllTags"] ?? AllTags;
        _allGroupsLabel = _localization?["Task_AllGroups"] ?? AllGroups;
        _sortNameLabel = _localization?["Task_SortName"] ?? "Name";
        _sortUpdatedLabel = _localization?["Task_SortUpdated"] ?? "Recently updated";
        _sortIdentifierLabel = _localization?["Task_SortIdentifier"] ?? "Identifier";
        SortOptions.Clear();
        SortOptions.Add(_sortNameLabel);
        SortOptions.Add(_sortUpdatedLabel);
        SortOptions.Add(_sortIdentifierLabel);
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
            throw new InvalidOperationException("Load the system model library first.");
        }
    }

    private bool IsCurrentContext(int generation, string projectId) =>
        generation == Volatile.Read(ref _contextGeneration) &&
        string.Equals(_projectId, projectId, StringComparison.Ordinal);

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

    private void SetError(Exception error, string statusKey, string statusFallback)
    {
        HasError = true;
        ErrorMessage = error.Message;
        SetStatus(statusKey, statusFallback);
    }

    private void SetStatus(string key, string fallback, params object?[] arguments)
    {
        _statusKey = key;
        _statusArguments = arguments;
        StatusMessage = _localization?.Format(key, arguments) ??
            string.Format(fallback, arguments);
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
        string? name,
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
