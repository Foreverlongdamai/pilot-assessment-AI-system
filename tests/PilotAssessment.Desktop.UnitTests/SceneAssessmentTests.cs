using System.IO.Pipes;
using System.Text.Json;
using System.Text.Json.Nodes;
using PilotAssessment.Desktop.Core.Protocol;
using PilotAssessment.Desktop.Core.SceneAssessment;

namespace PilotAssessment.Desktop.UnitTests;

public sealed class SceneAssessmentTests
{
    [Fact]
    public void TemplateContainsNullInputAndDoesNotInventBounds()
    {
        var workspace = new SceneWorkspace(CreateCatalog());
        Assert.Null(workspace.Input.Results!["terminal_hover_duration_s"]);
        var parameter = workspace.Configuration.Parameters["terminal_hover_duration_s"];
        Assert.Null(parameter.Expected);
        Assert.Null(parameter.Desired.Lower);
        Assert.Null(parameter.Desired.Upper);
        Assert.False(parameter.Desired.UnboundedUpper);
    }

    [Fact]
    public void CancelledEditorLeavesConfigurationAndReportUntouched()
    {
        var workspace = new SceneWorkspace(CreateCatalog());
        workspace.SetReport(CreateReport(workspace));
        var before = workspace.SaveConfigurationJson();
        var edit = workspace.BeginItemEdit("position");
        edit.Parameters["terminal_hover_duration_s"].Desired.Lower = 9;
        workspace.CancelItemEdit(edit);
        Assert.Equal(before, workspace.SaveConfigurationJson());
        Assert.NotNull(workspace.Report);
        Assert.Throws<InvalidOperationException>(() => workspace.CommitItemEdit(edit));
    }

    [Fact]
    public void CommittedSharedHoldParameterIsVisibleToBothItemsAndClearsReport()
    {
        var workspace = new SceneWorkspace(CreateCatalog());
        workspace.SetReport(CreateReport(workspace));
        var edit = workspace.BeginItemEdit("position");
        edit.Parameters["terminal_hover_duration_s"].Desired.Lower = 9;
        workspace.CommitItemEdit(edit);
        var other = workspace.BeginItemEdit("height");
        Assert.Equal(9, other.Parameters["terminal_hover_duration_s"].Desired.Lower);
        Assert.Single(workspace.Configuration.Parameters);
        Assert.Null(workspace.Report);
        Assert.Throws<InvalidOperationException>(() => workspace.ExportReportJson());
        edit.Parameters["terminal_hover_duration_s"].Desired.Lower = 100;
        Assert.Equal(9, workspace.Configuration.Parameters["terminal_hover_duration_s"].Desired.Lower);
    }

    [Fact]
    public void InputReloadInvalidatesPreviousReportAndPreservesBooleanAndNull()
    {
        var workspace = new SceneWorkspace(CreateCatalog());
        workspace.SetReport(CreateReport(workspace));
        workspace.LoadInputJson("""{"schema_version":"1.0","scene_id":"SCN-001","results":{"terminal_hover_duration_s":null,"stop_achieved":false}}""");
        Assert.Null(workspace.Report);
        Assert.Null(workspace.Input.Results!["terminal_hover_duration_s"]);
        Assert.False(workspace.Input.Results!["stop_achieved"]!.Value.GetBoolean());
        Assert.Contains("\"stop_achieved\": false", workspace.SaveInputJson());
    }

    [Fact]
    public void ReturnedSnapshotsCannotMutateWorkspaceOrExportedReport()
    {
        var workspace = new SceneWorkspace(CreateCatalog());
        var report = CreateReport(workspace);
        workspace.SetReport(report);
        var before = workspace.ExportReportJson();
        report.Configuration.Parameters["terminal_hover_duration_s"].Expected = 77;
        workspace.Configuration.Parameters.Clear();
        workspace.Input.Results!.Clear();
        workspace.Report!.Configuration.Parameters.Clear();
        Assert.Equal(before, workspace.ExportReportJson());
        Assert.Single(workspace.Configuration.Parameters);
        Assert.Equal(2, workspace.Input.Results!.Count);
    }

    [Fact]
    public void ReportFromBeforeAnEditCannotBeAcceptedAsCurrent()
    {
        var workspace = new SceneWorkspace(CreateCatalog());
        var report = CreateReport(workspace);
        var edit = workspace.BeginItemEdit("height");
        edit.Parameters["terminal_hover_duration_s"].Expected = 7;
        workspace.CommitItemEdit(edit);
        Assert.Throws<InvalidOperationException>(() => workspace.SetReport(report));
        Assert.Null(workspace.Report);
    }

    [Fact]
    public void ConfigurationRoundTripPreservesExplicitUnboundedUpperAndRejectsUnknownProperties()
    {
        var workspace = new SceneWorkspace(CreateCatalog());
        var edit = workspace.BeginItemEdit("height");
        edit.Parameters["terminal_hover_duration_s"].Desired.UnboundedUpper = true;
        workspace.CommitItemEdit(edit);
        var json = workspace.SaveConfigurationJson();
        var restored = new SceneWorkspace(CreateCatalog());
        restored.LoadConfigurationJson(json);
        Assert.Equal(json, restored.SaveConfigurationJson());
        Assert.Throws<JsonException>(() => restored.LoadConfigurationJson(json.Replace("unbounded_upper", "unbounded_uper")));
        Assert.Throws<JsonException>(() => restored.LoadInputJson("""{"schema_version":"1.0","scene_id":"other","results":{}}"""));
    }

    [Fact]
    public async Task GatewayUsesSceneMethodsAndSnakeCaseContracts()
    {
        var pipeName = $"scene-gateway-{Guid.NewGuid():N}";
        await using var server = new NamedPipeServerStream(pipeName, PipeDirection.InOut, 1, PipeTransmissionMode.Byte, PipeOptions.Asynchronous);
        await using var clientStream = new NamedPipeClientStream(".", pipeName, PipeDirection.InOut, PipeOptions.Asynchronous);
        await Task.WhenAll(server.WaitForConnectionAsync(), clientStream.ConnectAsync());
        await using var client = new JsonRpcClient(new JsonLineFramer(clientStream, clientStream));
        await using var serverFramer = new JsonLineFramer(server, server);
        await using var messages = serverFramer.ReadMessagesAsync().GetAsyncEnumerator();
        var gateway = new SceneGateway(client);

        var catalogTask = gateway.GetCatalogAsync();
        Assert.True(await messages.MoveNextAsync());
        Assert.Equal("scene.catalog", messages.Current.GetProperty("method").GetString());
        await ReplyAsync(JsonSerializer.SerializeToElement(CreateCatalog(), SceneJsonContext.Default.SceneCatalog));
        var catalog = await catalogTask;
        Assert.Equal("SCN-001", catalog.SceneId);

        var validationTask = gateway.ValidateConfigurationAsync(catalog.ConfigurationTemplate);
        Assert.True(await messages.MoveNextAsync());
        Assert.Equal("scene.validate_configuration", messages.Current.GetProperty("method").GetString());
        Assert.Equal("SCN-001", messages.Current.GetProperty("params").GetProperty("configuration").GetProperty("scene_id").GetString());
        await ReplyAsync(Parse("""{"valid":false,"issues":[{"path":"parameters.terminal_hover_duration_s","message":"缺少区间"}]}"""));
        Assert.False((await validationTask).Valid);

        var evaluationTask = gateway.EvaluateAsync(catalog.ConfigurationTemplate, catalog.InputTemplate);
        Assert.True(await messages.MoveNextAsync());
        Assert.Equal("scene.evaluate", messages.Current.GetProperty("method").GetString());
        Assert.Equal(JsonValueKind.Null, messages.Current.GetProperty("params").GetProperty("input").GetProperty("results").GetProperty("stop_achieved").ValueKind);
        await ReplyAsync(JsonSerializer.SerializeToElement(CreateReport(new SceneWorkspace(catalog)), SceneJsonContext.Default.SceneReport));
        Assert.Equal("needs_input", (await evaluationTask).CalculationStatus);

        async ValueTask ReplyAsync(JsonElement result)
        {
            var response = Parse($$"""{"jsonrpc":"2.0","id":{{messages.Current.GetProperty("id").GetRawText()}},"result":{{result.GetRawText()}}}""");
            await serverFramer.WriteAsync(response);
        }
    }

    [Theory]
    [InlineData("desired")]
    [InlineData("acceptable")]
    [InlineData("unbounded_upper")]
    public void ImportCannotSilentlySupplyMissingIntervalFields(string field)
    {
        var workspace = new SceneWorkspace(CreateCatalog());
        var root = JsonNode.Parse(workspace.SaveConfigurationJson())!;
        var parameter = root["parameters"]!["terminal_hover_duration_s"]!.AsObject();
        if (field == "unbounded_upper")
        {
            parameter["desired"]!.AsObject().Remove(field);
        }
        else
        {
            parameter.Remove(field);
        }

        Assert.Throws<JsonException>(() => workspace.LoadConfigurationJson(root.ToJsonString()));
    }

    [Fact]
    public void CatalogPreservesOptionalMissingEvidenceConditionWithoutCreatingFailureRule()
    {
        var root = JsonSerializer.SerializeToNode(CreateCatalog(), SceneJsonContext.Default.SceneCatalog)!;
        var checkpoint = root["items"]![0]!["checkpoints"]![0]!.AsObject();
        checkpoint["not_required_when"] = JsonNode.Parse("""[{"metric_id":"terminal_hover_duration_s","equals":0}]""");
        var catalog = JsonSerializer.Deserialize(root.ToJsonString(), SceneJsonContext.Default.SceneCatalog)!;
        var restored = JsonSerializer.SerializeToNode(catalog, SceneJsonContext.Default.SceneCatalog)!;
        Assert.True(JsonNode.DeepEquals(checkpoint["not_required_when"], restored["items"]![0]!["checkpoints"]![0]!["not_required_when"]));
        Assert.Empty(catalog.Items[0].Checkpoints[0].FailWhen);
    }

    private static SceneCatalog CreateCatalog() => new()
    {
        SchemaVersion = "1.0", SceneId = "SCN-001", Name = "加速减速任务",
        Metrics = [new() { MetricId = "terminal_hover_duration_s", Rule = "interval", ParameterKind = "hold", Shared = true }, new() { MetricId = "stop_achieved", Rule = "must_be_true", ParameterKind = "fact" }],
        Items = [Item("position"), Item("height")],
        ConfigurationTemplate = new() { SchemaVersion = "1.0", SceneId = "SCN-001", Parameters = new() { ["terminal_hover_duration_s"] = new() } },
        InputTemplate = new() { SchemaVersion = "1.0", SceneId = "SCN-001", Results = new() { ["terminal_hover_duration_s"] = null, ["stop_achieved"] = null } },
    };

    private static SceneItem Item(string id) => new() { ItemId = id, Checkpoints = [new() { CheckpointId = "hold", MetricIds = ["terminal_hover_duration_s"] }] };

    private static SceneReport CreateReport(SceneWorkspace workspace) => new()
    {
        SchemaVersion = "1.0", SceneId = "SCN-001", EvaluatedAt = "2026-09-07T12:00:00Z", CalculationStatus = "needs_input",
        Configuration = workspace.Configuration, Input = workspace.Input,
    };

    private static JsonElement Parse(string json) => JsonDocument.Parse(json).RootElement.Clone();
}
