using System.Diagnostics;
using System.Text;
using System.Text.Json;

using PilotAssessment.Desktop.Core.Protocol;

namespace PilotAssessment.Desktop.Services.Backend;

public sealed record BackendHandshake(
    string ProtocolVersion,
    string RuntimeId,
    string BackendVersion,
    IReadOnlyList<string> Capabilities,
    int MaxMessageBytes,
    JsonElement CapabilityCatalog,
    JsonElement InitialStatus);

public sealed class SidecarProcessHost : IAsyncDisposable
{
    private const int DiagnosticLineCapacity = 200;
    private static readonly string[] RequiredCapabilities =
    [
        "runtime.protocol.v1",
        "model.current-workspace.v1",
    ];

    private readonly BackendLaunchOptions _options;
    private readonly Process _process;
    private readonly object _diagnosticGate = new();
    private readonly Queue<string> _diagnosticLines = new();
    private readonly object _stopGate = new();
    private readonly Task _stderrReader;
    private Task? _stopTask;
    private int _handshakeCompleted;

    private SidecarProcessHost(
        BackendLaunchOptions options,
        Process process,
        JsonRpcClient client)
    {
        _options = options;
        _process = process;
        Client = client;
        _stderrReader = ReadStandardErrorAsync();
    }

    public event EventHandler<string>? DiagnosticLineReceived;

    public JsonRpcClient Client { get; }
    public BackendHandshake? Handshake { get; private set; }
    public int ProcessId => _process.Id;
    public Task ProcessExit => _process.WaitForExitAsync();

    public IReadOnlyList<string> DiagnosticLines
    {
        get
        {
            lock (_diagnosticGate)
            {
                return _diagnosticLines.ToArray();
            }
        }
    }

    public static async Task<SidecarProcessHost> StartAsync(
        BackendLaunchOptions options,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(options);
        var startInfo = CreateStartInfo(options);
        var process = new Process
        {
            StartInfo = startInfo,
            EnableRaisingEvents = true,
        };

        if (!process.Start())
        {
            process.Dispose();
            throw new InvalidOperationException("The assessment sidecar process did not start.");
        }

        var framer = new JsonLineFramer(
            process.StandardOutput.BaseStream,
            process.StandardInput.BaseStream,
            options.MaxMessageBytes);
        var client = new JsonRpcClient(framer);
        var host = new SidecarProcessHost(options, process, client);

        try
        {
            using var startupTimeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            startupTimeout.CancelAfter(options.StartupTimeout);
            host.Handshake = await host.PerformHandshakeAsync(startupTimeout.Token).ConfigureAwait(false);
            Volatile.Write(ref host._handshakeCompleted, 1);
            return host;
        }
        catch
        {
            await host.AbortStartupAsync().ConfigureAwait(false);
            throw;
        }
    }

    public Task StopAsync()
    {
        lock (_stopGate)
        {
            return _stopTask ??= StopCoreAsync();
        }
    }

    public async ValueTask DisposeAsync()
    {
        await StopAsync().ConfigureAwait(false);
    }

    private static ProcessStartInfo CreateStartInfo(BackendLaunchOptions options)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = options.ExecutablePath,
            WorkingDirectory = options.WorkingDirectory,
            UseShellExecute = false,
            CreateNoWindow = true,
            WindowStyle = ProcessWindowStyle.Hidden,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardInputEncoding = new UTF8Encoding(false, true),
            StandardOutputEncoding = new UTF8Encoding(false, true),
            StandardErrorEncoding = new UTF8Encoding(false, true),
        };

        foreach (var argument in options.Arguments)
        {
            startInfo.ArgumentList.Add(argument);
        }

        foreach (var variable in options.EnvironmentVariables)
        {
            if (variable.Value is null)
            {
                startInfo.Environment.Remove(variable.Key);
            }
            else
            {
                startInfo.Environment[variable.Key] = variable.Value;
            }
        }

        return startInfo;
    }

    private async Task<BackendHandshake> PerformHandshakeAsync(CancellationToken cancellationToken)
    {
        var hello = await Client.InvokeAsync(
            "runtime.hello",
            ParseElement("""
                {
                  "protocol_version": "1.0",
                  "supported_protocols": ["1.0"],
                  "client": {
                    "name": "PilotAssessment.Desktop",
                    "version": "0.1.0"
                  }
                }
                """),
            cancellationToken).ConfigureAwait(false);

        var protocolVersion = RequiredString(hello, "protocol_version");
        if (protocolVersion != "1.0")
        {
            throw new JsonLineProtocolException(
                $"The sidecar selected unsupported protocol version '{protocolVersion}'.");
        }

        if (RequiredString(hello, "state") != "ready")
        {
            throw new JsonLineProtocolException("The sidecar did not report ready after hello.");
        }

        var capabilities = RequiredStringArray(hello, "capabilities");
        foreach (var capability in RequiredCapabilities)
        {
            if (!capabilities.Contains(capability, StringComparer.Ordinal))
            {
                throw new JsonLineProtocolException(
                    $"The sidecar does not advertise required capability '{capability}'.");
            }
        }

        if (!hello.TryGetProperty("max_message_bytes", out var limitElement) ||
            !limitElement.TryGetInt32(out var advertisedLimit) ||
            advertisedLimit <= 0 ||
            advertisedLimit > _options.MaxMessageBytes)
        {
            throw new JsonLineProtocolException("The sidecar advertised an invalid frame limit.");
        }

        var catalog = await Client.InvokeAsync(
            "capabilities.list",
            EmptyObject(),
            cancellationToken).ConfigureAwait(false);
        var methods = RequiredStringArray(catalog, "methods");
        foreach (var requiredMethod in new[] { "runtime.status", "runtime.shutdown" })
        {
            if (!methods.Contains(requiredMethod, StringComparer.Ordinal))
            {
                throw new JsonLineProtocolException(
                    $"The sidecar method catalog is missing '{requiredMethod}'.");
            }
        }

        var status = await Client.InvokeAsync(
            "runtime.status",
            EmptyObject(),
            cancellationToken).ConfigureAwait(false);
        var state = RequiredString(status, "state");
        if (state is not ("ready" or "busy"))
        {
            throw new JsonLineProtocolException(
                $"The sidecar health state '{state}' is not usable.");
        }

        return new BackendHandshake(
            protocolVersion,
            RequiredString(hello, "runtime_id"),
            RequiredString(hello, "backend_version"),
            capabilities,
            advertisedLimit,
            catalog.Clone(),
            status.Clone());
    }

    private async Task StopCoreAsync()
    {
        try
        {
            if (!_process.HasExited && Volatile.Read(ref _handshakeCompleted) != 0)
            {
                try
                {
                    using var shutdownTimeout = new CancellationTokenSource(_options.ShutdownTimeout);
                    _ = await Client.InvokeAsync(
                        "runtime.shutdown",
                        EmptyObject(),
                        shutdownTimeout.Token).ConfigureAwait(false);
                }
                catch (Exception error)
                {
                    AppendDiagnostic($"sidecar shutdown request failed: {error.Message}");
                }
            }

            await WaitOrTerminateAsync().ConfigureAwait(false);
        }
        finally
        {
            await Client.DisposeAsync().ConfigureAwait(false);
            await AwaitStderrReaderAsync().ConfigureAwait(false);
            _process.Dispose();
        }
    }

    private async Task AbortStartupAsync()
    {
        TryTerminateProcess();
        try
        {
            await _process.WaitForExitAsync().ConfigureAwait(false);
        }
        catch (InvalidOperationException)
        {
        }

        await Client.DisposeAsync().ConfigureAwait(false);
        await AwaitStderrReaderAsync().ConfigureAwait(false);
        _process.Dispose();
    }

    private async Task WaitOrTerminateAsync()
    {
        if (_process.HasExited)
        {
            return;
        }

        using var timeout = new CancellationTokenSource(_options.ShutdownTimeout);
        try
        {
            await _process.WaitForExitAsync(timeout.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            AppendDiagnostic("sidecar did not exit within the shutdown timeout; terminating it");
            TryTerminateProcess();
            await _process.WaitForExitAsync().ConfigureAwait(false);
        }
    }

    private void TryTerminateProcess()
    {
        try
        {
            if (!_process.HasExited)
            {
                _process.Kill(entireProcessTree: true);
            }
        }
        catch (InvalidOperationException)
        {
        }
    }

    private async Task ReadStandardErrorAsync()
    {
        try
        {
            while (await _process.StandardError.ReadLineAsync().ConfigureAwait(false) is { } line)
            {
                AppendDiagnostic(line);
            }
        }
        catch (Exception error) when (error is IOException or ObjectDisposedException)
        {
        }
    }

    private async Task AwaitStderrReaderAsync()
    {
        try
        {
            await _stderrReader.ConfigureAwait(false);
        }
        catch
        {
            // The bounded diagnostic buffer is best effort during teardown.
        }
    }

    private void AppendDiagnostic(string line)
    {
        lock (_diagnosticGate)
        {
            while (_diagnosticLines.Count >= DiagnosticLineCapacity)
            {
                _diagnosticLines.Dequeue();
            }

            _diagnosticLines.Enqueue(line);
        }

        try
        {
            DiagnosticLineReceived?.Invoke(this, line);
        }
        catch
        {
            // Diagnostics consumers cannot break backend supervision.
        }
    }

    private static string RequiredString(JsonElement element, string propertyName)
    {
        if (!element.TryGetProperty(propertyName, out var value) ||
            value.ValueKind is not JsonValueKind.String ||
            string.IsNullOrWhiteSpace(value.GetString()))
        {
            throw new JsonLineProtocolException(
                $"Sidecar response is missing string property '{propertyName}'.");
        }

        return value.GetString()!;
    }

    private static string[] RequiredStringArray(JsonElement element, string propertyName)
    {
        if (!element.TryGetProperty(propertyName, out var value) ||
            value.ValueKind is not JsonValueKind.Array)
        {
            throw new JsonLineProtocolException(
                $"Sidecar response is missing array property '{propertyName}'.");
        }

        var result = new List<string>();
        foreach (var item in value.EnumerateArray())
        {
            if (item.ValueKind is not JsonValueKind.String ||
                string.IsNullOrWhiteSpace(item.GetString()))
            {
                throw new JsonLineProtocolException(
                    $"Sidecar response array '{propertyName}' contains a non-string value.");
            }

            result.Add(item.GetString()!);
        }

        return result.ToArray();
    }

    private static JsonElement EmptyObject() => ParseElement("{}");

    private static JsonElement ParseElement(string json)
    {
        using var document = JsonDocument.Parse(json);
        return document.RootElement.Clone();
    }
}
