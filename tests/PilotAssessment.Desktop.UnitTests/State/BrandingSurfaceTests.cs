using System.Xml.Linq;

using PilotAssessment.Desktop.Core.State;

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

    [Fact]
    public void DesktopPublishesIconAndResolvesItFromTheExecutableDirectory()
    {
        var root = FindRepositoryRoot(AppContext.BaseDirectory);
        var projectPath = Path.Combine(
            root,
            "src",
            "PilotAssessment.Desktop",
            "PilotAssessment.Desktop.csproj");
        var project = XDocument.Load(projectPath);
        var icon = Assert.Single(
            project.Descendants("Content"),
            element => element.Attribute("Include")?.Value == @"Assets\AppIcon.ico");

        Assert.Equal("PreserveNewest", icon.Element("CopyToOutputDirectory")?.Value);
        Assert.Equal("PreserveNewest", icon.Element("CopyToPublishDirectory")?.Value);

        var baseDirectory = Path.Combine(Path.GetTempPath(), "pilot-assessment", "app");
        Assert.Equal(
            Path.GetFullPath(Path.Combine(baseDirectory, "Assets", "AppIcon.ico")),
            DesktopAssetLocator.AppIconPath(baseDirectory));
    }

    [Fact]
    public void RuntimeLanguageSwitchUsesExplicitResourcesWithoutChangingPlatformOverride()
    {
        var root = FindRepositoryRoot(AppContext.BaseDirectory);
        var service = File.ReadAllText(Path.Combine(
            root,
            "src",
            "PilotAssessment.Desktop",
            "Services",
            "Localization",
            "LocalizationService.cs"));

        Assert.Contains("CreateContext(normalized)", service, StringComparison.Ordinal);
        Assert.DoesNotContain(
            "ApplicationLanguages.PrimaryLanguageOverride",
            service,
            StringComparison.Ordinal);
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
