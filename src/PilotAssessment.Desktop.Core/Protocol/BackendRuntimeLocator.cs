namespace PilotAssessment.Desktop.Core.Protocol;

public static class BackendRuntimeLocator
{
    private static readonly string[] PortableSidecarArguments =
    [
        "-I",
        "-B",
        "-u",
        "-X",
        "utf8",
        "-m",
        "pilot_assessment.sidecar",
    ];

    private static readonly string[] DevelopmentSidecarArguments =
    [
        "run",
        "python",
        "-m",
        "pilot_assessment.sidecar",
    ];

    public static BackendLaunchOptions Locate(
        string? applicationBaseDirectory = null,
        string? developmentStartDirectory = null,
        bool includeCurrentDirectory = true)
    {
        var applicationRoot = Path.GetFullPath(
            applicationBaseDirectory ?? AppContext.BaseDirectory);
        if (TryLocatePortable(applicationRoot, out var portable))
        {
            return portable;
        }

        var checkedDirectories = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var seed in DevelopmentSeeds(
                     applicationRoot,
                     developmentStartDirectory,
                     includeCurrentDirectory))
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
                        DevelopmentSidecarArguments,
                        root,
                        new Dictionary<string, string?>(StringComparer.OrdinalIgnoreCase)
                        {
                            ["PILOT_ASSESSMENT_SYSTEM_ROOT"] = Path.Combine(
                                root,
                                ".pilot-assessment-local",
                                "system"),
                        });
                }
            }
        }

        throw new FileNotFoundException(
            "Could not locate the packaged backend at " +
            "runtime/python/python.exe + backend/src/pilot_assessment, or a development " +
            "repository containing .tools/uv/uv.exe + pyproject.toml + src/pilot_assessment.");
    }

    private static bool TryLocatePortable(
        string root,
        out BackendLaunchOptions options)
    {
        var python = Path.Combine(root, "runtime", "python", "python.exe");
        var sitePackages = Path.Combine(root, "runtime", "site-packages");
        var backendRoot = Path.Combine(root, "backend");
        var packageRoot = Path.Combine(backendRoot, "src", "pilot_assessment");
        var sidecarEntry = Path.Combine(packageRoot, "sidecar", "__main__.py");

        if (File.Exists(python) &&
            Directory.Exists(sitePackages) &&
            File.Exists(sidecarEntry) &&
            File.Exists(Path.Combine(backendRoot, "pyproject.toml")) &&
            File.Exists(Path.Combine(backendRoot, "uv.lock")))
        {
            options = new BackendLaunchOptions(
                python,
                PortableSidecarArguments,
                root,
                new Dictionary<string, string?>(StringComparer.OrdinalIgnoreCase)
                {
                    ["PYTHONHOME"] = null,
                    ["PYTHONPATH"] = null,
                    ["PYTHONNOUSERSITE"] = "1",
                    ["PYTHONDONTWRITEBYTECODE"] = "1",
                    ["PILOT_ASSESSMENT_SYSTEM_ROOT"] = Path.Combine(root, "system"),
                });
            return true;
        }

        options = null!;
        return false;
    }

    private static IEnumerable<string> DevelopmentSeeds(
        string applicationRoot,
        string? explicitStart,
        bool includeCurrentDirectory)
    {
        if (!string.IsNullOrWhiteSpace(explicitStart))
        {
            yield return Path.GetFullPath(explicitStart);
        }

        yield return applicationRoot;
        if (includeCurrentDirectory)
        {
            yield return Environment.CurrentDirectory;
        }
    }
}
