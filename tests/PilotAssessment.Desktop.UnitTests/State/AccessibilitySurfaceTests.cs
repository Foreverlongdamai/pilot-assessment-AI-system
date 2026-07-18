using System.Xml.Linq;

namespace PilotAssessment.Desktop.UnitTests.State;

public sealed class AccessibilitySurfaceTests
{
    private static readonly XNamespace Presentation =
        "http://schemas.microsoft.com/winfx/2006/xaml/presentation";
    private static readonly XNamespace Xaml =
        "http://schemas.microsoft.com/winfx/2006/xaml";

    [Fact]
    public void MainWorkflowDeclaresHeadingsLiveStatusAndNamedNavigation()
    {
        var root = FindRepositoryRoot(AppContext.BaseDirectory);
        var mainWindow = Load(root, "src/PilotAssessment.Desktop/Views/MainWindow.xaml");
        var navigation = Assert.Single(mainWindow.Descendants(Presentation + "NavigationView"));
        Assert.Equal(
            "{Binding [A11y_MainNavigation], Source={StaticResource Localization}}",
            Attribute(navigation, "AutomationProperties.Name"));

        foreach (var relativePath in new[]
                 {
                     "src/PilotAssessment.Desktop/Views/Pages/ModelStudioPage.xaml",
                     "src/PilotAssessment.Desktop/Views/Pages/RunsPage.xaml",
                     "src/PilotAssessment.Desktop/Views/Pages/ResultsPage.xaml",
                     "src/PilotAssessment.Desktop/Views/Pages/DiagnosticsPage.xaml",
                 })
        {
            var page = Load(root, relativePath);
            Assert.Contains(
                page.Descendants(Presentation + "TextBlock"),
                element => Attribute(element, "AutomationProperties.HeadingLevel") == "Level1");
        }

        foreach (var relativePath in new[]
                 {
                     "src/PilotAssessment.Desktop/Views/Pages/ModelStudioPage.xaml",
                     "src/PilotAssessment.Desktop/Views/Pages/RunsPage.xaml",
                     "src/PilotAssessment.Desktop/Views/Pages/ResultsPage.xaml",
                     "src/PilotAssessment.Desktop/Views/Pages/DiagnosticsPage.xaml",
                 })
        {
            var page = Load(root, relativePath);
            Assert.Contains(
                page.Descendants(),
                element => Attribute(element, "AutomationProperties.LiveSetting") is "Polite" or "Assertive");
        }
    }

    [Fact]
    public void GraphUsesLocalizedAutomationHelpAndHighContrastThemeResources()
    {
        var root = FindRepositoryRoot(AppContext.BaseDirectory);
        var nodeButton = Load(
            root,
            "src/PilotAssessment.Desktop/Controls/Graph/GraphNodeButton.xaml");
        var button = Assert.Single(nodeButton.Descendants(Presentation + "Button"));
        Assert.Equal("NodeButton", button.Attribute(Xaml + "Name")?.Value);
        Assert.Equal(
            "{Binding [Graph_NodeHelp], Source={StaticResource Localization}}",
            Attribute(button, "AutomationProperties.HelpText"));
        Assert.DoesNotContain(
            nodeButton.Descendants().Attributes(),
            attribute => attribute.Name.LocalName == "Foreground" && attribute.Value == "White");

        var app = Load(root, "src/PilotAssessment.Desktop/App.xaml");
        var highContrast = Assert.Single(
            app.Descendants(Presentation + "ResourceDictionary"),
            element => element.Attribute(Xaml + "Key")?.Value == "HighContrast");
        var brushKeys = highContrast
            .Descendants(Presentation + "SolidColorBrush")
            .Select(element => element.Attribute(Xaml + "Key")?.Value)
            .Where(value => value is not null)
            .ToHashSet(StringComparer.Ordinal);
        Assert.Contains("GraphNodeForegroundBrush", brushKeys);
        Assert.Contains("GraphRawInputNodeBrush", brushKeys);
        Assert.Contains("GraphEvidenceNodeBrush", brushKeys);
        Assert.Contains("GraphBnNodeBrush", brushKeys);
        Assert.Contains("GraphExtractionEdgeBrush", brushKeys);
        Assert.Contains("GraphProbabilisticEdgeBrush", brushKeys);
    }

    private static string? Attribute(XElement element, string localName) =>
        element.Attributes().FirstOrDefault(attribute => attribute.Name.LocalName == localName)?.Value;

    private static XDocument Load(string root, string relativePath) =>
        XDocument.Load(Path.Combine(root, relativePath.Replace('/', Path.DirectorySeparatorChar)));

    private static string FindRepositoryRoot(string startDirectory)
    {
        for (var directory = new DirectoryInfo(startDirectory); directory is not null; directory = directory.Parent)
        {
            if (File.Exists(Path.Combine(directory.FullName, "pyproject.toml")) &&
                Directory.Exists(Path.Combine(directory.FullName, "src", "PilotAssessment.Desktop")))
            {
                return directory.FullName;
            }
        }

        throw new DirectoryNotFoundException(
            $"Could not locate pilot_assessment_system above {startDirectory}");
    }
}
