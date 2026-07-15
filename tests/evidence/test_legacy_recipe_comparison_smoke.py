from __future__ import annotations

import math

from pilot_assessment.contracts.anchor import EvidenceState
from pilot_assessment.evidence.builtins import (
    GazeFrame,
    NumericSample,
    SignalSeries,
    VectorSample,
    VectorSeries,
    register_builtin_operators,
)
from pilot_assessment.evidence.catalog import load_packaged_starter_catalog
from pilot_assessment.evidence.compiler import compile_recipe
from pilot_assessment.evidence.executor import RecipeExecutionResult, execute_recipe
from pilot_assessment.evidence.registry import OperatorRegistry


def _run(anchor_id: str, inputs: dict[str, object]) -> RecipeExecutionResult:
    registry = OperatorRegistry()
    register_builtin_operators(registry)
    recipe = load_packaged_starter_catalog().get_by_anchor(anchor_id)
    return execute_recipe(
        compile_recipe(recipe, registry),
        registry,
        binding_values=inputs,
    )


def test_o2_starter_preserves_peak_excursion_shape_and_initial_boundaries() -> None:
    actual = VectorSeries(
        series_id="actual",
        dimensions=("x", "y", "z"),
        unit="ft",
        samples=(
            VectorSample(0, (0.0, 0.0, 0.0)),
            VectorSample(1_000_000_000, (3.0, 4.0, 0.0)),
        ),
    )
    commanded = VectorSeries(
        series_id="commanded",
        dimensions=("x", "y", "z"),
        unit="ft",
        samples=(
            VectorSample(0, (0.0, 0.0, 0.0)),
            VectorSample(1_000_000_000, (0.0, 0.0, 0.0)),
        ),
    )

    result = _run("O2", {"actual-path": actual, "commanded-path": commanded})

    assert result.outputs["primary"] == 5.0
    assert result.scoring_outputs["state"] is EvidenceState.ADEQUATE


def test_h1_starter_turns_small_gaze_frames_into_expected_aoi_dwell() -> None:
    frames = (
        GazeFrame("instrument", 0, 8_500_000_000, "instrument", {}),
        GazeFrame("outside", 8_500_000_000, 10_000_000_000, "outside", {}),
    )

    result = _run("H1", {"gaze-frames": frames, "session-duration-s": 10.0})

    assert result.outputs["primary"] == 85.0
    assert result.scoring_outputs["state"] is EvidenceState.DESIRED


def test_h4_starter_composes_channel_detrend_and_rms_without_quality_filtering() -> None:
    heart_rate = SignalSeries(
        series_id="heart-rate",
        unit="bpm",
        samples=(
            NumericSample(0, 60.0),
            NumericSample(1_000_000_000, 70.0),
            NumericSample(2_000_000_000, 50.0),
        ),
    )

    result = _run("H4", {"h4-bundle": {"heart-rate": heart_rate}})

    assert math.isclose(
        result.outputs["primary"],
        math.sqrt(200.0 / 3.0),
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    assert result.scoring_outputs["state"] is EvidenceState.DESIRED
