from __future__ import annotations

from dataclasses import replace
from typing import Any

import polars as pl

from pilot_assessment.anchors.artifacts import InMemoryDerivedArtifactSink
from pilot_assessment.anchors.catalog import parameter_schema_sha256
from pilot_assessment.anchors.fingerprint import (
    parameter_snapshot_fingerprint,
    preprocessing_definition_fingerprint,
    schema_descriptor_sha256,
)
from pilot_assessment.anchors.protocols import (
    AnchorPluginContext,
    PreprocessingScope,
    ProjectedSemanticScope,
    TabularArtifactPayload,
)
from pilot_assessment.anchors.registry import PluginRegistry
from pilot_assessment.contracts.anchor_execution import (
    PreprocessingDependencySpec,
    PreprocessingProviderDefinition,
    ResolvedPreprocessingDependencyBinding,
    ResolvedPreprocessingRecipe,
)
from pilot_assessment.contracts.synchronization import SessionWindow
from pilot_assessment.synchronization.models import AlignedStreamView
from tests.anchors.test_dag import (
    _OUTPUT_DESCRIPTOR,
    SHA_A,
    SHA_B,
    _schema_defaults,
)


def _context() -> AnchorPluginContext:
    view = AlignedStreamView(
        modality="U",
        source_schema_id="u-raw-v0.1",
        aligned_schema_id="u-aligned-v0.1",
        clock_id="sim-clock",
        tables={
            "samples": pl.DataFrame(
                {"t_ns": [0, 1]},
                schema={"t_ns": pl.Int64},
            )
        },
        json_artifacts={},
        file_artifacts={},
        source_checksums={"streams/u.parquet": SHA_A},
    )
    return AnchorPluginContext(
        session_id="session-1",
        session_window=SessionWindow(end_t_ns=2, source="master-clock-x-mapped-coverage-v1"),
        streams={"U": view},
        context={},
        references={},
        semantic_scope=ProjectedSemanticScope(values={}),
    )


def _definition(
    provider_id: str,
    dependencies: tuple[PreprocessingDependencySpec, ...] = (),
) -> PreprocessingProviderDefinition:
    return PreprocessingProviderDefinition(
        provider_id=provider_id,
        provider_version="1.0.0",
        api_version="0.1.0",
        required_streams=("U",),
        required_context_paths=(),
        required_semantic_paths=(),
        required_reference_ids=(),
        dependencies=dependencies,
        parameter_schema_id="movement-events-v1-parameters-0.1",
        output_schema_id="test-events-v0.1",
        output_schema_descriptor=_OUTPUT_DESCRIPTOR,
        artifact_kind="event_trace",
        output_payload_kind="table",
    )


def _recipe(
    recipe_id: str,
    provider_id: str,
    *,
    dependencies: tuple[PreprocessingDependencySpec, ...] = (),
    bindings: tuple[ResolvedPreprocessingDependencyBinding, ...] = (),
) -> ResolvedPreprocessingRecipe:
    definition = _definition(provider_id, dependencies)
    parameters = _schema_defaults(definition.parameter_schema_id)
    return ResolvedPreprocessingRecipe(
        recipe_id=recipe_id,
        recipe_version="0.1.0",
        provider_id=provider_id,
        provider_version="1.0.0",
        api_version="0.1.0",
        definition_fingerprint=preprocessing_definition_fingerprint(definition),
        implementation_digest=SHA_B,
        parameter_schema_id=definition.parameter_schema_id,
        parameter_schema_sha256=parameter_schema_sha256(definition.parameter_schema_id),
        parameters=parameters,
        parameter_hash=parameter_snapshot_fingerprint(parameters),
        required_streams=("U",),
        required_context_paths=(),
        required_semantic_paths=(),
        required_reference_ids=(),
        dependency_specs=dependencies,
        dependency_bindings=bindings,
        output_schema_id=definition.output_schema_id,
        output_schema_descriptor=_OUTPUT_DESCRIPTOR,
        output_schema_sha256=schema_descriptor_sha256(
            definition.output_schema_id, _OUTPUT_DESCRIPTOR
        ),
        artifact_kind=definition.artifact_kind,
        output_payload_kind="table",
        scope_policy="phase",
    )


class _Provider:
    def __init__(self, definition: PreprocessingProviderDefinition, calls: list[dict[str, Any]]):
        self._definition = definition
        self._calls = calls

    def definition(self) -> PreprocessingProviderDefinition:
        return self._definition

    def compute(self, context, recipe, scope, dependencies):
        self._calls.append(
            {
                "context": context,
                "recipe": recipe,
                "scope": scope,
                "dependencies": dependencies,
            }
        )
        return TabularArtifactPayload(
            schema_id=recipe.output_schema_id,
            schema_descriptor=recipe.output_schema_descriptor,
            frame=pl.DataFrame(
                {"event_id": ["event-1"], "t_ns": [scope.start_t_ns]},
                schema={"event_id": pl.String, "t_ns": pl.Int64},
            ),
            order_keys=("t_ns", "event_id"),
            artifact_kind=recipe.artifact_kind,
            grid_hash=None,
            start_t_ns=scope.start_t_ns,
            end_t_ns=scope.end_t_ns,
        )


def _registry(
    recipes: tuple[ResolvedPreprocessingRecipe, ...],
    calls: dict[str, list[dict[str, Any]]],
) -> PluginRegistry:
    factories = {}
    for recipe in recipes:
        key = (recipe.provider_id, recipe.provider_version)
        definition = _definition(recipe.provider_id, recipe.dependency_specs)
        provider_calls = calls.setdefault(recipe.provider_id, [])
        factories[key] = lambda definition=definition, provider_calls=provider_calls: _Provider(
            definition, provider_calls
        )
    return PluginRegistry.from_factories_for_testing({}, factories)


def _scope(scope_id: str = "phase-1", *, start: int = 0, end: int = 2) -> PreprocessingScope:
    return PreprocessingScope(
        kind="phase",
        scope_id=scope_id,
        start_t_ns=start,
        end_t_ns=end,
        phase_id=scope_id,
        event_id=None,
        window_id=None,
    )


def _resolution_context(recipes: tuple[ResolvedPreprocessingRecipe, ...], sha: str = SHA_A):
    from pilot_assessment.anchors.preprocessing import PreprocessingResolutionContext

    return PreprocessingResolutionContext(
        provider_contexts={recipe.recipe_id: _context() for recipe in recipes},
        input_fingerprints={recipe.recipe_id: (("stream", "U", sha),) for recipe in recipes},
    )


def test_resolver_memoizes_one_exact_recipe_scope_and_input_identity() -> None:
    from pilot_assessment.anchors.preprocessing import PreprocessingResolver

    recipe = _recipe("movement-events", "test-movement-provider")
    calls: dict[str, list[dict[str, Any]]] = {}
    resolver = PreprocessingResolver(_registry((recipe,), calls), (recipe,))
    context = _resolution_context((recipe,))
    transaction = InMemoryDerivedArtifactSink().begin_evaluation("preprocessing-cache")

    first = resolver.resolve(recipe, context, _scope(), transaction)
    second = resolver.resolve(recipe, context, _scope(), transaction)

    assert first is second
    assert len(calls[recipe.provider_id]) == 1
    assert calls[recipe.provider_id][0]["scope"] == _scope()
    assert dict(calls[recipe.provider_id][0]["dependencies"]) == {}


def test_resolver_uses_dependency_slots_and_positive_provider_projection_only() -> None:
    from pilot_assessment.anchors.preprocessing import PreprocessingResolver

    leaf = _recipe("leaf", "test-leaf-provider")
    spec = PreprocessingDependencySpec(
        dependency_id="events",
        expected_schema_id=leaf.output_schema_id,
        expected_artifact_kind=leaf.artifact_kind,
    )
    parent = _recipe(
        "parent",
        "test-parent-provider",
        dependencies=(spec,),
        bindings=(
            ResolvedPreprocessingDependencyBinding(dependency_id="events", target_recipe_id="leaf"),
        ),
    )
    calls: dict[str, list[dict[str, Any]]] = {}
    resolver = PreprocessingResolver(_registry((leaf, parent), calls), (leaf, parent))
    transaction = InMemoryDerivedArtifactSink().begin_evaluation("preprocessing-dependency")

    resolved = resolver.resolve(
        parent,
        _resolution_context((leaf, parent)),
        _scope(),
        transaction,
    )

    assert len(calls[leaf.provider_id]) == 1
    assert len(calls[parent.provider_id]) == 1
    dependencies = calls[parent.provider_id][0]["dependencies"]
    assert tuple(dependencies) == ("events",)
    assert dependencies["events"].identity.recipe_id == "leaf"
    assert resolved.identity.dependency_fingerprints


def test_cache_key_and_identity_change_for_scope_or_declared_input_even_with_same_rows() -> None:
    from pilot_assessment.anchors.preprocessing import (
        PreprocessingCacheKey,
        PreprocessingResolver,
        preprocessing_dependency_fingerprint,
    )

    base_key = PreprocessingCacheKey(
        recipe_id="movement-events",
        recipe_version="0.1.0",
        provider_id="test-movement-provider",
        provider_version="1.0.0",
        implementation_digest=SHA_B,
        parameter_schema_id="movement-events-v1-parameters-0.1",
        parameter_schema_sha256=SHA_A,
        parameter_hash=SHA_B,
        scope_kind="phase",
        scope_id="phase-1",
        scope_start_t_ns=0,
        scope_end_t_ns=2,
        phase_id="phase-1",
        event_id=None,
        window_id=None,
        input_fingerprints=(("stream", "U", SHA_A),),
        dependency_fingerprints=(),
    )
    changed_fields = {
        "scope_id": "phase-2",
        "scope_start_t_ns": 1,
        "scope_end_t_ns": 3,
        "phase_id": "phase-2",
        "parameter_schema_sha256": SHA_B,
        "parameter_hash": SHA_A,
        "provider_version": "1.0.1",
        "input_fingerprints": (("stream", "U", SHA_B),),
        "dependency_fingerprints": (SHA_A,),
    }
    assert all(
        replace(base_key, **{field: value}) != base_key for field, value in changed_fields.items()
    )

    recipe = _recipe("movement-events", "test-movement-provider")
    calls: dict[str, list[dict[str, Any]]] = {}
    resolver = PreprocessingResolver(_registry((recipe,), calls), (recipe,))
    transaction = InMemoryDerivedArtifactSink().begin_evaluation("preprocessing-input-identity")
    first = resolver.resolve(recipe, _resolution_context((recipe,), SHA_A), _scope(), transaction)
    second = resolver.resolve(recipe, _resolution_context((recipe,), SHA_B), _scope(), transaction)

    assert len(calls[recipe.provider_id]) == 2
    assert first.payload.logical_content_sha256 == second.payload.logical_content_sha256
    assert first.identity != second.identity
    assert preprocessing_dependency_fingerprint(first) != preprocessing_dependency_fingerprint(
        second
    )
