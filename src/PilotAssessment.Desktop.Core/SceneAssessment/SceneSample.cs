using System.Text.Json;
using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

/// <summary>A supplied flight-relative interval; the client does not infer its boundaries.</summary>
public sealed class SceneSample
{
    [JsonRequired, JsonPropertyName("start_s")] public double StartS { get; set; }
    [JsonRequired, JsonPropertyName("end_s")] public double EndS { get; set; }
    [JsonRequired, JsonPropertyName("values")] public Dictionary<string, JsonElement?> Values { get; set; } = [];
}
