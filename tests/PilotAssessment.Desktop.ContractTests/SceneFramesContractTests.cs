using System.Diagnostics;
using System.Text;
using System.Text.Json;
using PilotAssessment.Desktop.Core.Protocol;
using PilotAssessment.Desktop.Core.SceneAssessment;

namespace PilotAssessment.Desktop.ContractTests;

public sealed class SceneFramesContractTests
{
    [Theory]
    [InlineData("SCN-001", 3, 12, 17)]
    [InlineData("SCN-002", 2, 6, 13)]
    public async Task RealBackend_TwoFrameScenesPreserveExactPointsIndependentRulesAndMissingEvidence(
        string sceneId, int itemCount, int checkpointCount, int metricCount)
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
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(60));
        try
        {
            var hello = await client.InvokeAsync("runtime.hello", JsonSerializer.SerializeToElement(new { supported_protocols = new[] { "1.0" } }), timeout.Token);
            Assert.Contains(hello.GetProperty("capabilities").EnumerateArray(), entry => entry.GetString() == "scene.assessment.v3");
            var gateway = new SceneGateway(client);
            var registry = await gateway.GetSceneListAsync(timeout.Token);
            Assert.Equal(new[] { "SCN-001", "SCN-002" }, registry.Scenes.Select(scene => scene.SceneId));
            var catalog = await gateway.GetCatalogAsync(sceneId, timeout.Token);
            Assert.Equal("3.0", catalog.SchemaVersion);
            Assert.Equal(itemCount, catalog.Items.Count);
            Assert.Equal(checkpointCount, catalog.Items.Sum(item => item.Checkpoints.Count));
            Assert.Equal(metricCount, catalog.Metrics.Count);
            Assert.All(catalog.Items, item => Assert.NotEmpty(item.Phases!));
            Assert.All(catalog.InputTemplate.Items!.Values, item => Assert.All(item.Frames!, frame => Assert.Null(frame.TimestampS)));

            var workspace = new SceneWorkspace(catalog);
            // The actual backend template deliberately leaves assessment parameters unfilled.
            var blankConfiguration = workspace.SaveConfigurationJson();
            workspace.LoadConfigurationJson(blankConfiguration);
            Assert.True(JsonNodeEquals(blankConfiguration, workspace.SaveConfigurationJson()));
            workspace.LoadInputJson(workspace.ExportInputTemplateJson());
            Assert.All(workspace.Input.Items!.Values, item => Assert.All(item.Frames!, frame => Assert.Null(frame.TimestampS)));
            if (sceneId == "SCN-001")
            {
                Assert.DoesNotContain(catalog.Items, item => item.ItemId == "A-S2-23");
                Assert.DoesNotContain("A-S2-23", workspace.Input.Items.Keys);
                Assert.DoesNotContain("A-S2-23", workspace.Configuration.SkillModels!.Keys);
                Assert.DoesNotContain(catalog.Metrics, metric => metric.MetricId.StartsWith("approach_", StringComparison.Ordinal)
                    || metric.MetricId.StartsWith("arrival_", StringComparison.Ordinal));
                Assert.Equal(new[] { "preflight", "acceleration", "hold", "deceleration", "stop" }, catalog.PhaseSequence!);
                var stop = Assert.Single(catalog.Items, item => item.ItemId == "A-S2-30");
                Assert.Equal("快速减速／快速停止", stop.Name);
                Assert.Contains("Rapid Deceleration/Quick Stop", stop.Description);
                var graph = SceneGraphProjection.Build([workspace]);
                Assert.Equal(1 + itemCount + checkpointCount, graph.Nodes.Count);
                Assert.DoesNotContain(graph.Nodes, node => node.ItemId == "A-S2-23");
            }
            if (sceneId == "SCN-002")
            {
                Assert.DoesNotContain(catalog.Items, item => item.ItemId == "SCENE-START");
                Assert.DoesNotContain("start", catalog.PhaseSequence!);
                Assert.Equal("lower_1", catalog.PhaseSequence![0]);
                Assert.DoesNotContain("SCENE-START", workspace.Input.Items.Keys);
                Assert.DoesNotContain("SCENE-START", workspace.Configuration.SkillModels!.Keys);
                Assert.DoesNotContain(catalog.Metrics, metric => metric.MetricId.StartsWith("start_", StringComparison.Ordinal));
                var graph = SceneGraphProjection.Build([workspace]);
                Assert.Equal(1 + itemCount + checkpointCount, graph.Nodes.Count);
                Assert.DoesNotContain(graph.Nodes, node => node.ItemId == "SCENE-START");

                Assert.DoesNotContain(catalog.Items, item => item.ItemId == "A-S2-01");
                Assert.DoesNotContain("A-S2-01", workspace.Input.Items.Keys);
                Assert.DoesNotContain("A-S2-01", workspace.Configuration.SkillModels.Keys);
                var hover = Assert.Single(catalog.Items, item => item.ItemId == "A-S2-02");
                Assert.Equal("定点悬停保持", hover.Name);
                Assert.Equal(4, hover.Checkpoints.Count);
                Assert.Equal(new[] { "hover_x_m", "hover_y_m", "hover_vx_mps", "hover_vy_mps" },
                    hover.Checkpoints.Single(checkpoint => checkpoint.CheckpointId == "A-S2-02-01").MetricIds);
                Assert.Equal(new[] { "hover_lower_height_m", "hover_upper_height_m", "hover_vz_mps" },
                    hover.Checkpoints.Single(checkpoint => checkpoint.CheckpointId == "A-S2-02-04").MetricIds);
                Assert.Equal(new[] { "hover_heading_deg" },
                    hover.Checkpoints.Single(checkpoint => checkpoint.CheckpointId == "A-S2-02-02").MetricIds);
                Assert.Equal(4, graph.Nodes.Count(node => node.ItemId == hover.ItemId && node.Kind == "checkpoint"));
                var hoverEdit = workspace.BeginItemEdit(hover.ItemId);
                Assert.Contains("hover_lower_height_m", hoverEdit.Parameters.Keys);
                Assert.Contains("hover_upper_height_m", hoverEdit.Parameters.Keys);
                Assert.Equal(4, hoverEdit.SkillModel!.CheckpointModels.Count);
                workspace.CancelItemEdit(hoverEdit);

                var previousConfiguration = workspace.SaveConfigurationJson();
                var oldConfiguration = workspace.Configuration;
                oldConfiguration.SkillModels![hover.ItemId].CheckpointModels.Remove("A-S2-02-04");
                var oldModelError = Assert.Throws<JsonException>(() => workspace.LoadConfigurationJson(
                    JsonSerializer.Serialize(oldConfiguration, SceneJsonContext.Default.SceneConfiguration)));
                Assert.Contains("不会自动合并旧 CPT", oldModelError.Message);
                Assert.Equal(previousConfiguration, workspace.SaveConfigurationJson());

                var obsoleteInput = workspace.Input;
                obsoleteInput.Items!["SCENE-START"] = new() { Frames = [] };
                var error = Assert.Throws<JsonException>(() => workspace.LoadInputJson(
                    JsonSerializer.Serialize(obsoleteInput, SceneJsonContext.Default.SceneInput)));
                Assert.Contains("SCENE-START", error.Message, StringComparison.Ordinal);
            }
            var configuration = workspace.Configuration;
            // This contract exercises rule-only evaluation; the new default model remains
            // an unconfigured draft until its prior and CPT are explicitly supplied.
            foreach (var model in configuration.SkillModels!.Values)
            {
                Assert.Equal(SceneSkillModel.CompensationInferenceMethod, model.InferenceMethod);
            }
            configuration.SkillModels = null;
            var input = SyntheticInput(catalog, configuration);
            workspace.LoadConfigurationJson(JsonSerializer.Serialize(configuration, SceneJsonContext.Default.SceneConfiguration));
            workspace.LoadInputJson(JsonSerializer.Serialize(input, SceneJsonContext.Default.SceneInput));
            var validation = await gateway.ValidateConfigurationAsync(configuration, timeout.Token);
            Assert.True(validation.Valid, string.Join("; ", validation.Issues.Select(issue => issue.Path + ": " + issue.Message)));
            var report = await gateway.EvaluateAsync(configuration, input, timeout.Token);
            Assert.Equal("complete", report.CalculationStatus);
            Assert.Equal(itemCount, report.Items.Count);
            Assert.Equal(catalog.Items.Select(item => item.ItemId), report.Items.Select(item => item.ItemId));
            Assert.Equal("D", report.Grade);
            Assert.True(report.Passed);
            Assert.All(report.Items, item =>
            {
                var sourceItem = catalog.Items.Single(source => source.ItemId == item.ItemId);
                Assert.Equal(input.Items![item.ItemId].Frames!.Count, item.Timeline!.Count);
                Assert.Equal(sourceItem.Phases!.Count, item.PhaseResults!.Count);
                Assert.Equal(0, item.FrameDistribution!.MissingFrameCount);
                Assert.Equal(1, item.FrameDistribution.Proportions["D"]);
                Assert.All(item.Timeline, point =>
                {
                    Assert.Null(point.StartS);
                    Assert.Null(point.EndS);
                    Assert.NotNull(point.FrameIndex);
                    Assert.Equal(input.Items[item.ItemId].Frames![point.FrameIndex!.Value].TimestampS, point.TimestampS);
                });
                Assert.All(item.PhaseResults!.Where(phase => phase.RequiredDurationS is > 0), phase =>
                {
                    Assert.True(phase.ObservedSpanS >= phase.RequiredDurationS);
                    Assert.False(string.IsNullOrWhiteSpace(phase.CoverageNote));
                });
                Assert.Equal(sourceItem.AssessmentKind == "checklist" ? "not_applicable" : "not_configured", item.SkillQuantification!.Status);
                Assert.Null(item.SkillQuantification.Score);
                Assert.Null(item.SkillQuantification.Posterior);
                Assert.All(item.Checkpoints.SelectMany(checkpoint => checkpoint.Metrics), metric =>
                {
                    Assert.Null(metric.Distribution);
                    Assert.Null(metric.Episodes);
                });
            });
            workspace.SetReport(report);
            var exported = JsonSerializer.Deserialize(workspace.ExportReportJson(), SceneJsonContext.Default.SceneReport)!;
            Assert.True(JsonElement.DeepEquals(JsonSerializer.SerializeToElement(input, SceneJsonContext.Default.SceneInput),
                JsonSerializer.SerializeToElement(exported.Input, SceneJsonContext.Default.SceneInput)));
            Assert.True(JsonElement.DeepEquals(JsonSerializer.SerializeToElement(configuration, SceneJsonContext.Default.SceneConfiguration),
                JsonSerializer.SerializeToElement(exported.Configuration, SceneJsonContext.Default.SceneConfiguration)));
            if (sceneId == "SCN-001")
            {
                Assert.DoesNotContain(catalog.Items, item => item.ItemId == "A-S2-23");
                Assert.DoesNotContain(catalog.Items, item => item.ItemId == "SCENE-START");
                Assert.DoesNotContain(catalog.Metrics, metric => metric.TargetMode == "phase_profile");
                Assert.DoesNotContain(report.Items, item => item.ItemId == "A-S2-23");
            }

            // Exercise heading wrapping against a stored target, without changing the original observations.
            var headingDefinition = catalog.Metrics.First(metric => metric.Comparison == "angle_degrees");
            var headingItem = catalog.Items.First(item => item.Checkpoints.Any(checkpoint => checkpoint.MetricIds.Contains(headingDefinition.MetricId)));
            var headingFrame = input.Items![headingItem.ItemId].Frames!.First(frame => frame.Values.ContainsKey(headingDefinition.MetricId));
            headingFrame.Values[headingDefinition.MetricId] = JsonSerializer.SerializeToElement(1d);
            var wrapped = await gateway.EvaluateAsync(configuration, input, timeout.Token);
            var wrappedPoint = Metric(wrapped, headingDefinition.MetricId).Timeline[0];
            Assert.Equal(1, wrappedPoint.Value!.Value.GetDouble());
            Assert.Equal(359, wrappedPoint.Expected);
            Assert.Equal(2, wrappedPoint.Deviation);
            Assert.Equal("A", wrappedPoint.Grade);
            headingFrame.Values[headingDefinition.MetricId] = JsonSerializer.SerializeToElement(359d);

            // A known excursion remains Fail even when a later frame has no observation.
            var seriesMetric = catalog.Metrics.First(metric => metric.Rule == "interval" && metric.Comparison == "linear"
                && configuration.Parameters[metric.MetricId].Expected is not null
                && input.Items!.Values.Any(item => item.Frames!.Count(frame => frame.Values.ContainsKey(metric.MetricId)) >= 2));
            var seriesItem = input.Items!.Values.First(item => item.Frames!.Count(frame => frame.Values.ContainsKey(seriesMetric.MetricId)) >= 2);
            var applicable = seriesItem.Frames!.Where(frame => frame.Values.ContainsKey(seriesMetric.MetricId)).ToArray();
            applicable[0].Values[seriesMetric.MetricId] = JsonSerializer.SerializeToElement(configuration.Parameters[seriesMetric.MetricId].Expected!.Value + 5);
            applicable[1].Values[seriesMetric.MetricId] = null;
            var missing = await gateway.EvaluateAsync(configuration, input, timeout.Token);
            Assert.Equal("U", missing.Grade);
            Assert.False(missing.Passed);
            Assert.NotEqual("complete", missing.CalculationStatus);
            var incompleteMetric = Metric(missing, seriesMetric.MetricId);
            Assert.Equal("U", incompleteMetric.Grade);
            Assert.Equal(1, incompleteMetric.FrameDistribution!.MissingFrameCount);
            Assert.Equal(1, incompleteMetric.FrameDistribution.Counts["U"]);
            Assert.Null(incompleteMetric.Timeline[1].Grade);

            if (sceneId == "SCN-002")
            {
                var laserDefinition = catalog.Metrics.First(metric => metric.Comparison == "radial");
                var laserFrame = input.Items.Values.SelectMany(item => item.Frames!).First(frame => frame.Values.ContainsKey(laserDefinition.MetricId));
                laserFrame.Values[laserDefinition.MetricId] = JsonSerializer.SerializeToElement(new { status = "miss", u_m = (double?)null, v_m = (double?)null });
                var miss = await gateway.EvaluateAsync(configuration, input, timeout.Token);
                Assert.Equal("U", Metric(miss, laserDefinition.MetricId).Timeline[0].Grade);
                laserFrame.Values[laserDefinition.MetricId] = null;
                var unavailable = await gateway.EvaluateAsync(configuration, input, timeout.Token);
                Assert.Null(Metric(unavailable, laserDefinition.MetricId).Timeline[0].Grade);
                Assert.Equal(1, Metric(unavailable, laserDefinition.MetricId).FrameDistribution!.MissingFrameCount);
            }

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

    private static SceneInput SyntheticInput(SceneCatalog catalog, SceneConfiguration configuration)
    {
        // Deliberate arithmetic fixtures only; these are not aircraft or human-factors recommendations.
        foreach (var metric in catalog.Metrics.Where(metric => metric.Rule == "interval"))
        {
            configuration.Parameters[metric.MetricId] = metric.TargetMode == "item_profile"
                ? new SceneParameter { Expected = null,
                    ReferenceProfile = [new() { ElapsedS = 0, Expected = 100 },
                        new() { ElapsedS = metric.PhaseIds!.Sum(phaseId => PhaseDuration(phaseId) + 1) - 1, Expected = 100 }],
                    Desired = new() { Lower = -1, Upper = 1 }, Acceptable = new() { Lower = -3, Upper = 3 } }
                : metric.TargetMode == "phase_profile"
                ? new SceneParameter { Expected = null,
                    ReferenceProfiles = metric.PhaseIds!.ToDictionary(phaseId => phaseId, phaseId => new List<SceneReferencePoint>
                    {
                        new() { ElapsedS = 0, Expected = 100 },
                        new() { ElapsedS = PhaseDuration(phaseId), Expected = 50 },
                    }),
                    Desired = new() { Lower = -1, Upper = 1 }, Acceptable = new() { Lower = -3, Upper = 3 } }
                : metric.Comparison == "radial"
                ? new SceneParameter { Expected = 0, CenterU = 3, CenterV = -4, TargetRadius = 3,
                    Desired = new() { Lower = 0, Upper = 1 }, Acceptable = new() { Lower = 0, Upper = 2 } }
                : metric.Comparison == "route_3d"
                ? new SceneParameter { Expected = 0,
                    RoutePoints = [new() { XM = 0, YM = 0, HeightM = 100 }, new() { XM = 100, YM = 0, HeightM = 100 }],
                    Desired = new() { Lower = 0, Upper = 1 }, Acceptable = new() { Lower = 0, Upper = 2 } }
                : new SceneParameter { Expected = metric.Comparison == "angle_degrees" ? 359 : metric.DefaultExpected ?? 100,
                    Desired = new() { Lower = -1, Upper = 1 }, Acceptable = new() { Lower = -3, Upper = 3 } };
        }
        var input = new SceneInput { SchemaVersion = "3.0", SceneId = catalog.SceneId, Items = [] };
        var phaseStarts = new Dictionary<string, double>(StringComparer.Ordinal);
        var nextStart = 12.000000123;
        foreach (var phaseId in catalog.PhaseSequence!)
        {
            var phase = catalog.Items.SelectMany(item => item.Phases!).First(phase => phase.PhaseId == phaseId);
            phaseStarts[phaseId] = nextStart;
            nextStart += (phase.SingleFrame ? 0 : phase.RequiredDurationS ?? 1) + 1;
        }
        foreach (var item in catalog.Items)
        {
            var frames = new List<SceneFrame>();
            var metricIds = item.Checkpoints.SelectMany(checkpoint => checkpoint.MetricIds).ToHashSet(StringComparer.Ordinal);
            foreach (var phase in item.Phases!)
            {
                var timestamp = phaseStarts[phase.PhaseId];
                var applicable = catalog.Metrics.Where(metric => metricIds.Contains(metric.MetricId) && metric.PhaseIds!.Contains(phase.PhaseId)).ToList();
                frames.Add(Frame(timestamp));
                if (!phase.SingleFrame)
                {
                    if (applicable.Any(metric => metric.TargetMode == "phase_profile"))
                    {
                        frames.Add(Frame(timestamp + (phase.RequiredDurationS ?? 1) / 2));
                    }
                    frames.Add(Frame(timestamp + (phase.RequiredDurationS ?? 1)));
                }

                SceneFrame Frame(double time) => new()
                {
                    TimestampS = time, PhaseId = phase.PhaseId,
                    Values = applicable.ToDictionary(metric => metric.MetricId, metric => (JsonElement?)(metric.Rule switch
                    {
                        "must_be_true" => JsonSerializer.SerializeToElement(true),
                        "zero_events" => JsonSerializer.SerializeToElement(0),
                        _ when metric.Comparison == "radial" => JsonSerializer.SerializeToElement(new { status = "hit", u_m = 4, v_m = -4 }),
                        _ when metric.Comparison == "route_3d" => JsonSerializer.SerializeToElement(new { x_m = 50, y_m = 0, height_m = 100 }),
                        _ when metric.TargetMode == "phase_profile" => JsonSerializer.SerializeToElement(100 - 50 * (time - timestamp) / PhaseDuration(phase.PhaseId)),
                        _ when metric.TargetMode == "item_profile" => JsonSerializer.SerializeToElement(100),
                        _ => JsonSerializer.SerializeToElement(configuration.Parameters[metric.MetricId].Expected),
                    })),
                    Controls = new() { ["Pilot Lon"] = JsonSerializer.SerializeToElement(.125) },
                };
            }
            input.Items[item.ItemId] = new() { Frames = frames };
        }
        return input;

        double PhaseDuration(string phaseId) => catalog.Items.SelectMany(item => item.Phases!)
            .First(phase => phase.PhaseId == phaseId).RequiredDurationS ?? 1;
    }

    private static SceneMetricResult Metric(SceneReport report, string metricId) => report.Items
        .SelectMany(item => item.Checkpoints).SelectMany(checkpoint => checkpoint.Metrics).First(metric => metric.MetricId == metricId);

    private static bool JsonNodeEquals(string left, string right)
    {
        using var leftDocument = JsonDocument.Parse(left);
        using var rightDocument = JsonDocument.Parse(right);
        return JsonElement.DeepEquals(leftDocument.RootElement, rightDocument.RootElement);
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
