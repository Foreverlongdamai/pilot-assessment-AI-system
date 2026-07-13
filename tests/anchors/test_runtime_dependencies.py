from __future__ import annotations

import base64
import hashlib
from importlib import import_module
from importlib.metadata import Distribution, distribution
from pathlib import Path, PurePosixPath

import pytest
import rfc8785

_RUNTIME_VERSION_BOUNDS = {
    "numpy": ((2, 3, 4), (2, 4, 0)),
    "scipy": ((1, 17, 0), (1, 18, 0)),
    "rfc8785": ((0, 1, 4), (0, 2, 0)),
}
_MUTABLE_RECORD_NAMES = frozenset({"INSTALLER", "REQUESTED", "direct_url.json"})


def _release_tuple(raw_version: str) -> tuple[int, int, int]:
    release = raw_version.split("+", maxsplit=1)[0].split(".")
    assert len(release) == 3
    major, minor, patch = (int(component) for component in release)
    return major, minor, patch


def _decode_urlsafe_digest(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _stable_record_rows(
    installed: Distribution,
) -> tuple[list[list[str | int]], set[str]]:
    package_files = installed.files
    assert package_files is not None
    assert installed.read_text("RECORD")

    distribution_root = Path(str(installed.locate_file(""))).resolve()
    rows: list[list[str | int]] = []
    excluded_paths: set[str] = set()

    for package_file in package_files:
        relative = PurePosixPath(str(package_file).replace("\\", "/"))
        relative_text = relative.as_posix()
        is_unsafe_path = relative.is_absolute() or ".." in relative.parts
        is_mutable_metadata = relative.name in _MUTABLE_RECORD_NAMES
        is_cache_file = "__pycache__" in relative.parts or relative.suffix in {".pyc", ".pyo"}
        is_record = relative.name == "RECORD"
        declared_hash = package_file.hash
        declared_size = package_file.size

        if (
            is_unsafe_path
            or is_mutable_metadata
            or is_cache_file
            or is_record
            or declared_hash is None
            or declared_hash.mode != "sha256"
            or declared_size is None
        ):
            excluded_paths.add(relative_text)
            continue

        resolved_file = Path(str(installed.locate_file(package_file))).resolve()
        assert resolved_file.is_relative_to(distribution_root)
        payload = resolved_file.read_bytes()
        assert len(payload) == declared_size
        assert hashlib.sha256(payload).digest() == _decode_urlsafe_digest(declared_hash.value)

        rows.append([relative_text, "sha256", declared_hash.value, declared_size])

    rows.sort(key=lambda row: str(row[0]))
    assert rows
    return rows, excluded_paths


@pytest.mark.parametrize(
    ("distribution_name", "lower", "upper"),
    [(name, bounds[0], bounds[1]) for name, bounds in _RUNTIME_VERSION_BOUNDS.items()],
)
def test_locked_runtime_dependency_is_importable_and_in_range(
    distribution_name: str,
    lower: tuple[int, int, int],
    upper: tuple[int, int, int],
) -> None:
    imported = import_module(distribution_name)
    installed = distribution(distribution_name)
    resolved = _release_tuple(installed.version)

    assert imported is not None
    assert lower <= resolved < upper


@pytest.mark.parametrize("distribution_name", _RUNTIME_VERSION_BOUNDS)
def test_stable_record_identity_rows_are_relative_and_content_verified(
    distribution_name: str,
) -> None:
    installed = distribution(distribution_name)
    rows, excluded_paths = _stable_record_rows(installed)
    canonical_rows = rfc8785.dumps(rows)

    assert len(hashlib.sha256(canonical_rows).hexdigest()) == 64
    assert str(Path(str(installed.locate_file(""))).resolve()).encode() not in canonical_rows
    assert all(not PurePosixPath(str(row[0])).is_absolute() for row in rows)
    assert all(".." not in PurePosixPath(str(row[0])).parts for row in rows)
    assert all(PurePosixPath(str(row[0])).name not in _MUTABLE_RECORD_NAMES for row in rows)
    assert all("__pycache__" not in PurePosixPath(str(row[0])).parts for row in rows)
    assert all(PurePosixPath(str(row[0])).name != "RECORD" for row in rows)
    assert any(PurePosixPath(path).name == "RECORD" for path in excluded_paths)
    assert any(PurePosixPath(path).name == "INSTALLER" for path in excluded_paths)
    if distribution_name == "numpy":
        installer_launchers = {path for path in excluded_paths if ".." in PurePosixPath(path).parts}
        assert installer_launchers
        assert {str(row[0]) for row in rows}.isdisjoint(installer_launchers)
