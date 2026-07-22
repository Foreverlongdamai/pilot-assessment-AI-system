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

    [Fact]
    public void GraphExposesGlobalNodeDeleteAndUsesStableHandledPointerTracking()
    {
        var root = FindRepositoryRoot(AppContext.BaseDirectory);
        var nodeXaml = Load(
            root,
            "src/PilotAssessment.Desktop/Controls/Graph/GraphNodeButton.xaml");
        Assert.Contains(
            nodeXaml.Descendants(Presentation + "MenuFlyoutItem"),
            element => Attribute(element, "Text") ==
                "{Binding [Graph_DeleteNode], Source={StaticResource Localization}}");

        var nodeCode = File.ReadAllText(Path.Combine(
            root,
            "src",
            "PilotAssessment.Desktop",
            "Controls",
            "Graph",
            "GraphNodeButton.xaml.cs"));
        Assert.Contains("args.GetCurrentPoint(this)", nodeCode, StringComparison.Ordinal);
        Assert.Contains(
            "AddHandler(PointerMovedEvent",
            nodeCode,
            StringComparison.Ordinal);
        Assert.DoesNotContain(
            "DragHoldDuration",
            nodeCode,
            StringComparison.Ordinal);

        var page = Load(
            root,
            "src/PilotAssessment.Desktop/Views/Pages/ModelStudioPage.xaml");
        Assert.Contains(
            page.Descendants(Presentation + "AppBarButton"),
            element => Attribute(element, "Label") ==
                "{Binding [Model_DeleteNode], Source={StaticResource Localization}}");
        var pageCode = File.ReadAllText(Path.Combine(
            root,
            "src",
            "PilotAssessment.Desktop",
            "Views",
            "Pages",
            "ModelStudioPage.xaml.cs"));
        Assert.Contains(
            "case GraphNodeCommand.DeleteGlobal:",
            pageCode,
            StringComparison.Ordinal);
    }

    [Fact]
    public void MainWindowExposesAccessibleAtomicSaveAllAndControlS()
    {
        var root = FindRepositoryRoot(AppContext.BaseDirectory);
        var mainWindow = Load(root, "src/PilotAssessment.Desktop/Views/MainWindow.xaml");
        var saveButton = Assert.Single(
            mainWindow.Descendants(Presentation + "AppBarButton"),
            element => Attribute(element, "Label") ==
                "{Binding [Common_SaveAll], Source={StaticResource Localization}}");
        Assert.Equal("OnSaveAllClick", Attribute(saveButton, "Click"));
        Assert.Equal(
            "{Binding [A11y_SaveAllChanges], Source={StaticResource Localization}}",
            Attribute(saveButton, "AutomationProperties.Name"));

        var accelerator = Assert.Single(
            mainWindow.Descendants(Presentation + "KeyboardAccelerator"),
            element => Attribute(element, "Key") == "S");
        Assert.Equal("Control", Attribute(accelerator, "Modifiers"));
        Assert.Equal("OnSaveAllAccelerator", Attribute(accelerator, "Invoked"));

        var mainWindowCode = File.ReadAllText(Path.Combine(
            root,
            "src",
            "PilotAssessment.Desktop",
            "Views",
            "MainWindow.xaml.cs"));
        Assert.Contains("FlushAllEditsAsync", mainWindowCode, StringComparison.Ordinal);
        Assert.Contains("if (!status.Dirty)", mainWindowCode, StringComparison.Ordinal);
        Assert.Contains("CommitEditAsync(\"expert.desktop\")", mainWindowCode, StringComparison.Ordinal);
        Assert.Contains("RefreshAfterModelSaveAsync", mainWindowCode, StringComparison.Ordinal);
        Assert.Contains(
            "SetAutosaveStatus(\"Committing\")",
            mainWindowCode,
            StringComparison.Ordinal);

        var registryCode = File.ReadAllText(Path.Combine(
            root,
            "src",
            "PilotAssessment.Desktop",
            "Services",
            "Windowing",
            "NodeWindowRegistry.cs"));
        Assert.Contains("LoadSystemAsync", registryCode, StringComparison.Ordinal);
        Assert.Contains("LoadGraphAsync", registryCode, StringComparison.Ordinal);

        var workspaceClientCode = File.ReadAllText(Path.Combine(
            root,
            "src",
            "PilotAssessment.Desktop",
            "Services",
            "Backend",
            "ModelWorkspaceClient.cs"));
        Assert.Contains(
            "SetAutosaveStatus(\"Pending changes\")",
            workspaceClientCode,
            StringComparison.Ordinal);

        var editorCode = File.ReadAllText(Path.Combine(
            root,
            "src",
            "PilotAssessment.Desktop",
            "Views",
            "Windows",
            "NodeEditorWindow.xaml.cs"));
        Assert.Contains(
            "_ => \"Pending changes\"",
            editorCode,
            StringComparison.Ordinal);
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
