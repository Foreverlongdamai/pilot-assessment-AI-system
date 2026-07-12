"""Bounded, snapshot-checked reading for M3 session annotations."""

from __future__ import annotations

import hashlib
import json
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, NoReturn, Self, cast

from pydantic import (
    JsonValue,
    StrictBool,
    StringConstraints,
    ValidationError,
    model_validator,
)

from pilot_assessment.contracts.common import (
    INT64_MAX,
    FiniteFloat,
    NonNegativeInt,
    NonNegativeInt64,
    StableId,
    StrictContractModel,
    UnitInterval,
)
from pilot_assessment.contracts.errors import DomainErrorData, ErrorSeverity
from pilot_assessment.contracts.synchronization import (
    AnnotationSynchronizationResult,
    BaselineInterval,
    EventMarker,
    PhaseInterval,
    SessionInterval,
    SessionWindow,
    SynchronizationItemStatus,
)
from pilot_assessment.ingestion.manifest_loader import LoadedManifest
from pilot_assessment.synchronization.clock import session_seconds_to_ns
from pilot_assessment.synchronization.models import AlignedAnnotations, SynchronizationInput

AnnotationRecordField = Literal["phases", "events", "baseline_intervals"]
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_NON_EMPTY_TEXT = Annotated[str, StringConstraints(min_length=1, max_length=512)]


@dataclass(frozen=True, slots=True)
class AnnotationReadLimits:
    max_bytes: int = 4 * 1024 * 1024
    max_records: int = 100_000


class AnnotationAlignmentError(Exception):
    def __init__(self, issue: DomainErrorData) -> None:
        self.issue = issue
        super().__init__(issue.message)


class _DuplicateJsonKeyError(ValueError):
    pass


class _NonStandardJsonConstantError(ValueError):
    pass


def _fail(
    error_code: Literal[
        "ANNOTATION_SEMANTICS_INVALID",
        "ANNOTATION_SCHEMA_UNSUPPORTED",
        "SOURCE_CHANGED_DURING_SYNCHRONIZATION",
    ],
    message: str,
    *,
    record_field: AnnotationRecordField,
    remediation: str,
    diagnostics: dict[str, JsonValue] | None = None,
) -> NoReturn:
    raise AnnotationAlignmentError(
        DomainErrorData(
            error_code=error_code,
            severity=ErrorSeverity.ERROR,
            recoverable=True,
            message=message,
            field_or_path=f"annotations.{record_field}",
            remediation=remediation,
            diagnostics=diagnostics or {},
        )
    )


def _require_valid_limits(
    limits: AnnotationReadLimits,
    record_field: AnnotationRecordField,
) -> None:
    if (
        type(limits.max_bytes) is not int
        or limits.max_bytes <= 0
        or type(limits.max_records) is not int
        or limits.max_records <= 0
    ):
        _fail(
            "ANNOTATION_SEMANTICS_INVALID",
            "Annotation reader limits must be positive integers",
            record_field=record_field,
            remediation="Use the approved positive annotation reader limits.",
        )


def _validate_relative_path(
    relative_path: str,
    record_field: AnnotationRecordField,
) -> tuple[str, ...]:
    invalid = (
        not relative_path
        or "\\" in relative_path
        or relative_path.startswith(("/", "//"))
        or ":" in relative_path
        or "\x00" in relative_path
        or relative_path.endswith("/")
    )
    canonical = PurePosixPath(relative_path)
    parts = tuple(canonical.parts)
    if (
        invalid
        or canonical.as_posix() != relative_path
        or not parts
        or any(part in {"", ".", ".."} for part in parts)
    ):
        _fail(
            "SOURCE_CHANGED_DURING_SYNCHRONIZATION",
            "Verified annotation path is no longer a safe bundle-local file",
            record_field=record_field,
            remediation="Restart from M1 integrity inspection with a local regular file.",
        )
    return parts


def _resolve_verified_file(
    loaded: LoadedManifest,
    relative_path: str,
    record_field: AnnotationRecordField,
) -> Path:
    parts = _validate_relative_path(relative_path, record_field)
    try:
        root = loaded.bundle_root.resolve(strict=True)
        candidate = root.joinpath(*parts)
        current = root
        for part in parts:
            current = current / part
            metadata = current.lstat()
            attributes = getattr(metadata, "st_file_attributes", 0)
            if stat.S_ISLNK(metadata.st_mode) or attributes & _REPARSE_POINT:
                _fail(
                    "SOURCE_CHANGED_DURING_SYNCHRONIZATION",
                    "Verified annotation path now contains a link or reparse point",
                    record_field=record_field,
                    remediation="Replace links with bundle-local regular files and restart M1.",
                )
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(root) or not resolved.is_file():
            _fail(
                "SOURCE_CHANGED_DURING_SYNCHRONIZATION",
                "Verified annotation path no longer resolves to a regular bundle file",
                record_field=record_field,
                remediation="Restore the verified regular file and restart from M1.",
            )
    except AnnotationAlignmentError:
        raise
    except OSError:
        _fail(
            "SOURCE_CHANGED_DURING_SYNCHRONIZATION",
            "Verified annotation file is missing or inaccessible",
            record_field=record_field,
            remediation="Restore file access and restart from M1 integrity inspection.",
        )
    return resolved


def _read_bounded(
    path: Path,
    *,
    record_field: AnnotationRecordField,
    max_bytes: int,
) -> bytes:
    try:
        with path.open("rb") as source:
            payload = source.read(max_bytes + 1)
    except OSError:
        _fail(
            "SOURCE_CHANGED_DURING_SYNCHRONIZATION",
            "Verified annotation file could not be read",
            record_field=record_field,
            remediation="Restore file access and restart from M1 integrity inspection.",
        )
    if len(payload) > max_bytes:
        _fail(
            "ANNOTATION_SEMANTICS_INVALID",
            "Annotation file exceeds the approved bounded reader limit",
            record_field=record_field,
            remediation="Reduce the annotation file below the approved byte limit.",
            diagnostics={"limit_name": "max_bytes", "limit": max_bytes},
        )
    return payload


def _reject_duplicate_pairs(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKeyError
        result[key] = value
    return result


def _reject_nonstandard_constant(_value: str) -> NoReturn:
    raise _NonStandardJsonConstantError


def _parse_annotation_payload(
    payload: bytes,
    *,
    record_field: AnnotationRecordField,
) -> dict[str, JsonValue]:
    try:
        text = payload.decode("utf-8", errors="strict")
        parsed = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonstandard_constant,
        )
    except (ValueError, RecursionError):
        _fail(
            "ANNOTATION_SEMANTICS_INVALID",
            "Annotation file is not strict bounded UTF-8 JSON",
            record_field=record_field,
            remediation="Export strict UTF-8 JSON without duplicate keys or non-finite values.",
        )
    if not isinstance(parsed, dict):
        _fail(
            "ANNOTATION_SEMANTICS_INVALID",
            "Annotation document must be a JSON object",
            record_field=record_field,
            remediation="Export the registered annotation object shape.",
        )
    records = parsed.get(record_field)
    if not isinstance(records, list):
        _fail(
            "ANNOTATION_SEMANTICS_INVALID",
            "Annotation record field must be a JSON array",
            record_field=record_field,
            remediation="Export the registered annotation array field.",
        )
    return cast(dict[str, JsonValue], parsed)


def read_verified_annotation(
    loaded: LoadedManifest,
    relative_path: str,
    *,
    record_field: AnnotationRecordField,
    limits: AnnotationReadLimits = AnnotationReadLimits(),  # noqa: B008
) -> dict[str, JsonValue]:
    """Read one M1-verified annotation through a bounded single file handle.

    M1 does not retain secured file handles. This function therefore detects
    bounded snapshot changes by path identity and digest; it does not claim to
    make a mutable external directory race-free.
    """

    _require_valid_limits(limits, record_field)
    expected_digest = loaded.verified_digests.get(relative_path)
    if expected_digest is None:
        _fail(
            "SOURCE_CHANGED_DURING_SYNCHRONIZATION",
            "Annotation path has no verified M1 digest",
            record_field=record_field,
            remediation="Restart from M1 so the annotation path and digest are verified.",
        )
    path = _resolve_verified_file(loaded, relative_path, record_field)
    payload = _read_bounded(
        path,
        record_field=record_field,
        max_bytes=limits.max_bytes,
    )
    if hashlib.sha256(payload).hexdigest() != expected_digest:
        _fail(
            "SOURCE_CHANGED_DURING_SYNCHRONIZATION",
            "Annotation bytes differ from the verified M1 snapshot",
            record_field=record_field,
            remediation="Stop synchronization and restart from M1 integrity inspection.",
        )
    parsed = _parse_annotation_payload(payload, record_field=record_field)
    records = cast(list[JsonValue], parsed[record_field])
    if len(records) > limits.max_records:
        _fail(
            "ANNOTATION_SEMANTICS_INVALID",
            "Annotation array exceeds the approved record-count limit",
            record_field=record_field,
            remediation="Split or reduce annotations below the approved record limit.",
            diagnostics={"limit_name": "max_records", "limit": limits.max_records},
        )
    return parsed


class _SyntheticAnnotationBase(StrictContractModel):
    generator_id: StableId
    seed: NonNegativeInt
    synthetic_semantics_unvalidated: StrictBool

    @model_validator(mode="after")
    def require_unvalidated_provenance(self) -> Self:
        if self.synthetic_semantics_unvalidated is not True:
            raise ValueError("synthetic annotation provenance must remain unvalidated")
        return self


class _SyntheticPhaseRecord(StrictContractModel):
    phase_id: StableId
    start_s: FiniteFloat
    end_s: FiniteFloat


class _SyntheticEventRecord(StrictContractModel):
    event_id: StableId
    event_type: StableId
    time_s: FiniteFloat


class _SyntheticBaselineRecord(StrictContractModel):
    interval_id: StableId
    start_s: FiniteFloat
    end_s: FiniteFloat


class _SyntheticPhases(_SyntheticAnnotationBase):
    schema_id: Literal["phases-synthetic-v0.1"]
    phases: list[_SyntheticPhaseRecord]


class _SyntheticEvents(_SyntheticAnnotationBase):
    schema_id: Literal["events-synthetic-v0.1"]
    events: list[_SyntheticEventRecord]


class _SyntheticBaselines(_SyntheticAnnotationBase):
    schema_id: Literal["baseline-intervals-synthetic-v0.1"]
    baseline_intervals: list[_SyntheticBaselineRecord]


class _SessionTimebase(StrictContractModel):
    origin: Literal["session_start"]
    unit: Literal["ns"]


class _CanonicalAnnotationBase(StrictContractModel):
    annotation_revision: StableId
    timebase: _SessionTimebase
    annotation_source: StableId


class _CanonicalPhaseRecord(StrictContractModel):
    phase_id: StableId
    label: _NON_EMPTY_TEXT
    start_t_ns: NonNegativeInt64
    end_t_ns: NonNegativeInt64
    source: StableId
    confidence: UnitInterval


class _CanonicalEventRecord(StrictContractModel):
    event_id: StableId
    event_type: StableId
    t_ns: NonNegativeInt64
    source: StableId
    confidence: UnitInterval
    duration_ns: NonNegativeInt64 | None = None
    response_mapping: dict[str, JsonValue] | None = None


class _CanonicalBaselineRecord(StrictContractModel):
    interval_id: StableId
    start_t_ns: NonNegativeInt64
    end_t_ns: NonNegativeInt64
    condition: StableId
    valid: StrictBool
    exclusion_reason: _NON_EMPTY_TEXT | None = None


class _CanonicalPhases(_CanonicalAnnotationBase):
    schema_id: Literal["phases-session-time-v0.1"]
    phases: list[_CanonicalPhaseRecord]


class _CanonicalEvents(_CanonicalAnnotationBase):
    schema_id: Literal["events-session-time-v0.1"]
    events: list[_CanonicalEventRecord]


class _CanonicalBaselines(_CanonicalAnnotationBase):
    schema_id: Literal["baseline-intervals-session-time-v0.1"]
    baseline_intervals: list[_CanonicalBaselineRecord]


_AnnotationDocument = (
    _SyntheticPhases
    | _SyntheticEvents
    | _SyntheticBaselines
    | _CanonicalPhases
    | _CanonicalEvents
    | _CanonicalBaselines
)
_REGISTRY: dict[
    str,
    tuple[AnnotationRecordField, type[StrictContractModel]],
] = {
    "phases-synthetic-v0.1": ("phases", _SyntheticPhases),
    "events-synthetic-v0.1": ("events", _SyntheticEvents),
    "baseline-intervals-synthetic-v0.1": (
        "baseline_intervals",
        _SyntheticBaselines,
    ),
    "phases-session-time-v0.1": ("phases", _CanonicalPhases),
    "events-session-time-v0.1": ("events", _CanonicalEvents),
    "baseline-intervals-session-time-v0.1": (
        "baseline_intervals",
        _CanonicalBaselines,
    ),
}


def _validate_registered_document(
    payload: dict[str, JsonValue],
    record_field: AnnotationRecordField,
) -> _AnnotationDocument:
    schema_id = payload.get("schema_id")
    if not isinstance(schema_id, str):
        _fail(
            "ANNOTATION_SEMANTICS_INVALID",
            "Annotation schema_id must be a string",
            record_field=record_field,
            remediation="Declare one exact registered annotation schema ID.",
        )
    registration = _REGISTRY.get(schema_id)
    if registration is None:
        _fail(
            "ANNOTATION_SCHEMA_UNSUPPORTED",
            "Annotation schema_id is not registered for M3 v0.1",
            record_field=record_field,
            remediation="Export one of the six registered M3 annotation schemas.",
        )
    expected_field, model_type = registration
    if expected_field != record_field:
        _fail(
            "ANNOTATION_SEMANTICS_INVALID",
            "Annotation schema does not match its manifest annotation role",
            record_field=record_field,
            remediation="Place each registered schema in its matching annotation role.",
        )
    try:
        return cast(_AnnotationDocument, model_type.model_validate(payload))
    except ValidationError:
        _fail(
            "ANNOTATION_SEMANTICS_INVALID",
            "Annotation document does not match its registered strict schema",
            record_field=record_field,
            remediation="Correct required fields, strict scalar types, and extra fields.",
        )


def _convert_phases(
    document: _SyntheticPhases | _CanonicalPhases,
    *,
    expected_phases: tuple[str, ...],
    window: SessionWindow,
) -> tuple[tuple[PhaseInterval, ...], tuple[SessionInterval, ...]]:
    phases: list[PhaseInterval] = []
    if isinstance(document, _SyntheticPhases):
        for item in document.phases:
            phases.append(
                PhaseInterval(
                    phase_id=item.phase_id,
                    start_t_ns=session_seconds_to_ns(item.start_s),
                    end_t_ns=session_seconds_to_ns(item.end_s),
                )
            )
    else:
        for item in document.phases:
            phases.append(
                PhaseInterval(
                    phase_id=item.phase_id,
                    label=item.label,
                    start_t_ns=item.start_t_ns,
                    end_t_ns=item.end_t_ns,
                    source=item.source,
                    confidence=item.confidence,
                )
            )

    phase_ids = tuple(phase.phase_id for phase in phases)
    if len(phase_ids) != len(set(phase_ids)) or phase_ids != expected_phases:
        raise ValueError("phase inventory does not exactly match manifest order")

    previous_end = window.start_t_ns
    for phase in phases:
        if (
            phase.start_t_ns < window.start_t_ns
            or phase.end_t_ns > window.end_t_ns
            or phase.start_t_ns < previous_end
        ):
            raise ValueError("phase intervals must be ordered, non-overlapping, and in session")
        previous_end = phase.end_t_ns

    gaps: list[SessionInterval] = []
    cursor = window.start_t_ns
    for phase in phases:
        if cursor < phase.start_t_ns:
            gaps.append(SessionInterval(start_t_ns=cursor, end_t_ns=phase.start_t_ns))
        cursor = phase.end_t_ns
    if cursor < window.end_t_ns:
        gaps.append(SessionInterval(start_t_ns=cursor, end_t_ns=window.end_t_ns))
    return tuple(phases), tuple(gaps)


def _convert_events(
    document: _SyntheticEvents | _CanonicalEvents,
    *,
    window: SessionWindow,
) -> tuple[EventMarker, ...]:
    events: list[EventMarker] = []
    if isinstance(document, _SyntheticEvents):
        for item in document.events:
            events.append(
                EventMarker(
                    event_id=item.event_id,
                    event_type=item.event_type,
                    t_ns=session_seconds_to_ns(item.time_s),
                )
            )
    else:
        for item in document.events:
            events.append(
                EventMarker(
                    event_id=item.event_id,
                    event_type=item.event_type,
                    t_ns=item.t_ns,
                    duration_ns=item.duration_ns,
                    source=item.source,
                    confidence=item.confidence,
                    response_mapping=item.response_mapping,
                )
            )

    event_ids = tuple(event.event_id for event in events)
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("event IDs must be unique")
    for event in events:
        if event.duration_ns is None:
            if not window.start_t_ns <= event.t_ns <= window.end_t_ns:
                raise ValueError("point event must be in the closed session window")
            continue
        event_end = event.t_ns + event.duration_ns
        if event_end > INT64_MAX:
            raise ValueError("duration event end exceeds signed int64")
        if event.t_ns > window.end_t_ns or event_end < window.start_t_ns:
            raise ValueError("duration event must intersect the session window")
    return tuple(events)


def _convert_baselines(
    document: _SyntheticBaselines | _CanonicalBaselines,
    *,
    window: SessionWindow,
) -> tuple[BaselineInterval, ...]:
    baselines: list[BaselineInterval] = []
    if isinstance(document, _SyntheticBaselines):
        for item in document.baseline_intervals:
            baselines.append(
                BaselineInterval(
                    interval_id=item.interval_id,
                    start_t_ns=session_seconds_to_ns(item.start_s),
                    end_t_ns=session_seconds_to_ns(item.end_s),
                )
            )
    else:
        for item in document.baseline_intervals:
            baselines.append(
                BaselineInterval(
                    interval_id=item.interval_id,
                    start_t_ns=item.start_t_ns,
                    end_t_ns=item.end_t_ns,
                    condition=item.condition,
                    valid=item.valid,
                    exclusion_reason=item.exclusion_reason,
                )
            )

    interval_ids = tuple(interval.interval_id for interval in baselines)
    if len(interval_ids) != len(set(interval_ids)):
        raise ValueError("baseline interval IDs must be unique")
    for interval in baselines:
        if interval.start_t_ns < window.start_t_ns or interval.end_t_ns > window.end_t_ns:
            raise ValueError("baseline intervals must be fully in session")
    return tuple(baselines)


def _validate_cross_document_provenance(
    documents: tuple[_AnnotationDocument, ...],
    *,
    manifest_revision: str,
) -> bool:
    synthetic_identity: tuple[str, int] | None = None
    any_synthetic = False
    for document in documents:
        if isinstance(document, _SyntheticAnnotationBase):
            any_synthetic = True
            identity = (document.generator_id, document.seed)
            if synthetic_identity is None:
                synthetic_identity = identity
            elif synthetic_identity != identity:
                raise ValueError("synthetic annotation provenance must be consistent")
        elif document.annotation_revision != manifest_revision:
            raise ValueError("canonical annotation revision must match the manifest")
    return any_synthetic


def align_annotations(
    sync_input: SynchronizationInput,
    window: SessionWindow,
    *,
    limits: AnnotationReadLimits = AnnotationReadLimits(),  # noqa: B008
) -> tuple[AlignedAnnotations, AnnotationSynchronizationResult]:
    """Validate and align the six registered annotation schemas to session ns."""

    loaded = sync_input.loaded_manifest
    manifest_annotations = loaded.manifest.annotations
    paths: dict[AnnotationRecordField, str] = {
        "phases": manifest_annotations.phases,
        "events": manifest_annotations.events,
        "baseline_intervals": manifest_annotations.baseline_intervals,
    }
    try:
        documents = {
            record_field: _validate_registered_document(
                read_verified_annotation(
                    loaded,
                    relative_path,
                    record_field=record_field,
                    limits=limits,
                ),
                record_field,
            )
            for record_field, relative_path in paths.items()
        }
        phase_document = documents["phases"]
        event_document = documents["events"]
        baseline_document = documents["baseline_intervals"]
        if not isinstance(phase_document, (_SyntheticPhases, _CanonicalPhases)):
            raise ValueError("phase schema registry returned the wrong document type")
        if not isinstance(event_document, (_SyntheticEvents, _CanonicalEvents)):
            raise ValueError("event schema registry returned the wrong document type")
        if not isinstance(baseline_document, (_SyntheticBaselines, _CanonicalBaselines)):
            raise ValueError("baseline schema registry returned the wrong document type")

        synthetic_unvalidated = _validate_cross_document_provenance(
            tuple(documents.values()),
            manifest_revision=manifest_annotations.revision,
        )
        phases, gaps = _convert_phases(
            phase_document,
            expected_phases=tuple(loaded.manifest.task.expected_phases),
            window=window,
        )
        events = _convert_events(event_document, window=window)
        baselines = _convert_baselines(baseline_document, window=window)
    except AnnotationAlignmentError:
        raise
    except (ValidationError, ValueError, TypeError, OverflowError):
        _fail(
            "ANNOTATION_SEMANTICS_INVALID",
            "Annotations violate the registered session-time self-consistency contract",
            record_field="phases",
            remediation="Correct schema, provenance, IDs, ordering, intervals, and window bounds.",
        )

    source_schema_ids: dict[str, str] = {
        record_field: document.schema_id for record_field, document in documents.items()
    }
    aligned = AlignedAnnotations(
        revision=manifest_annotations.revision,
        phases=phases,
        events=events,
        baseline_intervals=baselines,
        source_schema_ids=source_schema_ids,
        synthetic_semantics_unvalidated=synthetic_unvalidated,
    )
    result = AnnotationSynchronizationResult(
        synchronization_status=SynchronizationItemStatus.ALIGNED,
        revision=manifest_annotations.revision,
        phase_schema_id=phase_document.schema_id,
        event_schema_id=event_document.schema_id,
        baseline_schema_id=baseline_document.schema_id,
        phase_count=len(phases),
        event_count=len(events),
        baseline_count=len(baselines),
        unannotated_intervals=gaps,
        synthetic_semantics_unvalidated=synthetic_unvalidated,
        issues=(),
    )
    return aligned, result


__all__ = [
    "AnnotationAlignmentError",
    "AnnotationReadLimits",
    "align_annotations",
    "read_verified_annotation",
]
