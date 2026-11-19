using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

public sealed class SceneTemporalPoint
{
    [JsonRequired, JsonPropertyName("frame_index")] public int FrameIndex { get; set; }
    [JsonRequired, JsonPropertyName("timestamp_s")] public double TimestampS { get; set; }
    [JsonRequired, JsonPropertyName("phase_id")] public string PhaseId { get; set; } = "";
    [JsonPropertyName("grade")] public string? Grade { get; set; }
    [JsonRequired, JsonPropertyName("status")] public string Status { get; set; } = "";
    [JsonPropertyName("posterior")] public List<double>? Posterior { get; set; }
    [JsonPropertyName("prior"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public List<double>? Prior { get; set; }
    [JsonPropertyName("bayes_posterior"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public List<double>? BayesPosterior { get; set; }
    [JsonPropertyName("compensation_target"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public List<double>? CompensationTarget { get; set; }
    [JsonPropertyName("compensation_alpha"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? CompensationAlpha { get; set; }
    [JsonPropertyName("compensation_delta"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public List<double>? CompensationDelta { get; set; }
    [JsonPropertyName("score")] public double? Score { get; set; }
    [JsonPropertyName("log_bayes_factor_high_low")] public double? LogBayesFactorHighLow { get; set; }
    [JsonRequired, JsonPropertyName("update_kind")] public string UpdateKind { get; set; } = "";
    [JsonRequired, JsonPropertyName("evidence_count")] public int EvidenceCount { get; set; }
    [JsonRequired, JsonPropertyName("observed_checkpoint_count")] public int ObservedCheckpointCount { get; set; }
    [JsonRequired, JsonPropertyName("expected_checkpoint_count")] public int ExpectedCheckpointCount { get; set; }
}
