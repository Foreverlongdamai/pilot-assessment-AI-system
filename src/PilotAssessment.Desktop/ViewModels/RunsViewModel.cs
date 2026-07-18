using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Text.Json;

using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;
using PilotAssessment.Desktop.Core.ViewModels;

namespace PilotAssessment.Desktop.ViewModels;

public sealed record RunPurposeOption(RunPurpose Purpose, string Label);

public sealed record RunListItemViewModel(
    AssessmentRunV2 Run,
    string? ResultId,
    string Title,
    string StateText,
    string DetailText)
{
    public string RunId => Run.RunId;
    public bool HasResult => !string.IsNullOrWhiteSpace(ResultId);
}

public sealed record FrozenNodeItemViewModel(
    string NodeId,
    string Name,
    string Kind,
    string Revision,
    string ContentHash);

public partial class RunsViewModel : ObservableObject
{
    private const string Actor = "desktop-user";
    private readonly IRunGateway _gateway;
    private readonly SessionExplorerViewModel _sessions;
    private readonly TaskSchemeListViewModel _schemes;
    private readonly ApplicationShellState _shellState;
    private readonly ILocalizationLookup? _localization;
    private readonly RunWorkspaceState _workspace = new();
    private readonly SynchronizationContext? _uiContext;
    private INotifyPropertyChanged? _selectedSchemeSubscription;
    private int _initialized;
    private bool _refreshingPurposeOptions;

    [ObservableProperty]
    public partial RunPurposeOption? SelectedPurpose { get; set; }

    [ObservableProperty]
    public partial RunListItemViewModel? SelectedRun { get; set; }

    [ObservableProperty]
    public partial bool IsBusy { get; private set; }

    [ObservableProperty]
    public partial bool HasError { get; private set; }

    [ObservableProperty]
    public partial string ErrorMessage { get; private set; } = string.Empty;

    [ObservableProperty]
    public partial string StatusMessage { get; private set; } = string.Empty;

    [ObservableProperty]
    public partial string SelectionText { get; private set; } = string.Empty;

    [ObservableProperty]
    public partial string PreflightStatusText { get; private set; } = string.Empty;

    [ObservableProperty]
    public partial string ScientificBannerText { get; private set; } = string.Empty;

    [ObservableProperty]
    public partial string FrozenSnapshotText { get; private set; } = string.Empty;

    [ObservableProperty]
    public partial string ProgressText { get; private set; } = string.Empty;

    [ObservableProperty]
    public partial double ProgressValue { get; private set; }

    [ObservableProperty]
    public partial bool IsProgressIndeterminate { get; private set; }

    public RunsViewModel(
        IRunGateway gateway,
        SessionExplorerViewModel sessions,
        TaskSchemeListViewModel schemes,
        ApplicationShellState shellState,
        ILocalizationLookup? localization = null)
    {
        _gateway = gateway;
        _sessions = sessions;
        _schemes = schemes;
        _shellState = shellState;
        _localization = localization;
        _uiContext = SynchronizationContext.Current;
        _gateway.RunEventReceived += OnRunEventReceived;
        _sessions.PropertyChanged += OnContextPropertyChanged;
        _schemes.PropertyChanged += OnContextPropertyChanged;
        _shellState.Changed += OnShellStateChanged;
        _localization?.LanguageChanged += OnLanguageChanged;
        RebindSelectedScheme();
        RefreshPurposeOptions();
        RefreshPresentation();
    }

    public ObservableCollection<RunPurposeOption> PurposeOptions { get; } = [];

    public ObservableCollection<RunListItemViewModel> Runs { get; } = [];

    public ObservableCollection<RunDiagnostic> PreflightDiagnostics { get; } = [];

    public ObservableCollection<FrozenNodeItemViewModel> FrozenNodes { get; } = [];

    public bool CanRefresh => !IsBusy && _shellState.Snapshot.CanUseDomainCommands;

    public bool CanPreflight =>
        !IsBusy &&
        _shellState.Snapshot.CanUseDomainCommands &&
        _sessions.SelectedRevision is not null &&
        _schemes.SelectedScheme is { IsArchived: false };

    public bool CanStart =>
        !IsBusy &&
        _workspace.CanStart(
            _sessions.SelectedRevision?.SessionRevisionId,
            _schemes.SelectedScheme?.SchemeId,
            _schemes.SelectedScheme?.Scheme.SemanticRevision);

    public bool CanCancel => !IsBusy && _workspace.CanCancel;

    public async Task InitializeAsync(CancellationToken cancellationToken = default)
    {
        if (Interlocked.Exchange(ref _initialized, 1) == 0)
        {
            await RefreshAsync(cancellationToken);
            return;
        }

        RefreshSelectionText();
    }

    [RelayCommand(CanExecute = nameof(CanRefresh))]
    private async Task RefreshAsync(CancellationToken cancellationToken = default)
    {
        await RunBusyAsync(async () =>
        {
            var previousId = SelectedRun?.RunId;
            var currentRuns = await _gateway.ListCurrentRunsAsync(cancellationToken);
            ReplaceRuns(currentRuns);
            SelectedRun = Runs.FirstOrDefault(item => item.RunId == previousId)
                ?? Runs.FirstOrDefault(item => item.Run.State is RunState.Queued or RunState.Running or RunState.Cancelling)
                ?? Runs.FirstOrDefault();
            if (SelectedRun is not null)
            {
                await RestoreSelectedProgressAsync(cancellationToken);
            }

            StatusMessage = L("Runs_StatusRefreshed", "Current-model runs recovered from managed project storage.");
        });
    }

    [RelayCommand(CanExecute = nameof(CanPreflight))]
    private async Task PreflightAsync(CancellationToken cancellationToken = default)
    {
        await RunBusyAsync(async () =>
        {
            var revision = _sessions.SelectedRevision
                ?? throw new InvalidOperationException("Select a managed Session revision.");
            var scheme = _schemes.SelectedScheme?.Scheme
                ?? throw new InvalidOperationException("Select a current task scheme.");
            var purpose = SelectedPurpose?.Purpose ?? RunPurpose.SoftwareTest;
            var report = await _gateway.PreflightAsync(
                revision.SessionRevisionId,
                scheme.SchemeId,
                purpose,
                new Dictionary<string, JsonElement>(StringComparer.Ordinal),
                cancellationToken);
            _workspace.SetPreflight(report);
            ReplacePreflightDiagnostics(report.Diagnostics);
            RefreshPreflightPresentation();
            StatusMessage = report.TechnicalDisposition is TechnicalDisposition.Ready
                ? L("Runs_StatusPreflightReady", "Technical preflight is ready. The current model can run directly.")
                : L("Runs_StatusPreflightBlocked", "Technical preflight is blocked; review the exact diagnostics below.");
        });
    }

    [RelayCommand(CanExecute = nameof(CanStart))]
    private async Task StartAsync(CancellationToken cancellationToken = default)
    {
        await RunBusyAsync(async () =>
        {
            var report = _workspace.Preflight
                ?? throw new InvalidOperationException("Run preflight first.");
            var runId = $"run.desktop.{Guid.NewGuid():N}";
            var transactionId = $"tx.desktop-run-start.{Guid.NewGuid():N}";
            var run = await _gateway.StartAsync(
                report.PreflightId,
                runId,
                report.SchemeSemanticRevision,
                Actor,
                transactionId,
                cancellationToken);
            _workspace.SetRun(run);
            UpsertRun(run, null, select: true);
            RefreshRunPresentation();
            StatusMessage = L("Runs_StatusStarted", "Assessment run started from the frozen current scheme; no Publish step was used.");
        });
    }

    [RelayCommand(CanExecute = nameof(CanCancel))]
    private async Task CancelAsync(CancellationToken cancellationToken = default)
    {
        await RunBusyAsync(async () =>
        {
            var run = _workspace.CurrentRun
                ?? throw new InvalidOperationException("No running assessment is selected.");
            var transactionId = $"tx.desktop-run-cancel.{Guid.NewGuid():N}";
            var canonical = await _gateway.CancelAsync(
                run.RunId,
                Actor,
                transactionId,
                cancellationToken);
            _workspace.SetRun(canonical, _workspace.ResultId);
            UpsertRun(canonical, _workspace.ResultId, select: true);
            RefreshRunPresentation();
            StatusMessage = L("Runs_StatusCancellationRequested", "Cancellation was requested and reconciled with the canonical backend run.");
        });
    }

    partial void OnSelectedPurposeChanged(RunPurposeOption? value)
    {
        if (_refreshingPurposeOptions)
        {
            return;
        }

        _workspace.SetPreflight(null);
        PreflightDiagnostics.Clear();
        RefreshPreflightPresentation();
        NotifyCommandStates();
    }

    partial void OnSelectedRunChanged(RunListItemViewModel? value)
    {
        if (value is not null)
        {
            _workspace.SetRun(value.Run, value.ResultId);
        }

        RefreshRunPresentation();
        NotifyCommandStates();
    }

    partial void OnIsBusyChanged(bool value) => NotifyCommandStates();

    private async Task RestoreSelectedProgressAsync(CancellationToken cancellationToken)
    {
        var run = SelectedRun?.Run;
        if (run is null || run.ProgressSequence == 0)
        {
            return;
        }

        var events = await _gateway.ListEventsAsync(run.RunId, 0, cancellationToken);
        var latest = events.LastOrDefault(item => item.Sequence == run.ProgressSequence);
        if (latest is not null)
        {
            _workspace.RestoreProgress(latest);
            RefreshRunPresentation();
        }
    }

    private void OnRunEventReceived(object? sender, RunEventReceivedEventArgs args)
    {
        InvokeOnUi(() => ApplyRunEvent(args.RunEvent));
    }

    private void ApplyRunEvent(RunEvent runEvent)
    {
        if (!_workspace.TryApply(runEvent) || _workspace.CurrentRun is null)
        {
            return;
        }

        UpsertRun(_workspace.CurrentRun, _workspace.ResultId, select: true);
        RefreshRunPresentation();
        if (runEvent.State is RunState.Completed or RunState.Failed or RunState.Cancelled or RunState.Interrupted)
        {
            StatusMessage = $"{LocalizeState(runEvent.State)} · {runEvent.Message}";
            _ = ReconcileTerminalRunAsync(runEvent.RunId);
        }
    }

    private async Task ReconcileTerminalRunAsync(string runId)
    {
        try
        {
            var status = await _gateway.GetStatusAsync(runId);
            InvokeOnUi(() =>
            {
                _workspace.SetRun(status.Run, status.ResultId);
                UpsertRun(status.Run, status.ResultId, select: true);
                RefreshRunPresentation();
            });
        }
        catch (Exception error)
        {
            InvokeOnUi(() => SetError(error));
        }
    }

    private void ReplaceRuns(IReadOnlyList<CurrentModelRunListItem> items)
    {
        Runs.Clear();
        foreach (var item in items.OrderByDescending(item => item.Run.RequestedAt))
        {
            Runs.Add(BuildRunItem(item.Run, item.ResultId));
        }
    }

    private void UpsertRun(AssessmentRunV2 run, string? resultId, bool select)
    {
        var existing = Runs.FirstOrDefault(item => item.RunId == run.RunId);
        var index = existing is null ? -1 : Runs.IndexOf(existing);
        var replacement = BuildRunItem(run, resultId);
        if (index >= 0)
        {
            Runs[index] = replacement;
        }
        else
        {
            Runs.Insert(0, replacement);
        }

        if (select)
        {
            SelectedRun = replacement;
        }
    }

    private RunListItemViewModel BuildRunItem(AssessmentRunV2 run, string? resultId)
    {
        var schemeName = BilingualTextSelector.Select(
            _localization?.CurrentLanguage ?? "en-US",
            run.Snapshot.Scheme.NameZh,
            run.Snapshot.Scheme.NameEn,
            run.Snapshot.Scheme.SchemeId);
        return new RunListItemViewModel(
            run,
            resultId,
            $"{schemeName} · {run.RunId}",
            $"{LocalizeState(run.State)} · {LocalizeStage(run.Stage)}",
            $"{run.RequestedAt.ToLocalTime():g} · rev {run.Snapshot.Scheme.SemanticRevision} · {run.Snapshot.ActiveNodes.Length} nodes");
    }

    private void ReplacePreflightDiagnostics(IEnumerable<RunDiagnostic> diagnostics)
    {
        PreflightDiagnostics.Clear();
        foreach (var diagnostic in diagnostics)
        {
            PreflightDiagnostics.Add(diagnostic);
        }
    }

    private void RefreshPurposeOptions()
    {
        var selected = SelectedPurpose?.Purpose ?? RunPurpose.SoftwareTest;
        _refreshingPurposeOptions = true;
        try
        {
            PurposeOptions.Clear();
            PurposeOptions.Add(new RunPurposeOption(RunPurpose.Preview, L("Runs_PurposePreview", "Preview")));
            PurposeOptions.Add(new RunPurposeOption(RunPurpose.SoftwareTest, L("Runs_PurposeSoftwareTest", "Software test")));
            PurposeOptions.Add(new RunPurposeOption(RunPurpose.Assessment, L("Runs_PurposeAssessment", "Assessment")));
            SelectedPurpose = PurposeOptions.First(item => item.Purpose == selected);
        }
        finally
        {
            _refreshingPurposeOptions = false;
        }
    }

    private void RefreshPresentation()
    {
        RefreshSelectionText();
        RefreshPreflightPresentation();
        RefreshRunPresentation();
        if (string.IsNullOrWhiteSpace(StatusMessage))
        {
            StatusMessage = L("Runs_StatusStart", "Select a managed Session revision and current task scheme, then run technical preflight.");
        }
    }

    private void RefreshSelectionText()
    {
        var revision = _sessions.SelectedRevision?.SessionRevisionId
            ?? L("Runs_NoSessionRevision", "No managed Session revision selected");
        var scheme = _schemes.SelectedScheme?.DisplayName
            ?? L("Runs_NoScheme", "No current task scheme selected");
        SelectionText = $"{revision}  ·  {scheme}";
    }

    private void RefreshPreflightPresentation()
    {
        var report = _workspace.Preflight;
        PreflightStatusText = report is null
            ? L("Runs_PreflightNotRun", "Preflight not run")
            : $"{LocalizeDisposition(report.TechnicalDisposition)} · {report.PreflightId} · {report.PreflightHash}";
        ScientificBannerText = report switch
        {
            null => L("Runs_ScientificUnknown", "Scientific status will be shown after preflight."),
            { FormalRunAuthorized: true, SyntheticData: false } =>
                L("Runs_ScientificAuthorized", "Formal assessment is authorized by the selected scheme/session metadata."),
            { SyntheticData: true } =>
                L("Runs_ScientificSynthetic", "Engineering / synthetic run: useful for workflow verification, not a validated pilot assessment."),
            _ => L("Runs_ScientificNotAuthorized", "Engineering run: formal assessment is not authorized. Technical execution remains available."),
        };
        NotifyCommandStates();
    }

    private void RefreshRunPresentation()
    {
        FrozenNodes.Clear();
        var run = _workspace.CurrentRun;
        if (run is null)
        {
            FrozenSnapshotText = L("Runs_NoFrozenSnapshot", "No frozen run snapshot selected.");
            ProgressText = L("Runs_Idle", "Idle");
            ProgressValue = 0;
            IsProgressIndeterminate = false;
            _shellState.SetRunStatus("Idle");
            return;
        }

        foreach (var node in run.Snapshot.ActiveNodes)
        {
            var name = BilingualTextSelector.Select(
                _localization?.CurrentLanguage ?? "en-US",
                node.NameZh,
                node.NameEn,
                node.NodeId);
            FrozenNodes.Add(new FrozenNodeItemViewModel(
                node.NodeId,
                name,
                node.NodeKind.ToString(),
                node.SemanticRevision.ToString(),
                node.ContentHash));
        }

        FrozenSnapshotText =
            $"{run.RunId} · snapshot {run.Snapshot.SnapshotHash} · scheme rev {run.Snapshot.Scheme.SemanticRevision} · {run.Snapshot.ActiveNodes.Length} nodes";
        ProgressValue = _workspace.TotalUnits > 0
            ? 100.0 * _workspace.CompletedUnits / _workspace.TotalUnits
            : run.State is RunState.Completed ? 100 : 0;
        IsProgressIndeterminate = _workspace.TotalUnits <= 0 &&
            run.State is RunState.Queued or RunState.Running or RunState.Cancelling;
        ProgressText = string.IsNullOrWhiteSpace(_workspace.ProgressMessage)
            ? $"{LocalizeState(run.State)} · {LocalizeStage(run.Stage)}"
            : $"{LocalizeState(run.State)} · {LocalizeStage(run.Stage)} · {_workspace.ProgressMessage}";
        _shellState.SetRunStatus($"{LocalizeState(run.State)} · {LocalizeStage(run.Stage)}");
        NotifyCommandStates();
    }

    private void OnContextPropertyChanged(object? sender, PropertyChangedEventArgs args)
    {
        if (ReferenceEquals(sender, _schemes) && args.PropertyName == nameof(TaskSchemeListViewModel.SelectedScheme))
        {
            RebindSelectedScheme();
        }

        if (args.PropertyName is nameof(SessionExplorerViewModel.SelectedRevision) or
            nameof(TaskSchemeListViewModel.SelectedScheme))
        {
            InvalidatePreflightForContextChange();
        }
    }

    private void OnSelectedSchemeItemChanged(object? sender, PropertyChangedEventArgs args)
    {
        InvalidatePreflightForContextChange();
    }

    private void RebindSelectedScheme()
    {
        if (_selectedSchemeSubscription is not null)
        {
            _selectedSchemeSubscription.PropertyChanged -= OnSelectedSchemeItemChanged;
        }

        _selectedSchemeSubscription = _schemes.SelectedScheme;
        if (_selectedSchemeSubscription is not null)
        {
            _selectedSchemeSubscription.PropertyChanged += OnSelectedSchemeItemChanged;
        }
    }

    private void InvalidatePreflightForContextChange()
    {
        _workspace.SetPreflight(null);
        PreflightDiagnostics.Clear();
        RefreshSelectionText();
        RefreshPreflightPresentation();
    }

    private void OnShellStateChanged(object? sender, EventArgs args) =>
        InvokeOnUi(NotifyCommandStates);

    private void OnLanguageChanged(object? sender, EventArgs args) => InvokeOnUi(() =>
    {
        var selectedId = SelectedRun?.RunId;
        RefreshPurposeOptions();
        ReplaceRuns(Runs.Select(item => new CurrentModelRunListItem(item.Run, item.ResultId)).ToArray());
        SelectedRun = Runs.FirstOrDefault(item => item.RunId == selectedId);
        RefreshPresentation();
    });

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
        catch (OperationCanceledException)
        {
            StatusMessage = L("Common_Cancelled", "Cancelled");
        }
        catch (Exception error)
        {
            SetError(error);
        }
        finally
        {
            IsBusy = false;
        }
    }

    private void SetError(Exception error)
    {
        HasError = true;
        ErrorMessage = error.Message;
        StatusMessage = error.Message;
    }

    private void ClearError()
    {
        HasError = false;
        ErrorMessage = string.Empty;
    }

    private void NotifyCommandStates()
    {
        RefreshCommand.NotifyCanExecuteChanged();
        PreflightCommand.NotifyCanExecuteChanged();
        StartCommand.NotifyCanExecuteChanged();
        CancelCommand.NotifyCanExecuteChanged();
        OnPropertyChanged(nameof(CanRefresh));
        OnPropertyChanged(nameof(CanPreflight));
        OnPropertyChanged(nameof(CanStart));
        OnPropertyChanged(nameof(CanCancel));
    }

    private void InvokeOnUi(Action action)
    {
        if (_uiContext is null || ReferenceEquals(SynchronizationContext.Current, _uiContext))
        {
            action();
            return;
        }

        _uiContext.Post(static state => ((Action)state!).Invoke(), action);
    }

    private string LocalizeDisposition(TechnicalDisposition disposition) => disposition switch
    {
        TechnicalDisposition.Ready => L("Runs_Ready", "Ready"),
        _ => L("Runs_Blocked", "Blocked"),
    };

    private string LocalizeState(RunState state) => L($"Runs_State_{state}", state.ToString());

    private string LocalizeStage(RunStage stage) => L($"Runs_Stage_{stage}", stage.ToString());

    private string L(string key, string fallback)
    {
        if (_localization is null)
        {
            return fallback;
        }

        var value = _localization[key];
        return value.StartsWith("⟦", StringComparison.Ordinal) ? fallback : value;
    }
}
