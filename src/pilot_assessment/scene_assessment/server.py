"""Scene-only JSON-RPC endpoint; no project or legacy model is opened."""

from __future__ import annotations

import json
from typing import BinaryIO

from pilot_assessment.scene_assessment.calculator import evaluate, validate_configuration
from pilot_assessment.scene_assessment.catalog import (
    DEFAULT_SCENE_ID,
    UnsupportedSceneError,
    list_scenes,
    load_catalog,
)
from pilot_assessment.sidecar.dispatcher import JsonRpcDispatcher
from pilot_assessment.sidecar.errors import InvalidParamsFault, JsonRpcFault
from pilot_assessment.sidecar.framing import JsonLineWriter, read_json_line

CAPABILITIES = (
    "runtime.protocol.v1",
    "scene.assessment.v1",
    "scene.assessment.v2",
    "scene.assessment.v3",
)
SCENE_MAX_MESSAGE_BYTES = 64 * 1024 * 1024
METHODS = (
    "runtime.hello",
    "runtime.status",
    "runtime.shutdown",
    "capabilities.list",
    "scene.list",
    "scene.catalog",
    "scene.validate_configuration",
    "scene.evaluate",
)


class SceneDispatcher(JsonRpcDispatcher):
    def _hello(self, params, *, trace_id):
        result = super()._hello(params, trace_id=trace_id)
        result["max_message_bytes"] = SCENE_MAX_MESSAGE_BYTES
        return result


def serve(input_stream: BinaryIO, output_stream: BinaryIO) -> int:
    dispatcher = SceneDispatcher(capabilities=CAPABILITIES)
    writer = JsonLineWriter(output_stream, max_message_bytes=SCENE_MAX_MESSAGE_BYTES)
    shutdown_requested = False

    def shutdown(_params, _context):
        nonlocal shutdown_requested
        shutdown_requested = True
        return {"state": "stopping"}

    def guarded(handler, expected_keys, optional_keys=()):
        def call(params, context):
            required = set(expected_keys)
            if not required <= set(params) <= required | set(optional_keys):
                raise InvalidParamsFault("请求参数缺失或包含未知字段。")
            try:
                json.dumps(params, allow_nan=False)
            except (TypeError, ValueError):
                raise InvalidParamsFault("输入必须是标准 JSON，数值必须有限。") from None
            try:
                return handler(params, context)
            except UnsupportedSceneError as error:
                path = getattr(error, "path", "/scene_id")
                if "configuration" in params:
                    path = "/configuration" + path
                raise InvalidParamsFault(str(error), path=path) from None

        return call

    handlers = {
        "runtime.status": (lambda _p, _c: {"state": "ready"}, ()),
        "runtime.shutdown": (shutdown, ()),
        "capabilities.list": (
            lambda _p, _c: {"capabilities": list(CAPABILITIES), "methods": list(METHODS)},
            (),
        ),
        "scene.list": (lambda _p, _c: list_scenes(), ()),
        "scene.catalog": (
            lambda p, _c: load_catalog(
                p.get("scene_id", DEFAULT_SCENE_ID), p.get("schema_version", "3.0")
            ),
            (),
        ),
        "scene.validate_configuration": (
            lambda p, _c: validate_configuration(p["configuration"]),
            ("configuration",),
        ),
        "scene.evaluate": (
            lambda p, _c: evaluate(p["configuration"], p["input"]),
            ("configuration", "input"),
        ),
    }
    for name, (handler, expected_keys) in handlers.items():
        optional_keys = ("scene_id", "schema_version") if name == "scene.catalog" else ()
        dispatcher.register(name, guarded(handler, expected_keys, optional_keys))
    while not shutdown_requested:
        try:
            request = read_json_line(input_stream, max_message_bytes=SCENE_MAX_MESSAGE_BYTES)
        except JsonRpcFault as fault:
            writer.write(dispatcher.fault_response(fault))
            continue
        if request is None:
            break
        response = dispatcher.dispatch(request)
        if response is not None:
            writer.write(response)
    return 0
