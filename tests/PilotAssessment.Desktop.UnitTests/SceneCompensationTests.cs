using System.Text.Json;
using System.Text.Json.Nodes;
using PilotAssessment.Desktop.Core.SceneAssessment;

namespace PilotAssessment.Desktop.UnitTests;

public sealed class SceneCompensationTests
{
    private const string Method = "sequential_bayes_compensation_v1";

    [Fact]
    public void CompensationConfigurationRoundTripsAndPreservesExplicitMethod()
    {
        var workspace = new SceneWorkspace(Catalog());
        var source = Configuration(workspace, .2);
        workspace.LoadConfigurationJson(source.ToJsonString());
        Assert.True(JsonNode.DeepEquals(source, JsonNode.Parse(workspace.SaveConfigurationJson())));
        Assert.Equal(Method, workspace.Configuration.SkillModels!["flight"].InferenceMethod);
        Assert.DoesNotContain("process_model", workspace.SaveConfigurationJson());
    }

    [Fact]
    public void BlankTemplateCanBeStoredWithoutInventingProbabilities()
    {
        var workspace = new SceneWorkspace(Catalog());
        var source = Configuration(workspace, .2);
        var model = source["skill_models"]!["flight"]!;
        model["prior"] = new JsonArray(null, null, null);
        foreach (var checkpoint in model["checkpoint_models"]!.AsObject())
        {
            checkpoint.Value!["probabilities"] = JsonNode.Parse("[[null,null,null],[null,null,null],[null,null,null]]");
        }
        workspace.LoadConfigurationJson(source.ToJsonString());
        Assert.True(JsonNode.DeepEquals(source, JsonNode.Parse(workspace.SaveConfigurationJson())));
    }

    [Fact]
    public void FrameReportRetainsEveryBayesAndCompensationProbabilityWithoutChangingLegacyReports()
    {
        const string json = """
        {"frame_index":0,"timestamp_s":12.5,"phase_id":"hold","grade":"U","status":"calculated",
         "prior":[0.01,0.09,0.9],"bayes_posterior":[0.7,0.2,0.1],
         "compensation_target":[1,0,0],"compensation_alpha":0.2,"compensation_delta":[0.06,-0.04,-0.02],
         "posterior":[0.76,0.16,0.08],"score":16,"log_bayes_factor_high_low":-2.3,
         "update_kind":"bayes_compensation","evidence_count":2,"observed_checkpoint_count":2,"expected_checkpoint_count":2}
        """;
        var point = JsonSerializer.Deserialize(json, SceneJsonContext.Default.SceneTemporalPoint)!;
        Assert.True(JsonNode.DeepEquals(JsonNode.Parse(json), JsonNode.Parse(
            JsonSerializer.Serialize(point, SceneJsonContext.Default.SceneTemporalPoint))));
        var legacy = JsonSerializer.Serialize(new SceneTemporalPoint(), SceneJsonContext.Default.SceneTemporalPoint);
        Assert.DoesNotContain("compensation_", legacy);
        Assert.DoesNotContain("bayes_posterior", legacy);
    }

    [Theory]
    [InlineData(-.01)]
    [InlineData(1.01)]
    public void InvalidCompensationDoesNotReplaceWorkspaceOrExistingReport(double alpha)
    {
        var workspace = new SceneWorkspace(Catalog());
        workspace.SetReport(new SceneReport { SchemaVersion = "3.0", SceneId = "SCN-002",
            Configuration = workspace.Configuration, Input = workspace.Input });
        var before = workspace.SaveConfigurationJson();
        Assert.Throws<JsonException>(() => workspace.LoadConfigurationJson(Configuration(workspace, alpha).ToJsonString()));
        Assert.Equal(before, workspace.SaveConfigurationJson());
        Assert.NotNull(workspace.Report);
    }

    [Fact]
    public void CompensationCopyIsIsolatedAndEqualityIncludesAlpha()
    {
        var workspace = new SceneWorkspace(Catalog());
        workspace.LoadConfigurationJson(Configuration(workspace, .2).ToJsonString());
        var original = workspace.Configuration.SkillModels!["flight"];
        var copy = SceneSkillModelEditing.Copy(original);
        Assert.True(SceneSkillModelEditing.ParametersEqual(original, copy));
        var source = JsonNode.Parse(JsonSerializer.Serialize(copy, SceneJsonContext.Default.SceneSkillModel))!;
        source["compensation"]!["alpha"] = .4;
        var changed = JsonSerializer.Deserialize(source.ToJsonString(), SceneJsonContext.Default.SceneSkillModel)!;
        Assert.False(SceneSkillModelEditing.ParametersEqual(original, changed));
        Assert.Equal(.2, JsonNode.Parse(JsonSerializer.Serialize(original, SceneJsonContext.Default.SceneSkillModel))!["compensation"]!["alpha"]!.GetValue<double>());
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    public void EndpointAlphaAndZeroPriorAreValid(double alpha)
    {
        var workspace = new SceneWorkspace(Catalog());
        var source = Configuration(workspace, alpha);
        source["skill_models"]!["flight"]!["prior"] = new JsonArray(0, 0, 1);
        workspace.LoadConfigurationJson(source.ToJsonString());
        Assert.Equal([0d, 0d, 1d], workspace.Configuration.SkillModels!["flight"].Prior);
    }

    [Theory]
    [InlineData("missing-alpha")]
    [InlineData("null-alpha")]
    [InlineData("unknown-field")]
    [InlineData("process-model")]
    public void RejectsAmbiguousOrMalformedCompensationContract(string defect)
    {
        var workspace = new SceneWorkspace(Catalog());
        var source = Configuration(workspace, .2);
        var model = source["skill_models"]!["flight"]!;
        switch (defect)
        {
            case "missing-alpha": model["compensation"] = new JsonObject(); break;
            case "null-alpha": model["compensation"]!["alpha"] = null; break;
            case "unknown-field": model["compensation"]!["alhpa"] = .3; break;
            case "process-model": model["process_model"] = JsonNode.Parse("""{"method":"fixed_skill_markov_v1","checkpoint_time_constants_s":{}}"""); break;
        }
        Assert.Throws<JsonException>(() => workspace.LoadConfigurationJson(source.ToJsonString()));
    }

    [Fact]
    public void ModelStudioIdentifiesCompensatedEndpointWithoutRelabelingLegacyScore()
    {
        var workspace = new SceneWorkspace(Catalog());
        var report = new SceneReport { SchemaVersion = "3.0", SceneId = "SCN-002", Configuration = workspace.Configuration,
            Input = workspace.Input, Items = [new() { ItemId = "flight", Grade = "U", Passed = false,
                SkillQuantification = new() { Method = Method, Status = "complete", Score = 90, Posterior = [.05, .1, .85] } }] };
        workspace.SetReport(report);
        var node = Assert.Single(SceneGraphProjection.Build([workspace]).Nodes, node => node.Kind == "item");
        Assert.True(node.IsCompensationScore);
        Assert.Equal("U", node.Grade);
        report.Items[0].SkillQuantification!.Method = "demo_normalized_grade_likelihood_v1";
        workspace.SetReport(report);
        node = Assert.Single(SceneGraphProjection.Build([workspace]).Nodes, node => node.Kind == "item");
        Assert.False(node.IsCompensationScore);
        Assert.Null(node.Score);
    }

    private static JsonNode Configuration(SceneWorkspace workspace, double alpha)
    {
        var source = JsonNode.Parse(workspace.SaveConfigurationJson())!;
        source["skill_models"]!["flight"]!["inference_method"] = Method;
        source["skill_models"]!["flight"]!["compensation"] = new JsonObject { ["alpha"] = alpha };
        return source;
    }

    private static SceneCatalog Catalog()
    {
        var catalog = SceneFramesTests.Catalog();
        catalog.ConfigurationTemplate.SkillModels = new() { ["flight"] = new()
        {
            ModelVersion = "test", Calibration = "uncalibrated", ParameterSource = "demonstration",
            InferenceMethod = SceneSkillModel.CompensationInferenceMethod, Compensation = new() { Alpha = .2 },
            Prior = [1d / 3, 1d / 3, 1d / 3], StateScores = [0, 50, 100],
            CheckpointModels = catalog.Items[0].Checkpoints.ToDictionary(checkpoint => checkpoint.CheckpointId,
                _ => new SceneCheckpointSkillModel { States = ["D", "A", "U"],
                    Probabilities = [[.1, .25, .65], [.35, .63, .02], [.9, .099, .001]] }),
        } };
        return catalog;
    }
}
