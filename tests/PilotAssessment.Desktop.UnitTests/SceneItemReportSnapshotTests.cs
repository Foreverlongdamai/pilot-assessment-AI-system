using PilotAssessment.Desktop.Core.SceneAssessment;

namespace PilotAssessment.Desktop.UnitTests;

public sealed class SceneItemReportSnapshotTests
{
    [Fact]
    public void OpeningResult_CapturesIndependentParametersAndCompleteItemTimeRange()
    {
        var catalog = SceneFramesTests.Catalog();
        var workspace = new SceneWorkspace(catalog);
        var report = new SceneReport
        {
            SchemaVersion = "3.0", SceneId = "SCN-002", EvaluatedAt = "2026-09-15T16:00:00Z",
            Configuration = workspace.Configuration, Input = workspace.Input,
            Items = [new() { ItemId = "flight", Name = "悬停", Grade = "A", Passed = true }],
        };
        report.Input.Items!["flight"].Frames =
            [new() { TimestampS = 1.123, PhaseId = "hold" }, new() { TimestampS = 27.89, PhaseId = "hold" }];
        report.Configuration.Parameters["height"].Expected = 6;

        var snapshot = new SceneItemReportSnapshot(catalog, report, "flight");
        catalog.Items[0].Name = "modified catalog";
        report.Configuration.Parameters["height"].Expected = 99;
        report.Items[0].Grade = "U";
        report.Input.Items["flight"].Frames!.Clear();

        Assert.Equal("A", snapshot.Item.Grade);
        Assert.Equal(6, snapshot.Report.Configuration.Parameters["height"].Expected);
        Assert.Equal(1.123, snapshot.StartS);
        Assert.Equal(27.89, snapshot.EndS);
        Assert.NotEqual("modified catalog", snapshot.Definition.Name);
        Assert.Contains("2026-09-15T16:00:00Z", snapshot.WindowTitle);
    }

    [Fact]
    public void MismatchedSceneOrMissingItem_CannotOpenAnUnrelatedResult()
    {
        var catalog = SceneFramesTests.Catalog();
        var workspace = new SceneWorkspace(catalog);
        var report = new SceneReport
        {
            SchemaVersion = "3.0", SceneId = "other", Configuration = workspace.Configuration,
            Input = workspace.Input, Items = [new() { ItemId = "flight" }],
        };
        Assert.Throws<ArgumentException>(() => new SceneItemReportSnapshot(catalog, report, "flight"));
        report.SceneId = catalog.SceneId;
        Assert.Throws<ArgumentException>(() => new SceneItemReportSnapshot(catalog, report, "missing"));
    }
}
