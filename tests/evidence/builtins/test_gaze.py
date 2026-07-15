from __future__ import annotations

from pilot_assessment.evidence.builtins.gaze import (
    AoiFilterOperator,
    DwellRatioOperator,
    FirstMatchLatencyOperator,
    GazeAoiIntervalsOperator,
    GazeFrame,
)
from pilot_assessment.evidence.builtins.temporal import IntervalRecord
from pilot_assessment.evidence.operators import OperatorExecutionContext


def _context() -> OperatorExecutionContext:
    return OperatorExecutionContext(
        recipe_id="gaze-smoke",
        recipe_version=1,
        node_id="gaze",
        binding_values={},
    )


def _frames() -> tuple[GazeFrame, ...]:
    return (
        GazeFrame("frame-1", 1_000_000_000, 2_000_000_000, "outside", {}),
        GazeFrame(
            "frame-2",
            2_000_000_000,
            4_000_000_000,
            "instrument",
            {"outside": 1.0, "instrument": 2.0},
        ),
        GazeFrame("frame-3", 4_000_000_000, 6_000_000_000, "outside", {}),
    )


def test_assigned_and_geometry_modes_are_explicit_recipe_choices() -> None:
    context = _context()

    assigned = GazeAoiIntervalsOperator().execute(
        {"frames": _frames()},
        {"mode": "assigned_label", "merge_adjacent": True},
        context,
    )["value"]
    geometry = GazeAoiIntervalsOperator().execute(
        {"frames": _frames()},
        {"mode": "geometry_association", "merge_adjacent": True},
        context,
    )["value"]

    assert tuple(item.attributes["aoi_id"] for item in assigned) == (
        "outside",
        "instrument",
        "outside",
    )
    assert tuple(item.attributes["aoi_id"] for item in geometry) == ("outside",)


def test_no_matching_aoi_is_negative_evidence_not_missing_evidence() -> None:
    context = _context()
    window = IntervalRecord(
        "window-event-1",
        1_000_000_000,
        6_000_000_000,
        {},
    )
    assigned = GazeAoiIntervalsOperator().execute(
        {"frames": _frames()},
        {"mode": "assigned_label", "merge_adjacent": True},
        context,
    )["value"]
    matches = AoiFilterOperator().execute(
        {"intervals": assigned},
        {"aoi_ids": ["not-observed"]},
        context,
    )["value"]

    latency = FirstMatchLatencyOperator().execute(
        {"windows": (window,), "matches": matches},
        {"no_match_policy": "window_end", "fixed_latency_s": 0.0},
        context,
    )["value"]
    dwell = DwellRatioOperator().execute(
        {"windows": (window,), "matches": matches},
        {},
        context,
    )["value"]

    assert dict(latency) == {"window-event-1": 5.0}
    assert dict(dwell) == {"window-event-1": 0.0}
