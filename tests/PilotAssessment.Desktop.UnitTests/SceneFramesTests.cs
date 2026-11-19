using System.Text.Json;
using System.Text.Json.Nodes;
using PilotAssessment.Desktop.Core.SceneAssessment;

namespace PilotAssessment.Desktop.UnitTests;

public sealed class SceneFramesTests
{
    [Fact]
    public void ItemFrames_RoundTripPreservesExactTimesRawCoordinatesControlsAndNulls()
    {
        var workspace = new SceneWorkspace(Catalog());
        workspace.LoadInputJson(InputJson);
        Assert.True(JsonNode.DeepEquals(JsonNode.Parse(InputJson), JsonNode.Parse(workspace.SaveInputJson())));
        var exported = JsonNode.Parse(workspace.SaveInputJson())!;
        Assert.False(exported["items"]!["flight"]!.AsObject().ContainsKey("checkpoints"));
        Assert.Equal(12.000000123, exported["items"]!["flight"]!["frames"]![0]!["timestamp_s"]!.GetValue<double>());
    }

    [Fact]
    public void RadialDraftAndIndependentScenes_EditWithoutLosingBlankGeometryOrAnotherScene()
    {
        var studio = new SceneStudioState();
        var first = studio.AddCatalog(Catalog("SCN-001")).Workspace;
        var second = studio.AddCatalog(Catalog()).Workspace;
        var untouched = first.SaveConfigurationJson();
        var edit = second.BeginItemEdit("flight");
        edit.Parameters["height"].Expected = 20;
        second.CommitItemEdit(edit);
        Assert.Equal(untouched, first.SaveConfigurationJson());
        var saved = JsonNode.Parse(second.SaveConfigurationJson())!;
        Assert.Equal(20d, saved["parameters"]!["height"]!["expected"]!.GetValue<double>());
        Assert.Null(saved["parameters"]!["laser"]!["center_u"]);
        Assert.Null(saved["parameters"]!["laser"]!["target_radius"]);
        Assert.Equal(2, SceneGraphProjection.Build(studio.Documents.Select(document => document.Workspace)).Nodes.Count(node => node.Kind == "task"));
    }

    [Fact]
    public void BlankFrameTime_RemainsNullButMissingTimestampFieldIsRejected()
    {
        var catalog = Catalog();
        catalog.InputTemplate.Items!["flight"].Frames =
            [new() { TimestampS = null, PhaseId = "hold", Values = new() { ["height"] = null, ["laser"] = null } }];
        var workspace = new SceneWorkspace(catalog);
        workspace.LoadInputJson(workspace.ExportInputTemplateJson());
        var input = JsonNode.Parse(workspace.SaveInputJson())!;
        var frame = input["items"]!["flight"]!["frames"]![0]!.AsObject();
        Assert.True(frame.ContainsKey("timestamp_s"));
        Assert.Null(frame["timestamp_s"]);
        frame.Remove("timestamp_s");
        Assert.Throws<JsonException>(() => workspace.LoadInputJson(input.ToJsonString()));
        Assert.Null(workspace.Input.Items!["flight"].Frames![0].TimestampS);
    }

    [Theory]
    [InlineData("unknown")]
    [InlineData("earlier")]
    [InlineData("repeat-single")]
    public void PhaseMismatch_RejectsWithoutLosingCurrentDraft(string mismatch)
    {
        var catalog = Catalog();
        catalog.Items[0].Phases!.Add(new() { PhaseId = "later", Name = "下一段", SingleFrame = true });
        var workspace = new SceneWorkspace(catalog);
        var before = workspace.SaveInputJson();
        var input = JsonNode.Parse(InputJson)!;
        var frames = input["items"]!["flight"]!["frames"]!;
        frames[0]!["phase_id"] = mismatch == "unknown" ? "unknown" : "later";
        if (mismatch == "repeat-single")
        {
            frames[1]!["phase_id"] = "later";
        }
        Assert.Throws<JsonException>(() => workspace.LoadInputJson(input.ToJsonString()));
        Assert.Equal(before, workspace.SaveInputJson());
    }

    [Fact]
    public void VersionTwo_RejectsEvenNullFramesField()
    {
        var catalog = Catalog();
        catalog.SchemaVersion = catalog.ConfigurationTemplate.SchemaVersion = catalog.InputTemplate.SchemaVersion = "2.0";
        var workspace = new SceneWorkspace(catalog);
        Assert.Throws<JsonException>(() => workspace.LoadInputJson("""
        {"schema_version":"2.0","scene_id":"SCN-002","items":{"flight":{"checkpoints":{},"frames":null}}}
        """));
    }

    [Fact]
    public void RadialParameters_SaveAndRestoreExplicitGeometryWithoutFillingBlankThresholds()
    {
        var workspace = new SceneWorkspace(Catalog());
        var edit = workspace.BeginItemEdit("flight");
        edit.Parameters["laser"].CenterU = 4.25;
        edit.Parameters["laser"].CenterV = -2.125;
        edit.Parameters["laser"].TargetRadius = 2;
        workspace.CommitItemEdit(edit);
        var restored = new SceneWorkspace(Catalog());
        restored.LoadConfigurationJson(workspace.SaveConfigurationJson());
        Assert.Equal(4.25, restored.Configuration.Parameters["laser"].CenterU);
        Assert.Equal(-2.125, restored.Configuration.Parameters["laser"].CenterV);
        Assert.Equal(2, restored.Configuration.Parameters["laser"].TargetRadius);
        Assert.Null(restored.Configuration.Parameters["laser"].Desired.Upper);
        Assert.Null(restored.Configuration.Parameters["laser"].Acceptable.Upper);
    }

    [Theory]
    [InlineData("12.000000123")]
    [InlineData("11")]
    [InlineData("1e400")]
    [InlineData("-0.5")]
    public void InvalidFrameTimes_RejectWithoutReplacingCurrentInput(string replacement)
    {
        var workspace = new SceneWorkspace(Catalog());
        workspace.LoadInputJson(InputJson);
        var before = workspace.SaveInputJson();
        var invalid = JsonNode.Parse(InputJson)!;
        invalid["items"]!["flight"]!["frames"]![1]!["timestamp_s"] = JsonNode.Parse(replacement);
        Assert.Throws<JsonException>(() => workspace.LoadInputJson(invalid.ToJsonString()));
        Assert.Equal(before, workspace.SaveInputJson());
    }

    [Theory]
    [InlineData("checkpoints", "{}")]
    [InlineData("samples", "[]")]
    public void VersionThree_RejectsLegacyItemShapeEvenWhenFramesArePresent(string key, string value)
    {
        var workspace = new SceneWorkspace(Catalog());
        var input = JsonNode.Parse(InputJson)!;
        input["items"]!["flight"]![key] = JsonNode.Parse(value);
        Assert.Throws<JsonException>(() => workspace.LoadInputJson(input.ToJsonString()));
    }

    [Fact]
    public void RemovedItem_ImportExplainsCurrentTemplateAndPreservesInput()
    {
        var workspace = new SceneWorkspace(Catalog());
        workspace.LoadInputJson(InputJson);
        var before = workspace.SaveInputJson();
        var input = JsonNode.Parse(InputJson)!;
        input["items"]!["removed-item"] = new JsonObject { ["frames"] = new JsonArray() };

        var error = Assert.Throws<JsonException>(() => workspace.LoadInputJson(input.ToJsonString()));

        Assert.Contains("removed-item", error.Message);
        Assert.Contains("当前场景导出的新模板", error.Message);
        Assert.Equal(before, workspace.SaveInputJson());
    }

    [Fact]
    public void FrameDistribution_MissingRequiredCountsCannotBecomeZeroObservations()
    {
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize("""
        {"counts":{"D":0,"A":0,"U":0},"proportions":{"D":null,"A":null,"U":null},"valid_frame_count":0}
        """, SceneJsonContext.Default.SceneFrameDistribution));
    }

    [Fact]
    public void FrameReport_PreservesKnownFailMissingCountsNullProportionsAndExactPointShape()
    {
        var workspace = new SceneWorkspace(Catalog());
        workspace.LoadInputJson(InputJson);
        var reportJson = """
        {"schema_version":"3.0","scene_id":"SCN-002","calculation_status":"needs_input","grade":"U","passed":false,
         "configuration":CONFIGURATION_PLACEHOLDER,"input":INPUT_PLACEHOLDER,
         "items":[{"item_id":"flight","grade":"U","passed":false,
          "frame_distribution":{"counts":{"D":0,"A":0,"U":1},"proportions":{"D":0,"A":0,"U":1},"valid_frame_count":1,"missing_frame_count":1,"total_frame_count":2},
          "phase_results":[{"phase_id":"hold","name":"保持","grade":"U","passed":false,"observed_span_s":5,"required_duration_s":5,"coverage_note":"首末时间跨度不证明连续采样","frame_distribution":{"counts":{"D":0,"A":0,"U":1},"proportions":{"D":0,"A":0,"U":1},"valid_frame_count":1,"missing_frame_count":1,"total_frame_count":2}}],
          "timeline":[{"frame_index":0,"timestamp_s":12.000000123,"phase_id":"hold","grade":"U","status":"complete","reason":""}],
          "checkpoints":[{"checkpoint_id":"laser-cp","grade":null,"metrics":[{"metric_id":"laser","grade":null,"status":"missing","reason":"未提供",
           "timeline":[{"frame_index":0,"timestamp_s":12.000000123,"phase_id":"hold","value":null,"expected":0,"deviation":null,"grade":null,"status":"missing","reason":"未提供"}],
           "frame_distribution":{"counts":{"D":0,"A":0,"U":0},"proportions":{"D":null,"A":null,"U":null},"valid_frame_count":0,"missing_frame_count":1,"total_frame_count":1}}]}]}]}
        """.Replace("CONFIGURATION_PLACEHOLDER", workspace.SaveConfigurationJson()).Replace("INPUT_PLACEHOLDER", workspace.SaveInputJson());
        workspace.SetReport(JsonSerializer.Deserialize(reportJson, SceneJsonContext.Default.SceneReport)!);
        var result = JsonNode.Parse(workspace.ExportReportJson())!;
        Assert.False(result["passed"]!.GetValue<bool>());
        var metric = result["items"]![0]!["checkpoints"]![0]!["metrics"]![0]!;
        var point = metric["timeline"]![0]!.AsObject();
        Assert.False(point.ContainsKey("start_s"));
        Assert.False(point.ContainsKey("end_s"));
        Assert.Null(metric["frame_distribution"]!["proportions"]!["D"]);
        Assert.False(metric.AsObject().ContainsKey("distribution"));
        Assert.False(metric.AsObject().ContainsKey("episodes"));
        var stale = workspace.Report!;
        workspace.LoadInputJson(InputJson.Replace("17.000000123", "18.000000123"));
        Assert.False(workspace.HasReport);
        Assert.Throws<InvalidOperationException>(() => workspace.SetReport(stale));
    }

    internal static SceneCatalog Catalog(string sceneId = "SCN-002") => JsonSerializer.Deserialize(CatalogJson.Replace("SCN-002", sceneId), SceneJsonContext.Default.SceneCatalog)!;

    private const string InputJson = """
    {"schema_version":"3.0","scene_id":"SCN-002","items":{"flight":{"frames":[
    {"timestamp_s":12.000000123,"phase_id":"hold","values":{"height":1.5,"laser":{"status":"hit","u_m":0.25,"v_m":-0.5}},"controls":{"Pilot Lon":0.4}},
    {"timestamp_s":17.000000123,"phase_id":"hold","values":{"height":null,"laser":{"status":"miss","u_m":null,"v_m":null}}}
    ]}}}
    """;

    private const string CatalogJson = """
    {"schema_version":"3.0","scene_id":"SCN-002","name":"垂直机动","metrics":[
     {"metric_id":"height","name":"高度","input_kind":"frame","comparison":"linear","phase_ids":["hold"]},
     {"metric_id":"laser","name":"激光","input_kind":"frame","comparison":"radial","phase_ids":["hold"]}],
     "items":[{"item_id":"flight","assessment_kind":"flight","phases":[{"phase_id":"hold","name":"保持","single_frame":false,"required_duration_s":5}],"checkpoints":[{"checkpoint_id":"height-cp","metric_ids":["height"]},{"checkpoint_id":"laser-cp","metric_ids":["laser"]}]}],
     "configuration_template":{"schema_version":"3.0","scene_id":"SCN-002","parameters":{
      "height":{"expected":null,"desired":{"lower":null,"upper":null,"unbounded_upper":false},"acceptable":{"lower":null,"upper":null,"unbounded_upper":false}},
      "laser":{"expected":0,"center_u":null,"center_v":null,"target_radius":null,"desired":{"lower":0,"upper":null,"unbounded_upper":false},"acceptable":{"lower":0,"upper":null,"unbounded_upper":false}}}},
     "input_template":{"schema_version":"3.0","scene_id":"SCN-002","items":{"flight":{"frames":[]}}}}
    """;
}
