using System.Text.Json;
using System.Text.Json.Serialization;

using PilotAssessment.Desktop.Core.ViewModels;

namespace PilotAssessment.Desktop.Services.Preferences;

public sealed class RecentProjectStore : IRecentProjectStore
{
    private readonly string _filePath;

    public RecentProjectStore()
        : this(Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "PilotAssessmentSystem",
            "recent-projects.json"))
    {
    }

    internal RecentProjectStore(string filePath)
    {
        _filePath = filePath;
    }

    public async Task<IReadOnlyList<RecentProjectEntry>> LoadAsync(
        CancellationToken cancellationToken = default)
    {
        if (!File.Exists(_filePath))
        {
            return [];
        }

        try
        {
            var json = await File.ReadAllTextAsync(_filePath, cancellationToken);
            return JsonSerializer.Deserialize(
                    json,
                    RecentProjectJsonContext.Default.IReadOnlyListRecentProjectEntry)
                ?? [];
        }
        catch (Exception error) when (
            error is IOException or UnauthorizedAccessException or JsonException)
        {
            return [];
        }
    }

    public async Task SaveAsync(
        IReadOnlyList<RecentProjectEntry> projects,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(projects);
        var directory = Path.GetDirectoryName(_filePath)
            ?? throw new InvalidOperationException("Recent-project path has no parent directory.");
        Directory.CreateDirectory(directory);
        var temporaryPath = Path.Combine(
            directory,
            $".{Path.GetFileName(_filePath)}.{Guid.NewGuid():N}.tmp");
        try
        {
            var json = JsonSerializer.Serialize(
                projects,
                RecentProjectJsonContext.Default.IReadOnlyListRecentProjectEntry);
            await File.WriteAllTextAsync(
                temporaryPath,
                json,
                new System.Text.UTF8Encoding(false),
                cancellationToken);
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
[JsonSerializable(typeof(IReadOnlyList<RecentProjectEntry>))]
internal sealed partial class RecentProjectJsonContext : JsonSerializerContext;
