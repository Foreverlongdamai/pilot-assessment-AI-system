from __future__ import annotations

import math

import pytest

from pilot_assessment.contracts.anchor import EvidenceState
from pilot_assessment.contracts.model_components import RawModality
from pilot_assessment.evidence.builtins import (
    NumericSample,
    SignalSeries,
    VectorSample,
    VectorSeries,
    register_builtin_operators,
)
from pilot_assessment.evidence.compiler import compile_recipe
from pilot_assessment.evidence.executor import execute_recipe
from pilot_assessment.evidence.registry import OperatorRegistry
from pilot_assessment.model_library.migration import (
    load_hover_evidence_inventory,
    preflight_recipe_migration,
)
from pilot_assessment.model_library.sources import load_hover_source_catalog


def test_tpx_parallel_version_uses_only_provenance_closed_raw_and_session_inputs() -> None:
    inventory = load_hover_evidence_inventory()
    version = inventory.parallel_versions[0]

    report = preflight_recipe_migration(version.recipe, load_hover_source_catalog())

    assert report.compatible
    assert not report.legacy_only
    assert report.input_source_ids == ("X.state-vector", "U.channels", "session.duration-s")
    assert report.raw_modalities == (RawModality.X, RawModality.U)
    assert all(not source_id.startswith("anchor.") for source_id in report.input_source_ids)
    assert version.recipe.recipe_id == "starter.tpx.raw-task-v1"


def test_tpx_parallel_version_compiles_and_executes_with_tiny_in_memory_values() -> None:
    version = load_hover_evidence_inventory().parallel_versions[0]
    registry = OperatorRegistry()
    register_builtin_operators(registry)
    flight_state = VectorSeries(
        series_id="flight-state",
        dimensions=("x", "y", "z"),
        unit=None,
        samples=(
            VectorSample(0, (0.0, 0.0, 0.0)),
            VectorSample(5_000_000_000, (0.5, -0.5, 0.25)),
        ),
    )
    control = SignalSeries(
        series_id="primary",
        unit=None,
        samples=tuple(
            NumericSample(index * 2_000_000_000, value)
            for index, value in enumerate((0.0, 2.0, 0.0, 2.0, 0.0))
        ),
    )

    result = execute_recipe(
        compile_recipe(version.recipe, registry),
        registry,
        binding_values={
            "flight-state": flight_state,
            "control-bundle": {"primary": control},
            "session-duration-s": 90.0,
        },
    )

    primary = result.outputs["primary"]
    assert isinstance(primary, float)
    assert math.isfinite(primary)
    assert primary == pytest.approx(91.0 / 92.0)
    assert result.scoring_outputs["state"] is EvidenceState.DESIRED
