"""Expert-editable evidence computation foundation."""

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
    "OperatorExecutionContext",
    "OperatorImplementation",
    "OperatorRegistry",
    "OperatorRegistryError",
    "RecipeDiagnostic",
    "RecipeDiagnosticSeverity",
    "RecipeValidationDisposition",
    "RecipeValidationOutcome",
    "validate_recipe",
]
