using PilotAssessment.Desktop.Core.Contracts;

namespace PilotAssessment.Desktop.Core.State;

public enum GraphViewMode
{
    ActiveOnly,
    ActiveAndInactive,
    AllGlobalNodes,
}

public enum GraphDisplayLayer
{
    RawInputFamily,
    ExtractedData,
    Evidence,
    SubSkill,
    Competency,
}

public sealed record GraphProjectionOptions(
    GraphViewMode ViewMode,
    string? SearchText = null,
    GraphDisplayLayer? Layer = null,
    string? Group = null,
    bool? Active = null,
    IReadOnlySet<string>? SelectedNodeIds = null,
    string Language = "en-US",
    GraphProjectionLabels? Labels = null,
    GraphRawInputFamilyLabels? RawInputFamilyLabels = null);

public sealed record GraphRawInputFamilyLabel(
    string DisplayName,
    string Description);

public sealed record GraphRawInputFamilyLabels(
    GraphRawInputFamilyLabel X,
    GraphRawInputFamilyLabel U,
    GraphRawInputFamilyLabel I,
    GraphRawInputFamilyLabel G,
    GraphRawInputFamilyLabel P,
    string KindLabel,
    string AutomationFormat)
{
    public static GraphRawInputFamilyLabels English { get; } = new(
        new("Flight State", "Position, attitude, velocity, acceleration, and other flight states"),
        new("Control Input", "Stick, pedal, thrust, and other control inputs"),
        new("Visual Input", "VR first-person view and associated visual acquisition"),
        new("Gaze and AOI", "Gaze, fixation, stare, AOI, and field-of-view association"),
        new("Physiology", "EEG, ECG, and future physiological modalities"),
        "RAW INPUT FAMILY",
        "{0}(t) {1}, {2}, {3} source nodes");

    public GraphRawInputFamilyLabel For(RawInputFamily family) => family switch
    {
        RawInputFamily.X => X,
        RawInputFamily.U => U,
        RawInputFamily.I => I,
        RawInputFamily.G => G,
        RawInputFamily.P => P,
        _ => throw new ArgumentOutOfRangeException(nameof(family), family, null),
    };
}

public sealed record GraphProjectionLabels(
    string RawInput,
    string Evidence,
    string BnNode,
    string SubSkill,
    string Competency,
    string Active,
    string Inactive,
    string Archived,
    string Executable,
    string Incomplete,
    string Blocked,
    string OutputFormat,
    string AutomationFormat)
{
    public static GraphProjectionLabels English { get; } = new(
        "RAW INPUT",
        "EVIDENCE",
        "BN NODE",
        "BN • SUB-SKILL",
        "BN • COMPETENCY",
        "active",
        "inactive",
        "archived",
        "Executable",
        "Incomplete",
        "Blocked",
        "{0} • output",
        "{0}, {1}, {2}");
}

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
    double VisualOpacity,
    double LayoutOffsetX,
    double LayoutOffsetY)
{
    public string NodeId => Node.NodeId;
    public ModelNodeKind NodeKind => Node.NodeKind;
    public double Diameter => GraphProjection.NodeDiameter;
}

public sealed record GraphRawInputFamilyProjection(
    string ProjectionId,
    RawInputFamily Family,
    string Symbol,
    string DisplayName,
    string Description,
    string KindLabel,
    double X,
    double Y,
    int MemberCount,
    string AutomationName)
{
    public double Diameter => GraphProjection.RawInputFamilyDiameter;
}

public sealed record GraphProvenanceEdgeProjection(
    GraphRawInputFamilyProjection Parent,
    GraphNodeProjection Child,
    bool IsActive)
{
    public string EdgeId => $"provenance.{Parent.ProjectionId}.{Child.NodeId}";
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
    IReadOnlyList<GraphRawInputFamilyProjection> RawInputFamilies,
    IReadOnlyList<GraphProvenanceEdgeProjection> ProvenanceEdges,
    double ExtentWidth,
    double ExtentHeight);

public static class GraphProjection
{
    private static readonly IReadOnlySet<RawInputFamily> EmptyFamilies =
        new HashSet<RawInputFamily>();

    public const double NodeDiameter = 116;
    public const double RawInputFamilyDiameter = 148;
    public const double ExtractedDataLaneOffsetX = 300;
    public const double EvidenceLaneOffsetX = 300;
    public const double SubSkillLaneOffsetX = 800;
    public const double CompetencyLaneOffsetX = 1400;
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

        var allLayouts = snapshot.Nodes
            .Select(node => new NodeWithLayout(
                node,
                overrideLayouts.GetValueOrDefault(node.NodeId) ?? node.GlobalLayout))
            .ToArray();
        var candidates = allLayouts
            .Where(node => IncludeByView(node, activeIds, options.ViewMode))
            .Where(node => IncludeByFilters(node, activeIds, options))
            .OrderBy(item => item.Node.NodeId, StringComparer.Ordinal)
            .ToArray();

        var minimumX = allLayouts.Length == 0
            ? CanvasPadding
            : allLayouts.Min(item => item.Layout.X + LayerOffsetX(LayerOf(item.Node)));
        var minimumY = allLayouts.Length == 0
            ? CanvasPadding
            : allLayouts.Min(item => item.Layout.Y);
        var offsetX = minimumX < CanvasPadding ? CanvasPadding - minimumX : 0;
        var offsetY = minimumY < CanvasPadding ? CanvasPadding - minimumY : 0;
        var projectedNodes = candidates
            .Select(item => ProjectNode(
                item.Node,
                item.Layout.X + LayerOffsetX(LayerOf(item.Node)) + offsetX,
                item.Layout.Y + offsetY,
                activeIds.Contains(item.Node.NodeId),
                outputIds.Contains(item.Node.NodeId),
                selectedIds.Contains(item.Node.NodeId),
                options.Language,
                options.Labels ?? GraphProjectionLabels.English,
                LayerOffsetX(LayerOf(item.Node)) + offsetX,
                offsetY))
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

        var familyMembership = ResolveFamilyMembership(snapshot.Nodes);
        var rawInputLabels = options.RawInputFamilyLabels ?? GraphRawInputFamilyLabels.English;
        var showRawInputFamilies = options.Layer is null or GraphDisplayLayer.RawInputFamily;
        var familyNodes = showRawInputFamilies
            ? ProjectRawInputFamilies(projectedNodes, familyMembership, rawInputLabels)
            : [];
        var familyIndex = familyNodes.ToDictionary(node => node.Family);
        var provenanceEdges = projectedNodes
            .Where(node => node.Node.Definition is RawInputNodeDefinition)
            .SelectMany(node => familyMembership.GetValueOrDefault(node.NodeId, EmptyFamilies)
                .Where(familyIndex.ContainsKey)
                .Select(family => new GraphProvenanceEdgeProjection(
                    familyIndex[family],
                    node,
                    node.IsActive)))
            .OrderBy(edge => edge.EdgeId, StringComparer.Ordinal)
            .ToArray();

        var radius = NodeDiameter / 2;
        var familyRadius = RawInputFamilyDiameter / 2;
        var extentWidth = Math.Max(
            MinimumExtentWidth,
            Math.Max(
                projectedNodes.Length == 0 ? 0 : projectedNodes.Max(node => node.X) + radius,
                familyNodes.Length == 0 ? 0 : familyNodes.Max(node => node.X) + familyRadius) + CanvasPadding);
        var extentHeight = Math.Max(
            MinimumExtentHeight,
            Math.Max(
                projectedNodes.Length == 0 ? 0 : projectedNodes.Max(node => node.Y) + radius,
                familyNodes.Length == 0 ? 0 : familyNodes.Max(node => node.Y) + familyRadius) + CanvasPadding);
        return new GraphProjectionResult(
            projectedNodes,
            projectedEdges,
            familyNodes,
            provenanceEdges,
            extentWidth,
            extentHeight);
    }

    private static bool IncludeByView(
        NodeWithLayout item,
        IReadOnlySet<string> activeIds,
        GraphViewMode mode) => mode switch
        {
            GraphViewMode.ActiveOnly => activeIds.Contains(item.Node.NodeId),
            GraphViewMode.ActiveAndInactive => item.Node.Lifecycle is ModelObjectLifecycle.Active,
            GraphViewMode.AllGlobalNodes => true,
            _ => throw new ArgumentOutOfRangeException(nameof(mode), mode, null),
        };

    private static bool IncludeByFilters(
        NodeWithLayout item,
        IReadOnlySet<string> activeIds,
        GraphProjectionOptions options)
    {
        var node = item.Node;
        if (options.Layer is GraphDisplayLayer.RawInputFamily)
        {
            return false;
        }

        if (options.Layer is { } requiredLayer && LayerOf(node) != requiredLayer)
        {
            return false;
        }

        if (!string.IsNullOrWhiteSpace(options.Group) &&
            !string.Equals(node.Group, options.Group, StringComparison.Ordinal))
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
        bool selected,
        string language,
        GraphProjectionLabels labels,
        double layoutOffsetX,
        double layoutOffsetY)
    {
        var archived = node.Lifecycle is ModelObjectLifecycle.Archived;
        _ = language;
        var displayName = ModelDisplayNameResolver.ForNode(node);
        var kindLabel = node.Definition switch
        {
            BnNodeDefinition { NodeRole: BnNodeRole.AggregateCompetency } => labels.Competency,
            BnNodeDefinition { NodeRole: BnNodeRole.SubSkill } => labels.SubSkill,
            BnNodeDefinition => labels.BnNode,
            EvidenceNodeDefinition => labels.Evidence,
            RawInputNodeDefinition => labels.RawInput,
            _ => node.NodeKind switch
            {
                ModelNodeKind.RawInput => labels.RawInput,
                ModelNodeKind.Evidence => labels.Evidence,
                _ => labels.BnNode,
            },
        };
        var activationLabel = active ? labels.Active : labels.Inactive;
        var technicalStatus = node.TechnicalStatus switch
        {
            ModelTechnicalStatus.Executable => labels.Executable,
            ModelTechnicalStatus.Incomplete => labels.Incomplete,
            _ => labels.Blocked,
        };
        var statusLabel = output
            ? string.Format(labels.OutputFormat, technicalStatus)
            : technicalStatus;
        var lifecycleAndStatus = archived
            ? $"{activationLabel}, {labels.Archived}, {technicalStatus}"
            : $"{activationLabel}, {technicalStatus}";
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
            string.Format(labels.AutomationFormat, displayName, kindLabel, lifecycleAndStatus),
            archived ? 0.24 : active ? 1.0 : 0.38,
            layoutOffsetX,
            layoutOffsetY);
    }

    private static GraphRawInputFamilyProjection[] ProjectRawInputFamilies(
        IReadOnlyList<GraphNodeProjection> projectedNodes,
        IReadOnlyDictionary<string, IReadOnlySet<RawInputFamily>> membership,
        GraphRawInputFamilyLabels labels)
    {
        var families = new[]
        {
            RawInputFamily.X,
            RawInputFamily.U,
            RawInputFamily.I,
            RawInputFamily.G,
            RawInputFamily.P,
        };
        var x = CanvasPadding + (RawInputFamilyDiameter / 2);
        var firstY = CanvasPadding + (RawInputFamilyDiameter / 2);
        const double verticalGap = 28;
        var step = RawInputFamilyDiameter + verticalGap;
        return families.Select((family, index) =>
        {
            var label = labels.For(family);
            var memberCount = projectedNodes.Count(node =>
                membership.GetValueOrDefault(node.NodeId, EmptyFamilies).Contains(family));
            var symbol = family.ToString();
            return new GraphRawInputFamilyProjection(
                $"raw-family.{symbol}",
                family,
                symbol,
                label.DisplayName,
                label.Description,
                labels.KindLabel,
                x,
                firstY + (index * step),
                memberCount,
                string.Format(labels.AutomationFormat, symbol, label.DisplayName, labels.KindLabel, memberCount));
        }).ToArray();
    }

    private static IReadOnlyDictionary<string, IReadOnlySet<RawInputFamily>> ResolveFamilyMembership(
        IReadOnlyList<ModelNode> nodes)
    {
        var rawNodes = nodes
            .Where(node => node.Definition is RawInputNodeDefinition)
            .ToArray();
        var sourceIndex = rawNodes
            .Select(node => (Node: node, Definition: (RawInputNodeDefinition)node.Definition))
            .GroupBy(item => item.Definition.SourceDescriptor.SourceId, StringComparer.Ordinal)
            .ToDictionary(group => group.Key, group => group.First().Definition, StringComparer.Ordinal);
        return rawNodes.ToDictionary(
            node => node.NodeId,
            node => (IReadOnlySet<RawInputFamily>)ResolveFamilies(
                (RawInputNodeDefinition)node.Definition,
                sourceIndex,
                new HashSet<string>(StringComparer.Ordinal)),
            StringComparer.Ordinal);
    }

    private static HashSet<RawInputFamily> ResolveFamilies(
        RawInputNodeDefinition definition,
        IReadOnlyDictionary<string, RawInputNodeDefinition> sourceIndex,
        HashSet<string> visiting)
    {
        var result = new HashSet<RawInputFamily>();
        AddFamily(result, definition.Family);
        AddModality(result, definition.SourceDescriptor.RawModality);
        var sourceId = definition.SourceDescriptor.SourceId;
        if (!visiting.Add(sourceId))
        {
            return result;
        }

        foreach (var dependency in definition.SourceDescriptor.SourceDependencies)
        {
            if (sourceIndex.TryGetValue(dependency, out var dependencyDefinition))
            {
                result.UnionWith(ResolveFamilies(dependencyDefinition, sourceIndex, visiting));
            }
        }

        visiting.Remove(sourceId);
        return result;
    }

    private static void AddFamily(ISet<RawInputFamily> result, RawInputFamily? family)
    {
        if (family is null)
        {
            return;
        }

        result.Add(family is RawInputFamily.PilotCamera ? RawInputFamily.I : family.Value);
    }

    private static void AddModality(ISet<RawInputFamily> result, RawModality? modality)
    {
        var family = modality switch
        {
            RawModality.X => RawInputFamily.X,
            RawModality.U => RawInputFamily.U,
            RawModality.I or RawModality.PilotCamera => RawInputFamily.I,
            RawModality.G => RawInputFamily.G,
            RawModality.Eeg or RawModality.Ecg => RawInputFamily.P,
            _ => (RawInputFamily?)null,
        };
        AddFamily(result, family);
    }

    private static bool Contains(string? value, string search) =>
        value?.Contains(search, StringComparison.OrdinalIgnoreCase) ?? false;

    public static GraphDisplayLayer LayerOf(ModelNode node) => node.Definition switch
    {
        RawInputNodeDefinition => GraphDisplayLayer.ExtractedData,
        EvidenceNodeDefinition => GraphDisplayLayer.Evidence,
        BnNodeDefinition { NodeRole: BnNodeRole.AggregateCompetency } =>
            GraphDisplayLayer.Competency,
        BnNodeDefinition => GraphDisplayLayer.SubSkill,
        _ => node.NodeKind switch
        {
            ModelNodeKind.RawInput => GraphDisplayLayer.ExtractedData,
            ModelNodeKind.Evidence => GraphDisplayLayer.Evidence,
            ModelNodeKind.Bn when string.Equals(
                node.Group,
                "competencies",
                StringComparison.OrdinalIgnoreCase) => GraphDisplayLayer.Competency,
            ModelNodeKind.Bn => GraphDisplayLayer.SubSkill,
            _ => throw new ArgumentOutOfRangeException(nameof(node), node.NodeKind, null),
        },
    };

    public static double LayerOffsetX(GraphDisplayLayer layer) => layer switch
    {
        GraphDisplayLayer.ExtractedData => ExtractedDataLaneOffsetX,
        GraphDisplayLayer.Evidence => EvidenceLaneOffsetX,
        GraphDisplayLayer.SubSkill => SubSkillLaneOffsetX,
        GraphDisplayLayer.Competency => CompetencyLaneOffsetX,
        GraphDisplayLayer.RawInputFamily => 0,
        _ => throw new ArgumentOutOfRangeException(nameof(layer), layer, null),
    };

    private sealed record NodeWithLayout(ModelNode Node, NodeLayout Layout);
}
