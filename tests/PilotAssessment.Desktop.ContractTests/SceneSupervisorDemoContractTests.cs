using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using PilotAssessment.Desktop.Core.Protocol;
using PilotAssessment.Desktop.Core.SceneAssessment;

namespace PilotAssessment.Desktop.ContractTests;

public sealed class SceneSupervisorDemoContractTests
{
    [Theory]
    [InlineData("SCN-001", "01-proficient", true)]
    [InlineData("SCN-001", "02-marginal", true)]
    [InlineData("SCN-001", "03-unqualified", false)]
    [InlineData("SCN-002", "01-proficient", true)]
    [InlineData("SCN-002", "02-marginal", true)]
    [InlineData("SCN-002", "03-unqualified", false)]
    public async Task HistoricalConfigurationAfterExplicitScopeChangeUpgradesWithCurrentBackend(
        string sceneId, string caseId, bool passes)
    {
        var root = FindRoot();
        var folder = Path.Combine(root, "examples", "supervisor-demo-2026-09-15", sceneId);
        var start = new ProcessStartInfo
        {
            FileName = Path.Combine(root, ".venv", "Scripts", "python.exe"),
            WorkingDirectory = root,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardInputEncoding = new UTF8Encoding(false),
            StandardOutputEncoding = new UTF8Encoding(false),
            StandardErrorEncoding = new UTF8Encoding(false),
        };
        start.ArgumentList.Add("-m");
        start.ArgumentList.Add("pilot_assessment.scene_assessment");
        start.Environment["PYTHONPATH"] = Path.Combine(root, "src");
        using var process = Process.Start(start)!;
        var stderr = process.StandardError.ReadToEndAsync();
        await using var client = new JsonRpcClient(new JsonLineFramer(
            process.StandardOutput.BaseStream, process.StandardInput.BaseStream, 64 * 1024 * 1024));
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(60));
        try
        {
            await client.InvokeAsync("runtime.hello", JsonSerializer.SerializeToElement(new { supported_protocols = new[] { "1.0" } }), timeout.Token);
            var gateway = new SceneGateway(client);
            var workspace = new SceneWorkspace(await gateway.GetCatalogAsync(sceneId, timeout.Token));
            var configJson = await File.ReadAllTextAsync(Path.Combine(folder, "configuration.json"));
            // Historical files remain intact. The test explicitly removes the
            // unflown approach before exercising legacy inference migration.
            configJson = RemoveRetiredApproach(configJson, sceneId, isConfiguration: true);
            workspace.LoadConfigurationJson(configJson);
            var savedConfiguration = workspace.SaveConfigurationJson();
            Assert.DoesNotContain("demo_normalized_grade_likelihood_v1", savedConfiguration);
            Assert.DoesNotContain("process_model", savedConfiguration);
            Assert.All(workspace.Configuration.SkillModels!.Values, model =>
            {
                Assert.Equal(SceneSkillModel.CompensationInferenceMethod, model.InferenceMethod);
                Assert.Equal(.2, model.Compensation!.Alpha);
            });
            Assert.True(JsonElement.DeepEquals(JsonDocument.Parse(configJson).RootElement.GetProperty("parameters"),
                JsonDocument.Parse(savedConfiguration).RootElement.GetProperty("parameters")));
            workspace.LoadInputJson(RemoveRetiredApproach(
                await File.ReadAllTextAsync(Path.Combine(folder, caseId + ".input.json")), sceneId,
                isConfiguration: false));
            var report = await gateway.EvaluateAsync(workspace.Configuration, workspace.Input, timeout.Token);
            Assert.Equal("complete", report.CalculationStatus);
            Assert.Empty(report.Issues);
            Assert.Equal(passes, report.Passed);
            Assert.Equal(passes ? "A" : "U", report.Grade);
            if (sceneId == "SCN-001")
            {
                var speedDefinition = Assert.Single(workspace.Catalog.Metrics,
                    metric => metric.MetricId == "air_taxi_airspeed_mps");
                Assert.Equal("item_profile", speedDefinition.TargetMode);
                Assert.Equal("acceleration", speedDefinition.ReferenceOriginPhase);
                Assert.DoesNotContain(workspace.Catalog.Metrics,
                    metric => metric.MetricId is "speed_hold_airspeed_mps" or "speed_hold_duration_s");
                var taxi = Assert.Single(report.Items, item => item.ItemId == "A-S2-05");
                var speed = Assert.Single(taxi.Checkpoints.SelectMany(checkpoint => checkpoint.Metrics),
                    metric => metric.MetricId == "air_taxi_airspeed_mps");
                var frames = report.Input.Items![taxi.ItemId].Frames!;
                var origin = frames.First(frame => frame.PhaseId == "acceleration").TimestampS!.Value;
                Assert.True(origin > 0, "The fixture must exercise a flight that started before acceleration.");
                Assert.Equal(frames.Count, speed.Timeline.Count);
                Assert.DoesNotContain(frames, frame => frame.PhaseId == "hold_end");
                Assert.Equal(0, speed.Timeline[0].ReferenceElapsedS);
                Assert.True(speed.Timeline.First(point => point.PhaseId == "hold").ReferenceElapsedS > 0);
                Assert.All(speed.Timeline, point =>
                {
                    Assert.Equal(point.TimestampS!.Value - origin, point.ReferenceElapsedS!.Value, 9);
                    Assert.True(JsonElement.DeepEquals(frames[point.FrameIndex!.Value].Values![speed.MetricId]!.Value,
                        point.Value!.Value));
                    Assert.NotNull(point.Expected);
                });
            }
            if (sceneId == "SCN-002")
            {
                Assert.Equal(2, report.Items.Count);
                Assert.DoesNotContain(report.Items, item => item.ItemId == "A-S2-01");
                var hover = Assert.Single(report.Items, item => item.ItemId == "A-S2-02");
                Assert.Equal(4, hover.Checkpoints.Count);
                Assert.Equal(4, hover.SkillQuantification!.EvidenceCount);
                Assert.Equal(4, hover.SkillQuantification.ExpectedEvidenceCount);
                var height = Assert.Single(hover.Checkpoints, checkpoint => checkpoint.CheckpointId == "A-S2-02-04");
                Assert.Contains(height.Metrics, metric => metric.MetricId == "hover_lower_height_m");
                Assert.Contains(height.Metrics, metric => metric.MetricId == "hover_upper_height_m");
                Assert.Contains(height.Metrics, metric => metric.MetricId == "hover_vz_mps");
                Assert.Single(hover.SkillQuantification.TemporalAnalysis!.CheckpointTraces, trace => trace.CheckpointId == height.CheckpointId);
            }
            var reference = JsonSerializer.Deserialize(await File.ReadAllTextAsync(Path.Combine(root,
                "examples", "bayes-compensation-2026-09-23", sceneId, caseId + ".report.json")), SceneJsonContext.Default.SceneReport)!;
            foreach (var item in report.Items)
            {
                var expected = reference.Items.Single(i => i.ItemId == item.ItemId);
                Assert.Equal(expected.Grade, item.Grade);
                var q = item.SkillQuantification!;
                if (q.Status == "not_applicable")
                {
                    Assert.Null(q.Score);
                    Assert.Null(q.CumulativeTrace);
                    Assert.Equal("not_applicable", q.TemporalAnalysis!.Status);
                    Assert.Null(q.TemporalAnalysis.ItemTrace);
                    continue;
                }
                Assert.Equal("complete", q.Status);
                Assert.Equal("uncalibrated", q.Calibration);
                Assert.Null(q.EvidenceStrength);
                Assert.Equal(SceneSkillModel.CompensationInferenceMethod, q.Method);
                Assert.Equal(expected.SkillQuantification!.Score!.Value, q.Score!.Value, 10);
                Assert.Equal(1, q.Posterior!.Sum(), 12);
                var cumulative = Assert.IsType<SceneSkillCumulativeTrace>(q.CumulativeTrace);
                Assert.Equal(item.ItemId, cumulative.ItemId);
                Assert.Equal(SceneSkillModel.CompensationInferenceMethod, cumulative.Method);
                Assert.Equal(item.Timeline!.Count, cumulative.Timeline.Count);
                Assert.Equal(q.Score.Value, cumulative.Timeline[^1].Score!.Value, 12);
                Assert.Equal(q.Posterior, cumulative.Timeline[^1].Posterior);
                var temporal = Assert.IsType<SceneTemporalAnalysis>(q.TemporalAnalysis);
                Assert.Equal("complete", temporal.Status);
                Assert.Equal(SceneSkillModel.CompensationInferenceMethod, temporal.Method);
                Assert.Equal(item.Checkpoints.Count, temporal.CheckpointTraces.Count);
                Assert.Null(temporal.ItemTrace!.CheckpointId);
                foreach (var trace in temporal.CheckpointTraces.Append(temporal.ItemTrace))
                {
                    Assert.Equal(item.Timeline.Count, trace.Timeline.Count);
                    Assert.Equal("complete", trace.Status);
                    Assert.All(trace.Timeline, point =>
                    {
                        Assert.Equal(item.Timeline[point.FrameIndex].TimestampS, point.TimestampS);
                        if (point.Status == "calculated")
                        {
                            Assert.Equal(1, point.Posterior!.Sum(), 12);
                            Assert.InRange(point.Score!.Value, 0, 100);
                            Assert.True(double.IsFinite(point.LogBayesFactorHighLow!.Value));
                        }
                        else
                        {
                            Assert.Equal("no_evidence", point.Status);
                            Assert.Null(point.Score);
                            Assert.Null(point.Posterior);
                            Assert.Null(point.LogBayesFactorHighLow);
                        }
                    });
                }
                Assert.All(cumulative.Timeline, point =>
                {
                    Assert.Equal(item.Checkpoints.Count, point.ExpectedCheckpointCount);
                    Assert.Equal(item.Timeline[point.FrameIndex].TimestampS, point.TimestampS);
                    Assert.Equal(0, point.MissingFrameCount);
                    Assert.InRange(point.Score!.Value, 0, 100);
                    Assert.Equal(1, point.Posterior!.Sum(), 12);
                });
                Assert.Empty(q.LocalTraces!);
            }
            workspace.SetReport(report);
            var export = workspace.ExportReportJson();
            var saved = JsonSerializer.Deserialize(export, SceneJsonContext.Default.SceneReport)!;
            Assert.True(JsonElement.DeepEquals(
                JsonSerializer.SerializeToElement(report, SceneJsonContext.Default.SceneReport),
                JsonSerializer.SerializeToElement(saved, SceneJsonContext.Default.SceneReport)));
        }
        finally
        {
            process.StandardInput.Close();
            await process.WaitForExitAsync(timeout.Token);
        }
        Assert.Equal(0, process.ExitCode);
        Assert.True(string.IsNullOrWhiteSpace(await stderr));
    }

    private static string RemoveRetiredApproach(string json, string sceneId, bool isConfiguration)
    {
        if (sceneId != "SCN-001") return json;
        var document = JsonNode.Parse(json)!.AsObject();
        if (isConfiguration)
        {
            Assert.True(document["skill_models"]!.AsObject().Remove("A-S2-23"));
            var parameters = document["parameters"]!.AsObject();
            var retiredKeys = parameters.Select(entry => entry.Key).Where(key =>
                key.StartsWith("approach_", StringComparison.Ordinal)
                || key.StartsWith("arrival_", StringComparison.Ordinal)).ToList();
            Assert.Equal(8, retiredKeys.Count);
            foreach (var key in retiredKeys) parameters.Remove(key);
        }
        else
        {
            Assert.True(document["items"]!.AsObject().Remove("A-S2-23"));
        }
        return document.ToJsonString();
    }

    private static string FindRoot()
    {
        for (var directory = new DirectoryInfo(AppContext.BaseDirectory); directory is not null; directory = directory.Parent)
            if (File.Exists(Path.Combine(directory.FullName, "pyproject.toml"))) return directory.FullName;
        throw new DirectoryNotFoundException("Repository root not found.");
    }
}
