using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

public sealed class SceneRegistry
{
    [JsonPropertyName("trace_id"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? TraceId { get; set; }
    [JsonPropertyName("schema_version")]
    public required string SchemaVersion { get; set; }
    [JsonPropertyName("scenes")]
    public List<SceneSummary> Scenes { get; set; } = [];
}
