using PilotAssessment.Desktop.Controls.Graph;
using PilotAssessment.Desktop.Core.SceneAssessment;

var checks = new (string Name, Action Run)[]
{
    ("frame selection uses exact nonuniform timestamps", () =>
    {
        var points = Enumerable.Range(0, 100).Select(index => new SceneMetricTimePoint
        {
            TimestampS = index < 90 ? index / 100.0 : 100 + index - 90,
            Grade = "D", Deviation = 0,
        }).ToList();
        var selected = SceneTimelineSelection.SelectIndices(points, 10);
        Require(selected.Contains(90), "The first frame after the large time gap was not preserved by its time bucket.");
        Require(selected.Count <= 10, "Frame selection exceeded the budget.");
        Require(points.All(point => point.StartS is null && point.EndS is null), "Frame selection invented intervals.");
    }),
    ("nearest real frame is used without interval interpolation", () =>
    {
        var points = new List<SceneMetricTimePoint>
        {
            new() { TimestampS = 12 }, new() { TimestampS = 12.1 }, new() { TimestampS = 20 },
        };
        Require(SceneTimelineSelection.FindNearestFrame(points, 14) == 1, "A time gap did not select the nearest real frame.");
        Require(SceneTimelineSelection.FindNearestFrame(points, 18) == 2, "Nearest-frame search chose the wrong side of a gap.");
        Require(SceneTimelineSelection.FindNearestFrame(points, 0) == 0, "Leading pointer position lost the first frame.");
        Require(SceneTimelineSelection.FindNearestFrame(points, 30) == 2, "Trailing pointer position lost the last frame.");
        Require(SceneTimelineSelection.FindNearestFrame([], 12) == -1, "Empty input acquired a frame.");
        Require(SceneTimelineSelection.FindNearestFrame([points[0]], 12) == 0, "Single-frame input cannot be inspected.");
    }),
    ("single U between D intervals is retained", () =>
    {
        var points = Create(1801);
        points[1].Grade = "U";
        points[1].Deviation = 20;
        var selected = SceneTimelineSelection.SelectIndices(points, 1800);
        Require(selected.Contains(1), "The sole U interval at index 1 disappeared from the drawing.");
        Require(selected.Count <= 1800, "Selection exceeds the drawing budget.");
    }),
    ("large alternating trace has bounded geometry", () =>
    {
        var points = Create(100_000);
        for (var index = 0; index < points.Count; index++)
        {
            points[index].Grade = index % 2 == 0 ? "D" : "U";
            points[index].Deviation = index % 2 == 0 ? 0 : index % 3 == 0 ? -20 : 20;
        }
        var selected = SceneTimelineSelection.SelectIndices(points, 1800);
        Require(selected.Count <= 1800, "High failure density produced unbounded geometry.");
        Require(selected[0] == 0 && selected[^1] == points.Count - 1, "Trace boundaries disappeared.");
        Require(selected.SequenceEqual(selected.Distinct().Order()), "Indices must remain unique and ordered.");
        Require(selected.Any(index => points[index].Deviation == -20), "Negative extreme disappeared.");
        Require(selected.Any(index => points[index].Deviation == 20), "Positive extreme disappeared.");
    }),
    ("unequal time intervals preserve local failure and endpoints", () =>
    {
        var points = Create(4000);
        points[3999].StartS = 10000;
        points[3999].EndS = 10050;
        points[123].Grade = "U";
        points[123].Deviation = -100;
        var selected = SceneTimelineSelection.SelectIndices(points, 100);
        Require(selected.Contains(123), "The failure before a large time gap disappeared.");
        Require(selected.Contains(3999), "The last supplied interval disappeared.");
        Require(selected.Count <= 100, "Time bucketing exceeded the budget.");
        Require(points.Count == 4000 && points[3999].StartS == 10000, "Drawing selection changed source data.");
    }),
    ("small input and empty input remain unchanged", () =>
    {
        Require(SceneTimelineSelection.SelectIndices(Create(4), 20).SequenceEqual([0, 1, 2, 3]), "Small input was reduced.");
        Require(SceneTimelineSelection.SelectIndices([], 20).Count == 0, "Empty input acquired fabricated points.");
    }),
    ("worst grade is retained independently of numerical extrema", () =>
    {
        var points = Create(1801);
        points[1].Grade = "U";
        points[1].Deviation = null;
        points[2].Deviation = -30;
        points[3].Deviation = 40;
        var selected = SceneTimelineSelection.SelectIndices(points, 1800);
        Require(selected.Contains(1), "The reported U was discarded because its deviation is unavailable.");
        Require(selected.Contains(2) && selected.Contains(3), "Preserving the worst grade lost finite extremes.");
    }),
};

var failures = 0;
foreach (var (name, run) in checks)
{
    try { run(); Console.WriteLine("PASS " + name); }
    catch (Exception error) { failures++; Console.WriteLine("FAIL " + name + ": " + error.Message); }
}
Console.WriteLine($"{checks.Length - failures}/{checks.Length} checks passed.");
return failures + ObservationChecks.Run() == 0 ? 0 : 1;

static List<SceneMetricTimePoint> Create(int count) => Enumerable.Range(0, count).Select(index =>
    new SceneMetricTimePoint { StartS = index, EndS = index + 1, Expected = 100, Deviation = 0, Grade = "D" }).ToList();

static void Require(bool condition, string message)
{
    if (!condition) { throw new InvalidOperationException(message); }
}
