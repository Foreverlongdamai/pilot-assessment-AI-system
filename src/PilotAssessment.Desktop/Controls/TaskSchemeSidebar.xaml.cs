using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

using PilotAssessment.Desktop.Core.State;
using PilotAssessment.Desktop.Core.ViewModels;

namespace PilotAssessment.Desktop.Controls;

public sealed partial class TaskSchemeSidebar : UserControl
{
    public TaskSchemeSidebar()
    {
        ViewModel = App.Services.GetRequiredService<TaskSchemeListViewModel>();
        InitializeComponent();
    }

    public TaskSchemeListViewModel ViewModel { get; }

    private ILocalizationLookup Localization =>
        App.Services.GetRequiredService<ILocalizationLookup>();

    private async void OnCreateClick(object sender, RoutedEventArgs args)
    {
        var name = await ShowNameDialogAsync(
            Localization["Task_CreateDialog"],
            Localization["Task_DefaultNewName"]);
        if (name is not null)
        {
            await RunUiActionAsync(() => ViewModel.CreateAsync(name));
        }
    }

    private async void OnCopyClick(object sender, RoutedEventArgs args) =>
        await RunUiActionAsync(() => ViewModel.CopySelectedAsync());

    private async void OnRenameClick(object sender, RoutedEventArgs args)
    {
        var selected = ViewModel.SelectedScheme?.Scheme;
        if (selected is null)
        {
            return;
        }

        var name = await ShowNameDialogAsync(
            Localization["Task_RenameDialog"],
            selected.Name);
        if (name is not null)
        {
            await RunUiActionAsync(() => ViewModel.RenameSelectedAsync(name));
        }
    }

    private async void OnArchiveClick(object sender, RoutedEventArgs args)
    {
        var selected = ViewModel.SelectedScheme;
        if (selected is null)
        {
            return;
        }

        var confirmation = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = Localization["Task_ArchiveDialog"],
            Content = Localization.Format("Task_ArchiveDescription", selected.DisplayName),
            PrimaryButtonText = Localization["Common_Archive"],
            CloseButtonText = Localization["Common_Cancel"],
            DefaultButton = ContentDialogButton.Close,
        };
        if (await confirmation.ShowAsync() is ContentDialogResult.Primary)
        {
            await RunUiActionAsync(() => ViewModel.ArchiveSelectedAsync());
        }
    }

    private void OnSearchTextChanged(object sender, TextChangedEventArgs args)
    {
        if (sender is TextBox textBox)
        {
            ViewModel.SearchText = textBox.Text;
        }
    }

    private void OnSchemeSelectionChanged(object sender, SelectionChangedEventArgs args) =>
        ViewModel.Select(SchemeList.SelectedItem as TaskSchemeListItemViewModel);

    private async Task<string?> ShowNameDialogAsync(
        string title,
        string? name)
    {
        var canonicalName = new TextBox
        {
            Header = Localization["Editor_CanonicalName"],
            Text = name ?? string.Empty,
            PlaceholderText = Localization["Editor_CanonicalEnglishHint"],
        };
        var fields = new StackPanel { Spacing = 12 };
        fields.Children.Add(canonicalName);
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = title,
            Content = fields,
            PrimaryButtonText = Localization["Task_Save"],
            CloseButtonText = Localization["Common_Cancel"],
            DefaultButton = ContentDialogButton.Primary,
        };
        return await dialog.ShowAsync() is ContentDialogResult.Primary
            ? canonicalName.Text
            : null;
    }

    private async Task RunUiActionAsync(Func<Task> action)
    {
        try
        {
            await action();
        }
        catch (Exception error)
        {
            var dialog = new ContentDialog
            {
                XamlRoot = XamlRoot,
                Title = Localization["Task_NotChanged"],
                Content = error.Message,
                CloseButtonText = Localization["Task_Close"],
            };
            await dialog.ShowAsync();
        }
    }
}
