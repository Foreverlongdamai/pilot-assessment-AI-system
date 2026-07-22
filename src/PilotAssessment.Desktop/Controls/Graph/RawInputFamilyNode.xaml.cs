using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;

using PilotAssessment.Desktop.Core.State;

namespace PilotAssessment.Desktop.Controls.Graph;

public sealed partial class RawInputFamilyNode : UserControl
{
    private readonly TranslateTransform _dragTransform = new();
    private Windows.Foundation.Point _dragStart;
    private GraphRawInputFamilyProjection? _dragNode;
    private uint? _dragPointerId;
    private bool _dragMoved;

    public static readonly DependencyProperty NodeProperty = DependencyProperty.Register(
        nameof(Node),
        typeof(GraphRawInputFamilyProjection),
        typeof(RawInputFamilyNode),
        new PropertyMetadata(null, OnNodeChanged));

    public RawInputFamilyNode()
    {
        InitializeComponent();
        RenderTransform = _dragTransform;
        AddHandler(PointerPressedEvent, new PointerEventHandler(OnPointerPressed), true);
        AddHandler(PointerMovedEvent, new PointerEventHandler(OnPointerMoved), true);
        AddHandler(PointerReleasedEvent, new PointerEventHandler(OnPointerReleased), true);
        AddHandler(PointerCanceledEvent, new PointerEventHandler(OnPointerCanceled), true);
    }

    public GraphRawInputFamilyProjection? Node
    {
        get => (GraphRawInputFamilyProjection?)GetValue(NodeProperty);
        set => SetValue(NodeProperty, value);
    }

    public event EventHandler<RawInputFamilyDragCompletedEventArgs>? RawInputFamilyDragCompleted;

    private static void OnNodeChanged(
        DependencyObject dependencyObject,
        DependencyPropertyChangedEventArgs args)
    {
        if (dependencyObject is RawInputFamilyNode control)
        {
            control.ApplyNode(args.NewValue as GraphRawInputFamilyProjection);
        }
    }

    private void ApplyNode(GraphRawInputFamilyProjection? node)
    {
        if (node is null)
        {
            return;
        }

        SymbolText.Text = $"{node.Symbol}(t)";
        NameText.Text = node.DisplayName;
        KindText.Text = node.KindLabel;
        AutomationProperties.SetName(this, node.AutomationName);
        AutomationProperties.SetHelpText(this, node.Description);
        ToolTipService.SetToolTip(this, $"{node.Description}\n{node.AutomationName}");
    }

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
        CapturePointer(args.Pointer);
        args.Handled = true;
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
        if (!_dragMoved && Math.Sqrt((x * x) + (y * y)) < 4)
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
            ReleasePointerCapture(args.Pointer);
        }

        if (moved && node is not null)
        {
            RawInputFamilyDragCompleted?.Invoke(
                this,
                new RawInputFamilyDragCompletedEventArgs(node, deltaX, deltaY));
            args.Handled = true;
        }

        ResetDrag();
    }

    private Windows.Foundation.Point GetStablePointerPosition(PointerRoutedEventArgs args) =>
        args.GetCurrentPoint(XamlRoot?.Content as UIElement ?? this).Position;

    private void ResetDrag()
    {
        _dragPointerId = null;
        _dragNode = null;
        _dragMoved = false;
        _dragTransform.X = 0;
        _dragTransform.Y = 0;
    }
}

public sealed class RawInputFamilyDragCompletedEventArgs(
    GraphRawInputFamilyProjection node,
    double deltaX,
    double deltaY) : EventArgs
{
    public GraphRawInputFamilyProjection Node { get; } = node;
    public double DeltaX { get; } = deltaX;
    public double DeltaY { get; } = deltaY;
}
