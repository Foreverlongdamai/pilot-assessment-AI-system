using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization.Metadata;

using PilotAssessment.Desktop.Core.Contracts;

namespace PilotAssessment.Desktop.UnitTests.Contracts;

public sealed class ContractSerializationTests
{
    [Fact]
    public void ModelNode_PythonEvidenceFixture_RoundTripsTypedRecipe()
    {
        var node = ReadFixture(
            "model-node-evidence.json",
            PilotAssessmentJsonContext.Default.ModelNode);

        Assert.Equal("evidence.precision", node.NodeId);
        Assert.Equal(ModelNodeKind.Evidence, node.NodeKind);
        var definition = Assert.IsType<EvidenceNodeDefinition>(node.Definition);
        Assert.Equal("recipe.evidence.precision", definition.Recipe.RecipeId);
        Assert.Equal(0.5, definition.Recipe.Scoring!.Parameters["desired_boundary"]!.GetValue<double>());

        AssertRoundTripEquivalent(
            "model-node-evidence.json",
            node,
            PilotAssessmentJsonContext.Default.ModelNode);
    }

    [Fact]
    public void WorkspaceFixtures_PreserveCanonicalIdsHashesAndOrdering()
    {
        var graph = ReadFixture(
            "model-graph-snapshot.json",
            PilotAssessmentJsonContext.Default.ModelGraphSnapshot);
        var change = ReadFixture(
            "model-change-event.json",
            PilotAssessmentJsonContext.Default.ModelChangeEvent);
        var operatorDefinition = ReadFixture(
            "operator-definition.json",
            PilotAssessmentJsonContext.Default.OperatorDefinition);

        Assert.Equal("project.alpha", graph.ProjectId);
        Assert.Equal(["raw.x"], graph.Scheme.ComputedActiveClosure);
        Assert.Equal("41b97e6b379f1d744d0b63a1937fcffd1044d31dddeb67cf6f41adb1b2e7eb2a", graph.GraphHash);
        Assert.Equal(["/name_en"], change.Diff.ChangedPaths);
        Assert.Equal("input.binding", operatorDefinition.OperatorId);

        AssertRoundTripEquivalent(
            "model-graph-snapshot.json",
            graph,
            PilotAssessmentJsonContext.Default.ModelGraphSnapshot);
        AssertRoundTripEquivalent(
            "model-change-event.json",
            change,
            PilotAssessmentJsonContext.Default.ModelChangeEvent);
        AssertRoundTripEquivalent(
            "operator-definition.json",
            operatorDefinition,
            PilotAssessmentJsonContext.Default.OperatorDefinition);
    }

    [Fact]
    public void ProjectAndSessionFixtures_RoundTripWithoutPathNormalization()
    {
        var project = ReadFixture(
            "project-descriptor.json",
            PilotAssessmentJsonContext.Default.ProjectDescriptor);
        var session = ReadFixture(
            "session-record.json",
            PilotAssessmentJsonContext.Default.SessionRecord);
        var revision = ReadFixture(
            "session-revision.json",
            PilotAssessmentJsonContext.Default.SessionRevision);

        Assert.Equal("project.alpha", project.ProjectId);
        Assert.Equal("session.alpha.rev1", session.CurrentSessionRevisionId);
        Assert.Equal(
            "sessions/session.alpha/revisions/session.alpha.rev1/bundle",
            revision.ManagedBundlePath);

        AssertRoundTripEquivalent(
            "project-descriptor.json",
            project,
            PilotAssessmentJsonContext.Default.ProjectDescriptor);
        AssertRoundTripEquivalent(
            "session-record.json",
            session,
            PilotAssessmentJsonContext.Default.SessionRecord);
        AssertRoundTripEquivalent(
            "session-revision.json",
            revision,
            PilotAssessmentJsonContext.Default.SessionRevision);
    }

    [Fact]
    public void IngestionReadinessFixture_RoundTripsSevenCanonicalModalities()
    {
        var report = ReadFixture(
            "ingestion_readiness_ready.json",
            PilotAssessmentJsonContext.Default.IngestionReadinessReport);

        Assert.Equal(ReadinessDisposition.Ready, report.Disposition);
        Assert.Equal(7, report.StreamResults.Count);
        Assert.Contains("I", report.StreamResults.Keys);
        Assert.Contains("G", report.StreamResults.Keys);
        Assert.Contains("EEG", report.StreamResults.Keys);
        Assert.Contains("ECG", report.StreamResults.Keys);
        Assert.False(report.FormalRunAuthorized);

        AssertRoundTripEquivalent(
            "ingestion_readiness_ready.json",
            report,
            PilotAssessmentJsonContext.Default.IngestionReadinessReport);
    }

    [Fact]
    public void CurrentRunFixtures_RoundTripFrozenSnapshotAndArtifactReferences()
    {
        var preflight = ReadFixture(
            "current-model-run-preflight.json",
            PilotAssessmentJsonContext.Default.CurrentModelRunPreflightReport);
        var run = ReadFixture(
            "assessment-run-v2.json",
            PilotAssessmentJsonContext.Default.AssessmentRunV2);
        var result = ReadFixture(
            "run-result-envelope.json",
            PilotAssessmentJsonContext.Default.RunResultEnvelope);

        Assert.Equal(TechnicalDisposition.Ready, preflight.TechnicalDisposition);
        Assert.Equal("scheme.current", run.Snapshot.Scheme.SchemeId);
        Assert.Equal("artifact.posterior", result.PosteriorRef.ArtifactId);

        AssertRoundTripEquivalent(
            "current-model-run-preflight.json",
            preflight,
            PilotAssessmentJsonContext.Default.CurrentModelRunPreflightReport);
        AssertRoundTripEquivalent(
            "assessment-run-v2.json",
            run,
            PilotAssessmentJsonContext.Default.AssessmentRunV2);
        AssertRoundTripEquivalent(
            "run-result-envelope.json",
            result,
            PilotAssessmentJsonContext.Default.RunResultEnvelope);
    }

    [Fact]
    public void ModelNode_UnknownEnumValue_IsRejected()
    {
        var payload = LoadFixtureNode("model-node-evidence.json").AsObject();
        payload["node_kind"] = "unknown_kind";

        Assert.Throws<JsonException>(
            () => JsonSerializer.Deserialize(
                payload.ToJsonString(),
                PilotAssessmentJsonContext.Default.ModelNode));
    }

    [Fact]
    public void ModelNode_MissingRequiredField_IsRejected()
    {
        var payload = LoadFixtureNode("model-node-evidence.json").AsObject();
        payload.Remove("node_id");

        Assert.Throws<JsonException>(
            () => JsonSerializer.Deserialize(
                payload.ToJsonString(),
                PilotAssessmentJsonContext.Default.ModelNode));
    }

    [Fact]
    public void ModelNode_UnknownField_IsRejected()
    {
        var payload = LoadFixtureNode("model-node-evidence.json").AsObject();
        payload["client_only_shadow_state"] = true;

        Assert.Throws<JsonException>(
            () => JsonSerializer.Deserialize(
                payload.ToJsonString(),
                PilotAssessmentJsonContext.Default.ModelNode));
    }

    [Fact]
    public void JsonRpcError_TypedRecoveryFields_ArePreserved()
    {
        const string json = """
            {
              "jsonrpc": "2.0",
              "id": "request.1",
              "error": {
                "code": -32020,
                "message": "revision conflict",
                "data": {
                  "error_code": "MODEL_REVISION_CONFLICT",
                  "message": "revision conflict",
                  "recoverable": true,
                  "trace_id": "trace.1",
                  "transaction_id": "tx.1",
                  "current_revision": 4,
                  "diagnostics": {
                    "current_node": {
                      "node_id": "raw.x"
                    }
                  }
                }
              }
            }
            """;

        var response = JsonSerializer.Deserialize(
            json,
            PilotAssessmentJsonContext.Default.JsonRpcErrorResponse);

        Assert.NotNull(response);
        Assert.Equal(DomainErrorCode.ModelRevisionConflict, response.Error.Data.ErrorCode);
        Assert.Equal(4, response.Error.Data.CurrentRevision!.Value.GetInt32());
        Assert.Equal("raw.x", response.Error.Data.Diagnostics!["current_node"]!["node_id"]!.GetValue<string>());
    }

    [Fact]
    public void JsonRpcError_ProtocolFaultWithoutDomainRecoveryFields_IsAccepted()
    {
        const string json = """
            {
              "jsonrpc": "2.0",
              "id": null,
              "error": {
                "code": -32602,
                "message": "Invalid params",
                "data": {
                  "error_code": "INVALID_PARAMS",
                  "trace_id": "trace.2",
                  "detail": "node_id is required",
                  "path": "/node_id"
                }
              }
            }
            """;

        var response = JsonSerializer.Deserialize(
            json,
            PilotAssessmentJsonContext.Default.JsonRpcErrorResponse);

        Assert.NotNull(response);
        Assert.Equal(DomainErrorCode.InvalidParams, response.Error.Data.ErrorCode);
        Assert.Null(response.Error.Data.Recoverable);
        Assert.Equal("/node_id", response.Error.Data.Path);
    }

    private static T ReadFixture<T>(string fileName, JsonTypeInfo<T> typeInfo)
    {
        var json = File.ReadAllText(FixturePath(fileName));
        var result = JsonSerializer.Deserialize(json, typeInfo);
        Assert.NotNull(result);
        return result;
    }

    private static void AssertRoundTripEquivalent<T>(
        string fileName,
        T value,
        JsonTypeInfo<T> typeInfo)
    {
        var expected = LoadFixtureNode(fileName);
        var actual = JsonNode.Parse(JsonSerializer.Serialize(value, typeInfo));

        Assert.NotNull(actual);
        Assert.True(JsonNode.DeepEquals(expected, actual));
    }

    private static JsonNode LoadFixtureNode(string fileName)
    {
        var node = JsonNode.Parse(File.ReadAllText(FixturePath(fileName)));
        Assert.NotNull(node);
        return node;
    }

    private static string FixturePath(string fileName) =>
        Path.Combine(AppContext.BaseDirectory, "Fixtures", fileName);
}
