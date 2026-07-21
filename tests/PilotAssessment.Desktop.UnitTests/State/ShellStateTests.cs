using PilotAssessment.Desktop.Core.State;

namespace PilotAssessment.Desktop.UnitTests.State;

public sealed class ShellStateTests
{
    [Fact]
    public void DomainCommandsRequireReadyBackendAndProjectContext()
    {
        var state = new ApplicationShellState();

        Assert.False(state.Snapshot.CanUseDomainCommands);
        state.BeginBackendConnection();
        Assert.Equal(BackendConnectionState.Connecting, state.Snapshot.BackendState);
        Assert.False(state.Snapshot.CanUseDomainCommands);

        state.CompleteBackendConnection("protocol 1.0");
        Assert.True(state.Snapshot.IsBackendReady);
        Assert.False(state.Snapshot.CanUseDomainCommands);

        state.SetProjectContext("project.alpha", "session.alpha", "scheme.current");
        Assert.True(state.Snapshot.CanUseDomainCommands);
        Assert.Equal("session.alpha", state.Snapshot.SessionId);
    }

    [Fact]
    public void FailureDisablesCommandsAndReconnectClearsTheActionableError()
    {
        var state = new ApplicationShellState();
        state.BeginBackendConnection();
        state.CompleteBackendConnection("protocol 1.0");
        state.SetProjectContext("project.alpha");

        state.FailBackendConnection("sidecar exited");
        Assert.Equal(BackendConnectionState.Faulted, state.Snapshot.BackendState);
        Assert.Equal("sidecar exited", state.Snapshot.BackendError);
        Assert.False(state.Snapshot.CanUseDomainCommands);

        state.BeginBackendConnection();
        Assert.Null(state.Snapshot.BackendError);
        Assert.Equal(BackendConnectionState.Connecting, state.Snapshot.BackendState);
    }

    [Fact]
    public void ClearingProjectAlsoClearsSessionAndSchemeContext()
    {
        var state = new ApplicationShellState();
        state.SetProjectContext("project.alpha", "session.alpha", "scheme.alpha");

        state.SetProjectContext(null);

        Assert.Null(state.Snapshot.ProjectId);
        Assert.Null(state.Snapshot.SessionId);
        Assert.Null(state.Snapshot.SchemeId);
        Assert.Null(state.Snapshot.ProjectDisplayName);
        Assert.Null(state.Snapshot.SessionDisplayName);
        Assert.Null(state.Snapshot.SchemeDisplayName);
    }

    [Fact]
    public void PresentationNamesFollowIdentitiesWithoutReplacingTechnicalContext()
    {
        var state = new ApplicationShellState();
        state.SetProjectContext(
            "project.alpha",
            schemeId: "scheme.alpha",
            projectDisplayName: "Candidate Evaluation Project",
            schemeDisplayName: "Base Scheme");

        state.SetProjectContext("project.alpha", "session.alpha", "scheme.alpha");

        Assert.Equal("project.alpha", state.Snapshot.ProjectId);
        Assert.Equal("Candidate Evaluation Project", state.Snapshot.ProjectDisplayName);
        Assert.Equal("Base Scheme", state.Snapshot.SchemeDisplayName);
        Assert.Null(state.Snapshot.SessionDisplayName);

        state.SetSchemeContext("scheme.beta", "Hover Scheme");

        Assert.Equal("scheme.beta", state.Snapshot.SchemeId);
        Assert.Equal("Hover Scheme", state.Snapshot.SchemeDisplayName);
    }

    [Fact]
    public void DiagnosticsAreBoundedAndNewestLinesArePreserved()
    {
        var state = new ApplicationShellState();
        for (var index = 0; index < 220; index++)
        {
            state.AppendDiagnostic($"line-{index}");
        }

        Assert.Equal(200, state.Snapshot.Diagnostics.Count);
        Assert.Equal("line-20", state.Snapshot.Diagnostics[0]);
        Assert.Equal("line-219", state.Snapshot.Diagnostics[^1]);
    }
}
