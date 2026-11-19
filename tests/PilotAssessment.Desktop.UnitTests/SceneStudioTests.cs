using System.IO.Pipes;
using System.Text.Json;
using PilotAssessment.Desktop.Core.Protocol;
using PilotAssessment.Desktop.Core.SceneAssessment;

namespace PilotAssessment.Desktop.UnitTests;

public sealed class SceneStudioTests
{
    [Fact]
    public void TwoScenesWithRepeatedItemIdsHaveUniqueNodesAndLocalEdges()
    {
        var graph = SceneGraphProjection.Build([new(Catalog("SCN-001")), new(Catalog("SCN-002"))]);

        Assert.Equal(12, graph.Nodes.Count);
        Assert.Equal(graph.Nodes.Count, graph.Nodes.Select(node => node.Id).Distinct().Count());
        var nodes = graph.Nodes.ToDictionary(node => node.Id);
        foreach (var edge in graph.Edges)
        {
            Assert.Equal(nodes[edge.FromId].SceneId, nodes[edge.ToId].SceneId);
            Assert.Equal(edge.Kind == "membership" ? "task" : "item", nodes[edge.FromId].Kind);
            Assert.Equal(edge.Kind == "membership" ? "item" : "checkpoint", nodes[edge.ToId].Kind);
        }

        Assert.Equal(4, graph.Edges.Count(edge => edge.Kind == "membership"));
        Assert.Equal(6, graph.Edges.Count(edge => edge.Kind == "bayesian"));
        foreach (var checkpoint in graph.Nodes.Where(node => node.Kind == "checkpoint"))
        {
            Assert.Single(graph.Edges, edge => edge.ToId == checkpoint.Id && edge.Kind == "bayesian");
        }

        Assert.True(graph.Nodes.Where(node => node.SceneId == "SCN-001").Max(node => node.Y + node.Height)
            < graph.Nodes.Where(node => node.SceneId == "SCN-002").Min(node => node.Y));
        Assert.All(graph.Nodes, node => Assert.True(node.X >= 0 && node.Y >= 0
            && node.X + node.Width <= graph.Width && node.Y + node.Height <= graph.Height));
    }

    [Fact]
    public void NoReportDoesNotInventGradesOrScoresAndEmptyStudioIsValid()
    {
        var empty = SceneGraphProjection.Build([]);
        Assert.Empty(empty.Nodes);
        Assert.Empty(empty.Edges);
        var graph = SceneGraphProjection.Build([new(Catalog("SCN-001"))]);
        Assert.All(graph.Nodes, node => { Assert.Null(node.Grade); Assert.Null(node.Score); });
    }

    [Fact]
    public void ProjectionCopiesEvidenceButNeverCreatesTaskOrCheckpointScore()
    {
        var workspace = new SceneWorkspace(Catalog("SCN-001"));
        workspace.SetReport(Report(workspace));
        var graph = SceneGraphProjection.Build([workspace]);
        var task = Assert.Single(graph.Nodes, node => node.Kind == "task");
        Assert.Equal("U", task.Grade);
        Assert.Null(task.Score);
        var item = Assert.Single(graph.Nodes, node => node.ItemId == "item" && node.Kind == "item");
        Assert.Equal("U", item.Grade);
        Assert.Equal(77, item.Score);
        var checkpoint = Assert.Single(graph.Nodes, node => node.CheckpointId == "cp1");
        Assert.Equal("U", checkpoint.Grade);
        Assert.Null(checkpoint.Score);

        var edit = workspace.BeginItemEdit("item");
        edit.SkillModel!.Prior = [.2, .3, .5];
        workspace.CommitItemEdit(edit);
        Assert.Null(workspace.Report);
        Assert.Equal(77, item.Score);
        Assert.All(SceneGraphProjection.Build([workspace]).Nodes, node => Assert.Null(node.Score));
    }

    [Fact]
    public void ReturningToSceneRetainsFilesInputReportAndCancelledEdits()
    {
        var studio = new SceneStudioState();
        var first = studio.AddCatalog(Catalog("SCN-001"));
        first.ConfigurationPath = "first.config.json";
        first.InputPath = "first.input.json";
        first.IsDirty = true;
        first.Workspace.LoadInputJson("""{"schema_version":"1.0","scene_id":"SCN-001","results":{"metric":4}}""");
        first.Workspace.SetReport(Report(first.Workspace));
        var before = first.Workspace.SaveConfigurationJson();
        var edit = first.Workspace.BeginItemEdit("item");
        edit.SkillModel!.Prior = [.2, .3, .5];
        studio.AddCatalog(Catalog("SCN-002"));
        first.Workspace.CancelItemEdit(edit);

        var returned = studio.GetDocument("SCN-001");
        Assert.Same(first, returned);
        Assert.Equal("first.config.json", returned.ConfigurationPath);
        Assert.Equal("first.input.json", returned.InputPath);
        Assert.True(returned.IsDirty);
        Assert.Equal(4, returned.Workspace.Input.Results!["metric"]!.Value.GetDouble());
        Assert.NotNull(returned.Workspace.Report);
        Assert.Equal(before, returned.Workspace.SaveConfigurationJson());
    }

    [Fact]
    public void CommittingOneSceneCannotMutateOtherSceneOrAcceptItsEditor()
    {
        var studio = new SceneStudioState();
        var first = studio.AddCatalog(Catalog("SCN-001"));
        var second = studio.AddCatalog(Catalog("SCN-002"));
        first.Workspace.SetReport(Report(first.Workspace));
        second.Workspace.SetReport(Report(second.Workspace));
        var before = second.Workspace.SaveConfigurationJson();
        var edit = first.Workspace.BeginItemEdit("item");
        edit.SkillModel!.Prior = [.2, .3, .5];

        Assert.Throws<InvalidOperationException>(() => second.Workspace.CommitItemEdit(edit));
        first.Workspace.CommitItemEdit(edit);
        first.IsDirty = true;
        Assert.Equal(.2, studio.GetDocument("SCN-001").Workspace.Configuration.SkillModels!["item"].Prior[0]);
        Assert.Null(first.Workspace.Report);
        Assert.Equal(before, second.Workspace.SaveConfigurationJson());
        Assert.NotNull(second.Workspace.Report);
        Assert.False(second.IsDirty);
    }

    [Fact]
    public void DuplicateCatalogCannotResetExistingUnsavedScene()
    {
        var studio = new SceneStudioState();
        var document = studio.AddCatalog(Catalog("SCN-001"));
        document.IsDirty = true;
        Assert.Throws<ArgumentException>(() => studio.AddCatalog(Catalog("SCN-001")));
        Assert.Single(studio.Documents);
        Assert.Same(document, studio.GetDocument("SCN-001"));
        Assert.True(document.IsDirty);
        Assert.Throws<KeyNotFoundException>(() => studio.GetDocument("unknown"));
    }

    [Fact]
    public void EncodedGraphIdentitiesDoNotCollideWhenIdsContainSeparators()
    {
        var first = Catalog("scene/item");
        var second = Catalog("scene%2Fitem");
        var graph = SceneGraphProjection.Build([new(first), new(second)]);
        Assert.Equal(graph.Nodes.Count, graph.Nodes.Select(node => node.Id).Distinct().Count());
    }

    [Fact]
    public async Task GatewayDiscoversScenesAndRequestsSelectedCatalogWithSnakeCaseId()
    {
        var pipeName = $"studio-gateway-{Guid.NewGuid():N}";
        await using var server = new NamedPipeServerStream(pipeName, PipeDirection.InOut, 1, PipeTransmissionMode.Byte, PipeOptions.Asynchronous);
        await using var clientStream = new NamedPipeClientStream(".", pipeName, PipeDirection.InOut, PipeOptions.Asynchronous);
        await Task.WhenAll(server.WaitForConnectionAsync(), clientStream.ConnectAsync());
        await using var client = new JsonRpcClient(new JsonLineFramer(clientStream, clientStream));
        await using var serverFramer = new JsonLineFramer(server, server);
        await using var messages = serverFramer.ReadMessagesAsync().GetAsyncEnumerator();
        var gateway = new SceneGateway(client);

        var listTask = gateway.GetSceneListAsync();
        Assert.True(await messages.MoveNextAsync());
        Assert.Equal("scene.list", messages.Current.GetProperty("method").GetString());
        await ReplyAsync("""{"schema_version":"1.0","trace_id":"trace","scenes":[{"scene_id":"SCN-002","name":"第二场景","description":"待设计"}]}""");
        var registry = await listTask;
        Assert.Equal("trace", registry.TraceId);
        Assert.Equal("SCN-002", Assert.Single(registry.Scenes).SceneId);

        var catalogTask = gateway.GetCatalogAsync("SCN-002");
        Assert.True(await messages.MoveNextAsync());
        Assert.Equal("scene.catalog", messages.Current.GetProperty("method").GetString());
        Assert.Equal("SCN-002", messages.Current.GetProperty("params").GetProperty("scene_id").GetString());
        await ReplyAsync(JsonSerializer.Serialize(Catalog("SCN-002"), SceneJsonContext.Default.SceneCatalog));
        Assert.Equal("SCN-002", (await catalogTask).SceneId);

        var legacyTask = gateway.GetCatalogAsync("SCN-002", "1.0");
        Assert.True(await messages.MoveNextAsync());
        Assert.Equal("1.0", messages.Current.GetProperty("params").GetProperty("schema_version").GetString());
        await ReplyAsync(JsonSerializer.Serialize(Catalog("SCN-002"), SceneJsonContext.Default.SceneCatalog));
        Assert.Equal("1.0", (await legacyTask).SchemaVersion);

        async ValueTask ReplyAsync(string result)
        {
            using var response = JsonDocument.Parse($$"""{"jsonrpc":"2.0","id":{{messages.Current.GetProperty("id").GetRawText()}},"result":{{result}}}""");
            await serverFramer.WriteAsync(response.RootElement);
        }
    }

    private static SceneCatalog Catalog(string sceneId) => new()
    {
        SchemaVersion = "1.0", SceneId = sceneId, Name = "测试场景", Description = "只用于状态和投影测试",
        Metrics = [new() { MetricId = "metric", Rule = "interval" }],
        Items = [new() { ItemId = "item", Name = "起飞", SkillName = "起飞表现",
            Checkpoints = [new() { CheckpointId = "cp1", Name = "检查一", MetricIds = ["metric"] },
                new() { CheckpointId = "cp2", Name = "检查二", MetricIds = ["metric"] }] },
            new() { ItemId = "other", Name = "悬停", Checkpoints = [new() { CheckpointId = "cp3", Name = "检查三", MetricIds = ["metric"] }] }],
        ConfigurationTemplate = new() { SchemaVersion = "1.0", SceneId = sceneId, Parameters = new() { ["metric"] = new() },
            SkillModels = new() { ["item"] = new() { ModelVersion = "test", Calibration = "uncalibrated", ParameterSource = "demonstration",
                Prior = [1d / 3, 1d / 3, 1d / 3], StateScores = [0, 50, 100], CheckpointModels = new()
                {
                    ["cp1"] = new() { States = ["D", "A", "U"], Probabilities = [[.1, .25, .65], [.25, .5, .25], [.65, .25, .1]] },
                    ["cp2"] = new() { States = ["D", "A", "U"], Probabilities = [[.1, .25, .65], [.25, .5, .25], [.65, .25, .1]] },
                } } } },
        InputTemplate = new() { SchemaVersion = "1.0", SceneId = sceneId, Results = new() { ["metric"] = null } },
    };

    private static SceneReport Report(SceneWorkspace workspace) => new()
    {
        SchemaVersion = "1.0", SceneId = workspace.Catalog.SceneId, Grade = "U", Passed = false,
        Configuration = workspace.Configuration, Input = workspace.Input,
        Items = [new() { ItemId = "item", Grade = "U", Passed = false,
            SkillQuantification = new() { Status = "complete", Method = SceneSkillModel.CompensationInferenceMethod, Score = 77 },
            Checkpoints = [new() { CheckpointId = "cp1", Grade = "U" }, new() { CheckpointId = "cp2", Grade = "D" }] }],
    };
}
