using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

public sealed class SceneSkillEvidence
{
    [JsonPropertyName("checkpoint_id")] public string CheckpointId { get; set; } = "";
    [JsonPropertyName("grade")] public string? Grade { get; set; }
    [JsonPropertyName("used")] public bool Used { get; set; }
    [JsonPropertyName("frame_distribution"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public SceneFrameDistribution? FrameDistribution { get; set; }
    [JsonPropertyName("weight"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? Weight { get; set; }
}
