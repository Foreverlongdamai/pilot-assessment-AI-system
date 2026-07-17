using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;

using PilotAssessment.Desktop.Controls.Graph;
using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;
using PilotAssessment.Desktop.ViewModels;

namespace PilotAssessment.Desktop.Views.Pages;

public sealed partial class ModelStudioPage : Page
{
    public ModelStudioPage()
    {
        ViewModel = App.Services.GetRequiredService<ModelStudioViewModel>();
        InitializeComponent();
    }

    public ModelStudioViewModel ViewModel { get; }

    private async void OnPageLoaded(object sender, RoutedEventArgs args) =>
        await ViewModel.ActivateAsync();

    private void OnSearchTextChanged(object sender, TextChangedEventArgs args)
    {
        if (sender is TextBox textBox)
        {
            ViewModel.SearchText = textBox.Text;
        }
    }

    private void OnClearSelectionClick(object sender, RoutedEventArgs args) =>
        ViewModel.ClearSelection();

    private async void OnCreateRawInputClick(object sender, RoutedEventArgs args) =>
        await ShowNodeCreationAsync(ModelNodeKind.RawInput);

    private async void OnCreateEvidenceClick(object sender, RoutedEventArgs args) =>
        await ShowNodeCreationAsync(ModelNodeKind.Evidence);

    private async void OnCreateBnClick(object sender, RoutedEventArgs args) =>
        await ShowNodeCreationAsync(ModelNodeKind.Bn);

    private async void OnActivateSelectionClick(object sender, RoutedEventArgs args)
    {
        if (await RequireSelectedNodeAsync() is { } node)
        {
            await ViewModel.ActivateNodeAsync(node);
        }
    }

    private async void OnDeactivateSelectionClick(object sender, RoutedEventArgs args)
    {
        if (await RequireSelectedNodeAsync() is { } node)
        {
            await DeactivateWithConfirmationAsync(node);
        }
    }

    private async void OnCopySelectionClick(object sender, RoutedEventArgs args)
    {
        try
        {
            ViewModel.CopySelection();
        }
        catch (Exception error)
        {
            await ShowCommandErrorAsync(error);
        }
    }

    private async void OnPasteClick(object sender, RoutedEventArgs args) =>
        await ViewModel.PasteAsync();

    private async void OnCopyAccelerator(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        if (IsTextEditingFocused())
        {
            args.Handled = false;
            return;
        }

        args.Handled = true;
        try
        {
            ViewModel.CopySelection();
        }
        catch (Exception error)
        {
            await ShowCommandErrorAsync(error);
        }
    }

    private async void OnPasteAccelerator(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        if (IsTextEditingFocused())
        {
            args.Handled = false;
            return;
        }

        args.Handled = true;
        await ViewModel.PasteAsync();
    }

    private async void OnDeleteAccelerator(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        if (IsTextEditingFocused())
        {
            args.Handled = false;
            return;
        }

        args.Handled = true;
        if (await RequireSelectedNodeAsync() is { } node)
        {
            await DeactivateWithConfirmationAsync(node);
        }
    }

    private async void OnGraphNodeCommandRequested(object? sender, GraphNodeCommandEventArgs args)
    {
        try
        {
            switch (args.Command)
            {
                case GraphNodeCommand.OpenDetails:
                    ViewModel.RequestOpenNode(args.Node);
                    break;
                case GraphNodeCommand.Activate:
                    await ViewModel.ActivateNodeAsync(args.Node);
                    break;
                case GraphNodeCommand.Deactivate:
                    await DeactivateWithConfirmationAsync(args.Node);
                    break;
                case GraphNodeCommand.Copy:
                    ViewModel.CopyNode(args.Node);
                    break;
                case GraphNodeCommand.Paste:
                    await ViewModel.PasteAsync();
                    break;
                case GraphNodeCommand.ConnectSelectedParent:
                    if (await AskEdgeMigrationChoiceAsync(
                            removing: false,
                            ViewModel.SelectedParentEdgeKindFor(args.Node)) is { } addIncomplete)
                    {
                        await ViewModel.ConnectSelectedParentAsync(args.Node, addIncomplete);
                    }

                    break;
                case GraphNodeCommand.RemoveSelectedParent:
                    if (await AskEdgeMigrationChoiceAsync(
                            removing: true,
                            ViewModel.SelectedParentEdgeKindFor(args.Node)) is { } removeIncomplete)
                    {
                        await ViewModel.RemoveSelectedParentAsync(args.Node, removeIncomplete);
                    }

                    break;
            }
        }
        catch (Exception error)
        {
            await ShowCommandErrorAsync(error);
        }
    }

    private async Task ShowNodeCreationAsync(ModelNodeKind kind)
    {
        var dialog = new NodeCreationDialog(kind) { XamlRoot = XamlRoot };
        if (await dialog.ShowAsync() is not ContentDialogResult.Primary)
        {
            return;
        }

        var x = Math.Max(180, ViewModel.ExtentWidth / 2);
        var y = Math.Max(180, ViewModel.ExtentHeight / 2);
        await ViewModel.CreateNodeAsync(dialog.CreateRequest(x, y));
    }

    private async Task DeactivateWithConfirmationAsync(GraphNodeProjection node)
    {
        var impact = await ViewModel.PreviewDeactivationAsync(node);
        if (impact is null)
        {
            return;
        }

        if (!impact.ImpactedNodeIds.Any(nodeId => nodeId != node.NodeId))
        {
            await ViewModel.CompleteDeactivationAsync(
                node,
                impact,
                continueRequested: true);
            return;
        }

        var dialog = new DeactivationImpactDialog(
            impact,
            ViewModel.DescribeNodeIds(impact.ImpactedNodeIds))
        {
            XamlRoot = XamlRoot,
        };
        var result = await dialog.ShowAsync();
        await ViewModel.CompleteDeactivationAsync(
            node,
            impact,
            result is ContentDialogResult.Primary);
    }

    private async Task<bool?> AskEdgeMigrationChoiceAsync(
        bool removing,
        ModelGraphEdgeKind edgeKind)
    {
        var extraction = edgeKind is ModelGraphEdgeKind.Extraction;
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = extraction
                ? removing
                    ? "Remove Raw Input recipe binding?"
                    : "Add Raw Input recipe binding?"
                : removing
                    ? "Remove probabilistic parent?"
                    : "Add probabilistic parent?",
            Content = extraction
                ? removing
                    ? "The backend will remove this exact extraction edge and its EvidenceRecipe input binding in one operation."
                    : "The backend will add this exact Raw Input binding to the EvidenceRecipe in one operation. The recipe may remain incomplete while you continue editing it."
                : removing
                    ? "Choose how the child CPT is migrated when this fixed probabilistic parent is removed."
                    : "Choose how the child CPT is expanded when this fixed probabilistic parent is added.",
            PrimaryButtonText = extraction
                ? removing ? "Remove binding" : "Add binding"
                : removing ? "Marginalize / migrate" : "Preserve / migrate",
            SecondaryButtonText = extraction ? string.Empty : "Mark CPT incomplete",
            CloseButtonText = "Cancel",
            DefaultButton = ContentDialogButton.Close,
        };
        return await dialog.ShowAsync() switch
        {
            ContentDialogResult.Primary => false,
            ContentDialogResult.Secondary => true,
            _ => null,
        };
    }

    private async Task<GraphNodeProjection?> RequireSelectedNodeAsync()
    {
        if (ViewModel.PrimarySelectedNode is { } node)
        {
            return node;
        }

        await ShowCommandErrorAsync(new InvalidOperationException("Select one model node first."));
        return null;
    }

    private async Task ShowCommandErrorAsync(Exception error)
    {
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = "Model command not applied",
            Content = error.Message,
            CloseButtonText = "Close",
        };
        await dialog.ShowAsync();
    }

    private bool IsTextEditingFocused()
    {
        var focused = FocusManager.GetFocusedElement(XamlRoot) as DependencyObject;
        while (focused is not null)
        {
            if (focused is TextBox or RichEditBox or PasswordBox or NumberBox or AutoSuggestBox ||
                focused is ComboBox { IsEditable: true })
            {
                return true;
            }

            focused = VisualTreeHelper.GetParent(focused);
        }

        return false;
    }
}
