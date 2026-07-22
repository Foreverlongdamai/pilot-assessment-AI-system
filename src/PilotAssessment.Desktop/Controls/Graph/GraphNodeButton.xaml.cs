using Microsoft.UI;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;

namespace PilotAssessment.Desktop.Controls.Graph;

public sealed partial class GraphNodeButton : UserControl
{
    private readonly TranslateTransform _dragTransform = new();
    private Windows.Foundation.Point _dragStart;
    private GraphNodeProjection? _dragNode;
    private uint? _dragPointerId;
    private bool _dragMoved;
    private bool _suppressClick;

    public static readonly DependencyProperty NodeProperty = DependencyProperty.Register(
        nameof(Node),
        typeof(GraphNodeProjection),
        typeof(GraphNodeButton),
        new PropertyMetadata(null, OnNodePropertyChanged));

    public GraphNodeButton()
    {
        InitializeComponent();
        NodeButton.RenderTransform = _dragTransform;
        NodeButton.AddHandler(PointerPressedEvent, new PointerEventHandler(OnPointerPressed), true);
        NodeButton.AddHandler(PointerMovedEvent, new PointerEventHandler(OnPointerMoved), true);
        NodeButton.AddHandler(PointerReleasedEvent, new PointerEventHandler(OnPointerReleased), true);
        NodeButton.AddHandler(PointerCanceledEvent, new PointerEventHandler(OnPointerCanceled), true);
    }

    public GraphNodeProjection? Node
    {
        get => (GraphNodeProjection?)GetValue(NodeProperty);
        set => SetValue(NodeProperty, value);
    }

    public event EventHandler<GraphNodeInvokedEventArgs>? NodeInvoked;

    public event EventHandler<GraphNodeCommandEventArgs>? NodeCommandRequested;

    public event EventHandler<GraphNodeDragCompletedEventArgs>? NodeDragCompleted;

    private static void OnNodePropertyChanged(
        DependencyObject dependencyObject,
        DependencyPropertyChangedEventArgs args)
    {
        if (dependencyObject is GraphNodeButton button)
        {
            button.ApplyNode(args.NewValue as GraphNodeProjection);
        }
    }

    private void ApplyNode(GraphNodeProjection? node)
    {
        if (node is null)
        {
            return;
        }

        NameText.Text = node.DisplayName;
        KindText.Text = node.KindLabel;
        StatusText.Text = node.StatusLabel;
        NodeButton.Opacity = node.VisualOpacity;
        SelectionRing.Visibility = node.IsSelected ? Visibility.Visible : Visibility.Collapsed;
        OutputBadge.Visibility = node.IsOutput ? Visibility.Visible : Visibility.Collapsed;
        ActivateItem.IsEnabled = !node.IsActive && !node.IsArchived;
        DeactivateItem.IsEnabled = node.IsActive;
        DeleteNodeItem.IsEnabled = !node.IsArchived;
        AutomationProperties.SetName(NodeButton, node.AutomationName);
        ToolTipService.SetToolTip(NodeButton, node.AutomationName);

        (NodeSurface.Fill, KindGlyph.Glyph) = node.NodeKind switch
        {
            ModelNodeKind.RawInput => (ResolveBrush("GraphRawInputNodeBrush", 37, 99, 235), "\uE950"),
            ModelNodeKind.Evidence => (ResolveBrush("GraphEvidenceNodeBrush", 13, 148, 136), "\uE9D2"),
            _ => (ResolveBrush("GraphBnNodeBrush", 124, 58, 237), "\uE943"),
        };
        NodeSurface.Stroke = node.Node.TechnicalStatus switch
        {
            ModelTechnicalStatus.Blocked => ResolveBrush("GraphBlockedStatusBrush", 220, 38, 38),
            ModelTechnicalStatus.Incomplete => ResolveBrush("GraphIncompleteStatusBrush", 245, 158, 11),
            _ => ResolveBrush("GraphNodeForegroundBrush", 255, 255, 255),
        };
    }

    private void OnNodeClick(object sender, RoutedEventArgs args)
    {
        if (_suppressClick)
        {
            _suppressClick = false;
            return;
        }

        RaiseInvoked(false);
    }

    private void OnNodeDoubleTapped(object sender, DoubleTappedRoutedEventArgs args)
    {
        args.Handled = true;
        RaiseCommand(GraphNodeCommand.OpenDetails);
    }

    private void OnSelectClick(object sender, RoutedEventArgs args) => RaiseInvoked(false);

    private void OnToggleSelectionClick(object sender, RoutedEventArgs args) => RaiseInvoked(true);

    private void OnOpenDetailsClick(object sender, RoutedEventArgs args) =>
        RaiseCommand(GraphNodeCommand.OpenDetails);

    private void OnActivateClick(object sender, RoutedEventArgs args) =>
        RaiseCommand(GraphNodeCommand.Activate);

    private void OnDeactivateClick(object sender, RoutedEventArgs args) =>
        RaiseCommand(GraphNodeCommand.Deactivate);

    private void OnCopyClick(object sender, RoutedEventArgs args) =>
        RaiseCommand(GraphNodeCommand.Copy);

    private void OnPasteClick(object sender, RoutedEventArgs args) =>
        RaiseCommand(GraphNodeCommand.Paste);

    private void OnConnectParentClick(object sender, RoutedEventArgs args) =>
        RaiseCommand(GraphNodeCommand.ConnectSelectedParent);

    private void OnRemoveParentClick(object sender, RoutedEventArgs args) =>
        RaiseCommand(GraphNodeCommand.RemoveSelectedParent);

    private void OnDeleteNodeClick(object sender, RoutedEventArgs args) =>
        RaiseCommand(GraphNodeCommand.DeleteGlobal);

    private void OnPointerPressed(object sender, PointerRoutedEventArgs args)
    {
        var point = args.GetCurrentPoint(XamlRoot?.Content as UIElement ?? this);
        if (!point.Properties.IsLeftButtonPressed)
        {
            return;
        }

        _dragPointerId = args.Pointer.PointerId;
        _dragNode = Node;
        _dragStart = GetStablePointerPosition(args);
        _dragMoved = false;
        NodeButton.CapturePointer(args.Pointer);
    }

    private void OnPointerMoved(object sender, PointerRoutedEventArgs args)
    {
        if (_dragPointerId != args.Pointer.PointerId)
        {
            return;
        }

        var current = GetStablePointerPosition(args);
        var x = current.X - _dragStart.X;
        var y = current.Y - _dragStart.Y;
        var distance = Math.Sqrt((x * x) + (y * y));
        if (!_dragMoved && distance < 4)
        {
            return;
        }

        _dragMoved = true;
        _dragTransform.X = x;
        _dragTransform.Y = y;
        args.Handled = true;
    }

    private void OnPointerReleased(object sender, PointerRoutedEventArgs args)
        => CompleteDrag(args, releasePointer: true);

    private void OnPointerCanceled(object sender, PointerRoutedEventArgs args)
        => CompleteDrag(args, releasePointer: false);

    private void CompleteDrag(PointerRoutedEventArgs args, bool releasePointer)
    {
        if (_dragPointerId != args.Pointer.PointerId)
        {
            return;
        }

        var moved = _dragMoved;
        var node = _dragNode;
        var deltaX = _dragTransform.X;
        var deltaY = _dragTransform.Y;
        _dragPointerId = null;
        _dragNode = null;
        _dragMoved = false;
        if (releasePointer)
        {
            NodeButton.ReleasePointerCapture(args.Pointer);
        }

        if (moved && node is not null)
        {
            _suppressClick = true;
            NodeDragCompleted?.Invoke(
                this,
                new GraphNodeDragCompletedEventArgs(node, deltaX, deltaY));
            args.Handled = true;
            _ = DispatcherQueue.TryEnqueue(
                DispatcherQueuePriority.Low,
                () => _suppressClick = false);
        }

        ResetDrag();
    }

    private Windows.Foundation.Point GetStablePointerPosition(PointerRoutedEventArgs args) =>
        args.GetCurrentPoint(XamlRoot?.Content as UIElement ?? this).Position;

    private void RaiseInvoked(bool forceAdditive)
    {
        if (Node is not null)
        {
            NodeInvoked?.Invoke(this, new GraphNodeInvokedEventArgs(Node, forceAdditive));
        }
    }

    private void RaiseCommand(GraphNodeCommand command)
    {
        if (Node is not null)
        {
            NodeCommandRequested?.Invoke(this, new GraphNodeCommandEventArgs(Node, command));
        }
    }

    private void ResetDrag()
    {
        _dragPointerId = null;
        _dragNode = null;
        _dragMoved = false;
        _dragTransform.X = 0;
        _dragTransform.Y = 0;
    }

    private SolidColorBrush ResolveBrush(string key, byte red, byte green, byte blue)
    {
        if (Resources.TryGetValue(key, out var local) && local is SolidColorBrush localBrush)
        {
            return localBrush;
        }

        if (Application.Current.Resources.TryGetValue(key, out var app) &&
            app is SolidColorBrush appBrush)
        {
            return appBrush;
        }

        return new SolidColorBrush(ColorHelper.FromArgb(255, red, green, blue));
    }
}

public sealed class GraphNodeInvokedEventArgs(
    GraphNodeProjection node,
    bool forceAdditive) : EventArgs
{
    public GraphNodeProjection Node { get; } = node;
    public bool ForceAdditive { get; } = forceAdditive;
}

public enum GraphNodeCommand
{
    OpenDetails,
    Activate,
    Deactivate,
    Copy,
    Paste,
    ConnectSelectedParent,
    RemoveSelectedParent,
    DeleteGlobal,
}

public sealed class GraphNodeCommandEventArgs(
    GraphNodeProjection node,
    GraphNodeCommand command) : EventArgs
{
    public GraphNodeProjection Node { get; } = node;
    public GraphNodeCommand Command { get; } = command;
}

public sealed class GraphNodeDragCompletedEventArgs(
    GraphNodeProjection node,
    double deltaX,
    double deltaY) : EventArgs
{
    public GraphNodeProjection Node { get; } = node;
    public double DeltaX { get; } = deltaX;
    public double DeltaY { get; } = deltaY;
}
