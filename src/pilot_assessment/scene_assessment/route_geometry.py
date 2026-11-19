"""Distance from an observed 3D position to an explicitly configured polyline."""

from __future__ import annotations

import math
from decimal import Decimal, localcontext
from fractions import Fraction

from pilot_assessment.scene_assessment.series_validation import is_number
from pilot_assessment.scene_assessment.validation import object_issues

COORDINATES = ("x_m", "y_m", "height_m")


def position_status(value):
    """Missing coordinates are missing evidence, never an observed deviation."""
    if not isinstance(value, dict):
        return "invalid", "三维位置必须是包含 x_m、y_m、height_m 的对象。"
    if object_issues(value, set(COORDINATES), ""):
        return "invalid", "三维位置包含未定义字段。"
    if any(value.get(key) is not None and not is_number(value[key]) for key in COORDINATES):
        return "invalid", "三维位置坐标必须为有限数值，不能使用布尔值或字符串。"
    if any(value.get(key) is None for key in COORDINATES):
        return "missing", "缺少当前帧完整的 x_m、y_m、height_m 位置坐标。"
    return "calculated", ""


def _decimal_segment(point, start, end):
    # Rare fallback for finite inputs whose intermediate vector arithmetic
    # exceeds float range. It does not repair or replace supplied observations.
    with localcontext() as context:
        context.prec = 80
        p, a, b = ([Decimal(value) for value in values] for values in (point, start, end))
        direction = [right - left for left, right in zip(a, b, strict=True)]
        length_squared = sum(value * value for value in direction)
        fraction = (
            sum(
                (actual - left) * delta for actual, left, delta in zip(p, a, direction, strict=True)
            )
            / length_squared
        )
        fraction = max(Decimal(0), min(Decimal(1), fraction))
        nearest = [
            (1 - fraction) * left + fraction * right for left, right in zip(a, b, strict=True)
        ]
        distance = sum(
            (actual - projected) ** 2 for actual, projected in zip(p, nearest, strict=True)
        ).sqrt()
        return float(distance), tuple(float(value) for value in nearest)


def _closest_segment(point, start, end):
    direction = tuple(right - left for left, right in zip(start, end, strict=True))
    offset = tuple(actual - left for actual, left in zip(point, start, strict=True))
    if not all(is_number(value) for value in (*direction, *offset)):
        return _decimal_segment(point, start, end)
    scale = max(abs(value) for value in direction)
    if scale == 0:
        return _decimal_segment(point, start, end)
    scaled_direction = tuple(value / scale for value in direction)
    try:
        scaled_offset = tuple(value / scale for value in offset)
        if not all(is_number(value) for value in scaled_offset):
            return _decimal_segment(point, start, end)
        projection = math.fsum(
            value * component
            for value, component in zip(scaled_offset, scaled_direction, strict=True)
        )
    except OverflowError:
        return _decimal_segment(point, start, end)
    length_squared = math.fsum(value * value for value in scaled_direction)
    fraction = max(0.0, min(1.0, projection / length_squared))
    # Convex coordinates avoid overflow from subtracting opposite large values.
    nearest = tuple(
        (1 - fraction) * left + fraction * right for left, right in zip(start, end, strict=True)
    )
    return math.dist(point, nearest), nearest


def _exactly_on_segment(point, start, end):
    """Use exact input-number ratios, without a spatial or grading epsilon."""
    p, a, b = ([Fraction(value) for value in values] for values in (point, start, end))
    direction = [right - left for left, right in zip(a, b, strict=True)]
    axis = max(range(3), key=lambda index: abs(direction[index]))
    fraction = (p[axis] - a[axis]) / direction[axis]
    return 0 <= fraction <= 1 and all(
        actual - left == fraction * delta
        for actual, left, delta in zip(p, a, direction, strict=True)
    )


def nearest_route_position(value, route_points):
    """Return distance, nearest point and zero-based segment index.

    Call only with a validated position and a complete route. Segments are
    finite, including their endpoints. Ties use the first configured segment.
    Node order is retained; this spatial check does not infer route progress.
    """
    point = tuple(value[key] for key in COORDINATES)
    nodes = [tuple(node[key] for key in COORDINATES) for node in route_points]
    best = None
    for index, (start, end) in enumerate(zip(nodes, nodes[1:], strict=False)):
        distance, nearest = _closest_segment(point, start, end)
        # A computed nearest point can differ by a few representational ULPs
        # even for an exactly collinear input. Recheck exact number ratios at
        # that scale. This only selects a higher-precision check: an actual
        # nonzero deviation is retained, even when smaller than one ULP here.
        precision_scale = max(math.ulp(value) for value in (*point, *start, *end))
        if 0 < distance <= 8 * precision_scale and _exactly_on_segment(point, start, end):
            distance, nearest = 0.0, point
        if best is None or distance < best[0]:
            best = distance, dict(zip(COORDINATES, nearest, strict=True)), index
    return best
