"""Evaluation-local preprocessing resolution with exact identity memoization."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Literal, NoReturn

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from pilot_assessment.anchors.catalog import (
    load_parameter_schema,
    parameter_schema_sha256,
)
from pilot_assessment.anchors.fingerprint import (
    parameter_snapshot_fingerprint,
    typed_json_sha256,
)
from pilot_assessment.anchors.protocols import (
    AnchorPluginContext,
    EvaluationArtifactTransaction,
    PreprocessingProducer,
    PreprocessingProvider,
    PreprocessingScope,
    ResolvedPreprocessingDependency,
)
from pilot_assessment.anchors.registry import PluginRegistry, RegistryResolutionError
from pilot_assessment.contracts.anchor_execution import (
    PreprocessingProviderDefinition,
    ResolvedPreprocessingRecipe,
)
from pilot_assessment.contracts.common import Sha256Digest

_ScopeKind = Literal["session", "phase", "event", "window"]
InputFingerprint = tuple[str, str, Sha256Digest]


class PreprocessingResolutionError(ValueError):
    """Stable provider-resolution failure mapped to consumer dependency_missing."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _fail(code: str, message: str) -> NoReturn:
    raise PreprocessingResolutionError(code, message)


def _normalize_input_fingerprints(
    values: tuple[InputFingerprint, ...],
) -> tuple[InputFingerprint, ...]:
    if not isinstance(values, tuple):
        raise TypeError("input fingerprints must be a tuple")
    for value in values:
        if (
            not isinstance(value, tuple)
            or len(value) != 3
            or any(type(part) is not str or not part for part in value)
            or len(value[2]) != 64
        ):
            raise ValueError("input fingerprint entries must be typed kind/ID/SHA-256 triples")
    if values != tuple(sorted(values)) or len(values) != len(set(values)):
        raise ValueError("input fingerprints must be unique and canonically ordered")
    return values


@dataclass(frozen=True, slots=True)
class PreprocessingCacheKey:
    recipe_id: str
    recipe_version: str
    provider_id: str
    provider_version: str
    implementation_digest: Sha256Digest
    parameter_schema_id: str
    parameter_schema_sha256: Sha256Digest
    parameter_hash: Sha256Digest
    scope_kind: _ScopeKind
    scope_id: str
    scope_start_t_ns: int
    scope_end_t_ns: int
    phase_id: str | None
    event_id: str | None
    window_id: str | None
    input_fingerprints: tuple[InputFingerprint, ...]
    dependency_fingerprints: tuple[Sha256Digest, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "input_fingerprints",
            _normalize_input_fingerprints(self.input_fingerprints),
        )


@dataclass(frozen=True, slots=True)
class PreprocessingResolutionContext:
    """Positive per-recipe provider contexts and their declared input identities."""

    provider_contexts: Mapping[str, AnchorPluginContext]
    input_fingerprints: Mapping[str, tuple[InputFingerprint, ...]]

    def __post_init__(self) -> None:
        contexts: dict[str, AnchorPluginContext] = {}
        for recipe_id, context in self.provider_contexts.items():
            if type(recipe_id) is not str or not recipe_id:
                raise ValueError("provider context keys must be stable recipe IDs")
            if not isinstance(context, AnchorPluginContext):
                raise TypeError("provider contexts must contain AnchorPluginContext values")
            contexts[recipe_id] = context
        fingerprints = {
            recipe_id: _normalize_input_fingerprints(tuple(values))
            for recipe_id, values in self.input_fingerprints.items()
        }
        if set(contexts) != set(fingerprints):
            raise ValueError("provider contexts and input fingerprints must have equal inventory")
        object.__setattr__(self, "provider_contexts", MappingProxyType(contexts))
        object.__setattr__(self, "input_fingerprints", MappingProxyType(fingerprints))


def preprocessing_cache_key_fingerprint(key: PreprocessingCacheKey) -> Sha256Digest:
    return typed_json_sha256("preprocessing-cache-key", "0.1.0", asdict(key))


def preprocessing_dependency_fingerprint(
    dependency: ResolvedPreprocessingDependency,
) -> Sha256Digest:
    if not isinstance(dependency, ResolvedPreprocessingDependency):
        raise TypeError("dependency must be a ResolvedPreprocessingDependency")
    identity = asdict(dependency.identity)
    return typed_json_sha256(
        "preprocessing-dependency",
        "0.1.0",
        [identity, dependency.payload.logical_content_sha256],
    )


def _definition(recipe: ResolvedPreprocessingRecipe) -> PreprocessingProviderDefinition:
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


def _validate_parameters(recipe: ResolvedPreprocessingRecipe) -> None:
    try:
        if parameter_schema_sha256(recipe.parameter_schema_id) != recipe.parameter_schema_sha256:
            _fail(
                "provider_parameter_schema_mismatch",
                f"parameter schema bytes differ for recipe {recipe.recipe_id}",
            )
        schema = load_parameter_schema(recipe.parameter_schema_id)
        Draft202012Validator.check_schema(dict(schema))
        errors = tuple(Draft202012Validator(dict(schema)).iter_errors(dict(recipe.parameters)))
    except PreprocessingResolutionError:
        raise
    except (SchemaError, TypeError, ValueError) as error:
        raise PreprocessingResolutionError(
            "provider_parameter_schema_invalid",
            f"parameter schema cannot be validated for recipe {recipe.recipe_id}",
        ) from error
    if errors:
        raise PreprocessingResolutionError(
            "provider_parameter_invalid",
            f"parameters do not satisfy the schema for recipe {recipe.recipe_id}",
        ) from errors[0]
    if parameter_snapshot_fingerprint(recipe.parameters) != recipe.parameter_hash:
        _fail(
            "provider_parameter_fingerprint_mismatch",
            f"parameter fingerprint is stale for recipe {recipe.recipe_id}",
        )


class PreprocessingResolver:
    """Resolve provider recipes once per exact key inside one evaluation."""

    def __init__(
        self,
        registry: PluginRegistry,
        recipes: tuple[ResolvedPreprocessingRecipe, ...],
    ) -> None:
        if not isinstance(registry, PluginRegistry):
            raise TypeError("registry must be a PluginRegistry")
        if not isinstance(recipes, tuple) or any(
            not isinstance(recipe, ResolvedPreprocessingRecipe) for recipe in recipes
        ):
            raise TypeError("recipes must be a typed tuple")
        by_id = {recipe.recipe_id: recipe for recipe in recipes}
        if len(by_id) != len(recipes):
            raise ValueError("preprocessing recipe IDs must be unique")
        self._registry = registry
        self._recipes = MappingProxyType(by_id)
        self._cache: dict[PreprocessingCacheKey, ResolvedPreprocessingDependency] = {}
        self._resolving: set[str] = set()

    def _key(
        self,
        recipe: ResolvedPreprocessingRecipe,
        scope: PreprocessingScope,
        input_fingerprints: tuple[InputFingerprint, ...],
        dependency_fingerprints: tuple[Sha256Digest, ...],
    ) -> PreprocessingCacheKey:
        return PreprocessingCacheKey(
            recipe_id=recipe.recipe_id,
            recipe_version=recipe.recipe_version,
            provider_id=recipe.provider_id,
            provider_version=recipe.provider_version,
            implementation_digest=recipe.implementation_digest,
            parameter_schema_id=recipe.parameter_schema_id,
            parameter_schema_sha256=recipe.parameter_schema_sha256,
            parameter_hash=recipe.parameter_hash,
            scope_kind=scope.kind,
            scope_id=scope.scope_id,
            scope_start_t_ns=scope.start_t_ns,
            scope_end_t_ns=scope.end_t_ns,
            phase_id=scope.phase_id,
            event_id=scope.event_id,
            window_id=scope.window_id,
            input_fingerprints=input_fingerprints,
            dependency_fingerprints=dependency_fingerprints,
        )

    def resolve(
        self,
        recipe: ResolvedPreprocessingRecipe,
        context: PreprocessingResolutionContext,
        scope: PreprocessingScope,
        evaluation_transaction: EvaluationArtifactTransaction,
    ) -> ResolvedPreprocessingDependency:
        if not isinstance(recipe, ResolvedPreprocessingRecipe):
            raise TypeError("recipe must be a ResolvedPreprocessingRecipe")
        if not isinstance(context, PreprocessingResolutionContext):
            raise TypeError("context must be a PreprocessingResolutionContext")
        if not isinstance(scope, PreprocessingScope):
            raise TypeError("scope must be a PreprocessingScope")
        canonical = self._recipes.get(recipe.recipe_id)
        if canonical is None or canonical != recipe:
            _fail("provider_recipe_unvalidated", "recipe is not the resolver's validated object")
        if scope.kind != recipe.scope_policy:
            _fail(
                "provider_scope_mismatch",
                f"scope kind does not match recipe {recipe.recipe_id}",
            )
        provider_context = context.provider_contexts.get(recipe.recipe_id)
        input_fingerprints = context.input_fingerprints.get(recipe.recipe_id)
        if provider_context is None or input_fingerprints is None:
            _fail(
                "provider_projection_missing",
                f"positive provider projection is missing for {recipe.recipe_id}",
            )
        if recipe.recipe_id in self._resolving:
            _fail("provider_dependency_cycle", "provider dependency graph contains a cycle")

        self._resolving.add(recipe.recipe_id)
        try:
            specs = {spec.dependency_id: spec for spec in recipe.dependency_specs}
            bindings = {binding.dependency_id: binding for binding in recipe.dependency_bindings}
            if set(specs) != set(bindings):
                _fail(
                    "provider_binding_mismatch",
                    f"recipe {recipe.recipe_id} dependency binding inventory differs",
                )
            dependencies: dict[str, ResolvedPreprocessingDependency] = {}
            dependency_fingerprints: list[Sha256Digest] = []
            for spec in recipe.dependency_specs:
                binding = bindings[spec.dependency_id]
                target = self._recipes.get(binding.target_recipe_id)
                if (
                    target is None
                    or target.output_schema_id != spec.expected_schema_id
                    or target.artifact_kind != spec.expected_artifact_kind
                    or target.scope_policy != recipe.scope_policy
                ):
                    _fail(
                        "provider_dependency_unresolved",
                        f"dependency {spec.dependency_id} does not resolve exactly",
                    )
                resolved = self.resolve(target, context, scope, evaluation_transaction)
                dependencies[spec.dependency_id] = resolved
                dependency_fingerprints.append(preprocessing_dependency_fingerprint(resolved))

            key = self._key(
                recipe,
                scope,
                input_fingerprints,
                tuple(dependency_fingerprints),
            )
            cached = self._cache.get(key)
            if cached is not None:
                return cached

            _validate_parameters(recipe)
            try:
                provider = self._registry.resolve_preprocessor(
                    recipe.provider_id,
                    recipe.provider_version,
                    recipe.implementation_digest,
                )
            except RegistryResolutionError as error:
                raise PreprocessingResolutionError(
                    "provider_resolution_failed",
                    f"provider cannot be resolved for recipe {recipe.recipe_id}",
                ) from error
            self._validate_live_definition(provider, recipe)
            try:
                payload = provider.compute(
                    provider_context,
                    recipe,
                    scope,
                    MappingProxyType(dependencies),
                )
            except Exception as error:
                raise PreprocessingResolutionError(
                    "provider_compute_failed",
                    f"provider compute failed for recipe {recipe.recipe_id}",
                ) from error

            producer = PreprocessingProducer(
                recipe_id=recipe.recipe_id,
                recipe_version=recipe.recipe_version,
                provider_id=recipe.provider_id,
                provider_version=recipe.provider_version,
                implementation_digest=recipe.implementation_digest,
                parameter_schema_id=recipe.parameter_schema_id,
                parameter_schema_sha256=recipe.parameter_schema_sha256,
                parameter_hash=recipe.parameter_hash,
                output_schema_id=recipe.output_schema_id,
                output_schema_sha256=recipe.output_schema_sha256,
                artifact_kind=recipe.artifact_kind,
                output_payload_kind=recipe.output_payload_kind,
                scope_kind=scope.kind,
                scope_id=scope.scope_id,
                scope_start_t_ns=scope.start_t_ns,
                scope_end_t_ns=scope.end_t_ns,
                phase_id=scope.phase_id,
                event_id=scope.event_id,
                window_id=scope.window_id,
                input_fingerprints=input_fingerprints,
                dependency_fingerprints=tuple(dependency_fingerprints),
            )
            try:
                result = evaluation_transaction.stage_preprocessing(producer, payload)
            except Exception as error:
                raise PreprocessingResolutionError(
                    "provider_artifact_invalid",
                    f"provider output is invalid for recipe {recipe.recipe_id}",
                ) from error
            self._cache[key] = result
            return result
        finally:
            self._resolving.discard(recipe.recipe_id)

    @staticmethod
    def _validate_live_definition(
        provider: PreprocessingProvider,
        recipe: ResolvedPreprocessingRecipe,
    ) -> None:
        try:
            definition = provider.definition()
        except Exception as error:
            raise PreprocessingResolutionError(
                "provider_definition_failed",
                f"provider definition failed for recipe {recipe.recipe_id}",
            ) from error
        if not isinstance(definition, PreprocessingProviderDefinition) or definition != _definition(
            recipe
        ):
            _fail(
                "provider_definition_mismatch",
                f"live provider definition differs for recipe {recipe.recipe_id}",
            )


__all__ = [
    "InputFingerprint",
    "PreprocessingCacheKey",
    "PreprocessingResolutionContext",
    "PreprocessingResolutionError",
    "PreprocessingResolver",
    "preprocessing_cache_key_fingerprint",
    "preprocessing_dependency_fingerprint",
]
