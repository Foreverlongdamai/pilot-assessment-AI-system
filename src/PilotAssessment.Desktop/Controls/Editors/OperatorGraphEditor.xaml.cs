using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

using PilotAssessment.Desktop.ViewModels;

namespace PilotAssessment.Desktop.Controls.Editors;

public sealed partial class OperatorGraphEditor : UserControl
{
    public OperatorGraphEditor()
    {
        InitializeComponent();
    }

    public EvidenceEditorViewModel? ViewModel { get; private set; }

    public event EventHandler? RecipeNodeSelected;

    public void SetViewModel(EvidenceEditorViewModel viewModel)
    {
        ViewModel = viewModel;
        DataContext = viewModel;
        NodeList.SelectedItem = viewModel.SelectedRecipeNode;
    }

    private void OnAddOperatorClick(object sender, RoutedEventArgs args) => Run(() =>
    {
        ViewModel?.AddSelectedOperator();
        NodeList.SelectedItem = ViewModel?.SelectedRecipeNode;
        RecipeNodeSelected?.Invoke(this, EventArgs.Empty);
    });

    private void OnRemoveOperatorClick(object sender, RoutedEventArgs args) => Run(() =>
    {
        ViewModel?.RemoveSelectedOperator();
        NodeList.SelectedItem = ViewModel?.SelectedRecipeNode;
        RecipeNodeSelected?.Invoke(this, EventArgs.Empty);
    });

    private void OnNodeSelectionChanged(object sender, SelectionChangedEventArgs args)
    {
        ViewModel?.SelectRecipeNodeForEditing(NodeList.SelectedItem as RecipeNodeDisplayItem);
        RecipeNodeSelected?.Invoke(this, EventArgs.Empty);
    }

    private void OnRemoveEdgeClick(object sender, RoutedEventArgs args) => Run(() =>
    {
        if (EdgeList.SelectedItem is RecipeEdgeDisplayItem edge)
        {
            ViewModel?.RemoveEdge(edge);
        }
    });

    private void OnAddEdgeClick(object sender, RoutedEventArgs args) => Run(() =>
        ViewModel?.AddEdge(
            SourceNodeText.Text,
            SourcePortText.Text,
            TargetNodeText.Text,
            TargetPortText.Text,
            TargetSlotText.Text));

    private void Run(Action operation)
    {
        try
        {
            operation();
            GraphErrorText.Text = string.Empty;
            GraphErrorText.Visibility = Visibility.Collapsed;
        }
        catch (Exception error)
        {
            GraphErrorText.Text = error.Message;
            GraphErrorText.Visibility = Visibility.Visible;
        }
    }
}
