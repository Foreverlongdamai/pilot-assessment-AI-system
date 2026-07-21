using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;

namespace PilotAssessment.Desktop.Controls.Graph;

public sealed partial class NodeCreationDialog : ContentDialog
{
    public NodeCreationDialog(ModelNodeKind initialKind)
    {
        InitializeComponent();
        KindCombo.SelectedIndex = initialKind switch
        {
            ModelNodeKind.RawInput => 0,
            ModelNodeKind.Evidence => 1,
            _ => 2,
        };
        RawModalityCombo.SelectedIndex = 0;
        UpdateRawModalityVisibility();
    }

    public ModelNodeDraftRequest CreateRequest(double x, double y) => new(
        SelectedKind(),
        NameBox.Text,
        SelectedRawModality(),
        x,
        y);

    private void OnKindChanged(object sender, SelectionChangedEventArgs args) =>
        UpdateRawModalityVisibility();

    private void OnPrimaryButtonClick(ContentDialog sender, ContentDialogButtonClickEventArgs args)
    {
        if (string.IsNullOrWhiteSpace(NameBox.Text))
        {
            ValidationInfo.Message = App.Services
                .GetRequiredService<ILocalizationLookup>()["Dialog_NodeNameRequired"];
            ValidationInfo.IsOpen = true;
            args.Cancel = true;
        }
    }

    private void UpdateRawModalityVisibility()
    {
        if (RawModalityCombo is not null)
        {
            RawModalityCombo.Visibility = SelectedKind() is ModelNodeKind.RawInput
                ? Visibility.Visible
                : Visibility.Collapsed;
        }
    }

    private ModelNodeKind SelectedKind() =>
        (KindCombo.SelectedItem as ComboBoxItem)?.Tag?.ToString() switch
        {
            "raw_input" => ModelNodeKind.RawInput,
            "bn" => ModelNodeKind.Bn,
            _ => ModelNodeKind.Evidence,
        };

    private RawModality SelectedRawModality() =>
        (RawModalityCombo.SelectedItem as ComboBoxItem)?.Tag?.ToString() switch
        {
            "U" => RawModality.U,
            "I" => RawModality.I,
            "G" => RawModality.G,
            "EEG" => RawModality.Eeg,
            "ECG" => RawModality.Ecg,
            "pilot_camera" => RawModality.PilotCamera,
            _ => RawModality.X,
        };
}
