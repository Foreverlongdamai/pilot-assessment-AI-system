using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Text;

using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;
using PilotAssessment.Desktop.Core.ViewModels;
using PilotAssessment.Desktop.Services.Backend;

namespace PilotAssessment.Desktop.ViewModels;

public sealed record AuditEventItemViewModel(
    string OccurredAt,
    string EventType,
    string Subject,
    string Actor,
    string TransactionId);

public partial class DiagnosticsViewModel : ObservableObject
{
    private static readonly string[] SchemaIdentities =
    [
        "current-model-run-preflight-report@0.2.0",
        "current-model-run-snapshot@0.2.0",
        "backend-source-identity@0.1.0",
        "assessment-run@0.2.0",
        "run-event@0.1.0",
        "run-result-envelope@0.1.0",
        "evidence-runtime-result@0.1.0",
        "observation-set@0.1.0",
        "posterior-result@0.1.0",
        "inference-trace@0.1.0",
    ];

    private readonly BackendConnectionService _backend;
    private readonly IRunGateway _runs;
    private readonly ILocalizationLookup? _localization;
    private readonly SynchronizationContext? _uiContext;
    private int _initialized;
    private BackendSourceDiskStatus? _lastBackendSource;

    [ObservableProperty]
    public partial bool IsBusy { get; private set; }

    [ObservableProperty]
    public partial bool HasError { get; private set; }

    [ObservableProperty]
    public partial string ErrorMessage { get; private set; } = string.Empty;

    [ObservableProperty]
    public partial string BackendIdentityText { get; private set; } = string.Empty;

    [ObservableProperty]
    public partial string RuntimeStatusText { get; private set; } = string.Empty;

    [ObservableProperty]
    public partial string BackendSourceText { get; private set; } = string.Empty;

    [ObservableProperty]
    public partial bool SourceRestartRequired { get; private set; }

    [ObservableProperty]
    public partial string SourceRestartMessage { get; private set; } = string.Empty;

    [ObservableProperty]
    public partial string RecoveryText { get; private set; } = string.Empty;

    [ObservableProperty]
    public partial string CapabilitiesText { get; private set; } = string.Empty;

    [ObservableProperty]
    public partial string MethodsText { get; private set; } = string.Empty;

    [ObservableProperty]
    public partial string SchemaIdentitiesText { get; private set; } = string.Join(Environment.NewLine, SchemaIdentities);

    public DiagnosticsViewModel(
        ShellViewModel shell,
        BackendConnectionService backend,
        IRunGateway runs,
        ILocalizationLookup? localization = null)
    {
        Shell = shell;
        _backend = backend;
        _runs = runs;
        _localization = localization;
        _uiContext = SynchronizationContext.Current;
        Shell.PropertyChanged += OnShellPropertyChanged;
        _backend.ClientChanged += OnClientChanged;
        _localization?.LanguageChanged += OnLanguageChanged;
        RefreshIdentity();
    }

    public ShellViewModel Shell { get; }

    public ObservableCollection<AuditEventItemViewModel> AuditEvents { get; } = [];

    public bool CanRefresh => !IsBusy && _backend.Client is not null;

    public async Task InitializeAsync(CancellationToken cancellationToken = default)
    {
        if (Interlocked.Exchange(ref _initialized, 1) == 0 && CanRefresh)
        {
            await RefreshAsync(cancellationToken);
        }
    }

    [RelayCommand(CanExecute = nameof(CanRefresh))]
    private async Task RefreshAsync(CancellationToken cancellationToken = default)
    {
        if (IsBusy)
        {
            return;
        }

        IsBusy = true;
        ClearError();
        try
        {
            var runtimeTask = _runs.GetRuntimeStatusAsync(cancellationToken);
            var capabilitiesTask = _runs.GetCapabilitiesAsync(cancellationToken);
            var currentRunsTask = _runs.ListCurrentRunsAsync(cancellationToken);
            var auditTask = _runs.ListAuditEventsAsync(50, cancellationToken);
            await Task.WhenAll(runtimeTask, capabilitiesTask, currentRunsTask, auditTask);

            var runtime = await runtimeTask;
            var capabilities = await capabilitiesTask;
            var currentRuns = await currentRunsTask;
            var audit = await auditTask;
            RuntimeStatusText =
                $"{runtime.State} · project_open={runtime.ProjectOpen} · project_id={runtime.ProjectId ?? "—"}";
            _lastBackendSource = runtime.BackendSource;
            RefreshSourceIdentity();
            var recoverable = currentRuns
                .Where(item => item.Run.State is RunState.Queued or RunState.Running or RunState.Cancelling or RunState.Interrupted)
                .Select(item => $"{item.Run.RunId}: {item.Run.State}/{item.Run.Stage}")
                .ToArray();
            RecoveryText = recoverable.Length == 0
                ? L("Diagnostics_NoRecoverableRuns", "No queued, active or interrupted current-model run requires attention.")
                : string.Join(Environment.NewLine, recoverable);
            CapabilitiesText = string.Join(Environment.NewLine, capabilities.Capabilities.Order(StringComparer.Ordinal));
            var methods = new StringBuilder();
            foreach (var family in capabilities.MethodFamilies.OrderBy(item => item.Key, StringComparer.Ordinal))
            {
                methods.AppendLine($"[{family.Key}]");
                foreach (var method in family.Value.Order(StringComparer.Ordinal))
                {
                    methods.AppendLine(method);
                }
            }
            MethodsText = methods.ToString().TrimEnd();

            AuditEvents.Clear();
            foreach (var item in audit.OrderByDescending(item => item.OccurredAt))
            {
                AuditEvents.Add(new AuditEventItemViewModel(
                    item.OccurredAt.ToLocalTime().ToString("g"),
                    item.EventType,
                    $"{item.SubjectKind}:{item.SubjectId}",
                    item.ActorId,
                    item.TransactionId ?? "—"));
            }
            RefreshIdentity();
        }
        catch (Exception error)
        {
            HasError = true;
            ErrorMessage = error.Message;
        }
        finally
        {
            IsBusy = false;
        }
    }

    partial void OnIsBusyChanged(bool value)
    {
        RefreshCommand.NotifyCanExecuteChanged();
        OnPropertyChanged(nameof(CanRefresh));
    }

    private void RefreshIdentity()
    {
        var handshake = _backend.Handshake;
        BackendIdentityText = handshake is null
            ? L("Diagnostics_NoHandshake", "No active backend handshake.")
            : $"backend {handshake.BackendVersion} · protocol {handshake.ProtocolVersion} · runtime {handshake.RuntimeId} · max frame {handshake.MaxMessageBytes:N0} bytes";
    }

    private void OnShellPropertyChanged(object? sender, PropertyChangedEventArgs args)
    {
        OnPropertyChanged(nameof(Shell));
    }

    private void OnClientChanged(object? sender, BackendClientChangedEventArgs args)
    {
        InvokeOnUi(() =>
        {
            RefreshIdentity();
            RefreshCommand.NotifyCanExecuteChanged();
            OnPropertyChanged(nameof(CanRefresh));
        });
    }

    private void OnLanguageChanged(object? sender, EventArgs args)
    {
        InvokeOnUi(() =>
        {
            RefreshIdentity();
            RefreshSourceIdentity();
        });
    }

    private void RefreshSourceIdentity()
    {
        var source = _lastBackendSource;
        if (source is null)
        {
            SourceRestartRequired = false;
            SourceRestartMessage = string.Empty;
            BackendSourceText = L(
                "Diagnostics_SourceUnavailable",
                "Backend source identity is not available from this runtime.");
            return;
        }

        var loaded = source.LoadedIdentity;
        var baseline = !loaded.BaselineAvailable
            ? L("Diagnostics_BaselineUnavailable", "not available (development runtime)")
            : loaded.LocallyModified is true
                ? L("Diagnostics_BaselineModified", "locally modified")
                : L("Diagnostics_BaselineClean", "matches release baseline");
        SourceRestartRequired = source.RuntimeRestartRequired;
        SourceRestartMessage = source.RuntimeRestartRequired
            ? L(
                "Diagnostics_SourceRestartRequiredMessage",
                "Backend source changed after startup. Save your model edits, close and reopen the application before starting a run.")
            : string.Empty;
        BackendSourceText = string.Join(
            Environment.NewLine,
            $"{L("Diagnostics_SourceRoot", "Active source root")}: {loaded.ActiveSourceRoot}",
            $"{L("Diagnostics_SourceTreeHash", "Source tree SHA-256")}: {loaded.SourceTreeSha256}",
            $"{L("Diagnostics_ExecutionIdentity", "Execution identity")}: {loaded.IdentitySha256}",
            $"{L("Diagnostics_ReleaseBaseline", "Release baseline")}: {baseline}",
            $"Python: {loaded.PythonRuntime.Implementation} {loaded.PythonRuntime.Version} · {loaded.PythonRuntime.ExecutableName}",
            $"{L("Diagnostics_Dependencies", "Installed dependencies")}: {loaded.Dependencies.PackageCount} · {loaded.Dependencies.ManifestSha256}",
            $"{L("Diagnostics_OperatorCatalog", "Operator catalog")}: {loaded.OperatorCatalog.OperatorCount} · {loaded.OperatorCatalog.CatalogSha256}");
    }

    private void ClearError()
    {
        HasError = false;
        ErrorMessage = string.Empty;
    }

    private string L(string key, string fallback)
    {
        if (_localization is null)
        {
            return fallback;
        }

        var value = _localization[key];
        return value.StartsWith("⟦", StringComparison.Ordinal) ? fallback : value;
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
}
