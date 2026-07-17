using System.Text.Json;
using PilotAssessment.Desktop.Core.Contracts;

namespace PilotAssessment.Desktop.Core.State;

public sealed record ModelNodeDraftRequest(
    ModelNodeKind NodeKind,
    string? NameEn,
    string? NameZh,
    RawModality RawModality,
    double X,
    double Y);

public static class ModelNodeDraftFactory
{
    private const string ContractVersion = "0.1.0";
    private static readonly string[] DauStateIds = ["desired", "adequate", "undesired"];
    private static readonly string[] BnStateIds = ["low", "medium", "high"];

    public static ModelNode Create(ModelNodeDraftRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        var nameEn = Normalize(request.NameEn);
        var nameZh = Normalize(request.NameZh);
        if (nameEn is null && nameZh is null)
        {
            throw new ArgumentException("A model node needs an English or Chinese name.");
        }

        var nodeId = $"model-node.{KindId(request.NodeKind)}.{Guid.NewGuid():N}";
        var displayName = nameEn ?? nameZh!;
        var now = DateTime.UtcNow;
        ModelNodeDefinition definition = request.NodeKind switch
        {
            ModelNodeKind.RawInput => CreateRawDefinition(displayName, request.RawModality),
            ModelNodeKind.Evidence => CreateEvidenceDefinition(nodeId, displayName),
            ModelNodeKind.Bn => CreateBnDefinition(nodeId),
            _ => throw new ArgumentOutOfRangeException(nameof(request), request.NodeKind, null),
        };
        return new ModelNode(
            "model-node",
            ContractVersion,
            nodeId,
            request.NodeKind,
            nameZh,
            nameEn,
            Shorten(nameZh),
            Shorten(nameEn),
            nameZh is null ? null : "专家新建的可编辑节点；请在节点编辑器中补全其计算定义。",
            "Expert-created editable node; complete its definition in the node editor.",
            ["expert-created"],
            "expert",
            ModelObjectLifecycle.Active,
            null,
            definition,
            new NodeLayout(nodeId, request.X, request.Y),
            0,
            0,
            ModelTechnicalStatus.Incomplete,
            [],
            ZeroHash(),
            ZeroHash(),
            now,
            now);
    }

    private static RawInputNodeDefinition CreateRawDefinition(
        string displayName,
        RawModality modality)
    {
        var sourceId = $"source.user.{Guid.NewGuid():N}";
        return new RawInputNodeDefinition(
            Family(modality),
            RawResourceRole.Stream,
            new SourceDescriptor(
                "source-descriptor",
                ContractVersion,
                sourceId,
                SourceKind.RawStream,
                displayName,
                "Expert-configurable raw input source placeholder.",
                new PortType(ValueType(modality), PortCardinality.One, TemporalSemantics.Sampled, null),
                modality,
                [],
                EmptyElements(),
                ZeroHash()),
            EmptyElements(),
            null,
            "Select the session source and schema expected by this raw input node.");
    }

    private static EvidenceNodeDefinition CreateEvidenceDefinition(
        string nodeId,
        string displayName)
    {
        var states = DauStateIds
            .Select(stateId => new VariableState(stateId, Title(stateId), $"{Title(stateId)} observation."))
            .ToArray();
        var child = new ModelNodeRef(nodeId, ModelNodeKind.Evidence);
        var recipeId = $"recipe.{nodeId}";
        var observationMapping = DauStateIds.ToDictionary(
            stateId => stateId,
            stateId => JsonSerializer.SerializeToElement(
                new Dictionary<string, string>(StringComparer.Ordinal) { ["state_id"] = stateId }),
            StringComparer.Ordinal);
        return new EvidenceNodeDefinition(
            new EvidenceRecipe(
                "evidence-recipe",
                ContractVersion,
                recipeId,
                1,
                new RecipeAnchor(
                    recipeId,
                    displayName,
                    "Blank expert Evidence recipe; add inputs, operators, outputs and scoring.",
                    RecipeLifecycle.Active,
                    RecipeScientificStatus.ExpertDefined),
                [],
                new RecipeGraph([], []),
                [],
                null,
                new RecipeDocumentation(
                    "Blank expert recipe. Its calculation is intentionally incomplete.",
                    [],
                    new Dictionary<string, string>(StringComparer.Ordinal),
                    []),
                new RecipeUiMetadata([], EmptyElements())),
            [],
            states,
            observationMapping,
            [],
            IncompleteCpt(child, DauStateIds),
            ObservationPolicy.HardOrVirtual,
            new Dictionary<string, double>(StringComparer.Ordinal) { ["X"] = 1.0 },
            ModelScientificStatus.ExpertDefined,
            Provenance("blank_expert_evidence"),
            null,
            "Connect Raw Input sources, design the operator graph and configure observation scoring." );
    }

    private static BnNodeDefinition CreateBnDefinition(string nodeId)
    {
        var states = BnStateIds
            .Select(stateId => new VariableState(stateId, Title(stateId), $"{Title(stateId)} latent state."))
            .ToArray();
        var child = new ModelNodeRef(nodeId, ModelNodeKind.Bn);
        return new BnNodeDefinition(
            BnNodeRole.Custom,
            states,
            [],
            IncompleteCpt(child, BnStateIds),
            "Blank expert BN node; choose its role, parents, states and CPT.",
            ModelScientificStatus.ExpertDefined,
            EmptyElements(),
            Provenance("blank_expert_bn"),
            null,
            "Configure fixed probabilistic parents, state semantics and the CPT." );
    }

    private static NodeCpt IncompleteCpt(ModelNodeRef child, string[] stateIds) => new(
        $"cpt.{child.NodeId}",
        child,
        [],
        [.. stateIds],
        [],
        [],
        CptMode.Incomplete,
        Provenance("blank_expert_cpt"),
        ComponentSource.ExpertDefined);

    private static IReadOnlyDictionary<string, JsonElement> Provenance(string source) =>
        new Dictionary<string, JsonElement>(StringComparer.Ordinal)
        {
            ["creation_source"] = JsonSerializer.SerializeToElement(source),
        };

    private static IReadOnlyDictionary<string, JsonElement> EmptyElements() =>
        new Dictionary<string, JsonElement>(StringComparer.Ordinal);

    private static string KindId(ModelNodeKind kind) => kind switch
    {
        ModelNodeKind.RawInput => "raw_input",
        ModelNodeKind.Evidence => "evidence",
        ModelNodeKind.Bn => "bn",
        _ => throw new ArgumentOutOfRangeException(nameof(kind), kind, null),
    };

    private static RawInputFamily Family(RawModality modality) => modality switch
    {
        RawModality.X => RawInputFamily.X,
        RawModality.U => RawInputFamily.U,
        RawModality.I => RawInputFamily.I,
        RawModality.G => RawInputFamily.G,
        RawModality.Eeg or RawModality.Ecg => RawInputFamily.P,
        RawModality.PilotCamera => RawInputFamily.PilotCamera,
        _ => throw new ArgumentOutOfRangeException(nameof(modality), modality, null),
    };

    private static string ValueType(RawModality modality) => modality switch
    {
        RawModality.PilotCamera => "image_frame",
        RawModality.G => "gaze_sample",
        RawModality.Eeg or RawModality.Ecg => "signal_sample",
        _ => "numeric_sample",
    };

    private static string Title(string value) =>
        char.ToUpperInvariant(value[0]) + value[1..];

    private static string? Normalize(string? value) =>
        string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static string? Shorten(string? value) => value switch
    {
        null => null,
        { Length: <= 96 } => value,
        _ => value[..96],
    };

    private static string ZeroHash() => new('0', 64);
}
