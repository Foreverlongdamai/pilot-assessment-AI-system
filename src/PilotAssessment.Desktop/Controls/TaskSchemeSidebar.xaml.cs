using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

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

    private async void OnCreateClick(object sender, RoutedEventArgs args)
    {
        var names = await ShowNameDialogAsync("Create task scheme", "New task scheme", null);
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
            "Rename task scheme",
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
            Title = "Archive task scheme?",
            Content = $"{selected.DisplayName} will become read-only and disappear from the active list. Other task schemes are unchanged.",
            PrimaryButtonText = "Archive",
            CloseButtonText = "Cancel",
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
            Header = "English name",
            Text = nameEn ?? string.Empty,
            PlaceholderText = "At least one language is required",
        };
        var chinese = new TextBox
        {
            Header = "Chinese name",
            Text = nameZh ?? string.Empty,
            PlaceholderText = "至少填写一种语言",
        };
        var fields = new StackPanel { Spacing = 12 };
        fields.Children.Add(english);
        fields.Children.Add(chinese);
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = title,
            Content = fields,
            PrimaryButtonText = "Save",
            CloseButtonText = "Cancel",
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
                Title = "Task scheme was not changed",
                Content = error.Message,
                CloseButtonText = "Close",
            };
            await dialog.ShowAsync();
        }
    }

    private sealed record SchemeNames(string? NameEn, string? NameZh);
}
