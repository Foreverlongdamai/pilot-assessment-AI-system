using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;

using PilotAssessment.Desktop.Core.State;

namespace PilotAssessment.Desktop.Controls.Graph;

public sealed partial class RawInputFamilyNode : UserControl
{
    public static readonly DependencyProperty NodeProperty = DependencyProperty.Register(
        nameof(Node),
        typeof(GraphRawInputFamilyProjection),
        typeof(RawInputFamilyNode),
        new PropertyMetadata(null, OnNodeChanged));

    public RawInputFamilyNode()
    {
        InitializeComponent();
    }

    public GraphRawInputFamilyProjection? Node
    {
        get => (GraphRawInputFamilyProjection?)GetValue(NodeProperty);
        set => SetValue(NodeProperty, value);
    }

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
}
