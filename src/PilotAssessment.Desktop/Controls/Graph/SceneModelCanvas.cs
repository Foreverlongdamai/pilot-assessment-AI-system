using System.Globalization;

using Microsoft.UI;
using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;

using PilotAssessment.Desktop.Core.SceneAssessment;

using Windows.Foundation;

namespace PilotAssessment.Desktop.Controls.Graph;

/// <summary>Displays the published scene hierarchy and each item's Bayesian evidence links.</summary>
public sealed class SceneModelCanvas : UserControl
{
    private const float MinimumZoom = 0.15f;
    private const float MaximumZoom = 2.5f;
    private readonly Canvas _surface = new();
    private readonly ScrollViewer _scrollViewer;
    private readonly Grid _root = new();
    private readonly TextBlock _zoomText = new() { Text = "100%", MinWidth = 48, TextAlignment = TextAlignment.Center, VerticalAlignment = VerticalAlignment.Center };
    private readonly TextBlock _summaryText = new() { TextWrapping = TextWrapping.Wrap, VerticalAlignment = VerticalAlignment.Center };
    private readonly Dictionary<string, Button> _nodeButtons = new(StringComparer.Ordinal);
    private SceneGraphProjection? _projection;
    private string? _selectedNodeId;
    private bool _needsInitialFit = true;
    private uint? _panPointerId;
    private Point _panStart;
    private double _panHorizontal;
    private double _panVertical;
    private bool _panMoved;

    public SceneModelCanvas()
    {
        _root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        _root.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        _root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });

        var toolbar = new Grid { Padding = new Thickness(12, 10, 12, 10), ColumnSpacing = 12 };
        toolbar.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        toolbar.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        toolbar.Children.Add(_summaryText);
        var zoomTools = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 4 };
        zoomTools.Children.Add(CreateButton("−", "缩小画布", () => SetZoom(_scrollViewer!.ZoomFactor / 1.2f)));
        zoomTools.Children.Add(_zoomText);
        zoomTools.Children.Add(CreateButton("＋", "放大画布", () => SetZoom(_scrollViewer!.ZoomFactor * 1.2f)));
        zoomTools.Children.Add(CreateButton("适应全图", "缩放以查看全部场景", FitAll));
        zoomTools.Children.Add(CreateButton("100%", "恢复原始大小", () => SetZoom(1)));
        Grid.SetColumn(zoomTools, 1);
        toolbar.Children.Add(zoomTools);
        _root.Children.Add(toolbar);

        _scrollViewer = new ScrollViewer
        {
            Content = _surface,
            HorizontalScrollBarVisibility = ScrollBarVisibility.Auto,
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
            HorizontalScrollMode = ScrollMode.Enabled,
            VerticalScrollMode = ScrollMode.Enabled,
            ZoomMode = ZoomMode.Enabled,
            MinZoomFactor = MinimumZoom,
            MaxZoomFactor = MaximumZoom,
            HorizontalContentAlignment = HorizontalAlignment.Left,
            VerticalContentAlignment = VerticalAlignment.Top,
        };
        AutomationProperties.SetName(_scrollViewer, "全部场景模型画布，可双向滚动和缩放");
        _scrollViewer.ViewChanged += (_, _) => _zoomText.Text = $"{_scrollViewer.ZoomFactor:P0}";
        _scrollViewer.SizeChanged += (_, _) => TryInitialFit();
        _surface.PointerPressed += OnPointerPressed;
        _surface.PointerMoved += OnPointerMoved;
        _surface.PointerReleased += OnPointerReleased;
        _surface.PointerCanceled += OnPointerReleased;
        _surface.PointerCaptureLost += (_, _) => ResetPan();
        Grid.SetRow(_scrollViewer, 1);
        _root.Children.Add(_scrollViewer);

        var legend = new StackPanel { Padding = new Thickness(12, 9, 12, 9), Spacing = 4 };
        legend.Children.Add(new TextBlock
        {
            Text = "┄┄  场景 / 检查单归属     ──▶  飞行 item → 检查点：CPT 结构",
            TextWrapping = TextWrapping.Wrap,
            FontSize = 12,
        });
        legend.Children.Add(new TextBlock
        {
            Text = "点击节点编辑目标、容差或 CPT · 拖动画布空白处平移 · 演示分均未标定，正式方法待确定",
            TextWrapping = TextWrapping.Wrap,
            FontSize = 12,
            Opacity = 0.72,
        });
        Grid.SetRow(legend, 2);
        _root.Children.Add(legend);
        Content = _root;
        Loaded += (_, _) => TryInitialFit();
        ActualThemeChanged += (_, _) => RenderProjection();
    }

    public event EventHandler<SceneGraphNode>? NodeInvoked;

    /// <summary>Refreshes displayed values without resetting the viewport for unchanged geometry.</summary>
    public void SetProjection(SceneGraphProjection projection)
    {
        ArgumentNullException.ThrowIfNull(projection);
        if (_projection is null || !HasSameGeometry(_projection, projection))
        {
            _needsInitialFit = true;
        }

        _projection = projection;
        if (!projection.Nodes.Any(node => node.Id == _selectedNodeId))
        {
            _selectedNodeId = null;
        }

        RenderProjection();
        TryInitialFit();
    }

    private void RenderProjection()
    {
        _root.Background = ThemeBrush("LayerFillColorAltBrush");
        _surface.Background = new SolidColorBrush(Colors.Transparent);
        _surface.Children.Clear();
        _nodeButtons.Clear();
        if (_projection is null)
        {
            return;
        }

        _surface.Width = _projection.Width;
        _surface.Height = _projection.Height;
        var sceneGroups = _projection.Nodes.GroupBy(node => node.SceneId).ToArray();
        _summaryText.Text = $"{sceneGroups.Length} 个场景 · {_projection.Nodes.Count(node => node.Kind == "item")} 个 item · {_projection.Nodes.Count(node => node.Kind == "checkpoint")} 个检查点";
        AddLabel("TASK / 场景任务", 40, 16, 230);
        AddLabel("ITEM / 评估项", 340, 16, 270);
        AddLabel("CHECKPOINT / 检查点证据", 760, 16, 330);

        foreach (var group in sceneGroups)
        {
            var top = group.Min(node => node.Y);
            var bottom = group.Max(node => node.Y + node.Height);
            var task = group.FirstOrDefault(node => node.Kind == "task");
            AddLabel($"{group.Key}  {task?.Title}", 40, Math.Max(46, top - 50), _projection.Width - 80);
            var boundary = new Border
            {
                Width = _projection.Width - 32,
                Height = bottom - top + 28,
                CornerRadius = new CornerRadius(12),
                BorderBrush = ThemeBrush("CardStrokeColorDefaultBrush"),
                BorderThickness = new Thickness(1),
                IsHitTestVisible = false,
            };
            Place(boundary, 16, top - 14);
        }

        var nodesById = _projection.Nodes.ToDictionary(node => node.Id, StringComparer.Ordinal);
        foreach (var edge in _projection.Edges)
        {
            if (nodesById.TryGetValue(edge.FromId, out var from) && nodesById.TryGetValue(edge.ToId, out var to))
            {
                RenderEdge(from, to, edge.Kind == "bayesian");
            }
        }

        foreach (var node in _projection.Nodes)
        {
            RenderNode(node);
        }
    }

    private void RenderEdge(SceneGraphNode from, SceneGraphNode to, bool isBayesian)
    {
        var start = new Point(from.X + from.Width, from.Y + from.Height / 2);
        var end = new Point(to.X - (isBayesian ? 7 : 0), to.Y + to.Height / 2);
        var bend = (end.X - start.X) / 2;
        var figure = new PathFigure { StartPoint = start };
        figure.Segments.Add(new BezierSegment
        {
            Point1 = new Point(start.X + bend, start.Y),
            Point2 = new Point(end.X - bend, end.Y),
            Point3 = end,
        });
        var geometry = new PathGeometry();
        geometry.Figures.Add(figure);
        var brush = ThemeBrush(isBayesian ? "GraphProbabilisticEdgeBrush" : "TextFillColorTertiaryBrush");
        var path = new Microsoft.UI.Xaml.Shapes.Path
        {
            Data = geometry,
            Stroke = brush,
            StrokeThickness = isBayesian ? 1.8 : 1.4,
            IsHitTestVisible = false,
        };
        if (!isBayesian)
        {
            path.StrokeDashArray = [4, 4];
        }

        _surface.Children.Add(path);
        if (isBayesian)
        {
            _surface.Children.Add(new Polygon
            {
                Points = [new Point(to.X, end.Y), new Point(end.X - 2, end.Y - 4), new Point(end.X - 2, end.Y + 4)],
                Fill = brush,
                IsHitTestVisible = false,
            });
        }
    }

    private void RenderNode(SceneGraphNode node)
    {
        var kindLabel = node.Kind switch { "task" => "TASK", "item" => "ITEM", _ => "CHECKPOINT" };
        var identity = node.CheckpointId ?? node.ItemId ?? node.SceneId;
        var gradeLabel = node.Grade is "D" or "A" ? $"{node.Grade} · Pass" : node.Grade is "U" ? "U · Fail" : "待评估";
        var statusLabel = node.Kind == "item" && node.Score is double score
            ? $"{gradeLabel}   末帧模型分 {score.ToString("0.0", CultureInfo.CurrentCulture)}"
            : gradeLabel;
        var body = new StackPanel { Spacing = 2 };
        body.Children.Add(new TextBlock
        {
            Text = $"{kindLabel} · {identity}",
            FontSize = 10,
            Foreground = ThemeBrush("TextFillColorSecondaryBrush"),
            TextTrimming = TextTrimming.CharacterEllipsis,
        });
        body.Children.Add(new TextBlock
        {
            Text = node.Title,
            FontSize = 14,
            FontWeight = FontWeights.SemiBold,
            TextTrimming = TextTrimming.CharacterEllipsis,
        });
        body.Children.Add(new TextBlock
        {
            Text = statusLabel,
            FontSize = 11,
            Foreground = ThemeBrush(node.Grade switch
            {
                "D" => "SystemFillColorSuccessBrush",
                "A" => "SystemFillColorCautionBrush",
                "U" => "SystemFillColorCriticalBrush",
                _ => "TextFillColorSecondaryBrush",
            }),
        });
        var button = new Button
        {
            Content = body,
            Width = node.Width,
            Height = node.Height,
            Padding = new Thickness(12, 7, 12, 7),
            HorizontalContentAlignment = HorizontalAlignment.Stretch,
            VerticalContentAlignment = VerticalAlignment.Center,
            CornerRadius = new CornerRadius(8),
            Background = ThemeBrush("CardBackgroundFillColorDefaultBrush"),
            BorderBrush = NodeBorderBrush(node),
            BorderThickness = new Thickness(node.Id == _selectedNodeId ? 3 : 1.5),
            Tag = node,
        };
        AutomationProperties.SetName(button, $"{node.SceneId}，{kindLabel}，{node.Title}，{statusLabel}");
        AutomationProperties.SetHelpText(button, node.Detail);
        AutomationProperties.SetAutomationId(button, $"ModelNode_{node.Id}");
        ToolTipService.SetToolTip(button, $"{node.Title}\n{node.Detail}\n{statusLabel}");
        button.Click += (_, _) => SelectNode(node);
        _nodeButtons.Add(node.Id, button);
        Place(button, node.X, node.Y);
    }

    private void SelectNode(SceneGraphNode node)
    {
        _selectedNodeId = node.Id;
        foreach (var button in _nodeButtons.Values)
        {
            var buttonNode = (SceneGraphNode)button.Tag;
            button.BorderThickness = new Thickness(buttonNode.Id == node.Id ? 3 : 1.5);
            button.BorderBrush = NodeBorderBrush(buttonNode);
        }

        NodeInvoked?.Invoke(this, node);
    }

    private Brush NodeBorderBrush(SceneGraphNode node) => ThemeBrush(node.Id == _selectedNodeId
        ? "AccentFillColorDefaultBrush"
        : node.Kind switch
        {
            "item" => "GraphBnNodeBrush",
            "checkpoint" => "GraphEvidenceNodeBrush",
            _ => "ControlStrokeColorSecondaryBrush",
        });

    private void AddLabel(string text, double x, double y, double width) => Place(new TextBlock
    {
        Text = text,
        FontSize = 12,
        FontWeight = FontWeights.SemiBold,
        Width = width,
        Foreground = ThemeBrush("TextFillColorSecondaryBrush"),
        TextTrimming = TextTrimming.CharacterEllipsis,
        IsHitTestVisible = false,
    }, x, y);

    private void Place(FrameworkElement element, double x, double y)
    {
        Canvas.SetLeft(element, x);
        Canvas.SetTop(element, y);
        _surface.Children.Add(element);
    }

    private static Button CreateButton(string content, string name, Action action)
    {
        var button = new Button { Content = content, MinWidth = 32, Padding = new Thickness(9, 5, 9, 5) };
        AutomationProperties.SetName(button, name);
        ToolTipService.SetToolTip(button, name);
        button.Click += (_, _) => action();
        return button;
    }

    private void TryInitialFit()
    {
        if (!_needsInitialFit || _projection is null || _scrollViewer.ViewportWidth <= 0)
        {
            return;
        }

        _needsInitialFit = false;
        // Initial viewing preserves readable labels; the explicit fit command may zoom out further.
        var zoom = (float)Math.Clamp((_scrollViewer.ViewportWidth - 24) / Math.Max(_projection.Width, 1), 0.45, 1);
        _ = _scrollViewer.ChangeView(0, 0, zoom, true);
    }

    private void FitAll()
    {
        if (_projection is null || _scrollViewer.ViewportWidth <= 0 || _scrollViewer.ViewportHeight <= 0)
        {
            return;
        }

        var scale = Math.Min(_scrollViewer.ViewportWidth / Math.Max(_projection.Width, 1),
            _scrollViewer.ViewportHeight / Math.Max(_projection.Height, 1)) * 0.94;
        _ = _scrollViewer.ChangeView(0, 0, (float)Math.Clamp(scale, MinimumZoom, MaximumZoom), true);
    }

    private void SetZoom(float zoom) => _ = _scrollViewer.ChangeView(null, null, Math.Clamp(zoom, MinimumZoom, MaximumZoom), false);

    private void OnPointerPressed(object sender, PointerRoutedEventArgs args)
    {
        var point = args.GetCurrentPoint(_scrollViewer);
        if (!point.Properties.IsLeftButtonPressed || IsNodeSource(args.OriginalSource))
        {
            return;
        }

        _panPointerId = args.Pointer.PointerId;
        _panStart = point.Position;
        _panHorizontal = _scrollViewer.HorizontalOffset;
        _panVertical = _scrollViewer.VerticalOffset;
        _surface.CapturePointer(args.Pointer);
    }

    private void OnPointerMoved(object sender, PointerRoutedEventArgs args)
    {
        if (_panPointerId != args.Pointer.PointerId)
        {
            return;
        }

        var point = args.GetCurrentPoint(_scrollViewer).Position;
        var x = point.X - _panStart.X;
        var y = point.Y - _panStart.Y;
        _panMoved |= x * x + y * y > 16;
        if (_panMoved)
        {
            _ = _scrollViewer.ChangeView(Math.Clamp(_panHorizontal - x, 0, _scrollViewer.ScrollableWidth),
                Math.Clamp(_panVertical - y, 0, _scrollViewer.ScrollableHeight), null, true);
            args.Handled = true;
        }
    }

    private void OnPointerReleased(object sender, PointerRoutedEventArgs args)
    {
        if (_panPointerId == args.Pointer.PointerId)
        {
            args.Handled = _panMoved;
            _surface.ReleasePointerCapture(args.Pointer);
            ResetPan();
        }
    }

    private void ResetPan()
    {
        _panPointerId = null;
        _panMoved = false;
    }

    private bool IsNodeSource(object? source)
    {
        var current = source as DependencyObject;
        while (current is not null && current != _surface)
        {
            if (current is Button)
            {
                return true;
            }

            current = VisualTreeHelper.GetParent(current);
        }

        return false;
    }

    private Brush ThemeBrush(string key)
    {
        if (Resources.TryGetValue(key, out var local) && local is Brush localBrush)
        {
            return localBrush;
        }

        if (Application.Current.Resources.TryGetValue(key, out var value) && value is Brush brush)
        {
            return brush;
        }

        return ActualTheme == ElementTheme.Dark ? new SolidColorBrush(Colors.White) : new SolidColorBrush(Colors.Black);
    }

    private static bool HasSameGeometry(SceneGraphProjection left, SceneGraphProjection right) =>
        left.Width == right.Width && left.Height == right.Height && left.Nodes.Count == right.Nodes.Count &&
        left.Nodes.Zip(right.Nodes).All(pair => pair.First.Id == pair.Second.Id && pair.First.X == pair.Second.X &&
            pair.First.Y == pair.Second.Y && pair.First.Width == pair.Second.Width && pair.First.Height == pair.Second.Height);
}
