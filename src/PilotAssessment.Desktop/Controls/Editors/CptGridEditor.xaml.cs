using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

using PilotAssessment.Desktop.ViewModels;

namespace PilotAssessment.Desktop.Controls.Editors;

public sealed partial class CptGridEditor : UserControl
{
    private bool _ready;
    private bool _expanded;

    public CptGridEditor()
    {
        InitializeComponent();
        Loaded += (_, _) => ArmDirtyTracking();
    }

    public CptGridViewModel? ViewModel { get; private set; }

    public event EventHandler? LocalEditChanged;

    public event EventHandler<CanonicalNodeCommittedEventArgs>? CanonicalNodeCommitted;

    public void SetViewModel(CptGridViewModel viewModel)
    {
        if (ViewModel is not null)
        {
            ViewModel.LocalEditChanged -= OnViewModelLocalEditChanged;
            ViewModel.CanonicalNodeCommitted -= OnCanonicalNodeCommitted;
        }
        _ready = false;
        ViewModel = viewModel;
        DataContext = viewModel;
        viewModel.LocalEditChanged += OnViewModelLocalEditChanged;
        viewModel.CanonicalNodeCommitted += OnCanonicalNodeCommitted;
        ArmDirtyTracking();
    }

    private void OnCellTextChanged(object sender, TextChangedEventArgs args)
    {
        if (_ready && sender is Control { FocusState: not FocusState.Unfocused })
        {
            ViewModel?.MarkLocalEdit();
        }
    }

    private void OnNormalizeRowClick(object sender, RoutedEventArgs args) =>
        RunLocal(() => ViewModel?.NormalizeRow((CptRowEditItem)((FrameworkElement)sender).DataContext));

    private void OnApplyPasteClick(object sender, RoutedEventArgs args) => RunLocal(() =>
    {
        if (ViewModel is null)
        {
            return;
        }
        ViewModel.PasteStartRow = int.Parse(PasteStartRowBox.Text, System.Globalization.CultureInfo.InvariantCulture);
        ViewModel.PasteStartColumn = int.Parse(PasteStartColumnBox.Text, System.Globalization.CultureInfo.InvariantCulture);
        ViewModel.ApplyPaste(PasteTextBox.Text);
    });

    private async void OnSaveRowsClick(object sender, RoutedEventArgs args) =>
        await RunAsync(() => ViewModel?.SaveRowsAsync() ?? Task.CompletedTask);

    private async void OnMaterializeClick(object sender, RoutedEventArgs args) =>
        await RunAsync(() => ViewModel?.MaterializeAsync() ?? Task.CompletedTask);

    private void OnToggleExpandedClick(object sender, RoutedEventArgs args)
    {
        _expanded = !_expanded;
        CptRowsList.MaxHeight = _expanded ? double.PositiveInfinity : 520;
        if (sender is Button button)
        {
            button.Content = _expanded ? "Collapse grid" : "Expand grid";
        }
    }

    private void OnViewModelLocalEditChanged(object? sender, EventArgs args) =>
        LocalEditChanged?.Invoke(this, EventArgs.Empty);

    private void OnCanonicalNodeCommitted(object? sender, CanonicalNodeCommittedEventArgs args) =>
        CanonicalNodeCommitted?.Invoke(this, args);

    private void RunLocal(Action action)
    {
        try
        {
            ErrorBar.IsOpen = false;
            action();
        }
        catch (Exception error)
        {
            ErrorBar.Message = error.Message;
            ErrorBar.IsOpen = true;
        }
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
