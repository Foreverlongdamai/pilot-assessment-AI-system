using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

/// <summary>Explicit research parameters; probability validation and inference belong to Python.</summary>
public sealed class SceneSkillModel
{
    public const string CompensationInferenceMethod = "sequential_bayes_compensation_v1";

    [JsonRequired, JsonPropertyName("model_version")] public string ModelVersion { get; set; } = "";
    [JsonRequired, JsonPropertyName("calibration")] public string Calibration { get; set; } = "";
    [JsonRequired, JsonPropertyName("parameter_source")] public string ParameterSource { get; set; } = "";
    [JsonPropertyName("inference_method"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? InferenceMethod { get; set; }
    [JsonPropertyName("compensation"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public SceneCompensation? Compensation { get; set; }
    [JsonRequired, JsonPropertyName("prior")] public List<double?> Prior { get; set; } = [];
    [JsonRequired, JsonPropertyName("state_scores")] public List<double?> StateScores { get; set; } = [];
    [JsonRequired, JsonPropertyName("checkpoint_models")] public Dictionary<string, SceneCheckpointSkillModel> CheckpointModels { get; set; } = [];
}
