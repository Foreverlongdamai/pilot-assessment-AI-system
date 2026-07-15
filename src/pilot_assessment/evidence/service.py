"""Backend-only editable recipe use cases for draft, preview, apply and replay."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from pilot_assessment.contracts.evidence_recipe import EvidenceRecipe, RecipeLifecycle
from pilot_assessment.evidence.compiler import RecipeCompilationError, compile_recipe
from pilot_assessment.evidence.executor import (
    RecipeExecutionError,
    RecipeExecutionResult,
    execute_recipe,
)
from pilot_assessment.evidence.registry import OperatorRegistry
from pilot_assessment.evidence.repository import (
    AppliedRecipeRevision,
    RecipeDraftRecord,
    RecipeRepository,
)
from pilot_assessment.evidence.validation import (
    RecipeDiagnostic,
    RecipeValidationDisposition,
    RecipeValidationOutcome,
    validate_recipe,
)


@dataclass(frozen=True, slots=True)
class RecipeServiceDiagnostic:
    code: str
    location: str
    message: str
    node_id: str | None
    operator_id: str | None
    operator_version: str | None


@dataclass(frozen=True, slots=True)
class RecipePreviewOutcome:
    recipe_id: str
    draft_revision: int
    content_sha256: str
    succeeded: bool
    validation: RecipeValidationOutcome
    execution: RecipeExecutionResult | None
    diagnostics: tuple[RecipeServiceDiagnostic, ...]


class RecipeApplyError(ValueError):
    """Raised only when the selected draft is not technically executable."""

    def __init__(
        self,
        validation: RecipeValidationOutcome,
        diagnostics: tuple[RecipeServiceDiagnostic, ...],
    ) -> None:
        super().__init__("evidence recipe cannot be applied until technical errors are fixed")
        self.validation = validation
        self.diagnostics = diagnostics


def _node_id_from_location(location: str) -> str | None:
    prefix = "/graph/nodes/"
    if not location.startswith(prefix):
        return None
    suffix = location[len(prefix) :]
    return suffix.split("/", 1)[0] or None


def _validation_diagnostic(value: RecipeDiagnostic) -> RecipeServiceDiagnostic:
    return RecipeServiceDiagnostic(
        code=value.code,
        location=value.location,
        message=value.message,
        node_id=_node_id_from_location(value.location),
        operator_id=None,
        operator_version=None,
    )


def _execution_diagnostic(error: RecipeExecutionError) -> RecipeServiceDiagnostic:
    location = (
        "/scoring"
        if error.node_id == "scoring"
        else f"/graph/nodes/{error.node_id}"
    )
    return RecipeServiceDiagnostic(
        code=error.code,
        location=location,
        message=str(error),
        node_id=error.node_id,
        operator_id=error.operator_id,
        operator_version=error.operator_version,
    )


class EvidenceRecipeService:
    """Canonical use-case layer shared by the future HTTP API and WinUI client."""

    def __init__(
        self,
        repository: RecipeRepository,
        registry: OperatorRegistry,
    ) -> None:
        self._repository = repository
        self._registry = registry

    def create_draft(
        self,
        recipe: EvidenceRecipe,
        *,
        author_id: str,
    ) -> RecipeDraftRecord:
        return self._repository.create_draft(recipe, author_id=author_id)

    def save_draft(
        self,
        recipe: EvidenceRecipe,
        *,
        expected_draft_revision: int,
        author_id: str,
    ) -> RecipeDraftRecord:
        return self._repository.save_draft(
            recipe,
            expected_draft_revision=expected_draft_revision,
            author_id=author_id,
        )

    def clone_draft(
        self,
        source_recipe_id: str,
        new_recipe_id: str,
        *,
        author_id: str,
    ) -> RecipeDraftRecord:
        return self._repository.clone_draft(
            source_recipe_id,
            new_recipe_id,
            author_id=author_id,
        )

    def set_lifecycle(
        self,
        recipe_id: str,
        lifecycle: RecipeLifecycle | str,
        *,
        author_id: str,
    ) -> RecipeDraftRecord:
        return self._repository.set_lifecycle(
            recipe_id,
            lifecycle,
            author_id=author_id,
        )

    def preview(
        self,
        recipe_id: str,
        *,
        execution_inputs: Mapping[str, object],
        trace_node_ids: Iterable[str] = (),
    ) -> RecipePreviewOutcome:
        draft = self._repository.get_draft(recipe_id)
        validation = validate_recipe(draft.recipe, self._registry)
        validation_diagnostics = tuple(
            _validation_diagnostic(item) for item in validation.diagnostics
        )
        if validation.disposition is not RecipeValidationDisposition.EXECUTABLE:
            return RecipePreviewOutcome(
                recipe_id=recipe_id,
                draft_revision=draft.draft_revision,
                content_sha256=draft.content_sha256,
                succeeded=False,
                validation=validation,
                execution=None,
                diagnostics=validation_diagnostics,
            )
        try:
            compiled = compile_recipe(draft.recipe, self._registry)
            execution = execute_recipe(
                compiled,
                self._registry,
                binding_values=execution_inputs,
                trace_node_ids=trace_node_ids,
            )
        except RecipeCompilationError as error:
            diagnostics = tuple(
                _validation_diagnostic(item) for item in error.outcome.diagnostics
            )
            return RecipePreviewOutcome(
                recipe_id=recipe_id,
                draft_revision=draft.draft_revision,
                content_sha256=draft.content_sha256,
                succeeded=False,
                validation=error.outcome,
                execution=None,
                diagnostics=diagnostics,
            )
        except RecipeExecutionError as error:
            return RecipePreviewOutcome(
                recipe_id=recipe_id,
                draft_revision=draft.draft_revision,
                content_sha256=draft.content_sha256,
                succeeded=False,
                validation=validation,
                execution=None,
                diagnostics=(*validation_diagnostics, _execution_diagnostic(error)),
            )
        return RecipePreviewOutcome(
            recipe_id=recipe_id,
            draft_revision=draft.draft_revision,
            content_sha256=draft.content_sha256,
            succeeded=True,
            validation=validation,
            execution=execution,
            diagnostics=validation_diagnostics,
        )

    def apply(
        self,
        recipe_id: str,
        *,
        author_id: str,
        note: str | None = None,
    ) -> AppliedRecipeRevision:
        draft = self._repository.get_draft(recipe_id)
        validation = validate_recipe(draft.recipe, self._registry)
        diagnostics = tuple(
            _validation_diagnostic(item) for item in validation.diagnostics
        )
        if validation.disposition is not RecipeValidationDisposition.EXECUTABLE:
            raise RecipeApplyError(validation, diagnostics)
        try:
            compile_recipe(draft.recipe, self._registry)
        except RecipeCompilationError as error:
            compile_diagnostics = tuple(
                _validation_diagnostic(item) for item in error.outcome.diagnostics
            )
            raise RecipeApplyError(error.outcome, compile_diagnostics) from error
        return self._repository.create_applied_revision(
            recipe_id,
            author_id=author_id,
            note=note,
        )

    def get_applied_revision(self, revision_id: str) -> AppliedRecipeRevision:
        return self._repository.get_applied_revision(revision_id)

    def replay(
        self,
        revision_id: str,
        *,
        execution_inputs: Mapping[str, object],
        trace_node_ids: Iterable[str] = (),
    ) -> RecipeExecutionResult:
        revision = self._repository.get_applied_revision(revision_id)
        compiled = compile_recipe(revision.recipe, self._registry)
        return execute_recipe(
            compiled,
            self._registry,
            binding_values=execution_inputs,
            trace_node_ids=trace_node_ids,
        )


__all__ = [
    "EvidenceRecipeService",
    "RecipeApplyError",
    "RecipePreviewOutcome",
    "RecipeServiceDiagnostic",
]
