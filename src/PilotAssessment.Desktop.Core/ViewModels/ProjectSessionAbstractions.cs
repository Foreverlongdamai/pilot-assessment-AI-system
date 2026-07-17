using PilotAssessment.Desktop.Core.Contracts;

namespace PilotAssessment.Desktop.Core.ViewModels;

public sealed record RecentProjectEntry(
    string RootPath,
    string ProjectId,
    string Name,
    DateTime LastOpenedAt);

public sealed record StoredIngestionReport(
    string SessionRevisionId,
    ManagedArtifact? Artifact,
    bool InlineAvailable,
    IngestionReadinessReport? Report);

public interface IProjectSessionGateway
{
    Task<ProjectDescriptor> CreateProjectAsync(
        string root,
        string projectId,
        string name,
        string actor,
        CancellationToken cancellationToken = default);

    Task<ProjectDescriptor> OpenProjectAsync(
        string root,
        CancellationToken cancellationToken = default);

    Task CloseProjectAsync(CancellationToken cancellationToken = default);

    Task<IngestionReadinessReport> InspectSessionAsync(
        string externalBundle,
        CancellationToken cancellationToken = default);

    Task<SessionImportResponse> ImportSessionAsync(
        string externalBundle,
        string actor,
        CancellationToken cancellationToken = default);

    Task<IReadOnlyList<SessionCollectionItem>> ListSessionsAsync(
        CancellationToken cancellationToken = default);

    Task<StoredIngestionReport> GetIngestionReportAsync(
        string sessionRevisionId,
        CancellationToken cancellationToken = default);
}

public interface IProjectFolderPicker
{
    Task<string?> PickFolderAsync(
        string purpose,
        CancellationToken cancellationToken = default);
}

public interface IRecentProjectStore
{
    Task<IReadOnlyList<RecentProjectEntry>> LoadAsync(
        CancellationToken cancellationToken = default);

    Task SaveAsync(
        IReadOnlyList<RecentProjectEntry> projects,
        CancellationToken cancellationToken = default);
}
