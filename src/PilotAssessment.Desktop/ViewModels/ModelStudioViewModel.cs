using System.Collections.ObjectModel;
using System.ComponentModel;

using CommunityToolkit.Mvvm.ComponentModel;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;
using PilotAssessment.Desktop.Core.ViewModels;

namespace PilotAssessment.Desktop.ViewModels;

public sealed partial class ModelStudioViewModel : ObservableObject
{
    public const string AllGroups = "All groups";

    private readonly ModelGraphCommandCoordinator _commands;
    private readonly TaskSchemeListViewModel _schemes;
    private readonly IModelEditSessionGateway _editSession;
    private readonly ApplicationShellState _shellState;
    private readonly ILocalizationLookup _localization;
    private readonly HashSet<string> _selectedNodeIds = new(StringComparer.Ordinal);
    private readonly Dictionary<string, NodeLayout> _pendingLayouts = new(StringComparer.Ordinal);
    private int _loadGeneration;
    private int _busyOperations;
    private ModelGraphSnapshot? _snapshot;
    private CancellationTokenSource? _layoutDebounce;
    private string _allGroupsLabel = AllGroups;
    private string _viewActiveOnlyLabel = "Active only";
    private string _viewActiveInactiveLabel = "Active + inactive";
    private string _viewAllLabel = "All global nodes";
    private string _layerAllLabel = "All layers";
    private string _layerRawFamilyLabel = "Raw Input Family";
    private string _layerExtractedDataLabel = "Extracted Data";
    private string _layerEvidenceLabel = "Evidence";
    private string _layerSubSkillLabel = "Sub-skill";
    private string _layerCompetencyLabel = "Competency";
    private string _activationAllLabel = "All activation states";
    private string _activationActiveLabel = "Active";
    private string _activationInactiveLabel = "Inactive";

    [ObservableProperty]
    public partial string SearchText { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string SelectedViewMode { get; set; } = "Active + inactive";

    [ObservableProperty]
    public partial string SelectedLayer { get; set; } = "All layers";

    [ObservableProperty]
    public partial string SelectedActivation { get; set; } = "All activation states";

    [ObservableProperty]
    public partial string SelectedGroup { get; set; } = AllGroups;

    [ObservableProperty]
    public partial bool IsMultiSelect { get; set; }

    [ObservableProperty]
    public partial bool IsBusy { get; private set; }

    [ObservableProperty]
    public partial bool HasError { get; private set; }

    [ObservableProperty]
    public partial string ErrorMessage { get; private set; } = string.Empty;

    [ObservableProperty]
    public partial string StatusMessage { get; private set; } =
        "Choose a task scheme to load the global model graph.";

    [ObservableProperty]
    public partial string SelectedNodeSummary { get; private set; } = "No node selected";

    [ObservableProperty]
    public partial double ExtentWidth { get; private set; } = GraphProjection.MinimumExtentWidth;

    [ObservableProperty]
    public partial double ExtentHeight { get; private set; } = GraphProjection.MinimumExtentHeight;

    [ObservableProperty]
    public partial int ProjectionVersion { get; private set; }

    public ModelStudioViewModel(
        ModelGraphCommandCoordinator commands,
        TaskSchemeListViewModel schemes,
        IModelEditSessionGateway editSession,
        ApplicationShellState shellState,
        ILocalizationLookup localization)
    {
        _commands = commands;
        _schemes = schemes;
        _editSession = editSession;
        _shellState = shellState;
        _localization = localization;
        RefreshLocalizedOptions();
        AvailableGroups.Add(_allGroupsLabel);
        SelectedGroup = _allGroupsLabel;
        SelectedViewMode = _viewActiveInactiveLabel;
        SelectedLayer = _layerAllLabel;
        SelectedActivation = _activationAllLabel;
        StatusMessage = L("Model_ChooseTaskScheme");
        SelectedNodeSummary = L("Model_NoNodeSelected");
        _schemes.PropertyChanged += OnSchemePropertyChanged;
        _localization.LanguageChanged += OnLanguageChanged;
    }

    public ObservableCollection<GraphNodeProjection> Nodes { get; } = [];

    public ObservableCollection<GraphEdgeProjection> Edges { get; } = [];

    public ObservableCollection<GraphRawInputFamilyProjection> RawInputFamilies { get; } = [];

    public ObservableCollection<GraphProvenanceEdgeProjection> ProvenanceEdges { get; } = [];

    public ObservableCollection<string> AvailableGroups { get; } = [];

    public ObservableCollection<string> ViewModes { get; } = [];

    public ObservableCollection<string> LayerOptions { get; } = [];

    public ObservableCollection<string> ActivationOptions { get; } = [];

    public string? CurrentSchemeId => _snapshot?.Scheme.SchemeId;

    public GraphNodeProjection? PrimarySelectedNode =>
        Nodes.FirstOrDefault(node => node.IsSelected);

    public IReadOnlyList<string> SelectedNodeIds =>
        _selectedNodeIds.OrderBy(nodeId => nodeId, StringComparer.Ordinal).ToArray();

    public bool CanPaste =>
        _commands.CanPaste(SystemModelContext.Key);

    public event EventHandler<ModelNodeOpenRequestedEventArgs>? NodeEditorRequested;

    public event EventHandler<CanonicalModelGraphChangedEventArgs>? CanonicalGraphChanged;

    public async Task ActivateAsync(CancellationToken cancellationToken = default)
    {
        var selected = _schemes.SelectedScheme;
        if (selected is null)
        {
            ClearGraph(L("Model_ChooseTaskScheme"));
            return;
        }

        if (_snapshot?.Scheme.SchemeId == selected.SchemeId && Nodes.Count > 0)
        {
            return;
        }

        await LoadGraphAsync(selected.SchemeId, cancellationToken);
    }

    public async Task LoadGraphAsync(
        string schemeId,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(schemeId);
        var generation = Interlocked.Increment(ref _loadGeneration);
        var projectId = SystemModelContext.Key;
        BeginBusy();
        ClearError();
        StatusMessage = F("Model_StatusLoading", schemeId);
        try
        {
            var graph = await _commands.GetGraphAsync(schemeId, cancellationToken);
            if (generation != Volatile.Read(ref _loadGeneration) ||
                !IsCurrentContext(projectId, schemeId))
            {
                return;
            }

            ApplyCanonicalGraph(
                graph,
                _selectedNodeIds,
                F(
                    "Model_GraphSummary",
                    graph.Nodes.Length,
                    graph.Edges.Length,
                    graph.Scheme.ComputedActiveClosure.Length,
                    DisplaySchemeName(graph.Scheme)));
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception error)
        {
            if (generation == Volatile.Read(ref _loadGeneration))
            {
                HasError = true;
                ErrorMessage = error.Message;
                StatusMessage = L("Model_StatusLoadFailed");
            }
        }
        finally
        {
            EndBusy();
        }
    }

    public void SelectNode(GraphNodeProjection node, bool forceAdditive = false)
    {
        ArgumentNullException.ThrowIfNull(node);
        if (IsMultiSelect || forceAdditive)
        {
            if (!_selectedNodeIds.Add(node.NodeId))
            {
                _selectedNodeIds.Remove(node.NodeId);
            }
        }
        else
        {
            _selectedNodeIds.Clear();
            _selectedNodeIds.Add(node.NodeId);
        }

        UpdateSelectionSummary();
        Reproject();
        NotifySelectionChanged();
    }

    public void ClearSelection()
    {
        _selectedNodeIds.Clear();
        UpdateSelectionSummary();
        Reproject();
        NotifySelectionChanged();
    }

    public async Task<ModelNode?> CreateNodeAsync(
        ModelNodeDraftRequest request,
        CancellationToken cancellationToken = default)
    {
        var snapshot = RequireSnapshot();
        var projectId = RequireProjectId();
        var schemeId = snapshot.Scheme.SchemeId;
        BeginBusy();
        ClearError();
        StatusMessage = L("Model_StatusCreatingNode");
        try
        {
            var created = await _commands.CreateNodeAsync(request, cancellationToken);
            if (!IsCurrentContext(projectId, schemeId))
            {
                return created.Node;
            }

            try
            {
                var activated = await _commands.ActivateNodeAsync(
                    snapshot.Scheme,
                    created.Node.NodeId,
                    cancellationToken);
                if (IsCurrentContext(projectId, schemeId))
                {
                    ApplyCanonicalGraph(
                        activated.Graph,
                        [created.Node.NodeId],
                        L("Model_StatusNodeCreatedActive"));
                    NodeEditorRequested?.Invoke(
                        this,
                        new ModelNodeOpenRequestedEventArgs(created.Node, schemeId));
                }
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch (Exception activationError)
            {
                if (IsCurrentContext(projectId, schemeId))
                {
                    var graph = await _commands.GetGraphAsync(schemeId, cancellationToken);
                    ApplyCanonicalGraph(
                        graph,
                        [created.Node.NodeId],
                        L("Model_StatusNodeSavedInactive"));
                    SetError(
                        activationError,
                        L("Model_StatusNodeActivationRepair"));
                    NodeEditorRequested?.Invoke(
                        this,
                        new ModelNodeOpenRequestedEventArgs(created.Node, schemeId));
                }
            }

            return created.Node;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception error)
        {
            if (IsCurrentContext(projectId, schemeId))
            {
                SetError(error, L("Model_StatusNodeCreateFailed"));
            }

            return null;
        }
        finally
        {
            EndBusy();
        }
    }

    public async Task<bool> ActivateNodeAsync(
        GraphNodeProjection node,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(node);
        if (node.IsActive)
        {
            StatusMessage = L("Model_StatusAlreadyActive");
            return true;
        }

        var snapshot = RequireSnapshot();
        var projectId = RequireProjectId();
        var schemeId = snapshot.Scheme.SchemeId;
        BeginBusy();
        ClearError();
        StatusMessage = L("Model_StatusActivating");
        try
        {
            var response = await _commands.ActivateNodeAsync(
                snapshot.Scheme,
                node.NodeId,
                cancellationToken);
            if (IsCurrentContext(projectId, schemeId))
            {
                ApplyCanonicalGraph(
                    response.Graph,
                    [node.NodeId],
                    L("Model_StatusActivated"));
            }

            return true;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception error)
        {
            if (IsCurrentContext(projectId, schemeId))
            {
                SetError(error, L("Model_StatusActivationFailed"));
            }

            return false;
        }
        finally
        {
            EndBusy();
        }
    }

    public async Task<DeactivationImpact?> PreviewDeactivationAsync(
        GraphNodeProjection node,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(node);
        if (!node.IsActive)
        {
            StatusMessage = L("Model_StatusAlreadyInactive");
            return null;
        }

        var snapshot = RequireSnapshot();
        ClearError();
        try
        {
            return await _commands.PreviewDeactivationAsync(
                snapshot.Scheme,
                node.NodeId,
                cancellationToken);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception error)
        {
            SetError(error, L("Model_StatusImpactFailed"));
            return null;
        }
    }

    public async Task<bool> CompleteDeactivationAsync(
        GraphNodeProjection node,
        DeactivationImpact impact,
        bool continueRequested,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(node);
        ArgumentNullException.ThrowIfNull(impact);
        if (!continueRequested)
        {
            StatusMessage = L("Model_StatusDeactivationCancelled");
            return false;
        }

        var snapshot = RequireSnapshot();
        var projectId = RequireProjectId();
        var schemeId = snapshot.Scheme.SchemeId;
        if (impact.SchemeId != schemeId || impact.RequestedNodeId != node.NodeId)
        {
            throw new ArgumentException("The deactivation preview does not match this task and node.");
        }

        BeginBusy();
        ClearError();
        StatusMessage = L("Model_StatusDeactivating");
        try
        {
            var response = await _commands.CompleteDeactivationAsync(
                snapshot.Scheme,
                node.NodeId,
                impact,
                continueRequested,
                cancellationToken);
            if (response is null)
            {
                StatusMessage = L("Model_StatusDeactivationCancelled");
                return false;
            }

            if (IsCurrentContext(projectId, schemeId))
            {
                ApplyCanonicalGraph(
                    response.Graph,
                    [],
                    L("Model_StatusDeactivated"));
            }

            return true;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception error)
        {
            if (IsCurrentContext(projectId, schemeId))
            {
                SetError(
                    error,
                    L("Model_StatusDeactivationFailed"));
            }

            return false;
        }
        finally
        {
            EndBusy();
        }
    }

    public async Task<bool> DeleteNodeAsync(
        GraphNodeProjection node,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(node);
        if (node.IsArchived)
        {
            StatusMessage = L("Model_StatusNodeAlreadyDeleted");
            return true;
        }

        var snapshot = RequireSnapshot();
        var projectId = RequireProjectId();
        var schemeId = snapshot.Scheme.SchemeId;
        BeginBusy();
        ClearError();
        StatusMessage = L("Model_StatusDeletingNode");
        try
        {
            _pendingLayouts.Remove(node.NodeId);
            var response = await _commands.ArchiveNodeAsync(node.Node, cancellationToken);
            _selectedNodeIds.Remove(node.NodeId);
            await _schemes.LoadAsync(projectId, cancellationToken);
            if (IsCurrentContext(projectId, schemeId))
            {
                var graph = await _commands.GetGraphAsync(schemeId, cancellationToken);
                ApplyCanonicalGraph(
                    graph,
                    _selectedNodeIds,
                    F(
                        "Model_StatusNodeDeleted",
                        node.DisplayName,
                        response.AffectedSchemeIds.Length));
            }

            return true;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception error)
        {
            if (IsCurrentContext(projectId, schemeId))
            {
                SetError(error, L("Model_StatusNodeDeleteFailed"));
            }

            return false;
        }
        finally
        {
            EndBusy();
        }
    }

    public void CopySelection(GraphNodeProjection? fallbackNode = null)
    {
        var projectId = RequireProjectId();
        var ids = _selectedNodeIds.Count > 0
            ? _selectedNodeIds
            : fallbackNode is null
                ? []
                : [fallbackNode.NodeId];
        _commands.Copy(projectId, ids);
        StatusMessage = F(
            "Model_StatusCopiedCount",
            _selectedNodeIds.Count switch { 0 => 1, var count => count });
        OnPropertyChanged(nameof(CanPaste));
    }

    public void CopyNode(GraphNodeProjection node)
    {
        ArgumentNullException.ThrowIfNull(node);
        _commands.Copy(RequireProjectId(), [node.NodeId]);
        StatusMessage = F("Model_StatusCopiedNode", node.DisplayName);
        OnPropertyChanged(nameof(CanPaste));
    }

    public IReadOnlyList<string> DescribeNodeIds(IEnumerable<string> nodeIds)
    {
        ArgumentNullException.ThrowIfNull(nodeIds);
        var names = RequireSnapshot().Nodes.ToDictionary(
            node => node.NodeId,
            node => ModelDisplayNameResolver.ForNode(node),
            StringComparer.Ordinal);
        return nodeIds
            .Select(nodeId => names.TryGetValue(nodeId, out var name)
                ? name
                : ModelDisplayNameResolver.HumanizeIdentifier(nodeId, "Model Item"))
            .ToArray();
    }

    public async Task<IReadOnlyList<ModelNode>> PasteAsync(
        CancellationToken cancellationToken = default)
    {
        var snapshot = RequireSnapshot();
        var projectId = RequireProjectId();
        var schemeId = snapshot.Scheme.SchemeId;
        if (!_commands.CanPaste(projectId))
        {
            SetError(
                new InvalidOperationException("The in-app model clipboard is empty for this project."),
                L("Model_StatusNothingPasted"));
            return [];
        }

        BeginBusy();
        ClearError();
        StatusMessage = L("Model_StatusPasting");
        try
        {
            var response = await _commands.PasteAsync(
                projectId,
                snapshot.Scheme,
                cancellationToken);
            if (IsCurrentContext(projectId, schemeId))
            {
                ApplyCanonicalGraph(
                    response.Graph,
                    response.CopiedNodes.Select(node => node.NodeId),
                    L("Model_StatusPasted"));
            }

            return response.CopiedNodes;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception error)
        {
            if (IsCurrentContext(projectId, schemeId))
            {
                SetError(error, L("Model_StatusPasteFailed"));
            }

            return [];
        }
        finally
        {
            EndBusy();
        }
    }

    public void QueueLayoutUpdate(GraphNodeProjection node, double x, double y)
    {
        ArgumentNullException.ThrowIfNull(node);
        _pendingLayouts[node.NodeId] = new NodeLayout(
            node.NodeId,
            Math.Max(GraphProjection.NodeDiameter / 2, x - node.LayoutOffsetX),
            Math.Max(GraphProjection.NodeDiameter / 2, y - node.LayoutOffsetY));
        Reproject();
        var previous = Interlocked.Exchange(ref _layoutDebounce, new CancellationTokenSource());
        previous?.Cancel();
        previous?.Dispose();
        _ = SaveLayoutAfterDelayAsync(_layoutDebounce.Token);
    }

    public async Task<bool> FlushPendingLayoutAsync(CancellationToken cancellationToken = default)
    {
        var debounce = Interlocked.Exchange(ref _layoutDebounce, null);
        debounce?.Cancel();
        debounce?.Dispose();
        if (_pendingLayouts.Count == 0)
        {
            return true;
        }

        var snapshot = RequireSnapshot();
        var projectId = RequireProjectId();
        var schemeId = snapshot.Scheme.SchemeId;
        var positions = _pendingLayouts.Values
            .OrderBy(layout => layout.NodeId, StringComparer.Ordinal)
            .ToArray();
        BeginBusy();
        ClearError();
        StatusMessage = L("Model_StatusSavingLayout");
        try
        {
            var response = await _commands.UpdateLayoutAsync(
                snapshot.Scheme,
                positions,
                cancellationToken);
            if (IsCurrentContext(projectId, schemeId))
            {
                ApplyCanonicalGraph(
                    response.Graph,
                    _selectedNodeIds,
                    L("Model_StatusLayoutSaved"));
            }

            return true;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception error)
        {
            if (IsCurrentContext(projectId, schemeId))
            {
                _pendingLayouts.Clear();
                var graph = await _commands.GetGraphAsync(schemeId, cancellationToken);
                ApplyCanonicalGraph(
                    graph,
                    _selectedNodeIds,
                    L("Model_StatusLayoutRestored"));
                SetError(error, L("Model_StatusLayoutConflict"));
            }

            return false;
        }
        finally
        {
            EndBusy();
        }
    }

    public Task<bool> UndoEditAsync(CancellationToken cancellationToken = default) =>
        MoveEditHistoryAsync(redo: false, cancellationToken);

    public Task<bool> RedoEditAsync(CancellationToken cancellationToken = default) =>
        MoveEditHistoryAsync(redo: true, cancellationToken);

    private async Task<bool> MoveEditHistoryAsync(
        bool redo,
        CancellationToken cancellationToken)
    {
        var projectId = RequireProjectId();
        BeginBusy();
        ClearError();
        StatusMessage = L(redo ? "Model_StatusRedoing" : "Model_StatusUndoing");
        try
        {
            _ = redo
                ? await _editSession.RedoEditAsync("expert.desktop", cancellationToken)
                : await _editSession.UndoEditAsync("expert.desktop", cancellationToken);
            await _schemes.LoadAsync(projectId, cancellationToken);
            if (_schemes.SelectedScheme is { } selected)
            {
                await LoadGraphAsync(selected.SchemeId, cancellationToken);
            }

            StatusMessage = L(redo ? "Model_StatusRedone" : "Model_StatusUndone");
            return true;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception error)
        {
            SetError(error, L(redo ? "Model_StatusRedoFailed" : "Model_StatusUndoFailed"));
            return false;
        }
        finally
        {
            EndBusy();
        }
    }

    public async Task<bool> ConnectSelectedParentAsync(
        GraphNodeProjection target,
        bool markCptIncomplete,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(target);
        var source = RequireSingleSelectedSource(target.NodeId);
        var targetNode = CanonicalNode(target.NodeId);
        var sourceNode = CanonicalNode(source.NodeId);
        return await RunEdgeMutationAsync(
            targetNode,
            token => _commands.AddEdgeAsync(
                sourceNode,
                targetNode,
                markCptIncomplete,
                token),
            L("Model_StatusEdgeAdded"),
            cancellationToken);
    }

    public ModelGraphEdgeKind SelectedParentEdgeKindFor(GraphNodeProjection target)
    {
        ArgumentNullException.ThrowIfNull(target);
        var source = RequireSingleSelectedSource(target.NodeId);
        if (source.NodeKind is ModelNodeKind.RawInput)
        {
            if (target.NodeKind is not ModelNodeKind.Evidence)
            {
                throw new InvalidOperationException(
                    "Raw Input extraction edges can only target an Evidence node.");
            }

            return ModelGraphEdgeKind.Extraction;
        }

        if (target.NodeKind is ModelNodeKind.RawInput)
        {
            throw new InvalidOperationException("Raw Input nodes cannot have model parents.");
        }

        if (target.NodeKind is ModelNodeKind.Evidence && source.NodeKind is not ModelNodeKind.Bn)
        {
            throw new InvalidOperationException(
                "An Evidence probabilistic parent must be a BN node.");
        }

        return ModelGraphEdgeKind.Probabilistic;
    }

    public async Task<bool> RemoveSelectedParentAsync(
        GraphNodeProjection target,
        bool markCptIncomplete,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(target);
        var source = RequireSingleSelectedSource(target.NodeId);
        var targetNode = CanonicalNode(target.NodeId);
        var sourceNode = CanonicalNode(source.NodeId);
        var edge = _snapshot?.Edges.SingleOrDefault(item =>
            item.Parent.NodeId == sourceNode.NodeId && item.Child.NodeId == targetNode.NodeId)
            ?? throw new InvalidOperationException("The selected nodes do not have that canonical edge.");
        return await RunEdgeMutationAsync(
            targetNode,
            token => _commands.RemoveEdgeAsync(
                edge,
                sourceNode,
                targetNode,
                markCptIncomplete,
                token),
            L("Model_StatusEdgeRemoved"),
            cancellationToken);
    }

    public void RequestOpenNode(GraphNodeProjection node)
    {
        ArgumentNullException.ThrowIfNull(node);
        var schemeId = RequireSnapshot().Scheme.SchemeId;
        NodeEditorRequested?.Invoke(this, new ModelNodeOpenRequestedEventArgs(node.Node, schemeId));
    }

    private async Task SaveLayoutAfterDelayAsync(CancellationToken cancellationToken)
    {
        try
        {
            await Task.Delay(TimeSpan.FromMilliseconds(350), cancellationToken);
            await FlushPendingLayoutAsync();
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
        }
    }

    private async Task<bool> RunEdgeMutationAsync(
        ModelNode targetNode,
        Func<CancellationToken, Task> mutation,
        string successMessage,
        CancellationToken cancellationToken)
    {
        var snapshot = RequireSnapshot();
        var projectId = RequireProjectId();
        var schemeId = snapshot.Scheme.SchemeId;
        BeginBusy();
        ClearError();
        StatusMessage = L("Model_StatusSavingEdge");
        try
        {
            await mutation(cancellationToken);
            var graph = await _commands.GetGraphAsync(schemeId, cancellationToken);
            if (IsCurrentContext(projectId, schemeId))
            {
                ApplyCanonicalGraph(graph, [targetNode.NodeId], successMessage);
            }

            return true;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception error)
        {
            if (IsCurrentContext(projectId, schemeId))
            {
                SetError(error, L("Model_StatusEdgeFailed"));
            }

            return false;
        }
        finally
        {
            EndBusy();
        }
    }

    private ModelNode RequireSingleSelectedSource(string targetNodeId)
    {
        var sourceIds = _selectedNodeIds
            .Where(nodeId => nodeId != targetNodeId)
            .ToArray();
        if (sourceIds.Length != 1)
        {
            throw new InvalidOperationException(
                "Select exactly one parent node, then invoke the edge command on its child.");
        }

        return CanonicalNode(sourceIds[0]);
    }

    private ModelNode CanonicalNode(string nodeId) =>
        RequireSnapshot().Nodes.Single(node => node.NodeId == nodeId);

    private ModelGraphSnapshot RequireSnapshot() =>
        _snapshot ?? throw new InvalidOperationException("Load a task model graph first.");

    private static string RequireProjectId() => SystemModelContext.Key;

    private bool IsCurrentContext(string projectId, string schemeId) =>
        string.Equals(SystemModelContext.Key, projectId, StringComparison.Ordinal) &&
        string.Equals(_schemes.SelectedScheme?.SchemeId, schemeId, StringComparison.Ordinal);

    private void ApplyCanonicalGraph(
        ModelGraphSnapshot graph,
        IEnumerable<string> selectedNodeIds,
        string statusMessage)
    {
        _snapshot = graph;
        _pendingLayouts.Clear();
        _schemes.ApplyCanonical(graph.Scheme);
        _selectedNodeIds.Clear();
        _selectedNodeIds.UnionWith(
            selectedNodeIds.Where(nodeId => graph.Nodes.Any(node => node.NodeId == nodeId)));
        RefreshFilterOptions(graph);
        UpdateSelectionSummary();
        Reproject();
        StatusMessage = statusMessage;
        OnPropertyChanged(nameof(CurrentSchemeId));
        OnPropertyChanged(nameof(CanPaste));
        NotifySelectionChanged();
        CanonicalGraphChanged?.Invoke(this, new CanonicalModelGraphChangedEventArgs(graph));
    }

    private void NotifySelectionChanged()
    {
        OnPropertyChanged(nameof(PrimarySelectedNode));
        OnPropertyChanged(nameof(SelectedNodeIds));
    }

    private GraphProjectionResult ApplyPendingLayouts(GraphProjectionResult result)
    {
        if (_pendingLayouts.Count == 0 || result.Nodes.Count == 0)
        {
            return result;
        }

        var nodes = result.Nodes
            .Select(node => _pendingLayouts.TryGetValue(node.NodeId, out var layout)
                ? node with
                {
                    X = layout.X + node.LayoutOffsetX,
                    Y = layout.Y + node.LayoutOffsetY,
                }
                : node)
            .ToArray();
        var byId = nodes.ToDictionary(node => node.NodeId, StringComparer.Ordinal);
        var edges = result.Edges
            .Select(edge => edge with
            {
                Parent = byId[edge.Parent.NodeId],
                Child = byId[edge.Child.NodeId],
            })
            .ToArray();
        var provenanceEdges = result.ProvenanceEdges
            .Select(edge => edge with { Child = byId[edge.Child.NodeId] })
            .ToArray();
        var radius = GraphProjection.NodeDiameter / 2;
        var familyRadius = GraphProjection.RawInputFamilyDiameter / 2;
        var familyMaxX = result.RawInputFamilies.Count == 0
            ? 0
            : result.RawInputFamilies.Max(node => node.X) + familyRadius;
        var familyMaxY = result.RawInputFamilies.Count == 0
            ? 0
            : result.RawInputFamilies.Max(node => node.Y) + familyRadius;
        var width = Math.Max(
            GraphProjection.MinimumExtentWidth,
            Math.Max(
                nodes.Max(node => node.X) + radius,
                familyMaxX) + GraphProjection.CanvasPadding);
        var height = Math.Max(
            GraphProjection.MinimumExtentHeight,
            Math.Max(
                nodes.Max(node => node.Y) + radius,
                familyMaxY) + GraphProjection.CanvasPadding);
        return new GraphProjectionResult(
            nodes,
            edges,
            result.RawInputFamilies,
            provenanceEdges,
            width,
            height);
    }

    private void BeginBusy()
    {
        _busyOperations++;
        IsBusy = true;
    }

    private void EndBusy()
    {
        _busyOperations = Math.Max(0, _busyOperations - 1);
        IsBusy = _busyOperations > 0;
    }

    private void SetError(Exception error, string status)
    {
        HasError = true;
        ErrorMessage = error.Message;
        StatusMessage = status;
    }

    partial void OnSearchTextChanged(string value) => Reproject();

    partial void OnSelectedViewModeChanged(string value) => Reproject();

    partial void OnSelectedLayerChanged(string value) => Reproject();

    partial void OnSelectedActivationChanged(string value) => Reproject();

    partial void OnSelectedGroupChanged(string value) => Reproject();

    partial void OnIsMultiSelectChanged(bool value)
    {
        if (!value && _selectedNodeIds.Count > 1)
        {
            var retained = _selectedNodeIds.OrderBy(item => item, StringComparer.Ordinal).First();
            _selectedNodeIds.Clear();
            _selectedNodeIds.Add(retained);
            UpdateSelectionSummary();
            Reproject();
            NotifySelectionChanged();
        }
    }

    private async void OnSchemePropertyChanged(object? sender, PropertyChangedEventArgs args)
    {
        if (args.PropertyName is not nameof(TaskSchemeListViewModel.SelectedScheme))
        {
            return;
        }

        var selected = _schemes.SelectedScheme;
        if (selected is null)
        {
            Interlocked.Increment(ref _loadGeneration);
            ClearGraph("Choose a task scheme to load the global model graph.");
            return;
        }

        await LoadGraphAsync(selected.SchemeId);
    }

    private void OnLanguageChanged(object? sender, EventArgs args)
    {
        var viewMode = ParseViewMode(SelectedViewMode);
        var layer = ParseLayer(SelectedLayer);
        var activation = ParseActivation(SelectedActivation);
        var groupWasAll = SelectedGroup == _allGroupsLabel;

        RefreshLocalizedOptions();
        SelectedViewMode = viewMode switch
        {
            GraphViewMode.ActiveOnly => _viewActiveOnlyLabel,
            GraphViewMode.AllGlobalNodes => _viewAllLabel,
            _ => _viewActiveInactiveLabel,
        };
        SelectedLayer = layer switch
        {
            GraphDisplayLayer.RawInputFamily => _layerRawFamilyLabel,
            GraphDisplayLayer.ExtractedData => _layerExtractedDataLabel,
            GraphDisplayLayer.Evidence => _layerEvidenceLabel,
            GraphDisplayLayer.SubSkill => _layerSubSkillLabel,
            GraphDisplayLayer.Competency => _layerCompetencyLabel,
            _ => _layerAllLabel,
        };
        SelectedActivation = activation switch
        {
            true => _activationActiveLabel,
            false => _activationInactiveLabel,
            _ => _activationAllLabel,
        };
        SelectedGroup = groupWasAll ? _allGroupsLabel : SelectedGroup;
        if (_snapshot is not null)
        {
            RefreshFilterOptions(_snapshot);
            StatusMessage = F(
                "Model_GraphSummary",
                _snapshot.Nodes.Length,
                _snapshot.Edges.Length,
                _snapshot.Scheme.ComputedActiveClosure.Length,
                DisplaySchemeName(_snapshot.Scheme));
        }
        else
        {
            ResetFilterOptions();
            StatusMessage = _localization["Model_ChooseTaskScheme"];
        }

        UpdateSelectionSummary();
        Reproject();
    }

    private void RefreshLocalizedOptions()
    {
        _allGroupsLabel = _localization["Task_AllGroups"];
        _viewActiveOnlyLabel = _localization["Model_ViewActiveOnly"];
        _viewActiveInactiveLabel = _localization["Model_ViewActiveInactive"];
        _viewAllLabel = _localization["Model_ViewAll"];
        _layerAllLabel = _localization["Model_LayerAll"];
        _layerRawFamilyLabel = _localization["Model_LayerRawFamily"];
        _layerExtractedDataLabel = _localization["Model_LayerExtractedData"];
        _layerEvidenceLabel = _localization["Model_LayerEvidence"];
        _layerSubSkillLabel = _localization["Model_LayerSubSkill"];
        _layerCompetencyLabel = _localization["Model_LayerCompetency"];
        _activationAllLabel = _localization["Model_ActivationAll"];
        _activationActiveLabel = _localization["Common_Active"];
        _activationInactiveLabel = _localization["Common_Inactive"];

        Replace(ViewModes, [_viewActiveOnlyLabel, _viewActiveInactiveLabel, _viewAllLabel]);
        Replace(
            LayerOptions,
            [
                _layerAllLabel,
                _layerRawFamilyLabel,
                _layerExtractedDataLabel,
                _layerEvidenceLabel,
                _layerSubSkillLabel,
                _layerCompetencyLabel,
            ]);
        Replace(ActivationOptions, [_activationAllLabel, _activationActiveLabel, _activationInactiveLabel]);
    }

    private GraphProjectionLabels CreateGraphLabels() => new(
        _localization["Node_KindRaw"],
        _localization["Node_KindEvidence"],
        _localization["Node_KindBn"],
        _localization["Node_KindSubskill"],
        _localization["Node_KindCompetency"],
        _localization["Node_StatusActive"],
        _localization["Node_StatusInactive"],
        _localization["Node_StatusArchived"],
        _localization["Node_TechnicalExecutable"],
        _localization["Node_TechnicalIncomplete"],
        _localization["Node_TechnicalBlocked"],
        _localization["Node_OutputSuffix"],
        _localization["Node_A11y"]);

    private GraphRawInputFamilyLabels CreateRawInputFamilyLabels() => new(
        new(_localization["RawFamily_X_Name"], _localization["RawFamily_X_Description"]),
        new(_localization["RawFamily_U_Name"], _localization["RawFamily_U_Description"]),
        new(_localization["RawFamily_I_Name"], _localization["RawFamily_I_Description"]),
        new(_localization["RawFamily_G_Name"], _localization["RawFamily_G_Description"]),
        new(_localization["RawFamily_P_Name"], _localization["RawFamily_P_Description"]),
        _localization["RawFamily_Kind"],
        _localization["RawFamily_A11y"]);

    private void Reproject()
    {
        if (_snapshot is null)
        {
            return;
        }

        var result = ApplyPendingLayouts(
            GraphProjection.Project(
                _snapshot,
                new GraphProjectionOptions(
                    ParseViewMode(SelectedViewMode),
                    SearchText,
                    ParseLayer(SelectedLayer),
                    SelectedGroup == _allGroupsLabel ? null : SelectedGroup,
                    ParseActivation(SelectedActivation),
                    _selectedNodeIds,
                    _localization.CurrentLanguage,
                    CreateGraphLabels(),
                    CreateRawInputFamilyLabels())));
        Replace(Nodes, result.Nodes);
        Replace(Edges, result.Edges);
        Replace(RawInputFamilies, result.RawInputFamilies);
        Replace(ProvenanceEdges, result.ProvenanceEdges);
        ExtentWidth = result.ExtentWidth;
        ExtentHeight = result.ExtentHeight;
        ProjectionVersion++;
    }

    private void RefreshFilterOptions(ModelGraphSnapshot graph)
    {
        var selectedGroup = SelectedGroup;
        ReplaceOptions(
            AvailableGroups,
            _allGroupsLabel,
            graph.Nodes.Select(node => node.Group).OfType<string>());
        SelectedGroup = AvailableGroups.Contains(selectedGroup) ? selectedGroup : _allGroupsLabel;
    }

    private void ClearGraph(string status)
    {
        _snapshot = null;
        _pendingLayouts.Clear();
        var debounce = Interlocked.Exchange(ref _layoutDebounce, null);
        debounce?.Cancel();
        debounce?.Dispose();
        Nodes.Clear();
        Edges.Clear();
        RawInputFamilies.Clear();
        ProvenanceEdges.Clear();
        _selectedNodeIds.Clear();
        ExtentWidth = GraphProjection.MinimumExtentWidth;
        ExtentHeight = GraphProjection.MinimumExtentHeight;
        ResetFilterOptions();
        UpdateSelectionSummary();
        StatusMessage = status;
        ProjectionVersion++;
        OnPropertyChanged(nameof(CurrentSchemeId));
        OnPropertyChanged(nameof(CanPaste));
        NotifySelectionChanged();
    }

    private void UpdateSelectionSummary()
    {
        if (_selectedNodeIds.Count == 0)
        {
            SelectedNodeSummary = _localization["Model_NoNodeSelected"];
            return;
        }

        if (_selectedNodeIds.Count == 1 && _snapshot is not null)
        {
            var nodeId = _selectedNodeIds.Single();
            var node = _snapshot.Nodes.First(item => item.NodeId == nodeId);
            SelectedNodeSummary =
                $"{ModelDisplayNameResolver.ForNode(node)} " +
                $"• {DisplayNodeKind(node.NodeKind)} • {DisplayTechnicalStatus(node.TechnicalStatus)}";
            return;
        }

        SelectedNodeSummary = _localization.Format("Model_NodesSelected", _selectedNodeIds.Count);
    }

    private void ResetFilterOptions()
    {
        AvailableGroups.Clear();
        AvailableGroups.Add(_allGroupsLabel);
        SelectedGroup = _allGroupsLabel;
    }

    private void ClearError()
    {
        HasError = false;
        ErrorMessage = string.Empty;
    }

    private string L(string key) => _localization[key];

    private string F(string key, params object?[] arguments) =>
        _localization.Format(key, arguments);

    private string DisplayNodeKind(ModelNodeKind kind) => kind switch
    {
        ModelNodeKind.RawInput => _localization["Node_KindRaw"],
        ModelNodeKind.Evidence => _localization["Node_KindEvidence"],
        _ => _localization["Node_KindBn"],
    };

    private string DisplayTechnicalStatus(ModelTechnicalStatus status) => status switch
    {
        ModelTechnicalStatus.Executable => _localization["Node_TechnicalExecutable"],
        ModelTechnicalStatus.Incomplete => _localization["Node_TechnicalIncomplete"],
        _ => _localization["Node_TechnicalBlocked"],
    };

    private GraphViewMode ParseViewMode(string value) => value switch
    {
        var item when item == _viewActiveOnlyLabel => GraphViewMode.ActiveOnly,
        var item when item == _viewAllLabel => GraphViewMode.AllGlobalNodes,
        _ => GraphViewMode.ActiveAndInactive,
    };

    private GraphDisplayLayer? ParseLayer(string value) => value switch
    {
        var item when item == _layerRawFamilyLabel => GraphDisplayLayer.RawInputFamily,
        var item when item == _layerExtractedDataLabel => GraphDisplayLayer.ExtractedData,
        var item when item == _layerEvidenceLabel => GraphDisplayLayer.Evidence,
        var item when item == _layerSubSkillLabel => GraphDisplayLayer.SubSkill,
        var item when item == _layerCompetencyLabel => GraphDisplayLayer.Competency,
        _ => null,
    };

    private bool? ParseActivation(string value) => value switch
    {
        var item when item == _activationActiveLabel => true,
        var item when item == _activationInactiveLabel => false,
        _ => null,
    };

    private static string DisplaySchemeName(TaskScheme scheme) =>
        ModelDisplayNameResolver.ForScheme(scheme);

    private static void Replace<T>(ObservableCollection<T> target, IEnumerable<T> values)
    {
        target.Clear();
        foreach (var value in values)
        {
            target.Add(value);
        }
    }

    private static void ReplaceOptions(
        ObservableCollection<string> target,
        string allLabel,
        IEnumerable<string> values)
    {
        target.Clear();
        target.Add(allLabel);
        foreach (var value in values
                     .Where(item => !string.IsNullOrWhiteSpace(item))
                     .Distinct(StringComparer.Ordinal)
                     .OrderBy(item => item, StringComparer.Ordinal))
        {
            target.Add(value);
        }
    }
}

public sealed class ModelNodeOpenRequestedEventArgs(
    ModelNode node,
    string schemeId) : EventArgs
{
    public ModelNode Node { get; } = node;
    public string SchemeId { get; } = schemeId;
}

public sealed class CanonicalModelGraphChangedEventArgs(ModelGraphSnapshot graph) : EventArgs
{
    public ModelGraphSnapshot Graph { get; } = graph;
}
