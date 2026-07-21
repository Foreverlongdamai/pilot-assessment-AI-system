using System.Text.Json;
using System.Text.Json.Nodes;

using PilotAssessment.Desktop.Core.Contracts;

namespace PilotAssessment.Desktop.Core.State;

public sealed record ExtractionBindingEdit(
    string RecipeInputBindingId,
    EvidenceRecipe UpdatedRecipe);

public static class EvidenceRecipeEdgeEditor
{
    public static ExtractionBindingEdit AddRawInput(
        ModelNode evidence,
        ModelNode rawInput)
    {
        if (evidence.Definition is not EvidenceNodeDefinition evidenceDefinition)
        {
            throw new ArgumentException("Extraction child must be an Evidence node.", nameof(evidence));
        }

        if (rawInput.Definition is not RawInputNodeDefinition rawDefinition)
        {
            throw new ArgumentException("Extraction parent must be a Raw Input node.", nameof(rawInput));
        }

        var suffix = Guid.NewGuid().ToString("N");
        var bindingId = $"input.user.{suffix}";
        var recipeNodeId = $"input-node.user.{suffix}";
        var input = new RecipeInputBinding(
            bindingId,
            InputBindingKind.Stream,
            rawDefinition.SourceDescriptor.SourceId,
            rawInput.ShortName,
            rawDefinition.SourceDescriptor.DeclaredType,
            new Dictionary<string, JsonElement>(StringComparer.Ordinal));
        var recipeNode = new RecipeNode(
            recipeNodeId,
            "input.binding",
            "0.1.0",
            bindingId,
            new Dictionary<string, JsonNode?>(StringComparer.Ordinal));
        var recipe = evidenceDefinition.Recipe with
        {
            Inputs = [.. evidenceDefinition.Recipe.Inputs, input],
            Graph = evidenceDefinition.Recipe.Graph with
            {
                Nodes = [.. evidenceDefinition.Recipe.Graph.Nodes, recipeNode],
            },
        };
        return new ExtractionBindingEdit(bindingId, recipe);
    }

    public static EvidenceRecipe RemoveRawInput(
        EvidenceNodeDefinition definition,
        string bindingId)
    {
        ArgumentNullException.ThrowIfNull(definition);
        ArgumentException.ThrowIfNullOrWhiteSpace(bindingId);
        if (!definition.Recipe.Inputs.Any(input => input.BindingId == bindingId))
        {
            throw new ArgumentException("The extraction binding does not exist.", nameof(bindingId));
        }

        var removedNodeIds = definition.Recipe.Graph.Nodes
            .Where(node => node.InputBindingId == bindingId)
            .Select(node => node.NodeId)
            .ToHashSet(StringComparer.Ordinal);
        var scoring = definition.Recipe.Scoring;
        if (scoring?.Input is { } input && removedNodeIds.Contains(input.NodeId))
        {
            scoring = scoring with { Input = null };
        }

        return definition.Recipe with
        {
            Inputs = definition.Recipe.Inputs
                .Where(input => input.BindingId != bindingId)
                .ToArray(),
            Graph = definition.Recipe.Graph with
            {
                Nodes = definition.Recipe.Graph.Nodes
                    .Where(node => !removedNodeIds.Contains(node.NodeId))
                    .ToArray(),
                Edges = definition.Recipe.Graph.Edges
                    .Where(edge =>
                        !removedNodeIds.Contains(edge.Source.NodeId) &&
                        !removedNodeIds.Contains(edge.Target.NodeId))
                    .ToArray(),
            },
            Outputs = definition.Recipe.Outputs
                .Where(output => !removedNodeIds.Contains(output.Source.NodeId))
                .ToArray(),
            Scoring = scoring,
        };
    }

    public static double[] UniformStateWeights(ModelNode node)
    {
        var stateCount = node.Definition switch
        {
            EvidenceNodeDefinition evidence => evidence.OrderedObservationStates.Length,
            BnNodeDefinition bn => bn.OrderedStates.Length,
            _ => throw new ArgumentException("Raw Input nodes have no probabilistic states.", nameof(node)),
        };
        return Enumerable.Repeat(1.0 / stateCount, stateCount).ToArray();
    }
}
