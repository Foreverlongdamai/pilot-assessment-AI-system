from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pilot_assessment.ingestion.profiles import CsvProfile, load_builtin_profiles
from pilot_assessment.sidecar import JsonRpcDispatcher, SidecarMethods

NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def _raw_source(tmp_path: Path) -> Path:
    root = tmp_path / "raw-session"
    (root / "streams").mkdir(parents=True)
    (root / "annotations").mkdir()
    profile = load_builtin_profiles()["cranfield-simulator-combined-csv-raw-v0.1"]
    assert isinstance(profile, CsvProfile)
    headers = [column.source_header for column in profile.columns]
    rows = []
    for index in range(6):
        values = ["0" for _ in headers]
        values[headers.index("Simulation time")] = f"{index / 100:.2f}"
        values[headers.index("Control_Mode")] = "1"
        values[headers.index("Time Delay s")] = "0.2"
        values[headers.index("Lon Frequency rad/s")] = "8"
        values[headers.index("Long Damping")] = "0.8"
        rows.append(",".join(values))
    (root / "streams" / "simulator.csv").write_text(
        ",".join(headers) + "\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
        newline="",
    )
    return root


def _call(
    dispatcher: JsonRpcDispatcher,
    method: str,
    params: dict[str, object],
    sequence: int,
) -> dict:
    response = dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": f"request-{sequence}",
            "method": method,
            "params": params,
        }
    )
    assert response is not None
    assert "error" not in response, response
    return response["result"]


def test_sidecar_inspects_and_imports_raw_session_source(tmp_path: Path) -> None:
    methods = SidecarMethods(clock=lambda: NOW, system_root=tmp_path / "system")
    dispatcher = JsonRpcDispatcher(
        runtime_id="runtime.session-source-test",
        trace_id_factory=lambda: "trace.session-source-test",
    )
    methods.register(dispatcher)
    raw = _raw_source(tmp_path)
    try:
        _call(
            dispatcher,
            "runtime.hello",
            {
                "protocol_version": "1.0",
                "supported_protocols": ["1.0"],
                "client": {"name": "pytest", "version": "0.1.0"},
            },
            1,
        )
        _call(
            dispatcher,
            "project.create",
            {
                "root": str(tmp_path / "project"),
                "project_id": "project.raw-rpc",
                "name": "Raw RPC project",
                "transaction_id": "tx.project.raw-rpc",
                "actor": "expert.one",
            },
            2,
        )
        inspected = _call(
            dispatcher,
            "session.source.inspect",
            {"external_source": str(raw)},
            3,
        )

        assert inspected["source_kind"] == "simulator_raw"
        assert inspected["report"] is None
        assert inspected["raw"]["required_user_inputs"] == []
        assert inspected["raw"]["can_materialize"] is True
        yaw = next(
            item
            for item in inspected["raw"]["field_mappings"]
            if item["canonical_field"] == "control.yaw_raw"
        )
        assert yaw["declared_unit"] is None

        imported = _call(
            dispatcher,
            "session.source.import",
            {
                "external_source": str(raw),
                "inspected_fingerprint": inspected["raw"]["source_snapshot_fingerprint"],
                "transaction_id": "tx.session.raw-rpc",
                "actor": "expert.one",
            },
            4,
        )
        assert imported["replayed"] is False
        listed = _call(dispatcher, "session.list", {}, 5)
        assert listed["sessions"][0]["session"]["session_id"] == (imported["session"]["session_id"])
    finally:
        methods.close()
