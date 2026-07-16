from __future__ import annotations

from pilot_assessment.sidecar.dispatcher import JsonRpcDispatcher, RpcRequestContext
from pilot_assessment.sidecar.errors import DomainRpcError, InvalidParamsFault

TRACE_IDS = iter(f"trace.test.{index}" for index in range(100))


def _dispatcher(*, calls: list[tuple[dict, RpcRequestContext]] | None = None):
    recorded = calls if calls is not None else []

    def echo(params, context):
        recorded.append((params, context))
        return {"echo": params.get("value")}

    dispatcher = JsonRpcDispatcher(
        runtime_id="runtime.test",
        backend_version="0.1.0",
        trace_id_factory=lambda: next(TRACE_IDS),
    )
    dispatcher.register("test.echo", echo)
    return dispatcher


def _request(method: str, *, request_id="request-1", params=None):
    message = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    return message


def _hello(dispatcher: JsonRpcDispatcher):
    response = dispatcher.dispatch(
        _request(
            "runtime.hello",
            params={
                "protocol_version": "1.0",
                "supported_protocols": ["1.0"],
                "client": {"name": "test-client", "version": "0.1.0"},
            },
        )
    )
    assert response is not None
    assert "result" in response
    return response


def test_dispatcher_requires_hello_and_negotiates_a_common_protocol() -> None:
    calls: list[tuple[dict, RpcRequestContext]] = []
    dispatcher = _dispatcher(calls=calls)

    gated = dispatcher.dispatch(_request("test.echo", params={"value": "blocked"}))
    assert gated is not None
    assert -32099 <= gated["error"]["code"] <= -32000
    assert gated["error"]["data"] == {
        "error_code": "PROTOCOL_HANDSHAKE_REQUIRED",
        "message": "runtime.hello must succeed before business methods",
        "recoverable": True,
        "trace_id": gated["error"]["data"]["trace_id"],
    }
    assert calls == []

    unsupported = dispatcher.dispatch(
        _request(
            "runtime.hello",
            params={
                "protocol_version": "2.0",
                "supported_protocols": ["2.0"],
            },
        )
    )
    assert unsupported is not None
    assert unsupported["error"]["data"]["error_code"] == "PROTOCOL_VERSION_UNSUPPORTED"
    assert unsupported["error"]["data"]["recoverable"] is False

    hello = _hello(dispatcher)
    assert hello["result"]["protocol_version"] == "1.0"
    assert hello["result"]["runtime_id"] == "runtime.test"
    assert hello["result"]["state"] == "ready"
    assert "runtime.protocol.v1" in hello["result"]["capabilities"]

    response = dispatcher.dispatch(
        _request(
            "test.echo",
            request_id=7,
            params={"value": "飞行员", "transaction_id": "tx.echo"},
        )
    )
    assert response is not None
    assert response["id"] == 7
    assert response["result"]["echo"] == "飞行员"
    assert response["result"]["trace_id"].startswith("trace.test.")
    assert calls[0][1].transaction_id == "tx.echo"
    assert calls[0][1].protocol_version == "1.0"


def test_dispatcher_preserves_standard_errors_and_structured_domain_data() -> None:
    dispatcher = _dispatcher()
    _hello(dispatcher)

    invalid_request = dispatcher.dispatch([])
    assert invalid_request == {
        "jsonrpc": "2.0",
        "id": None,
        "error": {
            "code": -32600,
            "message": "Invalid Request",
            "data": {
                "error_code": "INVALID_REQUEST",
                "trace_id": invalid_request["error"]["data"]["trace_id"],
            },
        },
    }
    assert dispatcher.dispatch(_request("missing.method"))["error"]["code"] == -32601
    assert dispatcher.dispatch(_request("test.echo", params=[]))["error"]["code"] == -32602

    def invalid_params(_params, _context):
        raise InvalidParamsFault("field 'value' must be a string", path="/value")

    def conflict(_params, _context):
        raise DomainRpcError(
            "GRAPH_VERSION_CONFLICT",
            "Graph revision changed",
            recoverable=True,
            transaction_id="tx.graph",
            path="/expected_graph_version",
            current_revision=12,
            diagnostics={"expected": 11, "actual": 12},
        )

    def crashes(_params, _context):
        raise RuntimeError("private backend detail")

    dispatcher.register("test.invalid", invalid_params)
    dispatcher.register("test.conflict", conflict)
    dispatcher.register("test.crash", crashes)

    invalid = dispatcher.dispatch(_request("test.invalid"))
    assert invalid["error"]["code"] == -32602
    assert invalid["error"]["data"]["path"] == "/value"

    domain = dispatcher.dispatch(_request("test.conflict"))
    assert -32099 <= domain["error"]["code"] <= -32000
    assert domain["error"]["data"] == {
        "error_code": "GRAPH_VERSION_CONFLICT",
        "message": "Graph revision changed",
        "recoverable": True,
        "trace_id": domain["error"]["data"]["trace_id"],
        "transaction_id": "tx.graph",
        "path": "/expected_graph_version",
        "current_revision": 12,
        "diagnostics": {"expected": 11, "actual": 12},
    }

    internal = dispatcher.dispatch(_request("test.crash"))
    assert internal["error"]["code"] == -32603
    assert internal["error"]["data"]["error_code"] == "INTERNAL_ERROR"
    assert "private backend detail" not in internal["error"]["message"]


def test_notifications_are_distinct_from_null_id_requests_and_never_emit_responses() -> None:
    calls: list[tuple[dict, RpcRequestContext]] = []
    dispatcher = _dispatcher(calls=calls)

    assert (
        dispatcher.dispatch(
            {"jsonrpc": "2.0", "method": "test.echo", "params": {"value": "before hello"}}
        )
        is None
    )
    assert calls == []
    assert dispatcher.negotiated_protocol_version is None

    _hello(dispatcher)
    notification = {
        "jsonrpc": "2.0",
        "method": "test.echo",
        "params": {"value": "notification"},
    }
    assert dispatcher.dispatch(notification) is None
    assert calls[-1][0]["value"] == "notification"
    assert dispatcher.dispatch({"jsonrpc": "2.0", "method": "missing.method"}) is None

    null_id_response = dispatcher.dispatch(
        _request("test.echo", request_id=None, params={"value": "request"})
    )
    assert null_id_response is not None
    assert null_id_response["id"] is None
    assert null_id_response["result"]["echo"] == "request"
