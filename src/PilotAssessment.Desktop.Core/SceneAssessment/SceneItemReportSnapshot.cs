using System.Text.Json;

namespace PilotAssessment.Desktop.Core.SceneAssessment;

/// <summary>Owns one immutable-by-convention evaluation snapshot for an independent results window.</summary>
public sealed class SceneItemReportSnapshot
{
    public SceneItemReportSnapshot(SceneCatalog catalog, SceneReport report, string itemId)
    {
        ArgumentNullException.ThrowIfNull(catalog);
        ArgumentNullException.ThrowIfNull(report);
        if (catalog.SceneId != report.SceneId || catalog.SchemaVersion != report.SchemaVersion)
        {
            throw new ArgumentException("评估结果不属于当前场景或版本。", nameof(report));
        }
        if (!catalog.Items.Any(item => item.ItemId == itemId) || !report.Items.Any(item => item.ItemId == itemId))
        {
            throw new ArgumentException("评估快照不包含此 item。", nameof(itemId));
        }

        Catalog = JsonSerializer.Deserialize(JsonSerializer.SerializeToUtf8Bytes(catalog, SceneJsonContext.Default.SceneCatalog),
            SceneJsonContext.Default.SceneCatalog)!;
        Report = JsonSerializer.Deserialize(JsonSerializer.SerializeToUtf8Bytes(report, SceneJsonContext.Default.SceneReport),
            SceneJsonContext.Default.SceneReport)!;
        Definition = Catalog.Items.Single(item => item.ItemId == itemId);
        Item = Report.Items.Single(item => item.ItemId == itemId);
        var times = Report.Input.Items?.GetValueOrDefault(itemId)?.Frames?
            .Select(frame => frame.TimestampS).Where(time => time.HasValue && double.IsFinite(time.Value))
            .Select(time => time!.Value).ToArray() ?? [];
        if (times.Length > 0)
        {
            StartS = times.Min();
            EndS = times.Max();
        }
        var evaluatedAt = string.IsNullOrWhiteSpace(Report.EvaluatedAt) ? "评估时间未记录" : Report.EvaluatedAt;
        WindowTitle = $"{Catalog.SceneId} · {Item.Name} · {evaluatedAt} · 评估结果";
    }

    public SceneCatalog Catalog { get; }
    public SceneReport Report { get; }
    public SceneItem Definition { get; }
    public SceneItemResult Item { get; }
    public double? StartS { get; }
    public double? EndS { get; }
    public string WindowTitle { get; }
}
