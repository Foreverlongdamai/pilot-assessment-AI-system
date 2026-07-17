using PilotAssessment.Desktop.Core.State;

namespace PilotAssessment.Desktop.UnitTests.State;

public sealed class NodeWindowRegistryTests
{
    [Fact]
    public void Key_identity_includes_project_scheme_and_node()
    {
        var key = new NodeWindowKey("project-a", "scheme-a", "node-a");

        Assert.Equal(key, new NodeWindowKey("project-a", "scheme-a", "node-a"));
        Assert.NotEqual(key, new NodeWindowKey("project-b", "scheme-a", "node-a"));
        Assert.NotEqual(key, new NodeWindowKey("project-a", "scheme-b", "node-a"));
        Assert.NotEqual(key, new NodeWindowKey("project-a", "scheme-a", "node-b"));
    }

    [Fact]
    public void Reopening_the_same_key_focuses_the_existing_window()
    {
        var registry = new NodeWindowRegistryState<FakeWindow>();
        var key = new NodeWindowKey("project-a", "scheme-a", "node-a");
        var first = registry.OpenOrFocus(key, () => new FakeWindow(), window => window.Focus(), out var created);

        var second = registry.OpenOrFocus(
            key,
            () => throw new InvalidOperationException("A duplicate window must not be created."),
            window => window.Focus(),
            out var reopenedCreated);

        Assert.True(created);
        Assert.False(reopenedCreated);
        Assert.Same(first, second);
        Assert.Equal(1, first.FocusCount);
        Assert.Equal(1, registry.Count);
    }

    [Fact]
    public void The_same_node_can_have_independent_windows_in_other_contexts()
    {
        var registry = new NodeWindowRegistryState<FakeWindow>();
        var first = registry.OpenOrFocus(
            new NodeWindowKey("project-a", "scheme-a", "node-a"),
            () => new FakeWindow(),
            _ => { },
            out _);
        var second = registry.OpenOrFocus(
            new NodeWindowKey("project-a", "scheme-b", "node-a"),
            () => new FakeWindow(),
            _ => { },
            out _);

        Assert.NotSame(first, second);
        Assert.Equal(2, registry.Count);
    }

    [Fact]
    public void Close_cleanup_only_removes_the_registered_instance()
    {
        var registry = new NodeWindowRegistryState<FakeWindow>();
        var key = new NodeWindowKey("project-a", "scheme-a", "node-a");
        var window = registry.OpenOrFocus(key, () => new FakeWindow(), _ => { }, out _);

        Assert.False(registry.Remove(key, new FakeWindow()));
        Assert.True(registry.Remove(key, window));
        Assert.False(registry.Remove(key, window));
        Assert.Empty(registry.Snapshot());
    }

    [Fact]
    public void Off_screen_placement_recovers_to_the_primary_display()
    {
        var displays = new[]
        {
            new DisplayWorkArea(0, 0, 1920, 1040, IsPrimary: true),
            new DisplayWorkArea(1920, 0, 1280, 984),
        };

        var normalized = NodeWindowPlacementNormalizer.Normalize(
            new NodeWindowPlacement(5000, 5000, 900, 700, IsMaximized: true),
            displays);

        Assert.Equal(new NodeWindowPlacement(510, 170, 900, 700, IsMaximized: true), normalized);
    }

    [Fact]
    public void Oversized_placement_is_clamped_to_its_visible_display()
    {
        var normalized = NodeWindowPlacementNormalizer.Normalize(
            new NodeWindowPlacement(2100, 100, 4000, 3000, IsMaximized: false),
            [new DisplayWorkArea(1920, 0, 1280, 984, IsPrimary: true)]);

        Assert.Equal(new NodeWindowPlacement(1920, 0, 1280, 984, IsMaximized: false), normalized);
    }

    private sealed class FakeWindow
    {
        public int FocusCount { get; private set; }

        public void Focus() => FocusCount++;
    }
}
