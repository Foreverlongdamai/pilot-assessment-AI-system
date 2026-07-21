using System.Collections.ObjectModel;

using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;

namespace PilotAssessment.Desktop.Core.ViewModels;

public partial class ProjectLauncherViewModel : ObservableObject
{
    private const int RecentProjectLimit = 12;
    private readonly IProjectSessionGateway _gateway;
    private readonly IProjectFolderPicker _folderPicker;
    private readonly IRecentProjectStore _recentStore;
    private readonly ApplicationShellState _shellState;
    private readonly SessionExplorerViewModel _sessions;
    private readonly TaskSchemeListViewModel? _schemes;
    private readonly ILocalizationLookup? _localization;
    private string _statusKey = "Project_StatusStart";
    private object?[] _statusArguments = [];

    [ObservableProperty]
    public partial string ProjectName { get; set; } = "Pilot Assessment Project";

    [ObservableProperty]
    public partial string CreateRootPath { get; private set; } = string.Empty;

    [ObservableProperty]
    public partial ProjectDescriptor? CurrentProject { get; private set; }

    [ObservableProperty]
    public partial string? CurrentProjectRoot { get; private set; }

    [ObservableProperty]
    public partial bool IsBusy { get; private set; }

    [ObservableProperty]
    public partial bool HasError { get; private set; }

    [ObservableProperty]
    public partial string ErrorMessage { get; private set; } = string.Empty;

    [ObservableProperty]
    public partial string StatusMessage { get; private set; } =
        "Create a portable managed project or open an existing one.";

    public ObservableCollection<RecentProjectEntry> RecentProjects { get; } = [];

    public bool HasOpenProject => CurrentProject is not null;

    public string CurrentProjectText => CurrentProject is null
        ? L("Project_NoOpenProject", "No managed project is open.")
        : CurrentProject.Name;

    public string CurrentProjectRootText => CurrentProjectRoot ??
        L("Project_NoProjectFolder", "No project folder");

    public bool CanCreate =>
        !IsBusy &&
        !string.IsNullOrWhiteSpace(CreateRootPath) &&
        !string.IsNullOrWhiteSpace(ProjectName);

    public ProjectLauncherViewModel(
        IProjectSessionGateway gateway,
        IProjectFolderPicker folderPicker,
        IRecentProjectStore recentStore,
        ApplicationShellState shellState,
        SessionExplorerViewModel sessions,
        TaskSchemeListViewModel? schemes = null,
        ILocalizationLookup? localization = null)
    {
        _gateway = gateway;
        _folderPicker = folderPicker;
        _recentStore = recentStore;
        _shellState = shellState;
        _sessions = sessions;
        _schemes = schemes;
        _localization = localization;
        _localization?.LanguageChanged += OnLanguageChanged;
        SetStatus("Project_StatusStart", "Create a portable managed project or open an existing one.");
    }

    public async Task<bool> InitializeAsync(
        bool restoreLastProject,
        CancellationToken cancellationToken = default)
    {
        await ReloadRecentAsync(cancellationToken);
        if (!restoreLastProject || RecentProjects.Count == 0)
        {
            return CurrentProject is not null;
        }

        await OpenRootAsync(RecentProjects[0].RootPath, cancellationToken);
        return CurrentProject is not null;
    }

    [RelayCommand]
    private async Task ChooseCreateFolderAsync()
    {
        var selected = await _folderPicker.PickFolderAsync(
            L("Project_Create", "Create managed project"));
        if (string.IsNullOrWhiteSpace(selected))
        {
            SetStatus("Project_StatusCreateCancelled", "Project folder selection cancelled; nothing changed.");
            return;
        }

        CreateRootPath = selected;
        CreateProjectCommand.NotifyCanExecuteChanged();
    }

    [RelayCommand(CanExecute = nameof(CanCreate))]
    private Task CreateProjectAsync() => RunBusyAsync(async () =>
    {
        await CloseForSwitchAsync(CreateRootPath);
        var project = await _gateway.CreateProjectAsync(
            CreateRootPath,
            ProjectName,
            "expert.local");
        await ActivateProjectAsync(project, CreateRootPath);
        SetStatus("Project_StatusCreated", "Managed project created and opened from the backend canonical descriptor.");
    });

    [RelayCommand]
    private async Task OpenProjectAsync()
    {
        var selected = await _folderPicker.PickFolderAsync(
            L("Project_OpenManaged", "Open managed project"));
        if (string.IsNullOrWhiteSpace(selected))
        {
            SetStatus("Project_StatusOpenCancelled", "Open project cancelled; the current project was not changed.");
            return;
        }

        await OpenRootAsync(selected);
    }

    [RelayCommand]
    private Task OpenRecentAsync(RecentProjectEntry? entry) => entry is null
        ? Task.CompletedTask
        : OpenRootAsync(entry.RootPath);

    [RelayCommand(CanExecute = nameof(HasOpenProject))]
    private Task CloseProjectAsync() => RunBusyAsync(async () =>
    {
        await _gateway.CloseProjectAsync();
        ClearCurrentProject();
        SetStatus("Project_StatusClosed", "Project closed. Recent-project entries are only local shortcuts.");
    });

    partial void OnProjectNameChanged(string value) => CreateProjectCommand.NotifyCanExecuteChanged();

    partial void OnIsBusyChanged(bool value)
    {
        CreateProjectCommand.NotifyCanExecuteChanged();
        CloseProjectCommand.NotifyCanExecuteChanged();
    }

    private Task OpenRootAsync(string root, CancellationToken cancellationToken = default) =>
        RunBusyAsync(async () =>
        {
            if (CurrentProject is not null && SamePath(CurrentProjectRoot, root))
            {
                SetStatus("Project_StatusAlreadyOpen", "That managed project is already open.");
                return;
            }

            await CloseForSwitchAsync(root, cancellationToken);
            var project = await _gateway.OpenProjectAsync(root, cancellationToken);
            await ActivateProjectAsync(project, root, cancellationToken);
            SetStatus("Project_StatusOpened", "Managed project opened; canonical sessions were reloaded from SQLite.");
        });

    private async Task CloseForSwitchAsync(
        string targetRoot,
        CancellationToken cancellationToken = default)
    {
        if (CurrentProject is null || SamePath(CurrentProjectRoot, targetRoot))
        {
            return;
        }

        await _gateway.CloseProjectAsync(cancellationToken);
        ClearCurrentProject();
    }

    private async Task ActivateProjectAsync(
        ProjectDescriptor project,
        string root,
        CancellationToken cancellationToken = default)
    {
        CurrentProject = project;
        CurrentProjectRoot = root;
        _shellState.SetProjectContext(
            project.ProjectId,
            schemeId: _schemes?.SelectedScheme?.SchemeId ?? _shellState.Snapshot.SchemeId);
        OnPropertyChanged(nameof(HasOpenProject));
        OnPropertyChanged(nameof(CurrentProjectText));
        OnPropertyChanged(nameof(CurrentProjectRootText));
        CloseProjectCommand.NotifyCanExecuteChanged();
        await TouchRecentAsync(project, root, cancellationToken);
        await _sessions.LoadAsync(project.ProjectId, cancellationToken: cancellationToken);
    }

    private void ClearCurrentProject()
    {
        CurrentProject = null;
        CurrentProjectRoot = null;
        var selectedSchemeId = _schemes?.SelectedScheme?.SchemeId ?? _shellState.Snapshot.SchemeId;
        _shellState.SetProjectContext(null);
        _shellState.SetSchemeContext(selectedSchemeId);
        _sessions.Reset();
        OnPropertyChanged(nameof(HasOpenProject));
        OnPropertyChanged(nameof(CurrentProjectText));
        OnPropertyChanged(nameof(CurrentProjectRootText));
        CloseProjectCommand.NotifyCanExecuteChanged();
    }

    private async Task TouchRecentAsync(
        ProjectDescriptor project,
        string root,
        CancellationToken cancellationToken)
    {
        var updated = RecentProjects
            .Where(item => !SamePath(item.RootPath, root))
            .Prepend(new RecentProjectEntry(root, project.ProjectId, project.Name, DateTime.UtcNow))
            .Take(RecentProjectLimit)
            .ToArray();
        await _recentStore.SaveAsync(updated, cancellationToken);
        ReplaceRecent(updated);
    }

    private async Task ReloadRecentAsync(CancellationToken cancellationToken)
    {
        var stored = await _recentStore.LoadAsync(cancellationToken);
        ReplaceRecent(stored.OrderByDescending(item => item.LastOpenedAt).Take(RecentProjectLimit));
    }

    private void ReplaceRecent(IEnumerable<RecentProjectEntry> projects)
    {
        RecentProjects.Clear();
        foreach (var project in projects)
        {
            RecentProjects.Add(project);
        }
    }

    private async Task RunBusyAsync(Func<Task> operation)
    {
        if (IsBusy)
        {
            return;
        }

        IsBusy = true;
        ClearError();
        try
        {
            await operation();
        }
        catch (Exception error)
        {
            HasError = true;
            ErrorMessage = error.Message;
            SetStatus("Project_StatusFailed", "The project operation did not complete.");
        }
        finally
        {
            IsBusy = false;
        }
    }

    private void ClearError()
    {
        HasError = false;
        ErrorMessage = string.Empty;
    }

    private void OnLanguageChanged(object? sender, EventArgs args)
    {
        OnPropertyChanged(nameof(CurrentProjectText));
        OnPropertyChanged(nameof(CurrentProjectRootText));
        StatusMessage = _localization?.Format(_statusKey, _statusArguments) ?? StatusMessage;
    }

    private void SetStatus(string key, string fallback, params object?[] arguments)
    {
        _statusKey = key;
        _statusArguments = arguments;
        StatusMessage = _localization?.Format(key, arguments) ??
            string.Format(fallback, arguments);
    }

    private string L(string key, string fallback) => _localization?[key] ?? fallback;

    private static bool SamePath(string? left, string right)
    {
        if (string.IsNullOrWhiteSpace(left))
        {
            return false;
        }

        return string.Equals(
            Path.TrimEndingDirectorySeparator(Path.GetFullPath(left)),
            Path.TrimEndingDirectorySeparator(Path.GetFullPath(right)),
            StringComparison.OrdinalIgnoreCase);
    }
}
