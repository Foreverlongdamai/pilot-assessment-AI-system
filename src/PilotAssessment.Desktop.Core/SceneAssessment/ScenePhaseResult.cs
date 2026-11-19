using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

public sealed class ScenePhaseResult
{
    [JsonPropertyName("phase_id")] public string PhaseId { get; set; } = "";
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("grade")] public string? Grade { get; set; }
    [JsonPropertyName("passed")] public bool? Passed { get; set; }
    [JsonPropertyName("status"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public string? Status { get; set; }
    [JsonPropertyName("frame_distribution")] public SceneFrameDistribution? FrameDistribution { get; set; }
    [JsonPropertyName("observed_span_s")] public double? ObservedSpanS { get; set; }
    [JsonPropertyName("required_duration_s")] public double? RequiredDurationS { get; set; }
    [JsonPropertyName("minimum_frame_count"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public int? MinimumFrameCount { get; set; }
    [JsonPropertyName("coverage_note"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public string? CoverageNote { get; set; }
}
