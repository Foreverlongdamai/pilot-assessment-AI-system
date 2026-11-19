using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

public sealed class SceneCheckpointTimePoint
{
    [JsonPropertyName("start_s"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public double? StartS { get; set; }
    [JsonPropertyName("end_s"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public double? EndS { get; set; }
    [JsonPropertyName("frame_index"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public int? FrameIndex { get; set; }
    [JsonPropertyName("timestamp_s"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public double? TimestampS { get; set; }
    [JsonPropertyName("phase_id"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public string? PhaseId { get; set; }
    [JsonPropertyName("status"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public string? Status { get; set; }
    [JsonPropertyName("reason"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public string? Reason { get; set; }
    [JsonPropertyName("grade")] public string? Grade { get; set; }
}
