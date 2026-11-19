namespace PilotAssessment.Desktop.Core.SceneAssessment;

public sealed class SceneGraphNode
{
    public string Id { get; init; } = "";
    public string SceneId { get; init; } = "";
    public string? ItemId { get; init; }
    public string? CheckpointId { get; init; }
    public string Kind { get; init; } = "";
    public string Title { get; init; } = "";
    public string Detail { get; init; } = "";
    public string? Grade { get; init; }
    public double? Score { get; init; }
    public bool IsCompensationScore { get; init; }
    public double X { get; init; }
    public double Y { get; init; }
    public double Width { get; init; }
    public double Height { get; init; }
}
