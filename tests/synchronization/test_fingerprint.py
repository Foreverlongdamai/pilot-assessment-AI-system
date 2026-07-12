from __future__ import annotations

import hashlib
import math
from importlib.resources import files
from pathlib import Path
from types import MappingProxyType
from typing import cast

import polars as pl
import pytest

from pilot_assessment.contracts.common import INT64_MAX, INT64_MIN
from pilot_assessment.contracts.errors import DomainErrorData, ErrorSeverity
from pilot_assessment.contracts.synchronization import SynchronizationPolicy
from pilot_assessment.synchronization import SynchronizationInput, synchronize_session
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

from .test_service import _ready_input, _replace_stream_table


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


def test_synchronization_fingerprint_matches_full_framed_contract_order() -> None:
    source_snapshot = "1" * 64
    policy = "2" * 64
    catalog = "3" * 64
    time_parts = {
        "U/samples/in_session": encode_boolean_values((True, False)),
        "X/samples/t_ns": encode_int64_values((0, 10)),
    }
    annotations = canonical_json_bytes({"events": [], "phases": []})
    statuses = canonical_json_bytes({"disposition": "ready"})
    expected = hashlib.sha256()
    hash_part(
        expected,
        tag="source-snapshot-fingerprint",
        payload=source_snapshot.encode("ascii"),
    )
    hash_part(expected, tag="policy-fingerprint", payload=policy.encode("ascii"))
    hash_part(expected, tag="binding-catalog-fingerprint", payload=catalog.encode("ascii"))
    for logical_key in sorted(time_parts):
        hash_part(
            expected,
            tag=f"aligned-time:{logical_key}",
            payload=time_parts[logical_key],
        )
    hash_part(expected, tag="aligned-annotations", payload=annotations)
    hash_part(expected, tag="statuses-and-issues", payload=statuses)

    actual = fingerprint_synchronization(
        source_snapshot_fingerprint=source_snapshot,
        policy_fingerprint=policy,
        binding_catalog_fingerprint=catalog,
        aligned_time_parts=time_parts,
        aligned_annotations_json=annotations,
        statuses_and_issues_json=statuses,
    )

    assert actual == expected.hexdigest()


def test_annotation_fingerprint_is_canonical_and_content_sensitive() -> None:
    shared = {
        "source_snapshot_fingerprint": "1" * 64,
        "policy_fingerprint": "2" * 64,
        "binding_catalog_fingerprint": "3" * 64,
        "aligned_time_parts": {},
        "statuses_and_issues_json": canonical_json_bytes({"status": "ready"}),
    }
    first_annotations = canonical_json_bytes(
        {"z_metadata": {"source": "fixture"}, "events": [{"event_id": "event-1"}]}
    )
    reordered_annotations = canonical_json_bytes(
        {"events": [{"event_id": "event-1"}], "z_metadata": {"source": "fixture"}}
    )
    changed_annotations = canonical_json_bytes(
        {"events": [{"event_id": "event-2"}], "z_metadata": {"source": "fixture"}}
    )

    first = fingerprint_synchronization(
        **shared,
        aligned_annotations_json=first_annotations,
    )
    reordered = fingerprint_synchronization(
        **shared,
        aligned_annotations_json=reordered_annotations,
    )
    changed = fingerprint_synchronization(
        **shared,
        aligned_annotations_json=changed_annotations,
    )

    assert first_annotations == reordered_annotations
    assert first == reordered
    assert first != changed


def test_status_fingerprint_is_content_sensitive() -> None:
    shared = {
        "source_snapshot_fingerprint": "1" * 64,
        "policy_fingerprint": "2" * 64,
        "binding_catalog_fingerprint": "3" * 64,
        "aligned_time_parts": {},
        "aligned_annotations_json": canonical_json_bytes(None),
    }

    ready = fingerprint_synchronization(
        **shared,
        statuses_and_issues_json=canonical_json_bytes({"disposition": "ready"}),
    )
    blocked = fingerprint_synchronization(
        **shared,
        statuses_and_issues_json=canonical_json_bytes({"disposition": "blocked"}),
    )

    assert ready != blocked


def test_catalog_fingerprint_matches_packaged_resource_bytes() -> None:
    payload = (
        files("pilot_assessment.synchronization.profile_data")
        .joinpath("m3-temporal-bindings-0.1.json")
        .read_bytes()
    )

    assert builtin_temporal_catalog_fingerprint() == hashlib.sha256(payload).hexdigest()


def test_full_outcome_fingerprint_is_replay_stable(tmp_path: Path) -> None:
    sync_input = _ready_input(tmp_path)

    first = synchronize_session(sync_input)
    second = synchronize_session(sync_input)

    assert first.report.synchronization_fingerprint == second.report.synchronization_fingerprint
    assert first.aligned_session is not None and second.aligned_session is not None
    assert (
        first.aligned_session.synchronization_fingerprint
        == second.aligned_session.synchronization_fingerprint
    )


def test_full_outcome_fingerprint_is_bundle_root_independent(tmp_path: Path) -> None:
    left_root = tmp_path / "left"
    right_root = tmp_path / "right"
    left_root.mkdir()
    right_root.mkdir()
    left_input = _ready_input(left_root)
    right_input = _ready_input(right_root)

    left = synchronize_session(left_input)
    right = synchronize_session(right_input)

    assert left.report.source_snapshot_fingerprint == right.report.source_snapshot_fingerprint
    assert left.report.synchronization_fingerprint == right.report.synchronization_fingerprint


def test_synchronization_fingerprint_changes_with_policy_fingerprint() -> None:
    shared = {
        "source_snapshot_fingerprint": "1" * 64,
        "binding_catalog_fingerprint": "3" * 64,
        "aligned_time_parts": {"X/samples/t_ns": encode_int64_values((0, 1))},
        "aligned_annotations_json": canonical_json_bytes(None),
        "statuses_and_issues_json": canonical_json_bytes({"status": "ready"}),
    }

    first = fingerprint_synchronization(**shared, policy_fingerprint="2" * 64)
    second = fingerprint_synchronization(**shared, policy_fingerprint="4" * 64)

    assert first != second


def test_full_outcome_fingerprint_changes_with_aligned_time(tmp_path: Path) -> None:
    sync_input = _ready_input(tmp_path)
    source = sync_input.prepared_session.streams["U"].tables["samples"]
    mutated = source.with_columns(
        pl.when(pl.col("source_row_index") == 100)
        .then(pl.col("source_time_s") + 0.001)
        .otherwise(pl.col("source_time_s"))
        .alias("source_time_s")
    )
    changed_input = _replace_stream_table(sync_input, "U", "samples", mutated)

    original = synchronize_session(sync_input)
    changed = synchronize_session(changed_input)

    assert original.report.source_snapshot_fingerprint == changed.report.source_snapshot_fingerprint
    assert original.report.synchronization_fingerprint != changed.report.synchronization_fingerprint


def _nonblocking_issue(code: str, field: str) -> DomainErrorData:
    return DomainErrorData(
        error_code=code,
        severity=ErrorSeverity.WARNING,
        recoverable=True,
        message=f"bounded {code}",
        field_or_path=field,
        remediation="Use corrected fixture input.",
        diagnostics={"z": 2, "a": 1},
    )


def test_full_outcome_fingerprint_is_issue_order_independent(tmp_path: Path) -> None:
    sync_input = _ready_input(tmp_path)
    first_issue = _nonblocking_issue("A_ORDER_FIXTURE", "a")
    second_issue = _nonblocking_issue("Z_ORDER_FIXTURE", "z")
    x_result = sync_input.readiness_report.stream_results["X"]

    def reordered_input(reverse: bool) -> SynchronizationInput:
        ordered = (second_issue, first_issue) if reverse else (first_issue, second_issue)
        stream_results = dict(sync_input.readiness_report.stream_results)
        stream_results["X"] = x_result.model_copy(update={"issues": ordered})
        report = sync_input.readiness_report.model_copy(
            update={
                "stream_results": stream_results,
                "global_issues": ordered,
            }
        )
        return SynchronizationInput(
            loaded_manifest=sync_input.loaded_manifest,
            readiness_report=report,
            prepared_session=sync_input.prepared_session,
        )

    first = synchronize_session(reordered_input(reverse=False))
    second = synchronize_session(reordered_input(reverse=True))

    assert first.report.synchronization_fingerprint == second.report.synchronization_fingerprint


def test_full_outcome_fingerprint_is_issue_order_independent_for_sort_key_collisions(
    tmp_path: Path,
) -> None:
    sync_input = _ready_input(tmp_path)
    first_issue = DomainErrorData(
        error_code="ORDER_COLLISION_FIXTURE",
        severity=ErrorSeverity.WARNING,
        recoverable=True,
        message="same bounded issue",
        field_or_path="same.field",
        remediation="first remediation",
        diagnostics={"variant": "first"},
    )
    second_issue = DomainErrorData(
        error_code="ORDER_COLLISION_FIXTURE",
        severity=ErrorSeverity.WARNING,
        recoverable=True,
        message="same bounded issue",
        field_or_path="same.field",
        remediation="second remediation",
        diagnostics={"variant": "second"},
    )

    def with_issue_order(issues: tuple[DomainErrorData, ...]) -> SynchronizationInput:
        report = sync_input.readiness_report.model_copy(update={"global_issues": issues})
        return SynchronizationInput(
            loaded_manifest=sync_input.loaded_manifest,
            readiness_report=report,
            prepared_session=sync_input.prepared_session,
        )

    first = synchronize_session(with_issue_order((first_issue, second_issue)))
    second = synchronize_session(with_issue_order((second_issue, first_issue)))

    assert first.report.synchronization_fingerprint == second.report.synchronization_fingerprint
