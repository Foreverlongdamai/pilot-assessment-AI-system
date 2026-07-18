using Microsoft.UI.Xaml.Controls;

using PilotAssessment.Desktop.Views.Pages;

namespace PilotAssessment.Desktop.Services.Navigation;

public sealed class NavigationService
{
    private static readonly IReadOnlyDictionary<string, Type> Routes =
        new Dictionary<string, Type>(StringComparer.Ordinal)
        {
            ["project"] = typeof(ProjectLauncherPage),
            ["session"] = typeof(SessionExplorerPage),
            ["model"] = typeof(ModelStudioPage),
            ["runs"] = typeof(RunsPage),
            ["results"] = typeof(ResultsPage),
            ["library"] = typeof(WorkspacePlaceholderPage),
            ["diagnostics"] = typeof(DiagnosticsPage),
        };

    private Frame? _frame;
    private object? _navigationContext;

    public string? CurrentDestination { get; private set; }

    public void Initialize(Frame frame, object navigationContext)
    {
        ArgumentNullException.ThrowIfNull(frame);
        ArgumentNullException.ThrowIfNull(navigationContext);
        _frame = frame;
        _navigationContext = navigationContext;
    }

    public bool Navigate(string destination)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(destination);
        if (_frame is null || _navigationContext is null)
        {
            throw new InvalidOperationException("NavigationService has not been initialized.");
        }

        if (!Routes.TryGetValue(destination, out var pageType))
        {
            return false;
        }

        if (CurrentDestination == destination && _frame.Content?.GetType() == pageType)
        {
            return true;
        }

        var parameter = new ShellNavigationContext(destination, _navigationContext);
        if (!_frame.Navigate(pageType, parameter))
        {
            return false;
        }

        CurrentDestination = destination;
        return true;
    }

    public bool GoBack()
    {
        if (_frame is not { CanGoBack: true })
        {
            return false;
        }

        _frame.GoBack();
        return true;
    }
}

public sealed record ShellNavigationContext(string Destination, object ViewModel);
