from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import cast

import pytest

from pilot_assessment.contracts.session import SessionManifest
from pilot_assessment.contracts.synchronization import (
    SessionWindow,
    SynchronizationItemStatus,
)
from pilot_assessment.ingestion.manifest_loader import LoadedManifest
from pilot_assessment.synchronization.annotations import (
    AnnotationAlignmentError,
    AnnotationReadLimits,
    align_annotations,
    read_verified_annotation,
)
from pilot_assessment.synchronization.models import SynchronizationInput

_PATHS = {
    "phases": "annotations/phases.json",
    "events": "annotations/events.json",
    "baseline_intervals": "annotations/baseline_intervals.json",
}


def _synthetic_document(record_field: str) -> dict[str, object]:
    common: dict[str, object] = {
        "generator_id": "fixture-v0.1",
        "seed": 1,
        "synthetic_semantics_unvalidated": True,
    }
    if record_field == "phases":
        return {
            **common,
            "schema_id": "phases-synthetic-v0.1",
            "phases": [{"phase_id": "p1", "start_s": 0.0, "end_s": 1.0}],
        }
    if record_field == "events":
        return {
            **common,
            "schema_id": "events-synthetic-v0.1",
            "events": [{"event_id": "e1", "event_type": "disturbance", "time_s": 0.5}],
        }
    if record_field == "baseline_intervals":
        return {
            **common,
            "schema_id": "baseline-intervals-synthetic-v0.1",
            "baseline_intervals": [{"interval_id": "b1", "start_s": 0.0, "end_s": 0.2}],
        }
    raise AssertionError(record_field)


def _loaded_annotations(
    tmp_path: Path,
    *,
    raw_overrides: dict[str, bytes] | None = None,
    expected_phases: tuple[str, ...] = ("p1",),
    revision: str = "synthetic-unvalidated-v0.1",
) -> LoadedManifest:
    root = tmp_path / "bundle"
    (root / "annotations").mkdir(parents=True)
    raw_overrides = raw_overrides or {}
    digests: dict[str, str] = {}
    for record_field, relative_path in _PATHS.items():
        payload = raw_overrides.get(record_field)
        if payload is None:
            payload = json.dumps(
                _synthetic_document(record_field),
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        destination = root.joinpath(*relative_path.split("/"))
        destination.write_bytes(payload)
        digests[relative_path] = hashlib.sha256(payload).hexdigest()

    annotations = SimpleNamespace(revision=revision, **_PATHS)
    task = SimpleNamespace(expected_phases=list(expected_phases))
    manifest = cast(
        SessionManifest,
        SimpleNamespace(annotations=annotations, task=task, session_id="session-1"),
    )
    return LoadedManifest(
        manifest=manifest,
        bundle_root=root,
        manifest_path=root / "manifest.json",
        verified_paths=tuple(sorted(digests)),
        verified_digests=MappingProxyType(dict(digests)),
        declared_reference_count=len(digests),
        unique_artifact_count=len(digests),
    )


def _assert_safe_issue(
    caught: pytest.ExceptionInfo[AnnotationAlignmentError],
    *,
    code: str,
    forbidden: tuple[str, ...] = (),
) -> None:
    issue = caught.value.issue
    assert issue.error_code == code
    serialized = issue.model_dump_json()
    for value in forbidden:
        assert value not in serialized
    assert "exception_type" not in issue.diagnostics
    assert "payload" not in issue.diagnostics


def test_reader_rejects_invalid_utf8_without_leaking_payload(tmp_path: Path) -> None:
    loaded = _loaded_annotations(
        tmp_path,
        raw_overrides={"phases": b"\xffSECRET-INVALID-UTF8"},
    )

    with pytest.raises(AnnotationAlignmentError) as caught:
        read_verified_annotation(loaded, _PATHS["phases"], record_field="phases")

    _assert_safe_issue(
        caught,
        code="ANNOTATION_SEMANTICS_INVALID",
        forbidden=("SECRET-INVALID-UTF8", str(tmp_path)),
    )


def test_reader_rejects_duplicate_json_keys_without_leaking_payload(tmp_path: Path) -> None:
    secret = "SECRET-DUPLICATE-VALUE"
    payload = (
        '{"schema_id":"phases-synthetic-v0.1",'
        '"generator_id":"fixture-v0.1","seed":1,'
        '"synthetic_semantics_unvalidated":true,'
        f'"phases":[],"phases":[{{"secret":"{secret}"}}]}}'
    ).encode()
    loaded = _loaded_annotations(tmp_path, raw_overrides={"phases": payload})

    with pytest.raises(AnnotationAlignmentError) as caught:
        read_verified_annotation(loaded, _PATHS["phases"], record_field="phases")

    _assert_safe_issue(
        caught,
        code="ANNOTATION_SEMANTICS_INVALID",
        forbidden=(secret, str(tmp_path)),
    )


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_reader_rejects_nonstandard_json_constants(
    tmp_path: Path,
    constant: str,
) -> None:
    payload = (
        '{"schema_id":"events-synthetic-v0.1",'
        '"generator_id":"fixture-v0.1","seed":1,'
        '"synthetic_semantics_unvalidated":true,'
        '"events":[{"event_id":"e1","event_type":"disturbance",'
        f'"time_s":{constant}}}]}}'
    ).encode()
    loaded = _loaded_annotations(tmp_path, raw_overrides={"events": payload})

    with pytest.raises(AnnotationAlignmentError) as caught:
        read_verified_annotation(loaded, _PATHS["events"], record_field="events")

    _assert_safe_issue(
        caught,
        code="ANNOTATION_SEMANTICS_INVALID",
        forbidden=(constant, str(tmp_path)),
    )


def test_reader_rejects_file_larger_than_four_mib(tmp_path: Path) -> None:
    payload = b"{}" + b" " * (4 * 1024 * 1024)
    loaded = _loaded_annotations(tmp_path, raw_overrides={"phases": payload})

    with pytest.raises(AnnotationAlignmentError) as caught:
        read_verified_annotation(loaded, _PATHS["phases"], record_field="phases")

    _assert_safe_issue(
        caught,
        code="ANNOTATION_SEMANTICS_INVALID",
        forbidden=(str(tmp_path),),
    )


def test_reader_accepts_file_exactly_at_four_mib_limit(tmp_path: Path) -> None:
    compact = json.dumps(_synthetic_document("phases"), separators=(",", ":")).encode("utf-8")
    payload = compact + b" " * (4 * 1024 * 1024 - len(compact))
    assert len(payload) == 4 * 1024 * 1024
    loaded = _loaded_annotations(tmp_path, raw_overrides={"phases": payload})

    parsed = read_verified_annotation(loaded, _PATHS["phases"], record_field="phases")

    assert parsed["schema_id"] == "phases-synthetic-v0.1"


def test_reader_rejects_more_than_one_hundred_thousand_records(tmp_path: Path) -> None:
    payload = {
        "schema_id": "events-synthetic-v0.1",
        "generator_id": "fixture-v0.1",
        "seed": 1,
        "synthetic_semantics_unvalidated": True,
        "events": [{} for _ in range(100_001)],
    }
    loaded = _loaded_annotations(
        tmp_path,
        raw_overrides={"events": json.dumps(payload, separators=(",", ":")).encode("utf-8")},
    )

    with pytest.raises(AnnotationAlignmentError) as caught:
        read_verified_annotation(loaded, _PATHS["events"], record_field="events")

    _assert_safe_issue(
        caught,
        code="ANNOTATION_SEMANTICS_INVALID",
        forbidden=(str(tmp_path),),
    )


def test_reader_accepts_exactly_one_hundred_thousand_records(tmp_path: Path) -> None:
    payload = {
        "schema_id": "events-synthetic-v0.1",
        "generator_id": "fixture-v0.1",
        "seed": 1,
        "synthetic_semantics_unvalidated": True,
        "events": [{} for _ in range(100_000)],
    }
    loaded = _loaded_annotations(
        tmp_path,
        raw_overrides={"events": json.dumps(payload, separators=(",", ":")).encode("utf-8")},
    )

    parsed = read_verified_annotation(loaded, _PATHS["events"], record_field="events")

    records = cast(list[object], parsed["events"])
    assert len(records) == 100_000


def test_reader_requires_list_at_the_target_record_field(tmp_path: Path) -> None:
    payload = _synthetic_document("phases")
    payload["phases"] = {"not": "a-list"}
    loaded = _loaded_annotations(
        tmp_path,
        raw_overrides={"phases": json.dumps(payload).encode("utf-8")},
    )

    with pytest.raises(AnnotationAlignmentError) as caught:
        read_verified_annotation(loaded, _PATHS["phases"], record_field="phases")

    _assert_safe_issue(caught, code="ANNOTATION_SEMANTICS_INVALID")


def test_reader_translates_invalid_json_to_bounded_domain_error(tmp_path: Path) -> None:
    secret = "SECRET-TRUNCATED-JSON"
    loaded = _loaded_annotations(
        tmp_path,
        raw_overrides={"events": f'{{"events":["{secret}"'.encode()},
    )

    with pytest.raises(AnnotationAlignmentError) as caught:
        read_verified_annotation(loaded, _PATHS["events"], record_field="events")

    _assert_safe_issue(
        caught,
        code="ANNOTATION_SEMANTICS_INVALID",
        forbidden=(secret, str(tmp_path)),
    )


def test_reader_translates_python_integer_digit_limit_to_safe_domain_error(
    tmp_path: Path,
) -> None:
    secret_integer = "9" * 5_000
    payload = (
        '{"schema_id":"events-synthetic-v0.1",'
        '"generator_id":"fixture-v0.1",'
        f'"seed":{secret_integer},'
        '"synthetic_semantics_unvalidated":true,"events":[]}'
    ).encode()
    loaded = _loaded_annotations(tmp_path, raw_overrides={"events": payload})

    with pytest.raises(AnnotationAlignmentError) as caught:
        read_verified_annotation(loaded, _PATHS["events"], record_field="events")

    _assert_safe_issue(
        caught,
        code="ANNOTATION_SEMANTICS_INVALID",
        forbidden=(secret_integer, str(tmp_path), "Exceeds the limit"),
    )


def test_reader_rejects_path_escape_even_when_digest_is_in_snapshot(tmp_path: Path) -> None:
    loaded = _loaded_annotations(tmp_path)
    outside = tmp_path / "outside.json"
    outside_payload = json.dumps(_synthetic_document("phases")).encode("utf-8")
    outside.write_bytes(outside_payload)
    escaped = "../outside.json"
    escaped_loaded = replace(
        loaded,
        verified_digests=MappingProxyType(
            {
                **loaded.verified_digests,
                escaped: hashlib.sha256(outside_payload).hexdigest(),
            }
        ),
    )

    with pytest.raises(AnnotationAlignmentError) as caught:
        read_verified_annotation(escaped_loaded, escaped, record_field="phases")

    _assert_safe_issue(
        caught,
        code="SOURCE_CHANGED_DURING_SYNCHRONIZATION",
        forbidden=(str(outside), str(tmp_path), escaped),
    )


@pytest.mark.parametrize(
    "noncanonical",
    ["annotations/./phases.json", "annotations//phases.json"],
)
def test_reader_rejects_noncanonical_paths_that_alias_verified_file(
    tmp_path: Path,
    noncanonical: str,
) -> None:
    loaded = _loaded_annotations(tmp_path)
    digest = loaded.verified_digests[_PATHS["phases"]]
    aliased = replace(
        loaded,
        verified_digests=MappingProxyType({**loaded.verified_digests, noncanonical: digest}),
    )

    with pytest.raises(AnnotationAlignmentError) as caught:
        read_verified_annotation(aliased, noncanonical, record_field="phases")

    _assert_safe_issue(
        caught,
        code="SOURCE_CHANGED_DURING_SYNCHRONIZATION",
        forbidden=(str(tmp_path), noncanonical),
    )


def test_reader_rejects_symlink_even_when_target_bytes_match_snapshot(tmp_path: Path) -> None:
    loaded = _loaded_annotations(tmp_path)
    source = loaded.bundle_root.joinpath(*_PATHS["phases"].split("/"))
    payload = source.read_bytes()
    outside = tmp_path / "same-bytes.json"
    outside.write_bytes(payload)
    source.unlink()
    try:
        source.symlink_to(outside)
    except OSError:
        return

    with pytest.raises(AnnotationAlignmentError) as caught:
        read_verified_annotation(loaded, _PATHS["phases"], record_field="phases")

    _assert_safe_issue(
        caught,
        code="SOURCE_CHANGED_DURING_SYNCHRONIZATION",
        forbidden=(str(tmp_path), str(outside)),
    )


def test_reader_rejects_windows_reparse_point_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = _loaded_annotations(tmp_path)
    source = loaded.bundle_root.joinpath(*_PATHS["phases"].split("/"))
    original_lstat = Path.lstat

    def mark_annotation_as_reparse(path: Path):
        metadata = original_lstat(path)
        if path == source:
            return SimpleNamespace(
                st_mode=metadata.st_mode,
                st_file_attributes=0x400,
            )
        return metadata

    monkeypatch.setattr(Path, "lstat", mark_annotation_as_reparse)

    with pytest.raises(AnnotationAlignmentError) as caught:
        read_verified_annotation(loaded, _PATHS["phases"], record_field="phases")

    _assert_safe_issue(
        caught,
        code="SOURCE_CHANGED_DURING_SYNCHRONIZATION",
        forbidden=(str(tmp_path),),
    )


def test_reader_requires_path_and_digest_in_verified_snapshot(tmp_path: Path) -> None:
    loaded = _loaded_annotations(tmp_path)
    missing = replace(loaded, verified_digests=MappingProxyType({}))

    with pytest.raises(AnnotationAlignmentError) as caught:
        read_verified_annotation(missing, _PATHS["phases"], record_field="phases")

    _assert_safe_issue(
        caught,
        code="SOURCE_CHANGED_DURING_SYNCHRONIZATION",
        forbidden=(str(tmp_path), _PATHS["phases"]),
    )


def test_reader_rejects_snapshot_digest_change(tmp_path: Path) -> None:
    loaded = _loaded_annotations(tmp_path)
    source = loaded.bundle_root.joinpath(*_PATHS["phases"].split("/"))
    source.write_bytes(b'{"schema_id":"phases-synthetic-v0.1","phases":[]}')

    with pytest.raises(AnnotationAlignmentError) as caught:
        read_verified_annotation(loaded, _PATHS["phases"], record_field="phases")

    _assert_safe_issue(
        caught,
        code="SOURCE_CHANGED_DURING_SYNCHRONIZATION",
        forbidden=(str(tmp_path),),
    )


def test_reader_translates_missing_file_os_failure(tmp_path: Path) -> None:
    loaded = _loaded_annotations(tmp_path)
    source = loaded.bundle_root.joinpath(*_PATHS["phases"].split("/"))
    source.unlink()

    with pytest.raises(AnnotationAlignmentError) as caught:
        read_verified_annotation(loaded, _PATHS["phases"], record_field="phases")

    _assert_safe_issue(
        caught,
        code="SOURCE_CHANGED_DURING_SYNCHRONIZATION",
        forbidden=(str(tmp_path),),
    )


def test_reader_honours_custom_bounded_limits(tmp_path: Path) -> None:
    loaded = _loaded_annotations(tmp_path)

    with pytest.raises(AnnotationAlignmentError) as caught:
        read_verified_annotation(
            loaded,
            _PATHS["phases"],
            record_field="phases",
            limits=AnnotationReadLimits(max_bytes=64, max_records=1),
        )

    _assert_safe_issue(caught, code="ANNOTATION_SEMANTICS_INVALID")


def _canonical_documents() -> dict[str, dict[str, object]]:
    common: dict[str, object] = {
        "annotation_revision": "expert-revision-1",
        "timebase": {"origin": "session_start", "unit": "ns"},
        "annotation_source": "expert",
    }
    return {
        "phases": {
            **common,
            "schema_id": "phases-session-time-v0.1",
            "phases": [
                {
                    "phase_id": "p1",
                    "label": "phase one",
                    "start_t_ns": 0,
                    "end_t_ns": 1_000_000_000,
                    "source": "expert",
                    "confidence": 1.0,
                }
            ],
        },
        "events": {
            **common,
            "schema_id": "events-session-time-v0.1",
            "events": [
                {
                    "event_id": "e1",
                    "event_type": "disturbance",
                    "t_ns": 500_000_000,
                    "source": "expert",
                    "confidence": 1.0,
                }
            ],
        },
        "baseline_intervals": {
            **common,
            "schema_id": "baseline-intervals-session-time-v0.1",
            "baseline_intervals": [
                {
                    "interval_id": "b1",
                    "start_t_ns": 0,
                    "end_t_ns": 200_000_000,
                    "condition": "nominal",
                    "valid": True,
                }
            ],
        },
    }


def _align_documents(
    tmp_path: Path,
    *,
    documents: dict[str, dict[str, object]] | None = None,
    raw_overrides: dict[str, bytes] | None = None,
    expected_phases: tuple[str, ...] = ("p1",),
    revision: str = "synthetic-unvalidated-v0.1",
    end_t_ns: int = 1_000_000_000,
):
    if documents is None:
        documents = {field: _synthetic_document(field) for field in _PATHS}
    encoded = {
        field: json.dumps(
            document,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        for field, document in documents.items()
    }
    if raw_overrides:
        encoded.update(raw_overrides)
    loaded = _loaded_annotations(
        tmp_path,
        raw_overrides=encoded,
        expected_phases=expected_phases,
        revision=revision,
    )
    sync_input = cast(
        SynchronizationInput,
        SimpleNamespace(loaded_manifest=loaded),
    )
    window = SessionWindow(
        end_t_ns=end_t_ns,
        source="master-clock-x-mapped-coverage-v1",
    )
    return align_annotations(sync_input, window)


def _assert_annotation_error(
    caught: pytest.ExceptionInfo[AnnotationAlignmentError],
    code: str = "ANNOTATION_SEMANTICS_INVALID",
) -> None:
    assert caught.value.issue.error_code == code
    assert "exception_type" not in caught.value.issue.diagnostics
    assert "payload" not in caught.value.issue.diagnostics


_MINIMAL_REGISTERED_SHAPES = (
    ("phases", _synthetic_document("phases")),
    ("events", _synthetic_document("events")),
    ("baseline_intervals", _synthetic_document("baseline_intervals")),
    ("phases", _canonical_documents()["phases"]),
    ("events", _canonical_documents()["events"]),
    ("baseline_intervals", _canonical_documents()["baseline_intervals"]),
)


@pytest.mark.parametrize(("record_field", "document"), _MINIMAL_REGISTERED_SHAPES)
def test_exact_registered_annotation_shapes_accept_minimal_and_forbid_extra_fields(
    tmp_path: Path,
    record_field: str,
    document: dict[str, object],
) -> None:
    documents = {field: _synthetic_document(field) for field in _PATHS}
    documents[record_field] = document
    revision = (
        "expert-revision-1"
        if str(document["schema_id"]).endswith("session-time-v0.1")
        else "synthetic-unvalidated-v0.1"
    )
    aligned, result = _align_documents(
        tmp_path / "valid",
        documents=documents,
        revision=revision,
    )
    assert result.synchronization_status is SynchronizationItemStatus.ALIGNED
    assert aligned.source_schema_ids[record_field] == document["schema_id"]

    top_extra = {**document, "unexpected": "forbidden"}
    top_documents = {field: _synthetic_document(field) for field in _PATHS}
    top_documents[record_field] = top_extra
    with pytest.raises(AnnotationAlignmentError) as top_caught:
        _align_documents(
            tmp_path / "top-extra",
            documents=top_documents,
            revision=revision,
        )
    _assert_annotation_error(top_caught)

    nested_extra = json.loads(json.dumps(document))
    records = cast(list[dict[str, object]], nested_extra[record_field])
    records[0]["unexpected"] = "forbidden"
    nested_documents = {field: _synthetic_document(field) for field in _PATHS}
    nested_documents[record_field] = nested_extra
    with pytest.raises(AnnotationAlignmentError) as nested_caught:
        _align_documents(
            tmp_path / "nested-extra",
            documents=nested_documents,
            revision=revision,
        )
    _assert_annotation_error(nested_caught)


@pytest.mark.parametrize(
    ("record_field", "mutation"),
    [
        ("phases", {"seed": True}),
        ("events", {"seed": 1.0}),
        ("baseline_intervals", {"synthetic_semantics_unvalidated": 1}),
    ],
)
def test_synthetic_schema_rejects_bool_int_and_float_scalar_coercion(
    tmp_path: Path,
    record_field: str,
    mutation: dict[str, object],
) -> None:
    documents = {field: _synthetic_document(field) for field in _PATHS}
    documents[record_field] = {**documents[record_field], **mutation}

    with pytest.raises(AnnotationAlignmentError) as caught:
        _align_documents(tmp_path, documents=documents)

    _assert_annotation_error(caught)


def test_canonical_nanosecond_fields_reject_float_and_bool_coercion(tmp_path: Path) -> None:
    for index, invalid in enumerate((0.0, True)):
        documents = _canonical_documents()
        phase = cast(list[dict[str, object]], documents["phases"]["phases"])[0]
        phase["start_t_ns"] = invalid
        with pytest.raises(AnnotationAlignmentError) as caught:
            _align_documents(
                tmp_path / str(index),
                documents=documents,
                revision="expert-revision-1",
            )
        _assert_annotation_error(caught)


def test_synthetic_overflowing_json_exponent_is_rejected(tmp_path: Path) -> None:
    raw = (
        b'{"schema_id":"events-synthetic-v0.1",'
        b'"generator_id":"fixture-v0.1","seed":1,'
        b'"synthetic_semantics_unvalidated":true,'
        b'"events":[{"event_id":"e1","event_type":"disturbance",'
        b'"time_s":1e309}]}'
    )

    with pytest.raises(AnnotationAlignmentError) as caught:
        _align_documents(tmp_path, raw_overrides={"events": raw})

    _assert_annotation_error(caught)


def test_synthetic_annotation_seconds_use_shared_half_even_converter_without_device_clock(
    tmp_path: Path,
) -> None:
    documents = {
        "phases": {
            **_synthetic_document("phases"),
            "phases": [{"phase_id": "p1", "start_s": 0.0000000005, "end_s": 0.0000000015}],
        },
        "events": {
            **_synthetic_document("events"),
            "events": [
                {
                    "event_id": "e1",
                    "event_type": "disturbance",
                    "time_s": 0.0000000025,
                }
            ],
        },
        "baseline_intervals": {
            **_synthetic_document("baseline_intervals"),
            "baseline_intervals": [{"interval_id": "b1", "start_s": 0.0, "end_s": 0.0000000035}],
        },
    }

    aligned, _result = _align_documents(tmp_path, documents=documents, end_t_ns=10)

    assert (aligned.phases[0].start_t_ns, aligned.phases[0].end_t_ns) == (0, 2)
    assert aligned.events[0].t_ns == 2
    assert aligned.baseline_intervals[0].end_t_ns == 4


def test_synthetic_annotation_provenance_remains_semantically_unvalidated(
    tmp_path: Path,
) -> None:
    aligned, result = _align_documents(tmp_path)

    assert aligned.synthetic_semantics_unvalidated is True
    assert result.synthetic_semantics_unvalidated is True


def test_all_canonical_annotations_report_synthetic_provenance_false(tmp_path: Path) -> None:
    aligned, result = _align_documents(
        tmp_path,
        documents=_canonical_documents(),
        revision="expert-revision-1",
    )

    assert aligned.synthetic_semantics_unvalidated is False
    assert result.synthetic_semantics_unvalidated is False


def test_unknown_annotation_schema_is_rejected_without_guessing(tmp_path: Path) -> None:
    documents = {field: _synthetic_document(field) for field in _PATHS}
    documents["events"] = {**documents["events"], "schema_id": "events-future-v9"}

    with pytest.raises(AnnotationAlignmentError) as caught:
        _align_documents(tmp_path, documents=documents)

    _assert_annotation_error(caught, "ANNOTATION_SCHEMA_UNSUPPORTED")


def test_known_malformed_annotation_schema_is_semantics_invalid(tmp_path: Path) -> None:
    documents = {field: _synthetic_document(field) for field in _PATHS}
    del documents["events"]["generator_id"]

    with pytest.raises(AnnotationAlignmentError) as caught:
        _align_documents(tmp_path, documents=documents)

    _assert_annotation_error(caught)


@pytest.mark.parametrize(
    "phase_ids",
    [
        ("p1", "p1"),
        ("p2", "p1"),
        ("p1",),
        ("p1", "p2", "p3"),
    ],
)
def test_phase_ids_are_unique_and_match_manifest_order(
    tmp_path: Path,
    phase_ids: tuple[str, ...],
) -> None:
    documents = {field: _synthetic_document(field) for field in _PATHS}
    documents["phases"] = {
        **documents["phases"],
        "phases": [
            {"phase_id": phase_id, "start_s": index * 0.2, "end_s": (index + 1) * 0.2}
            for index, phase_id in enumerate(phase_ids)
        ],
    }

    with pytest.raises(AnnotationAlignmentError) as caught:
        _align_documents(
            tmp_path,
            documents=documents,
            expected_phases=("p1", "p2"),
        )

    _assert_annotation_error(caught)


@pytest.mark.parametrize(
    "phases",
    [
        [
            {"phase_id": "p1", "start_s": 0.2, "end_s": 0.2},
            {"phase_id": "p2", "start_s": 0.3, "end_s": 0.4},
        ],
        [
            {"phase_id": "p1", "start_s": 0.0, "end_s": 0.6},
            {"phase_id": "p2", "start_s": 0.5, "end_s": 0.8},
        ],
        [
            {"phase_id": "p1", "start_s": 0.5, "end_s": 0.7},
            {"phase_id": "p2", "start_s": 0.2, "end_s": 0.4},
        ],
        [
            {"phase_id": "p1", "start_s": 0.0, "end_s": 0.6},
            {"phase_id": "p2", "start_s": 0.8, "end_s": 1.1},
        ],
    ],
)
def test_phases_must_be_ordered_non_overlapping_and_fully_in_session(
    tmp_path: Path,
    phases: list[dict[str, object]],
) -> None:
    documents = {field: _synthetic_document(field) for field in _PATHS}
    documents["phases"] = {**documents["phases"], "phases": phases}

    with pytest.raises(AnnotationAlignmentError) as caught:
        _align_documents(
            tmp_path,
            documents=documents,
            expected_phases=("p1", "p2"),
        )

    _assert_annotation_error(caught)


def test_phase_gaps_are_allowed_and_reported(tmp_path: Path) -> None:
    documents = {field: _synthetic_document(field) for field in _PATHS}
    documents["phases"] = {
        **documents["phases"],
        "phases": [
            {"phase_id": "p1", "start_s": 0.2, "end_s": 0.4},
            {"phase_id": "p2", "start_s": 0.6, "end_s": 0.8},
        ],
    }

    _aligned, result = _align_documents(
        tmp_path,
        documents=documents,
        expected_phases=("p1", "p2"),
    )

    assert [
        (interval.start_t_ns, interval.end_t_ns) for interval in result.unannotated_intervals
    ] == [
        (0, 200_000_000),
        (400_000_000, 600_000_000),
        (800_000_000, 1_000_000_000),
    ]


def test_last_phase_includes_exact_session_endpoint(tmp_path: Path) -> None:
    documents = {field: _synthetic_document(field) for field in _PATHS}
    documents["phases"] = {
        **documents["phases"],
        "phases": [{"phase_id": "p1", "start_s": 0.0, "end_s": 1.0}],
    }

    aligned, result = _align_documents(tmp_path, documents=documents)

    assert aligned.phases[-1].end_t_ns == 1_000_000_000
    assert result.unannotated_intervals == ()


def test_point_events_accept_both_closed_window_boundaries(tmp_path: Path) -> None:
    documents = _canonical_documents()
    documents["events"]["events"] = [
        {
            "event_id": "start",
            "event_type": "disturbance",
            "t_ns": 0,
            "source": "expert",
            "confidence": 1.0,
        },
        {
            "event_id": "end",
            "event_type": "disturbance",
            "t_ns": 1_000_000_000,
            "source": "expert",
            "confidence": 1.0,
        },
    ]

    aligned, _result = _align_documents(
        tmp_path,
        documents=documents,
        revision="expert-revision-1",
    )

    assert [event.t_ns for event in aligned.events] == [0, 1_000_000_000]


def test_duration_event_requires_positive_duration_and_session_overlap(tmp_path: Path) -> None:
    for index, (start, duration) in enumerate(((0, 0), (1_000_000_001, 1))):
        documents = _canonical_documents()
        event = cast(list[dict[str, object]], documents["events"]["events"])[0]
        event.update({"t_ns": start, "duration_ns": duration})
        with pytest.raises(AnnotationAlignmentError) as caught:
            _align_documents(
                tmp_path / str(index),
                documents=documents,
                revision="expert-revision-1",
            )
        _assert_annotation_error(caught)

    touching = _canonical_documents()
    event = cast(list[dict[str, object]], touching["events"]["events"])[0]
    event.update({"t_ns": 1_000_000_000, "duration_ns": 1})
    aligned, _result = _align_documents(
        tmp_path / "touching",
        documents=touching,
        revision="expert-revision-1",
    )
    assert aligned.events[0].duration_ns == 1


def test_duration_event_rejects_int64_end_overflow(tmp_path: Path) -> None:
    maximum = 2**63 - 1
    documents = _canonical_documents()
    phase = cast(list[dict[str, object]], documents["phases"]["phases"])[0]
    phase["end_t_ns"] = maximum
    event = cast(list[dict[str, object]], documents["events"]["events"])[0]
    event.update({"t_ns": maximum - 1, "duration_ns": 10})

    with pytest.raises(AnnotationAlignmentError) as caught:
        _align_documents(
            tmp_path,
            documents=documents,
            revision="expert-revision-1",
            end_t_ns=maximum,
        )

    _assert_annotation_error(caught)


def test_event_response_mapping_is_validated_but_not_executed(tmp_path: Path) -> None:
    mapping = {
        "response_mapping_id": "mapping-v1",
        "observation_horizon_ns": 500_000_000,
        "expected_channels": ["control.longitudinal_raw"],
        "response_aggregation": "earliest_any_mapped",
    }
    documents = _canonical_documents()
    event = cast(list[dict[str, object]], documents["events"]["events"])[0]
    event["response_mapping"] = mapping

    aligned, _result = _align_documents(
        tmp_path / "valid",
        documents=documents,
        revision="expert-revision-1",
    )

    assert aligned.events[0].response_mapping == mapping

    invalid = _canonical_documents()
    invalid_event = cast(list[dict[str, object]], invalid["events"]["events"])[0]
    invalid_event["response_mapping"] = ["not", "an", "object"]
    with pytest.raises(AnnotationAlignmentError) as caught:
        _align_documents(
            tmp_path / "invalid",
            documents=invalid,
            revision="expert-revision-1",
        )
    _assert_annotation_error(caught)


@pytest.mark.parametrize(
    ("start_t_ns", "end_t_ns"),
    [(10, 10), (900_000_000, 1_000_000_001)],
)
def test_baseline_must_be_positive_and_fully_in_session(
    tmp_path: Path,
    start_t_ns: int,
    end_t_ns: int,
) -> None:
    documents = _canonical_documents()
    baseline = cast(
        list[dict[str, object]],
        documents["baseline_intervals"]["baseline_intervals"],
    )[0]
    baseline.update({"start_t_ns": start_t_ns, "end_t_ns": end_t_ns})

    with pytest.raises(AnnotationAlignmentError) as caught:
        _align_documents(
            tmp_path,
            documents=documents,
            revision="expert-revision-1",
        )

    _assert_annotation_error(caught)


def test_invalid_baseline_requires_exclusion_reason(tmp_path: Path) -> None:
    invalid = _canonical_documents()
    baseline = cast(
        list[dict[str, object]],
        invalid["baseline_intervals"]["baseline_intervals"],
    )[0]
    baseline["valid"] = False
    with pytest.raises(AnnotationAlignmentError) as caught:
        _align_documents(
            tmp_path / "missing",
            documents=invalid,
            revision="expert-revision-1",
        )
    _assert_annotation_error(caught)

    documented = _canonical_documents()
    documented_baseline = cast(
        list[dict[str, object]],
        documented["baseline_intervals"]["baseline_intervals"],
    )[0]
    documented_baseline.update({"valid": False, "exclusion_reason": "motion-contamination"})
    aligned, _result = _align_documents(
        tmp_path / "documented",
        documents=documented,
        revision="expert-revision-1",
    )
    assert aligned.baseline_intervals[0].exclusion_reason == "motion-contamination"


def test_baseline_phase_overlap_is_allowed(tmp_path: Path) -> None:
    documents = _canonical_documents()
    baseline = cast(
        list[dict[str, object]],
        documents["baseline_intervals"]["baseline_intervals"],
    )[0]
    baseline.update({"start_t_ns": 200_000_000, "end_t_ns": 800_000_000})

    aligned, _result = _align_documents(
        tmp_path,
        documents=documents,
        revision="expert-revision-1",
    )

    assert aligned.phases[0].start_t_ns < aligned.baseline_intervals[0].end_t_ns
    assert aligned.baseline_intervals[0].start_t_ns < aligned.phases[0].end_t_ns


def test_event_and_baseline_ids_must_be_unique(tmp_path: Path) -> None:
    for index, record_field in enumerate(("events", "baseline_intervals")):
        documents = _canonical_documents()
        records = cast(list[dict[str, object]], documents[record_field][record_field])
        records.append(dict(records[0]))
        with pytest.raises(AnnotationAlignmentError) as caught:
            _align_documents(
                tmp_path / str(index),
                documents=documents,
                revision="expert-revision-1",
            )
        _assert_annotation_error(caught)


def test_canonical_revision_and_timebase_must_match_manifest_contract(tmp_path: Path) -> None:
    wrong_revision = _canonical_documents()
    wrong_revision["events"]["annotation_revision"] = "different-revision"
    with pytest.raises(AnnotationAlignmentError) as revision_caught:
        _align_documents(
            tmp_path / "revision",
            documents=wrong_revision,
            revision="expert-revision-1",
        )
    _assert_annotation_error(revision_caught)

    wrong_timebase = _canonical_documents()
    wrong_timebase["events"]["timebase"] = {
        "origin": "device_start",
        "unit": "ns",
    }
    with pytest.raises(AnnotationAlignmentError) as timebase_caught:
        _align_documents(
            tmp_path / "timebase",
            documents=wrong_timebase,
            revision="expert-revision-1",
        )
    _assert_annotation_error(timebase_caught)


def test_canonical_nanoseconds_are_preserved_without_clock_transform(tmp_path: Path) -> None:
    documents = _canonical_documents()
    phase = cast(list[dict[str, object]], documents["phases"]["phases"])[0]
    phase.update({"start_t_ns": 123, "end_t_ns": 999_999_999})

    aligned, _result = _align_documents(
        tmp_path,
        documents=documents,
        revision="expert-revision-1",
    )

    assert (aligned.phases[0].start_t_ns, aligned.phases[0].end_t_ns) == (
        123,
        999_999_999,
    )


def test_synthetic_files_require_consistent_generator_seed_and_true_flag(
    tmp_path: Path,
) -> None:
    for index, mutation in enumerate(
        (
            {"generator_id": "other-generator-v0.1"},
            {"seed": 2},
            {"synthetic_semantics_unvalidated": False},
        )
    ):
        documents = {field: _synthetic_document(field) for field in _PATHS}
        documents["events"] = {**documents["events"], **mutation}
        with pytest.raises(AnnotationAlignmentError) as caught:
            _align_documents(tmp_path / str(index), documents=documents)
        _assert_annotation_error(caught)


def test_mixed_registered_families_remain_supported_and_any_synthetic_stays_flagged(
    tmp_path: Path,
) -> None:
    documents = _canonical_documents()
    documents["events"] = _synthetic_document("events")

    aligned, result = _align_documents(
        tmp_path,
        documents=documents,
        revision="expert-revision-1",
    )

    assert aligned.source_schema_ids == {
        "phases": "phases-session-time-v0.1",
        "events": "events-synthetic-v0.1",
        "baseline_intervals": "baseline-intervals-session-time-v0.1",
    }
    assert aligned.synthetic_semantics_unvalidated is True
    assert result.synthetic_semantics_unvalidated is True
