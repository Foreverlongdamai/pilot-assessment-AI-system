using System.Text.Json;
using System.Text.Json.Nodes;

using PilotAssessment.Desktop.Core.SceneAssessment;

namespace PilotAssessment.Desktop.UnitTests;

public sealed class SceneRouteTests
{
    [Theory]
    [InlineData("[]")]
    [InlineData("[{\"x_m\":null,\"y_m\":null,\"height_m\":null}]")]
    [InlineData("[{\"x_m\":0,\"y_m\":null,\"height_m\":12},{\"x_m\":30,\"y_m\":0,\"height_m\":8}]")]
    public void PartialRouteDraft_RoundTripsWithoutFillingCoordinatesOrChangingOtherTargets(string nodesJson)
    {
        var workspace = new SceneWorkspace(Catalog());
        var configuration = JsonNode.Parse(workspace.SaveConfigurationJson())!;
        configuration["parameters"]!["position"]!["route_points"] = JsonNode.Parse(nodesJson);
        workspace.LoadConfigurationJson(configuration.ToJsonString());
        var edit = workspace.BeginItemEdit("flight");
        edit.Parameters["heading"].Expected = 42;
        workspace.CommitItemEdit(edit);
        var saved = JsonNode.Parse(workspace.SaveConfigurationJson())!;
        Assert.True(JsonNode.DeepEquals(JsonNode.Parse(nodesJson), saved["parameters"]!["position"]!["route_points"]));
        Assert.Equal(42d, saved["parameters"]!["heading"]!["expected"]!.GetValue<double>());
        Assert.False(saved["parameters"]!["heading"]!.AsObject().ContainsKey("route_points"));
    }

    [Theory]
    [InlineData("missing-route")]
    [InlineData("null-route")]
    [InlineData("missing-coordinate")]
    [InlineData("null-point")]
    [InlineData("duplicate-points")]
    [InlineData("negative-radius")]
    [InlineData("equal-radii")]
    [InlineData("reversed-radii")]
    [InlineData("wrong-lower")]
    [InlineData("wrong-expected")]
    [InlineData("unbounded")]
    [InlineData("null-profile")]
    [InlineData("null-radial")]
    [InlineData("route-on-fixed")]
    [InlineData("null-route-on-fixed")]
    public void InvalidRouteConfiguration_RejectsAtomically(string defect)
    {
        var workspace = new SceneWorkspace(Catalog());
        var before = workspace.SaveConfigurationJson();
        var configuration = JsonNode.Parse(before)!;
        var parameter = configuration["parameters"]!["position"]!;
        switch (defect)
        {
            case "missing-route": parameter.AsObject().Remove("route_points"); break;
            case "null-route": parameter["route_points"] = null; break;
            case "missing-coordinate": parameter["route_points"]![0]!.AsObject().Remove("height_m"); break;
            case "null-point": parameter["route_points"]![0] = null; break;
            case "duplicate-points": parameter["route_points"]![1] = parameter["route_points"]![0]!.DeepClone(); break;
            case "negative-radius": parameter["desired"]!["upper"] = -1; break;
            case "equal-radii": parameter["acceptable"]!["upper"] = 1; break;
            case "reversed-radii": parameter["acceptable"]!["upper"] = .5; break;
            case "wrong-lower": parameter["desired"]!["lower"] = -1; break;
            case "wrong-expected": parameter["expected"] = 4; break;
            case "unbounded": parameter["acceptable"]!["unbounded_upper"] = true; break;
            case "null-profile": parameter["reference_profiles"] = null; break;
            case "null-radial": parameter["center_u"] = null; break;
            case "route-on-fixed": configuration["parameters"]!["heading"]!["route_points"] = parameter["route_points"]!.DeepClone(); break;
            case "null-route-on-fixed": configuration["parameters"]!["heading"]!["route_points"] = null; break;
        }
        Assert.Throws<JsonException>(() => workspace.LoadConfigurationJson(configuration.ToJsonString()));
        Assert.Equal(before, workspace.SaveConfigurationJson());
    }

    [Fact]
    public void InvalidRouteEdit_IsIsolatedAndRejectsKnownNonfiniteCoordinatesBeforeCommit()
    {
        var workspace = new SceneWorkspace(Catalog());
        var before = workspace.SaveConfigurationJson();
        var edit = workspace.BeginItemEdit("flight");
        var point = edit.Parameters["position"].RoutePoints![0];
        point.XM = 6;
        Assert.Equal(before, workspace.SaveConfigurationJson());
        point.HeightM = double.PositiveInfinity;
        Assert.Throws<JsonException>(() => workspace.CommitItemEdit(edit));
        Assert.Equal(before, workspace.SaveConfigurationJson());
        point.HeightM = null;
        workspace.CommitItemEdit(edit);
        Assert.Equal(6d, workspace.Configuration.Parameters["position"].RoutePoints![0].XM);
        Assert.Null(workspace.Configuration.Parameters["position"].RoutePoints![0].HeightM);
    }

    [Fact]
    public void RouteFrameReport_PreservesRawPositionNearestPointDistanceAndExactTime()
    {
        const string json = """
        {"frame_index":4,"timestamp_s":12.000000123,"phase_id":"approach","status":"calculated","reason":"",
         "value":{"x_m":4,"y_m":-1,"height_m":12},"expected":0,"deviation":1,"grade":"D",
         "nearest_route_point":{"x_m":4,"y_m":0,"height_m":12},"route_segment_index":0}
        """;
        var point = JsonSerializer.Deserialize(json, SceneJsonContext.Default.SceneMetricTimePoint)!;
        var saved = JsonSerializer.SerializeToNode(point, SceneJsonContext.Default.SceneMetricTimePoint);
        Assert.True(JsonNode.DeepEquals(JsonNode.Parse(json), saved));
        Assert.Equal(-1, point.Value!.Value.GetProperty("y_m").GetDouble());
        Assert.Equal(0, point.NearestRoutePoint!.YM);
        Assert.Equal(1, point.Deviation);
    }

    private static SceneCatalog Catalog() => JsonSerializer.Deserialize("""
    {"schema_version":"3.0","scene_id":"SCN-001","name":"路线","metrics":[
      {"metric_id":"position","name":"位置","comparison":"route_3d","input_kind":"frame","phase_ids":["approach"]},
      {"metric_id":"heading","name":"航向","comparison":"heading","input_kind":"frame","phase_ids":["approach"]}],
     "items":[{"item_id":"flight","phases":[{"phase_id":"approach","name":"进近","single_frame":false}],
       "checkpoints":[{"checkpoint_id":"route-cp","metric_ids":["position"]},{"checkpoint_id":"heading-cp","metric_ids":["heading"]}]}],
     "configuration_template":{"schema_version":"3.0","scene_id":"SCN-001","parameters":{
       "position":{"expected":0,"route_points":[{"x_m":0,"y_m":0,"height_m":12},{"x_m":30,"y_m":0,"height_m":8}],
        "desired":{"lower":0,"upper":1,"unbounded_upper":false},"acceptable":{"lower":0,"upper":2,"unbounded_upper":false}},
       "heading":{"expected":0,"desired":{"lower":-1,"upper":1,"unbounded_upper":false},"acceptable":{"lower":-2,"upper":2,"unbounded_upper":false}}}},
     "input_template":{"schema_version":"3.0","scene_id":"SCN-001","items":{"flight":{"frames":[]}}}}
    """, SceneJsonContext.Default.SceneCatalog)!;
}
