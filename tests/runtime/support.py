from __future__ import annotations

from datetime import datetime

from pilot_assessment.contracts.assessment_scheme import AssessmentSchemeVersion
from pilot_assessment.contracts.model_components import (
    BnNodeVersion,
    ComponentKind,
    CptVersion,
    EvidenceBindingVersion,
    EvidenceVersion,
    PinnedComponentRef,
    VersionLineage,
)
from pilot_assessment.model_library.repository import component_content_hash
from pilot_assessment.runtime import ProjectApplication

ZERO_HASH = "0" * 64


def _pin(item) -> PinnedComponentRef:
    identity = {
        EvidenceVersion: (ComponentKind.EVIDENCE_VERSION, "evidence_version_id"),
        EvidenceBindingVersion: (
            ComponentKind.EVIDENCE_BINDING_VERSION,
            "evidence_binding_version_id",
        ),
        BnNodeVersion: (ComponentKind.BN_NODE_VERSION, "bn_node_version_id"),
        CptVersion: (ComponentKind.CPT_VERSION, "cpt_version_id"),
    }[type(item)]
    return PinnedComponentRef(
        kind=identity[0],
        version_id=getattr(item, identity[1]),
        content_hash=item.content_hash,
    )


def minimal_o1_scheme(
    application: ProjectApplication,
    *,
    scheme_version_id: str,
    scheme_concept_id: str,
    name: str,
    created_at: datetime,
) -> AssessmentSchemeVersion:
    """Build a test-only one-Evidence projection of the editable starter scheme."""

    starter = application.system.components.get_exact(
        ComponentKind.ASSESSMENT_SCHEME_VERSION,
        application.starter_scheme_id,
    )
    assert isinstance(starter, AssessmentSchemeVersion)
    evidence = next(
        item
        for reference in starter.evidence_versions
        if isinstance(
            item := application.system.components.get_exact(reference.kind, reference.version_id),
            EvidenceVersion,
        )
        and item.recipe.anchor.anchor_id == "O1"
    )
    binding = next(
        item
        for reference in starter.evidence_binding_versions
        if isinstance(
            item := application.system.components.get_exact(reference.kind, reference.version_id),
            EvidenceBindingVersion,
        )
        and item.evidence_version_id.version_id == evidence.evidence_version_id
    )
    bn_by_id = {
        item.bn_node_version_id: item
        for reference in starter.bn_node_versions
        if isinstance(
            item := application.system.components.get_exact(reference.kind, reference.version_id),
            BnNodeVersion,
        )
    }
    selected_bn_ids: set[str] = set()
    pending = list(binding.ordered_probabilistic_parent_ids)
    while pending:
        reference = pending.pop()
        if reference.kind is not ComponentKind.BN_NODE_VERSION:
            continue
        if reference.version_id in selected_bn_ids:
            continue
        selected_bn_ids.add(reference.version_id)
        pending.extend(bn_by_id[reference.version_id].ordered_probabilistic_parent_ids)
    selected_bn = tuple(
        bn_by_id[reference.version_id]
        for reference in starter.bn_node_versions
        if reference.version_id in selected_bn_ids
    )
    selected_cpt_ids = {
        binding.cpt_version_id.version_id,
        *(node.cpt_version_id.version_id for node in selected_bn),
    }
    selected_cpts = tuple(
        item
        for reference in starter.cpt_versions
        if reference.version_id in selected_cpt_ids
        and isinstance(
            item := application.system.components.get_exact(reference.kind, reference.version_id),
            CptVersion,
        )
    )
    provisional = starter.model_copy(
        update={
            "scheme_version_id": scheme_version_id,
            "scheme_concept_id": scheme_concept_id,
            "name": name,
            "description": "Minimal engineering-only M6 pipeline scheme.",
            "evidence_versions": (_pin(evidence),),
            "evidence_binding_versions": (_pin(binding),),
            "bn_node_versions": tuple(_pin(item) for item in selected_bn),
            "cpt_versions": tuple(_pin(item) for item in selected_cpts),
            "output_node_ids": (binding.ordered_probabilistic_parent_ids[0],),
            "lineage": VersionLineage(
                source_version_ids=(starter.scheme_version_id,),
                created_at=created_at,
                created_by="test.runtime-support",
                note="Lightweight runtime vertical slice only.",
            ),
            "content_hash": ZERO_HASH,
        }
    )
    return provisional.model_copy(update={"content_hash": component_content_hash(provisional)})


__all__ = ["minimal_o1_scheme"]
