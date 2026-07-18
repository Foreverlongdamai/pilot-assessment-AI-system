namespace PilotAssessment.Desktop.Core.State;

public readonly record struct GraphViewportRect(
    double X,
    double Y,
    double Width,
    double Height)
{
    public double Left => X;
    public double Top => Y;
    public double Right => X + Width;
    public double Bottom => Y + Height;

    public GraphViewportRect Inflate(double amount) => new(
        X - amount,
        Y - amount,
        Width + (amount * 2),
        Height + (amount * 2));

    public bool Intersects(GraphViewportRect other) =>
        Left < other.Right &&
        Right > other.Left &&
        Top < other.Bottom &&
        Bottom > other.Top;
}

public sealed record GraphRealizedNode(
    int Index,
    GraphViewportRect Bounds);

public sealed record GraphRealizationPlan(
    IReadOnlyList<GraphRealizedNode> RealizedNodes,
    double ExtentWidth,
    double ExtentHeight);

public static class GraphViewportRealization
{
    public const double DefaultBuffer = 180;

    public static GraphRealizationPlan Plan(
        IReadOnlyList<GraphNodeProjection> nodes,
        GraphViewportRect viewport,
        double buffer = DefaultBuffer)
    {
        ArgumentNullException.ThrowIfNull(nodes);
        if (buffer < 0 || !double.IsFinite(buffer))
        {
            throw new ArgumentOutOfRangeException(nameof(buffer));
        }

        var realizationViewport = viewport.Inflate(buffer);
        var radius = GraphProjection.NodeDiameter / 2;
        var extentWidth = GraphProjection.MinimumExtentWidth;
        var extentHeight = GraphProjection.MinimumExtentHeight;
        var realized = new List<GraphRealizedNode>();

        for (var index = 0; index < nodes.Count; index++)
        {
            var node = nodes[index];
            var bounds = new GraphViewportRect(
                node.X - radius,
                node.Y - radius,
                GraphProjection.NodeDiameter,
                GraphProjection.NodeDiameter);
            extentWidth = Math.Max(
                extentWidth,
                bounds.Right + GraphProjection.CanvasPadding);
            extentHeight = Math.Max(
                extentHeight,
                bounds.Bottom + GraphProjection.CanvasPadding);
            if (bounds.Intersects(realizationViewport))
            {
                realized.Add(new GraphRealizedNode(index, bounds));
            }
        }

        return new GraphRealizationPlan(realized, extentWidth, extentHeight);
    }
}
