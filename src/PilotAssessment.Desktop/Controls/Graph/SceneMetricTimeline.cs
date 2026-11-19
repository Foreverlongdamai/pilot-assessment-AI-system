using System.Globalization;
using System.Text.Json;

using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Markup;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using Windows.Foundation;

using PilotAssessment.Desktop.Core.SceneAssessment;

namespace PilotAssessment.Desktop.Controls.Graph;

/// <summary>Displays supplied assessment results without inventing samples or recalculating grades.</summary>
public sealed class SceneMetricTimeline : UserControl
{
    private const int DrawingLimit = 1800;
    private readonly SceneMetricResult _result;
    private readonly string _unit;
    private readonly bool _frameBased;
    private readonly bool _radial;
    private readonly bool _route;
    private readonly IReadOnlyDictionary<string, string> _phaseNames;
    private readonly Canvas _plot = new() { Height = 310 };
    private readonly TextBlock _cursor = Label("");
    private double _firstTime;
    private double _lastTime;

    public SceneMetricTimeline(SceneMetricResult result, SceneMetric definition, bool frameBased, IReadOnlyDictionary<string, string> phaseNames)
    {
        _result = result;
        _unit = definition.Unit;
        _frameBased = frameBased;
        _radial = definition.Comparison == "radial";
        _route = definition.Comparison == "route_3d";
        _phaseNames = phaseNames;
        _cursor.Text = CursorHint;
        var body = new StackPanel { Spacing = 10 };
        body.Children.Add(Label($"{(_route ? "三维位置与距路线距离" : _radial ? "命中坐标与靶心距离" : "原值 / 目标与有符号偏差")} · {_result.Timeline.Count} {(_frameBased ? "帧" : "个输入时段")}", 15, true));
        body.Children.Add(Label(_frameBased
            ? "横轴：每帧提供的飞行相对秒。图点仅表示该帧；不连接、不延长为时间段。底部短标记表示每帧档位。"
            : "横轴：飞行相对秒。每条水平线对应上游给出的 [开始, 结束) 时段；不连接缺测间隔。", 12));
        body.Children.Add(Label(_route
            ? "上图：实际 X 为蓝色、Y 为紫色、高度为青色；细虚线标记是该帧对应的路线最近点，不是按时刻规定的目标。下图：三维位置到路线的距离，D 绿 / A 黄 / U 红。"
            : _radial
            ? "上图：命中 u 坐标为蓝色，v 坐标为紫色，靶心为对应虚线；下图：计算器给出的靶心距离，D 绿 / A 黄 / U 红。"
            : "颜色：D 绿色 · A 黄色 · U 红色；目标为虚线。完整档位同时列在明细中。", 12));
        if (_result.Timeline.Count > DrawingLimit)
        {
            body.Children.Add(Label($"绘图按时间分组保留首尾、最大/最小偏差与最差档代表，最多 {DrawingLimit} 个点；完整明细、计算和导出保留全部记录。", 12));
        }
        _plot.Background = new SolidColorBrush(Colors.Transparent);
        _plot.SizeChanged += (_, _) => Draw();
        _plot.PointerMoved += OnPointerMoved;
        _plot.PointerExited += (_, _) => _cursor.Text = CursorHint;
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(_plot, "原始值与目标及偏差时序图，完整数值可展开明细查看");
        body.Children.Add(_plot);
        body.Children.Add(_cursor);
        body.Children.Add(_frameBased ? FrameDistributionView(result.FrameDistribution) : DistributionView(result.Distribution));
        body.Children.Add(DetailExpander(_frameBased ? "全部帧明细 · 时间 / 阶段 / 原值 / 目标 / 偏差 / 档位" : "全部时段明细 · 时间 / 原值 / 目标 / 偏差 / 档位",
            _result.Timeline.Select(PointDescription)));
        if (_frameBased)
        {
            body.Children.Add(DetailExpander($"A / U 异常帧 · {_result.Timeline.Count(point => point.Grade is "A" or "U")} 帧",
                _result.Timeline.Where(point => point.Grade is "A" or "U").Select(PointDescription)));
        }
        else
        {
            var episodes = result.Episodes ?? [];
            body.Children.Add(DetailExpander($"A / U 事件明细 · {episodes.Count} 段",
                episodes.Select(episode => $"{episode.Grade}    [{Number(episode.StartS)}, {Number(episode.EndS)}) s    持续 {Number(episode.DurationS)} s    最大绝对偏差 {Number(episode.MaxAbsDeviation)} {_unit}")));
        }
        Content = body;
        ActualThemeChanged += (_, _) => Draw();
    }

    private string CursorHint => _frameBased ? "移动指针查看最近真实帧的时间、原值和档位。" : "移动指针查看该时段的原值、目标、偏差和档位。";

    private string PointDescription(SceneMetricTimePoint point)
    {
        var position = _frameBased
            ? $"{Number(point.TimestampS)} s · {_phaseNames.GetValueOrDefault(point.PhaseId ?? "", point.PhaseId ?? "未标注阶段")}" + (point.FrameIndex is { } index ? $" · 帧索引 {index}" : "")
            : $"[{Number(point.StartS)}, {Number(point.EndS)}) s";
        if (point.ReferenceElapsedS is { } elapsed)
        {
            position += $" · 参考曲线时间 {Number(elapsed)} s";
        }
        var metric = _route
            ? $"实际位置 {RoutePosition(point.Value)} · 距路线 {Number(point.Deviation)} {_unit}"
                + (point.NearestRoutePoint is { } nearest ? $" · 路线最近点（X {Number(nearest.XM)}, Y {Number(nearest.YM)}, 高度 {Number(nearest.HeightM)} m）" : "")
                + (point.RouteSegmentIndex is { } segment ? $" · 第 {segment + 1} 段" : "")
            : _radial
            ? $"原始命中 {Value(point.Value)} · 靶心距离 {Number(point.Deviation)} {_unit}"
            : $"原值 {Value(point.Value)} · 目标 {Number(point.Expected)} · 偏差 {Signed(point.Deviation)} {_unit}";
        return $"{position} · {metric} · {point.Grade ?? "无结论"}" + (string.IsNullOrWhiteSpace(point.Reason) ? "" : " · " + point.Reason);
    }

    public static FrameworkElement FrameDistributionView(SceneFrameDistribution? distribution)
    {
        var body = new StackPanel { Spacing = 7 };
        if (distribution is null)
        {
            body.Children.Add(Label("帧分布：尚无可用结果。", 13));
            return body;
        }
        body.Children.Add(Label($"有效分档 {distribution.ValidFrameCount} 帧 · 缺失 / 无结论 {distribution.MissingFrameCount} 帧", 13));
        var bar = new Grid { Height = 10, HorizontalAlignment = HorizontalAlignment.Stretch };
        var labels = new List<string>();
        var column = 0;
        foreach (var grade in new[] { "D", "A", "U" })
        {
            var fraction = distribution.Proportions.GetValueOrDefault(grade);
            labels.Add($"{grade} {distribution.Counts.GetValueOrDefault(grade)} 帧 · {(fraction is { } value ? (value * 100).ToString("0.0", CultureInfo.InvariantCulture) + "%" : "尚无占比")}");
            if (fraction is > 0)
            {
                bar.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(fraction.Value, GridUnitType.Star) });
                var segment = new Border { Background = GradeBrush(grade), CornerRadius = new CornerRadius(2) };
                Grid.SetColumn(segment, column++);
                bar.Children.Add(segment);
            }
        }
        if (column > 0) { body.Children.Add(bar); }
        body.Children.Add(Label(string.Join("    ", labels), 13));
        body.Children.Add(Label("占比以有效分档帧数为分母，不代表持续时间。A 不重复计入 D；缺失帧不计为通过。", 12));
        return body;
    }

    public static FrameworkElement DistributionView(SceneTimeDistribution? distribution)
    {
        var body = new StackPanel { Spacing = 7 };
        if (distribution is null)
        {
            body.Children.Add(Label("时长分布：尚无可用时序。", 13));
            return body;
        }
        body.Children.Add(Label($"有效分档 {Number(distribution.DurationS)} s / 跨度 {Number(distribution.SpanS)} s · 缺测 {Number(distribution.GapS)} s", 13));
        var bar = new Grid { Height = 10, HorizontalAlignment = HorizontalAlignment.Stretch };
        var labels = new List<string>();
        var column = 0;
        foreach (var grade in new[] { "D", "A", "U" })
        {
            var fraction = distribution.Proportions.GetValueOrDefault(grade);
            var duration = distribution.Durations.GetValueOrDefault(grade);
            labels.Add($"{grade} {Number(duration)} s · {(fraction is { } value ? (value * 100).ToString("0.0", CultureInfo.InvariantCulture) + "%" : "尚无占比")}");
            if (fraction is > 0)
            {
                bar.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(fraction.Value, GridUnitType.Star) });
                var segment = new Border { Background = GradeBrush(grade), CornerRadius = new CornerRadius(2) };
                Grid.SetColumn(segment, column++);
                bar.Children.Add(segment);
            }
        }
        if (column > 0) { body.Children.Add(bar); }
        body.Children.Add(Label(string.Join("    ", labels), 13));
        body.Children.Add(Label("占比以有效分档时长为分母；A 只计入 A 范围中不属于 D 的时段，缺测不计为通过。", 12));
        return body;
    }

    public static Expander DetailExpander(string heading, IEnumerable<string> rows)
    {
        var expander = new Expander { Header = heading, HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Stretch };
        expander.Expanding += (_, _) =>
        {
            if (expander.Content is not null) { return; }
            var values = rows.ToList();
            var containerStyle = new Style(typeof(ListViewItem));
            containerStyle.Setters.Add(new Setter(Control.HorizontalContentAlignmentProperty, HorizontalAlignment.Stretch));
            expander.Content = values.Count == 0 ? Label("无记录。", 13) : new ListView
            {
                ItemsSource = values,
                ItemContainerStyle = containerStyle,
                ItemTemplate = (DataTemplate)XamlReader.Load("""
                    <DataTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation">
                      <TextBlock Text="{Binding}" TextWrapping="Wrap" FontSize="13" Margin="4,6" />
                    </DataTemplate>
                    """),
                MaxHeight = 300,
                SelectionMode = ListViewSelectionMode.Single,
                IsItemClickEnabled = false,
                HorizontalAlignment = HorizontalAlignment.Stretch,
            };
        };
        return expander;
    }

    private void Draw()
    {
        _plot.Children.Clear();
        var points = _result.Timeline;
        var width = _plot.ActualWidth;
        if (width < 180 || points.Count == 0) { return; }
        _firstTime = (_frameBased ? points[0].TimestampS : points[0].StartS) ?? double.NaN;
        _lastTime = (_frameBased ? points[^1].TimestampS : points[^1].EndS) ?? double.NaN;
        if (!double.IsFinite(_firstTime) || !double.IsFinite(_lastTime) || _lastTime < _firstTime) { return; }
        if (_frameBased && _firstTime == _lastTime)
        {
            // Axis padding makes a single real frame visible; it does not extend its observation.
            _firstTime -= 0.5;
            _lastTime += 0.5;
        }
        if (_lastTime <= _firstTime) { return; }
        const double left = 64, right = 15, rawTop = 30, rawBottom = 124, errorTop = 182, errorBottom = 272;
        var rawValues = points.SelectMany(point => _route
            ? new[] { Coordinate(point.Value, "x_m"), Coordinate(point.Value, "y_m"), Coordinate(point.Value, "height_m"), point.NearestRoutePoint?.XM, point.NearestRoutePoint?.YM, point.NearestRoutePoint?.HeightM }
            : _radial
            ? new[] { Coordinate(point.Value, "u_m"), Coordinate(point.Value, "v_m"), _result.Parameter?.CenterU, _result.Parameter?.CenterV }
            : new[] { NumericValue(point.Value), point.Expected }).Where(value => value.HasValue).Select(value => value!.Value).ToArray();
        var deviations = points.Where(point => point.Deviation.HasValue).Select(point => point.Deviation!.Value).ToList();
        deviations.Add(0);
        if (_result.Parameter is { } parameter)
        {
            foreach (var value in new[] { parameter.Desired.Lower, parameter.Desired.Upper, parameter.Acceptable.Lower, parameter.Acceptable.Upper })
            {
                if (value is { } limit && double.IsFinite(limit)) { deviations.Add(limit); }
            }
        }
        var rawRange = Range(rawValues);
        var errorRange = Range(deviations);
        double X(double time) => left + (time - _firstTime) / (_lastTime - _firstTime) * (width - left - right);
        double RawY(double value) => rawBottom - (value - rawRange.Minimum) / (rawRange.Maximum - rawRange.Minimum) * (rawBottom - rawTop);
        double ErrorY(double value) => errorBottom - (value - errorRange.Minimum) / (errorRange.Maximum - errorRange.Minimum) * (errorBottom - errorTop);
        AddLabel(_route ? "实际 X / Y / 高度与路线最近点（m）" : _radial ? "命中坐标 u / v 与靶心（m）" : $"原值 / 目标（{_unit}）", left, 2);
        AddLabel(_route ? $"距路线距离（{_unit}） · 背景为 D / A 通道半径" : _radial ? $"靶心距离（{_unit}） · 背景为 D / A 半径范围" : $"有符号偏差（{_unit}） · 背景为 D / A 范围", left, 151);
        AddLabel(AxisNumber(rawRange.Maximum), 0, rawTop - 5);
        AddLabel(AxisNumber(rawRange.Minimum), 0, rawBottom - 12);
        AddLabel(AxisNumber(errorRange.Maximum), 0, errorTop - 5);
        AddLabel(AxisNumber(errorRange.Minimum), 0, errorBottom - 12);
        if (_result.Parameter is { } bands)
        {
            AddBand(bands.Acceptable, "A", ErrorY, errorRange, left, width - left - right);
            AddBand(bands.Desired, "D", ErrorY, errorRange, left, width - left - right);
        }
        AddLine(left, ErrorY(0), width - right, ErrorY(0), ThemeBrush("TextFillColorTertiaryBrush"), 1);
        for (var tick = 0; tick <= 4; tick++)
        {
            var time = _firstTime + (_lastTime - _firstTime) * tick / 4;
            var x = X(time);
            AddLine(x, rawTop, x, rawBottom, ThemeBrush("ControlStrokeColorDefaultBrush"), 0.7);
            AddLine(x, errorTop, x, errorBottom, ThemeBrush("ControlStrokeColorDefaultBrush"), 0.7);
            AddLabel(AxisNumber(time) + " s", Math.Clamp(x - 22, 0, width - 65), 286);
        }
        var geometry = new Dictionary<string, PathGeometry>();
        foreach (var key in new[] { "raw-D", "raw-A", "raw-U", "raw-?", "error-D", "error-A", "error-U", "grade-D", "grade-A", "grade-U", "grade-?", "target", "u", "v", "h", "center-u", "center-v", "center-h" }) { geometry[key] = new PathGeometry(); }
        foreach (var index in SceneTimelineSelection.SelectIndices(points, DrawingLimit))
        {
            var point = points[index];
            var grade = point.Grade is "D" or "A" or "U" ? point.Grade : "?";
            var start = (_frameBased ? point.TimestampS : point.StartS) ?? double.NaN;
            var end = (_frameBased ? point.TimestampS : point.EndS) ?? double.NaN;
            if (!double.IsFinite(start) || !double.IsFinite(end)) { continue; }
            var x1 = X(start) - (_frameBased ? 1.2 : 0);
            var x2 = X(end) + (_frameBased ? 1.2 : 0);
            if (_route)
            {
                if (Coordinate(point.Value, "x_m") is { } x) { Segment(geometry["u"], x1, x2, RawY(x)); }
                if (Coordinate(point.Value, "y_m") is { } y) { Segment(geometry["v"], x1, x2, RawY(y)); }
                if (Coordinate(point.Value, "height_m") is { } h) { Segment(geometry["h"], x1, x2, RawY(h)); }
                if (point.NearestRoutePoint?.XM is { } targetX) { Segment(geometry["center-u"], x1, x2, RawY(targetX)); }
                if (point.NearestRoutePoint?.YM is { } targetY) { Segment(geometry["center-v"], x1, x2, RawY(targetY)); }
                if (point.NearestRoutePoint?.HeightM is { } targetH) { Segment(geometry["center-h"], x1, x2, RawY(targetH)); }
            }
            else if (_radial)
            {
                if (Coordinate(point.Value, "u_m") is { } u) { Segment(geometry["u"], x1, x2, RawY(u)); }
                if (Coordinate(point.Value, "v_m") is { } v) { Segment(geometry["v"], x1, x2, RawY(v)); }
            }
            else
            {
                if (NumericValue(point.Value) is { } raw) { Segment(geometry[$"raw-{grade}"], x1, x2, RawY(raw)); }
                if (point.Expected is { } target) { Segment(geometry["target"], x1, x2, RawY(target)); }
            }
            if (point.Deviation is { } deviation && grade != "?") { Segment(geometry[$"error-{grade}"], x1, x2, ErrorY(deviation)); }
            if (_frameBased) { Segment(geometry[$"grade-{grade}"], x1, x2, errorBottom + 7); }
        }
        if (_radial)
        {
            if (_result.Parameter?.CenterU is { } u) { Segment(geometry["center-u"], left, width - right, RawY(u)); }
            if (_result.Parameter?.CenterV is { } v) { Segment(geometry["center-v"], left, width - right, RawY(v)); }
        }
        foreach (var (key, data) in geometry)
        {
            var path = new Microsoft.UI.Xaml.Shapes.Path
            {
                Data = data,
                Stroke = key switch
                {
                    "target" => ThemeBrush("TextFillColorPrimaryBrush"),
                    "u" or "center-u" => new SolidColorBrush(Colors.CornflowerBlue),
                    "v" or "center-v" => new SolidColorBrush(Colors.MediumPurple),
                    "h" or "center-h" => new SolidColorBrush(Colors.Teal),
                    _ => GradeBrush(key.Split('-')[1]),
                },
                StrokeThickness = key is "target" or "center-u" or "center-v" or "center-h" ? 1.3 : 2.8,
                StrokeStartLineCap = PenLineCap.Round,
                StrokeEndLineCap = PenLineCap.Round,
                IsHitTestVisible = false,
            };
            if (key is "target" or "center-u" or "center-v" or "center-h") { path.StrokeDashArray = [4, 3]; }
            _plot.Children.Add(path);
        }
    }

    private void OnPointerMoved(object sender, PointerRoutedEventArgs args)
    {
        if (_result.Timeline.Count == 0 || _lastTime <= _firstTime || _plot.ActualWidth <= 79) { return; }
        var x = args.GetCurrentPoint(_plot).Position.X;
        var time = _firstTime + (x - 64) / (_plot.ActualWidth - 79) * (_lastTime - _firstTime);
        if (_frameBased)
        {
            var index = SceneTimelineSelection.FindNearestFrame(_result.Timeline, time);
            _cursor.Text = index >= 0 ? PointDescription(_result.Timeline[index]) : "没有可定位的真实帧。";
            return;
        }
        var low = 0;
        var high = _result.Timeline.Count - 1;
        while (low <= high)
        {
            var middle = low + (high - low) / 2;
            var point = _result.Timeline[middle];
            if (time < point.StartS) { high = middle - 1; }
            else if (time >= point.EndS) { low = middle + 1; }
            else
            {
                _cursor.Text = PointDescription(point);
                return;
            }
        }
        _cursor.Text = "该时间位置没有输入时段。";
    }

    private void AddBand(SceneInterval interval, string grade, Func<double, double> y, (double Minimum, double Maximum) range, double x, double width)
    {
        if (interval.Lower is not { } lower) { return; }
        var upper = interval.UnboundedUpper ? range.Maximum : interval.Upper;
        if (upper is null) { return; }
        var top = y(Math.Min(upper.Value, range.Maximum));
        var bottom = y(Math.Max(lower, range.Minimum));
        if (bottom < top) { return; }
        var band = new Rectangle { Width = width, Height = bottom - top, Fill = GradeBrush(grade), Opacity = 0.13, IsHitTestVisible = false };
        Canvas.SetLeft(band, x);
        Canvas.SetTop(band, top);
        _plot.Children.Add(band);
    }

    private void AddLabel(string text, double x, double y)
    {
        var label = Label(text, 11);
        label.IsHitTestVisible = false;
        Canvas.SetLeft(label, x);
        Canvas.SetTop(label, y);
        _plot.Children.Add(label);
    }

    private void AddLine(double x1, double y1, double x2, double y2, Brush brush, double thickness) =>
        _plot.Children.Add(new Line { X1 = x1, Y1 = y1, X2 = x2, Y2 = y2, Stroke = brush, StrokeThickness = thickness, IsHitTestVisible = false });

    private static void Segment(PathGeometry geometry, double start, double end, double y)
    {
        var figure = new PathFigure { StartPoint = new Point(start, y), IsClosed = false, IsFilled = false };
        figure.Segments.Add(new LineSegment { Point = new Point(end, y) });
        geometry.Figures.Add(figure);
    }

    private static (double Minimum, double Maximum) Range(IEnumerable<double> values)
    {
        var finite = values.Where(double.IsFinite).ToArray();
        if (finite.Length == 0) { return (-1, 1); }
        var minimum = finite.Min();
        var maximum = finite.Max();
        var padding = maximum == minimum ? Math.Max(Math.Abs(minimum) * 0.05, 1) : (maximum - minimum) * 0.08;
        return (minimum - padding, maximum + padding);
    }

    private static double? NumericValue(JsonElement? value) => value is { ValueKind: JsonValueKind.Number } number && number.TryGetDouble(out var result) && double.IsFinite(result) ? result : null;
    private static double? Coordinate(JsonElement? value, string key) => value is { ValueKind: JsonValueKind.Object } point && point.TryGetProperty(key, out var coordinate) ? NumericValue(coordinate) : null;
    private static string RoutePosition(JsonElement? value) => value is { ValueKind: JsonValueKind.Object }
        ? $"（X {Number(Coordinate(value, "x_m"))}, Y {Number(Coordinate(value, "y_m"))}, 高度 {Number(Coordinate(value, "height_m"))} m）"
        : "缺失";
    private static string Value(JsonElement? value)
    {
        if (value is null || value.Value.ValueKind == JsonValueKind.Null) { return "缺失"; }
        if (value is { ValueKind: JsonValueKind.Object } point && point.TryGetProperty("status", out var status) && status.ValueKind == JsonValueKind.String)
        {
            return status.GetString() switch
            {
                "hit" => $"命中（u {Number(Coordinate(value, "u_m"))}, v {Number(Coordinate(value, "v_m"))} m）",
                "miss" => "未命中",
                _ => "不可用",
            };
        }
        return value.Value.ValueKind switch { JsonValueKind.True => "是", JsonValueKind.False => "否", _ => value.Value.ToString() };
    }
    private static string Number(double? value) => value?.ToString("G", CultureInfo.InvariantCulture) ?? "未提供";
    private static string AxisNumber(double value) => value.ToString("G4", CultureInfo.InvariantCulture);
    private static string Signed(double? value) => value is null ? "未提供" : (value > 0 ? "+" : "") + Number(value);
    private static Brush ThemeBrush(string resource) => (Brush)Application.Current.Resources[resource];
    private static Brush GradeBrush(string grade) => ThemeBrush(grade switch { "D" => "SystemFillColorSuccessBrush", "A" => "SystemFillColorCautionBrush", "U" => "SystemFillColorCriticalBrush", _ => "TextFillColorSecondaryBrush" });
    private static TextBlock Label(string text, double size = 14, bool semibold = false) => new() { Text = text, TextWrapping = TextWrapping.Wrap, FontSize = size, FontWeight = semibold ? Microsoft.UI.Text.FontWeights.SemiBold : Microsoft.UI.Text.FontWeights.Normal };
}
