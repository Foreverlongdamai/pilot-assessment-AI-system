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
from pilot_assessment.evidence.validation import (
    RecipeDiagnostic,
    RecipeDiagnosticSeverity,
    RecipeValidationDisposition,
    RecipeValidationOutcome,
    validate_recipe,
)

__all__ = [
    "CompiledRecipe",
    "NodeExecutionTrace",
    "OperatorExecutionContext",
    "OperatorImplementation",
    "OperatorRegistry",
    "OperatorRegistryError",
    "RecipeCompilationError",
    "RecipeDiagnostic",
    "RecipeDiagnosticSeverity",
    "RecipeExecutionError",
    "RecipeExecutionResult",
    "RecipeValidationDisposition",
    "RecipeValidationOutcome",
    "compile_recipe",
    "execute_recipe",
    "validate_recipe",
]
