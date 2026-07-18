using System.Globalization;
using System.Text.Json;

using PilotAssessment.Desktop.Core.Contracts;

namespace PilotAssessment.Desktop.Core.State;

public sealed class RunWorkspaceState
{
    public CurrentModelRunPreflightReport? Preflight { get; private set; }

    public AssessmentRunV2? CurrentRun { get; private set; }

    public string? ResultId { get; private set; }

    public int CompletedUnits { get; private set; }

    public int TotalUnits { get; private set; }

    public string ProgressMessage { get; private set; } = string.Empty;

    public bool CanStart(
        string? selectedSessionRevisionId,
        string? selectedSchemeId,
        int? selectedSchemeRevision) =>
        Preflight is
        {
            TechnicalDisposition: TechnicalDisposition.Ready,
        } report &&
        string.Equals(
            report.SessionRevisionRef.SessionRevisionId,
            selectedSessionRevisionId,
            StringComparison.Ordinal) &&
        string.Equals(report.SchemeId, selectedSchemeId, StringComparison.Ordinal) &&
        report.SchemeSemanticRevision == selectedSchemeRevision &&
        CurrentRun?.State is not (
            RunState.Queued or
            RunState.Running or
            RunState.Cancelling);

    public bool CanCancel => CurrentRun?.State is RunState.Queued or RunState.Running;

    public void SetPreflight(CurrentModelRunPreflightReport? preflight)
    {
        Preflight = preflight;
    }

    public void SetRun(AssessmentRunV2 run, string? resultId = null)
    {
        ArgumentNullException.ThrowIfNull(run);
        CurrentRun = run;
        ResultId = resultId;
        CompletedUnits = 0;
        TotalUnits = 0;
        ProgressMessage = string.Empty;
    }

    public void SetResultId(string? resultId)
    {
        ResultId = resultId;
    }

    public void RestoreProgress(RunEvent runEvent)
    {
        ArgumentNullException.ThrowIfNull(runEvent);
        if (CurrentRun is null ||
            !string.Equals(CurrentRun.RunId, runEvent.RunId, StringComparison.Ordinal) ||
            runEvent.Sequence != CurrentRun.ProgressSequence)
        {
            return;
        }

        CompletedUnits = runEvent.CompletedUnits;
        TotalUnits = runEvent.TotalUnits;
        ProgressMessage = runEvent.Message;
    }

    public bool TryApply(RunEvent runEvent)
    {
        ArgumentNullException.ThrowIfNull(runEvent);
        if (CurrentRun is null ||
            !string.Equals(CurrentRun.RunId, runEvent.RunId, StringComparison.Ordinal) ||
            runEvent.Sequence <= CurrentRun.ProgressSequence)
        {
            return false;
        }

        CurrentRun = CurrentRun with
        {
            State = runEvent.State,
            Stage = runEvent.Stage,
            ProgressSequence = runEvent.Sequence,
        };
        CompletedUnits = runEvent.CompletedUnits;
        TotalUnits = runEvent.TotalUnits;
        ProgressMessage = runEvent.Message;
        return true;
    }
}

public sealed record FrozenNodeProjection(
    string NodeId,
    ModelNodeKind NodeKind,
    int SemanticRevision,
    string ContentHash);

public sealed record EvidenceResultProjection(
    string NodeId,
    string DisplayName,
    string CalculationStatus,
    string PrimaryValue,
    string DauState,
    string Score);

public sealed record ObservationProjection(
    string NodeId,
    string DisplayName,
    ObservationKind Kind,
    string Value);

public sealed record PosteriorProjection(
    string NodeId,
    string DisplayName,
    string TopState,
    double TopProbability,
    double L1Change,
    string Distribution);

public sealed record InfluenceProjection(
    string EdgeId,
    string ObservedNode,
    string QueriedNode,
    double L1Delta,
    string MethodId,
    string CanonicalPath);

public static class RunResultProjector
{
    public static FrozenNodeProjection[] FrozenNodes(AssessmentRunV2 run) =>
        run.Snapshot.ActiveNodes
            .Select(node => new FrozenNodeProjection(
                node.NodeId,
                node.NodeKind,
                node.SemanticRevision,
                node.ContentHash))
            .ToArray();

    public static EvidenceResultProjection Evidence(
        EvidenceRuntimeResult result,
        string nodeId,
        string displayName)
    {
        var state = ReadScoringString(result.ScoringOutputs, "state");
        var score = ReadScoringValue(result.ScoringOutputs, "score");
        return new EvidenceResultProjection(
            nodeId,
            displayName,
            result.CalculationStatus,
            FormatJsonValue(result.PrimaryValue),
            string.IsNullOrWhiteSpace(state) ? "—" : state.ToUpperInvariant(),
            score);
    }

    public static ObservationProjection Observation(
        BayesianObservation observation,
        string nodeId,
        string displayName)
    {
        var value = observation.Kind switch
        {
            ObservationKind.Hard => observation.HardStateId ?? "—",
            ObservationKind.Virtual when observation.Likelihood is not null =>
                string.Join(" · ", observation.Likelihood.Select(value =>
                    value.ToString("0.000", CultureInfo.InvariantCulture))),
            _ => "—",
        };
        return new ObservationProjection(nodeId, displayName, observation.Kind, value);
    }

    public static PosteriorProjection Posterior(
        PosteriorDistribution posterior,
        PosteriorDistribution? prior,
        string nodeId,
        string displayName)
    {
        if (posterior.OrderedStateIds.Length != posterior.Probabilities.Length ||
            posterior.Probabilities.Length == 0)
        {
            throw new InvalidDataException("Posterior state and probability axes are inconsistent.");
        }

        var topIndex = 0;
        for (var index = 1; index < posterior.Probabilities.Length; index++)
        {
            if (posterior.Probabilities[index] > posterior.Probabilities[topIndex])
            {
                topIndex = index;
            }
        }

        var l1 = prior is not null && prior.Probabilities.Length == posterior.Probabilities.Length
            ? posterior.Probabilities.Zip(prior.Probabilities, (left, right) => Math.Abs(left - right)).Sum()
            : 0.0;
        var distribution = string.Join(
            " · ",
            posterior.OrderedStateIds.Zip(
                posterior.Probabilities,
                (state, probability) => $"{state} {probability:P1}"));
        return new PosteriorProjection(
            nodeId,
            displayName,
            posterior.OrderedStateIds[topIndex],
            posterior.Probabilities[topIndex],
            l1,
            distribution);
    }

    public static InfluenceProjection Influence(
        InferenceInfluenceEdge edge,
        string observedNode,
        string queriedNode) =>
        new(
            edge.EdgeId,
            observedNode,
            queriedNode,
            edge.L1Delta,
            edge.MethodId,
            string.Join(" → ", edge.CanonicalPath));

    private static string ReadScoringString(
        IReadOnlyDictionary<string, JsonElement> outputs,
        string key) =>
        outputs.TryGetValue(key, out var value) && value.ValueKind is JsonValueKind.String
            ? value.GetString() ?? string.Empty
            : string.Empty;

    private static string ReadScoringValue(
        IReadOnlyDictionary<string, JsonElement> outputs,
        string key) =>
        outputs.TryGetValue(key, out var value)
            ? FormatJsonValue(value)
            : "—";

    private static string FormatJsonValue(JsonElement? value)
    {
        if (value is null || value.Value.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined)
        {
            return "—";
        }

        var element = value.Value;
        return element.ValueKind switch
        {
            JsonValueKind.String => element.GetString() ?? string.Empty,
            JsonValueKind.Number when element.TryGetDouble(out var number) =>
                number.ToString("0.######", CultureInfo.InvariantCulture),
            JsonValueKind.True => "true",
            JsonValueKind.False => "false",
            _ => element.GetRawText(),
        };
    }
}
