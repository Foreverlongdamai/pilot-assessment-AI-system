using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace PilotAssessment.Desktop.Controls;

public sealed partial class SaveConflictBanner : UserControl
{
    public SaveConflictBanner()
    {
        InitializeComponent();
    }

    public event EventHandler? ReloadRequested;

    public event EventHandler? ReapplyRequested;

    public event EventHandler? RetryRequested;

    public void ShowConflict(string message)
    {
        Show("Canonical revision conflict", message);
        ReloadButton.Visibility = Visibility.Visible;
        ReapplyButton.Visibility = Visibility.Visible;
        RetryButton.Visibility = Visibility.Collapsed;
    }

    public void ShowOffline(string message)
    {
        Show("Backend connection interrupted", message);
        ReloadButton.Visibility = Visibility.Collapsed;
        ReapplyButton.Visibility = Visibility.Collapsed;
        RetryButton.Visibility = Visibility.Visible;
    }

    public void ShowBlocked(string message)
    {
        Show("Autosave blocked", message);
        ReloadButton.Visibility = Visibility.Collapsed;
        ReapplyButton.Visibility = Visibility.Collapsed;
        RetryButton.Visibility = Visibility.Collapsed;
    }

    public void Hide() => BannerRoot.Visibility = Visibility.Collapsed;

    private void Show(string title, string message)
    {
        TitleText.Text = title;
        MessageText.Text = message;
        BannerRoot.Visibility = Visibility.Visible;
    }

    private void OnReloadClick(object sender, RoutedEventArgs args) =>
        ReloadRequested?.Invoke(this, EventArgs.Empty);

    private void OnReapplyClick(object sender, RoutedEventArgs args) =>
        ReapplyRequested?.Invoke(this, EventArgs.Empty);

    private void OnRetryClick(object sender, RoutedEventArgs args) =>
        RetryRequested?.Invoke(this, EventArgs.Empty);
}
