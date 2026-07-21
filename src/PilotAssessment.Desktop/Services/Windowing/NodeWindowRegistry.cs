using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;
using PilotAssessment.Desktop.Core.ViewModels;
using PilotAssessment.Desktop.ViewModels;
using PilotAssessment.Desktop.Views.Windows;

namespace PilotAssessment.Desktop.Services.Windowing;

public sealed class NodeWindowRegistry : IDisposable
{
    private readonly NodeWindowRegistryState<NodeEditorWindow> _windows = new();
    private readonly WindowPlacementStore _placements;
    private readonly ApplicationShellState _shellState;
    private readonly TaskSchemeListViewModel _schemes;
    private readonly ModelStudioViewModel _modelStudio;
    private readonly ShellViewModel _shell;
    private readonly IModelNodeEditorGateway _editorGateway;
    private readonly IBayesianNodeEditorGateway _bayesianEditorGateway;
    private readonly CanonicalObjectStore<ModelNode> _canonicalNodes;
    private readonly SessionExplorerViewModel _sessions;
    private readonly ILocalizationLookup _localization;
    private bool _disposed;

    public NodeWindowRegistry(
        WindowPlacementStore placements,
        ApplicationShellState shellState,
        TaskSchemeListViewModel schemes,
        ModelStudioViewModel modelStudio,
        ShellViewModel shell,
        IModelNodeEditorGateway editorGateway,
        IBayesianNodeEditorGateway bayesianEditorGateway,
        CanonicalObjectStore<ModelNode> canonicalNodes,
        SessionExplorerViewModel sessions,
        ILocalizationLookup localization)
    {
        _placements = placements;
        _shellState = shellState;
        _schemes = schemes;
        _modelStudio = modelStudio;
        _shell = shell;
        _editorGateway = editorGateway;
        _bayesianEditorGateway = bayesianEditorGateway;
        _canonicalNodes = canonicalNodes;
        _sessions = sessions;
        _localization = localization;
        _modelStudio.NodeEditorRequested += OnNodeEditorRequested;
        _modelStudio.CanonicalGraphChanged += OnCanonicalGraphChanged;
        _shell.ThemeChanged += OnThemeChanged;
        _localization.LanguageChanged += OnLanguageChanged;
    }

    public int OpenWindowCount => _windows.Count;

    public async Task FlushAllEditsAsync(CancellationToken cancellationToken = default)
    {
        var snapshot = _windows.Snapshot();
        await Task.WhenAll(snapshot.Select(entry =>
            entry.Value.FlushAutosaveAsync(cancellationToken)));
        if (!await _modelStudio.FlushPendingLayoutAsync(cancellationToken))
        {
            throw new InvalidOperationException(
                "Pending model layout changes could not be written to the edit session.");
        }

        await _placements.FlushAsync(cancellationToken);
    }

    public async Task CloseAllWindowsAsync(CancellationToken cancellationToken = default)
    {
        var snapshot = _windows.Snapshot();
        foreach (var entry in snapshot)
        {
            _placements.Remember(entry.Key, entry.Value.CurrentPlacement);
            entry.Value.Close();
        }

        await _placements.FlushAsync(cancellationToken);
    }

    public async Task CloseAllAsync(CancellationToken cancellationToken = default)
    {
        await FlushAllEditsAsync(cancellationToken);
        await CloseAllWindowsAsync(cancellationToken);
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        _modelStudio.NodeEditorRequested -= OnNodeEditorRequested;
        _modelStudio.CanonicalGraphChanged -= OnCanonicalGraphChanged;
        _shell.ThemeChanged -= OnThemeChanged;
        _localization.LanguageChanged -= OnLanguageChanged;
    }

    private void OnNodeEditorRequested(object? sender, ModelNodeOpenRequestedEventArgs args)
    {
        var key = new NodeWindowKey(
            SystemModelContext.Key,
            args.SchemeId,
            args.Node.NodeId);
        var schemeDisplayName = DisplayScheme(args.SchemeId);
        var sharedSchemeCount = _schemes.CountCurrentSchemesUsingNode(args.Node.NodeId);
        var window = _windows.OpenOrFocus(
            key,
            () => CreateWindow(
                key,
                args.Node,
                schemeDisplayName,
                sharedSchemeCount),
            existing => existing.FocusWindow(),
            out var created);

        window.ReconcileCanonicalNode(args.Node, schemeDisplayName, sharedSchemeCount);
        if (created)
        {
            window.ApplyTheme(_shell.SelectedTheme);
            window.Activate();
        }
    }

    private NodeEditorWindow CreateWindow(
        NodeWindowKey key,
        ModelNode node,
        string schemeDisplayName,
        int sharedSchemeCount)
    {
        var window = new NodeEditorWindow(
            key,
            node,
            schemeDisplayName,
            sharedSchemeCount,
            _editorGateway,
            _bayesianEditorGateway,
            _canonicalNodes,
            _shellState,
            _sessions.Modalities,
            _sessions.SelectedRevision?.SessionRevisionId,
            _placements.Get(key),
            _windows.Count,
            _localization);
        window.CanonicalMutationCommitted += (_, _) =>
            _ = ReloadGraphSafelyAsync(key.SchemeId);
        window.Closed += (_, _) => OnWindowClosed(key, window);
        return window;
    }

    private void OnWindowClosed(NodeWindowKey key, NodeEditorWindow window)
    {
        _placements.Remember(key, window.CurrentPlacement);
        _windows.Remove(key, window);
        _ = FlushPlacementSafelyAsync();
    }

    private void OnCanonicalGraphChanged(object? sender, CanonicalModelGraphChangedEventArgs args)
    {
        var graph = args.Graph;
        var nodesById = graph.Nodes.ToDictionary(node => node.NodeId, StringComparer.Ordinal);
        foreach (var entry in _windows.Snapshot())
        {
            if (!nodesById.TryGetValue(entry.Key.NodeId, out var node) ||
                node.Lifecycle is ModelObjectLifecycle.Archived)
            {
                entry.Value.Close();
                continue;
            }

            entry.Value.ReconcileCanonicalNode(
                node,
                DisplayScheme(entry.Key.SchemeId),
                _schemes.CountCurrentSchemesUsingNode(node.NodeId));
        }
    }

    private void OnThemeChanged(object? sender, string theme)
    {
        foreach (var entry in _windows.Snapshot())
        {
            entry.Value.ApplyTheme(theme);
        }
    }

    private void OnLanguageChanged(object? sender, EventArgs args)
    {
        foreach (var entry in _windows.Snapshot())
        {
            entry.Value.RefreshLanguage(DisplayScheme(entry.Key.SchemeId));
        }
    }

    private string DisplayScheme(string schemeId)
    {
        var scheme = _schemes.FindScheme(schemeId);
        return scheme is null
            ? ModelDisplayNameResolver.HumanizeIdentifier(schemeId, "Assessment Scheme")
            : ModelDisplayNameResolver.ForScheme(scheme);
    }

    private async Task FlushPlacementSafelyAsync()
    {
        try
        {
            await _placements.FlushAsync();
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            _shellState.AppendDiagnostic($"Node-window placement was not saved: {error.Message}");
        }
    }

    private async Task ReloadGraphSafelyAsync(string schemeId)
    {
        try
        {
            await _modelStudio.LoadGraphAsync(schemeId);
        }
        catch (Exception error)
        {
            _shellState.AppendDiagnostic(
                $"The graph could not reconcile a committed node mutation: {error.Message}");
        }
    }
}
