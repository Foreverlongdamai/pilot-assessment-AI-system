from __future__ import annotations

from datetime import UTC, datetime

from pilot_assessment.contracts.model_components import (
    BnNodeVersion,
    ComponentIdRef,
    ComponentKind,
    ComponentSource,
    CptMode,
    CptVersion,
    ModelScientificStatus,
    VariableState,
    VersionLineage,
)
from pilot_assessment.model_library.repository import component_content_hash

ZERO_HASH = "0" * 64
NOW = datetime(2026, 7, 16, 16, 0, tzinfo=UTC)


def state_space(prefix: str, count: int) -> tuple[VariableState, ...]:
    return tuple(
        VariableState(
            state_id=f"{prefix}.{index}",
            label=f"{prefix.title()} {index}",
            description=f"Ordered state {index}.",
        )
        for index in range(count)
    )


def lineage() -> VersionLineage:
    return VersionLineage(
        source_version_ids=(),
        created_at=NOW,
        created_by="expert.fixture",
        note="Generic Bayesian fixture.",
    )


def ref(node: BnNodeVersion) -> ComponentIdRef:
    return ComponentIdRef(
        kind=ComponentKind.BN_NODE_VERSION,
        version_id=node.bn_node_version_id,
    )


def node(
    node_id: str,
    states: tuple[VariableState, ...],
    *,
    parents: tuple[BnNodeVersion, ...] = (),
    cpt_id: str | None = None,
) -> BnNodeVersion:
    provisional = BnNodeVersion(
        bn_node_version_id=node_id,
        concept_id=f"concept.{node_id}",
        ordered_states=states,
        ordered_probabilistic_parent_ids=tuple(ref(parent) for parent in parents),
        cpt_version_id=ComponentIdRef(
            kind=ComponentKind.CPT_VERSION,
            version_id=cpt_id or f"cpt.{node_id}",
        ),
        documentation="Generic variable.",
        scientific_status=ModelScientificStatus.ENGINEERING_DEFAULT,
        lineage=lineage(),
        content_hash=ZERO_HASH,
    )
    return provisional.model_copy(update={"content_hash": component_content_hash(provisional)})


def cpt(
    cpt_id: str,
    child: BnNodeVersion,
    *,
    parents: tuple[BnNodeVersion, ...] = (),
    rows: tuple[tuple[float, ...], ...],
    mode: CptMode = CptMode.MANUAL,
) -> CptVersion:
    provisional = CptVersion(
        cpt_version_id=cpt_id,
        child_variable_id=ref(child),
        ordered_parent_variable_ids=tuple(ref(parent) for parent in parents),
        child_state_ids=tuple(state.state_id for state in child.ordered_states),
        ordered_parent_state_ids=tuple(
            tuple(state.state_id for state in parent.ordered_states) for parent in parents
        ),
        materialized_probabilities=rows,
        mode=mode,
        generator_metadata={},
        source=ComponentSource.ENGINEERING_DEFAULT,
        lineage=lineage(),
        content_hash=ZERO_HASH,
    )
    return provisional.model_copy(update={"content_hash": component_content_hash(provisional)})


def variables(*nodes: BnNodeVersion) -> dict[tuple[ComponentKind, str], BnNodeVersion]:
    return {(ComponentKind.BN_NODE_VERSION, item.bn_node_version_id): item for item in nodes}
