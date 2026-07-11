"""Shared, version-stable primitives for assessment contracts."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

STABLE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
BUNDLE_RELATIVE_PATH_PATTERN = r"^[^/\\:\x00]+(?:/[^/\\:\x00]+)*$"
BUNDLE_RELATIVE_PATH_JSON_SCHEMA_PATTERN = (
    r"^(?!.*(?:^|/)\.{1,2}(?:/|$))"
    r"(?!.*(?:^|/)[^/]*[. ](?:/|$))"
    r"[^/\\:\x00]+(?:/[^/\\:\x00]+)*$"
)
SHA256_PATTERN = r"^[0-9A-Fa-f]{64}$"
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1

_STABLE_ID_PATTERN = re.compile(STABLE_ID_PATTERN)
_SHA256_PATTERN = re.compile(SHA256_PATTERN)
_WINDOWS_DRIVE_PATTERN = re.compile(r"^[A-Za-z]:")


class StrictContractModel(BaseModel):
    """Base class for immutable DTOs that reject undeclared fields."""

    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        str_strip_whitespace=False,
    )


def _validate_stable_id(value: str) -> str:
    if _STABLE_ID_PATTERN.fullmatch(value) is None:
        raise ValueError(
            "must start with an ASCII letter or digit and contain at most 128 "
            "ASCII letters, digits, '.', '_' or '-'"
        )
    return value


def _validate_bundle_relative_path(value: str) -> str:
    if not value or value.endswith("/"):
        raise ValueError("must identify a file below the bundle root")
    if "\\" in value:
        raise ValueError("must use POSIX '/' separators")
    if value.startswith("/") or value.startswith("//") or _WINDOWS_DRIVE_PATTERN.match(value):
        raise ValueError("must be a relative path")
    if ":" in value or "\x00" in value:
        raise ValueError("must not be a URI, drive path or contain NUL")

    raw_parts = value.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise ValueError("must be normalized and must not traverse directories")
    if any(part.endswith((".", " ")) for part in raw_parts):
        raise ValueError("must not contain Windows-ambiguous path segments")

    normalized = PurePosixPath(value).as_posix()
    if normalized != value:
        raise ValueError("must be a canonical POSIX relative path")
    return value


def _normalize_sha256(value: str) -> str:
    if _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError("must contain exactly 64 hexadecimal characters")
    return value.lower()


StableId = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128, pattern=STABLE_ID_PATTERN),
    AfterValidator(_validate_stable_id),
]
BundleRelativePath = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=1024,
        pattern=BUNDLE_RELATIVE_PATH_PATTERN,
    ),
    Field(
        json_schema_extra={
            "x-runtime-invariants": [
                "segments are not empty, '.' or '..'",
                "segments do not end in a dot or space",
                "resolved files remain below the owning artifact root",
            ]
        }
    ),
    AfterValidator(_validate_bundle_relative_path),
]
Sha256Digest = Annotated[
    str,
    StringConstraints(min_length=64, max_length=64, pattern=SHA256_PATTERN),
    AfterValidator(_normalize_sha256),
]
FiniteFloat = Annotated[float, Field(strict=True, allow_inf_nan=False)]
PositiveFiniteFloat = Annotated[
    float,
    Field(strict=True, gt=0.0, allow_inf_nan=False),
]
NonNegativeFiniteFloat = Annotated[
    float,
    Field(strict=True, ge=0.0, allow_inf_nan=False),
]
UnitInterval = Annotated[
    float,
    Field(strict=True, ge=0.0, le=1.0, allow_inf_nan=False),
]
Int64 = Annotated[int, Field(strict=True, ge=INT64_MIN, le=INT64_MAX)]
NonNegativeInt64 = Annotated[int, Field(strict=True, ge=0, le=INT64_MAX)]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]

__all__ = [
    "BUNDLE_RELATIVE_PATH_PATTERN",
    "BUNDLE_RELATIVE_PATH_JSON_SCHEMA_PATTERN",
    "BundleRelativePath",
    "FiniteFloat",
    "INT64_MAX",
    "INT64_MIN",
    "Int64",
    "NonNegativeFiniteFloat",
    "NonNegativeInt",
    "NonNegativeInt64",
    "PositiveFiniteFloat",
    "SHA256_PATTERN",
    "Sha256Digest",
    "STABLE_ID_PATTERN",
    "StableId",
    "StrictContractModel",
    "UnitInterval",
]
