using System.Text.Json;
using System.Text.Json.Nodes;
using PilotAssessment.Desktop.Core.SceneAssessment;

namespace PilotAssessment.Desktop.UnitTests;

public sealed class SceneItemReferenceProfileTests
{
    [Fact]
    public void SharedReference_RoundTripsThroughCatalogDraftAndIsolatedItemEdit()
    {
        var workspace = new SceneWorkspace(Catalog());
        var before = workspace.SaveConfigurationJson();
        workspace.LoadConfigurationJson(before);
        var edit = workspace.BeginItemEdit("flight");
        edit.Parameters["height"].Desired.Lower = -.5;
        workspace.CommitItemEdit(edit);

        var saved = JsonNode.Parse(workspace.SaveConfigurationJson())!;
        Assert.True(JsonNode.DeepEquals(JsonNode.Parse(before)!["parameters"]!["height"]!["reference_profile"],
            saved["parameters"]!["height"]!["reference_profile"]));
        Assert.Null(saved["parameters"]!["height"]!["expected"]);
        Assert.False(saved["parameters"]!["height"]!.AsObject().ContainsKey("reference_profiles"));
        var catalog = JsonSerializer.SerializeToNode(workspace.Catalog, SceneJsonContext.Default.SceneCatalog)!;
        Assert.Equal("acceleration", catalog["metrics"]![0]!["reference_origin_phase"]!.GetValue<string>());
    }

    [Theory]
    [InlineData("[]")]
    [InlineData("[{\"elapsed_s\":null,\"expected\":null}]")]
    [InlineData("[{\"elapsed_s\":0,\"expected\":0},{\"elapsed_s\":null,\"expected\":null}]")]
    public void IncompleteSharedReference_RemainsAnUnfilledDraft(string nodesJson)
    {
        var workspace = new SceneWorkspace(Catalog());
        var configuration = JsonNode.Parse(workspace.SaveConfigurationJson())!;
        configuration["parameters"]!["height"]!["reference_profile"] = JsonNode.Parse(nodesJson);
        workspace.LoadConfigurationJson(configuration.ToJsonString());
        var edit = workspace.BeginItemEdit("flight");
        edit.Parameters["laser"].CenterU = 12;
        workspace.CommitItemEdit(edit);
        var saved = JsonNode.Parse(workspace.SaveConfigurationJson())!;
        Assert.True(JsonNode.DeepEquals(JsonNode.Parse(nodesJson), saved["parameters"]!["height"]!["reference_profile"]));
    }

    [Theory]
    [InlineData("missing-profile")]
    [InlineData("null-profile")]
    [InlineData("nonzero-start")]
    [InlineData("duplicate-time")]
    [InlineData("negative-time")]
    [InlineData("missing-node-field")]
    [InlineData("fixed-expected")]
    [InlineData("old-phase-profiles")]
    [InlineData("old-phase-profiles-null")]
    [InlineData("profile-on-fixed")]
    [InlineData("profile-on-fixed-null")]
    public void InvalidSharedReference_IsRejectedWithoutReplacingCurrentConfiguration(string defect)
    {
        var workspace = new SceneWorkspace(Catalog());
        var before = workspace.SaveConfigurationJson();
        var configuration = JsonNode.Parse(before)!;
        var parameter = configuration["parameters"]!["height"]!;
        var points = parameter["reference_profile"]!;
        switch (defect)
        {
            case "missing-profile": parameter.AsObject().Remove("reference_profile"); break;
            case "null-profile": parameter["reference_profile"] = null; break;
            case "nonzero-start": points[0]!["elapsed_s"] = 1; break;
            case "duplicate-time": points[1]!["elapsed_s"] = 0; break;
            case "negative-time": points[1]!["elapsed_s"] = -1; break;
            case "missing-node-field": points[0]!.AsObject().Remove("elapsed_s"); break;
            case "fixed-expected": parameter["expected"] = 10; break;
            case "old-phase-profiles": parameter["reference_profiles"] = new JsonObject { ["hold"] = points.DeepClone() }; break;
            case "old-phase-profiles-null": parameter["reference_profiles"] = null; break;
            case "profile-on-fixed": configuration["parameters"]!["laser"]!["reference_profile"] = points.DeepClone(); break;
            case "profile-on-fixed-null": configuration["parameters"]!["laser"]!["reference_profile"] = null; break;
        }
        Assert.Throws<JsonException>(() => workspace.LoadConfigurationJson(configuration.ToJsonString()));
        Assert.Equal(before, workspace.SaveConfigurationJson());
    }

    [Fact]
    public void ReportPoint_PreservesOriginalAndReferenceTimeWithoutRecalculatingEither()
    {
        const string json = """
        {"frame_index":62,"timestamp_s":34.7,"phase_id":"hold","reference_elapsed_s":6.4,
         "value":9.8,"expected":10,"deviation":-0.2,"grade":"D"}
        """;
        var point = JsonSerializer.Deserialize(json, SceneJsonContext.Default.SceneMetricTimePoint)!;
        var saved = JsonSerializer.SerializeToNode(point, SceneJsonContext.Default.SceneMetricTimePoint)!;
        Assert.True(JsonNode.DeepEquals(JsonNode.Parse(json), saved));
    }

    [Fact]
    public void SharedReferenceNodeEdits_AreIsolatedAndRejectUnorderedOrNonfiniteValues()
    {
        var workspace = new SceneWorkspace(Catalog());
        var edit = workspace.BeginItemEdit("flight");
        var points = edit.Parameters["height"].ReferenceProfile!;
        points[1].Expected = 8;
        Assert.Equal(10, workspace.Configuration.Parameters["height"].ReferenceProfile![1].Expected);
        points[1].ElapsedS = 0;
        Assert.Throws<JsonException>(() => workspace.CommitItemEdit(edit));
        points[1].ElapsedS = 6;
        points[1].Expected = double.PositiveInfinity;
        Assert.Throws<JsonException>(() => workspace.CommitItemEdit(edit));
        points[1].Expected = 8;
        workspace.CommitItemEdit(edit);
        points[1].Expected = 99;
        Assert.Equal(8, workspace.Configuration.Parameters["height"].ReferenceProfile![1].Expected);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("unrelated")]
    public void SharedReference_MustDeclareAnApplicableOriginPhase(string? origin)
    {
        var catalog = Catalog();
        catalog.Metrics[0].ReferenceOriginPhase = origin;
        var workspace = new SceneWorkspace(catalog);
        Assert.Throws<JsonException>(() => workspace.LoadConfigurationJson(workspace.SaveConfigurationJson()));
    }

    [Fact]
    public void SharedReference_CannotBeAddedToTheLegacyPerPhaseMode()
    {
        var catalog = Catalog();
        catalog.Metrics[0].TargetMode = "phase_profile";
        catalog.Metrics[0].ReferenceOriginPhase = null;
        var workspace = new SceneWorkspace(catalog);
        Assert.Throws<JsonException>(() => workspace.LoadConfigurationJson(workspace.SaveConfigurationJson()));
    }

    [Fact]
    public void ItemReportSnapshot_PreservesSharedNodesOriginAndReportedReferenceTimes()
    {
        var catalog = Catalog();
        var workspace = new SceneWorkspace(catalog);
        var report = new SceneReport
        {
            SchemaVersion = catalog.SchemaVersion, SceneId = catalog.SceneId,
            Configuration = workspace.Configuration, Input = workspace.Input,
            Items = [new() { ItemId = "flight", Checkpoints = [new() { Metrics = [new()
            {
                MetricId = "height", Timeline = [new()
                {
                    FrameIndex = 62, TimestampS = 34.7, PhaseId = "hold", ReferenceElapsedS = 6.4,
                    Expected = 10, Value = JsonSerializer.SerializeToElement(9.8), Deviation = -.2, Grade = "D",
                }],
            }] }] }],
        };
        var snapshot = new SceneItemReportSnapshot(catalog, report, "flight");
        catalog.Metrics[0].ReferenceOriginPhase = "hold";
        report.Configuration.Parameters["height"].ReferenceProfile![1].Expected = 99;
        report.Items[0].Checkpoints[0].Metrics[0].Timeline[0].ReferenceElapsedS = 0;

        Assert.Equal("acceleration", snapshot.Catalog.Metrics[0].ReferenceOriginPhase);
        Assert.Equal(10, snapshot.Report.Configuration.Parameters["height"].ReferenceProfile![1].Expected);
        Assert.Equal(6.4, snapshot.Item.Checkpoints[0].Metrics[0].Timeline[0].ReferenceElapsedS);
        Assert.Equal(34.7, snapshot.Item.Checkpoints[0].Metrics[0].Timeline[0].TimestampS);
    }

    internal static SceneCatalog Catalog()
    {
        var catalog = JsonSerializer.SerializeToNode(SceneFramesTests.Catalog(), SceneJsonContext.Default.SceneCatalog)!;
        catalog["metrics"]![0]!["target_mode"] = "item_profile";
        catalog["metrics"]![0]!["reference_origin_phase"] = "acceleration";
        catalog["metrics"]![0]!["phase_ids"] = new JsonArray("acceleration", "hold");
        catalog["items"]![0]!["phases"]!.AsArray().Insert(0,
            new JsonObject { ["phase_id"] = "acceleration", ["name"] = "加速" });
        catalog["configuration_template"]!["parameters"]!["height"]!["reference_profile"] =
            JsonNode.Parse("""[{"elapsed_s":0,"expected":0},{"elapsed_s":6,"expected":10},{"elapsed_s":16.1,"expected":10}]""");
        return JsonSerializer.Deserialize(catalog, SceneJsonContext.Default.SceneCatalog)!;
    }
}
