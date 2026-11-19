using System.Text.Json;
using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

/// <summary>An observed state at an exact timestamp on the shared scene simulation clock, grouped within its item.</summary>
public sealed class SceneFrame
{
    [JsonRequired, JsonPropertyName("timestamp_s")] public double? TimestampS { get; set; }
    [JsonRequired, JsonPropertyName("phase_id")] public string PhaseId { get; set; } = "";
    [JsonRequired, JsonPropertyName("values")] public Dictionary<string, JsonElement?> Values { get; set; } = [];
    [JsonPropertyName("controls"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public Dictionary<string, JsonElement?>? Controls { get; set; }
}
