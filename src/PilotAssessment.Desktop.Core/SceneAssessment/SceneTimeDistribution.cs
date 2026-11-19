using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

public sealed class SceneTimeDistribution
{
    [JsonPropertyName("duration_s")] public double DurationS { get; set; }
    [JsonPropertyName("span_s")] public double SpanS { get; set; }
    [JsonPropertyName("gap_s")] public double GapS { get; set; }
    [JsonPropertyName("durations")] public Dictionary<string, double> Durations { get; set; } = [];
    [JsonPropertyName("proportions")] public Dictionary<string, double?> Proportions { get; set; } = [];
}
