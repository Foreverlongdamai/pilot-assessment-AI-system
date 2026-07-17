using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

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
}
