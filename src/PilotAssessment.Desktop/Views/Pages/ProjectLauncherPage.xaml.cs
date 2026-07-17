using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

using PilotAssessment.Desktop.Core.ViewModels;

namespace PilotAssessment.Desktop.Views.Pages;

public sealed partial class ProjectLauncherPage : Page
{
    public ProjectLauncherPage()
    {
        ViewModel = App.Services.GetRequiredService<ProjectLauncherViewModel>();
        InitializeComponent();
    }

    public ProjectLauncherViewModel ViewModel { get; }

    private async void OnOpenRecentClick(object sender, RoutedEventArgs args)
    {
        if (sender is FrameworkElement { DataContext: RecentProjectEntry entry })
        {
            await ViewModel.OpenRecentCommand.ExecuteAsync(entry);
        }
    }
}
