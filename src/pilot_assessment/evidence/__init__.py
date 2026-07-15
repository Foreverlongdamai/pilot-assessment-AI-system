"""Expert-editable evidence computation foundation."""

from pilot_assessment.evidence.compiler import (
    CompiledRecipe,
    RecipeCompilationError,
    compile_recipe,
)
from pilot_assessment.evidence.executor import (
    NodeExecutionTrace,
    RecipeExecutionError,
    RecipeExecutionResult,
    execute_recipe,
)
from pilot_assessment.evidence.operators import (
    OperatorExecutionContext,
    OperatorImplementation,
)
from pilot_assessment.evidence.registry import OperatorRegistry, OperatorRegistryError
from pilot_assessment.evidence.repository import (
    AppliedRecipeRevision,
    DraftRevisionConflictError,
    InMemoryRecipeRepository,
    RecipeDraftRecord,
    RecipeRepository,
)
from pilot_assessment.evidence.service import (
    EvidenceRecipeService,
    RecipeApplyError,
    RecipePreviewOutcome,
    RecipeServiceDiagnostic,
)
from pilot_assessment.evidence.validation import (
    RecipeDiagnostic,
    RecipeDiagnosticSeverity,
    RecipeValidationDisposition,
    RecipeValidationOutcome,
    validate_recipe,
)

__all__ = [
    "AppliedRecipeRevision",
    "CompiledRecipe",
    "DraftRevisionConflictError",
    "EvidenceRecipeService",
    "InMemoryRecipeRepository",
    "NodeExecutionTrace",
    "OperatorExecutionContext",
    "OperatorImplementation",
    "OperatorRegistry",
    "OperatorRegistryError",
    "RecipeCompilationError",
    "RecipeApplyError",
    "RecipeDiagnostic",
    "RecipeDiagnosticSeverity",
    "RecipeExecutionError",
    "RecipeExecutionResult",
    "RecipeDraftRecord",
    "RecipePreviewOutcome",
    "RecipeRepository",
    "RecipeServiceDiagnostic",
    "RecipeValidationDisposition",
    "RecipeValidationOutcome",
    "compile_recipe",
    "execute_recipe",
    "validate_recipe",
]
