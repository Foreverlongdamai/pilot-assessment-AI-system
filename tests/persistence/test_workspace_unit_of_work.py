from __future__ import annotations

from dataclasses import dataclass

import pytest

from pilot_assessment.contracts.model_components import ComponentIdRef, ComponentKind
from pilot_assessment.model_library.repository import LibraryItemNotFoundError
from pilot_assessment.persistence.database import ProjectDatabase
from pilot_assessment.persistence.draft_repository import (
    SqliteSchemeDraftRepository,
    SqliteWorkspaceUnitOfWork,
)
from pilot_assessment.persistence.model_repository import SqliteComponentLibraryRepository
from pilot_assessment.schemes.operations import CloneComponentVersion, ReplaceReportingPolicyRules
from pilot_assessment.schemes.service import SchemeWorkspaceService
from tests.schemes.support import NOW, SchemeFixture, build_fixture
from tests.schemes.workspace_support import FrozenClock, SequenceIdFactory


@dataclass(frozen=True, slots=True)
class DurableWorkspace:
    components: SqliteComponentLibraryRepository
    drafts: SqliteSchemeDraftRepository
    uow: SqliteWorkspaceUnitOfWork
    service: SchemeWorkspaceService


def _workspace(
    database: ProjectDatabase,
    fixture: SchemeFixture,
    *,
    ids: SequenceIdFactory,
    failure_hook=None,
    seed: bool = True,
) -> DurableWorkspace:
    components = SqliteComponentLibraryRepository(database)
    if seed:
        for item in (*fixture.components, fixture.scheme):
            components.add(item, recorded_at=NOW)
    clock = FrozenClock(NOW)
    drafts = SqliteSchemeDraftRepository(database, clock=clock.now)
    uow = SqliteWorkspaceUnitOfWork(
        database,
        components,
        drafts,
        failure_hook=failure_hook,
    )
    service = SchemeWorkspaceService(
        components,
        drafts,
        uow,
        source_catalog=fixture.source_catalog,
        operator_registry=fixture.operator_registry,
        clock=clock,
        ids=ids,
    )
    return DurableWorkspace(components, drafts, uow, service)


def _edited_policy(workspace: DurableWorkspace, fixture: SchemeFixture):
    draft = workspace.service.create_draft_from_scheme(
        fixture.scheme.scheme_version_id,
        draft_id="draft.publish-policy",
        author_id="expert.one",
    ).draft
    draft = workspace.service.apply_operation(
        draft.draft_id,
        CloneComponentVersion(
            expected_graph_version=0,
            source=ComponentIdRef(
                kind=fixture.scheme.reporting_policy.kind,
                version_id=fixture.scheme.reporting_policy.version_id,
            ),
            candidate_id="candidate.policy",
            replace_source=True,
        ),
        author_id="expert.one",
    ).draft
    return workspace.service.apply_operation(
        draft.draft_id,
        ReplaceReportingPolicyRules(
            expected_graph_version=1,
            candidate_id="candidate.policy",
            applicability_rules={"task": "generic"},
            coverage_rules={"report_modalities": True},
            output_rules={"include_trace": True},
        ),
        author_id="expert.one",
    ).draft


def test_atomic_publish_persists_components_scheme_and_rebased_draft(tmp_path) -> None:
    fixture = build_fixture()
    path = tmp_path / "project.sqlite3"
    database = ProjectDatabase.connect(path, clock=lambda: NOW)
    workspace = _workspace(
        database,
        fixture,
        ids=SequenceIdFactory("policy.generic-v4", "scheme-version.generic-v12"),
    )
    draft = _edited_policy(workspace, fixture)

    published = workspace.service.publish(
        draft.draft_id,
        expected_graph_version=2,
        expected_layout_version=0,
        author_id="expert.one",
        note="Parallel task policy.",
    )
    assert published.scheme.scheme_version_id == "scheme-version.generic-v12"
    assert (
        workspace.components.get_exact(
            ComponentKind.COVERAGE_REPORTING_POLICY_VERSION, "policy.generic-v4"
        ).content_hash
        == published.scheme.reporting_policy.content_hash
    )
    rebased = workspace.drafts.get(draft.draft_id)
    assert rebased.draft.base_scheme_version_id == published.scheme.scheme_version_id
    assert rebased.draft.history_cursor == 0
    database.close()

    reopened_database = ProjectDatabase.connect(path, clock=lambda: NOW)
    try:
        reopened = _workspace(
            reopened_database,
            fixture,
            ids=SequenceIdFactory(),
            seed=False,
        )
        assert (
            reopened.components.get_exact(
                ComponentKind.ASSESSMENT_SCHEME_VERSION,
                published.scheme.scheme_version_id,
            )
            == published.scheme
        )
        assert reopened.drafts.get(draft.draft_id).draft == rebased.draft
    finally:
        reopened_database.close()


def test_failure_hook_rolls_back_components_scheme_and_draft_rebase(tmp_path) -> None:
    def fail_before_commit(stage: str) -> None:
        if stage == "before_commit":
            raise RuntimeError("injected publication failure")

    fixture = build_fixture()
    database = ProjectDatabase.connect(tmp_path / "project.sqlite3", clock=lambda: NOW)
    workspace = _workspace(
        database,
        fixture,
        ids=SequenceIdFactory("policy.generic-v4", "scheme-version.generic-v12"),
        failure_hook=fail_before_commit,
    )
    draft = _edited_policy(workspace, fixture)
    before = workspace.drafts.get(draft.draft_id)
    try:
        with pytest.raises(RuntimeError, match="injected"):
            workspace.service.publish(
                draft.draft_id,
                expected_graph_version=2,
                expected_layout_version=0,
                author_id="expert.one",
            )
        for kind, record_id in (
            (ComponentKind.COVERAGE_REPORTING_POLICY_VERSION, "policy.generic-v4"),
            (ComponentKind.ASSESSMENT_SCHEME_VERSION, "scheme-version.generic-v12"),
        ):
            with pytest.raises(LibraryItemNotFoundError):
                workspace.components.get_exact(kind, record_id)
        assert workspace.drafts.get(draft.draft_id) == before
    finally:
        database.close()
