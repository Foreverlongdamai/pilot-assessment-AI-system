using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

using PilotAssessment.Desktop.ViewModels;

namespace PilotAssessment.Desktop.Controls.Editors;

public sealed partial class BnNodeEditor : UserControl
{
    private bool _ready;

    public BnNodeEditor()
    {
        InitializeComponent();
        Loaded += (_, _) => ArmDirtyTracking();
    }

    public BnNodeEditorViewModel? ViewModel { get; private set; }

    public event EventHandler<NodeEditorLocalEditEventArgs>? LocalEditChanged;

    public event EventHandler<CanonicalNodeCommittedEventArgs>? CanonicalNodeCommitted;

    public void SetViewModel(BnNodeEditorViewModel viewModel)
    {
        if (ViewModel is not null)
        {
            ViewModel.LocalEditChanged -= OnViewModelLocalEditChanged;
            ViewModel.CanonicalNodeCommitted -= OnCanonicalNodeCommitted;
        }
        _ready = false;
        ViewModel = viewModel;
        DataContext = viewModel;
        CptGrid.SetViewModel(viewModel.Cpt);
        viewModel.LocalEditChanged += OnViewModelLocalEditChanged;
        viewModel.CanonicalNodeCommitted += OnCanonicalNodeCommitted;
        ArmDirtyTracking();
    }

    public Task InitializeAsync(CancellationToken cancellationToken = default) =>
        ViewModel?.InitializeAsync(cancellationToken) ?? Task.CompletedTask;

    public void RefreshCanonical()
    {
        _ready = false;
        ArmDirtyTracking();
    }

    private void OnFieldChanged(object sender, TextChangedEventArgs args) =>
        NotifyLocalEdit(
            sender,
            sender is FrameworkElement { DataContext: BnStateEditItem }
                ? NodeEditorEditPersistence.ExplicitCommit
                : NodeEditorEditPersistence.Autosave);

    private void OnSelectionChanged(object sender, SelectionChangedEventArgs args) => NotifyLocalEdit(sender);

    private void OnAddStateClick(object sender, RoutedEventArgs args) => ViewModel?.AddState();

    private void OnRemoveStateClick(object sender, RoutedEventArgs args)
    {
        if (StateList.SelectedItem is BnStateEditItem state)
        {
            ViewModel?.RemoveState(state);
        }
    }

    private async void OnCommitStatesClick(object sender, RoutedEventArgs args) =>
        await RunAsync(() => ViewModel?.CommitStatesAsync() ?? Task.CompletedTask);

    private async void OnAddParentClick(object sender, RoutedEventArgs args) =>
        await RunAsync(() => ViewModel?.AddParentAsync() ?? Task.CompletedTask);

    private async void OnRemoveParentClick(object sender, RoutedEventArgs args) =>
        await RunAsync(() => ViewModel?.RemoveParentAsync() ?? Task.CompletedTask);

    private async void OnMoveParentUpClick(object sender, RoutedEventArgs args) =>
        await RunAsync(() => ViewModel?.MoveParentAsync(-1) ?? Task.CompletedTask);

    private async void OnMoveParentDownClick(object sender, RoutedEventArgs args) =>
        await RunAsync(() => ViewModel?.MoveParentAsync(1) ?? Task.CompletedTask);

    private void OnViewModelLocalEditChanged(object? sender, NodeEditorLocalEditEventArgs args) =>
        LocalEditChanged?.Invoke(this, args);

    private void OnCanonicalNodeCommitted(object? sender, CanonicalNodeCommittedEventArgs args) =>
        CanonicalNodeCommitted?.Invoke(this, args);

    private void NotifyLocalEdit(
        object sender,
        NodeEditorEditPersistence persistence = NodeEditorEditPersistence.Autosave)
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

    private async Task RunAsync(Func<Task> action)
    {
        try
        {
            ErrorBar.IsOpen = false;
            await action();
        }
        catch (Exception error)
        {
            ErrorBar.Message = error.Message;
            ErrorBar.IsOpen = true;
        }
    }

    private void ArmDirtyTracking() =>
        DispatcherQueue.TryEnqueue(DispatcherQueuePriority.Low, () => _ready = true);
}
