from __future__ import annotations

import json
import time
from io import BytesIO
from threading import Thread

import pytest

from pilot_assessment.sidecar.errors import JsonRpcFault
from pilot_assessment.sidecar.framing import JsonLineWriter, decode_json_line, read_json_line


class _FragmentingStream:
    def __init__(self) -> None:
        self.payload = bytearray()

    def write(self, data: bytes) -> int:
        for value in data:
            self.payload.append(value)
            time.sleep(0)
        return len(data)

    def flush(self) -> None:
        return None


def test_jsonl_round_trips_utf8_and_rejects_invalid_non_object_and_oversized() -> None:
    stream = BytesIO()
    writer = JsonLineWriter(stream)
    message = {
        "jsonrpc": "2.0",
        "id": "请求-1",
        "result": {"message": "飞行员评估"},
    }

    writer.write(message)

    assert stream.getvalue().endswith(b"\n")
    assert stream.getvalue().count(b"\n") == 1
    assert decode_json_line(stream.getvalue()) == message
    assert read_json_line(BytesIO(stream.getvalue())) == message
    assert read_json_line(BytesIO(b"")) is None

    with pytest.raises(JsonRpcFault) as malformed:
        decode_json_line(b'{"jsonrpc":\n')
    assert malformed.value.rpc_code == -32700
    assert malformed.value.error_code == "PARSE_ERROR"

    with pytest.raises(JsonRpcFault) as invalid_utf8:
        decode_json_line(b"\xff\n")
    assert invalid_utf8.value.rpc_code == -32700

    with pytest.raises(JsonRpcFault) as non_object:
        decode_json_line(b"[]\n")
    assert non_object.value.rpc_code == -32600
    assert non_object.value.error_code == "INVALID_REQUEST"

    with pytest.raises(JsonRpcFault) as oversized:
        decode_json_line(b'{"value":"0123456789"}\n', max_message_bytes=10)
    assert oversized.value.rpc_code == -32600
    assert oversized.value.error_code == "MESSAGE_TOO_LARGE"

    with pytest.raises(JsonRpcFault, match="4 bytes"):
        JsonLineWriter(BytesIO(), max_message_bytes=4).write({"x": "too large"})

    following = b'{"jsonrpc":"2.0","method":"next"}\n'
    oversized_stream = BytesIO(b"x" * 100 + b"\n" + following)
    with pytest.raises(JsonRpcFault) as streamed_oversized:
        read_json_line(oversized_stream, max_message_bytes=16)
    assert streamed_oversized.value.error_code == "MESSAGE_TOO_LARGE"
    assert read_json_line(oversized_stream) == {"jsonrpc": "2.0", "method": "next"}


def test_stdout_writer_serializes_concurrent_messages_without_byte_interleaving() -> None:
    stream = _FragmentingStream()
    writer = JsonLineWriter(stream)

    def emit(prefix: str) -> None:
        for index in range(20):
            writer.write(
                {
                    "jsonrpc": "2.0",
                    "method": "run.progress",
                    "params": {"key": f"{prefix}-{index}"},
                }
            )

    threads = [Thread(target=emit, args=(prefix,)) for prefix in ("response", "notification")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    lines = bytes(stream.payload).splitlines()
    decoded = [json.loads(line.decode("utf-8")) for line in lines]
    assert len(decoded) == 40
    assert {item["params"]["key"] for item in decoded} == {
        f"{prefix}-{index}" for prefix in ("response", "notification") for index in range(20)
    }
