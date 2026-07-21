using System.Text.Json;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;

namespace PilotAssessment.Desktop.UnitTests.State;

public sealed class ModelDisplayNameResolverTests
{
    private static readonly DateTime Now = new(2026, 7, 18, 12, 0, 0, DateTimeKind.Utc);

    [Fact]
    public void MissingRawInputNameUsesTypedSourceMeaning()
    {
        var definition = new RawInputNodeDefinition(
            RawInputFamily.X,
            RawResourceRole.Stream,
            new SourceDescriptor(
                "source-descriptor",
                "0.1.0",
                "source.x",
                SourceKind.RawStream,
                "Flight Dynamics State",
                "Simulator position, attitude and motion state.",
                new PortType("numeric_sample", PortCardinality.One, TemporalSemantics.Sampled, null),
                RawModality.X,
                [],
                EmptyJson(),
                Hash('1')),
            EmptyJson(),
            null,
            null);

        Assert.Equal(
            "Flight Dynamics State",
            ModelDisplayNameResolver.ForNode(Node("model-node.raw_input." + Hash('a')[..32], ModelNodeKind.RawInput, definition)));
    }

    [Fact]
    public void MissingEvidenceNameUsesRecipeAnchorMeaning()
    {
        var nodeId = "model-node.evidence." + Hash('b')[..32];
        var definition = new EvidenceNodeDefinition(
            new EvidenceRecipe(
                "evidence-recipe",
                "0.1.0",
                "recipe.disturbance-aoi",
                1,
                new RecipeAnchor(
                    "H-DISTURBANCE-AOI",
                    "Disturbance AOI Dwell",
                    "Checks whether the pilot attends the expected display during a disturbance.",
                    RecipeLifecycle.Active,
                    RecipeScientificStatus.ExpertDefined),
                [],
                new RecipeGraph([], []),
                [],
                null,
                new RecipeDocumentation("Disturbance AOI evidence.", [], EmptyStrings(), []),
                new RecipeUiMetadata([], EmptyJson())),
            [],
            [],
            EmptyJson(),
            [],
            EmptyCpt(nodeId, ModelNodeKind.Evidence),
            ObservationPolicy.HardOrVirtual,
            new Dictionary<string, double>(),
            ModelScientificStatus.ExpertDefined,
            EmptyJson(),
            null,
            null);

        Assert.Equal(
            "Disturbance AOI Dwell",
            ModelDisplayNameResolver.ForNode(Node(nodeId, ModelNodeKind.Evidence, definition)));
    }

    [Fact]
    public void MissingBnNameUsesReportingMeaningInsteadOfIdentity()
    {
        var nodeId = "model-node.bn." + Hash('c')[..32];
        var reporting = new Dictionary<string, JsonElement>(StringComparer.Ordinal)
        {
            ["display_name"] = JsonSerializer.SerializeToElement("Disturbance Recovery Skill"),
        };
        var definition = new BnNodeDefinition(
            BnNodeRole.SubSkill,
            [],
            [],
            EmptyCpt(nodeId, ModelNodeKind.Bn),
            "Represents recovery performance after a disturbance.",
            ModelScientificStatus.ExpertDefined,
            reporting,
            EmptyJson(),
            null,
            null);

        var name = ModelDisplayNameResolver.ForNode(Node(nodeId, ModelNodeKind.Bn, definition));

        Assert.Equal("Disturbance Recovery Skill", name);
        Assert.DoesNotContain(Hash('c')[..12], name, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void MissingTaskSchemeNameUsesTaskBindingMeaning()
    {
        var taskBindings = new Dictionary<string, JsonElement>(StringComparer.Ordinal)
        {
            ["task_name"] = JsonSerializer.SerializeToElement("Hover"),
        };
        var scheme = new TaskScheme(
            "task-scheme",
            "0.1.0",
            "task-scheme.user." + Hash('d')[..32],
            null,
            null,
            null,
            null,
            [],
            null,
            ModelObjectLifecycle.Active,
            null,
            [],
            [],
            [],
            taskBindings,
            [],
            0,
            0,
            ModelTechnicalStatus.Incomplete,
            [],
            Hash('1'),
            Hash('2'),
            Now,
            Now);

        Assert.Equal("Hover Assessment Scheme", ModelDisplayNameResolver.ForScheme(scheme));
    }

    [Fact]
    public void RandomIdentifierIsNeverPresentedAsTheName()
    {
        var identifier = "model-node.evidence.8cad2f4a80374f13a38f8dcf4e6fbd11";

        var name = ModelDisplayNameResolver.HumanizeIdentifier(identifier, "Evidence");

        Assert.Equal("Evidence", name);
        Assert.DoesNotContain("8cad", name, StringComparison.OrdinalIgnoreCase);
    }

    private static ModelNode Node(string nodeId, ModelNodeKind kind, ModelNodeDefinition definition) => new(
        "model-node",
        "0.1.0",
        nodeId,
        kind,
        null,
        null,
        null,
        null,
        null,
        null,
        [],
        null,
        ModelObjectLifecycle.Active,
        null,
        definition,
        new NodeLayout(nodeId, 0, 0),
        0,
        0,
        ModelTechnicalStatus.Incomplete,
        [],
        Hash('3'),
        Hash('4'),
        Now,
        Now);

    private static NodeCpt EmptyCpt(string nodeId, ModelNodeKind kind) => new(
        "cpt.test",
        new ModelNodeRef(nodeId, kind),
        [],
        [],
        [],
        [],
        CptMode.Incomplete,
        EmptyJson(),
        ComponentSource.ExpertDefined);

    private static IReadOnlyDictionary<string, JsonElement> EmptyJson() =>
        new Dictionary<string, JsonElement>(StringComparer.Ordinal);

    private static IReadOnlyDictionary<string, string> EmptyStrings() =>
        new Dictionary<string, string>(StringComparer.Ordinal);

    private static string Hash(char value) => new(value, 64);
}
