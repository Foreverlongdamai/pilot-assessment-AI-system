using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;
using PilotAssessment.Desktop.Core.ViewModels;

namespace PilotAssessment.Desktop.UnitTests.ViewModels;

public sealed class ProjectSessionViewModelTests
{
    private static readonly DateTime Now = new(2026, 7, 17, 12, 0, 0, DateTimeKind.Utc);

    [Fact]
    public async Task PickerCancellationDoesNotCloseOrOpenAProject()
    {
        var gateway = new FakeGateway();
        var picker = new FakePicker([null]);
        var shell = new ApplicationShellState();
        var sessions = new SessionExplorerViewModel(gateway, picker, shell);
        var projects = new ProjectLauncherViewModel(
            gateway,
            picker,
            new FakeRecentStore([]),
            shell,
            sessions);

        await projects.OpenProjectCommand.ExecuteAsync(null);

        Assert.Equal(0, gateway.OpenCalls);
        Assert.Equal(0, gateway.CloseCalls);
        Assert.Null(projects.CurrentProject);
        Assert.Contains("cancelled", projects.StatusMessage, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task InspectProjectsDiagnosticsAndAllSevenInputFamilies()
    {
        var report = CreateReport(withIssue: true);
        var gateway = new FakeGateway { Inspection = report };
        var shell = new ApplicationShellState();
        var sessions = new SessionExplorerViewModel(
            gateway,
            new FakePicker(),
            shell);
        await sessions.LoadAsync("project.alpha");
        sessions.SourceBundlePath = @"C:\external\session-bundle";

        await sessions.InspectSessionCommand.ExecuteAsync(null);

        Assert.Equal(7, sessions.Modalities.Count);
        Assert.Equal(
            StreamReadiness.Unavailable.ToString(),
            sessions.Modalities.Single(item => item.Modality == "I").Readiness);
        Assert.True(sessions.Modalities.Single(item => item.Modality == "EEG").IsAvailable);
        Assert.Contains("Export the missing stream", sessions.InspectionIssues);
        Assert.False(sessions.InspectionReport!.FormalRunAuthorized);
        Assert.True(sessions.CanImport);
    }

    [Fact]
    public async Task ImportReconcilesToCanonicalManagedSessionAndRevision()
    {
        var report = CreateReport();
        var canonical = CreateSessionItem();
        var gateway = new FakeGateway
        {
            Inspection = report,
            ImportedSessions = [canonical],
            StoredReport = CreateStoredReport(report),
            ImportResponse = new SessionImportResponse(
                canonical.Session,
                canonical.Revisions[0],
                "tx.import",
                "audit.import",
                false,
                "trace.import"),
        };
        var shell = new ApplicationShellState();
        var sessions = new SessionExplorerViewModel(gateway, new FakePicker(), shell);
        await sessions.LoadAsync("project.alpha");
        sessions.SourceBundlePath = @"C:\external\session-bundle";
        await sessions.InspectSessionCommand.ExecuteAsync(null);

        await sessions.ImportSessionCommand.ExecuteAsync(null);

        Assert.Equal("session.alpha", sessions.SelectedSession!.Session.SessionId);
        Assert.Equal("session-revision.abc", sessions.SelectedRevision!.SessionRevisionId);
        Assert.Equal("session.alpha", shell.Snapshot.SessionId);
        Assert.Equal("Stored inside this project", sessions.ManagedBundlePathText);
        Assert.DoesNotContain("session.alpha", sessions.InspectionSummary, StringComparison.Ordinal);
        Assert.DoesNotContain("artifact.readiness", sessions.ReadinessArtifactText, StringComparison.Ordinal);
        Assert.Equal(@"C:\external\session-bundle", gateway.LastImportedSource);
        Assert.Contains("canonical managed revision", sessions.StatusMessage);
    }

    [Fact]
    public async Task RawInspectionAllowsImportWhenControlUnitsAreUndeclared()
    {
        var raw = CreateRawInspection();
        var gateway = new FakeGateway
        {
            SourceInspection = new SessionSourceInspectionResponse(
                "0.1.0",
                SessionDataSourceKind.SimulatorRaw,
                null,
                raw,
                "trace.raw"),
        };
        var sessions = new SessionExplorerViewModel(
            gateway,
            new FakePicker(),
            new ApplicationShellState());
        await sessions.LoadAsync("project.alpha");
        sessions.SourceBundlePath = @"C:\external\raw-session";

        await sessions.InspectSessionCommand.ExecuteAsync(null);

        Assert.True(sessions.CanImport);
        Assert.Equal("Simulator raw export", sessions.SourceKindText);
        Assert.Contains("fixed Evidence extraction", sessions.InspectionIssues);
        var controls = sessions.Modalities.Single(item => item.Modality == "U");
        Assert.True(controls.IsAvailable);
        Assert.Contains("raw values", controls.Detail);
        Assert.DoesNotContain(raw.FieldMappings, mapping =>
            mapping.DeclaredUnit is not null && mapping.CanonicalField == "control.yaw_raw");
    }

    [Fact]
    public async Task InitializationReopensMostRecentProjectAndRestoresSessionSummary()
    {
        var report = CreateReport();
        var canonical = CreateSessionItem();
        var project = CreateProject();
        var gateway = new FakeGateway
        {
            Project = project,
            Sessions = [canonical],
            StoredReport = CreateStoredReport(report),
        };
        var recent = new FakeRecentStore(
            [new RecentProjectEntry(@"D:\portable\pilot-project", project.ProjectId, project.Name, Now)]);
        var shell = new ApplicationShellState();
        var picker = new FakePicker();
        var sessions = new SessionExplorerViewModel(gateway, picker, shell);
        var projects = new ProjectLauncherViewModel(gateway, picker, recent, shell, sessions);

        var restored = await projects.InitializeAsync(restoreLastProject: true);

        Assert.True(restored);
        Assert.Equal(1, gateway.OpenCalls);
        Assert.Equal(project.ProjectId, shell.Snapshot.ProjectId);
        Assert.Equal(canonical.Session.SessionId, shell.Snapshot.SessionId);
        Assert.Equal(7, sessions.Modalities.Count);
        Assert.Equal("Ready", sessions.Modalities.Single(item => item.Modality == "G").Readiness);
        Assert.Equal(@"D:\portable\pilot-project", projects.CurrentProjectRoot);
        Assert.Single(recent.LastSaved);
    }

    private static ProjectDescriptor CreateProject() => new(
        "project-descriptor",
        "0.1.0",
        "project.alpha",
        "0.1.0",
        "Alpha project",
        Now);

    private static SessionCollectionItem CreateSessionItem()
    {
        var revision = new SessionRevision(
            "session-revision",
            "0.1.0",
            "session-revision.abc",
            "session.alpha",
            "sessions/session.alpha/session-revision.abc/bundle",
            new string('a', 64),
            new string('b', 64),
            new string('c', 64),
            SessionSourceKind.ManagedImport,
            Now,
            "expert.local",
            "artifact.readiness",
            null);
        var session = new SessionRecord(
            "session-record",
            "0.1.0",
            "session.alpha",
            "project.alpha",
            "pilot.alpha",
            SessionLifecycle.Active,
            revision.SessionRevisionId,
            Now);
        return new SessionCollectionItem(session, [revision]);
    }

    private static StoredIngestionReport CreateStoredReport(IngestionReadinessReport report) => new(
        "session-revision.abc",
        new ManagedArtifact(
            "managed-artifact",
            "0.1.0",
            "artifact.readiness",
            new string('d', 64),
            2048,
            "application/json",
            "ingestion-readiness-report-0.1.0",
            "artifacts/aa/report.json",
            ArtifactLifecycle.Active,
            Now),
        true,
        report);

    private static IngestionReadinessReport CreateReport(bool withIssue = false)
    {
        var issue = new DomainIssue(
            "STREAM_UNAVAILABLE",
            ErrorSeverity.Warning,
            true,
            "Visual scene is not exported.",
            "/streams/I",
            null,
            "Export the missing stream when it becomes available.",
            null,
            null,
            null,
            new Dictionary<string, System.Text.Json.JsonElement>(),
            new Dictionary<string, System.Text.Json.JsonElement>());
        var results = new Dictionary<string, StreamReadinessResult>(StringComparer.Ordinal);
        foreach (var modality in new[] { "X", "U", "I", "G", "EEG", "ECG", "pilot_camera" })
        {
            var unavailable = modality == "I";
            results[modality] = new StreamReadinessResult(
                modality,
                unavailable ? StreamStatus.ExportPending : StreamStatus.Present,
                modality is "X" or "U",
                unavailable ? StreamReadiness.Unavailable : StreamReadiness.Ready,
                unavailable ? null : $"adapter.{modality.ToLowerInvariant()}",
                unavailable ? null : "0.1.0",
                unavailable ? [] : [$"streams/{modality}.csv"],
                unavailable
                    ? new Dictionary<string, string>()
                    : new Dictionary<string, string> { [$"streams/{modality}.csv"] = new string('e', 64) },
                unavailable ? null : $"{modality.ToLowerInvariant()}-aligned-v0.1",
                unavailable ? null : 10,
                new Dictionary<string, long>(),
                unavailable ? null : 0,
                unavailable ? null : 1,
                unavailable ? null : 10,
                unavailable ? [] : ["t_ns", "value"],
                new Dictionary<string, string>(),
                new Dictionary<string, System.Text.Json.JsonElement>(),
                [],
                withIssue && unavailable ? [issue] : []);
        }

        return new IngestionReadinessReport(
            "0.1.0",
            "inspect_only_ingestion_content_v1",
            "session.alpha",
            "0.1.0",
            "captured-session-data",
            null,
            ReadinessDisposition.ReadyPartial,
            true,
            false,
            results,
            null,
            [],
            ["scientific_validation"],
            new string('f', 64));
    }

    private static RawSessionInspection CreateRawInspection()
    {
        var proposals = new Dictionary<string, RawModalityProposal>(StringComparer.Ordinal);
        foreach (var modality in new[] { "X", "U", "I", "G", "EEG", "ECG", "pilot_camera" })
        {
            var present = modality is "X" or "U";
            proposals[modality] = new RawModalityProposal(
                modality,
                present ? StreamStatus.Present : StreamStatus.Missing,
                present ? ["streams/simulator.csv"] : [],
                present ? "csv" : "unavailable",
                present
                    ? "cranfield-simulator-combined-csv-raw-v0.1"
                    : $"{modality.ToLowerInvariant()}-missing-v0.1",
                present ? "simulator-clock" : $"{modality.ToLowerInvariant()}-clock",
                present ? 100.0 : null,
                new Dictionary<string, string>(),
                "undeclared-pass-through-v1");
        }

        return new RawSessionInspection(
            "0.1.0",
            new string('a', 64),
            "cranfield-simulator-combined-csv-raw-v0.1",
            ["cranfield-simulator-combined-csv-raw-v0.1"],
            [new RawSourceFile("streams/simulator.csv", 128, new string('b', 64))],
            [new RawFieldMapping(
                "streams/simulator.csv",
                "Pilot Yaw",
                "control.yaw_raw",
                "U",
                "f64",
                null,
                UnitProvenance.Undeclared,
                "measurement",
                "resolved")],
            proposals,
            [],
            [],
            [],
            true);
    }

    private sealed class FakePicker(params string?[] selections) : IProjectFolderPicker
    {
        private readonly Queue<string?> _selections = new(selections);

        public Task<string?> PickFolderAsync(
            string purpose,
            CancellationToken cancellationToken = default) =>
            Task.FromResult(_selections.Count == 0 ? null : _selections.Dequeue());
    }

    private sealed class FakeRecentStore(IReadOnlyList<RecentProjectEntry> initial)
        : IRecentProjectStore
    {
        private IReadOnlyList<RecentProjectEntry> _stored = initial;

        public IReadOnlyList<RecentProjectEntry> LastSaved { get; private set; } = [];

        public Task<IReadOnlyList<RecentProjectEntry>> LoadAsync(
            CancellationToken cancellationToken = default) => Task.FromResult(_stored);

        public Task SaveAsync(
            IReadOnlyList<RecentProjectEntry> projects,
            CancellationToken cancellationToken = default)
        {
            LastSaved = projects;
            _stored = projects;
            return Task.CompletedTask;
        }
    }

    private sealed class FakeGateway : IProjectSessionGateway
    {
        public ProjectDescriptor Project { get; init; } = CreateProject();
        public IngestionReadinessReport Inspection { get; init; } = CreateReport();
        public SessionSourceInspectionResponse? SourceInspection { get; init; }
        public StoredIngestionReport StoredReport { get; init; } =
            new("session-revision.none", null, false, null);
        public SessionImportResponse? ImportResponse { get; init; }
        public IReadOnlyList<SessionCollectionItem> Sessions { get; init; } = [];
        public IReadOnlyList<SessionCollectionItem> ImportedSessions { get; init; } = [];
        public int OpenCalls { get; private set; }
        public int CloseCalls { get; private set; }
        public string? LastImportedSource { get; private set; }
        private bool _imported;

        public Task<ProjectDescriptor> CreateProjectAsync(
            string root,
            string name,
            string actor,
            CancellationToken cancellationToken = default) => Task.FromResult(Project);

        public Task<ProjectDescriptor> OpenProjectAsync(
            string root,
            CancellationToken cancellationToken = default)
        {
            OpenCalls++;
            return Task.FromResult(Project);
        }

        public Task CloseProjectAsync(CancellationToken cancellationToken = default)
        {
            CloseCalls++;
            return Task.CompletedTask;
        }

        public Task<SessionSourceInspectionResponse> InspectSessionSourceAsync(
            string externalSource,
            CancellationToken cancellationToken = default) => Task.FromResult(
                SourceInspection ?? new SessionSourceInspectionResponse(
                    "0.1.0",
                    SessionDataSourceKind.CanonicalBundle,
                    Inspection,
                    null,
                    "trace.inspect"));

        public Task<SessionImportResponse> ImportSessionSourceAsync(
            string externalSource,
            string inspectedFingerprint,
            string actor,
            CancellationToken cancellationToken = default)
        {
            LastImportedSource = externalSource;
            _imported = true;
            return Task.FromResult(ImportResponse
                ?? throw new InvalidOperationException("No fake import response configured."));
        }

        public Task<IReadOnlyList<SessionCollectionItem>> ListSessionsAsync(
            CancellationToken cancellationToken = default) =>
            Task.FromResult(_imported ? ImportedSessions : Sessions);

        public Task<StoredIngestionReport> GetIngestionReportAsync(
            string sessionRevisionId,
            CancellationToken cancellationToken = default) => Task.FromResult(StoredReport);
    }
}
