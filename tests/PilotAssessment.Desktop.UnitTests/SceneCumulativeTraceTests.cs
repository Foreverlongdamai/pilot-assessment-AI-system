using System.Text.Json;
using System.Text.Json.Nodes;

using PilotAssessment.Desktop.Core.SceneAssessment;

namespace PilotAssessment.Desktop.UnitTests;

public sealed class SceneCumulativeTraceTests
{
    [Fact]
    public void CumulativeTracePreservesPartialCoverageMissingAndCompleteEndpoint()
    {
        var source = JsonNode.Parse(JsonSerializer.Serialize(new SceneSkillQuantification
        {
            Status = "complete", Method = SceneSkillModel.CompensationInferenceMethod,
            Posterior = [.1, .2, .7], Score = 80,
        }))!;
        source["cumulative_trace"] = JsonNode.Parse("""
        {
          "item_id": "hover", "method": "demo_cumulative_prefix_v1", "message": "累计表现",
          "timeline": [
            { "frame_index": 0, "timestamp_s": 10.1, "phase_id": "lower",
              "status": "partial", "observed_checkpoint_count": 1, "expected_checkpoint_count": 4,
              "missing_frame_count": 0, "posterior": [0.2,0.3,0.5], "score": 65 },
            { "frame_index": 1, "timestamp_s": 10.2, "phase_id": "lower",
              "status": "insufficient_evidence", "observed_checkpoint_count": 1, "expected_checkpoint_count": 4,
              "missing_frame_count": 1, "posterior": null, "score": null },
            { "frame_index": 2, "timestamp_s": 20.123456789, "phase_id": "upper",
              "status": "complete", "observed_checkpoint_count": 4, "expected_checkpoint_count": 4,
              "missing_frame_count": 0, "posterior": [0.1,0.2,0.7], "score": 80 }
          ]
        }
        """);
        // This is a serialization fixture, not a physically valid recovery from
        // cumulative missing evidence; the Python method tests that invariant.
        var model = JsonSerializer.Deserialize(source.ToJsonString(),
            SceneJsonContext.Default.SceneSkillQuantification)!;
        var restored = JsonNode.Parse(JsonSerializer.Serialize(model,
            SceneJsonContext.Default.SceneSkillQuantification))!;
        Assert.True(JsonNode.DeepEquals(source, restored));
        Assert.Equal(20.123456789, restored["cumulative_trace"]!["timeline"]![2]!["timestamp_s"]!.GetValue<double>());
        Assert.Null(restored["cumulative_trace"]!["timeline"]![1]!["score"]);
    }

    [Fact]
    public void ReportsWithoutCumulativeTraceDoNotInventOne()
    {
        var old = new SceneSkillQuantification { Status = "pending_method" };
        var json = JsonSerializer.Serialize(old, SceneJsonContext.Default.SceneSkillQuantification);
        Assert.DoesNotContain("cumulative_trace", json);
        var loaded = JsonSerializer.Deserialize(json, SceneJsonContext.Default.SceneSkillQuantification)!;
        Assert.Equal(json, JsonSerializer.Serialize(loaded, SceneJsonContext.Default.SceneSkillQuantification));
    }
}
