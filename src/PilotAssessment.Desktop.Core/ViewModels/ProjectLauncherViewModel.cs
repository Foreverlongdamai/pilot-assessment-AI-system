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

    [ObservableProperty]
    public partial string ProjectName { get; set; } = "Pilot Assessment Project";

    [ObservableProperty]
    public partial string ProjectId { get; set; } = $"project.{Guid.NewGuid():N}";

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
        ? "No managed project is open."
        : $"{CurrentProject.Name} · {CurrentProject.ProjectId}";

    public string CurrentProjectRootText => CurrentProjectRoot ?? "No project folder";

    public bool CanCreate =>
        !IsBusy &&
        !string.IsNullOrWhiteSpace(CreateRootPath) &&
        !string.IsNullOrWhiteSpace(ProjectId) &&
        !string.IsNullOrWhiteSpace(ProjectName);

    public ProjectLauncherViewModel(
        IProjectSessionGateway gateway,
        IProjectFolderPicker folderPicker,
        IRecentProjectStore recentStore,
        ApplicationShellState shellState,
        SessionExplorerViewModel sessions,
        TaskSchemeListViewModel? schemes = null)
    {
        _gateway = gateway;
        _folderPicker = folderPicker;
        _recentStore = recentStore;
        _shellState = shellState;
        _sessions = sessions;
        _schemes = schemes;
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
        var selected = await _folderPicker.PickFolderAsync("Create managed project");
        if (string.IsNullOrWhiteSpace(selected))
        {
            StatusMessage = "Project folder selection cancelled; nothing changed.";
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
            ProjectId,
            ProjectName,
            "expert.local");
        await ActivateProjectAsync(project, CreateRootPath);
        StatusMessage = "Managed project created and opened from the backend canonical descriptor.";
    });

    [RelayCommand]
    private async Task OpenProjectAsync()
    {
        var selected = await _folderPicker.PickFolderAsync("Open managed project");
        if (string.IsNullOrWhiteSpace(selected))
        {
            StatusMessage = "Open project cancelled; the current project was not changed.";
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
        StatusMessage = "Project closed. Recent-project entries are only local shortcuts.";
    });

    partial void OnProjectNameChanged(string value) => CreateProjectCommand.NotifyCanExecuteChanged();

    partial void OnProjectIdChanged(string value) => CreateProjectCommand.NotifyCanExecuteChanged();

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
                StatusMessage = "That managed project is already open.";
                return;
            }

            await CloseForSwitchAsync(root, cancellationToken);
            var project = await _gateway.OpenProjectAsync(root, cancellationToken);
            await ActivateProjectAsync(project, root, cancellationToken);
            StatusMessage = "Managed project opened; canonical sessions were reloaded from SQLite.";
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
        _shellState.SetProjectContext(project.ProjectId);
        OnPropertyChanged(nameof(HasOpenProject));
        OnPropertyChanged(nameof(CurrentProjectText));
        OnPropertyChanged(nameof(CurrentProjectRootText));
        CloseProjectCommand.NotifyCanExecuteChanged();
        await TouchRecentAsync(project, root, cancellationToken);
        await _sessions.LoadAsync(project.ProjectId, cancellationToken: cancellationToken);
        if (_schemes is not null)
        {
            await _schemes.LoadAsync(project.ProjectId, cancellationToken);
        }
    }

    private void ClearCurrentProject()
    {
        CurrentProject = null;
        CurrentProjectRoot = null;
        _shellState.SetProjectContext(null);
        _sessions.Reset();
        _schemes?.Reset();
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
            StatusMessage = "The project operation did not complete.";
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
