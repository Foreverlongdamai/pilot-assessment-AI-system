using System.Text.Json;
using System.Text.Json.Nodes;
using PilotAssessment.Desktop.Core.SceneAssessment;

namespace PilotAssessment.Desktop.UnitTests;

public sealed class SceneSeriesTests
{
    [Fact]
    public void NestedInputRoundTripPreservesCheckpointRoutingTimesRawValuesAndBooleanFacts()
    {
        var workspace = new SceneWorkspace(Catalog());
        workspace.LoadInputJson(InputJson);
        var saved = JsonNode.Parse(workspace.SaveInputJson())!;
        Assert.Null(saved["results"]);
        var checkpoint = saved["items"]!["flight"]!["checkpoints"]!["heading"]!;
        Assert.Equal(10d, checkpoint["samples"]![0]!["start_s"]!.GetValue<double>());
        Assert.Equal(11.5, checkpoint["samples"]![0]!["end_s"]!.GetValue<double>());
        Assert.Equal(1d, checkpoint["samples"]![0]!["values"]!["heading_deg"]!.GetValue<double>());
        Assert.False(saved["items"]!["preflight"]!["checkpoints"]!["battery"]!["values"]!["battery_checked"]!.GetValue<bool>());
        Assert.Null(checkpoint["values"]!["hold_s"]);
        Assert.True(JsonNode.DeepEquals(JsonNode.Parse(InputJson), saved));
    }

    [Fact]
    public void ReportRoundTripPreservesSignedEvidenceAndDetachedSnapshots()
    {
        var workspace = new SceneWorkspace(Catalog());
        Assert.False(workspace.HasReport);
        workspace.LoadInputJson(InputJson);
        var report = Report(workspace);
        workspace.SetReport(report);
        Assert.True(workspace.HasReport);
        var saved = workspace.ExportReportJson();
        var json = JsonNode.Parse(saved)!;
        var metric = json["items"]![0]!["checkpoints"]![0]!["metrics"]![0]!;
        Assert.Equal(359d, metric["timeline"]![0]!["expected"]!.GetValue<double>());
        Assert.Equal(2d, metric["timeline"]![0]!["deviation"]!.GetValue<double>());
        Assert.Equal("A", metric["timeline"]![0]!["grade"]!.GetValue<string>());
        Assert.Equal(1.5, metric["distribution"]!["durations"]!["A"]!.GetValue<double>());
        Assert.Equal(0d, metric["distribution"]!["proportions"]!["U"]!.GetValue<double>());
        Assert.Equal(2d, metric["episodes"]![0]!["max_abs_deviation"]!.GetValue<double>());
        Assert.Null(report.Items[0].SkillQuantification!.Score);
        Assert.Null(report.Items[0].SkillQuantification!.Posterior);

        report.Items.Clear();
        workspace.Report!.Items.Clear();
        Assert.Equal(saved, workspace.ExportReportJson());
        workspace.LoadInputJson(InputJson);
        Assert.Null(workspace.Report);
        Assert.False(workspace.HasReport);
    }

    [Fact]
    public void NonuniformIntervalsGapsAndAllMissingDistributionSurviveSnapshots()
    {
        var workspace = new SceneWorkspace(Catalog());
        workspace.LoadInputJson(InputJson);
        var report = Report(workspace);
        var metric = report.Items[0].Checkpoints[0].Metrics[0];
        metric.Timeline.Add(new() { StartS = 12.5, EndS = 14.5, Expected = 359, Deviation = -1,
            Value = JsonSerializer.SerializeToElement(358), Grade = "D" });
        metric.Timeline.Add(new() { StartS = 14.5, EndS = 15, Expected = 359, Grade = null });
        metric.Distribution = new() { DurationS = 3.5, SpanS = 5, GapS = 1.5,
            Durations = new() { ["D"] = 2, ["A"] = 1.5, ["U"] = 0 },
            Proportions = new() { ["D"] = 2d / 3.5, ["A"] = 1.5 / 3.5, ["U"] = 0 } };
        report.Items[0].Checkpoints[0].Metrics.Add(new() { MetricId = "missing",
            Timeline = [new() { StartS = 10, EndS = 11, Grade = null }],
            Distribution = new() { DurationS = 0, SpanS = 1, GapS = 1,
                Durations = new() { ["D"] = 0, ["A"] = 0, ["U"] = 0 },
                Proportions = new() { ["D"] = null, ["A"] = null, ["U"] = null } } });
        workspace.SetReport(report);
        metric.Timeline[0].Deviation = 99;
        metric.Distribution.GapS = 99;
        var restored = JsonSerializer.Deserialize(workspace.ExportReportJson(), SceneJsonContext.Default.SceneReport)!;
        var metrics = restored.Items[0].Checkpoints[0].Metrics;
        Assert.Equal(3, metrics[0].Timeline.Count);
        Assert.Equal(2, metrics[0].Timeline[0].Deviation);
        Assert.Equal(-1, metrics[0].Timeline[1].Deviation);
        Assert.Null(metrics[0].Timeline[2].Grade);
        Assert.Equal(1.5, metrics[0].Distribution!.GapS);
        Assert.Equal(3.5, metrics[0].Distribution!.DurationS);
        Assert.All(metrics[1].Distribution!.Proportions.Values, value => Assert.Null(value));
    }

    [Fact]
    public void VersionTwoRejectsVersionOneInputsAndConfigurationWithTemplateGuidance()
    {
        var workspace = new SceneWorkspace(Catalog());
        var before = workspace.SaveInputJson();
        var inputError = Assert.Throws<JsonException>(() => workspace.LoadInputJson("""{"schema_version":"1.0","scene_id":"SCN-001","results":{}}"""));
        Assert.Contains("模板", inputError.Message);
        var legacy = JsonNode.Parse(workspace.SaveConfigurationJson())!;
        legacy["schema_version"] = "1.0";
        var configurationError = Assert.Throws<JsonException>(() => workspace.LoadConfigurationJson(legacy.ToJsonString()));
        Assert.Contains("模板", configurationError.Message);
        Assert.Equal(before, workspace.SaveInputJson());
    }

    [Theory]
    [InlineData("{\"schema_version\":\"2.0\",\"scene_id\":\"SCN-001\",\"results\":{}}")]
    [InlineData("{\"schema_version\":\"2.0\",\"scene_id\":\"SCN-001\",\"items\":{},\"results\":{}}")]
    [InlineData("{\"schema_version\":\"2.0\",\"scene_id\":\"SCN-001\",\"items\":{},\"results\":null}")]
    [InlineData("{\"schema_version\":\"2.0\",\"scene_id\":\"SCN-001\",\"items\":null}")]
    public void VersionTwoCannotSilentlyTreatLegacyOrMissingInputAsNestedResults(string json)
    {
        var workspace = new SceneWorkspace(Catalog());
        Assert.Throws<JsonException>(() => workspace.LoadInputJson(json));
    }

    [Fact]
    public void NewNestedFieldsRemainStrictAndRejectedInputDoesNotInvalidateReport()
    {
        var workspace = new SceneWorkspace(Catalog());
        workspace.LoadInputJson(InputJson);
        workspace.SetReport(Report(workspace));
        var saved = workspace.ExportReportJson();
        Assert.Throws<JsonException>(() => workspace.LoadInputJson(InputJson.Replace("start_s", "starts_s")));
        Assert.Equal(saved, workspace.ExportReportJson());
    }

    [Theory]
    [InlineData("start_s", "10")]
    [InlineData("end_s", "11.5")]
    public void OverflowingTimesCannotPutAnUnserializableInputIntoWorkspace(string field, string value)
    {
        var workspace = new SceneWorkspace(Catalog());
        var before = workspace.SaveInputJson();
        var invalid = InputJson.Replace($"\"{field}\":{value}", $"\"{field}\":1e400");
        Assert.Throws<JsonException>(() => workspace.LoadInputJson(invalid));
        Assert.Equal(before, workspace.SaveInputJson());
    }

    [Fact]
    public void BlankFlightModelIsEditableWithoutInventedProbabilitiesOrBlockingRuleEdits()
    {
        var workspace = new SceneWorkspace(Catalog());
        var edit = workspace.BeginItemEdit("flight");
        Assert.All(edit.SkillModel!.Prior, value => Assert.Null(value));
        Assert.All(edit.SkillModel.CheckpointModels["heading"].Probabilities, row => Assert.All(row, value => Assert.Null(value)));
        edit.Parameters["heading_deg"].Expected = 359;
        edit.Parameters["heading_deg"].Desired = new() { Lower = -1, Upper = 1 };
        edit.Parameters["heading_deg"].Acceptable = new() { Lower = -3, Upper = 2 };
        workspace.CommitItemEdit(edit);
        Assert.Equal(359, workspace.Configuration.Parameters["heading_deg"].Expected);
        Assert.Equal("unconfigured", workspace.Configuration.SkillModels!["flight"].ParameterSource);
        Assert.All(workspace.Configuration.SkillModels["flight"].Prior, value => Assert.Null(value));
    }

    [Theory]
    [InlineData("prior", "[-0.1,0.6,0.5]")]
    [InlineData("prior", "[1.1,null,null]")]
    [InlineData("prior", "[0.2,0.3,0.4]")]
    [InlineData("prior", "[0.6,0.6,null]")]
    [InlineData("checkpoint", "[-0.1,0.6,0.5]")]
    [InlineData("checkpoint", "[1.1,null,null]")]
    [InlineData("checkpoint", "[0.2,0.3,0.4]")]
    [InlineData("checkpoint", "[0.6,0.6,null]")]
    [InlineData("scores", "[-1,null,null]")]
    [InlineData("scores", "[null,null,101]")]
    [InlineData("scores", "[80,null,20]")]
    [InlineData("scores", "[20,20,null]")]
    public void InvalidFilledDraftCellsCannotPartiallySaveRulesOrDestroyCurrentReport(string target, string rowJson)
    {
        var workspace = new SceneWorkspace(Catalog());
        workspace.SetReport(Report(workspace));
        var before = workspace.SaveConfigurationJson();
        var edit = workspace.BeginItemEdit("flight");
        edit.Parameters["heading_deg"].Expected = 123;
        using var document = JsonDocument.Parse(rowJson);
        var row = document.RootElement.EnumerateArray()
            .Select(value => value.ValueKind == JsonValueKind.Null ? (double?)null : value.GetDouble()).ToList();
        switch (target)
        {
            case "prior": edit.SkillModel!.Prior = row; break;
            case "checkpoint": edit.SkillModel!.CheckpointModels["heading"].Probabilities[0] = row; break;
            case "scores": edit.SkillModel!.StateScores = row; break;
        }
        Assert.Throws<JsonException>(() => workspace.CommitItemEdit(edit));
        Assert.Equal(before, workspace.SaveConfigurationJson());
        Assert.True(workspace.HasReport);
    }

    [Theory]
    [InlineData("[null,null,null]")]
    [InlineData("[0.2,null,null]")]
    [InlineData("[0.2,null,0.8]")]
    [InlineData("[0.2,0.3,0.5]")]
    public void ValidPartialAndCompleteProbabilityRowsCanBeSavedWithoutAutoNormalization(string rowJson)
    {
        var workspace = new SceneWorkspace(Catalog());
        var edit = workspace.BeginItemEdit("flight");
        using var document = JsonDocument.Parse(rowJson);
        var row = document.RootElement.EnumerateArray()
            .Select(value => value.ValueKind == JsonValueKind.Null ? (double?)null : value.GetDouble()).ToList();
        edit.SkillModel!.Prior = [.. row];
        edit.SkillModel.StateScores = [0, null, 100];
        edit.SkillModel.CheckpointModels["heading"].Probabilities[0] = [.. row];
        workspace.CommitItemEdit(edit);
        workspace.LoadConfigurationJson(workspace.SaveConfigurationJson());
        Assert.Equal(row, workspace.Configuration.SkillModels!["flight"].Prior);
        Assert.Equal(row, workspace.Configuration.SkillModels["flight"].CheckpointModels["heading"].Probabilities[0]);
        Assert.Null(workspace.Configuration.SkillModels["flight"].StateScores[1]);
    }

    [Fact]
    public void ImportRejectsInvalidProbabilityWithoutReplacingExistingConfiguration()
    {
        var workspace = new SceneWorkspace(Catalog());
        var before = workspace.SaveConfigurationJson();
        var root = JsonNode.Parse(before)!;
        root["skill_models"]!["flight"]!["prior"] = JsonNode.Parse("[-1,2,0]");
        Assert.Throws<JsonException>(() => workspace.LoadConfigurationJson(root.ToJsonString()));
        Assert.Equal(before, workspace.SaveConfigurationJson());
    }

    [Fact]
    public void ChecklistCannotAcquireFlightModelAndItsGraphUsesMembershipOnly()
    {
        var workspace = new SceneWorkspace(Catalog());
        var graph = SceneGraphProjection.Build([workspace]);
        var checklist = Assert.Single(graph.Nodes, node => node.ItemId == "preflight" && node.Kind == "item");
        Assert.Null(checklist.Score);
        var checklistEdge = Assert.Single(graph.Edges, edge => edge.FromId == checklist.Id);
        Assert.Equal("membership", checklistEdge.Kind);
        Assert.Single(graph.Edges, edge => edge.Kind == "bayesian");
        var edit = workspace.BeginItemEdit("preflight");
        Assert.Empty(edit.Parameters);
        Assert.Null(edit.SkillModel);
        edit.SkillModel = workspace.Configuration.SkillModels!["flight"];
        var before = workspace.SaveConfigurationJson();
        Assert.Throws<JsonException>(() => workspace.CommitItemEdit(edit));
        Assert.Equal(before, workspace.SaveConfigurationJson());
    }

    [Fact]
    public void PendingMethodOrChecklistCannotDisplayAStaleNumericSkillScore()
    {
        var workspace = new SceneWorkspace(Catalog());
        var report = Report(workspace);
        report.Items[0].SkillQuantification!.Score = 99;
        report.Items.Add(new() { ItemId = "preflight", Grade = "D", Passed = true,
            SkillQuantification = new() { Status = "complete", Score = 100 } });
        workspace.SetReport(report);
        Assert.All(SceneGraphProjection.Build([workspace]).Nodes, node => Assert.Null(node.Score));
    }

    private static SceneCatalog Catalog() => JsonSerializer.Deserialize(CatalogJson, SceneJsonContext.Default.SceneCatalog)!;

    private static SceneReport Report(SceneWorkspace workspace)
    {
        var root = JsonNode.Parse("""
            {"schema_version":"2.0","scene_id":"SCN-001","calculation_status":"needs_input",
             "items":[{"item_id":"flight","grade":"A","passed":null,
              "skill_quantification":{"status":"pending_method","score":null,"posterior":null},
              "checkpoints":[{"checkpoint_id":"heading","grade":"A",
               "timeline":[{"start_s":10,"end_s":11.5,"grade":"A"}],
               "distribution":{"duration_s":1.5,"span_s":1.5,"gap_s":0,"durations":{"D":0,"A":1.5,"U":0},"proportions":{"D":0,"A":1,"U":0}},
               "metrics":[{"metric_id":"heading_deg","value":null,"expected":359,"deviation":null,"grade":"A",
                "timeline":[{"start_s":10,"end_s":11.5,"value":1,"expected":359,"deviation":2,"grade":"A"}],
                "distribution":{"duration_s":1.5,"span_s":1.5,"gap_s":0,"durations":{"D":0,"A":1.5,"U":0},"proportions":{"D":0,"A":1,"U":0}},
                "episodes":[{"start_s":10,"end_s":11.5,"grade":"A","duration_s":1.5,"max_abs_deviation":2}]}]}]}]}
            """)!;
        root["configuration"] = JsonSerializer.SerializeToNode(workspace.Configuration, SceneJsonContext.Default.SceneConfiguration);
        root["input"] = JsonSerializer.SerializeToNode(workspace.Input, SceneJsonContext.Default.SceneInput);
        return JsonSerializer.Deserialize(root.ToJsonString(), SceneJsonContext.Default.SceneReport)!;
    }

    private const string InputJson = """
        {"schema_version":"2.0","scene_id":"SCN-001","items":{
          "preflight":{"checkpoints":{"battery":{"values":{"battery_checked":false},"samples":[]}}},
          "flight":{"checkpoints":{"heading":{"values":{"hold_s":null},"samples":[
            {"start_s":10,"end_s":11.5,"values":{"heading_deg":1}}
          ]}}}}}
        """;

    private const string CatalogJson = """
        {"schema_version":"2.0","scene_id":"SCN-001","name":"契约测试",
         "metrics":[
          {"metric_id":"battery_checked","rule":"must_be_true","value_type":"boolean","input_kind":"scalar","comparison":"linear"},
          {"metric_id":"heading_deg","rule":"interval","input_kind":"series","comparison":"angle_degrees"},
          {"metric_id":"hold_s","rule":"interval","input_kind":"scalar","comparison":"linear"}],
         "items":[
          {"item_id":"preflight","assessment_kind":"checklist","checkpoints":[{"checkpoint_id":"battery","metric_ids":["battery_checked"]}]},
          {"item_id":"flight","assessment_kind":"flight","checkpoints":[{"checkpoint_id":"heading","metric_ids":["heading_deg","hold_s"]}]}],
         "configuration_template":{"schema_version":"2.0","scene_id":"SCN-001","parameters":{
          "heading_deg":{"expected":null,"desired":{"lower":null,"upper":null,"unbounded_upper":false},"acceptable":{"lower":null,"upper":null,"unbounded_upper":false}},
          "hold_s":{"expected":null,"desired":{"lower":null,"upper":null,"unbounded_upper":false},"acceptable":{"lower":null,"upper":null,"unbounded_upper":false}}},
          "skill_models":{"flight":{"model_version":"draft-v2","calibration":"uncalibrated","parameter_source":"unconfigured",
           "prior":[null,null,null],"state_scores":[null,null,null],"checkpoint_models":{"heading":{"states":["D","A","U"],"probabilities":[[null,null,null],[null,null,null],[null,null,null]]}}}}},
         "input_template":{"schema_version":"2.0","scene_id":"SCN-001","items":{
          "preflight":{"checkpoints":{"battery":{"values":{"battery_checked":null},"samples":[]}}},
          "flight":{"checkpoints":{"heading":{"values":{"hold_s":null},"samples":[]}}}}}}
        """;
}
