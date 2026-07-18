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
    public const string AllTags = "All tags";

    private readonly ModelGraphCommandCoordinator _commands;
    private readonly TaskSchemeListViewModel _schemes;
    private readonly ApplicationShellState _shellState;
    private readonly ILocalizationLookup _localization;
    private readonly HashSet<string> _selectedNodeIds = new(StringComparer.Ordinal);
    private readonly Dictionary<string, NodeLayout> _pendingLayouts = new(StringComparer.Ordinal);
    private int _loadGeneration;
    private int _busyOperations;
    private ModelGraphSnapshot? _snapshot;
    private CancellationTokenSource? _layoutDebounce;
    private string _allGroupsLabel = AllGroups;
    private string _allTagsLabel = AllTags;
    private string _viewActiveOnlyLabel = "Active only";
    private string _viewActiveInactiveLabel = "Active + inactive";
    private string _viewAllLabel = "All global nodes";
    private string _kindAllLabel = "All node kinds";
    private string _kindRawLabel = "Raw Input";
    private string _kindEvidenceLabel = "Evidence";
    private string _kindBnLabel = "BN";
    private string _activationAllLabel = "All activation states";
    private string _activationActiveLabel = "Active";
    private string _activationInactiveLabel = "Inactive";

    [ObservableProperty]
    public partial string SearchText { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string SelectedViewMode { get; set; } = "Active + inactive";

    [ObservableProperty]
    public partial string SelectedKind { get; set; } = "All node kinds";

    [ObservableProperty]
    public partial string SelectedActivation { get; set; } = "All activation states";

    [ObservableProperty]
    public partial string SelectedGroup { get; set; } = AllGroups;

    [ObservableProperty]
    public partial string SelectedTag { get; set; } = AllTags;

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
        ApplicationShellState shellState,
        ILocalizationLookup localization)
    {
        _commands = commands;
        _schemes = schemes;
        _shellState = shellState;
        _localization = localization;
        RefreshLocalizedOptions();
        AvailableGroups.Add(_allGroupsLabel);
        AvailableTags.Add(_allTagsLabel);
        SelectedGroup = _allGroupsLabel;
        SelectedTag = _allTagsLabel;
        SelectedViewMode = _viewActiveInactiveLabel;
        SelectedKind = _kindAllLabel;
        SelectedActivation = _activationAllLabel;
        StatusMessage = L("Model_ChooseTaskScheme");
        SelectedNodeSummary = L("Model_NoNodeSelected");
        _schemes.PropertyChanged += OnSchemePropertyChanged;
        _localization.LanguageChanged += OnLanguageChanged;
    }

    public ObservableCollection<GraphNodeProjection> Nodes { get; } = [];

    public ObservableCollection<GraphEdgeProjection> Edges { get; } = [];

    public ObservableCollection<string> AvailableGroups { get; } = [];

    public ObservableCollection<string> AvailableTags { get; } = [];

    public ObservableCollection<string> ViewModes { get; } = [];

    public ObservableCollection<string> KindOptions { get; } = [];

    public ObservableCollection<string> ActivationOptions { get; } = [];

    public string? CurrentSchemeId => _snapshot?.Scheme.SchemeId;

    public GraphNodeProjection? PrimarySelectedNode =>
        Nodes.FirstOrDefault(node => node.IsSelected);

    public IReadOnlyList<string> SelectedNodeIds =>
        _selectedNodeIds.OrderBy(nodeId => nodeId, StringComparer.Ordinal).ToArray();

    public bool CanPaste =>
        _shellState.Snapshot.ProjectId is { } projectId &&
        _commands.CanPaste(projectId);

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
        var projectId = _shellState.Snapshot.ProjectId;
        BeginBusy();
        ClearError();
        StatusMessage = F("Model_StatusLoading", schemeId);
        try
        {
            var graph = await _commands.GetGraphAsync(schemeId, cancellationToken);
            if (generation != Volatile.Read(ref _loadGeneration) ||
                _shellState.Snapshot.ProjectId != projectId ||
                _schemes.SelectedScheme?.SchemeId != schemeId)
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
            node => BilingualTextSelector.SelectShortOrFull(
                _localization.CurrentLanguage,
                node.ShortNameZh,
                node.ShortNameEn,
                node.NameZh,
                node.NameEn,
                node.NodeId),
            StringComparer.Ordinal);
        return nodeIds
            .Select(nodeId => names.TryGetValue(nodeId, out var name)
                ? $"{name} ({nodeId})"
                : nodeId)
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
            Math.Max(GraphProjection.NodeDiameter / 2, x),
            Math.Max(GraphProjection.NodeDiameter / 2, y));
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

    private string RequireProjectId() =>
        _shellState.Snapshot.ProjectId ??
        throw new InvalidOperationException("Open a managed project first.");

    private bool IsCurrentContext(string projectId, string schemeId) =>
        string.Equals(_shellState.Snapshot.ProjectId, projectId, StringComparison.Ordinal) &&
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
                ? node with { X = layout.X, Y = layout.Y }
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
        var radius = GraphProjection.NodeDiameter / 2;
        var width = Math.Max(
            GraphProjection.MinimumExtentWidth,
            nodes.Max(node => node.X) + radius + GraphProjection.CanvasPadding);
        var height = Math.Max(
            GraphProjection.MinimumExtentHeight,
            nodes.Max(node => node.Y) + radius + GraphProjection.CanvasPadding);
        return new GraphProjectionResult(nodes, edges, width, height);
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

    partial void OnSelectedKindChanged(string value) => Reproject();

    partial void OnSelectedActivationChanged(string value) => Reproject();

    partial void OnSelectedGroupChanged(string value) => Reproject();

    partial void OnSelectedTagChanged(string value) => Reproject();

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
        var nodeKind = ParseKind(SelectedKind);
        var activation = ParseActivation(SelectedActivation);
        var groupWasAll = SelectedGroup == _allGroupsLabel;
        var tagWasAll = SelectedTag == _allTagsLabel;

        RefreshLocalizedOptions();
        SelectedViewMode = viewMode switch
        {
            GraphViewMode.ActiveOnly => _viewActiveOnlyLabel,
            GraphViewMode.AllGlobalNodes => _viewAllLabel,
            _ => _viewActiveInactiveLabel,
        };
        SelectedKind = nodeKind switch
        {
            ModelNodeKind.RawInput => _kindRawLabel,
            ModelNodeKind.Evidence => _kindEvidenceLabel,
            ModelNodeKind.Bn => _kindBnLabel,
            _ => _kindAllLabel,
        };
        SelectedActivation = activation switch
        {
            true => _activationActiveLabel,
            false => _activationInactiveLabel,
            _ => _activationAllLabel,
        };
        SelectedGroup = groupWasAll ? _allGroupsLabel : SelectedGroup;
        SelectedTag = tagWasAll ? _allTagsLabel : SelectedTag;
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
        _allTagsLabel = _localization["Task_AllTags"];
        _viewActiveOnlyLabel = _localization["Model_ViewActiveOnly"];
        _viewActiveInactiveLabel = _localization["Model_ViewActiveInactive"];
        _viewAllLabel = _localization["Model_ViewAll"];
        _kindAllLabel = _localization["Model_KindAll"];
        _kindRawLabel = _localization["Model_KindRaw"];
        _kindEvidenceLabel = _localization["Model_KindEvidence"];
        _kindBnLabel = _localization["Model_KindBn"];
        _activationAllLabel = _localization["Model_ActivationAll"];
        _activationActiveLabel = _localization["Common_Active"];
        _activationInactiveLabel = _localization["Common_Inactive"];

        Replace(ViewModes, [_viewActiveOnlyLabel, _viewActiveInactiveLabel, _viewAllLabel]);
        Replace(KindOptions, [_kindAllLabel, _kindRawLabel, _kindEvidenceLabel, _kindBnLabel]);
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
                    ParseKind(SelectedKind),
                    SelectedGroup == _allGroupsLabel ? null : SelectedGroup,
                    SelectedTag == _allTagsLabel ? null : SelectedTag,
                    ParseActivation(SelectedActivation),
                    _selectedNodeIds,
                    _localization.CurrentLanguage,
                    CreateGraphLabels())));
        Replace(Nodes, result.Nodes);
        Replace(Edges, result.Edges);
        ExtentWidth = result.ExtentWidth;
        ExtentHeight = result.ExtentHeight;
        ProjectionVersion++;
    }

    private void RefreshFilterOptions(ModelGraphSnapshot graph)
    {
        var selectedGroup = SelectedGroup;
        var selectedTag = SelectedTag;
        ReplaceOptions(
            AvailableGroups,
            _allGroupsLabel,
            graph.Nodes.Select(node => node.Group).OfType<string>());
        ReplaceOptions(
            AvailableTags,
            _allTagsLabel,
            graph.Nodes.SelectMany(node => node.Tags));
        SelectedGroup = AvailableGroups.Contains(selectedGroup) ? selectedGroup : _allGroupsLabel;
        SelectedTag = AvailableTags.Contains(selectedTag) ? selectedTag : _allTagsLabel;
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
                $"{BilingualTextSelector.SelectShortOrFull(_localization.CurrentLanguage, node.ShortNameZh, node.ShortNameEn, node.NameZh, node.NameEn, node.NodeId)} " +
                $"• {DisplayNodeKind(node.NodeKind)} • {DisplayTechnicalStatus(node.TechnicalStatus)}";
            return;
        }

        SelectedNodeSummary = _localization.Format("Model_NodesSelected", _selectedNodeIds.Count);
    }

    private void ResetFilterOptions()
    {
        AvailableGroups.Clear();
        AvailableGroups.Add(_allGroupsLabel);
        AvailableTags.Clear();
        AvailableTags.Add(_allTagsLabel);
        SelectedGroup = _allGroupsLabel;
        SelectedTag = _allTagsLabel;
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

    private ModelNodeKind? ParseKind(string value) => value switch
    {
        var item when item == _kindRawLabel => ModelNodeKind.RawInput,
        var item when item == _kindEvidenceLabel => ModelNodeKind.Evidence,
        var item when item == _kindBnLabel => ModelNodeKind.Bn,
        _ => null,
    };

    private bool? ParseActivation(string value) => value switch
    {
        var item when item == _activationActiveLabel => true,
        var item when item == _activationInactiveLabel => false,
        _ => null,
    };

    private string DisplaySchemeName(TaskScheme scheme) => BilingualTextSelector.Select(
        _localization.CurrentLanguage,
        scheme.NameZh,
        scheme.NameEn,
        scheme.SchemeId);

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
