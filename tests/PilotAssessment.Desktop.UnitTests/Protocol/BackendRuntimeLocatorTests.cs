using PilotAssessment.Desktop.Core.Protocol;

namespace PilotAssessment.Desktop.UnitTests.Protocol;

public sealed class BackendRuntimeLocatorTests : IDisposable
{
    private readonly string _root = Path.Combine(
        Path.GetTempPath(),
        $"pilot-assessment-backend-locator-{Guid.NewGuid():N}");

    [Fact]
    public void LocatePrefersPackagedPrivatePythonAndLiveSourceTree()
    {
        Touch("runtime/python/python.exe");
        Directory.CreateDirectory(PathAt("runtime/site-packages"));
        Touch("backend/src/pilot_assessment/sidecar/__main__.py");
        Touch("backend/pyproject.toml");
        Touch("backend/uv.lock");

        // A development layout at the same root must not shadow the product runtime.
        Touch(".tools/uv/uv.exe");
        Touch("pyproject.toml");
        Directory.CreateDirectory(PathAt("src/pilot_assessment"));

        var options = BackendRuntimeLocator.Locate(_root, _root);

        Assert.Equal(PathAt("runtime/python/python.exe"), options.ExecutablePath);
        Assert.Equal(
            ["-I", "-B", "-u", "-X", "utf8", "-m", "pilot_assessment.sidecar"],
            options.Arguments);
        Assert.Equal(Path.GetFullPath(_root), options.WorkingDirectory);
        Assert.Null(options.EnvironmentVariables["PYTHONHOME"]);
        Assert.Null(options.EnvironmentVariables["PYTHONPATH"]);
        Assert.Equal("1", options.EnvironmentVariables["PYTHONNOUSERSITE"]);
        Assert.Equal("1", options.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"]);
        Assert.Equal(PathAt("system"), options.EnvironmentVariables["PILOT_ASSESSMENT_SYSTEM_ROOT"]);
    }

    [Fact]
    public void LocateFindsPortableProductRootFromNestedDesktopPayload()
    {
        Touch("runtime/python/python.exe");
        Directory.CreateDirectory(PathAt("runtime/site-packages"));
        Touch("backend/src/pilot_assessment/sidecar/__main__.py");
        Touch("backend/pyproject.toml");
        Touch("backend/uv.lock");
        Directory.CreateDirectory(PathAt("app"));

        var options = BackendRuntimeLocator.Locate(
            PathAt("app"),
            PathAt("app"),
            includeCurrentDirectory: false);

        Assert.Equal(PathAt("runtime/python/python.exe"), options.ExecutablePath);
        Assert.Equal(Path.GetFullPath(_root), options.WorkingDirectory);
        Assert.Equal(
            PathAt("system"),
            options.EnvironmentVariables["PILOT_ASSESSMENT_SYSTEM_ROOT"]);
        Assert.Equal(
            Path.GetFullPath(_root),
            options.EnvironmentVariables["PILOT_ASSESSMENT_PRODUCT_ROOT"]);
    }

    [Fact]
    public void LocateFallsBackToRepositoryUvForDevelopment()
    {
        var repository = PathAt("repository");
        Touch("repository/.tools/uv/uv.exe");
        Touch("repository/pyproject.toml");
        Directory.CreateDirectory(PathAt("repository/src/pilot_assessment"));
        var nested = Path.Combine(repository, "src", "PilotAssessment.Desktop", "bin");
        Directory.CreateDirectory(nested);

        var options = BackendRuntimeLocator.Locate(PathAt("empty-app"), nested);

        Assert.Equal(Path.Combine(repository, ".tools", "uv", "uv.exe"), options.ExecutablePath);
        Assert.Equal(
            ["run", "python", "-m", "pilot_assessment.sidecar"],
            options.Arguments);
        Assert.Equal(repository, options.WorkingDirectory);
        Assert.Equal(
            Path.Combine(repository, ".pilot-assessment-local", "system"),
            options.EnvironmentVariables["PILOT_ASSESSMENT_SYSTEM_ROOT"]);
    }

    [Fact]
    public void LocateExplainsBothSupportedLayoutsWhenNothingIsAvailable()
    {
        Directory.CreateDirectory(_root);

        var error = Assert.Throws<FileNotFoundException>(
            () => BackendRuntimeLocator.Locate(_root, _root, includeCurrentDirectory: false));

        Assert.Contains("runtime/python/python.exe", error.Message, StringComparison.Ordinal);
        Assert.Contains(".tools/uv/uv.exe", error.Message, StringComparison.Ordinal);
    }

    public void Dispose()
    {
        if (Directory.Exists(_root))
        {
            Directory.Delete(_root, recursive: true);
        }
    }

    private string PathAt(string relativePath) =>
        Path.Combine(_root, relativePath.Replace('/', Path.DirectorySeparatorChar));

    private void Touch(string relativePath)
    {
        var path = PathAt(relativePath);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, string.Empty);
    }
}
