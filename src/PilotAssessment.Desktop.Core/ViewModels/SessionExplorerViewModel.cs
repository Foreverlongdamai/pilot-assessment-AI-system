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
    bool IsAvailable)
{
    public override string ToString() => $"{DisplayName} · {DeclaredStatus} · {Readiness}";
}

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
    public partial SessionSourceInspectionResponse? SourceInspection { get; private set; }

    [ObservableProperty]
    public partial string SourceKindText { get; private set; } = "Not inspected";

    [ObservableProperty]
    public partial string SourceProfileText { get; private set; } = "Not available";

    [ObservableProperty]
    public partial string SourceMappingText { get; private set; } =
        "Choose a session data folder to inspect its input mapping.";

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
        SourceInspection is not null &&
        (SourceInspection.Report is { CanContinueToSynchronization: true } ||
         SourceInspection.Raw is { CanMaterialize: true }) &&
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
        SourceKindText = L("Session_NotInspected", "Not inspected");
        SourceProfileText = L("Session_NotAvailable", "Not available");
        SourceMappingText = L(
            "Session_SourceMappingEmpty",
            "Choose a session data folder to inspect its input mapping.");
        InspectionSummary = L("Session_NotInspected", "Not inspected");
        InspectionIssues = L("Session_NoInspectionReport", "No inspection report loaded.");
        ManagedBundlePathText = L("Session_NoManagedRevision", "No managed revision selected");
        ReadinessArtifactText = L("Session_NotAvailable", "Not available");
        SynchronizationArtifactText = L("Session_NotGenerated", "Not generated");
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
        SourceInspection = null;
        SourceKindText = L("Session_NotInspected", "Not inspected");
        SourceProfileText = L("Session_NotAvailable", "Not available");
        SourceMappingText = L(
            "Session_SourceMappingEmpty",
            "Choose a session data folder to inspect its input mapping.");
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
            L("Session_InspectSource", "Inspect Session Data"));
        if (string.IsNullOrWhiteSpace(selected))
        {
            SetStatus("Session_StatusSelectionCancelled", "Session selection cancelled; nothing changed.");
            return;
        }

        SourceBundlePath = selected;
        if (!string.Equals(_inspectedSourcePath, selected, StringComparison.OrdinalIgnoreCase))
        {
            InspectionReport = null;
            SourceInspection = null;
            _inspectedSourcePath = null;
            SourceKindText = L("Session_NotInspected", "Not inspected");
            SourceProfileText = L("Session_NotAvailable", "Not available");
            SourceMappingText = L(
                "Session_SourceMappingEmpty",
                "Choose a session data folder to inspect its input mapping.");
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
        var inspected = await _gateway.InspectSessionSourceAsync(source);
        _inspectedSourcePath = source;
        ApplySourceInspection(inspected);
        SetStatus(
            "Session_StatusInspectionReadOnly",
            "Inspection is read-only. Import will create a canonical revision in managed project storage.");
    });

    [RelayCommand(CanExecute = nameof(CanImport))]
    private Task ImportSessionAsync() => RunBusyAsync(async () =>
    {
        var projectId = ProjectId
            ?? throw new InvalidOperationException("A managed project must be open before import.");
        var source = SourceBundlePath;
        var inspected = SourceInspection
            ?? throw new InvalidOperationException("Inspect the Session data before import.");
        var fingerprint = inspected.Report?.SourceSnapshotFingerprint
            ?? inspected.Raw?.SourceSnapshotFingerprint
            ?? throw new InvalidOperationException("The Session source inspection has no fingerprint.");
        var imported = await _gateway.ImportSessionSourceAsync(
            source,
            fingerprint,
            "expert.local");
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

        _inspectedSourcePath = null;
        SourceInspection = null;
        SetStatus(
            imported.Replayed ? "Session_StatusImportReplayed" : "Session_StatusImportComplete",
            imported.Replayed
                ? "The existing managed revision was reconciled from the idempotent import receipt."
                : "Import complete. The source remains unchanged; a canonical managed revision is ready.");
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
                ? L("Session_ArtifactAvailable", "Available")
                : F(
                    "Session_ArtifactBytes",
                    "Verified · {0:N0} bytes",
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
            "{0} · formal run authorized: {1}",
            LocalizeReadinessDisposition(report.Disposition),
            report.FormalRunAuthorized
                ? L("Common_Yes", "Yes")
                : L("Common_No", "No"));
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
                    L("Session_StatusUndeclared", "Undeclared"),
                    L("Session_StatusUnknown", "Unknown"),
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
                LocalizeStreamStatus(result.DeclaredStatus),
                LocalizeStreamReadiness(result.Readiness),
                detail,
                result.Readiness is StreamReadiness.Ready));
        }
        NotifyCommandStates();
    }

    private void ApplySourceInspection(SessionSourceInspectionResponse inspected)
    {
        SourceInspection = inspected;
        if (inspected.Report is not null)
        {
            SourceKindText = L("Session_SourceCanonical", "Canonical Session Bundle");
            SourceProfileText = L("Session_ProfileFromManifest", "Declared by manifest");
            SourceMappingText = L(
                "Session_CanonicalMapping",
                "The existing manifest and checksums will be validated and copied unchanged.");
            ApplyReport(inspected.Report);
            return;
        }

        var raw = inspected.Raw
            ?? throw new InvalidOperationException("The raw source inspection payload is missing.");
        InspectionReport = null;
        SourceKindText = L("Session_SourceSimulatorRaw", "Simulator raw export");
        SourceProfileText = raw.DetectedProfileId;
        SourceMappingText = F(
            "Session_RawMappingSummary",
            "{0} source file(s) mapped; a manifest and checksums will be generated during import.",
            raw.Files.Count);
        InspectionSummary = F(
            "Session_RawInspectionSummary",
            "Simulator raw export · {0} · ready to materialize: {1}",
            raw.DetectedProfileId,
            raw.CanMaterialize);
        var warnings = raw.Warnings
            .Select(issue => $"{issue.Severity}: {issue.Message} — {issue.Remediation}")
            .ToArray();
        InspectionIssues = warnings.Length == 0
            ? L(
                "Session_RawNoBlockingIssues",
                "No blocking mapping issues. Missing units remain undeclared and raw values use the fixed Evidence extraction rules.")
            : string.Join(Environment.NewLine, warnings);

        Modalities.Clear();
        foreach (var (id, name, family) in ModalityDefinitions())
        {
            if (!raw.ModalityProposals.TryGetValue(id, out var proposal))
            {
                Modalities.Add(new ModalityStatusItem(
                    id,
                    name,
                    family,
                    L("Session_StatusUndeclared", "Undeclared"),
                    L("Session_StatusUnknown", "Unknown"),
                    L("Session_NoCanonicalStream", "No canonical stream result"),
                    false));
                continue;
            }

            var undeclaredFields = raw.FieldMappings.Count(mapping =>
                string.Equals(mapping.Modality, id, StringComparison.Ordinal) &&
                mapping.DeclaredUnit is null);
            string detail;
            if (proposal.Status is StreamStatus.Present)
            {
                detail = F(
                    "Session_RawFilesMapped",
                    "{0} file(s) mapped",
                    proposal.Paths.Count);
                if (undeclaredFields > 0)
                {
                    detail += " · " + F(
                        "Session_UnitsUndeclaredPassThrough",
                        "{0} field(s) have no declared unit; raw values will be used as-is",
                        undeclaredFields);
                }
                else if (proposal.DeclaredUnits.Count > 0)
                {
                    detail += " · " + F(
                        "Session_UnitsDeclaredCount",
                        "{0} declared unit(s)",
                        proposal.DeclaredUnits.Count);
                }
            }
            else
            {
                detail = L(
                    "Session_ModalityMissingNoSynthesis",
                    "Not present in this export; no data will be synthesized.");
            }
            Modalities.Add(new ModalityStatusItem(
                id,
                name,
                family,
                LocalizeStreamStatus(proposal.Status),
                proposal.Status is StreamStatus.Present
                    ? L("Session_ReadyToImport", "Ready to import")
                    : L("Session_Missing", "Missing"),
                detail,
                proposal.Status is StreamStatus.Present));
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
            : L("Session_ManagedCopyReady", "Stored inside this project");
        ReadinessArtifactText = revision is null
            ? L("Session_NotAvailable", "Not available")
            : L("Session_ArtifactAvailable", "Available");
        SynchronizationArtifactText = revision?.SynchronizationRef is null
            ? L("Session_NotGenerated", "Not generated")
            : L("Session_ArtifactAvailable", "Available");
    }

    private void ShowUnknownModalities(string detailKey, string fallback)
    {
        _unknownModalityDetail = (detailKey, fallback);
        var detail = L(detailKey, fallback);
        Modalities.Clear();
        foreach (var (id, name, family) in ModalityDefinitions())
        {
            Modalities.Add(new ModalityStatusItem(
                id,
                name,
                family,
                L("Session_StatusUnknown", "Unknown"),
                L("Session_ReadinessNotLoaded", "Not loaded"),
                detail,
                false));
        }
    }

    private string LocalizeReadinessDisposition(ReadinessDisposition disposition) => disposition switch
    {
        ReadinessDisposition.Ready => L("Session_ReadinessReady", "Ready"),
        ReadinessDisposition.ReadyPartial => L("Session_ReadinessReadyPartial", "Ready with missing modalities"),
        _ => L("Session_ReadinessBlocked", "Blocked"),
    };

    private string LocalizeStreamStatus(StreamStatus status) => status switch
    {
        StreamStatus.Present => L("Session_StatusPresent", "Present"),
        StreamStatus.ExportPending => L("Session_StatusExportPending", "Export pending"),
        StreamStatus.Missing => L("Session_StatusMissing", "Missing"),
        StreamStatus.Invalid => L("Session_StatusInvalid", "Invalid"),
        _ => L("Session_StatusNotApplicable", "Not applicable"),
    };

    private string LocalizeStreamReadiness(StreamReadiness readiness) => readiness switch
    {
        StreamReadiness.Ready => L("Session_ReadinessReady", "Ready"),
        StreamReadiness.Unavailable => L("Session_ReadinessUnavailable", "Unavailable"),
        StreamReadiness.Invalid => L("Session_StatusInvalid", "Invalid"),
        StreamReadiness.Unsupported => L("Session_ReadinessUnsupported", "Unsupported"),
        _ => L("Session_StatusNotApplicable", "Not applicable"),
    };

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
        if (SourceInspection is not null)
        {
            ApplySourceInspection(SourceInspection);
            return;
        }
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
