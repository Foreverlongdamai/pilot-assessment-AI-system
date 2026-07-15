"""Narrow runtime protocols and immutable payload projections for M4."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Protocol, TypeVar, cast

import polars as pl
from pydantic import JsonValue, TypeAdapter

from pilot_assessment.anchors.models import ResolvedReference
from pilot_assessment.contracts.anchor_execution import (
    AnchorArtifactRecipe,
    AnchorPluginDefinition,
    PreprocessingProviderDefinition,
    ResolvedAlgorithmProfile,
    ResolvedPreprocessingRecipe,
)
from pilot_assessment.contracts.anchor_v2 import (
    AnchorArtifactRef,
    AnchorMeasurement,
    AnchorResultV2,
)
from pilot_assessment.contracts.common import Sha256Digest, StableId
from pilot_assessment.contracts.session import CORE_MODALITIES
from pilot_assessment.contracts.synchronization import SessionWindow
from pilot_assessment.synchronization.models import AlignedStreamView

_ValueT = TypeVar("_ValueT")
_ScopeKind = Literal["session", "phase", "event", "window"]
_PayloadKind = Literal["table", "blob"]
_STABLE_ID_ADAPTER = TypeAdapter(StableId)
_SHA256_ADAPTER = TypeAdapter(Sha256Digest)


def _strict_stable_id(value: object, *, label: str) -> str:
    try:
        return _STABLE_ID_ADAPTER.validate_python(value, strict=True)
    except ValueError as error:
        raise ValueError(f"{label} must be a stable ID") from error


def _strict_optional_stable_id(value: object, *, label: str) -> str | None:
    if value is None:
        return None
    return _strict_stable_id(value, label=label)


def _strict_sha256(value: object, *, label: str) -> str:
    try:
        return _SHA256_ADAPTER.validate_python(value, strict=True)
    except ValueError as error:
        raise ValueError(f"{label} must be a SHA-256 digest") from error


def _strict_optional_sha256(value: object, *, label: str) -> str | None:
    if value is None:
        return None
    return _strict_sha256(value, label=label)


def _normalized_fingerprints(
    values: tuple[Sha256Digest, ...] | list[Sha256Digest], *, label: str
) -> tuple[Sha256Digest, ...]:
    if not isinstance(values, (tuple, list)):
        raise TypeError(f"{label} must be an ordered tuple or list")
    return tuple(
        _strict_sha256(value, label=f"{label}[{index}]") for index, value in enumerate(values)
    )


def _normalized_ids(values: tuple[str, ...] | list[str], *, label: str) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list)):
        raise TypeError(f"{label} must be an ordered tuple or list")
    normalized = tuple(
        _strict_stable_id(value, label=f"{label}[{index}]") for index, value in enumerate(values)
    )
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{label} must not contain duplicate IDs")
    return normalized


def _normalized_order_keys(
    values: tuple[str, ...] | list[str],
) -> tuple[str, ...]:
    normalized = _normalized_ids(values, label="order_keys")
    if not normalized:
        raise ValueError("order_keys must be non-empty")
    return normalized


def _frozen_mapping(
    values: Mapping[str, _ValueT],
    *,
    label: str,
    value_type: type[_ValueT],
) -> Mapping[str, _ValueT]:
    if not isinstance(values, Mapping):
        raise TypeError(f"{label} must be a mapping")
    frozen: dict[str, _ValueT] = {}
    for raw_key, value in values.items():
        key = _strict_stable_id(raw_key, label=f"{label} key")
        if not isinstance(value, value_type):
            raise TypeError(f"{label}[{key}] has an invalid value type")
        frozen[key] = value
    return MappingProxyType(frozen)


def _freeze_json(value: object) -> object:
    if value is None or type(value) in {bool, int, str}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("runtime JSON numbers must be finite")
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, object] = {}
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError("runtime JSON object keys must be strings")
            frozen[key] = _freeze_json(item)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    raise TypeError("runtime JSON values must use JSON-compatible scalar or container types")


def _frozen_json_mapping(values: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
    if not isinstance(values, Mapping):
        raise TypeError("JSON projection must be a mapping")
    frozen: dict[str, JsonValue] = {}
    for key, value in values.items():
        if type(key) is not str:
            raise TypeError("runtime JSON object keys must be strings")
        frozen[key] = cast(JsonValue, _freeze_json(value))
    return MappingProxyType(frozen)


def _clone_frame(frame: pl.DataFrame) -> pl.DataFrame:
    if not isinstance(frame, pl.DataFrame):
        raise TypeError("frame must be a Polars DataFrame")
    return frame.clone()


def _clone_aligned_stream_view(view: AlignedStreamView) -> AlignedStreamView:
    if not isinstance(view, AlignedStreamView):
        raise TypeError("stream projection values must be AlignedStreamView instances")
    return AlignedStreamView(
        modality=view.modality,
        source_schema_id=view.source_schema_id,
        aligned_schema_id=view.aligned_schema_id,
        clock_id=view.clock_id,
        tables={role: frame.clone() for role, frame in view.tables.items()},
        json_artifacts={
            role: cast(
                Mapping[str, JsonValue],
                _freeze_json(payload),
            )
            for role, payload in view.json_artifacts.items()
        },
        file_artifacts={role: tuple(paths) for role, paths in view.file_artifacts.items()},
        source_checksums=dict(view.source_checksums),
    )


def _clone_stream_mapping(
    values: Mapping[str, AlignedStreamView],
) -> Mapping[str, AlignedStreamView]:
    if not isinstance(values, Mapping):
        raise TypeError("streams must be a mapping")
    cloned: dict[str, AlignedStreamView] = {}
    for raw_key, view in values.items():
        key = _strict_stable_id(raw_key, label="streams key")
        if not isinstance(view, AlignedStreamView):
            raise TypeError(f"streams[{key}] must be an AlignedStreamView")
        if key not in CORE_MODALITIES or key != view.modality:
            raise ValueError("stream key must equal its core-modality view identity")
        cloned[key] = _clone_aligned_stream_view(view)
    return MappingProxyType(cloned)


def _clone_reference_mapping(
    values: Mapping[str, ResolvedReference],
) -> Mapping[str, ResolvedReference]:
    if not isinstance(values, Mapping):
        raise TypeError("references must be a mapping")
    cloned: dict[str, ResolvedReference] = {}
    for raw_key, reference in values.items():
        key = _strict_stable_id(raw_key, label="references key")
        if not isinstance(reference, ResolvedReference):
            raise TypeError(f"references[{key}] must be a ResolvedReference")
        if key != reference.descriptor.reference_id:
            raise ValueError("reference key must equal descriptor reference_id")
        cloned[key] = ResolvedReference(
            descriptor=reference.descriptor,
            aligned_view=(
                None
                if reference.aligned_view is None
                else _clone_aligned_stream_view(reference.aligned_view)
            ),
        )
    return MappingProxyType(cloned)


def _validate_optional_bounds(start_t_ns: int | None, end_t_ns: int | None) -> None:
    if (start_t_ns is None) != (end_t_ns is None):
        raise ValueError("artifact bounds require both start_t_ns and end_t_ns")
    if start_t_ns is not None and end_t_ns is not None:
        if type(start_t_ns) is not int or type(end_t_ns) is not int:
            raise TypeError("artifact bounds must be strict integers")
        if start_t_ns < 0 or end_t_ns < start_t_ns:
            raise ValueError("artifact bounds must be an ordered non-negative range")


def _validate_scope(
    *,
    kind: str,
    scope_id: str,
    start_t_ns: int,
    end_t_ns: int,
    phase_id: str | None,
    event_id: str | None,
    window_id: str | None,
) -> None:
    if kind not in {"session", "phase", "event", "window"}:
        raise ValueError("scope kind is not supported")
    _strict_stable_id(scope_id, label="scope_id")
    _strict_optional_stable_id(phase_id, label="phase_id")
    _strict_optional_stable_id(event_id, label="event_id")
    _strict_optional_stable_id(window_id, label="window_id")
    if type(start_t_ns) is not int or type(end_t_ns) is not int:
        raise TypeError("scope bounds must be strict integers")
    if start_t_ns < 0 or end_t_ns <= start_t_ns:
        raise ValueError("scope must have a positive non-negative span")
    if kind == "session" and any(value is not None for value in (phase_id, event_id, window_id)):
        raise ValueError("session scope cannot claim phase, event, or window identity")
    if kind == "phase" and (phase_id != scope_id or event_id is not None or window_id is not None):
        raise ValueError("phase scope identity is inconsistent")
    if kind == "event" and (event_id != scope_id or window_id is not None):
        raise ValueError("event scope identity is inconsistent")
    if kind == "window" and window_id != scope_id:
        raise ValueError("window scope identity is inconsistent")


@dataclass(frozen=True, slots=True)
class ProjectedSemanticScope:
    values: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", _frozen_json_mapping(self.values))


@dataclass(frozen=True, slots=True)
class AnchorPluginContext:
    session_id: str
    session_window: SessionWindow
    streams: Mapping[str, AlignedStreamView]
    context: Mapping[str, JsonValue]
    references: Mapping[str, ResolvedReference]
    semantic_scope: ProjectedSemanticScope

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "session_id",
            _strict_stable_id(self.session_id, label="session_id"),
        )
        if not isinstance(self.session_window, SessionWindow):
            raise TypeError("session_window must be a SessionWindow")
        if not isinstance(self.semantic_scope, ProjectedSemanticScope):
            raise TypeError("semantic_scope must be a ProjectedSemanticScope")
        object.__setattr__(self, "streams", _clone_stream_mapping(self.streams))
        object.__setattr__(self, "context", _frozen_json_mapping(self.context))
        object.__setattr__(self, "references", _clone_reference_mapping(self.references))


@dataclass(frozen=True, slots=True)
class ArtifactProducer:
    anchor_id: str
    plugin_id: str
    plugin_version: str
    implementation_digest: Sha256Digest
    parameter_hash: Sha256Digest
    dependency_fingerprints: tuple[Sha256Digest, ...]

    def __post_init__(self) -> None:
        for field_name in ("anchor_id", "plugin_id", "plugin_version"):
            object.__setattr__(
                self,
                field_name,
                _strict_stable_id(getattr(self, field_name), label=field_name),
            )
        for field_name in ("implementation_digest", "parameter_hash"):
            object.__setattr__(
                self,
                field_name,
                _strict_sha256(getattr(self, field_name), label=field_name),
            )
        object.__setattr__(
            self,
            "dependency_fingerprints",
            _normalized_fingerprints(
                self.dependency_fingerprints,
                label="dependency_fingerprints",
            ),
        )


@dataclass(frozen=True, slots=True)
class PreprocessingScope:
    kind: _ScopeKind
    scope_id: str
    start_t_ns: int
    end_t_ns: int
    phase_id: str | None
    event_id: str | None
    window_id: str | None

    def __post_init__(self) -> None:
        _validate_scope(
            kind=self.kind,
            scope_id=self.scope_id,
            start_t_ns=self.start_t_ns,
            end_t_ns=self.end_t_ns,
            phase_id=self.phase_id,
            event_id=self.event_id,
            window_id=self.window_id,
        )


@dataclass(frozen=True, slots=True)
class PreprocessingProducer:
    recipe_id: str
    recipe_version: str
    provider_id: str
    provider_version: str
    implementation_digest: Sha256Digest
    parameter_schema_id: str
    parameter_schema_sha256: Sha256Digest
    parameter_hash: Sha256Digest
    output_schema_id: str
    output_schema_sha256: Sha256Digest
    artifact_kind: str
    output_payload_kind: _PayloadKind
    scope_kind: _ScopeKind
    scope_id: str
    scope_start_t_ns: int
    scope_end_t_ns: int
    phase_id: str | None
    event_id: str | None
    window_id: str | None
    dependency_fingerprints: tuple[Sha256Digest, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "recipe_id",
            "recipe_version",
            "provider_id",
            "provider_version",
            "parameter_schema_id",
            "output_schema_id",
            "artifact_kind",
        ):
            object.__setattr__(
                self,
                field_name,
                _strict_stable_id(getattr(self, field_name), label=field_name),
            )
        for field_name in (
            "implementation_digest",
            "parameter_schema_sha256",
            "parameter_hash",
            "output_schema_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _strict_sha256(getattr(self, field_name), label=field_name),
            )
        if self.output_payload_kind not in {"table", "blob"}:
            raise ValueError("output_payload_kind must be table or blob")
        _validate_scope(
            kind=self.scope_kind,
            scope_id=self.scope_id,
            start_t_ns=self.scope_start_t_ns,
            end_t_ns=self.scope_end_t_ns,
            phase_id=self.phase_id,
            event_id=self.event_id,
            window_id=self.window_id,
        )
        object.__setattr__(
            self,
            "dependency_fingerprints",
            _normalized_fingerprints(
                self.dependency_fingerprints,
                label="dependency_fingerprints",
            ),
        )


@dataclass(frozen=True, slots=True)
class TabularArtifactPayload:
    schema_id: str
    schema_descriptor: Mapping[str, JsonValue]
    frame: pl.DataFrame
    order_keys: tuple[str, ...]
    artifact_kind: str
    grid_hash: Sha256Digest | None
    start_t_ns: int | None
    end_t_ns: int | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "schema_id",
            _strict_stable_id(self.schema_id, label="schema_id"),
        )
        object.__setattr__(
            self,
            "artifact_kind",
            _strict_stable_id(self.artifact_kind, label="artifact_kind"),
        )
        object.__setattr__(self, "schema_descriptor", _frozen_json_mapping(self.schema_descriptor))
        object.__setattr__(self, "frame", _clone_frame(self.frame))
        object.__setattr__(
            self,
            "order_keys",
            _normalized_order_keys(self.order_keys),
        )
        object.__setattr__(
            self,
            "grid_hash",
            _strict_optional_sha256(self.grid_hash, label="grid_hash"),
        )
        _validate_optional_bounds(self.start_t_ns, self.end_t_ns)


@dataclass(frozen=True, slots=True)
class BlobArtifactPayload:
    schema_id: str
    payload_bytes: bytes
    artifact_kind: str
    start_t_ns: int | None
    end_t_ns: int | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "schema_id",
            _strict_stable_id(self.schema_id, label="schema_id"),
        )
        object.__setattr__(
            self,
            "artifact_kind",
            _strict_stable_id(self.artifact_kind, label="artifact_kind"),
        )
        if type(self.payload_bytes) is not bytes:
            raise TypeError("payload_bytes must be immutable bytes")
        _validate_optional_bounds(self.start_t_ns, self.end_t_ns)


@dataclass(frozen=True, slots=True)
class ReadOnlyTabularPayload:
    schema_id: str
    schema_descriptor: Mapping[str, JsonValue]
    frame: pl.DataFrame
    order_keys: tuple[str, ...]
    artifact_kind: str
    grid_hash: Sha256Digest | None
    start_t_ns: int | None
    end_t_ns: int | None
    logical_content_sha256: Sha256Digest

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "schema_id",
            _strict_stable_id(self.schema_id, label="schema_id"),
        )
        object.__setattr__(
            self,
            "artifact_kind",
            _strict_stable_id(self.artifact_kind, label="artifact_kind"),
        )
        object.__setattr__(self, "schema_descriptor", _frozen_json_mapping(self.schema_descriptor))
        object.__setattr__(
            self,
            "frame",
            _clone_frame(object.__getattribute__(self, "frame")),
        )
        object.__setattr__(
            self,
            "order_keys",
            _normalized_order_keys(self.order_keys),
        )
        object.__setattr__(
            self,
            "grid_hash",
            _strict_optional_sha256(self.grid_hash, label="grid_hash"),
        )
        object.__setattr__(
            self,
            "logical_content_sha256",
            _strict_sha256(
                self.logical_content_sha256,
                label="logical_content_sha256",
            ),
        )
        _validate_optional_bounds(self.start_t_ns, self.end_t_ns)

    def __getattribute__(self, name: str) -> object:
        value = object.__getattribute__(self, name)
        if name == "frame":
            return _clone_frame(value)
        return value


@dataclass(frozen=True, slots=True)
class ReadOnlyBlobPayload:
    schema_id: str
    payload_bytes: bytes
    artifact_kind: str
    start_t_ns: int | None
    end_t_ns: int | None
    logical_content_sha256: Sha256Digest

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "schema_id",
            _strict_stable_id(self.schema_id, label="schema_id"),
        )
        object.__setattr__(
            self,
            "artifact_kind",
            _strict_stable_id(self.artifact_kind, label="artifact_kind"),
        )
        if type(self.payload_bytes) is not bytes:
            raise TypeError("payload_bytes must be immutable bytes")
        object.__setattr__(
            self,
            "logical_content_sha256",
            _strict_sha256(
                self.logical_content_sha256,
                label="logical_content_sha256",
            ),
        )
        _validate_optional_bounds(self.start_t_ns, self.end_t_ns)


_ReadOnlyPayload = ReadOnlyTabularPayload | ReadOnlyBlobPayload


@dataclass(frozen=True, slots=True)
class ResolvedArtifactDependency:
    ref: AnchorArtifactRef
    payload: _ReadOnlyPayload

    def __post_init__(self) -> None:
        if not isinstance(self.ref, AnchorArtifactRef):
            raise TypeError("ref must be an AnchorArtifactRef")
        if not isinstance(self.payload, (ReadOnlyTabularPayload, ReadOnlyBlobPayload)):
            raise TypeError("payload must be a read-only artifact payload")
        if (
            self.ref.schema_id != self.payload.schema_id
            or self.ref.kind != self.payload.artifact_kind
            or self.ref.logical_content_sha256 != self.payload.logical_content_sha256
        ):
            raise ValueError("artifact reference and payload identities do not match")
        if (
            self.ref.start_t_ns != self.payload.start_t_ns
            or self.ref.end_t_ns != self.payload.end_t_ns
        ):
            raise ValueError("artifact reference and payload bounds do not match")
        if isinstance(self.payload, ReadOnlyTabularPayload):
            if self.ref.row_count != self.payload.frame.height:
                raise ValueError("artifact reference and table row count do not match")
            if self.ref.grid_hash != self.payload.grid_hash:
                raise ValueError("artifact reference and table grid identity do not match")
        elif self.ref.grid_hash is not None:
            raise ValueError("blob artifact references cannot claim a table grid")


@dataclass(frozen=True, slots=True)
class PreprocessingArtifactIdentity:
    recipe_id: str
    recipe_version: str
    provider_id: str
    provider_version: str
    implementation_digest: Sha256Digest
    parameter_schema_id: str
    parameter_schema_sha256: Sha256Digest
    parameter_hash: Sha256Digest
    scope_kind: _ScopeKind
    scope_id: str
    scope_start_t_ns: int
    scope_end_t_ns: int
    phase_id: str | None
    event_id: str | None
    window_id: str | None
    schema_id: str
    schema_sha256: Sha256Digest
    artifact_kind: str
    payload_kind: _PayloadKind
    logical_content_sha256: Sha256Digest
    dependency_fingerprints: tuple[Sha256Digest, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "recipe_id",
            "recipe_version",
            "provider_id",
            "provider_version",
            "parameter_schema_id",
            "schema_id",
            "artifact_kind",
        ):
            object.__setattr__(
                self,
                field_name,
                _strict_stable_id(getattr(self, field_name), label=field_name),
            )
        for field_name in (
            "implementation_digest",
            "parameter_schema_sha256",
            "parameter_hash",
            "schema_sha256",
            "logical_content_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _strict_sha256(getattr(self, field_name), label=field_name),
            )
        if self.payload_kind not in {"table", "blob"}:
            raise ValueError("payload_kind must be table or blob")
        _validate_scope(
            kind=self.scope_kind,
            scope_id=self.scope_id,
            start_t_ns=self.scope_start_t_ns,
            end_t_ns=self.scope_end_t_ns,
            phase_id=self.phase_id,
            event_id=self.event_id,
            window_id=self.window_id,
        )
        object.__setattr__(
            self,
            "dependency_fingerprints",
            _normalized_fingerprints(
                self.dependency_fingerprints,
                label="dependency_fingerprints",
            ),
        )


@dataclass(frozen=True, slots=True)
class ResolvedPreprocessingDependency:
    identity: PreprocessingArtifactIdentity
    payload: _ReadOnlyPayload

    def __post_init__(self) -> None:
        if not isinstance(self.identity, PreprocessingArtifactIdentity):
            raise TypeError("identity must be a PreprocessingArtifactIdentity")
        if not isinstance(self.payload, (ReadOnlyTabularPayload, ReadOnlyBlobPayload)):
            raise TypeError("payload must be a read-only artifact payload")
        payload_kind = "table" if isinstance(self.payload, ReadOnlyTabularPayload) else "blob"
        if (
            self.identity.schema_id != self.payload.schema_id
            or self.identity.artifact_kind != self.payload.artifact_kind
            or self.identity.payload_kind != payload_kind
            or self.identity.logical_content_sha256 != self.payload.logical_content_sha256
        ):
            raise ValueError("preprocessing identity and payload do not match")


@dataclass(frozen=True, slots=True)
class ResolvedDependencies:
    results: Mapping[str, AnchorResultV2]
    artifacts: Mapping[str, ResolvedArtifactDependency]
    algorithm_profiles: Mapping[str, ResolvedAlgorithmProfile]
    preprocessing: Mapping[str, ResolvedPreprocessingDependency]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "results",
            _frozen_mapping(
                self.results,
                label="result dependencies",
                value_type=AnchorResultV2,
            ),
        )
        object.__setattr__(
            self,
            "artifacts",
            _frozen_mapping(
                self.artifacts,
                label="artifact dependencies",
                value_type=ResolvedArtifactDependency,
            ),
        )
        object.__setattr__(
            self,
            "algorithm_profiles",
            _frozen_mapping(
                self.algorithm_profiles,
                label="algorithm profile dependencies",
                value_type=ResolvedAlgorithmProfile,
            ),
        )
        object.__setattr__(
            self,
            "preprocessing",
            _frozen_mapping(
                self.preprocessing,
                label="preprocessing dependencies",
                value_type=ResolvedPreprocessingDependency,
            ),
        )


class AnchorArtifactEmitter(Protocol):
    def stage_table(
        self, artifact_id: str, payload: TabularArtifactPayload
    ) -> AnchorArtifactRef: ...

    def stage_blob(self, artifact_id: str, payload: BlobArtifactPayload) -> AnchorArtifactRef: ...


class AnchorArtifactTransaction(Protocol):
    def emitter(self) -> AnchorArtifactEmitter: ...

    def staged_refs(self) -> tuple[AnchorArtifactRef, ...]: ...

    def commit(self) -> tuple[AnchorArtifactRef, ...]: ...

    def abort(self) -> None: ...


class EvaluationArtifactTransaction(Protocol):
    def begin_anchor(
        self,
        producer: ArtifactProducer,
        artifact_recipes: tuple[AnchorArtifactRecipe, ...],
    ) -> AnchorArtifactTransaction: ...

    def resolve(self, ref: AnchorArtifactRef) -> ResolvedArtifactDependency: ...

    def stage_preprocessing(
        self,
        producer: PreprocessingProducer,
        payload: TabularArtifactPayload | BlobArtifactPayload,
    ) -> ResolvedPreprocessingDependency: ...

    def commit(self) -> None: ...

    def abort(self) -> None: ...


class DerivedArtifactSink(Protocol):
    def begin_evaluation(self, evaluation_key: str) -> EvaluationArtifactTransaction: ...


class AnchorPlugin(Protocol):
    def definition(self) -> AnchorPluginDefinition: ...

    def compute(
        self,
        context: AnchorPluginContext,
        parameters: Mapping[str, JsonValue],
        temporal_recipe: Mapping[str, JsonValue],
        dependencies: ResolvedDependencies,
        artifacts: AnchorArtifactEmitter,
    ) -> AnchorMeasurement: ...


class PreprocessingProvider(Protocol):
    def definition(self) -> PreprocessingProviderDefinition: ...

    def compute(
        self,
        context: AnchorPluginContext,
        recipe: ResolvedPreprocessingRecipe,
        scope: PreprocessingScope,
        dependencies: Mapping[str, ResolvedPreprocessingDependency],
    ) -> TabularArtifactPayload | BlobArtifactPayload: ...


__all__ = [
    "AnchorArtifactEmitter",
    "AnchorArtifactTransaction",
    "AnchorPlugin",
    "AnchorPluginContext",
    "ArtifactProducer",
    "BlobArtifactPayload",
    "DerivedArtifactSink",
    "EvaluationArtifactTransaction",
    "PreprocessingArtifactIdentity",
    "PreprocessingProducer",
    "PreprocessingProvider",
    "PreprocessingScope",
    "ProjectedSemanticScope",
    "ReadOnlyBlobPayload",
    "ReadOnlyTabularPayload",
    "ResolvedArtifactDependency",
    "ResolvedDependencies",
    "ResolvedPreprocessingDependency",
    "TabularArtifactPayload",
]
