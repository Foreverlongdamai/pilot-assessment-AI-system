using System.Text.Json;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;
using PilotAssessment.Desktop.Core.ViewModels;
using PilotAssessment.Desktop.ViewModels;

namespace PilotAssessment.Desktop.UnitTests.ViewModels;

public sealed class BnNodeEditorTests
{
    [Fact]
    public void CptGridMapsOrderedParentAxesAndRectangularPaste()
    {
        var editor = Editor(
            childStates: ["low", "high"],
            parentIds: ["parent.a", "parent.b"],
            parentStates: [["a0", "a1"], ["b0", "b1", "b2"]],
            rows: []);
        var grid = new CptGridModel(editor);

        Assert.Equal("parent.a=a0 · parent.b=b0", grid.ParentAssignmentLabel(0));
        Assert.Equal("parent.a=a0 · parent.b=b2", grid.ParentAssignmentLabel(2));
        Assert.Equal("parent.a=a1 · parent.b=b0", grid.ParentAssignmentLabel(3));

        var pasted = grid.ApplyRectangularText(0, 0, "0.25\t0.75\n0.40\t0.60");

        Assert.Equal(new CptRectangularPasteResult(2, 2), pasted);
        Assert.Equal(0.25, grid.GetCell(0, 0));
        Assert.Equal(0.60, grid.GetCell(1, 1));
    }

    [Fact]
    public void CptGridRejectsNonRectangularPasteAndReportsRowSum()
    {
        var grid = new CptGridModel(Editor(
            childStates: ["low", "medium", "high"],
            parentIds: [],
            parentStates: [],
            rows: [[0.2, 0.3, 0.5]]));

        Assert.Throws<FormatException>(() =>
            grid.ApplyRectangularText(0, 0, "0.2\t0.8\n0.1"));
        grid.SetCell(0, 2, 0.4);

        var validation = grid.Validate();

        Assert.False(validation.IsValid);
        Assert.Contains(validation.Diagnostics, item => item.Code == "cpt.row_sum");
        grid.NormalizeRow(0);
        Assert.True(grid.Validate().IsValid);
    }

    [Fact]
    public async Task CptSaveSendsCompleteBatchAndReplacesLocalValuesWithCanonicalResponse()
    {
        var node = BnNode("bn.target", semanticRevision: 4);
        var definition = Assert.IsType<BnNodeDefinition>(node.Definition);
        var localEditor = EditorFrom(definition.Cpt with
        {
            Mode = CptMode.Manual,
            MaterializedProbabilities = [[0.2, 0.3, 0.5]],
        });
        var canonicalNode = node with
        {
            SemanticRevision = 5,
            Definition = definition with
            {
                Cpt = definition.Cpt with
                {
                    Mode = CptMode.Manual,
                    MaterializedProbabilities = [[0.25, 0.25, 0.5]],
                },
            },
        };
        var gateway = new FakeBayesianGateway
        {
            Graph = Graph([node]),
            CptUpdateResponse = CptResponse(canonicalNode, EditorFrom(
                ((BnNodeDefinition)canonicalNode.Definition).Cpt)),
        };
        var viewModel = new CptGridViewModel(node, localEditor, gateway);
        viewModel.Rows[0].Cells[0].ValueText = "0.4";
        viewModel.Rows[0].Cells[1].ValueText = "0.1";
        viewModel.Rows[0].Cells[2].ValueText = "0.5";
        ModelNode? committed = null;
        viewModel.CanonicalNodeCommitted += (_, args) => committed = args.Node;

        await viewModel.SaveRowsAsync();

        Assert.Equal([0.4, 0.1, 0.5], Assert.Single(gateway.UpdatedRows));
        Assert.Equal("0.25", viewModel.Rows[0].Cells[0].ValueText);
        Assert.Equal(5, committed?.SemanticRevision);
    }

    [Fact]
    public async Task StateCommitSendsExactTargetAndDependentRevisionSet()
    {
        var target = BnNode("bn.target", semanticRevision: 7);
        var targetDefinition = Assert.IsType<BnNodeDefinition>(target.Definition);
        var child = BnNode(
            "bn.child",
            semanticRevision: 9,
            parent: target,
            parentStates: targetDefinition.OrderedStates.Select(state => state.StateId).ToArray());
        var graph = Graph(
            [target, child],
            [new ModelGraphEdge(
                "edge.bn.target.child",
                ModelGraphEdgeKind.Probabilistic,
                new ModelNodeRef(target.NodeId, target.NodeKind),
                new ModelNodeRef(child.NodeId, child.NodeKind),
                null)]);
        var gateway = new FakeBayesianGateway { Graph = graph };
        var nodeGateway = new FakeNodeEditorGateway();
        var viewModel = new BnNodeEditorViewModel(
            target,
            graph.Scheme.SchemeId,
            nodeGateway,
            gateway);
        await viewModel.InitializeAsync();
        viewModel.States.Clear();
        viewModel.States.Add(new BnStateEditItem(new VariableState("bad", "Bad", "Bad state")));
        viewModel.States.Add(new BnStateEditItem(new VariableState("good", "Good", "Good state")));

        await viewModel.CommitStatesAsync();

        Assert.Equal(
            new Dictionary<string, int>(StringComparer.Ordinal)
            {
                ["bn.target"] = 7,
                ["bn.child"] = 9,
            },
            gateway.StateExpectedRevisions);
        Assert.Equal(["bad", "good"], gateway.ReplacementStates.Select(state => state.StateId));
        Assert.Equal(8, viewModel.BuildUpdatedNode().SemanticRevision);
        Assert.Equal(CptMode.Incomplete, viewModel.Cpt.Rows.Count > 0
            ? ((BnNodeDefinition)viewModel.BuildUpdatedNode().Definition).Cpt.Mode
            : CptMode.Incomplete);
    }

    private static CptEditorState Editor(
        string[] childStates,
        string[] parentIds,
        string[][] parentStates,
        double[][] rows)
    {
        var rowCount = parentStates.Length == 0
            ? 1
            : parentStates.Aggregate(1, (count, states) => count * states.Length);
        return new CptEditorState(
            new ModelNodeRef("child", ModelNodeKind.Bn),
            parentIds.Select(id => new ModelNodeRef(id, ModelNodeKind.Bn)).ToArray(),
            childStates,
            parentStates,
            rows,
            rows.Length == 0 ? CptMode.Incomplete : CptMode.Manual,
            rowCount,
            rowCount * childStates.Length);
    }

    private static CptEditorState EditorFrom(NodeCpt cpt)
    {
        var rows = cpt.OrderedParentStateIds.Length == 0
            ? 1
            : cpt.OrderedParentStateIds.Aggregate(1, (count, states) => count * states.Length);
        return new CptEditorState(
            cpt.ChildNode,
            cpt.OrderedParentNodes,
            cpt.ChildStateIds,
            cpt.OrderedParentStateIds,
            cpt.MaterializedProbabilities,
            cpt.Mode,
            rows,
            rows * cpt.ChildStateIds.Length);
    }

    private static ModelNode BnNode(
        string nodeId,
        int semanticRevision,
        ModelNode? parent = null,
        string[]? parentStates = null)
    {
        var draft = ModelNodeDraftFactory.Create(new ModelNodeDraftRequest(
            ModelNodeKind.Bn,
            nodeId,
            null,
            RawModality.X,
            100,
            100));
        var definition = Assert.IsType<BnNodeDefinition>(draft.Definition);
        var parentRefs = parent is null
            ? Array.Empty<ModelNodeRef>()
            : [new ModelNodeRef(parent.NodeId, parent.NodeKind)];
        var parentAxes = parentStates is null ? Array.Empty<string[]>() : [parentStates];
        var childStates = definition.OrderedStates.Select(state => state.StateId).ToArray();
        return draft with
        {
            NodeId = nodeId,
            NameEn = nodeId,
            SemanticRevision = semanticRevision,
            GlobalLayout = new NodeLayout(nodeId, 100, 100),
            Definition = definition with
            {
                OrderedProbabilisticParentNodes = parentRefs,
                Cpt = definition.Cpt with
                {
                    CptId = $"cpt.{nodeId}",
                    ChildNode = new ModelNodeRef(nodeId, ModelNodeKind.Bn),
                    OrderedParentNodes = parentRefs,
                    OrderedParentStateIds = parentAxes,
                    ChildStateIds = childStates,
                    MaterializedProbabilities = [],
                    Mode = CptMode.Incomplete,
                },
            },
        };
    }

    private static ModelGraphSnapshot Graph(
        ModelNode[] nodes,
        ModelGraphEdge[]? edges = null)
    {
        var now = DateTime.UtcNow;
        var scheme = new TaskScheme(
            "task-scheme",
            "0.1.0",
            "task-scheme.test",
            null,
            "Test scheme",
            null,
            null,
            [],
            null,
            ModelObjectLifecycle.Active,
            null,
            nodes.Select(node => node.NodeId).ToArray(),
            nodes.Select(node => node.NodeId).ToArray(),
            [nodes[0].NodeId],
            new Dictionary<string, JsonElement>(StringComparer.Ordinal),
            [],
            1,
            0,
            ModelTechnicalStatus.Incomplete,
            [],
            Hash('a'),
            Hash('b'),
            now,
            now);
        return new ModelGraphSnapshot(
            "model-graph-snapshot",
            "0.2.0",
            "model-library.test",
            scheme,
            nodes,
            edges ?? [],
            now,
            Hash('c'));
    }

    private static CptMutationResponse CptResponse(ModelNode node, CptEditorState editor) => new(
        node,
        ["task-scheme.test"],
        node.SemanticRevision,
        editor,
        EmptyDiff(),
        "tx.test",
        "audit.test",
        false,
        "trace.test");

    private static CanonicalModelDiff EmptyDiff() => new(
        [], [], [], [], [], new Dictionary<string, JsonElement>(StringComparer.Ordinal));

    private static string Hash(char value) => new(value, 64);

    private sealed class FakeNodeEditorGateway : IModelNodeEditorGateway
    {
        public Task<IReadOnlyList<OperatorDefinition>> ListOperatorsAsync(CancellationToken cancellationToken = default) =>
            Task.FromResult<IReadOnlyList<OperatorDefinition>>([]);

        public Task<ModelNodeMutationResponse> UpdateNodeAsync(ModelNode node, int expectedSemanticRevision, int expectedLayoutRevision, string actor, string transactionId, CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public Task<IReadOnlyList<ModelNodeUsage>> ListNodeUsagesAsync(string nodeId, CancellationToken cancellationToken = default) =>
            Task.FromResult<IReadOnlyList<ModelNodeUsage>>([]);

        public Task<IReadOnlyList<ModelChangeEvent>> ListNodeHistoryAsync(string nodeId, CancellationToken cancellationToken = default) =>
            Task.FromResult<IReadOnlyList<ModelChangeEvent>>([]);

        public Task<CurrentModelRunSnapshot> PreviewNodeAsync(string sessionRevisionId, string schemeId, string nodeId, IReadOnlyDictionary<string, JsonElement> runtimeParameters, CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();
    }

    private sealed class FakeBayesianGateway : IBayesianNodeEditorGateway
    {
        public required ModelGraphSnapshot Graph { get; set; }

        public CptMutationResponse? CptUpdateResponse { get; init; }

        public double[][] UpdatedRows { get; private set; } = [];

        public IReadOnlyDictionary<string, int> StateExpectedRevisions { get; private set; } =
            new Dictionary<string, int>(StringComparer.Ordinal);

        public VariableState[] ReplacementStates { get; private set; } = [];

        public Task<ModelGraphSnapshot> GetGraphAsync(string schemeId, CancellationToken cancellationToken = default) =>
            Task.FromResult(Graph);

        public Task<CptInspectResponse> InspectCptAsync(string nodeId, CancellationToken cancellationToken = default)
        {
            var node = Graph.Nodes.Single(item => item.NodeId == nodeId);
            var definition = Assert.IsType<BnNodeDefinition>(node.Definition);
            var editor = EditorFrom(definition.Cpt);
            return Task.FromResult(new CptInspectResponse(
                new CptValidationOutcome(false, editor.RequiredRowCount, editor.RequiredCellCount, []),
                editor,
                "trace.inspect"));
        }

        public Task<CptMutationResponse> UpdateCptRowsAsync(string nodeId, IReadOnlyList<IReadOnlyList<double>> rows, int expectedSemanticRevision, string actor, CancellationToken cancellationToken = default)
        {
            UpdatedRows = rows.Select(row => row.ToArray()).ToArray();
            return Task.FromResult(CptUpdateResponse ?? throw new InvalidOperationException("Missing CPT response fixture."));
        }

        public Task<CptMutationResponse> MaterializeCptAsync(string nodeId, string strategy, double[]? weights, double weakestLinkStrength, double sigma, int expectedSemanticRevision, string actor, CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public Task<CptMutationResponse> AddProbabilisticEdgeAsync(string childNodeId, string parentNodeId, string strategy, int expectedSemanticRevision, string actor, CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public Task<CptMutationResponse> RemoveProbabilisticEdgeAsync(string childNodeId, string parentNodeId, string strategy, double[]? marginalWeights, int expectedSemanticRevision, string actor, CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public Task<CptMutationResponse> ReorderProbabilisticParentsAsync(string childNodeId, IReadOnlyList<string> orderedParentNodeIds, int expectedSemanticRevision, string actor, CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public Task<ModelNodeStatesMutationResponse> ReplaceNodeStatesAsync(string nodeId, IReadOnlyList<VariableState> states, IReadOnlyDictionary<string, int> expectedSemanticRevisions, string actor, CancellationToken cancellationToken = default)
        {
            ReplacementStates = states.ToArray();
            StateExpectedRevisions = new Dictionary<string, int>(expectedSemanticRevisions, StringComparer.Ordinal);
            var changed = Graph.Nodes.Select(node =>
            {
                var definition = Assert.IsType<BnNodeDefinition>(node.Definition);
                var cpt = definition.Cpt with
                {
                    ChildStateIds = node.NodeId == nodeId
                        ? states.Select(state => state.StateId).ToArray()
                        : definition.Cpt.ChildStateIds,
                    OrderedParentStateIds = definition.Cpt.OrderedParentNodes.Any(parent => parent.NodeId == nodeId)
                        ? [states.Select(state => state.StateId).ToArray()]
                        : definition.Cpt.OrderedParentStateIds,
                    MaterializedProbabilities = [],
                    Mode = CptMode.Incomplete,
                };
                return node with
                {
                    SemanticRevision = node.SemanticRevision + 1,
                    Definition = definition with
                    {
                        OrderedStates = node.NodeId == nodeId ? states.ToArray() : definition.OrderedStates,
                        Cpt = cpt,
                    },
                };
            }).ToArray();
            Graph = Graph with { Nodes = changed };
            return Task.FromResult(new ModelNodeStatesMutationResponse(
                changed,
                [Graph.Scheme.SchemeId],
                EmptyDiff(),
                "tx.states",
                "audit.states",
                false,
                "trace.states"));
        }
    }
}
