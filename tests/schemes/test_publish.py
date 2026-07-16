from __future__ import annotations

import pytest

from pilot_assessment.contracts.model_components import ComponentIdRef, ComponentKind
from pilot_assessment.model_library.repository import LibraryItemNotFoundError
from pilot_assessment.schemes.operations import (
    CloneComponentVersion,
    ReplaceReportingPolicyRules,
    SetOutputNodes,
)
from pilot_assessment.schemes.repository import InMemoryWorkspaceUnitOfWork
from pilot_assessment.schemes.service import SchemePublicationError
from tests.schemes.support import build_fixture
from tests.schemes.workspace_support import SequenceIdFactory, build_workspace


def _edited_policy_workspace(*, failure_hook=None):
    fixture = build_fixture()
    ids = SequenceIdFactory("policy.generic-v4", "scheme-version.generic-v12")
    workspace = build_workspace(fixture, ids=ids, failure_hook=failure_hook)
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
    draft = workspace.service.apply_operation(
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
    return fixture, workspace, draft


def test_publish_creates_only_changed_versions_and_new_scheme_then_replays_exactly() -> None:
    fixture, workspace, draft = _edited_policy_workspace()
    before = fixture.repository.get_exact(
        ComponentKind.ASSESSMENT_SCHEME_VERSION,
        fixture.scheme.scheme_version_id,
    )

    published = workspace.service.publish(
        draft.draft_id,
        expected_graph_version=2,
        expected_layout_version=0,
        author_id="expert.one",
        note="Parallel task policy.",
    )

    assert [item.kind for item in published.new_component_refs] == [
        ComponentKind.COVERAGE_REPORTING_POLICY_VERSION
    ]
    assert published.scheme.scheme_version_id == "scheme-version.generic-v12"
    assert published.scheme.reporting_policy.version_id == "policy.generic-v4"
    assert (
        fixture.repository.get_exact(
            ComponentKind.ASSESSMENT_SCHEME_VERSION,
            fixture.scheme.scheme_version_id,
        )
        == before
    )
    replay = workspace.service.replay_exact(published.scheme.scheme_version_id)
    assert replay.scheme == published.scheme
    assert {
        (reference.kind, reference.version_id, reference.content_hash)
        for reference in replay.component_refs
    } == {
        (reference.kind, reference.version_id, reference.content_hash)
        for reference in (
            published.scheme.task_profile,
            *published.scheme.source_descriptors,
            *published.scheme.evidence_versions,
            *published.scheme.evidence_binding_versions,
            *published.scheme.bn_node_versions,
            *published.scheme.cpt_versions,
            published.scheme.reporting_policy,
            published.scheme.layout,
        )
    }


def test_failure_injection_leaves_no_partial_component_or_scheme() -> None:
    def fail_before_commit(stage: str) -> None:
        if stage == "before_commit":
            raise RuntimeError("injected publication failure")

    fixture, workspace, draft = _edited_policy_workspace(failure_hook=fail_before_commit)
    with pytest.raises(RuntimeError, match="injected"):
        workspace.service.publish(
            draft.draft_id,
            expected_graph_version=2,
            expected_layout_version=0,
            author_id="expert.one",
        )

    with pytest.raises(LibraryItemNotFoundError):
        fixture.repository.get_exact(
            ComponentKind.COVERAGE_REPORTING_POLICY_VERSION,
            "policy.generic-v4",
        )
    with pytest.raises(LibraryItemNotFoundError):
        fixture.repository.get_exact(
            ComponentKind.ASSESSMENT_SCHEME_VERSION,
            "scheme-version.generic-v12",
        )
    assert isinstance(workspace.uow, InMemoryWorkspaceUnitOfWork)


def test_incomplete_draft_cannot_publish_and_consumes_no_ids() -> None:
    fixture = build_fixture()
    ids = SequenceIdFactory("scheme-version.must-not-be-consumed")
    workspace = build_workspace(fixture, ids=ids)
    draft = workspace.service.create_draft_from_scheme(
        fixture.scheme.scheme_version_id,
        draft_id="draft.incomplete-publish",
        author_id="expert.one",
    ).draft
    draft = workspace.service.apply_operation(
        draft.draft_id,
        SetOutputNodes(expected_graph_version=0, output_node_ids=()),
        author_id="expert.one",
    ).draft

    with pytest.raises(SchemePublicationError):
        workspace.service.publish(
            draft.draft_id,
            expected_graph_version=1,
            expected_layout_version=0,
            author_id="expert.one",
        )
    assert ids.requested_kinds == []
