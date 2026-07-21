from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pilot_assessment.sidecar import JsonRpcDispatcher, SidecarMethods

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


class RpcHarness:
    def __init__(self, methods: SidecarMethods) -> None:
        self.dispatcher = JsonRpcDispatcher(
            runtime_id="runtime.methods-test",
            trace_id_factory=self._trace_id,
        )
        methods.register(self.dispatcher)
        self._sequence = 0
        self.call(
            "runtime.hello",
            {
                "protocol_version": "1.0",
                "supported_protocols": ["1.0"],
                "client": {"name": "pytest", "version": "0.1.0"},
            },
        )

    def _trace_id(self) -> str:
        self._sequence += 1
        return f"trace.methods.{self._sequence}"

    def call(self, method: str, params: dict | None = None) -> dict:
        self._sequence += 1
        response = self.dispatcher.dispatch(
            {
                "jsonrpc": "2.0",
                "id": f"request-{self._sequence}",
                "method": method,
                "params": params or {},
            }
        )
        assert response is not None
        assert "error" not in response, response
        return response["result"]

    def call_error(self, method: str, params: dict) -> dict:
        self._sequence += 1
        response = self.dispatcher.dispatch(
            {
                "jsonrpc": "2.0",
                "id": f"request-{self._sequence}",
                "method": method,
                "params": params,
            }
        )
        assert response is not None
        assert "error" in response, response
        return response["error"]


def _mutation(transaction_id: str, **params) -> dict:
    return {
        "transaction_id": transaction_id,
        "actor": "expert.one",
        **params,
    }


def test_system_model_is_browsable_and_editable_without_an_open_project(
    tmp_path: Path,
) -> None:
    methods = SidecarMethods(clock=lambda: NOW, system_root=tmp_path / "system")
    rpc = RpcHarness(methods)
    try:
        status = rpc.call("runtime.status")
        assert status["system_ready"] is True
        assert status["project_open"] is False
        assert status["project_id"] is None
        assert status["backend_source"]["runtime_restart_required"] is False
        assert status["backend_source"]["loaded_identity"]["baseline_available"] is False
        assert len(status["backend_source"]["loaded_identity"]["identity_sha256"]) == 64
        system_model = status["system_model"]
        initial_model_identity = system_model["model_identity_sha256"]
        assert system_model["model_library_id"] == status["model_library_id"]
        assert len(initial_model_identity) == 64
        assert system_model["format_version"] == "0.1.0"
        assert system_model["database_schema_version"] == 5
        assert system_model["node_count"] == 53
        assert system_model["scheme_count"] == 1
        assert system_model["edit_session_dirty"] is False
        assert system_model["recovery_diagnostics"] == []
        assert status["project_compatibility"] is None

        base = rpc.call("model.scheme.list")["schemes"][0]
        graph = rpc.call("model.graph.get", {"scheme_id": base["scheme_id"]})["graph"]
        assert graph["model_library_id"] == status["model_library_id"]
        assert len(graph["nodes"]) == 53

        copied = rpc.call(
            "model.scheme.copy",
            _mutation(
                "tx.no-project-copy",
                source_scheme_id=base["scheme_id"],
                new_scheme_id="task-scheme.no-project-copy",
                name_en="No-project editable copy",
            ),
        )["scheme"]
        assert copied["scheme_id"] == "task-scheme.no-project-copy"
        assert rpc.call("model.edit.status")["edit_session"]["dirty"] is True
        staged_status = rpc.call("runtime.status")
        assert staged_status["system_model"]["edit_session_dirty"] is True
        assert staged_status["system_model"]["scheme_count"] == 1

        rpc.call("model.edit.commit", _mutation("tx.no-project-save"))
        assert rpc.call("model.edit.status")["edit_session"]["dirty"] is False
        saved_status = rpc.call("runtime.status")
        assert saved_status["system_model"]["scheme_count"] == 2
        assert saved_status["system_model"]["model_identity_sha256"] != initial_model_identity

        rpc.call(
            "project.create",
            _mutation(
                "tx.no-project-diagnostics-project",
                root=str(tmp_path / "diagnostics-project"),
                name="Diagnostics project",
            ),
        )
        project_status = rpc.call("runtime.status")["project_compatibility"]
        assert project_status["format_version"] == "0.1.0"
        assert project_status["database_schema_version"] == 5
        assert project_status["compatibility"] == "compatible"
        assert project_status["recovery_diagnostics"] == []
        assert project_status["recovered_run_count"] == 0
        rpc.call("project.close")
        project_only = rpc.call_error("session.list", {})
        assert project_only["data"]["error_code"] == "PROJECT_NOT_OPEN"
    finally:
        methods.close()


def test_project_create_generates_stable_id_when_client_only_supplies_name_and_folder(
    tmp_path: Path,
) -> None:
    methods = SidecarMethods(clock=lambda: NOW, system_root=tmp_path / "system")
    rpc = RpcHarness(methods)
    request = _mutation(
        "tx.generated-project-id",
        root=str(tmp_path / "generated-id-project"),
        name="Generated ID project",
    )
    try:
        created = rpc.call("project.create", request)
        project_id = created["project"]["project_id"]
        assert project_id.startswith("project.")
        assert len(project_id) > len("project.")

        rpc.call("project.close")
        replayed = rpc.call("project.create", request)
        assert replayed["project"]["project_id"] == project_id
        assert replayed["replayed"] is True
    finally:
        methods.close()


def test_methods_expose_durable_expert_editing_with_idempotent_mutations(
    tmp_path: Path,
) -> None:
    methods = SidecarMethods(clock=lambda: NOW, system_root=tmp_path / "system")
    rpc = RpcHarness(methods)
    project_root = tmp_path / "managed-project"
    try:
        rejected_root = tmp_path / "must-not-be-created"
        rejected = rpc.call_error(
            "project.create",
            {
                "transaction_id": "tx.invalid-project",
                "root": str(rejected_root),
                "project_id": "project.invalid",
                "name": "Invalid project",
            },
        )
        assert rejected["code"] == -32602
        assert not rejected_root.exists()

        created = rpc.call(
            "project.create",
            _mutation(
                "tx.project-create",
                root=str(project_root),
                project_id="project.methods-test",
                name="Methods test project",
            ),
        )
        assert created["project"]["project_id"] == "project.methods-test"
        assert created["replayed"] is False
        replayed_create = rpc.call(
            "project.create",
            _mutation(
                "tx.project-create",
                root=str(project_root),
                project_id="project.methods-test",
                name="Methods test project",
            ),
        )
        assert replayed_create["replayed"] is True

        operators = rpc.call("operator.catalog.list")["operators"]
        assert operators
        schemes = rpc.call("scheme.version.list")["schemes"]
        assert len(schemes) == 1
        scheme_id = schemes[0]["scheme_version_id"]
        scheme = rpc.call(
            "scheme.version.get",
            {"scheme_version_id": scheme_id},
        )["scheme"]

        draft_id = "draft.methods-test"
        created_draft = rpc.call(
            "scheme.draft.create",
            _mutation(
                "tx.draft-create",
                draft_id=draft_id,
                scheme_version_id=scheme_id,
            ),
        )["draft_record"]["draft"]
        assert created_draft["graph_version"] == 0
        assert created_draft["layout_version"] == 0

        layout_reference = scheme["layout"]
        layout = rpc.call(
            "component.version.get",
            {
                "kind": layout_reference["kind"],
                "version_id": layout_reference["version_id"],
            },
        )["version"]
        node_id = layout["node_positions"][0]["node_id"]

        cloned = rpc.call(
            "graph.operations.apply",
            _mutation(
                "tx.clone-layout",
                draft_id=draft_id,
                operations=[
                    {
                        "type": "clone_component_version",
                        "expected_graph_version": 0,
                        "source": {
                            "kind": layout_reference["kind"],
                            "version_id": layout_reference["version_id"],
                        },
                        "candidate_id": "candidate.layout",
                        "replace_source": True,
                    }
                ],
            ),
        )["draft_record"]["draft"]
        assert cloned["graph_version"] == 1
        assert cloned["layout_version"] == 0

        layout_request = _mutation(
            "tx.layout-update",
            draft_id=draft_id,
            candidate_id="candidate.layout",
            expected_layout_version=0,
            positions=[{"node_id": node_id, "x": 42.0, "y": 24.0}],
        )
        moved = rpc.call("layout.update", layout_request)
        assert moved["draft_record"]["draft"]["layout_version"] == 1
        assert moved["replayed"] is False
        replayed_move = rpc.call("layout.update", layout_request)
        assert replayed_move["draft_record"] == moved["draft_record"]
        assert replayed_move["replayed"] is True

        mismatch = rpc.call_error(
            "layout.update",
            {
                **layout_request,
                "positions": [{"node_id": node_id, "x": 0.0, "y": 0.0}],
            },
        )
        assert mismatch["data"]["error_code"] == "TRANSACTION_REUSE_MISMATCH"

        validation = rpc.call("graph.validate", {"draft_id": draft_id})
        assert validation["graph_version"] == 1
        assert validation["layout_version"] == 1
        audits = rpc.call("audit.events.list", {"subject_id": draft_id})["events"]
        assert {event["event_type"] for event in audits} == {
            "scheme.draft.create",
            "graph.operations.apply",
            "layout.update",
        }

        closed = rpc.call("project.close")
        assert closed == {
            "closed": True,
            "project_id": "project.methods-test",
            "trace_id": closed["trace_id"],
        }
        reopened = rpc.call("project.open", {"root": str(project_root)})
        assert reopened["project"]["project_id"] == "project.methods-test"
        persisted = rpc.call("scheme.draft.get", {"draft_id": draft_id})
        assert persisted["draft_record"]["draft"]["layout_version"] == 1
    finally:
        methods.close()


def test_current_workspace_methods_return_canonical_state_and_idempotent_retries(
    tmp_path: Path,
) -> None:
    methods = SidecarMethods(clock=lambda: NOW, system_root=tmp_path / "system")
    rpc = RpcHarness(methods)
    try:
        rpc.call(
            "project.create",
            _mutation(
                "tx.current-project",
                root=str(tmp_path / "current-project"),
                project_id="project.current-methods",
                name="Current methods",
            ),
        )
        capabilities = rpc.call("capabilities.list")
        assert "model.current-workspace.v1" in capabilities["capabilities"]
        assert "model.graph.get" in capabilities["method_families"]["current_model"]
        assert "model.run.list" in capabilities["method_families"]["current_model"]
        assert "scheme.draft.publish" in capabilities["method_families"]["compatibility_model"]
        assert rpc.call("model.run.list")["runs"] == []

        base = rpc.call("model.scheme.list")["schemes"][0]
        graph = rpc.call("model.graph.get", {"scheme_id": base["scheme_id"]})["graph"]
        assert len(graph["nodes"]) == 53
        assert len(graph["scheme"]["computed_active_closure"]) == 52

        copy_request = _mutation(
            "tx.current-scheme-copy",
            source_scheme_id=base["scheme_id"],
            new_scheme_id="task-scheme.methods-copy",
            name_en="Methods copy",
        )
        copied = rpc.call("model.scheme.copy", copy_request)
        assert copied["scheme"]["copied_from_scheme_id"] == base["scheme_id"]
        replayed = rpc.call("model.scheme.copy", copy_request)
        assert replayed["scheme"] == copied["scheme"]
        assert replayed["replayed"] is True
        mismatch = rpc.call_error(
            "model.scheme.copy",
            {**copy_request, "name_en": "Different request"},
        )
        assert mismatch["data"]["error_code"] == "TRANSACTION_REUSE_MISMATCH"

        source = next(node for node in graph["nodes"] if node["node_kind"] == "evidence")
        copied_scheme = copied["scheme"]
        batch_request = _mutation(
            "tx.current-graph-copy",
            scheme_id=copied_scheme["scheme_id"],
            copy_node_ids=[source["node_id"]],
            activate_node_ids=[],
            layout_updates=[],
            expected_semantic_revision=copied_scheme["semantic_revision"],
            expected_layout_revision=copied_scheme["layout_revision"],
        )
        batch = rpc.call("model.graph.batch.apply", batch_request)
        new_node = batch["copied_nodes"][0]
        assert new_node["node_id"] in batch["scheme"]["computed_active_closure"]
        assert rpc.call("model.graph.batch.apply", batch_request)["copied_nodes"] == [new_node]

        update_request = _mutation(
            "tx.current-node-update",
            node={
                **new_node,
                "description_en": f"{new_node['description_en']} Edited through JSON-RPC.",
            },
            expected_semantic_revision=new_node["semantic_revision"],
        )
        updated = rpc.call("model.node.update", update_request)
        assert updated["node"]["semantic_revision"] == new_node["semantic_revision"] + 1
        assert rpc.call("model.node.update", update_request)["node"] == updated["node"]

        stale = rpc.call_error(
            "model.node.update",
            _mutation(
                "tx.current-node-stale",
                node={**updated["node"], "description_en": "Stale write"},
                expected_semantic_revision=new_node["semantic_revision"],
            ),
        )
        assert stale["data"]["error_code"] == "MODEL_REVISION_CONFLICT"
        assert stale["data"]["diagnostics"]["current_node"] == updated["node"]

        cpt = rpc.call("model.cpt.validate", {"node_id": new_node["node_id"]})
        assert cpt["validation"]["executable"] is True
        rows = updated["node"]["definition"]["cpt"]["materialized_probabilities"]
        cpt_update = rpc.call(
            "model.cpt.update",
            _mutation(
                "tx.current-cpt-update",
                node_id=new_node["node_id"],
                rows=rows,
                expected_semantic_revision=updated["node"]["semantic_revision"],
            ),
        )
        assert cpt_update["editor"]["materialized_probabilities"] == rows

        current_scheme = rpc.call(
            "model.scheme.get",
            {"scheme_id": copied_scheme["scheme_id"]},
        )["scheme"]
        impact = rpc.call(
            "model.scheme.deactivation.preview",
            {"scheme_id": current_scheme["scheme_id"], "node_id": new_node["node_id"]},
        )["impact"]
        stale_impact = rpc.call_error(
            "model.scheme.deactivate",
            _mutation(
                "tx.current-deactivate-stale",
                scheme_id=current_scheme["scheme_id"],
                node_id=new_node["node_id"],
                expected_semantic_revision=current_scheme["semantic_revision"],
                impact_hash="0" * 64,
            ),
        )
        assert stale_impact["data"]["error_code"] == "MODEL_DEACTIVATION_STALE"
        assert stale_impact["data"]["diagnostics"]["current_impact"] == impact
        deactivated = rpc.call(
            "model.scheme.deactivate",
            _mutation(
                "tx.current-deactivate",
                scheme_id=current_scheme["scheme_id"],
                node_id=new_node["node_id"],
                expected_semantic_revision=current_scheme["semantic_revision"],
                impact_hash=impact["impact_hash"],
            ),
        )
        assert new_node["node_id"] not in deactivated["scheme"]["computed_active_closure"]
        assert rpc.call("model.node.history.list", {"node_id": new_node["node_id"]})["events"]
    finally:
        methods.close()
