"""Deterministic synthetic artifacts used only for software verification."""

from pilot_assessment.synthetic.generator import generate_synthetic_bundle
from pilot_assessment.synthetic.prng import float32, triangular_noise, uniform53
from pilot_assessment.synthetic.timelines import (
    in_session_window,
    map_source_seconds_to_session_ns,
    source_grid,
)

__all__ = [
    "float32",
    "generate_synthetic_bundle",
    "in_session_window",
    "map_source_seconds_to_session_ns",
    "source_grid",
    "triangular_noise",
    "uniform53",
]
