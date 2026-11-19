using System.Globalization;
using System.Text.Json;

using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

using PilotAssessment.Desktop.Controls.Editors;
using PilotAssessment.Desktop.Core.SceneAssessment;

namespace PilotAssessment.Desktop.Views;

public sealed partial class SceneAssessmentWindow
{
    private bool _showStudio = true;
    private SceneGraphProjection? _projection;
    private string? _selectedNodeId;

    private void RenderSceneNavigation()
    {
        SceneNavigation.Children.Clear();
        foreach (var document in _studio.Documents)
        {
            var catalog = document.Workspace.Catalog;
            var label = new StackPanel { Spacing = 5 };
            label.Children.Add(Text(catalog.SceneId, 12, true));
            label.Children.Add(Text(catalog.Name, 16, true));
            var button = new Button
            {
                Content = label, Tag = catalog.SceneId, Padding = new Thickness(14), CornerRadius = new CornerRadius(8),
                HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Left,
            };
            Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(button, $"打开场景 {catalog.SceneId} {catalog.Name}");
            button.Click += (_, _) =>
            {
                if (_busy || _dialogOpen) { return; }
                _document = document;
                _showStudio = false;
                ShowCurrentView();
            };
            SceneNavigation.Children.Add(button);
        }
    }

    private void OnStudioNavigation(object sender, RoutedEventArgs args)
    {
        if (_busy || _dialogOpen) { return; }
        _showStudio = true;
        if (_projection?.Nodes.FirstOrDefault(node => node.Id == _selectedNodeId) is { } selected)
        {
            _document = _studio.GetDocument(selected.SceneId);
        }
        RefreshStudio();
        ShowCurrentView();
    }

    private void UpdateViewVisibility()
    {
        StudioContent.Visibility = _showStudio ? Visibility.Visible : Visibility.Collapsed;
        SceneContent.Visibility = _showStudio ? Visibility.Collapsed : Visibility.Visible;
        PageHeading.Text = _showStudio ? "Model Studio" : _workspace?.Catalog.Name ?? "评估场景";
        PageDescription.Text = _showStudio
            ? $"{_studio.Documents.Count} 个场景的模型总图 · 点击节点查看和编辑 · 配置与各场景共用"
            : "设置目标与允许量，按 item 导入真实帧，查看 D/A/U、P/F、阶段结果与帧分布。";
        SetNavigationAppearance(StudioNavigationButton, _showStudio);
        foreach (var button in SceneNavigation.Children.OfType<Button>())
        {
            SetNavigationAppearance(button, !_showStudio && (string?)button.Tag == _workspace?.Catalog.SceneId);
        }
    }

    private static void SetNavigationAppearance(Button button, bool selected)
    {
        button.Background = (Brush)Application.Current.Resources[selected ? "AccentFillColorDefaultBrush" : "ControlFillColorDefaultBrush"];
        button.Foreground = (Brush)Application.Current.Resources[selected ? "TextOnAccentFillColorPrimaryBrush" : "TextFillColorPrimaryBrush"];
    }

    private void ShowCurrentView()
    {
        UpdateViewVisibility();
        RenderItems();
        if (_workspace?.Report is { } report)
        {
            RenderReport(report);
        }
        else
        {
            ClearResults("完成参数配置并导入帧数据后，点击“开始评估”。");
        }
        UpdateContext();
    }

    private void RefreshStudio()
    {
        _projection = SceneGraphProjection.Build(_studio.Documents.Select(document => document.Workspace));
        StudioCanvas.SetProjection(_projection);
        RenderInspector(_projection.Nodes.FirstOrDefault(node => node.Id == _selectedNodeId));
    }

    private void OnStudioNodeInvoked(object? sender, SceneGraphNode node)
    {
        if (_busy || _dialogOpen) { return; }
        _selectedNodeId = node.Id;
        _document = _studio.GetDocument(node.SceneId);
        RenderInspector(node);
        UpdateContext();
    }

    private void RenderInspector(SceneGraphNode? node)
    {
        StudioInspector.Children.Clear();
        if (node is null || _workspace is null)
        {
            StudioInspector.Children.Add(Text("模型检查器", 21, true));
            StudioInspector.Children.Add(Text("点击总图中的一个节点。"));
            StudioInspector.Children.Add(Text("Task：场景范围与通过规则\nChecklist：程序完成性\n飞行 item：目标、偏差范围及 CPT 草稿\n检查点：原始量与判定方法", 14));
            StudioInspector.Children.Add(Text("贝叶斯网络根据每帧观测更新能力概率。可编辑先验、CPT 和更新系数 α；空白配置须补齐参数后才能评估。分数由概率换算，规则 P/F 独立保留。", 13));
            return;
        }

        var workspace = _studio.GetDocument(node.SceneId).Workspace;
        StudioInspector.Children.Add(Text(node.Kind switch { "task" => "Task · 场景", "item" => "item · 技能", _ => "检查点 · 观察" }, 12, true));
        StudioInspector.Children.Add(Text(node.Title, 21, true));
        StudioInspector.Children.Add(Text(workspace.Catalog.SceneId + " · " + workspace.Catalog.Name, 12));
        StudioInspector.Children.Add(Text(node.Detail, 14));
        if (node.Grade is not null)
        {
            StudioInspector.Children.Add(Text($"本次判定：{node.Grade} / {(node.Grade == "U" ? "Fail" : "Pass")}", 17, true));
        }
        if (node.Score is { } score)
        {
            var quantification = workspace.Report?.Items.FirstOrDefault(result => result.ItemId == node.ItemId)?.SkillQuantification;
            StudioInspector.Children.Add(Text($"末帧概率对应分数：{score.ToString("0.0", CultureInfo.InvariantCulture)} / 100 · 未标定", 17, true));
            if (quantification?.Posterior is { Count: 3 } posterior)
            {
                StudioInspector.Children.Add(Text($"模型状态概率：低 {FormatProbability(posterior[0])} · 中 {FormatProbability(posterior[1])} · 高 {FormatProbability(posterior[2])}", 14));
            }
        }
        if (node.Kind == "task")
        {
            StudioInspector.Children.Add(Text("Task 根据 item 的最差档得到 D/A/U 与 P/F。虚线表示这些 item 属于此场景；当前没有 Task CPT 或场景技能总分。", 14));
        }
        else
        {
            var item = workspace.Catalog.Items.Single(item => item.ItemId == node.ItemId);
            if (workspace.Report?.Items.Any(result => result.ItemId == item.ItemId) == true)
            {
                AddInspectorAction("打开此 item 的完整评估结果", () =>
                {
                    _document = _studio.GetDocument(node.SceneId);
                    OpenItemReport(item.ItemId);
                    return Task.CompletedTask;
                });
            }
            if (item.Phases is { Count: > 0 })
            {
                StudioInspector.Children.Add(Text("阶段：" + string.Join(" → ", item.Phases.Select(phase => phase.Name)), 13));
            }
            if (item.AssessmentKind == "checklist")
            {
                StudioInspector.Children.Add(Text("检查单只评价完成性：true → D / Pass，false → U / Fail。缺失不等于未完成；不设置操纵技能 CPT。", 14));
            }
            else
            {
                var model = workspace.Configuration.SkillModels?.GetValueOrDefault(item.ItemId);
                var compensationEnabled = model?.InferenceMethod == SceneSkillModel.CompensationInferenceMethod;
                StudioInspector.Children.Add(Text("量化对象：" + item.SkillName, 14));
                StudioInspector.Children.Add(Text(compensationEnabled
                    ? "贝叶斯网络根据每帧观测更新概率并换算分数，完整过程与最终结果同源。"
                    : item.SkillDescription, 13));
                if (node.Kind == "checkpoint")
                {
                    RenderCheckpointProbabilities(workspace, item.ItemId, node.CheckpointId!);
                }
                AddInspectorAction(node.Kind == "checkpoint"
                    ? "编辑此检查点 CPT"
                    : "编辑先验、CPT 与更新系数", () =>
                {
                    _document = _studio.GetDocument(node.SceneId);
                    return EditSkillModelAsync(item, node.CheckpointId);
                });
                StudioInspector.Children.Add(Text(compensationEnabled
                    ? $"更新系数 α = {model!.Compensation?.Alpha?.ToString("0.####", CultureInfo.InvariantCulture) ?? "未填"}，控制本帧观测对概率修正的幅度。参数未标定，采样率影响响应；规则 P/F 独立保留。"
                    : "参数可以留空并保存草稿，补齐先验、CPT 与更新系数后启用贝叶斯网络。", 12));
            }
            AddInspectorAction(item.AssessmentKind == "checklist" ? "查看检查单与来源" : "编辑此 item 的目标和偏差范围", () =>
            {
                _document = _studio.GetDocument(node.SceneId);
                return EditItemAsync(item);
            });
        }
        AddInspectorAction("进入此场景评估", () =>
        {
            _document = _studio.GetDocument(node.SceneId);
            _showStudio = false;
            ShowCurrentView();
            return Task.CompletedTask;
        });
    }

    private void RenderCheckpointProbabilities(SceneWorkspace workspace, string itemId, string checkpointId)
    {
        var models = workspace.Configuration.SkillModels;
        if (models is null || !models.TryGetValue(itemId, out var model)
            || !model.CheckpointModels.TryGetValue(checkpointId, out var checkpoint))
        {
            StudioInspector.Children.Add(Text("此配置尚未设置模型。可通过编辑入口载入空白参数草稿。", 13));
            return;
        }
        StudioInspector.Children.Add(Text("条件概率表 · 贝叶斯网络 · 未标定", 15, true));
        StudioInspector.Children.Add(Text("技能状态    " + string.Join("    ", checkpoint.States), 13, true));
        var labels = new[] { "低", "中", "高" };
        for (var row = 0; row < checkpoint.Probabilities.Count; row++)
        {
            StudioInspector.Children.Add(Text(labels[row] + "    " + string.Join("    ", checkpoint.Probabilities[row]
                .Select(value => value?.ToString("0.####", CultureInfo.InvariantCulture) ?? "未填")), 14));
        }
    }

    private void AddInspectorAction(string label, Func<Task> action)
    {
        var button = new Button { Content = label, HorizontalAlignment = HorizontalAlignment.Stretch };
        button.Click += async (_, _) =>
        {
            if (!_busy && !_dialogOpen) { await action(); }
        };
        StudioInspector.Children.Add(button);
    }

    private async Task EditSkillModelAsync(SceneItem item, string? checkpointId)
    {
        if (_workspace is null || _busy || _dialogOpen || item.AssessmentKind == "checklist") { return; }
        var workspace = _workspace;
        _dialogOpen = true;
        UpdateActions();
        try
        {
            var edit = workspace.BeginItemEdit(item.ItemId);
            var editor = new SceneSkillModelEditor(workspace.Catalog, item, edit, checkpointId);
            var dialog = new ContentDialog
            {
                XamlRoot = RootGrid.XamlRoot,
                Title = checkpointId is null ? $"{item.Name} · 贝叶斯参数" : $"{item.Checkpoints.Single(point => point.CheckpointId == checkpointId).Name} · CPT",
                Content = new ScrollViewer { Content = editor, MaxHeight = 570, VerticalScrollBarVisibility = ScrollBarVisibility.Auto },
                PrimaryButtonText = "应用模型参数", SecondaryButtonText = "保留草稿", CloseButtonText = "取消", MinWidth = 760,
                DefaultButton = ContentDialogButton.Primary,
            };
            dialog.Resources["ContentDialogMaxWidth"] = 860d;
            dialog.PrimaryButtonClick += async (_, args) =>
            {
                var deferral = args.GetDeferral();
                args.Cancel = true;
                try
                {
                    if (!editor.TryApply()) { return; }
                    editor.IsEnabled = false;
                    var validation = await _backend.Gateway!.ValidateConfigurationAsync(BuildCandidate());
                    var prefix = $"/skill_models/{item.ItemId}";
                    var related = validation.Issues.Where(issue => issue.Path == prefix || issue.Path.StartsWith(prefix + "/", StringComparison.Ordinal)).ToArray();
                    editor.ShowValidationIssues(related);
                    args.Cancel = related.Length != 0;
                }
                catch (Exception error)
                {
                    editor.ShowValidationIssues([new() { Path = $"/skill_models/{item.ItemId}", Message = error.Message }]);
                }
                finally
                {
                    editor.IsEnabled = true;
                    deferral.Complete();
                }
            };
            dialog.SecondaryButtonClick += (_, args) =>
            {
                args.Cancel = true;
                try
                {
                    if (!editor.TryApply()) { return; }
                    var draft = new SceneWorkspace(workspace.Catalog);
                    draft.LoadConfigurationJson(JsonSerializer.Serialize(BuildCandidate(), SceneJsonContext.Default.SceneConfiguration));
                    args.Cancel = false;
                }
                catch (Exception error)
                {
                    editor.ShowValidationIssues([new() { Path = $"/skill_models/{item.ItemId}", Message = error.Message }]);
                }
            };
            var result = await dialog.ShowAsync();
            if (result is ContentDialogResult.Primary or ContentDialogResult.Secondary)
            {
                var before = workspace.SaveConfigurationJson();
                workspace.CommitItemEdit(edit);
                _dirty |= before != workspace.SaveConfigurationJson();
                ClearResults("模型参数已更改，请重新评估。");
                RefreshStudio();
                UpdateContext();
                SetStatus(result == ContentDialogResult.Secondary ? "模型草稿已保留" : "模型参数已应用",
                    result == ContentDialogResult.Secondary ? "草稿已保留到当前配置，可用“保存配置”写入文件；补齐参数后才可演示量化。"
                    : $"{workspace.Catalog.Name} 的配置已更新，场景页使用同一组参数。", InfoBarSeverity.Success);
            }
            else
            {
                workspace.CancelItemEdit(edit);
            }

            SceneConfiguration BuildCandidate()
            {
                var configuration = workspace.Configuration;
                if (edit.SkillModel is { } model)
                {
                    configuration.SkillModels ??= [];
                    configuration.SkillModels[item.ItemId] = model;
                }
                return configuration;
            }
        }
        catch (Exception error)
        {
            SetStatus("模型编辑未完成", error.Message, InfoBarSeverity.Error);
        }
        finally
        {
            _dialogOpen = false;
            UpdateActions();
        }
    }
}
