using System.Text.Json;
using System.Text.Json.Nodes;
using PilotAssessment.Desktop.Core.SceneAssessment;

namespace PilotAssessment.Desktop.UnitTests;

public sealed class SceneConfigurationUpgradeTests
{
    [Theory]
    [InlineData("demo_normalized_grade_likelihood_v1")]
    [InlineData(null)]
    public void OldFrameConfigurationAutomaticallyUsesNewMethodAndExportsNoOldProcess(string? method)
    {
        var workspace = new SceneWorkspace(Catalog());
        var original = JsonNode.Parse(workspace.SaveConfigurationJson())!;
        var oldModel = original["skill_models"]!["flight"]!;
        oldModel["inference_method"] = method;
        oldModel.AsObject().Remove("compensation");
        oldModel["process_model"] = JsonNode.Parse("""{"method":"fixed_skill_markov_v1","checkpoint_time_constants_s":{"height-cp":[5,5,5],"laser-cp":[4,5,6]}}""");
        var beforeInput = workspace.ExportInputTemplateJson();
        workspace.LoadConfigurationJson(original.ToJsonString());
        var saved = JsonNode.Parse(workspace.SaveConfigurationJson())!;
        var upgraded = saved["skill_models"]!["flight"]!;
        Assert.Equal(SceneSkillModel.CompensationInferenceMethod, upgraded["inference_method"]!.GetValue<string>());
        Assert.Equal(.2, upgraded["compensation"]!["alpha"]!.GetValue<double>());
        Assert.Null(upgraded["process_model"]);
        foreach (var name in new[] { "prior", "state_scores", "checkpoint_models", "parameter_source", "model_version", "calibration" })
            Assert.True(JsonNode.DeepEquals(oldModel[name], upgraded[name]), name);
        Assert.Equal(beforeInput, workspace.ExportInputTemplateJson());
        Assert.True(JsonNode.DeepEquals(original["parameters"], saved["parameters"]));
    }

    [Fact]
    public void TemplateWithoutMethodStartsWithNewMethodAndDoesNotInventPrior()
    {
        var catalog = Catalog();
        catalog.ConfigurationTemplate.SkillModels!["flight"].InferenceMethod = null;
        catalog.ConfigurationTemplate.SkillModels["flight"].Compensation = null;
        catalog.ConfigurationTemplate.SkillModels["flight"].Prior = [null, null, null];
        var workspace = new SceneWorkspace(catalog);
        Assert.Equal(SceneSkillModel.CompensationInferenceMethod, workspace.Configuration.SkillModels!["flight"].InferenceMethod);
        Assert.Equal(.2, workspace.Configuration.SkillModels["flight"].Compensation!.Alpha);
        Assert.All(workspace.Configuration.SkillModels["flight"].Prior, value => Assert.Null(value));
        Assert.Equal(SceneSkillModel.CompensationInferenceMethod, workspace.Catalog.ConfigurationTemplate.SkillModels!["flight"].InferenceMethod);
    }

    [Fact]
    public void NewAlphaIsPreservedAndUnknownMethodDoesNotDamageWorkspace()
    {
        var workspace = new SceneWorkspace(Catalog());
        var source = JsonNode.Parse(workspace.SaveConfigurationJson())!;
        source["skill_models"]!["flight"]!["compensation"]!["alpha"] = .37;
        workspace.LoadConfigurationJson(source.ToJsonString());
        Assert.Equal(.37, workspace.Configuration.SkillModels!["flight"].Compensation!.Alpha);
        var before = workspace.SaveConfigurationJson();
        source["skill_models"]!["flight"]!["inference_method"] = "unknown_method";
        Assert.Throws<JsonException>(() => workspace.LoadConfigurationJson(source.ToJsonString()));
        Assert.Equal(before, workspace.SaveConfigurationJson());
    }

    [Fact]
    public void HistoricalMethodKeepsExistingAlphaInsteadOfResettingIt()
    {
        var workspace = new SceneWorkspace(Catalog());
        var source = JsonNode.Parse(workspace.SaveConfigurationJson())!;
        source["skill_models"]!["flight"]!["inference_method"] = "demo_normalized_grade_likelihood_v1";
        source["skill_models"]!["flight"]!["compensation"]!["alpha"] = .37;
        workspace.LoadConfigurationJson(source.ToJsonString());
        Assert.Equal(.37, workspace.Configuration.SkillModels!["flight"].Compensation!.Alpha);
    }

    [Theory]
    [InlineData("123")]
    [InlineData("[]")]
    [InlineData("{}")]
    [InlineData("true")]
    public void MalformedMethodFailsAsJsonExceptionWithoutReplacingWorkspace(string methodJson)
    {
        var workspace = new SceneWorkspace(Catalog());
        var source = JsonNode.Parse(workspace.SaveConfigurationJson())!;
        source["skill_models"]!["flight"]!["inference_method"] = JsonNode.Parse(methodJson);
        var before = workspace.SaveConfigurationJson();
        Assert.Throws<JsonException>(() => workspace.LoadConfigurationJson(source.ToJsonString()));
        Assert.Equal(before, workspace.SaveConfigurationJson());
    }

    [Fact]
    public void HistoricalMethodWithExplicitNullCompensationIsRejected()
    {
        var workspace = new SceneWorkspace(Catalog());
        var source = JsonNode.Parse(workspace.SaveConfigurationJson())!;
        source["skill_models"]!["flight"]!["inference_method"] = "demo_normalized_grade_likelihood_v1";
        source["skill_models"]!["flight"]!["compensation"] = null;
        Assert.Throws<JsonException>(() => workspace.LoadConfigurationJson(source.ToJsonString()));
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
