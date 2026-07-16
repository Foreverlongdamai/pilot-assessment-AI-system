"""Deterministically materialize the editable Hover starter model package."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import TypeVar, cast

from pilot_assessment.bayesian.validation import (
    materialize_ranked_cpt,
    materialize_uniform_prior,
)
from pilot_assessment.contracts.assessment_scheme import (
    AssessmentSchemeVersion,
    CoverageReportingPolicyVersion,
    LayoutGroup,
    LayoutVersion,
    NodePosition,
    TaskProfileVersion,
    Viewport,
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
    EvidenceVersion,
    ModelScientificStatus,
    ObservationPolicy,
    PinnedComponentRef,
    VariableState,
    VersionLineage,
)
from pilot_assessment.model_library.identity import typed_content_sha256
from pilot_assessment.model_library.migration import load_hover_evidence_inventory
from pilot_assessment.model_library.repository import (
    VersionLibraryItem,
    component_content_hash,
    component_kind,
    component_record_id,
)
from pilot_assessment.model_library.sources import load_hover_source_catalog

ZERO_HASH = "0" * 64
PROFILE_ID = "hover-starter-v0.1"
CREATED_AT = datetime(2026, 7, 16, 19, 0, tzinfo=UTC)
CREATED_BY = "generator.m5.task10"

_TVersion = TypeVar("_TVersion", bound=VersionLibraryItem)


@dataclass(frozen=True, slots=True)
class _CompetencyDefinition:
    node_id: str
    name: str


@dataclass(frozen=True, slots=True)
class _SubSkillDefinition:
    node_id: str
    name: str
    competency_id: str


@dataclass(frozen=True, slots=True)
class _EvidenceDefinition:
    anchor_id: str
    name: str
    parent_sub_skill_ids: tuple[str, ...]


COMPETENCIES = (
    _CompetencyDefinition("TCP", "Task Control Proficiency"),
    _CompetencyDefinition("PC", "Procedural Compliance"),
    _CompetencyDefinition("SM", "Situational Monitoring"),
    _CompetencyDefinition("OC", "Operational Composure"),
)

SUB_SKILLS = (
    _SubSkillDefinition("TCP.1", "Trajectory tracking", "TCP"),
    _SubSkillDefinition("TCP.2", "Maneuver precision", "TCP"),
    _SubSkillDefinition("TCP.3", "Control efficiency", "TCP"),
    _SubSkillDefinition("TCP.4", "Control smoothness", "TCP"),
    _SubSkillDefinition("PC.1", "Envelope discipline", "PC"),
    _SubSkillDefinition("PC.2", "Event response", "PC"),
    _SubSkillDefinition("SM.1", "Reactive vigilance", "SM"),
    _SubSkillDefinition("SM.2", "Attention allocation", "SM"),
    _SubSkillDefinition("OC.1", "Disturbance recovery", "OC"),
    _SubSkillDefinition("OC.2", "Stress resilience", "OC"),
    _SubSkillDefinition("OC.3", "Physio regulation", "OC"),
)

EVIDENCE = (
    _EvidenceDefinition("O1", "Phase-state precision", ("TCP.1", "PC.1")),
    _EvidenceDefinition("O2", "Peak tracking excursion", ("TCP.1", "TCP.2")),
    _EvidenceDefinition("O3", "Terminal capture quality", ("TCP.2",)),
    _EvidenceDefinition("O4", "Sustained hover time", ("TCP.2",)),
    _EvidenceDefinition("O5", "Workload rate", ("TCP.3",)),
    _EvidenceDefinition("O6", "Control magnitude RMS", ("TCP.3",)),
    _EvidenceDefinition("O7", "Control reversal rate", ("TCP.4", "OC.2")),
    _EvidenceDefinition("O8", "TPX composite", ("TCP.3",)),
    _EvidenceDefinition("O9", "Dead-band activity", ("TCP.4",)),
    _EvidenceDefinition("O10", "Recovery time", ("OC.1",)),
    _EvidenceDefinition("O11", "Disturbance latency", ("PC.2", "SM.1")),
    _EvidenceDefinition("O12", "Envelope-drift latency", ("PC.1", "SM.1")),
    _EvidenceDefinition("O13", "Physio-control coupling", ("OC.2",)),
    _EvidenceDefinition("H1", "AOI dwell", ("PC.2", "SM.2")),
    _EvidenceDefinition("H2", "First fixation latency", ("SM.1",)),
    _EvidenceDefinition("H3", "Off-task dwell", ("SM.2",)),
    _EvidenceDefinition("H4", "ECG fluctuation", ("OC.3",)),
    _EvidenceDefinition("H5", "EEG fluctuation", ("OC.3",)),
)

ABILITY_STATES = (
    VariableState(
        state_id="at_risk",
        label="At Risk",
        description="Starter low ability state; expert calibration required.",
    ),
    VariableState(
        state_id="developing",
        label="Developing",
        description="Starter intermediate ability state; expert calibration required.",
    ),
    VariableState(
        state_id="proficient",
        label="Proficient",
        description="Starter high ability state; expert calibration required.",
    ),
)

EVIDENCE_STATES = (
    VariableState(
        state_id="unacceptable",
        label="Unacceptable",
        description="Computed negative performance evidence.",
    ),
    VariableState(
        state_id="adequate",
        label="Adequate",
        description="Computed adequate performance evidence.",
    ),
    VariableState(
        state_id="desired",
        label="Desired",
        description="Computed desired performance evidence.",
    ),
)

SINGLE_PARENT_ROWS = (
    (0.79, 0.20, 0.01),
    (0.17, 0.66, 0.17),
    (0.01, 0.20, 0.79),
)


def _lineage(note: str, source_ids: tuple[str, ...] = ()) -> VersionLineage:
    return VersionLineage(
        source_version_ids=source_ids,
        created_at=CREATED_AT,
        created_by=CREATED_BY,
        note=note,
    )


def _rehash(item: _TVersion) -> _TVersion:
    return item.model_copy(update={"content_hash": component_content_hash(item)})


def _id_ref(kind: ComponentKind, version_id: str) -> ComponentIdRef:
    return ComponentIdRef(kind=kind, version_id=version_id)


def _pin(item: VersionLibraryItem) -> PinnedComponentRef:
    return PinnedComponentRef(
        kind=component_kind(item),
        version_id=component_record_id(item),
        content_hash=item.content_hash,
    )


def _bn_concept_id(node_id: str) -> str:
    return f"bn-concept.{node_id}"


def _bn_version_id(node_id: str) -> str:
    return f"bn-node-version.hover.{node_id}.v1"


def _bn_cpt_id(node_id: str) -> str:
    return f"cpt-version.hover.bn.{node_id}.v1"


def _binding_id(anchor_id: str) -> str:
    return f"evidence-binding-version.hover.{anchor_id}.v1"


def _evidence_cpt_id(anchor_id: str) -> str:
    return f"cpt-version.hover.evidence.{anchor_id}.v1"


def _cpt(
    *,
    cpt_id: str,
    child: ComponentIdRef,
    parents: tuple[ComponentIdRef, ...],
    child_state_ids: tuple[str, ...],
    parent_state_ids: tuple[tuple[str, ...], ...],
    rows: tuple[tuple[float, ...], ...],
    generator_metadata: Mapping[str, object],
) -> CptVersion:
    provisional = CptVersion.model_validate(
        {
            "cpt_version_id": cpt_id,
            "child_variable_id": child.model_dump(mode="json"),
            "ordered_parent_variable_ids": [item.model_dump(mode="json") for item in parents],
            "child_state_ids": list(child_state_ids),
            "ordered_parent_state_ids": [list(states) for states in parent_state_ids],
            "materialized_probabilities": [list(row) for row in rows],
            "mode": CptMode.GENERATED.value,
            "generator_metadata": dict(generator_metadata),
            "source": ComponentSource.ENGINEERING_DEFAULT.value,
            "lineage": _lineage("Editable engineering-default CPT.").model_dump(mode="json"),
            "content_hash": ZERO_HASH,
        }
    )
    return _rehash(provisional)


def _ability_components() -> tuple[
    tuple[BnNodeConcept, ...],
    tuple[BnNodeVersion, ...],
    tuple[CptVersion, ...],
]:
    concepts: list[BnNodeConcept] = []
    versions: list[BnNodeVersion] = []
    cpts: list[CptVersion] = []
    ability_state_ids = tuple(state.state_id for state in ABILITY_STATES)

    for definition in (*COMPETENCIES, *SUB_SKILLS):
        is_competency = isinstance(definition, _CompetencyDefinition)
        concepts.append(
            BnNodeConcept(
                concept_id=_bn_concept_id(definition.node_id),
                name=definition.name,
                description=(
                    "Editable aggregate competency starter concept."
                    if is_competency
                    else "Editable latent sub-skill starter concept."
                ),
                node_role=(
                    BnNodeRole.AGGREGATE_COMPETENCY if is_competency else BnNodeRole.SUB_SKILL
                ),
                tags=("hover-starter", "competency" if is_competency else "sub-skill"),
                lifecycle=ComponentLifecycle.ACTIVE,
            )
        )
        parents = (
            ()
            if is_competency
            else (
                _id_ref(
                    ComponentKind.BN_NODE_VERSION,
                    _bn_version_id(definition.competency_id),
                ),
            )
        )
        if parents:
            rows = SINGLE_PARENT_ROWS
            parent_states = (ability_state_ids,)
            generator = {
                "generator_type": "ordered-single-parent-preset-v1",
                "editable": True,
                "scientific_status": "engineering_default",
            }
        else:
            materialized = materialize_uniform_prior(ability_state_ids)
            rows = materialized.probabilities
            parent_states = ()
            generator = {
                "generator_type": "uniform-prior-v1",
                "editable": True,
                "scientific_status": "engineering_default",
            }
        cpt = _cpt(
            cpt_id=_bn_cpt_id(definition.node_id),
            child=_id_ref(ComponentKind.BN_NODE_VERSION, _bn_version_id(definition.node_id)),
            parents=parents,
            child_state_ids=ability_state_ids,
            parent_state_ids=parent_states,
            rows=rows,
            generator_metadata=generator,
        )
        cpts.append(cpt)
        provisional = BnNodeVersion(
            bn_node_version_id=_bn_version_id(definition.node_id),
            concept_id=_bn_concept_id(definition.node_id),
            ordered_states=ABILITY_STATES,
            ordered_probabilistic_parent_ids=parents,
            cpt_version_id=_id_ref(ComponentKind.CPT_VERSION, cpt.cpt_version_id),
            documentation=(
                "Hover starter only. Experts may clone and change states, parents, or CPT."
            ),
            scientific_status=ModelScientificStatus.STARTER_TEMPLATE,
            lineage=_lineage("Generated Hover starter BN node."),
            content_hash=ZERO_HASH,
        )
        versions.append(_rehash(provisional))
    return tuple(concepts), tuple(versions), tuple(cpts)


def _evidence_components(
    active_evidence: tuple[EvidenceVersion, ...],
) -> tuple[tuple[EvidenceBindingVersion, ...], tuple[CptVersion, ...]]:
    by_anchor = {version.recipe.anchor.anchor_id: version for version in active_evidence}
    if set(by_anchor) != {definition.anchor_id for definition in EVIDENCE}:
        raise ValueError("active Evidence inventory does not match the Hover starter definitions")
    source_catalog = load_hover_source_catalog()
    ability_state_ids = tuple(state.state_id for state in ABILITY_STATES)
    evidence_state_ids = tuple(state.state_id for state in EVIDENCE_STATES)
    bindings: list[EvidenceBindingVersion] = []
    cpts: list[CptVersion] = []

    for definition in EVIDENCE:
        evidence = by_anchor[definition.anchor_id]
        parents = tuple(
            _id_ref(ComponentKind.BN_NODE_VERSION, _bn_version_id(parent_id))
            for parent_id in definition.parent_sub_skill_ids
        )
        parent_states = tuple(ability_state_ids for _ in parents)
        if len(parents) == 1:
            rows = SINGLE_PARENT_ROWS
            generator: dict[str, object] = {
                "generator_type": "ordered-single-parent-preset-v1",
                "editable": True,
                "scientific_status": "engineering_default",
            }
        else:
            weights = tuple(1.0 / len(parents) for _ in parents)
            materialized = materialize_ranked_cpt(
                parent_states,
                evidence_state_ids,
                weights=weights,
                weakest_link_strength=0.5,
                sigma=0.6,
            )
            rows = materialized.probabilities
            generator = {
                "generator_type": "ranked-node-v1",
                "weights": list(weights),
                "weakest_link_strength": 0.5,
                "sigma": 0.6,
                "editable": True,
                "scientific_status": "engineering_default",
            }
        cpt = _cpt(
            cpt_id=_evidence_cpt_id(definition.anchor_id),
            child=_id_ref(
                ComponentKind.EVIDENCE_BINDING_VERSION,
                _binding_id(definition.anchor_id),
            ),
            parents=parents,
            child_state_ids=evidence_state_ids,
            parent_state_ids=parent_states,
            rows=rows,
            generator_metadata=generator,
        )
        cpts.append(cpt)

        closure = source_catalog.validate_extraction_sources(
            binding.source_id for binding in evidence.recipe.inputs
        )
        if not closure.compatible or not closure.raw_modalities:
            raise ValueError(
                f"Evidence {definition.anchor_id} lacks closed raw-modality provenance"
            )
        weight = 1.0 / len(closure.raw_modalities)
        modality_weights = {modality.value: weight for modality in closure.raw_modalities}
        strength = 0.5 if definition.anchor_id in {"O8", "O13", "H1", "H3"} else 1.0
        dependence_group = {
            "O8": "control-performance-shared-source",
            "O13": "control-physiology-shared-source",
            "H1": "gaze-allocation",
            "H3": "gaze-allocation",
        }.get(definition.anchor_id)
        provisional = EvidenceBindingVersion(
            evidence_binding_version_id=_binding_id(definition.anchor_id),
            evidence_version_id=_id_ref(
                ComponentKind.EVIDENCE_VERSION,
                evidence.evidence_version_id,
            ),
            ordered_observation_states=EVIDENCE_STATES,
            observation_mapping={
                "calculation_status": {
                    "computed": "observe",
                    "missing_input": "omit",
                    "not_applicable": "omit",
                    "not_computable": "omit",
                    "dependency_missing": "omit",
                    "extractor_error": "omit",
                },
                "evidence_state_map": {
                    "unacceptable": "unacceptable",
                    "adequate": "adequate",
                    "desired": "desired",
                },
                "likelihood_strength": strength,
                "dependence_group": dependence_group,
                "quality_gate": None,
            },
            ordered_probabilistic_parent_ids=parents,
            cpt_version_id=_id_ref(ComponentKind.CPT_VERSION, cpt.cpt_version_id),
            observation_policy=ObservationPolicy.HARD_OR_VIRTUAL,
            modality_attribution_weights=modality_weights,
            lineage=_lineage(
                "Generated observation binding for an editable Hover starter Evidence.",
                (evidence.evidence_version_id,),
            ),
            content_hash=ZERO_HASH,
        )
        bindings.append(_rehash(provisional))
    return tuple(bindings), tuple(cpts)


def _task_profile(required_source_ids: tuple[str, ...]) -> TaskProfileVersion:
    provisional = TaskProfileVersion(
        task_profile_version_id="task-profile-version.hover-starter.v1",
        task_concept_id="task-concept.hover",
        name="Hover starter task profile",
        description=(
            "Editable engineering template for a Hover-like task; not a validated task standard."
        ),
        task_semantics={
            "task_family": "hover",
            "phase_labels": ["translation", "deceleration", "hover_stabilization"],
            "starter_only": True,
        },
        required_source_descriptor_ids=required_source_ids,
        reference_parameters={
            "commanded_path_source": "task-reference.commanded-path",
            "expected_envelope_source": "task-reference.expected-envelope",
            "terminal_target_source": "task-reference.terminal-target",
            "expert_editable": True,
        },
        annotation_parameters={
            "disturbance_source": "semantic.disturbances",
            "attention_event_source": "semantic.attention-events",
            "expert_editable": True,
        },
        aoi_parameters={
            "scene_source": "I.frames",
            "taxonomy": "task-defined",
            "expert_editable": True,
        },
        source=ComponentSource.ENGINEERING_DEFAULT,
        lineage=_lineage("Generated editable Hover starter task profile."),
        content_hash=ZERO_HASH,
    )
    return _rehash(provisional)


def _reporting_policy() -> CoverageReportingPolicyVersion:
    provisional = CoverageReportingPolicyVersion(
        policy_version_id="coverage-reporting-policy-version.hover-starter.v1",
        applicability_rules={
            "computed_states_count_as_available": [
                "unacceptable",
                "adequate",
                "desired",
            ],
            "not_applicable_excluded_from_denominator": True,
            "missing_is_not_unacceptable": True,
        },
        coverage_rules={
            "method": "model-weighted-observed-evidence-v1",
            "quality_gate": None,
            "performance_filter": None,
        },
        output_rules={
            "include_full_posterior": True,
            "include_observation_trace": True,
            "include_scientific_status": True,
            "formal_run_authorized": False,
        },
        source=ComponentSource.ENGINEERING_DEFAULT,
        lineage=_lineage("Generated editable Hover starter reporting policy."),
        content_hash=ZERO_HASH,
    )
    return _rehash(provisional)


def _layout(
    source_ids: tuple[str, ...],
    bn_versions: tuple[BnNodeVersion, ...],
    bindings: tuple[EvidenceBindingVersion, ...],
) -> LayoutVersion:
    competency_ids = tuple(_bn_version_id(item.node_id) for item in COMPETENCIES)
    sub_skill_ids = tuple(_bn_version_id(item.node_id) for item in SUB_SKILLS)
    binding_ids = tuple(item.evidence_binding_version_id for item in bindings)
    positions: list[NodePosition] = []
    positions.extend(
        NodePosition(node_id=node_id, x=0.0, y=float(index * 100))
        for index, node_id in enumerate(source_ids)
    )
    positions.extend(
        NodePosition(node_id=node_id, x=360.0, y=float(index * 240))
        for index, node_id in enumerate(competency_ids)
    )
    positions.extend(
        NodePosition(node_id=node_id, x=720.0, y=float(index * 120))
        for index, node_id in enumerate(sub_skill_ids)
    )
    positions.extend(
        NodePosition(node_id=node_id, x=1080.0, y=float(index * 90))
        for index, node_id in enumerate(binding_ids)
    )
    declared_bn_ids = {item.bn_node_version_id for item in bn_versions}
    if declared_bn_ids != set((*competency_ids, *sub_skill_ids)):
        raise ValueError("layout BN inventory does not match generated BN versions")
    provisional = LayoutVersion(
        layout_version_id="layout-version.hover-starter.v1",
        node_positions=tuple(positions),
        groups=(
            LayoutGroup(
                group_id="layout-group.sources",
                label="Raw and task inputs",
                node_ids=source_ids,
                metadata={"node_family": "source"},
            ),
            LayoutGroup(
                group_id="layout-group.competencies",
                label="Aggregate competencies",
                node_ids=competency_ids,
                metadata={"node_family": "bn_node"},
            ),
            LayoutGroup(
                group_id="layout-group.sub-skills",
                label="Sub-skills",
                node_ids=sub_skill_ids,
                metadata={"node_family": "bn_node"},
            ),
            LayoutGroup(
                group_id="layout-group.evidence",
                label="Evidence observations",
                node_ids=binding_ids,
                metadata={"node_family": "evidence"},
            ),
        ),
        viewport=Viewport(x=0.0, y=0.0, zoom=0.75),
        lineage=_lineage("Generated editable integrated-workspace starter layout."),
        content_hash=ZERO_HASH,
    )
    return _rehash(provisional)


def _source_closure(active_evidence: tuple[EvidenceVersion, ...]) -> tuple[str, ...]:
    catalog = load_hover_source_catalog()
    requested = tuple(
        binding.source_id for evidence in active_evidence for binding in evidence.recipe.inputs
    )
    closure = catalog.validate_extraction_sources(requested)
    if not closure.compatible:
        raise ValueError("Hover starter Evidence source closure is not compatible")
    task_required = {
        "I.frames",
        "session.duration-s",
        "semantic.attention-events",
        "semantic.disturbances",
        "task-reference.commanded-path",
        "task-reference.expected-envelope",
        "task-reference.terminal-target",
    }
    return tuple(sorted(set(closure.resolved_source_ids) | task_required))


def _scheme(
    *,
    sources: tuple[VersionLibraryItem, ...],
    evidence: tuple[EvidenceVersion, ...],
    bindings: tuple[EvidenceBindingVersion, ...],
    bn_versions: tuple[BnNodeVersion, ...],
    cpts: tuple[CptVersion, ...],
    task_profile: TaskProfileVersion,
    reporting_policy: CoverageReportingPolicyVersion,
    layout: LayoutVersion,
) -> AssessmentSchemeVersion:
    output_ids = tuple(
        _id_ref(ComponentKind.BN_NODE_VERSION, _bn_version_id(item.node_id))
        for item in COMPETENCIES
    )
    provisional = AssessmentSchemeVersion(
        scheme_version_id="assessment-scheme-version.hover-starter.v1",
        scheme_concept_id="assessment-scheme-concept.hover-starter",
        name="Hover starter assessment scheme",
        description=(
            "Editable engineering template. It demonstrates the platform and is not a "
            "scientifically validated pilot assessment model."
        ),
        task_profile=_pin(task_profile),
        source_descriptors=tuple(_pin(item) for item in sources),
        evidence_versions=tuple(_pin(item) for item in evidence),
        evidence_binding_versions=tuple(_pin(item) for item in bindings),
        bn_node_versions=tuple(_pin(item) for item in bn_versions),
        cpt_versions=tuple(_pin(item) for item in cpts),
        reporting_policy=_pin(reporting_policy),
        layout=_pin(layout),
        output_node_ids=output_ids,
        lineage=_lineage("Generated first exact-pinned Hover starter scheme."),
        content_hash=ZERO_HASH,
    )
    return _rehash(provisional)


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")


def _resource_ref(item: object) -> dict[str, str]:
    if isinstance(item, BnNodeConcept):
        kind = ComponentKind.BN_NODE_CONCEPT
        record_id = item.concept_id
    else:
        version = cast(VersionLibraryItem, item)
        kind = component_kind(version)
        record_id = component_record_id(version)
    return {"kind": kind.value, "record_id": record_id}


def _resource_entry(
    *,
    path: str,
    type_id: str,
    schema_id: str,
    payload: bytes,
    record_refs: tuple[dict[str, str], ...],
    dependency_refs: tuple[dict[str, str], ...],
) -> dict[str, object]:
    return {
        "path": path,
        "type_id": type_id,
        "schema_id": schema_id,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "record_refs": list(record_refs),
        "dependency_refs": list(dependency_refs),
    }


def _unique_refs(refs: tuple[dict[str, str], ...]) -> tuple[dict[str, str], ...]:
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for ref in refs:
        key = (ref["kind"], ref["record_id"])
        if key not in seen:
            seen.add(key)
            result.append(ref)
    return tuple(result)


def _existing_bytes(filename: str) -> bytes:
    return (
        files("pilot_assessment.model_library.profile_data")
        .joinpath("hover", filename)
        .read_bytes()
    )


def _build_resources() -> tuple[dict[str, bytes], AssessmentSchemeVersion]:
    inventory = load_hover_evidence_inventory()
    active_evidence_by_anchor = {
        item.recipe.anchor.anchor_id: item for item in inventory.active_versions
    }
    active_evidence = tuple(
        active_evidence_by_anchor[definition.anchor_id] for definition in EVIDENCE
    )
    source_catalog = load_hover_source_catalog()
    source_ids = _source_closure(active_evidence)
    sources = tuple(source_catalog.get(source_id) for source_id in source_ids)
    bn_concepts, bn_versions, bn_cpts = _ability_components()
    bindings, evidence_cpts = _evidence_components(active_evidence)
    cpts = (*bn_cpts, *evidence_cpts)
    task_profile = _task_profile(source_ids)
    reporting_policy = _reporting_policy()
    layout = _layout(source_ids, bn_versions, bindings)
    scheme = _scheme(
        sources=cast(tuple[VersionLibraryItem, ...], sources),
        evidence=active_evidence,
        bindings=bindings,
        bn_versions=bn_versions,
        cpts=cpts,
        task_profile=task_profile,
        reporting_policy=reporting_policy,
        layout=layout,
    )

    resources = {
        "bn-node-concepts.json": _json_bytes(
            {
                "contract_id": "bn-node-concept-catalog",
                "contract_version": "0.1.0",
                "concepts": [item.model_dump(mode="json") for item in bn_concepts],
            }
        ),
        "bn-node-versions.json": _json_bytes(
            {
                "contract_id": "bn-node-version-catalog",
                "contract_version": "0.1.0",
                "versions": [item.model_dump(mode="json") for item in bn_versions],
            }
        ),
        "evidence-bindings.json": _json_bytes(
            {
                "contract_id": "evidence-binding-version-catalog",
                "contract_version": "0.1.0",
                "bindings": [item.model_dump(mode="json") for item in bindings],
            }
        ),
        "cpts.json": _json_bytes(
            {
                "contract_id": "cpt-version-catalog",
                "contract_version": "0.1.0",
                "cpts": [item.model_dump(mode="json") for item in cpts],
            }
        ),
        "task-profile.json": _json_bytes(task_profile.model_dump(mode="json")),
        "reporting-policy.json": _json_bytes(reporting_policy.model_dump(mode="json")),
        "layout.json": _json_bytes(layout.model_dump(mode="json")),
        "scheme.json": _json_bytes(scheme.model_dump(mode="json")),
    }

    local_records = {
        "bn-node-concepts.json": tuple(_resource_ref(item) for item in bn_concepts),
        "bn-node-versions.json": tuple(_resource_ref(item) for item in bn_versions),
        "evidence-bindings.json": tuple(_resource_ref(item) for item in bindings),
        "cpts.json": tuple(_resource_ref(item) for item in cpts),
        "task-profile.json": (_resource_ref(task_profile),),
        "reporting-policy.json": (_resource_ref(reporting_policy),),
        "layout.json": (_resource_ref(layout),),
        "scheme.json": (_resource_ref(scheme),),
    }
    bn_dependencies = _unique_refs(
        tuple(
            {
                "kind": ComponentKind.BN_NODE_CONCEPT.value,
                "record_id": item.concept_id,
            }
            for item in bn_versions
        )
        + tuple(_resource_ref(cpt) for cpt in bn_cpts)
        + tuple(
            {"kind": parent.kind.value, "record_id": parent.version_id}
            for item in bn_versions
            for parent in item.ordered_probabilistic_parent_ids
        )
    )
    binding_dependencies = (
        tuple(_resource_ref(item) for item in active_evidence)
        + tuple(_resource_ref(item) for item in bn_versions)
        + tuple(_resource_ref(item) for item in evidence_cpts)
    )
    cpt_dependencies = tuple(_resource_ref(item) for item in (*bn_versions, *bindings))
    scheme_dependencies = tuple(
        _resource_ref(item)
        for item in (
            *sources,
            *active_evidence,
            *bindings,
            *bn_versions,
            *cpts,
            task_profile,
            reporting_policy,
            layout,
        )
    )
    dependencies: dict[str, tuple[dict[str, str], ...]] = {
        "bn-node-concepts.json": (),
        "bn-node-versions.json": bn_dependencies,
        "evidence-bindings.json": binding_dependencies,
        "cpts.json": cpt_dependencies,
        "task-profile.json": tuple(
            {"kind": ComponentKind.SOURCE_DESCRIPTOR.value, "record_id": source_id}
            for source_id in source_ids
        ),
        "reporting-policy.json": (),
        "layout.json": tuple(_resource_ref(item) for item in (*bn_versions, *bindings, *sources)),
        "scheme.json": scheme_dependencies,
    }
    resource_kinds = {
        "bn-node-concepts.json": (
            "bn_node_concept_catalog",
            "bn-node-concept-catalog-v0.1",
        ),
        "bn-node-versions.json": (
            "bn_node_version_catalog",
            "bn-node-version-catalog-v0.1",
        ),
        "evidence-bindings.json": (
            "evidence_binding_version_catalog",
            "evidence-binding-version-catalog-v0.1",
        ),
        "cpts.json": ("cpt_version_catalog", "cpt-version-catalog-v0.1"),
        "task-profile.json": ("task_profile_version", "task-profile-version-v0.1"),
        "reporting-policy.json": (
            "coverage_reporting_policy_version",
            "coverage-reporting-policy-version-v0.1",
        ),
        "layout.json": ("layout_version", "layout-version-v0.1"),
        "scheme.json": (
            "assessment_scheme_version",
            "assessment-scheme-version-v0.1",
        ),
    }

    evidence_concept_refs = tuple(
        {
            "kind": ComponentKind.EVIDENCE_CONCEPT.value,
            "record_id": item.concept_id,
        }
        for item in inventory.concepts
    )
    supporting = {
        "source-descriptors.json": (
            "source_descriptor_catalog",
            "source-descriptor-catalog-v0.1",
            _existing_bytes("source-descriptors.json"),
            tuple(_resource_ref(item) for item in source_catalog.descriptors()),
            (),
        ),
        "evidence-concepts.json": (
            "evidence_concept_catalog",
            "evidence-concept-catalog-v0.1",
            _existing_bytes("evidence-concepts.json"),
            evidence_concept_refs,
            (),
        ),
        "migration-manifest.json": (
            "migration_support",
            "m4r-evidence-migration-manifest-v0.1",
            _existing_bytes("migration-manifest.json"),
            (),
            (*evidence_concept_refs, *tuple(_resource_ref(item) for item in active_evidence)),
        ),
        "tpx-raw-task-v1.json": (
            "evidence_recipe_support",
            "evidence-recipe-support-v0.1",
            _existing_bytes("tpx-raw-task-v1.json"),
            (),
            (
                {
                    "kind": ComponentKind.EVIDENCE_CONCEPT.value,
                    "record_id": "evidence-concept.O8",
                },
                {
                    "kind": ComponentKind.SOURCE_DESCRIPTOR.value,
                    "record_id": "X.state-vector",
                },
                {
                    "kind": ComponentKind.SOURCE_DESCRIPTOR.value,
                    "record_id": "U.channels",
                },
                {
                    "kind": ComponentKind.SOURCE_DESCRIPTOR.value,
                    "record_id": "session.duration-s",
                },
            ),
        ),
    }
    manifest_entries: list[dict[str, object]] = []
    for path, (type_id, schema_id, payload, record_refs, dependency_refs) in supporting.items():
        manifest_entries.append(
            _resource_entry(
                path=path,
                type_id=type_id,
                schema_id=schema_id,
                payload=payload,
                record_refs=record_refs,
                dependency_refs=dependency_refs,
            )
        )
    for path, payload in resources.items():
        type_id, schema_id = resource_kinds[path]
        manifest_entries.append(
            _resource_entry(
                path=path,
                type_id=type_id,
                schema_id=schema_id,
                payload=payload,
                record_refs=local_records[path],
                dependency_refs=dependencies[path],
            )
        )
    manifest_entries.sort(key=lambda item: cast(str, item["path"]))
    manifest_payload: dict[str, object] = {
        "contract_id": "model-profile-manifest",
        "contract_version": "0.1.0",
        "profile_id": PROFILE_ID,
        "created_at": CREATED_AT.isoformat().replace("+00:00", "Z"),
        "created_by": CREATED_BY,
        "scientific_status": ModelScientificStatus.STARTER_TEMPLATE.value,
        "entry_scheme_ref": _pin(scheme).model_dump(mode="json"),
        "external_component_refs": [_pin(item).model_dump(mode="json") for item in active_evidence],
        "resources": manifest_entries,
    }
    manifest_payload["manifest_hash"] = typed_content_sha256(
        "model-profile-manifest",
        "0.1.0",
        manifest_payload,
    )
    resources["manifest.json"] = _json_bytes(manifest_payload)
    return resources, scheme


def render_hover_starter_resources() -> dict[str, bytes]:
    """Return deterministic generated bytes keyed by package-relative filename."""

    resources, _ = _build_resources()
    return dict(sorted(resources.items()))


def write_hover_starter_resources(root: Path | None = None) -> tuple[Path, ...]:
    """Write the generated resources; repeated calls produce byte-identical files."""

    output_root = root or Path(__file__).resolve().parent / "hover"
    output_root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, payload in render_hover_starter_resources().items():
        target = output_root / filename
        target.write_bytes(payload)
        written.append(target)
    return tuple(written)


def main() -> int:
    for path in write_hover_starter_resources():
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
