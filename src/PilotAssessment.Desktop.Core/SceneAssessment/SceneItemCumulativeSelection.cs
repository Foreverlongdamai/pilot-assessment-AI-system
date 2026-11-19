namespace PilotAssessment.Desktop.Core.SceneAssessment;

/// <summary>Groups existing score points for drawing without joining unobserved gaps.</summary>
public static class SceneItemCumulativeSelection
{
    public static (double First, double Last) PlotTimeRange(double start, double end) =>
        start == end ? (start - .5, end + .5) : (start, end);

    public static IReadOnlyList<IReadOnlyList<int>> ContinuousRuns(IReadOnlyList<SceneSkillCumulativePoint> points)
    {
        var runs = new List<IReadOnlyList<int>>();
        List<int>? current = null;
        SceneSkillCumulativePoint? previous = null;
        for (var index = 0; index < points.Count; index++)
        {
            var point = points[index];
            if (point.Score is not { } score || !double.IsFinite(score) || score is < 0 or > 100
                || !double.IsFinite(point.TimestampS) || point.Status is not ("partial" or "complete"))
            {
                current = null;
                previous = null;
                continue;
            }
            if (current is null || previous is null || previous.PhaseId != point.PhaseId
                || previous.FrameIndex + 1 != point.FrameIndex || previous.TimestampS >= point.TimestampS)
            {
                current = [];
                runs.Add(current);
            }
            current.Add(index);
            previous = point;
        }
        return runs;
    }
}
