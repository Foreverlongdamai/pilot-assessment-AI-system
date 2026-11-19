using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

public sealed class ScenePhase
{
    [JsonPropertyName("phase_id")] public string PhaseId { get; set; } = "";
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("single_frame")] public bool SingleFrame { get; set; }
    [JsonPropertyName("required_duration_s")] public double? RequiredDurationS { get; set; }
    [JsonPropertyName("minimum_frame_count"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public int? MinimumFrameCount { get; set; }
}
