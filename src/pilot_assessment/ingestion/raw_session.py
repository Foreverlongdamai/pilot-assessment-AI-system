"""Read-only simulator export inspection and canonical bundle materialization."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Final, Literal, NoReturn, cast

from pydantic import JsonValue

from pilot_assessment.contracts.errors import DomainErrorData, ErrorSeverity
from pilot_assessment.contracts.ingestion import IngestionReadinessReport
from pilot_assessment.contracts.session import (
    AnnotationReferences,
    ClockSync,
    IntegrityDefinition,
    Participant,
    PrivacyDefinition,
    SessionManifest,
    SessionTimebase,
    SourceSession,
    StreamDescriptor,
    StreamStatus,
    TaskDefinition,
)
from pilot_assessment.contracts.session_source import (
    RawAnnotationMapping,
    RawFieldMapping,
    RawModalityProposal,
    RawSessionInspection,
    RawSourceFile,
    SessionDataSourceKind,
    SessionSourceInspection,
    UnitProvenance,
)
from pilot_assessment.ingestion.manifest_loader import LoadedManifest, ManifestLoader
from pilot_assessment.ingestion.profiles import (
    CompositeProfile,
    CsvColumnRole,
    CsvProfile,
    ExactPathsMatcher,
    PathPrefixMatcher,
    TableProfile,
    load_builtin_profiles,
)
from pilot_assessment.ingestion.readiness import (
    inspect_ingestion_readiness,
    inspect_loaded_ingestion_readiness,
)
from pilot_assessment.model_library.identity import typed_content_sha256

_CSV_PROFILE_ID: Final = "cranfield-simulator-combined-csv-raw-v0.1"
_CANONICAL_ANNOTATION_ROOT: Final = "_pilot_assessment/annotations"
_CHECKSUM_PATH: Final = "_pilot_assessment/integrity/checksums.sha256"
_COPY_CHUNK_SIZE: Final = 1024 * 1024
_MAX_SOURCE_FILES: Final = 10_000
_MAX_CSV_HEADER_BYTES: Final = 1024 * 1024

AnnotationField = Literal["phases", "events", "baseline_intervals"]

_ANNOTATION_DEFINITIONS: Final[tuple[tuple[AnnotationField, str, str], ...]] = (
    (
        "phases",
        "phases-session-time-v0.1",
        f"{_CANONICAL_ANNOTATION_ROOT}/phases.json",
    ),
    (
        "events",
        "events-session-time-v0.1",
        f"{_CANONICAL_ANNOTATION_ROOT}/events.json",
    ),
    (
        "baseline_intervals",
        "baseline-intervals-session-time-v0.1",
        f"{_CANONICAL_ANNOTATION_ROOT}/baseline_intervals.json",
    ),
)

_OPTIONAL_PROFILES: Final[Mapping[str, str]] = {
    "I": "vr-scene-source-bundle-v0.1",
    "G": "gaze-source-bundle-v0.1",
    "EEG": "eeg-source-bundle-v0.1",
    "ECG": "ecg-source-bundle-v0.1",
    "pilot_camera": "pilot-camera-source-bundle-v0.1",
}

_CLOCK_IDS: Final[Mapping[str, str]] = {
    "X": "simulator-clock",
    "U": "simulator-clock",
    "I": "vr-scene-clock",
    "G": "gaze-clock",
    "EEG": "eeg-clock",
    "ECG": "ecg-clock",
    "pilot_camera": "pilot-camera-clock",
}


class RawSessionError(Exception):
    """Stable domain-safe failure raised before a raw source enters persistence."""

    def __init__(self, error: DomainErrorData) -> None:
        self.error = error
        super().__init__(error.message)


@dataclass(frozen=True, slots=True)
class RawMaterializationResult:
    inspection: RawSessionInspection
    manifest: SessionManifest
    loaded: LoadedManifest
    readiness: IngestionReadinessReport


def detect_session_source(source_root: str | Path) -> SessionDataSourceKind:
    """Identify a canonical bundle or the explicit simulator raw directory shape."""

    root = _secure_root(source_root)
    manifest_path = root / "manifest.json"
    if manifest_path.exists() or _is_link_or_junction(manifest_path):
        return SessionDataSourceKind.CANONICAL_BUNDLE

    reserved = root / "_pilot_assessment"
    if reserved.exists() or _is_link_or_junction(reserved):
        _fail(
            "RAW_RESERVED_PATH_COLLISION",
            "Raw session source uses the reserved _pilot_assessment namespace",
            field_or_path="_pilot_assessment",
            remediation="Rename or remove the conflicting raw-source entry before import.",
        )

    streams = root / "streams"
    annotations = root / "annotations"
    if _regular_directory(streams) and _regular_directory(annotations):
        return SessionDataSourceKind.SIMULATOR_RAW
    _fail(
        "SESSION_SOURCE_UNRECOGNIZED",
        "Selected folder is neither a canonical Session Bundle nor a simulator raw export",
        field_or_path=str(root),
        remediation="Select a bundle with manifest.json or a folder with streams and annotations.",
    )


def inspect_session_source(source_root: str | Path) -> SessionSourceInspection:
    """Inspect one external source without writing to it or to managed storage."""

    kind = detect_session_source(source_root)
    if kind is SessionDataSourceKind.CANONICAL_BUNDLE:
        outcome = inspect_ingestion_readiness(source_root)
        return SessionSourceInspection(source_kind=kind, report=outcome.report)
    return SessionSourceInspection(
        source_kind=kind,
        raw=inspect_raw_session(source_root),
    )


def inspect_raw_session(source_root: str | Path) -> RawSessionInspection:
    """Probe one simulator raw export using packaged, versioned adapter profiles."""

    root = _secure_root(source_root)
    if detect_session_source(root) is not SessionDataSourceKind.SIMULATOR_RAW:
        _fail(
            "SESSION_SOURCE_UNRECOGNIZED",
            "Selected source is not a simulator raw export",
            field_or_path=str(root),
            remediation="Select a folder containing streams and annotations.",
        )
    files = _source_inventory(root)
    profile = _csv_profile()
    csv_matches = tuple(
        item
        for item in files
        if item.relative_path.startswith("streams/")
        and _matches_csv(root, item.relative_path, profile)
    )
    if not csv_matches:
        _fail(
            "RAW_PROFILE_UNSUPPORTED",
            "No simulator X/U CSV matches a registered adapter profile",
            field_or_path="streams",
            remediation=(
                "Export the simulator CSV with its original header or add an adapter profile."
            ),
        )
    if len(csv_matches) > 1:
        _fail(
            "RAW_PROFILE_AMBIGUOUS",
            "Multiple simulator X/U CSV files match the same adapter profile",
            field_or_path="streams",
            remediation="Keep one session CSV per import folder or select a narrower folder.",
            diagnostics={"matching_paths": [item.relative_path for item in csv_matches]},
        )

    csv_file = csv_matches[0]
    mappings = _field_mappings(csv_file.relative_path, profile)
    proposals = _modality_proposals(files, csv_file, profile)
    annotation_mappings, annotation_warnings = _annotation_mappings(root, files)
    fingerprint = typed_content_sha256(
        "raw-session-source-snapshot",
        "0.1.0",
        [item.model_dump(mode="json") for item in files],
    )
    return RawSessionInspection(
        source_snapshot_fingerprint=fingerprint,
        detected_profile_id=profile.schema_id,
        profile_candidates=(profile.schema_id,),
        files=files,
        field_mappings=mappings,
        modality_proposals=proposals,
        annotation_mappings=annotation_mappings,
        required_user_inputs=(),
        warnings=annotation_warnings,
        can_materialize=True,
    )


def materialize_raw_session(
    source_root: str | Path,
    target_root: str | Path,
    *,
    inspection: RawSessionInspection,
    transaction_id: str,
    created_at: datetime,
) -> RawMaterializationResult:
    """Create a canonical bundle in a new managed staging directory."""

    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("created_at must be timezone-aware")
    root = _secure_root(source_root)
    current = inspect_raw_session(root)
    if current.source_snapshot_fingerprint != inspection.source_snapshot_fingerprint:
        _fail(
            "RAW_SOURCE_CHANGED",
            "Raw session source changed after inspection",
            field_or_path=str(root),
            remediation="Inspect the source again before importing it.",
            diagnostics={
                "inspected_fingerprint": inspection.source_snapshot_fingerprint,
                "current_fingerprint": current.source_snapshot_fingerprint,
            },
        )

    target = Path(target_root).expanduser()
    try:
        target.mkdir(parents=True, exist_ok=False)
    except FileExistsError as error:
        raise ValueError("raw materialization target must not already exist") from error

    try:
        _copy_source_inventory(root, target, current.files)
        annotation_documents = _canonical_annotation_documents(root, current)
        for mapping in current.annotation_mappings:
            _write_json_exclusive(
                target,
                mapping.canonical_path,
                annotation_documents[mapping.record_field],
            )

        manifest = _build_manifest(
            current,
            transaction_id=transaction_id,
            created_at=created_at,
        )
        checksum_paths = _declared_checksum_paths(manifest)
        checksum_lines = []
        for relative_path in checksum_paths:
            digest, _size = _hash_file(target.joinpath(*PurePosixPath(relative_path).parts))
            checksum_lines.append(f"{digest}  {relative_path}\n")
        _write_bytes_exclusive(target, _CHECKSUM_PATH, "".join(checksum_lines).encode("utf-8"))
        _write_bytes_exclusive(
            target,
            "manifest.json",
            _json_bytes(manifest.model_dump(mode="json")),
        )

        loaded = ManifestLoader().load(target)
        outcome = inspect_loaded_ingestion_readiness(loaded)
    except Exception:
        # Persistence owns cleanup of its staging root. Standalone callers receive
        # the intact failed materialization for diagnosis.
        raise
    return RawMaterializationResult(
        inspection=current,
        manifest=manifest,
        loaded=loaded,
        readiness=outcome.report,
    )


def _field_mappings(relative_path: str, profile: CsvProfile) -> tuple[RawFieldMapping, ...]:
    mappings: list[RawFieldMapping] = []
    for column in profile.columns:
        undeclared = column.unit == "unknown_raw"
        if column.canonical_name == profile.source_timestamp_column:
            timestamp_role = "source_timestamp"
        elif column.role is CsvColumnRole.CONTEXT:
            timestamp_role = "context"
        elif column.role is CsvColumnRole.QUALITY_CHECK:
            timestamp_role = "quality_check"
        else:
            timestamp_role = "measurement"
        mappings.append(
            RawFieldMapping(
                source_path=relative_path,
                source_field=column.source_header,
                canonical_field=column.canonical_name,
                modality=column.role.value,
                physical_dtype="f64",
                declared_unit=None if undeclared else column.unit,
                unit_provenance=(
                    UnitProvenance.UNDECLARED if undeclared else UnitProvenance.PROFILE
                ),
                timestamp_role=timestamp_role,
            )
        )
    return tuple(mappings)


def _modality_proposals(
    files: tuple[RawSourceFile, ...],
    csv_file: RawSourceFile,
    csv_profile: CsvProfile,
) -> dict[str, RawModalityProposal]:
    catalog = load_builtin_profiles()
    proposals: dict[str, RawModalityProposal] = {}
    for modality in ("X", "U"):
        role = CsvColumnRole(modality)
        units = {
            column.canonical_name: column.unit
            for column in csv_profile.columns
            if column.role is role and column.unit != "unknown_raw"
        }
        proposals[modality] = RawModalityProposal(
            modality=modality,
            status=StreamStatus.PRESENT,
            paths=(csv_file.relative_path,),
            format=csv_profile.format,
            schema_id=csv_profile.schema_id,
            clock_id=_CLOCK_IDS[modality],
            sample_rate_hz=csv_profile.expected_sample_rate_hz,
            declared_units=units,
            unit_handling="undeclared-pass-through-v1",
        )

    file_paths = {item.relative_path for item in files}
    for modality, profile_id in _OPTIONAL_PROFILES.items():
        profile = catalog[profile_id]
        assert isinstance(profile, CompositeProfile)
        matched_paths, complete = _match_composite_paths(profile, file_paths)
        proposals[modality] = RawModalityProposal(
            modality=modality,
            status=StreamStatus.PRESENT if complete else StreamStatus.MISSING,
            paths=matched_paths if complete else (),
            format=profile.format,
            schema_id=profile.schema_id,
            clock_id=_CLOCK_IDS[modality],
            sample_rate_hz=_composite_sample_rate(profile),
            declared_units=_composite_units(profile) if complete else {},
            unit_handling="profile-declared-or-undeclared-pass-through-v1",
        )
    return proposals


def _match_composite_paths(
    profile: CompositeProfile,
    available: set[str],
) -> tuple[tuple[str, ...], bool]:
    selected: set[str] = set()
    complete = True
    for role in profile.artifact_roles.values():
        matcher = role.matcher
        if isinstance(matcher, ExactPathsMatcher):
            matches = set(matcher.paths).intersection(available)
            if role.required and matches != set(matcher.paths):
                complete = False
            selected.update(matches)
        elif isinstance(matcher, PathPrefixMatcher):
            matches = {path for path in available if path.startswith(matcher.path_prefix)}
            if role.required and not matches:
                complete = False
            selected.update(matches)
    return tuple(sorted(selected)), complete


def _composite_units(profile: CompositeProfile) -> dict[str, str]:
    catalog = load_builtin_profiles()
    units: dict[str, str] = {}
    for role in profile.artifact_roles.values():
        physical = catalog.get(role.schema_id)
        if isinstance(physical, TableProfile):
            units.update({column.name: column.unit for column in physical.columns})
    return dict(sorted(units.items()))


def _composite_sample_rate(profile: CompositeProfile) -> float | None:
    primary = load_builtin_profiles().get(profile.artifact_roles[profile.primary_role].schema_id)
    return primary.expected_sample_rate_hz if isinstance(primary, TableProfile) else None


def _annotation_mappings(
    root: Path,
    files: tuple[RawSourceFile, ...],
) -> tuple[tuple[RawAnnotationMapping, ...], tuple[DomainErrorData, ...]]:
    candidates: dict[str, tuple[str, int, str]] = {}
    warnings: list[DomainErrorData] = []
    for item in files:
        if not item.relative_path.startswith("annotations/") or not item.relative_path.endswith(
            ".json"
        ):
            continue
        payload = _read_json_object(root, item.relative_path)
        if payload is None:
            warnings.append(
                _warning(
                    "RAW_ANNOTATION_UNRECOGNIZED",
                    "Annotation file is preserved but is not a recognized canonical JSON document",
                    field_or_path=item.relative_path,
                )
            )
            continue
        schema_id = payload.get("schema_id")
        for field_name, expected_schema, _canonical_path in _ANNOTATION_DEFINITIONS:
            records = payload.get(field_name)
            if schema_id == expected_schema and isinstance(records, list):
                if field_name in candidates:
                    _fail(
                        "RAW_ANNOTATION_MAPPING_INVALID",
                        "Multiple annotation documents map to the same canonical category",
                        field_or_path=item.relative_path,
                        remediation="Keep one canonical document per annotation category.",
                    )
                candidates[field_name] = (item.relative_path, len(records), expected_schema)

    mappings = []
    for field_name, _expected_schema, canonical_path in _ANNOTATION_DEFINITIONS:
        candidate = candidates.get(field_name)
        mappings.append(
            RawAnnotationMapping(
                record_field=field_name,
                source_path=candidate[0] if candidate else None,
                canonical_path=canonical_path,
                source_schema_id=candidate[2] if candidate else None,
                record_count=candidate[1] if candidate else 0,
                disposition="normalized" if candidate else "empty",
            )
        )
    return tuple(mappings), tuple(warnings)


def _canonical_annotation_documents(
    root: Path,
    inspection: RawSessionInspection,
) -> dict[str, dict[str, JsonValue]]:
    revision = f"raw-import-{inspection.source_snapshot_fingerprint[:16]}"
    documents: dict[str, dict[str, JsonValue]] = {}
    schema_by_field = {field: schema for field, schema, _path in _ANNOTATION_DEFINITIONS}
    for mapping in inspection.annotation_mappings:
        if mapping.source_path is not None:
            source = _read_json_object(root, mapping.source_path)
            if source is None:
                _fail(
                    "RAW_SOURCE_CHANGED",
                    "Recognized annotation can no longer be parsed",
                    field_or_path=mapping.source_path,
                    remediation="Inspect the raw source again before import.",
                )
            documents[mapping.record_field] = source
            continue
        documents[mapping.record_field] = {
            "schema_id": schema_by_field[mapping.record_field],
            "annotation_revision": revision,
            "timebase": {"origin": "session_start", "unit": "ns"},
            "annotation_source": "raw-source-category-absent-v0.1",
            mapping.record_field: [],
        }
    return documents


def _build_manifest(
    inspection: RawSessionInspection,
    *,
    transaction_id: str,
    created_at: datetime,
) -> SessionManifest:
    session_digest = typed_content_sha256(
        "raw-session-identity",
        "0.1.0",
        {
            "transaction_id": transaction_id,
            "source_snapshot_fingerprint": inspection.source_snapshot_fingerprint,
        },
    )
    # Keep managed Windows paths below ordinary MAX_PATH limits while retaining
    # a 96-bit transaction/source-derived identity in the human-readable ID.
    session_id = f"raw-session-{session_digest[:24]}"
    file_digests = {item.relative_path: item.sha256 for item in inspection.files}
    shared_source_id = f"raw-csv-{inspection.source_snapshot_fingerprint[:24]}"
    streams: dict[str, StreamDescriptor] = {}
    for modality, proposal in inspection.modality_proposals.items():
        present = proposal.status is StreamStatus.PRESENT
        metadata: dict[str, JsonValue] = {
            "adapter_profile_id": proposal.schema_id,
            "unit_handling": proposal.unit_handling,
        }
        if modality in {"X", "U"}:
            metadata.update({"shared_source_id": shared_source_id, "view_id": modality})
        streams[modality] = StreamDescriptor(
            modality=modality,
            status=proposal.status,
            required_for_import=modality in {"X", "U"},
            paths=list(proposal.paths),
            format=proposal.format,
            schema_id=proposal.schema_id,
            clock_id=proposal.clock_id,
            clock_sync=(
                ClockSync(
                    method="adapter-fixed-source-time-v0.1",
                    scale=1.0,
                    offset_ns=0,
                    drift_ppm=0.0,
                    residual_rms_ms=0.0,
                    residual_max_ms=0.0,
                    extensions={"source": "versioned-adapter-profile"},
                )
                if present
                else None
            ),
            sample_rate_hz=proposal.sample_rate_hz if present else None,
            units=dict(proposal.declared_units),
            quality_summary=None,
            checksums={path: file_digests[path] for path in proposal.paths},
            metadata=metadata,
        )

    contains_biometrics = any(
        streams[modality].status is StreamStatus.PRESENT
        for modality in ("G", "EEG", "ECG", "pilot_camera")
    )
    annotation_paths = {
        mapping.record_field: mapping.canonical_path for mapping in inspection.annotation_mappings
    }
    return SessionManifest(
        bundle_schema_version="0.1.0",
        session_id=session_id,
        created_at=created_at.isoformat(),
        source_session=SourceSession(
            system="cranfield-simulator-raw-adapter",
            source_id=f"raw-source-{inspection.source_snapshot_fingerprint[:24]}",
            campaign="unclassified-simulator-session",
            extensions={"source_kind": "simulator_raw"},
        ),
        participant=Participant(
            pseudonymous_id=f"participant-{inspection.source_snapshot_fingerprint[:16]}"
        ),
        task=TaskDefinition(
            task_profile_id="unclassified-task",
            scenario_id=session_id,
            expected_phases=[],
            reference=None,
        ),
        session_timebase=SessionTimebase(
            origin="session_start",
            unit="ns",
            master_clock_id="simulator-clock",
        ),
        streams=streams,
        annotations=AnnotationReferences(
            revision=f"raw-import-{inspection.source_snapshot_fingerprint[:16]}",
            phases=annotation_paths["phases"],
            events=annotation_paths["events"],
            baseline_intervals=annotation_paths["baseline_intervals"],
        ),
        integrity=IntegrityDefinition(
            algorithm="sha256",
            manifest_canonicalization="sorted-compact-json-lf-v0.1",
            checksum_file=_CHECKSUM_PATH,
        ),
        privacy=PrivacyDefinition(
            classification="user-provided-session-data",
            direct_identifiers_removed=False,
            contains_biometric_data=contains_biometrics,
            biometric_modalities_export_pending=[],
            permitted_use="project-local-assessment",
        ),
        extensions={
            "raw_import": {
                "adapter_profile_id": inspection.detected_profile_id,
                "source_snapshot_fingerprint": inspection.source_snapshot_fingerprint,
                "source_paths": [item.relative_path for item in inspection.files],
                "unit_handling": "undeclared-pass-through-v1",
                "source_kind": "simulator_raw",
            }
        },
    )


def _declared_checksum_paths(manifest: SessionManifest) -> tuple[str, ...]:
    paths = {
        path
        for descriptor in manifest.streams.values()
        if descriptor.status is StreamStatus.PRESENT
        for path in descriptor.paths
    }
    paths.update(
        {
            manifest.annotations.phases,
            manifest.annotations.events,
            manifest.annotations.baseline_intervals,
        }
    )
    return tuple(sorted(paths))


def _csv_profile() -> CsvProfile:
    profile = load_builtin_profiles().get(_CSV_PROFILE_ID)
    if not isinstance(profile, CsvProfile):
        raise RuntimeError("packaged simulator CSV profile is missing")
    return profile


def _matches_csv(root: Path, relative_path: str, profile: CsvProfile) -> bool:
    if not relative_path.casefold().endswith(".csv"):
        return False
    path = root.joinpath(*PurePosixPath(relative_path).parts)
    try:
        with path.open("rb") as stream:
            first_line = stream.readline(_MAX_CSV_HEADER_BYTES + 1)
    except OSError:
        return False
    if len(first_line) > _MAX_CSV_HEADER_BYTES:
        return False
    try:
        decoded = first_line.decode("utf-8-sig", errors="strict")
        headers = next(csv.reader([decoded], delimiter=profile.delimiter))
    except (UnicodeDecodeError, csv.Error, StopIteration):
        return False
    normalized = {header.strip(" \t\r\n") for header in headers}
    required = {column.source_header for column in profile.columns if column.required}
    return required.issubset(normalized)


def _source_inventory(root: Path) -> tuple[RawSourceFile, ...]:
    paths = tuple(_walk_regular_files(root / "streams", root)) + tuple(
        _walk_regular_files(root / "annotations", root)
    )
    if len(paths) > _MAX_SOURCE_FILES:
        _fail(
            "RAW_SOURCE_LIMIT_EXCEEDED",
            "Raw session source contains too many files",
            field_or_path=str(root),
            remediation="Split the export into individual session folders.",
        )
    records = []
    for path in paths:
        digest, size = _hash_file(path)
        records.append(
            RawSourceFile(
                relative_path=path.relative_to(root).as_posix(),
                byte_size=size,
                sha256=digest,
            )
        )
    return tuple(sorted(records, key=lambda item: item.relative_path))


def _walk_regular_files(directory: Path, root: Path) -> Iterator[Path]:
    if not _regular_directory(directory):
        _fail(
            "SESSION_SOURCE_UNRECOGNIZED",
            "Raw session source requires regular streams and annotations directories",
            field_or_path=directory.relative_to(root).as_posix(),
            remediation="Restore the raw export directory structure without links.",
        )
    with os.scandir(directory) as scanner:
        entries = sorted(scanner, key=lambda entry: entry.name)
    for entry in entries:
        path = Path(entry.path)
        if entry.is_symlink() or _is_link_or_junction(path):
            _fail(
                "RAW_SOURCE_PATH_INVALID",
                "Raw session source contains a link, junction, or reparse point",
                field_or_path=path.relative_to(root).as_posix(),
                remediation="Replace links with regular files and directories.",
            )
        if entry.is_dir(follow_symlinks=False):
            yield from _walk_regular_files(path, root)
        elif entry.is_file(follow_symlinks=False):
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(root):
                _fail(
                    "RAW_SOURCE_PATH_INVALID",
                    "Raw session file resolves outside its source root",
                    field_or_path=path.relative_to(root).as_posix(),
                    remediation="Keep every raw session file inside the selected folder.",
                )
            yield path
        else:
            _fail(
                "RAW_SOURCE_PATH_INVALID",
                "Raw session source contains a non-regular entry",
                field_or_path=path.relative_to(root).as_posix(),
                remediation="Use only regular files and directories.",
            )


def _copy_source_inventory(
    root: Path,
    target: Path,
    inventory: tuple[RawSourceFile, ...],
) -> None:
    for record in inventory:
        source = root.joinpath(*PurePosixPath(record.relative_path).parts)
        if _is_link_or_junction(source) or not source.is_file():
            _fail(
                "RAW_SOURCE_CHANGED",
                "Raw source file changed to a link or non-file during import",
                field_or_path=record.relative_path,
                remediation="Inspect the raw source again before import.",
            )
        destination = target.joinpath(*PurePosixPath(record.relative_path).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        with source.open("rb") as input_stream, destination.open("xb") as output_stream:
            while chunk := input_stream.read(_COPY_CHUNK_SIZE):
                digest.update(chunk)
                size += len(chunk)
                output_stream.write(chunk)
            output_stream.flush()
            os.fsync(output_stream.fileno())
        if digest.hexdigest() != record.sha256 or size != record.byte_size:
            _fail(
                "RAW_SOURCE_CHANGED",
                "Raw source file changed while it was copied",
                field_or_path=record.relative_path,
                remediation="Inspect the raw source again before import.",
            )


def _read_json_object(root: Path, relative_path: str) -> dict[str, JsonValue] | None:
    path = root.joinpath(*PurePosixPath(relative_path).parts)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return cast(dict[str, JsonValue], raw) if isinstance(raw, dict) else None


def _write_json_exclusive(target: Path, relative_path: str, payload: object) -> None:
    _write_bytes_exclusive(target, relative_path, _json_bytes(payload))


def _json_bytes(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _write_bytes_exclusive(target: Path, relative_path: str, payload: bytes) -> None:
    path = target.joinpath(*PurePosixPath(relative_path).parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(_COPY_CHUNK_SIZE):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _secure_root(value: str | Path) -> Path:
    candidate = Path(value).expanduser()
    if _is_link_or_junction(candidate):
        _fail(
            "RAW_SOURCE_PATH_INVALID",
            "Session source root cannot be a link or junction",
            field_or_path=str(candidate),
            remediation="Select the real source directory.",
        )
    try:
        root = candidate.resolve(strict=True)
    except OSError:
        _fail(
            "SESSION_SOURCE_UNRECOGNIZED",
            "Session source root does not exist",
            field_or_path=str(candidate),
            remediation="Select an existing session data directory.",
        )
    if not root.is_dir():
        _fail(
            "SESSION_SOURCE_UNRECOGNIZED",
            "Session source root must be a directory",
            field_or_path=str(root),
            remediation="Select a directory rather than an individual file.",
        )
    return root


def _regular_directory(path: Path) -> bool:
    return path.is_dir() and not _is_link_or_junction(path)


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction is not None and is_junction())


def _warning(code: str, message: str, *, field_or_path: str) -> DomainErrorData:
    return DomainErrorData(
        error_code=code,
        severity=ErrorSeverity.WARNING,
        recoverable=True,
        message=message,
        field_or_path=field_or_path,
        remediation="Review or add an annotation adapter profile if these records are required.",
    )


def _fail(
    code: str,
    message: str,
    *,
    field_or_path: str,
    remediation: str,
    diagnostics: dict[str, JsonValue] | None = None,
) -> NoReturn:
    raise RawSessionError(
        DomainErrorData(
            error_code=code,
            severity=ErrorSeverity.ERROR,
            recoverable=True,
            message=message,
            field_or_path=field_or_path,
            remediation=remediation,
            diagnostics=diagnostics or {},
        )
    )


__all__ = [
    "RawMaterializationResult",
    "RawSessionError",
    "detect_session_source",
    "inspect_raw_session",
    "inspect_session_source",
    "materialize_raw_session",
]
