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
    LibraryItemNotFoundError,
    LibraryQuery,
    component_content_hash,
)
from pilot_assessment.persistence.database import ProjectDatabase, encode_canonical_json
from pilot_assessment.persistence.model_repository import SqliteComponentLibraryRepository

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)
ZERO_HASH = "0" * 64


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


def _concept(concept_id: str) -> EvidenceConcept:
    return EvidenceConcept(
        concept_id=concept_id,
        name="Trajectory deviation",
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


def test_repository_persists_exact_immutable_records_across_reopen(tmp_path) -> None:
    path = tmp_path / "project.sqlite3"
    database = ProjectDatabase.connect(path, clock=lambda: NOW)
    concept = _concept("concept.trajectory")
    version = _version("evidence-version.v1", concept.concept_id)
    repository = SqliteComponentLibraryRepository(database)
    repository.add(concept, recorded_at=NOW)
    repository.add(version, recorded_at=NOW)

    assert (
        repository.get_exact(ComponentKind.EVIDENCE_VERSION, version.evidence_version_id) == version
    )
    with pytest.raises(DuplicateLibraryItemError):
        repository.add(version, recorded_at=NOW)
    database.close()

    reopened_database = ProjectDatabase.connect(path, clock=lambda: NOW)
    try:
        reopened = SqliteComponentLibraryRepository(reopened_database)
        stored = reopened.get_exact(ComponentKind.EVIDENCE_VERSION, version.evidence_version_id)
        assert stored == version
        assert stored is not version
        with pytest.raises(LibraryItemNotFoundError):
            reopened.get_exact(ComponentKind.EVIDENCE_VERSION, "evidence-version.missing")
    finally:
        reopened_database.close()


def test_repository_stably_lists_parallel_versions_and_independent_lifecycle(tmp_path) -> None:
    database = ProjectDatabase.connect(tmp_path / "project.sqlite3", clock=lambda: NOW)
    repository = SqliteComponentLibraryRepository(database)
    concept = _concept("concept.trajectory")
    later = _version(
        "evidence-version.z",
        concept.concept_id,
        created_at=NOW + timedelta(hours=1),
    )
    earlier_b = _version("evidence-version.b", concept.concept_id)
    earlier_a = _version("evidence-version.a", concept.concept_id)
    try:
        repository.add(concept, recorded_at=NOW - timedelta(hours=1))
        repository.add(later, recorded_at=later.lineage.created_at)
        repository.add(earlier_b, recorded_at=earlier_b.lineage.created_at)
        repository.add(earlier_a, recorded_at=earlier_a.lineage.created_at)
        repository.set_lifecycle(
            ComponentKind.EVIDENCE_VERSION,
            earlier_b.evidence_version_id,
            lifecycle=ComponentLifecycle.ARCHIVED,
            changed_at=NOW + timedelta(minutes=1),
            changed_by="expert.one",
            reason="Retained for replay but not selected for new schemes.",
        )

        records = repository.list_records(
            LibraryQuery(
                kind=ComponentKind.EVIDENCE_VERSION,
                concept_id=concept.concept_id,
                tags=("control",),
            )
        )
        assert [record.record_id for record in records] == [
            "evidence-version.a",
            "evidence-version.b",
            "evidence-version.z",
        ]
        assert records[0].tags == concept.tags
        assert records[1].metadata.lifecycle is ComponentLifecycle.ARCHIVED
        assert (
            repository.get_exact(ComponentKind.EVIDENCE_VERSION, earlier_b.evidence_version_id)
            == earlier_b
        )
        assert (
            repository.get_lineage(ComponentKind.EVIDENCE_VERSION, earlier_b.evidence_version_id)
            == earlier_b.lineage
        )
        assert not hasattr(repository, "get_latest")
        assert not hasattr(repository, "resolve_latest")
    finally:
        database.close()


def test_repository_rejects_false_hash_and_detects_tampered_stored_json(tmp_path) -> None:
    database = ProjectDatabase.connect(tmp_path / "project.sqlite3", clock=lambda: NOW)
    repository = SqliteComponentLibraryRepository(database)
    version = _version("evidence-version.v1", "concept.trajectory")
    try:
        with pytest.raises(ComponentHashMismatchError):
            repository.add(version.model_copy(update={"content_hash": "f" * 64}), recorded_at=NOW)

        repository.add(version, recorded_at=NOW)
        tampered = version.model_dump(mode="json")
        tampered["recipe"]["anchor"]["name"] = "Tampered"
        database.execute(
            """
            UPDATE library_records SET canonical_json = ?
            WHERE kind = ? AND record_id = ?
            """,
            (
                encode_canonical_json(tampered),
                ComponentKind.EVIDENCE_VERSION.value,
                version.evidence_version_id,
            ),
        )

        with pytest.raises(ComponentHashMismatchError, match="content hash"):
            repository.get_exact(ComponentKind.EVIDENCE_VERSION, version.evidence_version_id)
    finally:
        database.close()
