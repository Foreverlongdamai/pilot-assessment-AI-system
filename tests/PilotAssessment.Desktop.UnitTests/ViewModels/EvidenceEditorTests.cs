using System.Text.Json;
using System.Text.Json.Nodes;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;
using PilotAssessment.Desktop.Core.ViewModels;

namespace PilotAssessment.Desktop.UnitTests.ViewModels;

public sealed class EvidenceEditorTests
{
    [Fact]
    public void SchemaFormUsesUiHintsAndPreservesUnknownParameters()
    {
        var definition = ThresholdOperator();
        var parameters = new Dictionary<string, JsonNode?>(StringComparer.Ordinal)
        {
            ["threshold"] = JsonValue.Create(2.5),
            ["direction"] = JsonValue.Create("rising"),
            ["enabled"] = JsonValue.Create(true),
            ["labels"] = JsonNode.Parse("[\"primary\"]"),
            ["advanced"] = JsonNode.Parse("{\"scale\":2}"),
            ["legacy_value"] = JsonValue.Create("keep-me"),
        };

        var form = JsonSchemaFormModel.Create(definition, parameters);

        Assert.Equal(JsonSchemaFieldKind.Number, Field(form, "/threshold").Kind);
        Assert.Equal("Threshold", Field(form, "/threshold").Label);
        Assert.Equal("m", Field(form, "/threshold").Unit);
        Assert.Equal(JsonSchemaFieldKind.Enum, Field(form, "/direction").Kind);
        Assert.Equal(JsonSchemaFieldKind.Boolean, Field(form, "/enabled").Kind);
        Assert.Equal(JsonSchemaFieldKind.Array, Field(form, "/labels").Kind);
        Assert.Equal(JsonSchemaFieldKind.Object, Field(form, "/advanced").Kind);
        Assert.True(Field(form, "/legacy_value").IsReadOnly);
        Assert.Equal(
            "keep-me",
            form.BuildParameters()["legacy_value"]!.GetValue<string>());
    }

    [Fact]
    public void SchemaFormAppliesTypedValuesWithoutDroppingUnsupportedJson()
    {
        var form = JsonSchemaFormModel.Create(
            ThresholdOperator(),
            new Dictionary<string, JsonNode?>(StringComparer.Ordinal)
            {
                ["threshold"] = JsonValue.Create(2.5),
                ["direction"] = JsonValue.Create("rising"),
                ["enabled"] = JsonValue.Create(true),
                ["labels"] = new JsonArray(),
                ["advanced"] = new JsonObject(),
                ["legacy_value"] = JsonValue.Create(77),
            });

        Assert.True(form.TrySetValue("/threshold", "4.75", out var numberError), numberError);
        Assert.True(form.TrySetValue("/direction", "falling", out var enumError), enumError);
        Assert.True(form.TrySetValue("/labels", "[\"a\",\"b\"]", out var arrayError), arrayError);
        Assert.True(form.TrySetValue("/advanced", "{\"scale\":3}", out var objectError), objectError);
        Assert.False(form.TrySetValue("/legacy_value", "99", out var preservedError));

        var result = form.BuildParameters();
        Assert.Equal(4.75, result["threshold"]!.GetValue<double>());
        Assert.Equal("falling", result["direction"]!.GetValue<string>());
        Assert.Equal(2, result["labels"]!.AsArray().Count);
        Assert.Equal(3, result["advanced"]!["scale"]!.GetValue<int>());
        Assert.Equal(77, result["legacy_value"]!.GetValue<int>());
        Assert.Contains("read-only", preservedError, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void RecipeEditorUsesExactOperatorPortsAndMapsCompleteRecipe()
    {
        var threshold = ThresholdOperator();
        var sink = SinkOperator();
        var recipe = BlankEvidence().Recipe with
        {
            Graph = new RecipeGraph(
                [
                    new RecipeNode(
                        "operator.1",
                        threshold.OperatorId,
                        threshold.ImplementationVersion,
                        null,
                        Parameters()),
                    new RecipeNode("operator.missing", "missing.operator", "9.0.0", null, Parameters()),
                ],
                []),
        };
        var editor = new EvidenceRecipeEditorModel(recipe, [threshold, sink]);

        var missing = Assert.Single(editor.MissingOperators);
        Assert.Equal("operator.missing", missing.RecipeNodeId);
        var added = editor.AddOperator(sink.OperatorId, sink.ImplementationVersion);
        var edge = editor.Connect("operator.1", "events", added.NodeId, "events");
        var form = editor.CreateParameterForm("operator.1");
        Assert.True(form.TrySetValue("/threshold", "8.5", out var error), error);
        editor.ApplyParameters("operator.1", form);

        Assert.Contains(editor.Recipe.Graph.Nodes, node => node.NodeId == added.NodeId);
        Assert.Equal("events", edge.Source.PortId);
        Assert.Equal("events", edge.Target.PortId);
        Assert.Equal(
            8.5,
            editor.Recipe.Graph.Nodes.Single(node => node.NodeId == "operator.1")
                .Parameters["threshold"]!.GetValue<double>());
        Assert.Contains(editor.Recipe.Graph.Nodes, node => node.OperatorId == "missing.operator");
    }

    [Fact]
    public async Task UpdateRequestKeepsCompleteEvidenceDefinitionAndExactRevisions()
    {
        var original = ModelNodeDraftFactory.Create(new ModelNodeDraftRequest(
            ModelNodeKind.Evidence,
            "Original",
            null,
            RawModality.X,
            120,
            140)) with
        {
            SemanticRevision = 7,
            LayoutRevision = 3,
        };
        var definition = Assert.IsType<EvidenceNodeDefinition>(original.Definition);
        var editor = new EvidenceRecipeEditorModel(definition.Recipe, [ThresholdOperator()]);
        editor.AddOperator("event.threshold", "1.0.0");
        var updated = editor.BuildUpdatedNode(
            original,
            "证据",
            "Edited Evidence",
            "中文说明",
            "English description",
            "attention",
            ["gaze", "expert"]);
        var gateway = new FakeEditorGateway();
        using var coordinator = new EvidenceEditorCoordinator(gateway);

        await coordinator.UpdateAsync(updated, "expert.local", "tx.evidence.test");

        Assert.Same(updated, gateway.UpdatedNode);
        Assert.Equal(7, gateway.ExpectedSemanticRevision);
        Assert.Equal(3, gateway.ExpectedLayoutRevision);
        var mapped = Assert.IsType<EvidenceNodeDefinition>(gateway.UpdatedNode!.Definition);
        Assert.Same(definition.Cpt, mapped.Cpt);
        Assert.Single(mapped.Recipe.Graph.Nodes);
        Assert.Equal("Edited Evidence", gateway.UpdatedNode.NameEn);
    }

    [Fact]
    public async Task PreviewCancellationStopsOnlyTheInFlightPreview()
    {
        var gateway = new FakeEditorGateway { WaitForPreviewCancellation = true };
        using var coordinator = new EvidenceEditorCoordinator(gateway);
        var preview = coordinator.PreviewAsync(
            "session-revision.test",
            "task-scheme.test",
            "evidence.test");
        await gateway.PreviewStarted.Task.WaitAsync(TimeSpan.FromSeconds(1));

        coordinator.CancelPreview();

        Assert.Null(await preview.WaitAsync(TimeSpan.FromSeconds(1)));
        Assert.True(gateway.PreviewWasCancelled);
    }

    private static JsonSchemaFormField Field(JsonSchemaFormModel form, string path) =>
        form.Fields.Single(field => field.Path == path);

    private static EvidenceNodeDefinition BlankEvidence()
    {
        var node = ModelNodeDraftFactory.Create(new ModelNodeDraftRequest(
            ModelNodeKind.Evidence,
            "Evidence",
            null,
            RawModality.X,
            100,
            100));
        return Assert.IsType<EvidenceNodeDefinition>(node.Definition);
    }

    private static IReadOnlyDictionary<string, JsonNode?> Parameters() =>
        new Dictionary<string, JsonNode?>(StringComparer.Ordinal)
        {
            ["threshold"] = JsonValue.Create(1.0),
            ["direction"] = JsonValue.Create("rising"),
            ["enabled"] = JsonValue.Create(true),
            ["labels"] = new JsonArray(),
            ["advanced"] = new JsonObject(),
        };

    private static OperatorDefinition ThresholdOperator() => new(
        "operator-definition",
        "0.1.0",
        "event.threshold",
        "1.0.0",
        OperatorFamily.Event,
        "Threshold",
        "Find threshold crossing events.",
        null,
        [],
        [Port("events", "event_collection", TemporalSemantics.Point)],
        JsonObject("""
        {
          "type": "object",
          "properties": {
            "threshold": {"type": "number", "minimum": 0},
            "direction": {"type": "string", "enum": ["rising", "falling"]},
            "enabled": {"type": "boolean"},
            "labels": {"type": "array", "items": {"type": "string"}},
            "advanced": {"type": "object"}
          },
          "required": ["threshold", "direction"],
          "additionalProperties": false
        }
        """),
        [
            new ParameterUiDefinition(
                "/threshold",
                "Threshold",
                "detection",
                ParameterControlKind.Number,
                "Crossing threshold.",
                "m"),
            new ParameterUiDefinition(
                "/direction",
                "Direction",
                "detection",
                ParameterControlKind.Select,
                "Crossing direction.",
                null),
        ],
        TraceCapability.Summary,
        OperatorImplementationSource.BuiltIn,
        "builtin.event.threshold");

    private static OperatorDefinition SinkOperator() => new(
        "operator-definition",
        "0.1.0",
        "statistics.count",
        "1.0.0",
        OperatorFamily.Statistics,
        "Count",
        "Count events.",
        null,
        [Port("events", "event_collection", TemporalSemantics.Point)],
        [Port("value", "number", TemporalSemantics.Timeless)],
        JsonObject("{\"type\":\"object\",\"properties\":{},\"additionalProperties\":false}"),
        [],
        TraceCapability.Summary,
        OperatorImplementationSource.BuiltIn,
        "builtin.statistics.count");

    private static OperatorPortDefinition Port(
        string id,
        string valueType,
        TemporalSemantics temporal) => new(
        id,
        id,
        id,
        new PortType(valueType, PortCardinality.One, temporal, null));

    private static IReadOnlyDictionary<string, JsonElement> JsonObject(string json) =>
        JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(json)
        ?? throw new InvalidOperationException("The JSON object fixture was empty.");

    private sealed class FakeEditorGateway : IModelNodeEditorGateway
    {
        public ModelNode? UpdatedNode { get; private set; }
        public int ExpectedSemanticRevision { get; private set; }
        public int ExpectedLayoutRevision { get; private set; }
        public bool WaitForPreviewCancellation { get; init; }
        public TaskCompletionSource PreviewStarted { get; } = new(
            TaskCreationOptions.RunContinuationsAsynchronously);
        public bool PreviewWasCancelled { get; private set; }

        public Task<IReadOnlyList<OperatorDefinition>> ListOperatorsAsync(
            CancellationToken cancellationToken = default) =>
            Task.FromResult<IReadOnlyList<OperatorDefinition>>([ThresholdOperator()]);

        public Task<ModelNodeMutationResponse> UpdateNodeAsync(
            ModelNode node,
            int expectedSemanticRevision,
            int expectedLayoutRevision,
            string actor,
            string transactionId,
            CancellationToken cancellationToken = default)
        {
            UpdatedNode = node;
            ExpectedSemanticRevision = expectedSemanticRevision;
            ExpectedLayoutRevision = expectedLayoutRevision;
            return Task.FromResult(new ModelNodeMutationResponse(
                node,
                [],
                expectedSemanticRevision + 1,
                expectedLayoutRevision,
                node.TechnicalStatus,
                new CanonicalModelDiff(
                    [], [], [], [], [],
                    new Dictionary<string, JsonElement>(StringComparer.Ordinal)),
                transactionId,
                "audit.test",
                false,
                "trace.test"));
        }

        public Task<IReadOnlyList<ModelNodeUsage>> ListNodeUsagesAsync(
            string nodeId,
            CancellationToken cancellationToken = default) =>
            Task.FromResult<IReadOnlyList<ModelNodeUsage>>([]);

        public Task<IReadOnlyList<ModelChangeEvent>> ListNodeHistoryAsync(
            string nodeId,
            CancellationToken cancellationToken = default) =>
            Task.FromResult<IReadOnlyList<ModelChangeEvent>>([]);

        public async Task<CurrentModelRunSnapshot> PreviewNodeAsync(
            string sessionRevisionId,
            string schemeId,
            string nodeId,
            IReadOnlyDictionary<string, JsonElement> runtimeParameters,
            CancellationToken cancellationToken = default)
        {
            PreviewStarted.TrySetResult();
            if (WaitForPreviewCancellation)
            {
                try
                {
                    await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken);
                }
                catch (OperationCanceledException)
                {
                    PreviewWasCancelled = true;
                    throw;
                }
            }
            throw new InvalidOperationException("This fixture only exercises cancellation.");
        }
    }
}
