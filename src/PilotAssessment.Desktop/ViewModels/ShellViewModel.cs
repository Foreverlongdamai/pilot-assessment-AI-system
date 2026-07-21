using System.Text;

using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

using PilotAssessment.Desktop.Core.State;
using PilotAssessment.Desktop.Services.Backend;
using PilotAssessment.Desktop.Services.Localization;
using PilotAssessment.Desktop.Services.Preferences;

namespace PilotAssessment.Desktop.ViewModels;

public partial class ShellViewModel : ObservableObject
{
    private readonly ApplicationShellState _state;
    private readonly BackendConnectionService _backend;
    private readonly LocalPreferencesStore _preferences;
    private readonly LocalizationService _localization;
    private readonly SynchronizationContext? _uiContext;

    [ObservableProperty]
    public partial string ProjectText { get; set; } = "No project";

    [ObservableProperty]
    public partial string SessionText { get; set; } = "No session";

    [ObservableProperty]
    public partial string SchemeText { get; set; } = "No task scheme";

    [ObservableProperty]
    public partial string BackendStatusText { get; set; } = "Stopped";

    [ObservableProperty]
    public partial string AutosaveStatusText { get; set; } = "No pending changes";

    [ObservableProperty]
    public partial string RunStatusText { get; set; } = "Idle";

    [ObservableProperty]
    public partial string LanguageText { get; set; } = "EN";

    [ObservableProperty]
    public partial string ThemeText { get; set; } = "System";

    [ObservableProperty]
    public partial string SelectedLanguage { get; set; } = "en-US";

    [ObservableProperty]
    public partial string SelectedTheme { get; set; } = "System";

    [ObservableProperty]
    public partial string CurrentDestination { get; set; } = "project";

    [ObservableProperty]
    public partial string? StartupError { get; set; }

    [ObservableProperty]
    public partial string? BackendDetails { get; set; }

    [ObservableProperty]
    public partial string DiagnosticText { get; set; } = "No backend diagnostics.";

    [ObservableProperty]
    public partial bool IsBackendReady { get; set; }

    [ObservableProperty]
    public partial bool CanUseDomainCommands { get; set; }

    [ObservableProperty]
    public partial bool HasStartupError { get; set; }

    public ShellViewModel(
        ApplicationShellState state,
        BackendConnectionService backend,
        LocalPreferencesStore preferences,
        LocalizationService localization)
    {
        _state = state;
        _backend = backend;
        _preferences = preferences;
        _localization = localization;
        _uiContext = SynchronizationContext.Current;
        _state.Changed += OnShellStateChanged;
        _localization.LanguageChanged += OnLocalizationChanged;
        ApplySnapshot(_state.Snapshot);
    }

    public event EventHandler<string>? ThemeChanged;

    public async Task InitializeAsync(CancellationToken cancellationToken = default)
    {
        var preferences = await _preferences.LoadAsync(cancellationToken);
        _localization.ChangeLanguage(preferences.Language);
        SelectedLanguage = _localization.CurrentLanguage;
        SelectedTheme = preferences.Theme;
        CurrentDestination = preferences.LastDestination;
        UpdatePresentationLabels();
        ThemeChanged?.Invoke(this, SelectedTheme);
    }

    public void SelectDestination(string destination)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(destination);
        CurrentDestination = destination;
        _ = SavePreferencesAsync();
    }

    [RelayCommand(CanExecute = nameof(CanReconnect))]
    private async Task ReconnectAsync()
    {
        _ = await _backend.ReconnectAsync();
    }

    private bool CanReconnect() =>
        _state.Snapshot.BackendState is not BackendConnectionState.Connecting;

    [RelayCommand]
    private async Task CycleLanguageAsync()
    {
        SelectedLanguage = SelectedLanguage.StartsWith("zh", StringComparison.OrdinalIgnoreCase)
            ? "en-US"
            : "zh-CN";
        _localization.ChangeLanguage(SelectedLanguage);
        UpdatePresentationLabels();
        await SavePreferencesAsync();
    }

    [RelayCommand]
    private async Task CycleThemeAsync()
    {
        SelectedTheme = SelectedTheme switch
        {
            "System" => "Light",
            "Light" => "Dark",
            _ => "System",
        };
        UpdatePresentationLabels();
        ThemeChanged?.Invoke(this, SelectedTheme);
        await SavePreferencesAsync();
    }

    private Task SavePreferencesAsync() =>
        _preferences.UpdateAsync(current => current with
        {
            Language = SelectedLanguage,
            Theme = SelectedTheme,
            LastDestination = CurrentDestination,
        });

    private void OnShellStateChanged(object? sender, EventArgs args)
    {
        var snapshot = _state.Snapshot;
        if (_uiContext is null || ReferenceEquals(SynchronizationContext.Current, _uiContext))
        {
            ApplySnapshot(snapshot);
            return;
        }

        _uiContext.Post(static state =>
        {
            var update = (SnapshotUpdate)state!;
            update.ViewModel.ApplySnapshot(update.Snapshot);
        }, new SnapshotUpdate(this, snapshot));
    }

    private void OnLocalizationChanged(object? sender, EventArgs args)
    {
        SelectedLanguage = _localization.CurrentLanguage;
        UpdatePresentationLabels();
        ApplySnapshot(_state.Snapshot);
    }

    private void UpdatePresentationLabels()
    {
        LanguageText = SelectedLanguage.StartsWith("zh", StringComparison.OrdinalIgnoreCase)
            ? "中文"
            : "EN";
        ThemeText = SelectedTheme switch
        {
            "Light" => _localization["Theme_Light"],
            "Dark" => _localization["Theme_Dark"],
            _ => _localization["Theme_System"],
        };
    }

    private void ApplySnapshot(ShellStateSnapshot snapshot)
    {
        ProjectText = ResolveVisibleName(
            snapshot.ProjectId,
            snapshot.ProjectDisplayName,
            "Shell_NoProject",
            "Shell_SelectedProject");
        SessionText = ResolveVisibleName(
            snapshot.SessionId,
            snapshot.SessionDisplayName,
            "Shell_NoSession",
            "Shell_SelectedSession");
        SchemeText = ResolveVisibleName(
            snapshot.SchemeId,
            snapshot.SchemeDisplayName,
            "Shell_NoTaskScheme",
            "Shell_SelectedTaskScheme");
        BackendStatusText = snapshot.BackendState switch
        {
            BackendConnectionState.Connecting => _localization["Shell_Connecting"],
            BackendConnectionState.Ready => _localization["Shell_Ready"],
            BackendConnectionState.Faulted => _localization["Shell_Unavailable"],
            _ => _localization["Shell_Stopped"],
        };
        AutosaveStatusText = LocalizeAutosave(snapshot.AutosaveStatus);
        RunStatusText = string.Equals(snapshot.RunStatus, "Idle", StringComparison.OrdinalIgnoreCase)
            ? _localization["Shell_Idle"]
            : snapshot.RunStatus;
        StartupError = snapshot.BackendError;
        BackendDetails = snapshot.BackendDetails;
        IsBackendReady = snapshot.IsBackendReady;
        CanUseDomainCommands = snapshot.CanUseDomainCommands;
        HasStartupError = !string.IsNullOrWhiteSpace(snapshot.BackendError);

        var diagnostics = new StringBuilder();
        foreach (var line in snapshot.Diagnostics)
        {
            diagnostics.AppendLine(line);
        }

        DiagnosticText = diagnostics.Length == 0
            ? _localization["Shell_NoBackendDiagnostics"]
            : diagnostics.ToString();
        ReconnectCommand.NotifyCanExecuteChanged();
    }

    private string LocalizeAutosave(string status) => status switch
    {
        "Pending changes" => _localization["Shell_PendingChanges"],
        "Saving" => _localization["Shell_Saving"],
        "Saved" => _localization["Shell_Saved"],
        "Offline / Retry" => _localization["Shell_OfflineRetry"],
        "Conflict" => _localization["Shell_Conflict"],
        "Blocked" => _localization["Shell_Blocked"],
        _ => _localization["Shell_NoPendingChanges"],
    };

    private string ResolveVisibleName(
        string? technicalId,
        string? displayName,
        string missingKey,
        string selectedKey) =>
        string.IsNullOrWhiteSpace(technicalId)
            ? _localization[missingKey]
            : string.IsNullOrWhiteSpace(displayName)
                ? _localization[selectedKey]
                : displayName;

    private sealed record SnapshotUpdate(
        ShellViewModel ViewModel,
        ShellStateSnapshot Snapshot);
}
