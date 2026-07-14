"""Shared, version-stable primitives for assessment contracts."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Annotated, Any, NoReturn, Self, SupportsIndex, cast

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, JsonValue, StringConstraints

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


class _FrozenJsonDict(dict[str, Any]):
    """Dict-compatible immutable snapshot used inside frozen contract DTOs."""

    def __setitem__(self, _key: str, _value: Any) -> None:
        raise TypeError("validated JSON mappings are immutable")

    def __delitem__(self, _key: str) -> None:
        raise TypeError("validated JSON mappings are immutable")

    def __ior__(self, _value: Any, /) -> Self:
        raise TypeError("validated JSON mappings are immutable")

    def clear(self) -> None:
        raise TypeError("validated JSON mappings are immutable")

    def pop(self, _key: object, _default: Any = None, /) -> Any:
        raise TypeError("validated JSON mappings are immutable")

    def popitem(self) -> tuple[str, Any]:
        raise TypeError("validated JSON mappings are immutable")

    def setdefault(self, _key: str, _default: Any = None, /) -> Any:
        raise TypeError("validated JSON mappings are immutable")

    def update(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("validated JSON mappings are immutable")

    def __deepcopy__(self, _memo: dict[int, object]) -> Self:
        return self


class _FrozenJsonList(list[Any]):
    """List-compatible immutable snapshot preserving JSON/list equality."""

    @staticmethod
    def _reject() -> NoReturn:
        raise TypeError("validated JSON arrays are immutable")

    def __setitem__(self, _index: Any, _value: Any) -> None:
        self._reject()

    def __delitem__(self, _index: Any) -> None:
        self._reject()

    def __iadd__(self, _value: Any) -> Self:
        self._reject()

    def __imul__(self, _value: SupportsIndex) -> Self:
        self._reject()

    def append(self, _value: Any) -> None:
        self._reject()

    def clear(self) -> None:
        self._reject()

    def extend(self, _values: Any) -> None:
        self._reject()

    def insert(self, _index: SupportsIndex, _value: Any) -> None:
        self._reject()

    def pop(self, _index: SupportsIndex = -1) -> Any:
        self._reject()

    def remove(self, _value: Any) -> None:
        self._reject()

    def reverse(self) -> None:
        self._reject()

    def sort(self, *args: Any, **kwargs: Any) -> None:
        self._reject()

    def __deepcopy__(self, _memo: dict[int, object]) -> Self:
        return self


def freeze_json_value(value: JsonValue) -> JsonValue:
    """Recursively snapshot a validated JSON tree without changing its JSON shape."""

    if isinstance(value, dict):
        frozen: dict[str, JsonValue] = {}
        for key, nested in value.items():
            if type(key) is not str:
                raise TypeError("JSON object keys must be strings")
            frozen[key] = freeze_json_value(nested)
        return cast(JsonValue, _FrozenJsonDict(frozen))
    if isinstance(value, (list, tuple)):
        return cast(JsonValue, _FrozenJsonList(freeze_json_value(item) for item in value))
    return value


def freeze_json_mapping(value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Return a dict-compatible recursively immutable JSON object snapshot."""

    return cast(dict[str, JsonValue], freeze_json_value(value))


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
    "freeze_json_mapping",
    "freeze_json_value",
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
