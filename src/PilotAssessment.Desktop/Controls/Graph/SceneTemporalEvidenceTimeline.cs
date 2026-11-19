using System.Globalization;
using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using PilotAssessment.Desktop.Core.SceneAssessment;
using Windows.Foundation;

namespace PilotAssessment.Desktop.Controls.Graph;

/// <summary>Displays backend temporal posteriors and actual frame grades on complete time axes.</summary>
public sealed class SceneTemporalEvidenceTimeline : UserControl
{
    private const double Left = 66, Right = 20, Top = 27, Bottom = 197;
    private const string CursorHint = "移动指针查看最近真实帧的时间、阶段、D/A/U、后验概率和期望分值。";
    private readonly SceneTemporalTrace _trace;
    private readonly IReadOnlyDictionary<string, string> _phaseNames;
    private readonly Canvas _posteriorPlot = Plot();
    private readonly Canvas _gradePlot = new() { Height = 92, Background = new SolidColorBrush(Colors.White) };
    private readonly TextBlock _cursor = Label(CursorHint, 12);
    private readonly double _start;
    private readonly double _end;

    public SceneTemporalEvidenceTimeline(SceneTemporalTrace trace, IReadOnlyDictionary<string, string> phaseNames,
        double? startS = null, double? endS = null)
    {
        _trace = trace;
        _phaseNames = phaseNames;
        var first = startS ?? trace.Timeline.FirstOrDefault()?.TimestampS ?? 0;
        var last = endS ?? trace.Timeline.LastOrDefault()?.TimestampS ?? first;
        (_start, _end) = SceneItemCumulativeSelection.PlotTimeRange(first, last);
        var body = new StackPanel { Spacing = 9 };
        var scope = trace.CheckpointId is null ? "整项" : "检查点";
        body.Children.Add(Label(scope + "贝叶斯网络", 19, true));
        body.Children.Add(Label("过程证据：" + (trace.Status switch
        {
            "complete" => "完整", "partial" => "部分，仍可查看已提供的过程", _ => "尚无有效证据",
        }) + " · 模型未标定", 12));
        body.Children.Add(Label("贝叶斯网络根据每帧观测更新低 / 中 / 高概率，纵轴展示对应分数。整项曲线终点与上方末帧分数一致，不是整段平均质量；恢复后的高分不会消除此前的 U 或 Fail。", 12));
        body.Children.Add(Label("下方色带显示每帧实际表现。阶段和缺失处断线；已知 D/A/U 即使没有有效后验也仍然显示。", 12));
        if (trace.Timeline.Count == 0) { body.Children.Add(Label("当前没有可绘制的过程时刻。", 13)); }
        ConfigurePlot(_posteriorPlot, "TemporalPosterior_" + (trace.CheckpointId ?? "item"), scope + "时序后验期望，完整真实时间轴", false);
        body.Children.Add(_posteriorPlot);
        body.Children.Add(Label("逐帧表现 · D / A / U", 16, true));
        if (trace.CheckpointId is null)
        {
            body.Children.Add(Label("整项色带取当帧适用检查点的综合档位：任一 U 为 U；无 U 但必需观测缺失为灰色；观测完整时取最差档。", 12));
        }
        var legend = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 18 };
        foreach (var (grade, text) in new[] { ("D", "D · Desired"), ("A", "A · Acceptable"), ("U", "U · Unacceptable"), ("missing", "缺测") })
        {
            var entry = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6 };
            entry.Children.Add(new Rectangle { Width = 12, Height = 12, Fill = GradeBrush(grade), VerticalAlignment = VerticalAlignment.Center });
            entry.Children.Add(Label(text, 12));
            legend.Children.Add(entry);
        }
        body.Children.Add(legend);
        ConfigurePlot(_gradePlot, "TemporalGrades_" + (trace.CheckpointId ?? "item"), scope + "逐帧表现色带，绿D黄A红U，灰色缺测，不适用留白", true);
        body.Children.Add(_gradePlot);
        body.Children.Add(Label("色块仅标记真实帧，不代表观测持续时间；缺测为灰色，不适用和时间空档留白。", 12));
        body.Children.Add(_cursor);
        var advanced = new List<string> { "每帧明细记录更新前先验、CPT 观测更新、观测目标、概率调整量和更新后概率。所有概率按低 / 中 / 高排列；概率调整量是更新后概率与 CPT 观测更新结果之差。" };
        if (!string.IsNullOrWhiteSpace(trace.Message)) { advanced.Add(trace.Message); }
        advanced.AddRange(trace.Timeline.Select(point => Describe(point, advanced: true)));
        body.Children.Add(SceneMetricTimeline.DetailExpander($"高级过程明细 · {trace.Timeline.Count} 个真实时刻", advanced));
        Content = body;
    }

    private void ConfigurePlot(Canvas plot, string id, string name, bool grades)
    {
        AutomationProperties.SetAutomationId(plot, id);
        AutomationProperties.SetName(plot, name);
        plot.SizeChanged += (_, _) => { if (grades) { DrawGradeBand(plot); } else { DrawPosterior(plot); } };
        plot.PointerMoved += OnPointerMoved;
        plot.PointerExited += (_, _) => _cursor.Text = CursorHint;
        ToolTipService.SetToolTip(plot, new ToolTip { Content = CursorHint });
    }

    private void DrawPosterior(Canvas plot)
    {
        plot.Children.Clear();
        var width = plot.ActualWidth;
        if (width < 180 || !double.IsFinite(_start) || !double.IsFinite(_end) || _end <= _start) { return; }
        var runs = SceneTemporalTraceSelection.ContinuousRuns(_trace.Timeline);
        double X(double time) => Left + (time - _start) / (_end - _start) * (width - Left - Right);
        static double Y(double value) => Bottom - value / 100 * (Bottom - Top);
        for (var tick = 0; tick <= 4; tick++)
        {
            var value = tick * 25;
            AddLabel(plot, value.ToString("0", CultureInfo.InvariantCulture), 4, Y(value) - 8);
            plot.Children.Add(new Line { X1 = Left, X2 = width - Right, Y1 = Y(value), Y2 = Y(value),
                Stroke = new SolidColorBrush(Colors.LightGray), StrokeThickness = .7,
                IsHitTestVisible = false });
            var time = _start + (_end - _start) * tick / 4;
            AddLabel(plot, time.ToString("0.###", CultureInfo.InvariantCulture) + " s", Math.Clamp(X(time) - 18, 0, width - 72), 207);
        }
        string? phase = null;
        foreach (var point in _trace.Timeline)
        {
            if (!double.IsFinite(point.TimestampS) || point.PhaseId == phase) { continue; }
            phase = point.PhaseId;
            var x = X(point.TimestampS);
            plot.Children.Add(new Line { X1 = x, X2 = x, Y1 = Top, Y2 = Bottom,
                Stroke = new SolidColorBrush(Colors.Silver), StrokeDashArray = [3, 3], StrokeThickness = 1, IsHitTestVisible = false });
            AddLabel(plot, _phaseNames.GetValueOrDefault(phase, phase), Math.Clamp(x + 3, Left, width - 125), 3);
        }
        var geometry = new PathGeometry();
        foreach (var run in runs)
        {
            var first = _trace.Timeline[run[0]];
            if (run.Count == 1)
            {
                var dot = new Ellipse { Width = 4, Height = 4, Fill = new SolidColorBrush(Colors.RoyalBlue), IsHitTestVisible = false };
                Canvas.SetLeft(dot, X(first.TimestampS) - 2); Canvas.SetTop(dot, Y(first.Score!.Value) - 2); plot.Children.Add(dot);
                continue;
            }
            var figure = new PathFigure { StartPoint = new Point(X(first.TimestampS), Y(first.Score!.Value)), IsClosed = false, IsFilled = false };
            foreach (var index in run.Skip(1))
            {
                var point = _trace.Timeline[index];
                figure.Segments.Add(new LineSegment { Point = new Point(X(point.TimestampS), Y(point.Score!.Value)) });
            }
            geometry.Figures.Add(figure);
        }
        AddPath(plot, geometry, Colors.RoyalBlue, 2);
    }

    private void DrawGradeBand(Canvas plot)
    {
        plot.Children.Clear();
        var width = plot.ActualWidth;
        if (width < 180 || !double.IsFinite(_start) || !double.IsFinite(_end) || _end <= _start) { return; }
        double X(double time) => Left + (time - _start) / (_end - _start) * (width - Left - Right);
        var cells = SceneTemporalTraceSelection.GradeCells(_trace.Timeline);
        // Every frame remains in the geometry. Draw U last so a sparse failure is
        // not hidden by neighbouring D markers when many frames share a pixel.
        foreach (var grade in new[] { "missing", "D", "A", "U" })
        {
            var geometry = new GeometryGroup { FillRule = FillRule.Nonzero };
            foreach (var cell in cells.Where(cell => cell.Grade == grade))
            {
                var start = X(cell.StartS);
                var end = X(cell.EndS);
                if (end - start < 1.5)
                {
                    var center = X(_trace.Timeline[cell.PointIndex].TimestampS);
                    start = center - .75;
                    end = center + .75;
                }
                start = Math.Clamp(start, Left, width - Right);
                end = Math.Clamp(end, Left, width - Right);
                geometry.Children.Add(new RectangleGeometry { Rect = new Rect(start, 28, Math.Max(.5, end - start), 28) });
            }
            plot.Children.Add(new Microsoft.UI.Xaml.Shapes.Path { Data = geometry, Fill = GradeBrush(grade), IsHitTestVisible = false });
        }
        string? phase = null;
        foreach (var point in _trace.Timeline)
        {
            if (!double.IsFinite(point.TimestampS) || point.PhaseId == phase) { continue; }
            phase = point.PhaseId;
            var x = X(point.TimestampS);
            plot.Children.Add(new Line { X1 = x, X2 = x, Y1 = 24, Y2 = 61,
                Stroke = new SolidColorBrush(Colors.Gray), StrokeThickness = .7, StrokeDashArray = [2, 2], IsHitTestVisible = false });
            AddLabel(plot, _phaseNames.GetValueOrDefault(phase, phase), Math.Clamp(x + 3, Left, width - 125), 3);
        }
        for (var tick = 0; tick <= 4; tick++)
        {
            var time = _start + (_end - _start) * tick / 4;
            AddLabel(plot, time.ToString("0.###", CultureInfo.InvariantCulture) + " s", Math.Clamp(X(time) - 18, 0, width - 72), 67);
        }
    }

    private void OnPointerMoved(object sender, PointerRoutedEventArgs args)
    {
        var plot = (Canvas)sender;
        if (plot.ActualWidth <= Left + Right) { return; }
        var time = _start + (args.GetCurrentPoint(plot).Position.X - Left) / (plot.ActualWidth - Left - Right) * (_end - _start);
        var index = SceneTemporalTraceSelection.FindNearestPoint(_trace.Timeline, time);
        if (index < 0) { return; }
        _cursor.Text = "最近真实帧：" + Describe(_trace.Timeline[index]);
        if (ToolTipService.GetToolTip(plot) is ToolTip tooltip) { tooltip.Content = _cursor.Text; }
    }

    private string Describe(SceneTemporalPoint point, bool advanced = false)
    {
        var grade = SceneTemporalTraceSelection.DisplayGrade(point) switch
        {
            "missing" => "缺测", null => "不适用 / 无观察", var known => known,
        };
        var text = $"{point.TimestampS.ToString("G", CultureInfo.InvariantCulture)} s · {_phaseNames.GetValueOrDefault(point.PhaseId, point.PhaseId)} · 帧 {point.FrameIndex} · {grade}";
        text += point.Score is { } score ? $"\n时序后验期望 {score.ToString("0.00", CultureInfo.InvariantCulture)} / 100" : "\n时序后验暂无结论";
        if (point.Posterior is { Count: 3 } posterior)
        {
            text += " · 低 / 中 / 高 " + string.Join(" / ", posterior.Select(value => (value * 100).ToString("0.###", CultureInfo.InvariantCulture) + "%"));
        }
        if (_trace.Method == SceneSkillModel.CompensationInferenceMethod)
        {
            if (point.Prior is { Count: 3 } prior) { text += "\n更新前先验：" + Probabilities(prior); }
            if (point.BayesPosterior is { Count: 3 } bayes) { text += "\nCPT 观测更新：" + Probabilities(bayes); }
            if (point.CompensationAlpha is { } alpha) { text += $"\n更新系数 α = {alpha.ToString("0.####", CultureInfo.InvariantCulture)}"; }
            if (point.CompensationTarget is { Count: 3 } target) { text += " · 观测目标：" + Probabilities(target); }
            if (point.CompensationDelta is { Count: 3 } delta)
            {
                text += "\n概率调整量（百分点）：" + string.Join(" / ", delta.Select(value => (value * 100).ToString("+0.###;-0.###;0", CultureInfo.InvariantCulture)));
            }
            if (point.Posterior is { Count: 3 } updated) { text += "\n更新后概率：" + Probabilities(updated); }
        }
        if (!advanced) { return text; }
        text += point.LogBayesFactorHighLow is { } evidence ? $"\n本帧 log BF（高/低）{evidence.ToString("+0.000;-0.000;0", CultureInfo.InvariantCulture)}" : "\n本帧新增证据未计算";
        var update = point.UpdateKind switch { "bayes_compensation" => "贝叶斯网络更新", "initial" => "初始观察", "transition" => "条件转移", "phase_initial" => "阶段/适用性起点",
            "mixed" => "混合证据", "missing" => "缺失", _ => "无新证据" };
        text += $" · {update} · 本帧有效证据 {point.EvidenceCount} · 已观察 {point.ObservedCheckpointCount}/{point.ExpectedCheckpointCount} 个检查点";
        return text;
    }

    private static string Probabilities(IReadOnlyList<double> values) => string.Join(" / ",
        values.Select(value => (value * 100).ToString("0.###", CultureInfo.InvariantCulture) + "%"));

    private static Canvas Plot() => new() { Height = 235, Background = new SolidColorBrush(Colors.White) };
    private static Brush GradeBrush(string grade) => new SolidColorBrush(grade switch
    {
        "D" => ColorHelper.FromArgb(255, 27, 143, 100),
        "A" => ColorHelper.FromArgb(255, 212, 167, 44),
        "U" => ColorHelper.FromArgb(255, 195, 63, 72),
        _ => ColorHelper.FromArgb(255, 135, 149, 155),
    });
    private static void AddPath(Canvas plot, PathGeometry geometry, Windows.UI.Color color, double thickness) =>
        plot.Children.Add(new Microsoft.UI.Xaml.Shapes.Path { Data = geometry, Stroke = new SolidColorBrush(color), StrokeThickness = thickness, IsHitTestVisible = false });
    private static void AddLabel(Canvas plot, string text, double x, double y)
    {
        var label = Label(text, 11);
        label.Foreground = new SolidColorBrush(Colors.DimGray);
        label.IsHitTestVisible = false;
        Canvas.SetLeft(label, x); Canvas.SetTop(label, y); plot.Children.Add(label);
    }
    private static TextBlock Label(string text, double size, bool bold = false) => new()
    {
        Text = text, FontSize = size, TextWrapping = TextWrapping.Wrap,
        FontWeight = bold ? Microsoft.UI.Text.FontWeights.SemiBold : Microsoft.UI.Text.FontWeights.Normal,
    };
}
