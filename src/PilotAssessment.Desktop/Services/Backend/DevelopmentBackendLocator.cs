using PilotAssessment.Desktop.Core.Protocol;

namespace PilotAssessment.Desktop.Services.Backend;

public static class DevelopmentBackendLocator
{
    private static readonly string[] SidecarArguments =
    [
        "run",
        "python",
        "-m",
        "pilot_assessment.sidecar",
    ];

    public static BackendLaunchOptions Locate(string? startDirectory = null)
    {
        var checkedDirectories = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var seed in CandidateSeeds(startDirectory))
        {
            for (var directory = new DirectoryInfo(seed); directory is not null; directory = directory.Parent)
            {
                var root = directory.FullName;
                if (!checkedDirectories.Add(root))
                {
                    continue;
                }

                var uvPath = Path.Combine(root, ".tools", "uv", "uv.exe");
                if (File.Exists(uvPath) &&
                    File.Exists(Path.Combine(root, "pyproject.toml")) &&
                    Directory.Exists(Path.Combine(root, "src", "pilot_assessment")))
                {
                    return new BackendLaunchOptions(
                        uvPath,
                        SidecarArguments,
                        root);
                }
            }
        }

        throw new FileNotFoundException(
            "Could not locate pilot_assessment_system/.tools/uv/uv.exe from the application or current directory.");
    }

    private static IEnumerable<string> CandidateSeeds(string? explicitStart)
    {
        if (!string.IsNullOrWhiteSpace(explicitStart))
        {
            yield return Path.GetFullPath(explicitStart);
        }

        yield return AppContext.BaseDirectory;
        yield return Environment.CurrentDirectory;
    }
}
