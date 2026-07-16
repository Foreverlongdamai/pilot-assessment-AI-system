"""Canonical content identity shared by versioned model components."""

from __future__ import annotations

import hashlib
import math
import struct
from collections.abc import Mapping
from typing import cast

import rfc8785
from pydantic import JsonValue

I_JSON_SAFE_INTEGER_MAX = 9_007_199_254_740_991


def canonical_json_value(value: object) -> JsonValue:
    """Project an accepted value into the frozen canonical JSON domain."""

    if value is None or type(value) in {bool, str}:
        if type(value) is str:
            try:
                value.encode("utf-8", errors="strict")
            except UnicodeEncodeError as error:
                raise ValueError(
                    "canonical JSON strings must not contain unpaired surrogates"
                ) from error
        return cast(JsonValue, value)
    if type(value) is int:
        if not -I_JSON_SAFE_INTEGER_MAX <= value <= I_JSON_SAFE_INTEGER_MAX:
            raise ValueError("canonical JSON integers must be in the I-JSON safe range")
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("canonical JSON numbers must be finite")
        return value
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for key, member in value.items():
            if type(key) is not str:
                raise TypeError("canonical JSON object keys must be exact strings")
            try:
                key.encode("utf-8", errors="strict")
            except UnicodeEncodeError as error:
                raise ValueError(
                    "canonical JSON keys must not contain unpaired surrogates"
                ) from error
            result[key] = canonical_json_value(member)
        return result
    if isinstance(value, (list, tuple)):
        return [canonical_json_value(member) for member in value]
    raise TypeError("value is outside the canonical JSON domain")


def jcs_bytes(value: object) -> bytes:
    """Return RFC 8785 bytes for the project's restricted JSON domain."""

    projected = canonical_json_value(value)
    try:
        return rfc8785.dumps(projected)
    except (rfc8785.CanonicalizationError, UnicodeError, ValueError) as error:
        raise ValueError("RFC 8785 canonicalization failed") from error


def _ascii_identity(value: str, *, label: str) -> bytes:
    if type(value) is not str or not value or "\0" in value:
        raise ValueError(f"{label} must be a non-empty ASCII string without NUL")
    try:
        return value.encode("ascii")
    except UnicodeEncodeError as error:
        raise ValueError(f"{label} must be ASCII") from error


def typed_content_sha256(type_id: str, schema_version: str, value: object) -> str:
    """Hash canonical content with the fixed NUL/uint64 typed framing."""

    type_bytes = _ascii_identity(type_id, label="type_id")
    version_bytes = _ascii_identity(schema_version, label="schema_version")
    canonical = jcs_bytes(value)
    framed = (
        type_bytes + b"\0" + version_bytes + b"\0" + struct.pack(">Q", len(canonical)) + canonical
    )
    return hashlib.sha256(framed).hexdigest()


__all__ = [
    "I_JSON_SAFE_INTEGER_MAX",
    "canonical_json_value",
    "jcs_bytes",
    "typed_content_sha256",
]
