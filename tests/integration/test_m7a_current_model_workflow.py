from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

from pilot_assessment.sidecar import JsonRpcDispatcher, SidecarMethods

NOW = datetime(2026, 7, 17, 20, 0, tzinfo=UTC)


class _Rpc:
    def __init__(self, methods: SidecarMethods) -> None:
        self.dispatcher = JsonRpcDispatcher(
            runtime_id="runtime.m7a-integration",
            trace_id_factory=self._trace_id,
        )
        methods.register(self.dispatcher)
        self.sequence = 0
        self.call(
            "runtime.hello",
            {
                "protocol_version": "1.0",
                "supported_protocols": ["1.0"],
                "client": {"name": "m7a-integration", "version": "0.1.0"},
            },
        )

    def _trace_id(self) -> str:
        self.sequence += 1
        return f"trace.m7a.{self.sequence}"

    def call(self, method: str, params: dict | None = None) -> dict:
        self.sequence += 1
        response = self.dispatcher.dispatch(
            {
                "jsonrpc": "2.0",
                "id": f"request-{self.sequence}",
                "method": method,
                "params": params or {},
            }
        )
        assert response is not None
        assert "error" not in response, response
        return response["result"]


def _mutation(transaction_id: str, **params) -> dict:
    return {
        "transaction_id": transaction_id,
        "actor": "expert.integration",
        **params,
    }


def _wait_completed(rpc: _Rpc, run_id: str) -> dict:
    for _ in range(200):
        status = rpc.call("run.status", {"run_id": run_id})
        if status["run"]["state"] in {
            "completed",
            "failed",
            "cancelled",
            "interrupted",
        }:
            assert status["run"]["state"] == "completed", rpc.call(
                "run.events.list",
                {"run_id": run_id},
            )
            return status
        time.sleep(0.05)
    raise AssertionError(f"run {run_id!r} did not become terminal")


def _node_index(graph: dict) -> dict[str, dict]:
    return {node["node_id"]: node for node in graph["nodes"]}


def _mutable(value):
    return json.loads(json.dumps(value))


def test_m7a_current_model_sidecar_workflow_is_editable_portable_and_snapshot_safe(
    tmp_path: Path,
    m4_workflow_bundle: Path,
) -> None:
    methods = SidecarMethods(clock=lambda: NOW, system_root=tmp_path / "system")
    rpc = _Rpc(methods)
    project_root = tmp_path / "m7a-project"
    current_run_id = "run.m7a-current"
    legacy_run_id = "run.m7a-legacy"
    try:
        rpc.call(
            "project.create",
            _mutation(
                "tx.m7a-project",
                root=str(project_root),
                project_id="project.m7a-integration",
                name="M7A integration",
            ),
        )
        base = rpc.call("model.scheme.list")["schemes"][0]
        base_graph = rpc.call("model.graph.get", {"scheme_id": base["scheme_id"]})["graph"]
        assert len(base_graph["nodes"]) == 53
        assert len(base_graph["scheme"]["computed_active_closure"]) == 52

        copied_scheme = rpc.call(
            "model.scheme.copy",
            _mutation(
                "tx.m7a-scheme-copy",
                source_scheme_id=base["scheme_id"],
                new_scheme_id="task-scheme.m7a-focused",
                name_en="Focused expert-editable task",
            ),
        )["scheme"]
        source = next(
            node
            for node in base_graph["nodes"]
            if node["node_kind"] == "evidence"
            and len(node["definition"]["ordered_probabilistic_parent_nodes"]) == 1
            and node["definition"]["recipe"].get("scoring") is not None
        )
        copied_batch = rpc.call(
            "model.graph.batch.apply",
            _mutation(
                "tx.m7a-node-copy",
                scheme_id=copied_scheme["scheme_id"],
                copy_node_ids=[source["node_id"]],
                activate_node_ids=[],
                layout_updates=[],
                expected_semantic_revision=copied_scheme["semantic_revision"],
                expected_layout_revision=copied_scheme["layout_revision"],
            ),
        )
        copied_node = copied_batch["copied_nodes"][0]
        assert (
            copied_node["definition"]["ordered_probabilistic_parent_nodes"]
            == source["definition"]["ordered_probabilistic_parent_nodes"]
        )

        nodes = _node_index(copied_batch["graph"])
        subskill_id = copied_node["definition"]["ordered_probabilistic_parent_nodes"][0]["node_id"]
        aggregate_id = nodes[subskill_id]["definition"]["ordered_probabilistic_parent_nodes"][0][
            "node_id"
        ]
        focused_scheme = _mutable(copied_batch["scheme"])
        focused_scheme["explicit_active_node_ids"] = sorted([copied_node["node_id"], aggregate_id])
        focused_scheme["output_node_ids"] = [aggregate_id]
        focused_scheme = rpc.call(
            "model.scheme.update",
            _mutation(
                "tx.m7a-scheme-focus",
                scheme=focused_scheme,
                expected_semantic_revision=copied_batch["scheme"]["semantic_revision"],
            ),
        )["scheme"]
        focused_graph = rpc.call(
            "model.graph.get",
            {"scheme_id": focused_scheme["scheme_id"]},
        )["graph"]
        active = set(focused_graph["scheme"]["computed_active_closure"])
        active_nodes = [node for node in focused_graph["nodes"] if node["node_id"] in active]
        assert sum(node["node_kind"] == "evidence" for node in active_nodes) == 1
        assert sum(node["node_kind"] == "bn" for node in active_nodes) == 2

        raw_parent_id = copied_node["definition"]["data_bindings"][0]["raw_input_node"]["node_id"]
        impact = rpc.call(
            "model.scheme.deactivation.preview",
            {"scheme_id": focused_scheme["scheme_id"], "node_id": raw_parent_id},
        )["impact"]
        deactivated = rpc.call(
            "model.scheme.deactivate",
            _mutation(
                "tx.m7a-parent-deactivate",
                scheme_id=focused_scheme["scheme_id"],
                node_id=raw_parent_id,
                expected_semantic_revision=focused_scheme["semantic_revision"],
                impact_hash=impact["impact_hash"],
            ),
        )["scheme"]
        assert copied_node["node_id"] not in deactivated["computed_active_closure"]
        assert (
            raw_parent_id
            in rpc.call(
                "model.scheme.get",
                {"scheme_id": base["scheme_id"]},
            )["scheme"]["computed_active_closure"]
        )

        reactivated = rpc.call(
            "model.scheme.activate",
            _mutation(
                "tx.m7a-child-reactivate",
                scheme_id=focused_scheme["scheme_id"],
                node_id=copied_node["node_id"],
                expected_semantic_revision=deactivated["semantic_revision"],
            ),
        )["scheme"]
        assert copied_node["node_id"] in reactivated["computed_active_closure"]
        assert raw_parent_id in reactivated["computed_active_closure"]
        assert subskill_id in reactivated["computed_active_closure"]

        editable = _mutable(rpc.call("model.node.get", {"node_id": copied_node["node_id"]})["node"])
        recipe = editable["definition"]["recipe"]
        recipe["scoring"]["parameters"]["likelihood_strength"] = 0.8
        editable["name_en"] = f"Task-specific {editable['name_en']}"
        edited = rpc.call(
            "model.node.update",
            _mutation(
                "tx.m7a-evidence-parameter",
                node=editable,
                expected_semantic_revision=editable["semantic_revision"],
            ),
        )["node"]
        rows = _mutable(edited["definition"]["cpt"]["materialized_probabilities"])
        assert len(rows[0]) == 3
        rows[0] = [0.6, 0.3, 0.1]
        cpt_edited = rpc.call(
            "model.cpt.update",
            _mutation(
                "tx.m7a-cpt",
                node_id=edited["node_id"],
                rows=rows,
                expected_semantic_revision=edited["semantic_revision"],
            ),
        )["node"]
        committed = rpc.call(
            "model.edit.commit",
            _mutation("tx.m7a-model-edit-commit"),
        )
        assert committed["edit_session"]["dirty"] is False

        imported = rpc.call(
            "session.import",
            _mutation(
                "tx.m7a-session",
                external_bundle=str(m4_workflow_bundle),
            ),
        )
        session_revision_id = imported["revision"]["session_revision_id"]
        runnable_scheme = rpc.call(
            "model.scheme.get",
            {"scheme_id": focused_scheme["scheme_id"]},
        )["scheme"]
        prepared = rpc.call(
            "model.run.preflight",
            {
                "session_revision_id": session_revision_id,
                "scheme_id": runnable_scheme["scheme_id"],
                "purpose": "software_test",
                "runtime_parameters": {},
            },
        )["preflight"]
        assert prepared["technical_disposition"] == "ready"
        started = rpc.call(
            "model.run.start",
            _mutation(
                "tx.m7a-current-run",
                preflight_id=prepared["preflight_id"],
                run_id=current_run_id,
                expected_scheme_revision=prepared["scheme_semantic_revision"],
            ),
        )["run"]
        completed = _wait_completed(rpc, current_run_id)["run"]
        assert completed["snapshot"]["snapshot_hash"] == started["snapshot"]["snapshot_hash"]
        current_result = rpc.call("result.get", {"run_id": current_run_id})["result"]
        assert current_result["snapshot_hash"] == started["snapshot"]["snapshot_hash"]
        listed_current_runs = rpc.call("model.run.list")["runs"]
        listed_current = next(
            item for item in listed_current_runs if item["run"]["run_id"] == current_run_id
        )
        assert listed_current["run"]["contract_version"] == "0.2.0"
        assert listed_current["result_id"] == current_result["result_id"]
        assert all(item["run"]["run_id"] != legacy_run_id for item in listed_current_runs)
        for reference_name in ("observation_set_ref", "posterior_ref", "inference_trace_ref"):
            reference = current_result[reference_name]
            artifact = rpc.call(
                "result.artifact.get",
                {
                    "result_id": current_result["result_id"],
                    "artifact_id": reference["artifact_id"],
                },
            )["artifact"]
            assert artifact["artifact_id"] == reference["artifact_id"]

        shared = _mutable(rpc.call("model.node.get", {"node_id": aggregate_id})["node"])
        old_shared_hash = shared["content_hash"]
        shared["description_en"] = f"{shared['description_en']} Future-run edit."
        rpc.call(
            "model.node.update",
            _mutation(
                "tx.m7a-shared-edit",
                node=shared,
                expected_semantic_revision=shared["semantic_revision"],
            ),
        )
        rpc.call(
            "model.edit.commit",
            _mutation("tx.m7a-future-model-edit-commit"),
        )
        future = rpc.call(
            "model.run.preflight",
            {
                "session_revision_id": session_revision_id,
                "scheme_id": runnable_scheme["scheme_id"],
                "purpose": "software_test",
                "runtime_parameters": {},
            },
        )["preflight"]
        assert future["preflight_hash"] != prepared["preflight_hash"]
        old_run = rpc.call("run.status", {"run_id": current_run_id})["run"]
        old_frozen_shared = next(
            node for node in old_run["snapshot"]["active_nodes"] if node["node_id"] == aggregate_id
        )
        assert old_frozen_shared["content_hash"] == old_shared_hash
        assert rpc.call("result.get", {"run_id": current_run_id})["result"] == current_result

        legacy_scheme_id = rpc.call("scheme.version.list")["schemes"][0]["scheme_version_id"]
        legacy_preflight = rpc.call(
            "run.preflight",
            {
                "session_revision_id": session_revision_id,
                "scheme_version_id": legacy_scheme_id,
                "purpose": "software_test",
                "runtime_parameters": {},
            },
        )["preflight"]
        rpc.call(
            "run.start",
            _mutation(
                "tx.m7a-legacy-run",
                preflight_id=legacy_preflight["preflight_id"],
                run_id=legacy_run_id,
            ),
        )
        assert _wait_completed(rpc, legacy_run_id)["run"]["contract_version"] == "0.1.0"

        rpc.call("project.close")
        rpc.call("project.open", {"root": str(project_root)})
        reopened = rpc.call("model.node.get", {"node_id": copied_node["node_id"]})["node"]
        assert (
            reopened["definition"]["recipe"]["scoring"]["parameters"]["likelihood_strength"] == 0.8
        )
        assert reopened["definition"]["cpt"]["materialized_probabilities"][0] == [
            0.6,
            0.3,
            0.1,
        ]
        assert rpc.call("result.get", {"run_id": current_run_id})["result"] == current_result
        legacy_replay = rpc.call("run.status", {"run_id": legacy_run_id})["run"]
        assert legacy_replay["snapshot"]["contract_id"] == "run-snapshot"
        assert legacy_replay["contract_version"] == "0.1.0"
        assert cpt_edited["node_id"] == reopened["node_id"]
    finally:
        methods.close()
