using System.Text;

using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

using PilotAssessment.Desktop.Core.State;
using PilotAssessment.Desktop.Services.Backend;
using PilotAssessment.Desktop.Services.Preferences;

namespace PilotAssessment.Desktop.ViewModels;

public partial class ShellViewModel : ObservableObject
{
    private readonly ApplicationShellState _state;
    private readonly BackendConnectionService _backend;
    private readonly LocalPreferencesStore _preferences;
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
    public partial string SelectedLanguage { get; set; } = "en-GB";

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
        LocalPreferencesStore preferences)
    {
        _state = state;
        _backend = backend;
        _preferences = preferences;
        _uiContext = SynchronizationContext.Current;
        _state.Changed += OnShellStateChanged;
        ApplySnapshot(_state.Snapshot);
    }

    public event EventHandler<string>? ThemeChanged;

    public async Task InitializeAsync(CancellationToken cancellationToken = default)
    {
        var preferences = await _preferences.LoadAsync(cancellationToken);
        SelectedLanguage = preferences.Language;
        SelectedTheme = preferences.Theme;
        CurrentDestination = preferences.LastDestination;
        LanguageText = SelectedLanguage.StartsWith("zh", StringComparison.OrdinalIgnoreCase)
            ? "中文"
            : "EN";
        ThemeText = SelectedTheme;
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
            ? "en-GB"
            : "zh-CN";
        LanguageText = SelectedLanguage.StartsWith("zh", StringComparison.OrdinalIgnoreCase)
            ? "中文"
            : "EN";
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
        ThemeText = SelectedTheme;
        ThemeChanged?.Invoke(this, SelectedTheme);
        await SavePreferencesAsync();
    }

    private Task SavePreferencesAsync() =>
        _preferences.SaveAsync(
            new LocalPreferences(SelectedLanguage, SelectedTheme, CurrentDestination));

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

    private void ApplySnapshot(ShellStateSnapshot snapshot)
    {
        ProjectText = snapshot.ProjectId ?? "No project";
        SessionText = snapshot.SessionId ?? "No session";
        SchemeText = snapshot.SchemeId ?? "No task scheme";
        BackendStatusText = snapshot.BackendStatus;
        AutosaveStatusText = snapshot.AutosaveStatus;
        RunStatusText = snapshot.RunStatus;
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
            ? "No backend diagnostics."
            : diagnostics.ToString();
        ReconnectCommand.NotifyCanExecuteChanged();
    }

    private sealed record SnapshotUpdate(
        ShellViewModel ViewModel,
        ShellStateSnapshot Snapshot);
}
