using System.Xml.Linq;

namespace PilotAssessment.Desktop.UnitTests.State;

public sealed class BrandingSurfaceTests
{
    [Fact]
    public void DesktopProjectEmbedsBrandIconInExecutable()
    {
        var root = FindRepositoryRoot(AppContext.BaseDirectory);
        var projectPath = Path.Combine(
            root,
            "src",
            "PilotAssessment.Desktop",
            "PilotAssessment.Desktop.csproj");
        var project = XDocument.Load(projectPath);

        var applicationIcon = project
            .Descendants("ApplicationIcon")
            .Select(element => element.Value.Trim())
            .SingleOrDefault();

        Assert.Equal(@"Assets\AppIcon.ico", applicationIcon);
        Assert.True(File.Exists(Path.Combine(Path.GetDirectoryName(projectPath)!, applicationIcon!)));
    }

    private static string FindRepositoryRoot(string startDirectory)
    {
        for (var directory = new DirectoryInfo(startDirectory);
             directory is not null;
             directory = directory.Parent)
        {
            if (File.Exists(Path.Combine(directory.FullName, "pyproject.toml")) &&
                Directory.Exists(Path.Combine(directory.FullName, "src", "PilotAssessment.Desktop")))
            {
                return directory.FullName;
            }
        }

        throw new DirectoryNotFoundException("Could not locate the repository root.");
    }
}
