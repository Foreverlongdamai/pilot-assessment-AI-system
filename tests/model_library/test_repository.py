from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pilot_assessment.contracts.evidence_recipe import (
    EvidenceRecipe,
    RecipeAnchor,
    RecipeDocumentation,
    RecipeGraph,
    RecipeLifecycle,
    RecipeScientificStatus,
    RecipeUiMetadata,
)
from pilot_assessment.contracts.model_components import (
    ComponentKind,
    ComponentLifecycle,
    EvidenceConcept,
    EvidenceVersion,
    ModelScientificStatus,
    VersionLineage,
)
from pilot_assessment.model_library.repository import (
    ComponentHashMismatchError,
    DuplicateLibraryItemError,
    InMemoryComponentLibraryRepository,
    LibraryItemNotFoundError,
    LibraryQuery,
    component_content_hash,
)
from pilot_assessment.model_library.sources import load_hover_source_catalog

ZERO_HASH = "0" * 64
NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def _recipe() -> EvidenceRecipe:
    return EvidenceRecipe(
        recipe_id="recipe.trajectory-deviation",
        recipe_version=1,
        anchor=RecipeAnchor(
            anchor_id="evidence.trajectory-deviation",
            name="Trajectory deviation",
            description="Editable computation.",
            lifecycle=RecipeLifecycle.ACTIVE,
            scientific_status=RecipeScientificStatus.STARTER_TEMPLATE,
        ),
        inputs=(),
        graph=RecipeGraph(nodes=(), edges=()),
        outputs=(),
        scoring=None,
        documentation=RecipeDocumentation(
            summary="Starter only.", assumptions=(), parameter_notes={}, references=()
        ),
        ui=RecipeUiMetadata(groups=(), preferred_layout={}),
    )


def _concept(concept_id: str, *, name: str = "Trajectory deviation") -> EvidenceConcept:
    return EvidenceConcept(
        concept_id=concept_id,
        name=name,
        description="Reusable Evidence concept.",
        tags=("trajectory", "control"),
        lifecycle=ComponentLifecycle.ACTIVE,
    )


def _version(
    version_id: str,
    concept_id: str,
    *,
    created_at: datetime = NOW,
    source_ids: tuple[str, ...] = (),
) -> EvidenceVersion:
    provisional = EvidenceVersion(
        evidence_version_id=version_id,
        concept_id=concept_id,
        recipe=_recipe(),
        scientific_status=ModelScientificStatus.ENGINEERING_DEFAULT,
        lineage=VersionLineage(
            source_version_ids=source_ids,
            created_at=created_at,
            created_by="expert.one",
            note="parallel version",
        ),
        content_hash=ZERO_HASH,
    )
    return provisional.model_copy(update={"content_hash": component_content_hash(provisional)})


def test_repository_keeps_exact_immutable_records_and_rejects_duplicate_ids() -> None:
    repository = InMemoryComponentLibraryRepository()
    concept = _concept("concept.trajectory")
    version = _version("evidence-version.v1", concept.concept_id)

    repository.add(concept, recorded_at=NOW)
    repository.add(version, recorded_at=NOW)

    stored = repository.get_exact(ComponentKind.EVIDENCE_VERSION, version.evidence_version_id)
    assert stored == version
    assert stored is not version
    with pytest.raises(DuplicateLibraryItemError):
        repository.add(version, recorded_at=NOW)
    with pytest.raises(LibraryItemNotFoundError):
        repository.get_exact(ComponentKind.EVIDENCE_VERSION, "evidence-version.missing")


def test_repository_allows_parallel_versions_and_stably_sorts_without_latest_selection() -> None:
    repository = InMemoryComponentLibraryRepository()
    concept = _concept("concept.trajectory")
    later = _version("evidence-version.z", concept.concept_id, created_at=NOW + timedelta(hours=1))
    earlier_b = _version("evidence-version.b", concept.concept_id)
    earlier_a = _version("evidence-version.a", concept.concept_id)
    repository.add(concept, recorded_at=NOW - timedelta(hours=1))
    repository.add(later, recorded_at=later.lineage.created_at)
    repository.add(earlier_b, recorded_at=earlier_b.lineage.created_at)
    repository.add(earlier_a, recorded_at=earlier_a.lineage.created_at)

    records = repository.list_records(
        LibraryQuery(
            kind=ComponentKind.EVIDENCE_VERSION,
            concept_id=concept.concept_id,
        )
    )

    assert [record.record_id for record in records] == [
        "evidence-version.a",
        "evidence-version.b",
        "evidence-version.z",
    ]
    assert not hasattr(repository, "get_latest")
    assert not hasattr(repository, "resolve_latest")


def test_repository_filters_by_kind_concept_lifecycle_and_inherited_concept_tags() -> None:
    repository = InMemoryComponentLibraryRepository()
    trajectory = _concept("concept.trajectory")
    same_name = _concept("concept.trajectory-other")
    first = _version("evidence-version.v1", trajectory.concept_id)
    second = _version("evidence-version.v2", same_name.concept_id)
    for item in (trajectory, same_name, first, second):
        repository.add(item, recorded_at=NOW)
    repository.set_lifecycle(
        ComponentKind.EVIDENCE_VERSION,
        first.evidence_version_id,
        lifecycle=ComponentLifecycle.ARCHIVED,
        changed_at=NOW + timedelta(minutes=1),
        changed_by="expert.one",
        reason="Superseded for new schemes, retained for replay.",
    )

    archived = repository.list_records(
        LibraryQuery(
            kind=ComponentKind.EVIDENCE_VERSION,
            concept_id=trajectory.concept_id,
            lifecycle=ComponentLifecycle.ARCHIVED,
            tags=("trajectory",),
        )
    )

    assert [record.record_id for record in archived] == [first.evidence_version_id]
    assert archived[0].metadata.changed_by == "expert.one"
    assert archived[0].metadata.reason == "Superseded for new schemes, retained for replay."
    assert repository.get_exact(ComponentKind.EVIDENCE_VERSION, first.evidence_version_id) == first


def test_repository_recomputes_content_hash_and_rejects_false_claims() -> None:
    repository = InMemoryComponentLibraryRepository()
    valid = _version("evidence-version.v1", "concept.trajectory")
    false_claim = valid.model_copy(update={"content_hash": "f" * 64})

    with pytest.raises(ComponentHashMismatchError, match="content hash"):
        repository.add(false_claim, recorded_at=NOW)


def test_version_hash_excludes_outer_version_identity_and_lineage_audit_fields() -> None:
    first = _version("evidence-version.v1", "concept.trajectory", created_at=NOW)
    second = _version(
        "evidence-version.v2",
        "concept.trajectory",
        created_at=NOW + timedelta(days=1),
        source_ids=(first.evidence_version_id,),
    )

    assert first.content_hash == second.content_hash


def test_repository_accepts_task3_source_descriptor_identity_without_rewriting_it() -> None:
    repository = InMemoryComponentLibraryRepository()
    descriptor = load_hover_source_catalog().get("G.frames")

    repository.add(descriptor, recorded_at=NOW)

    assert repository.get_exact(ComponentKind.SOURCE_DESCRIPTOR, "G.frames") == descriptor
