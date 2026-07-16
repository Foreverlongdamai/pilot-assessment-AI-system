from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from pilot_assessment.contracts.assessment_scheme import AssessmentSchemeVersion
from pilot_assessment.contracts.model_components import (
    BnNodeVersion,
    ComponentIdRef,
    ComponentKind,
    ComponentSource,
    CptMode,
    CptVersion,
    EvidenceBindingVersion,
    PinnedComponentRef,
)
from pilot_assessment.model_library.repository import (
    InMemoryComponentLibraryRepository,
    VersionLibraryItem,
)
from tests.schemes.support import NOW, build_fixture, pin, rehash, variable_ref


@dataclass(frozen=True, slots=True)
class InferenceFixture:
    scheme: AssessmentSchemeVersion
    repository: InMemoryComponentLibraryRepository
    root: BnNodeVersion
    observed: EvidenceBindingVersion
    other_root: BnNodeVersion | None = None


def _replace_components(
    components: tuple[VersionLibraryItem, ...],
    replacements: tuple[VersionLibraryItem, ...],
) -> tuple[VersionLibraryItem, ...]:
    replacement_keys = {(type(item), _version_id(item)): item for item in replacements}
    result: list[VersionLibraryItem] = []
    seen: set[tuple[type[object], str]] = set()
    for item in components:
        key = (type(item), _version_id(item))
        replacement = replacement_keys.get(key)
        result.append(replacement if replacement is not None else item)
        seen.add(key)
    result.extend(item for key, item in replacement_keys.items() if key not in seen)
    return tuple(result)


def _version_id(item: VersionLibraryItem) -> str:
    for field in (
        "evidence_version_id",
        "bn_node_version_id",
        "evidence_binding_version_id",
        "cpt_version_id",
        "task_profile_version_id",
        "policy_version_id",
        "layout_version_id",
        "scheme_version_id",
        "source_id",
    ):
        value = getattr(item, field, None)
        if isinstance(value, str):
            return value
    raise AssertionError(type(item).__name__)


def _cpt(
    cpt_id: str,
    child: BnNodeVersion | EvidenceBindingVersion,
    parents: tuple[BnNodeVersion, ...],
    rows: tuple[tuple[float, ...], ...],
) -> CptVersion:
    child_states = (
        child.ordered_states
        if isinstance(child, BnNodeVersion)
        else child.ordered_observation_states
    )
    provisional = CptVersion(
        cpt_version_id=cpt_id,
        child_variable_id=variable_ref(child),
        ordered_parent_variable_ids=tuple(variable_ref(parent) for parent in parents),
        child_state_ids=tuple(state.state_id for state in child_states),
        ordered_parent_state_ids=tuple(
            tuple(state.state_id for state in parent.ordered_states) for parent in parents
        ),
        materialized_probabilities=rows,
        mode=CptMode.MANUAL,
        generator_metadata={"fixture": "hand-calculated"},
        source=ComponentSource.ENGINEERING_DEFAULT,
        lineage=child.lineage,
        content_hash="0" * 64,
    )
    return cast(CptVersion, rehash(provisional))


def _repository(components: tuple[VersionLibraryItem, ...]) -> InMemoryComponentLibraryRepository:
    repository = InMemoryComponentLibraryRepository()
    for component in components:
        repository.add(component, recorded_at=NOW)
    return repository


def two_node_fixture(
    *,
    root_prior: tuple[float, float] = (0.6, 0.4),
    observed_rows: tuple[tuple[float, float], tuple[float, float]] = (
        (0.9, 0.1),
        (0.2, 0.8),
    ),
) -> InferenceFixture:
    base = build_fixture(state_count=2)
    root = next(item for item in base.components if isinstance(item, BnNodeVersion))
    observed = next(item for item in base.components if isinstance(item, EvidenceBindingVersion))
    root_cpt = _cpt("cpt.alpha-v2", root, (), (root_prior,))
    observed_cpt = _cpt("cpt.binding-v9", observed, (root,), observed_rows)
    components = _replace_components(base.components, (root_cpt, observed_cpt))
    scheme = cast(
        AssessmentSchemeVersion,
        rehash(
            base.scheme.model_copy(
                update={
                    "cpt_versions": (pin(root_cpt), pin(observed_cpt)),
                    "content_hash": "0" * 64,
                }
            )
        ),
    )
    return InferenceFixture(
        scheme=scheme,
        repository=_repository(components),
        root=root,
        observed=observed,
    )


def collider_fixture() -> InferenceFixture:
    base = build_fixture(state_count=2)
    root = next(item for item in base.components if isinstance(item, BnNodeVersion))
    observed_original = next(
        item for item in base.components if isinstance(item, EvidenceBindingVersion)
    )
    other_root = cast(
        BnNodeVersion,
        rehash(
            BnNodeVersion(
                bn_node_version_id="bn-version.beta-v1",
                concept_id="concept.beta",
                ordered_states=root.ordered_states,
                ordered_probabilistic_parent_ids=(),
                cpt_version_id=ComponentIdRef(
                    kind=ComponentKind.CPT_VERSION,
                    version_id="cpt.beta-v1",
                ),
                documentation="Second arbitrary root.",
                scientific_status=root.scientific_status,
                lineage=root.lineage,
                content_hash="0" * 64,
            )
        ),
    )
    observed = cast(
        EvidenceBindingVersion,
        rehash(
            observed_original.model_copy(
                update={
                    "ordered_probabilistic_parent_ids": (
                        variable_ref(root),
                        variable_ref(other_root),
                    ),
                    "content_hash": "0" * 64,
                }
            )
        ),
    )
    first_cpt = _cpt("cpt.alpha-v2", root, (), ((0.5, 0.5),))
    second_cpt = _cpt("cpt.beta-v1", other_root, (), ((0.5, 0.5),))
    observed_cpt = _cpt(
        "cpt.binding-v9",
        observed,
        (root, other_root),
        ((0.9, 0.1), (0.2, 0.8), (0.3, 0.7), (0.1, 0.9)),
    )
    replacements: tuple[VersionLibraryItem, ...] = (
        observed,
        other_root,
        first_cpt,
        second_cpt,
        observed_cpt,
    )
    components = _replace_components(base.components, replacements)
    scheme = cast(
        AssessmentSchemeVersion,
        rehash(
            base.scheme.model_copy(
                update={
                    "evidence_binding_versions": (pin(observed),),
                    "bn_node_versions": (pin(root), pin(other_root)),
                    "cpt_versions": (pin(first_cpt), pin(second_cpt), pin(observed_cpt)),
                    "output_node_ids": (variable_ref(root), variable_ref(other_root)),
                    "content_hash": "0" * 64,
                }
            )
        ),
    )
    return InferenceFixture(
        scheme=scheme,
        repository=_repository(components),
        root=root,
        observed=observed,
        other_root=other_root,
    )


def independent_fixture() -> InferenceFixture:
    base = two_node_fixture()
    other_root = cast(
        BnNodeVersion,
        rehash(
            BnNodeVersion(
                bn_node_version_id="bn-version.independent-v1",
                concept_id="concept.independent",
                ordered_states=base.root.ordered_states,
                ordered_probabilistic_parent_ids=(),
                cpt_version_id=ComponentIdRef(
                    kind=ComponentKind.CPT_VERSION,
                    version_id="cpt.independent-v1",
                ),
                documentation="Independent arbitrary root.",
                scientific_status=base.root.scientific_status,
                lineage=base.root.lineage,
                content_hash="0" * 64,
            )
        ),
    )
    other_cpt = _cpt("cpt.independent-v1", other_root, (), ((0.3, 0.7),))
    original_components = cast(
        tuple[VersionLibraryItem, ...],
        tuple(record.item for record in base.repository.list_records()),
    )
    components = _replace_components(original_components, (other_root, other_cpt))
    cpt_pins = tuple(base.scheme.cpt_versions) + (pin(other_cpt),)
    scheme = cast(
        AssessmentSchemeVersion,
        rehash(
            base.scheme.model_copy(
                update={
                    "bn_node_versions": (*base.scheme.bn_node_versions, pin(other_root)),
                    "cpt_versions": cpt_pins,
                    "output_node_ids": (variable_ref(base.root), variable_ref(other_root)),
                    "content_hash": "0" * 64,
                }
            )
        ),
    )
    return InferenceFixture(
        scheme=scheme,
        repository=_repository(components),
        root=base.root,
        observed=base.observed,
        other_root=other_root,
    )


def hard_observation(variable: EvidenceBindingVersion, state_id: str):
    from pilot_assessment.contracts.bayesian import Observation, ObservationKind

    return Observation(
        variable_id=variable_ref(variable),
        kind=ObservationKind.HARD,
        hard_state_id=state_id,
        likelihood=None,
    )


def pin_for(kind: ComponentKind, version_id: str, content_hash: str) -> PinnedComponentRef:
    return PinnedComponentRef(kind=kind, version_id=version_id, content_hash=content_hash)
