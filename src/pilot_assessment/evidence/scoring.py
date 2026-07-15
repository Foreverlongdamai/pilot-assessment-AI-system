"""Stable mapping from editable scoring modes to reusable operator identities."""

from __future__ import annotations

from pilot_assessment.contracts.evidence_recipe import RecipeScoring, ScoringMode

ORDERED_DAU_OPERATOR_IDENTITY = ("scoring.ordered-dau", "0.1.0")
SOFT_LIKELIHOOD_OPERATOR_IDENTITY = ("scoring.soft-likelihood", "0.1.0")


def scoring_operator_identity(scoring: RecipeScoring) -> tuple[str, str] | None:
    if scoring.mode is ScoringMode.ORDERED_DAU:
        return ORDERED_DAU_OPERATOR_IDENTITY
    if scoring.mode is ScoringMode.SOFT_LIKELIHOOD:
        return SOFT_LIKELIHOOD_OPERATOR_IDENTITY
    if scoring.custom_operator_id is None or scoring.custom_operator_version is None:
        return None
    return scoring.custom_operator_id, scoring.custom_operator_version


__all__ = [
    "ORDERED_DAU_OPERATOR_IDENTITY",
    "SOFT_LIKELIHOOD_OPERATOR_IDENTITY",
    "scoring_operator_identity",
]
