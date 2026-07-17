using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.UI.Xaml;

using PilotAssessment.Desktop.Core.State;
using PilotAssessment.Desktop.Services.Backend;
using PilotAssessment.Desktop.Services.Navigation;
using PilotAssessment.Desktop.Services.Preferences;
using PilotAssessment.Desktop.ViewModels;
using PilotAssessment.Desktop.Views;

namespace PilotAssessment.Desktop;

public partial class App : Application
{
    private IHost? _applicationHost;
    private int _shutdownStarted;

    public static Window Window { get; private set; } = null!;

    public static IServiceProvider Services =>
        ((App)Current)._applicationHost?.Services
        ?? throw new InvalidOperationException("Application services are not ready.");

    public static Microsoft.UI.Dispatching.DispatcherQueue DispatcherQueue { get; private set; } = null!;

    public static nint WindowHandle =>
        WinRT.Interop.WindowNative.GetWindowHandle(Window);

    public App()
    {
        InitializeComponent();
    }

    protected override async void OnLaunched(LaunchActivatedEventArgs args)
    {
        DispatcherQueue = Microsoft.UI.Dispatching.DispatcherQueue.GetForCurrentThread();
        var builder = Host.CreateApplicationBuilder();
        builder.Services.AddSingleton<ApplicationShellState>();
        builder.Services.AddSingleton<BackendConnectionService>();
        builder.Services.AddSingleton<LocalPreferencesStore>();
        builder.Services.AddSingleton<NavigationService>();
        builder.Services.AddSingleton<ShellViewModel>();
        builder.Services.AddSingleton<MainWindow>();
        _applicationHost = builder.Build();
        await _applicationHost.StartAsync();

        var shell = _applicationHost.Services.GetRequiredService<ShellViewModel>();
        var window = _applicationHost.Services.GetRequiredService<MainWindow>();
        Window = window;
        window.Activate();

        try
        {
            await shell.InitializeAsync();
            window.NavigateTo(shell.CurrentDestination);
            var backend = _applicationHost.Services.GetRequiredService<BackendConnectionService>();
            if (!await backend.ConnectAsync())
            {
                window.NavigateToDiagnostics();
            }
        }
        catch (Exception error)
        {
            _applicationHost.Services
                .GetRequiredService<ApplicationShellState>()
                .FailBackendConnection(error.Message);
            window.NavigateToDiagnostics();
        }
    }

    public async Task ShutdownAsync()
    {
        if (Interlocked.Exchange(ref _shutdownStarted, 1) != 0)
        {
            return;
        }

        if (_applicationHost is null)
        {
            return;
        }

        await _applicationHost.StopAsync();
        if (_applicationHost is IAsyncDisposable asyncHost)
        {
            await asyncHost.DisposeAsync();
        }
        else
        {
            _applicationHost.Dispose();
        }

        _applicationHost = null;
    }
}
