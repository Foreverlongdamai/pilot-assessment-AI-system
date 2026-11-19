using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

public sealed class SceneSkillCumulativeTrace
{
    [JsonRequired, JsonPropertyName("item_id")] public string ItemId { get; set; } = "";
    [JsonRequired, JsonPropertyName("method")] public string Method { get; set; } = "";
    [JsonPropertyName("message")] public string Message { get; set; } = "";
    [JsonRequired, JsonPropertyName("timeline")]
    public List<SceneSkillCumulativePoint> Timeline { get; set; } = [];
}
