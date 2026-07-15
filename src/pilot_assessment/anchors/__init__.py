"""M4 anchor execution runtime boundaries."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pilot_assessment.anchors.models import (
    ReferenceViewCandidate,
    ResolvedReference,
    ResolvedReferenceSet,
)
from pilot_assessment.anchors.reference_resolution import (
    ReferenceBindingError,
    bind_resolved_reference_snapshot,
)

if TYPE_CHECKING:
    from pilot_assessment.anchors.models import AnchorEvaluationRequest
    from pilot_assessment.anchors.protocols import DerivedArtifactSink
    from pilot_assessment.contracts.anchor_execution import AnchorEvaluationReport


def evaluate(
    request: AnchorEvaluationRequest,
    sink: DerivedArtifactSink,
) -> AnchorEvaluationReport:
    """Lazily enter the fixed public evaluator without preloading CLI modules."""

    from pilot_assessment.anchors.api import evaluate as public_evaluate

    return public_evaluate(request, sink)


__all__ = [
    "ReferenceBindingError",
    "ReferenceViewCandidate",
    "ResolvedReference",
    "ResolvedReferenceSet",
    "bind_resolved_reference_snapshot",
    "evaluate",
]
