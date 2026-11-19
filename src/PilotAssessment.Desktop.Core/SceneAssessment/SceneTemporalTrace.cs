using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

public sealed class SceneTemporalTrace
{
    [JsonPropertyName("checkpoint_id")] public string? CheckpointId { get; set; }
    [JsonRequired, JsonPropertyName("method")] public string Method { get; set; } = "";
    [JsonRequired, JsonPropertyName("status")] public string Status { get; set; } = "";
    [JsonPropertyName("message")] public string Message { get; set; } = "";
    [JsonRequired, JsonPropertyName("timeline")] public List<SceneTemporalPoint> Timeline { get; set; } = [];
}
