namespace PilotAssessment.Desktop.Core.State;

public readonly record struct GraphViewportPanOrigin(
    double PointerX,
    double PointerY,
    double HorizontalOffset,
    double VerticalOffset);

public readonly record struct GraphViewportOffset(
    double Horizontal,
    double Vertical);

public static class GraphViewportPan
{
    public static GraphViewportOffset Calculate(
        GraphViewportPanOrigin origin,
        double pointerX,
        double pointerY,
        double maximumHorizontalOffset,
        double maximumVerticalOffset)
    {
        var horizontal = origin.HorizontalOffset - (pointerX - origin.PointerX);
        var vertical = origin.VerticalOffset - (pointerY - origin.PointerY);
        return new GraphViewportOffset(
            Math.Clamp(horizontal, 0, Math.Max(0, maximumHorizontalOffset)),
            Math.Clamp(vertical, 0, Math.Max(0, maximumVerticalOffset)));
    }
}
