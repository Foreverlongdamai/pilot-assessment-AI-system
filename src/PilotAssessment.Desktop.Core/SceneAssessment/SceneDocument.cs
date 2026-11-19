namespace PilotAssessment.Desktop.Core.SceneAssessment;

/// <summary>Retains one scene's workspace and file state while navigating between scenes.</summary>
public sealed class SceneDocument
{
    internal SceneDocument(SceneCatalog catalog) => Workspace = new SceneWorkspace(catalog);

    public SceneWorkspace Workspace { get; }
    public string? ConfigurationPath { get; set; }
    public string? InputPath { get; set; }
    public bool IsDirty { get; set; }
}
