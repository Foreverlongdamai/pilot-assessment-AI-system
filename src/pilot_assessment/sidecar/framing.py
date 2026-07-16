"""Bounded UTF-8 JSONL framing with one serialized output writer."""

from __future__ import annotations

import json
from collections.abc import Mapping
from threading import Lock
from typing import BinaryIO, cast

from pydantic import JsonValue

from pilot_assessment.sidecar.errors import (
    InvalidRequestFault,
    JsonRpcMessage,
    MessageTooLargeFault,
    ParseErrorFault,
)

DEFAULT_MAX_MESSAGE_BYTES = 4 * 1024 * 1024


def _require_limit(value: int) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError("max_message_bytes must be a positive strict integer")
    return value


def _payload_without_line_ending(raw: bytes) -> bytes:
    payload = raw[:-1] if raw.endswith(b"\n") else raw
    if payload.endswith(b"\r"):
        payload = payload[:-1]
    return payload


def _reject_constant(_value: str) -> None:
    raise ValueError("non-finite JSON number is forbidden")


def _unique_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON member {key!r}")
        result[key] = value
    return result


def decode_json_line(
    raw: bytes,
    *,
    max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES,
) -> JsonRpcMessage:
    """Decode one physical line and reject non-object or non-standard JSON."""

    limit = _require_limit(max_message_bytes)
    if type(raw) is not bytes:
        raise TypeError("JSONL input must be exact bytes")
    payload = _payload_without_line_ending(raw)
    if len(payload) > limit:
        raise MessageTooLargeFault(limit)
    try:
        text = payload.decode("utf-8", errors="strict")
        decoded = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise ParseErrorFault() from None
    if not isinstance(decoded, dict):
        raise InvalidRequestFault("top-level JSON-RPC message must be an object")
    return cast(JsonRpcMessage, decoded)


def read_json_line(
    stream: BinaryIO,
    *,
    max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES,
) -> JsonRpcMessage | None:
    """Read one bounded line; EOF before bytes is the only normal empty result."""

    limit = _require_limit(max_message_bytes)
    raw = stream.readline(limit + 3)
    if raw == b"":
        return None
    if len(_payload_without_line_ending(raw)) > limit and not raw.endswith(b"\n"):
        # Discard the remainder without retaining it so the next read starts at a frame boundary.
        while True:
            remainder = stream.readline(64 * 1024)
            if remainder == b"" or remainder.endswith(b"\n"):
                break
    return decode_json_line(raw, max_message_bytes=limit)


class JsonLineWriter:
    """Serialize every response/notification through one byte-level lock."""

    def __init__(
        self,
        stream: BinaryIO,
        *,
        max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES,
    ) -> None:
        self.stream = stream
        self.max_message_bytes = _require_limit(max_message_bytes)
        self._lock = Lock()

    def write(self, message: Mapping[str, JsonValue]) -> None:
        if not isinstance(message, Mapping):
            raise InvalidRequestFault("outbound JSON-RPC message must be an object")
        try:
            payload = json.dumps(
                dict(message),
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise InvalidRequestFault("outbound message is outside the JSON domain") from error
        if len(payload) > self.max_message_bytes:
            raise MessageTooLargeFault(self.max_message_bytes)
        framed = payload + b"\n"
        with self._lock:
            written = self.stream.write(framed)
            if written is not None and written != len(framed):
                raise OSError("stdout writer did not accept the complete JSONL frame")
            self.stream.flush()


__all__ = [
    "DEFAULT_MAX_MESSAGE_BYTES",
    "JsonLineWriter",
    "decode_json_line",
    "read_json_line",
]
