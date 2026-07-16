from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pilot_assessment.contracts.assessment_scheme import (
    AssessmentSchemeVersion,
    CoverageReportingPolicyVersion,
    DraftComponentCandidate,
    DraftDiagnostic,
    DraftDiagnosticSeverity,
    DraftValidationState,
    LayoutGroup,
    LayoutVersion,
    NodePosition,
    SchemeDraft,
    TaskProfileVersion,
    Viewport,
)
from pilot_assessment.contracts.bayesian import BayesianDependencyEdge, ExtractionEdge
from pilot_assessment.contracts.model_components import (
    ComponentIdRef,
    ComponentKind,
    ComponentSource,
    PinnedComponentRef,
    VersionLineage,
)

SHA_A = "a" * 64
SHA_B = "b" * 64


def _lineage() -> VersionLineage:
    return VersionLineage(
        source_version_ids=(),
        created_at=datetime(2026, 7, 16, 12, 0, tzinfo=UTC),
        created_by="expert.one",
        note=None,
    )


def _pinned(kind: ComponentKind, version_id: str, content_hash: str = SHA_A):
    return PinnedComponentRef(
        kind=kind,
        version_id=version_id,
        content_hash=content_hash,
    )


def _task_profile() -> TaskProfileVersion:
    return TaskProfileVersion(
        task_profile_version_id="task-profile.hover-v1",
        task_concept_id="task.hover",
        name="Hover",
        description="Editable task profile.",
        task_semantics={"task_kind": "hover", "expected_duration_s": 30.0},
        required_source_descriptor_ids=("X.state-vector", "U.channels"),
        reference_parameters={"expected_envelope_id": "hover-envelope-v1"},
        annotation_parameters={"required_phase_kinds": ["hover"]},
        aoi_parameters={},
        source=ComponentSource.ENGINEERING_DEFAULT,
        lineage=_lineage(),
        content_hash=SHA_A,
    )


def _policy() -> CoverageReportingPolicyVersion:
    return CoverageReportingPolicyVersion(
        policy_version_id="reporting-policy.hover-v1",
        applicability_rules={"missing_task_semantics": "not_applicable"},
        coverage_rules={"report_modalities": True},
        output_rules={"include_trace": True},
        source=ComponentSource.ENGINEERING_DEFAULT,
        lineage=_lineage(),
        content_hash=SHA_A,
    )


def _layout() -> LayoutVersion:
    return LayoutVersion(
        layout_version_id="layout.hover-v1",
        node_positions=(
            NodePosition(node_id="raw.X", x=10.0, y=20.0),
            NodePosition(node_id="evidence.trajectory", x=200.0, y=20.0),
        ),
        groups=(
            LayoutGroup(
                group_id="group.inputs",
                label="Inputs",
                node_ids=("raw.X",),
                metadata={"collapsed": False},
            ),
        ),
        viewport=Viewport(x=0.0, y=0.0, zoom=1.0),
        lineage=_lineage(),
        content_hash=SHA_A,
    )


def _scheme() -> AssessmentSchemeVersion:
    task = _pinned(ComponentKind.TASK_PROFILE_VERSION, "task-profile.hover-v1")
    evidence = _pinned(
        ComponentKind.EVIDENCE_VERSION,
        "evidence-version.trajectory-v1",
    )
    binding = _pinned(
        ComponentKind.EVIDENCE_BINDING_VERSION,
        "binding.trajectory-v1",
    )
    bn = _pinned(ComponentKind.BN_NODE_VERSION, "bn-version.skill-v1")
    cpt = _pinned(ComponentKind.CPT_VERSION, "cpt.skill-v1")
    source = _pinned(ComponentKind.SOURCE_DESCRIPTOR, "X.state-vector")
    policy = _pinned(
        ComponentKind.COVERAGE_REPORTING_POLICY_VERSION,
        "reporting-policy.hover-v1",
    )
    layout = _pinned(ComponentKind.LAYOUT_VERSION, "layout.hover-v1")
    return AssessmentSchemeVersion(
        scheme_version_id="scheme.hover-v1",
        scheme_concept_id="scheme-concept.hover",
        name="Hover starter",
        description="Editable starter assessment scheme.",
        task_profile=task,
        source_descriptors=(source,),
        evidence_versions=(evidence,),
        evidence_binding_versions=(binding,),
        bn_node_versions=(bn,),
        cpt_versions=(cpt,),
        reporting_policy=policy,
        layout=layout,
        output_node_ids=(
            ComponentIdRef(
                kind=ComponentKind.BN_NODE_VERSION,
                version_id="bn-version.skill-v1",
            ),
        ),
        lineage=_lineage(),
        content_hash=SHA_B,
    )


def test_task_policy_and_layout_are_strict_frozen_round_trip_contracts() -> None:
    task = _task_profile()
    policy = _policy()
    layout = _layout()

    assert TaskProfileVersion.model_validate_json(task.model_dump_json()) == task
    assert CoverageReportingPolicyVersion.model_validate_json(policy.model_dump_json()) == policy
    assert LayoutVersion.model_validate_json(layout.model_dump_json()) == layout
    with pytest.raises(TypeError):
        task.task_semantics["task_kind"] = "changed"
    with pytest.raises(TypeError):
        policy.coverage_rules["report_modalities"] = False
    with pytest.raises(TypeError):
        layout.groups[0].metadata["collapsed"] = True
    with pytest.raises(ValidationError):
        LayoutVersion.model_validate(
            {**layout.model_dump(), "viewport": {"x": 0.0, "y": 0.0, "zoom": float("nan")}}
        )
    with pytest.raises(ValidationError):
        TaskProfileVersion.model_validate({**task.model_dump(), "unknown": "field"})


def test_scheme_uses_kind_checked_exact_pins_and_unique_versions() -> None:
    scheme = _scheme()

    assert AssessmentSchemeVersion.model_validate_json(scheme.model_dump_json()) == scheme
    assert scheme.task_profile.content_hash == SHA_A
    with pytest.raises(ValidationError, match="task profile"):
        AssessmentSchemeVersion.model_validate(
            {
                **scheme.model_dump(),
                "task_profile": _pinned(
                    ComponentKind.EVIDENCE_VERSION,
                    "evidence-version.not-a-task",
                ),
            }
        )
    with pytest.raises(ValidationError, match="duplicate"):
        AssessmentSchemeVersion.model_validate(
            {
                **scheme.model_dump(),
                "evidence_versions": (
                    scheme.evidence_versions[0],
                    scheme.evidence_versions[0],
                ),
            }
        )
    with pytest.raises(ValidationError, match="output"):
        AssessmentSchemeVersion.model_validate(
            {
                **scheme.model_dump(),
                "output_node_ids": (
                    ComponentIdRef(
                        kind=ComponentKind.CPT_VERSION,
                        version_id="cpt.not-output",
                    ),
                ),
            }
        )


def test_incomplete_scheme_draft_is_saveable_and_recursively_frozen() -> None:
    candidate = DraftComponentCandidate(
        kind=ComponentKind.BN_NODE_VERSION,
        candidate_id="candidate.bn-new",
        base_version_id=None,
        payload={"ordered_states": [], "documentation": {"note": "unfinished"}},
    )
    diagnostic = DraftDiagnostic(
        code="draft-incomplete",
        severity=DraftDiagnosticSeverity.WARNING,
        location="/candidate_components/0/payload/ordered_states",
        component_id="candidate.bn-new",
        message="State space is incomplete.",
    )
    draft = SchemeDraft(
        draft_id="draft.hover-edit",
        base_scheme_version_id="scheme.hover-v1",
        graph_version=0,
        layout_version=0,
        history_cursor=0,
        retained_component_refs=(),
        candidate_components=(candidate,),
        extraction_edges=(),
        bayesian_edges=(),
        output_node_ids=(),
        validation_state=DraftValidationState.INCOMPLETE,
        diagnostics=(diagnostic,),
    )

    assert SchemeDraft.model_validate_json(draft.model_dump_json()) == draft
    with pytest.raises(TypeError):
        candidate.payload["ordered_states"] = ["desired"]
    nested = candidate.payload["documentation"]
    assert isinstance(nested, dict)
    with pytest.raises(TypeError):
        nested["note"] = "changed"
    with pytest.raises(ValidationError):
        SchemeDraft.model_validate({**draft.model_dump(), "graph_version": True})
    with pytest.raises(ValidationError):
        DraftComponentCandidate.model_validate(
            {**candidate.model_dump(), "payload": {"value": float("inf")}}
        )


def test_draft_preserves_typed_extraction_and_bayesian_edges() -> None:
    extraction = ExtractionEdge(
        edge_id="edge.raw-to-evidence",
        source_descriptor_id="X.state-vector",
        target_evidence_version_id="candidate.evidence",
        input_binding_id="input.state",
    )
    bayesian = BayesianDependencyEdge(
        edge_id="edge.skill-to-evidence",
        parent_variable_id=ComponentIdRef(
            kind=ComponentKind.BN_NODE_VERSION,
            version_id="candidate.skill",
        ),
        child_variable_id=ComponentIdRef(
            kind=ComponentKind.EVIDENCE_BINDING_VERSION,
            version_id="candidate.binding",
        ),
    )
    draft = SchemeDraft(
        draft_id="draft.edges",
        base_scheme_version_id=None,
        graph_version=2,
        layout_version=1,
        history_cursor=2,
        retained_component_refs=(),
        candidate_components=(),
        extraction_edges=(extraction,),
        bayesian_edges=(bayesian,),
        output_node_ids=(),
        validation_state=DraftValidationState.INCOMPLETE,
        diagnostics=(),
    )

    assert draft.extraction_edges[0].edge_kind == "extraction"
    assert draft.bayesian_edges[0].edge_kind == "bayesian_dependency"
    with pytest.raises(ValidationError):
        SchemeDraft.model_validate(
            {
                **draft.model_dump(),
                "extraction_edges": (bayesian.model_dump(),),
            }
        )
