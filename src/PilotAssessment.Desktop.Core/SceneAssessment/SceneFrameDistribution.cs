using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

public sealed class SceneFrameDistribution
{
    [JsonRequired, JsonPropertyName("counts")] public Dictionary<string, int> Counts { get; set; } = [];
    [JsonRequired, JsonPropertyName("proportions")] public Dictionary<string, double?> Proportions { get; set; } = [];
    [JsonRequired, JsonPropertyName("valid_frame_count")] public int ValidFrameCount { get; set; }
    [JsonRequired, JsonPropertyName("missing_frame_count")] public int MissingFrameCount { get; set; }
    [JsonPropertyName("total_frame_count"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public int? TotalFrameCount { get; set; }
}
