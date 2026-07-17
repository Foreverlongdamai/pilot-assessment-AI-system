using PilotAssessment.Desktop.Core.Contracts;

namespace PilotAssessment.Desktop.Core.State;

public enum GraphViewMode
{
    ActiveOnly,
    ActiveAndInactive,
    AllGlobalNodes,
}

public sealed record GraphProjectionOptions(
    GraphViewMode ViewMode,
    string? SearchText = null,
    ModelNodeKind? NodeKind = null,
    string? Group = null,
    string? Tag = null,
    bool? Active = null,
    IReadOnlySet<string>? SelectedNodeIds = null);

public sealed record GraphNodeProjection(
    ModelNode Node,
    double X,
    double Y,
    bool IsActive,
    bool IsOutput,
    bool IsArchived,
    bool IsSelected,
    string DisplayName,
    string KindLabel,
    string StatusLabel,
    string AutomationName,
    double VisualOpacity)
{
    public string NodeId => Node.NodeId;
    public ModelNodeKind NodeKind => Node.NodeKind;
    public double Diameter => GraphProjection.NodeDiameter;
}

public sealed record GraphEdgeProjection(
    ModelGraphEdge Edge,
    GraphNodeProjection Parent,
    GraphNodeProjection Child,
    bool IsActive)
{
    public string EdgeId => Edge.EdgeId;
    public ModelGraphEdgeKind EdgeKind => Edge.EdgeKind;
}

public sealed record GraphProjectionResult(
    IReadOnlyList<GraphNodeProjection> Nodes,
    IReadOnlyList<GraphEdgeProjection> Edges,
    double ExtentWidth,
    double ExtentHeight);

public static class GraphProjection
{
    public const double NodeDiameter = 116;
    public const double CanvasPadding = 96;
    public const double MinimumExtentWidth = 960;
    public const double MinimumExtentHeight = 640;

    public static GraphProjectionResult Project(
        ModelGraphSnapshot snapshot,
        GraphProjectionOptions options)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        ArgumentNullException.ThrowIfNull(options);

        var activeIds = snapshot.Scheme.ComputedActiveClosure.ToHashSet(StringComparer.Ordinal);
        var outputIds = snapshot.Scheme.OutputNodeIds.ToHashSet(StringComparer.Ordinal);
        var selectedIds = options.SelectedNodeIds ?? new HashSet<string>(StringComparer.Ordinal);
        var overrideLayouts = snapshot.Scheme.LayoutOverrides.ToDictionary(
            layout => layout.NodeId,
            StringComparer.Ordinal);

        var candidates = snapshot.Nodes
            .Where(node => IncludeByView(node, activeIds, options.ViewMode))
            .Where(node => IncludeByFilters(node, activeIds, options))
            .Select(node => new NodeWithLayout(
                node,
                overrideLayouts.GetValueOrDefault(node.NodeId) ?? node.GlobalLayout))
            .OrderBy(item => item.Node.NodeId, StringComparer.Ordinal)
            .ToArray();

        if (candidates.Length == 0)
        {
            return new GraphProjectionResult([], [], MinimumExtentWidth, MinimumExtentHeight);
        }

        var minimumX = candidates.Min(item => item.Layout.X);
        var minimumY = candidates.Min(item => item.Layout.Y);
        var offsetX = minimumX < CanvasPadding ? CanvasPadding - minimumX : 0;
        var offsetY = minimumY < CanvasPadding ? CanvasPadding - minimumY : 0;
        var projectedNodes = candidates
            .Select(item => ProjectNode(
                item.Node,
                item.Layout.X + offsetX,
                item.Layout.Y + offsetY,
                activeIds.Contains(item.Node.NodeId),
                outputIds.Contains(item.Node.NodeId),
                selectedIds.Contains(item.Node.NodeId)))
            .ToArray();
        var nodeIndex = projectedNodes.ToDictionary(node => node.NodeId, StringComparer.Ordinal);
        var projectedEdges = snapshot.Edges
            .Where(edge => nodeIndex.ContainsKey(edge.Parent.NodeId) && nodeIndex.ContainsKey(edge.Child.NodeId))
            .OrderBy(edge => edge.EdgeId, StringComparer.Ordinal)
            .Select(edge => new GraphEdgeProjection(
                edge,
                nodeIndex[edge.Parent.NodeId],
                nodeIndex[edge.Child.NodeId],
                activeIds.Contains(edge.Parent.NodeId) && activeIds.Contains(edge.Child.NodeId)))
            .ToArray();

        var radius = NodeDiameter / 2;
        var extentWidth = Math.Max(
            MinimumExtentWidth,
            projectedNodes.Max(node => node.X) + radius + CanvasPadding);
        var extentHeight = Math.Max(
            MinimumExtentHeight,
            projectedNodes.Max(node => node.Y) + radius + CanvasPadding);
        return new GraphProjectionResult(
            projectedNodes,
            projectedEdges,
            extentWidth,
            extentHeight);
    }

    private static bool IncludeByView(
        ModelNode node,
        IReadOnlySet<string> activeIds,
        GraphViewMode mode) => mode switch
        {
            GraphViewMode.ActiveOnly => activeIds.Contains(node.NodeId),
            GraphViewMode.ActiveAndInactive => node.Lifecycle is ModelObjectLifecycle.Active,
            GraphViewMode.AllGlobalNodes => true,
            _ => throw new ArgumentOutOfRangeException(nameof(mode), mode, null),
        };

    private static bool IncludeByFilters(
        ModelNode node,
        IReadOnlySet<string> activeIds,
        GraphProjectionOptions options)
    {
        if (options.NodeKind is { } nodeKind && node.NodeKind != nodeKind)
        {
            return false;
        }

        if (!string.IsNullOrWhiteSpace(options.Group) &&
            !string.Equals(node.Group, options.Group, StringComparison.Ordinal))
        {
            return false;
        }

        if (!string.IsNullOrWhiteSpace(options.Tag) && !node.Tags.Contains(options.Tag))
        {
            return false;
        }

        var active = activeIds.Contains(node.NodeId);
        if (options.Active is { } requiredActive && active != requiredActive)
        {
            return false;
        }

        if (string.IsNullOrWhiteSpace(options.SearchText))
        {
            return true;
        }

        var search = options.SearchText.Trim();
        return Contains(node.NodeId, search) ||
               Contains(node.NameEn, search) ||
               Contains(node.NameZh, search) ||
               Contains(node.ShortNameEn, search) ||
               Contains(node.ShortNameZh, search) ||
               Contains(node.DescriptionEn, search) ||
               Contains(node.DescriptionZh, search) ||
               Contains(node.Group, search) ||
               node.Tags.Any(tag => Contains(tag, search));
    }

    private static GraphNodeProjection ProjectNode(
        ModelNode node,
        double x,
        double y,
        bool active,
        bool output,
        bool selected)
    {
        var archived = node.Lifecycle is ModelObjectLifecycle.Archived;
        var displayName = FirstNonBlank(
            node.ShortNameEn,
            node.ShortNameZh,
            node.NameEn,
            node.NameZh,
            node.NodeId);
        var kindLabel = node.Definition switch
        {
            BnNodeDefinition { NodeRole: BnNodeRole.AggregateCompetency } => "BN • COMPETENCY",
            BnNodeDefinition { NodeRole: BnNodeRole.SubSkill } => "BN • SUB-SKILL",
            BnNodeDefinition => "BN NODE",
            EvidenceNodeDefinition => "EVIDENCE",
            RawInputNodeDefinition => "RAW INPUT",
            _ => node.NodeKind switch
            {
                ModelNodeKind.RawInput => "RAW INPUT",
                ModelNodeKind.Evidence => "EVIDENCE",
                _ => "BN NODE",
            },
        };
        var activationLabel = active ? "active" : "inactive";
        var lifecycleLabel = archived ? ", archived" : string.Empty;
        var statusLabel = output
            ? $"{node.TechnicalStatus} • output"
            : node.TechnicalStatus.ToString();
        return new GraphNodeProjection(
            node,
            x,
            y,
            active,
            output,
            archived,
            selected,
            displayName,
            kindLabel,
            statusLabel,
            $"{displayName}, {kindLabel}, {activationLabel}{lifecycleLabel}, {node.TechnicalStatus}",
            archived ? 0.24 : active ? 1.0 : 0.38);
    }

    private static bool Contains(string? value, string search) =>
        value?.Contains(search, StringComparison.OrdinalIgnoreCase) ?? false;

    private static string FirstNonBlank(params string?[] values) =>
        values.First(value => !string.IsNullOrWhiteSpace(value))!;

    private sealed record NodeWithLayout(ModelNode Node, NodeLayout Layout);
}
