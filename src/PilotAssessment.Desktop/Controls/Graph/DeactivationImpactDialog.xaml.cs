using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml.Controls;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;

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
        var localization = App.Services.GetRequiredService<ILocalizationLookup>();
        SummaryText.Text = labels.Length == 0
            ? localization["Dialog_DeactivateNoImpact"]
            : localization.Format("Dialog_DeactivateImpactCount", labels.Length);
    }
}
