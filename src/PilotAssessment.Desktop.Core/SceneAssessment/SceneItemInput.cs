using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

public sealed class SceneItemInput
{
    [JsonPropertyName("checkpoints"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public Dictionary<string, SceneCheckpointInput>? Checkpoints { get; set; }
    [JsonPropertyName("frames"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public List<SceneFrame>? Frames { get; set; }
}
