from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from pilot_assessment.contracts.assessment_scheme import (
    AssessmentSchemeVersion,
    CoverageReportingPolicyVersion,
    LayoutVersion,
    NodePosition,
    TaskProfileVersion,
    Viewport,
)
from pilot_assessment.contracts.evidence_recipe import (
    EvidenceRecipe,
    InputBindingKind,
    NodePortReference,
    OutputRole,
    PortCardinality,
    PortType,
    RecipeAnchor,
    RecipeDocumentation,
    RecipeEdge,
    RecipeGraph,
    RecipeInputBinding,
    RecipeLifecycle,
    RecipeNode,
    RecipeOutputBinding,
    RecipeScientificStatus,
    RecipeScoring,
    RecipeUiMetadata,
    ScoringMode,
    TemporalSemantics,
)
from pilot_assessment.contracts.model_components import (
    BnNodeVersion,
    ComponentIdRef,
    ComponentKind,
    ComponentSource,
    CptMode,
    CptVersion,
    EvidenceBindingVersion,
    EvidenceVersion,
    ModelScientificStatus,
    ObservationPolicy,
    PinnedComponentRef,
    RawModality,
    SourceKind,
    VariableState,
    VersionLineage,
)
from pilot_assessment.evidence.builtins import register_builtin_operators
from pilot_assessment.evidence.registry import OperatorRegistry
from pilot_assessment.model_library.repository import (
    InMemoryComponentLibraryRepository,
    VersionLibraryItem,
    component_content_hash,
    component_kind,
    component_record_id,
)
from pilot_assessment.model_library.sources import SourceCatalog, create_source_descriptor

ZERO_HASH = "0" * 64
NOW = datetime(2026, 7, 16, 15, 0, tzinfo=UTC)


def number_type() -> PortType:
    return PortType(
        value_type="number",
        cardinality=PortCardinality.ONE,
        temporal_semantics=TemporalSemantics.TIMELESS,
        unit=None,
    )


def lineage(*source_ids: str) -> VersionLineage:
    return VersionLineage(
        source_version_ids=source_ids,
        created_at=NOW,
        created_by="expert.fixture",
        note="Generic scheme fixture.",
    )


def rehash(item: VersionLibraryItem) -> VersionLibraryItem:
    provisional = item.model_copy(update={"content_hash": ZERO_HASH})
    return provisional.model_copy(update={"content_hash": component_content_hash(provisional)})


def pin(item: VersionLibraryItem) -> PinnedComponentRef:
    return PinnedComponentRef(
        kind=component_kind(item),
        version_id=component_record_id(item),
        content_hash=item.content_hash,
    )


def variable_ref(item: BnNodeVersion | EvidenceBindingVersion) -> ComponentIdRef:
    return ComponentIdRef(
        kind=component_kind(item),
        version_id=component_record_id(item),
    )


def states(count: int) -> tuple[VariableState, ...]:
    return tuple(
        VariableState(
            state_id=f"level.{index}",
            label=f"Level {index}",
            description=f"Generic state {index}.",
        )
        for index in range(count)
    )


def evidence_recipe() -> EvidenceRecipe:
    metric = RecipeInputBinding(
        binding_id="metric",
        kind=InputBindingKind.STREAM,
        source_id="X.metric",
        name="Metric",
        declared_type=number_type(),
        selector={},
    )
    threshold = RecipeInputBinding(
        binding_id="threshold",
        kind=InputBindingKind.SEMANTIC,
        source_id="task.threshold",
        name="Task threshold",
        declared_type=number_type(),
        selector={},
    )
    metric_node = RecipeNode(
        node_id="metric-input",
        operator_id="input.binding",
        operator_version="0.1.0",
        input_binding_id="metric",
        parameters={},
    )
    threshold_node = RecipeNode(
        node_id="threshold-input",
        operator_id="input.binding",
        operator_version="0.1.0",
        input_binding_id="threshold",
        parameters={},
    )
    formula = RecipeNode(
        node_id="difference",
        operator_id="composition.safe-formula",
        operator_version="0.1.0",
        input_binding_id=None,
        parameters={"formula": "metric - threshold", "constants": {}},
    )
    result = NodePortReference(node_id="difference", port_id="value")
    return EvidenceRecipe(
        recipe_id="recipe.generic-metric",
        recipe_version=1,
        anchor=RecipeAnchor(
            anchor_id="evidence.generic-metric",
            name="Generic metric",
            description="Platform-only arbitrary-ID fixture.",
            lifecycle=RecipeLifecycle.ACTIVE,
            scientific_status=RecipeScientificStatus.STARTER_TEMPLATE,
        ),
        inputs=(metric, threshold),
        graph=RecipeGraph(
            nodes=(metric_node, threshold_node, formula),
            edges=(
                RecipeEdge(
                    edge_id="metric-to-difference",
                    source=NodePortReference(node_id="metric-input", port_id="value"),
                    target=NodePortReference(node_id="difference", port_id="variables"),
                    target_slot_id="metric",
                ),
                RecipeEdge(
                    edge_id="threshold-to-difference",
                    source=NodePortReference(node_id="threshold-input", port_id="value"),
                    target=NodePortReference(node_id="difference", port_id="variables"),
                    target_slot_id="threshold",
                ),
            ),
        ),
        outputs=(
            RecipeOutputBinding(
                output_id="primary",
                role=OutputRole.PRIMARY_VALUE,
                name="Primary metric",
                source=result,
                unit=None,
            ),
        ),
        scoring=RecipeScoring(
            mode=ScoringMode.ORDERED_DAU,
            input=result,
            parameters={
                "direction": "higher_is_better",
                "desired_boundary": 1.0,
                "adequate_boundary": 0.0,
                "likelihood_strength": 0.8,
            },
            custom_operator_id=None,
            custom_operator_version=None,
        ),
        documentation=RecipeDocumentation(
            summary="Generic technical fixture.",
            assumptions=(),
            parameter_notes={},
            references=(),
        ),
        ui=RecipeUiMetadata(groups=(), preferred_layout={}),
    )


def recipe_with_unknown_operator() -> EvidenceRecipe:
    recipe = evidence_recipe()
    first = recipe.graph.nodes[0].model_copy(update={"operator_id": "operator.missing"})
    return recipe.model_copy(
        update={
            "graph": recipe.graph.model_copy(update={"nodes": (first, *recipe.graph.nodes[1:])})
        }
    )


def cyclic_recipe() -> EvidenceRecipe:
    recipe = evidence_recipe()
    left = RecipeNode(
        node_id="left",
        operator_id="composition.safe-formula",
        operator_version="0.1.0",
        input_binding_id=None,
        parameters={"formula": "right", "constants": {}},
    )
    right = RecipeNode(
        node_id="right",
        operator_id="composition.safe-formula",
        operator_version="0.1.0",
        input_binding_id=None,
        parameters={"formula": "left", "constants": {}},
    )
    result = NodePortReference(node_id="left", port_id="value")
    return recipe.model_copy(
        update={
            "graph": RecipeGraph(
                nodes=(left, right),
                edges=(
                    RecipeEdge(
                        edge_id="left-to-right",
                        source=result,
                        target=NodePortReference(node_id="right", port_id="variables"),
                        target_slot_id="left",
                    ),
                    RecipeEdge(
                        edge_id="right-to-left",
                        source=NodePortReference(node_id="right", port_id="value"),
                        target=NodePortReference(node_id="left", port_id="variables"),
                        target_slot_id="right",
                    ),
                ),
            ),
            "outputs": (recipe.outputs[0].model_copy(update={"source": result}),),
            "scoring": recipe.scoring.model_copy(update={"input": result})
            if recipe.scoring is not None
            else None,
        }
    )


def _uniform_rows(row_count: int, state_count: int) -> tuple[tuple[float, ...], ...]:
    probability = 1.0 / state_count
    return tuple(tuple(probability for _ in range(state_count)) for _ in range(row_count))


def _cpt(
    cpt_id: str,
    child: BnNodeVersion | EvidenceBindingVersion,
    parents: tuple[BnNodeVersion | EvidenceBindingVersion, ...],
    state_space: tuple[VariableState, ...],
) -> CptVersion:
    provisional = CptVersion(
        cpt_version_id=cpt_id,
        child_variable_id=variable_ref(child),
        ordered_parent_variable_ids=tuple(variable_ref(parent) for parent in parents),
        child_state_ids=tuple(state.state_id for state in state_space),
        ordered_parent_state_ids=tuple(
            tuple(state.state_id for state in parent.ordered_states)
            if isinstance(parent, BnNodeVersion)
            else tuple(state.state_id for state in parent.ordered_observation_states)
            for parent in parents
        ),
        materialized_probabilities=_uniform_rows(
            max(1, len(state_space) ** len(parents)),
            len(state_space),
        ),
        mode=CptMode.MANUAL,
        generator_metadata={"fixture": "non_monotonic_uniform"},
        source=ComponentSource.ENGINEERING_DEFAULT,
        lineage=lineage(),
        content_hash=ZERO_HASH,
    )
    return cast(CptVersion, rehash(provisional))


@dataclass(frozen=True, slots=True)
class SchemeFixture:
    scheme: AssessmentSchemeVersion
    components: tuple[VersionLibraryItem, ...]
    repository: InMemoryComponentLibraryRepository
    source_catalog: SourceCatalog
    operator_registry: OperatorRegistry


def build_fixture(
    *,
    state_count: int = 3,
    recipe: EvidenceRecipe | None = None,
    require_task_semantic: bool = True,
    bn_cycle: bool = False,
) -> SchemeFixture:
    raw_source = create_source_descriptor(
        source_id="X.metric",
        kind=SourceKind.RAW_STREAM,
        name="Metric source",
        description="Generic raw metric.",
        declared_type=number_type(),
        raw_modality=RawModality.X,
        metadata={"fixture": True},
    )
    task_source = create_source_descriptor(
        source_id="task.threshold",
        kind=SourceKind.TASK_SEMANTIC,
        name="Task threshold",
        description="Generic task semantic.",
        declared_type=number_type(),
        metadata={"fixture": True},
    )
    state_space = states(state_count)
    evidence = cast(
        EvidenceVersion,
        rehash(
            EvidenceVersion(
                evidence_version_id="evidence-version.metric-v7",
                concept_id="concept.metric",
                recipe=recipe or evidence_recipe(),
                scientific_status=ModelScientificStatus.STARTER_TEMPLATE,
                lineage=lineage(),
                content_hash=ZERO_HASH,
            )
        ),
    )

    if bn_cycle:
        node_a_provisional = BnNodeVersion(
            bn_node_version_id="bn-version.alpha-v2",
            concept_id="concept.alpha",
            ordered_states=state_space,
            ordered_probabilistic_parent_ids=(
                ComponentIdRef(
                    kind=ComponentKind.BN_NODE_VERSION,
                    version_id="bn-version.beta-v4",
                ),
            ),
            cpt_version_id=ComponentIdRef(
                kind=ComponentKind.CPT_VERSION,
                version_id="cpt.alpha-v2",
            ),
            documentation="Arbitrary node alpha.",
            scientific_status=ModelScientificStatus.ENGINEERING_DEFAULT,
            lineage=lineage(),
            content_hash=ZERO_HASH,
        )
        node_b_provisional = BnNodeVersion(
            bn_node_version_id="bn-version.beta-v4",
            concept_id="concept.beta",
            ordered_states=state_space,
            ordered_probabilistic_parent_ids=(
                ComponentIdRef(
                    kind=ComponentKind.BN_NODE_VERSION,
                    version_id="bn-version.alpha-v2",
                ),
            ),
            cpt_version_id=ComponentIdRef(
                kind=ComponentKind.CPT_VERSION,
                version_id="cpt.beta-v4",
            ),
            documentation="Arbitrary node beta.",
            scientific_status=ModelScientificStatus.ENGINEERING_DEFAULT,
            lineage=lineage(),
            content_hash=ZERO_HASH,
        )
        node_a = cast(BnNodeVersion, rehash(node_a_provisional))
        node_b: BnNodeVersion | None = cast(BnNodeVersion, rehash(node_b_provisional))
        bn_nodes = (node_a, node_b)
    else:
        node_a = cast(
            BnNodeVersion,
            rehash(
                BnNodeVersion(
                    bn_node_version_id="bn-version.alpha-v2",
                    concept_id="concept.alpha",
                    ordered_states=state_space,
                    ordered_probabilistic_parent_ids=(),
                    cpt_version_id=ComponentIdRef(
                        kind=ComponentKind.CPT_VERSION,
                        version_id="cpt.alpha-v2",
                    ),
                    documentation="Arbitrary root node.",
                    scientific_status=ModelScientificStatus.ENGINEERING_DEFAULT,
                    lineage=lineage(),
                    content_hash=ZERO_HASH,
                )
            ),
        )
        node_b = None
        bn_nodes = (node_a,)

    binding = cast(
        EvidenceBindingVersion,
        rehash(
            EvidenceBindingVersion(
                evidence_binding_version_id="binding-version.metric-v9",
                evidence_version_id=ComponentIdRef(
                    kind=ComponentKind.EVIDENCE_VERSION,
                    version_id=evidence.evidence_version_id,
                ),
                ordered_observation_states=state_space,
                observation_mapping={
                    "mode": "state_ids",
                    "state_ids": [state.state_id for state in state_space],
                },
                ordered_probabilistic_parent_ids=(variable_ref(node_a),),
                cpt_version_id=ComponentIdRef(
                    kind=ComponentKind.CPT_VERSION,
                    version_id="cpt.binding-v9",
                ),
                observation_policy=ObservationPolicy.HARD_OR_VIRTUAL,
                modality_attribution_weights={"X": 1.0},
                lineage=lineage(),
                content_hash=ZERO_HASH,
            )
        ),
    )

    cpts: list[CptVersion] = []
    if bn_cycle:
        assert node_b is not None
        cpts.append(_cpt("cpt.alpha-v2", node_a, (node_b,), state_space))
        cpts.append(_cpt("cpt.beta-v4", node_b, (node_a,), state_space))
    else:
        cpts.append(_cpt("cpt.alpha-v2", node_a, (), state_space))
    cpts.append(_cpt("cpt.binding-v9", binding, (node_a,), state_space))

    required_sources = ("X.metric", "task.threshold") if require_task_semantic else ("X.metric",)
    task_profile = cast(
        TaskProfileVersion,
        rehash(
            TaskProfileVersion(
                task_profile_version_id="task-profile.generic-v5",
                task_concept_id="task-concept.generic",
                name="Generic task",
                description="Arbitrary task fixture.",
                task_semantics={"task.threshold": 0.0},
                required_source_descriptor_ids=required_sources,
                reference_parameters={},
                annotation_parameters={},
                aoi_parameters={},
                source=ComponentSource.ENGINEERING_DEFAULT,
                lineage=lineage(),
                content_hash=ZERO_HASH,
            )
        ),
    )
    reporting = cast(
        CoverageReportingPolicyVersion,
        rehash(
            CoverageReportingPolicyVersion(
                policy_version_id="policy.generic-v3",
                applicability_rules={},
                coverage_rules={},
                output_rules={},
                source=ComponentSource.ENGINEERING_DEFAULT,
                lineage=lineage(),
                content_hash=ZERO_HASH,
            )
        ),
    )
    positions = tuple(
        NodePosition(node_id=component_record_id(node), x=float(index), y=0.0)
        for index, node in enumerate((*bn_nodes, binding))
    )
    layout = cast(
        LayoutVersion,
        rehash(
            LayoutVersion(
                layout_version_id="layout.generic-v8",
                node_positions=positions,
                groups=(),
                viewport=Viewport(x=0.0, y=0.0, zoom=1.0),
                lineage=lineage(),
                content_hash=ZERO_HASH,
            )
        ),
    )
    components: tuple[VersionLibraryItem, ...] = (
        raw_source,
        task_source,
        evidence,
        binding,
        *bn_nodes,
        *cpts,
        task_profile,
        reporting,
        layout,
    )
    repository = InMemoryComponentLibraryRepository()
    for component in components:
        repository.add(component, recorded_at=NOW)
    source_catalog = SourceCatalog((raw_source, task_source))
    registry = OperatorRegistry()
    register_builtin_operators(registry)

    provisional_scheme = AssessmentSchemeVersion(
        scheme_version_id="scheme-version.generic-v11",
        scheme_concept_id="scheme-concept.generic",
        name="Generic exact scheme",
        description="No starter-specific IDs or cardinalities.",
        task_profile=pin(task_profile),
        source_descriptors=(pin(raw_source), pin(task_source)),
        evidence_versions=(pin(evidence),),
        evidence_binding_versions=(pin(binding),),
        bn_node_versions=tuple(pin(node) for node in bn_nodes),
        cpt_versions=tuple(pin(cpt) for cpt in cpts),
        reporting_policy=pin(reporting),
        layout=pin(layout),
        output_node_ids=(variable_ref(node_a),),
        lineage=lineage(),
        content_hash=ZERO_HASH,
    )
    scheme = cast(AssessmentSchemeVersion, rehash(provisional_scheme))
    return SchemeFixture(
        scheme=scheme,
        components=components,
        repository=repository,
        source_catalog=source_catalog,
        operator_registry=registry,
    )


def revise_scheme(
    fixture: SchemeFixture,
    **updates: object,
) -> AssessmentSchemeVersion:
    provisional = fixture.scheme.model_copy(update={**updates, "content_hash": ZERO_HASH})
    return cast(AssessmentSchemeVersion, rehash(provisional))
