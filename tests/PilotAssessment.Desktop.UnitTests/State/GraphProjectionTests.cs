using System.Text.Json;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;

namespace PilotAssessment.Desktop.UnitTests.State;

public sealed class GraphProjectionTests
{
    private static readonly DateTime Now = new(2026, 7, 17, 15, 0, 0, DateTimeKind.Utc);

    [Fact]
    public void ActiveOnlyUsesCanonicalClosureAndKeepsBothEdgeSemantics()
    {
        var snapshot = SevenNodeGraph();

        var result = GraphProjection.Project(
            snapshot,
            new GraphProjectionOptions(GraphViewMode.ActiveOnly));

        Assert.Equal(4, result.Nodes.Count);
        Assert.All(result.Nodes, node => Assert.True(node.IsActive));
        Assert.Equal(3, result.Edges.Count);
        Assert.Contains(result.Edges, edge => edge.EdgeKind is ModelGraphEdgeKind.Extraction);
        Assert.Contains(result.Edges, edge => edge.EdgeKind is ModelGraphEdgeKind.Probabilistic);
        Assert.All(result.Edges, edge => Assert.True(edge.IsActive));
        Assert.True(result.Nodes.Single(node => node.NodeId == "bn.competency").IsOutput);
    }

    [Fact]
    public void ActiveAndInactiveDimsRealNodesAndAppliesSchemeLayoutOverride()
    {
        var snapshot = SevenNodeGraph();

        var result = GraphProjection.Project(
            snapshot,
            new GraphProjectionOptions(
                GraphViewMode.ActiveAndInactive,
                SelectedNodeIds: new HashSet<string>(["evidence.precision"], StringComparer.Ordinal)));

        Assert.Equal(6, result.Nodes.Count);
        Assert.DoesNotContain(result.Nodes, node => node.NodeId == "bn.archived");
        var active = result.Nodes.Single(node => node.NodeId == "evidence.precision");
        var inactive = result.Nodes.Single(node => node.NodeId == "evidence.gaze");
        Assert.Equal(777, active.X);
        Assert.Equal(333, active.Y);
        Assert.True(active.IsSelected);
        Assert.Equal(1.0, active.VisualOpacity);
        Assert.True(inactive.VisualOpacity < 0.5);
        Assert.Contains(result.Edges, edge => !edge.IsActive);
    }

    [Fact]
    public void AllGlobalAndFiltersSearchBilingualMetadataWithoutReconstructingEdges()
    {
        var snapshot = SevenNodeGraph();
        var all = GraphProjection.Project(
            snapshot,
            new GraphProjectionOptions(GraphViewMode.AllGlobalNodes));

        Assert.Equal(7, all.Nodes.Count);
        Assert.True(all.Nodes.Single(node => node.NodeId == "bn.archived").IsArchived);

        var bilingual = GraphProjection.Project(
            snapshot,
            new GraphProjectionOptions(
                GraphViewMode.AllGlobalNodes,
                SearchText: "轨迹",
                NodeKind: ModelNodeKind.Evidence));
        Assert.Single(bilingual.Nodes);
        Assert.Equal("evidence.precision", bilingual.Nodes[0].NodeId);
        Assert.Empty(bilingual.Edges);

        var inactiveGaze = GraphProjection.Project(
            snapshot,
            new GraphProjectionOptions(
                GraphViewMode.ActiveAndInactive,
                NodeKind: ModelNodeKind.Evidence,
                Group: "attention",
                Tag: "gaze",
                Active: false));
        Assert.Single(inactiveGaze.Nodes);
        Assert.Equal("evidence.gaze", inactiveGaze.Nodes[0].NodeId);
    }

    private static ModelGraphSnapshot SevenNodeGraph()
    {
        var nodes = new[]
        {
            Node("raw.x", ModelNodeKind.RawInput, "Flight state", "飞行状态", 100, 110, ["trajectory"], "inputs"),
            Node("raw.g", ModelNodeKind.RawInput, "Gaze", "注视", 100, 330, ["gaze"], "inputs"),
            Node("evidence.precision", ModelNodeKind.Evidence, "Trajectory precision", "轨迹精度", 320, 110, ["trajectory"], "control"),
            Node("evidence.gaze", ModelNodeKind.Evidence, "AOI response", "AOI 响应", 320, 330, ["gaze"], "attention"),
            Node("bn.skill", ModelNodeKind.Bn, "Tracking", "跟踪", 540, 150, ["control"], "skills"),
            Node("bn.competency", ModelNodeKind.Bn, "Task control", "任务控制", 740, 150, ["competency"], "competencies"),
            Node(
                "bn.archived",
                ModelNodeKind.Bn,
                "Legacy skill",
                "旧技能",
                740,
                390,
                ["legacy"],
                "legacy",
                ModelObjectLifecycle.Archived),
        };
        var active = new[] { "bn.competency", "bn.skill", "evidence.precision", "raw.x" };
        var scheme = new TaskScheme(
            "task-scheme",
            "0.1.0",
            "task-scheme.test",
            null,
            "Projection test",
            null,
            null,
            [],
            null,
            ModelObjectLifecycle.Active,
            null,
            ["bn.competency"],
            active,
            ["bn.competency"],
            new Dictionary<string, JsonElement>(StringComparer.Ordinal),
            [new NodeLayout("evidence.precision", 777, 333)],
            3,
            1,
            ModelTechnicalStatus.Executable,
            [],
            new string('a', 64),
            new string('b', 64),
            Now,
            Now);
        var edges = new[]
        {
            Edge("edge.extract.x", ModelGraphEdgeKind.Extraction, nodes[0], nodes[2], "input.x"),
            Edge("edge.bn.skill.precision", ModelGraphEdgeKind.Probabilistic, nodes[4], nodes[2]),
            Edge("edge.bn.competency.skill", ModelGraphEdgeKind.Probabilistic, nodes[5], nodes[4]),
            Edge("edge.extract.g", ModelGraphEdgeKind.Extraction, nodes[1], nodes[3], "input.g"),
            Edge("edge.bn.skill.gaze", ModelGraphEdgeKind.Probabilistic, nodes[4], nodes[3]),
        };
        return new ModelGraphSnapshot(
            "model-graph-snapshot",
            "0.1.0",
            "project.test",
            scheme,
            nodes,
            edges,
            Now,
            new string('c', 64));
    }

    private static ModelNode Node(
        string id,
        ModelNodeKind kind,
        string nameEn,
        string nameZh,
        double x,
        double y,
        string[] tags,
        string group,
        ModelObjectLifecycle lifecycle = ModelObjectLifecycle.Active) => new(
            "model-node",
            "0.1.0",
            id,
            kind,
            nameZh,
            nameEn,
            nameZh,
            nameEn,
            nameZh,
            nameEn,
            tags,
            group,
            lifecycle,
            null,
            new TestDefinition(),
            new NodeLayout(id, x, y),
            0,
            0,
            ModelTechnicalStatus.Executable,
            [],
            new string('d', 64),
            new string('e', 64),
            Now,
            Now);

    private static ModelGraphEdge Edge(
        string id,
        ModelGraphEdgeKind kind,
        ModelNode parent,
        ModelNode child,
        string? binding = null) => new(
            id,
            kind,
            new ModelNodeRef(parent.NodeId, parent.NodeKind),
            new ModelNodeRef(child.NodeId, child.NodeKind),
            binding);

    private sealed record TestDefinition : ModelNodeDefinition;
}
