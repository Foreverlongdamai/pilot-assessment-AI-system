"""Deterministic M4 anchor evaluator with consumer-local failure isolation."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import suppress
from typing import cast

from pydantic import JsonValue

from pilot_assessment.anchors.artifacts import ArtifactTransactionError
from pilot_assessment.anchors.dag import (
    EvaluationPolicy,
    TestFaultHooks,
    validate_anchor_evaluation_request,
    validate_request_bound_execution_plan,
)
from pilot_assessment.anchors.fingerprint import (
    evaluation_fingerprint_payload,
    typed_json_sha256,
)
from pilot_assessment.anchors.models import AnchorEvaluationRequest
from pilot_assessment.anchors.preprocessing import (
    PreprocessingResolutionContext,
    PreprocessingResolutionError,
    PreprocessingResolver,
    preprocessing_dependency_fingerprint,
)
from pilot_assessment.anchors.protocols import (
    AnchorPluginContext,
    ArtifactProducer,
    DerivedArtifactSink,
    EvaluationArtifactTransaction,
    PreprocessingScope,
    ProjectedSemanticScope,
    ResolvedArtifactDependency,
    ResolvedDependencies,
    ResolvedPreprocessingDependency,
)
from pilot_assessment.anchors.registry import PluginRegistry, RegistryResolutionError
from pilot_assessment.anchors.scoring import ScoringError, score_measurement
from pilot_assessment.contracts.anchor_execution import (
    AnchorCapabilityStatus,
    AnchorEvaluationDisposition,
    AnchorEvaluationReport,
    AnchorExecutionEntry,
    AnchorInventoryItem,
    AnchorInventoryStatus,
    AnchorPluginDefinition,
    DependencyKind,
    ResolvedAlgorithmProfile,
    ResolvedPreprocessingRecipe,
    SemanticApplicabilityStatus,
)
from pilot_assessment.contracts.anchor_v2 import (
    AnchorCalculationStatusV2,
    AnchorMeasurement,
    AnchorResultProvenance,
    AnchorResultV2,
    ComputationTrace,
)
from pilot_assessment.contracts.common import Sha256Digest
from pilot_assessment.contracts.errors import DomainErrorData, ErrorSeverity

_PLACEHOLDER_SHA256 = "0" * 64


class AnchorEvaluationError(ValueError):
    """Global post-request evaluation failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _diagnostic(
    code: str,
    message: str,
    *,
    anchor_id: str | None = None,
    diagnostics: Mapping[str, JsonValue] | None = None,
) -> DomainErrorData:
    return DomainErrorData(
        error_code=code,
        severity=ErrorSeverity.ERROR,
        recoverable=True,
        message=message,
        node_or_anchor_id=anchor_id,
        remediation="Inspect the typed diagnostic and correct the affected input or plugin.",
        diagnostics=dict(diagnostics or {}),
    )


def _trace(diagnostics: tuple[DomainErrorData, ...]) -> ComputationTrace:
    return ComputationTrace(
        sample_count=0,
        source_start_t_ns=None,
        source_end_t_ns=None,
        analysis_start_t_ns=None,
        analysis_end_t_ns=None,
        grid_id=None,
        window_ids=(),
        interpolation_method=None,
        matching_method=None,
        diagnostics=diagnostics,
    )


def _plugin_definition(entry: AnchorExecutionEntry) -> AnchorPluginDefinition:
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


def _path_value(root: object, path: str, namespace: str) -> JsonValue:
    prefix = f"{namespace}."
    if not path.startswith(prefix):
        raise KeyError(path)
    current = root
    for member in path.removeprefix(prefix).split("."):
        if isinstance(current, Mapping):
            current = cast(Mapping[str, object], current)[member]
        elif isinstance(current, (list, tuple)) and member.isdigit():
            current = current[int(member)]
        else:
            raise KeyError(path)
    return cast(JsonValue, current)


def _context_projection(
    request: AnchorEvaluationRequest,
    *,
    required_streams: tuple[object, ...],
    required_context_paths: tuple[str, ...],
    required_semantic_paths: tuple[str, ...],
    required_reference_ids: tuple[str, ...],
) -> AnchorPluginContext:
    streams = {
        str(modality): request.aligned_session.streams[str(modality)]
        for modality in required_streams
        if str(modality) in request.aligned_session.streams
    }
    context_values = {
        path: _path_value(request.aligned_session.context, path, "context")
        for path in required_context_paths
    }
    semantic_root = request.session_semantic_snapshot.model_dump(mode="json")
    semantic_values = {
        path: _path_value(semantic_root, path, "semantic") for path in required_semantic_paths
    }
    references = {
        reference_id: request.resolved_references.entries[reference_id]
        for reference_id in required_reference_ids
        if reference_id in request.resolved_references.entries
    }
    return AnchorPluginContext(
        session_id=request.aligned_session.session_id,
        session_window=request.aligned_session.window,
        streams=streams,
        context=context_values,
        references=references,
        semantic_scope=ProjectedSemanticScope(values=semantic_values),
    )


def _stream_projection_fingerprint(context: AnchorPluginContext, modality: str) -> str:
    view = context.streams[modality]
    payload = {
        "modality": modality,
        "source_schema_id": view.source_schema_id,
        "aligned_schema_id": view.aligned_schema_id,
        "clock_id": view.clock_id,
        "source_checksums": dict(sorted(view.source_checksums.items())),
        "tables": [[role, view.tables[role].to_dicts()] for role in sorted(view.tables)],
        "json_artifacts": [
            [role, view.json_artifacts[role]] for role in sorted(view.json_artifacts)
        ],
        "file_artifacts": [
            [role, list(view.file_artifacts[role])] for role in sorted(view.file_artifacts)
        ],
    }
    return typed_json_sha256("aligned-stream-projection", "0.1.0", payload)


def _provider_resolution_context(
    request: AnchorEvaluationRequest,
    recipes: tuple[ResolvedPreprocessingRecipe, ...],
) -> PreprocessingResolutionContext:
    contexts: dict[str, AnchorPluginContext] = {}
    fingerprints: dict[str, tuple[tuple[str, str, Sha256Digest], ...]] = {}
    for recipe in recipes:
        context = _context_projection(
            request,
            required_streams=recipe.required_streams,
            required_context_paths=recipe.required_context_paths,
            required_semantic_paths=recipe.required_semantic_paths,
            required_reference_ids=recipe.required_reference_ids,
        )
        contexts[recipe.recipe_id] = context
        members: list[tuple[str, str, Sha256Digest]] = []
        for modality in sorted(context.streams):
            members.append(("stream", modality, _stream_projection_fingerprint(context, modality)))
        members.extend(
            ("context", path, typed_json_sha256("context-projection", "0.1.0", value))
            for path, value in sorted(context.context.items())
        )
        members.extend(
            ("semantic", path, typed_json_sha256("semantic-projection", "0.1.0", value))
            for path, value in sorted(context.semantic_scope.values.items())
        )
        members.extend(
            (
                "reference",
                reference_id,
                typed_json_sha256(
                    "reference-projection",
                    "0.1.0",
                    reference.descriptor.model_dump(mode="json"),
                ),
            )
            for reference_id, reference in sorted(context.references.items())
        )
        fingerprints[recipe.recipe_id] = tuple(sorted(members))
    return PreprocessingResolutionContext(
        provider_contexts=contexts,
        input_fingerprints=fingerprints,
    )


def _scope_for(
    request: AnchorEvaluationRequest,
    entry: AnchorExecutionEntry,
    recipe: ResolvedPreprocessingRecipe,
) -> PreprocessingScope:
    window = request.aligned_session.window
    if recipe.scope_policy == "session":
        return PreprocessingScope(
            kind="session",
            scope_id=request.aligned_session.session_id,
            start_t_ns=window.start_t_ns,
            end_t_ns=window.end_t_ns,
            phase_id=None,
            event_id=None,
            window_id=None,
        )
    if recipe.scope_policy == "phase":
        if len(entry.phase_scope) != 1:
            raise AnchorEvaluationError(
                "preprocessing_scope_ambiguous",
                f"anchor {entry.anchor_id} requires one exact phase for recipe {recipe.recipe_id}",
            )
        phase_id = entry.phase_scope[0]
        phase = next(
            (
                phase
                for phase in request.session_semantic_snapshot.phases
                if phase.phase_id == phase_id
            ),
            None,
        )
        if phase is None:
            raise AnchorEvaluationError(
                "preprocessing_scope_missing",
                f"phase {phase_id} is absent for recipe {recipe.recipe_id}",
            )
        return PreprocessingScope(
            kind="phase",
            scope_id=phase_id,
            start_t_ns=phase.start_t_ns,
            end_t_ns=phase.end_t_ns,
            phase_id=phase_id,
            event_id=None,
            window_id=None,
        )
    if recipe.scope_policy == "event":
        if len(entry.event_scope) != 1:
            raise AnchorEvaluationError(
                "preprocessing_scope_ambiguous",
                f"anchor {entry.anchor_id} requires one exact event for recipe {recipe.recipe_id}",
            )
        event_id = entry.event_scope[0]
        event = next(
            (
                event
                for event in request.session_semantic_snapshot.events
                if event.event_id == event_id
            ),
            None,
        )
        if event is None:
            raise AnchorEvaluationError(
                "preprocessing_scope_missing",
                f"event {event_id} is absent for recipe {recipe.recipe_id}",
            )
        end_t_ns = event.t_ns + max(event.duration_ns or 1, 1)
        return PreprocessingScope(
            kind="event",
            scope_id=event_id,
            start_t_ns=event.t_ns,
            end_t_ns=end_t_ns,
            phase_id=None,
            event_id=event_id,
            window_id=None,
        )
    window_id = cast(str | None, entry.temporal_recipe.get("window_id"))
    if window_id is None:
        window_id = f"{entry.anchor_id.lower()}-window"
    return PreprocessingScope(
        kind="window",
        scope_id=window_id,
        start_t_ns=window.start_t_ns,
        end_t_ns=window.end_t_ns,
        phase_id=entry.phase_scope[0] if len(entry.phase_scope) == 1 else None,
        event_id=entry.event_scope[0] if len(entry.event_scope) == 1 else None,
        window_id=window_id,
    )


def _noncomputed_result(
    entry: AnchorExecutionEntry,
    status: AnchorCalculationStatusV2,
    diagnostics: tuple[DomainErrorData, ...],
    dependency_fingerprints: tuple[Sha256Digest, ...] = (),
) -> AnchorResultV2:
    trace = _trace(diagnostics)
    measurement = AnchorMeasurement(
        anchor_id=entry.anchor_id,
        calculation_status=status,
        primary_value=None,
        primary_value_reason=None,
        raw_metrics={},
        phase_results=(),
        event_results=(),
        classification_override_candidate=None,
        source_windows=(),
        derived_artifacts=(),
        trace=trace,
        diagnostics=diagnostics,
    )
    provenance = AnchorResultProvenance(
        plugin_id=entry.plugin_id,
        plugin_version=entry.plugin_version,
        implementation_digest=entry.implementation_digest,
        parameter_hash=entry.parameter_hash,
        dependency_fingerprints=dependency_fingerprints,
        computation_trace=trace,
    )
    return score_measurement(measurement, entry.scorer_policy, provenance)


def _report_with_fingerprint(**values: object) -> AnchorEvaluationReport:
    draft_values = {**values, "evaluation_fingerprint": _PLACEHOLDER_SHA256}
    draft = AnchorEvaluationReport.model_validate(draft_values)
    payload = draft.model_dump(mode="python")
    payload["evaluation_fingerprint"] = typed_json_sha256(
        draft.contract_id,
        draft.contract_version,
        evaluation_fingerprint_payload(draft),
    )
    return AnchorEvaluationReport.model_validate(payload)


def _blocked_report(
    request: AnchorEvaluationRequest,
    diagnostics: tuple[DomainErrorData, ...],
    *,
    reason: str = "plan_invalid",
) -> AnchorEvaluationReport:
    seen: set[str] = set()
    entries = tuple(
        entry
        for entry in request.execution_plan.entries
        if not (entry.anchor_id in seen or seen.add(entry.anchor_id))
    )
    capability = (
        AnchorCapabilityStatus.NOT_IMPLEMENTED
        if any("not_implemented" in item.error_code for item in diagnostics)
        else AnchorCapabilityStatus.INCOMPATIBLE
    )
    inventory = tuple(
        AnchorInventoryItem(
            anchor_id=entry.anchor_id,
            capability_status=capability,
            evaluation_status=AnchorInventoryStatus.NOT_ATTEMPTED,
            result_fingerprint=None,
            global_block_reason=reason,
            diagnostics=tuple(
                diagnostic
                for diagnostic in diagnostics
                if diagnostic.node_or_anchor_id in {None, entry.anchor_id}
            ),
        )
        for entry in entries
    )
    return _report_with_fingerprint(
        session_id=request.aligned_session.session_id,
        disposition=AnchorEvaluationDisposition.BLOCKED,
        inventory=inventory,
        results=(),
        expected_count=len(inventory),
        executed_count=0,
        applicable_count=0,
        computed_count=0,
        raw_availability=None,
        catalog_fingerprint=request.execution_plan.catalog_fingerprint,
        registry_fingerprint=request.execution_plan.registry_fingerprint,
        execution_plan_fingerprint=request.execution_plan.plan_fingerprint,
        formal_run_authorized=False,
        scientific_validation_status=request.execution_plan.scientific_validation_status,
        diagnostics=diagnostics,
    )


class AnchorEvaluator:
    """Execute one already synchronized, identity-closed M4 request."""

    def __init__(self, registry: PluginRegistry, policy: EvaluationPolicy) -> None:
        self._init(registry, policy, fault_hooks=None, testing=False)

    def _init(
        self,
        registry: PluginRegistry,
        policy: EvaluationPolicy,
        *,
        fault_hooks: TestFaultHooks | None,
        testing: bool,
    ) -> None:
        if not isinstance(registry, PluginRegistry):
            raise TypeError("registry must be a PluginRegistry")
        if not isinstance(policy, EvaluationPolicy):
            raise TypeError("policy must be an EvaluationPolicy")
        if fault_hooks is not None and not testing:
            raise ValueError("fault hooks are test-only")
        if not testing and not registry.is_trusted:
            raise ValueError("injected registries require AnchorEvaluator.for_testing()")
        self._registry = registry
        self._policy = policy
        self._fault_hooks = fault_hooks or TestFaultHooks()
        self._testing = testing

    @classmethod
    def for_testing(
        cls,
        registry: PluginRegistry,
        policy: EvaluationPolicy,
        fault_hooks: TestFaultHooks | None = None,
    ) -> AnchorEvaluator:
        instance = cls.__new__(cls)
        instance._init(registry, policy, fault_hooks=fault_hooks, testing=True)
        return instance

    def evaluate(
        self,
        request: AnchorEvaluationRequest,
        sink: DerivedArtifactSink,
    ) -> AnchorEvaluationReport:
        validate_anchor_evaluation_request(request)
        plan = request.execution_plan
        if self._policy.require_packaged_registry_fingerprint and not self._registry.is_trusted:
            return _blocked_report(
                request,
                (
                    _diagnostic(
                        "anchor.plan.packaged_registry_required",
                        "this evaluator requires the trusted packaged registry",
                    ),
                ),
            )
        if not self._registry.is_trusted and (
            not self._policy.allow_injected_test_profile_ids
            or not plan.plan_id.startswith("test-")
            or not plan.model_profile_id.startswith("test-")
        ):
            return _blocked_report(
                request,
                (
                    _diagnostic(
                        "anchor.plan.test_profile_required",
                        "injected registries require test-* plan and model profile IDs",
                    ),
                ),
            )
        if self._registry.is_trusted and (
            plan.plan_id.startswith("test-") or plan.model_profile_id.startswith("test-")
        ):
            return _blocked_report(
                request,
                (
                    _diagnostic(
                        "anchor.plan.test_profile_forbidden",
                        "test profiles are forbidden at the trusted registry boundary",
                    ),
                ),
            )
        outcome = validate_request_bound_execution_plan(request=request, registry=self._registry)
        if outcome.disposition == "blocked" or outcome.validated_plan is None:
            return _blocked_report(request, outcome.diagnostics)

        evaluation_key = typed_json_sha256(
            "anchor-evaluation-transaction",
            "0.1.0",
            [request.aligned_session.session_id, request.execution_plan.plan_fingerprint],
        )
        try:
            transaction = sink.begin_evaluation(evaluation_key)
        except Exception as error:
            return _blocked_report(
                request,
                (
                    _diagnostic(
                        "anchor.transaction.begin_failed",
                        f"evaluation artifact transaction could not start: {error}",
                    ),
                ),
                reason="transaction_failed",
            )

        try:
            results = self._execute(request, outcome.validated_plan.levels, transaction)
            transaction.commit()
        except Exception as error:
            with suppress(Exception):
                transaction.abort()
            return _blocked_report(
                request,
                (
                    _diagnostic(
                        "anchor.transaction.finalization_failed",
                        f"evaluation transaction failed atomically: {error}",
                    ),
                ),
                reason="transaction_failed",
            )
        return self._ready_report(request, results)

    def _execute(
        self,
        request: AnchorEvaluationRequest,
        levels: tuple[tuple[str, ...], ...],
        transaction: EvaluationArtifactTransaction,
    ) -> dict[str, AnchorResultV2]:
        entries = {entry.anchor_id: entry for entry in request.execution_plan.entries}
        recipes = {
            recipe.recipe_id: recipe for recipe in request.execution_plan.preprocessing_recipes
        }
        profiles = {
            profile.profile_id: profile for profile in request.execution_plan.algorithm_profiles
        }
        provider_context = _provider_resolution_context(
            request, request.execution_plan.preprocessing_recipes
        )
        resolver = PreprocessingResolver(
            self._registry, request.execution_plan.preprocessing_recipes
        )
        results: dict[str, AnchorResultV2] = {}
        for level in levels:
            for anchor_id in level:
                entry = entries[anchor_id]
                results[anchor_id] = self._execute_entry(
                    request,
                    entry,
                    results,
                    recipes,
                    profiles,
                    resolver,
                    provider_context,
                    transaction,
                )
        return results

    def _execute_entry(
        self,
        request: AnchorEvaluationRequest,
        entry: AnchorExecutionEntry,
        results: Mapping[str, AnchorResultV2],
        recipes: Mapping[str, ResolvedPreprocessingRecipe],
        profiles: Mapping[str, ResolvedAlgorithmProfile],
        resolver: PreprocessingResolver,
        provider_context: PreprocessingResolutionContext,
        transaction: EvaluationArtifactTransaction,
    ) -> AnchorResultV2:
        if entry.applicability is SemanticApplicabilityStatus.NOT_APPLICABLE:
            return _noncomputed_result(entry, AnchorCalculationStatusV2.NOT_APPLICABLE, ())

        context = _context_projection(
            request,
            required_streams=entry.required_streams,
            required_context_paths=entry.required_context_paths,
            required_semantic_paths=entry.required_semantic_paths,
            required_reference_ids=entry.required_reference_ids,
        )
        missing_diagnostics: list[DomainErrorData] = []
        for modality_value in entry.required_streams:
            modality = str(modality_value)
            hook = self._fault_hooks.direct_stream_projection_failures.get(
                (entry.anchor_id, modality)
            )
            if hook is not None:
                missing_diagnostics.append(hook)
                continue
            if modality not in context.streams:
                status = request.synchronization_report.stream_results[modality]
                missing_diagnostics.append(
                    _diagnostic(
                        "anchor.input.stream_missing",
                        f"required stream {modality} is not aligned for {entry.anchor_id}",
                        anchor_id=entry.anchor_id,
                        diagnostics={
                            "modality": modality,
                            "synchronization_status": status.synchronization_status.value,
                        },
                    )
                )
        if missing_diagnostics:
            return _noncomputed_result(
                entry,
                AnchorCalculationStatusV2.MISSING_INPUT,
                tuple(missing_diagnostics),
            )

        absent_references = tuple(
            reference_id
            for reference_id in entry.required_reference_ids
            if reference_id not in context.references
            or context.references[reference_id].descriptor.resolution_status.value != "present"
        )
        if absent_references:
            diagnostic = _diagnostic(
                "anchor.input.reference_absent",
                f"required reference is explicitly absent for {entry.anchor_id}",
                anchor_id=entry.anchor_id,
                diagnostics={"reference_ids": list(absent_references)},
            )
            return _noncomputed_result(
                entry, AnchorCalculationStatusV2.NOT_COMPUTABLE, (diagnostic,)
            )

        resolved, dependency_fingerprints, dependency_diagnostics = self._dependencies(
            request,
            entry,
            results,
            recipes,
            profiles,
            resolver,
            provider_context,
            transaction,
        )
        if dependency_diagnostics:
            return _noncomputed_result(
                entry,
                AnchorCalculationStatusV2.DEPENDENCY_MISSING,
                dependency_diagnostics,
                dependency_fingerprints,
            )
        return self._call_plugin(
            entry,
            context,
            resolved,
            dependency_fingerprints,
            transaction,
        )

    def _dependencies(
        self,
        request: AnchorEvaluationRequest,
        entry: AnchorExecutionEntry,
        results: Mapping[str, AnchorResultV2],
        recipes: Mapping[str, ResolvedPreprocessingRecipe],
        profiles: Mapping[str, ResolvedAlgorithmProfile],
        resolver: PreprocessingResolver,
        provider_context: PreprocessingResolutionContext,
        transaction: EvaluationArtifactTransaction,
    ) -> tuple[ResolvedDependencies, tuple[Sha256Digest, ...], tuple[DomainErrorData, ...]]:
        result_dependencies: dict[str, AnchorResultV2] = {}
        artifact_dependencies: dict[str, ResolvedArtifactDependency] = {}
        profile_dependencies: dict[str, ResolvedAlgorithmProfile] = {}
        preprocessing_dependencies: dict[str, ResolvedPreprocessingDependency] = {}
        fingerprints: list[Sha256Digest] = []
        diagnostics: list[DomainErrorData] = []
        for dependency in entry.dependencies:
            try:
                if dependency.kind is DependencyKind.RESULT:
                    result = results.get(dependency.target_anchor_id or "")
                    if (
                        result is None
                        or result.calculation_status is not AnchorCalculationStatusV2.COMPUTED
                    ):
                        raise AnchorEvaluationError(
                            "result_dependency_missing", "upstream result is unavailable"
                        )
                    result_dependencies[dependency.dependency_id] = result
                    fingerprints.append(result.result_fingerprint)
                elif dependency.kind is DependencyKind.ARTIFACT:
                    result = results.get(dependency.target_anchor_id or "")
                    if result is None:
                        raise AnchorEvaluationError(
                            "artifact_dependency_missing", "upstream result is unavailable"
                        )
                    matches = tuple(
                        ref
                        for ref in result.derived_artifacts
                        if ref.artifact_id == dependency.target_resource_id
                        and ref.schema_id == dependency.expected_schema_id
                        and ref.kind == dependency.expected_artifact_kind
                    )
                    if len(matches) != 1:
                        raise AnchorEvaluationError(
                            "artifact_dependency_missing", "upstream artifact is unavailable"
                        )
                    resolved_artifact = transaction.resolve(matches[0])
                    artifact_dependencies[dependency.dependency_id] = resolved_artifact
                    fingerprints.append(matches[0].logical_content_sha256)
                elif dependency.kind is DependencyKind.ALGORITHM_PROFILE:
                    profile = profiles.get(dependency.target_resource_id or "")
                    if profile is None:
                        raise AnchorEvaluationError(
                            "algorithm_profile_missing", "algorithm profile is unavailable"
                        )
                    profile_dependencies[dependency.dependency_id] = profile
                    fingerprints.append(profile.parameter_hash)
                else:
                    recipe = recipes.get(dependency.target_resource_id or "")
                    if recipe is None:
                        raise AnchorEvaluationError(
                            "preprocessing_dependency_missing",
                            "preprocessing recipe is unavailable",
                        )
                    resolved_preprocessing = resolver.resolve(
                        recipe,
                        provider_context,
                        _scope_for(request, entry, recipe),
                        transaction,
                    )
                    hook = self._fault_hooks.preprocessing_resolution_failures.get(
                        (entry.anchor_id, recipe.recipe_id)
                    )
                    if hook is not None:
                        if dependency.required:
                            diagnostics.append(hook)
                        continue
                    preprocessing_dependencies[dependency.dependency_id] = resolved_preprocessing
                    fingerprints.append(
                        preprocessing_dependency_fingerprint(resolved_preprocessing)
                    )
            except (
                AnchorEvaluationError,
                ArtifactTransactionError,
                PreprocessingResolutionError,
            ) as error:
                if not dependency.required:
                    continue
                diagnostics.append(
                    _diagnostic(
                        "anchor.dependency.missing",
                        f"dependency {dependency.dependency_id} is unavailable: {error}",
                        anchor_id=entry.anchor_id,
                        diagnostics={
                            "dependency_id": dependency.dependency_id,
                            "failure_code": getattr(error, "code", "dependency_missing"),
                        },
                    )
                )
        return (
            ResolvedDependencies(
                results=result_dependencies,
                artifacts=artifact_dependencies,
                algorithm_profiles=profile_dependencies,
                preprocessing=preprocessing_dependencies,
            ),
            tuple(fingerprints),
            tuple(diagnostics),
        )

    def _call_plugin(
        self,
        entry: AnchorExecutionEntry,
        context: AnchorPluginContext,
        dependencies: ResolvedDependencies,
        dependency_fingerprints: tuple[Sha256Digest, ...],
        transaction: EvaluationArtifactTransaction,
    ) -> AnchorResultV2:
        anchor_transaction = None
        measurement: AnchorMeasurement | None = None
        diagnostics: tuple[DomainErrorData, ...] = ()
        try:
            plugin = self._registry.resolve(
                entry.plugin_id, entry.plugin_version, entry.implementation_digest
            )
            live_definition = plugin.definition()
            if live_definition != _plugin_definition(entry):
                raise AnchorEvaluationError(
                    "plugin_definition_mismatch", "live plugin definition differs from the plan"
                )
            producer = ArtifactProducer(
                anchor_id=entry.anchor_id,
                plugin_id=entry.plugin_id,
                plugin_version=entry.plugin_version,
                implementation_digest=entry.implementation_digest,
                parameter_hash=entry.parameter_hash,
                dependency_fingerprints=dependency_fingerprints,
            )
            anchor_transaction = transaction.begin_anchor(producer, entry.artifact_recipes)
            measurement = plugin.compute(
                context,
                entry.parameters,
                entry.temporal_recipe,
                dependencies,
                anchor_transaction.emitter(),
            )
            if not isinstance(measurement, AnchorMeasurement):
                raise AnchorEvaluationError(
                    "plugin_measurement_invalid", "plugin did not return AnchorMeasurement"
                )
            if measurement.anchor_id != entry.anchor_id:
                raise AnchorEvaluationError(
                    "plugin_measurement_identity_mismatch",
                    "measurement anchor identity differs from the current entry",
                )
            staged = anchor_transaction.staged_refs()
            if measurement.derived_artifacts != staged:
                raise AnchorEvaluationError(
                    "plugin_artifact_return_mismatch",
                    "returned artifact refs differ from the exact staged order",
                )
            hook = self._fault_hooks.anchor_transaction_failures.get(entry.anchor_id)
            if hook is not None:
                diagnostics = (*measurement.diagnostics, hook)
                raise AnchorEvaluationError(
                    "anchor_transaction_hook", "test anchor transaction hook failed"
                )
            anchor_transaction.commit()
            provenance = AnchorResultProvenance(
                plugin_id=entry.plugin_id,
                plugin_version=entry.plugin_version,
                implementation_digest=entry.implementation_digest,
                parameter_hash=entry.parameter_hash,
                dependency_fingerprints=dependency_fingerprints,
                computation_trace=measurement.trace,
            )
            return score_measurement(measurement, entry.scorer_policy, provenance)
        except (
            AnchorEvaluationError,
            ArtifactTransactionError,
            RegistryResolutionError,
            ScoringError,
            TypeError,
            ValueError,
        ) as error:
            if anchor_transaction is not None:
                with suppress(Exception):
                    anchor_transaction.abort()
            if not diagnostics:
                diagnostics = (
                    *(() if measurement is None else measurement.diagnostics),
                    _diagnostic(
                        "anchor.extractor.failed",
                        f"anchor {entry.anchor_id} extractor failed: {error}",
                        anchor_id=entry.anchor_id,
                        diagnostics={"failure_code": getattr(error, "code", "extractor_error")},
                    ),
                )
            return _noncomputed_result(
                entry,
                AnchorCalculationStatusV2.EXTRACTOR_ERROR,
                diagnostics,
                dependency_fingerprints,
            )
        except Exception as error:
            if anchor_transaction is not None:
                with suppress(Exception):
                    anchor_transaction.abort()
            diagnostic = _diagnostic(
                "anchor.extractor.failed",
                f"anchor {entry.anchor_id} extractor raised an exception: {error}",
                anchor_id=entry.anchor_id,
            )
            return _noncomputed_result(
                entry,
                AnchorCalculationStatusV2.EXTRACTOR_ERROR,
                (diagnostic,),
                dependency_fingerprints,
            )

    @staticmethod
    def _ready_report(
        request: AnchorEvaluationRequest,
        results_by_id: Mapping[str, AnchorResultV2],
    ) -> AnchorEvaluationReport:
        entries = request.execution_plan.entries
        results = tuple(results_by_id[entry.anchor_id] for entry in entries)
        inventory = tuple(
            AnchorInventoryItem(
                anchor_id=result.anchor_id,
                capability_status=AnchorCapabilityStatus.AVAILABLE,
                evaluation_status=AnchorInventoryStatus.EXECUTED,
                result_fingerprint=result.result_fingerprint,
                global_block_reason=None,
                diagnostics=result.diagnostics,
            )
            for result in results
        )
        applicable_count = sum(
            result.calculation_status is not AnchorCalculationStatusV2.NOT_APPLICABLE
            for result in results
        )
        computed_count = sum(
            result.calculation_status is AnchorCalculationStatusV2.COMPUTED for result in results
        )
        disposition = (
            AnchorEvaluationDisposition.READY
            if computed_count == applicable_count
            else AnchorEvaluationDisposition.READY_PARTIAL
        )
        return _report_with_fingerprint(
            session_id=request.aligned_session.session_id,
            disposition=disposition,
            inventory=inventory,
            results=results,
            expected_count=len(inventory),
            executed_count=len(results),
            applicable_count=applicable_count,
            computed_count=computed_count,
            raw_availability=(None if applicable_count == 0 else computed_count / applicable_count),
            catalog_fingerprint=request.execution_plan.catalog_fingerprint,
            registry_fingerprint=request.execution_plan.registry_fingerprint,
            execution_plan_fingerprint=request.execution_plan.plan_fingerprint,
            formal_run_authorized=False,
            scientific_validation_status=request.execution_plan.scientific_validation_status,
            diagnostics=(),
        )


__all__ = ["AnchorEvaluationError", "AnchorEvaluator"]
