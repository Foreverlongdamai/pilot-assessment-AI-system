"""Build the tagged Windows x64 Pilot Assessment v0.1.0-rc.1 candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tomllib
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from email.parser import Parser
from pathlib import Path
from typing import Any

from system_model_capture import (
    SYSTEM_EDIT_DATABASE,
    SYSTEM_LOCK_NAME,
    USER_OWNED_SYSTEM_TABLES,
    SystemCaptureError,
    SystemCaptureReport,
    capture_current_system,
    model_identity,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DESKTOP_PROJECT = (
    REPOSITORY_ROOT / "src" / "PilotAssessment.Desktop" / ("PilotAssessment.Desktop.csproj")
)
UV = REPOSITORY_ROOT / ".tools" / "uv" / "uv.exe"
WORK_ROOT = REPOSITORY_ROOT / "build" / "portable-release"
CACHE_ROOT = REPOSITORY_ROOT / "build" / "release-cache"
DEFAULT_OUTPUT_ROOT = REPOSITORY_ROOT / "dist" / "releases"
DOCUMENTATION_TOOL_ROOT = REPOSITORY_ROOT / "tools" / "documentation"
DOCUMENTATION_SOURCE_ROOT = REPOSITORY_ROOT / "docs" / "product" / "manuals"
RELEASE_SOURCE_ROOT = REPOSITORY_ROOT / "docs" / "product" / "release"

PYTHON_VERSION = "3.11.9"
PYTHON_EMBED_URL = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"
PYTHON_EMBED_SHA256 = "009d6bf7e3b2ddca3d784fa09f90fe54336d5b60f0e0f305c37f400bf83cfd3b"
COPY_EXCLUDED_DIRECTORIES = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".ty",
    ".venv",
    "__pycache__",
    "bin",
    "obj",
}
COPY_EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".pdb", ".tmp", ".log"}


@dataclass(frozen=True)
class ReleaseIdentity:
    """Explicit identity of the M8E release candidate being built."""

    product_version: str
    release_label: str
    release_channel: str
    candidate: str
    user_acceptance: str
    documentation_status: str

    @property
    def package_name(self) -> str:
        return f"PilotAssessment-{self.product_version}-{self.candidate}-win-x64"


class ReleaseBuildError(RuntimeError):
    """Raised when a portable release invariant is not satisfied."""


def _internal_verification_root(*, work_root: Path, identity: ReleaseIdentity) -> Path:
    """Keep the disposable copy's root name identical to the candidate package."""

    return work_root / identity.package_name


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Directory that receives the product folder and ZIP.",
    )
    parser.add_argument(
        "--skip-archive",
        action="store_true",
        help="Engineering-only switch; the M8E release candidate rejects it.",
    )
    parser.add_argument(
        "--system-source",
        type=Path,
        required=True,
        help="Saved and closed system directory to capture into this release.",
    )
    parser.add_argument("--release-label", required=True)
    parser.add_argument(
        "--release-channel",
        required=True,
        choices=("release-candidate",),
    )
    parser.add_argument("--candidate", required=True)
    parser.add_argument(
        "--user-acceptance",
        required=True,
        choices=("pending",),
    )
    parser.add_argument(
        "--documentation-status",
        required=True,
        choices=("released",),
    )
    return parser.parse_args()


def _release_identity(
    *,
    product_version: str,
    release_label: str,
    release_channel: str,
    candidate: str,
    user_acceptance: str,
    documentation_status: str,
    skip_archive: bool,
) -> ReleaseIdentity:
    expected_label = f"v{product_version}-{candidate}"
    if product_version != "0.1.0":
        raise ReleaseBuildError(
            f"M8E rc.1 requires base product version 0.1.0, got {product_version}"
        )
    if release_channel != "release-candidate":
        raise ReleaseBuildError("M8E rc.1 requires release-channel=release-candidate")
    if candidate != "rc.1":
        raise ReleaseBuildError(f"M8E first acceptance candidate must be rc.1, got {candidate}")
    if release_label != expected_label:
        raise ReleaseBuildError(
            f"release label must match product/candidate identity: expected {expected_label}"
        )
    if user_acceptance != "pending":
        raise ReleaseBuildError("release candidate must retain user-acceptance=pending")
    if documentation_status != "released":
        raise ReleaseBuildError("release candidate requires 24 released documentation outputs")
    if skip_archive:
        raise ReleaseBuildError("release candidate cannot be built with --skip-archive")
    return ReleaseIdentity(
        product_version=product_version,
        release_label=release_label,
        release_channel=release_channel,
        candidate=candidate,
        user_acceptance=user_acceptance,
        documentation_status=documentation_status,
    )


def _run(
    command: list[str],
    *,
    cwd: Path = REPOSITORY_ROOT,
    echo_output: bool = True,
) -> str:
    print("+", subprocess.list2cmdline(command), flush=True)
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed.stdout and echo_output:
        print(completed.stdout.rstrip(), flush=True)
    if completed.returncode != 0:
        raise ReleaseBuildError(
            f"command failed with exit code {completed.returncode}: {command[0]}"
        )
    return completed.stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _assert_child(path: Path, parent: Path) -> Path:
    resolved_path = path.resolve()
    resolved_parent = parent.resolve()
    if resolved_path == resolved_parent or not resolved_path.is_relative_to(resolved_parent):
        raise ReleaseBuildError(
            f"refusing to mutate path outside {resolved_parent}: {resolved_path}"
        )
    return resolved_path


def _remove_tree(path: Path, parent: Path) -> None:
    resolved = _assert_child(path, parent)
    if resolved.exists():
        shutil.rmtree(resolved)


def _require_external_system_source(system_source: Path, package_root: Path) -> Path:
    """Prevent output cleanup or staging from touching the selected source system."""

    source = system_source.expanduser().resolve()
    package = package_root.resolve()
    if source == package or source.is_relative_to(package):
        raise ReleaseBuildError(
            "system source is inside the package output that the builder recreates"
        )
    if package.is_relative_to(source):
        raise ReleaseBuildError("package output cannot be created inside the system source")
    return source


def _unlink(path: Path, parent: Path) -> None:
    resolved = _assert_child(path, parent)
    if resolved.exists():
        resolved.unlink()


def _copy_ignore(_directory: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        if name in COPY_EXCLUDED_DIRECTORIES or Path(name).suffix.lower() in (
            COPY_EXCLUDED_SUFFIXES
        ):
            ignored.add(name)
    return ignored


def _copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise ReleaseBuildError(f"source directory is missing: {source}")
    shutil.copytree(source, destination, ignore=_copy_ignore, dirs_exist_ok=True)


def _read_product_version() -> str:
    with (REPOSITORY_ROOT / "pyproject.toml").open("rb") as stream:
        value = tomllib.load(stream)["project"]["version"]
    if not isinstance(value, str) or not value:
        raise ReleaseBuildError("pyproject project.version must be a non-empty string")
    return value


def _generate_documentation(product_version: str, documentation_status: str) -> Path:
    """Build the explicitly selected manual set before staging the package."""

    _run(
        [
            str(UV),
            "run",
            "--project",
            str(DOCUMENTATION_TOOL_ROOT),
            "--frozen",
            "python",
            str(DOCUMENTATION_TOOL_ROOT / "build_manuals.py"),
            "--status",
            documentation_status,
        ],
        echo_output=False,
    )
    documentation_root = (
        REPOSITORY_ROOT / "dist" / "documentation" / f"PilotAssessment-{product_version}-docs"
    )
    manifest_path = documentation_root / "documentation-manifest.json"
    catalog_path = documentation_root / "source-catalog.json"
    if not manifest_path.is_file() or not catalog_path.is_file():
        raise ReleaseBuildError("documentation build did not produce its manifest and catalog")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    if manifest.get("product_version") != product_version:
        raise ReleaseBuildError("documentation manifest product version differs from the product")
    if catalog.get("product_version") != product_version:
        raise ReleaseBuildError("documentation catalog product version differs from the product")
    if manifest.get("build_status") != documentation_status:
        raise ReleaseBuildError(
            "documentation build status differs from the requested release identity"
        )
    outputs = manifest.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise ReleaseBuildError("documentation build produced no review/released manuals")
    return documentation_root


def _download_python_embed() -> Path:
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    archive = CACHE_ROOT / f"python-{PYTHON_VERSION}-embed-amd64.zip"
    if archive.exists() and _sha256(archive) != PYTHON_EMBED_SHA256:
        _unlink(archive, CACHE_ROOT)
    if not archive.exists():
        print(f"Downloading {PYTHON_EMBED_URL}", flush=True)
        request = urllib.request.Request(
            PYTHON_EMBED_URL,
            headers={"User-Agent": "PilotAssessment-M8E-Builder/0.1"},
        )
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
            archive.write_bytes(response.read())
    actual = _sha256(archive)
    if actual != PYTHON_EMBED_SHA256:
        raise ReleaseBuildError(
            f"CPython embedded ZIP hash mismatch: expected {PYTHON_EMBED_SHA256}, got {actual}"
        )
    return archive


def _extract_zip(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    destination_root = destination.resolve()
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            output = (destination / member.filename).resolve()
            if not output.is_relative_to(destination_root):
                raise ReleaseBuildError(f"unsafe ZIP entry: {member.filename}")
        package.extractall(destination)


def _publish_desktop(publish_root: Path) -> None:
    _run(
        [
            "dotnet",
            "publish",
            str(DESKTOP_PROJECT),
            "--configuration",
            "Release",
            "--runtime",
            "win-x64",
            "--self-contained",
            "true",
            "--output",
            str(publish_root),
            "-p:Platform=x64",
            "-p:WindowsPackageType=None",
            "-p:WindowsAppSDKSelfContained=true",
            "-p:PublishSingleFile=false",
            "-p:PublishTrimmed=false",
            "-p:PublishReadyToRun=true",
            "-p:DebugType=None",
            "-p:DebugSymbols=false",
            "--nologo",
        ]
    )
    executable = publish_root / "PilotAssessment.Desktop.exe"
    if not executable.is_file():
        raise ReleaseBuildError(f"desktop publish did not produce {executable.name}")


def _install_python_runtime(package_root: Path, requirements: Path) -> None:
    runtime = package_root / "runtime"
    python_root = runtime / "python"
    site_packages = runtime / "site-packages"
    _extract_zip(_download_python_embed(), python_root)
    site_packages.mkdir(parents=True, exist_ok=True)

    pth = python_root / "python311._pth"
    pth.write_text(
        "python311.zip\n.\n../site-packages\n../../backend/src\nimport site\n",
        encoding="utf-8",
        newline="\n",
    )

    _run(
        [
            str(UV),
            "export",
            "--frozen",
            "--no-dev",
            "--no-emit-project",
            "--format",
            "requirements.txt",
            "--output-file",
            str(requirements),
        ],
        echo_output=False,
    )
    _run(
        [
            str(UV),
            "pip",
            "install",
            "--target",
            str(site_packages),
            "--python-version",
            "3.11",
            "--python-platform",
            "x86_64-pc-windows-msvc",
            "--require-hashes",
            "--requirements",
            str(requirements),
        ]
    )

    for bytecode in site_packages.rglob("*.py[co]"):
        bytecode.unlink()
    pycache_directories = sorted(
        (path for path in site_packages.rglob("__pycache__") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for pycache in pycache_directories:
        _remove_tree(pycache, site_packages)

    hidden_first_party = [
        path
        for path in site_packages.iterdir()
        if path.name.lower().replace("-", "_").startswith("pilot_assessment")
    ]
    if hidden_first_party:
        names = ", ".join(path.name for path in hidden_first_party)
        raise ReleaseBuildError(f"private site-packages contains first-party copy: {names}")


def _copy_documentation(documentation_root: Path, docs_root: Path) -> None:
    manifest_path = documentation_root / "documentation-manifest.json"
    catalog_path = documentation_root / "source-catalog.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    outputs = manifest.get("outputs")
    if not isinstance(outputs, list):
        raise ReleaseBuildError("documentation manifest outputs must be an array")

    shutil.copy2(manifest_path, docs_root / manifest_path.name)
    shutil.copy2(catalog_path, docs_root / catalog_path.name)
    review_count = 0
    for item in outputs:
        if not isinstance(item, dict):
            raise ReleaseBuildError("documentation manifest output must be an object")
        status = item.get("status")
        if status not in {"review", "released"}:
            raise ReleaseBuildError(f"documentation output has invalid package status: {status!r}")
        relative = Path(str(item.get("output", "")))
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            raise ReleaseBuildError(f"documentation output path is unsafe: {relative}")
        source = (documentation_root / relative).resolve()
        if not source.is_relative_to(documentation_root.resolve()) or not source.is_file():
            raise ReleaseBuildError(f"generated documentation output is missing: {relative}")
        destination_root = docs_root if status == "released" else docs_root / "review"
        destination = destination_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if status == "review":
            review_count += 1

    if review_count:
        review_readme = docs_root / "review" / "README.txt"
        review_readme.parent.mkdir(parents=True, exist_ok=True)
        review_readme.write_text(
            "These DOCX files are generated review-status engineering manuals.\n"
            "They are included for M8C-0 evaluation and are not M8E released manuals.\n",
            encoding="utf-8",
            newline="\n",
        )


def _copy_product_sources(package_root: Path, documentation_root: Path) -> None:
    backend = package_root / "backend"
    _copy_tree(
        REPOSITORY_ROOT / "src" / "pilot_assessment",
        backend / "src" / "pilot_assessment",
    )
    for name in ("pyproject.toml", "uv.lock", ".python-version"):
        shutil.copy2(REPOSITORY_ROOT / name, backend / name)
    shutil.copy2(
        REPOSITORY_ROOT / "docs" / "product" / "release" / "README-DEVELOPMENT.md",
        backend / "README-DEVELOPMENT.md",
    )

    desktop_source = package_root / "developer" / "desktop-source"
    _copy_tree(
        REPOSITORY_ROOT / "src" / "PilotAssessment.Desktop",
        desktop_source / "PilotAssessment.Desktop",
    )
    _copy_tree(
        REPOSITORY_ROOT / "src" / "PilotAssessment.Desktop.Core",
        desktop_source / "PilotAssessment.Desktop.Core",
    )
    _copy_tree(
        REPOSITORY_ROOT / "tools" / "release",
        package_root / "developer" / "build" / "release",
    )
    developer_tools = package_root / "developer" / "tools"
    developer_tools.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        REPOSITORY_ROOT / "tools" / "developer" / "manage_python_dependencies.ps1",
        developer_tools / "manage_python_dependencies.ps1",
    )
    shutil.copy2(UV, developer_tools / "uv.exe")
    _copy_tree(
        REPOSITORY_ROOT / "developer" / "examples" / "operator-extension",
        package_root / "developer" / "examples" / "operator-extension",
    )

    docs_root = package_root / "docs"
    docs_root.mkdir(parents=True, exist_ok=True)
    for name in ("README-PORTABLE.md", "KNOWN-LIMITATIONS.md"):
        shutil.copy2(RELEASE_SOURCE_ROOT / name, docs_root / name)
    _copy_documentation(documentation_root, docs_root)
    _copy_tree(
        DOCUMENTATION_SOURCE_ROOT / "assets" / "screenshots",
        docs_root / "assets" / "screenshots",
    )
    handoff_files = {
        "README-CANDIDATE.md": "README-CANDIDATE.md",
        "RELEASE-NOTES-v0.1.0-rc.1.md": "RELEASE-NOTES.md",
        "ACCEPTANCE-CHECKLIST-v0.1.0-rc.1.md": "ACCEPTANCE-CHECKLIST.md",
        "KNOWN-LIMITATIONS.md": "KNOWN-LIMITATIONS.md",
    }
    for source_name, destination_name in handoff_files.items():
        shutil.copy2(RELEASE_SOURCE_ROOT / source_name, package_root / destination_name)
    shutil.copy2(package_root / "README-CANDIDATE.md", package_root / "README.txt")


def _initialize_captured_system(
    package_root: Path,
    *,
    product_version: str,
    built_at: str,
    capture_report: SystemCaptureReport,
) -> None:
    """Rebuild one clean edit workspace around the captured canonical model."""

    python = package_root / "runtime" / "python" / "python.exe"
    system_root = package_root / "system"
    program = """
import json
import sys
from datetime import datetime
from pilot_assessment.runtime import SystemApplication

stamp = datetime.fromisoformat(sys.argv[2].replace("Z", "+00:00"))
application = SystemApplication.open_or_create(
    sys.argv[1],
    clock=lambda: stamp,
    product_version=sys.argv[3],
)
try:
    status = application.model_edits.status()
    print(json.dumps({
        "model_library_id": application.model_library_id,
        "node_count": len(application.current_model.list_nodes()),
        "scheme_count": len(application.current_model.list_schemes()),
        "edit_session_dirty": status.dirty,
        "cursor": status.cursor,
        "latest_sequence": status.latest_sequence,
    }))
finally:
    application.close()
"""
    output = _run(
        [
            str(python),
            "-I",
            "-B",
            "-X",
            "utf8",
            "-c",
            program,
            str(system_root),
            built_at,
            product_version,
        ],
        cwd=package_root,
        echo_output=False,
    )
    initialized = json.loads(output)
    expected = {
        "model_library_id": capture_report.model_library_id,
        "node_count": capture_report.node_count,
        "scheme_count": capture_report.scheme_count,
        "edit_session_dirty": False,
        "cursor": 0,
        "latest_sequence": 0,
    }
    if initialized != expected:
        raise ReleaseBuildError(
            "captured system initialization changed model facts: "
            f"expected={expected}, actual={initialized}"
        )
    lock_path = system_root / SYSTEM_LOCK_NAME
    if lock_path.exists():
        lock_path.unlink()
    transient = tuple(system_root.rglob("*.sqlite3-wal")) + tuple(
        system_root.rglob("*.sqlite3-shm")
    )
    if transient:
        raise ReleaseBuildError(f"captured system has transient SQLite files: {transient}")


def _system_model_baseline(
    package_root: Path,
    *,
    capture_report: SystemCaptureReport,
) -> dict[str, Any]:
    system_root = package_root / "system"
    canonical_path = system_root / "model-library.sqlite3"
    edit_path = system_root / SYSTEM_EDIT_DATABASE
    locator_path = system_root / "system.json"
    if not all(path.is_file() for path in (canonical_path, edit_path, locator_path)):
        raise ReleaseBuildError("captured system store is incomplete")

    locator = json.loads(locator_path.read_text(encoding="utf-8"))
    canonical = sqlite3.connect(canonical_path)
    edit = sqlite3.connect(edit_path)
    try:
        current_identity, node_count, scheme_count = model_identity(canonical)
        metadata = canonical.execute(
            """
            SELECT model_library_id, format_version, starter_seed_id,
                   starter_seed_hash, clean_shutdown
            FROM system_metadata WHERE singleton = 1
            """
        ).fetchone()
        if metadata is None:
            raise ReleaseBuildError("captured system metadata is missing")
        state = edit.execute(
            """
            SELECT model_library_id, base_fingerprint, baseline_state_hash,
                   cursor, latest_sequence
            FROM model_edit_session_state WHERE singleton = 1
            """
        ).fetchone()
        if state is None:
            raise ReleaseBuildError("captured model edit-session state is missing")
        user_counts = {
            table: int(canonical.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in USER_OWNED_SYSTEM_TABLES
        }
        database_schema_version = int(
            canonical.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        )
        system_schema_version = int(
            canonical.execute("SELECT MAX(version) FROM system_schema_migrations").fetchone()[0]
        )
    finally:
        canonical.close()
        edit.close()

    model_library_id = str(metadata[0])
    if locator.get("model_library_id") != model_library_id:
        raise ReleaseBuildError("captured locator and database model-library identities differ")
    if (
        model_library_id != capture_report.model_library_id
        or str(metadata[1]) != capture_report.system_format_version
        or str(metadata[2]) != capture_report.starter_seed_id
        or str(metadata[3]) != capture_report.starter_seed_hash
        or int(metadata[4]) != 1
    ):
        raise ReleaseBuildError("captured system identity or clean-shutdown state is invalid")
    if str(state[0]) != model_library_id or int(state[3]) != 0 or int(state[4]) != 0:
        raise ReleaseBuildError("captured system edit workspace is not clean")
    if (
        str(state[1]) != capture_report.base_fingerprint
        or str(state[2]) != capture_report.baseline_state_hash
    ):
        raise ReleaseBuildError("captured edit baseline differs from the selected source")
    if any(user_counts.values()):
        raise ReleaseBuildError(f"captured system contains user-owned data: {user_counts}")
    if (
        current_identity != capture_report.model_identity_sha256
        or node_count != capture_report.node_count
        or scheme_count != capture_report.scheme_count
    ):
        raise ReleaseBuildError("captured system model facts differ from the selected source")
    if (
        database_schema_version != capture_report.database_schema_version
        or system_schema_version != capture_report.system_schema_version
    ):
        raise ReleaseBuildError("captured system schema facts differ from the selected source")
    if _sha256(locator_path) != capture_report.source_locator_sha256:
        raise ReleaseBuildError("captured system locator differs from the selected source")

    return {
        "schema_version": "pilot-assessment-system-model-baseline-v2",
        "capture_mode": "explicit-current-system",
        "model_library_id": model_library_id,
        "system_format_version": str(metadata[1]),
        "database_schema_version": database_schema_version,
        "system_schema_version": system_schema_version,
        "starter_lineage": {
            "starter_seed_id": str(metadata[2]),
            "starter_seed_hash": str(metadata[3]),
        },
        "model_identity_sha256": current_identity,
        "node_count": node_count,
        "scheme_count": scheme_count,
        "capture_source": {
            "locator_sha256": capture_report.source_locator_sha256,
            "canonical_database_sha256": capture_report.source_canonical_sha256,
        },
        "canonical_database": {
            "path": canonical_path.relative_to(package_root).as_posix(),
            "sha256": _sha256(canonical_path),
        },
        "edit_workspace": {
            "path": edit_path.relative_to(package_root).as_posix(),
            "sha256": _sha256(edit_path),
            "base_fingerprint": str(state[1]),
            "baseline_state_hash": str(state[2]),
            "cursor": int(state[3]),
            "latest_sequence": int(state[4]),
            "dirty": False,
        },
        "user_owned_row_counts": user_counts,
    }


def _installed_python_packages(site_packages: Path) -> list[dict[str, str]]:
    packages: list[dict[str, str]] = []
    for dist_info in sorted(site_packages.glob("*.dist-info"), key=lambda path: path.name.lower()):
        metadata_path = dist_info / "METADATA"
        if not metadata_path.is_file():
            continue
        metadata = Parser().parsestr(metadata_path.read_text(encoding="utf-8", errors="replace"))
        name = metadata.get("Name")
        version = metadata.get("Version")
        if name and version:
            packages.append({"name": name, "version": version})
    return packages


def _collect_licenses(package_root: Path) -> list[str]:
    licenses = package_root / "licenses"
    wheel_licenses = licenses / "python-packages"
    wheel_licenses.mkdir(parents=True, exist_ok=True)
    python_license = package_root / "runtime" / "python" / "LICENSE.txt"
    if not python_license.is_file():
        raise ReleaseBuildError("embedded Python LICENSE.txt is missing")
    shutil.copy2(python_license, licenses / f"python-{PYTHON_VERSION}.txt")
    shutil.copy2(
        REPOSITORY_ROOT / "docs" / "product" / "release" / "THIRD-PARTY-NOTICES.md",
        licenses / "THIRD-PARTY-NOTICES.md",
    )

    copied: list[str] = []
    site_packages = package_root / "runtime" / "site-packages"
    for dist_info in sorted(site_packages.glob("*.dist-info"), key=lambda path: path.name.lower()):
        candidates: list[Path] = []
        license_directory = dist_info / "licenses"
        if license_directory.is_dir():
            candidates.extend(path for path in license_directory.rglob("*") if path.is_file())
        candidates.extend(
            path
            for path in dist_info.iterdir()
            if path.is_file() and path.name.lower().startswith(("license", "copying", "notice"))
        )
        for index, source in enumerate(sorted(set(candidates))):
            safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", source.name)
            destination = wheel_licenses / f"{dist_info.name}--{index:02d}--{safe_name}"
            shutil.copy2(source, destination)
            copied.append(destination.relative_to(package_root).as_posix())
    return copied


def _validate_candidate_git_state(
    *,
    release_label: str,
    commit: str,
    status: str,
    tag_type: str,
    peeled_commit: str,
) -> dict[str, Any]:
    if status.strip():
        raise ReleaseBuildError("release candidate source worktree must be clean")
    if tag_type.strip() != "tag":
        raise ReleaseBuildError(f"{release_label} must be an annotated Git tag")
    if peeled_commit.strip() != commit.strip():
        raise ReleaseBuildError(f"{release_label} does not peel to the current HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", commit.strip()):
        raise ReleaseBuildError("release candidate Git commit is not a full SHA-1 identity")
    return {
        "commit": commit.strip(),
        "dirty": False,
        "tag": release_label,
        "tag_type": "annotated",
        "tag_peels_to_head": True,
    }


def _git_state(release_label: str) -> dict[str, Any]:
    commit = _run(["git", "rev-parse", "HEAD"]).splitlines()[-1]
    status = _run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        echo_output=False,
    )
    tag_type = _run(["git", "cat-file", "-t", release_label], echo_output=False)
    peeled_commit = _run(
        ["git", "rev-parse", f"{release_label}^{{}}"],
        echo_output=False,
    )
    return _validate_candidate_git_state(
        release_label=release_label,
        commit=commit,
        status=status,
        tag_type=tag_type,
        peeled_commit=peeled_commit,
    )


def _dotnet_packages(package_root: Path) -> list[dict[str, str]]:
    deps_path = package_root / "PilotAssessment.Desktop.deps.json"
    if not deps_path.is_file():
        return []
    payload = json.loads(deps_path.read_text(encoding="utf-8"))
    packages: list[dict[str, str]] = []
    for identity, details in payload.get("libraries", {}).items():
        if details.get("type") != "package" or "/" not in identity:
            continue
        name, version = identity.rsplit("/", 1)
        packages.append({"name": name, "version": version})
    return sorted(packages, key=lambda item: (item["name"].lower(), item["version"]))


def _spdx_id(kind: str, name: str, version: str) -> str:
    token = hashlib.sha1(f"{kind}:{name}:{version}".encode()).hexdigest()[:16]  # noqa: S324
    return f"SPDXRef-{kind}-{token}"


def _write_sbom(
    package_root: Path,
    *,
    identity: ReleaseIdentity,
    built_at: str,
    python_packages: list[dict[str, str]],
) -> None:
    first_party = {
        "name": "pilot-assessment-system",
        "version": identity.product_version,
        "kind": "Product",
    }
    components = [
        first_party,
        {"name": "CPython", "version": PYTHON_VERSION, "kind": "Runtime"},
        *({**item, "kind": "PythonPackage"} for item in python_packages),
        *({**item, "kind": "DotNetPackage"} for item in _dotnet_packages(package_root)),
    ]
    spdx_packages = []
    relationships = []
    for component in components:
        identifier = _spdx_id(component["kind"], component["name"], component["version"])
        spdx_packages.append(
            {
                "SPDXID": identifier,
                "name": component["name"],
                "versionInfo": component["version"],
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": False,
                "licenseConcluded": "NOASSERTION",
                "licenseDeclared": "NOASSERTION",
                "copyrightText": "NOASSERTION",
                "comment": component["kind"],
            }
        )
        relationships.append(
            {
                "spdxElementId": "SPDXRef-DOCUMENT",
                "relationshipType": "DESCRIBES",
                "relatedSpdxElement": identifier,
            }
        )
    namespace_token = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"pilot-assessment:{identity.release_label}:{built_at}",
    )
    payload = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": identity.package_name,
        "documentNamespace": f"https://pilot-assessment.local/spdx/{namespace_token}",
        "creationInfo": {
            "created": built_at,
            "creators": ["Tool: PilotAssessment-M8E-Builder-0.1"],
        },
        "packages": spdx_packages,
        "relationships": relationships,
    }
    _write_json(package_root / "manifest" / "sbom.spdx.json", payload)


def _source_baseline(package_root: Path) -> dict[str, Any]:
    source_root = package_root / "backend" / "src" / "pilot_assessment"
    candidates = [path for path in source_root.rglob("*") if path.is_file()]
    candidates.sort(key=lambda path: path.relative_to(source_root).as_posix().casefold())
    files: list[dict[str, Any]] = []
    aggregate = hashlib.sha256()
    aggregate.update(b"pilot-assessment-source-tree-v2\0")
    seen: set[str] = set()
    for path in candidates:
        relative = path.relative_to(source_root).as_posix().casefold()
        if relative in seen:
            raise ReleaseBuildError(f"case-insensitive source path collision: {relative}")
        seen.add(relative)
        payload = path.read_bytes()
        path_bytes = relative.encode("utf-8")
        aggregate.update(len(path_bytes).to_bytes(8, "big"))
        aggregate.update(path_bytes)
        aggregate.update(len(payload).to_bytes(8, "big"))
        aggregate.update(payload)
        files.append(
            {
                "path": f"backend/src/pilot_assessment/{relative}",
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            }
        )
    return {
        "schema_version": "pilot-assessment-source-baseline-v2",
        "active_source_root": "backend/src/pilot_assessment",
        "policy": "single-active-first-party-python-tree",
        "tree_algorithm": "pilot-assessment-source-tree-v2",
        "tree_sha256": aggregate.hexdigest(),
        "aggregate_sha256": aggregate.hexdigest(),
        "file_count": len(files),
        "files": files,
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_checksums(package_root: Path) -> int:
    checksum_path = package_root / "manifest" / "checksums.sha256"
    files = [
        path for path in sorted(package_root.rglob("*")) if path.is_file() and path != checksum_path
    ]
    checksum_path.write_text(
        "".join(
            f"{_sha256(path)}  {path.relative_to(package_root).as_posix()}\n" for path in files
        ),
        encoding="utf-8",
        newline="\n",
    )
    return len(files)


def _documentation_release_summary(package_root: Path) -> dict[str, Any]:
    docs_root = package_root / "docs"
    manifest_path = docs_root / "documentation-manifest.json"
    catalog_path = docs_root / "source-catalog.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    outputs = manifest.get("outputs")
    if not isinstance(outputs, list):
        raise ReleaseBuildError("documentation manifest outputs must be an array")
    statuses = [str(item.get("status")) for item in outputs if isinstance(item, dict)]
    if len(statuses) != len(outputs):
        raise ReleaseBuildError("documentation manifest contains a non-object output")
    screenshot_manifest_path = docs_root / "assets" / "screenshots" / "manifest.json"
    screenshot_manifest = json.loads(screenshot_manifest_path.read_text(encoding="utf-8"))
    screenshots = screenshot_manifest.get("screenshots")
    if not isinstance(screenshots, list) or len(screenshots) != 10:
        raise ReleaseBuildError("release candidate must contain ten registered screenshots")
    return {
        "build_status": manifest.get("build_status"),
        "manifest": "docs/documentation-manifest.json",
        "manifest_sha256": _sha256(manifest_path),
        "catalog": "docs/source-catalog.json",
        "catalog_sha256": _sha256(catalog_path),
        "generated_output_count": len(outputs),
        "released_output_count": statuses.count("released"),
        "review_output_count": statuses.count("review"),
        "screenshot_manifest": "docs/assets/screenshots/manifest.json",
        "screenshot_manifest_sha256": _sha256(screenshot_manifest_path),
        "candidate_screenshot_count": len(screenshots),
    }


def _write_manifests(
    package_root: Path,
    *,
    identity: ReleaseIdentity,
    git_state: dict[str, Any],
    license_files: list[str],
    built_at: str,
    capture_report: SystemCaptureReport,
) -> None:
    manifest_root = package_root / "manifest"
    manifest_root.mkdir(parents=True, exist_ok=True)
    python_packages = _installed_python_packages(package_root / "runtime" / "site-packages")
    source_baseline = _source_baseline(package_root)
    _write_json(manifest_root / "source-baseline.json", source_baseline)
    system_model_baseline = _system_model_baseline(
        package_root,
        capture_report=capture_report,
    )
    system_model_baseline_path = manifest_root / "system-model-baseline.json"
    _write_json(system_model_baseline_path, system_model_baseline)
    _write_sbom(
        package_root,
        identity=identity,
        built_at=built_at,
        python_packages=python_packages,
    )

    dotnet_version = _run(["dotnet", "--version"]).splitlines()[-1]
    uv_version = _run([str(UV), "--version"]).splitlines()[-1]
    payload: dict[str, Any] = {
        "schema_version": "pilot-assessment-release-manifest-v2",
        "product": "Pilot Assessment System",
        "product_version": identity.product_version,
        "release_channel": identity.release_channel,
        "release_label": identity.release_label,
        "candidate": identity.candidate,
        "user_acceptance": identity.user_acceptance,
        "documentation_status": identity.documentation_status,
        "build_kind": "m8e-release-candidate",
        "built_at_utc": built_at,
        "target": {
            "operating_system": "windows",
            "architecture": "x64",
            "runtime_identifier": "win-x64",
            "distribution": "unpackaged-self-contained-directory",
        },
        "entrypoint": "PilotAssessment.Desktop.exe",
        "backend": {
            "launch": ("runtime/python/python.exe -I -B -u -X utf8 -m pilot_assessment.sidecar"),
            "active_source_root": "backend/src/pilot_assessment",
            "source_policy": "single-active-first-party-python-tree",
            "project_wheel_installed": False,
            "extension_registration": (
                "backend/src/pilot_assessment/evidence/extensions/__init__.py"
            ),
            "dependency_tool": "developer/tools/manage_python_dependencies.ps1",
        },
        "toolchain": {
            "dotnet_sdk": dotnet_version,
            "windows_app_sdk": "2.3.1",
            "python_embedded": PYTHON_VERSION,
            "python_embedded_sha256": PYTHON_EMBED_SHA256,
            "uv": uv_version,
        },
        "git": git_state,
        "python_packages": python_packages,
        "documentation": _documentation_release_summary(package_root),
        "source_baseline_sha256": source_baseline["aggregate_sha256"],
        "system_model_baseline_sha256": _sha256(system_model_baseline_path),
        "system_model": {
            "baseline": "manifest/system-model-baseline.json",
            "capture_mode": system_model_baseline["capture_mode"],
            "model_library_id": system_model_baseline["model_library_id"],
            "model_identity_sha256": system_model_baseline["model_identity_sha256"],
            "node_count": system_model_baseline["node_count"],
            "scheme_count": system_model_baseline["scheme_count"],
        },
        "license_files_collected": license_files,
        "content_policy": {
            "user_projects_included": False,
            "session_data_included": False,
            "result_artifacts_included": False,
            "synthetic_demo_data_included": False,
        },
        "scientific_status": {
            "formal_run_authorized": False,
            "starter_content": "engineering-defaults-require-expert-calibration",
        },
    }
    _write_json(manifest_root / "release-manifest.json", payload)
    payload["checksummed_file_count"] = _write_checksums(package_root)
    _write_json(manifest_root / "release-manifest.json", payload)
    _write_checksums(package_root)


def _write_delivery_manifest(
    delivery_path: Path,
    *,
    package_root: Path,
    archive_path: Path,
    archive_sha256: str,
) -> dict[str, Any]:
    release_manifest_path = package_root / "manifest" / "release-manifest.json"
    sbom_path = package_root / "manifest" / "sbom.spdx.json"
    release_manifest = json.loads(release_manifest_path.read_text(encoding="utf-8"))
    payload = {
        "schema_version": "pilot-assessment-delivery-v1",
        "product": release_manifest["product"],
        "product_version": release_manifest["product_version"],
        "release_channel": release_manifest["release_channel"],
        "release_label": release_manifest["release_label"],
        "candidate": release_manifest["candidate"],
        "user_acceptance": release_manifest["user_acceptance"],
        "build_kind": release_manifest["build_kind"],
        "archive": {
            "file": archive_path.name,
            "bytes": archive_path.stat().st_size,
            "sha256": archive_sha256,
            "sha256_file": f"{archive_path.name}.sha256",
        },
        "git": release_manifest["git"],
        "system_model": release_manifest["system_model"],
        "documentation": release_manifest["documentation"],
        "manifests": {
            "release_manifest": "manifest/release-manifest.json",
            "release_manifest_sha256": _sha256(release_manifest_path),
            "sbom": "manifest/sbom.spdx.json",
            "sbom_sha256": _sha256(sbom_path),
        },
        "scientific_status": release_manifest["scientific_status"],
    }
    _write_json(delivery_path, payload)
    return payload


def _build(
    output_root: Path,
    *,
    system_source: Path,
    skip_archive: bool,
    release_label: str,
    release_channel: str,
    candidate: str,
    user_acceptance: str,
    documentation_status: str,
) -> dict[str, Any]:
    required = [
        DESKTOP_PROJECT,
        UV,
        REPOSITORY_ROOT / "uv.lock",
        REPOSITORY_ROOT / "src" / "pilot_assessment",
        REPOSITORY_ROOT / "tools" / "release" / "verify_portable.py",
        REPOSITORY_ROOT / "tools" / "developer" / "manage_python_dependencies.ps1",
        REPOSITORY_ROOT / "developer" / "examples" / "operator-extension",
        REPOSITORY_ROOT / "docs" / "product" / "release" / "README-PORTABLE.md",
        DOCUMENTATION_SOURCE_ROOT / "catalog.json",
        DOCUMENTATION_TOOL_ROOT / "build_manuals.py",
        DOCUMENTATION_TOOL_ROOT / "uv.lock",
        DOCUMENTATION_SOURCE_ROOT / "assets" / "screenshots" / "manifest.json",
        RELEASE_SOURCE_ROOT / "README-CANDIDATE.md",
        RELEASE_SOURCE_ROOT / "RELEASE-NOTES-v0.1.0-rc.1.md",
        RELEASE_SOURCE_ROOT / "ACCEPTANCE-CHECKLIST-v0.1.0-rc.1.md",
        RELEASE_SOURCE_ROOT / "KNOWN-LIMITATIONS.md",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise ReleaseBuildError(f"required release inputs are missing: {missing}")

    version = _read_product_version()
    identity = _release_identity(
        product_version=version,
        release_label=release_label,
        release_channel=release_channel,
        candidate=candidate,
        user_acceptance=user_acceptance,
        documentation_status=documentation_status,
        skip_archive=skip_archive,
    )
    git_state = _git_state(identity.release_label)
    documentation_root = _generate_documentation(version, identity.documentation_status)
    package_name = identity.package_name
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    package_root = output_root / package_name
    archive_path = output_root / f"{package_name}.zip"
    archive_hash_path = output_root / f"{package_name}.zip.sha256"
    delivery_path = output_root / f"{package_name}.delivery.json"
    system_source = _require_external_system_source(system_source, package_root)
    _remove_tree(package_root, output_root)
    _unlink(archive_path, output_root)
    _unlink(archive_hash_path, output_root)
    _unlink(delivery_path, output_root)

    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    publish_root = WORK_ROOT / "desktop-publish"
    _remove_tree(publish_root, WORK_ROOT)
    publish_root.mkdir(parents=True)
    requirements = WORK_ROOT / "runtime-requirements.txt"
    if requirements.exists():
        requirements.unlink()

    _publish_desktop(publish_root)
    shutil.copytree(publish_root, package_root, dirs_exist_ok=True)
    for path in package_root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".pdb", ".tmp", ".log"}:
            path.unlink()

    _install_python_runtime(package_root, requirements)
    _copy_product_sources(package_root, documentation_root)
    built_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    capture_report = capture_current_system(system_source, package_root / "system")
    _initialize_captured_system(
        package_root,
        product_version=identity.product_version,
        built_at=built_at,
        capture_report=capture_report,
    )
    license_files = _collect_licenses(package_root)
    _write_manifests(
        package_root,
        identity=identity,
        git_state=git_state,
        license_files=license_files,
        built_at=built_at,
        capture_report=capture_report,
    )

    verification_root = _internal_verification_root(
        work_root=WORK_ROOT,
        identity=identity,
    )
    _remove_tree(verification_root, WORK_ROOT)
    shutil.copytree(package_root, verification_root)
    _run(
        [
            str(verification_root / "runtime" / "python" / "python.exe"),
            "-I",
            "-B",
            "-X",
            "utf8",
            str(verification_root / "developer" / "build" / "release" / "verify_portable.py"),
            str(verification_root),
            "--verify-operator-extension",
        ],
        cwd=verification_root,
    )
    _remove_tree(verification_root, WORK_ROOT)

    created = shutil.make_archive(
        str(archive_path.with_suffix("")),
        "zip",
        root_dir=output_root,
        base_dir=package_name,
    )
    archive_path = Path(created)
    archive_hash = _sha256(archive_path)
    archive_hash_path.write_text(
        f"{archive_hash}  {archive_path.name}\n",
        encoding="utf-8",
        newline="\n",
    )
    _write_delivery_manifest(
        delivery_path,
        package_root=package_root,
        archive_path=archive_path,
        archive_sha256=archive_hash,
    )

    return {
        "package_directory": str(package_root),
        "package_bytes": sum(
            path.stat().st_size for path in package_root.rglob("*") if path.is_file()
        ),
        "release_label": identity.release_label,
        "user_acceptance": identity.user_acceptance,
        "zip": str(archive_path),
        "zip_bytes": archive_path.stat().st_size,
        "zip_sha256": archive_hash,
        "zip_sha256_file": str(archive_hash_path),
        "delivery_manifest": str(delivery_path),
        "system_model": {
            "model_library_id": capture_report.model_library_id,
            "model_identity_sha256": capture_report.model_identity_sha256,
            "node_count": capture_report.node_count,
            "scheme_count": capture_report.scheme_count,
        },
    }


def main() -> int:
    args = _arguments()
    try:
        result = _build(
            args.output_root,
            system_source=args.system_source,
            skip_archive=args.skip_archive,
            release_label=args.release_label,
            release_channel=args.release_channel,
            candidate=args.candidate,
            user_acceptance=args.user_acceptance,
            documentation_status=args.documentation_status,
        )
    except (OSError, KeyError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        print(f"Pilot Assessment portable build failed: {error}", file=sys.stderr)
        return 1
    except ReleaseBuildError as error:
        print(f"Pilot Assessment portable build failed: {error}", file=sys.stderr)
        return 1
    except SystemCaptureError as error:
        print(f"Pilot Assessment portable build failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
