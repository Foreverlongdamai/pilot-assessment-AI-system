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
