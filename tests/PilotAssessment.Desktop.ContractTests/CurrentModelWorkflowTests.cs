using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

using PilotAssessment.Desktop.Core.Protocol;

namespace PilotAssessment.Desktop.ContractTests;

public sealed class CurrentModelWorkflowTests
{
    [Fact]
    public async Task RealSidecar_StagedModelWorkflowCommitsAndPersistsWithoutPublish()
    {
        var repositoryRoot = FindRepositoryRoot(AppContext.BaseDirectory);
        var uvPath = Path.Combine(repositoryRoot, ".tools", "uv", "uv.exe");
        Assert.True(File.Exists(uvPath), $"Repository uv executable was not found at {uvPath}");
        var temporaryRoot = Path.Combine(
            Path.GetTempPath(),
            $"pilot-assessment-m7b-current-workflow-{Guid.NewGuid():N}");
        var bundleRoot = Path.Combine(temporaryRoot, "fixture");
        var projectRoot = Path.Combine(temporaryRoot, "project");
        Directory.CreateDirectory(temporaryRoot);

        await BuildLightweightBundleAsync(repositoryRoot, uvPath, bundleRoot);

        using var process = new Process
        {
            StartInfo = CreateSidecarStartInfo(
                repositoryRoot,
                uvPath,
                Path.Combine(temporaryRoot, "system")),
        };
        Assert.True(process.Start());
        var stderrTask = process.StandardError.ReadToEndAsync();
        await using var client = new JsonRpcClient(
            new JsonLineFramer(
                process.StandardOutput.BaseStream,
                process.StandardInput.BaseStream));

        var runId = $"run.contract.task15.{Guid.NewGuid():N}";
        string? copiedNodeId = null;
        string? resultId = null;
        string? resultHash = null;

        try
        {
            _ = await CallAsync(
                client,
                "runtime.hello",
                new JsonObject
                {
                    ["protocol_version"] = "1.0",
                    ["supported_protocols"] = new JsonArray { "1.0" },
                    ["client"] = new JsonObject
                    {
                        ["name"] = "PilotAssessment.Desktop.ContractTests",
                        ["version"] = "0.1.0",
                    },
                });

            var create = Mutation($"tx.contract.project.{Guid.NewGuid():N}");
            create["root"] = projectRoot;
            create["project_id"] = $"project.contract.task15.{Guid.NewGuid():N}";
            create["name"] = "M7B Task 15 current-model contract";
            _ = await CallAsync(client, "project.create", create);

            var schemes = await CallAsync(client, "model.scheme.list");
            var baseScheme = Assert.Single(Array(schemes, "schemes"))!.AsObject();
            var baseSchemeId = Text(baseScheme, "scheme_id");
            var copyScheme = Mutation($"tx.contract.scheme-copy.{Guid.NewGuid():N}");
            copyScheme["source_scheme_id"] = baseSchemeId;
            copyScheme["new_scheme_id"] = $"task-scheme.contract.{Guid.NewGuid():N}";
            copyScheme["name"] = "Task 15 contract scheme";
            var copiedSchemeResponse = await CallAsync(client, "model.scheme.copy", copyScheme);
            var copiedScheme = Object(copiedSchemeResponse, "scheme");
            var schemeId = Text(copiedScheme, "scheme_id");

            var graphResponse = await CallAsync(
                client,
                "model.graph.get",
                new JsonObject { ["scheme_id"] = schemeId });
            var graph = Object(graphResponse, "graph");
            var source = Array(graph, "nodes")
                .Select(node => node!.AsObject())
                .First(node =>
                    Text(node, "node_kind") == "evidence" &&
                    Object(node, "definition")["recipe"]?["scoring"] is not null);
            var sourceNodeId = Text(source, "node_id");

            var copyNode = Mutation($"tx.contract.node-copy.{Guid.NewGuid():N}");
            copyNode["scheme_id"] = schemeId;
            copyNode["copy_node_ids"] = new JsonArray { sourceNodeId };
            copyNode["activate_node_ids"] = new JsonArray();
            copyNode["layout_updates"] = new JsonArray();
            copyNode["expected_semantic_revision"] = Number(copiedScheme, "semantic_revision");
            copyNode["expected_layout_revision"] = Number(copiedScheme, "layout_revision");
            var copiedBatch = await CallAsync(client, "model.graph.batch.apply", copyNode);
            var copiedNode = Assert.Single(Array(copiedBatch, "copied_nodes"))!.AsObject();
            copiedNodeId = Text(copiedNode, "node_id");
            var schemeAfterCopy = Object(copiedBatch, "scheme");
            Assert.Contains(
                copiedNodeId,
                Array(schemeAfterCopy, "computed_active_closure").Select(node => node!.GetValue<string>()));

            var preview = await CallAsync(
                client,
                "model.scheme.deactivation.preview",
                new JsonObject
                {
                    ["scheme_id"] = schemeId,
                    ["node_id"] = copiedNodeId,
                });
            var impact = Object(preview, "impact");
            var deactivate = Mutation($"tx.contract.deactivate.{Guid.NewGuid():N}");
            deactivate["scheme_id"] = schemeId;
            deactivate["node_id"] = copiedNodeId;
            deactivate["expected_semantic_revision"] = Number(schemeAfterCopy, "semantic_revision");
            deactivate["impact_hash"] = Text(impact, "impact_hash");
            var deactivatedResponse = await CallAsync(client, "model.scheme.deactivate", deactivate);
            var deactivated = Object(deactivatedResponse, "scheme");
            Assert.DoesNotContain(
                copiedNodeId,
                Array(deactivated, "computed_active_closure").Select(node => node!.GetValue<string>()));

            var activate = Mutation($"tx.contract.activate.{Guid.NewGuid():N}");
            activate["scheme_id"] = schemeId;
            activate["node_id"] = copiedNodeId;
            activate["expected_semantic_revision"] = Number(deactivated, "semantic_revision");
            var activatedResponse = await CallAsync(client, "model.scheme.activate", activate);
            var activated = Object(activatedResponse, "scheme");
            Assert.Contains(
                copiedNodeId,
                Array(activated, "computed_active_closure").Select(node => node!.GetValue<string>()));

            var nodeResponse = await CallAsync(
                client,
                "model.node.get",
                new JsonObject { ["node_id"] = copiedNodeId });
            var editableNode = Object(nodeResponse, "node").DeepClone().AsObject();
            var editedName = $"Task 15 edited node {Guid.NewGuid():N}";
            editableNode["name"] = editedName;
            var updateNode = Mutation($"tx.contract.node-update.{Guid.NewGuid():N}");
            updateNode["node"] = editableNode.DeepClone();
            updateNode["expected_semantic_revision"] = Number(editableNode, "semantic_revision");
            var updatedResponse = await CallAsync(client, "model.node.update", updateNode);
            Assert.Equal(editedName, Text(Object(updatedResponse, "node"), "name"));

            var importSession = Mutation($"tx.contract.session-import.{Guid.NewGuid():N}");
            importSession["external_bundle"] = bundleRoot;
            var imported = await CallAsync(client, "session.import", importSession);
            var revisionId = Text(Object(imported, "revision"), "session_revision_id");

            var dirtyStatus = Object(
                await CallAsync(client, "model.edit.status"),
                "edit_session");
            Assert.True(dirtyStatus["dirty"]!.GetValue<bool>());
            var commit = Mutation($"tx.contract.edit-commit.{Guid.NewGuid():N}");
            var committed = await CallAsync(client, "model.edit.commit", commit);
            Assert.False(Object(committed, "edit_session")["dirty"]!.GetValue<bool>());

            var currentSchemeResponse = await CallAsync(
                client,
                "model.scheme.get",
                new JsonObject { ["scheme_id"] = schemeId });
            var currentScheme = Object(currentSchemeResponse, "scheme");

            var preflightResponse = await CallAsync(
                client,
                "model.run.preflight",
                new JsonObject
                {
                    ["session_revision_id"] = revisionId,
                    ["scheme_id"] = schemeId,
                    ["purpose"] = "software_test",
                    ["runtime_parameters"] = new JsonObject(),
                });
            var preflight = Object(preflightResponse, "preflight");
            Assert.Equal("ready", Text(preflight, "technical_disposition"));

            var startRun = Mutation($"tx.contract.run-start.{Guid.NewGuid():N}");
            startRun["preflight_id"] = Text(preflight, "preflight_id");
            startRun["run_id"] = runId;
            startRun["expected_scheme_revision"] = Number(currentScheme, "semantic_revision");
            var startedResponse = await CallAsync(client, "model.run.start", startRun);
            var started = Object(startedResponse, "run");
            var snapshotHash = Text(Object(started, "snapshot"), "snapshot_hash");

            var completed = await WaitForCompletionAsync(client, runId);
            Assert.Equal(snapshotHash, Text(Object(completed, "snapshot"), "snapshot_hash"));
            var resultResponse = await CallAsync(
                client,
                "result.get",
                new JsonObject { ["run_id"] = runId });
            var result = Object(resultResponse, "result");
            resultId = Text(result, "result_id");
            resultHash = Text(result, "result_hash");
            Assert.Equal(snapshotHash, Text(result, "snapshot_hash"));

            var listed = await CallAsync(client, "model.run.list");
            Assert.Contains(
                Array(listed, "runs"),
                item => Text(Object(item!.AsObject(), "run"), "run_id") == runId);

            _ = await CallAsync(client, "project.close");
            _ = await CallAsync(
                client,
                "project.open",
                new JsonObject { ["root"] = projectRoot });
            var reopenedNode = Object(
                await CallAsync(
                    client,
                    "model.node.get",
                    new JsonObject { ["node_id"] = copiedNodeId }),
                "node");
            Assert.Equal(editedName, Text(reopenedNode, "name"));
            var reopenedResult = Object(
                await CallAsync(
                    client,
                    "result.get",
                    new JsonObject { ["run_id"] = runId }),
                "result");
            Assert.Equal(resultId, Text(reopenedResult, "result_id"));
            Assert.Equal(resultHash, Text(reopenedResult, "result_hash"));

            _ = await CallAsync(client, "runtime.shutdown");
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(15));
            await process.WaitForExitAsync(timeout.Token);
            Assert.Equal(0, process.ExitCode);
            Assert.DoesNotContain("Traceback", await stderrTask, StringComparison.Ordinal);
        }
        finally
        {
            if (!process.HasExited)
            {
                process.Kill(entireProcessTree: true);
                await process.WaitForExitAsync();
            }

            if (Directory.Exists(temporaryRoot))
            {
                Directory.Delete(temporaryRoot, recursive: true);
            }
        }

        Assert.NotNull(copiedNodeId);
        Assert.NotNull(resultId);
        Assert.NotNull(resultHash);
    }

    private static async Task<JsonObject> WaitForCompletionAsync(JsonRpcClient client, string runId)
    {
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        while (!timeout.IsCancellationRequested)
        {
            var response = await CallAsync(
                client,
                "run.status",
                new JsonObject { ["run_id"] = runId });
            var run = Object(response, "run");
            var state = Text(run, "state");
            if (state is "completed")
            {
                return run;
            }

            Assert.DoesNotContain(state, new[] { "failed", "cancelled", "interrupted" });
            await Task.Delay(50, timeout.Token);
        }

        throw new TimeoutException($"Current-model run {runId} did not complete in 30 seconds.");
    }

    private static async Task BuildLightweightBundleAsync(
        string repositoryRoot,
        string uvPath,
        string outputRoot)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = uvPath,
            WorkingDirectory = repositoryRoot,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        foreach (var argument in new[]
                 {
                     "run",
                     "python",
                     "tests/m4_support/fixture_builder.py",
                     "--recipe",
                     "tests/fixtures/m4/m4-workflow-smoke-recipe-v0.1.json",
                     "--case-id",
                     "m4-workflow-smoke-v0.1",
                     "--output-root",
                     outputRoot,
                 })
        {
            startInfo.ArgumentList.Add(argument);
        }

        using var process = new Process { StartInfo = startInfo };
        Assert.True(process.Start());
        var standardOutput = process.StandardOutput.ReadToEndAsync();
        var standardError = process.StandardError.ReadToEndAsync();
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        await process.WaitForExitAsync(timeout.Token);
        Assert.True(
            process.ExitCode == 0,
            $"Lightweight fixture builder failed. stdout: {await standardOutput}; stderr: {await standardError}");
        Assert.True(File.Exists(Path.Combine(outputRoot, "manifest.json")));
    }

    private static async Task<JsonObject> CallAsync(
        JsonRpcClient client,
        string method,
        JsonObject? parameters = null)
    {
        var element = parameters is null
            ? ParseElement("{}")
            : JsonSerializer.SerializeToElement(parameters);
        var response = await client.InvokeAsync(method, element);
        return JsonNode.Parse(response.GetRawText())?.AsObject()
            ?? throw new JsonException($"Sidecar method {method} returned an empty response.");
    }

    private static JsonObject Mutation(string transactionId) => new()
    {
        ["transaction_id"] = transactionId,
        ["actor"] = "contract.task15",
    };

    private static JsonObject Object(JsonObject parent, string property) =>
        parent[property]?.AsObject()
        ?? throw new JsonException($"Expected object property {property}.");

    private static JsonArray Array(JsonObject parent, string property) =>
        parent[property]?.AsArray()
        ?? throw new JsonException($"Expected array property {property}.");

    private static string Text(JsonObject parent, string property) =>
        parent[property]?.GetValue<string>()
        ?? throw new JsonException($"Expected string property {property}.");

    private static int Number(JsonObject parent, string property) =>
        parent[property]?.GetValue<int>()
        ?? throw new JsonException($"Expected integer property {property}.");

    private static JsonElement ParseElement(string json)
    {
        using var document = JsonDocument.Parse(json);
        return document.RootElement.Clone();
    }

    private static ProcessStartInfo CreateSidecarStartInfo(
        string repositoryRoot,
        string uvPath,
        string systemRoot)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = uvPath,
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
        foreach (var argument in new[] { "run", "python", "-m", "pilot_assessment.sidecar" })
        {
            startInfo.ArgumentList.Add(argument);
        }
        startInfo.Environment["PILOT_ASSESSMENT_SYSTEM_ROOT"] = systemRoot;

        return startInfo;
    }

    private static string FindRepositoryRoot(string startDirectory)
    {
        for (var directory = new DirectoryInfo(startDirectory); directory is not null; directory = directory.Parent)
        {
            if (File.Exists(Path.Combine(directory.FullName, "pyproject.toml")) &&
                Directory.Exists(Path.Combine(directory.FullName, "src", "pilot_assessment")))
            {
                return directory.FullName;
            }
        }

        throw new DirectoryNotFoundException(
            $"Could not locate pilot_assessment_system above {startDirectory}");
    }
}
