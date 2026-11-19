using PilotAssessment.Desktop.Core.SceneAssessment;

namespace PilotAssessment.Desktop.Controls.Graph;

/// <summary>Selects drawing indices without changing the underlying assessment trace.</summary>
public static class SceneTimelineSelection
{
    public static IReadOnlyList<int> SelectIndices(IReadOnlyList<SceneMetricTimePoint> points, int maximumPoints)
    {
        ArgumentNullException.ThrowIfNull(points);
        ArgumentOutOfRangeException.ThrowIfLessThan(maximumPoints, 5);
        if (points.Count <= maximumPoints)
        {
            return Enumerable.Range(0, points.Count).ToArray();
        }

        // Five representatives per time bucket bound geometry independently of failure density.
        // First/last preserve trace boundaries; extrema and worst grade preserve local anomalies.
        var bucketCount = maximumPoints / 5;
        var buckets = new Bucket[bucketCount];
        var firstTime = points[0].TimestampS ?? points[0].StartS ?? 0;
        var span = (points[^1].TimestampS ?? points[^1].EndS ?? firstTime) - firstTime;
        for (var index = 0; index < points.Count; index++)
        {
            var fraction = double.IsFinite(span) && span > 0
                ? ((points[index].TimestampS ?? points[index].StartS ?? firstTime) - firstTime) / span
                : (double)index / points.Count;
            var bucketIndex = Math.Clamp((int)(fraction * bucketCount), 0, bucketCount - 1);
            (buckets[bucketIndex] ??= new Bucket()).Add(index, points[index]);
        }

        var selected = new SortedSet<int>();
        foreach (var bucket in buckets)
        {
            if (bucket is null) { continue; }
            selected.Add(bucket.First);
            selected.Add(bucket.Last);
            selected.Add(bucket.Worst);
            if (bucket.Minimum >= 0) { selected.Add(bucket.Minimum); }
            if (bucket.Maximum >= 0) { selected.Add(bucket.Maximum); }
        }
        return selected.ToArray();
    }

    public static int FindNearestFrame(IReadOnlyList<SceneMetricTimePoint> points, double timestampS)
    {
        ArgumentNullException.ThrowIfNull(points);
        if (points.Count == 0 || !double.IsFinite(timestampS)) { return -1; }
        var low = 0;
        var high = points.Count - 1;
        while (low <= high)
        {
            var middle = low + (high - low) / 2;
            if (points[middle].TimestampS is not { } time || !double.IsFinite(time)) { return -1; }
            if (time < timestampS) { low = middle + 1; }
            else if (time > timestampS) { high = middle - 1; }
            else { return middle; }
        }
        if (low == 0) { return 0; }
        if (low == points.Count) { return points.Count - 1; }
        return timestampS - points[low - 1].TimestampS <= points[low].TimestampS - timestampS ? low - 1 : low;
    }

    private sealed class Bucket
    {
        public int First { get; private set; } = -1;
        public int Last { get; private set; }
        public int Worst { get; private set; }
        public int Minimum { get; private set; } = -1;
        public int Maximum { get; private set; } = -1;
        private int _worstRank = -1;
        private double _minimum = double.PositiveInfinity;
        private double _maximum = double.NegativeInfinity;

        public void Add(int index, SceneMetricTimePoint point)
        {
            if (First < 0) { First = index; }
            Last = index;
            var rank = point.Grade switch { "U" => 3, "A" => 2, "D" => 1, _ => 0 };
            if (rank > _worstRank) { Worst = index; _worstRank = rank; }
            if (point.Deviation is not { } deviation || !double.IsFinite(deviation)) { return; }
            if (deviation < _minimum) { Minimum = index; _minimum = deviation; }
            if (deviation > _maximum) { Maximum = index; _maximum = deviation; }
        }
    }
}
