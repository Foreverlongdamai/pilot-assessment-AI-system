"""Fixed public M4 evaluation entry point."""

from pilot_assessment.anchors.dag import (
    EvaluationPolicy,
    validate_anchor_evaluation_request,
)
from pilot_assessment.anchors.models import AnchorEvaluationRequest
from pilot_assessment.anchors.protocols import DerivedArtifactSink
from pilot_assessment.anchors.registry import load_packaged_registry
from pilot_assessment.anchors.service import AnchorEvaluator
from pilot_assessment.contracts.anchor_execution import AnchorEvaluationReport


def evaluate(
    request: AnchorEvaluationRequest,
    sink: DerivedArtifactSink,
) -> AnchorEvaluationReport:
    """Evaluate through the packaged trusted registry and fixed production policy."""

    validate_anchor_evaluation_request(request)
    evaluator = AnchorEvaluator(
        load_packaged_registry(),
        EvaluationPolicy(
            require_packaged_registry_fingerprint=True,
            allow_injected_test_profile_ids=False,
        ),
    )
    return evaluator.evaluate(request, sink)


__all__ = ["evaluate"]
