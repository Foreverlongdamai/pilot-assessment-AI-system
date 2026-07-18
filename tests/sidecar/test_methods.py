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


def test_methods_expose_durable_expert_editing_with_idempotent_mutations(
    tmp_path: Path,
) -> None:
    methods = SidecarMethods(clock=lambda: NOW)
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
    methods = SidecarMethods(clock=lambda: NOW)
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
