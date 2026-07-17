using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

using PilotAssessment.Desktop.Core.State;

using Windows.Foundation;

namespace PilotAssessment.Desktop.Controls.Graph;

public sealed class GraphVirtualizingLayout : VirtualizingLayout
{
    private const double RealizationBuffer = 180;

    protected override void InitializeForContextCore(VirtualizingLayoutContext context)
    {
        base.InitializeForContextCore(context);
        context.LayoutState = new GraphLayoutState();
    }

    protected override void UninitializeForContextCore(VirtualizingLayoutContext context)
    {
        context.LayoutState = null;
        base.UninitializeForContextCore(context);
    }

    protected override Size MeasureOverride(
        VirtualizingLayoutContext context,
        Size availableSize)
    {
        var state = (GraphLayoutState?)context.LayoutState ?? new GraphLayoutState();
        context.LayoutState = state;
        var realization = Inflate(context.RealizationRect, RealizationBuffer);
        state.Elements.Clear();
        state.Bounds.Clear();
        var extentWidth = GraphProjection.MinimumExtentWidth;
        var extentHeight = GraphProjection.MinimumExtentHeight;
        var radius = GraphProjection.NodeDiameter / 2;

        for (var index = 0; index < context.ItemCount; index++)
        {
            if (context.GetItemAt(index) is not GraphNodeProjection node)
            {
                continue;
            }

            var bounds = new Rect(
                node.X - radius,
                node.Y - radius,
                GraphProjection.NodeDiameter,
                GraphProjection.NodeDiameter);
            extentWidth = Math.Max(extentWidth, bounds.Right + GraphProjection.CanvasPadding);
            extentHeight = Math.Max(extentHeight, bounds.Bottom + GraphProjection.CanvasPadding);
            if (!Intersects(bounds, realization))
            {
                continue;
            }

            var element = context.GetOrCreateElementAt(index);
            state.Elements[index] = element;
            state.Bounds[index] = bounds;
            element.Measure(new Size(bounds.Width, bounds.Height));
        }

        return new Size(extentWidth, extentHeight);
    }

    protected override Size ArrangeOverride(
        VirtualizingLayoutContext context,
        Size finalSize)
    {
        if (context.LayoutState is not GraphLayoutState state)
        {
            return finalSize;
        }

        foreach (var entry in state.Elements)
        {
            if (state.Bounds.TryGetValue(entry.Key, out var bounds))
            {
                entry.Value.Arrange(bounds);
            }
        }

        return finalSize;
    }

    private static Rect Inflate(Rect value, double amount) => new(
        value.X - amount,
        value.Y - amount,
        value.Width + (amount * 2),
        value.Height + (amount * 2));

    private static bool Intersects(Rect left, Rect right) =>
        left.Left < right.Right &&
        left.Right > right.Left &&
        left.Top < right.Bottom &&
        left.Bottom > right.Top;

    private sealed class GraphLayoutState
    {
        public Dictionary<int, UIElement> Elements { get; } = [];
        public Dictionary<int, Rect> Bounds { get; } = [];
    }
}
