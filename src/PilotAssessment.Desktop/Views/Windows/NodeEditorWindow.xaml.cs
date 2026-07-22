using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

using PilotAssessment.Desktop.Controls.Editors;
using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.Protocol;
using PilotAssessment.Desktop.Core.State;
using PilotAssessment.Desktop.Core.ViewModels;
using PilotAssessment.Desktop.ViewModels;

using Windows.Graphics;

namespace PilotAssessment.Desktop.Views.Windows;

public sealed partial class NodeEditorWindow : Window
{
    private readonly NodeWindowKey _key;
    private ModelNode _canonicalNode;
    private ModelNode? _pendingCanonicalNode;
    private bool _hasUnsavedChanges;
    private bool _hasExplicitLocalChanges;
    private NodeWindowPlacement _restoredPlacement;
    private string _schemeDisplayName;
    private int _sharedSchemeCount;
    private readonly IModelNodeEditorGateway _editorGateway;
    private readonly IBayesianNodeEditorGateway _bayesianEditorGateway;
    private readonly ApplicationShellState _shellState;
    private readonly AutosaveCoordinator<ModelNode, ModelNode> _autosave;
    private AutosaveState _autosaveState = new(AutosavePhase.Saved, "Saved");
    private readonly ModalityStatusItem[] _sessionAvailability;
    private readonly string? _sessionRevisionId;
    private readonly ILocalizationLookup _localization;
    private RawInputEditorViewModel? _rawInputViewModel;
    private RawInputEditor? _rawInputEditor;
    private EvidenceEditorViewModel? _evidenceViewModel;
    private EvidenceEditor? _evidenceEditor;
    private BnNodeEditorViewModel? _bnViewModel;
    private BnNodeEditor? _bnEditor;

    public NodeEditorWindow(
        NodeWindowKey key,
        ModelNode node,
        string schemeDisplayName,
        int sharedSchemeCount,
        IModelNodeEditorGateway editorGateway,
        IBayesianNodeEditorGateway bayesianEditorGateway,
        CanonicalObjectStore<ModelNode> canonicalStore,
        ApplicationShellState shellState,
        IEnumerable<ModalityStatusItem> sessionAvailability,
        string? sessionRevisionId,
        NodeWindowPlacement? savedPlacement,
        int cascadeIndex,
        ILocalizationLookup localization)
    {
        _key = key;
        _canonicalNode = node;
        _schemeDisplayName = schemeDisplayName;
        _sharedSchemeCount = sharedSchemeCount;
        _editorGateway = editorGateway;
        _bayesianEditorGateway = bayesianEditorGateway;
        _shellState = shellState;
        _sessionAvailability = sessionAvailability.ToArray();
        _sessionRevisionId = sessionRevisionId;
        _localization = localization;
        _autosave = new AutosaveCoordinator<ModelNode, ModelNode>(
            $"{key.ProjectId}\u001f{node.NodeId}",
            canonicalStore,
            ModelNodeDraftRebaser.Rebase,
            async (draft, transactionId, cancellationToken) =>
                (await editorGateway.UpdateNodeAsync(
                    draft,
                    draft.SemanticRevision,
                    draft.LayoutRevision,
                    "expert.desktop",
                    transactionId,
                    cancellationToken)).Node,
            ClassifyAutosaveFailure,
            () => $"tx.desktop.node-autosave.{Guid.NewGuid():N}");
        _autosave.SeedCanonical(node);
        InitializeComponent();

        _autosave.StateChanged += OnAutosaveStateChanged;
        _autosave.Committed += OnAutosaveCommitted;
        _localization.LanguageChanged += OnLanguageChanged;

        AppWindow.SetIcon(DesktopAssetLocator.AppIconPath(AppContext.BaseDirectory));
        AppWindow.Changed += OnAppWindowChanged;
        _restoredPlacement = RestorePlacement(savedPlacement, cascadeIndex);
        RenderCanonicalNode();
        CreateEditorSurface();
        Closed += OnClosed;
    }

    public NodeWindowKey Key => _key;

    public bool HasUnsavedChanges => _hasUnsavedChanges;

    public bool HasCanonicalConflict => _pendingCanonicalNode is not null;

    public event EventHandler? CanonicalMutationCommitted;

    public NodeWindowPlacement CurrentPlacement => _restoredPlacement with
    {
        IsMaximized = AppWindow.Presenter is OverlappedPresenter
        {
            State: OverlappedPresenterState.Maximized,
        },
    };

    public void FocusWindow()
    {
        if (AppWindow.Presenter is OverlappedPresenter
            {
                State: OverlappedPresenterState.Minimized,
            } presenter)
        {
            presenter.Restore();
        }

        Activate();
    }

    public void ApplyTheme(string theme)
    {
        RootGrid.RequestedTheme = theme switch
        {
            "Light" => ElementTheme.Light,
            "Dark" => ElementTheme.Dark,
            _ => ElementTheme.Default,
        };
    }

    public Task FlushAutosaveAsync(CancellationToken cancellationToken = default) =>
        _autosave.FlushAsync(cancellationToken);

    public void RefreshLanguage(string schemeDisplayName)
    {
        _schemeDisplayName = schemeDisplayName;
        RenderCanonicalNode();
    }

    public void ReconcileCanonicalNode(
        ModelNode node,
        string schemeDisplayName,
        int sharedSchemeCount)
    {
        ArgumentNullException.ThrowIfNull(node);
        if (!string.Equals(node.NodeId, _key.NodeId, StringComparison.Ordinal))
        {
            throw new ArgumentException("A node editor window cannot change node identity.", nameof(node));
        }

        _schemeDisplayName = schemeDisplayName;
        _sharedSchemeCount = sharedSchemeCount;
        var changed = node.SemanticRevision != _canonicalNode.SemanticRevision ||
            node.LayoutRevision != _canonicalNode.LayoutRevision ||
            !string.Equals(node.ContentHash, _canonicalNode.ContentHash, StringComparison.Ordinal) ||
            !string.Equals(node.LayoutHash, _canonicalNode.LayoutHash, StringComparison.Ordinal);
        if (changed && _hasUnsavedChanges)
        {
            _pendingCanonicalNode = node;
            _autosave.AcceptExternalCanonical(node);
            SaveConflictBanner.ShowConflict(_localization["Node_ConflictNewer"]);
            _shellState.SetAutosaveStatus("Conflict");
            RenderSaveState();
            return;
        }

        _canonicalNode = node;
        _pendingCanonicalNode = null;
        _autosave.AcceptExternalCanonical(node);
        SaveConflictBanner.Hide();
        RenderCanonicalNode();
        ApplyCanonicalEditor();
    }

    private NodeWindowPlacement RestorePlacement(
        NodeWindowPlacement? savedPlacement,
        int cascadeIndex)
    {
        var displays = GetDisplayWorkAreas();
        var normalized = NodeWindowPlacementNormalizer.Normalize(savedPlacement, displays);
        if (savedPlacement is null && cascadeIndex > 0)
        {
            var offset = 32 * (cascadeIndex % 7);
            normalized = NodeWindowPlacementNormalizer.Normalize(
                normalized with { X = normalized.X + offset, Y = normalized.Y + offset },
                displays);
        }

        AppWindow.MoveAndResize(new RectInt32(
            normalized.X,
            normalized.Y,
            normalized.Width,
            normalized.Height));
        if (normalized.IsMaximized && AppWindow.Presenter is OverlappedPresenter presenter)
        {
            presenter.Maximize();
        }

        return normalized;
    }

    private void OnAppWindowChanged(AppWindow sender, AppWindowChangedEventArgs args)
    {
        if (sender.Presenter is OverlappedPresenter
            {
                State: not OverlappedPresenterState.Restored,
            })
        {
            return;
        }

        if (args.DidPositionChange || args.DidSizeChange || args.DidPresenterChange)
        {
            _restoredPlacement = new NodeWindowPlacement(
                sender.Position.X,
                sender.Position.Y,
                sender.Size.Width,
                sender.Size.Height,
                IsMaximized: false);
        }
    }

    private void OnReloadCanonicalRequested(object? sender, EventArgs args)
    {
        if (_pendingCanonicalNode is null)
        {
            return;
        }

        _canonicalNode = _pendingCanonicalNode;
        _pendingCanonicalNode = null;
        _hasExplicitLocalChanges = false;
        _autosave.ReloadConflict(_canonicalNode);
        SaveConflictBanner.Hide();
        RenderCanonicalNode();
        ApplyCanonicalEditor();
    }

    private async void OnReapplyCanonicalRequested(object? sender, EventArgs args)
    {
        if (_pendingCanonicalNode is null)
        {
            return;
        }

        var canonical = _pendingCanonicalNode;
        _pendingCanonicalNode = null;
        _canonicalNode = canonical;
        AcceptCanonicalEditorBase(canonical);
        SaveConflictBanner.Hide();
        try
        {
            await _autosave.ReapplyConflictAsync(canonical);
        }
        catch (InvalidOperationException) when (_hasExplicitLocalChanges)
        {
            _autosave.ReloadConflict(canonical);
            RenderCanonicalNode();
            RenderSaveState();
        }
        catch (Exception error)
        {
            SaveConflictBanner.ShowBlocked(error.Message);
        }
    }

    private async void OnRetryAutosaveRequested(object? sender, EventArgs args)
    {
        try
        {
            await _autosave.RetryAsync();
        }
        catch (Exception error)
        {
            SaveConflictBanner.ShowBlocked(error.Message);
        }
    }

    private void RenderCanonicalNode()
    {
        var displayName = PrimaryName(_canonicalNode);
        Title = _localization.Format("Node_WindowTitle", displayName);
        NodeNameText.Text = displayName;
        NodeIdentityText.Text = _canonicalNode.NodeId;
        NodeKindText.Text = DisplayKind(_canonicalNode.NodeKind);
        TaskSchemeText.Text = _schemeDisplayName;
        SharedUsageText.Text = _sharedSchemeCount == 1
            ? _localization["Node_UsedByOne"]
            : _localization.Format("Node_UsedByMany", _sharedSchemeCount);
        WindowKeyText.Text = $"{_key.ProjectId} / {_key.SchemeId} / {_key.NodeId}";
        TechnicalStatusText.Text = DisplayTechnicalStatus(_canonicalNode.TechnicalStatus);
        SemanticRevisionText.Text = _canonicalNode.SemanticRevision.ToString();
        LayoutRevisionText.Text = _canonicalNode.LayoutRevision.ToString();
        GroupText.Text = string.IsNullOrWhiteSpace(_canonicalNode.Group)
            ? _localization["Common_NoGroup"]
            : _canonicalNode.Group;
        TagsText.Text = _canonicalNode.Tags.Length == 0
            ? _localization["Common_NoTags"]
            : string.Join(", ", _canonicalNode.Tags);
        RenderSaveState();
    }

    private void RenderSaveState()
    {
        _hasUnsavedChanges = _hasExplicitLocalChanges ||
            _pendingCanonicalNode is not null ||
            _autosaveState.Phase is AutosavePhase.Pending or AutosavePhase.Saving or
                AutosavePhase.OfflineRetry or AutosavePhase.Conflict or AutosavePhase.Blocked;
        var text = _pendingCanonicalNode is not null
            ? _localization["Node_SaveConflict"]
            : _autosaveState.Phase switch
            {
                AutosavePhase.Pending => _localization["Node_SavePending"],
                AutosavePhase.Saving => _localization["Node_SaveSaving"],
                AutosavePhase.OfflineRetry => _localization["Node_SaveOffline"],
                AutosavePhase.Conflict => _localization["Node_SaveConflict"],
                AutosavePhase.Blocked => _autosaveState.Message,
                _ => _localization.Format("Node_SaveSaved", _canonicalNode.SemanticRevision),
            };
        SaveStateText.Text = _hasExplicitLocalChanges
            ? _localization.Format("Node_ExplicitPending", text)
            : text;
    }

    private void OnLanguageChanged(object? sender, EventArgs args)
    {
        RenderCanonicalNode();
        _evidenceViewModel?.RefreshLanguage();
        _bnViewModel?.RefreshLanguage();
    }

    private void CreateEditorSurface()
    {
        switch (_canonicalNode.Definition)
        {
            case RawInputNodeDefinition:
                _rawInputViewModel = new RawInputEditorViewModel(
                    _canonicalNode,
                    _sessionAvailability);
                _rawInputEditor = new RawInputEditor();
                _rawInputEditor.SetViewModel(_rawInputViewModel);
                _rawInputEditor.LocalEditChanged += OnLocalEditChanged;
                EditorHost.Content = _rawInputEditor;
                break;
            case EvidenceNodeDefinition:
                _evidenceViewModel = new EvidenceEditorViewModel(
                    _canonicalNode,
                    _key.SchemeId,
                    _sessionRevisionId,
                    _editorGateway,
                    _bayesianEditorGateway,
                    _localization);
                _evidenceEditor = new EvidenceEditor();
                _evidenceEditor.SetViewModel(_evidenceViewModel);
                _evidenceEditor.LocalEditChanged += OnLocalEditChanged;
                _evidenceViewModel.CanonicalNodeCommitted += OnCanonicalNodeCommitted;
                EditorHost.Content = _evidenceEditor;
                _ = InitializeEvidenceEditorAsync();
                break;
            case BnNodeDefinition:
                _bnViewModel = new BnNodeEditorViewModel(
                    _canonicalNode,
                    _key.SchemeId,
                    _editorGateway,
                    _bayesianEditorGateway,
                    _localization);
                _bnEditor = new BnNodeEditor();
                _bnEditor.SetViewModel(_bnViewModel);
                _bnEditor.LocalEditChanged += OnLocalEditChanged;
                _bnEditor.CanonicalNodeCommitted += OnCanonicalNodeCommitted;
                EditorHost.Content = _bnEditor;
                _ = InitializeBnEditorAsync();
                break;
        }
    }

    private void ApplyCanonicalEditor()
    {
        if (_rawInputViewModel is not null)
        {
            _rawInputViewModel.ApplyCanonical(_canonicalNode);
            _rawInputEditor?.ResetDirtyBoundary();
        }
        if (_evidenceViewModel is not null)
        {
            _evidenceViewModel.ApplyCanonical(
                _canonicalNode,
                _key.SchemeId,
                _sessionRevisionId);
            _evidenceEditor?.RefreshCanonical();
        }
        if (_bnViewModel is not null)
        {
            _bnViewModel.ApplyCanonical(_canonicalNode, _key.SchemeId);
            _bnEditor?.RefreshCanonical();
        }
    }

    private void AcceptCanonicalEditorBase(ModelNode canonical)
    {
        _rawInputViewModel?.AcceptCanonicalBase(canonical);
        _evidenceViewModel?.AcceptCanonicalBase(canonical);
        _bnViewModel?.AcceptCanonicalBase(canonical);
    }

    private ModelNode BuildEditorDraft() =>
        _rawInputViewModel?.BuildUpdatedNode()
        ?? _evidenceViewModel?.BuildUpdatedNode()
        ?? _bnViewModel?.BuildUpdatedNode()
        ?? throw new InvalidOperationException("This node type has no editable autosave intent.");

    private async Task InitializeEvidenceEditorAsync()
    {
        try
        {
            if (_evidenceEditor is not null)
            {
                await _evidenceEditor.InitializeAsync();
            }
        }
        catch (Exception error)
        {
            SaveStateText.Text = _localization.Format("Node_EvidenceMetadataError", error.Message);
        }
    }

    private async Task InitializeBnEditorAsync()
    {
        try
        {
            if (_bnEditor is not null)
            {
                await _bnEditor.InitializeAsync();
            }
        }
        catch (Exception error)
        {
            SaveStateText.Text = _localization.Format("Node_BnMetadataError", error.Message);
        }
    }

    private void OnCanonicalNodeCommitted(object? sender, CanonicalNodeCommittedEventArgs args)
    {
        _canonicalNode = args.Node;
        _pendingCanonicalNode = null;
        _hasExplicitLocalChanges = false;
        _autosave.AcceptExternalCanonical(args.Node);
        AcceptCanonicalEditorBase(args.Node);
        SaveConflictBanner.Hide();
        RenderCanonicalNode();
        CanonicalMutationCommitted?.Invoke(this, EventArgs.Empty);
    }

    private void OnLocalEditChanged(object? sender, NodeEditorLocalEditEventArgs args)
    {
        if (args.Persistence is NodeEditorEditPersistence.ExplicitCommit)
        {
            _hasExplicitLocalChanges = true;
            RenderSaveState();
            return;
        }

        try
        {
            _autosave.Queue(BuildEditorDraft());
        }
        catch (Exception error) when (error is ArgumentException or InvalidOperationException or System.Text.Json.JsonException)
        {
            _autosave.ReportBlocked(error);
        }
    }

    private void OnAutosaveStateChanged(object? sender, AutosaveStateChangedEventArgs args)
    {
        _autosaveState = args.State;
        _shellState.SetAutosaveStatus(ShellAutosaveStatus(args.State.Phase));
        switch (args.State.Phase)
        {
            case AutosavePhase.OfflineRetry:
                SaveConflictBanner.ShowOffline(args.State.Message);
                break;
            case AutosavePhase.Conflict:
                SaveConflictBanner.ShowConflict(args.State.Message);
                _ = LoadConflictCanonicalAsync();
                break;
            case AutosavePhase.Blocked:
                SaveConflictBanner.ShowBlocked(args.State.Message);
                break;
            case AutosavePhase.Pending:
            case AutosavePhase.Saving:
            case AutosavePhase.Saved:
                if (_pendingCanonicalNode is null)
                {
                    SaveConflictBanner.Hide();
                }
                break;
        }
        RenderSaveState();
    }

    private void OnAutosaveCommitted(
        object? sender,
        AutosaveCommittedEventArgs<ModelNode, ModelNode> args)
    {
        _canonicalNode = args.Canonical;
        _pendingCanonicalNode = null;
        if (args.PendingDraft is not null || _hasExplicitLocalChanges)
        {
            AcceptCanonicalEditorBase(args.Canonical);
        }
        else
        {
            ApplyCanonicalEditor();
        }
        RenderCanonicalNode();
        CanonicalMutationCommitted?.Invoke(this, EventArgs.Empty);
    }

    private async Task LoadConflictCanonicalAsync()
    {
        try
        {
            var graph = await _bayesianEditorGateway.GetGraphAsync(_key.SchemeId);
            var current = graph.Nodes.Single(node => node.NodeId == _key.NodeId);
            _pendingCanonicalNode = current;
            _autosave.AcceptExternalCanonical(current);
            SaveConflictBanner.ShowConflict(
                _localization.Format("Node_ConflictRevision", current.SemanticRevision));
            RenderSaveState();
        }
        catch (Exception error)
        {
            SaveConflictBanner.ShowBlocked(
                _localization.Format("Node_ConflictLoadFailed", error.Message));
        }
    }

    private void OnClosed(object sender, WindowEventArgs args)
    {
        if (_rawInputEditor is not null)
        {
            _rawInputEditor.LocalEditChanged -= OnLocalEditChanged;
        }
        if (_evidenceEditor is not null)
        {
            _evidenceEditor.LocalEditChanged -= OnLocalEditChanged;
        }
        if (_evidenceViewModel is not null)
        {
            _evidenceViewModel.CanonicalNodeCommitted -= OnCanonicalNodeCommitted;
        }
        if (_bnEditor is not null)
        {
            _bnEditor.LocalEditChanged -= OnLocalEditChanged;
            _bnEditor.CanonicalNodeCommitted -= OnCanonicalNodeCommitted;
        }
        _evidenceViewModel?.Dispose();
        _autosave.StateChanged -= OnAutosaveStateChanged;
        _autosave.Committed -= OnAutosaveCommitted;
        _localization.LanguageChanged -= OnLanguageChanged;
        _ = FlushAndDisposeAutosaveAsync();
    }

    private async Task FlushAndDisposeAutosaveAsync()
    {
        try
        {
            await _autosave.FlushAsync();
        }
        catch (Exception error)
        {
            _shellState.AppendDiagnostic($"Node autosave did not flush during close: {error.Message}");
        }
        finally
        {
            await _autosave.DisposeAsync();
        }
    }

    private static AutosaveFailureKind ClassifyAutosaveFailure(Exception error)
    {
        if (error is JsonRpcRemoteException remote &&
            remote.DataElement is { ValueKind: System.Text.Json.JsonValueKind.Object } data &&
            data.TryGetProperty("error_code", out var code) &&
            string.Equals(
                code.GetString(),
                "MODEL_REVISION_CONFLICT",
                StringComparison.Ordinal))
        {
            return AutosaveFailureKind.Conflict;
        }
        if (error is IOException ||
            error is InvalidOperationException invalid &&
            invalid.Message.Contains("not connected", StringComparison.OrdinalIgnoreCase))
        {
            return AutosaveFailureKind.Offline;
        }
        return AutosaveFailureKind.Blocked;
    }

    private static string ShellAutosaveStatus(AutosavePhase phase) => phase switch
    {
        AutosavePhase.Pending => "Pending changes",
        AutosavePhase.Saving => "Saving",
        AutosavePhase.OfflineRetry => "Offline / Retry",
        AutosavePhase.Conflict => "Conflict",
        AutosavePhase.Blocked => "Blocked",
        _ => "Pending changes",
    };

    private static IReadOnlyList<DisplayWorkArea> GetDisplayWorkAreas()
    {
        var areas = DisplayArea.FindAll();
        var result = new List<DisplayWorkArea>(areas.Count);
        for (var index = 0; index < areas.Count; index++)
        {
            var area = areas[index];
            var outer = area.OuterBounds;
            var work = area.WorkArea;
            result.Add(new DisplayWorkArea(
                outer.X + work.X,
                outer.Y + work.Y,
                work.Width,
                work.Height,
                area.IsPrimary));
        }

        return result;
    }

    private static string PrimaryName(ModelNode node) =>
        ModelDisplayNameResolver.ForNode(node, preferShort: false);

    private string DisplayKind(ModelNodeKind kind) => kind switch
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
}
