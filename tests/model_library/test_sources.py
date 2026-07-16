from __future__ import annotations

import pytest

from pilot_assessment.contracts.evidence_recipe import (
    PortCardinality,
    PortType,
    TemporalSemantics,
)
from pilot_assessment.contracts.model_components import RawModality, SourceKind
from pilot_assessment.model_library.sources import (
    SourceCatalog,
    SourceCatalogError,
    SourceDiagnosticCode,
    create_source_descriptor,
    load_hover_source_catalog,
    source_descriptor_content_hash,
)


def _type(
    value_type: str,
    *,
    temporal: TemporalSemantics = TemporalSemantics.SAMPLED,
) -> PortType:
    return PortType(
        value_type=value_type,
        cardinality=PortCardinality.ONE,
        temporal_semantics=temporal,
        unit=None,
    )


def _source(
    source_id: str,
    kind: SourceKind,
    *,
    dependencies: tuple[str, ...] = (),
    raw_modality: RawModality | None = None,
    declared_type: PortType | None = None,
):
    return create_source_descriptor(
        source_id=source_id,
        kind=kind,
        name=source_id,
        description="Test-only source descriptor.",
        declared_type=declared_type or _type("number"),
        raw_modality=raw_modality,
        source_dependencies=dependencies,
        metadata={"scientific_status": "test_only"},
    )


def test_raw_session_and_task_sources_are_valid_provenance_roots() -> None:
    catalog = SourceCatalog(
        (
            _source("X.position", SourceKind.RAW_STREAM, raw_modality=RawModality.X),
            _source(
                "session.duration",
                SourceKind.SESSION_SEMANTIC,
                declared_type=_type("number", temporal=TemporalSemantics.TIMELESS),
            ),
            _source("task.commanded-path", SourceKind.TASK_SEMANTIC),
        )
    )

    report = catalog.validate_extraction_sources(
        ("X.position", "session.duration", "task.commanded-path")
    )

    assert report.compatible
    assert report.diagnostics == ()
    assert report.root_source_ids == (
        "X.position",
        "session.duration",
        "task.commanded-path",
    )
    assert report.raw_modalities == (RawModality.X,)


def test_derived_source_must_close_recursively_to_legal_roots() -> None:
    catalog = SourceCatalog(
        (
            _source("X.position", SourceKind.RAW_STREAM, raw_modality=RawModality.X),
            _source("task.commanded-path", SourceKind.TASK_SEMANTIC),
            _source(
                "derived.flight-error",
                SourceKind.DERIVED_ARTIFACT,
                dependencies=("X.position", "task.commanded-path"),
            ),
        )
    )

    report = catalog.validate_extraction_sources(("derived.flight-error",))

    assert report.compatible
    assert report.resolved_source_ids == (
        "derived.flight-error",
        "X.position",
        "task.commanded-path",
    )
    assert report.root_source_ids == ("X.position", "task.commanded-path")


def test_unknown_dependency_is_rejected_with_a_structured_source_path() -> None:
    catalog = SourceCatalog(
        (
            _source(
                "derived.flight-error",
                SourceKind.DERIVED_ARTIFACT,
                dependencies=("missing.position",),
            ),
        )
    )

    report = catalog.validate_extraction_sources(("derived.flight-error",))

    assert not report.compatible
    assert len(report.diagnostics) == 1
    diagnostic = report.diagnostics[0]
    assert diagnostic.code is SourceDiagnosticCode.UNKNOWN_SOURCE
    assert diagnostic.source_id == "missing.position"
    assert diagnostic.source_path == ("derived.flight-error", "missing.position")


def test_provenance_cycle_is_rejected_with_the_closed_cycle_path() -> None:
    catalog = SourceCatalog(
        (
            _source(
                "derived.a",
                SourceKind.DERIVED_ARTIFACT,
                dependencies=("derived.b",),
            ),
            _source(
                "derived.b",
                SourceKind.DERIVED_ARTIFACT,
                dependencies=("derived.a",),
            ),
        )
    )

    report = catalog.validate_extraction_sources(("derived.a",))

    assert not report.compatible
    assert report.diagnostics[0].code is SourceDiagnosticCode.PROVENANCE_CYCLE
    assert report.diagnostics[0].source_path == (
        "derived.a",
        "derived.b",
        "derived.a",
    )


def test_evidence_observation_namespace_is_classified_but_rejected_for_extraction() -> None:
    report = SourceCatalog().validate_extraction_sources(("anchor.O1-score",))

    assert not report.compatible
    assert report.diagnostics[0].code is SourceDiagnosticCode.EVIDENCE_OBSERVATION_INPUT
    assert report.diagnostics[0].source_id == "anchor.O1-score"
    assert report.diagnostics[0].source_path == ("anchor.O1-score",)


def test_root_sources_cannot_hide_dependencies_and_derived_sources_need_dependencies() -> None:
    with pytest.raises(SourceCatalogError, match="root source.*dependencies"):
        SourceCatalog(
            (
                _source(
                    "task.bad-root",
                    SourceKind.TASK_SEMANTIC,
                    dependencies=("X.position",),
                ),
            )
        )

    report = SourceCatalog(
        (_source("derived.unclosed", SourceKind.DERIVED_ARTIFACT),)
    ).validate_extraction_sources(("derived.unclosed",))
    assert not report.compatible
    assert report.diagnostics[0].code is SourceDiagnosticCode.DERIVED_SOURCE_WITHOUT_DEPENDENCIES


def test_hover_source_resource_has_explicit_typed_provenance_and_valid_identity() -> None:
    catalog = load_hover_source_catalog()

    assert catalog.get("semantic.disturbances").kind is SourceKind.TASK_SEMANTIC
    assert catalog.get("semantic.control-excursions").source_dependencies == ("U.channels",)
    assert catalog.get("derived.flight-error").source_dependencies == (
        "X.position-vector",
        "task-reference.commanded-path",
    )
    assert catalog.get("I.frames").raw_modality is RawModality.I
    assert catalog.get("pilot_camera.frames").raw_modality is RawModality.PILOT_CAMERA
    for descriptor in catalog.descriptors():
        assert descriptor.content_hash == source_descriptor_content_hash(descriptor)
