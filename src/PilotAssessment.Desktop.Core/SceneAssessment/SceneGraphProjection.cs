namespace PilotAssessment.Desktop.Core.SceneAssessment;

/// <summary>Projects scene hierarchy and current evidence without introducing task-level inference.</summary>
public sealed class SceneGraphProjection
{
    private const double NodeHeight = 76;
    private const double RowStride = 92;
    private const double SceneGap = 100;

    private SceneGraphProjection(List<SceneGraphNode> nodes, List<SceneGraphEdge> edges)
    {
        Nodes = nodes.AsReadOnly();
        Edges = edges.AsReadOnly();
        Height = nodes.Count == 0 ? 160 : nodes.Max(node => node.Y + node.Height) + 40;
    }

    public IReadOnlyList<SceneGraphNode> Nodes { get; }
    public IReadOnlyList<SceneGraphEdge> Edges { get; }
    public double Width => 1130;
    public double Height { get; }

    public static SceneGraphProjection Build(IEnumerable<SceneWorkspace> workspaces)
    {
        ArgumentNullException.ThrowIfNull(workspaces);
        var nodes = new List<SceneGraphNode>();
        var edges = new List<SceneGraphEdge>();
        var sceneIds = new HashSet<string>(StringComparer.Ordinal);
        var sceneTop = 100d;

        foreach (var workspace in workspaces)
        {
            ArgumentNullException.ThrowIfNull(workspace);
            var catalog = workspace.Catalog;
            if (!sceneIds.Add(catalog.SceneId))
            {
                throw new ArgumentException($"画布中不能重复加入场景 {catalog.SceneId}。", nameof(workspaces));
            }

            var report = workspace.Report;
            var taskId = $"scene/{Uri.EscapeDataString(catalog.SceneId)}/task";
            var row = 0;
            var itemNodes = new List<SceneGraphNode>();
            foreach (var item in catalog.Items)
            {
                var itemId = $"{taskId}/item/{Uri.EscapeDataString(item.ItemId)}";
                var itemReport = report?.Items.FirstOrDefault(result => result.ItemId == item.ItemId);
                var rowCount = Math.Max(1, item.Checkpoints.Count);
                var itemNode = new SceneGraphNode
                {
                    Id = itemId, SceneId = catalog.SceneId, ItemId = item.ItemId, Kind = "item",
                    Title = item.Name, Detail = string.IsNullOrWhiteSpace(item.SkillName) ? item.Description : item.SkillName,
                    Grade = itemReport?.Grade,
                    Score = item.AssessmentKind != "checklist" && itemReport?.SkillQuantification is
                        { Status: "complete", Method: SceneSkillModel.CompensationInferenceMethod }
                        ? itemReport.SkillQuantification.Score : null,
                    IsCompensationScore = itemReport?.SkillQuantification is
                        { Status: "complete", Method: SceneSkillModel.CompensationInferenceMethod },
                    X = 340, Y = sceneTop + (row + (rowCount - 1) / 2d) * RowStride, Width = 270, Height = NodeHeight,
                };
                itemNodes.Add(itemNode);
                nodes.Add(itemNode);
                edges.Add(new() { FromId = taskId, ToId = itemId, Kind = "membership" });

                for (var index = 0; index < item.Checkpoints.Count; index++)
                {
                    var checkpoint = item.Checkpoints[index];
                    var checkpointId = $"{itemId}/checkpoint/{Uri.EscapeDataString(checkpoint.CheckpointId)}";
                    var checkpointReport = itemReport?.Checkpoints.FirstOrDefault(result => result.CheckpointId == checkpoint.CheckpointId);
                    nodes.Add(new()
                    {
                        Id = checkpointId, SceneId = catalog.SceneId, ItemId = item.ItemId,
                        CheckpointId = checkpoint.CheckpointId, Kind = "checkpoint", Title = checkpoint.Name,
                        Detail = checkpoint.Description, Grade = checkpointReport?.Grade,
                        X = 760, Y = sceneTop + (row + index) * RowStride, Width = 330, Height = NodeHeight,
                    });
                    edges.Add(new() { FromId = itemId, ToId = checkpointId,
                        Kind = item.AssessmentKind == "checklist" ? "membership" : "bayesian" });
                }

                row += rowCount;
            }

            nodes.Add(new()
            {
                Id = taskId, SceneId = catalog.SceneId, Kind = "task", Title = catalog.Name,
                Detail = catalog.Description, Grade = report?.Grade,
                X = 40, Y = itemNodes.Count == 0 ? sceneTop : (itemNodes[0].Y + itemNodes[^1].Y) / 2,
                Width = 230, Height = NodeHeight,
            });
            sceneTop += Math.Max(1, row) * RowStride + SceneGap;
        }

        return new SceneGraphProjection(nodes, edges);
    }
}
