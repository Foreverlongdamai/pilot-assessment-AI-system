using System.Collections.ObjectModel;

using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;

namespace PilotAssessment.Desktop.Core.ViewModels;

public sealed record ModalityStatusItem(
    string Modality,
    string DisplayName,
    string Family,
    string DeclaredStatus,
    string Readiness,
    string Detail,
    bool IsAvailable);

public partial class SessionExplorerViewModel : ObservableObject
{
    private readonly IProjectSessionGateway _gateway;
    private readonly IProjectFolderPicker _folderPicker;
    private readonly ApplicationShellState _shellState;
    private readonly ILocalizationLookup? _localization;
    private string? _inspectedSourcePath;
    private long _selectionSequence;
    private string _statusKey = "Session_StatusStart";
    private object?[] _statusArguments = [];
    private (string Key, string Fallback)? _unknownModalityDetail;

    [ObservableProperty]
    public partial string? ProjectId { get; private set; }

    [ObservableProperty]
    public partial string SourceBundlePath { get; set; } = string.Empty;

    [ObservableProperty]
    public partial SessionCollectionItem? SelectedSession { get; private set; }

    [ObservableProperty]
    public partial SessionRevision? SelectedRevision { get; private set; }

    [ObservableProperty]
    public partial IngestionReadinessReport? InspectionReport { get; private set; }

    [ObservableProperty]
    public partial bool IsBusy { get; private set; }

    [ObservableProperty]
    public partial bool HasError { get; private set; }

    [ObservableProperty]
    public partial string ErrorMessage { get; private set; } = string.Empty;

    [ObservableProperty]
    public partial string StatusMessage { get; private set; } =
        "Open a managed project to inspect and import a Session Bundle.";

    [ObservableProperty]
    public partial string InspectionSummary { get; private set; } = "Not inspected";

    [ObservableProperty]
    public partial string InspectionIssues { get; private set; } = "No inspection report loaded.";

    [ObservableProperty]
    public partial string ManagedBundlePathText { get; private set; } = "No managed revision selected";

    [ObservableProperty]
    public partial string ReadinessArtifactText { get; private set; } = "Not available";

    [ObservableProperty]
    public partial string SynchronizationArtifactText { get; private set; } = "Not generated";

    public ObservableCollection<SessionCollectionItem> Sessions { get; } = [];

    public ObservableCollection<SessionRevision> Revisions { get; } = [];

    public ObservableCollection<ModalityStatusItem> Modalities { get; } = [];

    public bool HasProject => !string.IsNullOrWhiteSpace(ProjectId);

    public bool CanInspect => HasProject && !IsBusy && !string.IsNullOrWhiteSpace(SourceBundlePath);

    public bool CanImport =>
        CanInspect &&
        InspectionReport is { CanContinueToSynchronization: true } &&
        string.Equals(_inspectedSourcePath, SourceBundlePath, StringComparison.OrdinalIgnoreCase);

    public SessionExplorerViewModel(
        IProjectSessionGateway gateway,
        IProjectFolderPicker folderPicker,
        ApplicationShellState shellState,
        ILocalizationLookup? localization = null)
    {
        _gateway = gateway;
        _folderPicker = folderPicker;
        _shellState = shellState;
        _localization = localization;
        _localization?.LanguageChanged += OnLanguageChanged;
        SetStatus("Session_StatusStart", "Open a managed project to inspect and import a Session Bundle.");
        ShowUnknownModalities("Session_NoReportLoaded", "No report loaded");
    }

    public async Task LoadAsync(
        string projectId,
        string? preferredSessionId = null,
        string? preferredRevisionId = null,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(projectId);
        await RunBusyAsync(() => LoadCoreAsync(
            projectId,
            preferredSessionId,
            preferredRevisionId,
            cancellationToken));
    }

    public void Reset()
    {
        Interlocked.Increment(ref _selectionSequence);
        ProjectId = null;
        Sessions.Clear();
        Revisions.Clear();
        SourceBundlePath = string.Empty;
        _inspectedSourcePath = null;
        InspectionReport = null;
        ClearSelection();
        ClearError();
        InspectionSummary = L("Session_NotInspected", "Not inspected");
        InspectionIssues = L("Session_NoInspectionReport", "No inspection report loaded.");
        SetStatus("Session_StatusStart", "Open a managed project to inspect and import a Session Bundle.");
        ShowUnknownModalities("Session_NoReportLoaded", "No report loaded");
        OnPropertyChanged(nameof(HasProject));
        NotifyCommandStates();
    }

    public Task SelectSessionAsync(
        SessionCollectionItem? session,
        CancellationToken cancellationToken = default)
    {
        if (session is null)
        {
            ClearSelection();
            return Task.CompletedTask;
        }

        var revision = session.Revisions.FirstOrDefault(item =>
                string.Equals(
                    item.SessionRevisionId,
                    session.Session.CurrentSessionRevisionId,
                    StringComparison.Ordinal))
            ?? session.Revisions.FirstOrDefault();
        return SelectCoreAsync(session, revision, cancellationToken);
    }

    public Task SelectRevisionAsync(
        SessionRevision? revision,
        CancellationToken cancellationToken = default)
    {
        if (SelectedSession is null || revision is null)
        {
            return Task.CompletedTask;
        }

        return SelectCoreAsync(SelectedSession, revision, cancellationToken);
    }

    [RelayCommand]
    private async Task ChooseSessionBundleAsync()
    {
        var selected = await _folderPicker.PickFolderAsync(
            L("Session_InspectBundle", "Inspect Session Bundle"));
        if (string.IsNullOrWhiteSpace(selected))
        {
            SetStatus("Session_StatusSelectionCancelled", "Session selection cancelled; nothing changed.");
            return;
        }

        SourceBundlePath = selected;
        if (!string.Equals(_inspectedSourcePath, selected, StringComparison.OrdinalIgnoreCase))
        {
            InspectionReport = null;
            _inspectedSourcePath = null;
            InspectionSummary = L("Session_NotInspected", "Not inspected");
            InspectionIssues = L("Session_InspectBeforeImport", "Inspect this source before importing it.");
            ShowUnknownModalities("Session_SourceNotInspected", "Source not inspected");
        }
        NotifyCommandStates();
    }

    [RelayCommand(CanExecute = nameof(CanInspect))]
    private Task InspectSessionAsync() => RunBusyAsync(async () =>
    {
        var source = SourceBundlePath;
        var report = await _gateway.InspectSessionAsync(source);
        _inspectedSourcePath = source;
        ApplyReport(report);
        SetStatus(
            "Session_StatusInspectionReadOnly",
            "Inspection is read-only. Import will copy this exact bundle into managed project storage.");
    });

    [RelayCommand(CanExecute = nameof(CanImport))]
    private Task ImportSessionAsync() => RunBusyAsync(async () =>
    {
        var projectId = ProjectId
            ?? throw new InvalidOperationException("A managed project must be open before import.");
        var source = SourceBundlePath;
        var inspected = InspectionReport
            ?? throw new InvalidOperationException("Inspect the Session Bundle before import.");
        var imported = await _gateway.ImportSessionAsync(source, "expert.local");
        await LoadCoreAsync(
            projectId,
            imported.Session.SessionId,
            imported.Revision.SessionRevisionId,
            CancellationToken.None);
        if (SelectedSession?.Session.SessionId != imported.Session.SessionId ||
            SelectedRevision?.SessionRevisionId != imported.Revision.SessionRevisionId)
        {
            throw new InvalidOperationException(
                "The imported canonical session revision was not present after reconciliation.");
        }

        _inspectedSourcePath = source;
        ApplyReport(inspected);
        SetStatus(
            imported.Replayed ? "Session_StatusImportReplayed" : "Session_StatusImportComplete",
            imported.Replayed
                ? "The existing managed revision was reconciled from the idempotent import receipt."
                : "Import complete. The source remains external; the managed revision is an exact project copy.");
    });

    [RelayCommand(CanExecute = nameof(HasProject))]
    private Task RefreshSessionsAsync() => ProjectId is null
        ? Task.CompletedTask
        : LoadAsync(ProjectId);

    partial void OnSourceBundlePathChanged(string value) => NotifyCommandStates();

    partial void OnIsBusyChanged(bool value) => NotifyCommandStates();

    private async Task SelectCoreAsync(
        SessionCollectionItem session,
        SessionRevision? revision,
        CancellationToken cancellationToken)
    {
        SelectedSession = session;
        Revisions.Clear();
        foreach (var item in session.Revisions)
        {
            Revisions.Add(item);
        }
        SelectedRevision = revision;
        UpdateRevisionText(revision);
        _shellState.SetProjectContext(ProjectId, session.Session.SessionId);
        if (revision is null)
        {
            ShowUnknownModalities("Session_NoManagedRevision", "No managed revision selected");
            return;
        }

        var sequence = Interlocked.Increment(ref _selectionSequence);
        try
        {
            var stored = await _gateway.GetIngestionReportAsync(
                revision.SessionRevisionId,
                cancellationToken);
            if (sequence != Volatile.Read(ref _selectionSequence))
            {
                return;
            }

            ReadinessArtifactText = stored.Artifact is null
                ? revision.IngestionReadinessRef
                : F(
                    "Session_ArtifactBytes",
                    "{0} · {1:N0} bytes",
                    stored.Artifact.ArtifactId,
                    stored.Artifact.ByteSize);
            if (stored.Report is not null)
            {
                ApplyReport(stored.Report);
            }
            else
            {
                InspectionSummary = stored.InlineAvailable
                    ? L("Session_StoredReportUnavailable", "Stored report unavailable")
                    : L("Session_StoredReportReferenceOnly", "Stored report is reference-only");
                InspectionIssues = L(
                    "Session_ReferencePreserved",
                    "The canonical artifact reference is preserved; no large payload was loaded.");
                ShowUnknownModalities("Session_ReportNotInline", "Report not loaded inline");
            }
        }
        catch (Exception error)
        {
            if (sequence == Volatile.Read(ref _selectionSequence))
            {
                SetError(error);
                ShowUnknownModalities(
                    "Session_StoredReportLoadFailed",
                    "Stored report could not be loaded");
            }
        }
    }

    private void ApplyReport(IngestionReadinessReport report)
    {
        InspectionReport = report;
        _unknownModalityDetail = null;
        InspectionSummary = F(
            "Session_ReportSummary",
            "{0} · session {1} · formal run authorized: {2}",
            report.Disposition,
            report.SessionId,
            report.FormalRunAuthorized);
        var issues = report.GlobalIssues
            .Concat(report.StreamResults.Values.SelectMany(result => result.Issues))
            .Select(issue => $"{issue.Severity}: {issue.Message} — {issue.Remediation}")
            .ToArray();
        InspectionIssues = issues.Length == 0
            ? L("Session_NoIngestionIssues", "No ingestion issues reported.")
            : string.Join(Environment.NewLine, issues);

        Modalities.Clear();
        foreach (var (id, name, family) in ModalityDefinitions())
        {
            if (!report.StreamResults.TryGetValue(id, out var result))
            {
                Modalities.Add(new ModalityStatusItem(
                    id,
                    name,
                    family,
                    "undeclared",
                    "unknown",
                    L("Session_NoCanonicalStream", "No canonical stream result"),
                    false));
                continue;
            }

            var detail = result.Readiness is StreamReadiness.Ready
                ? F(
                    "Session_Rows",
                    "{0:N0} rows",
                    result.RowCount.GetValueOrDefault()) +
                    (result.ObservedSampleRateHz is double rate ? $" · {rate:G6} Hz" : string.Empty)
                : result.Issues.FirstOrDefault()?.Message ??
                  L("Session_NoExportedContent", "No exported content inspected");
            Modalities.Add(new ModalityStatusItem(
                id,
                name,
                family,
                result.DeclaredStatus.ToString(),
                result.Readiness.ToString(),
                detail,
                result.Readiness is StreamReadiness.Ready));
        }
        NotifyCommandStates();
    }

    private void ClearSelection()
    {
        SelectedSession = null;
        SelectedRevision = null;
        Revisions.Clear();
        ManagedBundlePathText = L("Session_NoManagedRevision", "No managed revision selected");
        ReadinessArtifactText = L("Session_NotAvailable", "Not available");
        SynchronizationArtifactText = L("Session_NotGenerated", "Not generated");
        if (ProjectId is not null)
        {
            _shellState.SetProjectContext(ProjectId);
        }
    }

    private void UpdateRevisionText(SessionRevision? revision)
    {
        ManagedBundlePathText = revision is null
            ? L("Session_NoManagedRevision", "No managed revision selected")
            : revision.ManagedBundlePath;
        ReadinessArtifactText = revision?.IngestionReadinessRef ??
            L("Session_NotAvailable", "Not available");
        SynchronizationArtifactText = revision?.SynchronizationRef ??
            L("Session_NotGenerated", "Not generated");
    }

    private void ShowUnknownModalities(string detailKey, string fallback)
    {
        _unknownModalityDetail = (detailKey, fallback);
        var detail = L(detailKey, fallback);
        Modalities.Clear();
        foreach (var (id, name, family) in ModalityDefinitions())
        {
            Modalities.Add(new ModalityStatusItem(
                id, name, family, "unknown", "not loaded", detail, false));
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
            SetError(error);
        }
        finally
        {
            IsBusy = false;
        }
    }

    private async Task LoadCoreAsync(
        string projectId,
        string? preferredSessionId,
        string? preferredRevisionId,
        CancellationToken cancellationToken)
    {
        ProjectId = projectId;
        OnPropertyChanged(nameof(HasProject));
        NotifyCommandStates();
        var sessions = await _gateway.ListSessionsAsync(cancellationToken);
        Sessions.Clear();
        foreach (var session in sessions)
        {
            Sessions.Add(session);
        }

        var desiredSessionId = preferredSessionId ?? _shellState.Snapshot.SessionId;
        var selected = Sessions.FirstOrDefault(item =>
                string.Equals(item.Session.SessionId, desiredSessionId, StringComparison.Ordinal))
            ?? Sessions.FirstOrDefault();
        if (selected is null)
        {
            ClearSelection();
            SetStatus("Session_StatusNoManaged", "This project has no managed sessions yet.");
            return;
        }

        var revisionId = preferredRevisionId ?? selected.Session.CurrentSessionRevisionId;
        var revision = selected.Revisions.FirstOrDefault(item =>
                string.Equals(item.SessionRevisionId, revisionId, StringComparison.Ordinal))
            ?? selected.Revisions.FirstOrDefault();
        await SelectCoreAsync(selected, revision, cancellationToken);
        SetStatus("Session_StatusLoaded", "Loaded {0} managed session(s).", Sessions.Count);
    }

    private void SetError(Exception error)
    {
        HasError = true;
        ErrorMessage = error.Message;
        SetStatus("Session_StatusFailed", "The project/session operation did not complete.");
    }

    private void ClearError()
    {
        HasError = false;
        ErrorMessage = string.Empty;
    }

    private void OnLanguageChanged(object? sender, EventArgs args)
    {
        StatusMessage = _localization?.Format(_statusKey, _statusArguments) ?? StatusMessage;
        UpdateRevisionText(SelectedRevision);
        if (InspectionReport is not null)
        {
            ApplyReport(InspectionReport);
            return;
        }

        InspectionSummary = L("Session_NotInspected", "Not inspected");
        InspectionIssues = string.IsNullOrWhiteSpace(SourceBundlePath)
            ? L("Session_NoInspectionReport", "No inspection report loaded.")
            : L("Session_InspectBeforeImport", "Inspect this source before importing it.");
        if (_unknownModalityDetail is { } unknown)
        {
            ShowUnknownModalities(unknown.Key, unknown.Fallback);
        }
    }

    private (string Id, string Name, string Family)[] ModalityDefinitions() =>
    [
        ("X", L("Modality_X_Name", "Flight state"), L("Modality_X_Family", "Simulator state X(t)")),
        ("U", L("Modality_U_Name", "Control input"), L("Modality_U_Family", "Pilot control U(t)")),
        ("I", L("Modality_I_Name", "VR visual scene"), L("Modality_I_Family", "Pilot field of view I(t)")),
        ("G", L("Modality_G_Name", "Gaze and AOI"), L("Modality_G_Family", "Eye tracking G(t)")),
        ("pilot_camera", L("Modality_Camera_Name", "Pilot camera"), L("Modality_Camera_Family", "Pilot image frames")),
        ("EEG", "EEG", L("Modality_Physiology", "Physiology P(t)")),
        ("ECG", "ECG", L("Modality_Physiology", "Physiology P(t)")),
    ];

    private void SetStatus(string key, string fallback, params object?[] arguments)
    {
        _statusKey = key;
        _statusArguments = arguments;
        StatusMessage = F(key, fallback, arguments);
    }

    private string L(string key, string fallback) => _localization?[key] ?? fallback;

    private string F(string key, string fallback, params object?[] arguments) =>
        _localization?.Format(key, arguments) ?? string.Format(fallback, arguments);

    private void NotifyCommandStates()
    {
        InspectSessionCommand.NotifyCanExecuteChanged();
        ImportSessionCommand.NotifyCanExecuteChanged();
        RefreshSessionsCommand.NotifyCanExecuteChanged();
    }
}
