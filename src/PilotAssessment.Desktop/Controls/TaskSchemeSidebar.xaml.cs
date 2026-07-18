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
        var names = await ShowNameDialogAsync(
            Localization["Task_CreateDialog"],
            Localization["Task_DefaultNewName"],
            null);
        if (names is not null)
        {
            await RunUiActionAsync(() => ViewModel.CreateAsync(names.NameEn, names.NameZh));
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

        var names = await ShowNameDialogAsync(
            Localization["Task_RenameDialog"],
            selected.NameEn,
            selected.NameZh);
        if (names is not null)
        {
            await RunUiActionAsync(() => ViewModel.RenameSelectedAsync(names.NameEn, names.NameZh));
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

    private async Task<SchemeNames?> ShowNameDialogAsync(
        string title,
        string? nameEn,
        string? nameZh)
    {
        var english = new TextBox
        {
            Header = Localization["Editor_EnglishName"],
            Text = nameEn ?? string.Empty,
            PlaceholderText = Localization["Task_OneLanguageRequired"],
        };
        var chinese = new TextBox
        {
            Header = Localization["Editor_ChineseName"],
            Text = nameZh ?? string.Empty,
            PlaceholderText = Localization["Task_OneLanguageRequired"],
        };
        var fields = new StackPanel { Spacing = 12 };
        fields.Children.Add(english);
        fields.Children.Add(chinese);
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
            ? new SchemeNames(english.Text, chinese.Text)
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

    private sealed record SchemeNames(string? NameEn, string? NameZh);
}
