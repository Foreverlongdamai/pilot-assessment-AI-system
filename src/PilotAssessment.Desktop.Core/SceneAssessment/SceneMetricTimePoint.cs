using System.Text.Json;
using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

public sealed class SceneMetricTimePoint
{
    [JsonPropertyName("start_s"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public double? StartS { get; set; }
    [JsonPropertyName("end_s"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public double? EndS { get; set; }
    [JsonPropertyName("frame_index"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public int? FrameIndex { get; set; }
    [JsonPropertyName("timestamp_s"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public double? TimestampS { get; set; }
    [JsonPropertyName("phase_id"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public string? PhaseId { get; set; }
    [JsonPropertyName("reference_elapsed_s"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public double? ReferenceElapsedS { get; set; }
    [JsonPropertyName("status"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public string? Status { get; set; }
    [JsonPropertyName("reason"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public string? Reason { get; set; }
    [JsonPropertyName("value")] public JsonElement? Value { get; set; }
    [JsonPropertyName("expected")] public double? Expected { get; set; }
    [JsonPropertyName("deviation")] public double? Deviation { get; set; }
    [JsonPropertyName("nearest_route_point"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public SceneRoutePoint? NearestRoutePoint { get; set; }
    [JsonPropertyName("route_segment_index"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public int? RouteSegmentIndex { get; set; }
    [JsonPropertyName("grade")] public string? Grade { get; set; }
}
