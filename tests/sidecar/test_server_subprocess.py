from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path


class SidecarProcess:
    def __init__(self) -> None:
        self.process = subprocess.Popen(
            [sys.executable, "-m", "pilot_assessment.sidecar"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        self._messages: queue.Queue[str | None] = queue.Queue()
        self._request_sequence = 0
        self.raw_stdout: list[str] = []
        self.notifications: list[dict] = []
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader.start()

    def _read_stdout(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self._messages.put(line)
        self._messages.put(None)

    def call(self, method: str, params: dict | None = None, *, timeout: float = 30.0) -> dict:
        self._request_sequence += 1
        request_id = f"request-{self._request_sequence}"
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError(f"timed out waiting for {method}")
            try:
                raw = self._messages.get(timeout=remaining)
            except queue.Empty as error:
                raise AssertionError(f"timed out waiting for {method}") from error
            if raw is None:
                stderr = self._stderr_after_exit()
                raise AssertionError(f"sidecar exited while waiting for {method}: {stderr}")
            self.raw_stdout.append(raw)
            message = json.loads(raw)
            assert isinstance(message, dict)
            assert message.get("jsonrpc") == "2.0"
            if "id" not in message:
                self.notifications.append(message)
                continue
            if message["id"] != request_id:
                raise AssertionError(f"unexpected response ID: {message}")
            assert "error" not in message, message
            return message["result"]

    def _stderr_after_exit(self) -> str:
        if self.process.poll() is None or self.process.stderr is None:
            return ""
        return self.process.stderr.read()

    def shutdown(self) -> str:
        if self.process.poll() is None:
            result = self.call("runtime.shutdown")
            assert result["state"] == "stopping"
        if self.process.stdin is not None:
            self.process.stdin.close()
        self.process.wait(timeout=15)
        self._reader.join(timeout=5)
        assert self.process.stderr is not None
        return self.process.stderr.read()

    def terminate(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)


def _mutation(transaction_id: str, **params) -> dict:
    return {
        "transaction_id": transaction_id,
        "actor": "expert.subprocess",
        **params,
    }


def test_stdio_sidecar_supports_the_managed_edit_and_assessment_loop(
    tmp_path: Path,
    m4_workflow_bundle: Path,
) -> None:
    sidecar = SidecarProcess()
    project_root = tmp_path / "stdio-project"
    try:
        hello = sidecar.call(
            "runtime.hello",
            {
                "protocol_version": "1.0",
                "supported_protocols": ["1.0"],
                "client": {"name": "subprocess-smoke", "version": "0.1.0"},
            },
        )
        assert hello["protocol_version"] == "1.0"

        created = sidecar.call(
            "project.create",
            _mutation(
                "tx.subprocess-project",
                root=str(project_root),
                project_id="project.subprocess",
                name="Subprocess project",
            ),
        )
        assert created["project"]["project_id"] == "project.subprocess"
        assert sidecar.call("project.get")["project"] == created["project"]
        assert sidecar.call("project.close")["closed"] is True
        recovery = sidecar.call("project.open", {"root": str(project_root)})["recovery"]
        assert recovery["interrupted_runs"] == []
        assert all(value == 0 for value in recovery["artifacts"].values())
        assert all(value == 0 for value in recovery["sessions"].values())

        operators = sidecar.call("operator.catalog.list")["operators"]
        assert operators
        listed_components = sidecar.call(
            "component.version.list",
            {"kind": "evidence_version"},
        )["versions"]
        assert listed_components
        exact_component = sidecar.call(
            "component.version.get",
            {
                "kind": "evidence_version",
                "version_id": listed_components[0]["version_id"],
            },
        )["version"]
        assert exact_component["content_hash"] == listed_components[0]["content_hash"]

        schemes = sidecar.call("scheme.version.list")["schemes"]
        assert len(schemes) == 1
        scheme_id = schemes[0]["scheme_version_id"]
        scheme = sidecar.call(
            "scheme.version.get",
            {"scheme_version_id": scheme_id},
        )["scheme"]
        draft_id = "draft.subprocess"
        sidecar.call(
            "scheme.draft.create",
            _mutation(
                "tx.subprocess-draft",
                draft_id=draft_id,
                scheme_version_id=scheme_id,
            ),
        )
        layout_reference = scheme["layout"]
        layout = sidecar.call(
            "component.version.get",
            {
                "kind": layout_reference["kind"],
                "version_id": layout_reference["version_id"],
            },
        )["version"]
        sidecar.call(
            "graph.operations.apply",
            _mutation(
                "tx.subprocess-clone-layout",
                draft_id=draft_id,
                operations=[
                    {
                        "type": "clone_component_version",
                        "expected_graph_version": 0,
                        "source": {
                            "kind": layout_reference["kind"],
                            "version_id": layout_reference["version_id"],
                        },
                        "candidate_id": "candidate.subprocess-layout",
                    }
                ],
            ),
        )
        edited = sidecar.call(
            "layout.update",
            _mutation(
                "tx.subprocess-layout",
                draft_id=draft_id,
                candidate_id="candidate.subprocess-layout",
                expected_layout_version=0,
                positions=[
                    {
                        "node_id": layout["node_positions"][0]["node_id"],
                        "x": 12.0,
                        "y": 34.0,
                    }
                ],
            ),
        )
        assert edited["draft_record"]["draft"]["layout_version"] == 1

        imported = sidecar.call(
            "session.import",
            _mutation(
                "tx.subprocess-session",
                external_bundle=str(m4_workflow_bundle),
            ),
            timeout=60,
        )
        preflight = sidecar.call(
            "run.preflight",
            {
                "session_revision_id": imported["revision"]["session_revision_id"],
                "scheme_version_id": scheme_id,
                "purpose": "software_test",
                "runtime_parameters": {},
            },
            timeout=60,
        )["preflight"]
        assert preflight["technical_disposition"] == "ready"
        run_id = "run.subprocess"
        sidecar.call(
            "run.start",
            _mutation(
                "tx.subprocess-run",
                preflight_id=preflight["preflight_id"],
                run_id=run_id,
            ),
        )

        terminal = None
        for _ in range(100):
            status = sidecar.call("run.status", {"run_id": run_id})
            if status["run"]["state"] in {
                "completed",
                "failed",
                "cancelled",
                "interrupted",
            }:
                terminal = status
                break
            time.sleep(0.05)
        assert terminal is not None
        assert terminal["run"]["state"] == "completed", sidecar.call(
            "run.events.list", {"run_id": run_id}
        )
        events = sidecar.call("run.events.list", {"run_id": run_id})["events"]
        assert events[-1]["state"] == "completed"

        result = sidecar.call("result.get", {"run_id": run_id})["result"]
        assert result["run_id"] == run_id
        artifact_reference = result["observation_set_ref"]
        artifact = sidecar.call(
            "result.artifact.get",
            {
                "result_id": result["result_id"],
                "artifact_id": artifact_reference["artifact_id"],
            },
        )["artifact"]
        assert artifact["artifact_id"] == artifact_reference["artifact_id"]
        assert "payload" not in artifact
        assert "bytes" not in artifact

        cancel_terminal = sidecar.call(
            "run.cancel",
            _mutation("tx.subprocess-cancel-terminal", run_id=run_id),
        )
        assert cancel_terminal["run"]["state"] == "completed"
        assert sidecar.call("project.close")["closed"] is True
        stderr = sidecar.shutdown()
        assert all(isinstance(json.loads(line), dict) for line in sidecar.raw_stdout)
        assert "Traceback" not in stderr
    finally:
        sidecar.terminate()
