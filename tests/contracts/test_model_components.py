from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pilot_assessment.contracts.evidence_recipe import (
    EvidenceRecipe,
    PortCardinality,
    PortType,
    RecipeAnchor,
    RecipeDocumentation,
    RecipeGraph,
    RecipeLifecycle,
    RecipeScientificStatus,
    RecipeUiMetadata,
    TemporalSemantics,
)
from pilot_assessment.contracts.model_components import (
    BnNodeConcept,
    BnNodeRole,
    BnNodeVersion,
    ComponentIdRef,
    ComponentKind,
    ComponentLifecycle,
    ComponentSource,
    CptMode,
    CptVersion,
    EvidenceBindingVersion,
    EvidenceConcept,
    EvidenceVersion,
    ModelScientificStatus,
    ObservationPolicy,
    PinnedComponentRef,
    RawModality,
    SourceDescriptor,
    SourceKind,
    VariableState,
    VersionLineage,
)

SHA_A = "a" * 64
SHA_B = "b" * 64


def _lineage(*source_ids: str) -> VersionLineage:
    return VersionLineage(
        source_version_ids=source_ids,
        created_at=datetime(2026, 7, 16, 12, 0, tzinfo=UTC),
        created_by="expert.one",
        note="starter lineage",
    )


def _recipe() -> EvidenceRecipe:
    return EvidenceRecipe(
        recipe_id="recipe.trajectory-deviation",
        recipe_version=1,
        anchor=RecipeAnchor(
            anchor_id="evidence.trajectory-deviation",
            name="Trajectory deviation",
            description="Editable starter computation.",
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


def _states() -> tuple[VariableState, ...]:
    return (
        VariableState(state_id="unacceptable", label="Unacceptable", description="Low"),
        VariableState(state_id="adequate", label="Adequate", description="Middle"),
        VariableState(state_id="desired", label="Desired", description="High"),
    )


def _ref(kind: ComponentKind, version_id: str) -> ComponentIdRef:
    return ComponentIdRef(kind=kind, version_id=version_id)


def test_concepts_are_strict_frozen_and_allow_parallel_names() -> None:
    evidence = EvidenceConcept(
        concept_id="concept.trajectory-deviation",
        name="Trajectory deviation",
        description="A reusable evidence concept.",
        tags=("trajectory", "control"),
        lifecycle=ComponentLifecycle.ACTIVE,
    )
    same_name_other_concept = EvidenceConcept(
        concept_id="concept.trajectory-deviation-alt",
        name=evidence.name,
        description="A scientifically different concept may share a label.",
        tags=(),
        lifecycle=ComponentLifecycle.ACTIVE,
    )
    bn = BnNodeConcept(
        concept_id="concept.task-control",
        name="Task Control",
        description="Aggregate competency.",
        node_role=BnNodeRole.AGGREGATE_COMPETENCY,
        tags=("competency",),
        lifecycle=ComponentLifecycle.ACTIVE,
    )

    assert EvidenceConcept.model_validate_json(evidence.model_dump_json()) == evidence
    assert same_name_other_concept.concept_id != evidence.concept_id
    assert bn.node_role is BnNodeRole.AGGREGATE_COMPETENCY
    with pytest.raises(ValidationError):
        evidence.name = "changed"  # ty: ignore[invalid-assignment]
    with pytest.raises(ValidationError):
        EvidenceConcept(
            concept_id="bad concept",
            name="Bad",
            description="",
            tags=("duplicate", "duplicate"),
            lifecycle=ComponentLifecycle.ACTIVE,
        )
    with pytest.raises(ValidationError):
        EvidenceConcept.model_validate({**evidence.model_dump(), "unexpected": True})


def test_evidence_and_bn_versions_use_exact_id_only_internal_refs() -> None:
    evidence = EvidenceVersion(
        evidence_version_id="evidence-version.hover-v1",
        concept_id="concept.trajectory-deviation",
        recipe=_recipe(),
        scientific_status=ModelScientificStatus.ENGINEERING_DEFAULT,
        lineage=_lineage(),
        content_hash=SHA_A,
    )
    parent = _ref(ComponentKind.BN_NODE_VERSION, "bn-version.task-control-v1")
    node = BnNodeVersion(
        bn_node_version_id="bn-version.trajectory-tracking-v1",
        concept_id="concept.trajectory-tracking",
        ordered_states=_states(),
        ordered_probabilistic_parent_ids=(parent,),
        cpt_version_id=_ref(ComponentKind.CPT_VERSION, "cpt.trajectory-tracking-v1"),
        documentation="Editable starter node.",
        scientific_status=ModelScientificStatus.ENGINEERING_DEFAULT,
        lineage=_lineage("bn-version.trajectory-tracking-v0"),
        content_hash=SHA_B,
    )

    assert EvidenceVersion.model_validate_json(evidence.model_dump_json()) == evidence
    assert BnNodeVersion.model_validate_json(node.model_dump_json()) == node
    assert set(parent.model_dump()) == {"kind", "version_id"}
    with pytest.raises(ValidationError):
        ComponentIdRef.model_validate(
            {"kind": "bn_node_version", "version_id": "bn.v1", "content_hash": SHA_A}
        )
    with pytest.raises(ValidationError, match="state IDs"):
        BnNodeVersion.model_validate(
            {
                **node.model_dump(),
                "ordered_states": (node.ordered_states[0], node.ordered_states[0]),
            }
        )
    with pytest.raises(ValidationError, match="parent"):
        BnNodeVersion.model_validate(
            {
                **node.model_dump(),
                "ordered_probabilistic_parent_ids": (
                    _ref(ComponentKind.CPT_VERSION, "cpt.not-a-variable"),
                ),
            }
        )


def test_pinned_refs_require_exact_hashes_and_reject_invalid_ids() -> None:
    pinned = PinnedComponentRef(
        kind=ComponentKind.EVIDENCE_VERSION,
        version_id="evidence-version.hover-v1",
        content_hash=SHA_A.upper(),
    )

    assert pinned.content_hash == SHA_A
    with pytest.raises(ValidationError):
        PinnedComponentRef.model_validate(
            {"kind": "evidence_version", "version_id": "bad id", "content_hash": SHA_A}
        )
    with pytest.raises(ValidationError):
        PinnedComponentRef.model_validate({"kind": "evidence_version", "version_id": "evidence.v1"})


def test_evidence_binding_freezes_mapping_and_validates_weights() -> None:
    binding = EvidenceBindingVersion(
        evidence_binding_version_id="binding.trajectory-deviation-v1",
        evidence_version_id=_ref(ComponentKind.EVIDENCE_VERSION, "evidence-version.hover-v1"),
        ordered_observation_states=_states(),
        observation_mapping={"mode": "ordered_dau", "thresholds": [0.2, 0.8]},
        ordered_probabilistic_parent_ids=(
            _ref(ComponentKind.BN_NODE_VERSION, "bn-version.trajectory-tracking-v1"),
        ),
        cpt_version_id=_ref(ComponentKind.CPT_VERSION, "cpt.binding-v1"),
        observation_policy=ObservationPolicy.HARD_OR_VIRTUAL,
        modality_attribution_weights={"X": 0.75, "U": 0.25},
        lineage=_lineage(),
        content_hash=SHA_A,
    )

    assert EvidenceBindingVersion.model_validate_json(binding.model_dump_json()) == binding
    with pytest.raises(TypeError):
        binding.observation_mapping["mode"] = "changed"
    with pytest.raises(TypeError):
        binding.modality_attribution_weights["X"] = 1.0
    with pytest.raises(ValidationError, match="sum to 1"):
        EvidenceBindingVersion.model_validate(
            {
                **binding.model_dump(),
                "modality_attribution_weights": {"X": 0.8, "U": 0.3},
            }
        )
    with pytest.raises(ValidationError):
        EvidenceBindingVersion.model_validate(
            {
                **binding.model_dump(),
                "modality_attribution_weights": {"X": float("nan")},
            }
        )


def test_cpt_and_source_descriptor_are_canonical_frozen_snapshots() -> None:
    cpt = CptVersion(
        cpt_version_id="cpt.task-control-v1",
        child_variable_id=_ref(ComponentKind.BN_NODE_VERSION, "bn-version.task-control-v1"),
        ordered_parent_variable_ids=(),
        child_state_ids=("unacceptable", "adequate", "desired"),
        ordered_parent_state_ids=(),
        materialized_probabilities=((0.2, 0.3, 0.5),),
        mode=CptMode.MANUAL,
        generator_metadata={"note": ["editable"]},
        source=ComponentSource.ENGINEERING_DEFAULT,
        lineage=_lineage(),
        content_hash=SHA_A,
    )
    descriptor = SourceDescriptor(
        source_id="X.state-vector",
        kind=SourceKind.RAW_STREAM,
        name="Flight state",
        description="Aligned simulator flight-state input.",
        declared_type=PortType(
            value_type="flight-state-table",
            cardinality=PortCardinality.ONE,
            temporal_semantics=TemporalSemantics.SAMPLED,
            unit=None,
        ),
        raw_modality=RawModality.X,
        source_dependencies=(),
        metadata={"table_role": "samples"},
        content_hash=SHA_B,
    )

    assert CptVersion.model_validate_json(cpt.model_dump_json()) == cpt
    assert SourceDescriptor.model_validate_json(descriptor.model_dump_json()) == descriptor
    with pytest.raises(TypeError):
        cpt.generator_metadata["note"] = []
    with pytest.raises(TypeError):
        descriptor.metadata["table_role"] = "other"
    with pytest.raises(ValidationError):
        CptVersion.model_validate(
            {
                **cpt.model_dump(),
                "materialized_probabilities": ((float("nan"), 0.0, 1.0),),
            }
        )
    with pytest.raises(ValidationError, match="child state IDs"):
        CptVersion.model_validate(
            {
                **cpt.model_dump(),
                "child_state_ids": ("desired", "desired"),
            }
        )
    with pytest.raises(ValidationError, match="source dependencies"):
        SourceDescriptor.model_validate(
            {
                **descriptor.model_dump(),
                "source_dependencies": ("X.state-vector", "X.state-vector"),
            }
        )


def test_m5_contracts_are_available_from_the_public_contract_package() -> None:
    import pilot_assessment.contracts as contracts

    assert contracts.EvidenceConcept is EvidenceConcept
    assert contracts.CptVersion is CptVersion
    assert contracts.SourceDescriptor is SourceDescriptor
    assert contracts.InferencePlan.__name__ == "InferencePlan"
    assert contracts.AssessmentSchemeVersion.__name__ == "AssessmentSchemeVersion"
