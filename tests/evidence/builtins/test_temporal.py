from __future__ import annotations

from pilot_assessment.evidence.builtins.temporal import (
    EventRecord,
    EventSelectOperator,
    EventWindowOperator,
    IntervalIntersectOperator,
    IntervalRecord,
)
from pilot_assessment.evidence.operators import OperatorExecutionContext


def _context() -> OperatorExecutionContext:
    return OperatorExecutionContext(
        recipe_id="temporal-smoke",
        recipe_version=1,
        node_id="temporal",
        binding_values={},
    )


def test_event_selection_window_and_intersection_are_composable() -> None:
    context = _context()
    events = (
        EventRecord("event-1", "disturbance", 1_000_000_000),
        EventRecord("event-2", "phase-change", 8_000_000_000),
    )

    selected = EventSelectOperator().execute(
        {"events": events},
        {"event_types": ["disturbance"]},
        context,
    )["value"]
    windows = EventWindowOperator().execute(
        {"events": selected},
        {
            "start_offset_ns": 0,
            "end_offset_ns": 5_000_000_000,
            "include_event_duration": False,
            "clamp_to_zero": True,
        },
        context,
    )["value"]
    intersections = IntervalIntersectOperator().execute(
        {
            "left": windows,
            "right": (IntervalRecord("look", 2_000_000_000, 4_000_000_000, {}),),
        },
        {},
        context,
    )["value"]

    assert windows == (
        IntervalRecord(
            "window-event-1",
            1_000_000_000,
            6_000_000_000,
            {"event_id": "event-1", "event_type": "disturbance"},
        ),
    )
    assert intersections == (
        IntervalRecord(
            "intersection-window-event-1-look",
            2_000_000_000,
            4_000_000_000,
            {
                "event_id": "event-1",
                "event_type": "disturbance",
                "left_interval_id": "window-event-1",
                "right_interval_id": "look",
            },
        ),
    )
