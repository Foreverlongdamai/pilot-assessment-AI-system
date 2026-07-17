using System.Text.Json;
using System.Text.Json.Serialization;

namespace PilotAssessment.Desktop.Services.Preferences;

public sealed record LocalPreferences(
    string Language,
    string Theme,
    string LastDestination)
{
    public static LocalPreferences Default { get; } = new("en-GB", "System", "project");
}

public sealed class LocalPreferencesStore
{
    private readonly string _filePath;

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
        if (!File.Exists(_filePath))
        {
            return LocalPreferences.Default;
        }

        try
        {
            var json = await File.ReadAllTextAsync(_filePath, cancellationToken).ConfigureAwait(false);
            return JsonSerializer.Deserialize(
                    json,
                    LocalPreferencesJsonContext.Default.LocalPreferences)
                ?? LocalPreferences.Default;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or JsonException)
        {
            return LocalPreferences.Default;
        }
    }

    public async Task SaveAsync(
        LocalPreferences preferences,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(preferences);
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
