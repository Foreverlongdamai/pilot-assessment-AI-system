using System.Text.Json;
using System.Text.Json.Nodes;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.State;

namespace PilotAssessment.Desktop.UnitTests.ViewModels;

public sealed class RunResultViewModelTests
{
    [Fact]
    public void TechnicalPreflightBlocksOnlyBlockedOrStaleSelection()
    {
        var workspace = new RunWorkspaceState();
        var ready = ReadFixture(
            "current-model-run-preflight.json",
            PilotAssessmentJsonContext.Default.CurrentModelRunPreflightReport);
        workspace.SetPreflight(ready with { TechnicalDisposition = TechnicalDisposition.Blocked });

        Assert.False(workspace.CanStart("session.alpha.rev1", "scheme.current", 3));

        workspace.SetPreflight(ready);
        Assert.True(workspace.CanStart("session.alpha.rev1", "scheme.current", 3));
        Assert.False(workspace.CanStart("session.alpha.rev2", "scheme.current", 3));
        Assert.False(workspace.CanStart("session.alpha.rev1", "scheme.current", 4));
    }

    [Fact]
    public void FrozenSnapshotProjectionPreservesBackendNodeIdentityAndHash()
    {
        var run = CurrentRun();

        var nodes = RunResultProjector.FrozenNodes(run);

        var node = Assert.Single(nodes);
        Assert.Equal("raw.x", node.NodeId);
        Assert.Equal(ModelNodeKind.RawInput, node.NodeKind);
        Assert.Equal(2, node.SemanticRevision);
        Assert.Equal(new string('c', 64), node.ContentHash);
        Assert.Equal(new string('d', 64), run.Snapshot.SnapshotHash);
    }

    [Fact]
    public void ProgressEventsAreMonotonicAndIgnoreOtherRuns()
    {
        var workspace = new RunWorkspaceState();
        workspace.SetRun(CurrentRun());
        var second = Event("run.alpha", 2, RunState.Running, RunStage.Evidence, 4, 10);
        var stale = Event("run.alpha", 1, RunState.Running, RunStage.Ingestion, 2, 10);
        var other = Event("run.other", 3, RunState.Completed, RunStage.Completed, 10, 10);

        Assert.True(workspace.TryApply(second));
        Assert.False(workspace.TryApply(stale));
        Assert.False(workspace.TryApply(other));
        Assert.Equal(2, workspace.CurrentRun?.ProgressSequence);
        Assert.Equal(RunStage.Evidence, workspace.CurrentRun?.Stage);
        Assert.Equal(4, workspace.CompletedUnits);
        Assert.Equal(10, workspace.TotalUnits);
    }

    [Fact]
    public void CancellationIsAvailableOnlyBeforeCancellingOrTerminalState()
    {
        var workspace = new RunWorkspaceState();
        var run = CurrentRun();

        workspace.SetRun(run with { State = RunState.Queued });
        Assert.True(workspace.CanCancel);
        workspace.SetRun(run with { State = RunState.Running });
        Assert.True(workspace.CanCancel);
        workspace.SetRun(run with { State = RunState.Cancelling });
        Assert.False(workspace.CanCancel);
        workspace.SetRun(run with { State = RunState.Completed });
        Assert.False(workspace.CanCancel);
    }

    [Fact]
    public void EvidenceProjectionMapsPrimaryValueAndDauStateWithoutComputingEvidence()
    {
        using var primary = JsonDocument.Parse("6.514994829369182");
        using var state = JsonDocument.Parse("\"unacceptable\"");
        using var score = JsonDocument.Parse("0");
        var result = new EvidenceRuntimeResult(
            "evidence-runtime-result",
            "0.1.0",
            "evidence-version.test",
            ["evidence-binding.test"],
            "computed",
            primary.RootElement.Clone(),
            new Dictionary<string, JsonElement>(StringComparer.Ordinal)
            {
                ["state"] = state.RootElement.Clone(),
                ["score"] = score.RootElement.Clone(),
            });

        var row = RunResultProjector.Evidence(result, "evidence.o1", "Phase-state precision");

        Assert.Equal("6.514995", row.PrimaryValue);
        Assert.Equal("UNACCEPTABLE", row.DauState);
        Assert.Equal("0", row.Score);
    }

    [Fact]
    public void PosteriorAndInfluenceProjectionKeepCanonicalEdgesOutOfResultOverlay()
    {
        var variable = new ComponentIdRef(ComponentKind.BnNodeVersion, "bn.version.tcp");
        var prior = new PosteriorDistribution(variable, ["at_risk", "proficient"], [0.5, 0.5]);
        var posterior = new PosteriorDistribution(variable, ["at_risk", "proficient"], [0.2, 0.8]);
        var row = RunResultProjector.Posterior(posterior, prior, "bn.tcp", "Task Control Proficiency");
        var influence = RunResultProjector.Influence(
            new InferenceInfluenceEdge(
                "inference_influence",
                "influence.test",
                new ComponentIdRef(ComponentKind.EvidenceBindingVersion, "evidence.binding.o1"),
                variable,
                "leave-one-observation-out-v1",
                0.3,
                ["evidence.binding.o1", "bn.version.tcp"]),
            "Phase-state precision",
            "Task Control Proficiency");

        Assert.Equal("proficient", row.TopState);
        Assert.Equal(0.8, row.TopProbability);
        Assert.Equal(0.6, row.L1Change, 10);
        Assert.Equal("Phase-state precision", influence.ObservedNode);
        Assert.Equal("Task Control Proficiency", influence.QueriedNode);
        Assert.Equal("influence.test", influence.EdgeId);
        Assert.DoesNotContain("probabilistic", influence.MethodId, StringComparison.OrdinalIgnoreCase);
    }

    private static AssessmentRunV3 CurrentRun() => ReadFixture(
        "assessment-run-v3.json",
        PilotAssessmentJsonContext.Default.AssessmentRunV3);

    private static RunEvent Event(
        string runId,
        int sequence,
        RunState state,
        RunStage stage,
        int completed,
        int total) =>
        new(
            "run-event",
            "0.1.0",
            $"event.{sequence}",
            runId,
            sequence,
            state,
            stage,
            completed,
            total,
            $"progress {sequence}",
            DateTime.UtcNow,
            new Dictionary<string, JsonNode?>());

    private static T ReadFixture<T>(
        string name,
        System.Text.Json.Serialization.Metadata.JsonTypeInfo<T> typeInfo)
    {
        var path = Path.Combine(AppContext.BaseDirectory, "Fixtures", name);
        return JsonSerializer.Deserialize(File.ReadAllText(path), typeInfo)
            ?? throw new InvalidDataException($"Fixture {name} was empty.");
    }
}
