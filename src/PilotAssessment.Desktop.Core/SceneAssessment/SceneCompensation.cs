using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

public sealed class SceneCompensation
{
    [JsonRequired, JsonPropertyName("alpha")] public double? Alpha { get; set; }
}
