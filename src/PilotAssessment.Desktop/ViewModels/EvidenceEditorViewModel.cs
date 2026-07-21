using System.Collections.ObjectModel;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;

using CommunityToolkit.Mvvm.ComponentModel;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;
using PilotAssessment.Desktop.Core.ViewModels;

namespace PilotAssessment.Desktop.ViewModels;

public sealed record OperatorOptionItem(
    string OperatorId,
    string ImplementationVersion,
    string Name,
    OperatorFamily Family)
{
    public string DisplayName => $"{Name} · {OperatorId}@{ImplementationVersion}";
}

public sealed record RecipeNodeDisplayItem(
    string NodeId,
    string OperatorId,
    string OperatorVersion,
    string DisplayName,
    bool IsMissing,
    string ParametersSummary);

public sealed record RecipeEdgeDisplayItem(
    string EdgeId,
    string SourceNodeId,
    string SourcePortId,
    string TargetNodeId,
    string TargetPortId,
    string? TargetSlotId)
{
    public string DisplayName =>
        $"{SourceNodeId}.{SourcePortId} → {TargetNodeId}.{TargetPortId}" +
        (TargetSlotId is null ? string.Empty : $" [{TargetSlotId}]");
}

public sealed partial class ObservationStateEditItem : ObservableObject
{
    public ObservationStateEditItem(VariableState state)
    {
        StateId = state.StateId;
        Label = state.Label;
        Description = state.Description;
    }

    [ObservableProperty]
    public partial string StateId { get; set; }

    [ObservableProperty]
    public partial string Label { get; set; }

    [ObservableProperty]
    public partial string Description { get; set; }

    public VariableState Build() => new(StateId.Trim(), Label.Trim(), Description.Trim());
}

public sealed partial class EvidenceEditorViewModel : ObservableObject, IDisposable
{
    private static readonly JsonSerializerOptions ContractJsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        WriteIndented = true,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) },
    };

    private readonly EvidenceEditorCoordinator _coordinator;
    private readonly IBayesianNodeEditorGateway _bayesianGateway;
    private readonly ILocalizationLookup? _localization;
    private ModelNode _canonicalNode;
    private EvidenceRecipeEditorModel _recipeModel;
    private ModelGraphSnapshot? _graph;
    private string? _sessionRevisionId;
    private string _schemeId;
    private IReadOnlyList<ModelNodeUsage> _usages = [];
    private IReadOnlyList<ModelChangeEvent> _history = [];
    private string _statusKey = "Evidence_StatusLoading";
    private string _statusFallback = "Loading Evidence editor metadata…";
    private object?[] _statusArguments = [];
    private string _previewKey = "Evidence_PreviewNone";
    private string _previewFallback = "No preview requested.";
    private object?[] _previewArguments = [];

    [ObservableProperty]
    public partial string Name { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string Description { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string Group { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string TagsText { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string AnchorName { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string AnchorDescription { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string RecipeSummary { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string ScoringJson { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string ObservationMappingJson { get; set; } = "{}";

    [ObservableProperty]
    public partial string ModalityWeightsJson { get; set; } = "{}";

    [ObservableProperty]
    public partial ObservationPolicy ObservationPolicy { get; set; }

    [ObservableProperty]
    public partial string HelpText { get; set; } = string.Empty;

    [ObservableProperty]
    public partial OperatorOptionItem? SelectedOperator { get; set; }

    [ObservableProperty]
    public partial RecipeNodeDisplayItem? SelectedRecipeNode { get; private set; }

    [ObservableProperty]
    public partial JsonSchemaFormModel? ParameterForm { get; private set; }

    [ObservableProperty]
    public partial bool HasMissingOperators { get; private set; }

    [ObservableProperty]
    public partial string MissingOperatorsText { get; private set; } = "All recipe operators are installed.";

    [ObservableProperty]
    public partial string StatusMessage { get; private set; } = "Loading Evidence editor metadata…";

    [ObservableProperty]
    public partial string PreviewSummary { get; private set; } = "No preview requested.";

    [ObservableProperty]
    public partial bool IsBusy { get; private set; }

    [ObservableProperty]
    public partial bool IsPreviewBusy { get; private set; }

    public EvidenceEditorViewModel(
        ModelNode node,
        string schemeId,
        string? sessionRevisionId,
        IModelNodeEditorGateway gateway,
        IBayesianNodeEditorGateway bayesianGateway,
        ILocalizationLookup? localization = null)
    {
        _canonicalNode = node;
        _schemeId = schemeId;
        _sessionRevisionId = sessionRevisionId;
        _coordinator = new EvidenceEditorCoordinator(gateway);
        _bayesianGateway = bayesianGateway;
        _localization = localization;
        var definition = node.Definition as EvidenceNodeDefinition
            ?? throw new ArgumentException("Evidence editor requires an Evidence node.");
        _recipeModel = new EvidenceRecipeEditorModel(definition.Recipe, []);
        Cpt = new CptGridViewModel(node, EditorFrom(definition.Cpt), bayesianGateway, localization);
        Cpt.LocalEditChanged += (_, _) => MarkLocalEdit(NodeEditorEditPersistence.ExplicitCommit);
        Cpt.CanonicalNodeCommitted += OnCptCanonicalNodeCommitted;
        ApplyCanonical(node, schemeId, sessionRevisionId);
        RefreshLanguage();
    }

    public ObservableCollection<OperatorOptionItem> OperatorOptions { get; } = [];

    public ObservableCollection<RecipeNodeDisplayItem> RecipeNodes { get; } = [];

    public ObservableCollection<RecipeEdgeDisplayItem> RecipeEdges { get; } = [];

    public ObservableCollection<ObservationStateEditItem> ObservationStates { get; } = [];

    public ObservableCollection<string> RawBindings { get; } = [];

    public ObservableCollection<string> OutputBindings { get; } = [];

    public ObservableCollection<string> UsedBySchemes { get; } = [];

    public ObservableCollection<string> HistoryItems { get; } = [];

    public CptGridViewModel Cpt { get; }

    public IReadOnlyList<ObservationPolicy> ObservationPolicies { get; } =
        Enum.GetValues<ObservationPolicy>();

    public string ProbabilisticParentsText
    {
        get
        {
            var definition = (EvidenceNodeDefinition)_canonicalNode.Definition;
            return definition.OrderedProbabilisticParentNodes.Length == 0
                ? L("Evidence_NoProbabilisticParents", "No probabilistic parents")
                : string.Join(Environment.NewLine, definition.OrderedProbabilisticParentNodes
                    .Select(parent => $"{parent.NodeKind}: {parent.NodeId}"));
        }
    }

    public string CptSummary
    {
        get
        {
            var cpt = ((EvidenceNodeDefinition)_canonicalNode.Definition).Cpt;
            return F(
                "Evidence_CptSummary",
                "{0} · {1} rows · {2} observation states",
                cpt.Mode,
                cpt.MaterializedProbabilities.Length,
                cpt.ChildStateIds.Length);
        }
    }

    public event EventHandler<NodeEditorLocalEditEventArgs>? LocalEditChanged;

    public event EventHandler<CanonicalNodeCommittedEventArgs>? CanonicalNodeCommitted;

    public async Task InitializeAsync(CancellationToken cancellationToken = default)
    {
        if (IsBusy)
        {
            return;
        }

        IsBusy = true;
        try
        {
            var operatorsTask = _coordinator.ListOperatorsAsync(cancellationToken);
            var usagesTask = _coordinator.ListUsagesAsync(_canonicalNode.NodeId, cancellationToken);
            var historyTask = _coordinator.ListHistoryAsync(_canonicalNode.NodeId, cancellationToken);
            var graphTask = _bayesianGateway.GetGraphAsync(_schemeId, cancellationToken);
            var cptTask = _bayesianGateway.InspectCptAsync(_canonicalNode.NodeId, cancellationToken);
            await Task.WhenAll(operatorsTask, usagesTask, historyTask, graphTask, cptTask);

            var operators = await operatorsTask;
            _recipeModel = new EvidenceRecipeEditorModel(
                ((EvidenceNodeDefinition)_canonicalNode.Definition).Recipe,
                operators);
            Replace(
                OperatorOptions,
                operators.Select(definition => new OperatorOptionItem(
                    definition.OperatorId,
                    definition.ImplementationVersion,
                    definition.Name,
                    definition.Family)));
            SelectedOperator = OperatorOptions.FirstOrDefault();
            _usages = await usagesTask;
            _history = await historyTask;
            RefreshUsageAndHistory();
            RefreshRecipeCollections();
            _graph = await graphTask;
            Cpt.ApplyCanonical(_canonicalNode, (await cptTask).Editor);
            SetStatus(
                "Evidence_StatusLoaded",
                "Loaded {0} trusted operators, {1} task usages and {2} history events.",
                OperatorOptions.Count,
                UsedBySchemes.Count,
                HistoryItems.Count);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception error)
        {
            SetStatus(
                "Evidence_StatusLoadFailed",
                "Editor metadata could not be loaded: {0}",
                error.Message);
        }
        finally
        {
            IsBusy = false;
        }
    }

    public void ApplyCanonical(
        ModelNode node,
        string schemeId,
        string? sessionRevisionId)
    {
        ArgumentNullException.ThrowIfNull(node);
        var definition = node.Definition as EvidenceNodeDefinition
            ?? throw new ArgumentException("Evidence editor requires an Evidence node.");
        _canonicalNode = node;
        _schemeId = schemeId;
        _sessionRevisionId = sessionRevisionId;
        var catalog = _recipeModel.Operators;
        _recipeModel = new EvidenceRecipeEditorModel(definition.Recipe, catalog);
        Name = node.Name;
        Description = node.Description;
        Group = node.Group ?? string.Empty;
        TagsText = string.Join(", ", node.Tags);
        AnchorName = definition.Recipe.Anchor.Name;
        AnchorDescription = definition.Recipe.Anchor.Description;
        RecipeSummary = definition.Recipe.Documentation.Summary;
        ScoringJson = definition.Recipe.Scoring is null
            ? string.Empty
            : JsonSerializer.Serialize(definition.Recipe.Scoring, ContractJsonOptions);
        ObservationMappingJson = JsonSerializer.Serialize(
            definition.ObservationMapping,
            ContractJsonOptions);
        ModalityWeightsJson = JsonSerializer.Serialize(
            definition.ModalityAttributionWeights,
            ContractJsonOptions);
        ObservationPolicy = definition.ObservationPolicy;
        HelpText = definition.HelpText;
        Replace(ObservationStates, definition.OrderedObservationStates.Select(state =>
            new ObservationStateEditItem(state)));
        Replace(RawBindings, definition.DataBindings.Select(binding =>
            $"{binding.RecipeInputBindingId} ← {binding.RawInputNode.NodeId}"));
        Replace(OutputBindings, definition.Recipe.Outputs.Select(output =>
            $"{output.Role}: {output.Name} ← {output.Source.NodeId}.{output.Source.PortId}"));
        Cpt.ApplyCanonical(node, EditorFrom(definition.Cpt));
        RefreshRecipeCollections();
        OnPropertyChanged(nameof(ProbabilisticParentsText));
        OnPropertyChanged(nameof(CptSummary));
    }

    public void ApplyDraftIntent(ModelNode draft)
    {
        var canonical = _canonicalNode;
        ApplyCanonical(draft, _schemeId, _sessionRevisionId);
        _canonicalNode = canonical;
    }

    public void AcceptCanonicalBase(ModelNode canonical)
    {
        _ = canonical.Definition as EvidenceNodeDefinition
            ?? throw new ArgumentException("Evidence editor requires an Evidence node.");
        _canonicalNode = canonical;
        OnPropertyChanged(nameof(ProbabilisticParentsText));
        OnPropertyChanged(nameof(CptSummary));
    }

    public void MarkLocalEdit(
        NodeEditorEditPersistence persistence = NodeEditorEditPersistence.Autosave) =>
        LocalEditChanged?.Invoke(this, new NodeEditorLocalEditEventArgs(persistence));

    public void SetOperationError(string message) =>
        SetStatus("Evidence_StatusBlocked", "Evidence operation blocked: {0}", message);

    public void SelectRecipeNodeForEditing(RecipeNodeDisplayItem? item)
    {
        SelectedRecipeNode = item;
        ParameterForm = item is null || item.IsMissing
            ? null
            : _recipeModel.CreateParameterForm(item.NodeId);
    }

    public void ApplyParameterForm()
    {
        if (SelectedRecipeNode is null || ParameterForm is null)
        {
            return;
        }
        _recipeModel.ApplyParameters(SelectedRecipeNode.NodeId, ParameterForm);
        RefreshRecipeCollections(SelectedRecipeNode.NodeId);
        MarkLocalEdit(NodeEditorEditPersistence.ExplicitCommit);
    }

    public void AddSelectedOperator()
    {
        if (SelectedOperator is null)
        {
            return;
        }
        var node = _recipeModel.AddOperator(
            SelectedOperator.OperatorId,
            SelectedOperator.ImplementationVersion);
        RefreshRecipeCollections(node.NodeId);
        MarkLocalEdit(NodeEditorEditPersistence.ExplicitCommit);
    }

    public void RemoveSelectedOperator()
    {
        if (SelectedRecipeNode is null)
        {
            return;
        }
        _recipeModel.RemoveOperator(SelectedRecipeNode.NodeId);
        RefreshRecipeCollections();
        MarkLocalEdit();
    }

    public void AddEdge(
        string sourceNodeId,
        string sourcePortId,
        string targetNodeId,
        string targetPortId,
        string? targetSlotId)
    {
        _recipeModel.Connect(
            sourceNodeId.Trim(),
            sourcePortId.Trim(),
            targetNodeId.Trim(),
            targetPortId.Trim(),
            Normalize(targetSlotId));
        RefreshRecipeCollections(SelectedRecipeNode?.NodeId);
        MarkLocalEdit();
    }

    public void RemoveEdge(RecipeEdgeDisplayItem edge)
    {
        ArgumentNullException.ThrowIfNull(edge);
        _recipeModel.RemoveEdge(edge.EdgeId);
        RefreshRecipeCollections(SelectedRecipeNode?.NodeId);
        MarkLocalEdit();
    }

    public void AddObservationState()
    {
        var used = ObservationStates.Select(item => item.StateId).ToHashSet(StringComparer.Ordinal);
        var index = 1;
        while (used.Contains($"state_{index}"))
        {
            index++;
        }
        ObservationStates.Add(new ObservationStateEditItem(
            new VariableState($"state_{index}", $"State {index}", "Expert-defined observation state.")));
        MarkLocalEdit();
    }

    public void RemoveObservationState(ObservationStateEditItem state)
    {
        ArgumentNullException.ThrowIfNull(state);
        ObservationStates.Remove(state);
        MarkLocalEdit();
    }

    public async Task CommitObservationStatesAsync(CancellationToken cancellationToken = default)
    {
        var localIntent = BuildUpdatedNode();
        var states = ObservationStates.Select(item => item.Build()).ToArray();
        if (states.Length < 2 || states.Any(state => string.IsNullOrWhiteSpace(state.StateId)) ||
            states.Select(state => state.StateId).Distinct(StringComparer.Ordinal).Count() != states.Length)
        {
            throw new InvalidOperationException("Evidence observation states require at least two unique, non-empty state IDs.");
        }
        var graph = _graph ?? await _bayesianGateway.GetGraphAsync(_schemeId, cancellationToken);
        var response = await _bayesianGateway.ReplaceNodeStatesAsync(
            _canonicalNode.NodeId,
            states,
            BnNodeEditorViewModel.StateChangeRevisionPlan(graph, _canonicalNode.NodeId),
            "expert.desktop",
            cancellationToken);
        var canonical = response.Nodes.Single(node => node.NodeId == _canonicalNode.NodeId);
        _graph = graph with
        {
            Nodes = graph.Nodes.Select(node =>
                response.Nodes.FirstOrDefault(changed => changed.NodeId == node.NodeId) ?? node).ToArray(),
        };
        ApplyCanonical(canonical, _schemeId, _sessionRevisionId);
        ApplyDraftIntent(ModelNodeDraftRebaser.Rebase(localIntent, canonical));
        SetStatus(
            "Evidence_StatusStatesSaved",
            "Canonical observation states saved; {0} affected CPT definition(s) are explicitly incomplete and repairable.",
            response.Nodes.Length);
        CanonicalNodeCommitted?.Invoke(this, new CanonicalNodeCommittedEventArgs(canonical));
    }

    public ModelNode BuildUpdatedNode()
    {
        var definition = (EvidenceNodeDefinition)_canonicalNode.Definition;
        var scoring = string.IsNullOrWhiteSpace(ScoringJson)
            ? null
            : JsonSerializer.Deserialize<RecipeScoring>(ScoringJson, ContractJsonOptions)
                ?? throw new JsonException("Evidence scoring JSON was empty.");
        var recipe = _recipeModel.Recipe with
        {
            Anchor = _recipeModel.Recipe.Anchor with
            {
                Name = AnchorName.Trim(),
                Description = AnchorDescription.Trim(),
            },
            Scoring = scoring,
            Documentation = _recipeModel.Recipe.Documentation with
            {
                Summary = RecipeSummary.Trim(),
            },
        };
        var mapped = _recipeModel.BuildUpdatedNode(
            _canonicalNode,
            Name,
            Description,
            Group,
            SplitValues(TagsText));
        return mapped with
        {
            Definition = definition with
            {
                Recipe = recipe,
                ObservationMapping = ParseJsonElementDictionary(ObservationMappingJson),
                ObservationPolicy = ObservationPolicy,
                ModalityAttributionWeights = ParseDoubleDictionary(ModalityWeightsJson),
                HelpText = Require(HelpText, "Evidence help text"),
            },
        };
    }

    public async Task PreviewAsync(CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(_sessionRevisionId))
        {
            SetPreview(
                "Evidence_PreviewSelectSession",
                "Select a managed session revision before requesting a preview.");
            return;
        }

        IsPreviewBusy = true;
        SetPreview(
            "Evidence_PreviewRequesting",
            "Requesting a backend-frozen node preview snapshot…");
        try
        {
            var snapshot = await _coordinator.PreviewAsync(
                _sessionRevisionId,
                _schemeId,
                _canonicalNode.NodeId,
                cancellationToken);
            if (snapshot is null)
            {
                SetPreview("Evidence_PreviewCancelled", "Preview cancelled.");
            }
            else
            {
                SetPreview(
                    "Evidence_PreviewSnapshot",
                    "Snapshot {0}\nHash: {1}\nLocked active nodes: {2}\nLocked operator identities: {3}\nThe current backend method freezes the exact preview inputs; Task 14 executes and renders result artifacts.",
                    snapshot.RunId,
                    snapshot.SnapshotHash,
                    snapshot.ActiveNodes.Length,
                    snapshot.LockedOperatorIdentities.Length);
            }
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception error)
        {
            SetPreview("Evidence_PreviewBlocked", "Preview blocked: {0}", error.Message);
        }
        finally
        {
            IsPreviewBusy = false;
        }
    }

    public void CancelPreview() => _coordinator.CancelPreview();

    public void Dispose() => _coordinator.Dispose();

    public void RefreshLanguage()
    {
        StatusMessage = F(_statusKey, _statusFallback, _statusArguments);
        PreviewSummary = F(_previewKey, _previewFallback, _previewArguments);
        RefreshUsageAndHistory();
        RefreshRecipeCollections(SelectedRecipeNode?.NodeId);
        Cpt.RefreshLanguage();
        OnPropertyChanged(nameof(ProbabilisticParentsText));
        OnPropertyChanged(nameof(CptSummary));
    }

    private void OnCptCanonicalNodeCommitted(object? sender, CanonicalNodeCommittedEventArgs args)
    {
        _canonicalNode = args.Node;
        OnPropertyChanged(nameof(ProbabilisticParentsText));
        OnPropertyChanged(nameof(CptSummary));
        CanonicalNodeCommitted?.Invoke(this, args);
    }

    private void RefreshRecipeCollections(string? preferredNodeId = null)
    {
        var operators = _recipeModel.Operators.ToDictionary(
            definition => $"{definition.OperatorId}\u001f{definition.ImplementationVersion}",
            StringComparer.Ordinal);
        Replace(RecipeNodes, _recipeModel.Recipe.Graph.Nodes.Select(node =>
        {
            var found = operators.TryGetValue(
                $"{node.OperatorId}\u001f{node.OperatorVersion}",
                out var definition);
            return new RecipeNodeDisplayItem(
                node.NodeId,
                node.OperatorId,
                node.OperatorVersion,
                found ? definition!.Name : F("Evidence_MissingOperator", "Missing: {0}", node.OperatorId),
                !found,
                node.Parameters.Count == 0
                    ? L("Evidence_NoParameters", "No parameters")
                    : string.Join(", ", node.Parameters.Keys.OrderBy(item => item, StringComparer.Ordinal)));
        }));
        Replace(RecipeEdges, _recipeModel.Recipe.Graph.Edges.Select(edge =>
            new RecipeEdgeDisplayItem(
                edge.EdgeId,
                edge.Source.NodeId,
                edge.Source.PortId,
                edge.Target.NodeId,
                edge.Target.PortId,
                edge.TargetSlotId)));
        var missing = _recipeModel.MissingOperators;
        HasMissingOperators = missing.Count > 0;
        MissingOperatorsText = missing.Count == 0
            ? L("Evidence_AllOperatorsInstalled", "All recipe operators are installed.")
            : F(
                "Evidence_MissingOperators",
                "Technical run blocker: {0}",
                string.Join(", ", missing.Select(item => $"{item.OperatorId}@{item.OperatorVersion}")));
        var selected = RecipeNodes.FirstOrDefault(item => item.NodeId == preferredNodeId)
            ?? RecipeNodes.FirstOrDefault(item => item.NodeId == SelectedRecipeNode?.NodeId);
        SelectRecipeNodeForEditing(selected);
    }

    private void RefreshUsageAndHistory()
    {
        Replace(UsedBySchemes, _usages.Select(usage =>
            $"{usage.SchemeId} · " +
            (usage.ExplicitlyActive
                ? L("Editor_UsageExplicit", "explicit")
                : L("Editor_UsageParentClosure", "parent closure")) +
            (usage.SelectedAsOutput ? L("Editor_UsageOutputSuffix", " · output") : string.Empty)));
        Replace(HistoryItems, _history
            .OrderByDescending(item => item.OccurredAt)
            .Select(item => F(
                "Editor_HistoryLine",
                "{0:yyyy-MM-dd HH:mm:ss} · {1} · semantic {2}, layout {3}",
                item.OccurredAt,
                item.EventKind,
                item.SemanticRevision,
                item.LayoutRevision)));
    }

    private void SetStatus(string key, string fallback, params object?[] arguments)
    {
        _statusKey = key;
        _statusFallback = fallback;
        _statusArguments = arguments;
        StatusMessage = F(key, fallback, arguments);
    }

    private void SetPreview(string key, string fallback, params object?[] arguments)
    {
        _previewKey = key;
        _previewFallback = fallback;
        _previewArguments = arguments;
        PreviewSummary = F(key, fallback, arguments);
    }

    private string L(string key, string fallback) => _localization?[key] ?? fallback;

    private string F(string key, string fallback, params object?[] arguments) =>
        _localization?.Format(key, arguments)
        ?? string.Format(System.Globalization.CultureInfo.CurrentCulture, fallback, arguments);

    private static IReadOnlyDictionary<string, JsonElement> ParseJsonElementDictionary(string json) =>
        JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(json, ContractJsonOptions)
        ?? throw new JsonException("Expected a JSON object.");

    private static IReadOnlyDictionary<string, double> ParseDoubleDictionary(string json) =>
        JsonSerializer.Deserialize<Dictionary<string, double>>(json, ContractJsonOptions)
        ?? throw new JsonException("Expected a numeric JSON object.");

    private static string[] SplitValues(string value) => value
        .Split([',', ';', '\r', '\n'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
        .Distinct(StringComparer.Ordinal)
        .OrderBy(item => item, StringComparer.Ordinal)
        .ToArray();

    private static string? Normalize(string? value) =>
        string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static string Require(string value, string label) =>
        Normalize(value) ?? throw new InvalidOperationException($"{label} must not be blank.");

    private static CptEditorState EditorFrom(NodeCpt cpt)
    {
        var rows = cpt.OrderedParentStateIds.Length == 0
            ? 1
            : cpt.OrderedParentStateIds.Aggregate(1, (count, states) => checked(count * states.Length));
        return new CptEditorState(
            cpt.ChildNode,
            cpt.OrderedParentNodes,
            cpt.ChildStateIds,
            cpt.OrderedParentStateIds,
            cpt.MaterializedProbabilities,
            cpt.Mode,
            rows,
            checked(rows * cpt.ChildStateIds.Length));
    }

    private static void Replace<T>(ObservableCollection<T> target, IEnumerable<T> values)
    {
        target.Clear();
        foreach (var value in values)
        {
            target.Add(value);
        }
    }
}
