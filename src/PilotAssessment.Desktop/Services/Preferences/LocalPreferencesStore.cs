using System.Text.Json;
using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Services.Preferences;

public sealed record NodeWindowPlacementPreference(
    string ProjectId,
    string SchemeId,
    string NodeId,
    int X,
    int Y,
    int Width,
    int Height,
    bool IsMaximized);

public sealed record LocalPreferences(
    string Language,
    string Theme,
    string LastDestination,
    NodeWindowPlacementPreference[] NodeWindows)
{
    public static LocalPreferences Default { get; } = new("en-US", "System", "project", []);
}

public sealed class LocalPreferencesStore
{
    private readonly string _filePath;
    private readonly SemaphoreSlim _gate = new(1, 1);

    public LocalPreferencesStore()
        : this(Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "PilotAssessmentSystem",
            "ui-state.json"))
    {
    }

    internal LocalPreferencesStore(string filePath)
    {
        _filePath = filePath;
    }

    public async Task<LocalPreferences> LoadAsync(CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            return await LoadCoreAsync(cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task SaveAsync(
        LocalPreferences preferences,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(preferences);
        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            await SaveCoreAsync(preferences, cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task<LocalPreferences> UpdateAsync(
        Func<LocalPreferences, LocalPreferences> update,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(update);
        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var current = await LoadCoreAsync(cancellationToken).ConfigureAwait(false);
            var updated = update(current) ??
                throw new InvalidOperationException("The UI preference update returned null.");
            await SaveCoreAsync(updated, cancellationToken).ConfigureAwait(false);
            return updated;
        }
        finally
        {
            _gate.Release();
        }
    }

    private async Task<LocalPreferences> LoadCoreAsync(CancellationToken cancellationToken)
    {
        if (!File.Exists(_filePath))
        {
            return LocalPreferences.Default;
        }

        try
        {
            var json = await File.ReadAllTextAsync(_filePath, cancellationToken).ConfigureAwait(false);
            var loaded = JsonSerializer.Deserialize(
                    json,
                    LocalPreferencesJsonContext.Default.LocalPreferences)
                ?? LocalPreferences.Default;
            return loaded.NodeWindows is null ? loaded with { NodeWindows = [] } : loaded;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or JsonException)
        {
            return LocalPreferences.Default;
        }
    }

    private async Task SaveCoreAsync(
        LocalPreferences preferences,
        CancellationToken cancellationToken)
    {
        var directory = Path.GetDirectoryName(_filePath)
            ?? throw new InvalidOperationException("UI preference path has no parent directory.");
        Directory.CreateDirectory(directory);

        var temporaryPath = Path.Combine(
            directory,
            $".{Path.GetFileName(_filePath)}.{Guid.NewGuid():N}.tmp");
        try
        {
            var json = JsonSerializer.Serialize(
                preferences,
                LocalPreferencesJsonContext.Default.LocalPreferences);
            await File.WriteAllTextAsync(
                temporaryPath,
                json,
                new System.Text.UTF8Encoding(false),
                cancellationToken).ConfigureAwait(false);
            File.Move(temporaryPath, _filePath, overwrite: true);
        }
        finally
        {
            if (File.Exists(temporaryPath))
            {
                File.Delete(temporaryPath);
            }
        }
    }
}

[JsonSourceGenerationOptions(
    PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase,
    WriteIndented = true)]
[JsonSerializable(typeof(LocalPreferences))]
internal sealed partial class LocalPreferencesJsonContext : JsonSerializerContext;
