using System.Xml.Linq;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;

namespace PilotAssessment.Desktop.UnitTests.State;

public sealed class LocalizationTests
{
    private static readonly DateTime Now = new(2026, 7, 17, 12, 0, 0, DateTimeKind.Utc);

    [Fact]
    public void EnglishAndChineseResourcesHaveExactlyTheSameKeys()
    {
        var english = ReadResourceKeys("en-US");
        var chinese = ReadResourceKeys("zh-CN");

        Assert.NotEmpty(english);
        Assert.Equal(english.Length, english.Distinct(StringComparer.Ordinal).Count());
        Assert.Equal(chinese.Length, chinese.Distinct(StringComparer.Ordinal).Count());
        Assert.Equal(english, chinese);
    }

    [Theory]
    [InlineData("zh-CN", "中文名", "English", "中文名")]
    [InlineData("en-US", "中文名", "English", "English")]
    [InlineData("zh-CN", null, "English", "English [EN fallback]")]
    [InlineData("en-US", "中文名", null, "中文名 [中文回退]")]
    [InlineData("en-US", null, null, "node.test [ID fallback]")]
    public void BilingualSelectionUsesVisibleFallbackMarkers(
        string language,
        string? chinese,
        string? english,
        string expected)
    {
        Assert.Equal(
            expected,
            BilingualTextSelector.Select(language, chinese, english, "node.test"));
    }

    [Fact]
    public void LiveLanguageChangeRaisesIndexerAndLanguageNotifications()
    {
        var lookup = new TestLocalization();
        var changedProperties = new List<string?>();
        var languageChanges = 0;
        lookup.PropertyChanged += (_, args) => changedProperties.Add(args.PropertyName);
        lookup.LanguageChanged += (_, _) => languageChanges++;

        Assert.Equal("Projects", lookup["Project_Title"]);
        lookup.Switch("zh-CN");

        Assert.Equal("项目", lookup["Project_Title"]);
        Assert.Contains("Item[]", changedProperties);
        Assert.Contains(nameof(ObservableLocalizationLookup.CurrentLanguage), changedProperties);
        Assert.Equal(1, languageChanges);
    }

    [Fact]
    public void LanguageProjectionDoesNotMutateCanonicalIdentityOrRevisions()
    {
        var node = Node();
        var identityBefore = Identity(node);

        var english = BilingualTextSelector.SelectShortOrFull(
            "en-US",
            node.ShortNameZh,
            node.ShortNameEn,
            node.NameZh,
            node.NameEn,
            node.NodeId);
        var chinese = BilingualTextSelector.SelectShortOrFull(
            "zh-CN",
            node.ShortNameZh,
            node.ShortNameEn,
            node.NameZh,
            node.NameEn,
            node.NodeId);

        Assert.Equal("Precision", english);
        Assert.Equal("精度", chinese);
        Assert.Equal(identityBefore, Identity(node));
    }

    private static string[] ReadResourceKeys(string language)
    {
        var path = Path.Combine(
            AppContext.BaseDirectory,
            "Strings",
            language,
            "Resources.resw");
        return XDocument.Load(path)
            .Root!
            .Elements("data")
            .Select(element => (string)element.Attribute("name")!)
            .OrderBy(key => key, StringComparer.Ordinal)
            .ToArray();
    }

    private static ModelNode Node() => new(
        "model-node",
        "0.1.0",
        "evidence.precision",
        ModelNodeKind.Evidence,
        "精度",
        "Precision",
        "精度",
        "Precision",
        "说明",
        "Description",
        ["precision"],
        "control",
        ModelObjectLifecycle.Active,
        null,
        new TestDefinition(),
        new NodeLayout("evidence.precision", 100, 120),
        7,
        3,
        ModelTechnicalStatus.Executable,
        [],
        new string('a', 64),
        new string('b', 64),
        Now,
        Now);

    private static object Identity(ModelNode node) => new
    {
        node.NodeId,
        node.NodeKind,
        node.SemanticRevision,
        node.LayoutRevision,
        node.ContentHash,
        node.LayoutHash,
        node.Definition,
    };

    private sealed record TestDefinition : ModelNodeDefinition;

    private sealed class TestLocalization : ObservableLocalizationLookup
    {
        private static readonly IReadOnlyDictionary<string, IReadOnlyDictionary<string, string>> Values =
            new Dictionary<string, IReadOnlyDictionary<string, string>>(StringComparer.Ordinal)
            {
                ["en-US"] = new Dictionary<string, string> { ["Project_Title"] = "Projects" },
                ["zh-CN"] = new Dictionary<string, string> { ["Project_Title"] = "项目" },
            };

        public TestLocalization()
            : base("en-US")
        {
        }

        public override string GetString(string key) => Values[CurrentLanguage][key];

        public void Switch(string language) => SetCurrentLanguage(language);
    }
}
