"""Internal, in-process stream containers used by ingestion adapters.

These types deliberately keep Polars objects behind the ingestion boundary.
The dataclasses freeze the artifact inventory and mappings; downstream stages
must treat the contained DataFrames as read-only values.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

import polars as pl
from pydantic import JsonValue


def _freeze_tables(values: Mapping[str, pl.DataFrame]) -> Mapping[str, pl.DataFrame]:
    return MappingProxyType(dict(values))


def _freeze_json_artifacts(
    values: Mapping[str, Mapping[str, JsonValue]],
) -> Mapping[str, Mapping[str, JsonValue]]:
    return MappingProxyType(
        {role: MappingProxyType(dict(payload)) for role, payload in values.items()}
    )


def _freeze_file_artifacts(
    values: Mapping[str, tuple[str, ...]],
) -> Mapping[str, tuple[str, ...]]:
    return MappingProxyType({role: tuple(paths) for role, paths in values.items()})


def _freeze_string_mapping(values: Mapping[str, str]) -> Mapping[str, str]:
    return MappingProxyType(dict(values))


def _validate_artifact_roles(
    tables: Mapping[str, pl.DataFrame],
    json_artifacts: Mapping[str, Mapping[str, JsonValue]],
    file_artifacts: Mapping[str, tuple[str, ...]],
) -> None:
    role_groups = (set(tables), set(json_artifacts), set(file_artifacts))
    overlaps = (
        (role_groups[0] & role_groups[1])
        | (role_groups[0] & role_groups[2])
        | (role_groups[1] & role_groups[2])
    )
    if overlaps:
        raise ValueError(
            f"artifact roles must identify exactly one representation: {sorted(overlaps)}"
        )
    if any(not role for roles in role_groups for role in roles):
        raise ValueError("artifact roles must be non-empty")


def _validate_source_identity(
    source_paths: tuple[str, ...], source_checksums: Mapping[str, str]
) -> None:
    folded = [path.casefold() for path in source_paths]
    if len(folded) != len(set(folded)):
        raise ValueError("source paths must be unique under Windows case folding")
    if set(source_paths) != set(source_checksums):
        raise ValueError("source checksum keys must match source paths exactly")


@dataclass(frozen=True, slots=True)
class RawStream:
    """A validated physical stream before canonical column normalization."""

    modality: str
    schema_id: str
    clock_id: str
    tables: Mapping[str, pl.DataFrame]
    json_artifacts: Mapping[str, Mapping[str, JsonValue]]
    file_artifacts: Mapping[str, tuple[str, ...]]
    source_paths: tuple[str, ...]
    source_checksums: Mapping[str, str]

    def __post_init__(self) -> None:
        _validate_artifact_roles(self.tables, self.json_artifacts, self.file_artifacts)
        _validate_source_identity(self.source_paths, self.source_checksums)
        object.__setattr__(self, "tables", _freeze_tables(self.tables))
        object.__setattr__(self, "json_artifacts", _freeze_json_artifacts(self.json_artifacts))
        object.__setattr__(self, "file_artifacts", _freeze_file_artifacts(self.file_artifacts))
        object.__setattr__(self, "source_paths", tuple(self.source_paths))
        object.__setattr__(self, "source_checksums", _freeze_string_mapping(self.source_checksums))


@dataclass(frozen=True, slots=True)
class NormalizedStream:
    """One logical stream with all of its normalized artifact roles."""

    modality: str
    schema_id: str
    clock_id: str
    source_timestamp_column: str
    primary_table_role: str
    tables: Mapping[str, pl.DataFrame]
    json_artifacts: Mapping[str, Mapping[str, JsonValue]]
    file_artifacts: Mapping[str, tuple[str, ...]]
    source_paths: tuple[str, ...]
    source_checksums: Mapping[str, str]

    def __post_init__(self) -> None:
        if self.primary_table_role not in self.tables:
            raise ValueError("primary_table_role must identify a table artifact")
        if not self.source_timestamp_column:
            raise ValueError("source_timestamp_column must be non-empty")
        _validate_artifact_roles(self.tables, self.json_artifacts, self.file_artifacts)
        _validate_source_identity(self.source_paths, self.source_checksums)
        object.__setattr__(self, "tables", _freeze_tables(self.tables))
        object.__setattr__(self, "json_artifacts", _freeze_json_artifacts(self.json_artifacts))
        object.__setattr__(self, "file_artifacts", _freeze_file_artifacts(self.file_artifacts))
        object.__setattr__(self, "source_paths", tuple(self.source_paths))
        object.__setattr__(self, "source_checksums", _freeze_string_mapping(self.source_checksums))

    @property
    def primary_table(self) -> pl.DataFrame:
        """Return the profile-declared primary table without copying it."""

        return self.tables[self.primary_table_role]


@dataclass(frozen=True, slots=True)
class PreparedSession:
    """Adapter output ready for M3 synchronization, but not yet aligned."""

    streams: Mapping[str, NormalizedStream]
    context: Mapping[str, JsonValue]
    task_reference: NormalizedStream | None

    def __post_init__(self) -> None:
        mismatched = [
            stream_id for stream_id, stream in self.streams.items() if stream_id != stream.modality
        ]
        if mismatched:
            raise ValueError(f"prepared stream keys must match modality: {sorted(mismatched)}")
        if "task_reference" in self.streams:
            raise ValueError("task_reference must use the dedicated task_reference field")
        if self.task_reference is not None and self.task_reference.modality != "task_reference":
            raise ValueError("task_reference must have modality 'task_reference'")
        object.__setattr__(self, "streams", MappingProxyType(dict(self.streams)))
        object.__setattr__(self, "context", MappingProxyType(dict(self.context)))


__all__ = ["NormalizedStream", "PreparedSession", "RawStream"]
