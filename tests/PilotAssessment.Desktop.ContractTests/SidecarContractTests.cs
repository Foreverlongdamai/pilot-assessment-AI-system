using System.Diagnostics;
using System.Text;
using System.Text.Json;

using PilotAssessment.Desktop.Core.Protocol;

namespace PilotAssessment.Desktop.ContractTests;

public sealed class SidecarContractTests
{
    [Fact]
    public async Task RealPythonSidecar_HelloCapabilitiesHealthAndShutdownUseJsonlOnly()
    {
        var repositoryRoot = FindRepositoryRoot(AppContext.BaseDirectory);
        var uvPath = Path.Combine(repositoryRoot, ".tools", "uv", "uv.exe");
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
        }
    }

    private static JsonElement EmptyObject() => ParseElement("{}");

    private static JsonElement ParseElement(string json)
    {
        using var document = JsonDocument.Parse(json);
        return document.RootElement.Clone();
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
