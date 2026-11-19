using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

public sealed class SceneSkillQuantification
{
    [JsonPropertyName("status")] public string Status { get; set; } = "";
    [JsonPropertyName("skill_name")] public string SkillName { get; set; } = "";
    [JsonPropertyName("method")] public string Method { get; set; } = "";
    [JsonPropertyName("model_version")] public string? ModelVersion { get; set; }
    [JsonPropertyName("calibration")] public string? Calibration { get; set; }
    [JsonPropertyName("parameter_source")] public string? ParameterSource { get; set; }
    [JsonPropertyName("posterior")] public List<double>? Posterior { get; set; }
    [JsonPropertyName("score")] public double? Score { get; set; }
    [JsonPropertyName("evidence_count")] public int EvidenceCount { get; set; }
    [JsonPropertyName("expected_evidence_count")] public int ExpectedEvidenceCount { get; set; }
    [JsonPropertyName("evidence_strength"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? EvidenceStrength { get; set; }
    [JsonPropertyName("local_traces"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public List<SceneSkillLocalTrace>? LocalTraces { get; set; }
    [JsonPropertyName("cumulative_trace"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public SceneSkillCumulativeTrace? CumulativeTrace { get; set; }
    [JsonPropertyName("temporal_analysis"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public SceneTemporalAnalysis? TemporalAnalysis { get; set; }
    [JsonPropertyName("evidence")] public List<SceneSkillEvidence> Evidence { get; set; } = [];
    [JsonPropertyName("message")] public string Message { get; set; } = "";
    [JsonPropertyName("warnings")] public List<string> Warnings { get; set; } = [];
}
