using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

using PilotAssessment.Desktop.ViewModels;

namespace PilotAssessment.Desktop.Views.Pages;

public sealed partial class ResultsPage : Page
{
    public ResultsPage()
    {
        ViewModel = App.Services.GetRequiredService<ResultsViewModel>();
        InitializeComponent();
    }

    public ResultsViewModel ViewModel { get; }

    private async void OnPageLoaded(object sender, RoutedEventArgs args) =>
        await ViewModel.InitializeAsync();

    private async void OnOpenArtifactClick(object sender, RoutedEventArgs args)
    {
        if (sender is FrameworkElement { DataContext: ResultArtifactItemViewModel item })
        {
            await ViewModel.OpenArtifactCommand.ExecuteAsync(item);
        }
    }
}
