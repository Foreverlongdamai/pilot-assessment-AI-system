using System.Diagnostics;
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
        Assert.Equal(777 + active.LayoutOffsetX, active.X);
        Assert.Equal(333, active.Y);
        Assert.True(active.IsSelected);
        Assert.Equal(1.0, active.VisualOpacity);
        Assert.True(inactive.VisualOpacity < 0.5);
        Assert.Contains(result.Edges, edge => !edge.IsActive);
    }

    [Fact]
    public void AllGlobalAndFiltersSearchCanonicalMetadataWithoutReconstructingEdges()
    {
        var snapshot = SevenNodeGraph();
        var all = GraphProjection.Project(
            snapshot,
            new GraphProjectionOptions(GraphViewMode.AllGlobalNodes));

        Assert.Equal(7, all.Nodes.Count);
        Assert.True(all.Nodes.Single(node => node.NodeId == "bn.archived").IsArchived);

        var canonical = GraphProjection.Project(
            snapshot,
            new GraphProjectionOptions(
                GraphViewMode.AllGlobalNodes,
                SearchText: "Trajectory",
                Layer: GraphDisplayLayer.Evidence));
        Assert.Single(canonical.Nodes);
        Assert.Equal("evidence.precision", canonical.Nodes[0].NodeId);
        Assert.Empty(canonical.Edges);

        var inactiveGaze = GraphProjection.Project(
            snapshot,
            new GraphProjectionOptions(
                GraphViewMode.ActiveAndInactive,
                Layer: GraphDisplayLayer.Evidence,
                Group: "attention",
                Active: false));
        Assert.Single(inactiveGaze.Nodes);
        Assert.Equal("evidence.gaze", inactiveGaze.Nodes[0].NodeId);
    }

    [Fact]
    public void FiveLayerFilterHidesFamilyRootsAndPreservesCanonicalBnDirection()
    {
        var snapshot = SevenNodeGraph();
        var all = GraphProjection.Project(
            snapshot,
            new GraphProjectionOptions(GraphViewMode.ActiveAndInactive));

        var rawX = all.Nodes.Single(node => node.NodeId == "raw.x");
        var evidence = all.Nodes.Single(node => node.NodeId == "evidence.precision");
        var subSkill = all.Nodes.Single(node => node.NodeId == "bn.skill");
        var competency = all.Nodes.Single(node => node.NodeId == "bn.competency");
        Assert.True(all.RawInputFamilies.Max(node => node.X) < rawX.X);
        Assert.True(rawX.X < evidence.X);
        Assert.True(evidence.X < subSkill.X);
        Assert.True(subSkill.X < competency.X);

        var probabilistic = all.Edges.Single(edge =>
            edge.Parent.NodeId == "bn.competency" && edge.Child.NodeId == "bn.skill");
        Assert.True(probabilistic.Parent.X > probabilistic.Child.X);

        foreach (var layer in new[]
                 {
                     GraphDisplayLayer.ExtractedData,
                     GraphDisplayLayer.Evidence,
                     GraphDisplayLayer.SubSkill,
                     GraphDisplayLayer.Competency,
                 })
        {
            var filtered = GraphProjection.Project(
                snapshot,
                new GraphProjectionOptions(GraphViewMode.ActiveAndInactive, Layer: layer));
            Assert.Empty(filtered.RawInputFamilies);
            Assert.All(filtered.Nodes, node => Assert.Equal(layer, GraphProjection.LayerOf(node.Node)));
        }

        var families = GraphProjection.Project(
            snapshot,
            new GraphProjectionOptions(
                GraphViewMode.ActiveAndInactive,
                Layer: GraphDisplayLayer.RawInputFamily));
        Assert.Empty(families.Nodes);
        Assert.Equal(5, families.RawInputFamilies.Count);
    }

    [Fact]
    public void ThousandNodeProjectionRealizesOnlyBufferedViewportAndRemainsResponsive()
    {
        var nodes = Enumerable.Range(0, 1_000)
            .Select(index => Node(
                $"evidence.synthetic-{index:D4}",
                ModelNodeKind.Evidence,
                $"Synthetic evidence {index}",
                $"合成证据 {index}",
                100 + ((index % 40) * 180),
                100 + ((index / 40) * 180),
                ["projection-only"],
                "ui-benchmark"))
            .ToArray();
        var active = nodes.Select(node => node.NodeId).ToArray();
        var scheme = new TaskScheme(
            "task-scheme",
            "0.2.0",
            "task-scheme.ui-benchmark",
            "In-memory UI projection benchmark",
            "In-memory graph projection performance fixture.",
            [],
            null,
            ModelObjectLifecycle.Active,
            null,
            [nodes[0].NodeId],
            active,
            [nodes[0].NodeId],
            new Dictionary<string, JsonElement>(StringComparer.Ordinal),
            [],
            0,
            0,
            ModelTechnicalStatus.Executable,
            [],
            new string('a', 64),
            new string('b', 64),
            Now,
            Now);
        var snapshot = new ModelGraphSnapshot(
            "model-graph-snapshot",
            "0.3.0",
            "model-library.ui-benchmark",
            scheme,
            nodes,
            [],
            Now,
            new string('c', 64));

        var stopwatch = Stopwatch.StartNew();
        var projection = GraphProjection.Project(
            snapshot,
            new GraphProjectionOptions(GraphViewMode.ActiveAndInactive));
        var plan = GraphViewportRealization.Plan(
            projection.Nodes,
            new GraphViewportRect(0, 0, 1_280, 720));
        stopwatch.Stop();

        Assert.Equal(1_000, projection.Nodes.Count);
        Assert.InRange(plan.RealizedNodes.Count, 1, 100);
        Assert.True(plan.ExtentWidth > 7_000);
        Assert.True(plan.ExtentHeight > 4_000);
        Assert.True(
            stopwatch.Elapsed < TimeSpan.FromSeconds(2),
            $"1,000-node UI projection took {stopwatch.Elapsed.TotalMilliseconds:F1} ms.");
    }

    [Theory]
    [InlineData(500, 400, 100, 100, 160, 130, 440, 370)]
    [InlineData(20, 10, 100, 100, 180, 140, 0, 0)]
    [InlineData(980, 790, 100, 100, 40, 20, 1_000, 800)]
    public void CanvasPanConvertsPointerDragToClampedScrollOffsets(
        double startHorizontalOffset,
        double startVerticalOffset,
        double startPointerX,
        double startPointerY,
        double currentPointerX,
        double currentPointerY,
        double expectedHorizontalOffset,
        double expectedVerticalOffset)
    {
        var origin = new GraphViewportPanOrigin(
            startPointerX,
            startPointerY,
            startHorizontalOffset,
            startVerticalOffset);

        var offset = GraphViewportPan.Calculate(
            origin,
            currentPointerX,
            currentPointerY,
            1_000,
            800);

        Assert.Equal(expectedHorizontalOffset, offset.Horizontal);
        Assert.Equal(expectedVerticalOffset, offset.Vertical);
    }

    [Fact]
    public void ProjectsFiveUnifiedFamilyRootsAndTypedReadOnlyProvenance()
    {
        var rawNodes = new[]
        {
            RawNode("raw.x", RawInputFamily.X, RawModality.X, "X.state", 100, 100),
            RawNode("raw.u", RawInputFamily.U, RawModality.U, "U.controls", 100, 260),
            RawNode("raw.i", RawInputFamily.I, RawModality.I, "I.frames", 100, 420),
            RawNode("raw.g", RawInputFamily.G, RawModality.G, "G.frames", 100, 580),
            RawNode("raw.eeg", RawInputFamily.P, RawModality.Eeg, "EEG.channels", 100, 740),
            RawNode(
                "raw.pilot-camera",
                RawInputFamily.PilotCamera,
                RawModality.PilotCamera,
                "pilot_camera.frames",
                100,
                900),
            RawNode(
                "raw.derived",
                null,
                null,
                "derived.control-state",
                280,
                180,
                ["X.state", "U.controls"]),
            RawNode(
                "raw.cycle-a",
                null,
                null,
                "derived.cycle-a",
                280,
                500,
                ["derived.cycle-b"]),
            RawNode(
                "raw.cycle-b",
                null,
                null,
                "derived.cycle-b",
                280,
                660,
                ["derived.cycle-a"]),
        };
        var scheme = Scheme("task-scheme.raw-family", rawNodes);
        var snapshot = new ModelGraphSnapshot(
            "model-graph-snapshot",
            "0.2.0",
            "model-library.raw-family",
            scheme,
            rawNodes,
            [],
            Now,
            new string('c', 64));

        var result = GraphProjection.Project(
            snapshot,
            new GraphProjectionOptions(GraphViewMode.ActiveAndInactive));

        Assert.Equal(5, result.RawInputFamilies.Count);
        Assert.All(result.RawInputFamilies, family =>
        {
            Assert.Equal(GraphProjection.RawInputFamilyDiameter, family.Diameter);
            Assert.StartsWith("raw-family.", family.ProjectionId, StringComparison.Ordinal);
            Assert.True(family.X < result.Nodes.Min(node => node.X));
        });
        Assert.Equal(8, result.ProvenanceEdges.Count);
        Assert.Equal(2, result.RawInputFamilies.Single(node => node.Family is RawInputFamily.X).MemberCount);
        Assert.Equal(2, result.RawInputFamilies.Single(node => node.Family is RawInputFamily.U).MemberCount);
        Assert.Equal(2, result.RawInputFamilies.Single(node => node.Family is RawInputFamily.I).MemberCount);
        Assert.Equal(1, result.RawInputFamilies.Single(node => node.Family is RawInputFamily.G).MemberCount);
        Assert.Equal(1, result.RawInputFamilies.Single(node => node.Family is RawInputFamily.P).MemberCount);
        Assert.Contains(
            result.ProvenanceEdges,
            edge => edge.Parent.Family is RawInputFamily.I && edge.Child.NodeId == "raw.pilot-camera");
        Assert.Equal(2, result.ProvenanceEdges.Count(edge => edge.Child.NodeId == "raw.derived"));
        Assert.DoesNotContain(
            result.ProvenanceEdges,
            edge => edge.Child.NodeId is "raw.cycle-a" or "raw.cycle-b");
        Assert.Empty(result.Edges);
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
            "0.2.0",
            "task-scheme.test",
            "Projection test",
            "Graph projection test scheme.",
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
            "0.3.0",
            "model-library.test",
            scheme,
            nodes,
            edges,
            Now,
            new string('c', 64));
    }

    private static TaskScheme Scheme(string schemeId, IReadOnlyList<ModelNode> nodes) => new(
        "task-scheme",
        "0.2.0",
        schemeId,
        "Raw family projection",
        "Raw input family projection scheme.",
        [],
        null,
        ModelObjectLifecycle.Active,
        null,
        nodes.Select(node => node.NodeId).ToArray(),
        nodes.Select(node => node.NodeId).ToArray(),
        [],
        new Dictionary<string, JsonElement>(StringComparer.Ordinal),
        [],
        0,
        0,
        ModelTechnicalStatus.Executable,
        [],
        new string('a', 64),
        new string('b', 64),
        Now,
        Now);

    private static ModelNode RawNode(
        string id,
        RawInputFamily? family,
        RawModality? modality,
        string sourceId,
        double x,
        double y,
        string[]? dependencies = null)
    {
        var descriptor = new SourceDescriptor(
            "source-descriptor",
            "0.1.0",
            sourceId,
            dependencies is { Length: > 0 } ? SourceKind.DerivedArtifact : SourceKind.RawStream,
            sourceId,
            sourceId,
            new PortType("table", PortCardinality.Many, TemporalSemantics.Sampled, null),
            modality,
            dependencies ?? [],
            new Dictionary<string, JsonElement>(StringComparer.Ordinal),
            new string('f', 64));
        return new ModelNode(
            "model-node",
            "0.2.0",
            id,
            ModelNodeKind.RawInput,
            sourceId,
            sourceId,
            $"{sourceId} raw input.",
            [],
            "inputs",
            ModelObjectLifecycle.Active,
            null,
            new RawInputNodeDefinition(
                family,
                dependencies is { Length: > 0 }
                    ? RawResourceRole.DerivedResource
                    : RawResourceRole.Stream,
                descriptor,
                new Dictionary<string, JsonElement>(StringComparer.Ordinal),
                "Raw input help."),
            new NodeLayout(id, x, y),
            0,
            0,
            ModelTechnicalStatus.Executable,
            [],
            new string('d', 64),
            new string('e', 64),
            Now,
            Now);
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
            "0.2.0",
            id,
            kind,
            nameEn,
            nameEn,
            $"{nameEn} graph node.",
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
