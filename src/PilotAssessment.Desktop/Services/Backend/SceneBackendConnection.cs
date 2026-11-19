using PilotAssessment.Desktop.Core.Protocol;
using PilotAssessment.Desktop.Core.SceneAssessment;

namespace PilotAssessment.Desktop.Services.Backend;

public sealed class SceneBackendConnection : IAsyncDisposable
{
    private SidecarProcessHost? _host;

    public SceneGateway? Gateway { get; private set; }

    public async Task ConnectAsync(CancellationToken cancellationToken = default)
    {
        if (_host is not null)
        {
            await _host.DisposeAsync();
            _host = null;
            Gateway = null;
        }

        var located = BackendRuntimeLocator.Locate();
        var developmentPython = Path.Combine(located.WorkingDirectory, ".venv", "Scripts", "python.exe");
        var useDevelopmentPython = Path.GetFileName(located.ExecutablePath).Equals("uv.exe", StringComparison.OrdinalIgnoreCase)
            && File.Exists(developmentPython);
        if (Path.GetFileName(located.ExecutablePath).Equals("uv.exe", StringComparison.OrdinalIgnoreCase)
            && !useDevelopmentPython)
        {
            throw new FileNotFoundException("未找到项目已配置的 Python 运行环境。", developmentPython);
        }
        var options = new BackendLaunchOptions(
            useDevelopmentPython ? developmentPython : located.ExecutablePath,
            useDevelopmentPython ? ["-B", "-u", "-X", "utf8", "-m", "pilot_assessment.scene_assessment"] :
            located.Arguments.Select(argument => argument == "pilot_assessment.sidecar"
                ? "pilot_assessment.scene_assessment" : argument).ToArray(),
            located.WorkingDirectory,
            located.EnvironmentVariables,
            located.StartupTimeout,
            located.ShutdownTimeout,
            64 * 1024 * 1024);
        _host = await SidecarProcessHost.StartAsync(options, cancellationToken,
            ["runtime.protocol.v1", "scene.assessment.v1"]);
        Gateway = new SceneGateway(_host.Client);
    }

    public async ValueTask DisposeAsync()
    {
        var host = _host;
        _host = null;
        Gateway = null;
        if (host is not null)
        {
            await host.DisposeAsync();
        }
    }
}
