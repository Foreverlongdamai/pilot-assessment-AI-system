using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

public sealed class SceneCheckpointSkillModel
{
    [JsonRequired, JsonPropertyName("states")] public List<string> States { get; set; } = [];
    [JsonRequired, JsonPropertyName("probabilities")] public List<List<double?>> Probabilities { get; set; } = [];
}
