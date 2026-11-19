using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

public sealed class SceneRoutePoint
{
    [JsonRequired, JsonPropertyName("x_m")] public double? XM { get; set; }
    [JsonRequired, JsonPropertyName("y_m")] public double? YM { get; set; }
    [JsonRequired, JsonPropertyName("height_m")] public double? HeightM { get; set; }
}
