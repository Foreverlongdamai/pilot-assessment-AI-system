using System.Text.Json;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;
using PilotAssessment.Desktop.Core.ViewModels;

namespace PilotAssessment.Desktop.UnitTests.ViewModels;

public sealed class GraphCommandTests
{
    [Fact]
    public void DraftFactoryCreatesTypedIncompleteNodesWithoutPythonGeneration()
    {
        var raw = Draft(ModelNodeKind.RawInput, "New raw");
        var evidence = Draft(ModelNodeKind.Evidence, "New evidence");
        var bn = Draft(ModelNodeKind.Bn, "New BN");

        Assert.IsType<RawInputNodeDefinition>(raw.Definition);
        var evidenceDefinition = Assert.IsType<EvidenceNodeDefinition>(evidence.Definition);
        var bnDefinition = Assert.IsType<BnNodeDefinition>(bn.Definition);
        Assert.Equal(ModelTechnicalStatus.Incomplete, evidence.TechnicalStatus);
        Assert.Empty(evidenceDefinition.Recipe.Graph.Nodes);
        Assert.Null(evidenceDefinition.Recipe.Scoring);
        Assert.Equal(CptMode.Incomplete, evidenceDefinition.Cpt.Mode);
        Assert.Empty(evidenceDefinition.Cpt.MaterializedProbabilities);
        Assert.Equal(CptMode.Incomplete, bnDefinition.Cpt.Mode);
        Assert.DoesNotContain("python", JsonSerializer.Serialize(
            evidence,
            PilotAssessmentJsonContext.Default.ModelNode), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task ActivationUsesBackendClosureAndKeepsOtherSchemeIsolated()
    {
        var fixture = new FakeGraphGateway();
        var coordinator = new ModelGraphCommandCoordinator(fixture, new ModelClipboard());
        var inactive = fixture.Graph.Nodes.Single(node => node.NodeId == fixture.InactiveNodeId);

        var response = await coordinator.ActivateNodeAsync(fixture.Graph.Scheme, inactive.NodeId);

        Assert.Equal(fixture.Graph.Scheme.SchemeId, fixture.LastActivationSchemeId);
        Assert.Contains(inactive.NodeId, response.Scheme.ComputedActiveClosure);
        Assert.All(
            ((EvidenceNodeDefinition)inactive.Definition).OrderedProbabilisticParentNodes,
            parent => Assert.Contains(parent.NodeId, response.Scheme.ComputedActiveClosure));
        Assert.DoesNotContain(inactive.NodeId, fixture.OtherScheme.ComputedActiveClosure);
    }

    [Fact]
    public async Task DeactivationCancelSendsNoWriteAndContinueUsesExactImpactHash()
    {
        var fixture = new FakeGraphGateway();
        var coordinator = new ModelGraphCommandCoordinator(fixture, new ModelClipboard());
        var nodeId = fixture.ActiveEvidenceId;
        var impact = await coordinator.PreviewDeactivationAsync(fixture.Graph.Scheme, nodeId);

        var cancelled = await coordinator.CompleteDeactivationAsync(
            fixture.Graph.Scheme,
            nodeId,
            impact,
            continueRequested: false);

        Assert.Null(cancelled);
        Assert.Equal(0, fixture.DeactivationWrites);

        var applied = await coordinator.CompleteDeactivationAsync(
            fixture.Graph.Scheme,
            nodeId,
            impact,
            continueRequested: true);

        Assert.NotNull(applied);
        Assert.Equal(1, fixture.DeactivationWrites);
        Assert.Equal(impact.ImpactHash, fixture.LastImpactHash);
        Assert.DoesNotContain(nodeId, applied.Scheme.ComputedActiveClosure);
    }

    [Fact]
    public async Task StaleImpactPropagatesWithoutInventingLocalState()
    {
        var fixture = new FakeGraphGateway { RejectDeactivationAsStale = true };
        var coordinator = new ModelGraphCommandCoordinator(fixture, new ModelClipboard());
        var originalHash = fixture.Graph.GraphHash;
        var impact = await coordinator.PreviewDeactivationAsync(
            fixture.Graph.Scheme,
            fixture.ActiveEvidenceId);

        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            coordinator.CompleteDeactivationAsync(
                fixture.Graph.Scheme,
                fixture.ActiveEvidenceId,
                impact,
                continueRequested: true));

        Assert.Equal(originalHash, fixture.Graph.GraphHash);
        Assert.Equal(1, fixture.DeactivationWrites);
    }

    [Fact]
    public async Task ModelLibraryScopedPasteCopiesOnlySelectedNodeAndRetainsFixedParents()
    {
        var fixture = new FakeGraphGateway();
        var clipboard = new ModelClipboard();
        var coordinator = new ModelGraphCommandCoordinator(fixture, clipboard);
        var source = fixture.Graph.Nodes.Single(node => node.NodeId == fixture.ActiveEvidenceId);
        var sourceDefinition = Assert.IsType<EvidenceNodeDefinition>(source.Definition);
        coordinator.Copy(fixture.Graph.ModelLibraryId, [source.NodeId]);

        var response = await coordinator.PasteAsync(
            fixture.Graph.ModelLibraryId,
            fixture.Graph.Scheme);

        var copied = Assert.Single(response.CopiedNodes);
        Assert.Equal([source.NodeId], fixture.LastBatchCopyNodeIds);
        Assert.Equal(source.NodeId, copied.CopiedFromNodeId);
        Assert.Equal(
            sourceDefinition.OrderedProbabilisticParentNodes,
            Assert.IsType<EvidenceNodeDefinition>(copied.Definition).OrderedProbabilisticParentNodes);
        Assert.Contains(source.NodeId, response.Scheme.ComputedActiveClosure);
        Assert.Contains(copied.NodeId, response.Scheme.ComputedActiveClosure);
        Assert.False(coordinator.CanPaste("project.other"));
        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            coordinator.PasteAsync("project.other", fixture.Graph.Scheme));
    }

    [Fact]
    public async Task LayoutAndProbabilisticEdgeChoicesMapToTypedBackendRequests()
    {
        var fixture = new FakeGraphGateway();
        var coordinator = new ModelGraphCommandCoordinator(fixture, new ModelClipboard());
        var target = fixture.Graph.Nodes.Single(node => node.NodeId == fixture.InactiveNodeId);
        var source = fixture.Graph.Nodes.Single(node => node.NodeId == fixture.ParentNodeId);
        var layout = new NodeLayout(target.NodeId, 777, 555);

        var layoutResponse = await coordinator.UpdateLayoutAsync(fixture.Graph.Scheme, [layout]);
        await coordinator.AddEdgeAsync(source, target, markCptIncomplete: false);
        await coordinator.RemoveEdgeAsync(
            new ModelGraphEdge(
                "edge.test",
                ModelGraphEdgeKind.Probabilistic,
                new ModelNodeRef(source.NodeId, source.NodeKind),
                new ModelNodeRef(target.NodeId, target.NodeKind),
                null),
            source,
            target,
            markCptIncomplete: true);

        Assert.Equal(layout, Assert.Single(fixture.LastLayoutPositions));
        Assert.Equal(fixture.Graph.Scheme.SemanticRevision, fixture.LastLayoutSemanticRevision);
        Assert.Equal("preserve_independence", fixture.LastAddStrategy);
        Assert.Equal("incomplete", fixture.LastRemoveStrategy);
        Assert.Null(fixture.LastMarginalWeights);
        Assert.Equal(777, layoutResponse.Graph.Scheme.LayoutOverrides.Single().X);
    }

    [Fact]
    public async Task ExtractionEdgeUsesExactRecipeBindingMigration()
    {
        var fixture = new FakeGraphGateway();
        var coordinator = new ModelGraphCommandCoordinator(fixture, new ModelClipboard());
        var raw = fixture.Graph.Nodes.Single(node => node.NodeKind is ModelNodeKind.RawInput);
        var evidence = fixture.Graph.Nodes.Single(node => node.NodeId == fixture.InactiveNodeId);

        await coordinator.AddEdgeAsync(raw, evidence, markCptIncomplete: false);

        Assert.NotNull(fixture.LastExtractionBindingId);
        Assert.Contains(
            fixture.LastExtractionRecipe!.Inputs,
            input => input.BindingId == fixture.LastExtractionBindingId);
        Assert.Contains(
            fixture.LastExtractionRecipe.Graph.Nodes,
            node => node.InputBindingId == fixture.LastExtractionBindingId);
    }

    private static ModelNode Draft(ModelNodeKind kind, string name) =>
        ModelNodeDraftFactory.Create(new ModelNodeDraftRequest(
            kind,
            name,
            RawModality.X,
            100,
            100));

    private sealed class FakeGraphGateway : IModelGraphGateway
    {
        private static readonly DateTime Now = new(2026, 7, 17, 22, 0, 0, DateTimeKind.Utc);
        private readonly CanonicalModelDiff _diff = new(
            [], [], [], [], [], new Dictionary<string, JsonElement>(StringComparer.Ordinal));

        public FakeGraphGateway()
        {
            var parent = Draft(ModelNodeKind.Bn, "Parent skill");
            ParentNodeId = parent.NodeId;
            var activeEvidence = WithParent(Draft(ModelNodeKind.Evidence, "Active Evidence"), parent);
            ActiveEvidenceId = activeEvidence.NodeId;
            var inactive = WithParent(Draft(ModelNodeKind.Evidence, "Inactive Evidence"), parent);
            InactiveNodeId = inactive.NodeId;
            var raw = Draft(ModelNodeKind.RawInput, "Raw X");
            var scheme = Scheme(
                "task-scheme.active",
                [activeEvidence.NodeId],
                [parent.NodeId, activeEvidence.NodeId]);
            Graph = Snapshot(scheme, [raw, parent, activeEvidence, inactive]);
            OtherScheme = Scheme("task-scheme.other", [], []);
        }

        public ModelGraphSnapshot Graph { get; private set; }
        public TaskScheme OtherScheme { get; }
        public string ParentNodeId { get; }
        public string ActiveEvidenceId { get; }
        public string InactiveNodeId { get; }
        public string? LastActivationSchemeId { get; private set; }
        public int DeactivationWrites { get; private set; }
        public string? LastImpactHash { get; private set; }
        public bool RejectDeactivationAsStale { get; set; }
        public string[] LastBatchCopyNodeIds { get; private set; } = [];
        public NodeLayout[] LastLayoutPositions { get; private set; } = [];
        public int LastLayoutSemanticRevision { get; private set; }
        public string? LastAddStrategy { get; private set; }
        public string? LastRemoveStrategy { get; private set; }
        public double[]? LastMarginalWeights { get; private set; }
        public string? LastExtractionBindingId { get; private set; }
        public EvidenceRecipe? LastExtractionRecipe { get; private set; }

        public Task<ModelGraphSnapshot> GetGraphAsync(
            string schemeId,
            CancellationToken cancellationToken = default) => Task.FromResult(Graph);

        public Task<ModelNodeMutationResponse> CreateNodeAsync(
            ModelNode node,
            string actor,
            CancellationToken cancellationToken = default)
        {
            Graph = Graph with { Nodes = [.. Graph.Nodes, node] };
            return Task.FromResult(NodeMutation(node));
        }

        public Task<TaskSchemeMutationResponse> ActivateNodeAsync(
            string schemeId,
            string nodeId,
            int expectedSemanticRevision,
            string actor,
            CancellationToken cancellationToken = default)
        {
            LastActivationSchemeId = schemeId;
            var node = Graph.Nodes.Single(item => item.NodeId == nodeId);
            var closure = Graph.Scheme.ComputedActiveClosure
                .Concat(Parents(node))
                .Append(nodeId)
                .Distinct(StringComparer.Ordinal)
                .OrderBy(item => item, StringComparer.Ordinal)
                .ToArray();
            var scheme = Graph.Scheme with
            {
                ExplicitActiveNodeIds = Graph.Scheme.ExplicitActiveNodeIds
                    .Append(nodeId)
                    .Distinct(StringComparer.Ordinal)
                    .OrderBy(item => item, StringComparer.Ordinal)
                    .ToArray(),
                ComputedActiveClosure = closure,
                SemanticRevision = Graph.Scheme.SemanticRevision + 1,
            };
            Graph = Graph with { Scheme = scheme, GraphHash = Hash('a') };
            return Task.FromResult(SchemeMutation(scheme));
        }

        public Task<DeactivationImpact> PreviewDeactivationAsync(
            string schemeId,
            string nodeId,
            CancellationToken cancellationToken = default) => Task.FromResult(new DeactivationImpact(
                "deactivation-impact",
                "0.1.0",
                schemeId,
                Graph.Scheme.SemanticRevision,
                nodeId,
                [nodeId],
                [],
                Hash('d')));

        public Task<TaskSchemeMutationResponse> DeactivateNodeAsync(
            string schemeId,
            string nodeId,
            int expectedSemanticRevision,
            string impactHash,
            string actor,
            CancellationToken cancellationToken = default)
        {
            DeactivationWrites++;
            LastImpactHash = impactHash;
            if (RejectDeactivationAsStale)
            {
                throw new InvalidOperationException("MODEL_DEACTIVATION_STALE");
            }

            var scheme = Graph.Scheme with
            {
                ExplicitActiveNodeIds = Graph.Scheme.ExplicitActiveNodeIds
                    .Where(item => item != nodeId)
                    .ToArray(),
                ComputedActiveClosure = Graph.Scheme.ComputedActiveClosure
                    .Where(item => item != nodeId)
                    .ToArray(),
                SemanticRevision = Graph.Scheme.SemanticRevision + 1,
            };
            Graph = Graph with { Scheme = scheme, GraphHash = Hash('e') };
            return Task.FromResult(SchemeMutation(scheme));
        }

        public Task<GraphBatchMutationResponse> ApplyGraphBatchAsync(
            string schemeId,
            IReadOnlyList<string> copyNodeIds,
            IReadOnlyList<string> activateNodeIds,
            IReadOnlyList<NodeLayout> layoutUpdates,
            int expectedSemanticRevision,
            int expectedLayoutRevision,
            string actor,
            CancellationToken cancellationToken = default)
        {
            LastBatchCopyNodeIds = copyNodeIds.ToArray();
            var copies = copyNodeIds.Select(id => Copy(Graph.Nodes.Single(node => node.NodeId == id))).ToArray();
            var scheme = Graph.Scheme with
            {
                ExplicitActiveNodeIds = Graph.Scheme.ExplicitActiveNodeIds
                    .Concat(copies.Select(node => node.NodeId))
                    .Distinct(StringComparer.Ordinal)
                    .OrderBy(item => item, StringComparer.Ordinal)
                    .ToArray(),
                ComputedActiveClosure = Graph.Scheme.ComputedActiveClosure
                    .Concat(copies.SelectMany(Parents))
                    .Concat(copies.Select(node => node.NodeId))
                    .Distinct(StringComparer.Ordinal)
                    .OrderBy(item => item, StringComparer.Ordinal)
                    .ToArray(),
                SemanticRevision = Graph.Scheme.SemanticRevision + 1,
            };
            Graph = Graph with { Nodes = [.. Graph.Nodes, .. copies], Scheme = scheme };
            return Task.FromResult(Batch(copies, scheme));
        }

        public Task<GraphBatchMutationResponse> UpdateLayoutAsync(
            string schemeId,
            IReadOnlyList<NodeLayout> positions,
            int expectedSemanticRevision,
            int expectedLayoutRevision,
            string actor,
            CancellationToken cancellationToken = default)
        {
            LastLayoutPositions = positions.ToArray();
            LastLayoutSemanticRevision = expectedSemanticRevision;
            var scheme = Graph.Scheme with
            {
                LayoutOverrides = positions.ToArray(),
                LayoutRevision = Graph.Scheme.LayoutRevision + 1,
            };
            Graph = Graph with { Scheme = scheme };
            return Task.FromResult(Batch([], scheme));
        }

        public Task<CptMutationResponse> AddProbabilisticEdgeAsync(
            string childNodeId,
            string parentNodeId,
            string strategy,
            int expectedSemanticRevision,
            string actor,
            CancellationToken cancellationToken = default)
        {
            LastAddStrategy = strategy;
            return Task.FromResult(CptMutation(Graph.Nodes.Single(node => node.NodeId == childNodeId)));
        }

        public Task<CptMutationResponse> RemoveProbabilisticEdgeAsync(
            string childNodeId,
            string parentNodeId,
            string strategy,
            double[]? marginalWeights,
            int expectedSemanticRevision,
            string actor,
            CancellationToken cancellationToken = default)
        {
            LastRemoveStrategy = strategy;
            LastMarginalWeights = marginalWeights;
            return Task.FromResult(CptMutation(Graph.Nodes.Single(node => node.NodeId == childNodeId)));
        }

        public Task<ModelNodeMutationResponse> AddExtractionEdgeAsync(
            string childNodeId,
            string parentNodeId,
            string recipeInputBindingId,
            EvidenceRecipe updatedRecipe,
            int expectedSemanticRevision,
            string actor,
            CancellationToken cancellationToken = default)
        {
            LastExtractionBindingId = recipeInputBindingId;
            LastExtractionRecipe = updatedRecipe;
            return Task.FromResult(NodeMutation(Graph.Nodes.Single(node => node.NodeId == childNodeId)));
        }

        public Task<ModelNodeMutationResponse> RemoveExtractionEdgeAsync(
            string childNodeId,
            string recipeInputBindingId,
            EvidenceRecipe updatedRecipe,
            int expectedSemanticRevision,
            string actor,
            CancellationToken cancellationToken = default) =>
            Task.FromResult(NodeMutation(Graph.Nodes.Single(node => node.NodeId == childNodeId)));

        private TaskSchemeMutationResponse SchemeMutation(TaskScheme scheme) => new(
            scheme,
            Graph,
            scheme.SemanticRevision,
            scheme.LayoutRevision,
            scheme.TechnicalStatus,
            _diff,
            "tx.test",
            "audit.test",
            false,
            "trace.test");

        private GraphBatchMutationResponse Batch(ModelNode[] copies, TaskScheme scheme) => new(
            copies,
            scheme,
            Graph,
            _diff,
            "tx.test",
            "audit.test",
            false,
            "trace.test");

        private ModelNodeMutationResponse NodeMutation(ModelNode node) => new(
            node,
            [],
            node.SemanticRevision,
            node.LayoutRevision,
            node.TechnicalStatus,
            _diff,
            "tx.test",
            "audit.test",
            false,
            "trace.test");

        private CptMutationResponse CptMutation(ModelNode node)
        {
            var definition = (EvidenceNodeDefinition)node.Definition;
            return new CptMutationResponse(
                node,
                [],
                node.SemanticRevision,
                new CptEditorState(
                    definition.Cpt.ChildNode,
                    definition.Cpt.OrderedParentNodes,
                    definition.Cpt.ChildStateIds,
                    definition.Cpt.OrderedParentStateIds,
                    definition.Cpt.MaterializedProbabilities,
                    definition.Cpt.Mode,
                    0,
                    0),
                _diff,
                "tx.test",
                "audit.test",
                false,
                "trace.test");
        }

        private static ModelNode WithParent(ModelNode evidence, ModelNode parent)
        {
            var definition = (EvidenceNodeDefinition)evidence.Definition;
            var parentRef = new ModelNodeRef(parent.NodeId, ModelNodeKind.Bn);
            var parentStates = ((BnNodeDefinition)parent.Definition).OrderedStates
                .Select(state => state.StateId)
                .ToArray();
            return evidence with
            {
                Definition = definition with
                {
                    OrderedProbabilisticParentNodes = [parentRef],
                    Cpt = definition.Cpt with
                    {
                        OrderedParentNodes = [parentRef],
                        OrderedParentStateIds = [parentStates],
                    },
                },
            };
        }

        private static ModelNode Copy(ModelNode source)
        {
            var newId = $"model-node.evidence.copy{Guid.NewGuid():N}";
            var definition = (EvidenceNodeDefinition)source.Definition;
            return source with
            {
                NodeId = newId,
                CopiedFromNodeId = source.NodeId,
                GlobalLayout = new NodeLayout(newId, source.GlobalLayout.X + 40, source.GlobalLayout.Y + 40),
                Definition = definition with
                {
                    Cpt = definition.Cpt with
                    {
                        ChildNode = new ModelNodeRef(newId, ModelNodeKind.Evidence),
                    },
                },
            };
        }

        private static IEnumerable<string> Parents(ModelNode node) => node.Definition switch
        {
            EvidenceNodeDefinition evidence => evidence.OrderedProbabilisticParentNodes
                .Select(parent => parent.NodeId),
            BnNodeDefinition bn => bn.OrderedProbabilisticParentNodes.Select(parent => parent.NodeId),
            _ => [],
        };

        private static TaskScheme Scheme(
            string id,
            string[] explicitIds,
            string[] closure) => new(
                "task-scheme",
                "0.2.0",
                id,
                id,
                "Test task scheme.",
                [],
                "test",
                ModelObjectLifecycle.Active,
                null,
                explicitIds,
                closure,
                closure.Where(nodeId => nodeId.Contains("bn", StringComparison.Ordinal)).Take(1).ToArray(),
                new Dictionary<string, JsonElement>(StringComparer.Ordinal),
                [],
                4,
                2,
                ModelTechnicalStatus.Executable,
                [],
                Hash('1'),
                Hash('2'),
                Now,
                Now);

        private static ModelGraphSnapshot Snapshot(TaskScheme scheme, ModelNode[] nodes) => new(
            "model-graph-snapshot",
            "0.3.0",
            "project.test",
            scheme,
            nodes,
            [],
            Now,
            Hash('3'));

        private static string Hash(char value) => new(value, 64);
    }
}
