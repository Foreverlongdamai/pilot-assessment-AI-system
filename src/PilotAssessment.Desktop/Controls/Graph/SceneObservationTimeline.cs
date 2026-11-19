using System.Globalization;
using System.Text.Json;

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

/// <summary>Shows the complete supplied frame series in one physical unit, with raw-coordinate tolerance bands.</summary>
public sealed class SceneObservationTimeline : UserControl
{
    private const double Left = 64, Right = 20, Top = 30, Bottom = 218;
    private readonly SceneMetricResult _result;
    private readonly SceneMetric _metric;
    private readonly IReadOnlyDictionary<string, string> _phaseNames;
    private readonly IReadOnlyList<SceneObservationProjection.Sample> _samples;
    private readonly IReadOnlyList<IReadOnlyList<int>> _runs;
    private readonly bool _boolean;
    private readonly Canvas _plot = new() { Height = 260, Background = Brush(Colors.White) };
    private readonly TextBlock _cursor = Label("移动指针或逐帧滑块查看真实观测值。", 12);
    private readonly ToolTip _tooltip = new();
    private readonly double _firstTime;
    private readonly double _lastTime;

    public SceneObservationTimeline(SceneMetricResult result, SceneMetric metric,
        IReadOnlyDictionary<string, string>? phaseNames = null, double? itemStartS = null, double? itemEndS = null)
    {
        _result = result;
        _metric = metric;
        _phaseNames = phaseNames ?? new Dictionary<string, string>();
        _boolean = metric.ValueType == "boolean" || metric.Comparison == "boolean";
        var parameter = result.Parameter;
        _samples = SceneObservationProjection.Build(result.Timeline, metric.Comparison,
            parameter?.Desired.Lower, Upper(parameter?.Desired), parameter?.Acceptable.Lower,
            Upper(parameter?.Acceptable), _boolean);
        _runs = SceneObservationProjection.ContinuousRuns(_samples);
        var times = _samples.Select(point => point.TimestampS).OfType<double>().ToArray();
        _firstTime = Finite(itemStartS) ?? (times.Length > 0 ? times.Min() : 0);
        _lastTime = Finite(itemEndS) ?? (times.Length > 0 ? times.Max() : _firstTime);

        var body = new StackPanel { Spacing = 8, HorizontalAlignment = HorizontalAlignment.Stretch };
        body.Children.Add(Label($"{metric.Name} · {(_boolean ? "检查状态" : AxisLabel)} · {result.Timeline.Count} 帧", 15, true));
        if (!_boolean)
        {
            var legend = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 16 };
            legend.Children.Add(Legend("实际值", Colors.Black, false));
            legend.Children.Add(Legend("期望", Colors.DimGray, true));
            legend.Children.Add(Legend("Desired", Color(205, 229, 203), false, true));
            legend.Children.Add(Legend("Acceptable", Color(255, 246, 204), false, true));
            legend.Children.Add(Label("U 带外", 12));
            body.Children.Add(legend);
        }
        body.Children.Add(Label(_boolean
            ? "按真实帧记录 true / false；缺失单独标记。"
            : "完整时间轴 · A / U 见底部标记 · 缺失、阶段切换处断开", 12));
        if (metric.Comparison == "radial")
        {
            body.Children.Add(Label("未命中只标记 U，不画虚构距离；原始命中坐标见逐帧明细。", 12));
        }
        _plot.SizeChanged += (_, _) => Draw();
        _plot.PointerMoved += OnPointerMoved;
        ToolTipService.SetToolTip(_plot, _tooltip);
        AutomationProperties.SetName(_plot, $"{metric.Name} · 完整观测时间轴");
        AutomationProperties.SetAutomationId(_plot, $"ObservationTimeline_{metric.MetricId}");
        body.Children.Add(new Border { Child = _plot, BorderBrush = Brush(Color(218, 223, 228)), BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(4) });
        if (_samples.Count > 0)
        {
            var slider = new Slider { Minimum = 0, Maximum = Math.Max(1, _samples.Count - 1), StepFrequency = 1,
                TickFrequency = 1, IsEnabled = _samples.Count > 1, HorizontalAlignment = HorizontalAlignment.Stretch };
            AutomationProperties.SetName(slider, $"{metric.Name} · 逐帧查看");
            AutomationProperties.SetAutomationId(slider, $"ObservationFrame_{metric.MetricId}");
            slider.ValueChanged += (_, args) => Inspect(Math.Clamp((int)Math.Round(args.NewValue), 0, _samples.Count - 1));
            body.Children.Add(slider);
            Inspect(0);
        }
        body.Children.Add(_cursor);
        body.Children.Add(SceneMetricTimeline.DetailExpander($"全部帧明细 · {result.Timeline.Count} 帧",
            Enumerable.Range(0, result.Timeline.Count).Select(PointDescription)));
        body.Children.Add(SceneMetricTimeline.DetailExpander($"A / U 记录 · {result.Timeline.Count(point => point.Grade is "A" or "U")} 帧",
            Enumerable.Range(0, result.Timeline.Count).Where(index => result.Timeline[index].Grade is "A" or "U").Select(PointDescription)));
        body.Children.Add(SceneMetricTimeline.DetailExpander("图表说明", Explanation()));
        Content = body;
    }

    private string AxisLabel => _metric.Comparison switch
    {
        "radial" => $"靶心距离 / {_metric.Unit}",
        "route_3d" => $"距路线距离 / {_metric.Unit}",
        "angle_degrees" => $"相对目标展开角 / {_metric.Unit}",
        _ => $"观测值 / {_metric.Unit}",
    };

    private IEnumerable<string> Explanation()
    {
        yield return "图中每个顶点对应一帧真实数据，直线仅连接相邻观测以帮助阅读；不使用平滑曲线、不补帧、不表示两帧之间已连续测量。逐帧滑块与完整明细保留全部帧。";
        yield return "各指标使用同一 item 的完整时间横轴；不适用阶段保留空白。绿色为 Desired 内带，淡黄色为 Acceptable 中除去 Desired 的部分；带外为 U。底部 A/U 标记依据后端实际分档，缺失/无结论为灰色。";
        if (_metric.Comparison == "angle_degrees")
        {
            yield return "为避免 359°→1° 被画成穿过整圈，显示值为展开后的目标角 + 后端最短角差；目标跨零时连续展开。原始角度保持不变，见逐帧明细。最短角差在 ±180° 分支切换处断线。";
        }
        else if (_metric.Comparison == "radial")
        {
            yield return "纵轴采用后端计算的靶心距离；原始 u/v 坐标、命中状态在明细中。未命中显示 U 标记，不伪造一个距离值；不能仅凭光点推断飞机位置。";
        }
        else if (_metric.Comparison == "route_3d")
        {
            yield return "纵轴采用后端给出的距预设路线距离，目标为零；原始 X/Y/高度、对应最近路线点和线段在明细中，不把三个坐标轴混画成一个观测值。";
        }
        else if (!_boolean)
        {
            yield return "容差带上下边界 = 该帧期望值 + 对应有符号容差。动态期望和色带跟随每帧后端结果；缺少目标或容差时不补零、不生成假色带。单帧只显示点与边界，不延伸成持续区间。";
        }
    }

    private void Draw()
    {
        _plot.Children.Clear();
        var width = _plot.ActualWidth;
        if (width < 180) { return; }
        if (_samples.Count == 0)
        {
            AddLabel("没有可绘制的逐帧记录。", Left, 90);
            return;
        }
        var first = _firstTime;
        var last = _lastTime;
        if (last <= first) { first -= .5; last += .5; }
        double X(double time) => Left + (time - first) / (last - first) * (width - Left - Right);
        var values = _samples.SelectMany(sample => new[] { sample.Observed, sample.Target,
            sample.DesiredLower, sample.DesiredUpper, sample.AcceptableLower, sample.AcceptableUpper })
            .OfType<double>().Where(double.IsFinite).ToArray();
        var low = values.Length > 0 ? values.Min() : -1;
        var high = values.Length > 0 ? values.Max() : 1;
        var padding = high == low ? Math.Max(Math.Abs(high) * .05, 1) : (high - low) * .1;
        low -= padding; high += padding;
        double Y(double value) => Bottom - (Math.Clamp(value, low, high) - low) / (high - low) * (Bottom - Top);

        if (!_boolean)
        {
            DrawBands(_runs, X, Y, false);
            DrawBands(_runs, X, Y, true);
            for (var tick = 0; tick <= 4; tick++)
            {
                var value = low + (high - low) * tick / 4;
                var y = Y(value);
                AddLabel(value.ToString("G4", CultureInfo.InvariantCulture), 3, y - 8);
                AddLine(Left, y, width - Right, y, Color(220, 226, 230), .6);
            }
            DrawSeries(_runs, sample => sample.Target, X, Y, true);
            DrawSeries(_runs, sample => sample.Observed, X, Y, false);
        }
        else
        {
            AddLabel("true", 7, 65); AddLabel("false", 7, 143);
            AddLine(Left, 74, width - Right, 74, Color(220, 226, 230), .8);
            AddLine(Left, 152, width - Right, 152, Color(220, 226, 230), .8);
            foreach (var sample in _samples.Where(sample => sample.TimestampS is not null && sample.BooleanValue is not null))
            {
                Dot(X(sample.TimestampS!.Value), sample.BooleanValue!.Value ? 74 : 152, 4, Colors.Black);
            }
        }
        AddLabel(_boolean ? "检查状态" : AxisLabel, Left, 5);
        for (var tick = 0; tick <= 4; tick++)
        {
            var time = first + (last - first) * tick / 4;
            AddLabel(time.ToString("G4", CultureInfo.InvariantCulture) + " s", Math.Clamp(X(time) - 18, 0, width - 70), 239);
        }
        var events = new Dictionary<string, PathGeometry> { ["A"] = new(), ["U"] = new(), ["?"] = new() };
        string? previousPhase = null;
        foreach (var sample in _samples)
        {
            if (sample.TimestampS is not { } time) { continue; }
            var x = X(time);
            if (sample.PhaseId != previousPhase)
            {
                previousPhase = sample.PhaseId;
                AddLine(x, Top, x, Bottom, Color(163, 172, 181), .7, true);
                if (!string.IsNullOrWhiteSpace(sample.PhaseId))
                {
                    AddLabel(_phaseNames.GetValueOrDefault(sample.PhaseId, sample.PhaseId), Math.Clamp(x + 3, Left, width - 85), Top + 2, 10);
                }
            }
            var grade = sample.Grade is "D" or "A" or "U" ? sample.Grade : "?";
            if (grade == "D") { continue; }
            var figure = new PathFigure { StartPoint = new Point(x, 224), IsFilled = false };
            figure.Segments.Add(new LineSegment { Point = new Point(x, 233) });
            events[grade].Figures.Add(figure);
        }
        foreach (var (grade, geometry) in events)
        {
            _plot.Children.Add(new Microsoft.UI.Xaml.Shapes.Path { Data = geometry, Stroke = Brush(grade switch
            { "A" => Color(177, 129, 0), "U" => Color(198, 40, 40), _ => Color(110, 118, 128) }), StrokeThickness = 1.6, IsHitTestVisible = false });
        }
        AddLabel("A/U", 24, 219, 10);
    }

    private void DrawBands(IReadOnlyList<IReadOnlyList<int>> runs, Func<double, double> x, Func<double, double> y, bool desired)
    {
        var geometry = new PathGeometry();
        foreach (var run in runs)
        {
            for (var position = 0; position < run.Count; position++)
            {
                var current = _samples[run[position]];
                var lower = desired ? current.DesiredLower : current.AcceptableLower;
                var upper = desired ? current.DesiredUpper : current.AcceptableUpper;
                if (lower is not { } lo || upper is not { } hi || lo > hi) { continue; }
                var px = x(current.TimestampS!.Value);
                if (run.Count == 1)
                {
                    AddLine(px, y(lo), px, y(hi), desired ? Color(143, 191, 143) : Color(232, 205, 111), 2);
                    continue;
                }
                if (position == 0) { continue; }
                var prior = _samples[run[position - 1]];
                var priorLower = desired ? prior.DesiredLower : prior.AcceptableLower;
                var priorUpper = desired ? prior.DesiredUpper : prior.AcceptableUpper;
                if (priorLower is not { } pLo || priorUpper is not { } pHi || pLo > pHi) { continue; }
                var startX = x(prior.TimestampS!.Value);
                var figure = new PathFigure { StartPoint = new Point(startX, y(pLo)), IsFilled = true, IsClosed = true };
                figure.Segments.Add(new LineSegment { Point = new Point(startX, y(pHi)) });
                figure.Segments.Add(new LineSegment { Point = new Point(px, y(hi)) });
                figure.Segments.Add(new LineSegment { Point = new Point(px, y(lo)) });
                geometry.Figures.Add(figure);
            }
        }
        _plot.Children.Add(new Microsoft.UI.Xaml.Shapes.Path { Data = geometry,
            Fill = Brush(desired ? Color(205, 229, 203) : Color(255, 246, 204)), IsHitTestVisible = false });
    }

    private void DrawSeries(IReadOnlyList<IReadOnlyList<int>> runs, Func<SceneObservationProjection.Sample, double?> select,
        Func<double, double> x, Func<double, double> y, bool target)
    {
        var geometry = new PathGeometry();
        foreach (var run in runs)
        {
            PathFigure? figure = null;
            foreach (var index in run)
            {
                var sample = _samples[index];
                if (select(sample) is not { } value || !double.IsFinite(value)) { figure = null; continue; }
                var point = new Point(x(sample.TimestampS!.Value), y(value));
                if (figure is null)
                {
                    figure = new PathFigure { StartPoint = point, IsFilled = false };
                    geometry.Figures.Add(figure);
                }
                else { figure.Segments.Add(new LineSegment { Point = point }); }
                if (run.Count == 1)
                {
                    if (target) { AddLine(point.X - 2, point.Y, point.X + 2, point.Y, Colors.DimGray, 1.5); }
                    else { Dot(point.X, point.Y, 3, Colors.Black); }
                }
            }
        }
        var path = new Microsoft.UI.Xaml.Shapes.Path { Data = geometry, Stroke = Brush(target ? Colors.DimGray : Colors.Black),
            StrokeThickness = target ? 1.3 : 1.8, IsHitTestVisible = false };
        if (target) { path.StrokeDashArray = [4, 3]; }
        _plot.Children.Add(path);
    }

    private void OnPointerMoved(object sender, PointerRoutedEventArgs args)
    {
        if (_samples.Count == 0 || _plot.ActualWidth <= Left + Right) { return; }
        var first = _firstTime == _lastTime ? _firstTime - .5 : _firstTime;
        var last = _firstTime == _lastTime ? _lastTime + .5 : _lastTime;
        var fraction = (args.GetCurrentPoint(_plot).Position.X - Left) / (_plot.ActualWidth - Left - Right);
        var index = SceneTimelineSelection.FindNearestFrame(_result.Timeline, first + fraction * (last - first));
        if (index >= 0) { Inspect(index); }
    }

    private void Inspect(int index)
    {
        _cursor.Text = "真实帧 · " + PointDescription(index);
        _tooltip.Content = _cursor.Text;
    }

    private string PointDescription(int index)
    {
        var point = _result.Timeline[index];
        var sample = _samples[index];
        var phase = _phaseNames.GetValueOrDefault(point.PhaseId ?? "", point.PhaseId ?? "未标注阶段");
        var text = $"{Number(point.TimestampS)} s · {phase} · 帧 {point.FrameIndex?.ToString(CultureInfo.InvariantCulture) ?? index.ToString(CultureInfo.InvariantCulture)}"
            + (_metric.TargetMode == "item_profile"
                ? $" · {(_metric.ReferenceOriginPhase == "acceleration" ? "加速开始后" : "参考曲线时间")} {Number(point.ReferenceElapsedS)} s" : "")
            + $" · 原值 {Raw(point.Value)}";
        if (!_boolean)
        {
            if (_metric.Comparison is "radial" or "route_3d")
            {
                text += $" · {(sample.State == "miss" ? "未命中，无距离值" : "距离 " + Number(sample.Observed) + " " + _metric.Unit)}";
                if (point.NearestRoutePoint is { } nearest)
                {
                    text += $" · 路线最近点 X {Number(nearest.XM)} / Y {Number(nearest.YM)} / 高度 {Number(nearest.HeightM)} m";
                }
                if (point.RouteSegmentIndex is { } segment) { text += $" · 路线第 {segment + 1} 段"; }
            }
            else
            {
                text += $" · 期望 {Number(point.Expected)} · 偏差 {Signed(point.Deviation)} {_metric.Unit}";
                if (sample.Angular) { text += $" · 相对目标展开显示 {Number(sample.Observed)}°"; }
            }
        }
        text += $" · {point.Grade ?? "无结论"}";
        return text + (string.IsNullOrWhiteSpace(point.Reason) ? "" : " · " + point.Reason);
    }

    private static string Raw(JsonElement? value) => value is null || value.Value.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined
        ? "缺失" : value.Value.GetRawText();
    private static double? Upper(SceneInterval? interval) => interval?.UnboundedUpper == true ? double.PositiveInfinity : interval?.Upper;
    private static double? Finite(double? value) => value is { } number && double.IsFinite(number) ? number : null;
    private static string Number(double? value) => value?.ToString("G", CultureInfo.InvariantCulture) ?? "未提供";
    private static string Signed(double? value) => (value > 0 ? "+" : "") + Number(value);
    private static Windows.UI.Color Color(byte red, byte green, byte blue) => ColorHelper.FromArgb(255, red, green, blue);
    private static SolidColorBrush Brush(Windows.UI.Color color) => new(color);

    private void Dot(double x, double y, double radius, Windows.UI.Color color)
    {
        var dot = new Ellipse { Width = radius * 2, Height = radius * 2, Fill = Brush(color), IsHitTestVisible = false };
        Canvas.SetLeft(dot, x - radius); Canvas.SetTop(dot, y - radius); _plot.Children.Add(dot);
    }

    private void AddLine(double x1, double y1, double x2, double y2, Windows.UI.Color color, double thickness, bool dashed = false)
    {
        var line = new Line { X1 = x1, Y1 = y1, X2 = x2, Y2 = y2, Stroke = Brush(color), StrokeThickness = thickness, IsHitTestVisible = false };
        if (dashed) { line.StrokeDashArray = [3, 3]; }
        _plot.Children.Add(line);
    }

    private void AddLabel(string text, double x, double y, double size = 11)
    {
        var label = Label(text, size); label.Foreground = Brush(Colors.Black); label.IsHitTestVisible = false;
        Canvas.SetLeft(label, x); Canvas.SetTop(label, y); _plot.Children.Add(label);
    }

    private static FrameworkElement Legend(string text, Windows.UI.Color color, bool dashed, bool band = false)
    {
        var body = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 5 };
        if (band) { body.Children.Add(new Rectangle { Width = 18, Height = 11, Fill = Brush(color), Stroke = Brush(Color(145, 157, 166)), StrokeThickness = .5 }); }
        else
        {
            var line = new Line { X1 = 0, X2 = 20, Y1 = 7, Y2 = 7, Width = 20, Height = 14, Stroke = Brush(color), StrokeThickness = 1.7 };
            if (dashed) { line.StrokeDashArray = [3, 2]; }
            body.Children.Add(line);
        }
        body.Children.Add(Label(text, 12));
        return body;
    }

    private static TextBlock Label(string text, double size = 14, bool semibold = false) => new()
    {
        Text = text, FontSize = size, TextWrapping = TextWrapping.Wrap,
        FontWeight = semibold ? Microsoft.UI.Text.FontWeights.SemiBold : Microsoft.UI.Text.FontWeights.Normal,
    };
}
