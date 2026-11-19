using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

public sealed class SceneSkillCumulativePoint
{
    [JsonRequired, JsonPropertyName("frame_index")] public int FrameIndex { get; set; }
    [JsonRequired, JsonPropertyName("timestamp_s")] public double TimestampS { get; set; }
    [JsonRequired, JsonPropertyName("phase_id")] public string PhaseId { get; set; } = "";
    [JsonRequired, JsonPropertyName("status")] public string Status { get; set; } = "";
    [JsonRequired, JsonPropertyName("observed_checkpoint_count")]
    public int ObservedCheckpointCount { get; set; }
    [JsonRequired, JsonPropertyName("expected_checkpoint_count")]
    public int ExpectedCheckpointCount { get; set; }
    [JsonRequired, JsonPropertyName("missing_frame_count")]
    public int MissingFrameCount { get; set; }
    [JsonPropertyName("posterior")] public List<double>? Posterior { get; set; }
    [JsonPropertyName("score")] public double? Score { get; set; }
}
