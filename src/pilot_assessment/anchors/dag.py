"""Typed M4 execution-plan validation and deterministic DAG scheduling."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, NoReturn, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from pydantic import JsonValue

from pilot_assessment.anchors.catalog import (
    CatalogResourceError,
    load_packaged_catalog,
    load_parameter_schema,
    parameter_schema_sha256,
)
from pilot_assessment.anchors.fingerprint import (
    aligned_reference_content_fingerprint,
    execution_plan_fingerprint_payload,
    packaged_catalog_fingerprint,
    parameter_snapshot_fingerprint,
    plugin_definition_fingerprint,
    preprocessing_definition_fingerprint,
    reference_alignment_fingerprint,
    reference_resource_fingerprint,
    reference_table_contract_fingerprint,
    resolved_reference_set_fingerprint,
    scorer_policy_fingerprint,
    session_semantic_snapshot_fingerprint,
    typed_json_sha256,
)
from pilot_assessment.anchors.models import (
    AnchorEvaluationRequest,
    AnchorRequestValidationError,
)
from pilot_assessment.anchors.registry import PluginRegistry, packaged_registry_fingerprint
from pilot_assessment.anchors.scoring import ScoringError, compile_scorer_policy
from pilot_assessment.contracts.anchor_execution import (
    AnchorExecutionEntry,
    AnchorExecutionPlan,
    AnchorPluginDefinition,
    DependencyKind,
    PreprocessingProviderDefinition,
    ResolvedPreprocessingRecipe,
    ResolvedReferenceSetSnapshot,
    SemanticApplicabilityStatus,
)
from pilot_assessment.contracts.common import Sha256Digest
from pilot_assessment.contracts.errors import DomainErrorData, ErrorSeverity


@dataclass(frozen=True, slots=True)
class ValidatedExecutionPlan:
    plan: AnchorExecutionPlan
    levels: tuple[tuple[str, ...], ...]
    registry_fingerprint: str


@dataclass(frozen=True, slots=True)
class PlanValidationOutcome:
    disposition: Literal["valid", "blocked"]
    validated_plan: ValidatedExecutionPlan | None
    diagnostics: tuple[DomainErrorData, ...]


@dataclass(frozen=True, slots=True)
class EvaluationPolicy:
    require_packaged_registry_fingerprint: bool
    allow_injected_test_profile_ids: bool


@dataclass(frozen=True, slots=True)
class TestFaultHooks:
    direct_stream_projection_failures: Mapping[tuple[str, str], DomainErrorData] = field(
        default_factory=dict
    )
    preprocessing_resolution_failures: Mapping[tuple[str, str], DomainErrorData] = field(
        default_factory=dict
    )
    anchor_transaction_failures: Mapping[str, DomainErrorData] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "direct_stream_projection_failures",
            MappingProxyType(dict(self.direct_stream_projection_failures)),
        )
        object.__setattr__(
            self,
            "preprocessing_resolution_failures",
            MappingProxyType(dict(self.preprocessing_resolution_failures)),
        )
        object.__setattr__(
            self,
            "anchor_transaction_failures",
            MappingProxyType(dict(self.anchor_transaction_failures)),
        )


class _PlanBlocked(ValueError):
    def __init__(self, code: str, message: str, *, anchor_id: str | None = None) -> None:
        self.code = code
        self.anchor_id = anchor_id
        super().__init__(message)


def _diagnostic(error: _PlanBlocked) -> DomainErrorData:
    return DomainErrorData(
        error_code=error.code,
        severity=ErrorSeverity.ERROR,
        recoverable=False,
        message=str(error),
        node_or_anchor_id=error.anchor_id,
        remediation="Correct the immutable execution plan or runtime registry and retry.",
    )


def _block(code: str, message: str, *, anchor_id: str | None = None) -> NoReturn:
    raise _PlanBlocked(code, message, anchor_id=anchor_id)


def _anchor_edges(
    entries: Sequence[AnchorExecutionEntry],
) -> tuple[dict[str, AnchorExecutionEntry], dict[str, set[str]]]:
    by_id: dict[str, AnchorExecutionEntry] = {}
    for entry in entries:
        if entry.anchor_id in by_id:
            _block(
                "anchor.plan.duplicate_anchor",
                f"execution plan repeats anchor {entry.anchor_id}",
                anchor_id=entry.anchor_id,
            )
        by_id[entry.anchor_id] = entry

    graph: dict[str, set[str]] = {anchor_id: set() for anchor_id in by_id}
    for consumer in entries:
        dependency_ids: set[str] = set()
        for dependency in consumer.dependencies:
            if dependency.dependency_id in dependency_ids:
                _block(
                    "anchor.plan.duplicate_dependency",
                    f"anchor {consumer.anchor_id} repeats dependency {dependency.dependency_id}",
                    anchor_id=consumer.anchor_id,
                )
            dependency_ids.add(dependency.dependency_id)
            if dependency.kind not in {DependencyKind.RESULT, DependencyKind.ARTIFACT}:
                continue
            target = dependency.target_anchor_id
            if target is None or target not in by_id:
                _block(
                    "anchor.plan.dependency_unresolved",
                    f"anchor {consumer.anchor_id} dependency "
                    f"{dependency.dependency_id} is unresolved",
                    anchor_id=consumer.anchor_id,
                )
            graph[consumer.anchor_id].add(target)
    return by_id, graph


def _levels_from_graph(
    graph: Mapping[str, set[str]],
    order: Mapping[str, tuple[int, str]],
    *,
    cycle_code: str,
) -> tuple[tuple[str, ...], ...]:
    remaining = {node: set(dependencies) for node, dependencies in graph.items()}
    levels: list[tuple[str, ...]] = []
    resolved: set[str] = set()
    while remaining:
        ready = tuple(
            sorted(
                (node for node, dependencies in remaining.items() if dependencies <= resolved),
                key=order.__getitem__,
            )
        )
        if not ready:
            _block(cycle_code, "dependency graph contains a cycle")
        levels.append(ready)
        resolved.update(ready)
        for node in ready:
            del remaining[node]
    return tuple(levels)


def topological_levels(
    entries: Sequence[AnchorExecutionEntry],
) -> tuple[tuple[str, ...], ...]:
    """Return stable parallel levels ordered by plan canonical order then ID."""

    by_id, graph = _anchor_edges(entries)
    return _levels_from_graph(
        graph,
        {anchor_id: (entry.canonical_order, anchor_id) for anchor_id, entry in by_id.items()},
        cycle_code="anchor.plan.anchor_cycle",
    )


def _reconstructed_plugin_definition(entry: AnchorExecutionEntry) -> AnchorPluginDefinition:
    return AnchorPluginDefinition(
        anchor_id=entry.anchor_id,
        definition_version=entry.definition_version,
        plugin_id=entry.plugin_id,
        plugin_version=entry.plugin_version,
        api_version=entry.api_version,
        required_streams=entry.required_streams,
        required_context_paths=entry.required_context_paths,
        required_semantic_paths=entry.required_semantic_paths,
        required_reference_ids=entry.required_reference_ids,
        dependencies=entry.dependencies,
        parameter_schema_id=entry.parameter_schema_id,
        measurement_schema_id=entry.measurement_schema_id,
        artifact_recipes=entry.artifact_recipes,
    )


def _reconstructed_provider_definition(
    recipe: ResolvedPreprocessingRecipe,
) -> PreprocessingProviderDefinition:
    return PreprocessingProviderDefinition(
        provider_id=recipe.provider_id,
        provider_version=recipe.provider_version,
        api_version=recipe.api_version,
        required_streams=recipe.required_streams,
        required_context_paths=recipe.required_context_paths,
        required_semantic_paths=recipe.required_semantic_paths,
        required_reference_ids=recipe.required_reference_ids,
        dependencies=recipe.dependency_specs,
        parameter_schema_id=recipe.parameter_schema_id,
        output_schema_id=recipe.output_schema_id,
        output_schema_descriptor=recipe.output_schema_descriptor,
        artifact_kind=recipe.artifact_kind,
        output_payload_kind=recipe.output_payload_kind,
    )


def _validate_parameter_object(
    schema_id: str,
    parameters: Mapping[str, JsonValue],
    claimed_hash: str,
    *,
    anchor_id: str | None,
) -> None:
    try:
        schema = load_parameter_schema(schema_id)
        Draft202012Validator.check_schema(dict(schema))
        validator = Draft202012Validator(dict(schema))
        materialized = dict(parameters)
        errors = tuple(validator.iter_errors(materialized))
    except (CatalogResourceError, SchemaError, TypeError, ValueError) as error:
        _block(
            "anchor.plan.parameter_schema_invalid",
            f"parameter schema {schema_id} cannot be validated: {error}",
            anchor_id=anchor_id,
        )
    if errors:
        first = sorted(errors, key=lambda item: tuple(str(part) for part in item.path))[0]
        _block(
            "anchor.plan.parameter_schema_invalid",
            f"parameters do not satisfy {schema_id}: {first.message}",
            anchor_id=anchor_id,
        )
    if parameter_snapshot_fingerprint(parameters) != claimed_hash:
        _block(
            "anchor.plan.parameter_fingerprint_mismatch",
            f"parameter hash is stale for {schema_id}",
            anchor_id=anchor_id,
        )


def _validate_scorer(entry: AnchorExecutionEntry) -> None:
    try:
        schema = load_parameter_schema(entry.parameter_schema_id)
        annotation = schema.get("x-scorer-policy-default")
        if not isinstance(annotation, Mapping):
            raise ScoringError("scorer_policy_invalid", "schema has no scorer annotation")
        authoritative = compile_scorer_policy(cast(Mapping[str, JsonValue], annotation))
    except (CatalogResourceError, ScoringError, TypeError, ValueError) as error:
        _block(
            "anchor.plan.scorer_policy_invalid",
            f"scorer policy cannot be compiled for {entry.anchor_id}: {error}",
            anchor_id=entry.anchor_id,
        )
    if entry.scorer_policy != authoritative or (
        scorer_policy_fingerprint(entry.scorer_policy) != entry.scorer_policy.policy_hash
    ):
        _block(
            "anchor.plan.scorer_policy_mismatch",
            f"scorer policy is not the authoritative policy for {entry.anchor_id}",
            anchor_id=entry.anchor_id,
        )


def _validate_dependency_contracts(plan: AnchorExecutionPlan) -> None:
    entries = {entry.anchor_id: entry for entry in plan.entries}
    profiles = {profile.profile_id: profile for profile in plan.algorithm_profiles}
    recipes = {recipe.recipe_id: recipe for recipe in plan.preprocessing_recipes}
    if len(profiles) != len(plan.algorithm_profiles):
        _block("anchor.plan.duplicate_algorithm_profile", "algorithm profile IDs repeat")
    if len(recipes) != len(plan.preprocessing_recipes):
        _block("anchor.plan.duplicate_preprocessing_recipe", "preprocessing recipe IDs repeat")

    for consumer in plan.entries:
        for dependency in consumer.dependencies:
            if dependency.kind is DependencyKind.RESULT:
                target = entries.get(dependency.target_anchor_id or "")
                if target is None or target.result_schema_id != dependency.expected_schema_id:
                    _block(
                        "anchor.plan.dependency_unresolved",
                        f"result dependency {dependency.dependency_id} does not resolve exactly",
                        anchor_id=consumer.anchor_id,
                    )
            elif dependency.kind is DependencyKind.ARTIFACT:
                target = entries.get(dependency.target_anchor_id or "")
                matches = (
                    ()
                    if target is None
                    else tuple(
                        recipe
                        for recipe in target.artifact_recipes
                        if recipe.artifact_id == dependency.target_resource_id
                        and recipe.schema_id == dependency.expected_schema_id
                        and recipe.kind == dependency.expected_artifact_kind
                    )
                )
                if len(matches) != 1:
                    _block(
                        "anchor.plan.dependency_unresolved",
                        f"artifact dependency {dependency.dependency_id} does not resolve exactly",
                        anchor_id=consumer.anchor_id,
                    )
            elif dependency.kind is DependencyKind.ALGORITHM_PROFILE:
                profile = profiles.get(dependency.target_resource_id or "")
                if profile is None or profile.output_schema_id != dependency.expected_schema_id:
                    _block(
                        "anchor.plan.dependency_unresolved",
                        f"algorithm dependency {dependency.dependency_id} does not resolve exactly",
                        anchor_id=consumer.anchor_id,
                    )
            elif dependency.kind is DependencyKind.PREPROCESSING:
                recipe = recipes.get(dependency.target_resource_id or "")
                if (
                    recipe is None
                    or recipe.output_schema_id != dependency.expected_schema_id
                    or recipe.artifact_kind != dependency.expected_artifact_kind
                ):
                    _block(
                        "anchor.plan.dependency_unresolved",
                        f"preprocessing dependency {dependency.dependency_id} "
                        "does not resolve exactly",
                        anchor_id=consumer.anchor_id,
                    )


def _validate_provider_graph(plan: AnchorExecutionPlan) -> None:
    recipes: dict[str, ResolvedPreprocessingRecipe] = {}
    for recipe in plan.preprocessing_recipes:
        if recipe.recipe_id in recipes:
            _block(
                "anchor.plan.duplicate_preprocessing_recipe",
                f"preprocessing recipe {recipe.recipe_id} repeats",
            )
        recipes[recipe.recipe_id] = recipe
    graph: dict[str, set[str]] = {recipe_id: set() for recipe_id in recipes}
    for recipe in plan.preprocessing_recipes:
        specs = {spec.dependency_id: spec for spec in recipe.dependency_specs}
        bindings: dict[str, str] = {}
        for binding in recipe.dependency_bindings:
            if binding.dependency_id in bindings:
                _block(
                    "anchor.plan.preprocessing_binding_duplicate",
                    f"recipe {recipe.recipe_id} repeats binding {binding.dependency_id}",
                )
            bindings[binding.dependency_id] = binding.target_recipe_id
        if set(specs) != set(bindings):
            _block(
                "anchor.plan.preprocessing_binding_mismatch",
                f"recipe {recipe.recipe_id} dependency specs and bindings differ",
            )
        for dependency_id, spec in specs.items():
            target = recipes.get(bindings[dependency_id])
            if (
                target is None
                or target.output_schema_id != spec.expected_schema_id
                or target.artifact_kind != spec.expected_artifact_kind
            ):
                _block(
                    "anchor.plan.preprocessing_dependency_unresolved",
                    f"recipe {recipe.recipe_id} dependency {dependency_id} "
                    "does not resolve exactly",
                )
            if target.scope_policy != recipe.scope_policy:
                _block(
                    "anchor.plan.preprocessing_scope_mismatch",
                    f"recipe {recipe.recipe_id} crosses preprocessing scope policies",
                )
            graph[recipe.recipe_id].add(target.recipe_id)
    _levels_from_graph(
        graph,
        {recipe_id: (index, recipe_id) for index, recipe_id in enumerate(recipes)},
        cycle_code="anchor.plan.preprocessing_cycle",
    )


def _validate_registry_bindings(plan: AnchorExecutionPlan, registry: PluginRegistry) -> str:
    trusted = registry.is_trusted
    if trusted:
        actual_registry_fingerprint = packaged_registry_fingerprint()
        try:
            catalog = load_packaged_catalog(plan.model_profile_id)
            actual_catalog_fingerprint = packaged_catalog_fingerprint(plan.model_profile_id)
        except (CatalogResourceError, TypeError, ValueError) as error:
            _block(
                "anchor.plan.catalog_unavailable",
                f"model profile has no packaged catalog: {error}",
            )
        if plan.catalog_fingerprint != actual_catalog_fingerprint:
            _block(
                "anchor.plan.catalog_fingerprint_mismatch",
                "plan catalog fingerprint does not match the packaged catalog",
            )
        if plan.registry_fingerprint != actual_registry_fingerprint:
            _block(
                "anchor.plan.registry_fingerprint_mismatch",
                "plan registry fingerprint does not match the packaged registry",
            )
        expected_recipe_ids = tuple(
            dict.fromkeys(
                cast(str, dependency.target_resource_id)
                for entry in catalog.entries
                for dependency in entry.dependencies
                if dependency.kind is DependencyKind.PREPROCESSING
            )
        )
        expected_profile_ids = tuple(
            cast(str, dependency.target_resource_id)
            for entry in catalog.entries
            for dependency in entry.dependencies
            if dependency.kind is DependencyKind.ALGORITHM_PROFILE
        )
        actual_recipe_ids = tuple(recipe.recipe_id for recipe in plan.preprocessing_recipes)
        actual_profile_ids = tuple(profile.profile_id for profile in plan.algorithm_profiles)
        if (
            plan.scientific_validation_status != catalog.scientific_validation_status
            or len(plan.entries) != len(catalog.entries)
            or actual_recipe_ids != expected_recipe_ids
            or actual_profile_ids != expected_profile_ids
        ):
            _block(
                "anchor.plan.catalog_inventory_mismatch",
                "production plan inventory differs from the packaged catalog",
            )
        for entry, expected in zip(plan.entries, catalog.entries, strict=True):
            required_inputs = (
                *(f"stream.{modality.value}" for modality in entry.required_streams),
                *entry.required_context_paths,
                *(f"reference.{reference_id}" for reference_id in entry.required_reference_ids),
                *entry.required_semantic_paths,
            )
            if (
                entry.anchor_id != expected.anchor_id
                or entry.definition_version != expected.definition_version
                or entry.lifecycle != expected.lifecycle.value
                or entry.canonical_order != expected.canonical_order
                or entry.plugin_id != expected.plugin_id
                or entry.plugin_version != expected.plugin_version
                or entry.parameter_schema_id != expected.parameter_schema_id
                or entry.scorer_policy.scorer_id != expected.scorer_id
                or required_inputs != expected.required_inputs
                or entry.dependencies != expected.dependencies
                or entry.artifact_recipes != expected.artifact_recipes
            ):
                _block(
                    "anchor.plan.catalog_inventory_mismatch",
                    f"production plan entry {entry.anchor_id} differs from the packaged catalog",
                    anchor_id=entry.anchor_id,
                )
    else:
        actual_registry_fingerprint = plan.registry_fingerprint

    for entry in plan.entries:
        definition = _reconstructed_plugin_definition(entry)
        if plugin_definition_fingerprint(definition) != entry.definition_fingerprint:
            _block(
                "anchor.plan.definition_fingerprint_mismatch",
                f"plugin definition fingerprint is stale for {entry.anchor_id}",
                anchor_id=entry.anchor_id,
            )
        key = (entry.plugin_id, entry.plugin_version)
        if trusted:
            declared = registry.declared_plugin_entry(*key)
            if declared is None:
                _block(
                    "anchor.plan.plugin_not_implemented",
                    f"plugin {key!r} is not implemented",
                    anchor_id=entry.anchor_id,
                )
            if (
                declared.anchor_id != entry.anchor_id
                or declared.definition_version != entry.definition_version
                or declared.api_version != entry.api_version
                or declared.definition_fingerprint != entry.definition_fingerprint
                or declared.implementation_digest != entry.implementation_digest
                or declared.parameter_schema_id != entry.parameter_schema_id
                or declared.measurement_schema_id != entry.measurement_schema_id
            ):
                _block(
                    "anchor.plan.registry_identity_mismatch",
                    f"plugin registry identity differs for {entry.anchor_id}",
                    anchor_id=entry.anchor_id,
                )
        elif not registry.has_injected_plugin_factory(*key):
            _block(
                "anchor.plan.plugin_not_implemented",
                f"test plugin {key!r} is not registered",
                anchor_id=entry.anchor_id,
            )

    for recipe in plan.preprocessing_recipes:
        definition = _reconstructed_provider_definition(recipe)
        if preprocessing_definition_fingerprint(definition) != recipe.definition_fingerprint:
            _block(
                "anchor.plan.preprocessing_definition_fingerprint_mismatch",
                f"provider definition fingerprint is stale for {recipe.recipe_id}",
            )
        key = (recipe.provider_id, recipe.provider_version)
        if trusted:
            declared = registry.declared_preprocessing_entry(*key)
            if declared is None:
                _block(
                    "anchor.plan.preprocessing_not_implemented",
                    f"preprocessing provider {key!r} is not implemented",
                )
            if (
                declared.definition_fingerprint != recipe.definition_fingerprint
                or declared.implementation_digest != recipe.implementation_digest
                or declared.parameter_schema_id != recipe.parameter_schema_id
                or declared.parameter_schema_sha256 != recipe.parameter_schema_sha256
                or declared.output_schema_id != recipe.output_schema_id
                or declared.output_schema_sha256 != recipe.output_schema_sha256
                or declared.artifact_kind != recipe.artifact_kind
                or declared.output_payload_kind != recipe.output_payload_kind
            ):
                _block(
                    "anchor.plan.preprocessing_registry_identity_mismatch",
                    f"provider registry identity differs for {recipe.recipe_id}",
                )
        elif not registry.has_injected_preprocessing_factory(*key):
            _block(
                "anchor.plan.preprocessing_not_implemented",
                f"test preprocessing provider {key!r} is not registered",
            )
    return actual_registry_fingerprint


def validate_execution_plan(
    plan: AnchorExecutionPlan,
    registry: PluginRegistry,
) -> PlanValidationOutcome:
    """Validate a complete plan without importing or invoking any factory."""

    try:
        if not isinstance(plan, AnchorExecutionPlan) or not isinstance(registry, PluginRegistry):
            _block("anchor.plan.invalid_type", "plan and registry must be typed M4 objects")
        entries, _graph = _anchor_edges(plan.entries)
        ordered = tuple(
            sorted(plan.entries, key=lambda item: (item.canonical_order, item.anchor_id))
        )
        if plan.entries != ordered:
            _block("anchor.plan.noncanonical_order", "execution entries are not canonical")
        levels = topological_levels(plan.entries)
        _validate_dependency_contracts(plan)
        _validate_provider_graph(plan)
        for entry in entries.values():
            _validate_parameter_object(
                entry.parameter_schema_id,
                entry.parameters,
                entry.parameter_hash,
                anchor_id=entry.anchor_id,
            )
            _validate_scorer(entry)
        for recipe in plan.preprocessing_recipes:
            if (
                parameter_schema_sha256(recipe.parameter_schema_id)
                != recipe.parameter_schema_sha256
            ):
                _block(
                    "anchor.plan.parameter_schema_hash_mismatch",
                    f"provider schema hash is stale for {recipe.recipe_id}",
                )
            _validate_parameter_object(
                recipe.parameter_schema_id,
                recipe.parameters,
                recipe.parameter_hash,
                anchor_id=None,
            )
        for profile in plan.algorithm_profiles:
            if parameter_snapshot_fingerprint(profile.parameters) != profile.parameter_hash:
                _block(
                    "anchor.plan.algorithm_profile_fingerprint_mismatch",
                    f"algorithm profile hash is stale for {profile.profile_id}",
                )
        registry_fingerprint = _validate_registry_bindings(plan, registry)
        return PlanValidationOutcome(
            disposition="valid",
            validated_plan=ValidatedExecutionPlan(
                plan=plan,
                levels=levels,
                registry_fingerprint=registry_fingerprint,
            ),
            diagnostics=(),
        )
    except _PlanBlocked as error:
        return PlanValidationOutcome(
            disposition="blocked",
            validated_plan=None,
            diagnostics=(_diagnostic(error),),
        )
    except (CatalogResourceError, SchemaError, ValidationError, TypeError, ValueError) as error:
        wrapped = _PlanBlocked("anchor.plan.invalid", f"execution plan is invalid: {error}")
        return PlanValidationOutcome(
            disposition="blocked",
            validated_plan=None,
            diagnostics=(_diagnostic(wrapped),),
        )


def _validate_o6_request_closure(request: AnchorEvaluationRequest) -> None:
    entry = next(
        (candidate for candidate in request.execution_plan.entries if candidate.anchor_id == "O6"),
        None,
    )
    if entry is None:
        return
    applicability = next(
        (
            item
            for item in request.session_semantic_snapshot.applicability
            if item.anchor_id == "O6"
        ),
        None,
    )
    if applicability is None:
        _block("anchor.plan.o6_semantic_mismatch", "O6 applicability is missing", anchor_id="O6")
    raw_weights = entry.parameters.get("channel_weights")
    if not isinstance(raw_weights, (list, tuple)):
        _block(
            "anchor.plan.o6_parameter_mismatch",
            "O6 channel_weights must be a materialized ordered array",
            anchor_id="O6",
        )
    if applicability.status is not SemanticApplicabilityStatus.APPLICABLE:
        if tuple(raw_weights) != ():
            _block(
                "anchor.plan.o6_parameter_mismatch",
                "not-applicable O6 requires channel_weights=[]",
                anchor_id="O6",
            )
        return

    mappings = {
        mapping.control_mapping_id: mapping
        for mapping in request.session_semantic_snapshot.control_mappings
    }
    selected = []
    for mapping_id in applicability.control_mapping_ids:
        mapping = mappings.get(mapping_id)
        if mapping is None:
            _block(
                "anchor.plan.o6_semantic_mismatch",
                f"O6 control mapping {mapping_id} is unresolved",
                anchor_id="O6",
            )
        selected.append(mapping)
    if not selected:
        _block(
            "anchor.plan.o6_semantic_mismatch",
            "applicable O6 requires at least one control channel",
            anchor_id="O6",
        )

    calibration_by_channel: dict[str, tuple[str, float, float, float]] = {}
    for mapping in selected:
        calibration = (mapping.control_unit, mapping.lower, mapping.trim, mapping.upper)
        previous = calibration_by_channel.setdefault(mapping.control_channel_id, calibration)
        if previous != calibration:
            _block(
                "anchor.plan.o6_semantic_mismatch",
                f"O6 channel {mapping.control_channel_id} has conflicting calibration",
                anchor_id="O6",
            )
    expected_channels = tuple(sorted(calibration_by_channel))
    parsed: list[tuple[str, float]] = []
    for item in raw_weights:
        if not isinstance(item, Mapping) or set(item) != {"channel_id", "weight"}:
            _block(
                "anchor.plan.o6_parameter_mismatch",
                "O6 weight items require exact channel_id/weight fields",
                anchor_id="O6",
            )
        channel_id = item["channel_id"]
        weight = item["weight"]
        if (
            type(channel_id) is not str
            or isinstance(weight, bool)
            or not isinstance(weight, (int, float))
            or not math.isfinite(float(weight))
            or float(weight) < 0.0
        ):
            _block(
                "anchor.plan.o6_parameter_mismatch",
                "O6 weights require stable channel IDs and finite non-negative numbers",
                anchor_id="O6",
            )
        parsed.append((channel_id, float(weight)))
    channels = tuple(channel for channel, _weight in parsed)
    if channels != expected_channels or len(channels) != len(set(channels)):
        _block(
            "anchor.plan.o6_parameter_mismatch",
            "O6 weights must exactly cover canonical applicable channels",
            anchor_id="O6",
        )
    if abs(math.fsum(weight for _channel, weight in parsed) - 1.0) > 1e-12:
        _block(
            "anchor.plan.o6_parameter_mismatch",
            "O6 channel weights must sum to one",
            anchor_id="O6",
        )


def _algorithm_profile_parameters(
    request: AnchorEvaluationRequest,
    source_anchor_id: str,
) -> dict[str, JsonValue]:
    plan = request.execution_plan
    semantic = request.session_semantic_snapshot
    source_entry = next(
        (entry for entry in plan.entries if entry.anchor_id == source_anchor_id),
        None,
    )
    applicability = next(
        (item for item in semantic.applicability if item.anchor_id == source_anchor_id),
        None,
    )
    if source_entry is None or applicability is None:
        _block(
            "anchor.plan.algorithm_profile_mismatch",
            f"algorithm profile source {source_anchor_id} is incomplete",
            anchor_id="O13",
        )
    phase_by_id = {phase.phase_id: phase for phase in semantic.phases}
    envelope_by_id = {envelope.envelope_id: envelope for envelope in semantic.envelopes}
    mapping_by_id = {mapping.control_mapping_id: mapping for mapping in semantic.control_mappings}
    recipes = {recipe.recipe_id: recipe for recipe in plan.preprocessing_recipes}
    selected_recipe_ids = tuple(
        cast(str, dependency.target_resource_id)
        for dependency in source_entry.dependencies
        if dependency.kind is DependencyKind.PREPROCESSING
    )
    expected_recipe_ids = () if source_anchor_id == "O1" else ("movement-events-v1",)
    if selected_recipe_ids != expected_recipe_ids or any(
        recipe_id not in recipes for recipe_id in selected_recipe_ids
    ):
        _block(
            "anchor.plan.algorithm_profile_mismatch",
            f"{source_anchor_id} preprocessing profile does not match its exact inventory",
            anchor_id="O13",
        )
    if any(phase_id not in phase_by_id for phase_id in applicability.phase_ids):
        _block(
            "anchor.plan.algorithm_profile_mismatch",
            f"{source_anchor_id} phase projection is unresolved",
            anchor_id="O13",
        )
    selected_phases = tuple(phase_by_id[phase_id] for phase_id in applicability.phase_ids)
    if any(envelope_id not in envelope_by_id for envelope_id in applicability.envelope_ids):
        _block(
            "anchor.plan.algorithm_profile_mismatch",
            f"{source_anchor_id} envelope projection is unresolved",
            anchor_id="O13",
        )
    selected_envelopes = (
        tuple(envelope_by_id[envelope_id] for envelope_id in applicability.envelope_ids)
        if source_anchor_id == "O1"
        else ()
    )
    if any(mapping_id not in mapping_by_id for mapping_id in applicability.control_mapping_ids):
        _block(
            "anchor.plan.algorithm_profile_mismatch",
            f"{source_anchor_id} control projection is unresolved",
            anchor_id="O13",
        )
    selected_mappings = (
        tuple(mapping_by_id[mapping_id] for mapping_id in applicability.control_mapping_ids)
        if source_anchor_id in {"O5", "O7"}
        else ()
    )
    if source_anchor_id == "O1":
        reachable_envelopes = tuple(
            sorted(
                {phase.envelope_id for phase in selected_phases if phase.envelope_id is not None}
            )
        )
        if any(
            phase.envelope_id is None for phase in selected_phases
        ) or reachable_envelopes != tuple(applicability.envelope_ids):
            _block(
                "anchor.plan.algorithm_profile_mismatch",
                "O1 phases and envelopes do not form an exact reachable projection",
                anchor_id="O13",
            )
    elif not selected_mappings:
        _block(
            "anchor.plan.algorithm_profile_mismatch",
            f"{source_anchor_id} requires a non-empty configured control-channel projection",
            anchor_id="O13",
        )
    if source_anchor_id in {"O5", "O7"}:
        selected_channels = tuple(
            sorted({mapping.control_channel_id for mapping in selected_mappings})
        )
        if not selected_channels:
            _block(
                "anchor.plan.algorithm_profile_mismatch",
                f"{source_anchor_id} has no materialized source channels",
                anchor_id="O13",
            )
    input_contracts = tuple(
        contract
        for contract in plan.input_table_contracts
        if contract.modality in source_entry.required_streams
    )
    return cast(
        dict[str, JsonValue],
        {
            "semantic_snapshot_fingerprint": plan.semantic_snapshot_fingerprint,
            "source_entry": source_entry.model_dump(mode="json"),
            "parameter_schema_sha256": parameter_schema_sha256(source_entry.parameter_schema_id),
            "applicability": applicability.model_dump(mode="json"),
            "input_table_contracts": [
                contract.model_dump(mode="json") for contract in input_contracts
            ],
            "semantic_projection": {
                "phases": [phase.model_dump(mode="json") for phase in selected_phases],
                "envelopes": [envelope.model_dump(mode="json") for envelope in selected_envelopes],
                "control_mappings": [
                    mapping.model_dump(mode="json") for mapping in selected_mappings
                ],
            },
            "preprocessing_recipes": [
                recipes[recipe_id].model_dump(mode="json") for recipe_id in selected_recipe_ids
            ],
        },
    )


def _validate_algorithm_profile_request_closure(request: AnchorEvaluationRequest) -> None:
    plan = request.execution_plan
    o13 = next((entry for entry in plan.entries if entry.anchor_id == "O13"), None)
    algorithm_dependencies = (
        ()
        if o13 is None
        else tuple(
            dependency
            for dependency in o13.dependencies
            if dependency.kind is DependencyKind.ALGORITHM_PROFILE
        )
    )
    if not algorithm_dependencies and plan.model_profile_id != "reference-model-v0.1":
        return
    expected_rows = {
        "O1": ("o1-profile", "o1-algorithm-profile", "o1-algorithm-profile-output-v0.1"),
        "O5": ("o5-profile", "o5-algorithm-profile", "o5-algorithm-profile-output-v0.1"),
        "O7": ("o7-profile", "o7-algorithm-profile", "o7-algorithm-profile-output-v0.1"),
    }
    expected_dependencies = tuple(
        (dependency_id, profile_id, output_schema_id)
        for dependency_id, profile_id, output_schema_id in expected_rows.values()
    )
    actual_dependencies = tuple(
        (
            dependency.dependency_id,
            dependency.target_resource_id,
            dependency.expected_schema_id,
        )
        for dependency in algorithm_dependencies
    )
    if o13 is None or actual_dependencies != expected_dependencies:
        _block(
            "anchor.plan.algorithm_profile_mismatch",
            "O13 must bind the exact O1/O5/O7 algorithm-profile inventory",
            anchor_id="O13",
        )
    entries = {entry.anchor_id: entry for entry in plan.entries}
    profiles = {profile.profile_id: profile for profile in plan.algorithm_profiles}
    if set(profiles) != {
        profile_id for _dependency_id, profile_id, _schema_id in expected_rows.values()
    }:
        _block(
            "anchor.plan.algorithm_profile_mismatch",
            "execution plan must contain exactly the O1/O5/O7 algorithm profiles",
            anchor_id="O13",
        )
    applicability = {
        item.anchor_id: item for item in request.session_semantic_snapshot.applicability
    }
    o13_applicable = o13.applicability is SemanticApplicabilityStatus.APPLICABLE
    for source_anchor_id, (
        _dependency_id,
        profile_id,
        output_schema_id,
    ) in expected_rows.items():
        source_entry = entries.get(source_anchor_id)
        profile = profiles.get(profile_id)
        source_applicability = applicability.get(source_anchor_id)
        if source_entry is None or profile is None or source_applicability is None:
            _block(
                "anchor.plan.algorithm_profile_mismatch",
                f"algorithm profile source {source_anchor_id} is incomplete",
                anchor_id="O13",
            )
        expected_parameters = _algorithm_profile_parameters(request, source_anchor_id)
        if (
            profile.profile_version != source_entry.definition_version
            or profile.output_schema_id != output_schema_id
            or profile.implementation_digest != source_entry.implementation_digest
            or profile.parameters != expected_parameters
            or profile.parameter_hash != parameter_snapshot_fingerprint(expected_parameters)
        ):
            _block(
                "anchor.plan.algorithm_profile_mismatch",
                f"algorithm profile {profile_id} differs from its authoritative closure",
                anchor_id="O13",
            )
        if o13_applicable and (
            source_applicability.status is not SemanticApplicabilityStatus.APPLICABLE
            or not set(o13.phase_scope) <= set(source_applicability.phase_ids)
        ):
            _block(
                "anchor.plan.algorithm_profile_mismatch",
                f"O13 phase scope is outside applicable {source_anchor_id} phases",
                anchor_id="O13",
            )


def validate_request_bound_execution_plan(
    request: AnchorEvaluationRequest,
    registry: PluginRegistry,
) -> PlanValidationOutcome:
    """Validate plan-only identity plus semantic materialization bound by the request."""

    outcome = validate_execution_plan(request.execution_plan, registry)
    if outcome.disposition == "blocked":
        return outcome
    try:
        _validate_o6_request_closure(request)
        _validate_algorithm_profile_request_closure(request)
    except _PlanBlocked as error:
        return PlanValidationOutcome(
            disposition="blocked",
            validated_plan=None,
            diagnostics=(_diagnostic(error),),
        )
    except (
        CatalogResourceError,
        SchemaError,
        ValidationError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        wrapped = _PlanBlocked(
            "anchor.plan.request_closure_invalid",
            f"request-bound plan closure is invalid: {error}",
        )
        return PlanValidationOutcome(
            disposition="blocked",
            validated_plan=None,
            diagnostics=(_diagnostic(wrapped),),
        )
    return outcome


def _request_fingerprint_error(field_name: str, reason: str) -> NoReturn:
    raise AnchorRequestValidationError(
        "request_fingerprint_mismatch",
        {"field": field_name, "reason": reason},
    )


def validate_anchor_evaluation_request(request: AnchorEvaluationRequest) -> None:
    """Idempotently recompute the complete M3/M4 request identity closure."""

    if not isinstance(request, AnchorEvaluationRequest):
        raise AnchorRequestValidationError(
            "request_session_mismatch",
            {"field": "request", "reason": "invalid_runtime_type"},
        )

    # Keep the documented stable error precedence even when a caller mutated a
    # nested runtime object after request construction.
    request._validate_session_identity()
    request._validate_semantic_relations()
    request._validate_reference_inventory_and_provenance()

    semantic = request.session_semantic_snapshot
    if session_semantic_snapshot_fingerprint(semantic) != semantic.semantic_snapshot_fingerprint:
        _request_fingerprint_error("session_semantic_snapshot", "stale_canonical_digest")

    descriptors = []
    for reference_id in sorted(request.resolved_references.entries):
        resolved = request.resolved_references.entries[reference_id]
        descriptor = resolved.descriptor
        contract = descriptor.table_contract
        if reference_table_contract_fingerprint(contract) != contract.table_contract_fingerprint:
            _request_fingerprint_error(
                f"resolved_references.{reference_id}.table_contract",
                "stale_canonical_digest",
            )
        if descriptor.resolution_status.value == "present":
            view = resolved.aligned_view
            if view is None:
                _request_fingerprint_error(
                    f"resolved_references.{reference_id}", "present_without_view"
                )
            table = view.tables.get(contract.table_role)
            if table is None:
                _request_fingerprint_error(
                    f"resolved_references.{reference_id}", "reference_table_missing"
                )
            if reference_resource_fingerprint(descriptor) != descriptor.resource_fingerprint:
                _request_fingerprint_error(
                    f"resolved_references.{reference_id}.resource_fingerprint",
                    "stale_canonical_digest",
                )
            if (
                aligned_reference_content_fingerprint(table, descriptor.aligned_schema_id, contract)
                != descriptor.aligned_content_fingerprint
            ):
                _request_fingerprint_error(
                    f"resolved_references.{reference_id}.aligned_content_fingerprint",
                    "stale_canonical_digest",
                )
            if (
                reference_alignment_fingerprint(
                    descriptor, request.resolved_references.session_identity
                )
                != descriptor.alignment_fingerprint
            ):
                _request_fingerprint_error(
                    f"resolved_references.{reference_id}.alignment_fingerprint",
                    "stale_canonical_digest",
                )
        elif (
            resolved.aligned_view is not None
            or descriptor.resource_checksums
            or descriptor.resource_fingerprint is not None
            or descriptor.aligned_content_fingerprint is not None
            or descriptor.alignment_fingerprint is not None
        ):
            _request_fingerprint_error(
                f"resolved_references.{reference_id}", "invalid_absent_reference_identity"
            )
        descriptors.append(descriptor)

    snapshot = ResolvedReferenceSetSnapshot(
        session_identity=request.resolved_references.session_identity,
        descriptors=tuple(descriptors),
        reference_set_fingerprint=request.resolved_references.reference_set_fingerprint,
    )
    if (
        resolved_reference_set_fingerprint(snapshot)
        != request.resolved_references.reference_set_fingerprint
    ):
        _request_fingerprint_error("resolved_references", "stale_canonical_digest")

    plan = request.execution_plan
    for entry in plan.entries:
        if parameter_snapshot_fingerprint(entry.parameters) != entry.parameter_hash:
            _request_fingerprint_error(
                f"execution_plan.entries.{entry.anchor_id}.parameter_hash",
                "stale_canonical_digest",
            )
        if scorer_policy_fingerprint(entry.scorer_policy) != entry.scorer_policy.policy_hash:
            _request_fingerprint_error(
                f"execution_plan.entries.{entry.anchor_id}.scorer_policy",
                "stale_canonical_digest",
            )
    for recipe in plan.preprocessing_recipes:
        if parameter_snapshot_fingerprint(recipe.parameters) != recipe.parameter_hash:
            _request_fingerprint_error(
                f"execution_plan.preprocessing_recipes.{recipe.recipe_id}",
                "stale_canonical_digest",
            )
    for profile in plan.algorithm_profiles:
        if parameter_snapshot_fingerprint(profile.parameters) != profile.parameter_hash:
            _request_fingerprint_error(
                f"execution_plan.algorithm_profiles.{profile.profile_id}",
                "stale_canonical_digest",
            )
    expected_plan_fingerprint: Sha256Digest = typed_json_sha256(
        plan.contract_id,
        plan.contract_version,
        execution_plan_fingerprint_payload(plan),
    )
    if expected_plan_fingerprint != plan.plan_fingerprint:
        _request_fingerprint_error("execution_plan.plan_fingerprint", "stale_canonical_digest")
    request._validate_fingerprint_closure()


__all__ = [
    "EvaluationPolicy",
    "PlanValidationOutcome",
    "TestFaultHooks",
    "ValidatedExecutionPlan",
    "topological_levels",
    "validate_anchor_evaluation_request",
    "validate_execution_plan",
    "validate_request_bound_execution_plan",
]
