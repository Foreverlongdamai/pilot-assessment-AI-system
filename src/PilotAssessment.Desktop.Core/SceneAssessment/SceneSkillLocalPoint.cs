using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

public sealed class SceneSkillLocalPoint
{
    [JsonRequired, JsonPropertyName("frame_index")] public int FrameIndex { get; set; }
    [JsonRequired, JsonPropertyName("timestamp_s")] public double TimestampS { get; set; }
    [JsonRequired, JsonPropertyName("phase_id")] public string PhaseId { get; set; } = "";
    [JsonRequired, JsonPropertyName("window_start_s")] public double WindowStartS { get; set; }
    [JsonRequired, JsonPropertyName("observed_start_s")] public double ObservedStartS { get; set; }
    [JsonRequired, JsonPropertyName("observed_span_s")] public double ObservedSpanS { get; set; }
    [JsonRequired, JsonPropertyName("window_complete")] public bool WindowComplete { get; set; }
    [JsonRequired, JsonPropertyName("frame_distribution")] public SceneFrameDistribution FrameDistribution { get; set; } = new();
    [JsonRequired, JsonPropertyName("status")] public string Status { get; set; } = "";
    [JsonPropertyName("posterior")] public List<double>? Posterior { get; set; }
    [JsonPropertyName("score")] public double? Score { get; set; }
}
