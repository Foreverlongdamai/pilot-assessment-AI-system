from __future__ import annotations

from collections import deque
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
    EvidenceVersion,
    ModelScientificStatus,
)
from pilot_assessment.model_library.repository import (
    InMemoryComponentLibraryRepository,
    LibraryItemNotFoundError,
    LibraryQuery,
)
from pilot_assessment.model_library.service import ModelLibraryService


class FrozenClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


class SequenceIdFactory:
    def __init__(self, *values: str) -> None:
        self.values = deque(values)
        self.requested_kinds: list[ComponentKind] = []

    def new_id(self, kind: ComponentKind) -> str:
        self.requested_kinds.append(kind)
        return self.values.popleft()


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


def test_service_creates_same_name_concepts_and_parallel_versions_without_overwrite() -> None:
    clock = FrozenClock(datetime(2026, 7, 16, 12, 0, tzinfo=UTC))
    ids = SequenceIdFactory(
        "concept.trajectory-a",
        "concept.trajectory-b",
        "evidence-version.v1",
        "evidence-version.v2",
    )
    service = ModelLibraryService(InMemoryComponentLibraryRepository(), clock=clock, ids=ids)
    first_concept = service.create_evidence_concept(
        name="Trajectory deviation",
        description="First expert meaning.",
        tags=("trajectory",),
    )
    second_concept = service.create_evidence_concept(
        name="Trajectory deviation",
        description="A different expert meaning may share the display name.",
        tags=("trajectory",),
    )
    payload = {
        "concept_id": first_concept.concept_id,
        "recipe": _recipe(),
        "scientific_status": ModelScientificStatus.EXPERT_DEFINED,
    }
    first = service.create_version(
        ComponentKind.EVIDENCE_VERSION,
        payload,
        created_by="expert.one",
        note="Initial version.",
    )
    clock.value += timedelta(hours=1)
    second = service.create_version(
        ComponentKind.EVIDENCE_VERSION,
        payload,
        created_by="expert.two",
        source_version_ids=("evidence-version.v1",),
        note="Parallel revision.",
    )

    assert first_concept.concept_id != second_concept.concept_id
    assert isinstance(first, EvidenceVersion)
    assert isinstance(second, EvidenceVersion)
    assert first.evidence_version_id == "evidence-version.v1"
    assert second.evidence_version_id == "evidence-version.v2"
    assert first.content_hash == second.content_hash
    assert service.get_exact(ComponentKind.EVIDENCE_VERSION, first.evidence_version_id) == first
    assert service.get_exact(ComponentKind.EVIDENCE_VERSION, second.evidence_version_id) == second
    assert ids.requested_kinds == [
        ComponentKind.EVIDENCE_CONCEPT,
        ComponentKind.EVIDENCE_CONCEPT,
        ComponentKind.EVIDENCE_VERSION,
        ComponentKind.EVIDENCE_VERSION,
    ]


def test_service_exposes_exact_lineage_archive_and_filtered_list_but_no_latest_resolution() -> None:
    clock = FrozenClock(datetime(2026, 7, 16, 12, 0, tzinfo=UTC))
    service = ModelLibraryService(
        InMemoryComponentLibraryRepository(),
        clock=clock,
        ids=SequenceIdFactory("concept.trajectory", "evidence-version.v1"),
    )
    concept = service.create_evidence_concept(
        name="Trajectory deviation",
        description="Reusable concept.",
        tags=("trajectory", "control"),
    )
    version = service.create_version(
        ComponentKind.EVIDENCE_VERSION,
        {
            "concept_id": concept.concept_id,
            "recipe": _recipe(),
            "scientific_status": ModelScientificStatus.EXPERT_DEFINED,
        },
        created_by="expert.one",
        source_version_ids=("imported.m4r-version",),
        note="Imported and made explicit.",
    )
    assert isinstance(version, EvidenceVersion)

    lineage = service.get_lineage(ComponentKind.EVIDENCE_VERSION, version.evidence_version_id)
    assert lineage is not None
    assert lineage.source_version_ids == ("imported.m4r-version",)
    clock.value += timedelta(minutes=5)
    metadata = service.archive(
        ComponentKind.EVIDENCE_VERSION,
        version.evidence_version_id,
        changed_by="expert.one",
        reason="Not selected for new schemes.",
    )

    assert metadata.lifecycle is ComponentLifecycle.ARCHIVED
    assert service.get_exact(ComponentKind.EVIDENCE_VERSION, version.evidence_version_id) == version
    assert [
        record.record_id
        for record in service.list_records(
            LibraryQuery(
                kind=ComponentKind.EVIDENCE_VERSION,
                lifecycle=ComponentLifecycle.ARCHIVED,
                tags=("control",),
            )
        )
    ] == [version.evidence_version_id]
    assert not hasattr(service, "get_latest")
    assert not hasattr(service, "resolve_latest")
    with pytest.raises(LibraryItemNotFoundError):
        service.get_exact(ComponentKind.EVIDENCE_VERSION, "evidence-version.missing")
