using System.Diagnostics;
using System.Text;
using System.Text.Json;

using PilotAssessment.Desktop.Core.Contracts;
using PilotAssessment.Desktop.Core.Protocol;
using PilotAssessment.Desktop.Core.State;

namespace PilotAssessment.Desktop.ContractTests;

public sealed class SidecarContractTests
{
    [Fact]
    public async Task RealPythonSidecar_HelloCapabilitiesHealthAndShutdownUseJsonlOnly()
    {
        var repositoryRoot = FindRepositoryRoot(AppContext.BaseDirectory);
        var uvPath = Path.Combine(repositoryRoot, ".tools", "uv", "uv.exe");
        Assert.True(File.Exists(uvPath), $"Repository uv executable was not found at {uvPath}");
        var systemRoot = Path.Combine(
            Path.GetTempPath(),
            $"pilot-assessment-contract-system-{Guid.NewGuid():N}");
        var startInfo = CreateSidecarStartInfo(repositoryRoot, uvPath, systemRoot);

        using var process = new Process { StartInfo = startInfo };
        Assert.True(process.Start());
        var stderrTask = process.StandardError.ReadToEndAsync();
        await using var client = new JsonRpcClient(
            new JsonLineFramer(
                process.StandardOutput.BaseStream,
                process.StandardInput.BaseStream));

        try
        {
            var hello = await client.InvokeAsync(
                "runtime.hello",
                ParseElement("""
                    {
                      "protocol_version": "1.0",
                      "supported_protocols": ["1.0"],
                      "client": {
                        "name": "PilotAssessment.Desktop.ContractTests",
                        "version": "0.1.0"
                      }
                    }
                    """));
            Assert.Equal("1.0", hello.GetProperty("protocol_version").GetString());
            Assert.Equal("ready", hello.GetProperty("state").GetString());
            var capabilities = hello.GetProperty("capabilities")
                .EnumerateArray()
                .Select(value => value.GetString())
                .ToArray();
            Assert.Contains("runtime.protocol.v1", capabilities);
            Assert.Contains("model.current-workspace.v1", capabilities);

            var catalog = await client.InvokeAsync("capabilities.list", EmptyObject());
            Assert.Contains(
                catalog.GetProperty("methods").EnumerateArray(),
                value => value.GetString() == "runtime.shutdown");

            var status = await client.InvokeAsync("runtime.status", EmptyObject());
            Assert.Equal("ready", status.GetProperty("state").GetString());
            Assert.False(status.GetProperty("project_open").GetBoolean());

            foreach (var result in new[] { hello, catalog, status })
            {
                Assert.Equal(JsonValueKind.Object, result.ValueKind);
                Assert.DoesNotContain("\"payload\"", result.GetRawText(), StringComparison.Ordinal);
                Assert.DoesNotContain("\"bytes\"", result.GetRawText(), StringComparison.Ordinal);
                Assert.True(result.GetRawText().Length < 128 * 1024);
            }

            var shutdown = await client.InvokeAsync("runtime.shutdown", EmptyObject());
            Assert.Equal("stopping", shutdown.GetProperty("state").GetString());
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

            if (Directory.Exists(systemRoot))
            {
                Directory.Delete(systemRoot, recursive: true);
            }
        }
    }

    [Fact]
    public async Task RealPythonSidecar_AcceptsTypedNodeActivationAndDeactivationContracts()
    {
        var repositoryRoot = FindRepositoryRoot(AppContext.BaseDirectory);
        var uvPath = Path.Combine(repositoryRoot, ".tools", "uv", "uv.exe");
        var projectRoot = Path.Combine(
            Path.GetTempPath(),
            $"pilot-assessment-m7b-contract-{Guid.NewGuid():N}");
        var systemRoot = Path.Combine(
            Path.GetTempPath(),
            $"pilot-assessment-contract-system-{Guid.NewGuid():N}");
        var startInfo = CreateSidecarStartInfo(repositoryRoot, uvPath, systemRoot);

        using var process = new Process { StartInfo = startInfo };
        Assert.True(process.Start());
        var stderrTask = process.StandardError.ReadToEndAsync();
        await using var client = new JsonRpcClient(
            new JsonLineFramer(
                process.StandardOutput.BaseStream,
                process.StandardInput.BaseStream));

        try
        {
            _ = await client.InvokeAsync(
                "runtime.hello",
                ParseElement("""
                    {
                      "protocol_version": "1.0",
                      "supported_protocols": ["1.0"],
                      "client": {
                        "name": "PilotAssessment.Desktop.ContractTests",
                        "version": "0.1.0"
                      }
                    }
                    """));

            const string actor = "contract.test";
            var createProject = new ProjectCreateRequest(
                $"tx.contract.project.{Guid.NewGuid():N}",
                actor,
                projectRoot,
                $"project.contract.{Guid.NewGuid():N}",
                "M7B contract project");
            _ = Deserialize(
                await client.InvokeAsync(
                    "project.create",
                    JsonSerializer.SerializeToElement(
                        createProject,
                        PilotAssessmentJsonContext.Default.ProjectCreateRequest)),
                PilotAssessmentJsonContext.Default.ProjectMutationResponse);

            var schemes = Deserialize(
                await client.InvokeAsync("model.scheme.list", EmptyObject()),
                PilotAssessmentJsonContext.Default.TaskSchemeListResponse);
            var scheme = Assert.Single(schemes.Schemes);
            var drafts = new[]
            {
                ModelNodeDraftFactory.Create(new ModelNodeDraftRequest(
                    ModelNodeKind.RawInput,
                    "Contract smoke Raw Input",
                    RawModality.G,
                    640,
                    280)),
                ModelNodeDraftFactory.Create(new ModelNodeDraftRequest(
                    ModelNodeKind.Evidence,
                    "Contract smoke Evidence",
                    RawModality.X,
                    840,
                    280)),
                ModelNodeDraftFactory.Create(new ModelNodeDraftRequest(
                    ModelNodeKind.Bn,
                    "Contract smoke BN",
                    RawModality.X,
                    1040,
                    280)),
            };
            var createdNodes = new List<ModelNodeMutationResponse>();
            foreach (var draft in drafts)
            {
                var createNode = new ModelNodeCreateRequest(
                    draft,
                    actor,
                    $"tx.contract.node.{Guid.NewGuid():N}");
                var createdNode = Deserialize(
                    await client.InvokeAsync(
                        "model.node.create",
                        JsonSerializer.SerializeToElement(
                            createNode,
                            PilotAssessmentJsonContext.Default.ModelNodeCreateRequest)),
                    PilotAssessmentJsonContext.Default.ModelNodeMutationResponse);

                Assert.Equal(draft.NodeId, createdNode.Node.NodeId);
                Assert.Empty(createdNode.AffectedSchemeIds);
                createdNodes.Add(createdNode);
            }

            var createdEvidence = createdNodes.Single(
                response => response.Node.NodeKind is ModelNodeKind.Evidence);
            var createdRawInput = createdNodes.Single(
                response => response.Node.NodeKind is ModelNodeKind.RawInput);
            Assert.Equal(ModelTechnicalStatus.Incomplete, createdEvidence.Node.TechnicalStatus);

            var extractionEdit = EvidenceRecipeEdgeEditor.AddRawInput(
                createdEvidence.Node,
                createdRawInput.Node);
            var extractionRequest = new ExtractionEdgeAddRequest(
                "extraction",
                createdEvidence.Node.NodeId,
                createdRawInput.Node.NodeId,
                extractionEdit.RecipeInputBindingId,
                extractionEdit.UpdatedRecipe,
                createdEvidence.Node.SemanticRevision,
                actor,
                $"tx.contract.edge.{Guid.NewGuid():N}");
            var created = Deserialize(
                await client.InvokeAsync(
                    "model.edge.add",
                    JsonSerializer.SerializeToElement(
                        extractionRequest,
                        PilotAssessmentJsonContext.Default.ExtractionEdgeAddRequest)),
                PilotAssessmentJsonContext.Default.ModelNodeMutationResponse);
            Assert.Contains(
                ((EvidenceNodeDefinition)created.Node.Definition).DataBindings,
                binding => binding.RawInputNode.NodeId == createdRawInput.Node.NodeId);
            Assert.Equal(ModelTechnicalStatus.Incomplete, created.Node.TechnicalStatus);
            Assert.Contains(
                created.Node.Diagnostics,
                diagnostic => diagnostic.Code == "model.recipe.primary_output_missing");

            var activate = new SchemeNodeActivationRequest(
                scheme.SchemeId,
                created.Node.NodeId,
                scheme.SemanticRevision,
                actor,
                $"tx.contract.activate.{Guid.NewGuid():N}");
            var activated = Deserialize(
                await client.InvokeAsync(
                    "model.scheme.activate",
                    JsonSerializer.SerializeToElement(
                        activate,
                        PilotAssessmentJsonContext.Default.SchemeNodeActivationRequest)),
                PilotAssessmentJsonContext.Default.TaskSchemeMutationResponse);
            Assert.Contains(created.Node.NodeId, activated.Scheme.ComputedActiveClosure);
            Assert.Contains(createdRawInput.Node.NodeId, activated.Scheme.ComputedActiveClosure);

            var source = activated.Graph.Nodes.First(node =>
                node.NodeKind is ModelNodeKind.Evidence &&
                ((EvidenceNodeDefinition)node.Definition).OrderedProbabilisticParentNodes.Length > 0);
            var copyBatch = new GraphBatchApplyRequest(
                scheme.SchemeId,
                [source.NodeId],
                [],
                [],
                activated.Scheme.SemanticRevision,
                activated.Scheme.LayoutRevision,
                actor,
                $"tx.contract.copy.{Guid.NewGuid():N}");
            var copied = Deserialize(
                await client.InvokeAsync(
                    "model.graph.batch.apply",
                    JsonSerializer.SerializeToElement(
                        copyBatch,
                        PilotAssessmentJsonContext.Default.GraphBatchApplyRequest)),
                PilotAssessmentJsonContext.Default.GraphBatchMutationResponse);
            var copiedNode = Assert.Single(copied.CopiedNodes);
            Assert.Equal(source.NodeId, copiedNode.CopiedFromNodeId);
            Assert.Equal(
                ((EvidenceNodeDefinition)source.Definition).OrderedProbabilisticParentNodes,
                ((EvidenceNodeDefinition)copiedNode.Definition).OrderedProbabilisticParentNodes);

            var previewRequest = new SchemeDeactivationPreviewRequest(
                scheme.SchemeId,
                created.Node.NodeId);
            var preview = Deserialize(
                await client.InvokeAsync(
                    "model.scheme.deactivation.preview",
                    JsonSerializer.SerializeToElement(
                        previewRequest,
                        PilotAssessmentJsonContext.Default.SchemeDeactivationPreviewRequest)),
                PilotAssessmentJsonContext.Default.SchemeDeactivationPreviewResponse);
            Assert.Contains(created.Node.NodeId, preview.Impact.ImpactedNodeIds);

            var deactivate = new SchemeNodeDeactivationRequest(
                scheme.SchemeId,
                created.Node.NodeId,
                copied.Scheme.SemanticRevision,
                preview.Impact.ImpactHash,
                actor,
                $"tx.contract.deactivate.{Guid.NewGuid():N}");
            var deactivated = Deserialize(
                await client.InvokeAsync(
                    "model.scheme.deactivate",
                    JsonSerializer.SerializeToElement(
                        deactivate,
                        PilotAssessmentJsonContext.Default.SchemeNodeDeactivationRequest)),
                PilotAssessmentJsonContext.Default.TaskSchemeMutationResponse);
            Assert.DoesNotContain(created.Node.NodeId, deactivated.Scheme.ComputedActiveClosure);

            _ = await client.InvokeAsync("project.close", EmptyObject());
            _ = await client.InvokeAsync("runtime.shutdown", EmptyObject());
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

            if (Directory.Exists(projectRoot))
            {
                Directory.Delete(projectRoot, recursive: true);
            }

            if (Directory.Exists(systemRoot))
            {
                Directory.Delete(systemRoot, recursive: true);
            }
        }
    }

    private static JsonElement EmptyObject() => ParseElement("{}");

    private static JsonElement ParseElement(string json)
    {
        using var document = JsonDocument.Parse(json);
        return document.RootElement.Clone();
    }

    private static T Deserialize<T>(JsonElement element, System.Text.Json.Serialization.Metadata.JsonTypeInfo<T> type) =>
        element.Deserialize(type)
        ?? throw new JsonException($"The sidecar response for {typeof(T).Name} was empty.");

    private static ProcessStartInfo CreateSidecarStartInfo(
        string repositoryRoot,
        string uvPath,
        string systemRoot)
    {
        Assert.True(File.Exists(uvPath), $"Repository uv executable was not found at {uvPath}");
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
