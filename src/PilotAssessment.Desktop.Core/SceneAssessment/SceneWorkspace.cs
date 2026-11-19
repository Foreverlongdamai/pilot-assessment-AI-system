using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization.Metadata;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

public sealed class SceneItemEdit
{
    internal SceneItemEdit(SceneWorkspace owner, string itemId, long revision, Dictionary<string, SceneParameter> parameters, SceneSkillModel? skillModel)
    {
        Owner = owner;
        ItemId = itemId;
        Revision = revision;
        Parameters = parameters;
        SkillModel = skillModel;
    }

    public string ItemId { get; }
    public Dictionary<string, SceneParameter> Parameters { get; }
    public SceneSkillModel? SkillModel { get; set; }
    internal SceneWorkspace Owner { get; }
    internal long Revision { get; }
    internal bool Closed { get; set; }
}

/// <summary>Owns editable scene files and current report; grading stays in the Python calculator.</summary>
public sealed class SceneWorkspace
{
    private SceneConfiguration _configuration;
    private SceneInput _input;
    private SceneReport? _report;
    private long _revision;

    public SceneWorkspace(SceneCatalog catalog)
    {
        ArgumentNullException.ThrowIfNull(catalog);
        Catalog = Clone(catalog, SceneJsonContext.Default.SceneCatalog);
        _configuration = Clone(catalog.ConfigurationTemplate, SceneJsonContext.Default.SceneConfiguration);
        NormalizeModels(Catalog.ConfigurationTemplate);
        NormalizeModels(_configuration);
        _input = Clone(catalog.InputTemplate, SceneJsonContext.Default.SceneInput);
    }

    public SceneCatalog Catalog { get; }
    public bool HasReport => _report is not null;
    public SceneConfiguration Configuration => Clone(_configuration, SceneJsonContext.Default.SceneConfiguration);
    public SceneInput Input => Clone(_input, SceneJsonContext.Default.SceneInput);
    public SceneReport? Report => _report is null ? null : Clone(_report, SceneJsonContext.Default.SceneReport);

    public SceneItemEdit BeginItemEdit(string itemId)
    {
        var item = Catalog.Items.FirstOrDefault(candidate => candidate.ItemId == itemId)
            ?? throw new ArgumentException("场景不包含此 item。", nameof(itemId));
        var editable = Catalog.Metrics.Where(metric => metric.Rule == "interval").Select(metric => metric.MetricId).ToHashSet(StringComparer.Ordinal);
        var parameters = new Dictionary<string, SceneParameter>(StringComparer.Ordinal);
        foreach (var metricId in item.Checkpoints.SelectMany(checkpoint => checkpoint.MetricIds).Distinct(StringComparer.Ordinal))
        {
            if (!editable.Contains(metricId))
            {
                continue;
            }

            parameters[metricId] = _configuration.Parameters.TryGetValue(metricId, out var parameter)
                ? Clone(parameter, SceneJsonContext.Default.SceneParameter)
                : new SceneParameter();
        }

        var model = _configuration.SkillModels is not null && _configuration.SkillModels.TryGetValue(itemId, out var existing)
            ? Clone(existing, SceneJsonContext.Default.SceneSkillModel)
            : null;
        return new SceneItemEdit(this, itemId, _revision, parameters, model);
    }

    public void CommitItemEdit(SceneItemEdit edit)
    {
        EnsureActiveEdit(edit);
        if (edit.Revision != _revision)
        {
            throw new InvalidOperationException("编辑期间配置或输入已更改，请重新打开 item 编辑器。");
        }

        var allowed = BeginItemEdit(edit.ItemId).Parameters.Keys.ToHashSet(StringComparer.Ordinal);
        if (!allowed.SetEquals(edit.Parameters.Keys))
        {
            throw new InvalidOperationException("编辑器中的结果字段与 item 不一致。");
        }

        // Stage every row before committing so malformed edits cannot partially change the workspace.
        var updated = Configuration;
        foreach (var (metricId, parameter) in edit.Parameters)
        {
            EnsureParameter(parameter, metricId);
            updated.Parameters[metricId] = Clone(parameter, SceneJsonContext.Default.SceneParameter);
        }

        if (edit.SkillModel is not null)
        {
            var model = Clone(edit.SkillModel, SceneJsonContext.Default.SceneSkillModel);
            if (Catalog.SchemaVersion == "3.0") { NormalizeModel(model); }
            EnsureSkillModel(model, edit.ItemId);
            updated.SkillModels ??= new(StringComparer.Ordinal);
            updated.SkillModels[edit.ItemId] = model;
        }
        else
        {
            updated.SkillModels?.Remove(edit.ItemId);
        }

        _configuration = updated;
        edit.Closed = true;
        InvalidateReport();
    }

    public void CancelItemEdit(SceneItemEdit edit)
    {
        EnsureActiveEdit(edit);
        edit.Closed = true;
    }

    public void LoadConfigurationJson(string json)
    {
        using var document = JsonDocument.Parse(NormalizeImportedConfiguration(json));
        var configuration = document.RootElement.Deserialize(SceneJsonContext.Default.SceneConfiguration)
            ?? throw new JsonException("配置文件为空。");
        EnsureIdentity(configuration.SchemaVersion, configuration.SceneId);
        if (configuration.Parameters is null)
        {
            throw new JsonException("parameters 必须是结果字段到参数的对象。");
        }

        foreach (var (metricId, parameter) in configuration.Parameters)
        {
            EnsureParameter(parameter, metricId);
            EnsureRawParameterKeys(document.RootElement.GetProperty("parameters").GetProperty(metricId), metricId);
        }

        if (configuration.SkillModels is not null)
        {
            foreach (var (itemId, model) in configuration.SkillModels)
            {
                if (configuration.SchemaVersion != "3.0"
                    && document.RootElement.GetProperty("skill_models").GetProperty(itemId).TryGetProperty("inference_method", out _))
                {
                    throw new JsonException($"skill_models.{itemId}.inference_method 仅适用于 3.0 配置。");
                }
                EnsureSkillModel(model, itemId);
            }
        }

        _configuration = configuration;
        InvalidateReport();
    }

    public string SaveConfigurationJson() => JsonSerializer.Serialize(_configuration, SceneJsonContext.Default.SceneConfiguration);

    private static string NormalizeImportedConfiguration(string json)
    {
        var root = JsonNode.Parse(json);
        if (root is not JsonObject configuration || configuration["schema_version"] is not JsonValue schema
            || !schema.TryGetValue<string>(out var schemaVersion) || schemaVersion != "3.0"
            || configuration["skill_models"] is not JsonObject models) { return json; }
        foreach (var entry in models)
        {
            if (entry.Value is not JsonObject model) { continue; }
            string? method = null;
            if (model["inference_method"] is { } methodNode
                && (methodNode is not JsonValue methodValue || !methodValue.TryGetValue(out method))) { continue; }
            if (method is null or "demo_normalized_grade_likelihood_v1")
            {
                model["inference_method"] = SceneSkillModel.CompensationInferenceMethod;
                if (!model.ContainsKey("compensation")) { model["compensation"] = new JsonObject { ["alpha"] = .2 }; }
                model.Remove("process_model");
            }
        }
        return configuration.ToJsonString();
    }

    private static void NormalizeModels(SceneConfiguration configuration)
    {
        if (configuration.SchemaVersion != "3.0" || configuration.SkillModels is null) { return; }
        foreach (var model in configuration.SkillModels.Values) { if (model is not null) { NormalizeModel(model); } }
    }

    private static void NormalizeModel(SceneSkillModel model)
    {
        if (model.InferenceMethod is null or "demo_normalized_grade_likelihood_v1")
        {
            model.InferenceMethod = SceneSkillModel.CompensationInferenceMethod;
            model.Compensation ??= new SceneCompensation { Alpha = .2 };
        }
    }

    public void LoadInputJson(string json)
    {
        using var document = JsonDocument.Parse(json);
        var input = document.RootElement.Deserialize(SceneJsonContext.Default.SceneInput)
            ?? throw new JsonException("输入文件为空。");
        EnsureIdentity(input.SchemaVersion, input.SceneId);
        if (input.SchemaVersion == "1.0"
            && (input.Results is null || document.RootElement.TryGetProperty("items", out _)))
        {
            throw new JsonException("1.0 输入必须包含 results，不能包含 2.0 的 items。");
        }

        if (input.SchemaVersion is "2.0" or "3.0")
        {
            if (document.RootElement.TryGetProperty("results", out _))
            {
                throw new JsonException($"{input.SchemaVersion} 输入不能包含旧版 results；请使用新输入模板。");
            }

            if (input.SchemaVersion == "3.0")
            {
                EnsureFrameInput(input, document.RootElement);
            }
            else
            {
                EnsureNestedInput(input, document.RootElement);
            }
        }

        _input = input;
        InvalidateReport();
    }

    public string SaveInputJson() => JsonSerializer.Serialize(_input, SceneJsonContext.Default.SceneInput);
    public string ExportInputTemplateJson() => JsonSerializer.Serialize(Catalog.InputTemplate, SceneJsonContext.Default.SceneInput);

    public void SetReport(SceneReport report)
    {
        ArgumentNullException.ThrowIfNull(report);
        EnsureIdentity(report.SchemaVersion, report.SceneId);
        if (!SameJson(report.Configuration, _configuration, SceneJsonContext.Default.SceneConfiguration)
            || !SameJson(report.Input, _input, SceneJsonContext.Default.SceneInput))
        {
            throw new InvalidOperationException("计算期间配置或输入已更改，此报告已失效，请重新计算。");
        }

        _report = Clone(report, SceneJsonContext.Default.SceneReport);
    }

    public string ExportReportJson() => _report is null
        ? throw new InvalidOperationException("没有当前报告，请先计算或重新计算。")
        : JsonSerializer.Serialize(_report, SceneJsonContext.Default.SceneReport);

    private void EnsureIdentity(string version, string sceneId)
    {
        if (version != Catalog.SchemaVersion || sceneId != Catalog.SceneId)
        {
            throw new JsonException($"文件的 schema_version 和 scene_id 必须为 {Catalog.SchemaVersion} / {Catalog.SceneId}。请使用当前场景导出的新模板；系统不会自动转换旧输入或容差。");
        }
    }

    private static void EnsureNestedInput(SceneInput input, JsonElement root)
    {
        if (input.Items is null || input.Results is not null)
        {
            throw new JsonException("2.0 输入必须包含 items，不能包含旧版 results；请使用新输入模板。");
        }

        foreach (var (itemId, item) in input.Items)
        {
            if (root.GetProperty("items").GetProperty(itemId).TryGetProperty("frames", out _))
            {
                throw new JsonException($"2.0 的 items.{itemId} 不能包含 3.0 的 frames。");
            }
            if (item?.Checkpoints is null)
            {
                throw new JsonException($"items.{itemId} 必须包含 checkpoints 对象。");
            }

            foreach (var (checkpointId, checkpoint) in item.Checkpoints)
            {
                if (checkpoint?.Values is null || checkpoint.Samples is null
                    || checkpoint.Samples.Any(sample => sample?.Values is null))
                {
                    throw new JsonException($"items.{itemId}.checkpoints.{checkpointId} 必须包含 values 对象和 samples 列表。");
                }

                if (checkpoint.Samples.Any(sample => !double.IsFinite(sample.StartS) || !double.IsFinite(sample.EndS)))
                {
                    throw new JsonException($"items.{itemId}.checkpoints.{checkpointId} 的 start_s 和 end_s 必须为有限数值。");
                }
            }
        }
    }

    private void EnsureFrameInput(SceneInput input, JsonElement root)
    {
        if (input.Items is null)
        {
            throw new JsonException("3.0 输入必须包含 items 对象；请使用当前场景导出的帧模板。");
        }

        var catalogItems = Catalog.Items.ToDictionary(item => item.ItemId, StringComparer.Ordinal);
        foreach (var (itemId, item) in input.Items)
        {
            if (!catalogItems.TryGetValue(itemId, out var definition))
            {
                throw new JsonException($"items.{itemId} 不属于当前场景。请使用当前场景导出的新模板，将原始帧整理到现有 item；系统不会自动合并旧 item 数据。");
            }
            if (item?.Frames is null)
            {
                throw new JsonException($"items.{itemId} 必须包含 frames 列表。");
            }
            if (root.GetProperty("items").GetProperty(itemId).TryGetProperty("checkpoints", out _))
            {
                throw new JsonException($"3.0 的 items.{itemId} 不能包含旧版 checkpoints；请使用当前帧模板。");
            }

            var phases = definition.Phases ?? [];
            var previousPhase = -1;
            double? previousTimestamp = null;
            var phaseCounts = new Dictionary<string, int>(StringComparer.Ordinal);
            foreach (var frame in item.Frames)
            {
                if (frame?.Values is null || frame.PhaseId is null)
                {
                    throw new JsonException($"items.{itemId}.frames 每帧必须包含 phase_id 和 values 对象。");
                }
                var phaseIndex = phases.FindIndex(phase => phase.PhaseId == frame.PhaseId);
                if (phaseIndex < 0 || phaseIndex < previousPhase)
                {
                    throw new JsonException($"items.{itemId}.frames 的 phase_id 必须属于该 item，且按场景阶段顺序排列。");
                }
                phaseCounts.TryGetValue(frame.PhaseId, out var count);
                if (phases[phaseIndex].SingleFrame && count > 0)
                {
                    throw new JsonException($"items.{itemId} 的 {frame.PhaseId} 阶段只允许一帧。");
                }
                phaseCounts[frame.PhaseId] = count + 1;
                previousPhase = phaseIndex;

                // Null is an intentional placeholder in an exported input template, never time zero.
                if (frame.TimestampS is not { } timestamp)
                {
                    continue;
                }
                if (!double.IsFinite(timestamp) || timestamp < 0
                    || (previousTimestamp is { } previous && timestamp <= previous))
                {
                    throw new JsonException($"items.{itemId}.frames 已填 timestamp_s 必须为非负有限数值，并在该 item 内严格递增。");
                }
                previousTimestamp = timestamp;
            }
        }
    }

    private void EnsureParameter(SceneParameter? parameter, string metricId)
    {
        if (parameter is null || parameter.Desired is null || parameter.Acceptable is null)
        {
            throw new JsonException($"parameters.{metricId} 必须包含 desired 和 acceptable 区间对象。");
        }

        var metric = Catalog.Metrics.FirstOrDefault(candidate => candidate.MetricId == metricId);
        if (metric is null || metric.Rule != "interval")
        {
            throw new JsonException($"parameters.{metricId} 不属于当前场景的可配置数值指标；请使用当前场景的配置模板。");
        }
        if (metric.Comparison == "route_3d")
        {
            EnsureRouteParameter(parameter, metricId);
            return;
        }
        if (parameter.RoutePoints is not null)
        {
            throw new JsonException($"parameters.{metricId} 不使用三维路线，不能包含 route_points。");
        }
        if (metric.TargetMode == "item_profile")
        {
            if (Catalog.SchemaVersion != "3.0" || string.IsNullOrWhiteSpace(metric.ReferenceOriginPhase)
                || metric.PhaseIds?.Contains(metric.ReferenceOriginPhase, StringComparer.Ordinal) != true)
            {
                throw new JsonException($"parameters.{metricId} 的共享参考曲线必须使用 3.0 帧数据，并在适用阶段中指定 reference_origin_phase。");
            }
            if (parameter.Expected is not null || parameter.ReferenceProfiles is not null)
            {
                throw new JsonException($"parameters.{metricId} 使用共享时间轴；expected 必须为空，不能包含分阶段的 reference_profiles。");
            }
            EnsureReferencePoints(parameter.ReferenceProfile, $"parameters.{metricId}.reference_profile");
            return;
        }
        if (parameter.ReferenceProfile is not null)
        {
            throw new JsonException($"parameters.{metricId} 不使用共享参考曲线，不能包含 reference_profile。");
        }
        if (metric.TargetMode != "phase_profile")
        {
            if (parameter.ReferenceProfiles is not null)
            {
                throw new JsonException($"parameters.{metricId} 使用固定目标，不能包含 reference_profiles。");
            }
            return;
        }

        if (parameter.Expected is not null)
        {
            throw new JsonException($"parameters.{metricId}.expected 必须为空；该字段使用各阶段的分段参考目标。");
        }
        var expectedPhases = (metric.PhaseIds ?? []).ToHashSet(StringComparer.Ordinal);
        if (parameter.ReferenceProfiles is null || !expectedPhases.SetEquals(parameter.ReferenceProfiles.Keys))
        {
            throw new JsonException($"parameters.{metricId}.reference_profiles 必须包含该指标的所有适用阶段，不能包含其他阶段。");
        }

        foreach (var (phaseId, points) in parameter.ReferenceProfiles)
        {
            EnsureReferencePoints(points, $"parameters.{metricId}.reference_profiles.{phaseId}");
        }
    }

    private static void EnsureReferencePoints(IReadOnlyList<SceneReferencePoint>? points, string path)
    {
        if (points is null)
        {
            throw new JsonException($"{path} 必须是参考节点列表；草稿可以暂时为空，完整评估前需至少两个完整节点。");
        }
        double? previousTime = null;
        for (var index = 0; index < points.Count; index++)
        {
            var point = points[index];
            if (point is null)
            {
                throw new JsonException($"{path}.{index} 必须包含 elapsed_s 和 expected。");
            }
            if (point.ElapsedS is { } time)
            {
                if (!double.IsFinite(time) || time < 0 || (index == 0 && time != 0)
                    || (previousTime is { } previous && time <= previous))
                {
                    throw new JsonException($"{path}.{index}.elapsed_s 已填时刻必须为非负有限值、严格递增，首节点从 0 秒开始。");
                }
                previousTime = time;
            }
            if (point.Expected is { } expected && !double.IsFinite(expected))
            {
                throw new JsonException($"{path}.{index}.expected 已填期望值必须为有限数值。");
            }
        }
    }

    private void EnsureRawParameterKeys(JsonElement parameter, string metricId)
    {
        var metric = Catalog.Metrics.Single(candidate => candidate.MetricId == metricId);
        var allowed = new HashSet<string>(StringComparer.Ordinal) { "expected", "desired", "acceptable" };
        if (metric.Comparison == "route_3d") { allowed.Add("route_points"); }
        else if (metric.Comparison == "radial") { allowed.UnionWith(["center_u", "center_v", "target_radius"]); }
        else if (metric.TargetMode == "phase_profile") { allowed.Add("reference_profiles"); }
        else if (metric.TargetMode == "item_profile") { allowed.Add("reference_profile"); }
        foreach (var property in parameter.EnumerateObject())
        {
            // Check presence before nullable DTO fields can erase obsolete or incompatible keys.
            if (!allowed.Contains(property.Name))
            {
                throw new JsonException($"parameters.{metricId}.{property.Name} 不属于该指标的配置字段，即使值为空也不能保留；请使用当前模板。");
            }
        }
    }

    private static void EnsureRouteParameter(SceneParameter parameter, string metricId)
    {
        var path = $"parameters.{metricId}";
        if (parameter.ReferenceProfiles is not null || parameter.ReferenceProfile is not null || parameter.CenterU is not null
            || parameter.CenterV is not null || parameter.TargetRadius is not null)
        {
            throw new JsonException($"{path} 使用三维路线，不能包含时间参考曲线或靶面几何参数。");
        }
        if (parameter.Expected is not null and not 0 || parameter.Desired.Lower is not null and not 0
            || parameter.Acceptable.Lower is not null and not 0
            || parameter.Desired.UnboundedUpper || parameter.Acceptable.UnboundedUpper)
        {
            throw new JsonException($"{path} 距路线距离目标和 D / A 下界必须为 0，且不支持无上限；未确定的值可以保留为空。");
        }
        foreach (var radius in new[] { parameter.Desired.Upper, parameter.Acceptable.Upper })
        {
            if (radius is { } value && (!double.IsFinite(value) || value < 0))
            {
                throw new JsonException($"{path} 已填 D / A 通道半径必须是非负有限数值。");
            }
        }
        if (parameter.Desired.Upper is { } desired && parameter.Acceptable.Upper is { } acceptable && desired >= acceptable)
        {
            throw new JsonException($"{path} D 通道半径必须小于 A 通道半径。");
        }
        if (parameter.RoutePoints is null)
        {
            throw new JsonException($"{path}.route_points 必须是路线节点列表；草稿可以暂时为空，完整评估前需至少两个完整节点。");
        }
        SceneRoutePoint? previous = null;
        for (var index = 0; index < parameter.RoutePoints.Count; index++)
        {
            var point = parameter.RoutePoints[index];
            if (point is null || new[] { point.XM, point.YM, point.HeightM }.Any(value => value is { } number && !double.IsFinite(number)))
            {
                throw new JsonException($"{path}.route_points.{index} 必须包含 X、Y 和高度；已填坐标必须为有限数值。");
            }
            if (point.XM.HasValue && point.YM.HasValue && point.HeightM.HasValue && previous is not null
                && point.XM == previous.XM && point.YM == previous.YM && point.HeightM == previous.HeightM)
            {
                throw new JsonException($"{path}.route_points.{index} 与前一节点重合，请删除重复节点或修改坐标。");
            }
            previous = point;
        }
    }

    private void EnsureActiveEdit(SceneItemEdit edit)
    {
        ArgumentNullException.ThrowIfNull(edit);
        if (edit.Owner != this || edit.Closed)
        {
            throw new InvalidOperationException("item 编辑会话已结束或不属于当前场景。");
        }
    }

    private void EnsureSkillModel(SceneSkillModel? model, string itemId)
    {
        var item = Catalog.Items.FirstOrDefault(candidate => candidate.ItemId == itemId)
            ?? throw new JsonException($"skill_models.{itemId} 不属于当前场景。请使用当前场景的配置模板重新设置模型；系统不会自动合并旧 CPT。");
        if (item.AssessmentKind == "checklist")
        {
            throw new JsonException($"skill_models.{itemId} 为检查单完成性检查，不使用技能 CPT。");
        }
        if (model is null || model.Prior is null || model.Prior.Count != 3
            || model.StateScores is null || model.StateScores.Count != 3 || model.CheckpointModels is null
            || model.ModelVersion is null || model.Calibration is null || model.ParameterSource is null)
        {
            throw new JsonException($"skill_models.{itemId} 必须包含模型来源、三个先验、三个状态分值及检查点模型。");
        }

        var compensationInference = model.InferenceMethod == SceneSkillModel.CompensationInferenceMethod;
        if (model.InferenceMethod is not null
            && (Catalog.SchemaVersion != "3.0"
                || !compensationInference))
        {
            throw new JsonException($"skill_models.{itemId}.inference_method 仅支持 3.0 的贝叶斯网络方法。");
        }
        EnsureDraftProbabilityRow(model.Prior, $"skill_models.{itemId}.prior");
        if (compensationInference)
        {
            if (model.Compensation?.Alpha is not { } alpha || !double.IsFinite(alpha) || alpha is < 0 or > 1)
            {
                throw new JsonException($"skill_models.{itemId}.compensation.alpha（更新系数 α）必须是 0 至 1 之间的有限数值。");
            }
        }
        else if (model.Compensation is not null)
        {
            throw new JsonException($"skill_models.{itemId}.compensation 仅用于贝叶斯网络方法。");
        }
        double? previousScore = null;
        foreach (var score in model.StateScores)
        {
            if (score is not { } filled)
            {
                continue;
            }
            if (!double.IsFinite(filled) || filled is < 0 or > 100)
            {
                throw new JsonException($"skill_models.{itemId}.state_scores 已填分值必须为0至100之间的有限数值。");
            }
            if (previousScore is { } previous && filled <= previous)
            {
                throw new JsonException($"skill_models.{itemId}.state_scores 已填分值必须满足低 < 中 < 高。");
            }
            previousScore = filled;
        }

        var checkpointIds = item.Checkpoints.Select(checkpoint => checkpoint.CheckpointId).ToHashSet(StringComparer.Ordinal);
        if (!checkpointIds.SetEquals(model.CheckpointModels.Keys))
        {
            throw new JsonException($"skill_models.{itemId} 的检查点与当前 item 不一致。请使用当前场景的配置模板重新设置模型；系统不会自动合并旧 CPT。");
        }

        var metrics = Catalog.Metrics.ToDictionary(metric => metric.MetricId, StringComparer.Ordinal);
        foreach (var checkpoint in item.Checkpoints)
        {
            var row = model.CheckpointModels[checkpoint.CheckpointId];
            string[] states = checkpoint.MetricIds.Any(id => metrics[id].Rule == "interval") ? ["D", "A", "U"] : ["D", "U"];
            if (row is null || row.States is null || !row.States.SequenceEqual(states)
                || row.Probabilities is null || row.Probabilities.Count != 3
                || row.Probabilities.Any(probabilities => probabilities is null || probabilities.Count != states.Length))
            {
                throw new JsonException($"skill_models.{itemId}.{checkpoint.CheckpointId} 的概率表形状或等级不正确。");
            }

            for (var index = 0; index < row.Probabilities.Count; index++)
            {
                EnsureDraftProbabilityRow(row.Probabilities[index],
                    $"skill_models.{itemId}.checkpoint_models.{checkpoint.CheckpointId}.probabilities.{index}", compensationInference);
            }
        }
    }

    private static void EnsureDraftProbabilityRow(IReadOnlyList<double?> row, string path, bool requirePositive = false)
    {
        var total = 0d;
        var complete = true;
        foreach (var probability in row)
        {
            if (probability is not { } filled)
            {
                complete = false;
                continue;
            }
            if (!double.IsFinite(filled) || filled is < 0 or > 1)
            {
                throw new JsonException($"{path} 已填概率必须为0至1之间的有限数值；尚未确定的值可以留空。");
            }
            if (requirePositive && filled == 0)
            {
                throw new JsonException($"{path} 演示推断的已填概率必须大于0；尚未确定的值可以留空。");
            }
            total += filled;
        }

        if (total > 1 + 1e-9 || (complete && Math.Abs(total - 1) > 1e-9))
        {
            throw new JsonException($"{path} 已填概率之和不能超过1，填齐后必须等于1；系统不会自动归一化。");
        }
    }

    private void InvalidateReport()
    {
        _revision++;
        _report = null;
    }

    private static T Clone<T>(T value, JsonTypeInfo<T> typeInfo) =>
        JsonSerializer.Deserialize(JsonSerializer.SerializeToUtf8Bytes(value, typeInfo), typeInfo)
        ?? throw new JsonException("无法复制场景数据。");

    private static bool SameJson<T>(T left, T right, JsonTypeInfo<T> typeInfo) => JsonElement.DeepEquals(
        JsonSerializer.SerializeToElement(left, typeInfo), JsonSerializer.SerializeToElement(right, typeInfo));
}
