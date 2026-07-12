"""Versioned temporal-binding catalog for native-rate synchronization."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from functools import lru_cache
from importlib.resources import files
from types import MappingProxyType
from typing import Annotated, Literal, NoReturn, Self

from pydantic import Field, model_validator

from pilot_assessment.contracts.common import StableId, StrictContractModel
from pilot_assessment.ingestion.profiles import (
    CompositeProfile,
    TableProfile,
    load_builtin_profiles,
)


class TemporalCatalogLoadError(ValueError):
    """Raised when the trusted temporal-binding catalog is invalid."""


class _DuplicateJsonKey(ValueError):
    pass


def _object_without_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"non-standard JSON constant: {value}")


class PointBinding(StrictContractModel):
    mode: Literal["point"]
    artifact_role: StableId
    expected_artifact_schema_id: StableId
    aligned_artifact_schema_id: StableId
    source_timestamp_column: StableId
    target_timestamp_column: Literal["t_ns"] = "t_ns"
    in_session_column: Literal["in_session"] = "in_session"
    stable_keys: tuple[StableId, ...]

    @model_validator(mode="after")
    def validate_point(self) -> Self:
        if not self.stable_keys or len(self.stable_keys) != len(set(self.stable_keys)):
            raise ValueError("point stable_keys must be non-empty and unique")
        if not self.aligned_artifact_schema_id.endswith("-aligned-v0.1"):
            raise ValueError("point aligned schema must end with -aligned-v0.1")
        return self


class IntervalBinding(StrictContractModel):
    mode: Literal["interval"]
    artifact_role: StableId
    expected_artifact_schema_id: StableId
    aligned_artifact_schema_id: StableId
    source_start_column: StableId
    source_end_column: StableId
    target_start_column: Literal["start_t_ns"] = "start_t_ns"
    target_end_column: Literal["end_t_ns"] = "end_t_ns"
    overlaps_session_column: Literal["overlaps_session"] = "overlaps_session"
    fully_in_session_column: Literal["fully_in_session"] = "fully_in_session"
    stable_keys: tuple[StableId, ...]

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        if not self.stable_keys or len(self.stable_keys) != len(set(self.stable_keys)):
            raise ValueError("interval stable_keys must be non-empty and unique")
        if not self.aligned_artifact_schema_id.endswith("-aligned-v0.1"):
            raise ValueError("interval aligned schema must end with -aligned-v0.1")
        return self


class InheritBinding(StrictContractModel):
    mode: Literal["inherit"]
    artifact_role: StableId
    expected_artifact_schema_id: StableId
    aligned_artifact_schema_id: StableId
    parent_role: StableId
    parent_key_columns: tuple[StableId, ...]
    foreign_key_columns: tuple[StableId, ...]
    target_timestamp_column: Literal["t_ns"] = "t_ns"
    in_session_column: Literal["in_session"] = "in_session"
    stable_keys: tuple[StableId, ...]

    @model_validator(mode="after")
    def validate_inherit(self) -> Self:
        if (
            not self.stable_keys
            or not self.parent_key_columns
            or len(self.parent_key_columns) != len(self.foreign_key_columns)
            or len(self.stable_keys) != len(set(self.stable_keys))
        ):
            raise ValueError("inherit keys must be non-empty, unique, and paired")
        if not self.aligned_artifact_schema_id.endswith("-aligned-v0.1"):
            raise ValueError("inherit aligned schema must end with -aligned-v0.1")
        return self


class UntimedBinding(StrictContractModel):
    mode: Literal["untimed"]
    artifact_role: StableId
    expected_artifact_schema_id: StableId


TemporalBinding = Annotated[
    PointBinding | IntervalBinding | InheritBinding | UntimedBinding,
    Field(discriminator="mode"),
]


class TemporalStreamProfile(StrictContractModel):
    stream_schema_id: StableId
    aligned_stream_schema_id: StableId
    bindings: tuple[TemporalBinding, ...]

    @model_validator(mode="after")
    def validate_profile(self) -> Self:
        roles = [binding.artifact_role for binding in self.bindings]
        if not roles or len(roles) != len(set(roles)):
            raise ValueError("stream binding roles must be non-empty and unique")
        if not self.aligned_stream_schema_id.endswith("-aligned-v0.1"):
            raise ValueError("aligned stream schema must end with -aligned-v0.1")
        return self

    @property
    def bindings_by_role(self) -> Mapping[str, TemporalBinding]:
        return MappingProxyType({binding.artifact_role: binding for binding in self.bindings})


class TemporalBindingCatalog(StrictContractModel):
    catalog_version: Literal["0.1.0"]
    streams: tuple[TemporalStreamProfile, ...]

    @model_validator(mode="after")
    def validate_catalog(self) -> Self:
        schema_ids = [profile.stream_schema_id for profile in self.streams]
        if not schema_ids or len(schema_ids) != len(set(schema_ids)):
            raise ValueError("catalog stream schema IDs must be non-empty and unique")
        return self

    @property
    def streams_by_schema(self) -> Mapping[str, TemporalStreamProfile]:
        return MappingProxyType({profile.stream_schema_id: profile for profile in self.streams})


def parse_temporal_binding_catalog(payload: str | bytes) -> TemporalBindingCatalog:
    """Parse strict UTF-8 JSON without duplicate keys or non-standard numbers."""

    try:
        text = payload.decode("utf-8", errors="strict") if isinstance(payload, bytes) else payload
        raw = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
        if not isinstance(raw, dict):
            raise ValueError("temporal binding catalog root must be an object")
        return TemporalBindingCatalog.model_validate(raw)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        _DuplicateJsonKey,
        ValueError,
    ) as error:
        if isinstance(error, TemporalCatalogLoadError):
            raise
        raise TemporalCatalogLoadError(f"invalid temporal binding catalog: {error}") from error


@lru_cache(maxsize=1)
def _builtin_payload() -> bytes:
    resource = files("pilot_assessment.synchronization.profile_data").joinpath(
        "m3-temporal-bindings-0.1.json"
    )
    return resource.read_bytes()


def _cross_validate_with_m2(catalog: TemporalBindingCatalog) -> None:
    m2 = load_builtin_profiles()
    runtime_schema_ids = {
        "flight-state-normalized-v0.1",
        "control-input-normalized-v0.1",
        "vr-scene-source-bundle-v0.1",
        "gaze-source-bundle-v0.1",
        "eeg-source-bundle-v0.1",
        "ecg-source-bundle-v0.1",
        "pilot-camera-source-bundle-v0.1",
        "task-reference-normalized-v0.1",
    }
    composite_schema_ids = {
        "vr-scene-source-bundle-v0.1",
        "gaze-source-bundle-v0.1",
        "eeg-source-bundle-v0.1",
        "ecg-source-bundle-v0.1",
        "pilot-camera-source-bundle-v0.1",
    }
    try:
        actual_schema_ids = set(catalog.streams_by_schema)
        if actual_schema_ids != runtime_schema_ids:
            missing = sorted(runtime_schema_ids - actual_schema_ids)
            extra = sorted(actual_schema_ids - runtime_schema_ids)
            raise ValueError(
                "runtime stream schema IDs must exactly match the M3 inventory "
                f"(missing={missing}, extra={extra})"
            )
        for schema_id in composite_schema_ids:
            source_profile = m2[schema_id]
            if not isinstance(source_profile, CompositeProfile):
                raise ValueError(f"M2 profile {schema_id} is not composite")
            temporal_profile = catalog.streams_by_schema[schema_id]
            actual = {
                role: binding.expected_artifact_schema_id
                for role, binding in temporal_profile.bindings_by_role.items()
            }
            expected = {
                role: artifact.schema_id for role, artifact in source_profile.artifact_roles.items()
            }
            if actual != expected:
                raise ValueError(f"M3 roles disagree with M2 profile {schema_id}")

        for schema_id in (
            "flight-state-normalized-v0.1",
            "control-input-normalized-v0.1",
        ):
            binding = catalog.streams_by_schema[schema_id].bindings_by_role["samples"]
            if binding.expected_artifact_schema_id != schema_id:
                raise ValueError(f"M3 runtime normalized schema mismatch for {schema_id}")

        task_reference = m2["task-reference-path-raw-v0.1"]
        if not isinstance(task_reference, TableProfile):
            raise ValueError("M2 task reference profile is not a table")
        reference_binding = catalog.streams_by_schema[
            "task-reference-normalized-v0.1"
        ].bindings_by_role["commanded_path"]
        if reference_binding.expected_artifact_schema_id != task_reference.schema_id:
            raise ValueError("M3 task reference binding disagrees with M2")
    except (KeyError, ValueError) as error:
        raise TemporalCatalogLoadError(
            f"invalid packaged temporal binding catalog: {error}"
        ) from error


@lru_cache(maxsize=1)
def _builtin_catalog() -> TemporalBindingCatalog:
    catalog = parse_temporal_binding_catalog(_builtin_payload())
    _cross_validate_with_m2(catalog)
    return catalog


def load_builtin_temporal_catalog() -> TemporalBindingCatalog:
    """Return the cross-validated, immutable built-in temporal catalog."""

    return _builtin_catalog()


def builtin_temporal_catalog_fingerprint() -> str:
    """Return SHA-256 of the exact bytes packaged as the built-in catalog."""

    return hashlib.sha256(_builtin_payload()).hexdigest()


__all__ = [
    "InheritBinding",
    "IntervalBinding",
    "PointBinding",
    "TemporalBinding",
    "TemporalBindingCatalog",
    "TemporalCatalogLoadError",
    "TemporalStreamProfile",
    "UntimedBinding",
    "builtin_temporal_catalog_fingerprint",
    "load_builtin_temporal_catalog",
    "parse_temporal_binding_catalog",
]
