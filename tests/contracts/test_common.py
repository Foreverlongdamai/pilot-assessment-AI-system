import math

import pytest
from pydantic import TypeAdapter, ValidationError

from pilot_assessment.contracts.common import (
    BundleRelativePath,
    Sha256Digest,
    StableId,
    UnitInterval,
)


@pytest.mark.parametrize(
    "value",
    ["O1", "session-p001-20260710-001", "PC.1", "aligned_state_grid-v1"],
)
def test_stable_id_accepts_canonical_ascii_identifiers(value: str) -> None:
    assert TypeAdapter(StableId).validate_python(value) == value


@pytest.mark.parametrize(
    "value",
    ["", " has-space", "contains space", "a/b", "生理", "a" * 129],
)
def test_stable_id_rejects_ambiguous_values(value: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(StableId).validate_python(value)


def test_bundle_relative_path_accepts_canonical_posix_file_path() -> None:
    value = "streams/flight_state.parquet"
    assert TypeAdapter(BundleRelativePath).validate_python(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        ".",
        "..",
        "../secret",
        "a/../../secret",
        "/etc/passwd",
        "C:/Windows/system.ini",
        r"C:\Windows\system.ini",
        r"\\server\share\data.parquet",
        r"a\..\secret",
        "a//b",
        "a/./b",
        "file:///tmp/data",
        "streams/data.parquet/",
    ],
)
def test_bundle_relative_path_rejects_escape_and_noncanonical_forms(value: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(BundleRelativePath).validate_python(value)


def test_sha256_digest_is_validated_and_normalized() -> None:
    uppercase = "A" * 64
    assert TypeAdapter(Sha256Digest).validate_python(uppercase) == uppercase.lower()


@pytest.mark.parametrize("value", ["", "a" * 63, "g" * 64, "a" * 65])
def test_sha256_digest_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(Sha256Digest).validate_python(value)


@pytest.mark.parametrize("value", [0.0, 0.25, 1.0])
def test_unit_interval_accepts_finite_bounds(value: float) -> None:
    assert TypeAdapter(UnitInterval).validate_python(value) == value


@pytest.mark.parametrize("value", [-0.1, 1.1, math.nan, math.inf, -math.inf])
def test_unit_interval_rejects_out_of_range_or_nonfinite_values(value: float) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(UnitInterval).validate_python(value)
