using System.Diagnostics;
using System.Globalization;
using System.Text;
using System.Text.Json;
using PilotAssessment.Desktop.Core.Protocol;
using PilotAssessment.Desktop.Core.SceneAssessment;

namespace PilotAssessment.Desktop.ContractTests;

public sealed class SceneAssessmentContractTests
{
    [Fact]
    public async Task RealSceneBackend_VersionOneRetainsRulesWithoutLegacyBayesianScoring()
    {
        var repositoryRoot = FindRepositoryRoot();
        var pythonPath = Path.Combine(repositoryRoot, ".venv", "Scripts", "python.exe");
        Assert.True(File.Exists(pythonPath), $"Existing project Python was not found: {pythonPath}");
        var startInfo = new ProcessStartInfo
        {
            FileName = pythonPath,
            WorkingDirectory = repositoryRoot,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardInputEncoding = new UTF8Encoding(false, true),
            StandardOutputEncoding = new UTF8Encoding(false, true),
            StandardErrorEncoding = new UTF8Encoding(false, true),
        };
        startInfo.ArgumentList.Add("-m");
        startInfo.ArgumentList.Add("pilot_assessment.scene_assessment");
        startInfo.Environment["PYTHONPATH"] = Path.Combine(repositoryRoot, "src");
        using var process = new Process { StartInfo = startInfo };
        Assert.True(process.Start());
        var stderr = process.StandardError.ReadToEndAsync();
        await using var client = new JsonRpcClient(new JsonLineFramer(process.StandardOutput.BaseStream, process.StandardInput.BaseStream));
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        try
        {
            var hello = await client.InvokeAsync("runtime.hello", Parse("""{"supported_protocols":["1.0"]}"""), timeout.Token);
            Assert.Contains(hello.GetProperty("capabilities").EnumerateArray(), entry => entry.GetString() == "scene.assessment.v1");
            Assert.DoesNotContain(hello.GetProperty("capabilities").EnumerateArray(), entry => entry.GetString() == "model.current-workspace.v1");
            var gateway = new SceneGateway(client);
            var registry = await gateway.GetSceneListAsync(timeout.Token);
            Assert.Equal(new[] { "SCN-001", "SCN-002" }, registry.Scenes.Select(scene => scene.SceneId));
            Assert.Equal("SCN-001", registry.Scenes[0].SceneId);
            var selectedCatalog = await gateway.GetCatalogAsync(registry.Scenes[0].SceneId, "1.0", timeout.Token);
            Assert.Equal(registry.Scenes[0].SceneId, selectedCatalog.SceneId);
            var unknownScene = await Assert.ThrowsAsync<JsonRpcRemoteException>(() => gateway.GetCatalogAsync("SCN-DOES-NOT-EXIST", timeout.Token));
            Assert.Equal(-32602, unknownScene.Code);
            var catalog = await gateway.GetCatalogAsync("SCN-001", "1.0", timeout.Token);
            var studio = new SceneStudioState();
            studio.AddCatalog(selectedCatalog);
            var graph = SceneGraphProjection.Build(studio.Documents.Select(document => document.Workspace));
            Assert.Equal(26, graph.Nodes.Count);
            Assert.Equal(19, graph.Edges.Count(edge => edge.Kind == "bayesian"));
            Assert.Equal(6, graph.Edges.Count(edge => edge.Kind == "membership"));
            Assert.All(graph.Nodes, node => Assert.Null(node.Score));
            Assert.Equal(6, catalog.Items.Count);
            Assert.Equal(30, catalog.Metrics.Count);
            Assert.Equal(19, catalog.Items.Sum(item => item.Checkpoints.Count));
            Assert.Empty(catalog.ConfigurationTemplate.SkillModels!);
            Assert.All(catalog.InputTemplate.Results!.Values, value => Assert.Null(value));
            Assert.All(catalog.ConfigurationTemplate.Parameters.Values, parameter => Assert.Null(parameter.Desired.Upper));
            var holdReferences = catalog.Items
                .Where(item => item.ItemId is "A-S2-01" or "A-S2-02")
                .SelectMany(item => item.Checkpoints)
                .SelectMany(checkpoint => checkpoint.MetricIds)
                .Count(id => id == "terminal_hover_duration_s");
            Assert.Equal(2, holdReferences);

            var workspace = new SceneWorkspace(catalog);
            var blankValidation = await gateway.ValidateConfigurationAsync(workspace.Configuration, timeout.Token);
            Assert.False(blankValidation.Valid);

            // Arithmetic-only test values; no scientific defaults are supplied by the application.
            var configuration = workspace.Configuration;
            var input = workspace.Input;
            foreach (var metric in catalog.Metrics)
            {
                if (metric.Rule == "must_be_true")
                {
                    input.Results![metric.MetricId] = Parse("true");
                    continue;
                }

                if (metric.Rule == "zero_events")
                {
                    input.Results![metric.MetricId] = Parse("0");
                    continue;
                }

                var parameter = SyntheticParameter(metric.ParameterKind);
                configuration.Parameters[metric.MetricId] = parameter;
                input.Results![metric.MetricId] = Parse(parameter.Expected!.Value.ToString("R", CultureInfo.InvariantCulture));
            }

            workspace.LoadConfigurationJson(JsonSerializer.Serialize(configuration, SceneJsonContext.Default.SceneConfiguration));
            workspace.LoadInputJson(JsonSerializer.Serialize(input, SceneJsonContext.Default.SceneInput));
            var validation = await gateway.ValidateConfigurationAsync(workspace.Configuration, timeout.Token);
            Assert.True(validation.Valid, string.Join("; ", validation.Issues.Select(issue => issue.Path + ": " + issue.Message)));
            var report = await gateway.EvaluateAsync(workspace.Configuration, workspace.Input, timeout.Token);
            Assert.Equal("complete", report.CalculationStatus);
            Assert.Equal("D", report.Grade);
            Assert.True(report.Passed);
            Assert.Empty(report.Issues);
            Assert.All(report.Items, item => Assert.Equal("D", item.Grade));
            Assert.All(report.Items, item =>
            {
                var skill = Assert.IsType<SceneSkillQuantification>(item.SkillQuantification);
                Assert.Null(skill.Posterior);
                Assert.Null(skill.Score);
                Assert.NotEqual("eap", skill.Method);
            });
            workspace.SetReport(report);
            var exported = JsonSerializer.Deserialize(workspace.ExportReportJson(), SceneJsonContext.Default.SceneReport)!;
            Assert.True(JsonElement.DeepEquals(
                JsonSerializer.SerializeToElement(configuration, SceneJsonContext.Default.SceneConfiguration),
                JsonSerializer.SerializeToElement(exported.Configuration, SceneJsonContext.Default.SceneConfiguration)));
            Assert.True(JsonElement.DeepEquals(
                JsonSerializer.SerializeToElement(input, SceneJsonContext.Default.SceneInput),
                JsonSerializer.SerializeToElement(exported.Input, SceneJsonContext.Default.SceneInput)));

            var edit = workspace.BeginItemEdit("A-S2-01");
            edit.Parameters["terminal_hover_duration_s"].Expected = 3;
            workspace.CommitItemEdit(edit);
            Assert.Null(workspace.Report);
            Assert.Equal(2, exported.Configuration.Parameters["terminal_hover_duration_s"].Expected);

            // Legacy input schemas retain rule grading but cannot execute the removed Bayesian model.
            var headingId = catalog.Items.Single(item => item.ItemId == "A-S2-08").Checkpoints[2].MetricIds.Single();
            input.Results![headingId] = Parse("1.5");
            var acceptable = await gateway.EvaluateAsync(configuration, input, timeout.Token);
            var takeoff = acceptable.Items.Single(item => item.ItemId == "A-S2-08");
            Assert.Equal("A", takeoff.Grade);
            Assert.True(takeoff.Passed);
            Assert.Null(takeoff.SkillQuantification!.Score);
            input.Results![headingId] = Parse("3");
            var failed = await gateway.EvaluateAsync(configuration, input, timeout.Token);
            takeoff = failed.Items.Single(item => item.ItemId == "A-S2-08");
            Assert.Equal("U", takeoff.Grade);
            Assert.False(takeoff.Passed);
            Assert.Null(takeoff.SkillQuantification!.Score);
            input.Results![headingId] = Parse("0");

            configuration.SkillModels = null;
            var legacy = await gateway.EvaluateAsync(configuration, input, timeout.Token);
            Assert.Equal("D", legacy.Grade);
            Assert.True(legacy.Passed);
            Assert.Null(legacy.Configuration.SkillModels);
            Assert.All(legacy.Items, item =>
            {
                Assert.Null(item.SkillQuantification!.Score);
                Assert.Null(item.SkillQuantification.Posterior);
            });

            await client.InvokeAsync("runtime.shutdown", cancellationToken: timeout.Token);
            await process.WaitForExitAsync(timeout.Token);
            Assert.Equal(0, process.ExitCode);
            Assert.DoesNotContain("Traceback", await stderr, StringComparison.Ordinal);
        }
        finally
        {
            if (!process.HasExited)
            {
                process.Kill(entireProcessTree: true);
                await process.WaitForExitAsync();
            }
        }
    }

    [Fact]
    public async Task RealSceneBackend_VersionTwoRawSeriesAndChecklistProduceTraceableResultsWithoutInventedScores()
    {
        var repositoryRoot = FindRepositoryRoot();
        var startInfo = new ProcessStartInfo
        {
            FileName = Path.Combine(repositoryRoot, ".venv", "Scripts", "python.exe"),
            WorkingDirectory = repositoryRoot,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardInputEncoding = new UTF8Encoding(false, true),
            StandardOutputEncoding = new UTF8Encoding(false, true),
            StandardErrorEncoding = new UTF8Encoding(false, true),
        };
        startInfo.ArgumentList.Add("-m");
        startInfo.ArgumentList.Add("pilot_assessment.scene_assessment");
        startInfo.Environment["PYTHONPATH"] = Path.Combine(repositoryRoot, "src");
        using var process = new Process { StartInfo = startInfo };
        Assert.True(process.Start());
        var stderr = process.StandardError.ReadToEndAsync();
        await using var client = new JsonRpcClient(new JsonLineFramer(
            process.StandardOutput.BaseStream, process.StandardInput.BaseStream, 64 * 1024 * 1024));
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(90));
        try
        {
            var hello = await client.InvokeAsync("runtime.hello", Parse("""{"supported_protocols":["1.0"]}"""), timeout.Token);
            Assert.Contains(hello.GetProperty("capabilities").EnumerateArray(), entry => entry.GetString() == "scene.assessment.v2");
            var gateway = new SceneGateway(client);
            var catalog = await gateway.GetCatalogAsync("SCN-001", "2.0", timeout.Token);
            Assert.Equal("2.0", catalog.SchemaVersion);
            Assert.Equal(4, catalog.Items.Count);
            Assert.Equal(16, catalog.Items.Sum(item => item.Checkpoints.Count));
            Assert.Equal(25, catalog.Metrics.Count);
            Assert.Null(catalog.InputTemplate.Results);
            Assert.Equal(3, catalog.ConfigurationTemplate.SkillModels!.Count);
            var checklist = Assert.Single(catalog.Items, item => item.AssessmentKind == "checklist");
            Assert.False(catalog.ConfigurationTemplate.SkillModels.ContainsKey(checklist.ItemId));
            Assert.All(catalog.ConfigurationTemplate.SkillModels.Values, model =>
            {
                Assert.Equal("unconfigured", model.ParameterSource);
                Assert.All(model.Prior, value => Assert.Null(value));
                Assert.All(model.StateScores, value => Assert.Null(value));
                Assert.All(model.CheckpointModels.Values, checkpoint =>
                    Assert.All(checkpoint.Probabilities, row => Assert.All(row, value => Assert.Null(value))));
            });

            var workspace = new SceneWorkspace(catalog);
            var configuration = workspace.Configuration;
            var input = workspace.Input;
            var metrics = catalog.Metrics.ToDictionary(metric => metric.MetricId);
            foreach (var metric in catalog.Metrics.Where(metric => metric.Rule == "interval"))
            {
                // Explicit arithmetic fixtures, not training recommendations.
                var expected = metric.Comparison == "angle_degrees" ? 359d : 100d;
                configuration.Parameters[metric.MetricId] = Parameter(expected, -1, 1, -3, 3);
            }

            foreach (var item in catalog.Items)
            {
                foreach (var checkpoint in item.Checkpoints)
                {
                    var checkpointInput = input.Items![item.ItemId].Checkpoints![checkpoint.CheckpointId];
                    foreach (var metricId in checkpoint.MetricIds.Where(id => metrics[id].InputKind == "scalar"))
                    {
                        checkpointInput.Values[metricId] = metrics[metricId].Rule switch
                        {
                            "must_be_true" => Parse("true"),
                            "zero_events" => Parse("0"),
                            _ => JsonSerializer.SerializeToElement(configuration.Parameters[metricId].Expected),
                        };
                    }
                    var seriesIds = checkpoint.MetricIds.Where(id => metrics[id].InputKind == "series").ToArray();
                    if (seriesIds.Length > 0)
                    {
                        checkpointInput.Samples = [Sample(10, 11), Sample(11, 13)];
                    }
                    SceneSample Sample(double start, double end) => new()
                    {
                        StartS = start, EndS = end,
                        Values = seriesIds.ToDictionary(id => id,
                            id => (JsonElement?)JsonSerializer.SerializeToElement(configuration.Parameters[id].Expected)),
                    };
                }
            }

            var headingCheckpoint = catalog.Items.Single(item => item.ItemId == "A-S2-08").Checkpoints
                .Single(checkpoint => checkpoint.MetricIds.Contains("takeoff_heading_deg"));
            var headingInput = input.Items!["A-S2-08"].Checkpoints![headingCheckpoint.CheckpointId];
            headingInput.Samples[0].Values["takeoff_heading_deg"] = Parse("1");
            workspace.LoadConfigurationJson(JsonSerializer.Serialize(configuration, SceneJsonContext.Default.SceneConfiguration));
            workspace.LoadInputJson(JsonSerializer.Serialize(input, SceneJsonContext.Default.SceneInput));
            var validation = await gateway.ValidateConfigurationAsync(configuration, timeout.Token);
            Assert.True(validation.Valid, string.Join("; ", validation.Issues.Select(issue => issue.Message)));
            var report = await gateway.EvaluateAsync(configuration, input, timeout.Token);
            Assert.Equal("complete", report.CalculationStatus);
            Assert.True(report.Passed);
            Assert.Equal("A", report.Grade);
            Assert.All(report.Items, item =>
            {
                var quantification = Assert.IsType<SceneSkillQuantification>(item.SkillQuantification);
                Assert.Equal(item.ItemId == checklist.ItemId ? "not_applicable" : "pending_method", quantification.Status);
                Assert.Null(quantification.Score);
                Assert.Null(quantification.Posterior);
            });
            var heading = HeadingResult(report);
            Assert.Equal(2, heading.Timeline.Count);
            Assert.Equal(1d, heading.Timeline[0].Value!.Value.GetDouble());
            Assert.Equal(359d, heading.Timeline[0].Expected);
            Assert.Equal(2d, heading.Timeline[0].Deviation);
            Assert.Equal("A", heading.Timeline[0].Grade);
            Assert.Equal(3d, heading.Distribution!.DurationS);
            Assert.Equal(1d / 3, heading.Distribution.Proportions["A"]!.Value, 12);
            Assert.Equal(2d / 3, heading.Distribution.Proportions["D"]!.Value, 12);
            Assert.Equal(1d, Assert.Single(heading.Episodes!).DurationS);
            workspace.SetReport(report);
            var restored = JsonSerializer.Deserialize(workspace.ExportReportJson(), SceneJsonContext.Default.SceneReport)!;
            Assert.True(JsonElement.DeepEquals(JsonSerializer.SerializeToElement(input, SceneJsonContext.Default.SceneInput),
                JsonSerializer.SerializeToElement(restored.Input, SceneJsonContext.Default.SceneInput)));
            Assert.Equal(2d, HeadingResult(restored).Timeline[0].Deviation);
            var graph = SceneGraphProjection.Build([workspace]);
            Assert.Equal(21, graph.Nodes.Count);
            Assert.Equal(10, graph.Edges.Count(edge => edge.Kind == "bayesian"));
            Assert.Equal(10, graph.Edges.Count(edge => edge.Kind == "membership"));
            Assert.All(graph.Nodes, node => Assert.Null(node.Score));

            configuration.SkillModels!["A-S2-08"].Prior = [-1, 2, 0];
            var invalidModelValidation = await gateway.ValidateConfigurationAsync(configuration, timeout.Token);
            Assert.False(invalidModelValidation.Valid);
            Assert.All(invalidModelValidation.Issues, issue => Assert.StartsWith("/skill_models/", issue.Path));
            var invalidModelReport = await gateway.EvaluateAsync(configuration, input, timeout.Token);
            Assert.Equal("complete", invalidModelReport.CalculationStatus);
            Assert.True(invalidModelReport.Passed);
            Assert.Equal("A", invalidModelReport.Grade);
            var invalidSkill = invalidModelReport.Items.Single(item => item.ItemId == "A-S2-08").SkillQuantification!;
            Assert.Equal("invalid_model", invalidSkill.Status);
            Assert.NotEmpty(invalidSkill.Warnings);
            Assert.Null(invalidSkill.Score);
            Assert.Null(invalidSkill.Posterior);
            Assert.Throws<JsonException>(() => workspace.LoadConfigurationJson(
                JsonSerializer.Serialize(configuration, SceneJsonContext.Default.SceneConfiguration)));
            configuration.SkillModels["A-S2-08"].Prior = [.2, null, null];
            var partialModelValidation = await gateway.ValidateConfigurationAsync(configuration, timeout.Token);
            Assert.True(partialModelValidation.Valid);
            configuration.SkillModels["A-S2-08"].Prior = [null, null, null];

            // One known U is retained even when a later interval has missing coverage.
            headingInput.Samples[0].Values["takeoff_heading_deg"] = Parse("10");
            headingInput.Samples[1].StartS = 12;
            headingInput.Samples[1].EndS = 14;
            var failedWithGap = await gateway.EvaluateAsync(configuration, input, timeout.Token);
            Assert.False(failedWithGap.Passed);
            Assert.Equal("U", failedWithGap.Grade);
            Assert.NotEqual("complete", failedWithGap.CalculationStatus);
            Assert.Equal(1d, HeadingResult(failedWithGap).Distribution!.GapS);

            var checklistCheckpoint = checklist.Checkpoints[0];
            input.Items[checklist.ItemId].Checkpoints![checklistCheckpoint.CheckpointId].Values[checklistCheckpoint.MetricIds[0]] = Parse("false");
            var uncheckedReport = await gateway.EvaluateAsync(configuration, input, timeout.Token);
            Assert.False(uncheckedReport.Items.Single(item => item.ItemId == checklist.ItemId).Passed);

            // Exercise the scene-only 64 MiB transport on both request and response.
            input.Items[checklist.ItemId].Checkpoints![checklistCheckpoint.CheckpointId].Values[checklistCheckpoint.MetricIds[0]] = Parse("true");
            headingInput.Samples = Enumerable.Range(0, 80_000).Select(index => new SceneSample
            {
                StartS = index, EndS = index + 1,
                Values = new() { ["takeoff_heading_deg"] = Parse("359") },
            }).ToList();
            using (var payload = new MemoryStream())
            {
                using var writer = new Utf8JsonWriter(payload);
                JsonSerializer.Serialize(writer, input, SceneJsonContext.Default.SceneInput);
                writer.Flush();
                Assert.True(payload.Length > JsonLineFramer.DefaultMaxMessageBytes);
            }
            var largeReport = await gateway.EvaluateAsync(configuration, input, timeout.Token);
            Assert.Equal("complete", largeReport.CalculationStatus);
            Assert.True(largeReport.Passed);
            Assert.Equal(80_000, HeadingResult(largeReport).Timeline.Count);
            Assert.Equal(80_000, largeReport.Input.Items!["A-S2-08"].Checkpoints![headingCheckpoint.CheckpointId].Samples.Count);
            Assert.Equal(80_000d, HeadingResult(largeReport).Distribution!.DurationS);
            Assert.Null(largeReport.Items.Single(item => item.ItemId == "A-S2-08").SkillQuantification!.Score);

            await client.InvokeAsync("runtime.shutdown", cancellationToken: timeout.Token);
            await process.WaitForExitAsync(timeout.Token);
            Assert.Equal(0, process.ExitCode);
            Assert.DoesNotContain("Traceback", await stderr, StringComparison.Ordinal);

            SceneMetricResult HeadingResult(SceneReport result) => result.Items.Single(item => item.ItemId == "A-S2-08")
                .Checkpoints.Single(checkpoint => checkpoint.CheckpointId == headingCheckpoint.CheckpointId)
                .Metrics.Single(metric => metric.MetricId == "takeoff_heading_deg");
        }
        finally
        {
            if (!process.HasExited)
            {
                process.Kill(entireProcessTree: true);
                await process.WaitForExitAsync();
            }
        }
    }

    private static SceneParameter SyntheticParameter(string kind) => kind switch
    {
        "error" => Parameter(0, 0, 1, 0, 2),
        "signed" => Parameter(0, -1, 1, -2, 2),
        "hold" => new() { Expected = 2, Desired = new() { Lower = 2, UnboundedUpper = true }, Acceptable = new() { Lower = 1, UnboundedUpper = true } },
        "gaze" => Parameter(2, 2, 3, 1, 4),
        "duration" => Parameter(2, 1, 3, 0, 4),
        _ => throw new InvalidOperationException($"Unknown parameter kind: {kind}"),
    };

    private static SceneParameter Parameter(double expected, double dl, double du, double al, double au) => new()
    {
        Expected = expected,
        Desired = new() { Lower = dl, Upper = du },
        Acceptable = new() { Lower = al, Upper = au },
    };

    private static JsonElement Parse(string json)
    {
        using var document = JsonDocument.Parse(json);
        return document.RootElement.Clone();
    }

    private static string FindRepositoryRoot()
    {
        for (var directory = new DirectoryInfo(AppContext.BaseDirectory); directory is not null; directory = directory.Parent)
        {
            if (File.Exists(Path.Combine(directory.FullName, "pyproject.toml")))
            {
                return directory.FullName;
            }
        }

        throw new DirectoryNotFoundException("Could not locate pilot_assessment_system.");
    }
}
