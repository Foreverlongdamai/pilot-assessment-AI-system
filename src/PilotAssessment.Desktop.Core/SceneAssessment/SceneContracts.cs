using System.Text.Json;
using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

public sealed class SceneCatalog
{
    [JsonPropertyName("trace_id"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public string? TraceId { get; set; }
    [JsonPropertyName("schema_version")] public required string SchemaVersion { get; set; }
    [JsonPropertyName("scene_id")] public required string SceneId { get; set; }
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("description")] public string Description { get; set; } = "";
    [JsonPropertyName("phase_sequence"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public List<string>? PhaseSequence { get; set; }
    [JsonPropertyName("metrics")] public List<SceneMetric> Metrics { get; set; } = [];
    [JsonPropertyName("items")] public List<SceneItem> Items { get; set; } = [];
    [JsonPropertyName("configuration_template")] public required SceneConfiguration ConfigurationTemplate { get; set; }
    [JsonPropertyName("input_template")] public required SceneInput InputTemplate { get; set; }
}

public sealed class SceneMetric
{
    [JsonPropertyName("metric_id")] public string MetricId { get; set; } = "";
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("description")] public string Description { get; set; } = "";
    [JsonPropertyName("unit")] public string Unit { get; set; } = "";
    [JsonPropertyName("value_type")] public string ValueType { get; set; } = "number";
    [JsonPropertyName("rule")] public string Rule { get; set; } = "interval";
    [JsonPropertyName("parameter_kind")] public string ParameterKind { get; set; } = "";
    [JsonPropertyName("shared")] public bool Shared { get; set; }
    [JsonPropertyName("input_kind")] public string InputKind { get; set; } = "scalar";
    [JsonPropertyName("comparison")] public string Comparison { get; set; } = "linear";
    [JsonPropertyName("default_expected"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public double? DefaultExpected { get; set; }
    [JsonPropertyName("phase_ids"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public List<string>? PhaseIds { get; set; }
    [JsonPropertyName("target_mode"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public string? TargetMode { get; set; }
    [JsonPropertyName("reference_origin_phase"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public string? ReferenceOriginPhase { get; set; }
}

public sealed class SceneItem
{
    [JsonPropertyName("item_id")] public string ItemId { get; set; } = "";
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("description")] public string Description { get; set; } = "";
    [JsonPropertyName("skill_name")] public string SkillName { get; set; } = "";
    [JsonPropertyName("skill_description")] public string SkillDescription { get; set; } = "";
    [JsonPropertyName("assessment_kind")] public string AssessmentKind { get; set; } = "flight";
    [JsonPropertyName("phases"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public List<ScenePhase>? Phases { get; set; }
    [JsonPropertyName("equivalent_values"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public List<List<string>>? EquivalentValues { get; set; }
    [JsonPropertyName("checkpoints")] public List<SceneCheckpoint> Checkpoints { get; set; } = [];
}

public sealed class SceneCheckpoint
{
    [JsonPropertyName("checkpoint_id")] public string CheckpointId { get; set; } = "";
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("description")] public string Description { get; set; } = "";
    [JsonPropertyName("metric_ids")] public List<string> MetricIds { get; set; } = [];
    [JsonPropertyName("sources")] public List<SceneSource> Sources { get; set; } = [];
    [JsonPropertyName("fail_when")] public List<SceneFailCondition> FailWhen { get; set; } = [];
    [JsonPropertyName("not_required_when")] public List<SceneFailCondition> NotRequiredWhen { get; set; } = [];
}

public sealed class SceneSource
{
    [JsonPropertyName("document")] public string Document { get; set; } = "";
    [JsonPropertyName("clause")] public string Clause { get; set; } = "";
    [JsonPropertyName("page")] public string Page { get; set; } = "";
    [JsonPropertyName("url")] public string Url { get; set; } = "";
    [JsonPropertyName("support")] public string Support { get; set; } = "";
    [JsonPropertyName("note")] public string Note { get; set; } = "";
}

public sealed class SceneFailCondition
{
    [JsonPropertyName("metric_id")] public string MetricId { get; set; } = "";
    [JsonPropertyName("equals")] public JsonElement EqualsValue { get; set; }
}

public sealed class SceneConfiguration
{
    [JsonPropertyName("schema_version")] public required string SchemaVersion { get; set; }
    [JsonPropertyName("scene_id")] public required string SceneId { get; set; }
    [JsonPropertyName("parameters")] public required Dictionary<string, SceneParameter> Parameters { get; set; }
    [JsonPropertyName("skill_models"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public Dictionary<string, SceneSkillModel>? SkillModels { get; set; }
}

public sealed class SceneParameter
{
    [JsonPropertyName("expected")] public double? Expected { get; set; }
    [JsonPropertyName("center_u"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public double? CenterU { get; set; }
    [JsonPropertyName("center_v"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public double? CenterV { get; set; }
    [JsonPropertyName("target_radius"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public double? TargetRadius { get; set; }
    [JsonPropertyName("reference_profiles"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public Dictionary<string, List<SceneReferencePoint>>? ReferenceProfiles { get; set; }
    [JsonPropertyName("reference_profile"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public List<SceneReferencePoint>? ReferenceProfile { get; set; }
    [JsonPropertyName("route_points"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public List<SceneRoutePoint>? RoutePoints { get; set; }
    [JsonRequired, JsonPropertyName("desired")] public SceneInterval Desired { get; set; } = new();
    [JsonRequired, JsonPropertyName("acceptable")] public SceneInterval Acceptable { get; set; } = new();
}

public sealed class SceneInterval
{
    [JsonPropertyName("lower")] public double? Lower { get; set; }
    [JsonPropertyName("upper")] public double? Upper { get; set; }
    [JsonRequired, JsonPropertyName("unbounded_upper")] public bool UnboundedUpper { get; set; }
}

public sealed class SceneInput
{
    [JsonPropertyName("schema_version")] public required string SchemaVersion { get; set; }
    [JsonPropertyName("scene_id")] public required string SceneId { get; set; }
    [JsonPropertyName("results"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public Dictionary<string, JsonElement?>? Results { get; set; }
    [JsonPropertyName("items"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public Dictionary<string, SceneItemInput>? Items { get; set; }
}

public sealed class SceneIssue
{
    [JsonPropertyName("path")] public string Path { get; set; } = "";
    [JsonPropertyName("message")] public string Message { get; set; } = "";
}

public sealed class SceneValidationResult
{
    [JsonPropertyName("trace_id"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public string? TraceId { get; set; }
    [JsonPropertyName("valid")] public bool Valid { get; set; }
    [JsonPropertyName("issues")] public List<SceneIssue> Issues { get; set; } = [];
}

public sealed class SceneReport
{
    [JsonPropertyName("trace_id"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public string? TraceId { get; set; }
    [JsonPropertyName("schema_version")] public required string SchemaVersion { get; set; }
    [JsonPropertyName("scene_id")] public required string SceneId { get; set; }
    [JsonPropertyName("evaluated_at")] public string EvaluatedAt { get; set; } = "";
    [JsonPropertyName("calculation_status")] public string CalculationStatus { get; set; } = "";
    [JsonPropertyName("grade")] public string? Grade { get; set; }
    [JsonPropertyName("passed")] public bool? Passed { get; set; }
    [JsonPropertyName("configuration")] public required SceneConfiguration Configuration { get; set; }
    [JsonPropertyName("input")] public required SceneInput Input { get; set; }
    [JsonPropertyName("issues")] public List<SceneIssue> Issues { get; set; } = [];
    [JsonPropertyName("items")] public List<SceneItemResult> Items { get; set; } = [];
}

public sealed class SceneItemResult
{
    [JsonPropertyName("item_id")] public string ItemId { get; set; } = "";
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("grade")] public string? Grade { get; set; }
    [JsonPropertyName("passed")] public bool? Passed { get; set; }
    [JsonPropertyName("checkpoints")] public List<SceneCheckpointResult> Checkpoints { get; set; } = [];
    [JsonPropertyName("skill_quantification"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public SceneSkillQuantification? SkillQuantification { get; set; }
    [JsonPropertyName("timeline"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public List<SceneCheckpointTimePoint>? Timeline { get; set; }
    [JsonPropertyName("frame_distribution"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public SceneFrameDistribution? FrameDistribution { get; set; }
    [JsonPropertyName("phase_results"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public List<ScenePhaseResult>? PhaseResults { get; set; }
}

public sealed class SceneCheckpointResult
{
    [JsonPropertyName("checkpoint_id")] public string CheckpointId { get; set; } = "";
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("grade")] public string? Grade { get; set; }
    [JsonPropertyName("metrics")] public List<SceneMetricResult> Metrics { get; set; } = [];
    [JsonPropertyName("timeline")] public List<SceneCheckpointTimePoint> Timeline { get; set; } = [];
    [JsonPropertyName("distribution"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public SceneTimeDistribution? Distribution { get; set; }
    [JsonPropertyName("frame_distribution"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public SceneFrameDistribution? FrameDistribution { get; set; }
}

public sealed class SceneMetricResult
{
    [JsonPropertyName("metric_id")] public string MetricId { get; set; } = "";
    [JsonPropertyName("value")] public JsonElement? Value { get; set; }
    [JsonPropertyName("grade")] public string? Grade { get; set; }
    [JsonPropertyName("status")] public string Status { get; set; } = "";
    [JsonPropertyName("reason")] public string Reason { get; set; } = "";
    [JsonPropertyName("parameter")] public SceneParameter? Parameter { get; set; }
    [JsonPropertyName("expected")] public double? Expected { get; set; }
    [JsonPropertyName("deviation")] public double? Deviation { get; set; }
    [JsonPropertyName("timeline")] public List<SceneMetricTimePoint> Timeline { get; set; } = [];
    [JsonPropertyName("distribution"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public SceneTimeDistribution? Distribution { get; set; }
    [JsonPropertyName("episodes"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public List<SceneMetricEpisode>? Episodes { get; set; }
    [JsonPropertyName("frame_distribution"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public SceneFrameDistribution? FrameDistribution { get; set; }
}

public sealed record SceneValidationRequest([property: JsonPropertyName("configuration")] SceneConfiguration Configuration);
public sealed record SceneCatalogRequest(
    [property: JsonPropertyName("scene_id")] string SceneId,
    [property: JsonPropertyName("schema_version"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] string? SchemaVersion = null);
public sealed record SceneEvaluationRequest(
    [property: JsonPropertyName("configuration")] SceneConfiguration Configuration,
    [property: JsonPropertyName("input")] SceneInput Input);
