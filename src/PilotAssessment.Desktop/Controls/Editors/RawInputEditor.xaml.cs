using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

using PilotAssessment.Desktop.ViewModels;

namespace PilotAssessment.Desktop.Controls.Editors;

public sealed partial class RawInputEditor : UserControl
{
    private bool _ready;

    public RawInputEditor()
    {
        InitializeComponent();
        Loaded += OnLoaded;
    }

    public RawInputEditorViewModel? ViewModel { get; private set; }

    public event EventHandler<NodeEditorLocalEditEventArgs>? LocalEditChanged;

    public void SetViewModel(RawInputEditorViewModel viewModel)
    {
        _ready = false;
        ViewModel = viewModel;
        DataContext = viewModel;
        ArmDirtyTracking();
    }

    public void ResetDirtyBoundary()
    {
        _ready = false;
        ArmDirtyTracking();
    }

    private void OnLoaded(object sender, RoutedEventArgs args) => ArmDirtyTracking();

    private void OnFieldChanged(object sender, TextChangedEventArgs args) => NotifyLocalEdit(sender);

    private void OnSelectionChanged(object sender, SelectionChangedEventArgs args) => NotifyLocalEdit(sender);

    private void NotifyLocalEdit(object sender)
    {
        if (_ready && sender is Control { FocusState: not FocusState.Unfocused })
        {
            if (sender is TextBox textBox)
            {
                textBox.GetBindingExpression(TextBox.TextProperty)?.UpdateSource();
            }
            LocalEditChanged?.Invoke(
                this,
                new NodeEditorLocalEditEventArgs(NodeEditorEditPersistence.Autosave));
        }
    }

    private void ArmDirtyTracking() =>
        DispatcherQueue.TryEnqueue(DispatcherQueuePriority.Low, () => _ready = true);
}
