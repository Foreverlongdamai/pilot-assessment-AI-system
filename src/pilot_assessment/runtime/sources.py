"""Per-run, registry-driven resolution of versioned Evidence input sources."""

from __future__ import annotations

import math
from bisect import bisect_left
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol, cast, runtime_checkable

import polars as pl
from pydantic import JsonValue

from pilot_assessment.contracts.assessment_scheme import TaskProfileVersion
from pilot_assessment.contracts.evidence_recipe import RecipeInputBinding
from pilot_assessment.evidence.builtins.flight import (
    VectorSample,
    VectorSeries,
    vector_series,
)
from pilot_assessment.evidence.builtins.gaze import GazeFrame
from pilot_assessment.evidence.builtins.signal import (
    NumericSample,
    SignalSeries,
    signal_series,
)
from pilot_assessment.evidence.builtins.temporal import EventRecord
from pilot_assessment.model_library.sources import (
    SourceCatalog,
    SourceCatalogLookupError,
)
from pilot_assessment.synchronization.models import AlignedSession, AlignedStreamView


class RuntimeSourceProviderRegistryError(ValueError):
    """Raised for duplicate or malformed runtime source-provider registrations."""


class SourceUnavailableError(RuntimeError):
    """Expected absence or inapplicability; it does not imply poor performance."""


class SourceResolutionStatus(StrEnum):
    AVAILABLE = "available"
    OMITTED = "omitted"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class RuntimeSourceDiagnostic:
    code: str
    source_id: str
    message: str
    dependency_path: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SourceResolution:
    source_id: str
    status: SourceResolutionStatus
    value: object | None
    diagnostics: tuple[RuntimeSourceDiagnostic, ...]

    def __post_init__(self) -> None:
        if self.status is SourceResolutionStatus.AVAILABLE and self.value is None:
            raise ValueError("available source resolution requires a value")
        if self.status is not SourceResolutionStatus.AVAILABLE and self.value is not None:
            raise ValueError("unavailable source resolution cannot carry a value")


@dataclass(frozen=True, slots=True)
class ResolvedRecipeInputs:
    binding_values: Mapping[str, object]
    omitted_binding_ids: tuple[str, ...]
    error_binding_ids: tuple[str, ...]
    diagnostics: tuple[RuntimeSourceDiagnostic, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "binding_values",
            MappingProxyType(dict(self.binding_values)),
        )

    @property
    def executable(self) -> bool:
        return not self.omitted_binding_ids and not self.error_binding_ids


@dataclass(frozen=True, slots=True)
class SourceResolutionContext:
    aligned_session: AlignedSession
    task_profile: TaskProfileVersion
    runtime_parameters: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "runtime_parameters",
            MappingProxyType(dict(self.runtime_parameters)),
        )


@runtime_checkable
class RuntimeSourceProvider(Protocol):
    """One trusted adapter from an aligned run context to a stable source ID."""

    @property
    def source_id(self) -> str:
        """Stable descriptor identity implemented by this provider."""

    def provide(
        self,
        context: SourceResolutionContext,
        dependencies: Mapping[str, object],
    ) -> object:
        """Return the source value or raise SourceUnavailableError."""


class RuntimeSourceProviderRegistry:
    """Explicit registry; the generic resolver never branches on task or Evidence IDs."""

    def __init__(self) -> None:
        self._providers: dict[str, RuntimeSourceProvider] = {}

    def register(self, provider: RuntimeSourceProvider) -> None:
        if not isinstance(provider, RuntimeSourceProvider):
            raise RuntimeSourceProviderRegistryError(
                "runtime source provider does not implement the provider protocol"
            )
        if type(provider.source_id) is not str or not provider.source_id:
            raise RuntimeSourceProviderRegistryError("provider source_id must be non-empty")
        if provider.source_id in self._providers:
            raise RuntimeSourceProviderRegistryError(
                f"runtime source provider {provider.source_id!r} is already registered"
            )
        self._providers[provider.source_id] = provider

    def get(self, source_id: str) -> RuntimeSourceProvider:
        try:
            return self._providers[source_id]
        except KeyError as error:
            raise RuntimeSourceProviderRegistryError(
                f"runtime source provider {source_id!r} is not registered"
            ) from error

    def source_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))


class RuntimeSourceResolver:
    """Resolve a descriptor dependency DAG once and cache values for one run."""

    def __init__(
        self,
        catalog: SourceCatalog,
        registry: RuntimeSourceProviderRegistry,
        context: SourceResolutionContext,
    ) -> None:
        self.catalog = catalog
        self.registry = registry
        self.context = context
        self._cache: dict[str, SourceResolution] = {}

    def resolve(self, source_id: str) -> SourceResolution:
        return self._resolve(source_id, ())

    def resolve_bindings(
        self,
        bindings: Sequence[RecipeInputBinding],
    ) -> ResolvedRecipeInputs:
        values: dict[str, object] = {}
        omitted: list[str] = []
        errors: list[str] = []
        diagnostics: list[RuntimeSourceDiagnostic] = []
        for binding in bindings:
            result = self.resolve(binding.source_id)
            diagnostics.extend(result.diagnostics)
            if result.status is SourceResolutionStatus.AVAILABLE:
                assert result.value is not None
                values[binding.binding_id] = result.value
            elif result.status is SourceResolutionStatus.OMITTED:
                omitted.append(binding.binding_id)
            else:
                errors.append(binding.binding_id)
        diagnostic_keys: set[tuple[str, str, tuple[str, ...], str]] = set()
        ordered_diagnostics: list[RuntimeSourceDiagnostic] = []
        for diagnostic in diagnostics:
            key = (
                diagnostic.code,
                diagnostic.source_id,
                diagnostic.dependency_path,
                diagnostic.message,
            )
            if key not in diagnostic_keys:
                diagnostic_keys.add(key)
                ordered_diagnostics.append(diagnostic)
        return ResolvedRecipeInputs(
            binding_values=values,
            omitted_binding_ids=tuple(omitted),
            error_binding_ids=tuple(errors),
            diagnostics=tuple(ordered_diagnostics),
        )

    def _resolve(self, source_id: str, active: tuple[str, ...]) -> SourceResolution:
        cached = self._cache.get(source_id)
        if cached is not None:
            return cached
        if source_id in active:
            return self._error(
                source_id,
                "runtime.source_dependency_cycle",
                f"runtime source dependency cycle: {' -> '.join((*active, source_id))}",
                (*active, source_id),
            )
        try:
            descriptor = self.catalog.get(source_id)
        except SourceCatalogLookupError:
            result = self._error(
                source_id,
                "runtime.source_unknown",
                f"source descriptor {source_id!r} is not selected by this run",
                (*active, source_id),
            )
            self._cache[source_id] = result
            return result
        try:
            provider = self.registry.get(source_id)
        except RuntimeSourceProviderRegistryError as error:
            result = self._error(
                source_id,
                "runtime.source_provider_missing",
                str(error),
                (*active, source_id),
            )
            self._cache[source_id] = result
            return result

        dependency_values: dict[str, object] = {}
        dependency_diagnostics: list[RuntimeSourceDiagnostic] = []
        dependency_status = SourceResolutionStatus.AVAILABLE
        next_active = (*active, source_id)
        for dependency_id in descriptor.source_dependencies:
            dependency = self._resolve(dependency_id, next_active)
            dependency_diagnostics.extend(dependency.diagnostics)
            if dependency.status is SourceResolutionStatus.ERROR:
                dependency_status = SourceResolutionStatus.ERROR
            elif (
                dependency.status is SourceResolutionStatus.OMITTED
                and dependency_status is SourceResolutionStatus.AVAILABLE
            ):
                dependency_status = SourceResolutionStatus.OMITTED
            if dependency.status is SourceResolutionStatus.AVAILABLE:
                assert dependency.value is not None
                dependency_values[dependency_id] = dependency.value
        if dependency_status is not SourceResolutionStatus.AVAILABLE:
            diagnostic = RuntimeSourceDiagnostic(
                code="runtime.source_dependency_unavailable",
                source_id=source_id,
                message="one or more declared source dependencies are unavailable",
                dependency_path=next_active,
            )
            result = SourceResolution(
                source_id=source_id,
                status=dependency_status,
                value=None,
                diagnostics=tuple((*dependency_diagnostics, diagnostic)),
            )
            self._cache[source_id] = result
            return result

        try:
            value = provider.provide(
                self.context,
                MappingProxyType(dependency_values),
            )
            if value is None:
                raise SourceUnavailableError("provider returned no applicable value")
        except SourceUnavailableError as error:
            result = SourceResolution(
                source_id=source_id,
                status=SourceResolutionStatus.OMITTED,
                value=None,
                diagnostics=(
                    RuntimeSourceDiagnostic(
                        code="runtime.source_unavailable",
                        source_id=source_id,
                        message=str(error),
                        dependency_path=next_active,
                    ),
                ),
            )
        except Exception as error:
            result = self._error(
                source_id,
                "runtime.source_provider_failed",
                f"source provider raised {type(error).__name__}: {error}",
                next_active,
            )
        else:
            result = SourceResolution(
                source_id=source_id,
                status=SourceResolutionStatus.AVAILABLE,
                value=value,
                diagnostics=(),
            )
        self._cache[source_id] = result
        return result

    @staticmethod
    def _error(
        source_id: str,
        code: str,
        message: str,
        dependency_path: tuple[str, ...],
    ) -> SourceResolution:
        return SourceResolution(
            source_id=source_id,
            status=SourceResolutionStatus.ERROR,
            value=None,
            diagnostics=(
                RuntimeSourceDiagnostic(
                    code=code,
                    source_id=source_id,
                    message=message,
                    dependency_path=dependency_path,
                ),
            ),
        )


ProviderFunction = Callable[[SourceResolutionContext, Mapping[str, object]], object]


@dataclass(frozen=True, slots=True)
class FunctionSourceProvider:
    source_id: str
    function: ProviderFunction

    def provide(
        self,
        context: SourceResolutionContext,
        dependencies: Mapping[str, object],
    ) -> object:
        return self.function(context, dependencies)


def _stream(context: SourceResolutionContext, modality: str) -> AlignedStreamView:
    try:
        return context.aligned_session.streams[modality]
    except KeyError as error:
        raise SourceUnavailableError(
            f"aligned modality {modality!r} is absent; Evidence must be omitted"
        ) from error


def _table(
    context: SourceResolutionContext,
    modality: str,
    role: str,
) -> pl.DataFrame:
    stream = _stream(context, modality)
    try:
        frame = stream.tables[role]
    except KeyError as error:
        raise SourceUnavailableError(
            f"aligned modality {modality!r} has no {role!r} table"
        ) from error
    if "in_session" in frame.columns:
        frame = frame.filter(pl.col("in_session"))
    if frame.is_empty():
        raise SourceUnavailableError(
            f"aligned modality {modality!r} table {role!r} has no in-session rows"
        )
    if "t_ns" in frame.columns:
        frame = frame.sort("t_ns", maintain_order=True)
    return frame


def _require_columns(frame: pl.DataFrame, columns: Sequence[str], source_id: str) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise SourceUnavailableError(
            f"source {source_id!r} requires missing aligned columns {missing!r}"
        )


def _numeric(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SourceUnavailableError(f"{label} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise SourceUnavailableError(f"{label} must be finite")
    return numeric


def _vector_from_table(
    frame: pl.DataFrame,
    *,
    source_id: str,
    dimensions: tuple[str, ...],
    columns: tuple[str, ...],
    unit: str | None,
) -> VectorSeries:
    _require_columns(frame, ("t_ns", *columns), source_id)
    samples = tuple(
        VectorSample(
            t_ns=int(row[0]),
            values=tuple(float(value) for value in row[1:]),
        )
        for row in frame.select(("t_ns", *columns)).iter_rows()
    )
    return VectorSeries(
        series_id=source_id,
        dimensions=dimensions,
        unit=unit,
        samples=samples,
    )


def _signal_from_column(
    frame: pl.DataFrame,
    *,
    source_id: str,
    column: str,
    unit: str | None,
) -> SignalSeries:
    _require_columns(frame, ("t_ns", column), source_id)
    samples = tuple(
        NumericSample(t_ns=int(t_ns), value=float(value))
        for t_ns, value in frame.select(("t_ns", column)).iter_rows()
        if value is not None
    )
    if not samples:
        raise SourceUnavailableError(f"source {source_id!r} has no numeric samples")
    return SignalSeries(series_id=source_id, unit=unit, samples=samples)


def _raw_vector_provider(
    source_id: str,
    columns: tuple[str, ...],
    dimensions: tuple[str, ...],
    *,
    unit: str | None,
) -> FunctionSourceProvider:
    def provide(context: SourceResolutionContext, _dependencies: Mapping[str, object]) -> object:
        return _vector_from_table(
            _table(context, "X", "samples"),
            source_id=source_id,
            dimensions=dimensions,
            columns=columns,
            unit=unit,
        )

    return FunctionSourceProvider(source_id, provide)


def _u_bundle(context: SourceResolutionContext, _dependencies: Mapping[str, object]) -> object:
    frame = _table(context, "U", "samples")
    definitions = {
        "yaw": ("control.yaw_raw", None),
        "longitudinal": ("control.longitudinal_raw", None),
        "lateral": ("control.lateral_raw", None),
        "heave": ("control.heave_raw", None),
        "primary": ("control.longitudinal_raw", None),
    }
    return MappingProxyType(
        {
            channel_id: _signal_from_column(
                frame,
                source_id=f"U.channels.{channel_id}",
                column=column,
                unit=unit,
            )
            for channel_id, (column, unit) in definitions.items()
        }
    )


def _u_primary(context: SourceResolutionContext, _dependencies: Mapping[str, object]) -> object:
    return cast(Mapping[str, object], _u_bundle(context, {}))["primary"]


def _eeg_bundle(context: SourceResolutionContext, _dependencies: Mapping[str, object]) -> object:
    frame = _table(context, "EEG", "samples")
    physical_columns = tuple(column for column in frame.columns if column.endswith("_uV"))
    if not physical_columns:
        raise SourceUnavailableError("aligned EEG contains no numeric channel columns")
    channels: dict[str, object] = {
        column.removesuffix("_uV"): _signal_from_column(
            frame,
            source_id=f"EEG.channels.{column.removesuffix('_uV')}",
            column=column,
            unit="uV",
        )
        for column in physical_columns
    }
    _require_columns(frame, ("t_ns", *physical_columns), "EEG.channels.engagement")
    engagement = SignalSeries(
        series_id="EEG.channels.engagement",
        unit="uV-rms",
        samples=tuple(
            NumericSample(
                t_ns=int(row[0]),
                value=math.sqrt(
                    sum(float(value) ** 2 for value in row[1:]) / len(physical_columns)
                ),
            )
            for row in frame.select(("t_ns", *physical_columns)).iter_rows()
        ),
    )
    channels["engagement"] = engagement
    return MappingProxyType(channels)


def _ecg_bundle(context: SourceResolutionContext, _dependencies: Mapping[str, object]) -> object:
    stream = _stream(context, "ECG")
    channels: dict[str, object] = {}
    if "samples" in stream.tables:
        samples = _table(context, "ECG", "samples")
        raw_columns = tuple(column for column in samples.columns if column.endswith("_mV"))
        for column in raw_columns:
            channels[column.removesuffix("_mV")] = _signal_from_column(
                samples,
                source_id=f"ECG.channels.{column.removesuffix('_mV')}",
                column=column,
                unit="mV",
            )
    if "r_peaks" in stream.tables:
        peaks = _table(context, "ECG", "r_peaks")
        _require_columns(peaks, ("t_ns", "rr_interval_ms"), "ECG.channels.heart-rate")
        heart_samples = tuple(
            NumericSample(int(t_ns), 60_000.0 / float(rr_ms))
            for t_ns, rr_ms in peaks.select(("t_ns", "rr_interval_ms")).iter_rows()
            if rr_ms is not None and float(rr_ms) > 0.0
        )
        if heart_samples:
            channels["heart-rate"] = SignalSeries(
                series_id="ECG.channels.heart-rate",
                unit="beats/min",
                samples=heart_samples,
            )
    if "heart-rate" not in channels:
        raise SourceUnavailableError(
            "aligned ECG has no positive RR intervals for heart-rate Evidence"
        )
    return MappingProxyType(channels)


def _gaze_frames(context: SourceResolutionContext, _dependencies: Mapping[str, object]) -> object:
    frame = _table(context, "G", "gaze_samples")
    columns = ("gaze_sample_id", "t_ns", "assigned_aoi_id")
    _require_columns(frame, columns, "G.frames")
    rows = tuple(frame.select(columns).iter_rows())
    if not rows:
        raise SourceUnavailableError("aligned gaze contains no in-session samples")
    result: list[GazeFrame] = []
    session_end = context.aligned_session.window.end_t_ns
    for index, row in enumerate(rows):
        start = int(row[1])
        end = int(rows[index + 1][1]) if index + 1 < len(rows) else session_end
        if end <= start:
            continue
        assigned = None if row[2] is None else str(row[2])
        result.append(
            GazeFrame(
                frame_id=str(row[0]),
                start_t_ns=start,
                end_t_ns=end,
                assigned_aoi_id=assigned,
                geometry_hits={},
            )
        )
    if not result:
        raise SourceUnavailableError("aligned gaze samples have no positive frame intervals")
    return tuple(result)


def _frame_records(modality: str, role: str) -> ProviderFunction:
    def provide(context: SourceResolutionContext, _dependencies: Mapping[str, object]) -> object:
        frame = _table(context, modality, role)
        return tuple(MappingProxyType(dict(row)) for row in frame.to_dicts())

    return provide


def _duration(context: SourceResolutionContext, _dependencies: Mapping[str, object]) -> object:
    return context.aligned_session.window.end_t_ns / 1_000_000_000.0


def _event_records(
    context: SourceResolutionContext,
    event_types: frozenset[str],
) -> tuple[EventRecord, ...]:
    return tuple(
        EventRecord(
            event_id=event.event_id,
            event_type=event.event_type,
            t_ns=event.t_ns,
            duration_ns=event.duration_ns or 0,
            attributes={
                "source": event.source,
                "confidence": event.confidence,
                "response_mapping": event.response_mapping,
                **dict(event.extensions),
            },
        )
        for event in context.aligned_session.annotations.events
        if event.event_type in event_types
    )


def _event_provider(source_id: str, *event_types: str) -> FunctionSourceProvider:
    selected = frozenset(event_types)

    def provide(context: SourceResolutionContext, _dependencies: Mapping[str, object]) -> object:
        return _event_records(context, selected)

    return FunctionSourceProvider(source_id, provide)


def _task_reference_table(context: SourceResolutionContext) -> pl.DataFrame:
    reference = context.aligned_session.task_reference
    if reference is None:
        raise SourceUnavailableError("aligned session has no task reference")
    try:
        frame = reference.tables["commanded_path"]
    except KeyError as error:
        raise SourceUnavailableError(
            "aligned task reference has no commanded_path table"
        ) from error
    if "in_session" in frame.columns:
        frame = frame.filter(pl.col("in_session"))
    if frame.is_empty():
        raise SourceUnavailableError("aligned commanded path has no in-session rows")
    return frame.sort("t_ns", maintain_order=True)


def _commanded_path(
    context: SourceResolutionContext,
    _dependencies: Mapping[str, object],
) -> object:
    return _vector_from_table(
        _task_reference_table(context),
        source_id="task-reference.commanded-path",
        dimensions=("x", "y", "z"),
        columns=("target_x_m", "target_y_m", "target_z_m"),
        unit="m",
    )


def _terminal_target(
    context: SourceResolutionContext,
    _dependencies: Mapping[str, object],
) -> object:
    frame = _task_reference_table(context)
    columns = ("target_x_m", "target_y_m", "target_z_m")
    _require_columns(frame, columns, "task-reference.terminal-target")
    row = frame.select(columns).tail(1).row(0)
    return tuple(float(value) for value in row)


def _expected_envelope(
    context: SourceResolutionContext,
    _dependencies: Mapping[str, object],
) -> object:
    frame = _task_reference_table(context)
    envelope_ids = (
        tuple(str(value) for value in frame["envelope_id"].drop_nulls().unique())
        if "envelope_id" in frame.columns
        else ()
    )
    return MappingProxyType(
        {
            "lower_bounds": (-1.0, -1.0, -1.0),
            "upper_bounds": (1.0, 1.0, 1.0),
            "envelope_ids": envelope_ids,
            "task_reference_parameters": dict(context.task_profile.reference_parameters),
        }
    )


def _nearest_vector(reference: VectorSeries, t_ns: int) -> tuple[float, ...]:
    if not reference.samples:
        raise SourceUnavailableError("reference vector series is empty")
    times = tuple(sample.t_ns for sample in reference.samples)
    index = bisect_left(times, t_ns)
    if index == 0:
        return reference.samples[0].values
    if index == len(times):
        return reference.samples[-1].values
    left = reference.samples[index - 1]
    right = reference.samples[index]
    return left.values if t_ns - left.t_ns <= right.t_ns - t_ns else right.values


def _flight_error(
    _context: SourceResolutionContext,
    dependencies: Mapping[str, object],
) -> object:
    actual = vector_series(dependencies["X.position-vector"])
    commanded = vector_series(dependencies["task-reference.commanded-path"])
    if actual.dimensions != commanded.dimensions:
        raise SourceUnavailableError("actual and commanded path dimensions differ")
    return SignalSeries(
        series_id="derived.flight-error",
        unit="m",
        samples=tuple(
            NumericSample(
                sample.t_ns,
                math.sqrt(
                    sum(
                        (actual_value - reference_value) ** 2
                        for actual_value, reference_value in zip(
                            sample.values,
                            _nearest_vector(commanded, sample.t_ns),
                            strict=True,
                        )
                    )
                ),
            )
            for sample in actual.samples
        ),
    )


def _terminal_error(
    _context: SourceResolutionContext,
    dependencies: Mapping[str, object],
) -> object:
    actual = vector_series(dependencies["X.position-vector"])
    raw_target = dependencies["task-reference.terminal-target"]
    if isinstance(raw_target, (str, bytes)) or not isinstance(raw_target, Sequence):
        raise SourceUnavailableError("terminal target is not a numeric vector")
    target = tuple(_numeric(value, "terminal target value") for value in raw_target)
    if len(target) != len(actual.dimensions):
        raise SourceUnavailableError("terminal target width differs from actual position")
    return SignalSeries(
        series_id="derived.terminal-error",
        unit="m",
        samples=tuple(
            NumericSample(
                sample.t_ns,
                math.sqrt(
                    sum(
                        (actual_value - target_value) ** 2
                        for actual_value, target_value in zip(
                            sample.values,
                            target,
                            strict=True,
                        )
                    )
                ),
            )
            for sample in actual.samples
        ),
    )


def _envelope_error(
    _context: SourceResolutionContext,
    dependencies: Mapping[str, object],
) -> object:
    state = vector_series(dependencies["X.state-vector"])
    raw_envelope = dependencies["task-reference.expected-envelope"]
    if not isinstance(raw_envelope, Mapping):
        raise SourceUnavailableError("expected envelope is not a bounds mapping")
    envelope = cast(Mapping[str, object], raw_envelope)
    raw_lower = envelope.get("lower_bounds")
    raw_upper = envelope.get("upper_bounds")
    if (
        isinstance(raw_lower, (str, bytes))
        or not isinstance(raw_lower, Sequence)
        or isinstance(raw_upper, (str, bytes))
        or not isinstance(raw_upper, Sequence)
    ):
        raise SourceUnavailableError("expected envelope bounds must be numeric arrays")
    lower = tuple(_numeric(value, "lower envelope bound") for value in raw_lower)
    upper = tuple(_numeric(value, "upper envelope bound") for value in raw_upper)
    if len(lower) != len(state.dimensions) or len(upper) != len(state.dimensions):
        raise SourceUnavailableError("expected envelope width differs from state vector")

    def outside(values: tuple[float, ...]) -> float:
        return max(
            0.0,
            *(low - value for low, value in zip(lower, values, strict=True)),
            *(value - high for value, high in zip(values, upper, strict=True)),
        )

    return SignalSeries(
        series_id="derived.envelope-error",
        unit=None,
        samples=tuple(
            NumericSample(sample.t_ns, outside(sample.values)) for sample in state.samples
        ),
    )


def _control_excursions(
    _context: SourceResolutionContext,
    dependencies: Mapping[str, object],
) -> object:
    channels = dependencies["U.channels"]
    if not isinstance(channels, Mapping) or "primary" not in channels:
        raise SourceUnavailableError("U.channels lacks the primary control")
    primary = signal_series(cast(Mapping[str, object], channels)["primary"])
    threshold = 0.05
    events: list[EventRecord] = []
    previous = 0.0
    for index, sample in enumerate(primary.samples):
        if abs(previous) <= threshold < abs(sample.value):
            events.append(
                EventRecord(
                    event_id=f"control-excursion-{index}",
                    event_type="control_excursion",
                    t_ns=sample.t_ns,
                    attributes={"threshold": threshold},
                )
            )
        previous = sample.value
    return tuple(events)


def register_hover_source_providers(registry: RuntimeSourceProviderRegistry) -> None:
    """Register ordinary starter adapters; they remain replaceable task content."""

    providers: tuple[RuntimeSourceProvider, ...] = (
        _raw_vector_provider(
            "X.state-vector",
            (
                "velocity.earth.x_m_s",
                "velocity.earth.y_m_s",
                "velocity.earth.z_m_s",
            ),
            ("x", "y", "z"),
            unit="m/s",
        ),
        _raw_vector_provider(
            "X.position-vector",
            (
                "position.earth.x_m",
                "position.earth.y_m",
                "position.earth.z_m",
            ),
            ("x", "y", "z"),
            unit="m",
        ),
        _raw_vector_provider(
            "X.hover-vector",
            (
                "velocity.earth.x_m_s",
                "velocity.earth.y_m_s",
                "velocity.earth.z_m_s",
            ),
            ("x", "y", "z"),
            unit="m/s",
        ),
        FunctionSourceProvider("U.channels", _u_bundle),
        FunctionSourceProvider("U.primary-control", _u_primary),
        FunctionSourceProvider("I.frames", _frame_records("I", "frame_index")),
        FunctionSourceProvider("G.frames", _gaze_frames),
        FunctionSourceProvider("EEG.channels", _eeg_bundle),
        FunctionSourceProvider("ECG.channels", _ecg_bundle),
        FunctionSourceProvider(
            "pilot_camera.frames",
            _frame_records("pilot_camera", "frame_index"),
        ),
        FunctionSourceProvider("session.duration-s", _duration),
        FunctionSourceProvider("task-reference.commanded-path", _commanded_path),
        FunctionSourceProvider("task-reference.expected-envelope", _expected_envelope),
        FunctionSourceProvider("task-reference.terminal-target", _terminal_target),
        _event_provider("semantic.attention-events", "visual_cue", "attention_cue"),
        _event_provider("semantic.disturbances", "disturbance"),
        FunctionSourceProvider("semantic.control-excursions", _control_excursions),
        FunctionSourceProvider("derived.flight-error", _flight_error),
        FunctionSourceProvider("derived.terminal-error", _terminal_error),
        FunctionSourceProvider("derived.envelope-error", _envelope_error),
    )
    for provider in providers:
        registry.register(provider)


__all__ = [
    "FunctionSourceProvider",
    "ResolvedRecipeInputs",
    "RuntimeSourceDiagnostic",
    "RuntimeSourceProvider",
    "RuntimeSourceProviderRegistry",
    "RuntimeSourceProviderRegistryError",
    "RuntimeSourceResolver",
    "SourceResolution",
    "SourceResolutionContext",
    "SourceResolutionStatus",
    "SourceUnavailableError",
    "register_hover_source_providers",
]
