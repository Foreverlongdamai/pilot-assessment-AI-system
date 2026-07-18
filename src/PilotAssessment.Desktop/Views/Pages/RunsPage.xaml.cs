using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

using PilotAssessment.Desktop.ViewModels;

namespace PilotAssessment.Desktop.Views.Pages;

public sealed partial class RunsPage : Page
{
    public RunsPage()
    {
        ViewModel = App.Services.GetRequiredService<RunsViewModel>();
        InitializeComponent();
    }

    public RunsViewModel ViewModel { get; }

    private async void OnPageLoaded(object sender, RoutedEventArgs args) =>
        await ViewModel.InitializeAsync();
}
