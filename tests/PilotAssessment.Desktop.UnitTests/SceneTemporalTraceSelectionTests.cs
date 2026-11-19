using PilotAssessment.Desktop.Core.SceneAssessment;

namespace PilotAssessment.Desktop.UnitTests;

public sealed class SceneTemporalTraceSelectionTests
{
    [Fact]
    public void CompleteRunsNeverJoinMissingPhaseOrUnobservedFrames()
    {
        var points = new List<SceneTemporalPoint>
        {
            Point(0, 12), Point(1, 12.11), Point(2, 12.2, "insufficient_evidence"),
            Point(3, 12.3), Point(4, 19, phase: "upper"), Point(6, 19.2, phase: "upper"),
        };
        Assert.Equal(new[] { "0,1", "3", "4", "5" },
            SceneTemporalTraceSelection.ContinuousRuns(points).Select(run => string.Join(",", run)));
        Assert.Equal(6, points.Count);
    }

    [Fact]
    public void EvidenceIsNotClampedToScoreRangeOrInferredFromScore()
    {
        var points = new List<SceneTemporalPoint> { Point(0, 1), Point(1, 2), Point(2, 3) };
        points[0].LogBayesFactorHighLow = -12;
        points[1].LogBayesFactorHighLow = 0;
        points[2].LogBayesFactorHighLow = 12;
        Assert.Single(SceneTemporalTraceSelection.ContinuousRuns(points, evidence: true));
        points[1].LogBayesFactorHighLow = null;
        Assert.Equal(2, SceneTemporalTraceSelection.ContinuousRuns(points, evidence: true).Count);
        Assert.Single(SceneTemporalTraceSelection.ContinuousRuns(points));
    }

    [Fact]
    public void CursorUsesExactNearestRealFrameAndAllTimesAreRetained()
    {
        var points = new List<SceneTemporalPoint> { Point(0, 28.312345), Point(1, 28.91), Point(2, 45.78) };
        Assert.Equal(1, SceneTemporalTraceSelection.FindNearestPoint(points, 30));
        Assert.Equal(2, SceneTemporalTraceSelection.FindNearestPoint(points, 44));
        Assert.Equal(0, SceneTemporalTraceSelection.FindNearestPoint(points, 1));
        Assert.Equal(-1, SceneTemporalTraceSelection.FindNearestPoint([], 1));
        Assert.Equal(28.312345, points[0].TimestampS);
    }

    [Fact]
    public void InvalidNumericalValuesAndNoEvidenceAreGaps()
    {
        var points = new List<SceneTemporalPoint> { Point(0, 1), Point(1, 2), Point(2, 3), Point(3, 4) };
        points[0].Score = double.NaN;
        points[1].Score = 101;
        points[2].Status = "no_evidence";
        points[3].TimestampS = double.PositiveInfinity;
        Assert.Empty(SceneTemporalTraceSelection.ContinuousRuns(points));
    }

    private static SceneTemporalPoint Point(int index, double time, string status = "calculated", string phase = "lower") => new()
    {
        FrameIndex = index, TimestampS = time, PhaseId = phase, Status = status, Score = 80,
        LogBayesFactorHighLow = .02, EvidenceCount = 1,
    };
}
