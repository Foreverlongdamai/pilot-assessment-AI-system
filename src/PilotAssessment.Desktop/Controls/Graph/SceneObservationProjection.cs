using System.Text.Json;

using PilotAssessment.Desktop.Core.SceneAssessment;

namespace PilotAssessment.Desktop.Controls.Graph;

/// <summary>Projects reported observations into one physical unit without changing evidence or grades.</summary>
public static class SceneObservationProjection
{
    public sealed record Sample(int SourceIndex, double? TimestampS, int? FrameIndex, string? PhaseId,
        double? Observed, double? Target, double? DesiredLower, double? DesiredUpper,
        double? AcceptableLower, double? AcceptableUpper, string? Grade, string State,
        bool? BooleanValue, bool Angular);

    public static IReadOnlyList<Sample> Build(IReadOnlyList<SceneMetricTimePoint> points, string comparison,
        double? desiredLower, double? desiredUpper, double? acceptableLower, double? acceptableUpper,
        bool boolean = false)
    {
        var samples = new List<Sample>(points.Count);
        double? previousTarget = null;
        double? previousRawTarget = null;
        string? previousPhase = null;
        for (var index = 0; index < points.Count; index++)
        {
            var point = points[index];
            var angular = comparison == "angle_degrees";
            var distance = comparison is "radial" or "route_3d";
            var miss = comparison == "radial" && point.Value is { ValueKind: JsonValueKind.Object } value
                && value.TryGetProperty("status", out var status) && status.ValueKind == JsonValueKind.String
                && status.GetString() == "miss";
            bool? booleanValue = point.Value?.ValueKind switch { JsonValueKind.True => true, JsonValueKind.False => false, _ => null };
            double? target = boolean ? null : distance ? 0 : Finite(point.Expected);
            if (angular && target is { } rawTarget && previousTarget is { } lastTarget
                && previousRawTarget is { } lastRawTarget && previousPhase == point.PhaseId)
            {
                target = lastTarget + Shortest(rawTarget - lastRawTarget);
            }
            double? observed = boolean || miss ? null : distance ? Finite(point.Deviation)
                : angular ? target + Finite(point.Deviation) : Numeric(point.Value);
            var state = miss ? "miss" : boolean ? booleanValue is null ? "missing" : "boolean"
                : observed is null ? "missing" : "observed";
            samples.Add(new Sample(index, Finite(point.TimestampS), point.FrameIndex, point.PhaseId,
                observed, target, Offset(target, desiredLower), Offset(target, desiredUpper),
                Offset(target, acceptableLower), Offset(target, acceptableUpper), point.Grade, state,
                boolean ? booleanValue : null, angular));
            previousPhase = point.PhaseId;
            previousTarget = target;
            previousRawTarget = Finite(point.Expected);
        }
        return samples;
    }

    /// <summary>Only joins adjacent reported frames with a numeric observation and no known discontinuity.</summary>
    public static IReadOnlyList<IReadOnlyList<int>> ContinuousRuns(IReadOnlyList<Sample> samples)
    {
        var runs = new List<IReadOnlyList<int>>();
        List<int>? run = null;
        Sample? previous = null;
        for (var index = 0; index < samples.Count; index++)
        {
            var sample = samples[index];
            if (sample.TimestampS is null || sample.Observed is null)
            {
                run = null;
                previous = null;
                continue;
            }
            var continuous = previous is not null && sample.PhaseId == previous.PhaseId
                && sample.TimestampS > previous.TimestampS
                && (sample.FrameIndex is null || previous.FrameIndex is null || sample.FrameIndex == previous.FrameIndex + 1)
                && sample.Grade is "D" or "A" or "U" && previous.Grade is "D" or "A" or "U"
                && (!sample.Angular || Math.Abs(sample.Observed.Value - previous.Observed!.Value) <= 180);
            if (!continuous || run is null)
            {
                run = [];
                runs.Add(run);
            }
            run.Add(index);
            previous = sample;
        }
        return runs;
    }

    private static double? Offset(double? target, double? bound) => target is { } center && bound is { } offset
        && !double.IsNaN(offset) ? center + offset : null;
    private static double? Finite(double? value) => value is { } number && double.IsFinite(number) ? number : null;
    private static double? Numeric(JsonElement? value) => value is { ValueKind: JsonValueKind.Number } number
        && number.TryGetDouble(out var result) && double.IsFinite(result) ? result : null;
    private static double Shortest(double difference) => ((difference % 360) + 540) % 360 - 180;
}
