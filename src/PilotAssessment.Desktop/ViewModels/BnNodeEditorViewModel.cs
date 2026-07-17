using System.Collections.ObjectModel;
using System.Globalization;
using System.Text.Json;
using System.Text.Json.Serialization;

using CommunityToolkit.Mvvm.ComponentModel;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;
using PilotAssessment.Desktop.Core.ViewModels;

namespace PilotAssessment.Desktop.ViewModels;

public sealed class CanonicalNodeCommittedEventArgs(ModelNode node) : EventArgs
{
    public ModelNode Node { get; } = node;
}

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
    public string Label => $"{DisplayName} · {NodeId}";
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
    private ModelNode _canonicalNode;
    private CptGridModel _grid;

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
        IBayesianNodeEditorGateway gateway)
    {
        _canonicalNode = node;
        _grid = new CptGridModel(editor);
        _gateway = gateway;
        RefreshRows();
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
        StatusMessage = $"Normalized row {row.RowIndex}. Save the CPT rows to commit this change.";
        LocalEditChanged?.Invoke(this, EventArgs.Empty);
    }

    public void ApplyPaste(string text)
    {
        PullCellsIntoGrid();
        var result = _grid.ApplyRectangularText(PasteStartRow, PasteStartColumn, text);
        RefreshRows();
        StatusMessage = $"Pasted a {result.RowCount} × {result.ColumnCount} probability block.";
        LocalEditChanged?.Invoke(this, EventArgs.Empty);
    }

    public async Task SaveRowsAsync(CancellationToken cancellationToken = default)
    {
        PullCellsIntoGrid();
        var rows = _grid.BuildBackendRows();
        IsBusy = true;
        StatusMessage = "Saving the complete CPT row batch through the Python backend…";
        try
        {
            var response = await _gateway.UpdateCptRowsAsync(
                _canonicalNode.NodeId,
                rows,
                _canonicalNode.SemanticRevision,
                "expert.desktop",
                cancellationToken);
            ApplyCanonical(response.Node, response.Editor);
            StatusMessage = "Canonical CPT rows saved and reconciled.";
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
        StatusMessage = $"Requesting {MaterializationStrategy} CPT materialization from Python…";
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
            StatusMessage = $"Canonical {response.Editor.Mode} CPT materialized and reconciled.";
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
        ModeSummary = $"{_grid.Editor.Mode} · {_grid.RowCount} rows · {_grid.ColumnCount} child states · " +
            $"{_grid.Editor.RequiredCellCount} required cells";
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
            ? $"Local grid is technically valid: {validation.RowCount} rows / {validation.CellCount} cells."
            : $"Local grid has {validation.Diagnostics.Count} technical issue(s): {validation.Diagnostics[0].Message}";
    }

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
    private ModelNode _canonicalNode;
    private ModelGraphSnapshot? _graph;
    private string _schemeId;

    [ObservableProperty]
    public partial string NameZh { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string NameEn { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string DescriptionZh { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string DescriptionEn { get; set; } = string.Empty;

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
    public partial string HelpTextZh { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string HelpTextEn { get; set; } = string.Empty;

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
        IBayesianNodeEditorGateway bayesianGateway)
    {
        _canonicalNode = node;
        _schemeId = schemeId;
        _nodeGateway = nodeGateway;
        _bayesianGateway = bayesianGateway;
        var definition = node.Definition as BnNodeDefinition
            ?? throw new ArgumentException("BN editor requires a BN node.");
        Cpt = new CptGridViewModel(node, EditorFrom(definition.Cpt), bayesianGateway);
        Cpt.LocalEditChanged += OnCptLocalEditChanged;
        Cpt.CanonicalNodeCommitted += OnCptCanonicalNodeCommitted;
        ApplyCanonical(node, schemeId);
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

    public string PosteriorSummary =>
        "The canonical arrows show P(child | fixed parents). Posterior/influence is a read-only run result overlay and does not reverse or rewrite these edges. Task 14 displays executed posterior and influence artifacts.";

    public event EventHandler? LocalEditChanged;

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
            Replace(UsedBySchemes, (await usagesTask).Select(usage =>
                $"{usage.SchemeId} · {(usage.ExplicitlyActive ? "explicit" : "parent closure")}" +
                (usage.SelectedAsOutput ? " · output" : string.Empty)));
            Replace(HistoryItems, (await historyTask)
                .OrderByDescending(item => item.OccurredAt)
                .Select(item => $"{item.OccurredAt:yyyy-MM-dd HH:mm:ss} · {item.EventKind} · semantic {item.SemanticRevision}"));
            StatusMessage =
                $"Loaded {Parents.Count} fixed parents, {Children.Count} children, {UsedBySchemes.Count} task usages and {HistoryItems.Count} history events.";
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
        NameZh = node.NameZh ?? string.Empty;
        NameEn = node.NameEn ?? string.Empty;
        DescriptionZh = node.DescriptionZh ?? string.Empty;
        DescriptionEn = node.DescriptionEn ?? string.Empty;
        Group = node.Group ?? string.Empty;
        TagsText = string.Join(", ", node.Tags);
        NodeRole = definition.NodeRole;
        ScientificStatus = definition.ScientificStatus;
        Documentation = definition.Documentation;
        ReportingMetadataJson = JsonSerializer.Serialize(
            definition.ReportingMetadata,
            ContractJsonOptions);
        HelpTextZh = definition.HelpTextZh ?? string.Empty;
        HelpTextEn = definition.HelpTextEn ?? string.Empty;
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

    public ModelNode BuildUpdatedNode()
    {
        var definition = (BnNodeDefinition)_canonicalNode.Definition;
        return _canonicalNode with
        {
            NameZh = Normalize(NameZh),
            NameEn = Normalize(NameEn),
            DescriptionZh = Normalize(DescriptionZh),
            DescriptionEn = Normalize(DescriptionEn),
            Group = Normalize(Group),
            Tags = SplitValues(TagsText),
            Definition = definition with
            {
                NodeRole = NodeRole,
                Documentation = Documentation.Trim(),
                ScientificStatus = ScientificStatus,
                ReportingMetadata = ParseJsonDictionary(ReportingMetadataJson),
                HelpTextZh = Normalize(HelpTextZh),
                HelpTextEn = Normalize(HelpTextEn),
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
        LocalEditChanged?.Invoke(this, EventArgs.Empty);
    }

    public void RemoveState(BnStateEditItem state)
    {
        ArgumentNullException.ThrowIfNull(state);
        States.Remove(state);
        LocalEditChanged?.Invoke(this, EventArgs.Empty);
    }

    public async Task CommitStatesAsync(CancellationToken cancellationToken = default)
    {
        var states = States.Select(item => item.Build()).ToArray();
        ValidateStates(states);
        var graph = _graph ?? await _bayesianGateway.GetGraphAsync(_schemeId, cancellationToken);
        var revisions = StateChangeRevisionPlan(graph, _canonicalNode.NodeId);
        IsBusy = true;
        StatusMessage = "Replacing states and atomically marking every affected CPT incomplete…";
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
            RefreshRelationships(_graph);
            StatusMessage =
                $"Canonical states saved; {response.Nodes.Length} node CPT definition(s) are now explicitly incomplete and repairable.";
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
            "Canonical parent order and CPT axes reordered atomically.",
            cancellationToken);
    }

    public void MarkLocalEdit() => LocalEditChanged?.Invoke(this, EventArgs.Empty);

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
        string successMessage,
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
            StatusMessage = successMessage;
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
                ? $"{DisplayName(child)} · {child.NodeId}"
                : edge.Child.NodeId));
        SelectedParent = Parents.FirstOrDefault();
        SelectedParentCandidate = ParentCandidates.FirstOrDefault();
    }

    private void OnCptLocalEditChanged(object? sender, EventArgs args) =>
        LocalEditChanged?.Invoke(this, EventArgs.Empty);

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

    private static BnNodeOptionItem Option(ModelNode? node, ModelNodeRef reference) =>
        new(reference.NodeId, reference.NodeKind, node is null ? reference.NodeId : DisplayName(node));

    private static string DisplayName(ModelNode node) =>
        node.NameEn ?? node.NameZh ?? node.ShortNameEn ?? node.ShortNameZh ?? node.NodeId;

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

    private static void Replace<T>(ObservableCollection<T> target, IEnumerable<T> values)
    {
        target.Clear();
        foreach (var value in values)
        {
            target.Add(value);
        }
    }
}
