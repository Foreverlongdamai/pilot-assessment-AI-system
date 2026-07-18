using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

using PilotAssessment.Desktop.ViewModels;

namespace PilotAssessment.Desktop.Controls.Editors;

public sealed partial class EvidenceEditor : UserControl
{
    private bool _ready;

    public EvidenceEditor()
    {
        InitializeComponent();
        Loaded += OnLoaded;
        OperatorGraph.RecipeNodeSelected += OnRecipeNodeSelected;
        ParameterEditor.ParameterChanged += OnParameterChanged;
    }

    public EvidenceEditorViewModel? ViewModel { get; private set; }

    public event EventHandler<NodeEditorLocalEditEventArgs>? LocalEditChanged;

    public void SetViewModel(EvidenceEditorViewModel viewModel)
    {
        _ready = false;
        ViewModel = viewModel;
        DataContext = viewModel;
        viewModel.LocalEditChanged += OnViewModelLocalEditChanged;
        OperatorGraph.SetViewModel(viewModel);
        ParameterEditor.SetModel(viewModel.ParameterForm);
        EvidenceCptGrid.SetViewModel(viewModel.Cpt);
        ArmDirtyTracking();
    }

    public async Task InitializeAsync(CancellationToken cancellationToken = default)
    {
        if (ViewModel is null)
        {
            return;
        }
        await ViewModel.InitializeAsync(cancellationToken);
        OperatorGraph.SetViewModel(ViewModel);
        ParameterEditor.SetModel(ViewModel.ParameterForm);
        ArmDirtyTracking();
    }

    public void RefreshCanonical()
    {
        if (ViewModel is null)
        {
            return;
        }
        _ready = false;
        OperatorGraph.SetViewModel(ViewModel);
        ParameterEditor.SetModel(ViewModel.ParameterForm);
        ArmDirtyTracking();
    }

    private void OnLoaded(object sender, RoutedEventArgs args) => ArmDirtyTracking();

    private void OnRecipeNodeSelected(object? sender, EventArgs args) =>
        ParameterEditor.SetModel(ViewModel?.ParameterForm);

    private void OnParameterChanged(object? sender, EventArgs args)
    {
        ViewModel?.ApplyParameterForm();
        NotifyLocalEdit();
    }

    private void OnFieldChanged(object sender, TextChangedEventArgs args) =>
        NotifyLocalEdit(
            sender is FrameworkElement { DataContext: ObservationStateEditItem }
                ? NodeEditorEditPersistence.ExplicitCommit
                : NodeEditorEditPersistence.Autosave,
            sender);

    private void OnSelectionChanged(object sender, SelectionChangedEventArgs args) =>
        NotifyLocalEdit(sender: sender);

    private void OnAddStateClick(object sender, RoutedEventArgs args)
    {
        ViewModel?.AddObservationState();
    }

    private void OnRemoveStateClick(object sender, RoutedEventArgs args)
    {
        if (StateList.SelectedItem is ObservationStateEditItem state)
        {
            ViewModel?.RemoveObservationState(state);
        }
    }

    private async void OnCommitStatesClick(object sender, RoutedEventArgs args)
    {
        if (ViewModel is null)
        {
            return;
        }
        try
        {
            await ViewModel.CommitObservationStatesAsync();
        }
        catch (Exception error)
        {
            ViewModel.SetOperationError(error.Message);
        }
    }

    private async void OnPreviewClick(object sender, RoutedEventArgs args)
    {
        if (ViewModel is not null)
        {
            await ViewModel.PreviewAsync();
        }
    }

    private void OnCancelPreviewClick(object sender, RoutedEventArgs args) =>
        ViewModel?.CancelPreview();

    private void OnViewModelLocalEditChanged(
        object? sender,
        NodeEditorLocalEditEventArgs args) =>
        LocalEditChanged?.Invoke(this, args);

    private void NotifyLocalEdit(
        NodeEditorEditPersistence persistence = NodeEditorEditPersistence.Autosave,
        object? sender = null)
    {
        if (!_ready || sender is Control { FocusState: FocusState.Unfocused })
        {
            return;
        }
        if (sender is TextBox textBox)
        {
            textBox.GetBindingExpression(TextBox.TextProperty)?.UpdateSource();
        }
        ViewModel?.MarkLocalEdit(persistence);
    }

    private void ArmDirtyTracking() =>
        DispatcherQueue.TryEnqueue(DispatcherQueuePriority.Low, () => _ready = true);
}
