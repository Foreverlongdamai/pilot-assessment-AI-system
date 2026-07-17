using System.ComponentModel;

using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;
using PilotAssessment.Desktop.ViewModels;

using Windows.Foundation;

namespace PilotAssessment.Desktop.Controls.Graph;

public sealed partial class ModelGraphControl : UserControl
{
    private const double MinimapWidth = 180;
    private const double MinimapHeight = 110;
    private Rectangle? _viewportIndicator;

    public ModelGraphControl()
    {
        ViewModel = App.Services.GetRequiredService<ModelStudioViewModel>();
        NodeLayout = new GraphVirtualizingLayout();
        InitializeComponent();
    }

    public ModelStudioViewModel ViewModel { get; }

    public GraphVirtualizingLayout NodeLayout { get; }

    private void OnLoaded(object sender, RoutedEventArgs args)
    {
        ViewModel.PropertyChanged += OnViewModelPropertyChanged;
        ActualThemeChanged += OnActualThemeChanged;
        RenderGraphLayers();
    }

    private void OnUnloaded(object sender, RoutedEventArgs args)
    {
        ViewModel.PropertyChanged -= OnViewModelPropertyChanged;
        ActualThemeChanged -= OnActualThemeChanged;
    }

    private void OnViewModelPropertyChanged(object? sender, PropertyChangedEventArgs args)
    {
        if (args.PropertyName is nameof(ModelStudioViewModel.ProjectionVersion))
        {
            RenderGraphLayers();
        }
    }

    private void OnActualThemeChanged(FrameworkElement sender, object args) => RenderGraphLayers();

    private void OnNodeInvoked(object sender, GraphNodeInvokedEventArgs args) =>
        ViewModel.SelectNode(args.Node, args.ForceAdditive);

    private void OnZoomOutClick(object sender, RoutedEventArgs args) =>
        SetZoom(GraphScrollViewer.ZoomFactor - 0.15f);

    private void OnZoomInClick(object sender, RoutedEventArgs args) =>
        SetZoom(GraphScrollViewer.ZoomFactor + 0.15f);

    private void OnFitClick(object sender, RoutedEventArgs args)
    {
        if (GraphScrollViewer.ActualWidth <= 0 || GraphScrollViewer.ActualHeight <= 0)
        {
            return;
        }

        var horizontal = GraphScrollViewer.ActualWidth / ViewModel.ExtentWidth;
        var vertical = GraphScrollViewer.ActualHeight / ViewModel.ExtentHeight;
        var target = (float)Math.Clamp(Math.Min(horizontal, vertical) * 0.92, 0.25, 2.5);
        _ = GraphScrollViewer.ChangeView(0, 0, target, true);
    }

    private void OnViewChanged(object sender, ScrollViewerViewChangedEventArgs args)
    {
        ZoomText.Text = $"{GraphScrollViewer.ZoomFactor:P0}";
        UpdateViewportIndicator();
    }

    private void SetZoom(float requested)
    {
        var target = Math.Clamp(requested, 0.25f, 2.5f);
        _ = GraphScrollViewer.ChangeView(null, null, target, false);
    }

    private void RenderGraphLayers()
    {
        EdgeLayer.Children.Clear();
        foreach (var edge in ViewModel.Edges)
        {
            RenderEdge(edge);
        }

        RenderMinimap();
    }

    private void RenderEdge(GraphEdgeProjection edge)
    {
        var start = new Point(edge.Parent.X, edge.Parent.Y);
        var end = new Point(edge.Child.X, edge.Child.Y);
        var deltaX = end.X - start.X;
        var deltaY = end.Y - start.Y;
        var length = Math.Sqrt((deltaX * deltaX) + (deltaY * deltaY));
        if (length < 1)
        {
            return;
        }

        var unitX = deltaX / length;
        var unitY = deltaY / length;
        var radius = GraphProjection.NodeDiameter / 2;
        var lineStart = new Point(start.X + (unitX * radius), start.Y + (unitY * radius));
        var lineEnd = new Point(end.X - (unitX * (radius + 5)), end.Y - (unitY * (radius + 5)));
        var brush = EdgeBrush(edge.EdgeKind, edge.IsActive);
        var line = new Line
        {
            X1 = lineStart.X,
            Y1 = lineStart.Y,
            X2 = lineEnd.X,
            Y2 = lineEnd.Y,
            Stroke = brush,
            StrokeThickness = edge.IsActive ? 2.2 : 1.2,
            Opacity = edge.IsActive ? 0.92 : 0.34,
        };
        if (edge.EdgeKind is ModelGraphEdgeKind.Extraction)
        {
            line.StrokeDashArray = [6, 4];
        }

        EdgeLayer.Children.Add(line);

        var arrowLength = 10.0;
        var arrowWidth = 5.0;
        var baseX = lineEnd.X - (unitX * arrowLength);
        var baseY = lineEnd.Y - (unitY * arrowLength);
        var perpendicularX = -unitY;
        var perpendicularY = unitX;
        var arrow = new Polygon
        {
            Fill = brush,
            Opacity = edge.IsActive ? 0.92 : 0.34,
            Points =
            [
                lineEnd,
                new Point(baseX + (perpendicularX * arrowWidth), baseY + (perpendicularY * arrowWidth)),
                new Point(baseX - (perpendicularX * arrowWidth), baseY - (perpendicularY * arrowWidth)),
            ],
        };
        EdgeLayer.Children.Add(arrow);
    }

    private void RenderMinimap()
    {
        MinimapCanvas.Children.Clear();
        var scale = Math.Min(
            MinimapWidth / Math.Max(ViewModel.ExtentWidth, 1),
            MinimapHeight / Math.Max(ViewModel.ExtentHeight, 1));
        foreach (var edge in ViewModel.Edges)
        {
            var line = new Line
            {
                X1 = edge.Parent.X * scale,
                Y1 = edge.Parent.Y * scale,
                X2 = edge.Child.X * scale,
                Y2 = edge.Child.Y * scale,
                Stroke = EdgeBrush(edge.EdgeKind, edge.IsActive),
                StrokeThickness = edge.IsActive ? 1 : 0.5,
                Opacity = edge.IsActive ? 0.75 : 0.24,
            };
            MinimapCanvas.Children.Add(line);
        }

        foreach (var node in ViewModel.Nodes)
        {
            var dot = new Ellipse
            {
                Width = node.IsActive ? 5 : 3.5,
                Height = node.IsActive ? 5 : 3.5,
                Fill = NodeBrush(node.NodeKind),
                Opacity = node.VisualOpacity,
            };
            Canvas.SetLeft(dot, (node.X * scale) - (dot.Width / 2));
            Canvas.SetTop(dot, (node.Y * scale) - (dot.Height / 2));
            MinimapCanvas.Children.Add(dot);
        }

        _viewportIndicator = new Rectangle
        {
            Stroke = ResolveBrush("AccentTextFillColorPrimaryBrush", Colors.DeepSkyBlue),
            StrokeThickness = 1.5,
            Fill = new SolidColorBrush(ColorHelper.FromArgb(24, 0, 120, 212)),
            IsHitTestVisible = false,
        };
        MinimapCanvas.Children.Add(_viewportIndicator);
        UpdateViewportIndicator();
    }

    private void UpdateViewportIndicator()
    {
        if (_viewportIndicator is null)
        {
            return;
        }

        var scale = Math.Min(
            MinimapWidth / Math.Max(ViewModel.ExtentWidth, 1),
            MinimapHeight / Math.Max(ViewModel.ExtentHeight, 1));
        var zoom = Math.Max(GraphScrollViewer.ZoomFactor, 0.01f);
        var left = (GraphScrollViewer.HorizontalOffset / zoom) * scale;
        var top = (GraphScrollViewer.VerticalOffset / zoom) * scale;
        _viewportIndicator.Width = Math.Min(
            MinimapWidth,
            (GraphScrollViewer.ViewportWidth / zoom) * scale);
        _viewportIndicator.Height = Math.Min(
            MinimapHeight,
            (GraphScrollViewer.ViewportHeight / zoom) * scale);
        Canvas.SetLeft(_viewportIndicator, Math.Clamp(left, 0, MinimapWidth));
        Canvas.SetTop(_viewportIndicator, Math.Clamp(top, 0, MinimapHeight));
    }

    private Brush EdgeBrush(ModelGraphEdgeKind kind, bool active)
    {
        if (!active)
        {
            return ResolveBrush("GraphInactiveEdgeBrush", ColorHelper.FromArgb(255, 107, 114, 128));
        }

        return kind is ModelGraphEdgeKind.Extraction
            ? ResolveBrush("GraphExtractionEdgeBrush", ColorHelper.FromArgb(255, 13, 148, 136))
            : ResolveBrush("GraphProbabilisticEdgeBrush", ColorHelper.FromArgb(255, 124, 58, 237));
    }

    private Brush NodeBrush(ModelNodeKind kind) => kind switch
    {
        ModelNodeKind.RawInput => ResolveBrush("GraphRawInputNodeBrush", ColorHelper.FromArgb(255, 37, 99, 235)),
        ModelNodeKind.Evidence => ResolveBrush("GraphEvidenceNodeBrush", ColorHelper.FromArgb(255, 13, 148, 136)),
        _ => ResolveBrush("GraphBnNodeBrush", ColorHelper.FromArgb(255, 124, 58, 237)),
    };

    private Brush ResolveBrush(string key, Windows.UI.Color fallback)
    {
        if (Resources.TryGetValue(key, out var local) && local is Brush localBrush)
        {
            return localBrush;
        }

        if (Application.Current.Resources.TryGetValue(key, out var app) && app is Brush appBrush)
        {
            return appBrush;
        }

        return new SolidColorBrush(fallback);
    }
}
