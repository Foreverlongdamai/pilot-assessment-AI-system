using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;

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

    public NodeEditorWindow(
        NodeWindowKey key,
        ModelNode node,
        string schemeDisplayName,
        int sharedSchemeCount,
        NodeWindowPlacement? savedPlacement,
        int cascadeIndex)
    {
        _key = key;
        _canonicalNode = node;
        _schemeDisplayName = schemeDisplayName;
        _sharedSchemeCount = sharedSchemeCount;
        InitializeComponent();

        AppWindow.SetIcon("Assets/AppIcon.ico");
        AppWindow.Changed += OnAppWindowChanged;
        _restoredPlacement = RestorePlacement(savedPlacement, cascadeIndex);
        RenderCanonicalNode();
    }

    public NodeWindowKey Key => _key;

    public bool HasUnsavedChanges => _hasUnsavedChanges;

    public bool HasCanonicalConflict => _pendingCanonicalNode is not null;

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
