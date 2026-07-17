namespace PilotAssessment.Desktop.Core.State;

public sealed record NodeWindowKey
{
    public NodeWindowKey(string projectId, string schemeId, string nodeId)
    {
        ProjectId = RequireIdentifier(projectId, nameof(projectId));
        SchemeId = RequireIdentifier(schemeId, nameof(schemeId));
        NodeId = RequireIdentifier(nodeId, nameof(nodeId));
    }

    public string ProjectId { get; }

    public string SchemeId { get; }

    public string NodeId { get; }

    private static string RequireIdentifier(string value, string parameterName)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(value, parameterName);
        return value.Trim();
    }
}

public sealed record NodeWindowPlacement(
    int X,
    int Y,
    int Width,
    int Height,
    bool IsMaximized);

public sealed record DisplayWorkArea(
    int X,
    int Y,
    int Width,
    int Height,
    bool IsPrimary = false);

public static class NodeWindowPlacementNormalizer
{
    public const int DefaultWidth = 960;
    public const int DefaultHeight = 760;
    public const int MinimumWidth = 640;
    public const int MinimumHeight = 480;

    public static NodeWindowPlacement Normalize(
        NodeWindowPlacement? saved,
        IReadOnlyList<DisplayWorkArea> displays)
    {
        ArgumentNullException.ThrowIfNull(displays);
        var usableDisplays = displays
            .Where(display => display.Width > 0 && display.Height > 0)
            .ToArray();
        if (usableDisplays.Length == 0)
        {
            throw new ArgumentException("At least one usable display work area is required.", nameof(displays));
        }

        var primary = usableDisplays.FirstOrDefault(display => display.IsPrimary) ?? usableDisplays[0];
        if (saved is null || saved.Width <= 0 || saved.Height <= 0)
        {
            return CenterIn(primary, DefaultWidth, DefaultHeight, false);
        }

        var target = usableDisplays
            .Select(display => new
            {
                Display = display,
                Intersection = IntersectionArea(saved, display),
            })
            .OrderByDescending(candidate => candidate.Intersection)
            .ThenByDescending(candidate => candidate.Display.IsPrimary)
            .First();
        if (target.Intersection == 0)
        {
            return CenterIn(primary, saved.Width, saved.Height, saved.IsMaximized);
        }

        return ClampTo(target.Display, saved);
    }

    private static NodeWindowPlacement CenterIn(
        DisplayWorkArea display,
        int requestedWidth,
        int requestedHeight,
        bool isMaximized)
    {
        var width = ClampDimension(requestedWidth, MinimumWidth, display.Width);
        var height = ClampDimension(requestedHeight, MinimumHeight, display.Height);
        return new NodeWindowPlacement(
            display.X + Math.Max(0, (display.Width - width) / 2),
            display.Y + Math.Max(0, (display.Height - height) / 2),
            width,
            height,
            isMaximized);
    }

    private static NodeWindowPlacement ClampTo(
        DisplayWorkArea display,
        NodeWindowPlacement placement)
    {
        var width = ClampDimension(placement.Width, MinimumWidth, display.Width);
        var height = ClampDimension(placement.Height, MinimumHeight, display.Height);
        var x = Math.Clamp(placement.X, display.X, display.X + display.Width - width);
        var y = Math.Clamp(placement.Y, display.Y, display.Y + display.Height - height);
        return new NodeWindowPlacement(x, y, width, height, placement.IsMaximized);
    }

    private static int ClampDimension(int value, int minimum, int available) =>
        Math.Min(Math.Max(value, Math.Min(minimum, available)), available);

    private static long IntersectionArea(
        NodeWindowPlacement placement,
        DisplayWorkArea display)
    {
        var left = Math.Max((long)placement.X, display.X);
        var top = Math.Max((long)placement.Y, display.Y);
        var right = Math.Min((long)placement.X + placement.Width, (long)display.X + display.Width);
        var bottom = Math.Min((long)placement.Y + placement.Height, (long)display.Y + display.Height);
        return Math.Max(0, right - left) * Math.Max(0, bottom - top);
    }
}

public sealed class NodeWindowRegistryState<TWindow>
    where TWindow : class
{
    private readonly object _gate = new();
    private readonly Dictionary<NodeWindowKey, TWindow> _windows = [];

    public int Count
    {
        get
        {
            lock (_gate)
            {
                return _windows.Count;
            }
        }
    }

    public TWindow OpenOrFocus(
        NodeWindowKey key,
        Func<TWindow> create,
        Action<TWindow> focus,
        out bool created)
    {
        ArgumentNullException.ThrowIfNull(key);
        ArgumentNullException.ThrowIfNull(create);
        ArgumentNullException.ThrowIfNull(focus);

        lock (_gate)
        {
            if (_windows.TryGetValue(key, out var existing))
            {
                created = false;
                focus(existing);
                return existing;
            }

            var window = create() ?? throw new InvalidOperationException("The window factory returned null.");
            _windows.Add(key, window);
            created = true;
            return window;
        }
    }

    public bool Remove(NodeWindowKey key, TWindow expectedWindow)
    {
        ArgumentNullException.ThrowIfNull(key);
        ArgumentNullException.ThrowIfNull(expectedWindow);
        lock (_gate)
        {
            return _windows.TryGetValue(key, out var current) &&
                ReferenceEquals(current, expectedWindow) &&
                _windows.Remove(key);
        }
    }

    public IReadOnlyList<KeyValuePair<NodeWindowKey, TWindow>> Snapshot()
    {
        lock (_gate)
        {
            return _windows.ToArray();
        }
    }
}
