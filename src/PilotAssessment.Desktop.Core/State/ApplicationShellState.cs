namespace PilotAssessment.Desktop.Core.State;

public enum BackendConnectionState
{
    Stopped,
    Connecting,
    Ready,
    Faulted,
}

public sealed record ShellStateSnapshot(
    BackendConnectionState BackendState,
    string BackendStatus,
    string? BackendError,
    string? BackendDetails,
    string? ProjectId,
    string? SessionId,
    string? SchemeId,
    string? ProjectDisplayName,
    string? SessionDisplayName,
    string? SchemeDisplayName,
    string AutosaveStatus,
    string RunStatus,
    IReadOnlyList<string> Diagnostics)
{
    public bool IsBackendReady => BackendState is BackendConnectionState.Ready;
    public bool HasProjectContext => !string.IsNullOrWhiteSpace(ProjectId);
    public bool CanUseDomainCommands => IsBackendReady && HasProjectContext;
}

public sealed class ApplicationShellState
{
    private const int DiagnosticCapacity = 200;
    private readonly object _gate = new();
    private readonly Queue<string> _diagnostics = new();
    private BackendConnectionState _backendState = BackendConnectionState.Stopped;
    private string _backendStatus = "Stopped";
    private string? _backendError;
    private string? _backendDetails;
    private string? _projectId;
    private string? _sessionId;
    private string? _schemeId;
    private string? _projectDisplayName;
    private string? _sessionDisplayName;
    private string? _schemeDisplayName;
    private string _autosaveStatus = "No pending changes";
    private string _runStatus = "Idle";

    public event EventHandler? Changed;

    public ShellStateSnapshot Snapshot
    {
        get
        {
            lock (_gate)
            {
                return SnapshotUnsafe();
            }
        }
    }

    public void BeginBackendConnection()
    {
        Mutate(() =>
        {
            _backendState = BackendConnectionState.Connecting;
            _backendStatus = "Connecting";
            _backendError = null;
            _backendDetails = null;
        });
    }

    public void CompleteBackendConnection(string details)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(details);
        Mutate(() =>
        {
            _backendState = BackendConnectionState.Ready;
            _backendStatus = "Ready";
            _backendError = null;
            _backendDetails = details;
        });
    }

    public void FailBackendConnection(string error)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(error);
        Mutate(() =>
        {
            _backendState = BackendConnectionState.Faulted;
            _backendStatus = "Unavailable";
            _backendError = error;
        });
    }

    public void MarkBackendStopped()
    {
        Mutate(() =>
        {
            _backendState = BackendConnectionState.Stopped;
            _backendStatus = "Stopped";
            _backendDetails = null;
        });
    }

    public void SetProjectContext(
        string? projectId,
        string? sessionId = null,
        string? schemeId = null,
        string? projectDisplayName = null,
        string? sessionDisplayName = null,
        string? schemeDisplayName = null)
    {
        if (string.IsNullOrWhiteSpace(projectId) &&
            (!string.IsNullOrWhiteSpace(sessionId) || !string.IsNullOrWhiteSpace(schemeId)))
        {
            throw new ArgumentException("Session and scheme context require a project context.");
        }

        Mutate(() =>
        {
            var nextProjectId = Normalize(projectId);
            var nextSessionId = Normalize(sessionId);
            var nextSchemeId = Normalize(schemeId);
            _projectDisplayName = ResolveDisplayName(
                _projectId,
                nextProjectId,
                _projectDisplayName,
                projectDisplayName);
            _sessionDisplayName = ResolveDisplayName(
                _sessionId,
                nextSessionId,
                _sessionDisplayName,
                sessionDisplayName);
            _schemeDisplayName = ResolveDisplayName(
                _schemeId,
                nextSchemeId,
                _schemeDisplayName,
                schemeDisplayName);
            _projectId = nextProjectId;
            _sessionId = nextSessionId;
            _schemeId = nextSchemeId;
        });
    }

    public void SetSchemeContext(string? schemeId, string? schemeDisplayName = null)
    {
        Mutate(() =>
        {
            var nextSchemeId = Normalize(schemeId);
            _schemeDisplayName = ResolveDisplayName(
                _schemeId,
                nextSchemeId,
                _schemeDisplayName,
                schemeDisplayName);
            _schemeId = nextSchemeId;
        });
    }

    public void SetAutosaveStatus(string status)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(status);
        Mutate(() => _autosaveStatus = status);
    }

    public void SetRunStatus(string status)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(status);
        Mutate(() => _runStatus = status);
    }

    public void AppendDiagnostic(string line)
    {
        if (string.IsNullOrWhiteSpace(line))
        {
            return;
        }

        Mutate(() =>
        {
            while (_diagnostics.Count >= DiagnosticCapacity)
            {
                _diagnostics.Dequeue();
            }

            _diagnostics.Enqueue(line);
        });
    }

    private void Mutate(Action mutation)
    {
        lock (_gate)
        {
            mutation();
        }

        Changed?.Invoke(this, EventArgs.Empty);
    }

    private ShellStateSnapshot SnapshotUnsafe() => new(
        _backendState,
        _backendStatus,
        _backendError,
        _backendDetails,
        _projectId,
        _sessionId,
        _schemeId,
        _projectDisplayName,
        _sessionDisplayName,
        _schemeDisplayName,
        _autosaveStatus,
        _runStatus,
        _diagnostics.ToArray());

    private static string? Normalize(string? value) =>
        string.IsNullOrWhiteSpace(value) ? null : value;

    private static string? ResolveDisplayName(
        string? previousId,
        string? nextId,
        string? previousDisplayName,
        string? requestedDisplayName)
    {
        if (nextId is null)
        {
            return null;
        }

        var normalized = Normalize(requestedDisplayName);
        return string.Equals(previousId, nextId, StringComparison.Ordinal)
            ? normalized ?? previousDisplayName
            : normalized;
    }
}
