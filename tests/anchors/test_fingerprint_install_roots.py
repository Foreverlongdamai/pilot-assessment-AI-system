from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
from collections.abc import Iterator, Sequence
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import cast

import rfc8785
from pydantic import JsonValue

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
UV = REPOSITORY_ROOT / ".tools" / "uv" / "uv.exe"
RUNTIME_DISTRIBUTIONS = ("numpy", "scipy", "rfc8785")


def _run(
    command: Sequence[str | os.PathLike[str]],
    *,
    cwd: Path,
    environment: dict[str, str] | None = None,
    timeout_seconds: int = 300,
) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(
        [os.fspath(part) for part in command],
        cwd=cwd,
        env=environment,
        capture_output=True,
        check=False,
        timeout=timeout_seconds,
    )
    if completed.returncode != 0:
        raise AssertionError(
            "subprocess failed\n"
            f"command: {completed.args!r}\n"
            f"return code: {completed.returncode}\n"
            f"stdout: {completed.stdout.decode('utf-8', errors='replace')}\n"
            f"stderr: {completed.stderr.decode('utf-8', errors='replace')}"
        )
    return completed


def _venv_python(environment_root: Path) -> Path:
    if os.name == "nt":
        return environment_root / "Scripts" / "python.exe"
    return environment_root / "bin" / "python"


def _locked_runtime_versions() -> dict[str, str]:
    lock = tomllib.loads((REPOSITORY_ROOT / "uv.lock").read_text(encoding="utf-8"))
    versions = {
        package["name"]: package["version"]
        for package in lock["package"]
        if package["name"] in RUNTIME_DISTRIBUTIONS
    }
    assert set(versions) == set(RUNTIME_DISTRIBUTIONS)
    return versions


def _json_strings(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for member in value:
            yield from _json_strings(member)
    elif isinstance(value, dict):
        for member in value.values():
            yield from _json_strings(member)


def _reject_non_json_number(token: str) -> None:
    raise AssertionError(f"non-JSON number in child stdout: {token}")


def _assert_canonical_runtime_output(
    output: bytes,
    *,
    locked_versions: dict[str, str],
) -> None:
    assert output.endswith(b"\n")
    assert not output.endswith(b"\n\n")
    assert b"\n" not in output[:-1]

    payload = json.loads(output[:-1], parse_constant=_reject_non_json_number)
    assert output == rfc8785.dumps(cast(JsonValue, payload)) + b"\n"
    assert isinstance(payload, list) and len(payload) == 2

    python_identity, distribution_identities = payload
    assert isinstance(python_identity, dict)
    assert set(python_identity) == {"implementation_name", "version", "cache_tag", "soabi"}
    assert isinstance(distribution_identities, list)
    assert [identity["normalized_name"] for identity in distribution_identities] == [
        "numpy",
        "rfc8785",
        "scipy",
    ]
    for identity in distribution_identities:
        assert set(identity) == {"normalized_name", "version", "record_content_sha256"}
        assert identity["version"] == locked_versions[identity["normalized_name"]]
        assert re.fullmatch(r"[0-9a-f]{64}", identity["record_content_sha256"])

    for text in _json_strings(payload):
        assert not PureWindowsPath(text).is_absolute()
        assert not PurePosixPath(text).is_absolute()


def _install_locked_wheels_and_run_cli(
    *,
    environment_root: Path,
    child_cwd: Path,
    project_wheel: Path,
    distribution_order: Sequence[str],
) -> bytes:
    sync_environment = os.environ.copy()
    sync_environment.pop("VIRTUAL_ENV", None)
    sync_environment["UV_PROJECT_ENVIRONMENT"] = os.fspath(environment_root)

    # --frozen binds both roots to the same uv.lock; --no-build makes the lock resolve
    # only to wheels, while --no-install-project prevents an editable/source install.
    _run(
        [
            UV,
            "sync",
            "--frozen",
            "--no-dev",
            "--no-install-project",
            "--no-build",
            "--link-mode",
            "copy",
            "--python",
            sys.executable,
            "--project",
            REPOSITORY_ROOT,
        ],
        cwd=REPOSITORY_ROOT,
        environment=sync_environment,
    )
    python = _venv_python(environment_root)
    assert python.is_file()

    # Both roots receive this exact wheel path. Its dependencies are already supplied by
    # the frozen sync, so resolution cannot replace them or import the source checkout.
    _run(
        [
            UV,
            "pip",
            "install",
            "--python",
            python,
            "--no-deps",
            "--no-build",
            "--link-mode",
            "copy",
            project_wheel,
        ],
        cwd=child_cwd,
    )

    child_environment = os.environ.copy()
    child_environment.pop("PYTHONPATH", None)
    child_environment.pop("PYTHONHOME", None)
    child_environment.pop("VIRTUAL_ENV", None)
    child_environment["PYTHONNOUSERSITE"] = "1"
    completed = _run(
        [
            python,
            "-I",
            "-m",
            "pilot_assessment.anchors.fingerprint",
            "runtime-identity",
            *distribution_order,
        ],
        cwd=child_cwd,
        environment=child_environment,
    )
    assert completed.stderr == b""
    return completed.stdout


def test_runtime_identity_is_install_root_independent(tmp_path: Path) -> None:
    assert UV.is_file()
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()

    # The project wheel is deliberately built exactly once and then reused by both roots.
    _run(
        [
            UV,
            "build",
            "--wheel",
            "--out-dir",
            wheelhouse,
            "--no-create-gitignore",
            REPOSITORY_ROOT,
        ],
        cwd=REPOSITORY_ROOT,
    )
    project_wheels = list(wheelhouse.glob("pilot_assessment_system-*.whl"))
    assert len(project_wheels) == 1
    project_wheel = project_wheels[0]

    environment_a = tmp_path / "install-root-a"
    environment_b = tmp_path / "install-root-b"
    child_cwd_a = tmp_path / "child-cwd-a"
    child_cwd_b = tmp_path / "child-cwd-b"
    child_cwd_a.mkdir()
    child_cwd_b.mkdir()
    assert environment_a.resolve() != environment_b.resolve()
    assert not child_cwd_a.resolve().is_relative_to(REPOSITORY_ROOT.resolve())
    assert not child_cwd_b.resolve().is_relative_to(REPOSITORY_ROOT.resolve())

    output_a = _install_locked_wheels_and_run_cli(
        environment_root=environment_a,
        child_cwd=child_cwd_a,
        project_wheel=project_wheel,
        distribution_order=RUNTIME_DISTRIBUTIONS,
    )
    output_b = _install_locked_wheels_and_run_cli(
        environment_root=environment_b,
        child_cwd=child_cwd_b,
        project_wheel=project_wheel,
        distribution_order=tuple(reversed(RUNTIME_DISTRIBUTIONS)),
    )

    locked_versions = _locked_runtime_versions()
    _assert_canonical_runtime_output(output_a, locked_versions=locked_versions)
    _assert_canonical_runtime_output(output_b, locked_versions=locked_versions)
    assert output_a == output_b

    forbidden_roots = (
        REPOSITORY_ROOT,
        environment_a,
        environment_b,
        child_cwd_a,
        child_cwd_b,
        project_wheel,
    )
    decoded_output = output_a.decode("utf-8")
    for root in forbidden_roots:
        assert os.fspath(root) not in decoded_output
