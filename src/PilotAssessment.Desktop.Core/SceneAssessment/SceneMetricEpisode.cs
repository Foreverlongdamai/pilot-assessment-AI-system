using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

public sealed class SceneMetricEpisode
{
    [JsonPropertyName("start_s")] public double StartS { get; set; }
    [JsonPropertyName("end_s")] public double EndS { get; set; }
    [JsonPropertyName("grade")] public string Grade { get; set; } = "";
    [JsonPropertyName("duration_s")] public double DurationS { get; set; }
    [JsonPropertyName("max_abs_deviation")] public double? MaxAbsDeviation { get; set; }
}
