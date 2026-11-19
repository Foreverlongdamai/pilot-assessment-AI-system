using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

public sealed class SceneReferencePoint
{
    [JsonRequired, JsonPropertyName("elapsed_s")] public double? ElapsedS { get; set; }
    [JsonRequired, JsonPropertyName("expected")] public double? Expected { get; set; }
}
