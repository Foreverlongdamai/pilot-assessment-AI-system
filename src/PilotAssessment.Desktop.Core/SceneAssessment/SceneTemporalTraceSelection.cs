namespace PilotAssessment.Desktop.Core.SceneAssessment;

/// <summary>Selects supplied process points for display without inferring between observations.</summary>
public static class SceneTemporalTraceSelection
{
    /// <summary>Plot-only bounds around one real timestamp; these are not observation intervals.</summary>
    public readonly record struct GradeCell(int PointIndex, double StartS, double EndS, string Grade);

    public static IReadOnlyList<GradeCell> GradeCells(IReadOnlyList<SceneTemporalPoint> points)
    {
        var cells = new List<GradeCell>();
        for (var first = 0; first < points.Count;)
        {
            var end = first + 1;
            while (end < points.Count && points[end].PhaseId == points[first].PhaseId) { end++; }
            var steps = new List<double>();
            for (var index = first + 1; index < end; index++)
            {
                if (Adjacent(points[index - 1], points[index]))
                {
                    steps.Add(points[index].TimestampS - points[index - 1].TimestampS);
                }
            }
            steps.Sort();
            // A single interval cannot distinguish cadence from a long unobserved gap.
            // The lower median also avoids averaging an isolated long gap into the cadence.
            var halfStep = steps.Count < 2 ? 0 : steps[(steps.Count - 1) / 2] / 2;
            for (var index = first; index < end; index++)
            {
                var point = points[index];
                var grade = DisplayGrade(point);
                if (grade is null || !double.IsFinite(point.TimestampS)) { continue; }
                var start = point.TimestampS;
                var finish = point.TimestampS;
                if (index > first && DisplayGrade(points[index - 1]) is not null && Adjacent(points[index - 1], point))
                {
                    start -= Math.Min((point.TimestampS - points[index - 1].TimestampS) / 2, halfStep);
                }
                if (index + 1 < end && DisplayGrade(points[index + 1]) is not null && Adjacent(point, points[index + 1]))
                {
                    finish += Math.Min((points[index + 1].TimestampS - point.TimestampS) / 2, halfStep);
                }
                cells.Add(new GradeCell(index, start, finish, grade));
            }
            first = end;
        }
        return cells;
    }

    public static string? DisplayGrade(SceneTemporalPoint point)
    {
        if (point.Status == "no_evidence"
            || (point.Grade is null && point.UpdateKind == "none" && point.EvidenceCount == 0))
        {
            return null;
        }
        return point.Grade is "D" or "A" or "U" ? point.Grade
            : point.Status == "insufficient_evidence" ? "missing" : null;
    }

    private static bool Adjacent(SceneTemporalPoint previous, SceneTemporalPoint current) =>
        previous.FrameIndex + 1 == current.FrameIndex && previous.PhaseId == current.PhaseId
        && double.IsFinite(previous.TimestampS) && double.IsFinite(current.TimestampS)
        && current.TimestampS > previous.TimestampS;

    public static IReadOnlyList<IReadOnlyList<int>> ContinuousRuns(IReadOnlyList<SceneTemporalPoint> points, bool evidence = false)
    {
        var runs = new List<IReadOnlyList<int>>();
        List<int>? current = null;
        SceneTemporalPoint? previous = null;
        for (var index = 0; index < points.Count; index++)
        {
            var point = points[index];
            var value = evidence ? point.LogBayesFactorHighLow : point.Score;
            if (point.Status != "calculated" || !double.IsFinite(point.TimestampS)
                || value is not { } number || !double.IsFinite(number)
                || (!evidence && number is < 0 or > 100))
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

    public static int FindNearestPoint(IReadOnlyList<SceneTemporalPoint> points, double time)
    {
        if (!double.IsFinite(time)) { return -1; }
        var best = -1;
        var distance = double.PositiveInfinity;
        for (var index = 0; index < points.Count; index++)
        {
            var candidate = Math.Abs(points[index].TimestampS - time);
            if (candidate < distance) { best = index; distance = candidate; }
        }
        return best;
    }
}
