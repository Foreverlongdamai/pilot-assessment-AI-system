using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;

using PilotAssessment.Desktop.Core.State;
using PilotAssessment.Desktop.Core.ViewModels;
using PilotAssessment.Desktop.Services.Navigation;
using PilotAssessment.Desktop.Services.Windowing;
using PilotAssessment.Desktop.ViewModels;

namespace PilotAssessment.Desktop.Views;

public sealed partial class MainWindow : Window
{
    private readonly NavigationService _navigation;
    private readonly NodeWindowRegistry _nodeWindows;
    private readonly IModelEditSessionGateway _editSession;
    private readonly ILocalizationLookup _localization;
    private readonly ApplicationShellState _shellState;
    private readonly SemaphoreSlim _editSessionOperationGate = new(1, 1);
    private bool _closeApproved;
    private bool _shutdownInProgress;

    public MainWindow(
        ShellViewModel viewModel,
        NavigationService navigation,
        NodeWindowRegistry nodeWindows,
        IModelEditSessionGateway editSession,
        ILocalizationLookup localization,
        ApplicationShellState shellState)
    {
        ViewModel = viewModel;
        _navigation = navigation;
        _nodeWindows = nodeWindows;
        _editSession = editSession;
        _localization = localization;
        _shellState = shellState;
        InitializeComponent();

        ExtendsContentIntoTitleBar = true;
        SetTitleBar(AppTitleBar);
        AppWindow.SetIcon(DesktopAssetLocator.AppIconPath(AppContext.BaseDirectory));
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

    private async void OnSaveAllClick(object sender, RoutedEventArgs args) =>
        await SaveAllChangesAsync();

    private async void OnSaveAllAccelerator(
        KeyboardAccelerator sender,
        KeyboardAcceleratorInvokedEventArgs args)
    {
        args.Handled = true;
        await SaveAllChangesAsync();
    }

    private async Task SaveAllChangesAsync()
    {
        if (_shutdownInProgress || !ViewModel.IsBackendReady ||
            !await _editSessionOperationGate.WaitAsync(0))
        {
            return;
        }

        var committed = false;
        try
        {
            _shellState.SetAutosaveStatus("Committing");
            await _nodeWindows.FlushAllEditsAsync();
            var status = await _editSession.GetEditStatusAsync();
            if (!status.Dirty)
            {
                _shellState.SetAutosaveStatus("No pending changes");
                return;
            }

            await _editSession.CommitEditAsync("expert.desktop");
            committed = true;
            _shellState.SetAutosaveStatus("Saved");
            await _nodeWindows.RefreshAfterModelSaveAsync();
        }
        catch (Exception error)
        {
            if (committed)
            {
                _shellState.SetAutosaveStatus("Saved");
                _shellState.AppendDiagnostic(
                    $"The model was saved, but the desktop view could not refresh: {error.Message}");
                await ShowSaveRefreshFailureAsync(error);
            }
            else
            {
                _shellState.SetAutosaveStatus("Offline / Retry");
                _shellState.AppendDiagnostic($"Save all failed: {error.Message}");
                await ShowSaveFailureAsync(error);
            }
        }
        finally
        {
            _editSessionOperationGate.Release();
        }
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
        await _editSessionOperationGate.WaitAsync();
        try
        {
            await _nodeWindows.FlushAllEditsAsync();
            if (ViewModel.IsBackendReady)
            {
                var status = await _editSession.GetEditStatusAsync();
                if (status.Dirty && !await ResolveDirtyEditSessionAsync())
                {
                    _shutdownInProgress = false;
                    return;
                }
            }

            await _nodeWindows.CloseAllWindowsAsync();
            await ((App)Application.Current).ShutdownAsync();
            _closeApproved = true;
            Close();
        }
        catch (Exception error)
        {
            _shutdownInProgress = false;
            await ShowCloseFailureAsync(error);
        }
        finally
        {
            _editSessionOperationGate.Release();
        }
    }

    private async Task<bool> ResolveDirtyEditSessionAsync()
    {
        var dialog = new ContentDialog
        {
            XamlRoot = RootGrid.XamlRoot,
            Title = _localization["Dialog_SaveChangesTitle"],
            Content = _localization["Dialog_SaveChangesDescription"],
            PrimaryButtonText = _localization["Dialog_SaveAndClose"],
            SecondaryButtonText = _localization["Dialog_DiscardAndClose"],
            CloseButtonText = _localization["Common_Cancel"],
            DefaultButton = ContentDialogButton.Close,
        };
        switch (await dialog.ShowAsync())
        {
            case ContentDialogResult.Primary:
                await _editSession.CommitEditAsync("expert.desktop");
                return true;
            case ContentDialogResult.Secondary:
                await _editSession.DiscardEditAsync("expert.desktop");
                return true;
            default:
                return false;
        }
    }

    private async Task ShowCloseFailureAsync(Exception error)
    {
        var dialog = new ContentDialog
        {
            XamlRoot = RootGrid.XamlRoot,
            Title = _localization["Dialog_CloseFailedTitle"],
            Content = string.Format(
                _localization["Dialog_CloseFailedDescription"],
                error.Message),
            CloseButtonText = _localization["Task_Close"],
        };
        await dialog.ShowAsync();
    }

    private async Task ShowSaveFailureAsync(Exception error)
    {
        var dialog = new ContentDialog
        {
            XamlRoot = RootGrid.XamlRoot,
            Title = _localization["Dialog_SaveFailedTitle"],
            Content = string.Format(
                _localization["Dialog_SaveFailedDescription"],
                error.Message),
            CloseButtonText = _localization["Task_Close"],
        };
        await dialog.ShowAsync();
    }

    private async Task ShowSaveRefreshFailureAsync(Exception error)
    {
        var dialog = new ContentDialog
        {
            XamlRoot = RootGrid.XamlRoot,
            Title = _localization["Dialog_SaveRefreshFailedTitle"],
            Content = string.Format(
                _localization["Dialog_SaveRefreshFailedDescription"],
                error.Message),
            CloseButtonText = _localization["Task_Close"],
        };
        await dialog.ShowAsync();
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
