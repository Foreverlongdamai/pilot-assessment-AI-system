using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

public sealed class SceneSkillLocalTrace
{
    [JsonRequired, JsonPropertyName("checkpoint_id")] public string CheckpointId { get; set; } = "";
    [JsonRequired, JsonPropertyName("method")] public string Method { get; set; } = "";
    [JsonRequired, JsonPropertyName("window_s")] public double WindowS { get; set; }
    [JsonRequired, JsonPropertyName("phase_reset")] public bool PhaseReset { get; set; }
    [JsonPropertyName("message")] public string Message { get; set; } = "";
    [JsonRequired, JsonPropertyName("timeline")] public List<SceneSkillLocalPoint> Timeline { get; set; } = [];
}
