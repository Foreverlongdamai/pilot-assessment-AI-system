from __future__ import annotations

import base64
import csv
import hashlib
import importlib.metadata
import io
import json
import os
import struct
import sys
import sysconfig
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any, cast

import pytest
import rfc8785
from pydantic import JsonValue

from pilot_assessment.contracts.anchor_execution import (
    NumericRuntimeIdentity,
    PythonRuntimeIdentity,
)


@pytest.fixture
def fingerprint_module() -> ModuleType:
    return import_module("pilot_assessment.anchors.fingerprint")


def _call(module: ModuleType, name: str, *args: object) -> Any:
    return getattr(module, name)(*args)


def _typed_hash(type_id: str, version: str, payload: object) -> str:
    canonical = rfc8785.dumps(cast(JsonValue, payload))
    framed = (
        type_id.encode("ascii")
        + b"\0"
        + version.encode("ascii")
        + b"\0"
        + struct.pack(">Q", len(canonical))
        + canonical
    )
    return hashlib.sha256(framed).hexdigest()


def _urlsafe_sha256(payload: bytes) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=").decode()


_Z_MEMBER_DIGEST = _urlsafe_sha256(b"Z = 1\n")


@dataclass
class _FakeDistribution:
    root: Path
    dist_info_name: str
    project_name: str
    version: str
    read_counts: dict[str, int] = field(default_factory=dict)

    @property
    def metadata(self) -> dict[str, str]:
        return {"Name": self.project_name}

    @property
    def files(self) -> tuple[PurePosixPath, ...]:
        text = (self.root / self.dist_info_name / "RECORD").read_text(encoding="utf-8")
        return tuple(PurePosixPath(row[0]) for row in csv.reader(io.StringIO(text)))

    @property
    def _path(self) -> Path:
        return self.root / self.dist_info_name

    def locate_file(self, path: str | os.PathLike[str]) -> Path:
        return self.root / os.fspath(path)

    def read_text(self, filename: str) -> str | None:
        self.read_counts[filename] = self.read_counts.get(filename, 0) + 1
        path = self.root / self.dist_info_name / filename
        return path.read_text(encoding="utf-8") if path.is_file() else None


def _write_csv(rows: list[list[str]]) -> str:
    stream = io.StringIO(newline="")
    csv.writer(stream, lineterminator="\n").writerows(rows)
    return stream.getvalue()


def _build_distribution(
    tmp_path: Path,
    *,
    project_name: str = "Demo.Pkg_Name",
    direct_url: str | None = None,
) -> tuple[_FakeDistribution, list[list[str | int]]]:
    root = tmp_path / "venv" / "Lib" / "site-packages"
    dist_info_name = "demo_pkg_name-1.2.3.dist-info"
    dist_info = root / dist_info_name
    dist_info.mkdir(parents=True)
    members = {
        "demo_pkg/Z.py": b"Z = 1\n",
        "demo_pkg/\u00e9.txt": b"accent\n",
    }
    declared: list[list[str | int]] = []
    for relative, payload in members.items():
        path = root / PurePosixPath(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        declared.append([relative, "sha256", _urlsafe_sha256(payload), len(payload)])
    rows = [[str(item[0]), f"sha256={item[2]}", str(item[3])] for item in reversed(declared)]
    rows.extend(
        [
            [f"{dist_info_name}/INSTALLER", "", ""],
            [f"{dist_info_name}/REQUESTED", "", ""],
            [f"{dist_info_name}/RECORD", "", ""],
        ]
    )
    if direct_url is not None:
        (dist_info / "direct_url.json").write_text(direct_url, encoding="utf-8")
        rows.append([f"{dist_info_name}/direct_url.json", "", ""])
    (dist_info / "RECORD").write_text(_write_csv(rows), encoding="utf-8", newline="")
    return _FakeDistribution(root, dist_info_name, project_name, "1.2.3"), declared


def _patch_distribution(
    module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    installed: _FakeDistribution,
) -> None:
    def lookup(_name: str) -> _FakeDistribution:
        return installed

    monkeypatch.setattr(importlib.metadata, "distribution", lookup)
    monkeypatch.setattr(module, "distribution", lookup, raising=False)


def _record_rows(installed: _FakeDistribution) -> list[list[str]]:
    record = installed.root / installed.dist_info_name / "RECORD"
    return list(csv.reader(io.StringIO(record.read_text(encoding="utf-8"))))


def _replace_record(installed: _FakeDistribution, rows: list[list[str]]) -> None:
    record = installed.root / installed.dist_info_name / "RECORD"
    record.write_text(_write_csv(rows), encoding="utf-8", newline="")


def test_python_runtime_prefers_soabi_over_windows_ext_suffix(
    fingerprint_module: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    values = {"SOABI": "cp311-authoritative", "EXT_SUFFIX": ".bad.extra.pyd"}
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sysconfig, "get_config_var", values.get)

    identity = _call(fingerprint_module, "python_runtime_identity")

    assert identity.soabi == "cp311-authoritative"
    assert identity.version == tuple(sys.version_info[:3])
    assert identity.implementation_name == sys.implementation.name
    assert identity.cache_tag == sys.implementation.cache_tag


@pytest.mark.parametrize(
    ("suffix", "expected"),
    [
        (".cp311-win_amd64.pyd", "cp311-win_amd64"),
        (".cp313t-win_amd64.pyd", "cp313t-win_amd64"),
        (".cp313d-win_amd64.pyd", "cp313d-win_amd64"),
    ],
)
def test_python_runtime_uses_exact_windows_ext_suffix_fallback(
    fingerprint_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
    expected: str,
) -> None:
    values = {"SOABI": None, "EXT_SUFFIX": suffix}
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sysconfig, "get_config_var", values.get)

    assert _call(fingerprint_module, "python_runtime_identity").soabi == expected


@pytest.mark.parametrize(
    "suffix",
    [None, "", "cp311-win_amd64.pyd", ".cp311.win_amd64.pyd", ".pyd", ".cp311.so"],
)
def test_python_runtime_rejects_invalid_windows_abi_fallback(
    fingerprint_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    suffix: str | None,
) -> None:
    values = {"SOABI": None, "EXT_SUFFIX": suffix}
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sysconfig, "get_config_var", values.get)

    with pytest.raises((TypeError, ValueError)):
        _call(fingerprint_module, "python_runtime_identity")


def test_distribution_identity_uses_metadata_pep503_name_and_sorted_stable_record(
    fingerprint_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    installed, declared = _build_distribution(tmp_path)
    _patch_distribution(fingerprint_module, monkeypatch, installed)
    expected_rows = sorted(declared, key=lambda row: str(row[0]))

    identity = _call(fingerprint_module, "distribution_content_identity", "ignored_request")

    assert identity == NumericRuntimeIdentity(
        normalized_name="demo-pkg-name",
        version="1.2.3",
        record_content_sha256=_typed_hash("numeric-runtime-record", "0.1.0", expected_rows),
    )
    assert installed.read_counts["RECORD"] == 1
    assert str(installed.root) not in json.dumps(identity.model_dump(mode="json"))


@pytest.mark.parametrize(
    "direct_url",
    [
        '{"dir_info":{"editable":true}}',
        '{"dir_info":{},"dir_info":{}}',
        '{"dir_info":{"editable":false,"editable":false}}',
        '{"dir_info":{"editable":"true"}}',
        "{",
        "[]",
    ],
)
def test_distribution_identity_rejects_editable_or_ambiguous_direct_url(
    fingerprint_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    direct_url: str,
) -> None:
    installed, _ = _build_distribution(tmp_path, direct_url=direct_url)
    _patch_distribution(fingerprint_module, monkeypatch, installed)

    with pytest.raises((TypeError, ValueError)):
        _call(fingerprint_module, "distribution_content_identity", "demo")


def test_distribution_identity_requires_exact_three_cell_record_rows(
    fingerprint_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    installed, _ = _build_distribution(tmp_path)
    rows = _record_rows(installed)
    rows.append(["demo_pkg/bad.py", "sha256=abc"])
    _replace_record(installed, rows)
    _patch_distribution(fingerprint_module, monkeypatch, installed)

    with pytest.raises((TypeError, ValueError)):
        _call(fingerprint_module, "distribution_content_identity", "demo")


@pytest.mark.parametrize(
    "bad_path",
    [
        "",
        "../escape.py",
        "demo_pkg\\alias.py",
        "/absolute.py",
        "demo_pkg//empty.py",
        "demo_pkg/./dot.py",
        "./demo_pkg/dot.py",
        "demo_pkg/Z.py",
        "demo_pkg/z.py",
    ],
)
def test_distribution_identity_rejects_traversal_paths_and_aliases(
    fingerprint_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    bad_path: str,
) -> None:
    installed, _ = _build_distribution(tmp_path)
    rows = _record_rows(installed)
    rows.append([bad_path, f"sha256={_urlsafe_sha256(b'x')}", "1"])
    _replace_record(installed, rows)
    _patch_distribution(fingerprint_module, monkeypatch, installed)

    with pytest.raises((TypeError, ValueError)):
        _call(fingerprint_module, "distribution_content_identity", "demo")


@pytest.mark.parametrize(
    "declaration",
    (
        "md5=YWJj",
        "sha256=abc",
        "sha256=********************************43",
        f"sha256={_Z_MEMBER_DIGEST}=",
    ),
)
def test_distribution_identity_rejects_noncanonical_sha256_declarations(
    fingerprint_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    declaration: str,
) -> None:
    installed, _ = _build_distribution(tmp_path)
    rows = _record_rows(installed)
    rows[0][1] = declaration
    _replace_record(installed, rows)
    _patch_distribution(fingerprint_module, monkeypatch, installed)

    with pytest.raises((TypeError, ValueError)):
        _call(fingerprint_module, "distribution_content_identity", "demo")


@pytest.mark.parametrize("mutation", ["hash", "size", "missing-hash", "missing-size"])
def test_distribution_identity_recomputes_retained_member_hash_and_size(
    fingerprint_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mutation: str,
) -> None:
    installed, _ = _build_distribution(tmp_path)
    rows = _record_rows(installed)
    stable = rows[0]
    if mutation == "hash":
        stable[1] = f"sha256={_urlsafe_sha256(b'wrong')}"
    elif mutation == "size":
        stable[2] = str(int(stable[2]) + 1)
    elif mutation == "missing-hash":
        stable[1] = ""
    else:
        stable[2] = ""
    _replace_record(installed, rows)
    _patch_distribution(fingerprint_module, monkeypatch, installed)

    with pytest.raises((TypeError, ValueError)):
        _call(fingerprint_module, "distribution_content_identity", "demo")


def test_distribution_identity_rejects_retained_symlink(
    fingerprint_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    installed, _ = _build_distribution(tmp_path)
    link = installed.root / "demo_pkg" / "Z.py"
    target = installed.root / "demo_pkg" / "target.py"
    payload = link.read_bytes()
    target.write_bytes(payload)
    link.unlink()
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("host does not permit creating a test symlink")
    _patch_distribution(fingerprint_module, monkeypatch, installed)

    with pytest.raises((TypeError, ValueError)):
        _call(fingerprint_module, "distribution_content_identity", "demo")


def test_distribution_identity_excludes_only_exact_mutable_members(
    fingerprint_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    installed, declared = _build_distribution(tmp_path)
    rows = _record_rows(installed)
    package_installer = installed.root / "demo_pkg" / "INSTALLER"
    package_installer.write_bytes(b"package resource\n")
    package_row: list[str | int] = [
        "demo_pkg/INSTALLER",
        "sha256",
        _urlsafe_sha256(package_installer.read_bytes()),
        package_installer.stat().st_size,
    ]
    rows.append([str(package_row[0]), f"sha256={package_row[2]}", str(package_row[3])])

    excluded_paths = (
        "demo_pkg/__pycache__/cache.cpython-311.pyc",
        "demo_pkg/cache.pyo",
    )
    for relative in excluded_paths:
        path = installed.root / PurePosixPath(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"mutable bytecode")
        rows.append([relative, "", ""])
    _replace_record(installed, rows)
    _patch_distribution(fingerprint_module, monkeypatch, installed)

    expected_rows = sorted([*declared, package_row], key=lambda row: str(row[0]))
    first = _call(fingerprint_module, "distribution_content_identity", "demo")
    assert first.record_content_sha256 == _typed_hash(
        "numeric-runtime-record", "0.1.0", expected_rows
    )

    for relative in excluded_paths:
        (installed.root / PurePosixPath(relative)).write_bytes(b"changed excluded bytes")
    assert _call(fingerprint_module, "distribution_content_identity", "demo") == first

    changed_payload = b"changed stable package resource\n"
    package_installer.write_bytes(changed_payload)
    rows = _record_rows(installed)
    for row in rows:
        if row[0] == "demo_pkg/INSTALLER":
            row[1] = f"sha256={_urlsafe_sha256(changed_payload)}"
            row[2] = str(len(changed_payload))
    _replace_record(installed, rows)
    assert _call(fingerprint_module, "distribution_content_identity", "demo") != first


def test_distribution_identity_excludes_exact_active_scripts_traversal(
    fingerprint_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    installed, declared = _build_distribution(tmp_path)
    scripts = tmp_path / "venv" / "Scripts"
    scripts.mkdir(parents=True)
    launcher = scripts / "demo.exe"
    launcher.write_bytes(b"root-specific launcher")
    rows = _record_rows(installed)
    rows.append(
        [
            "../../Scripts/demo.exe",
            f"sha256={_urlsafe_sha256(launcher.read_bytes())}",
            str(launcher.stat().st_size),
        ]
    )
    _replace_record(installed, rows)
    _patch_distribution(fingerprint_module, monkeypatch, installed)
    original_get_path = sysconfig.get_path
    monkeypatch.setattr(
        sysconfig,
        "get_path",
        lambda name, *args, **kwargs: (
            str(scripts) if name == "scripts" else original_get_path(name, *args, **kwargs)
        ),
    )

    identity = _call(fingerprint_module, "distribution_content_identity", "demo")
    assert identity.record_content_sha256 == _typed_hash(
        "numeric-runtime-record", "0.1.0", sorted(declared, key=lambda row: str(row[0]))
    )


def test_distribution_identity_requires_a_present_stable_member(
    fingerprint_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    installed, _ = _build_distribution(tmp_path)
    rows = [
        row
        for row in _record_rows(installed)
        if PurePosixPath(row[0]).name in {"INSTALLER", "REQUESTED", "RECORD"}
    ]
    _replace_record(installed, rows)
    _patch_distribution(fingerprint_module, monkeypatch, installed)

    with pytest.raises((TypeError, ValueError)):
        _call(fingerprint_module, "distribution_content_identity", "demo")


def test_distribution_identity_rejects_a_missing_stable_member(
    fingerprint_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    installed, _ = _build_distribution(tmp_path)
    (installed.root / "demo_pkg" / "Z.py").unlink()
    _patch_distribution(fingerprint_module, monkeypatch, installed)

    with pytest.raises((TypeError, ValueError)):
        _call(fingerprint_module, "distribution_content_identity", "demo")


def test_runtime_cli_emits_canonical_normalized_name_order(
    fingerprint_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsysbinary: pytest.CaptureFixture[bytes],
) -> None:
    python_identity = PythonRuntimeIdentity(
        implementation_name="cpython",
        version=(3, 11, 9),
        cache_tag="cpython-311",
        soabi="cp311-win_amd64",
    )
    identities = {
        "Sci_Py": NumericRuntimeIdentity(
            normalized_name="scipy", version="1.17.0", record_content_sha256="b" * 64
        ),
        "Num.Py": NumericRuntimeIdentity(
            normalized_name="numpy", version="2.3.4", record_content_sha256="a" * 64
        ),
    }
    monkeypatch.setattr(
        fingerprint_module, "python_runtime_identity", lambda: python_identity, raising=False
    )
    monkeypatch.setattr(
        fingerprint_module,
        "distribution_content_identity",
        identities.__getitem__,
        raising=False,
    )

    return_code = _call(fingerprint_module, "main", ["runtime-identity", "Sci_Py", "Num.Py"])
    captured = capsysbinary.readouterr()
    expected = (
        rfc8785.dumps(
            [
                python_identity.model_dump(mode="json"),
                [
                    identities["Num.Py"].model_dump(mode="json"),
                    identities["Sci_Py"].model_dump(mode="json"),
                ],
            ]
        )
        + b"\n"
    )

    assert return_code == 0
    assert captured.out == expected
    assert captured.err == b""
    assert b"site-packages" not in captured.out


def test_runtime_cli_rejects_duplicate_normalized_distribution_names(
    fingerprint_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsysbinary: pytest.CaptureFixture[bytes],
) -> None:
    identity = NumericRuntimeIdentity(
        normalized_name="demo-pkg", version="1.0.0", record_content_sha256="a" * 64
    )
    monkeypatch.setattr(
        fingerprint_module,
        "distribution_content_identity",
        lambda _name: identity,
        raising=False,
    )

    return_code = _call(fingerprint_module, "main", ["runtime-identity", "Demo_Pkg", "demo.pkg"])
    captured = capsysbinary.readouterr()

    assert return_code != 0
    assert captured.out == b""
    assert captured.err
