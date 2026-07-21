"""Build the Windows x64 portable Pilot Assessment engineering release."""

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
from datetime import UTC, datetime
from email.parser import Parser
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DESKTOP_PROJECT = (
    REPOSITORY_ROOT / "src" / "PilotAssessment.Desktop" / ("PilotAssessment.Desktop.csproj")
)
UV = REPOSITORY_ROOT / ".tools" / "uv" / "uv.exe"
WORK_ROOT = REPOSITORY_ROOT / "build" / "portable-release"
CACHE_ROOT = REPOSITORY_ROOT / "build" / "release-cache"
DEFAULT_OUTPUT_ROOT = REPOSITORY_ROOT / "dist" / "releases"

PYTHON_VERSION = "3.11.9"
PYTHON_EMBED_URL = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"
PYTHON_EMBED_SHA256 = "009d6bf7e3b2ddca3d784fa09f90fe54336d5b60f0e0f305c37f400bf83cfd3b"
SYSTEM_MODEL_LIBRARY_ID = "model-library.system.default"

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


class ReleaseBuildError(RuntimeError):
    """Raised when a portable release invariant is not satisfied."""


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
        help="Build and verify the product directory without creating a ZIP.",
    )
    return parser.parse_args()


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


def _download_python_embed() -> Path:
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    archive = CACHE_ROOT / f"python-{PYTHON_VERSION}-embed-amd64.zip"
    if archive.exists() and _sha256(archive) != PYTHON_EMBED_SHA256:
        _unlink(archive, CACHE_ROOT)
    if not archive.exists():
        print(f"Downloading {PYTHON_EMBED_URL}", flush=True)
        request = urllib.request.Request(
            PYTHON_EMBED_URL,
            headers={"User-Agent": "PilotAssessment-M8B0-Builder/0.2"},
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


def _copy_product_sources(package_root: Path) -> None:
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

    docs_root = package_root / "docs"
    docs_root.mkdir(parents=True, exist_ok=True)
    for name in ("README-PORTABLE.md", "KNOWN-LIMITATIONS.md"):
        shutil.copy2(REPOSITORY_ROOT / "docs" / "product" / "release" / name, docs_root / name)
    shutil.copy2(docs_root / "README-PORTABLE.md", package_root / "README.txt")


def _initialize_system_model(
    package_root: Path,
    *,
    product_version: str,
    built_at: str,
) -> None:
    """Create the one clean starter model store shipped by this software copy."""

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
    model_library_id=sys.argv[4],
)
try:
    status = application.model_edits.status()
    print(json.dumps({
        "model_library_id": application.model_library_id,
        "node_count": len(application.current_model.list_nodes()),
        "scheme_count": len(application.current_model.list_schemes()),
        "edit_session_dirty": status.dirty,
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
            SYSTEM_MODEL_LIBRARY_ID,
        ],
        cwd=package_root,
        echo_output=False,
    )
    initialized = json.loads(output)
    expected = {
        "model_library_id": SYSTEM_MODEL_LIBRARY_ID,
        "node_count": 53,
        "scheme_count": 1,
        "edit_session_dirty": False,
    }
    if initialized != expected:
        raise ReleaseBuildError(f"starter system initialization is incomplete: {initialized}")
    lock_path = system_root / ".system-writer.lock"
    if lock_path.exists():
        lock_path.unlink()
    transient = tuple(system_root.rglob("*.sqlite3-wal")) + tuple(
        system_root.rglob("*.sqlite3-shm")
    )
    if transient:
        raise ReleaseBuildError(f"starter system has transient SQLite files: {transient}")


def _model_identity(connection: sqlite3.Connection) -> tuple[str, int, int]:
    digest = hashlib.sha256()
    node_rows = connection.execute(
        "SELECT node_id, content_hash, layout_hash FROM model_nodes ORDER BY node_id"
    ).fetchall()
    scheme_rows = connection.execute(
        "SELECT scheme_id, content_hash, layout_hash FROM task_schemes ORDER BY scheme_id"
    ).fetchall()
    for kind, rows in (("node", node_rows), ("scheme", scheme_rows)):
        for identity, content_hash, layout_hash in rows:
            digest.update(kind.encode("ascii"))
            digest.update(b"\0")
            digest.update(str(identity).encode("utf-8"))
            digest.update(b"\0")
            digest.update(str(content_hash).encode("ascii"))
            digest.update(b"\0")
            digest.update(str(layout_hash).encode("ascii"))
            digest.update(b"\n")
    return digest.hexdigest(), len(node_rows), len(scheme_rows)


def _system_model_baseline(package_root: Path) -> dict[str, Any]:
    system_root = package_root / "system"
    canonical_path = system_root / "model-library.sqlite3"
    edit_path = system_root / "staging" / "model-edit" / "workspace.sqlite3"
    locator_path = system_root / "system.json"
    if not all(path.is_file() for path in (canonical_path, edit_path, locator_path)):
        raise ReleaseBuildError("starter system store is incomplete")

    locator = json.loads(locator_path.read_text(encoding="utf-8"))
    canonical = sqlite3.connect(canonical_path)
    edit = sqlite3.connect(edit_path)
    try:
        model_identity, node_count, scheme_count = _model_identity(canonical)
        metadata = canonical.execute(
            "SELECT model_library_id, clean_shutdown FROM system_metadata WHERE singleton = 1"
        ).fetchone()
        if metadata is None:
            raise ReleaseBuildError("starter system metadata is missing")
        state = edit.execute(
            """
            SELECT model_library_id, base_fingerprint, baseline_state_hash,
                   cursor, latest_sequence
            FROM model_edit_session_state WHERE singleton = 1
            """
        ).fetchone()
        if state is None:
            raise ReleaseBuildError("starter model edit-session state is missing")
        user_tables = (
            "project_metadata",
            "sessions",
            "session_revisions",
            "managed_artifacts",
            "artifact_references",
            "run_preflights",
            "runs",
            "run_results",
            "model_run_preflights_v2",
            "model_run_links_v2",
            "legacy_system_model_import_receipts",
        )
        user_counts = {
            table: int(canonical.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in user_tables
        }
    finally:
        canonical.close()
        edit.close()

    model_library_id = str(metadata[0])
    if locator.get("model_library_id") != model_library_id:
        raise ReleaseBuildError("starter locator and database model-library identities differ")
    if model_library_id != SYSTEM_MODEL_LIBRARY_ID or int(metadata[1]) != 1:
        raise ReleaseBuildError("starter system identity or clean-shutdown state is invalid")
    if str(state[0]) != model_library_id or int(state[3]) != 0 or int(state[4]) != 0:
        raise ReleaseBuildError("starter system edit workspace is not clean")
    if any(user_counts.values()):
        raise ReleaseBuildError(f"starter system contains user-owned data: {user_counts}")

    return {
        "schema_version": "pilot-assessment-system-model-baseline-v1",
        "model_library_id": model_library_id,
        "starter_seed_id": locator["starter_seed_id"],
        "starter_seed_hash": locator["starter_seed_hash"],
        "model_identity_sha256": model_identity,
        "node_count": node_count,
        "scheme_count": scheme_count,
        "canonical_database": {
            "path": canonical_path.relative_to(package_root).as_posix(),
            "sha256": _sha256(canonical_path),
        },
        "edit_workspace": {
            "path": edit_path.relative_to(package_root).as_posix(),
            "sha256": _sha256(edit_path),
            "base_fingerprint": str(state[1]),
            "baseline_state_hash": str(state[2]),
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


def _git_state() -> dict[str, Any]:
    commit = _run(["git", "rev-parse", "HEAD"]).splitlines()[-1]
    status = _run(["git", "status", "--porcelain"], echo_output=False)
    return {"commit": commit, "dirty": bool(status.strip())}


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
    product_version: str,
    built_at: str,
    python_packages: list[dict[str, str]],
) -> None:
    first_party = {
        "name": "pilot-assessment-system",
        "version": product_version,
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
        f"pilot-assessment:{product_version}:{built_at}",
    )
    payload = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"PilotAssessment-{product_version}-win-x64",
        "documentNamespace": f"https://pilot-assessment.local/spdx/{namespace_token}",
        "creationInfo": {
            "created": built_at,
            "creators": ["Tool: PilotAssessment-M8B0-Builder-0.2"],
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


def _write_manifests(
    package_root: Path,
    *,
    product_version: str,
    license_files: list[str],
    built_at: str,
) -> None:
    manifest_root = package_root / "manifest"
    manifest_root.mkdir(parents=True, exist_ok=True)
    python_packages = _installed_python_packages(package_root / "runtime" / "site-packages")
    source_baseline = _source_baseline(package_root)
    _write_json(manifest_root / "source-baseline.json", source_baseline)
    system_model_baseline = _system_model_baseline(package_root)
    _write_json(manifest_root / "system-model-baseline.json", system_model_baseline)
    _write_sbom(
        package_root,
        product_version=product_version,
        built_at=built_at,
        python_packages=python_packages,
    )

    dotnet_version = _run(["dotnet", "--version"]).splitlines()[-1]
    uv_version = _run([str(UV), "--version"]).splitlines()[-1]
    payload: dict[str, Any] = {
        "schema_version": "pilot-assessment-release-manifest-v1",
        "product": "Pilot Assessment System",
        "product_version": product_version,
        "build_kind": "m8b-source-provenance-engineering",
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
        },
        "toolchain": {
            "dotnet_sdk": dotnet_version,
            "windows_app_sdk": "2.3.1",
            "python_embedded": PYTHON_VERSION,
            "python_embedded_sha256": PYTHON_EMBED_SHA256,
            "uv": uv_version,
        },
        "git": _git_state(),
        "python_packages": python_packages,
        "source_baseline_sha256": source_baseline["aggregate_sha256"],
        "system_model_baseline_sha256": _sha256(manifest_root / "system-model-baseline.json"),
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


def _build(output_root: Path, *, skip_archive: bool) -> dict[str, Any]:
    required = [
        DESKTOP_PROJECT,
        UV,
        REPOSITORY_ROOT / "uv.lock",
        REPOSITORY_ROOT / "src" / "pilot_assessment",
        REPOSITORY_ROOT / "tools" / "release" / "verify_portable.py",
        REPOSITORY_ROOT / "docs" / "product" / "release" / "README-PORTABLE.md",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise ReleaseBuildError(f"required release inputs are missing: {missing}")

    version = _read_product_version()
    package_name = f"PilotAssessment-{version}-win-x64"
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    package_root = output_root / package_name
    archive_path = output_root / f"{package_name}.zip"
    archive_hash_path = output_root / f"{package_name}.zip.sha256"
    _remove_tree(package_root, output_root)
    _unlink(archive_path, output_root)
    _unlink(archive_hash_path, output_root)

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
    _copy_product_sources(package_root)
    built_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    _initialize_system_model(
        package_root,
        product_version=version,
        built_at=built_at,
    )
    license_files = _collect_licenses(package_root)
    _write_manifests(
        package_root,
        product_version=version,
        license_files=license_files,
        built_at=built_at,
    )

    verification_root = WORK_ROOT / "verification-copy"
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
        ],
        cwd=verification_root,
    )
    _remove_tree(verification_root, WORK_ROOT)

    archive_hash = None
    if not skip_archive:
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

    return {
        "package_directory": str(package_root),
        "package_bytes": sum(
            path.stat().st_size for path in package_root.rglob("*") if path.is_file()
        ),
        "zip": None if skip_archive else str(archive_path),
        "zip_bytes": None if skip_archive else archive_path.stat().st_size,
        "zip_sha256": archive_hash,
    }


def main() -> int:
    args = _arguments()
    try:
        result = _build(args.output_root, skip_archive=args.skip_archive)
    except (OSError, KeyError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        print(f"M8B-0 portable build failed: {error}", file=sys.stderr)
        return 1
    except ReleaseBuildError as error:
        print(f"M8B-0 portable build failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
