using System.Text.Json;
using PilotAssessment.Desktop.Controls.Graph;
using PilotAssessment.Desktop.Core.SceneAssessment;

internal static class ObservationChecks
{
    public static int Run()
    {
        var checks = new (string Name, Action Check)[]
        {
            ("signed tolerances are translated into raw coordinates", () =>
            {
                var samples = Build([Point(0, 12.5, 12, .5)]);
                Equal(12.5, samples[0].Observed);
                Equal(12, samples[0].Target);
                Equal(11, samples[0].DesiredLower);
                Equal(14, samples[0].DesiredUpper);
                Equal(9, samples[0].AcceptableLower);
                Equal(16, samples[0].AcceptableUpper);
            }),
            ("dynamic targets carry their own bands at every supplied frame", () =>
            {
                var samples = Build([Point(0, 10, 10, 0), Point(8, 20.3, 20, .3)]);
                Equal(19, samples[1].DesiredLower);
                Equal(24, samples[1].AcceptableUpper);
                Equal(20.3, samples[1].Observed);
            }),
            ("same grade micro fluctuations and whole item timestamps are retained", () =>
            {
                var points = Enumerable.Range(0, 5001).Select(i => Point(i / 50d, 10 + .01 * Math.Sin(i), 10, .01 * Math.Sin(i))).ToList();
                var samples = Build(points);
                Require(samples.Count == 5001 && samples[^1].TimestampS == 100, "The full observation timeline was cropped or downsampled.");
                Equal(points[311].Value!.Value.GetDouble(), samples[311].Observed);
                Require(SceneObservationProjection.ContinuousRuns(samples).Single().Count == 5001, "Same-grade movement was flattened.");
            }),
            ("missing frames and phase boundaries interrupt connecting paths", () =>
            {
                var points = new List<SceneMetricTimePoint> { Point(0, 1, 0, 1), Point(1, 2, 0, 2), Point(2, null, 0, null), Point(3, 1, 0, 1), Point(4, 1, 0, 1, "upper") };
                var runs = SceneObservationProjection.ContinuousRuns(Build(points));
                Require(runs.Count == 3 && runs[0].Count == 2 && runs[1].Single() == 3 && runs[2].Single() == 4, "A line crossed missing data or a phase boundary.");
            }),
            ("absent frame indices cannot be bridged", () =>
            {
                var points = new List<SceneMetricTimePoint> { Point(0, 1, 0, 1), Point(1, 1, 0, 1) };
                points[0].FrameIndex = 0; points[1].FrameIndex = 5;
                Require(SceneObservationProjection.ContinuousRuns(Build(points)).Count == 2, "The graph filled omitted frames.");
            }),
            ("angular observations unwrap around target while raw values remain unchanged", () =>
            {
                var points = new List<SceneMetricTimePoint> { Point(0, 359, 0, -1), Point(1, 1, 0, 1) };
                var samples = Build(points, "angle_degrees");
                Equal(-1, samples[0].Observed); Equal(1, samples[1].Observed);
                Require(points[0].Value!.Value.GetDouble() == 359, "Angular display mutated source data.");
                var moving = Build([Point(0, 358, 359, -1), Point(1, 2, 1, 1)], "angle_degrees");
                Equal(361, moving[1].Target); Equal(362, moving[1].Observed);
            }),
            ("angular opposite branch does not draw a false sweep through target", () =>
            {
                var samples = Build([Point(0, 179, 0, 179), Point(1, 181, 0, -179)], "angle_degrees");
                Require(SceneObservationProjection.ContinuousRuns(samples).Count == 2, "A branch change falsely crossed the desired zone.");
            }),
            ("radial and route plots use reported distance, never component coordinates", () =>
            {
                var hit = Point(0, null, null, .5); hit.Value = JsonSerializer.SerializeToElement(new { status = "hit", u_m = 90, v_m = -30 });
                var radial = Build([hit], "radial"); Equal(.5, radial[0].Observed); Equal(0, radial[0].Target);
                var route = Point(0, null, null, 2); route.Value = JsonSerializer.SerializeToElement(new { x_m = 500, y_m = 100, height_m = 30 });
                Equal(2, Build([route], "route_3d")[0].Observed);
            }),
            ("laser misses and unavailable distance never manufacture plotted values", () =>
            {
                var miss = Point(0, null, null, 0); miss.Value = JsonSerializer.SerializeToElement(new { status = "miss" }); miss.Grade = "U";
                var sample = Build([miss], "radial")[0];
                Require(sample.Observed is null && sample.State == "miss" && sample.Grade == "U", "Miss was plotted at a invented radius or its U was erased.");
            }),
            ("boolean states stay categorical", () =>
            {
                var point = Point(0, null, null, null); point.Value = JsonSerializer.SerializeToElement(true);
                var sample = SceneObservationProjection.Build([point], "linear", null, null, null, null, true)[0];
                Require(sample.BooleanValue == true && sample.Observed is null && sample.Target is null, "Checklist state became a measured number.");
            }),
            ("unknown target cannot create a zero-centered tolerance band", () =>
            {
                var sample = Build([Point(0, 7, null, null)])[0];
                Equal(7, sample.Observed);
                Require(sample.Target is null && sample.DesiredLower is null && sample.AcceptableUpper is null, "Missing target was filled.");
            }),
        };
        var failures = 0;
        foreach (var (name, check) in checks)
        {
            try { check(); Console.WriteLine("PASS " + name); }
            catch (Exception error) { failures++; Console.WriteLine("FAIL " + name + ": " + error.Message); }
        }
        Console.WriteLine($"{checks.Length - failures}/{checks.Length} observation checks passed.");
        return failures;
    }

    private static IReadOnlyList<SceneObservationProjection.Sample> Build(IReadOnlyList<SceneMetricTimePoint> points, string comparison = "linear") =>
        SceneObservationProjection.Build(points, comparison, -1, 2, -3, 4);

    private static SceneMetricTimePoint Point(double time, double? value, double? expected, double? deviation, string phase = "lower") => new()
    {
        TimestampS = time, Value = value is { } number ? JsonSerializer.SerializeToElement(number) : null,
        Expected = expected, Deviation = deviation, PhaseId = phase, Grade = value is null && deviation is null ? null : "D",
    };

    private static void Equal(double expected, double? actual) => Require(actual is { } value && Math.Abs(value - expected) < 1e-9, $"Expected {expected}, got {actual}.");
    private static void Require(bool condition, string message) { if (!condition) { throw new InvalidOperationException(message); } }
}
