using System.Text.Json;
using System.Text.Json.Nodes;
using PilotAssessment.Desktop.Core.SceneAssessment;

namespace PilotAssessment.Desktop.UnitTests;

public sealed class SceneReferenceProfileTests
{
    [Fact]
    public void ManualReferenceProfiles_RoundTripThroughCatalogDraftAndItemEdit()
    {
        var workspace = new SceneWorkspace(Catalog());
        var before = workspace.SaveConfigurationJson();
        workspace.LoadConfigurationJson(before);
        var edit = workspace.BeginItemEdit("flight");
        edit.Parameters["height"].Desired.Lower = -.5;
        workspace.CommitItemEdit(edit);

        var saved = JsonNode.Parse(workspace.SaveConfigurationJson())!;
        Assert.True(JsonNode.DeepEquals(JsonNode.Parse(before)!["parameters"]!["height"]!["reference_profiles"],
            saved["parameters"]!["height"]!["reference_profiles"]));
        Assert.False(saved["parameters"]!["laser"]!.AsObject().ContainsKey("reference_profiles"));
        Assert.Null(saved["parameters"]!["height"]!["expected"]);
        var catalog = JsonSerializer.SerializeToNode(workspace.Catalog, SceneJsonContext.Default.SceneCatalog)!;
        Assert.Equal("phase_profile", catalog["metrics"]![0]!["target_mode"]!.GetValue<string>());
        Assert.Equal(2, catalog["items"]![0]!["phases"]![0]!["minimum_frame_count"]!.GetValue<int>());
    }

    [Theory]
    [InlineData("missing-profile")]
    [InlineData("unknown-phase")]
    [InlineData("missing-phase")]
    [InlineData("null-phase-nodes")]
    [InlineData("nonzero-start")]
    [InlineData("duplicate-time")]
    [InlineData("negative-time")]
    [InlineData("fixed-expected")]
    [InlineData("profile-on-fixed")]
    public void MalformedProfile_RejectsWithoutReplacingCurrentConfiguration(string defect)
    {
        var workspace = new SceneWorkspace(Catalog());
        var before = workspace.SaveConfigurationJson();
        var configuration = JsonNode.Parse(before)!;
        var parameter = configuration["parameters"]!["height"]!;
        var profiles = parameter["reference_profiles"]!.AsObject();
        switch (defect)
        {
            case "missing-profile": parameter.AsObject().Remove("reference_profiles"); break;
            case "unknown-phase": profiles["unknown"] = profiles["hold"]!.DeepClone(); break;
            case "missing-phase": profiles.Remove("hold"); break;
            case "null-phase-nodes": profiles["hold"] = null; break;
            case "nonzero-start": profiles["hold"]![0]!["elapsed_s"] = 1; break;
            case "duplicate-time": profiles["hold"]![1]!["elapsed_s"] = 0; break;
            case "negative-time": profiles["hold"]![1]!["elapsed_s"] = -1; break;
            case "fixed-expected": parameter["expected"] = 10; break;
            case "profile-on-fixed": configuration["parameters"]!["laser"]!["reference_profiles"] = profiles.DeepClone(); break;
        }
        Assert.Throws<JsonException>(() => workspace.LoadConfigurationJson(configuration.ToJsonString()));
        Assert.Equal(before, workspace.SaveConfigurationJson());
    }

    [Fact]
    public void BlankProfileNodes_RemainEditableWithoutInventedTargetOrDuration()
    {
        var workspace = new SceneWorkspace(Catalog());
        var configuration = JsonNode.Parse(workspace.SaveConfigurationJson())!;
        configuration["parameters"]!["height"]!["reference_profiles"]!["hold"] =
            JsonNode.Parse("""[{"elapsed_s":0,"expected":null},{"elapsed_s":null,"expected":null}]""");
        workspace.LoadConfigurationJson(configuration.ToJsonString());
        var saved = JsonNode.Parse(workspace.SaveConfigurationJson())!;
        Assert.True(JsonNode.DeepEquals(configuration["parameters"]!["height"], saved["parameters"]!["height"]));
    }

    [Theory]
    [InlineData("[]")]
    [InlineData("[{\"elapsed_s\":null,\"expected\":null}]")]
    [InlineData("[{\"elapsed_s\":0,\"expected\":30}]")]
    public void UnfinishedProfileStructure_RoundTripsAndAllowsOtherParameterEdits(string nodesJson)
    {
        var workspace = new SceneWorkspace(Catalog());
        var configuration = JsonNode.Parse(workspace.SaveConfigurationJson())!;
        configuration["parameters"]!["height"]!["reference_profiles"]!["hold"] = JsonNode.Parse(nodesJson);
        workspace.LoadConfigurationJson(configuration.ToJsonString());
        var edit = workspace.BeginItemEdit("flight");
        edit.Parameters["laser"].CenterU = 12;
        workspace.CommitItemEdit(edit);
        var saved = JsonNode.Parse(workspace.SaveConfigurationJson())!;
        Assert.True(JsonNode.DeepEquals(JsonNode.Parse(nodesJson), saved["parameters"]!["height"]!["reference_profiles"]!["hold"]));
        Assert.Equal(12d, saved["parameters"]!["laser"]!["center_u"]!.GetValue<double>());
    }

    [Fact]
    public void EditingReferenceNodes_IsolatedUntilCommitAndRejectsNonfiniteOrUnorderedTargets()
    {
        var workspace = new SceneWorkspace(Catalog());
        var edit = workspace.BeginItemEdit("flight");
        var points = edit.Parameters["height"].ReferenceProfiles!["hold"];
        points[0].Expected = 22;
        Assert.Equal(30, workspace.Configuration.Parameters["height"].ReferenceProfiles!["hold"][0].Expected);
        points[1].ElapsedS = 0;
        Assert.Throws<JsonException>(() => workspace.CommitItemEdit(edit));
        points[1].ElapsedS = 5;
        points[1].Expected = double.PositiveInfinity;
        Assert.Throws<JsonException>(() => workspace.CommitItemEdit(edit));
        points[1].Expected = null;
        workspace.CommitItemEdit(edit);
        Assert.Equal(22, workspace.Configuration.Parameters["height"].ReferenceProfiles!["hold"][0].Expected);
        Assert.Null(workspace.Configuration.Parameters["height"].ReferenceProfiles!["hold"][1].Expected);
    }

    [Fact]
    public void MinimumFrameEvidenceStatus_SurvivesReportRoundTrip()
    {
        const string json = """
        {"phase_id":"establish","name":"建立悬停","status":"missing","grade":null,"passed":null,
         "frame_distribution":null,"observed_span_s":0,"required_duration_s":null,"minimum_frame_count":2,
         "coverage_note":"只有一帧，不能证明持续表现。"}
        """;
        var result = JsonSerializer.Deserialize(json, SceneJsonContext.Default.ScenePhaseResult)!;
        var saved = JsonSerializer.SerializeToNode(result, SceneJsonContext.Default.ScenePhaseResult);
        Assert.True(JsonNode.DeepEquals(JsonNode.Parse(json), saved));
    }

    [Theory]
    [InlineData("obsolete-key")]
    [InlineData("noninterval-key")]
    public void ConfigurationWithoutSkillModels_RejectsObsoleteOrNonEditableParameterKeys(string defect)
    {
        var catalog = SceneFramesTests.Catalog();
        if (defect == "noninterval-key")
        {
            catalog.Metrics[0].Rule = "must_be_true";
            catalog.ConfigurationTemplate.Parameters.Remove("height");
        }
        var workspace = new SceneWorkspace(catalog);
        var before = workspace.SaveConfigurationJson();
        var configuration = JsonNode.Parse(before)!;
        configuration.AsObject().Remove("skill_models");
        configuration["parameters"]![defect == "obsolete-key" ? "start_x_m" : "height"] =
            configuration["parameters"]!["laser"]!.DeepClone();
        Assert.Throws<JsonException>(() => workspace.LoadConfigurationJson(configuration.ToJsonString()));
        Assert.Equal(before, workspace.SaveConfigurationJson());
    }

    private static SceneCatalog Catalog()
    {
        var catalog = JsonSerializer.SerializeToNode(SceneFramesTests.Catalog(), SceneJsonContext.Default.SceneCatalog)!;
        catalog["metrics"]![0]!["target_mode"] = "phase_profile";
        catalog["items"]![0]!["phases"]![0]!["minimum_frame_count"] = 2;
        catalog["configuration_template"]!["parameters"]!["height"]!["reference_profiles"] =
            JsonNode.Parse("""{"hold":[{"elapsed_s":0,"expected":30},{"elapsed_s":5,"expected":10}]}""");
        return JsonSerializer.Deserialize(catalog, SceneJsonContext.Default.SceneCatalog)!;
    }
}
