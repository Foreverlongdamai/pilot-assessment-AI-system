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

        Assert.Equal("model-library.alpha", graph.ModelLibraryId);
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
    public void RuntimeStatus_RoundTripsTypedSystemAndProjectCompatibility()
    {
        const string json = """
            {
              "state": "ready",
              "project_open": true,
              "project_id": "project.alpha",
              "active_run_ids": [],
              "trace_id": "trace.runtime-status",
              "system_ready": true,
              "model_library_id": "model-library.alpha",
              "system_model": {
                "model_library_id": "model-library.alpha",
                "model_identity_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "format_version": "0.1.0",
                "database_schema_version": 5,
                "node_count": 54,
                "scheme_count": 2,
                "edit_session_dirty": false,
                "recovery_diagnostics": []
              },
              "project_compatibility": {
                "project_id": "project.alpha",
                "format_version": "0.1.0",
                "database_schema_version": 5,
                "compatibility": "compatible",
                "recovery_diagnostics": [],
                "recovered_run_count": 0
              }
            }
            """;

        var status = JsonSerializer.Deserialize(
            json,
            PilotAssessmentJsonContext.Default.RuntimeStatusResponse);

        Assert.NotNull(status);
        Assert.Equal(54, status.SystemModel!.NodeCount);
        Assert.Equal(2, status.SystemModel.SchemeCount);
        Assert.False(status.SystemModel.EditSessionDirty);
        Assert.Equal("compatible", status.ProjectCompatibility!.Compatibility);
        Assert.Equal(5, status.ProjectCompatibility.DatabaseSchemaVersion);

        var expected = JsonNode.Parse(json);
        var actual = JsonNode.Parse(JsonSerializer.Serialize(
            status,
            PilotAssessmentJsonContext.Default.RuntimeStatusResponse));
        Assert.True(JsonNode.DeepEquals(expected, actual));
    }

    [Fact]
    public void RawSessionInspection_PreservesUndeclaredUnitWithoutUserInput()
    {
        const string json = """
            {
              "contract_version": "0.1.0",
              "source_kind": "simulator_raw",
              "report": null,
              "raw": {
                "contract_version": "0.1.0",
                "source_snapshot_fingerprint": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "detected_profile_id": "cranfield-simulator-combined-csv-raw-v0.1",
                "profile_candidates": ["cranfield-simulator-combined-csv-raw-v0.1"],
                "files": [{
                  "relative_path": "streams/simulator.csv",
                  "byte_size": 128,
                  "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                }],
                "field_mappings": [{
                  "source_path": "streams/simulator.csv",
                  "source_field": "Pilot Yaw",
                  "canonical_field": "control.yaw_raw",
                  "modality": "U",
                  "physical_dtype": "f64",
                  "declared_unit": null,
                  "unit_provenance": "undeclared",
                  "timestamp_role": "measurement",
                  "resolution_status": "resolved"
                }],
                "modality_proposals": {
                  "U": {
                    "modality": "U",
                    "status": "present",
                    "paths": ["streams/simulator.csv"],
                    "format": "csv",
                    "schema_id": "cranfield-simulator-combined-csv-raw-v0.1",
                    "clock_id": "simulator-clock",
                    "sample_rate_hz": 100.0,
                    "declared_units": {},
                    "unit_handling": "undeclared-pass-through-v1"
                  }
                },
                "annotation_mappings": [],
                "required_user_inputs": [],
                "warnings": [],
                "can_materialize": true
              },
              "trace_id": "trace.raw"
            }
            """;

        var inspected = JsonSerializer.Deserialize(
            json,
            PilotAssessmentJsonContext.Default.SessionSourceInspectionResponse);

        Assert.NotNull(inspected);
        Assert.Equal(SessionDataSourceKind.SimulatorRaw, inspected.SourceKind);
        Assert.True(inspected.Raw!.CanMaterialize);
        Assert.Empty(inspected.Raw.RequiredUserInputs);
        Assert.Null(inspected.Raw.FieldMappings[0].DeclaredUnit);
        Assert.Equal(UnitProvenance.Undeclared, inspected.Raw.FieldMappings[0].UnitProvenance);
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
    public void ModelEditSessionResponse_DeserializesOptionalCommitDetails()
    {
        const string json = """
            {
              "edit_session": {
                "contract_id": "model-edit-session-status",
                "contract_version": "0.2.0",
                "session_id": "model-edit-session.1",
                "model_library_id": "model-library.alpha",
                "base_fingerprint": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "cursor": 0,
                "latest_sequence": 0,
                "dirty": false,
                "can_undo": false,
                "can_redo": false,
                "change_count": 0,
                "recovered": false
              },
              "transaction_id": "tx.edit.commit",
              "audit_event_id": "audit.edit.commit",
              "replayed": false,
              "trace_id": "trace.edit.commit",
              "changed_node_ids": ["evidence.precision"],
              "changed_scheme_ids": ["scheme.hover"]
            }
            """;

        var response = JsonSerializer.Deserialize(
            json,
            PilotAssessmentJsonContext.Default.ModelEditSessionMutationResponse);

        Assert.NotNull(response);
        Assert.False(response.EditSession.Dirty);
        Assert.Equal(["evidence.precision"], response.ChangedNodeIds!);
        Assert.Equal(["scheme.hover"], response.ChangedSchemeIds!);
        Assert.Null(response.DiscardedChangeCount);
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
