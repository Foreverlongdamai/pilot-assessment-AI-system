using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

using PilotAssessment.Desktop.Services.Navigation;
using PilotAssessment.Desktop.ViewModels;

namespace PilotAssessment.Desktop.Views;

public sealed partial class MainWindow : Window
{
    private readonly NavigationService _navigation;
    private bool _closeApproved;
    private bool _shutdownInProgress;

    public MainWindow(ShellViewModel viewModel, NavigationService navigation)
    {
        ViewModel = viewModel;
        _navigation = navigation;
        InitializeComponent();

        ExtendsContentIntoTitleBar = true;
        SetTitleBar(AppTitleBar);
        AppWindow.SetIcon("Assets/AppIcon.ico");
        AppWindow.Closing += OnAppWindowClosing;
        ViewModel.ThemeChanged += OnThemeChanged;
        _navigation.Initialize(ContentFrame, ViewModel);
    }

    public ShellViewModel ViewModel { get; }

    public void NavigateTo(string destination)
    {
        if (!_navigation.Navigate(destination))
        {
            return;
        }

        ViewModel.SelectDestination(destination);
        var item = FindNavigationItem(destination);
        if (item is not null)
        {
            ShellNavigation.SelectedItem = item;
        }
    }

    public void NavigateToDiagnostics() => NavigateTo("diagnostics");

    private void OnRootLoaded(object sender, RoutedEventArgs args) =>
        NavigateTo(ViewModel.CurrentDestination);

    private void OnNavigationSelectionChanged(
        NavigationView sender,
        NavigationViewSelectionChangedEventArgs args)
    {
        if (args.SelectedItemContainer?.Tag is string destination)
        {
            NavigateTo(destination);
        }
    }

    private void OnThemeChanged(object? sender, string theme)
    {
        RootGrid.RequestedTheme = theme switch
        {
            "Light" => ElementTheme.Light,
            "Dark" => ElementTheme.Dark,
            _ => ElementTheme.Default,
        };
    }

    private async void OnAppWindowClosing(AppWindow sender, AppWindowClosingEventArgs args)
    {
        if (_closeApproved)
        {
            return;
        }

        args.Cancel = true;
        if (_shutdownInProgress)
        {
            return;
        }

        _shutdownInProgress = true;
        await ((App)Application.Current).ShutdownAsync();
        _closeApproved = true;
        Close();
    }

    private NavigationViewItem? FindNavigationItem(string destination)
    {
        foreach (var item in ShellNavigation.MenuItems.Concat(ShellNavigation.FooterMenuItems))
        {
            if (item is NavigationViewItem navigationItem &&
                navigationItem.Tag is string tag &&
                tag == destination)
            {
                return navigationItem;
            }
        }

        return null;
    }
}
