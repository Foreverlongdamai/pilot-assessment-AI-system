from __future__ import annotations

from pilot_assessment.contracts.bayesian import BayesianDependencyEdge, ExtractionEdge
from pilot_assessment.contracts.evidence_recipe import ScoringMode
from pilot_assessment.contracts.model_components import (
    ComponentIdRef,
    ComponentKind,
    EvidenceVersion,
    VariableState,
)
from pilot_assessment.schemes.operations import (
    AddBayesianDependency,
    AddExistingComponent,
    AddExtractionDependency,
    CloneComponentVersion,
    RemoveBayesianDependency,
    RemoveComponent,
    RemoveExtractionDependency,
    ReplaceBnStates,
    ReplaceCptProbabilities,
    ReplaceEvidenceRecipe,
    ReplaceEvidenceScoring,
    StageNewComponentVersion,
)
from tests.schemes.support import NOW, build_fixture
from tests.schemes.workspace_support import build_workspace


def test_create_draft_projects_exact_scheme_edges_and_clone_is_copy_on_write() -> None:
    fixture = build_fixture()
    workspace = build_workspace(fixture)

    created = workspace.service.create_draft_from_scheme(
        fixture.scheme.scheme_version_id,
        draft_id="draft.generic-edit",
        author_id="expert.one",
    )
    original_evidence = fixture.scheme.evidence_versions[0]
    cloned = workspace.service.apply_operation(
        created.draft.draft_id,
        CloneComponentVersion(
            expected_graph_version=0,
            source=ComponentIdRef(
                kind=ComponentKind.EVIDENCE_VERSION,
                version_id=original_evidence.version_id,
            ),
            candidate_id="candidate.evidence.metric-v8",
            replace_source=True,
        ),
        author_id="expert.one",
    )

    assert len(created.draft.extraction_edges) == 2
    assert len(created.draft.bayesian_edges) == 1
    assert cloned.draft.graph_version == 1
    assert cloned.draft.validation_state.value == "incomplete"
    assert original_evidence not in cloned.draft.retained_component_refs
    candidate = cloned.draft.candidate_components[0]
    assert candidate.base_version_id == original_evidence.version_id
    assert candidate.payload["evidence_version_id"] == candidate.candidate_id
    stored_evidence = fixture.repository.get_exact(
        ComponentKind.EVIDENCE_VERSION,
        original_evidence.version_id,
    )
    assert isinstance(stored_evidence, EvidenceVersion)
    assert stored_evidence.content_hash == original_evidence.content_hash


def test_typed_component_and_edge_commands_update_only_the_selected_draft_candidates() -> None:
    fixture = build_fixture()
    workspace = build_workspace(fixture)
    draft = workspace.service.create_draft_from_scheme(
        fixture.scheme.scheme_version_id,
        draft_id="draft.generic-typed-ops",
        author_id="expert.one",
    ).draft

    evidence_ref = fixture.scheme.evidence_versions[0]
    binding_ref = fixture.scheme.evidence_binding_versions[0]
    bn_ref = fixture.scheme.bn_node_versions[0]
    cpt_ref = fixture.scheme.cpt_versions[0]
    for reference, candidate_id in (
        (evidence_ref, "candidate.evidence"),
        (binding_ref, "candidate.binding"),
        (bn_ref, "candidate.bn"),
        (cpt_ref, "candidate.cpt"),
    ):
        draft = workspace.service.apply_operation(
            draft.draft_id,
            CloneComponentVersion(
                expected_graph_version=draft.graph_version,
                source=ComponentIdRef(
                    kind=reference.kind,
                    version_id=reference.version_id,
                ),
                candidate_id=candidate_id,
                replace_source=True,
            ),
            author_id="expert.one",
        ).draft

    stored_evidence = fixture.repository.get_exact(
        ComponentKind.EVIDENCE_VERSION,
        evidence_ref.version_id,
    )
    assert isinstance(stored_evidence, EvidenceVersion)
    changed_recipe = stored_evidence.recipe.model_copy(
        update={
            "documentation": stored_evidence.recipe.documentation.model_copy(
                update={"summary": "Expert edited."}
            )
        }
    )
    draft = workspace.service.apply_operation(
        draft.draft_id,
        ReplaceEvidenceRecipe(
            expected_graph_version=draft.graph_version,
            candidate_id="candidate.evidence",
            recipe=changed_recipe,
        ),
        author_id="expert.one",
    ).draft
    new_states = (
        VariableState(state_id="low", label="Low", description="Low state."),
        VariableState(state_id="high", label="High", description="High state."),
    )
    draft = workspace.service.apply_operation(
        draft.draft_id,
        ReplaceBnStates(
            expected_graph_version=draft.graph_version,
            candidate_id="candidate.bn",
            ordered_states=new_states,
        ),
        author_id="expert.one",
    ).draft
    draft = workspace.service.apply_operation(
        draft.draft_id,
        ReplaceCptProbabilities(
            expected_graph_version=draft.graph_version,
            candidate_id="candidate.cpt",
            probabilities=((0.6, 0.4),),
        ),
        author_id="expert.one",
    ).draft

    extraction = next(
        edge
        for edge in draft.extraction_edges
        if edge.target_evidence_version_id == "candidate.evidence"
        and edge.input_binding_id == "metric"
    )
    draft = workspace.service.apply_operation(
        draft.draft_id,
        RemoveExtractionDependency(
            expected_graph_version=draft.graph_version,
            edge_id=extraction.edge_id,
        ),
        author_id="expert.one",
    ).draft
    metric_binding = changed_recipe.inputs[0]
    draft = workspace.service.apply_operation(
        draft.draft_id,
        AddExtractionDependency(
            expected_graph_version=draft.graph_version,
            edge=ExtractionEdge(
                edge_id="edge.metric-restored",
                source_descriptor_id="X.metric",
                target_evidence_version_id="candidate.evidence",
                input_binding_id="metric",
            ),
            binding=metric_binding,
        ),
        author_id="expert.one",
    ).draft

    bayesian = draft.bayesian_edges[0]
    draft = workspace.service.apply_operation(
        draft.draft_id,
        RemoveBayesianDependency(
            expected_graph_version=draft.graph_version,
            edge_id=bayesian.edge_id,
        ),
        author_id="expert.one",
    ).draft
    draft = workspace.service.apply_operation(
        draft.draft_id,
        AddBayesianDependency(
            expected_graph_version=draft.graph_version,
            edge=BayesianDependencyEdge(
                edge_id="edge.bn-restored",
                parent_variable_id=ComponentIdRef(
                    kind=ComponentKind.BN_NODE_VERSION,
                    version_id="candidate.bn",
                ),
                child_variable_id=ComponentIdRef(
                    kind=ComponentKind.EVIDENCE_BINDING_VERSION,
                    version_id="candidate.binding",
                ),
            ),
        ),
        author_id="expert.one",
    ).draft

    candidates = {item.candidate_id: item for item in draft.candidate_components}
    recipe_payload = candidates["candidate.evidence"].payload["recipe"]
    assert isinstance(recipe_payload, dict)
    documentation = recipe_payload["documentation"]
    assert isinstance(documentation, dict)
    assert documentation["summary"] == "Expert edited."
    state_payload = candidates["candidate.bn"].payload["ordered_states"]
    assert isinstance(state_payload, list)
    assert isinstance(state_payload[1], dict)
    assert state_payload[1]["state_id"] == "high"
    assert candidates["candidate.cpt"].payload["materialized_probabilities"] == [[0.6, 0.4]]
    assert candidates["candidate.cpt"].payload["mode"] == "manual"
    assert any(edge.edge_id == "edge.metric-restored" for edge in draft.extraction_edges)
    assert any(edge.edge_id == "edge.bn-restored" for edge in draft.bayesian_edges)
    assert (
        fixture.repository.get_record(
            ComponentKind.EVIDENCE_VERSION,
            evidence_ref.version_id,
        ).metadata.created_at
        == NOW
    )


def test_exact_component_selection_and_scoring_have_dedicated_form_operations() -> None:
    fixture = build_fixture()
    workspace = build_workspace(fixture)
    draft = workspace.service.create_draft_from_scheme(
        fixture.scheme.scheme_version_id,
        draft_id="draft.selection-and-scoring",
        author_id="expert.one",
    ).draft
    selected_source = fixture.scheme.source_descriptors[0]
    draft = workspace.service.apply_operation(
        draft.draft_id,
        RemoveComponent(
            expected_graph_version=0,
            target=ComponentIdRef(
                kind=selected_source.kind,
                version_id=selected_source.version_id,
            ),
        ),
        author_id="expert.one",
    ).draft
    assert selected_source not in draft.retained_component_refs
    draft = workspace.service.apply_operation(
        draft.draft_id,
        AddExistingComponent(
            expected_graph_version=1,
            reference=selected_source,
        ),
        author_id="expert.one",
    ).draft
    evidence_ref = fixture.scheme.evidence_versions[0]
    draft = workspace.service.apply_operation(
        draft.draft_id,
        CloneComponentVersion(
            expected_graph_version=2,
            source=ComponentIdRef(
                kind=evidence_ref.kind,
                version_id=evidence_ref.version_id,
            ),
            candidate_id="candidate.scoring-form",
            replace_source=True,
        ),
        author_id="expert.one",
    ).draft
    stored = fixture.repository.get_exact(evidence_ref.kind, evidence_ref.version_id)
    assert isinstance(stored, EvidenceVersion)
    assert stored.recipe.scoring is not None
    changed_scoring = stored.recipe.scoring.model_copy(
        update={
            "mode": ScoringMode.ORDERED_DAU,
            "parameters": {
                **stored.recipe.scoring.parameters,
                "likelihood_strength": 0.35,
            },
        }
    )
    draft = workspace.service.apply_operation(
        draft.draft_id,
        ReplaceEvidenceScoring(
            expected_graph_version=3,
            candidate_id="candidate.scoring-form",
            scoring=changed_scoring,
        ),
        author_id="expert.one",
    ).draft

    assert selected_source in draft.retained_component_refs
    candidate = next(
        item for item in draft.candidate_components if item.candidate_id == "candidate.scoring-form"
    )
    recipe = candidate.payload["recipe"]
    assert isinstance(recipe, dict)
    scoring = recipe["scoring"]
    assert isinstance(scoring, dict)
    parameters = scoring["parameters"]
    assert isinstance(parameters, dict)
    assert parameters["likelihood_strength"] == 0.35

    staged = workspace.service.apply_operation(
        draft.draft_id,
        StageNewComponentVersion(
            expected_graph_version=4,
            kind=ComponentKind.EVIDENCE_VERSION,
            candidate_id="candidate.brand-new-evidence",
            payload={},
        ),
        author_id="expert.one",
    )
    assert staged.draft.validation_state.value == "incomplete"
    new_candidate = next(
        item
        for item in staged.draft.candidate_components
        if item.candidate_id == "candidate.brand-new-evidence"
    )
    assert new_candidate.base_version_id is None
