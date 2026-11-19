namespace PilotAssessment.Desktop.Core.SceneAssessment;

/// <summary>Keeps plotted local evidence separate at phase changes and unavailable observations.</summary>
public static class SceneLocalTraceSelection
{
    public static IReadOnlyList<IReadOnlyList<int>> ContinuousRuns(IReadOnlyList<SceneSkillLocalPoint> points)
    {
        var runs = new List<IReadOnlyList<int>>();
        List<int>? current = null;
        SceneSkillLocalPoint? previous = null;
        for (var index = 0; index < points.Count; index++)
        {
            var point = points[index];
            if (point.Status != "complete" || point.Score is not { } score || !double.IsFinite(score)
                || score is < 0 or > 100 || !double.IsFinite(point.TimestampS))
            {
                current = null;
                previous = null;
                continue;
            }
            if (current is null || previous is null || point.PhaseId != previous.PhaseId
                || point.TimestampS <= previous.TimestampS || point.ObservedStartS > previous.TimestampS)
            {
                current = [];
                runs.Add(current);
            }
            current.Add(index);
            previous = point;
        }
        return runs;
    }

    public static int FindNearestPoint(IReadOnlyList<SceneSkillLocalPoint> points, double timestampS)
    {
        if (points.Count == 0 || !double.IsFinite(timestampS)) { return -1; }
        var low = 0;
        var high = points.Count - 1;
        while (low <= high)
        {
            var middle = low + (high - low) / 2;
            if (points[middle].TimestampS < timestampS) { low = middle + 1; }
            else if (points[middle].TimestampS > timestampS) { high = middle - 1; }
            else { return middle; }
        }
        if (low == 0) { return 0; }
        if (low == points.Count) { return points.Count - 1; }
        return timestampS - points[low - 1].TimestampS <= points[low].TimestampS - timestampS ? low - 1 : low;
    }
}
