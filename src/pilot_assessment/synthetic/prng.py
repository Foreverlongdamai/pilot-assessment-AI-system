"""Versioned SHA-256 counter noise with no implicit global random state."""

from __future__ import annotations

import hashlib
import math
import re
import struct

_PREFIX = b"pilot-assessment|sha256-counter-prng-v0.1\0"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MAX_SEED = 2**63 - 1
_MAX_UINT64 = 2**64 - 1
_MAX_UINT32 = 2**32 - 1
_UNIFORM_DENOMINATOR = 2**53


def _identifier_bytes(value: str, field: str) -> bytes:
    if _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{field} must be a non-empty ASCII stable identifier")
    return value.encode("ascii")


def _counter_payload(
    seed: int,
    modality: str,
    channel: str,
    index: int,
    lane: int,
) -> bytes:
    if isinstance(seed, bool) or not 0 <= seed <= _MAX_SEED:
        raise ValueError("seed must be an integer in 0..2^63-1")
    if isinstance(index, bool) or not 0 <= index <= _MAX_UINT64:
        raise ValueError("index must be an integer in 0..2^64-1")
    if isinstance(lane, bool) or not 0 <= lane <= _MAX_UINT32:
        raise ValueError("lane must be an integer in 0..2^32-1")
    return b"".join(
        (
            _PREFIX,
            str(seed).encode("ascii"),
            b"\0",
            _identifier_bytes(modality, "modality"),
            b"\0",
            _identifier_bytes(channel, "channel"),
            b"\0",
            index.to_bytes(8, "big"),
            lane.to_bytes(4, "big"),
        )
    )


def uniform53(
    seed: int,
    modality: str,
    channel: str,
    index: int,
    lane: int,
) -> float:
    """Return a deterministic open-interval uniform value from a counter coordinate."""

    digest = hashlib.sha256(_counter_payload(seed, modality, channel, index, lane)).digest()
    mantissa = int.from_bytes(digest[:8], "big") >> 11
    return (mantissa + 0.5) / _UNIFORM_DENOMINATOR


def float32(value: float) -> float:
    """Quantize a finite Python float to IEEE-754 binary32, round-to-nearest-even."""

    if not math.isfinite(value):
        raise ValueError("binary32 values must be finite")
    try:
        return struct.unpack("<f", struct.pack("<f", value))[0]
    except OverflowError as error:
        raise ValueError("value is outside the finite binary32 range") from error


def triangular_noise(seed: int, modality: str, channel: str, index: int) -> float:
    """Return deterministic bounded triangular noise quantized to binary32."""

    return float32(
        uniform53(seed, modality, channel, index, 0)
        + uniform53(seed, modality, channel, index, 1)
        - 1.0
    )


__all__ = ["float32", "triangular_noise", "uniform53"]
