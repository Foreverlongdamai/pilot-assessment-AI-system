using System.Globalization;
using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using PilotAssessment.Desktop.Controls.Graph;
using PilotAssessment.Desktop.Core.SceneAssessment;
using PilotAssessment.Desktop.Core.State;

namespace PilotAssessment.Desktop.Views;

/// <summary>Independent, resizable view of one captured evaluation and its complete observation series.</summary>
public sealed class SceneItemReportWindow : Window
{
    private readonly SceneItemReportSnapshot _snapshot;
    private readonly IReadOnlyDictionary<string, string> _phaseNames;

    public SceneItemReportWindow(SceneItemReportSnapshot snapshot, ElementTheme theme)
    {
        _snapshot = snapshot;
        _phaseNames = (snapshot.Definition.Phases ?? []).ToDictionary(phase => phase.PhaseId, phase => phase.Name, StringComparer.Ordinal);
        Title = snapshot.WindowTitle;
        SystemBackdrop = new MicaBackdrop();
        AppWindow.Resize(new global::Windows.Graphics.SizeInt32(1180, 900));
        AppWindow.SetIcon(DesktopAssetLocator.AppIconPath(AppContext.BaseDirectory));

        var root = new Grid { RequestedTheme = theme, Padding = new Thickness(26, 22, 26, 18), RowSpacing = 18 };
        root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        root.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        var heading = new StackPanel { Spacing = 5 };
        heading.Children.Add(Text(snapshot.Item.Name, 28, true));
        heading.Children.Add(Text($"{snapshot.Catalog.SceneId} · {snapshot.Catalog.Name} · {snapshot.Item.ItemId}", 13));
        heading.Children.Add(Text($"评估快照：{snapshot.Report.EvaluatedAt} · 此窗口保留本次结果", 12));
        root.Children.Add(heading);
        var body = new StackPanel { Spacing = 18, Padding = new Thickness(0, 0, 12, 18) };
        body.Children.Add(Summary());
        var temporal = snapshot.Item.SkillQuantification?.TemporalAnalysis;
        if (temporal?.Method == SceneSkillModel.CompensationInferenceMethod && temporal.ItemTrace is { } process)
        {
            body.Children.Add(Card(new SceneTemporalEvidenceTimeline(process, _phaseNames, snapshot.StartS, snapshot.EndS)));
        }
        else if (temporal?.Method == SceneSkillModel.CompensationInferenceMethod)
        {
            body.Children.Add(Text(TemporalNotice(temporal), 13));
        }
        else
        {
            body.Children.Add(Text(snapshot.Item.SkillQuantification?.Status == "not_applicable"
                ? "检查单记录完成性，不计算操纵技能分数。"
                : "请重新评估以查看贝叶斯网络结果；已有规则和观测结果如下。", 13));
        }
        body.Children.Add(Text("检查点 · 展开查看完整观测", 21, true));
        foreach (var checkpoint in snapshot.Item.Checkpoints) { body.Children.Add(CheckpointCard(checkpoint)); }
        body.Children.Add(MethodDetails());
        var scroll = new ScrollViewer { Content = body, VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
            HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled };
        AutomationProperties.SetName(scroll, "item 评估结果，可滚动查看所有检查点");
        Grid.SetRow(scroll, 1); root.Children.Add(scroll); Content = root;
    }

    public string SceneId => _snapshot.Report.SceneId;
    public string ItemId => _snapshot.Item.ItemId;
    public string EvaluatedAt => _snapshot.Report.EvaluatedAt;

    private Border Summary()
    {
        var item = _snapshot.Item;
        var grid = new Grid { ColumnSpacing = 30 };
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        var rule = new StackPanel { Spacing = 6 };
        rule.Children.Add(Text("本次规则判定", 13));
        var grade = Text(Grade(item.Grade, item.Passed), 30, true);
        grade.Foreground = GradeBrush(item.Grade); rule.Children.Add(grade);
        rule.Children.Add(Text($"{item.Checkpoints.Count} 个检查点 · D / A 为 Pass，U 为 Fail", 12));
        grid.Children.Add(rule);
        var score = new StackPanel { Spacing = 6 };
        var quantification = item.SkillQuantification;
        score.Children.Add(Text("末帧模型概率对应分数", 13));
        score.Children.Add(Text(quantification?.Method == SceneSkillModel.CompensationInferenceMethod && quantification.Score is { } value
            ? value.ToString("0.0", CultureInfo.InvariantCulture) + " / 100" : "暂未提供", 30, true));
        score.Children.Add(Text(ScoreNotice(quantification), 12));
        Grid.SetColumn(score, 1); grid.Children.Add(score);
        return Card(grid);
    }

    private Expander CheckpointCard(SceneCheckpointResult checkpoint)
    {
        var definition = _snapshot.Definition.Checkpoints.Single(value => value.CheckpointId == checkpoint.CheckpointId);
        var header = new Grid { ColumnSpacing = 20, MinWidth = 500 };
        header.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        header.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        var label = new StackPanel { Spacing = 5 };
        label.Children.Add(Text(definition.Name, 17, true));
        var distribution = checkpoint.FrameDistribution;
        var note = $"{checkpoint.Metrics.Count} 项观测";
        if (distribution is not null)
        {
            note += $" · {distribution.ValidFrameCount} 帧有效";
            var unacceptable = distribution.Counts.GetValueOrDefault("U");
            if (unacceptable > 0) { note += $" · {unacceptable} 帧 U"; }
            if (distribution.MissingFrameCount > 0) { note += $" · {distribution.MissingFrameCount} 帧缺失"; }
        }
        label.Children.Add(Text(note, 12)); header.Children.Add(label);
        var grade = Text(checkpoint.Grade ?? "待补充", 20, true);
        grade.Foreground = GradeBrush(checkpoint.Grade); Grid.SetColumn(grade, 1); header.Children.Add(grade);
        var expander = new Expander { Header = header, HorizontalAlignment = HorizontalAlignment.Stretch,
            HorizontalContentAlignment = HorizontalAlignment.Stretch };
        AutomationProperties.SetName(expander, $"检查点 {definition.Name} · {checkpoint.Grade ?? "待补充"} · 展开完整观测");
        AutomationProperties.SetAutomationId(expander, "CheckpointReport_" + checkpoint.CheckpointId);
        expander.Expanding += (_, _) =>
        {
            if (expander.Content is not null) { return; }
            var content = new StackPanel { Spacing = 20 };
            content.Children.Add(Text(definition.Description, 13));
            var process = _snapshot.Item.SkillQuantification?.TemporalAnalysis?.CheckpointTraces
                .FirstOrDefault(trace => trace.CheckpointId == checkpoint.CheckpointId);
            if (process?.Method == SceneSkillModel.CompensationInferenceMethod)
            {
                content.Children.Add(new SceneTemporalEvidenceTimeline(process, _phaseNames, _snapshot.StartS, _snapshot.EndS));
            }
            foreach (var result in checkpoint.Metrics)
            {
                var metric = _snapshot.Catalog.Metrics.Single(value => value.MetricId == result.MetricId);
                if (result.Timeline.Count > 0)
                {
                    content.Children.Add(new SceneObservationTimeline(result, metric, _phaseNames, _snapshot.StartS, _snapshot.EndS));
                }
                else
                {
                    content.Children.Add(Text($"{metric.Name}：{result.Value?.ToString() ?? "未提供"} · {result.Grade ?? "无结论"}", 15, true));
                    if (!string.IsNullOrWhiteSpace(result.Reason)) { content.Children.Add(Text(result.Reason, 12)); }
                }
            }
            content.Children.Add(SceneMetricTimeline.DetailExpander("检查依据与场景适配",
                definition.Sources.Select(source => $"{source.Document} · {source.Clause} · {source.Support}\n{source.Note}")));
            expander.Content = content;
        };
        return expander;
    }

    private Expander MethodDetails()
    {
        var quantification = _snapshot.Item.SkillQuantification;
        var lines = new List<string>
        { "概率过程用于回看本次任务，不代表经过验证的学习进度。规则 Fail 独立保留。" };
        lines.Add("贝叶斯网络使用上一帧更新后的概率作为先验，根据本帧检查点观测更新能力概率。分数由更新后的概率换算，最终值与过程末点一致。");
        if (!string.IsNullOrWhiteSpace(quantification?.Message)) { lines.Add(quantification.Message); }
        if (quantification?.ModelVersion is { } version) { lines.Add("参数版本：" + version); }
        if (quantification?.TemporalAnalysis is { Method: SceneSkillModel.CompensationInferenceMethod } temporal)
        {
            lines.Add("概率分数曲线配合逐帧 D/A/U 色带展示。悬停指针或展开明细可查看先验、CPT 观测更新、观测目标、概率调整量与更新后概率。检查点单独更新；item 使用检查点的原始 CPT 证据，不加权检查点分数。");
            lines.Add(TemporalNotice(temporal));
            lines.AddRange(temporal.Warnings);
        }
        lines.AddRange(quantification?.Warnings ?? []);
        return SceneMetricTimeline.DetailExpander("评分方法与参数说明", lines);
    }

    private static Border Card(UIElement child) => new()
    {
        Child = child, Padding = new Thickness(20), CornerRadius = new CornerRadius(10), BorderThickness = new Thickness(1),
        Background = (Brush)Application.Current.Resources["LayerFillColorDefaultBrush"],
        BorderBrush = (Brush)Application.Current.Resources["ControlStrokeColorDefaultBrush"],
    };

    private static Brush GradeBrush(string? grade) => new SolidColorBrush(grade switch
    {
        "U" => ColorHelper.FromArgb(255, 181, 36, 43), "A" => ColorHelper.FromArgb(255, 130, 91, 0),
        "D" => ColorHelper.FromArgb(255, 16, 117, 72), _ => Colors.Gray,
    });
    private static string TemporalNotice(SceneTemporalAnalysis temporal) => (temporal.Status switch
    {
        "not_applicable" => "检查单记录完成性，不进行连续操纵能力的时序推断。",
        "not_configured" => "尚未填写贝叶斯网络参数，可在 item 模型编辑器中配置。",
        "invalid_model" => "贝叶斯网络参数无效；规则结果保留，模型概率与分数未计算。",
        "blocked" => "输入或规则参数不完整，未生成时序证据。",
        "partial" => "时序过程证据不完整，仅展示已有结果。",
        _ => "时序过程分析使用未标定模型假设。",
    }) + (string.IsNullOrWhiteSpace(temporal.Message) ? "" : "\n" + temporal.Message);
    private static string ScoreNotice(SceneSkillQuantification? quantification) => quantification?.Status switch
    {
        "not_applicable" => "检查单不设置技能分数",
        "pending_method" => "请补齐逐帧模型参数并重新评估",
        "not_configured" or null => "尚未设置技能量化模型",
        "invalid_model" => "模型参数无效 · 未计算分数",
        "partial" or "no_evidence" => "证据不完整 · 尚无最终分数",
        _ when quantification.Method == SceneSkillModel.CompensationInferenceMethod => "贝叶斯网络 · 参数未标定 · 分数不改变 P/F",
        _ => "请重新评估以获得当前模型分数",
    };
    private static string Grade(string? grade, bool? passed) => grade is null ? "结果待补充"
        : $"{grade} / {(passed == false ? "Fail" : passed == true ? "Pass" : "待补充")}";
    private static TextBlock Text(string text, double size = 14, bool bold = false) => new()
    {
        Text = text, FontSize = size, TextWrapping = TextWrapping.Wrap,
        FontWeight = bold ? Microsoft.UI.Text.FontWeights.SemiBold : Microsoft.UI.Text.FontWeights.Normal,
    };
}
