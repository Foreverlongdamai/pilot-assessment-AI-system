using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;

namespace PilotAssessment.Desktop.Controls.Graph;

public sealed partial class GraphNodeButton : UserControl
{
    public static readonly DependencyProperty NodeProperty = DependencyProperty.Register(
        nameof(Node),
        typeof(GraphNodeProjection),
        typeof(GraphNodeButton),
        new PropertyMetadata(null, OnNodePropertyChanged));

    public GraphNodeButton()
    {
        InitializeComponent();
    }

    public GraphNodeProjection? Node
    {
        get => (GraphNodeProjection?)GetValue(NodeProperty);
        set => SetValue(NodeProperty, value);
    }

    public event EventHandler<GraphNodeInvokedEventArgs>? NodeInvoked;

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
        AutomationProperties.SetName(NodeButton, node.AutomationName);
        AutomationProperties.SetHelpText(
            NodeButton,
            "Press Enter to select. Use multi-select mode to compare several nodes.");
        ToolTipService.SetToolTip(
            NodeButton,
            $"{node.Node.NodeId}\n{node.AutomationName}");

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
            _ => new SolidColorBrush(Colors.White),
        };
    }

    private void OnNodeClick(object sender, RoutedEventArgs args) => RaiseInvoked(false);

    private void OnSelectClick(object sender, RoutedEventArgs args) => RaiseInvoked(false);

    private void OnToggleSelectionClick(object sender, RoutedEventArgs args) => RaiseInvoked(true);

    private void RaiseInvoked(bool forceAdditive)
    {
        if (Node is not null)
        {
            NodeInvoked?.Invoke(this, new GraphNodeInvokedEventArgs(Node, forceAdditive));
        }
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
