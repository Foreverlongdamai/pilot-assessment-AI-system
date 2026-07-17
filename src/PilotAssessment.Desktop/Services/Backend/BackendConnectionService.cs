using PilotAssessment.Desktop.Core.Protocol;
using PilotAssessment.Desktop.Core.State;

namespace PilotAssessment.Desktop.Services.Backend;

public sealed class BackendConnectionService : IAsyncDisposable
{
    private readonly ApplicationShellState _shellState;
    private readonly SemaphoreSlim _connectionGate = new(1, 1);
    private SidecarProcessHost? _host;
    private int _disposed;

    public BackendConnectionService(ApplicationShellState shellState)
    {
        _shellState = shellState;
    }

    public JsonRpcClient? Client => Volatile.Read(ref _host)?.Client;

    public async Task<bool> ConnectAsync(CancellationToken cancellationToken = default)
    {
        ObjectDisposedException.ThrowIf(Volatile.Read(ref _disposed) != 0, this);
        await _connectionGate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            _shellState.BeginBackendConnection();
            try
            {
                var previous = Interlocked.Exchange(ref _host, null);
                if (previous is not null)
                {
                    previous.DiagnosticLineReceived -= OnDiagnosticLineReceived;
                    await previous.DisposeAsync().ConfigureAwait(false);
                }

                var options = DevelopmentBackendLocator.Locate();
                var host = await SidecarProcessHost.StartAsync(options, cancellationToken)
                    .ConfigureAwait(false);
                host.DiagnosticLineReceived += OnDiagnosticLineReceived;
                Volatile.Write(ref _host, host);

                var handshake = host.Handshake
                    ?? throw new InvalidOperationException("Sidecar handshake did not complete.");
                _shellState.CompleteBackendConnection(
                    $"Backend {handshake.BackendVersion}; protocol {handshake.ProtocolVersion}; " +
                    $"PID {host.ProcessId}");
                _ = MonitorUnexpectedExitAsync(host);
                return true;
            }
            catch (Exception error)
            {
                _shellState.AppendDiagnostic(error.ToString());
                _shellState.FailBackendConnection(error.Message);
                return false;
            }
        }
        finally
        {
            _connectionGate.Release();
        }
    }

    public Task<bool> ReconnectAsync(CancellationToken cancellationToken = default) =>
        ConnectAsync(cancellationToken);

    public async ValueTask DisposeAsync()
    {
        if (Interlocked.Exchange(ref _disposed, 1) != 0)
        {
            return;
        }

        await _connectionGate.WaitAsync().ConfigureAwait(false);
        try
        {
            var host = Interlocked.Exchange(ref _host, null);
            if (host is not null)
            {
                host.DiagnosticLineReceived -= OnDiagnosticLineReceived;
                await host.DisposeAsync().ConfigureAwait(false);
            }

            _shellState.MarkBackendStopped();
        }
        finally
        {
            _connectionGate.Release();
            _connectionGate.Dispose();
        }
    }

    private async Task MonitorUnexpectedExitAsync(SidecarProcessHost host)
    {
        try
        {
            await Task.WhenAny(host.ProcessExit, host.Client.Completion).ConfigureAwait(false);
            if (Volatile.Read(ref _disposed) == 0 && ReferenceEquals(Volatile.Read(ref _host), host))
            {
                _shellState.FailBackendConnection(
                    "The local assessment backend stopped unexpectedly. Open Diagnostics and reconnect.");
            }
        }
        catch (Exception error)
        {
            if (Volatile.Read(ref _disposed) == 0 && ReferenceEquals(Volatile.Read(ref _host), host))
            {
                _shellState.AppendDiagnostic(error.ToString());
                _shellState.FailBackendConnection(error.Message);
            }
        }
    }

    private void OnDiagnosticLineReceived(object? sender, string line) =>
        _shellState.AppendDiagnostic(line);
}
