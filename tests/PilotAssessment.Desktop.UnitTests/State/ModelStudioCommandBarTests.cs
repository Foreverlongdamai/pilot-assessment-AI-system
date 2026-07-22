using System.Xml.Linq;

namespace PilotAssessment.Desktop.UnitTests.State;

public sealed class ModelStudioCommandBarTests
{
    [Fact]
    public void ToolbarUsesLocalizedActionTooltipsAndOmitsOpaqueSelectionModeButtons()
    {
        var root = FindRepositoryRoot(AppContext.BaseDirectory);
        var path = Path.Combine(
            root,
            "src",
            "PilotAssessment.Desktop",
            "Views",
            "Pages",
            "ModelStudioPage.xaml");
        var document = XDocument.Load(path);
        var xaml = document.Root!.Name.Namespace;
        var page = document.Root;

        Assert.Equal("Hidden", page.Attribute("KeyboardAcceleratorPlacementMode")?.Value);

        var commandBar = document
            .Descendants(xaml + "CommandBar")
            .Single(element => element.Attribute("DefaultLabelPosition")?.Value == "Collapsed");
        var buttons = commandBar.Elements(xaml + "AppBarButton").ToArray();

        Assert.Equal(7, buttons.Length);
        Assert.Empty(commandBar.Elements(xaml + "AppBarToggleButton"));
        Assert.All(buttons, button =>
        {
            var label = button.Attribute("Label")?.Value;
            var tooltip = button.Attribute("ToolTipService.ToolTip")?.Value;
            Assert.False(string.IsNullOrWhiteSpace(label));
            Assert.Equal(label, tooltip);
            Assert.DoesNotContain("Ctrl+C", tooltip, StringComparison.OrdinalIgnoreCase);
        });

        var labels = buttons.Select(button => button.Attribute("Label")!.Value).ToArray();
        Assert.Contains(labels, value => value.Contains("Common_Copy", StringComparison.Ordinal));
        Assert.Contains(labels, value => value.Contains("Model_Paste", StringComparison.Ordinal));
        Assert.DoesNotContain(labels, value => value.Contains("Model_ClearSelection", StringComparison.Ordinal));
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
