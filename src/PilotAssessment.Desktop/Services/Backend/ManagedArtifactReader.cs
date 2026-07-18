using System.Diagnostics;
using System.Text;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.ViewModels;

namespace PilotAssessment.Desktop.Services.Backend;

public sealed class ManagedArtifactReader : IManagedArtifactReader
{
    private readonly ProjectLauncherViewModel _projects;

    public ManagedArtifactReader(ProjectLauncherViewModel projects)
    {
        _projects = projects;
    }

    public async Task<string> ReadTextAsync(
        ManagedArtifact artifact,
        long maxBytes,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(artifact);
        if (artifact.ByteSize > maxBytes)
        {
            throw new InvalidDataException(
                $"Artifact {artifact.ArtifactId} is {artifact.ByteSize} bytes; the inline limit is {maxBytes} bytes.");
        }

        var path = ResolvePath(artifact);
        var info = new FileInfo(path);
        if (!info.Exists || info.Length != artifact.ByteSize)
        {
            throw new InvalidDataException(
                $"Managed artifact {artifact.ArtifactId} no longer matches its verified metadata.");
        }

        await using var stream = new FileStream(
            path,
            FileMode.Open,
            FileAccess.Read,
            FileShare.Read,
            4096,
            FileOptions.Asynchronous | FileOptions.SequentialScan);
        using var reader = new StreamReader(
            stream,
            new UTF8Encoding(false, true),
            detectEncodingFromByteOrderMarks: true,
            leaveOpen: false);
        return await reader.ReadToEndAsync(cancellationToken);
    }

    public string ResolvePath(ManagedArtifact artifact)
    {
        ArgumentNullException.ThrowIfNull(artifact);
        var root = _projects.CurrentProjectRoot;
        if (string.IsNullOrWhiteSpace(root))
        {
            throw new InvalidOperationException("No managed project is open.");
        }

        if (Path.IsPathRooted(artifact.ManagedRelativePath))
        {
            throw new InvalidDataException("Managed artifact paths must be project-relative.");
        }

        var fullRoot = Path.GetFullPath(root);
        var rootPrefix = fullRoot.EndsWith(Path.DirectorySeparatorChar)
            ? fullRoot
            : fullRoot + Path.DirectorySeparatorChar;
        var fullPath = Path.GetFullPath(Path.Combine(fullRoot, artifact.ManagedRelativePath));
        if (!fullPath.StartsWith(rootPrefix, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException("Managed artifact path escapes the open project root.");
        }

        return fullPath;
    }

    public Task OpenAsync(
        ManagedArtifact artifact,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var path = ResolvePath(artifact);
        var startInfo = new ProcessStartInfo
        {
            FileName = "explorer.exe",
            UseShellExecute = false,
        };
        startInfo.ArgumentList.Add("/select,");
        startInfo.ArgumentList.Add(path);
        _ = Process.Start(startInfo)
            ?? throw new InvalidOperationException("Windows Explorer could not be started.");
        return Task.CompletedTask;
    }
}
