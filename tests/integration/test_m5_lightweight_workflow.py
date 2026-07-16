from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from pilot_assessment.contracts.bayesian import Observation, ObservationKind
from pilot_assessment.contracts.model_components import (
    ComponentIdRef,
    ComponentKind,
    CptMode,
    CptVersion,
    EvidenceBindingVersion,
    EvidenceVersion,
)
from pilot_assessment.evidence.builtins import register_builtin_operators
from pilot_assessment.evidence.registry import OperatorRegistry
from pilot_assessment.model_library.migration import load_hover_evidence_inventory
from pilot_assessment.model_library.profile import (
    LoadedModelProfile,
    load_hover_starter_package,
)
from pilot_assessment.model_library.repository import (
    InMemoryComponentLibraryRepository,
    LibraryItemNotFoundError,
)
from pilot_assessment.schemes.operations import (
    CloneComponentVersion,
    ReplaceCptProbabilities,
    ReplaceEvidenceRecipe,
)
from pilot_assessment.schemes.repository import (
    InMemorySchemeDraftRepository,
    InMemoryWorkspaceUnitOfWork,
)
from pilot_assessment.schemes.service import (
    SchemePublicationError,
    SchemeWorkspaceService,
)

NOW = datetime(2026, 7, 16, 20, 0, tzinfo=UTC)


class FrozenClock:
    def now(self) -> datetime:
        return NOW


class SequenceIds:
    def __init__(self, *values: str) -> None:
        self._values = deque(values)
        self.requested: list[ComponentKind] = []

    def new_id(self, kind: ComponentKind) -> str:
        self.requested.append(kind)
        return self._values.popleft()


@dataclass(frozen=True, slots=True)
class Workspace:
    profile: LoadedModelProfile
    repository: InMemoryComponentLibraryRepository
    service: SchemeWorkspaceService
    ids: SequenceIds


def _workspace(
    *,
    failure_hook: Callable[[str], None] | None = None,
) -> Workspace:
    profile = load_hover_starter_package()
    repository = profile.to_repository(recorded_at=NOW)
    drafts = InMemorySchemeDraftRepository(clock=FrozenClock().now)
    ids = SequenceIds(
        "evidence-version.task-demo.O2.v1",
        "evidence-binding-version.task-demo.O2.v1",
        "cpt-version.task-demo.O2.v1",
        "assessment-scheme-version.task-demo.v1",
    )
    registry = OperatorRegistry()
    register_builtin_operators(registry)
    service = SchemeWorkspaceService(
        repository,
        drafts,
        InMemoryWorkspaceUnitOfWork(
            repository,
            drafts,
            failure_hook=failure_hook,
        ),
        source_catalog=profile.source_catalog,
        operator_registry=registry,
        clock=FrozenClock(),
        ids=ids,
    )
    return Workspace(profile=profile, repository=repository, service=service, ids=ids)


def _selected_o2(
    profile: LoadedModelProfile,
) -> tuple[
    EvidenceVersion,
    EvidenceBindingVersion,
    CptVersion,
]:
    evidence = next(
        item
        for item in profile.library_items
        if isinstance(item, EvidenceVersion) and item.recipe.anchor.anchor_id == "O2"
    )
    binding = next(
        item
        for item in profile.library_items
        if isinstance(item, EvidenceBindingVersion)
        and item.evidence_version_id.version_id == evidence.evidence_version_id
    )
    cpt = next(
        item
        for item in profile.library_items
        if isinstance(item, CptVersion) and item.cpt_version_id == binding.cpt_version_id.version_id
    )
    return evidence, binding, cpt


def _stage_parallel_o2(workspace: Workspace, *, draft_id: str):
    evidence, binding, cpt = _selected_o2(workspace.profile)
    draft = workspace.service.create_draft_from_scheme(
        workspace.profile.scheme.scheme_version_id,
        draft_id=draft_id,
        author_id="expert.demo",
    ).draft
    for source, candidate_id in (
        (
            ComponentIdRef(
                kind=ComponentKind.EVIDENCE_VERSION,
                version_id=evidence.evidence_version_id,
            ),
            "candidate.evidence.O2",
        ),
        (
            ComponentIdRef(
                kind=ComponentKind.EVIDENCE_BINDING_VERSION,
                version_id=binding.evidence_binding_version_id,
            ),
            "candidate.binding.O2",
        ),
        (
            ComponentIdRef(
                kind=ComponentKind.CPT_VERSION,
                version_id=cpt.cpt_version_id,
            ),
            "candidate.cpt.O2",
        ),
    ):
        draft = workspace.service.apply_operation(
            draft.draft_id,
            CloneComponentVersion(
                expected_graph_version=draft.graph_version,
                source=source,
                candidate_id=candidate_id,
                replace_source=True,
            ),
            author_id="expert.demo",
        ).draft

    changed_nodes = tuple(
        node.model_copy(update={"parameters": {"percentile": 95.0}})
        if node.node_id == "peak-error"
        else node
        for node in evidence.recipe.graph.nodes
    )
    changed_recipe = evidence.recipe.model_copy(
        update={
            "graph": evidence.recipe.graph.model_copy(update={"nodes": changed_nodes}),
            "documentation": evidence.recipe.documentation.model_copy(
                update={
                    "summary": (
                        "Task-demo parallel version using an expert-editable 95th percentile."
                    )
                }
            ),
        }
    )
    draft = workspace.service.apply_operation(
        draft.draft_id,
        ReplaceEvidenceRecipe(
            expected_graph_version=draft.graph_version,
            candidate_id="candidate.evidence.O2",
            recipe=changed_recipe,
        ),
        author_id="expert.demo",
    ).draft
    changed_rows = ((0.75, 0.22, 0.03), *cpt.materialized_probabilities[1:])
    return workspace.service.apply_operation(
        draft.draft_id,
        ReplaceCptProbabilities(
            expected_graph_version=draft.graph_version,
            candidate_id="candidate.cpt.O2",
            probabilities=changed_rows,
        ),
        author_id="expert.demo",
    ).draft


def _observations(profile: LoadedModelProfile) -> tuple[Observation, ...]:
    h4 = next(
        item
        for item in profile.library_items
        if isinstance(item, EvidenceBindingVersion)
        and item.evidence_binding_version_id.endswith(".H4.v1")
    )
    return (
        Observation(
            variable_id=ComponentIdRef(
                kind=ComponentKind.EVIDENCE_BINDING_VERSION,
                version_id="candidate.binding.O2",
            ),
            kind=ObservationKind.HARD,
            hard_state_id="desired",
            likelihood=None,
        ),
        Observation(
            variable_id=ComponentIdRef(
                kind=ComponentKind.EVIDENCE_BINDING_VERSION,
                version_id=h4.evidence_binding_version_id,
            ),
            kind=ObservationKind.VIRTUAL,
            hard_state_id=None,
            likelihood=(0.2, 0.5, 0.3),
        ),
    )


def test_preview_publish_and_parallel_scheme_replay_are_one_lightweight_workflow() -> None:
    workspace = _workspace()
    old_scheme = workspace.profile.scheme
    draft = _stage_parallel_o2(workspace, draft_id="draft.task-demo")

    preview = workspace.service.preview(
        draft.draft_id,
        expected_graph_version=draft.graph_version,
        expected_layout_version=draft.layout_version,
        observations=_observations(workspace.profile),
        query_node_ids=draft.output_node_ids,
    )

    assert preview.graph_version == draft.graph_version
    assert preview.layout_version == draft.layout_version
    assert preview.draft_hash
    assert len(preview.plan.variables) == 33
    assert len(preview.posterior.posteriors) == 4
    assert preview.trace.influence_edges
    assert workspace.ids.requested == []
    with pytest.raises(LibraryItemNotFoundError):
        workspace.repository.get_exact(
            ComponentKind.EVIDENCE_VERSION,
            "candidate.evidence.O2",
        )
    with pytest.raises(SchemePublicationError, match="revision"):
        workspace.service.preview(
            draft.draft_id,
            expected_graph_version=draft.graph_version - 1,
            expected_layout_version=draft.layout_version,
            observations=(),
            query_node_ids=draft.output_node_ids,
        )

    published = workspace.service.publish(
        draft.draft_id,
        expected_graph_version=draft.graph_version,
        expected_layout_version=draft.layout_version,
        author_id="expert.demo",
        note="Parallel task-demo scheme; starter remains unchanged.",
    )

    assert published.scheme.scheme_version_id == "assessment-scheme-version.task-demo.v1"
    assert [reference.kind for reference in published.new_component_refs] == [
        ComponentKind.EVIDENCE_VERSION,
        ComponentKind.EVIDENCE_BINDING_VERSION,
        ComponentKind.CPT_VERSION,
    ]
    assert old_scheme.evidence_versions == workspace.profile.scheme.evidence_versions
    old_replay = workspace.service.replay_exact(old_scheme.scheme_version_id)
    new_replay = workspace.service.replay_exact(published.scheme.scheme_version_id)
    assert old_replay.scheme == old_scheme
    assert old_replay.scheme.evidence_versions != new_replay.scheme.evidence_versions
    new_cpt = next(
        item
        for item in new_replay.components
        if isinstance(item, CptVersion) and item.cpt_version_id == "cpt-version.task-demo.O2.v1"
    )
    assert new_cpt.mode is CptMode.MANUAL

    migration = load_hover_evidence_inventory()
    assert len(migration.legacy_artifacts) == 1
    assert migration.legacy_artifacts[0].compatibility.legacy_only
    assert migration.legacy_artifacts[0].recipe.recipe_id == "starter.o8"
    assert all(
        reference.version_id != "starter.o8" for reference in published.scheme.evidence_versions
    )
    assert not any(
        isinstance(item, EvidenceVersion) and item.recipe.recipe_id == "starter.o8"
        for item in new_replay.components
    )


def test_failure_before_commit_leaves_no_parallel_components_or_scheme() -> None:
    def fail(stage: str) -> None:
        if stage == "before_commit":
            raise RuntimeError("injected atomic failure")

    workspace = _workspace(failure_hook=fail)
    draft = _stage_parallel_o2(workspace, draft_id="draft.failure-demo")

    with pytest.raises(RuntimeError, match="injected atomic failure"):
        workspace.service.publish(
            draft.draft_id,
            expected_graph_version=draft.graph_version,
            expected_layout_version=draft.layout_version,
            author_id="expert.demo",
        )

    for kind, version_id in (
        (ComponentKind.EVIDENCE_VERSION, "evidence-version.task-demo.O2.v1"),
        (
            ComponentKind.EVIDENCE_BINDING_VERSION,
            "evidence-binding-version.task-demo.O2.v1",
        ),
        (ComponentKind.CPT_VERSION, "cpt-version.task-demo.O2.v1"),
        (
            ComponentKind.ASSESSMENT_SCHEME_VERSION,
            "assessment-scheme-version.task-demo.v1",
        ),
    ):
        with pytest.raises(LibraryItemNotFoundError):
            workspace.repository.get_exact(kind, version_id)
