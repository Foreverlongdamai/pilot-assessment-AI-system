using System.Globalization;

using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

using PilotAssessment.Desktop.Core.SceneAssessment;

namespace PilotAssessment.Desktop.Controls.Editors;

public sealed class SceneItemParameterEditor : UserControl
{
    private readonly List<Func<bool>> _applyFields = [];
    private readonly Dictionary<string, TextBlock> _validationMessages = [];
    private readonly TextBlock _validationSummary = Text("", 13);
    private readonly SceneSkillModelEditor? _skillEditor;
    private readonly Expander? _skillExpander;
    private readonly string _modelPath;

    public SceneItemParameterEditor(SceneCatalog catalog, SceneItem item, SceneItemEdit edit)
    {
        var body = new StackPanel { Spacing = 20, Padding = new Thickness(0, 0, 12, 12) };
        Content = new ScrollViewer
        {
            MaxHeight = 620,
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
            HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled,
            Content = body,
        };
        body.Children.Add(Text(item.Description));
        body.Children.Add(Text(item.AssessmentKind == "checklist"
            ? "检查单只评价程序是否完成：true 对应 D / Pass，false 对应 U / Fail。缺失记录不等同于未完成。"
            : "填写实际目标，以及低于 / 高于目标的允许量（均填非负数，可以不对称）。D 范围应包含在 A 内且更窄。三维路线使用路线节点和 D / A 通道半径；激光检查使用靶心坐标和 D / A 半径。"));
        if (item.Phases is { Count: > 0 })
        {
            body.Children.Add(Text("输入阶段顺序：" + string.Join(" → ", item.Phases.Select(phase =>
                phase.Name + (phase.SingleFrame ? "（指定单帧）" : "")
                + (phase.MinimumFrameCount is >= 2 ? $"（至少 {phase.MinimumFrameCount} 帧）" : "")
                + (phase.RequiredDurationS is { } duration ? $"（至少 {duration:G} s 跨度）" : ""))), 13));
        }
        _validationSummary.Visibility = Visibility.Collapsed;
        body.Children.Add(_validationSummary);
        _modelPath = $"/skill_models/{item.ItemId}";
        if (item.AssessmentKind != "checklist")
        {
            _skillEditor = new SceneSkillModelEditor(catalog, item, edit);
            _skillExpander = new Expander
            {
                Header = Text("贝叶斯参数 · 先验、分值与 CPT", 17, true),
                Content = _skillEditor,
                HorizontalAlignment = HorizontalAlignment.Stretch,
                HorizontalContentAlignment = HorizontalAlignment.Stretch,
            };
            body.Children.Add(_skillExpander);
        }
        foreach (var checkpoint in item.Checkpoints)
        {
            var section = new StackPanel { Spacing = 10 };
            section.Children.Add(Text(checkpoint.Name, 18, true));
            var routeOnly = checkpoint.MetricIds.Count > 0 && checkpoint.MetricIds.All(id =>
                catalog.Metrics.Single(metric => metric.MetricId == id).Comparison == "route_3d");
            if (!routeOnly) { section.Children.Add(Text(checkpoint.Description)); }
            foreach (var metricId in checkpoint.MetricIds)
            {
                var metric = catalog.Metrics.Single(value => value.MetricId == metricId);
                var fields = new StackPanel { Spacing = 8 };
                fields.Children.Add(Text(metric.Name + (metric.Shared ? " · 共享参数" : ""), 15, true));
                if (metric.Comparison != "route_3d")
                {
                    fields.Children.Add(Text(metric.Description + (string.IsNullOrWhiteSpace(metric.Unit) ? "" : $" · 单位：{metric.Unit}")));
                    if (metric.PhaseIds is { Count: > 0 })
                    {
                        fields.Children.Add(Text("适用阶段：" + string.Join("、", metric.PhaseIds.Select(id =>
                            item.Phases?.FirstOrDefault(phase => phase.PhaseId == id)?.Name ?? id)), 12));
                    }
                }
                if (metric.Rule != "interval")
                {
                    fields.Children.Add(Text(metric.Rule == "must_be_true"
                        ? "固定规则：已完成 = D；明确未完成 = U。缺失结果不能当作未完成。"
                        : "固定规则：禁止事件为 0 = D；至少 1 次 = U。"));
                }
                else
                {
                    var parameter = edit.Parameters[metricId];
                    if (metric.Comparison == "radial")
                    {
                        fields.Children.Add(Text("系统根据命中点与靶心坐标计算距离。D 半径 < A 半径 < 靶面半径；圆周边界计入对应范围。明确未命中为 U，缺失数据不等于未命中。", 12));
                        fields.Children.Add(NumericBox("靶心 u 坐标（m）", parameter.CenterU, value => parameter.CenterU = value));
                        fields.Children.Add(NumericBox("靶心 v 坐标（m）", parameter.CenterV, value => parameter.CenterV = value));
                        fields.Children.Add(NumericBox("靶面半径（m）", parameter.TargetRadius, value => parameter.TargetRadius = value, nonNegative: true));
                        fields.Children.Add(NumericBox("D 半径（m）", parameter.Desired.Upper, value => parameter.Desired.Upper = value, nonNegative: true));
                        fields.Children.Add(NumericBox("A 半径（m）", parameter.Acceptable.Upper, value => parameter.Acceptable.Upper = value, nonNegative: true));
                        fields.Children.Add(Text("距离目标与 D / A 下界固定为 0；靶心、靶面半径和允许半径留空表示尚未配置。", 12));
                        fields.Children.Add(RadialDefinitionEditor(parameter));
                    }
                    else if (metric.Comparison == "route_3d")
                    {
                        fields.Children.Add(RouteEditor(parameter));
                        fields.Children.Add(NumericBox("D 通道半径（m）", parameter.Desired.Upper, value => parameter.Desired.Upper = value, nonNegative: true));
                        fields.Children.Add(NumericBox("A 通道半径（m）", parameter.Acceptable.Upper, value => parameter.Acceptable.Upper = value, nonNegative: true));
                        fields.Children.Add(RouteInstructions(item, checkpoint, metric));
                        fields.Children.Add(RadialDefinitionEditor(parameter, route: true));
                    }
                    else
                    {
                        fields.Children.Add(Text(metric.Comparison is "angle_degrees" or "heading"
                            ? "偏差采用有符号最短角差，范围为 [−180°, 180°)。"
                            : "有符号偏差 = 实际值 − 期望值。", 12));
                        if (metric.TargetMode == "item_profile")
                        {
                            fields.Children.Add(ItemReferenceProfileEditor(item, metric, parameter));
                        }
                        else if (metric.TargetMode == "phase_profile")
                        {
                            fields.Children.Add(ReferenceProfileEditor(item, metric, parameter));
                        }
                        else
                        {
                            fields.Children.Add(NumericBox("期望值 / 实际目标", parameter.Expected, value => parameter.Expected = value));
                        }
                        var signedAllowances = catalog.SchemaVersion != "1.0";
                        fields.Children.Add(IntervalRow(signedAllowances ? "D · 允许量" : "D · 原始范围", parameter.Desired, signedAllowances));
                        fields.Children.Add(IntervalRow(signedAllowances ? "A · 允许量" : "A · 原始范围", parameter.Acceptable, signedAllowances));
                    }
                    var validation = Text("", 13);
                    validation.Foreground = (Brush)Application.Current.Resources["SystemFillColorCriticalBrush"];
                    validation.Visibility = Visibility.Collapsed;
                    _validationMessages[metricId] = validation;
                    fields.Children.Add(validation);
                }
                section.Children.Add(new Border
                {
                    Padding = new Thickness(14),
                    CornerRadius = new CornerRadius(8),
                    BorderThickness = new Thickness(1),
                    BorderBrush = (Brush)Application.Current.Resources["ControlStrokeColorDefaultBrush"],
                    Child = fields,
                });
            }

            foreach (var source in checkpoint.Sources)
            {
                section.Children.Add(Text($"依据：{source.Document} · {source.Clause} · 页 {source.Page}\n{source.Support}：{source.Note}", 12));
                if (Uri.TryCreate(source.Url, UriKind.Absolute, out var uri) && uri.Scheme is "https" or "http")
                {
                    section.Children.Add(new HyperlinkButton
                    {
                        Content = "查看来源文件",
                        NavigateUri = uri,
                        Padding = new Thickness(0),
                        HorizontalAlignment = HorizontalAlignment.Left,
                    });
                }
            }
            body.Children.Add(section);
        }
    }

    public bool TryApply()
    {
        var valid = true;
        foreach (var apply in _applyFields)
        {
            valid = apply() && valid;
        }
        return (_skillEditor?.TryApply() ?? true) && valid;
    }

    public void ShowValidationIssues(IReadOnlyList<SceneIssue> issues)
    {
        _validationSummary.Text = issues.Count == 0 ? "" : "请修正下方参数问题后再应用。";
        _validationSummary.Visibility = issues.Count == 0 ? Visibility.Collapsed : Visibility.Visible;
        _skillEditor?.ShowValidationIssues(issues);
        if (_skillExpander is not null && issues.Any(issue => issue.Path == _modelPath || issue.Path.StartsWith(_modelPath + "/", StringComparison.Ordinal)))
        {
            _skillExpander.IsExpanded = true;
        }
        foreach (var (metricId, message) in _validationMessages)
        {
            var prefix = $"/parameters/{metricId}";
            var related = issues.Where(issue => issue.Path == prefix || issue.Path.StartsWith(prefix + "/", StringComparison.Ordinal));
            message.Text = string.Join("\n", related.Select(issue => issue.Message).Distinct());
            message.Visibility = message.Text.Length == 0 ? Visibility.Collapsed : Visibility.Visible;
        }
    }

    public void ShowValidationFailure(string message)
    {
        _validationSummary.Text = "参数验证未完成：" + message;
        _validationSummary.Visibility = Visibility.Visible;
    }

    private StackPanel ReferenceProfileEditor(SceneItem item, SceneMetric metric, SceneParameter parameter)
    {
        var body = new StackPanel { Spacing = 12 };
        body.Children.Add(Text("分段参考目标：每个环节分别填写至少两个节点，第一节点为环节开始后 0 秒，后续时间严格递增。节点之间按直线插值计算每帧期望值；留空可保存草稿，完整评估前需补齐并覆盖该环节的全部帧。", 12));
        foreach (var phaseId in metric.PhaseIds ?? [])
        {
            var phaseName = item.Phases?.FirstOrDefault(phase => phase.PhaseId == phaseId)?.Name ?? phaseId;
            body.Children.Add(Text(phaseName, 14, true));
            body.Children.Add(ReferenceProfileRows(metric, parameter.ReferenceProfiles?.GetValueOrDefault(phaseId) ?? [],
                points =>
                {
                    parameter.ReferenceProfiles ??= [];
                    parameter.ReferenceProfiles[phaseId] = points;
                }, "环节开始后 / s"));
        }
        return body;
    }

    private StackPanel ItemReferenceProfileEditor(SceneItem item, SceneMetric metric, SceneParameter parameter)
    {
        var body = new StackPanel { Spacing = 10 };
        var originId = metric.ReferenceOriginPhase ?? "";
        var originName = item.Phases?.FirstOrDefault(phase => phase.PhaseId == originId)?.Name ?? originId;
        var elapsedLabel = originId == "acceleration" ? "加速开始后 / s" : $"{originName}开始后 / s";
        body.Children.Add(Text($"共用一条时间轴：以输入中“{originName}”的第一帧为第 0 秒；后续阶段继续计时，不重新归零。原始时间戳保持不变。", 12));
        body.Children.Add(Text("至少填写两个节点，首节点为 0 秒，之后严格递增。节点之间按直线插值取得每个实际帧的期望值；D / A 允许量随期望曲线移动。留空可保存草稿，完整评估前须填齐，并让参考曲线与输入帧互相覆盖完整任务时间。", 12));
        body.Children.Add(ReferenceProfileRows(metric, parameter.ReferenceProfile ?? [],
            points => parameter.ReferenceProfile = points, elapsedLabel));
        return body;
    }

    private StackPanel ReferenceProfileRows(SceneMetric metric, List<SceneReferencePoint> points,
        Action<List<SceneReferencePoint>> setPoints, string elapsedLabel)
    {
        var section = new StackPanel { Spacing = 8 };
        var rows = new StackPanel { Spacing = 8 };
        var applyRows = new List<List<Func<bool>>>();
        var add = new Button { HorizontalAlignment = HorizontalAlignment.Left };
        section.Children.Add(rows);
        section.Children.Add(add);
        foreach (var point in points)
        {
            AddRow(point);
        }
        RefreshAddButton();
        add.Click += (_, _) =>
        {
            // A reference is initialized only by an explicit action, without inventing targets.
            setPoints(points);
            if (points.Count == 0)
            {
                var first = new SceneReferencePoint { ElapsedS = 0 };
                points.Add(first);
                AddRow(first);
            }
            var next = new SceneReferencePoint();
            points.Add(next);
            AddRow(next);
            RefreshAddButton();
        };
        _applyFields.Add(() =>
        {
            var valid = true;
            foreach (var fields in applyRows)
            {
                foreach (var apply in fields)
                {
                    valid = apply() && valid;
                }
            }
            return valid;
        });
        return section;

        void AddRow(SceneReferencePoint point)
        {
            var fields = new List<Func<bool>>();
            var row = new Grid { ColumnSpacing = 12 };
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            var elapsed = NumericBox(elapsedLabel, point.ElapsedS, value => point.ElapsedS = value, nonNegative: true, applyFields: fields);
            row.Children.Add(elapsed);
            var expectedLabel = metric.MetricId == "air_taxi_airspeed_mps" ? "期望空速" : "期望值";
            var expected = NumericBox(expectedLabel + (string.IsNullOrWhiteSpace(metric.Unit) ? "" : $" / {metric.Unit}"), point.Expected, value => point.Expected = value, applyFields: fields);
            Grid.SetColumn(expected, 1);
            row.Children.Add(expected);
            var remove = new Button { Content = "删除节点", VerticalAlignment = VerticalAlignment.Bottom };
            Grid.SetColumn(remove, 2);
            row.Children.Add(remove);
            remove.Click += (_, _) =>
            {
                points.Remove(point);
                rows.Children.Remove(row);
                // Removed controls must not validate or write into the draft on a later apply.
                applyRows.Remove(fields);
                RefreshAddButton();
            };
            applyRows.Add(fields);
            rows.Children.Add(row);
        }

        void RefreshAddButton() => add.Content = points.Count == 0 ? "初始化两个目标节点" : "添加目标节点";
    }

    private StackPanel RouteEditor(SceneParameter parameter)
    {
        var body = new StackPanel { Spacing = 10 };
        body.Children.Add(Text("按飞行方向填写 X、Y 和高度：直线路线用两个节点，转弯处添加节点。", 12));
        var rows = new StackPanel { Spacing = 8 };
        var applyRows = new List<List<Func<bool>>>();
        var points = parameter.RoutePoints ?? [];
        var add = new Button { HorizontalAlignment = HorizontalAlignment.Left };
        body.Children.Add(rows);
        body.Children.Add(add);
        foreach (var point in points) { AddRow(point); }
        RefreshAddButton();
        add.Click += (_, _) =>
        {
            // New geometry is created only by this explicit action, with no inferred coordinates.
            parameter.RoutePoints = points;
            if (points.Count == 0)
            {
                var first = new SceneRoutePoint();
                points.Add(first);
                AddRow(first);
            }
            var next = new SceneRoutePoint();
            points.Add(next);
            AddRow(next);
            RefreshAddButton();
        };
        _applyFields.Add(() =>
        {
            var valid = true;
            foreach (var fields in applyRows)
            {
                foreach (var apply in fields) { valid = apply() && valid; }
            }
            return valid;
        });
        return body;

        void AddRow(SceneRoutePoint point)
        {
            var fields = new List<Func<bool>>();
            var row = new Grid { ColumnSpacing = 10 };
            for (var column = 0; column < 3; column++)
            {
                row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            }
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            var x = NumericBox("路线 X（m）", point.XM, value => point.XM = value, applyFields: fields);
            row.Children.Add(x);
            var y = NumericBox("路线 Y（m）", point.YM, value => point.YM = value, applyFields: fields);
            Grid.SetColumn(y, 1);
            row.Children.Add(y);
            var height = NumericBox("路线高度（m）", point.HeightM, value => point.HeightM = value, applyFields: fields);
            Grid.SetColumn(height, 2);
            row.Children.Add(height);
            var remove = new Button { Content = "删除路线节点", VerticalAlignment = VerticalAlignment.Bottom };
            Grid.SetColumn(remove, 3);
            row.Children.Add(remove);
            remove.Click += (_, _) =>
            {
                points.Remove(point);
                rows.Children.Remove(row);
                applyRows.Remove(fields);
                RefreshAddButton();
            };
            rows.Children.Add(row);
            applyRows.Add(fields);
        }

        void RefreshAddButton() => add.Content = points.Count == 0 ? "初始化两个路线节点" : "添加路线节点";
    }

    private static Expander RouteInstructions(SceneItem item, SceneCheckpoint checkpoint, SceneMetric metric)
    {
        var body = new StackPanel { Spacing = 8 };
        body.Children.Add(Text(checkpoint.Description, 12));
        body.Children.Add(Text(metric.Description + (string.IsNullOrWhiteSpace(metric.Unit) ? "" : $" · 单位：{metric.Unit}"), 12));
        if (metric.PhaseIds is { Count: > 0 })
        {
            body.Children.Add(Text("适用阶段：" + string.Join("、", metric.PhaseIds.Select(id =>
                item.Phases?.FirstOrDefault(phase => phase.PhaseId == id)?.Name ?? id)), 12));
        }
        body.Children.Add(Text("相邻节点之间是直线段。这里只定义空间路线，不要求逐秒参考速度或高度；输入位置和路线必须采用同一坐标系、原点及高度基准。", 12));
        body.Children.Add(Text("路线坐标与到点悬停目标分别手工填写；系统不会根据其中一个自动修改另一个。请确认末节点对应场景要求的到达点。", 12));
        body.Children.Add(Text("每帧按实际三维位置到路线有限线段的最短距离分档：距离 ≤ D 半径为 D；超出 D、但 ≤ A 半径为 A；超出 A 为 U。高度偏离已包含在距离中。D 半径必须小于 A 半径，具体数值由项目配置。", 12));
        return new Expander
        {
            Header = "路线填写说明",
            Content = body,
            IsExpanded = false,
            HorizontalAlignment = HorizontalAlignment.Stretch,
            HorizontalContentAlignment = HorizontalAlignment.Stretch,
        };
    }

    private static Expander RadialDefinitionEditor(SceneParameter parameter, bool route = false)
    {
        var values = Text("", 12);
        var restore = new Button { Content = "还原距离定义", HorizontalAlignment = HorizontalAlignment.Left };
        var body = new StackPanel { Spacing = 8 };
        body.Children.Add(Text("以下是导入文件当前保存的距离定义。还原按钮只将距离目标及 D / A 下界设为 0，并取消 D / A 无上限；"
            + (route ? "路线节点和通道半径保留原值。" : "靶心和三个半径保留原值。"), 12));
        body.Children.Add(values);
        body.Children.Add(restore);
        var expander = new Expander
        {
            Content = body,
            HorizontalAlignment = HorizontalAlignment.Stretch,
            HorizontalContentAlignment = HorizontalAlignment.Stretch,
        };
        Refresh();
        expander.IsExpanded = restore.IsEnabled;
        restore.Click += (_, _) =>
        {
            // This is an explicit edit action; opening the editor never corrects imported values.
            parameter.Expected = 0;
            parameter.Desired.Lower = 0;
            parameter.Acceptable.Lower = 0;
            parameter.Desired.UnboundedUpper = false;
            parameter.Acceptable.UnboundedUpper = false;
            Refresh();
        };
        return expander;

        void Refresh()
        {
            var valid = parameter.Expected == 0 && parameter.Desired.Lower == 0 && parameter.Acceptable.Lower == 0
                && !parameter.Desired.UnboundedUpper && !parameter.Acceptable.UnboundedUpper;
            expander.Header = valid ? "固定距离定义 · 当前值正确" : "固定距离定义 · 当前值需要修正";
            restore.IsEnabled = !valid;
            values.Text = $"当前距离目标：{Number(parameter.Expected)}\n"
                + $"D 下界：{Number(parameter.Desired.Lower)} · D 无上限：{(parameter.Desired.UnboundedUpper ? "是" : "否")}\n"
                + $"A 下界：{Number(parameter.Acceptable.Lower)} · A 无上限：{(parameter.Acceptable.UnboundedUpper ? "是" : "否")}";
        }

        static string Number(double? value) => value?.ToString("G", CultureInfo.InvariantCulture) ?? "未提供";
    }

    private Grid IntervalRow(string title, SceneInterval interval, bool signedAllowances)
    {
        var grid = new Grid { ColumnSpacing = 12 };
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(140) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(96) });
        grid.Children.Add(new TextBlock { Text = title, VerticalAlignment = VerticalAlignment.Center });
        var lower = signedAllowances
            ? NumericBox("低于目标允许量", -interval.Lower, value => interval.Lower = -value, nonNegative: true)
            : NumericBox("下界（原始值）", interval.Lower, value => interval.Lower = value);
        Grid.SetColumn(lower, 1);
        grid.Children.Add(lower);
        var upper = NumericBox(signedAllowances ? "高于目标允许量" : "上界（原始值）", interval.Upper, value => interval.Upper = value, nonNegative: signedAllowances);
        upper.IsEnabled = !interval.UnboundedUpper;
        Grid.SetColumn(upper, 2);
        grid.Children.Add(upper);
        var unlimited = new CheckBox
        {
            Content = "无上限",
            IsChecked = interval.UnboundedUpper,
            VerticalAlignment = VerticalAlignment.Center,
        };
        unlimited.Checked += (_, _) => upper.IsEnabled = false;
        unlimited.Unchecked += (_, _) => upper.IsEnabled = true;
        Grid.SetColumn(unlimited, 3);
        grid.Children.Add(unlimited);
        _applyFields.Add(() =>
        {
            interval.UnboundedUpper = unlimited.IsChecked == true;
            if (interval.UnboundedUpper)
            {
                interval.Upper = null;
            }
            return true;
        });
        return grid;
    }

    private UserControl NumericBox(string label, double? value, Action<double?> set, bool readOnly = false, bool nonNegative = false, List<Func<bool>>? applyFields = null)
    {
        var box = new TextBox
        {
            Header = label,
            Text = value?.ToString("G", CultureInfo.InvariantCulture) ?? "",
            PlaceholderText = "未填写",
            IsReadOnly = readOnly,
            MinWidth = 100,
        };
        var error = Text(nonNegative ? "请输入非负有限数值，或留空。" : "请输入有限数值，或留空。", 12);
        error.Foreground = (Brush)Application.Current.Resources["SystemFillColorCriticalBrush"];
        error.Visibility = Visibility.Collapsed;
        var panel = new StackPanel { Spacing = 3 };
        panel.Children.Add(box);
        panel.Children.Add(error);
        var control = new UserControl { Content = panel };
        (applyFields ?? _applyFields).Add(() =>
        {
            if (!control.IsEnabled)
            {
                error.Visibility = Visibility.Collapsed;
                return true;
            }
            if (string.IsNullOrWhiteSpace(box.Text))
            {
                set(null);
                error.Visibility = Visibility.Collapsed;
                return true;
            }
            if (double.TryParse(box.Text, NumberStyles.Float, CultureInfo.InvariantCulture, out var parsed)
                && double.IsFinite(parsed) && (!nonNegative || parsed >= 0))
            {
                set(parsed);
                error.Visibility = Visibility.Collapsed;
                return true;
            }
            error.Visibility = Visibility.Visible;
            return false;
        });
        return control;
    }

    private static TextBlock Text(string content, double size = 14, bool semibold = false) => new()
    {
        Text = content,
        TextWrapping = TextWrapping.Wrap,
        FontSize = size,
        FontWeight = semibold ? Microsoft.UI.Text.FontWeights.SemiBold : Microsoft.UI.Text.FontWeights.Normal,
    };
}
