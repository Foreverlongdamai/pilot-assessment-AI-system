from __future__ import annotations

from dataclasses import dataclass

import pytest

from pilot_assessment.contracts.assessment_scheme import TaskProfileVersion
from pilot_assessment.contracts.evidence_recipe import (
    PortCardinality,
    PortType,
    TemporalSemantics,
)
from pilot_assessment.contracts.model_components import SourceKind
from pilot_assessment.contracts.synchronization import SessionWindow
from pilot_assessment.model_library.profile import load_hover_starter_package
from pilot_assessment.model_library.sources import SourceCatalog, create_source_descriptor
from pilot_assessment.runtime.sources import (
    RuntimeSourceProviderRegistry,
    RuntimeSourceProviderRegistryError,
    RuntimeSourceResolver,
    SourceResolutionContext,
    SourceResolutionStatus,
    register_hover_source_providers,
)
from pilot_assessment.synchronization.models import AlignedAnnotations, AlignedSession


def _number_type() -> PortType:
    return PortType(
        value_type="number",
        cardinality=PortCardinality.ONE,
        temporal_semantics=TemporalSemantics.TIMELESS,
        unit=None,
    )


def _profile_task() -> TaskProfileVersion:
    profile = load_hover_starter_package()
    item = next(item for item in profile.library_items if isinstance(item, TaskProfileVersion))
    return item


def _context() -> SourceResolutionContext:
    aligned = AlignedSession(
        session_id="session.alpha",
        window=SessionWindow(
            end_t_ns=1_000_000_000,
            source="master-clock-x-mapped-coverage-v1",
        ),
        streams={},
        context={},
        annotations=AlignedAnnotations(
            revision="annotations.v1",
            phases=(),
            events=(),
            baseline_intervals=(),
            source_schema_ids={},
            synthetic_semantics_unvalidated=False,
        ),
        task_reference=None,
        source_snapshot_fingerprint="a" * 64,
        synchronization_fingerprint="b" * 64,
    )
    return SourceResolutionContext(
        aligned_session=aligned,
        task_profile=_profile_task(),
        runtime_parameters={},
    )


@dataclass
class _Provider:
    source_id: str
    value: int
    calls: list[str]

    def provide(self, context, dependencies):
        del context
        self.calls.append(self.source_id)
        return self.value + sum(int(value) for value in dependencies.values())


def test_registry_resolves_dependency_topology_once_per_run_and_rejects_duplicates() -> None:
    root = create_source_descriptor(
        source_id="root.value",
        kind=SourceKind.SESSION_SEMANTIC,
        name="Root",
        description="Test root",
        declared_type=_number_type(),
    )
    derived = create_source_descriptor(
        source_id="derived.value",
        kind=SourceKind.DERIVED_ARTIFACT,
        name="Derived",
        description="Test derived",
        declared_type=_number_type(),
        source_dependencies=(root.source_id,),
    )
    catalog = SourceCatalog((derived, root))
    calls: list[str] = []
    registry = RuntimeSourceProviderRegistry()
    registry.register(_Provider(root.source_id, 40, calls))
    registry.register(_Provider(derived.source_id, 2, calls))
    with pytest.raises(RuntimeSourceProviderRegistryError, match="already registered"):
        registry.register(_Provider(root.source_id, 99, calls))

    resolver = RuntimeSourceResolver(catalog, registry, _context())
    first = resolver.resolve(derived.source_id)
    second = resolver.resolve(derived.source_id)

    assert first.status is SourceResolutionStatus.AVAILABLE
    assert first.value == 42
    assert second is first
    assert calls == [root.source_id, derived.source_id]


def test_unknown_missing_provider_and_missing_modality_are_structured_not_bad_performance() -> None:
    profile = load_hover_starter_package()
    registry = RuntimeSourceProviderRegistry()
    register_hover_source_providers(registry)
    assert set(registry.source_ids()) == {
        descriptor.source_id for descriptor in profile.source_catalog.descriptors()
    }

    resolver = RuntimeSourceResolver(profile.source_catalog, registry, _context())
    duration = resolver.resolve("session.duration-s")
    missing_stream = resolver.resolve("X.state-vector")
    unknown = resolver.resolve("not.registered")

    assert duration.status is SourceResolutionStatus.AVAILABLE
    assert duration.value == 1.0
    assert missing_stream.status is SourceResolutionStatus.OMITTED
    assert {item.code for item in missing_stream.diagnostics} == {"runtime.source_unavailable"}
    assert unknown.status is SourceResolutionStatus.ERROR
    assert {item.code for item in unknown.diagnostics} == {"runtime.source_unknown"}

    root_only = SourceCatalog(
        (
            create_source_descriptor(
                source_id="root.unimplemented",
                kind=SourceKind.SESSION_SEMANTIC,
                name="Root",
                description="No runtime provider",
                declared_type=_number_type(),
            ),
        )
    )
    no_provider = RuntimeSourceResolver(
        root_only,
        RuntimeSourceProviderRegistry(),
        _context(),
    ).resolve("root.unimplemented")
    assert no_provider.status is SourceResolutionStatus.ERROR
    assert {item.code for item in no_provider.diagnostics} == {"runtime.source_provider_missing"}
