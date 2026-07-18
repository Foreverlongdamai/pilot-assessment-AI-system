using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

using PilotAssessment.Desktop.Core.State;

using Windows.Foundation;

namespace PilotAssessment.Desktop.Controls.Graph;

public sealed class GraphVirtualizingLayout : VirtualizingLayout
{
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
        state.Elements.Clear();
        state.Bounds.Clear();
        var nodes = new GraphNodeProjection[context.ItemCount];
        for (var index = 0; index < nodes.Length; index++)
        {
            nodes[index] = context.GetItemAt(index) as GraphNodeProjection
                ?? throw new InvalidOperationException(
                    $"Graph layout item {index} is not a GraphNodeProjection.");
        }

        var viewport = context.RealizationRect;
        var plan = GraphViewportRealization.Plan(
            nodes,
            new GraphViewportRect(viewport.X, viewport.Y, viewport.Width, viewport.Height));
        foreach (var item in plan.RealizedNodes)
        {
            var element = context.GetOrCreateElementAt(item.Index);
            var bounds = new Rect(
                item.Bounds.X,
                item.Bounds.Y,
                item.Bounds.Width,
                item.Bounds.Height);
            state.Elements[item.Index] = element;
            state.Bounds[item.Index] = bounds;
            element.Measure(new Size(bounds.Width, bounds.Height));
        }

        return new Size(plan.ExtentWidth, plan.ExtentHeight);
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

    private sealed class GraphLayoutState
    {
        public Dictionary<int, UIElement> Elements { get; } = [];
        public Dictionary<int, Rect> Bounds { get; } = [];
    }
}
