using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

public sealed class SceneTemporalAnalysis
{
    [JsonRequired, JsonPropertyName("status")] public string Status { get; set; } = "";
    [JsonRequired, JsonPropertyName("method")] public string Method { get; set; } = "";
    [JsonPropertyName("model_version")] public string? ModelVersion { get; set; }
    [JsonPropertyName("message")] public string Message { get; set; } = "";
    [JsonPropertyName("warnings")] public List<string> Warnings { get; set; } = [];
    [JsonRequired, JsonPropertyName("checkpoint_traces")] public List<SceneTemporalTrace> CheckpointTraces { get; set; } = [];
    [JsonPropertyName("item_trace")] public SceneTemporalTrace? ItemTrace { get; set; }
}
