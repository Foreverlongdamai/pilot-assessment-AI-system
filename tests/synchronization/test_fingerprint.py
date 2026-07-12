from __future__ import annotations

import hashlib
import math
from importlib.resources import files
from types import MappingProxyType
from typing import cast

import pytest

from pilot_assessment.contracts.common import INT64_MAX, INT64_MIN
from pilot_assessment.contracts.synchronization import SynchronizationPolicy
from pilot_assessment.synchronization.fingerprint import (
    canonical_json_bytes,
    encode_boolean_values,
    encode_int64_values,
    fingerprint_canonical_json,
    fingerprint_policy,
    fingerprint_synchronization,
    hash_part,
)
from pilot_assessment.synchronization.profiles import builtin_temporal_catalog_fingerprint


class _RecordingHashWriter:
    def __init__(self) -> None:
        self.payload = bytearray()

    def update(self, data: bytes) -> object:
        self.payload.extend(data)
        return None


def test_hash_part_uses_unambiguous_tag_and_length_framing() -> None:
    recorder = _RecordingHashWriter()

    hash_part(recorder, tag="ab", payload=b"c")

    assert bytes(recorder.payload) == (b"\x00\x00\x00\x02ab\x00\x00\x00\x00\x00\x00\x00\x01c")
    first = hashlib.sha256()
    second = hashlib.sha256()
    hash_part(first, tag="ab", payload=b"c")
    hash_part(second, tag="a", payload=b"bc")
    assert first.digest() != second.digest()


def test_int64_encoder_uses_signed_little_endian_and_rejects_non_int64() -> None:
    values = (INT64_MIN, -1, 0, 1, INT64_MAX)
    assert encode_int64_values(values) == b"".join(
        value.to_bytes(8, "little", signed=True) for value in values
    )
    for invalid in (True, 1.0, INT64_MIN - 1, INT64_MAX + 1):
        with pytest.raises((TypeError, ValueError), match="signed int64"):
            encode_int64_values(cast(tuple[int, ...], (invalid,)))


def test_boolean_encoder_uses_single_bytes_and_rejects_integer_aliases() -> None:
    assert encode_boolean_values((False, True, False)) == b"\x00\x01\x00"
    for invalid in (0, 1):
        with pytest.raises(TypeError, match="boolean"):
            encode_boolean_values(cast(tuple[bool, ...], (invalid,)))


def test_policy_fingerprint_is_canonical_and_replay_stable() -> None:
    policy = SynchronizationPolicy()
    first = fingerprint_policy(policy)
    second = fingerprint_policy(SynchronizationPolicy.model_validate(policy.model_dump()))

    assert first == second
    assert first == fingerprint_canonical_json(
        "synchronization-policy",
        policy.model_dump(mode="json"),
    )
    assert canonical_json_bytes({"z": "飞行员", "a": [True, 1]}) == (
        b'{"a":[true,1],"z":"\xe9\xa3\x9e\xe8\xa1\x8c\xe5\x91\x98"}'
    )
    for invalid in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError, match="compliant"):
            canonical_json_bytes({"invalid": invalid})


def test_canonical_json_normalizes_frozen_mappings_and_tuples() -> None:
    ordinary = {"a": [1, {"nested": [True, False]}], "z": "pilot"}
    frozen = MappingProxyType(
        {
            "z": "pilot",
            "a": (1, MappingProxyType({"nested": (True, False)})),
        }
    )

    assert canonical_json_bytes(frozen) == canonical_json_bytes(ordinary)


def test_synchronization_fingerprint_sorts_logical_time_part_keys() -> None:
    inputs = {
        "source_snapshot_fingerprint": "1" * 64,
        "policy_fingerprint": "2" * 64,
        "binding_catalog_fingerprint": "3" * 64,
        "aligned_annotations_json": canonical_json_bytes(None),
        "statuses_and_issues_json": canonical_json_bytes({"status": "ready"}),
    }
    first = fingerprint_synchronization(
        **inputs,
        aligned_time_parts={"X/samples/in_session": b"\x01", "X/samples/t_ns": b"\x00"},
    )
    second = fingerprint_synchronization(
        **inputs,
        aligned_time_parts={"X/samples/t_ns": b"\x00", "X/samples/in_session": b"\x01"},
    )

    assert first == second


def test_catalog_fingerprint_matches_packaged_resource_bytes() -> None:
    payload = (
        files("pilot_assessment.synchronization.profile_data")
        .joinpath("m3-temporal-bindings-0.1.json")
        .read_bytes()
    )

    assert builtin_temporal_catalog_fingerprint() == hashlib.sha256(payload).hexdigest()
