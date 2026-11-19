using System.Globalization;
using System.Text;
using System.Text.Json;

using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Windows.Storage.Pickers;

using PilotAssessment.Desktop.Controls.Editors;
using PilotAssessment.Desktop.Controls.Graph;
using PilotAssessment.Desktop.Core.SceneAssessment;
using PilotAssessment.Desktop.Core.State;
using PilotAssessment.Desktop.Services.Backend;

namespace PilotAssessment.Desktop.Views;

public sealed partial class SceneAssessmentWindow : Window
{
    private readonly SceneBackendConnection _backend = new();
    private readonly SceneStudioState _studio = new();
    private SceneDocument? _document;
    private SceneWorkspace? _workspace => _document?.Workspace;
    private string? _configurationPath { get => _document?.ConfigurationPath; set { if (_document is not null) { _document.ConfigurationPath = value; } } }
    private string? _inputPath { get => _document?.InputPath; set { if (_document is not null) { _document.InputPath = value; } } }
    private bool _dirty { get => _document?.IsDirty == true; set { if (_document is not null) { _document.IsDirty = value; } } }
    private bool _busy;
    private bool _initialized;
    private bool _dialogOpen;
    private bool _closeApproved;

    public SceneAssessmentWindow(string theme)
    {
        InitializeComponent();
        RootGrid.RequestedTheme = theme switch
        {
            "Light" => ElementTheme.Light,
            "Dark" => ElementTheme.Dark,
            _ => ElementTheme.Default,
        };
        ExtendsContentIntoTitleBar = true;
        SetTitleBar(SceneTitleBar);
        AppWindow.Resize(new global::Windows.Graphics.SizeInt32(1300, 900));
        AppWindow.SetIcon(DesktopAssetLocator.AppIconPath(AppContext.BaseDirectory));
        AppWindow.Closing += OnClosing;
        StudioCanvas.NodeInvoked += OnStudioNodeInvoked;
    }

    private async void OnLoaded(object sender, RoutedEventArgs args)
    {
        if (_initialized)
        {
            return;
        }
        _initialized = true;
        await RunOperationAsync(async () =>
        {
            await _backend.ConnectAsync();
            var registry = await _backend.Gateway!.GetSceneListAsync();
            foreach (var scene in registry.Scenes)
            {
                _studio.AddCatalog(await _backend.Gateway.GetCatalogAsync(scene.SceneId));
            }
            _document = _studio.Documents.FirstOrDefault();
            RenderSceneNavigation();
            RefreshStudio();
            ShowCurrentView();
            SetStatus("模型工作区已就绪", "总图与场景页共用配置。选择节点编辑模型，或从左侧进入场景评估。", InfoBarSeverity.Informational);
        });
    }

    private void RenderItems()
    {
        ItemCards.Children.Clear();
        if (_workspace is null) { return; }
        var report = _workspace.Report;
        foreach (var item in _workspace.Catalog.Items)
        {
            var result = report?.Items.FirstOrDefault(candidate => candidate.ItemId == item.ItemId);
            var panel = new StackPanel { Spacing = 7 };
            panel.Children.Add(Text($"{item.ItemId}   {item.Name}", 18, true));
            panel.Children.Add(Text(string.Join(" · ", item.Checkpoints.Select(checkpoint => checkpoint.Name)), 13));
            panel.Children.Add(Text(result is null
                ? "尚未评估 · 请先配置参数并导入帧数据"
                : $"{GradeText(result.Grade, result.Passed)}   ·   {SkillScoreText(result.SkillQuantification)}", 14, result is not null));
            if (result is not null) { panel.Children.Add(Text("查看完整结果与过程曲线 →", 13)); }
            var open = new Button
            {
                Content = panel, IsEnabled = result is not null, Tag = result is not null,
                HorizontalAlignment = HorizontalAlignment.Stretch,
                HorizontalContentAlignment = HorizontalAlignment.Stretch,
                Padding = new Thickness(18), CornerRadius = new CornerRadius(8),
            };
            Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(open, $"查看 {item.Name} 的评估结果");
            open.Click += (_, _) => OpenItemReport(item.ItemId);
            var edit = new Button
            {
                Content = item.AssessmentKind == "checklist" ? "查看检查单" : "编辑参数",
                VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(12, 0, 0, 0),
            };
            Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(edit, $"编辑 {item.Name} 的检查参数");
            edit.Click += async (_, _) => await EditItemAsync(item);
            var row = new Grid();
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            row.Children.Add(open);
            Grid.SetColumn(edit, 1);
            row.Children.Add(edit);
            ItemCards.Children.Add(row);
        }
    }

    private readonly List<SceneItemReportWindow> _reportWindows = [];

    private void OpenItemReport(string itemId)
    {
        if (_workspace is null || _busy || _dialogOpen || _workspace.Report is not { } report) { return; }
        var existing = _reportWindows.FirstOrDefault(window => window.SceneId == report.SceneId
            && window.ItemId == itemId && window.EvaluatedAt == report.EvaluatedAt);
        if (existing is not null) { existing.Activate(); return; }
        var window = new SceneItemReportWindow(new SceneItemReportSnapshot(_workspace.Catalog, report, itemId), RootGrid.RequestedTheme);
        _reportWindows.Add(window);
        window.Closed += (_, _) => _reportWindows.Remove(window);
        window.Activate();
    }

    private async Task EditItemAsync(SceneItem item)
    {
        if (_workspace is null || _busy || _dialogOpen)
        {
            return;
        }
        _dialogOpen = true;
        UpdateActions();
        try
        {
            var edit = _workspace.BeginItemEdit(item.ItemId);
            var editor = new SceneItemParameterEditor(_workspace.Catalog, item, edit);
            var dialog = new ContentDialog
            {
                XamlRoot = RootGrid.XamlRoot,
                Title = $"{item.ItemId} · {item.Name}",
                Content = editor,
                PrimaryButtonText = "应用参数",
                SecondaryButtonText = "保留草稿",
                CloseButtonText = "取消",
                DefaultButton = ContentDialogButton.Primary,
                MinWidth = 760,
            };
            dialog.Resources["ContentDialogMaxWidth"] = 860d;
            dialog.PrimaryButtonClick += async (_, args) =>
            {
                var deferral = args.GetDeferral();
                args.Cancel = true;
                try
                {
                    if (!editor.TryApply())
                    {
                        return;
                    }
                    editor.IsEnabled = false;
                    var validation = await _backend.Gateway!.ValidateConfigurationAsync(BuildCandidate());
                    var modelPrefix = $"/skill_models/{item.ItemId}";
                    var related = validation.Issues.Where(issue =>
                        issue.Path == modelPrefix || issue.Path.StartsWith(modelPrefix + "/", StringComparison.Ordinal)
                        || edit.Parameters.Keys.Any(metricId => issue.Path == $"/parameters/{metricId}"
                            || issue.Path.StartsWith($"/parameters/{metricId}/", StringComparison.Ordinal))).ToArray();
                    editor.ShowValidationIssues(related);
                    args.Cancel = related.Length != 0;
                }
                catch (Exception error)
                {
                    editor.ShowValidationFailure(error.Message);
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
                    if (!editor.TryApply())
                    {
                        return;
                    }
                    var candidate = BuildCandidate();
                    var draft = new SceneWorkspace(_workspace.Catalog);
                    draft.LoadConfigurationJson(JsonSerializer.Serialize(candidate, SceneJsonContext.Default.SceneConfiguration));
                    args.Cancel = false;
                }
                catch (Exception error)
                {
                    editor.ShowValidationFailure(error.Message);
                }
            };
            var result = await dialog.ShowAsync();
            if (result is ContentDialogResult.Primary or ContentDialogResult.Secondary)
            {
                var previous = _workspace.SaveConfigurationJson();
                _workspace.CommitItemEdit(edit);
                if (previous != _workspace.SaveConfigurationJson())
                {
                    _dirty = true;
                }
                ClearResults(result == ContentDialogResult.Secondary ? "草稿已保留，补齐参数后请重新评估。" : "参数已应用，请重新评估。");
                RefreshStudio();
                UpdateContext();
                if (result == ContentDialogResult.Secondary)
                {
                    SetStatus("草稿已保留", "草稿已保留到当前配置，尚未通过完整评估校验。可继续编辑，并用“保存配置”写入文件。", InfoBarSeverity.Informational);
                }
                else
                {
                    SetStatus("参数已应用", "检查区间与技能模型已应用，可继续设置其他 item，或保存当前配置。", InfoBarSeverity.Informational);
                }
            }
            else
            {
                _workspace.CancelItemEdit(edit);
            }

            SceneConfiguration BuildCandidate()
            {
                var candidate = _workspace.Configuration;
                foreach (var (metricId, parameter) in edit.Parameters)
                {
                    candidate.Parameters[metricId] = parameter;
                }
                if (edit.SkillModel is { } model)
                {
                    candidate.SkillModels ??= [];
                    candidate.SkillModels[item.ItemId] = model;
                }
                else
                {
                    candidate.SkillModels?.Remove(item.ItemId);
                }
                return candidate;
            }
        }
        catch (Exception error)
        {
            SetStatus("编辑未完成", error.Message, InfoBarSeverity.Error);
        }
        finally
        {
            _dialogOpen = false;
            UpdateActions();
        }
    }

    private async void OnSaveConfiguration(object sender, RoutedEventArgs args) =>
        await RunOperationAsync(async () => { await SaveConfigurationAsync(); });

    private async Task<bool> SaveConfigurationAsync()
    {
        if (_workspace is null)
        {
            return false;
        }
        var path = await PickSaveAsync($"{_workspace.Catalog.SceneId}-configuration.json");
        if (path is null)
        {
            return false;
        }
        await WriteJsonAsync(path, _workspace.SaveConfigurationJson());
        _configurationPath = path;
        _dirty = false;
        UpdateContext();
        SetStatus("配置已保存", path, InfoBarSeverity.Success);
        return true;
    }

    private async void OnLoadConfiguration(object sender, RoutedEventArgs args) =>
        await RunOperationAsync(async () =>
        {
            var path = await PickOpenAsync($"加载 {_workspace!.Catalog.SceneId} 配置");
            if (path is null || !await ResolveUnsavedAsync())
            {
                return;
            }
            var json = await File.ReadAllTextAsync(path);
            _workspace!.LoadConfigurationJson(json);
            _configurationPath = path;
            _dirty = false;
            ClearResults("配置已加载，请重新评估。");
            RefreshStudio();
            UpdateContext();
            var compensationEnabled = _workspace.Configuration.SkillModels?.Values.Any(model => model.InferenceMethod == SceneSkillModel.CompensationInferenceMethod) == true;
            SetStatus("配置已加载", compensationEnabled
                ? "已载入贝叶斯网络配置。可编辑先验、CPT 与更新系数 α；导入帧数据后评估，分数由更新后的概率换算。"
                : "点击 item 查看目标、相对偏差范围与 CPT 草稿，补齐参数后启用贝叶斯网络。", InfoBarSeverity.Success);
        });

    private async void OnExportTemplate(object sender, RoutedEventArgs args) =>
        await RunOperationAsync(async () =>
        {
            var path = await PickSaveAsync($"{_workspace!.Catalog.SceneId}-input-template.json");
            if (path is not null)
            {
                await WriteJsonAsync(path, _workspace!.ExportInputTemplateJson());
                SetStatus("空白输入模板已导出", "模板已按 item 组织；填入每帧的真实时间戳、阶段与原始值后再导入。", InfoBarSeverity.Success);
            }
        });

    private async void OnImportInput(object sender, RoutedEventArgs args) =>
        await RunOperationAsync(async () =>
        {
            var path = await PickOpenAsync("导入帧数据");
            if (path is null)
            {
                return;
            }
            _workspace!.LoadInputJson(await File.ReadAllTextAsync(path));
            _inputPath = path;
            ClearResults("输入结果已更改，请重新评估。");
            RefreshStudio();
            UpdateContext();
            SetStatus("帧数据已导入", "点击“开始评估”计算原值相对目标的偏差、档位与帧分布。", InfoBarSeverity.Success);
        });

    private async void OnEvaluate(object sender, RoutedEventArgs args) =>
        await RunOperationAsync(async () =>
        {
            var validation = await _backend.Gateway!.ValidateConfigurationAsync(_workspace!.Configuration);
            var ruleIssues = validation.Issues.Where(issue => !IsSkillModelPath(issue.Path)).ToArray();
            if (ruleIssues.Length != 0)
            {
                ClearResults("配置需要补充或修正。");
                ResultsPanel.Children.Clear();
                foreach (var issue in ruleIssues)
                {
                    ResultsPanel.Children.Add(Text($"{DescribePath(issue.Path)}：{issue.Message}"));
                }
                SetStatus("尚不能计算", "请按照下面的问题列表补充或修正参数。", InfoBarSeverity.Warning);
                _showStudio = false;
                UpdateViewVisibility();
                return;
            }
            var report = await _backend.Gateway.EvaluateAsync(_workspace.Configuration, _workspace.Input);
            _workspace.SetReport(report);
            RenderReport(report);
            RefreshStudio();
            _showStudio = false;
            UpdateViewVisibility();
            SetStatus(report.CalculationStatus == "complete" ? "评估完成" : "部分结果待补充",
                $"场景：{GradeText(report.Grade, report.Passed)}。点击 item 卡片打开完整结果。",
                report.CalculationStatus != "complete" ? InfoBarSeverity.Warning :
                    report.Passed == true ? InfoBarSeverity.Success : InfoBarSeverity.Warning);
        });

    private async void OnExportReport(object sender, RoutedEventArgs args) =>
        await RunOperationAsync(async () =>
        {
            var json = _workspace!.ExportReportJson();
            var path = await PickSaveAsync($"{_workspace!.Catalog.SceneId}-assessment-report.json");
            if (path is not null)
            {
                await WriteJsonAsync(path, json);
                SetStatus("报告已导出", "报告保留全部输入帧的原值、目标、偏差、档位、阶段与分布，包含输入和配置快照。", InfoBarSeverity.Success);
            }
        });

    private void RenderReport(SceneReport report)
    {
        RenderItems();
        ResultsPanel.Children.Clear();
        ResultsPanel.Children.Add(Text($"场景评估：{GradeText(report.Grade, report.Passed)}", 21, true));
        ResultsPanel.Children.Add(Text("点击上方 item 卡片，在独立窗口查看整项分数变化和各检查点的完整观测。参数通过右侧“编辑参数”单独设置。", 13));
        foreach (var issue in report.Issues)
        {
            ResultsPanel.Children.Add(Text($"{DescribePath(issue.Path)}：{issue.Message}"));
        }
    }

    private static string SkillScoreText(SceneSkillQuantification? quantification) => quantification?.Status switch
    {
        "pending_method" => "请补齐逐帧模型参数并重新评估",
        "not_applicable" => "检查单完成性 · 不推断操纵技能",
        "complete" when quantification?.Method == SceneSkillModel.CompensationInferenceMethod && quantification.Score is { } compensationScore
            => $"末帧模型分数：{compensationScore.ToString("0.0", CultureInfo.InvariantCulture)} / 100 · 贝叶斯网络",
        _ when quantification?.Method == SceneSkillModel.CompensationInferenceMethod
            => $"贝叶斯网络：未输出 · {SkillStatusText(quantification.Status)}",
        _ => $"模型分数：未输出 · {SkillStatusText(quantification?.Status ?? "not_configured")}",
    };

    private static string Number(double? value) => value?.ToString("G", CultureInfo.InvariantCulture) ?? "未提供";

    private static string FormatProbability(double value) => (value * 100).ToString("0.0", CultureInfo.InvariantCulture) + "%";

    private static string FrameProportionsText(SceneFrameDistribution distribution) => string.Join(" · ",
        new[] { "D", "A", "U" }.Select(grade => $"{grade} {(distribution.Proportions.TryGetValue(grade, out var proportion) && proportion is { } value ? FormatProbability(value) : "未提供")}"));

    private static string SkillStatusText(string status) => status switch
    {
        "complete" => "证据完整",
        "pending_method" or "requires_frames" => "需提供逐帧数据及模型参数",
        "not_applicable" => "不适用技能量化",
        "partial" => "证据不完整",
        "not_configured" => "尚未设置模型",
        "not_performed" => "未执行必要动作",
        "unknown_action" => "必要动作状态未知",
        "no_evidence" => "没有可用证据",
        "invalid_model" => "模型参数无效",
        "invalid_evidence" => "证据无效",
        "insufficient_evidence" => "证据不完整",
        "impossible_evidence" => "证据与模型冲突",
        _ => status,
    };

    private static bool IsSkillModelPath(string path) => path == "/skill_models"
        || path.StartsWith("/skill_models/", StringComparison.Ordinal);

    private string DescribePath(string path)
    {
        if (_workspace is null)
        {
            return path;
        }
        foreach (var metric in _workspace.Catalog.Metrics)
        {
            if (path.Contains(metric.MetricId, StringComparison.Ordinal))
            {
                return path.Replace(metric.MetricId, metric.Name, StringComparison.Ordinal);
            }
        }
        return path;
    }

    private void ClearResults(string message)
    {
        RenderItems();
        ResultsPanel.Children.Clear();
        ResultsPanel.Children.Add(Text(message));
        ExportReportButton.IsEnabled = false;
    }

    private void UpdateContext()
    {
        var configuration = _configurationPath is null ? "配置未保存" : Path.GetFileName(_configurationPath);
        var input = _inputPath is null ? "尚未导入帧数据" : $"输入：{Path.GetFileName(_inputPath)}";
        ContextText.Text = $"当前配置 / 输入目标：{_workspace?.Catalog.SceneId ?? "未选择场景"}    |    {configuration}{(_dirty ? " · 有未保存修改" : "")}    |    {input}";
        var compensationEnabled = _workspace?.Configuration.SkillModels?.Values.Any(model => model.InferenceMethod == SceneSkillModel.CompensationInferenceMethod) == true;
        QuantificationNotice.Text = compensationEnabled
            ? "贝叶斯网络\n先验 / CPT / 更新系数 α 可编辑 · 未标定"
            : "CPT 参数可编辑\n补齐后启用贝叶斯网络";
        UpdateActions();
    }

    private void UpdateActions()
    {
        Actions.IsEnabled = _workspace is not null && !_busy && !_dialogOpen;
        foreach (var button in ItemCards.Children.OfType<Grid>().SelectMany(row => row.Children.OfType<Button>()))
        {
            button.IsEnabled = Actions.IsEnabled && button.Tag is not false;
        }
        ExportReportButton.IsEnabled = _workspace?.HasReport == true && !_busy;
        StudioNavigationButton.IsEnabled = Actions.IsEnabled;
        SceneNavigation.IsHitTestVisible = Actions.IsEnabled;
        StudioCanvas.IsHitTestVisible = Actions.IsEnabled;
        StudioInspector.IsHitTestVisible = Actions.IsEnabled;
    }

    private async Task RunOperationAsync(Func<Task> operation)
    {
        if (_busy || _dialogOpen)
        {
            return;
        }
        _busy = true;
        UpdateActions();
        try
        {
            await operation();
        }
        catch (Exception error)
        {
            SetStatus("操作未完成", error.Message, InfoBarSeverity.Error);
        }
        finally
        {
            _busy = false;
            UpdateActions();
        }
    }

    private async Task<bool> ResolveUnsavedAsync()
    {
        if (!_dirty)
        {
            return true;
        }
        _dialogOpen = true;
        try
        {
            var dialog = new ContentDialog
            {
                XamlRoot = RootGrid.XamlRoot,
                Title = $"保存 {_workspace?.Catalog.Name} 的修改？",
                Content = "当前场景参数尚未保存。可以先保存配置，或放弃这些修改。",
                PrimaryButtonText = "保存配置",
                SecondaryButtonText = "放弃修改",
                CloseButtonText = "取消",
                DefaultButton = ContentDialogButton.Close,
            };
            return await dialog.ShowAsync() switch
            {
                ContentDialogResult.Primary => await SaveConfigurationAsync(),
                ContentDialogResult.Secondary => true,
                _ => false,
            };
        }
        finally
        {
            _dialogOpen = false;
        }
    }

    private async void OnClosing(AppWindow sender, AppWindowClosingEventArgs args)
    {
        if (_closeApproved)
        {
            return;
        }
        args.Cancel = true;
        if (_busy || _dialogOpen)
        {
            return;
        }
        _busy = true;
        UpdateActions();
        try
        {
            foreach (var document in _studio.Documents.Where(document => document.IsDirty).ToArray())
            {
                _document = document;
                ShowCurrentView();
                if (!await ResolveUnsavedAsync())
                {
                    return;
                }
            }
            await _backend.DisposeAsync();
            foreach (var window in _reportWindows.ToArray()) { window.Close(); }
            _closeApproved = true;
            Close();
        }
        catch (Exception error)
        {
            SetStatus("关闭未完成", error.Message, InfoBarSeverity.Error);
        }
        finally
        {
            _busy = false;
            if (!_closeApproved)
            {
                UpdateActions();
            }
        }
    }

    private async Task<string?> PickOpenAsync(string title)
    {
        var picker = new FileOpenPicker
        {
            SuggestedStartLocation = PickerLocationId.DocumentsLibrary,
            CommitButtonText = title,
        };
        picker.FileTypeFilter.Add(".json");
        WinRT.Interop.InitializeWithWindow.Initialize(picker, App.WindowHandle);
        return (await picker.PickSingleFileAsync())?.Path;
    }

    private async Task<string?> PickSaveAsync(string fileName)
    {
        var picker = new FileSavePicker
        {
            SuggestedStartLocation = PickerLocationId.DocumentsLibrary,
            SuggestedFileName = fileName,
            DefaultFileExtension = ".json",
        };
        picker.FileTypeChoices.Add("JSON 文件", [".json"]);
        WinRT.Interop.InitializeWithWindow.Initialize(picker, App.WindowHandle);
        return (await picker.PickSaveFileAsync())?.Path;
    }

    private static async Task WriteJsonAsync(string path, string json)
    {
        var temporary = Path.Combine(Path.GetDirectoryName(path)!, $".{Path.GetFileName(path)}.{Guid.NewGuid():N}.tmp");
        try
        {
            await File.WriteAllTextAsync(temporary, json, new UTF8Encoding(false));
            File.Move(temporary, path, overwrite: true);
        }
        finally
        {
            if (File.Exists(temporary))
            {
                File.Delete(temporary);
            }
        }
    }

    private void SetStatus(string title, string message, InfoBarSeverity severity)
    {
        StatusBar.Title = title;
        StatusBar.Message = message;
        StatusBar.Severity = severity;
        StatusBar.IsOpen = true;
    }

    private static string GradeText(string? grade, bool? passed) => grade is null
        ? "尚无结论" : $"{grade} / {passed switch { true => "Pass", false => "Fail", null => "尚未完整评估" }}";

    private static string StatusText(string status) => status switch
    {
        "missing" => "待补充",
        "invalid" => "数据无效",
        "not_required" => "本次不要求",
        _ => "尚无结论",
    };

    private static string FormatValue(JsonElement value) => value.ValueKind switch
    {
        JsonValueKind.True => "是",
        JsonValueKind.False => "否",
        JsonValueKind.Null => "缺失",
        _ => value.ToString(),
    };

    private static string FormatInterval(SceneInterval interval) =>
        $"[{interval.Lower?.ToString("G", CultureInfo.InvariantCulture) ?? "未填"}, " +
        $"{(interval.UnboundedUpper ? "∞" : interval.Upper?.ToString("G", CultureInfo.InvariantCulture) ?? "未填")} ]";

    private static string FormatAllowances(SceneInterval interval) =>
        $"低于 {Number(-interval.Lower)} / 高于 {(interval.UnboundedUpper ? "无上限" : Number(interval.Upper))}";

    private static TextBlock Text(string content, double size = 14, bool semibold = false) => new()
    {
        Text = content,
        TextWrapping = TextWrapping.Wrap,
        FontSize = size,
        FontWeight = semibold ? Microsoft.UI.Text.FontWeights.SemiBold : Microsoft.UI.Text.FontWeights.Normal,
    };
}
