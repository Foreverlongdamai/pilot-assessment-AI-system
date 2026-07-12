"""Canonical, length-framed fingerprint primitives for M3 replay."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Protocol, cast

from pydantic import JsonValue

from pilot_assessment.contracts.common import INT64_MAX, INT64_MIN
from pilot_assessment.contracts.synchronization import SynchronizationPolicy


class HashWriter(Protocol):
    def update(self, data: bytes, /) -> object: ...


def hash_part(hasher: HashWriter, *, tag: str, payload: bytes) -> None:
    """Write one unambiguous UTF-8 tag and opaque payload frame."""

    tag_bytes = tag.encode("utf-8")
    hasher.update(len(tag_bytes).to_bytes(4, "big", signed=False))
    hasher.update(tag_bytes)
    hasher.update(len(payload).to_bytes(8, "big", signed=False))
    hasher.update(payload)


def encode_int64_values(values: Iterable[int]) -> bytes:
    """Encode strict signed-int64 values as contiguous little-endian words."""

    payload = bytearray()
    for value in values:
        if type(value) is not int:
            raise TypeError("aligned time values must be strict signed int64 values")
        if not INT64_MIN <= value <= INT64_MAX:
            raise ValueError("aligned time values must be signed int64 values")
        payload.extend(value.to_bytes(8, "little", signed=True))
    return bytes(payload)


def encode_boolean_values(values: Iterable[bool]) -> bytes:
    """Encode strict booleans as one byte per value, rejecting integer aliases."""

    payload = bytearray()
    for value in values:
        if type(value) is not bool:
            raise TypeError("aligned mask values must be boolean values")
        payload.append(1 if value else 0)
    return bytes(payload)


def _normalize_json_value(value: object) -> JsonValue:
    if isinstance(value, Mapping):
        normalized: dict[str, JsonValue] = {}
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError("JSON object keys must be strings")
            normalized[key] = _normalize_json_value(item)
        return normalized
    if isinstance(value, (tuple, list)):
        return [_normalize_json_value(item) for item in value]
    if value is None or type(value) in {str, bool, int, float}:
        return cast(JsonValue, value)
    raise TypeError(f"unsupported JSON value type: {type(value).__name__}")


def canonical_json_bytes(value: object) -> bytes:
    """Serialize one JSON value canonically without non-standard numbers."""

    return json.dumps(
        _normalize_json_value(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def fingerprint_canonical_json(tag: str, value: object) -> str:
    hasher = hashlib.sha256()
    hash_part(hasher, tag=tag, payload=canonical_json_bytes(value))
    return hasher.hexdigest()


def fingerprint_policy(policy: SynchronizationPolicy) -> str:
    return fingerprint_canonical_json(
        "synchronization-policy",
        policy.model_dump(mode="json"),
    )


def fingerprint_synchronization(
    *,
    source_snapshot_fingerprint: str,
    policy_fingerprint: str,
    binding_catalog_fingerprint: str,
    aligned_time_parts: Mapping[str, bytes],
    aligned_annotations_json: bytes,
    statuses_and_issues_json: bytes,
) -> str:
    """Hash the caller-prepared deterministic M3 facts in one frozen order."""

    hasher = hashlib.sha256()
    hash_part(
        hasher,
        tag="source-snapshot-fingerprint",
        payload=source_snapshot_fingerprint.encode("ascii"),
    )
    hash_part(
        hasher,
        tag="policy-fingerprint",
        payload=policy_fingerprint.encode("ascii"),
    )
    hash_part(
        hasher,
        tag="binding-catalog-fingerprint",
        payload=binding_catalog_fingerprint.encode("ascii"),
    )
    for logical_key in sorted(aligned_time_parts):
        hash_part(
            hasher,
            tag=f"aligned-time:{logical_key}",
            payload=aligned_time_parts[logical_key],
        )
    hash_part(hasher, tag="aligned-annotations", payload=aligned_annotations_json)
    hash_part(hasher, tag="statuses-and-issues", payload=statuses_and_issues_json)
    return hasher.hexdigest()


__all__ = [
    "HashWriter",
    "canonical_json_bytes",
    "encode_boolean_values",
    "encode_int64_values",
    "fingerprint_canonical_json",
    "fingerprint_policy",
    "fingerprint_synchronization",
    "hash_part",
]
