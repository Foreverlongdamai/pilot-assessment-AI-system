using Microsoft.UI.Xaml.Controls;

using PilotAssessment.Desktop.Core.Contracts;

namespace PilotAssessment.Desktop.Controls.Graph;

public sealed partial class DeactivationImpactDialog : ContentDialog
{
    public DeactivationImpactDialog(
        DeactivationImpact impact,
        IEnumerable<string> impactedNodeLabels)
    {
        ArgumentNullException.ThrowIfNull(impact);
        ArgumentNullException.ThrowIfNull(impactedNodeLabels);
        InitializeComponent();
        var labels = impactedNodeLabels.ToArray();
        ImpactedNodesList.ItemsSource = labels;
        SummaryText.Text = labels.Length == 0
            ? "The backend found no active nodes to change."
            : $"The backend found {labels.Length} node(s) in this task that will become inactive:";
    }
}
