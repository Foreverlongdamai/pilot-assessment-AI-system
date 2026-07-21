using System.Text.Json.Nodes;

using PilotAssessment.Desktop.Core.Contracts;

namespace PilotAssessment.Desktop.Core.State;

public sealed record MissingOperatorIdentity(
    string RecipeNodeId,
    string OperatorId,
    string OperatorVersion);

public sealed class EvidenceRecipeEditorModel
{
    private readonly Dictionary<string, OperatorDefinition> _operators;

    public EvidenceRecipeEditorModel(
        EvidenceRecipe recipe,
        IEnumerable<OperatorDefinition> operators)
    {
        ArgumentNullException.ThrowIfNull(recipe);
        ArgumentNullException.ThrowIfNull(operators);
        Recipe = recipe;
        _operators = operators.ToDictionary(
            definition => Key(definition.OperatorId, definition.ImplementationVersion),
            StringComparer.Ordinal);
    }

    public EvidenceRecipe Recipe { get; private set; }

    public IReadOnlyList<OperatorDefinition> Operators => _operators.Values
        .OrderBy(definition => definition.Family)
        .ThenBy(definition => definition.Name, StringComparer.Ordinal)
        .ThenBy(definition => definition.ImplementationVersion, StringComparer.Ordinal)
        .ToArray();

    public IReadOnlyList<MissingOperatorIdentity> MissingOperators => Recipe.Graph.Nodes
        .Where(node => !_operators.ContainsKey(Key(node.OperatorId, node.OperatorVersion)))
        .Select(node => new MissingOperatorIdentity(
            node.NodeId,
            node.OperatorId,
            node.OperatorVersion))
        .ToArray();

    public JsonSchemaFormModel CreateParameterForm(string recipeNodeId)
    {
        var node = FindNode(recipeNodeId);
        if (!_operators.TryGetValue(Key(node.OperatorId, node.OperatorVersion), out var definition))
        {
            throw new InvalidOperationException(
                $"Operator {node.OperatorId}@{node.OperatorVersion} is not installed.");
        }

        return JsonSchemaFormModel.Create(definition, node.Parameters);
    }

    public void ApplyParameters(string recipeNodeId, JsonSchemaFormModel form)
    {
        ArgumentNullException.ThrowIfNull(form);
        var replacement = FindNode(recipeNodeId) with { Parameters = form.BuildParameters() };
        Recipe = Recipe with
        {
            Graph = Recipe.Graph with
            {
                Nodes = Recipe.Graph.Nodes
                    .Select(node => node.NodeId == recipeNodeId ? replacement : node)
                    .ToArray(),
            },
        };
    }

    public RecipeNode AddOperator(string operatorId, string operatorVersion)
    {
        if (!_operators.ContainsKey(Key(operatorId, operatorVersion)))
        {
            throw new ArgumentException(
                $"Operator {operatorId}@{operatorVersion} is not installed.");
        }

        var nodeId = NewId("operator", Recipe.Graph.Nodes.Select(node => node.NodeId));
        var node = new RecipeNode(
            nodeId,
            operatorId,
            operatorVersion,
            null,
            new Dictionary<string, JsonNode?>(StringComparer.Ordinal));
        Recipe = Recipe with
        {
            Graph = Recipe.Graph with { Nodes = [.. Recipe.Graph.Nodes, node] },
        };
        return node;
    }

    public void RemoveOperator(string recipeNodeId)
    {
        FindNode(recipeNodeId);
        Recipe = Recipe with
        {
            Graph = Recipe.Graph with
            {
                Nodes = Recipe.Graph.Nodes
                    .Where(node => node.NodeId != recipeNodeId)
                    .ToArray(),
                Edges = Recipe.Graph.Edges
                    .Where(edge => edge.Source.NodeId != recipeNodeId && edge.Target.NodeId != recipeNodeId)
                    .ToArray(),
            },
            Outputs = Recipe.Outputs
                .Where(output => output.Source.NodeId != recipeNodeId)
                .ToArray(),
            Scoring = Recipe.Scoring?.Input?.NodeId == recipeNodeId ? null : Recipe.Scoring,
        };
    }

    public RecipeEdge Connect(
        string sourceNodeId,
        string sourcePortId,
        string targetNodeId,
        string targetPortId,
        string? targetSlotId = null)
    {
        var source = Definition(FindNode(sourceNodeId));
        var target = Definition(FindNode(targetNodeId));
        if (!source.OutputPorts.Any(port => port.PortId == sourcePortId))
        {
            throw new ArgumentException("The source output port is not declared by the operator.");
        }
        if (!target.InputPorts.Any(port => port.PortId == targetPortId))
        {
            throw new ArgumentException("The target input port is not declared by the operator.");
        }

        var edge = new RecipeEdge(
            NewId("edge", Recipe.Graph.Edges.Select(item => item.EdgeId)),
            new NodePortReference(sourceNodeId, sourcePortId),
            new NodePortReference(targetNodeId, targetPortId),
            targetSlotId);
        Recipe = Recipe with
        {
            Graph = Recipe.Graph with { Edges = [.. Recipe.Graph.Edges, edge] },
        };
        return edge;
    }

    public void RemoveEdge(string edgeId)
    {
        if (!Recipe.Graph.Edges.Any(edge => edge.EdgeId == edgeId))
        {
            throw new ArgumentException($"Recipe edge {edgeId} does not exist.");
        }
        Recipe = Recipe with
        {
            Graph = Recipe.Graph with
            {
                Edges = Recipe.Graph.Edges.Where(edge => edge.EdgeId != edgeId).ToArray(),
            },
        };
    }

    public ModelNode BuildUpdatedNode(
        ModelNode original,
        string name,
        string description,
        string? group,
        IEnumerable<string> tags)
    {
        ArgumentNullException.ThrowIfNull(original);
        if (original.Definition is not EvidenceNodeDefinition definition)
        {
            throw new ArgumentException("The editor model can only update an Evidence node.");
        }

        var canonicalName = Normalize(name)
            ?? throw new ArgumentException("Evidence name must not be blank.", nameof(name));
        var canonicalDescription = Normalize(description)
            ?? throw new ArgumentException("Evidence description must not be blank.", nameof(description));

        return original with
        {
            Name = canonicalName,
            ShortName = Shorten(canonicalName)!,
            Description = canonicalDescription,
            Group = Normalize(group),
            Tags = tags
                .Select(Normalize)
                .OfType<string>()
                .Distinct(StringComparer.Ordinal)
                .OrderBy(value => value, StringComparer.Ordinal)
                .ToArray(),
            Definition = definition with { Recipe = Recipe },
        };
    }

    private RecipeNode FindNode(string recipeNodeId) => Recipe.Graph.Nodes.SingleOrDefault(node =>
            string.Equals(node.NodeId, recipeNodeId, StringComparison.Ordinal))
        ?? throw new ArgumentException($"Recipe node {recipeNodeId} does not exist.");

    private OperatorDefinition Definition(RecipeNode node) =>
        _operators.TryGetValue(Key(node.OperatorId, node.OperatorVersion), out var definition)
            ? definition
            : throw new InvalidOperationException(
                $"Operator {node.OperatorId}@{node.OperatorVersion} is not installed.");

    private static string NewId(string prefix, IEnumerable<string> existing)
    {
        var used = existing.ToHashSet(StringComparer.Ordinal);
        for (var index = 1; ; index++)
        {
            var candidate = $"{prefix}.{index}";
            if (!used.Contains(candidate))
            {
                return candidate;
            }
        }
    }

    private static string Key(string operatorId, string operatorVersion) =>
        $"{operatorId}\u001f{operatorVersion}";

    private static string? Normalize(string? value) =>
        string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static string? Shorten(string? value)
    {
        var normalized = Normalize(value);
        return normalized is { Length: > 96 } ? normalized[..96] : normalized;
    }
}
