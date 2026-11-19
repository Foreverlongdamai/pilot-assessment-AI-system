using System.Text.Json;
using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

public sealed class SceneCheckpointInput
{
    [JsonRequired, JsonPropertyName("values")]
    public Dictionary<string, JsonElement?> Values { get; set; } = [];
    [JsonRequired, JsonPropertyName("samples")]
    public List<SceneSample> Samples { get; set; } = [];
}
