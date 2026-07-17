namespace PilotAssessment.Desktop.Core.Protocol;

public sealed record BackendLaunchOptions
{
    public BackendLaunchOptions(
        string executablePath,
        IReadOnlyList<string> arguments,
        string workingDirectory,
        IReadOnlyDictionary<string, string?>? environmentVariables = null,
        TimeSpan? startupTimeout = null,
        TimeSpan? shutdownTimeout = null,
        int maxMessageBytes = JsonLineFramer.DefaultMaxMessageBytes)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(executablePath);
        ArgumentNullException.ThrowIfNull(arguments);
        ArgumentException.ThrowIfNullOrWhiteSpace(workingDirectory);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(maxMessageBytes);

        ExecutablePath = executablePath;
        Arguments = arguments.ToArray();
        WorkingDirectory = workingDirectory;
        EnvironmentVariables = environmentVariables is null
            ? new Dictionary<string, string?>(StringComparer.OrdinalIgnoreCase)
            : new Dictionary<string, string?>(environmentVariables, StringComparer.OrdinalIgnoreCase);
        StartupTimeout = startupTimeout ?? TimeSpan.FromSeconds(15);
        ShutdownTimeout = shutdownTimeout ?? TimeSpan.FromSeconds(10);
        MaxMessageBytes = maxMessageBytes;

        if (StartupTimeout <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(nameof(startupTimeout));
        }

        if (ShutdownTimeout <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(nameof(shutdownTimeout));
        }
    }

    public string ExecutablePath { get; }
    public IReadOnlyList<string> Arguments { get; }
    public string WorkingDirectory { get; }
    public IReadOnlyDictionary<string, string?> EnvironmentVariables { get; }
    public TimeSpan StartupTimeout { get; }
    public TimeSpan ShutdownTimeout { get; }
    public int MaxMessageBytes { get; }
}
