using System.Diagnostics;
using System.Text;
using System.Text.Json;
using PilotAssessment.Desktop.Core.Protocol;
using PilotAssessment.Desktop.Core.SceneAssessment;

namespace PilotAssessment.Desktop.ContractTests;

public sealed class SceneCompensationContractTests
{
    [Theory]
    [InlineData("SCN-001", "01-proficient", true)]
    [InlineData("SCN-001", "02-marginal", true)]
    [InlineData("SCN-001", "03-unqualified", false)]
    [InlineData("SCN-002", "01-proficient", true)]
    [InlineData("SCN-002", "02-marginal", true)]
    [InlineData("SCN-002", "03-unqualified", false)]
    public async Task ActualCompensationFilesRoundTripThroughRealBackendWithOneProbabilityHistory(
        string sceneId, string caseId, bool passes)
    {
        var root = FindRoot();
        var folder = Path.Combine(root, "examples", "task-scope-2026-10-11", sceneId);
        var start = new ProcessStartInfo
        {
            FileName = Path.Combine(root, ".venv", "Scripts", "python.exe"), WorkingDirectory = root,
            UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true,
            RedirectStandardOutput = true, RedirectStandardError = true,
            StandardInputEncoding = new UTF8Encoding(false), StandardOutputEncoding = new UTF8Encoding(false),
            StandardErrorEncoding = new UTF8Encoding(false),
        };
        start.ArgumentList.Add("-m"); start.ArgumentList.Add("pilot_assessment.scene_assessment");
        start.Environment["PYTHONPATH"] = Path.Combine(root, "src");
        using var process = Process.Start(start)!;
        var stderr = process.StandardError.ReadToEndAsync();
        await using var client = new JsonRpcClient(new JsonLineFramer(
            process.StandardOutput.BaseStream, process.StandardInput.BaseStream, 64 * 1024 * 1024));
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(90));
        try
        {
            await client.InvokeAsync("runtime.hello", JsonSerializer.SerializeToElement(new { supported_protocols = new[] { "1.0" } }), timeout.Token);
            var gateway = new SceneGateway(client);
            var workspace = new SceneWorkspace(await gateway.GetCatalogAsync(sceneId, timeout.Token));
            var config = await File.ReadAllTextAsync(Path.Combine(folder, "configuration.json"));
            workspace.LoadConfigurationJson(config);
            Assert.True(JsonElement.DeepEquals(JsonDocument.Parse(config).RootElement,
                JsonDocument.Parse(workspace.SaveConfigurationJson()).RootElement));
            workspace.LoadInputJson(await File.ReadAllTextAsync(Path.Combine(folder, caseId + ".input.json")));
            var report = await gateway.EvaluateAsync(workspace.Configuration, workspace.Input, timeout.Token);
            var reference = JsonSerializer.Deserialize(await File.ReadAllTextAsync(Path.Combine(folder, caseId + ".report.json")), SceneJsonContext.Default.SceneReport)!;
            Assert.Equal("complete", report.CalculationStatus);
            Assert.Equal(passes, report.Passed);
            foreach (var item in report.Items.Where(item => item.SkillQuantification?.Status != "not_applicable"))
            {
                var q = item.SkillQuantification!;
                var model = workspace.Configuration.SkillModels![item.ItemId];
                Assert.Equal(SceneSkillModel.CompensationInferenceMethod, q.Method);
                Assert.Equal(.2, model.Compensation!.Alpha);
                Assert.Null(q.EvidenceStrength);
                Assert.DoesNotContain("process_model", workspace.SaveConfigurationJson());
                Assert.Equal(reference.Items.Single(value => value.ItemId == item.ItemId).SkillQuantification!.Score, q.Score);
                var temporal = q.TemporalAnalysis!;
                Assert.Equal(q.Method, temporal.Method);
                Assert.Equal(q.Posterior, temporal.ItemTrace!.Timeline.Last().Posterior);
                Assert.Equal(q.Score, temporal.ItemTrace.Timeline.Last().Score);
                Assert.Equal(q.Score, q.CumulativeTrace!.Timeline.Last().Score);
                Assert.Equal(q.Posterior, q.CumulativeTrace.Timeline.Last().Posterior);
                foreach (var trace in temporal.CheckpointTraces.Append(temporal.ItemTrace))
                {
                    List<double>? previous = null;
                    foreach (var point in trace.Timeline.Where(point => point.Posterior is not null))
                    {
                        Assert.Equal(previous ?? model.Prior.Select(value => value!.Value), point.Prior!);
                        Assert.Equal(3, point.BayesPosterior!.Count);
                        Assert.Equal(3, point.CompensationTarget!.Count);
                        Assert.Equal(3, point.CompensationDelta!.Count);
                        Assert.Equal(model.Compensation.Alpha, point.CompensationAlpha);
                        Assert.Equal(1, point.Posterior!.Sum(), 12);
                        for (var index = 0; index < 3; index++)
                        {
                            var expected = (1 - point.CompensationAlpha!.Value) * point.BayesPosterior[index]
                                + point.CompensationAlpha.Value * point.CompensationTarget[index];
                            Assert.Equal(expected, point.Posterior![index], 12);
                            Assert.Equal(point.Posterior[index] - point.BayesPosterior[index], point.CompensationDelta![index], 12);
                        }
                        Assert.Equal(point.Posterior!.Select((value, index) => value * model.StateScores[index]!.Value).Sum(), point.Score!.Value, 10);
                        previous = point.Posterior;
                    }
                }
            }
            workspace.SetReport(report);
            var restored = JsonSerializer.Deserialize(workspace.ExportReportJson(), SceneJsonContext.Default.SceneReport)!;
            Assert.True(JsonElement.DeepEquals(JsonSerializer.SerializeToElement(report, SceneJsonContext.Default.SceneReport),
                JsonSerializer.SerializeToElement(restored, SceneJsonContext.Default.SceneReport)));
        }
        finally
        {
            process.StandardInput.Close();
            await process.WaitForExitAsync(timeout.Token);
        }
        Assert.Equal(0, process.ExitCode);
        Assert.True(string.IsNullOrWhiteSpace(await stderr));
    }

    private static string FindRoot()
    {
        for (var directory = new DirectoryInfo(AppContext.BaseDirectory); directory is not null; directory = directory.Parent)
            if (File.Exists(Path.Combine(directory.FullName, "pyproject.toml"))) return directory.FullName;
        throw new DirectoryNotFoundException("Repository root not found.");
    }
}
