using System.Globalization;

using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

using PilotAssessment.Desktop.Core.SceneAssessment;

namespace PilotAssessment.Desktop.Controls.Editors;

public sealed class SceneSkillModelEditor : UserControl
{
    private static readonly string[] SkillStates = ["低", "中", "高"];
    private readonly SceneItem _item;
    private readonly SceneItemEdit _edit;
    private readonly SceneSkillModel? _demonstration;
    private readonly StackPanel _fields = new() { Spacing = 16 };
    private readonly List<Func<bool>> _applyFields = [];
    private readonly TextBlock _validation = Text("", 13);
    private SceneSkillModel? _baseline;
    private readonly InfoBar _methodNotice = new() { IsOpen = true, IsClosable = false, Severity = InfoBarSeverity.Warning };
    private readonly string? _checkpointId;
    private readonly bool _seriesMethod;
    private readonly bool _processSupported;

    public SceneSkillModelEditor(SceneCatalog catalog, SceneItem item, SceneItemEdit edit, string? checkpointId = null)
    {
        _item = item;
        _seriesMethod = catalog.SchemaVersion is "2.0" or "3.0";
        _processSupported = catalog.SchemaVersion == "3.0" && item.AssessmentKind != "checklist";
        _checkpointId = checkpointId;
        _edit = edit;
        _baseline = edit.SkillModel is null ? null : Clone(edit.SkillModel);
        if (catalog.ConfigurationTemplate.SkillModels?.TryGetValue(item.ItemId, out var demonstration) == true)
        {
            _demonstration = demonstration;
        }

        var body = new StackPanel { Spacing = 12 };
        body.Children.Add(Text("量化对象：" + item.SkillName, 15, true));
        body.Children.Add(Text(_seriesMethod
            ? "按检查点表现配置先验、状态分值和 CPT；是否计算概率与分数取决于当前加载的模型方法。"
            : item.SkillDescription));
        body.Children.Add(_methodNotice);
        var load = new Button
        {
            Content = _seriesMethod ? "载入空白参数草稿" : edit.SkillModel is null ? "载入本项演示模型" : checkpointId is null ? "重新载入本项演示模型" : "恢复本检查点演示概率",
            IsEnabled = _demonstration is not null,
            HorizontalAlignment = HorizontalAlignment.Left,
        };
        load.Click += (_, _) =>
        {
            if (_demonstration is null)
            {
                return;
            }
            if (_checkpointId is not null && _edit.SkillModel is { } existing)
            {
                existing.CheckpointModels[_checkpointId] = Clone(_demonstration).CheckpointModels[_checkpointId];
            }
            else
            {
                _edit.SkillModel = Clone(_demonstration);
                _baseline = Clone(_demonstration);
            }
            load.Content = _seriesMethod ? "重新载入空白参数草稿" : _checkpointId is null ? "重新载入本项演示模型" : "恢复本检查点演示概率";
            _validation.Visibility = Visibility.Collapsed;
            RenderFields();
        };
        body.Children.Add(load);
        _validation.Foreground = (Brush)Application.Current.Resources["SystemFillColorCriticalBrush"];
        _validation.Visibility = Visibility.Collapsed;
        body.Children.Add(_validation);
        body.Children.Add(_fields);
        Content = body;
        RenderFields();
    }

    public bool TryApply()
    {
        var valid = true;
        foreach (var apply in _applyFields)
        {
            valid = apply() && valid;
        }
        if (valid && _edit.SkillModel is { } model && _baseline is { } baseline)
        {
            model.ParameterSource = SceneSkillModelEditing.ParametersEqual(model, baseline) ? baseline.ParameterSource : "user_defined";
        }
        return valid;
    }

    public void ShowValidationIssues(IReadOnlyList<SceneIssue> issues)
    {
        var prefix = $"/skill_models/{_item.ItemId}";
        _validation.Text = string.Join("\n", issues
            .Where(issue => issue.Path == prefix || issue.Path.StartsWith(prefix + "/", StringComparison.Ordinal))
            .Select(issue => $"{issue.Path[prefix.Length..]}：{issue.Message}")
            .Distinct());
        _validation.Visibility = _validation.Text.Length == 0 ? Visibility.Collapsed : Visibility.Visible;
    }

    private void RenderFields()
    {
        _fields.Children.Clear();
        _applyFields.Clear();
        var compensationInference = _edit.SkillModel?.InferenceMethod == SceneSkillModel.CompensationInferenceMethod;
        _methodNotice.Title = "贝叶斯网络 · 参数未标定";
        _methodNotice.Message = compensationInference
            ? "贝叶斯网络根据每个有效帧的观测更新概率，更新后的概率成为下一帧先验。分数由概率和状态分值换算；D/A/U 与 P/F 独立判定。"
            : _seriesMethod
                ? "先验与 CPT 留空表示尚未配置。逐帧模型须补齐概率后才能评估，可以保留参数草稿。"
                : "概率表与状态分值是项目设定，不是 FAA、EASA 或 CAA 规定的数值。D/A/U 和 P/F 继续独立判定。";
        if (_edit.SkillModel is not { } model)
        {
            _fields.Children.Add(Text(_seriesMethod ? "尚未设置参数草稿。可载入空白结构后填写；不会生成整段技能分数。" : "此配置尚未设置本项技能模型。仍可计算 D/A/U 和 P/F。"));
            return;
        }
        var source = model.ParameterSource switch { "unconfigured" => "尚未配置", "demonstration" => "演示设定", _ => "用户设定" };
        _fields.Children.Add(Text($"模型：{model.ModelVersion} · 参数来源：{source}", 12));
        if (_processSupported) { AddCompensationEditor(model); }
        if (compensationInference)
        {
            _fields.Children.Add(Text("同一 item 帧的各检查点 CPT 证据共同用于更新能力概率，当帧最差 D/A/U 档作为观测目标；不对检查点分数加权。", 13));
            _fields.Children.Add(Text("分数 = 低、中、高概率与对应状态分值的乘积之和。最终分数与完整过程曲线末点使用同一组概率。", 13));
        }
        if (model.Prior.Count != 3 || model.StateScores.Count != 3 || _item.Checkpoints.Any(checkpoint =>
            !model.CheckpointModels.TryGetValue(checkpoint.CheckpointId, out var probability)
            || probability.Probabilities.Count != 3
            || probability.Probabilities.Any(row => row.Count != probability.States.Count)))
        {
            _fields.Children.Add(Text("模型的行列结构不完整。请修正配置文件，或显式重新载入本项结构。"));
            return;
        }

        if (_checkpointId is null)
        {
            _fields.Children.Add(Text("先验描述未查看本次证据前的低 / 中 / 高概率。填齐后三个先验之和须为 1，状态分值须在 0–100 内按低 < 中 < 高排列；可以保留空白草稿。", 13));
            var priorGrid = Table(["技能状态", "先验概率", "状态分值"], 4);
            for (var state = 0; state < SkillStates.Length; state++)
            {
                var index = state;
                AddCell(priorGrid, Text(SkillStates[state], 14, true), state + 1, 0);
                AddCell(priorGrid, NumericBox($"{SkillStates[state]}技能先验概率", model.Prior[state], value => model.Prior[index] = value), state + 1, 1);
                AddCell(priorGrid, NumericBox($"{SkillStates[state]}技能状态分值", model.StateScores[state], value => model.StateScores[index] = value), state + 1, 2);
            }
            _fields.Children.Add(priorGrid);
        }
        _fields.Children.Add(Text(compensationInference
            ? "先验非负且总和为 1；CPT 每项须大于 0、每行总和为 1。空白可保留草稿，补齐后才能计算。"
            : _seriesMethod
            ? "这些参数暂不用于生成整段分数。不会把每帧作为独立证据累计，也不会把整段最差档冒充已确定的贝叶斯输入。"
            : "EAP 分数由各技能状态概率和对应分值计算。", 13));
        _fields.Children.Add(Text(compensationInference
            ? "CPT 表示给定模型状态时，观察到检查点 D / A / U 的概率。后验仅反映本套演示假设，不代表已验证的真实能力概率。"
            : "下表保留技能状态与检查点 D / A / U 的条件概率结构。填齐的每行之和须为 1，系统不自动归一化；占比和这些概率的组合方法需另外确定。", 13));
        foreach (var checkpoint in _item.Checkpoints.Where(checkpoint => _checkpointId is null || checkpoint.CheckpointId == _checkpointId))
        {
            var probability = model.CheckpointModels[checkpoint.CheckpointId];
            var block = new StackPanel { Spacing = 8 };
            block.Children.Add(Text(checkpoint.Name, 15, true));
            if (probability.States.SequenceEqual(["D", "U"]))
            {
                block.Children.Add(Text("此检查点只有 D / U 两档，未设置 A 档。", 12));
            }
            var grid = Table(["技能状态", .. probability.States], 4);
            for (var state = 0; state < SkillStates.Length; state++)
            {
                var row = state;
                AddCell(grid, Text(SkillStates[state], 14, true), state + 1, 0);
                for (var observation = 0; observation < probability.States.Count; observation++)
                {
                    var column = observation;
                    AddCell(grid, NumericBox($"{checkpoint.Name}，{SkillStates[state]}技能，{probability.States[observation]} 概率",
                        probability.Probabilities[state][observation], value => probability.Probabilities[row][column] = value), state + 1, observation + 1);
                }
            }
            block.Children.Add(grid);
            _fields.Children.Add(block);
        }
    }

    private void AddCompensationEditor(SceneSkillModel model)
    {
        var block = new StackPanel { Spacing = 10 };
        block.Children.Add(Text("贝叶斯网络更新参数", 17, true));
        block.Children.Add(Text("更新系数 α（0–1）：控制本帧观测对概率修正的幅度。α = 0 时保留 CPT 观测更新结果；α = 1 时完全采用本帧观测目标。0.2 是未标定演示值。", 12));
        block.Children.Add(NumericBox("更新系数 α", model.Compensation?.Alpha,
            value => { model.Compensation ??= new SceneCompensation(); model.Compensation.Alpha = value; }));
        block.Children.Add(Text("α 按有效帧使用，采样率会影响过程响应。缺测不更新概率；分数由更新后的概率换算。", 12));
        _fields.Children.Add(block);
    }

    private FrameworkElement NumericBox(string label, double? value, Action<double?> set, List<Func<bool>>? applyFields = null)
    {
        var box = new TextBox
        {
            Text = value?.ToString("G", CultureInfo.InvariantCulture) ?? "",
            PlaceholderText = "未填写",
            MinWidth = 92,
        };
        AutomationProperties.SetName(box, label);
        var error = Text("请输入有限数值。", 12);
        error.Foreground = (Brush)Application.Current.Resources["SystemFillColorCriticalBrush"];
        error.Visibility = Visibility.Collapsed;
        var panel = new StackPanel { Spacing = 3 };
        panel.Children.Add(box);
        panel.Children.Add(error);
        (applyFields ?? _applyFields).Add(() =>
        {
            if (string.IsNullOrWhiteSpace(box.Text))
            {
                set(null);
                error.Visibility = Visibility.Collapsed;
                return true;
            }
            if (double.TryParse(box.Text, NumberStyles.Float, CultureInfo.InvariantCulture, out var parsed)
                && double.IsFinite(parsed))
            {
                set(parsed);
                error.Visibility = Visibility.Collapsed;
                return true;
            }
            error.Visibility = Visibility.Visible;
            return false;
        });
        return panel;
    }

    private static Grid Table(string[] headers, int rows)
    {
        var grid = new Grid { ColumnSpacing = 10, RowSpacing = 8 };
        for (var column = 0; column < headers.Length; column++)
        {
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        }
        for (var row = 0; row < rows; row++)
        {
            grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        }
        for (var column = 0; column < headers.Length; column++)
        {
            AddCell(grid, Text(headers[column], 13, true), 0, column);
        }
        return grid;
    }

    private static void AddCell(Grid grid, FrameworkElement cell, int row, int column)
    {
        Grid.SetRow(cell, row);
        Grid.SetColumn(cell, column);
        cell.VerticalAlignment = VerticalAlignment.Center;
        grid.Children.Add(cell);
    }

    private static SceneSkillModel Clone(SceneSkillModel model) => SceneSkillModelEditing.Copy(model);

    private static TextBlock Text(string content, double size = 14, bool semibold = false) => new()
    {
        Text = content,
        TextWrapping = TextWrapping.Wrap,
        FontSize = size,
        FontWeight = semibold ? Microsoft.UI.Text.FontWeights.SemiBold : Microsoft.UI.Text.FontWeights.Normal,
    };
}
