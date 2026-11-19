using PilotAssessment.Desktop.Core.SceneAssessment;

namespace PilotAssessment.Desktop.UnitTests;

public sealed class SceneItemCumulativeSelectionTests
{
    [Theory]
    [InlineData(10, 10.2, 10, 10.2)]
    [InlineData(10, 10, 9.5, 10.5)]
    public void PlotTimeRange_PreservesSubsecondEndpointsAndCentersSingleFrame(double start, double end, double first, double last)
    {
        var range = SceneItemCumulativeSelection.PlotTimeRange(start, end);
        Assert.Equal(first, range.First, 10);
        Assert.Equal(last, range.Last, 10);
    }

    [Fact]
    public void Runs_KeepPartialPrefixValuesWithoutConnectingPhasesOrMissingResults()
    {
        SceneSkillCumulativePoint[] points =
        [
            Point(0, "first", 50, "partial"), Point(1, "first", 70, "complete"),
            Point(2, "second", 73, "complete"), Point(3, "second", null, "insufficient_evidence"),
            Point(4, "second", 77, "complete"), Point(6, "second", 80, "complete"),
        ];
        var runs = SceneItemCumulativeSelection.ContinuousRuns(points);
        Assert.Equal(4, runs.Count);
        Assert.Equal(new[] { 0, 1 }, runs[0]);
        Assert.Equal(new[] { 2 }, runs[1]);
        Assert.Equal(new[] { 4 }, runs[2]);
        Assert.Equal(new[] { 5 }, runs[3]);
        Assert.Equal(73, points[runs[1][0]].Score);
    }

    [Fact]
    public void Runs_DoNotInventScoresForInvalidOrEmptyData()
    {
        Assert.Empty(SceneItemCumulativeSelection.ContinuousRuns([]));
        Assert.Empty(SceneItemCumulativeSelection.ContinuousRuns(
            [Point(0, "hold", double.NaN, "complete"), Point(1, "hold", 101, "complete")]));
    }

    private static SceneSkillCumulativePoint Point(int frame, string phase, double? score, string status) => new()
    {
        FrameIndex = frame, TimestampS = frame, PhaseId = phase, Score = score, Status = status,
    };
}
