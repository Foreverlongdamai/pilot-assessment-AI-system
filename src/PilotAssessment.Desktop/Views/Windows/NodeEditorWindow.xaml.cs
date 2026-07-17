using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

using PilotAssessment.Desktop.Controls.Editors;
using PilotAssessment.Desktop.Core.Contracts;
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
    private bool _conflictAcknowledged;
    private NodeWindowPlacement _restoredPlacement;
    private string _schemeDisplayName;
    private int _sharedSchemeCount;
    private readonly IModelNodeEditorGateway _editorGateway;
    private readonly IBayesianNodeEditorGateway _bayesianEditorGateway;
    private readonly ModalityStatusItem[] _sessionAvailability;
    private readonly string? _sessionRevisionId;
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
        IEnumerable<ModalityStatusItem> sessionAvailability,
        string? sessionRevisionId,
        NodeWindowPlacement? savedPlacement,
        int cascadeIndex)
    {
        _key = key;
        _canonicalNode = node;
        _schemeDisplayName = schemeDisplayName;
        _sharedSchemeCount = sharedSchemeCount;
        _editorGateway = editorGateway;
        _bayesianEditorGateway = bayesianEditorGateway;
        _sessionAvailability = sessionAvailability.ToArray();
        _sessionRevisionId = sessionRevisionId;
        InitializeComponent();

        AppWindow.SetIcon("Assets/AppIcon.ico");
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

    public void SetUnsavedChanges(bool hasUnsavedChanges)
    {
        _hasUnsavedChanges = hasUnsavedChanges;
        if (!hasUnsavedChanges && _pendingCanonicalNode is not null)
        {
            _canonicalNode = _pendingCanonicalNode;
            _pendingCanonicalNode = null;
            _conflictAcknowledged = false;
            CanonicalConflictPanel.Visibility = Visibility.Collapsed;
            RenderCanonicalNode();
            ApplyCanonicalEditor();
            return;
        }

        RenderSaveState();
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
            _conflictAcknowledged = false;
            CanonicalConflictPanel.Visibility = Visibility.Visible;
            RenderSaveState();
            return;
        }

        _canonicalNode = node;
        _pendingCanonicalNode = null;
        _conflictAcknowledged = false;
        CanonicalConflictPanel.Visibility = Visibility.Collapsed;
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

    private void OnReloadCanonicalClick(object sender, RoutedEventArgs args)
    {
        if (_pendingCanonicalNode is null)
        {
            return;
        }

        _canonicalNode = _pendingCanonicalNode;
        _pendingCanonicalNode = null;
        _hasUnsavedChanges = false;
        _conflictAcknowledged = false;
        CanonicalConflictPanel.Visibility = Visibility.Collapsed;
        RenderCanonicalNode();
        ApplyCanonicalEditor();
    }

    private void OnKeepEditingClick(object sender, RoutedEventArgs args)
    {
        _conflictAcknowledged = true;
        CanonicalConflictPanel.Visibility = Visibility.Collapsed;
        RenderSaveState();
    }

    private void RenderCanonicalNode()
    {
        var bilingualName = BilingualName(_canonicalNode);
        Title = $"{PrimaryName(_canonicalNode)} — Node Editor";
        NodeNameText.Text = bilingualName;
        NodeIdentityText.Text = _canonicalNode.NodeId;
        NodeKindText.Text = DisplayKind(_canonicalNode.NodeKind);
        TaskSchemeText.Text = $"{_schemeDisplayName} ({_key.SchemeId})";
        SharedUsageText.Text = _sharedSchemeCount == 1
            ? "Used by 1 current task scheme"
            : $"Used by {_sharedSchemeCount} current task schemes";
        WindowKeyText.Text = $"{_key.ProjectId} / {_key.SchemeId} / {_key.NodeId}";
        TechnicalStatusText.Text = _canonicalNode.TechnicalStatus.ToString();
        SemanticRevisionText.Text = _canonicalNode.SemanticRevision.ToString();
        LayoutRevisionText.Text = _canonicalNode.LayoutRevision.ToString();
        GroupText.Text = string.IsNullOrWhiteSpace(_canonicalNode.Group)
            ? "No group"
            : _canonicalNode.Group;
        TagsText.Text = _canonicalNode.Tags.Length == 0
            ? "No tags"
            : string.Join(", ", _canonicalNode.Tags);
        RenderSaveState();
    }

    private void RenderSaveState()
    {
        SaveStateText.Text = _pendingCanonicalNode is not null
            ? _conflictAcknowledged
                ? "Unsaved · canonical conflict pending"
                : "Conflict · choose reload or keep editing"
            : _hasUnsavedChanges
                ? "Unsaved local changes"
                : $"Canonical · rev {_canonicalNode.SemanticRevision}";
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
                    _bayesianEditorGateway);
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
                    _bayesianEditorGateway);
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
            SaveStateText.Text = $"Editor metadata error · {error.Message}";
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
            SaveStateText.Text = $"BN editor metadata error · {error.Message}";
        }
    }

    private void OnCanonicalNodeCommitted(object? sender, CanonicalNodeCommittedEventArgs args)
    {
        _canonicalNode = args.Node;
        _pendingCanonicalNode = null;
        _hasUnsavedChanges = false;
        _conflictAcknowledged = false;
        CanonicalConflictPanel.Visibility = Visibility.Collapsed;
        RenderCanonicalNode();
        CanonicalMutationCommitted?.Invoke(this, EventArgs.Empty);
    }

    private void OnLocalEditChanged(object? sender, EventArgs args) => SetUnsavedChanges(true);

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
    }

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
        node.NameEn ?? node.ShortNameEn ?? node.NameZh ?? node.ShortNameZh ?? node.NodeId;

    private static string BilingualName(ModelNode node)
    {
        var names = new[] { node.NameZh, node.NameEn }
            .Where(name => !string.IsNullOrWhiteSpace(name))
            .Distinct(StringComparer.Ordinal)
            .ToArray();
        return names.Length == 0 ? node.NodeId : string.Join(" / ", names);
    }

    private static string DisplayKind(ModelNodeKind kind) => kind switch
    {
        ModelNodeKind.RawInput => "RAW INPUT / 原始输入",
        ModelNodeKind.Evidence => "EVIDENCE / 证据",
        _ => "BN NODE / 贝叶斯节点",
    };
}
