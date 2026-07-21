using System.Collections.ObjectModel;
using System.Globalization;
using System.Text.Json;
using System.Text.Json.Serialization;

using CommunityToolkit.Mvvm.ComponentModel;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;
using PilotAssessment.Desktop.Core.ViewModels;

namespace PilotAssessment.Desktop.ViewModels;

public sealed partial class BnStateEditItem : ObservableObject
{
    public BnStateEditItem(VariableState state)
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

public sealed record BnNodeOptionItem(string NodeId, ModelNodeKind NodeKind, string DisplayName)
{
    public string Label => DisplayName;
}

public sealed record CptColumnHeaderItem(int ColumnIndex, string StateId);

public sealed partial class CptCellEditItem : ObservableObject
{
    public CptCellEditItem(int rowIndex, int columnIndex, string stateId, double? value)
    {
        RowIndex = rowIndex;
        ColumnIndex = columnIndex;
        StateId = stateId;
        ValueText = value?.ToString("G17", CultureInfo.InvariantCulture) ?? string.Empty;
    }

    public int RowIndex { get; }

    public int ColumnIndex { get; }

    public string StateId { get; }

    [ObservableProperty]
    public partial string ValueText { get; set; }
}

public sealed partial class CptRowEditItem : ObservableObject
{
    public CptRowEditItem(
        int rowIndex,
        string assignmentLabel,
        IEnumerable<CptCellEditItem> cells)
    {
        RowIndex = rowIndex;
        AssignmentLabel = assignmentLabel;
        foreach (var cell in cells)
        {
            Cells.Add(cell);
        }
    }

    public int RowIndex { get; }

    public string AssignmentLabel { get; }

    public ObservableCollection<CptCellEditItem> Cells { get; } = [];

    [ObservableProperty]
    public partial string RowStatus { get; set; } = string.Empty;
}

public sealed partial class CptGridViewModel : ObservableObject
{
    private readonly IBayesianNodeEditorGateway _gateway;
    private readonly ILocalizationLookup? _localization;
    private ModelNode _canonicalNode;
    private CptGridModel _grid;
    private string _statusKey = "Cpt_StatusLoaded";
    private string _statusFallback = "CPT loaded from the canonical backend node.";
    private object?[] _statusArguments = [];

    [ObservableProperty]
    public partial string StatusMessage { get; private set; } = "CPT loaded from the canonical backend node.";

    [ObservableProperty]
    public partial string ValidationSummary { get; private set; } = string.Empty;

    [ObservableProperty]
    public partial string ModeSummary { get; private set; } = string.Empty;

    [ObservableProperty]
    public partial bool IsBusy { get; private set; }

    [ObservableProperty]
    public partial int PasteStartRow { get; set; }

    [ObservableProperty]
    public partial int PasteStartColumn { get; set; }

    [ObservableProperty]
    public partial string MaterializationStrategy { get; set; } = "uniform";

    [ObservableProperty]
    public partial string RankedWeightsText { get; set; } = string.Empty;

    [ObservableProperty]
    public partial double WeakestLinkStrength { get; set; }

    [ObservableProperty]
    public partial double Sigma { get; set; } = 0.8;

    public CptGridViewModel(
        ModelNode node,
        CptEditorState editor,
        IBayesianNodeEditorGateway gateway,
        ILocalizationLookup? localization = null)
    {
        _canonicalNode = node;
        _grid = new CptGridModel(editor);
        _gateway = gateway;
        _localization = localization;
        RefreshRows();
        RefreshLanguage();
    }

    public ObservableCollection<CptColumnHeaderItem> Columns { get; } = [];

    public ObservableCollection<CptRowEditItem> Rows { get; } = [];

    public IReadOnlyList<string> MaterializationStrategies { get; } = ["uniform", "ranked"];

    public event EventHandler? LocalEditChanged;

    public event EventHandler<CanonicalNodeCommittedEventArgs>? CanonicalNodeCommitted;

    public void MarkLocalEdit()
    {
        PullCellsIntoGrid();
        RefreshValidation();
        LocalEditChanged?.Invoke(this, EventArgs.Empty);
    }

    public void NormalizeRow(CptRowEditItem row)
    {
        ArgumentNullException.ThrowIfNull(row);
        PullCellsIntoGrid();
        _grid.NormalizeRow(row.RowIndex);
        RefreshRows();
        SetStatus(
            "Cpt_StatusNormalized",
            "Normalized row {0}. Save the CPT rows to commit this change.",
            row.RowIndex);
        LocalEditChanged?.Invoke(this, EventArgs.Empty);
    }

    public void ApplyPaste(string text)
    {
        PullCellsIntoGrid();
        var result = _grid.ApplyRectangularText(PasteStartRow, PasteStartColumn, text);
        RefreshRows();
        SetStatus(
            "Cpt_StatusPasted",
            "Pasted a {0} × {1} probability block.",
            result.RowCount,
            result.ColumnCount);
        LocalEditChanged?.Invoke(this, EventArgs.Empty);
    }

    public async Task SaveRowsAsync(CancellationToken cancellationToken = default)
    {
        PullCellsIntoGrid();
        var rows = _grid.BuildBackendRows();
        IsBusy = true;
        SetStatus(
            "Cpt_StatusSavingRows",
            "Saving the complete CPT row batch through the Python backend…");
        try
        {
            var response = await _gateway.UpdateCptRowsAsync(
                _canonicalNode.NodeId,
                rows,
                _canonicalNode.SemanticRevision,
                "expert.desktop",
                cancellationToken);
            ApplyCanonical(response.Node, response.Editor);
            SetStatus("Cpt_StatusRowsSaved", "Canonical CPT rows saved and reconciled.");
            CanonicalNodeCommitted?.Invoke(this, new CanonicalNodeCommittedEventArgs(response.Node));
        }
        finally
        {
            IsBusy = false;
        }
    }

    public async Task MaterializeAsync(CancellationToken cancellationToken = default)
    {
        var weights = ParseOptionalWeights(RankedWeightsText);
        IsBusy = true;
        SetStatus(
            "Cpt_StatusRequestingMaterialization",
            "Requesting {0} CPT materialization from Python…",
            MaterializationStrategy);
        try
        {
            var response = await _gateway.MaterializeCptAsync(
                _canonicalNode.NodeId,
                MaterializationStrategy,
                weights,
                WeakestLinkStrength,
                Sigma,
                _canonicalNode.SemanticRevision,
                "expert.desktop",
                cancellationToken);
            ApplyCanonical(response.Node, response.Editor);
            SetStatus(
                "Cpt_StatusMaterialized",
                "Canonical {0} CPT materialized and reconciled.",
                response.Editor.Mode);
            CanonicalNodeCommitted?.Invoke(this, new CanonicalNodeCommittedEventArgs(response.Node));
        }
        finally
        {
            IsBusy = false;
        }
    }

    public void ApplyCanonical(ModelNode node, CptEditorState editor)
    {
        _canonicalNode = node;
        _grid.ReplaceCanonical(editor);
        RefreshRows();
    }

    public void RefreshLanguage()
    {
        StatusMessage = F(_statusKey, _statusFallback, _statusArguments);
        RefreshSummaries();
    }

    private void PullCellsIntoGrid()
    {
        foreach (var row in Rows)
        {
            foreach (var cell in row.Cells)
            {
                _grid.SetCell(
                    cell.RowIndex,
                    cell.ColumnIndex,
                    double.TryParse(
                        cell.ValueText,
                        NumberStyles.Float,
                        CultureInfo.InvariantCulture,
                        out var value)
                        ? value
                        : null);
            }
        }
    }

    private void RefreshRows()
    {
        Columns.Clear();
        for (var column = 0; column < _grid.ColumnCount; column++)
        {
            Columns.Add(new CptColumnHeaderItem(column, _grid.ChildStateIds[column]));
        }

        Rows.Clear();
        for (var row = 0; row < _grid.RowCount; row++)
        {
            Rows.Add(new CptRowEditItem(
                row,
                _grid.ParentAssignmentLabel(row),
                Enumerable.Range(0, _grid.ColumnCount).Select(column =>
                    new CptCellEditItem(
                        row,
                        column,
                        _grid.ChildStateIds[column],
                        _grid.GetCell(row, column)))));
        }
        RefreshSummaries();
    }

    private void RefreshSummaries()
    {
        ModeSummary = F(
            "Cpt_ModeSummary",
            "{0} · {1} rows · {2} child states · {3} required cells",
            _grid.Editor.Mode,
            _grid.RowCount,
            _grid.ColumnCount,
            _grid.Editor.RequiredCellCount);
        RefreshValidation();
    }

    private void RefreshValidation()
    {
        var validation = _grid.Validate();
        var byRow = validation.Diagnostics
            .Where(item => item.RowIndex is not null)
            .GroupBy(item => item.RowIndex!.Value)
            .ToDictionary(group => group.Key, group => group.First().Message);
        foreach (var row in Rows)
        {
            row.RowStatus = byRow.GetValueOrDefault(row.RowIndex, "Σ = 1");
        }
        ValidationSummary = validation.IsValid
            ? F(
                "Cpt_ValidationValid",
                "Local grid is technically valid: {0} rows / {1} cells.",
                validation.RowCount,
                validation.CellCount)
            : F(
                "Cpt_ValidationInvalid",
                "Local grid has {0} technical issue(s): {1}",
                validation.Diagnostics.Count,
                validation.Diagnostics[0].Message);
    }

    private void SetStatus(string key, string fallback, params object?[] arguments)
    {
        _statusKey = key;
        _statusFallback = fallback;
        _statusArguments = arguments;
        StatusMessage = F(key, fallback, arguments);
    }

    private string F(string key, string fallback, params object?[] arguments) =>
        _localization?.Format(key, arguments)
        ?? string.Format(CultureInfo.CurrentCulture, fallback, arguments);

    private static double[]? ParseOptionalWeights(string text)
    {
        if (string.IsNullOrWhiteSpace(text))
        {
            return null;
        }
        return text
            .Split([',', ';', ' ', '\r', '\n'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Select(value => double.Parse(value, NumberStyles.Float, CultureInfo.InvariantCulture))
            .ToArray();
    }
}

public sealed partial class BnNodeEditorViewModel : ObservableObject
{
    private static readonly JsonSerializerOptions ContractJsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        WriteIndented = true,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) },
    };

    private readonly IModelNodeEditorGateway _nodeGateway;
    private readonly IBayesianNodeEditorGateway _bayesianGateway;
    private readonly ILocalizationLookup? _localization;
    private ModelNode _canonicalNode;
    private ModelGraphSnapshot? _graph;
    private string _schemeId;
    private IReadOnlyList<ModelNodeUsage> _usages = [];
    private IReadOnlyList<ModelChangeEvent> _history = [];
    private string _statusKey = "Bn_StatusLoading";
    private string _statusFallback = "Loading BN editor metadata…";
    private object?[] _statusArguments = [];

    [ObservableProperty]
    public partial string Name { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string Description { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string Group { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string TagsText { get; set; } = string.Empty;

    [ObservableProperty]
    public partial BnNodeRole NodeRole { get; set; }

    [ObservableProperty]
    public partial ModelScientificStatus ScientificStatus { get; set; }

    [ObservableProperty]
    public partial string Documentation { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string ReportingMetadataJson { get; set; } = "{}";

    [ObservableProperty]
    public partial string HelpText { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string StatusMessage { get; private set; } = "Loading BN editor metadata…";

    [ObservableProperty]
    public partial bool IsBusy { get; private set; }

    [ObservableProperty]
    public partial BnNodeOptionItem? SelectedParent { get; set; }

    [ObservableProperty]
    public partial BnNodeOptionItem? SelectedParentCandidate { get; set; }

    [ObservableProperty]
    public partial string AddParentStrategy { get; set; } = "preserve_independence";

    [ObservableProperty]
    public partial string RemoveParentStrategy { get; set; } = "incomplete";

    [ObservableProperty]
    public partial string MarginalWeightsText { get; set; } = string.Empty;

    public BnNodeEditorViewModel(
        ModelNode node,
        string schemeId,
        IModelNodeEditorGateway nodeGateway,
        IBayesianNodeEditorGateway bayesianGateway,
        ILocalizationLookup? localization = null)
    {
        _canonicalNode = node;
        _schemeId = schemeId;
        _nodeGateway = nodeGateway;
        _bayesianGateway = bayesianGateway;
        _localization = localization;
        var definition = node.Definition as BnNodeDefinition
            ?? throw new ArgumentException("BN editor requires a BN node.");
        Cpt = new CptGridViewModel(node, EditorFrom(definition.Cpt), bayesianGateway, localization);
        Cpt.LocalEditChanged += OnCptLocalEditChanged;
        Cpt.CanonicalNodeCommitted += OnCptCanonicalNodeCommitted;
        ApplyCanonical(node, schemeId);
        RefreshLanguage();
    }

    public CptGridViewModel Cpt { get; }

    public ObservableCollection<BnStateEditItem> States { get; } = [];

    public ObservableCollection<BnNodeOptionItem> Parents { get; } = [];

    public ObservableCollection<BnNodeOptionItem> ParentCandidates { get; } = [];

    public ObservableCollection<string> Children { get; } = [];

    public ObservableCollection<string> UsedBySchemes { get; } = [];

    public ObservableCollection<string> HistoryItems { get; } = [];

    public IReadOnlyList<BnNodeRole> NodeRoles { get; } = Enum.GetValues<BnNodeRole>();

    public IReadOnlyList<ModelScientificStatus> ScientificStatuses { get; } =
        Enum.GetValues<ModelScientificStatus>();

    public IReadOnlyList<string> AddParentStrategies { get; } =
        ["preserve_independence", "uniform", "incomplete"];

    public IReadOnlyList<string> RemoveParentStrategies { get; } = ["marginalize", "incomplete"];

    public string PosteriorSummary => L(
        "Bn_PosteriorSummary",
        "The canonical arrows show P(child | fixed parents). Posterior/influence is a read-only run result overlay and does not reverse or rewrite these edges. Task 14 displays executed posterior and influence artifacts.");

    public event EventHandler<NodeEditorLocalEditEventArgs>? LocalEditChanged;

    public event EventHandler<CanonicalNodeCommittedEventArgs>? CanonicalNodeCommitted;

    public async Task InitializeAsync(CancellationToken cancellationToken = default)
    {
        IsBusy = true;
        try
        {
            var graphTask = _bayesianGateway.GetGraphAsync(_schemeId, cancellationToken);
            var cptTask = _bayesianGateway.InspectCptAsync(_canonicalNode.NodeId, cancellationToken);
            var usagesTask = _nodeGateway.ListNodeUsagesAsync(_canonicalNode.NodeId, cancellationToken);
            var historyTask = _nodeGateway.ListNodeHistoryAsync(_canonicalNode.NodeId, cancellationToken);
            await Task.WhenAll(graphTask, cptTask, usagesTask, historyTask);

            _graph = await graphTask;
            RefreshRelationships(_graph);
            var inspection = await cptTask;
            Cpt.ApplyCanonical(_canonicalNode, inspection.Editor);
            _usages = await usagesTask;
            _history = await historyTask;
            RefreshUsageAndHistory();
            SetStatus(
                "Bn_StatusLoaded",
                "Loaded {0} fixed parents, {1} children, {2} task usages and {3} history events.",
                Parents.Count,
                Children.Count,
                UsedBySchemes.Count,
                HistoryItems.Count);
        }
        finally
        {
            IsBusy = false;
        }
    }

    public void ApplyCanonical(ModelNode node, string schemeId)
    {
        var definition = node.Definition as BnNodeDefinition
            ?? throw new ArgumentException("BN editor requires a BN node.");
        _canonicalNode = node;
        _schemeId = schemeId;
        Name = node.Name;
        Description = node.Description;
        Group = node.Group ?? string.Empty;
        TagsText = string.Join(", ", node.Tags);
        NodeRole = definition.NodeRole;
        ScientificStatus = definition.ScientificStatus;
        Documentation = definition.Documentation;
        ReportingMetadataJson = JsonSerializer.Serialize(
            definition.ReportingMetadata,
            ContractJsonOptions);
        HelpText = definition.HelpText;
        Replace(States, definition.OrderedStates.Select(state => new BnStateEditItem(state)));
        Cpt.ApplyCanonical(node, EditorFrom(definition.Cpt));
        if (_graph is not null)
        {
            RefreshRelationships(_graph with
            {
                Nodes = _graph.Nodes.Select(item => item.NodeId == node.NodeId ? node : item).ToArray(),
            });
        }
    }

    public void ApplyDraftIntent(ModelNode draft)
    {
        var canonical = _canonicalNode;
        var graph = _graph;
        ApplyCanonical(draft, _schemeId);
        _canonicalNode = canonical;
        if (graph is not null)
        {
            RefreshRelationships(graph with
            {
                Nodes = graph.Nodes.Select(node =>
                    node.NodeId == canonical.NodeId ? canonical : node).ToArray(),
            });
        }
    }

    public void AcceptCanonicalBase(ModelNode canonical)
    {
        _ = canonical.Definition as BnNodeDefinition
            ?? throw new ArgumentException("BN editor requires a BN node.");
        _canonicalNode = canonical;
        if (_graph is not null)
        {
            _graph = _graph with
            {
                Nodes = _graph.Nodes.Select(node =>
                    node.NodeId == canonical.NodeId ? canonical : node).ToArray(),
            };
        }
    }

    public ModelNode BuildUpdatedNode()
    {
        var definition = (BnNodeDefinition)_canonicalNode.Definition;
        var canonicalName = Require(Name, "BN node name");
        return _canonicalNode with
        {
            Name = canonicalName,
            ShortName = Shorten(canonicalName),
            Description = Require(Description, "BN node description"),
            Group = Normalize(Group),
            Tags = SplitValues(TagsText),
            Definition = definition with
            {
                NodeRole = NodeRole,
                Documentation = Documentation.Trim(),
                ScientificStatus = ScientificStatus,
                ReportingMetadata = ParseJsonDictionary(ReportingMetadataJson),
                HelpText = Require(HelpText, "BN node help text"),
            },
        };
    }

    public void AddState()
    {
        var used = States.Select(item => item.StateId).ToHashSet(StringComparer.Ordinal);
        var index = 1;
        while (used.Contains($"state_{index}"))
        {
            index++;
        }
        States.Add(new BnStateEditItem(new VariableState(
            $"state_{index}",
            $"State {index}",
            "Expert-defined BN state.")));
        LocalEditChanged?.Invoke(
            this,
            new NodeEditorLocalEditEventArgs(NodeEditorEditPersistence.ExplicitCommit));
    }

    public void RemoveState(BnStateEditItem state)
    {
        ArgumentNullException.ThrowIfNull(state);
        States.Remove(state);
        LocalEditChanged?.Invoke(
            this,
            new NodeEditorLocalEditEventArgs(NodeEditorEditPersistence.ExplicitCommit));
    }

    public async Task CommitStatesAsync(CancellationToken cancellationToken = default)
    {
        var localIntent = BuildUpdatedNode();
        var states = States.Select(item => item.Build()).ToArray();
        ValidateStates(states);
        var graph = _graph ?? await _bayesianGateway.GetGraphAsync(_schemeId, cancellationToken);
        var revisions = StateChangeRevisionPlan(graph, _canonicalNode.NodeId);
        IsBusy = true;
        SetStatus(
            "Bn_StatusReplacingStates",
            "Replacing states and atomically marking every affected CPT incomplete…");
        try
        {
            var response = await _bayesianGateway.ReplaceNodeStatesAsync(
                _canonicalNode.NodeId,
                states,
                revisions,
                "expert.desktop",
                cancellationToken);
            var canonical = response.Nodes.Single(node => node.NodeId == _canonicalNode.NodeId);
            _graph = graph with
            {
                Nodes = graph.Nodes.Select(node =>
                    response.Nodes.FirstOrDefault(changed => changed.NodeId == node.NodeId) ?? node).ToArray(),
            };
            ApplyCanonical(canonical, _schemeId);
            ApplyDraftIntent(ModelNodeDraftRebaser.Rebase(localIntent, canonical));
            RefreshRelationships(_graph);
            SetStatus(
                "Bn_StatusStatesSaved",
                "Canonical states saved; {0} node CPT definition(s) are now explicitly incomplete and repairable.",
                response.Nodes.Length);
            CanonicalNodeCommitted?.Invoke(this, new CanonicalNodeCommittedEventArgs(canonical));
        }
        finally
        {
            IsBusy = false;
        }
    }

    public async Task AddParentAsync(CancellationToken cancellationToken = default)
    {
        var parent = SelectedParentCandidate
            ?? throw new InvalidOperationException("Select a parent candidate first.");
        await ApplyCptMutationAsync(
            _bayesianGateway.AddProbabilisticEdgeAsync(
                _canonicalNode.NodeId,
                parent.NodeId,
                AddParentStrategy,
                _canonicalNode.SemanticRevision,
                "expert.desktop",
                cancellationToken),
            "Bn_StatusParentAdded",
            "Canonical parent added with atomic CPT migration.",
            cancellationToken);
    }

    public async Task RemoveParentAsync(CancellationToken cancellationToken = default)
    {
        var parent = SelectedParent
            ?? throw new InvalidOperationException("Select a fixed parent first.");
        await ApplyCptMutationAsync(
            _bayesianGateway.RemoveProbabilisticEdgeAsync(
                _canonicalNode.NodeId,
                parent.NodeId,
                RemoveParentStrategy,
                ParseOptionalWeights(MarginalWeightsText),
                _canonicalNode.SemanticRevision,
                "expert.desktop",
                cancellationToken),
            "Bn_StatusParentRemoved",
            "Canonical parent removed with atomic CPT migration.",
            cancellationToken);
    }

    public async Task MoveParentAsync(int offset, CancellationToken cancellationToken = default)
    {
        var parent = SelectedParent
            ?? throw new InvalidOperationException("Select a fixed parent first.");
        var ordered = Parents.Select(item => item.NodeId).ToList();
        var index = ordered.IndexOf(parent.NodeId);
        var target = index + offset;
        if (index < 0 || target < 0 || target >= ordered.Count)
        {
            return;
        }
        (ordered[index], ordered[target]) = (ordered[target], ordered[index]);
        await ApplyCptMutationAsync(
            _bayesianGateway.ReorderProbabilisticParentsAsync(
                _canonicalNode.NodeId,
                ordered,
                _canonicalNode.SemanticRevision,
                "expert.desktop",
                cancellationToken),
            "Bn_StatusParentsReordered",
            "Canonical parent order and CPT axes reordered atomically.",
            cancellationToken);
    }

    public void MarkLocalEdit(
        NodeEditorEditPersistence persistence = NodeEditorEditPersistence.Autosave) =>
        LocalEditChanged?.Invoke(this, new NodeEditorLocalEditEventArgs(persistence));

    public static IReadOnlyDictionary<string, int> StateChangeRevisionPlan(
        ModelGraphSnapshot graph,
        string changedNodeId)
    {
        var affected = graph.Nodes.Where(node =>
        {
            if (node.NodeId == changedNodeId)
            {
                return node.Definition is EvidenceNodeDefinition or BnNodeDefinition;
            }
            return node.Definition switch
            {
                EvidenceNodeDefinition evidence => evidence.Cpt.OrderedParentNodes.Any(parent => parent.NodeId == changedNodeId),
                BnNodeDefinition bn => bn.Cpt.OrderedParentNodes.Any(parent => parent.NodeId == changedNodeId),
                _ => false,
            };
        });
        return affected.ToDictionary(node => node.NodeId, node => node.SemanticRevision, StringComparer.Ordinal);
    }

    private async Task ApplyCptMutationAsync(
        Task<CptMutationResponse> mutation,
        string successKey,
        string successFallback,
        CancellationToken cancellationToken)
    {
        IsBusy = true;
        try
        {
            var response = await mutation;
            _canonicalNode = response.Node;
            Cpt.ApplyCanonical(response.Node, response.Editor);
            _graph = await _bayesianGateway.GetGraphAsync(_schemeId, cancellationToken);
            RefreshRelationships(_graph);
            SetStatus(successKey, successFallback);
            CanonicalNodeCommitted?.Invoke(this, new CanonicalNodeCommittedEventArgs(response.Node));
        }
        finally
        {
            IsBusy = false;
        }
    }

    private void RefreshRelationships(ModelGraphSnapshot graph)
    {
        _graph = graph;
        var definition = (BnNodeDefinition)_canonicalNode.Definition;
        var byId = graph.Nodes.ToDictionary(node => node.NodeId, StringComparer.Ordinal);
        Replace(Parents, definition.OrderedProbabilisticParentNodes.Select(parent =>
            Option(byId.GetValueOrDefault(parent.NodeId), parent)));
        Replace(ParentCandidates, graph.Nodes
            .Where(node => node.NodeKind is ModelNodeKind.Evidence or ModelNodeKind.Bn)
            .Where(node => node.NodeId != _canonicalNode.NodeId)
            .Where(node => definition.OrderedProbabilisticParentNodes.All(parent => parent.NodeId != node.NodeId))
            .OrderBy(DisplayName, StringComparer.Ordinal)
            .Select(node => new BnNodeOptionItem(node.NodeId, node.NodeKind, DisplayName(node))));
        Replace(Children, graph.Edges
            .Where(edge => edge.EdgeKind is ModelGraphEdgeKind.Probabilistic && edge.Parent.NodeId == _canonicalNode.NodeId)
            .Select(edge => byId.TryGetValue(edge.Child.NodeId, out var child)
                ? DisplayName(child)
                : ModelDisplayNameResolver.HumanizeIdentifier(edge.Child.NodeId, "Pilot Skill")));
        SelectedParent = Parents.FirstOrDefault();
        SelectedParentCandidate = ParentCandidates.FirstOrDefault();
    }

    public void RefreshLanguage()
    {
        StatusMessage = F(_statusKey, _statusFallback, _statusArguments);
        Cpt.RefreshLanguage();
        RefreshUsageAndHistory();
        OnPropertyChanged(nameof(PosteriorSummary));
        if (_graph is not null)
        {
            RefreshRelationships(_graph);
        }
    }

    private void OnCptLocalEditChanged(object? sender, EventArgs args) =>
        LocalEditChanged?.Invoke(
            this,
            new NodeEditorLocalEditEventArgs(NodeEditorEditPersistence.ExplicitCommit));

    private void OnCptCanonicalNodeCommitted(object? sender, CanonicalNodeCommittedEventArgs args)
    {
        _canonicalNode = args.Node;
        CanonicalNodeCommitted?.Invoke(this, args);
    }

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

    private static void ValidateStates(IReadOnlyList<VariableState> states)
    {
        if (states.Count < 2)
        {
            throw new InvalidOperationException("A Bayesian variable requires at least two states.");
        }
        if (states.Any(state => string.IsNullOrWhiteSpace(state.StateId)))
        {
            throw new InvalidOperationException("Every state requires a stable ID.");
        }
        if (states.Select(state => state.StateId).Distinct(StringComparer.Ordinal).Count() != states.Count)
        {
            throw new InvalidOperationException("State IDs must be unique.");
        }
    }

    private BnNodeOptionItem Option(ModelNode? node, ModelNodeRef reference) =>
        new(
            reference.NodeId,
            reference.NodeKind,
            node is null
                ? ModelDisplayNameResolver.HumanizeIdentifier(reference.NodeId, "Pilot Skill")
                : DisplayName(node));

    private static string DisplayName(ModelNode node) => ModelDisplayNameResolver.ForNode(node);

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

    private string L(string key, string fallback) => _localization?[key] ?? fallback;

    private string F(string key, string fallback, params object?[] arguments) =>
        _localization?.Format(key, arguments)
        ?? string.Format(CultureInfo.CurrentCulture, fallback, arguments);

    private static IReadOnlyDictionary<string, JsonElement> ParseJsonDictionary(string json) =>
        JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(json, ContractJsonOptions)
        ?? throw new JsonException("Expected a JSON object.");

    private static double[]? ParseOptionalWeights(string text)
    {
        if (string.IsNullOrWhiteSpace(text))
        {
            return null;
        }
        return text
            .Split([',', ';', ' ', '\r', '\n'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Select(value => double.Parse(value, NumberStyles.Float, CultureInfo.InvariantCulture))
            .ToArray();
    }

    private static string[] SplitValues(string value) => value
        .Split([',', ';', '\r', '\n'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
        .Distinct(StringComparer.Ordinal)
        .OrderBy(item => item, StringComparer.Ordinal)
        .ToArray();

    private static string? Normalize(string? value) =>
        string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static string Require(string value, string label) =>
        Normalize(value) ?? throw new InvalidOperationException($"{label} must not be blank.");

    private static string Shorten(string value) => value.Length <= 96 ? value : value[..96];

    private static void Replace<T>(ObservableCollection<T> target, IEnumerable<T> values)
    {
        target.Clear();
        foreach (var value in values)
        {
            target.Add(value);
        }
    }
}
