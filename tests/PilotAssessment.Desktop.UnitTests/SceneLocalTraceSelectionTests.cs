using System.Text.Json;

using PilotAssessment.Desktop.Core.SceneAssessment;

namespace PilotAssessment.Desktop.UnitTests;

public sealed class SceneLocalTraceSelectionTests
{
    [Fact]
    public void DrawingRunsBreakAtMissingFramesAndPhaseBoundariesWithoutRecalculatingScores()
    {
        var points = new[]
        {
            Point(0, "lower", 82.123), Point(1, "lower", 42.789),
            Point(2, "lower", null, "insufficient_evidence"), Point(3, "lower", 61),
            Point(4, "upper", 91), Point(5, "upper", 92),
        };
        var runs = SceneLocalTraceSelection.ContinuousRuns(points);
        Assert.Equal(3, runs.Count);
        Assert.Equal([0, 1], runs[0]);
        Assert.Equal([3], runs[1]);
        Assert.Equal([4, 5], runs[2]);
        Assert.Equal(82.123, points[0].Score);
        Assert.Equal(42.789, points[1].Score);
        Assert.Null(points[2].Score);
    }

    [Fact]
    public void DrawingDoesNotConnectAcrossARealGapWhenWindowsShareNoObservation()
    {
        var points = new[] { Point(0, "hold", 80), Point(1, "hold", 70), Point(20, "hold", 40), Point(21, "hold", 50) };
        points[2].ObservedStartS = 20;
        points[3].ObservedStartS = 20;
        var runs = SceneLocalTraceSelection.ContinuousRuns(points);
        Assert.Equal(2, runs.Count);
        Assert.Equal([0, 1], runs[0]);
        Assert.Equal([2, 3], runs[1]);
        Assert.Equal(2, SceneLocalTraceSelection.FindNearestPoint(points, 20));
    }

    [Fact]
    public void InitialShortWindowRemainsVisibleButInvalidOrUnorderedValuesAreNotConnected()
    {
        var points = new[]
        {
            Point(0, "hold", 80), Point(1, "hold", double.NaN), Point(2, "hold", 101),
            Point(3, "hold", 50), Point(3, "hold", 40),
        };
        points[0].WindowComplete = false;
        var runs = SceneLocalTraceSelection.ContinuousRuns(points);
        Assert.Equal(3, runs.Count);
        Assert.Equal([0], runs[0]);
        Assert.Equal([3], runs[1]);
        Assert.Equal([4], runs[2]);
    }

    [Fact]
    public void CursorSelectsActualMissingObservationInsteadOfJumpingAcrossGap()
    {
        var points = new[] { Point(10, "hold", 80), Point(11, "hold", null, "insufficient_evidence"), Point(12, "hold", 40) };
        Assert.Equal(1, SceneLocalTraceSelection.FindNearestPoint(points, 11.1));
        Assert.Equal(0, SceneLocalTraceSelection.FindNearestPoint(points, 0));
        Assert.Equal(2, SceneLocalTraceSelection.FindNearestPoint(points, 99));
        Assert.Equal(-1, SceneLocalTraceSelection.FindNearestPoint([], 0));
    }

    [Fact]
    public void LocalTracePointCannotSilentlyInventMissingTimeOrWindowMetadata()
    {
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize("""
            {"frame_index":0,"phase_id":"hold","status":"complete","score":90,"posterior":[0.05,0.1,0.85]}
            """, SceneJsonContext.Default.SceneSkillLocalPoint));
    }

    private static SceneSkillLocalPoint Point(double time, string phase, double? score, string status = "complete") => new()
    {
        TimestampS = time, PhaseId = phase, Score = score, Status = status,
        Posterior = score is null ? null : [.1, .2, .7],
    };
}
