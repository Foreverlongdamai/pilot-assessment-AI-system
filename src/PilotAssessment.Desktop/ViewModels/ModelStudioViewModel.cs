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

    private readonly IModelWorkspaceGateway _gateway;
    private readonly TaskSchemeListViewModel _schemes;
    private readonly ApplicationShellState _shellState;
    private readonly HashSet<string> _selectedNodeIds = new(StringComparer.Ordinal);
    private int _loadGeneration;
    private ModelGraphSnapshot? _snapshot;

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
        IModelWorkspaceGateway gateway,
        TaskSchemeListViewModel schemes,
        ApplicationShellState shellState)
    {
        _gateway = gateway;
        _schemes = schemes;
        _shellState = shellState;
        AvailableGroups.Add(AllGroups);
        AvailableTags.Add(AllTags);
        _schemes.PropertyChanged += OnSchemePropertyChanged;
    }

    public ObservableCollection<GraphNodeProjection> Nodes { get; } = [];

    public ObservableCollection<GraphEdgeProjection> Edges { get; } = [];

    public ObservableCollection<string> AvailableGroups { get; } = [];

    public ObservableCollection<string> AvailableTags { get; } = [];

    public IReadOnlyList<string> ViewModes { get; } =
        ["Active only", "Active + inactive", "All global nodes"];

    public IReadOnlyList<string> KindOptions { get; } =
        ["All node kinds", "Raw Input", "Evidence", "BN"];

    public IReadOnlyList<string> ActivationOptions { get; } =
        ["All activation states", "Active", "Inactive"];

    public string? CurrentSchemeId => _snapshot?.Scheme.SchemeId;

    public async Task ActivateAsync(CancellationToken cancellationToken = default)
    {
        var selected = _schemes.SelectedScheme;
        if (selected is null)
        {
            ClearGraph("Choose a task scheme to load the global model graph.");
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
        IsBusy = true;
        ClearError();
        StatusMessage = $"Loading canonical graph for {schemeId}…";
        try
        {
            var graph = await _gateway.GetGraphAsync(schemeId, cancellationToken);
            if (generation != Volatile.Read(ref _loadGeneration) ||
                _shellState.Snapshot.ProjectId != projectId ||
                _schemes.SelectedScheme?.SchemeId != schemeId)
            {
                return;
            }

            _snapshot = graph;
            _selectedNodeIds.IntersectWith(graph.Nodes.Select(node => node.NodeId));
            RefreshFilterOptions(graph);
            Reproject();
            StatusMessage =
                $"{graph.Nodes.Length} global nodes, {graph.Edges.Length} canonical edges; " +
                $"{graph.Scheme.ComputedActiveClosure.Length} active in {DisplaySchemeName(graph.Scheme)}.";
            OnPropertyChanged(nameof(CurrentSchemeId));
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
                StatusMessage = "The model graph could not be loaded.";
            }
        }
        finally
        {
            if (generation == Volatile.Read(ref _loadGeneration))
            {
                IsBusy = false;
            }
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
    }

    public void ClearSelection()
    {
        _selectedNodeIds.Clear();
        UpdateSelectionSummary();
        Reproject();
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

    private void Reproject()
    {
        if (_snapshot is null)
        {
            return;
        }

        var result = GraphProjection.Project(
            _snapshot,
            new GraphProjectionOptions(
                ParseViewMode(SelectedViewMode),
                SearchText,
                ParseKind(SelectedKind),
                SelectedGroup == AllGroups ? null : SelectedGroup,
                SelectedTag == AllTags ? null : SelectedTag,
                ParseActivation(SelectedActivation),
                _selectedNodeIds));
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
            AllGroups,
            graph.Nodes.Select(node => node.Group).OfType<string>());
        ReplaceOptions(
            AvailableTags,
            AllTags,
            graph.Nodes.SelectMany(node => node.Tags));
        SelectedGroup = AvailableGroups.Contains(selectedGroup) ? selectedGroup : AllGroups;
        SelectedTag = AvailableTags.Contains(selectedTag) ? selectedTag : AllTags;
    }

    private void ClearGraph(string status)
    {
        _snapshot = null;
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
    }

    private void UpdateSelectionSummary()
    {
        if (_selectedNodeIds.Count == 0)
        {
            SelectedNodeSummary = "No node selected";
            return;
        }

        if (_selectedNodeIds.Count == 1 && _snapshot is not null)
        {
            var nodeId = _selectedNodeIds.Single();
            var node = _snapshot.Nodes.First(item => item.NodeId == nodeId);
            SelectedNodeSummary =
                $"{node.ShortNameEn ?? node.NameEn ?? node.ShortNameZh ?? node.NameZh ?? node.NodeId} " +
                $"• {node.NodeKind} • {node.TechnicalStatus}";
            return;
        }

        SelectedNodeSummary = $"{_selectedNodeIds.Count} nodes selected";
    }

    private void ResetFilterOptions()
    {
        AvailableGroups.Clear();
        AvailableGroups.Add(AllGroups);
        AvailableTags.Clear();
        AvailableTags.Add(AllTags);
        SelectedGroup = AllGroups;
        SelectedTag = AllTags;
    }

    private void ClearError()
    {
        HasError = false;
        ErrorMessage = string.Empty;
    }

    private static GraphViewMode ParseViewMode(string value) => value switch
    {
        "Active only" => GraphViewMode.ActiveOnly,
        "All global nodes" => GraphViewMode.AllGlobalNodes,
        _ => GraphViewMode.ActiveAndInactive,
    };

    private static ModelNodeKind? ParseKind(string value) => value switch
    {
        "Raw Input" => ModelNodeKind.RawInput,
        "Evidence" => ModelNodeKind.Evidence,
        "BN" => ModelNodeKind.Bn,
        _ => null,
    };

    private static bool? ParseActivation(string value) => value switch
    {
        "Active" => true,
        "Inactive" => false,
        _ => null,
    };

    private static string DisplaySchemeName(TaskScheme scheme) =>
        scheme.NameEn ?? scheme.NameZh ?? scheme.SchemeId;

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
