using System.Text.Json;
using System.Text.Json.Nodes;
using PilotAssessment.Desktop.Core.SceneAssessment;

namespace PilotAssessment.Desktop.UnitTests;

public sealed class SceneSkillModelTests
{
    [Fact]
    public void CancelKeepsModelAndReportWhileCommitCopiesModelAndInvalidatesReport()
    {
        var workspace = new SceneWorkspace(Catalog());
        workspace.SetReport(Report(workspace));
        var before = workspace.SaveConfigurationJson();
        var cancelled = workspace.BeginItemEdit("item");
        cancelled.SkillModel!.Prior[0] = .2;
        cancelled.SkillModel.CheckpointModels["cp"].Probabilities[0][0] = .9;
        workspace.CancelItemEdit(cancelled);
        Assert.Equal(before, workspace.SaveConfigurationJson());
        Assert.NotNull(workspace.Report);

        var committed = workspace.BeginItemEdit("item");
        committed.SkillModel!.Prior = [.2, .3, .5];
        committed.SkillModel.ParameterSource = "user_defined";
        workspace.CommitItemEdit(committed);
        Assert.Equal(.2, workspace.Configuration.SkillModels!["item"].Prior[0]);
        Assert.Null(workspace.Report);
        committed.SkillModel.Prior[0] = .99;
        workspace.Configuration.SkillModels!["item"].Prior[0] = .99;
        Assert.Equal(.2, workspace.Configuration.SkillModels!["item"].Prior[0]);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void LegacyAbsentOrNullModelsStayAbsentUntilExplicitlyAdded(bool explicitNull)
    {
        var workspace = new SceneWorkspace(Catalog());
        var json = JsonNode.Parse(workspace.SaveConfigurationJson())!.AsObject();
        json.Remove("skill_models");
        if (explicitNull)
        {
            json["skill_models"] = null;
        }

        workspace.LoadConfigurationJson(json.ToJsonString());
        Assert.Null(workspace.Configuration.SkillModels);
        var legacyEdit = workspace.BeginItemEdit("item");
        Assert.Null(legacyEdit.SkillModel);
        workspace.CommitItemEdit(legacyEdit);
        Assert.DoesNotContain("skill_models", workspace.SaveConfigurationJson());

        var explicitEdit = workspace.BeginItemEdit("item");
        explicitEdit.SkillModel = Model();
        workspace.CommitItemEdit(explicitEdit);
        Assert.NotNull(workspace.Configuration.SkillModels!["item"]);
    }

    [Fact]
    public void MalformedModelCannotPartiallyCommitParametersOrClearCurrentReport()
    {
        var workspace = new SceneWorkspace(Catalog());
        workspace.SetReport(Report(workspace));
        var before = workspace.SaveConfigurationJson();
        var edit = workspace.BeginItemEdit("item");
        edit.Parameters["metric"].Expected = 17;
        edit.SkillModel!.CheckpointModels["cp"].Probabilities[0].RemoveAt(0);
        Assert.Throws<JsonException>(() => workspace.CommitItemEdit(edit));
        Assert.Equal(before, workspace.SaveConfigurationJson());
        Assert.NotNull(workspace.Report);
    }

    [Fact]
    public void ModelsAndQuantificationRoundTripAndCannotMutateSavedReport()
    {
        var workspace = new SceneWorkspace(Catalog());
        var report = Report(workspace);
        report.Items = [new() { ItemId = "item", SkillQuantification = new()
        {
            Status = "complete", SkillName = "当次表现", Method = "eap", ModelVersion = "scn001-skill-demo-v1",
            Calibration = "uncalibrated", ParameterSource = "demonstration", Posterior = [.1, .2, .7], Score = 80,
            EvidenceCount = 1, ExpectedEvidenceCount = 1,
            Evidence = [new() { CheckpointId = "cp", Grade = "D", Used = true }], Warnings = ["research"], Message = "complete",
        } }];
        workspace.SetReport(report);
        var saved = workspace.ExportReportJson();
        var restored = JsonSerializer.Deserialize(saved, SceneJsonContext.Default.SceneReport)!;
        Assert.Equal(80, restored.Items[0].SkillQuantification!.Score);
        Assert.Equal(.7, restored.Items[0].SkillQuantification!.Posterior![2]);
        Assert.Equal(3, restored.Configuration.SkillModels!["item"].CheckpointModels["cp"].Probabilities.Count);
        report.Items[0].SkillQuantification!.Posterior![0] = 1;
        report.Configuration.SkillModels!["item"].Prior.Clear();
        Assert.Equal(saved, workspace.ExportReportJson());
        var edit = workspace.BeginItemEdit("item");
        edit.SkillModel!.StateScores[1] = 60;
        workspace.CommitItemEdit(edit);
        Assert.Throws<InvalidOperationException>(() => workspace.SetReport(restored));
    }

    [Theory]
    [InlineData("prior")]
    [InlineData("checkpoint_models")]
    [InlineData("state_scores")]
    public void RequiredModelFieldsCannotBeSilentlyFilledOnImport(string field)
    {
        var workspace = new SceneWorkspace(Catalog());
        var root = JsonNode.Parse(workspace.SaveConfigurationJson())!;
        root["skill_models"]!["item"]!.AsObject().Remove(field);
        Assert.Throws<JsonException>(() => workspace.LoadConfigurationJson(root.ToJsonString()));
    }

    [Fact]
    public void DraftNullNumbersRoundTripButUnknownModelFieldsAreRejected()
    {
        var workspace = new SceneWorkspace(Catalog());
        var edit = workspace.BeginItemEdit("item");
        edit.SkillModel!.Prior[0] = null;
        workspace.CommitItemEdit(edit);
        var saved = workspace.SaveConfigurationJson();
        workspace.LoadConfigurationJson(saved);
        Assert.Null(workspace.Configuration.SkillModels!["item"].Prior[0]);
        Assert.Throws<JsonException>(() => workspace.LoadConfigurationJson(saved.Replace("parameter_source", "parameter_soruce")));
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void ObsoleteModelStructure_ExplainsTemplateWithoutMergingCptOrReplacingCurrentState(bool removedItem)
    {
        var workspace = new SceneWorkspace(Catalog());
        workspace.SetReport(Report(workspace));
        var before = workspace.SaveConfigurationJson();
        var configuration = workspace.Configuration;
        if (removedItem)
        {
            configuration.SkillModels!["removed-item"] = Model();
        }
        else
        {
            configuration.SkillModels!["item"].CheckpointModels["removed-checkpoint"] =
                configuration.SkillModels["item"].CheckpointModels["cp"];
        }

        var error = Assert.Throws<JsonException>(() => workspace.LoadConfigurationJson(
            JsonSerializer.Serialize(configuration, SceneJsonContext.Default.SceneConfiguration)));

        Assert.Contains("当前场景的配置模板", error.Message);
        Assert.Contains("不会自动合并旧 CPT", error.Message);
        Assert.Equal(before, workspace.SaveConfigurationJson());
        Assert.NotNull(workspace.Report);
    }

    private static SceneCatalog Catalog() => new()
    {
        SchemaVersion = "1.0", SceneId = "SCN-001",
        Metrics = [new() { MetricId = "metric", Rule = "interval" }],
        Items = [new() { ItemId = "item", SkillName = "当次表现", SkillDescription = "演示",
            Checkpoints = [new() { CheckpointId = "cp", MetricIds = ["metric"] }] }],
        ConfigurationTemplate = new() { SchemaVersion = "1.0", SceneId = "SCN-001", Parameters = new() { ["metric"] = new() },
            SkillModels = new() { ["item"] = Model() } },
        InputTemplate = new() { SchemaVersion = "1.0", SceneId = "SCN-001", Results = new() { ["metric"] = null } },
    };

    private static SceneSkillModel Model() => new()
    {
        ModelVersion = "scn001-skill-demo-v1", Calibration = "uncalibrated", ParameterSource = "demonstration",
        Prior = [1d / 3, 1d / 3, 1d / 3], StateScores = [0, 50, 100],
        CheckpointModels = new() { ["cp"] = new() { States = ["D", "A", "U"],
            Probabilities = [[.1, .25, .65], [.25, .5, .25], [.65, .25, .1]] } },
    };

    private static SceneReport Report(SceneWorkspace workspace) => new()
    {
        SchemaVersion = "1.0", SceneId = "SCN-001", Configuration = workspace.Configuration, Input = workspace.Input,
    };
}
