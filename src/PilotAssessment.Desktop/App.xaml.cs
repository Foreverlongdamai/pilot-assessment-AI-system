using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.UI.Xaml;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;
using PilotAssessment.Desktop.Core.ViewModels;
using PilotAssessment.Desktop.Services.Backend;
using PilotAssessment.Desktop.Services.Localization;
using PilotAssessment.Desktop.Services.Navigation;
using PilotAssessment.Desktop.Services.Preferences;
using PilotAssessment.Desktop.Services.Windowing;
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
        var preferencesStore = new LocalPreferencesStore();
        var localPreferences = await preferencesStore.LoadAsync();
        var localization = new LocalizationService(localPreferences.Language);
        Resources["Localization"] = localization;

        var builder = Host.CreateApplicationBuilder();
        builder.Services.AddSingleton<ApplicationShellState>();
        builder.Services.AddSingleton<CanonicalObjectStore<ModelNode>>();
        builder.Services.AddSingleton<ModelClipboard>();
        builder.Services.AddSingleton<BackendConnectionService>();
        builder.Services.AddSingleton(preferencesStore);
        builder.Services.AddSingleton(localization);
        builder.Services.AddSingleton<ILocalizationLookup>(localization);
        builder.Services.AddSingleton<WindowPlacementStore>();
        builder.Services.AddSingleton<IRecentProjectStore, RecentProjectStore>();
        builder.Services.AddSingleton<IProjectFolderPicker, FolderPickerService>();
        builder.Services.AddSingleton<ProjectSessionClient>();
        builder.Services.AddSingleton<IProjectSessionGateway>(services =>
            services.GetRequiredService<ProjectSessionClient>());
        builder.Services.AddSingleton<ModelWorkspaceClient>();
        builder.Services.AddSingleton<IModelWorkspaceGateway>(services =>
            services.GetRequiredService<ModelWorkspaceClient>());
        builder.Services.AddSingleton<IModelGraphGateway>(services =>
            services.GetRequiredService<ModelWorkspaceClient>());
        builder.Services.AddSingleton<IModelNodeEditorGateway>(services =>
            services.GetRequiredService<ModelWorkspaceClient>());
        builder.Services.AddSingleton<IBayesianNodeEditorGateway>(services =>
            services.GetRequiredService<ModelWorkspaceClient>());
        builder.Services.AddSingleton<RunClient>();
        builder.Services.AddSingleton<IRunGateway>(services =>
            services.GetRequiredService<RunClient>());
        builder.Services.AddSingleton<ManagedArtifactReader>();
        builder.Services.AddSingleton<IManagedArtifactReader>(services =>
            services.GetRequiredService<ManagedArtifactReader>());
        builder.Services.AddSingleton<ModelGraphCommandCoordinator>();
        builder.Services.AddSingleton<NavigationService>();
        builder.Services.AddSingleton<ShellViewModel>();
        builder.Services.AddSingleton<SessionExplorerViewModel>();
        builder.Services.AddSingleton<TaskSchemeListViewModel>();
        builder.Services.AddSingleton<ProjectLauncherViewModel>();
        builder.Services.AddSingleton<ModelStudioViewModel>();
        builder.Services.AddSingleton<RunsViewModel>();
        builder.Services.AddSingleton<ResultsViewModel>();
        builder.Services.AddSingleton<DiagnosticsViewModel>();
        builder.Services.AddSingleton<NodeWindowRegistry>();
        builder.Services.AddSingleton<MainWindow>();
        _applicationHost = builder.Build();
        await _applicationHost.StartAsync();

        await _applicationHost.Services
            .GetRequiredService<WindowPlacementStore>()
            .InitializeAsync();

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
                return;
            }

            var projects = _applicationHost.Services.GetRequiredService<ProjectLauncherViewModel>();
            var restored = await projects.InitializeAsync(restoreLastProject: true);
            if (!restored && shell.CurrentDestination is not ("project" or "diagnostics"))
            {
                window.NavigateTo("project");
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
