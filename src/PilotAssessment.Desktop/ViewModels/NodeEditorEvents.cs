using PilotAssessment.Desktop.Core.Contracts;

namespace PilotAssessment.Desktop.ViewModels;

public enum NodeEditorEditPersistence
{
    Autosave,
    ExplicitCommit,
}

public sealed class NodeEditorLocalEditEventArgs(
    NodeEditorEditPersistence persistence) : EventArgs
{
    public NodeEditorEditPersistence Persistence { get; } = persistence;
}

public sealed class CanonicalNodeCommittedEventArgs(ModelNode node) : EventArgs
{
    public ModelNode Node { get; } = node;
}
