using PilotAssessment.Desktop.Core.Contracts;

namespace PilotAssessment.Desktop.Core.ViewModels;

public interface IModelEditSessionGateway
{
    Task<ModelEditSessionStatus> GetEditStatusAsync(
        CancellationToken cancellationToken = default);

    Task<ModelEditSessionMutationResponse> UndoEditAsync(
        string actor,
        CancellationToken cancellationToken = default);

    Task<ModelEditSessionMutationResponse> RedoEditAsync(
        string actor,
        CancellationToken cancellationToken = default);

    Task<ModelEditSessionMutationResponse> CommitEditAsync(
        string actor,
        CancellationToken cancellationToken = default);

    Task<ModelEditSessionMutationResponse> DiscardEditAsync(
        string actor,
        CancellationToken cancellationToken = default);
}
