from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pilot_assessment.persistence.system import SystemStoreLockedError
from pilot_assessment.sidecar import JsonRpcDispatcher, SidecarMethods

NOW = datetime(2026, 7, 21, 15, 0, tzinfo=UTC)


class _Rpc:
    def __init__(self, methods: SidecarMethods) -> None:
        self.dispatcher = JsonRpcDispatcher(
            runtime_id="runtime.m8b-integration",
            trace_id_factory=self._trace_id,
        )
        methods.register(self.dispatcher)
        self.sequence = 0
        self.call(
            "runtime.hello",
            {
                "protocol_version": "1.0",
                "supported_protocols": ["1.0"],
                "client": {"name": "m8b-integration", "version": "0.1.0"},
            },
        )

    def _trace_id(self) -> str:
        self.sequence += 1
        return f"trace.m8b.{self.sequence}"

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


def _mutable(value):
    return json.loads(json.dumps(value))


def _wait_completed(rpc: _Rpc, run_id: str) -> dict:
    for _ in range(200):
        status = rpc.call("run.status", {"run_id": run_id})
        if status["run"]["state"] in {"completed", "failed", "cancelled", "interrupted"}:
            assert status["run"]["state"] == "completed", rpc.call(
                "run.events.list", {"run_id": run_id}
            )
            return status
        time.sleep(0.05)
    raise AssertionError(f"run {run_id!r} did not become terminal")


def test_one_system_model_serves_two_projects_without_rewriting_old_runs(
    tmp_path: Path,
    m4_workflow_bundle: Path,
) -> None:
    system_root = tmp_path / "system"
    project_a = tmp_path / "project-a"
    moved_project_a = tmp_path / "project-a-moved"
    project_b = tmp_path / "project-b"
    methods = SidecarMethods(clock=lambda: NOW, system_root=system_root)
    rpc = _Rpc(methods)
    run_id = "run.m8b.project-a"
    try:
        with pytest.raises(SystemStoreLockedError):
            SidecarMethods(clock=lambda: NOW, system_root=system_root)

        rpc.call(
            "project.create",
            _mutation("tx.m8b.project-a", root=str(project_a), name="Project A"),
        )
        imported = rpc.call(
            "session.import",
            _mutation(
                "tx.m8b.project-a-session",
                external_bundle=str(m4_workflow_bundle),
            ),
        )
        scheme = rpc.call("model.scheme.list")["schemes"][0]
        prepared = rpc.call(
            "model.run.preflight",
            {
                "session_revision_id": imported["revision"]["session_revision_id"],
                "scheme_id": scheme["scheme_id"],
                "purpose": "software_test",
                "runtime_parameters": {},
            },
        )["preflight"]
        started = rpc.call(
            "model.run.start",
            _mutation(
                "tx.m8b.project-a-run",
                preflight_id=prepared["preflight_id"],
                run_id=run_id,
                expected_scheme_revision=prepared["scheme_semantic_revision"],
            ),
        )["run"]
        completed = _wait_completed(rpc, run_id)["run"]
        old_snapshot = completed["snapshot"]
        old_result = rpc.call("result.get", {"run_id": run_id})["result"]
        assert old_snapshot["snapshot_hash"] == started["snapshot"]["snapshot_hash"]
        assert methods.application is not None
        assert (
            methods.application.project.database.fetchone("SELECT COUNT(*) FROM model_nodes")[0]
            == 0
        )
        assert (
            methods.application.project.database.fetchone("SELECT COUNT(*) FROM task_schemes")[0]
            == 0
        )

        rpc.call("project.close")
        rpc.call(
            "project.create",
            _mutation("tx.m8b.project-b", root=str(project_b), name="Project B"),
        )
        graph = rpc.call("model.graph.get", {"scheme_id": scheme["scheme_id"]})["graph"]
        target = _mutable(next(node for node in graph["nodes"] if node["node_kind"] == "bn"))
        target_id = target["node_id"]
        old_content_hash = target["content_hash"]
        target["description"] = f"{target['description']} Shared system edit."
        edited = rpc.call(
            "model.node.update",
            _mutation(
                "tx.m8b.shared-model-edit",
                node=target,
                expected_semantic_revision=target["semantic_revision"],
            ),
        )["node"]
        assert edited["content_hash"] != old_content_hash
        rpc.call("model.edit.commit", _mutation("tx.m8b.shared-model-save"))
        assert methods.application is not None
        assert (
            methods.application.project.database.fetchone("SELECT COUNT(*) FROM model_nodes")[0]
            == 0
        )
        assert methods.application.sessions.list_sessions() == ()
        rpc.call("project.close")

        project_a.rename(moved_project_a)
        rpc.call("project.open", {"root": str(moved_project_a)})
        assert rpc.call("model.node.get", {"node_id": target_id})["node"] == edited
        assert rpc.call("run.status", {"run_id": run_id})["run"]["snapshot"] == old_snapshot
        assert rpc.call("result.get", {"run_id": run_id})["result"] == old_result
        frozen = next(node for node in old_snapshot["active_nodes"] if node["node_id"] == target_id)
        assert frozen["content_hash"] == old_content_hash
    finally:
        methods.close()
