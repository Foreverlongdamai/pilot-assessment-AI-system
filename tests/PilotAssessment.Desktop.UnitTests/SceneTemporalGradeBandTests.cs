using PilotAssessment.Desktop.Core.SceneAssessment;

namespace PilotAssessment.Desktop.UnitTests;

public sealed class SceneTemporalGradeBandTests
{
    [Fact]
    public void RegularFramesMeetAtMidpointsWithoutExtendingBeyondFirstOrLastFrame()
    {
        var points = new[] { Point(0, 10, "D"), Point(1, 11, "A"), Point(2, 12, "U") };
        var cells = SceneTemporalTraceSelection.GradeCells(points);
        Assert.Equal(3, cells.Count);
        Assert.Equal((10d, 10.5), (cells[0].StartS, cells[0].EndS));
        Assert.Equal((10.5, 11.5), (cells[1].StartS, cells[1].EndS));
        Assert.Equal((11.5, 12d), (cells[2].StartS, cells[2].EndS));
    }

    [Fact]
    public void LongGapCannotTurnIntoAColouredObservationInterval()
    {
        var points = new[] { Point(0, 0, "D"), Point(1, .1, "A"), Point(2, 100, "U") };
        var cells = SceneTemporalTraceSelection.GradeCells(points);
        Assert.Equal(.15, cells[1].EndS, 12);
        Assert.Equal(99.95, cells[2].StartS, 12);
        Assert.All(cells, cell => Assert.InRange(cell.EndS - cell.StartS, 0, .1000001));
    }

    [Fact]
    public void PhaseBoundariesAndInapplicableFramesStayBlank()
    {
        var points = new[] { Point(0, 0, "D"), Point(1, .1, "D"), Point(2, .2, null, "no_evidence"),
            Point(3, .3, "U"), Point(4, .4, "D"), Point(5, .5, "A", phase: "upper"),
            Point(6, .6, "A", phase: "upper"), Point(7, .7, "D", phase: "upper") };
        var cells = SceneTemporalTraceSelection.GradeCells(points);
        Assert.DoesNotContain(cells, cell => cell.PointIndex == 2);
        Assert.Equal(.1, cells.Single(cell => cell.PointIndex == 1).EndS);
        Assert.Equal(.3, cells.Single(cell => cell.PointIndex == 3).StartS);
        Assert.Equal(.4, cells.Single(cell => cell.PointIndex == 4).EndS);
        Assert.Equal(.5, cells.Single(cell => cell.PointIndex == 5).StartS);
    }

    [Fact]
    public void CurrentKnownGradeSurvivesEarlierMissingPosteriorWhileCurrentMissingIsGrey()
    {
        var points = new[] { Point(0, 5, "D"), Point(1, 5.1, null, "insufficient_evidence"),
            Point(2, 5.2, "U", "insufficient_evidence") };
        points[1].Score = points[2].Score = null;
        var cells = SceneTemporalTraceSelection.GradeCells(points);
        Assert.Equal(new[] { "D", "missing", "U" }, cells.Select(cell => cell.Grade));
        Assert.Equal(5.15, cells[1].EndS, 12);
        Assert.Equal(5.15, cells[2].StartS, 12);
    }

    [Fact]
    public void SingleFrameAndUncertainTwoFrameCadenceRemainPixelMarkers()
    {
        var one = Assert.Single(SceneTemporalTraceSelection.GradeCells([Point(0, 12.3456789, "U")]));
        Assert.Equal(12.3456789, one.StartS);
        Assert.Equal(one.StartS, one.EndS);
        var two = SceneTemporalTraceSelection.GradeCells([Point(0, 0, "D"), Point(1, 100, "U")]);
        Assert.All(two, cell => Assert.Equal(cell.StartS, cell.EndS));
    }

    [Fact]
    public void AllFramesIncludingAnIsolatedFailureAreRetainedWithoutChangingTheirData()
    {
        var points = Enumerable.Range(0, 10_000).Select(index => Point(index, index * .01, index == 4321 ? "U" : "D")).ToArray();
        var cells = SceneTemporalTraceSelection.GradeCells(points);
        Assert.Equal(points.Length, cells.Count);
        Assert.Equal(4321, Assert.Single(cells, cell => cell.Grade == "U").PointIndex);
        Assert.Equal(43.21, points[4321].TimestampS);
        Assert.Equal(0, cells[0].StartS);
        Assert.Equal(points[^1].TimestampS, cells[^1].EndS);
    }

    [Fact]
    public void StructuralFrameGapsAndNonFiniteTimesNeverAcquireAColouredBridge()
    {
        var points = new[] { Point(0, 0, "D"), Point(1, .1, "D"), Point(3, .2, "U"),
            Point(4, .3, "U"), Point(5, double.NaN, "D") };
        var cells = SceneTemporalTraceSelection.GradeCells(points);
        Assert.Equal(4, cells.Count);
        Assert.Equal(.1, cells[1].EndS);
        Assert.Equal(.2, cells[2].StartS);
    }

    [Fact]
    public void ExplicitInapplicabilityNeverAppearsAsAnObservedGrade()
    {
        Assert.Empty(SceneTemporalTraceSelection.GradeCells([Point(0, 5, "D", "no_evidence")]));
    }

    [Fact]
    public void EarlierMissingEvidenceDoesNotPaintAnInactiveItemFrameGrey()
    {
        var missing = Point(0, 5, null, "insufficient_evidence");
        missing.UpdateKind = "missing";
        var inactive = Point(1, 5.1, null, "insufficient_evidence");
        inactive.UpdateKind = "none";
        inactive.EvidenceCount = 0;
        var laterKnown = Point(2, 5.2, "D", "insufficient_evidence");
        laterKnown.UpdateKind = "missing";
        laterKnown.EvidenceCount = 1;
        var cells = SceneTemporalTraceSelection.GradeCells([missing, inactive, laterKnown]);
        Assert.Equal(new[] { 0, 2 }, cells.Select(cell => cell.PointIndex));
        Assert.Equal(new[] { "missing", "D" }, cells.Select(cell => cell.Grade));
        Assert.All(cells, cell => Assert.Equal(cell.StartS, cell.EndS));
    }

    private static SceneTemporalPoint Point(int index, double time, string? grade, string status = "calculated", string phase = "lower") => new()
    {
        FrameIndex = index, TimestampS = time, PhaseId = phase, Grade = grade, Status = status, Score = 80,
    };
}
