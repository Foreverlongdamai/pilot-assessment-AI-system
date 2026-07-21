"""Verify a Pilot Assessment portable product directory without dev dependencies."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from ctypes import wintypes
from pathlib import Path
from typing import Any

_RELEASE_TOOL_ROOT = Path(__file__).resolve().parent
if str(_RELEASE_TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(_RELEASE_TOOL_ROOT))

from system_model_capture import USER_OWNED_SYSTEM_TABLES, model_identity  # noqa: E402

FORBIDDEN_DIRECTORY_NAMES = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".ty",
    ".venv",
    "__pycache__",
    "local_data",
}
FORBIDDEN_FILE_SUFFIXES = {
    ".db",
    ".edf",
    ".log",
    ".mp4",
    ".parquet",
    ".pdb",
    ".pyc",
    ".pyo",
    ".sqlite",
    ".sqlite3",
    ".tmp",
}
TEXT_SCAN_SUFFIXES = {
    ".cmd",
    ".cs",
    ".csproj",
    ".json",
    ".md",
    ".props",
    ".ps1",
    ".py",
    ".resw",
    ".targets",
    ".toml",
    ".txt",
    ".xaml",
    ".xml",
}
SYSTEM_MODEL_FILES = {
    "system/system.json",
    "system/model-library.sqlite3",
    "system/staging/model-edit/workspace.sqlite3",
}
ROOT_DIRECTORIES = {
    "app",
    "backend",
    "developer",
    "docs",
    "licenses",
    "manifest",
    "runtime",
    "system",
}
ROOT_FILES = {"PilotAssessment.exe", "README.txt"}


class PortableVerificationError(RuntimeError):
    """Raised when the portable product violates its release contract."""


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_root", type=Path)
    parser.add_argument(
        "--verify-editable-source",
        action="store_true",
        help="Temporarily edit dispatcher.py and prove restart loads the edit.",
    )
    parser.add_argument(
        "--verify-operator-extension",
        action="store_true",
        help="Temporarily install the bundled example operator and run the M8B-2 vertical slice.",
    )
    parser.add_argument(
        "--launch-desktop",
        action="store_true",
        help="Launch the WinUI app, observe its packaged Python child, then close it.",
    )
    parser.add_argument("--desktop-timeout", type=float, default=30.0)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _restricted_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PATH"] = str(Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32")
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def _verify_root_surface(root: Path) -> dict[str, Any]:
    actual_directories = {path.name for path in root.iterdir() if path.is_dir()}
    actual_files = {path.name for path in root.iterdir() if path.is_file()}
    unexpected = sorted(
        (actual_directories - ROOT_DIRECTORIES) | (actual_files - ROOT_FILES),
        key=str.casefold,
    )
    missing = sorted(
        (ROOT_DIRECTORIES - actual_directories) | (ROOT_FILES - actual_files),
        key=str.casefold,
    )
    if unexpected or missing:
        raise PortableVerificationError(
            "portable product has unexpected root entries or missing semantic entries: "
            f"unexpected={unexpected}, missing={missing}"
        )
    launchers = sorted(
        name
        for name in actual_files
        if Path(name).suffix.casefold() in {".exe", ".cmd", ".bat", ".ps1", ".vbs"}
    )
    if launchers != ["PilotAssessment.exe"]:
        raise PortableVerificationError(
            f"portable product must expose one root launcher: {launchers}"
        )
    return {
        "root_directories": len(actual_directories),
        "root_files": len(actual_files),
        "launchers": launchers,
        "desktop_payload_root": "app",
    }


def _required_layout(root: Path) -> dict[str, Any]:
    surface = _verify_root_surface(root)
    required_files = [
        "PilotAssessment.exe",
        "app/PilotAssessment.Desktop.exe",
        "app/PilotAssessment.Desktop.deps.json",
        "app/Assets/AppIcon.ico",
        "runtime/python/python.exe",
        "runtime/python/python311._pth",
        "backend/src/pilot_assessment/__init__.py",
        "backend/src/pilot_assessment/evidence/extensions/__init__.py",
        "backend/src/pilot_assessment/sidecar/__main__.py",
        "backend/pyproject.toml",
        "backend/uv.lock",
        "manifest/release-manifest.json",
        "manifest/source-baseline.json",
        "manifest/system-model-baseline.json",
        "manifest/checksums.sha256",
        "manifest/sbom.spdx.json",
        "README.txt",
        "developer/tools/manage_python_dependencies.ps1",
        "developer/tools/uv.exe",
        "developer/examples/operator-extension/example_scalar_offset.py",
        "developer/examples/operator-extension/test_example_scalar_offset.py",
        "developer/examples/operator-extension/README.md",
        "docs/documentation-manifest.json",
        "docs/source-catalog.json",
        "docs/assets/screenshots/manifest.json",
        "docs/README-CANDIDATE.md",
        "docs/RELEASE-NOTES.md",
        "docs/ACCEPTANCE-CHECKLIST.md",
        "docs/KNOWN-LIMITATIONS.md",
        "system/system.json",
        "system/model-library.sqlite3",
        "system/staging/model-edit/workspace.sqlite3",
    ]
    missing = [relative for relative in required_files if not (root / relative).is_file()]
    if missing:
        raise PortableVerificationError(f"portable layout is incomplete: {missing}")
    if not (root / "runtime" / "site-packages").is_dir():
        raise PortableVerificationError("runtime/site-packages is missing")
    return surface


def _verify_release_identity(root: Path) -> dict[str, Any]:
    manifest = json.loads((root / "manifest" / "release-manifest.json").read_text(encoding="utf-8"))
    expected = {
        "schema_version": "pilot-assessment-release-manifest-v3",
        "product_version": "0.1.0",
        "release_channel": "release-candidate",
        "user_acceptance": "pending",
        "documentation_status": "released",
        "build_kind": "m8e-release-candidate",
    }
    observed = {key: manifest.get(key) for key in expected}
    if observed != expected:
        raise PortableVerificationError(
            f"release candidate identity differs: expected={expected}, actual={observed}"
        )
    candidate = manifest.get("candidate")
    release_label = manifest.get("release_label")
    if not isinstance(candidate, str) or re.fullmatch(r"rc\.[1-9][0-9]*", candidate) is None:
        raise PortableVerificationError("release candidate sequence is invalid")
    expected_label = f"v{expected['product_version']}-{candidate}"
    if release_label != expected_label:
        raise PortableVerificationError("release label differs from product/candidate identity")
    if root.name != f"PilotAssessment-{expected['product_version']}-{candidate}-win-x64":
        raise PortableVerificationError("product directory name differs from candidate identity")
    expected_layout = {
        "schema_version": "pilot-assessment-portable-layout-v2",
        "launcher": "PilotAssessment.exe",
        "desktop_payload_root": "app",
        "desktop_executable": "app/PilotAssessment.Desktop.exe",
        "semantic_root_directories": sorted(ROOT_DIRECTORIES),
    }
    if (
        manifest.get("entrypoint") != "PilotAssessment.exe"
        or manifest.get("portable_layout") != expected_layout
    ):
        raise PortableVerificationError("portable root/desktop payload contract differs")
    git = manifest.get("git")
    if not isinstance(git, dict) or git.get("dirty") is not False:
        raise PortableVerificationError("release manifest does not prove a clean Git source")
    if (
        git.get("tag") != release_label
        or git.get("tag_type") != "annotated"
        or git.get("tag_peels_to_head") is not True
        or not isinstance(git.get("commit"), str)
        or len(git["commit"]) != 40
    ):
        raise PortableVerificationError("release manifest tagged Git identity is invalid")
    scientific = manifest.get("scientific_status")
    if not isinstance(scientific, dict) or scientific.get("formal_run_authorized") is not False:
        raise PortableVerificationError("release candidate scientific boundary is missing")
    for filename in (
        "README-CANDIDATE.md",
        "RELEASE-NOTES.md",
        "ACCEPTANCE-CHECKLIST.md",
        "KNOWN-LIMITATIONS.md",
    ):
        text = (root / "docs" / filename).read_text(encoding="utf-8")
        if release_label not in text or "pending" not in text.lower():
            raise PortableVerificationError(
                f"candidate handoff file lacks release/acceptance identity: {filename}"
            )
    return {
        "product_version": expected["product_version"],
        "release_label": release_label,
        "candidate": candidate,
        "user_acceptance": expected["user_acceptance"],
        "git": git,
        "formal_run_authorized": False,
    }


def _verify_checksums(root: Path, *, ignore_mutable_system: bool = False) -> int:
    checksum_path = root / "manifest" / "checksums.sha256"
    entries: dict[str, str] = {}
    for line_number, line in enumerate(checksum_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line:
            continue
        try:
            digest, relative = line.split("  ", 1)
        except ValueError as error:
            raise PortableVerificationError(
                f"invalid checksum line {line_number}: {line!r}"
            ) from error
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise PortableVerificationError(f"checksum escapes package root: {relative}")
        if ignore_mutable_system and relative.startswith("system/"):
            continue
        if not path.is_file():
            raise PortableVerificationError(f"checksummed file is missing: {relative}")
        actual = _sha256(path)
        if actual != digest:
            raise PortableVerificationError(
                f"checksum mismatch for {relative}: expected {digest}, got {actual}"
            )
        entries[relative] = digest

    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and path != checksum_path
        and not (ignore_mutable_system and path.relative_to(root).as_posix().startswith("system/"))
    }
    if actual_files != set(entries):
        missing = sorted(actual_files - set(entries))
        extra = sorted(set(entries) - actual_files)
        raise PortableVerificationError(
            f"checksum inventory differs from product files: unlisted={missing}, stale={extra}"
        )
    return len(entries)


def _verify_documentation(root: Path) -> dict[str, Any]:
    docs_root = root / "docs"
    manifest_path = docs_root / "documentation-manifest.json"
    catalog_path = docs_root / "source-catalog.json"
    release_manifest_path = root / "manifest" / "release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    release_manifest = json.loads(release_manifest_path.read_text(encoding="utf-8"))

    if manifest.get("schema_version") != "pilot-assessment-document-build-v1":
        raise PortableVerificationError("documentation manifest version is unsupported")
    if catalog.get("schema_version") != "pilot-assessment-document-catalog-v1":
        raise PortableVerificationError("documentation catalog version is unsupported")
    product_version = release_manifest.get("product_version")
    if not (product_version == manifest.get("product_version") == catalog.get("product_version")):
        raise PortableVerificationError("documentation and product versions differ")
    if manifest.get("build_status") != "released":
        raise PortableVerificationError("release candidate documentation must be released")
    if not (
        manifest.get("release_channel")
        == catalog.get("release_channel")
        == release_manifest.get("release_channel")
        == "release-candidate"
        and manifest.get("release_label")
        == catalog.get("release_label")
        == release_manifest.get("release_label")
        and manifest.get("user_acceptance")
        == catalog.get("user_acceptance")
        == release_manifest.get("user_acceptance")
        == "pending"
    ):
        raise PortableVerificationError("documentation release-candidate identity differs")

    documents = catalog.get("documents")
    outputs = manifest.get("outputs")
    if not isinstance(documents, list) or not isinstance(outputs, list) or not outputs:
        raise PortableVerificationError("documentation catalog/outputs are missing")
    catalog_index = {
        str(item.get("document_id")): item for item in documents if isinstance(item, dict)
    }
    if len(catalog_index) != 12:
        raise PortableVerificationError("documentation catalog must contain 12 logical manuals")
    if len(outputs) != 24:
        raise PortableVerificationError("release candidate must contain 24 documentation outputs")

    expected_docx: set[str] = set()
    status_counts = {"review": 0, "released": 0}
    for item in outputs:
        if not isinstance(item, dict):
            raise PortableVerificationError("documentation output must be an object")
        status = str(item.get("status"))
        if status not in status_counts:
            raise PortableVerificationError(
                f"draft/unknown documentation cannot enter the engineering package: {status!r}"
            )
        relative = Path(str(item.get("output", "")))
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            raise PortableVerificationError(f"unsafe documentation output path: {relative}")
        package_relative = (
            Path("docs") / relative if status == "released" else Path("docs") / "review" / relative
        )
        output = (root / package_relative).resolve()
        if not output.is_relative_to(root) or not output.is_file():
            raise PortableVerificationError(
                f"document output is missing from its status directory: {package_relative}"
            )
        if output.stat().st_size != int(item.get("output_bytes", -1)):
            raise PortableVerificationError(f"document output size differs: {package_relative}")
        if _sha256(output) != item.get("output_sha256"):
            raise PortableVerificationError(f"document output hash differs: {package_relative}")
        logical = package_relative.as_posix()
        if logical in expected_docx:
            raise PortableVerificationError(f"duplicate documentation output: {logical}")
        expected_docx.add(logical)
        status_counts[status] += 1

        document_id = str(item.get("document_id"))
        language = str(item.get("language"))
        record = catalog_index.get(document_id)
        variants = record.get("languages") if isinstance(record, dict) else None
        variant = variants.get(language) if isinstance(variants, dict) else None
        if not isinstance(variant, dict):
            raise PortableVerificationError(
                f"documentation output is absent from the catalog: {document_id}/{language}"
            )
        if variant.get("status") != status or variant.get("output") != relative.name:
            raise PortableVerificationError(
                f"documentation catalog differs from output: {document_id}/{language}"
            )

    actual_docx = {
        path.relative_to(root).as_posix() for path in docs_root.rglob("*.docx") if path.is_file()
    }
    if actual_docx != expected_docx:
        raise PortableVerificationError(
            "packaged DOCX inventory differs from documentation manifest: "
            f"actual={sorted(actual_docx)}, expected={sorted(expected_docx)}"
        )

    if status_counts != {"review": 0, "released": 24}:
        raise PortableVerificationError(
            f"release candidate documentation status counts differ: {status_counts}"
        )

    screenshot_manifest_path = docs_root / "assets" / "screenshots" / "manifest.json"
    screenshot_manifest = json.loads(screenshot_manifest_path.read_text(encoding="utf-8"))
    screenshots = screenshot_manifest.get("screenshots")
    if not isinstance(screenshots, list) or len(screenshots) != 10:
        raise PortableVerificationError("release candidate must contain ten screenshots")
    screenshot_keys: set[tuple[str, str]] = set()
    for item in screenshots:
        if not isinstance(item, dict):
            raise PortableVerificationError("screenshot manifest entry must be an object")
        key = (str(item.get("screenshot_id")), str(item.get("language")))
        screenshot_keys.add(key)
        relative = Path(str(item.get("path", "")))
        path = (docs_root / relative).resolve()
        if not path.is_relative_to(docs_root) or not path.is_file():
            raise PortableVerificationError(f"candidate screenshot is missing: {relative}")
        if _sha256(path) != item.get("sha256"):
            raise PortableVerificationError(f"candidate screenshot hash differs: {relative}")
        if item.get("status") != "release-candidate":
            raise PortableVerificationError(f"candidate screenshot status differs: {relative}")
        privacy = item.get("privacy_review")
        if not isinstance(privacy, dict) or privacy.get("status") != "passed":
            raise PortableVerificationError(
                f"candidate screenshot privacy review differs: {relative}"
            )
    if len(screenshot_keys) != 10:
        raise PortableVerificationError("candidate screenshot identities are not unique")

    recorded = release_manifest.get("documentation")
    expected_summary = {
        "build_status": manifest.get("build_status"),
        "manifest": "docs/documentation-manifest.json",
        "manifest_sha256": _sha256(manifest_path),
        "catalog": "docs/source-catalog.json",
        "catalog_sha256": _sha256(catalog_path),
        "generated_output_count": len(outputs),
        "released_output_count": status_counts["released"],
        "review_output_count": status_counts["review"],
        "screenshot_manifest": "docs/assets/screenshots/manifest.json",
        "screenshot_manifest_sha256": _sha256(screenshot_manifest_path),
        "candidate_screenshot_count": len(screenshots),
    }
    if recorded != expected_summary:
        raise PortableVerificationError("release manifest documentation summary differs")
    return expected_summary


def _verify_system_model_baseline(root: Path) -> dict[str, Any]:
    baseline_path = root / "manifest" / "system-model-baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    if baseline.get("schema_version") != "pilot-assessment-system-model-baseline-v2":
        raise PortableVerificationError("system model baseline version is unsupported")
    if baseline.get("capture_mode") != "explicit-current-system":
        raise PortableVerificationError("system model baseline capture mode is invalid")
    actual_system_files = {
        path.relative_to(root).as_posix() for path in (root / "system").rglob("*") if path.is_file()
    }
    if actual_system_files != SYSTEM_MODEL_FILES:
        raise PortableVerificationError(
            f"captured system file set is invalid: {sorted(actual_system_files)}"
        )

    locator = json.loads((root / "system" / "system.json").read_text(encoding="utf-8"))
    if baseline.get("user_owned_row_counts") != {table: 0 for table in USER_OWNED_SYSTEM_TABLES}:
        raise PortableVerificationError("system baseline user-owned table inventory is invalid")
    if baseline["canonical_database"].get("path") != "system/model-library.sqlite3":
        raise PortableVerificationError("system baseline canonical path is invalid")
    if baseline["edit_workspace"].get("path") != ("system/staging/model-edit/workspace.sqlite3"):
        raise PortableVerificationError("system baseline edit-workspace path is invalid")
    canonical_path = (root / baseline["canonical_database"]["path"]).resolve()
    edit_path = (root / baseline["edit_workspace"]["path"]).resolve()
    if _sha256(canonical_path) != baseline["canonical_database"]["sha256"]:
        raise PortableVerificationError("captured canonical model database hash differs")
    if _sha256(edit_path) != baseline["edit_workspace"]["sha256"]:
        raise PortableVerificationError("captured edit workspace database hash differs")

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
        state = edit.execute(
            """
            SELECT model_library_id, base_fingerprint, baseline_state_hash,
                   cursor, latest_sequence
            FROM model_edit_session_state WHERE singleton = 1
            """
        ).fetchone()
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

    if metadata is None or state is None:
        raise PortableVerificationError("captured system metadata or edit state is missing")
    model_library_id = str(metadata[0])
    if not (
        model_library_id == baseline["model_library_id"] == locator.get("model_library_id")
        and str(state[0]) == model_library_id
    ):
        raise PortableVerificationError("captured model-library identities differ")
    lineage = baseline.get("starter_lineage")
    if not isinstance(lineage, dict) or not (
        str(metadata[1]) == baseline.get("system_format_version") == locator.get("format_version")
        and str(metadata[2]) == lineage.get("starter_seed_id") == locator.get("starter_seed_id")
        and str(metadata[3]) == lineage.get("starter_seed_hash") == locator.get("starter_seed_hash")
    ):
        raise PortableVerificationError("captured system format or starter lineage differs")
    if (
        int(metadata[4]) != 1
        or int(state[3]) != 0
        or int(state[4]) != 0
        or baseline["edit_workspace"].get("cursor") != 0
        or baseline["edit_workspace"].get("latest_sequence") != 0
    ):
        raise PortableVerificationError("captured system is not cleanly closed and edit-clean")
    if (
        str(state[1]) != baseline["edit_workspace"]["base_fingerprint"]
        or str(state[2]) != baseline["edit_workspace"]["baseline_state_hash"]
        or baseline["edit_workspace"].get("dirty") is not False
    ):
        raise PortableVerificationError("captured edit baseline identity differs")
    if (
        current_identity != baseline["model_identity_sha256"]
        or node_count != baseline["node_count"]
        or scheme_count != baseline["scheme_count"]
    ):
        raise PortableVerificationError("captured system model identity differs")
    if database_schema_version != baseline.get(
        "database_schema_version"
    ) or system_schema_version != baseline.get("system_schema_version"):
        raise PortableVerificationError("captured system schema identity differs")
    if user_counts != baseline["user_owned_row_counts"] or any(user_counts.values()):
        raise PortableVerificationError(f"captured system contains user-owned rows: {user_counts}")

    source = baseline.get("capture_source")
    if not isinstance(source, dict):
        raise PortableVerificationError("captured system source facts are missing")
    source_hashes = (
        source.get("locator_sha256"),
        source.get("canonical_database_sha256"),
    )
    if any(
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
        for value in source_hashes
    ):
        raise PortableVerificationError("captured system source hashes are invalid")
    if _sha256(root / "system" / "system.json") != source["locator_sha256"]:
        raise PortableVerificationError("captured locator differs from its selected source")

    release_manifest = json.loads(
        (root / "manifest" / "release-manifest.json").read_text(encoding="utf-8")
    )
    expected_summary = {
        "baseline": "manifest/system-model-baseline.json",
        "capture_mode": "explicit-current-system",
        "model_library_id": model_library_id,
        "model_identity_sha256": current_identity,
        "node_count": node_count,
        "scheme_count": scheme_count,
    }
    if release_manifest.get("system_model") != expected_summary:
        raise PortableVerificationError("release manifest system-model summary differs")
    if release_manifest.get("system_model_baseline_sha256") != _sha256(baseline_path):
        raise PortableVerificationError("release manifest system baseline hash differs")
    return {
        "model_library_id": model_library_id,
        "model_identity_sha256": current_identity,
        "node_count": node_count,
        "scheme_count": scheme_count,
        "edit_session_dirty": False,
        "capture_mode": "explicit-current-system",
    }


def _verify_runtime_system_model(
    runtime: object,
    baseline: dict[str, Any],
) -> None:
    if not isinstance(runtime, dict):
        raise PortableVerificationError("runtime status omitted the system model summary")
    keys = (
        "model_library_id",
        "model_identity_sha256",
        "node_count",
        "scheme_count",
    )
    if any(runtime.get(key) != baseline.get(key) for key in keys):
        raise PortableVerificationError(
            "runtime system model identity/counts differ from the captured release baseline"
        )
    if runtime.get("edit_session_dirty") is not False:
        raise PortableVerificationError("fresh packaged runtime system model is unexpectedly dirty")


def _verify_source_baseline(root: Path) -> int:
    baseline = json.loads((root / "manifest" / "source-baseline.json").read_text(encoding="utf-8"))
    expected_root = "backend/src/pilot_assessment"
    if baseline.get("active_source_root") != expected_root:
        raise PortableVerificationError("source baseline points at the wrong active tree")
    expected_files = baseline.get("files")
    if not isinstance(expected_files, list):
        raise PortableVerificationError("source baseline files must be a list")
    source_root = root / expected_root
    candidates = [path for path in source_root.rglob("*") if path.is_file()]
    candidates.sort(key=lambda path: path.relative_to(source_root).as_posix().casefold())
    actual: dict[str, str] = {}
    digest = hashlib.sha256()
    digest.update(b"pilot-assessment-source-tree-v2\0")
    for path in candidates:
        relative = path.relative_to(source_root).as_posix().casefold()
        logical = f"backend/src/pilot_assessment/{relative}"
        if logical in actual:
            raise PortableVerificationError("live backend has a case-insensitive path collision")
        payload = path.read_bytes()
        path_bytes = relative.encode("utf-8")
        digest.update(len(path_bytes).to_bytes(8, "big"))
        digest.update(path_bytes)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
        actual[logical] = hashlib.sha256(payload).hexdigest()
    recorded = {str(item["path"]).casefold(): item["sha256"] for item in expected_files}
    if actual != recorded:
        raise PortableVerificationError("live backend source differs from source-baseline.json")
    expected_tree_hash = baseline.get("tree_sha256") or baseline.get("aggregate_sha256")
    if baseline.get("tree_algorithm") != "pilot-assessment-source-tree-v2":
        raise PortableVerificationError("source baseline uses an unsupported tree algorithm")
    if digest.hexdigest() != expected_tree_hash:
        raise PortableVerificationError("live backend tree hash differs from source baseline")
    return len(actual)


def _verify_content_policy(root: Path) -> None:
    violations: list[str] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_dir() and path.name.lower() in FORBIDDEN_DIRECTORY_NAMES:
            violations.append(f"forbidden directory: {relative}")
        if not path.is_file():
            continue
        if path.suffix.lower() in FORBIDDEN_FILE_SUFFIXES and relative not in SYSTEM_MODEL_FILES:
            violations.append(f"forbidden file type: {relative}")
        if path.suffix.lower() == ".pth" and not relative.endswith("python311._pth"):
            violations.append(f"unexpected import-path injection: {relative}")
        if path.suffix.lower() in TEXT_SCAN_SUFFIXES and path.stat().st_size <= 5_000_000:
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            private_markers = (
                "c:" + "\\users\\" + "long",
                "c:" + "/users/" + "long",
                "cranfieldoffer/" + "proj/" + "pilot_assessment_system",
                "cranfieldoffer\\" + "proj\\" + "pilot_assessment_system",
            )
            if any(marker in text for marker in private_markers):
                violations.append(f"developer-private absolute path: {relative}")

    site_packages = root / "runtime" / "site-packages"
    hidden_first_party = [
        path.relative_to(root).as_posix()
        for path in site_packages.iterdir()
        if path.name.lower().replace("-", "_").startswith("pilot_assessment")
    ]
    violations.extend(f"hidden first-party copy: {value}" for value in hidden_first_party)
    if violations:
        raise PortableVerificationError("content policy violations:\n- " + "\n- ".join(violations))


def _run_private_import(root: Path) -> dict[str, Any]:
    python = root / "runtime" / "python" / "python.exe"
    program = (
        "import json, pathlib, pilot_assessment; "
        "print(json.dumps({'file': str(pathlib.Path(pilot_assessment.__file__).resolve()), "
        "'version': pilot_assessment.__version__}))"
    )
    completed = subprocess.run(
        [str(python), "-I", "-B", "-X", "utf8", "-c", program],
        cwd=root,
        env=_restricted_environment(),
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise PortableVerificationError(f"private Python import failed: {completed.stderr.strip()}")
    payload = json.loads(completed.stdout)
    expected_root = (root / "backend" / "src" / "pilot_assessment").resolve()
    origin = Path(payload["file"]).resolve()
    if not origin.is_relative_to(expected_root):
        raise PortableVerificationError(f"pilot_assessment loaded from hidden origin: {origin}")
    return payload


def _sidecar_roundtrip(root: Path) -> dict[str, Any]:
    python = root / "runtime" / "python" / "python.exe"
    with tempfile.TemporaryDirectory(prefix="pilot-assessment-m8b-projects-") as temporary:
        project_root = Path(temporary)
        requests = [
            {
                "jsonrpc": "2.0",
                "id": "hello",
                "method": "runtime.hello",
                "params": {
                    "protocol_version": "1.0",
                    "supported_protocols": ["1.0"],
                    "client": {"name": "m8b-portable-verifier", "version": "0.1.0"},
                },
            },
            {"jsonrpc": "2.0", "id": "status-before", "method": "runtime.status"},
            {"jsonrpc": "2.0", "id": "schemes-before", "method": "model.scheme.list"},
            {
                "jsonrpc": "2.0",
                "id": "create-a",
                "method": "project.create",
                "params": {
                    "root": str(project_root / "project-a"),
                    "name": "Portable verification A",
                    "transaction_id": "tx.portable.project-a",
                    "actor": "system.portable-verifier",
                },
            },
            {"jsonrpc": "2.0", "id": "schemes-a", "method": "model.scheme.list"},
            {"jsonrpc": "2.0", "id": "close-a", "method": "project.close"},
            {
                "jsonrpc": "2.0",
                "id": "create-b",
                "method": "project.create",
                "params": {
                    "root": str(project_root / "project-b"),
                    "name": "Portable verification B",
                    "transaction_id": "tx.portable.project-b",
                    "actor": "system.portable-verifier",
                },
            },
            {"jsonrpc": "2.0", "id": "schemes-b", "method": "model.scheme.list"},
            {"jsonrpc": "2.0", "id": "close-b", "method": "project.close"},
            {"jsonrpc": "2.0", "id": "status-after", "method": "runtime.status"},
            {"jsonrpc": "2.0", "id": "shutdown", "method": "runtime.shutdown"},
        ]
        process = subprocess.Popen(
            [
                str(python),
                "-I",
                "-B",
                "-u",
                "-X",
                "utf8",
                "-m",
                "pilot_assessment.sidecar",
            ],
            cwd=root,
            env=_restricted_environment(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        input_text = "".join(json.dumps(request) + "\n" for request in requests)
        try:
            stdout, stderr = process.communicate(input=input_text, timeout=45)
        except subprocess.TimeoutExpired as error:
            process.kill()
            process.wait(timeout=5)
            raise PortableVerificationError("packaged sidecar timed out") from error
        if process.returncode != 0:
            raise PortableVerificationError(f"packaged sidecar failed: {stderr.strip()}")
        lines = [line for line in stdout.splitlines() if line]
        try:
            messages = [json.loads(line) for line in lines]
        except json.JSONDecodeError as error:
            raise PortableVerificationError(f"sidecar stdout is not JSONL: {stdout!r}") from error
        by_id = {message.get("id"): message for message in messages if "id" in message}
        expected_ids = {request["id"] for request in requests}
        if set(by_id) != expected_ids:
            raise PortableVerificationError(f"unexpected sidecar responses: {messages}")
        if any("error" in by_id[request_id] for request_id in expected_ids):
            raise PortableVerificationError(f"sidecar returned an RPC error: {messages}")

        hello = by_id["hello"]["result"]
        status_before = by_id["status-before"]["result"]
        status_after = by_id["status-after"]["result"]
        if hello.get("state") != "ready" or hello.get("protocol_version") != "1.0":
            raise PortableVerificationError(f"sidecar handshake is not ready: {hello}")
        if not status_before.get("system_ready") or status_before.get("project_open"):
            raise PortableVerificationError("system model is not ready without a project")
        backend_source = status_before.get("backend_source")
        if not isinstance(backend_source, dict):
            raise PortableVerificationError("runtime status omitted backend source provenance")
        loaded_source = backend_source.get("loaded_identity")
        if not isinstance(loaded_source, dict) or not loaded_source.get("baseline_available"):
            raise PortableVerificationError("portable backend did not load its release baseline")
        if backend_source.get("runtime_restart_required"):
            raise PortableVerificationError("fresh portable backend unexpectedly requires restart")
        runtime_system_model = status_before.get("system_model")
        if not isinstance(runtime_system_model, dict):
            raise PortableVerificationError("runtime status omitted system model diagnostics")
        if status_after.get("system_model") != runtime_system_model:
            raise PortableVerificationError("runtime system model changed across project switches")
        if status_after.get("model_library_id") != status_before.get("model_library_id"):
            raise PortableVerificationError("system model identity changed across projects")
        schemes_before = by_id["schemes-before"]["result"]["schemes"]
        if not schemes_before or not (
            schemes_before
            == by_id["schemes-a"]["result"]["schemes"]
            == by_id["schemes-b"]["result"]["schemes"]
        ):
            raise PortableVerificationError("projects did not observe one shared system model")
        project_ids = {
            by_id["create-a"]["result"]["project"]["project_id"],
            by_id["create-b"]["result"]["project"]["project_id"],
        }
        if len(project_ids) != 2:
            raise PortableVerificationError("portable project IDs are not independently generated")
        for name in ("project-a", "project-b"):
            database = sqlite3.connect(project_root / name / "project.sqlite3")
            try:
                if database.execute("SELECT COUNT(*) FROM model_nodes").fetchone()[0] != 0:
                    raise PortableVerificationError("project contains editable system model nodes")
                if database.execute("SELECT COUNT(*) FROM task_schemes").fetchone()[0] != 0:
                    raise PortableVerificationError("project contains editable task schemes")
            finally:
                database.close()
        return {
            "hello": hello,
            "model_library_id": status_before["model_library_id"],
            "scheme_count": len(schemes_before),
            "system_model": runtime_system_model,
            "created_project_count": len(project_ids),
            "stderr": stderr.strip(),
            "stdout_lines": len(lines),
            "backend_source": backend_source,
        }


def _verify_editable_source(root: Path) -> str:
    dispatcher = root / "backend" / "src" / "pilot_assessment" / "sidecar" / "dispatcher.py"
    original = dispatcher.read_bytes()
    marker = "0.1.0+m8b-live-source-smoke"
    old = b'backend_version: str = "0.1.0"'
    new = f'backend_version: str = "{marker}"'.encode()
    if original.count(old) != 1:
        raise PortableVerificationError("editable-source marker target is not unique")
    try:
        dispatcher.write_bytes(original.replace(old, new))
        edited_roundtrip = _sidecar_roundtrip(root)
        observed = edited_roundtrip["hello"].get("backend_version")
        if observed != marker:
            raise PortableVerificationError(
                f"sidecar did not load edited live source: observed {observed!r}"
            )
        edited_identity = edited_roundtrip["backend_source"]["loaded_identity"]
        if edited_identity.get("locally_modified") is not True:
            raise PortableVerificationError(
                "restarted sidecar did not report the edited source as locally modified"
            )
    finally:
        dispatcher.write_bytes(original)
    return marker


def _start_sidecar(root: Path, system_root: Path) -> subprocess.Popen[str]:
    environment = _restricted_environment()
    environment["PILOT_ASSESSMENT_PRODUCT_ROOT"] = str(root)
    environment["PILOT_ASSESSMENT_SYSTEM_ROOT"] = str(system_root)
    return subprocess.Popen(
        [
            str(root / "runtime" / "python" / "python.exe"),
            "-I",
            "-B",
            "-u",
            "-X",
            "utf8",
            "-m",
            "pilot_assessment.sidecar",
        ],
        cwd=root,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _sidecar_call(
    process: subprocess.Popen[str],
    request_id: str,
    method: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if process.stdin is None or process.stdout is None:
        raise PortableVerificationError("sidecar pipes are unavailable")
    request = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params or {},
    }
    process.stdin.write(json.dumps(request) + "\n")
    process.stdin.flush()
    while True:
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(process.stdout.readline)
            try:
                raw = pending.result(timeout=30)
            except FutureTimeoutError as error:
                process.kill()
                pending.result(timeout=5)
                raise PortableVerificationError(
                    f"sidecar timed out waiting for {method}"
                ) from error
        if not raw:
            stderr = "" if process.stderr is None else process.stderr.read()
            raise PortableVerificationError(
                f"sidecar exited before {method} response: {stderr.strip()}"
            )
        try:
            message = json.loads(raw)
        except json.JSONDecodeError as error:
            raise PortableVerificationError(f"sidecar emitted non-JSONL output: {raw!r}") from error
        if message.get("id") != request_id:
            continue
        if "error" in message:
            raise PortableVerificationError(
                f"sidecar {method} returned an RPC error: {message['error']}"
            )
        result = message.get("result")
        if not isinstance(result, dict):
            raise PortableVerificationError(f"sidecar {method} result is not an object")
        return result


def _close_sidecar(process: subprocess.Popen[str]) -> str:
    try:
        if process.poll() is None:
            _sidecar_call(process, "shutdown", "runtime.shutdown")
        if process.stdin is not None:
            process.stdin.close()
        process.wait(timeout=20)
    except (OSError, subprocess.SubprocessError, PortableVerificationError):
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        raise
    stderr = "" if process.stderr is None else process.stderr.read().strip()
    if process.returncode != 0:
        raise PortableVerificationError(f"sidecar exited with code {process.returncode}: {stderr}")
    return stderr


def _install_example_extension(root: Path) -> tuple[Path, bytes, Path]:
    source = root / "developer" / "examples" / "operator-extension" / "example_scalar_offset.py"
    extension_root = root / "backend" / "src" / "pilot_assessment" / "evidence" / "extensions"
    target = extension_root / "example_scalar_offset.py"
    registration = extension_root / "__init__.py"
    if target.exists():
        raise PortableVerificationError("example extension target unexpectedly already exists")
    original_registration = registration.read_bytes()
    import_anchor = b"from pilot_assessment.evidence.registry import OperatorRegistry\n"
    call_anchor = (
        b"    del registry  # The clean distribution intentionally starts with no local extensions."
    )
    if (
        original_registration.count(import_anchor) != 1
        or original_registration.count(call_anchor) != 1
    ):
        raise PortableVerificationError("extension registration template anchors are not unique")
    import_line = (
        b"from pilot_assessment.evidence.extensions.example_scalar_offset "
        b"import register_example_scalar_offset\n"
    )
    updated = original_registration.replace(import_anchor, import_anchor + import_line).replace(
        call_anchor,
        b"    register_example_scalar_offset(registry)",
    )
    shutil.copy2(source, target)
    registration.write_bytes(updated)
    return registration, original_registration, target


def _verify_dependency_tool_and_template(root: Path) -> dict[str, Any]:
    powershell = (
        Path(os.environ.get("SYSTEMROOT", r"C:\Windows"))
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "powershell.exe"
    )
    dependency_tool = root / "developer" / "tools" / "manage_python_dependencies.ps1"
    listed = subprocess.run(
        [
            str(powershell),
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(dependency_tool),
            "list",
        ],
        cwd=root,
        env=_restricted_environment(),
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=60,
    )
    if listed.returncode != 0 or "pydantic==" not in listed.stdout.casefold():
        raise PortableVerificationError(
            "private dependency list tool failed: "
            f"stdout={listed.stdout.strip()!r}, stderr={listed.stderr.strip()!r}"
        )
    template_test = subprocess.run(
        [
            str(root / "runtime" / "python" / "python.exe"),
            "-I",
            "-B",
            "-X",
            "utf8",
            str(
                root
                / "developer"
                / "examples"
                / "operator-extension"
                / "test_example_scalar_offset.py"
            ),
        ],
        cwd=root,
        env=_restricted_environment(),
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=60,
    )
    if template_test.returncode != 0:
        raise PortableVerificationError(
            "bundled operator template test failed: "
            f"stdout={template_test.stdout.strip()!r}, stderr={template_test.stderr.strip()!r}"
        )
    uv = subprocess.run(
        [str(root / "developer" / "tools" / "uv.exe"), "--version"],
        cwd=root,
        env=_restricted_environment(),
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=30,
    )
    if uv.returncode != 0 or not uv.stdout.strip().startswith("uv "):
        raise PortableVerificationError("bundled uv dependency tool did not start")
    return {
        "listed_package_count": len([line for line in listed.stdout.splitlines() if "==" in line]),
        "uv_version": uv.stdout.strip(),
        "template_test": "PASS",
    }


def _run_extension_recipe_and_assessment(root: Path) -> dict[str, Any]:
    program = r"""
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from pilot_assessment.contracts.evidence_recipe import (
    EvidenceRecipe, InputBindingKind, NodePortReference, OutputRole, PortCardinality,
    PortType, RecipeAnchor, RecipeDocumentation, RecipeEdge, RecipeGraph,
    RecipeInputBinding, RecipeLifecycle, RecipeNode, RecipeOutputBinding,
    RecipeScientificStatus, RecipeScoring, RecipeUiMetadata, ScoringMode,
    TemporalSemantics,
)
from pilot_assessment.contracts.run import RunPurpose
from pilot_assessment.evidence.compiler import compile_recipe
from pilot_assessment.evidence.executor import execute_recipe
from pilot_assessment.ingestion.profiles import CsvProfile, load_builtin_profiles
from pilot_assessment.runtime import ProjectApplication, SystemApplication
from pilot_assessment.synthetic import generate_synthetic_bundle

product_root = Path(sys.argv[1]).resolve()
work_root = Path(sys.argv[2]).resolve()
now = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
system = SystemApplication.open_or_create(
    work_root / "system",
    model_library_id="model-library.m8b2-extension",
    product_root=product_root,
    clock=lambda: now,
)
application = ProjectApplication.create(
    work_root / "project",
    system=system,
    project_id="project.m8b2-extension",
    name="M8B-2 extension verification",
    created_at=now,
    clock=lambda: now,
)
try:
    number_type = PortType(
        value_type="number",
        cardinality=PortCardinality.ONE,
        temporal_semantics=TemporalSemantics.TIMELESS,
        unit=None,
    )
    recipe = EvidenceRecipe(
        recipe_id="recipe.m8b2-extension",
        recipe_version=1,
        anchor=RecipeAnchor(
            anchor_id="M8B2-EXAMPLE",
            name="M8B-2 extension example",
            description="Engineering-only release verification evidence.",
            lifecycle=RecipeLifecycle.ACTIVE,
            scientific_status=RecipeScientificStatus.EXPERT_DEFINED,
        ),
        inputs=(RecipeInputBinding(
            binding_id="input.micro-value",
            kind=InputBindingKind.SEMANTIC,
            source_id="micro.value",
            name="Micro value",
            declared_type=number_type,
            selector={},
        ),),
        graph=RecipeGraph(
            nodes=(
                RecipeNode(
                    node_id="input",
                    operator_id="input.binding",
                    operator_version="0.1.0",
                    input_binding_id="input.micro-value",
                    parameters={},
                ),
                RecipeNode(
                    node_id="offset",
                    operator_id="extension.example.scalar-offset",
                    operator_version="0.1.0",
                    input_binding_id=None,
                    parameters={"offset": 0.75},
                ),
            ),
            edges=(RecipeEdge(
                edge_id="edge.input-offset",
                source=NodePortReference(node_id="input", port_id="value"),
                target=NodePortReference(node_id="offset", port_id="value"),
                target_slot_id=None,
            ),),
        ),
        outputs=(RecipeOutputBinding(
            output_id="offset-value",
            role=OutputRole.PRIMARY_VALUE,
            name="Offset value",
            source=NodePortReference(node_id="offset", port_id="value"),
            unit=None,
        ),),
        scoring=RecipeScoring(
            mode=ScoringMode.ORDERED_DAU,
            input=NodePortReference(node_id="offset", port_id="value"),
            parameters={
                "direction": "higher_is_better",
                "desired_boundary": 2.5,
                "adequate_boundary": 1.5,
                "likelihood_strength": 0.8,
            },
            custom_operator_id=None,
            custom_operator_version=None,
        ),
        documentation=RecipeDocumentation(
            summary="Engineering-only extension execution check.",
            assumptions=(),
            parameter_notes={},
            references=(),
        ),
        ui=RecipeUiMetadata(groups=(), preferred_layout={}),
    )
    compiled = compile_recipe(recipe, application.operator_registry)
    executed = execute_recipe(
        compiled,
        application.operator_registry,
        binding_values={"input.micro-value": 2.0},
        trace_node_ids=("offset",),
    )

    source_csv = work_root / "micro.csv"
    profile = load_builtin_profiles()["cranfield-simulator-combined-csv-raw-v0.1"]
    if not isinstance(profile, CsvProfile):
        raise RuntimeError("combined simulator profile is unavailable")
    headers = [column.source_header for column in profile.columns]
    with source_csv.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(headers)
        for index in range(201):
            time_s = index / 100.0
            velocity_x = 0.1 * time_s
            velocity_y = -0.2 * time_s
            velocity_z = 0.05 * time_s
            values = ["0" for _ in headers]
            updates = {
                "Simulation time": f"{time_s:.2f}",
                "Xe m": str(0.75 * time_s),
                "Ze m": "-31.668",
                "Ground Elevation m": "21.008",
                "V_ex m/s": str(velocity_x),
                "V_ey m/s": str(velocity_y),
                "V_ez m/s": str(velocity_z),
                "V_ex kts": str(velocity_x * 1.9438444924406048),
                "V_ey kts": str(velocity_y * 1.9438444924406048),
                "V_ez kts": str(velocity_z * 1.9438444924406048),
                "V_bx m/s": str(velocity_x),
                "V_by m/s": str(velocity_y),
                "V_bz m/s": str(velocity_z),
                "psi deg": "270",
                "Pilot Lon": str(-100.0 * index / 200),
            }
            for header, value in updates.items():
                values[headers.index(header)] = value
            values[headers.index("Control_Mode")] = "1"
            values[headers.index("Time Delay s")] = "0.2"
            values[headers.index("Lon Frequency rad/s")] = "8"
            values[headers.index("Long Damping")] = "0.8"
            writer.writerow(values)
    bundle = generate_synthetic_bundle(source_csv, work_root / "micro-bundle", seed=20260721)
    imported = application.sessions.import_bundle(
        bundle,
        transaction_id="tx.m8b2-extension-session",
        imported_by="system.m8b2-verifier",
    )
    scheme = application.current_model.get_scheme(application.current_starter_scheme_id)
    preflight = application.current_preflight.prepare(
        session_revision_id=imported.revision.session_revision_id,
        scheme_id=scheme.scheme_id,
        purpose=RunPurpose.ASSESSMENT,
        runtime_parameters={},
    )
    if preflight.technical_disposition.value != "ready":
        raise RuntimeError(f"micro assessment preflight is not ready: {preflight.issues}")
    authorization_codes = [diagnostic.code for diagnostic in preflight.diagnostics]
    if preflight.formal_run_authorized is not False:
        raise RuntimeError("engineering Assessment unexpectedly became formally authorized")
    if "run.assessment_not_authorized" not in authorization_codes:
        raise RuntimeError("engineering Assessment omitted its authorization warning")
    run = application.current_preflight.create_run(
        preflight.preflight_id,
        run_id="run.m8b2-extension",
        expected_scheme_revision=scheme.semantic_revision,
        requested_at=now,
    )
    application.coordinator.enqueue(run.run_id)
    terminal = application.coordinator.wait(run.run_id, timeout=60)
    if terminal.state.value != "completed":
        events = [
            {
                "state": event.state.value,
                "stage": event.stage.value,
                "message": event.message,
                "details": event.details,
            }
            for event in application.runs.list_events(run.run_id)
        ]
        raise RuntimeError(
            f"micro assessment run ended as {terminal.state.value}: "
            + json.dumps(events, default=str)
        )
    source_ref = run.snapshot.source_snapshot_ref
    if source_ref is None:
        raise RuntimeError("run snapshot omitted source artifact")
    source_artifact = application.artifacts.get(source_ref.artifact_id)
    print(json.dumps({
        "operator_count": len(application.operator_registry.catalog()),
        "recipe_value": executed.outputs["offset-value"],
        "recipe_state": str(executed.scoring_outputs["state"]),
        "recipe_trace_operator": executed.traces[1].operator_id,
        "run_state": terminal.state.value,
        "run_purpose": run.snapshot.purpose.value,
        "formal_run_authorized": preflight.formal_run_authorized,
        "authorization_warning": "run.assessment_not_authorized" in authorization_codes,
        "source_identity": run.snapshot.backend_source_identity.identity_sha256,
        "source_artifact_id": source_artifact.artifact_id,
        "source_artifact_sha256": source_artifact.sha256,
        "source_operator_count": (
            run.snapshot.backend_source_identity.operator_catalog.operator_count
        ),
        "session_source_rows": 201,
    }, sort_keys=True))
finally:
    application.close()
    system.close()
"""
    with tempfile.TemporaryDirectory(prefix="pilot-assessment-m8b2-extension-run-") as temporary:
        environment = _restricted_environment()
        environment["PILOT_ASSESSMENT_PRODUCT_ROOT"] = str(root)
        completed = subprocess.run(
            [
                str(root / "runtime" / "python" / "python.exe"),
                "-I",
                "-B",
                "-X",
                "utf8",
                "-c",
                program,
                str(root),
                temporary,
            ],
            cwd=root,
            env=environment,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=120,
        )
    if completed.returncode != 0:
        raise PortableVerificationError(
            "extension recipe/run vertical slice failed: "
            f"stdout={completed.stdout.strip()!r}, stderr={completed.stderr.strip()!r}"
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise PortableVerificationError(
            f"extension recipe/run output is not JSON: {completed.stdout!r}"
        ) from error
    if not isinstance(payload, dict):
        raise PortableVerificationError("extension recipe/run result is not an object")
    return payload


def _verify_operator_extension(root: Path) -> dict[str, Any]:
    dependency_tool = _verify_dependency_tool_and_template(root)
    registration: Path | None = None
    original_registration: bytes | None = None
    extension_target: Path | None = None
    old_process: subprocess.Popen[str] | None = None
    new_process: subprocess.Popen[str] | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="pilot-assessment-m8b2-old-sidecar-") as temporary:
            old_process = _start_sidecar(root, Path(temporary) / "system")
            hello = _sidecar_call(
                old_process,
                "hello",
                "runtime.hello",
                {
                    "protocol_version": "1.0",
                    "supported_protocols": ["1.0"],
                    "client": {"name": "m8b2-extension-verifier", "version": "0.1.0"},
                },
            )
            if hello.get("state") != "ready":
                raise PortableVerificationError("pre-edit extension sidecar did not become ready")
            before = _sidecar_call(old_process, "catalog-before", "operator.catalog.list")
            if len(before.get("operators", [])) != 45:
                raise PortableVerificationError(
                    "clean operator catalog does not contain 45 entries"
                )

            registration, original_registration, extension_target = _install_example_extension(root)
            stale_status = _sidecar_call(old_process, "status-stale", "runtime.status")
            backend_source = stale_status.get("backend_source")
            if not isinstance(backend_source, dict) or not backend_source.get(
                "runtime_restart_required"
            ):
                raise PortableVerificationError(
                    "running sidecar did not require restart after extension source changed"
                )
            _close_sidecar(old_process)
            old_process = None

        with tempfile.TemporaryDirectory(prefix="pilot-assessment-m8b2-new-sidecar-") as temporary:
            new_process = _start_sidecar(root, Path(temporary) / "system")
            _sidecar_call(
                new_process,
                "hello",
                "runtime.hello",
                {
                    "protocol_version": "1.0",
                    "supported_protocols": ["1.0"],
                    "client": {"name": "m8b2-extension-verifier", "version": "0.1.0"},
                },
            )
            status = _sidecar_call(new_process, "status", "runtime.status")
            catalog = _sidecar_call(new_process, "catalog", "operator.catalog.list")
            _close_sidecar(new_process)
            new_process = None

        operators = catalog.get("operators", [])
        extension = next(
            (
                item
                for item in operators
                if item.get("operator_id") == "extension.example.scalar-offset"
                and item.get("implementation_version") == "0.1.0"
            ),
            None,
        )
        if len(operators) != 46 or extension is None:
            raise PortableVerificationError("restarted catalog omitted the example extension")
        if extension.get("implementation_source") != "trusted_extension":
            raise PortableVerificationError("example extension has the wrong implementation source")
        schema = extension.get("parameter_schema")
        if not isinstance(schema, dict) or schema.get("required") != ["offset"]:
            raise PortableVerificationError("example extension parameter schema was not exposed")
        backend_source = status.get("backend_source")
        if not isinstance(backend_source, dict):
            raise PortableVerificationError("restarted extension sidecar omitted source provenance")
        loaded = backend_source.get("loaded_identity")
        if (
            not isinstance(loaded, dict)
            or loaded.get("locally_modified") is not True
            or backend_source.get("runtime_restart_required") is not False
        ):
            raise PortableVerificationError("restarted extension source identity is inconsistent")

        vertical = _run_extension_recipe_and_assessment(root)
        if (
            vertical.get("operator_count") != 46
            or vertical.get("source_operator_count") != 46
            or vertical.get("recipe_value") != 2.75
            or vertical.get("recipe_state") != "desired"
            or vertical.get("recipe_trace_operator") != "extension.example.scalar-offset"
            or vertical.get("run_state") != "completed"
            or vertical.get("run_purpose") != "assessment"
            or vertical.get("formal_run_authorized") is not False
            or vertical.get("authorization_warning") is not True
            or vertical.get("source_identity") != loaded.get("identity_sha256")
        ):
            raise PortableVerificationError(
                f"extension recipe/run result is inconsistent: {vertical}"
            )
        return {
            "dependency_tool": dependency_tool,
            "old_process_restart_required": True,
            "operator_id": extension["operator_id"],
            "operator_count": len(operators),
            "parameter_schema": schema,
            "loaded_source_identity": loaded["identity_sha256"],
            "recipe_and_run": vertical,
        }
    finally:
        for process in (old_process, new_process):
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=5)
        if registration is not None and original_registration is not None:
            registration.write_bytes(original_registration)
        if extension_target is not None and extension_target.exists():
            extension_target.unlink()


def _window_for_process(process_id: int) -> int | None:
    if os.name != "nt":
        return None
    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(window: int, _parameter: int) -> bool:
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(window, ctypes.byref(owner))
        if owner.value == process_id and user32.IsWindowVisible(window):
            found.append(window)
            return False
        return True

    user32.EnumWindows(callback, 0)
    return found[0] if found else None


def _child_processes(parent_id: int) -> list[int]:
    if os.name != "nt":
        return []

    class ProcessEntry32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.windll.kernel32
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot in (0, -1):
        return []
    entry = ProcessEntry32()
    entry.dwSize = ctypes.sizeof(ProcessEntry32)
    children: list[int] = []
    try:
        success = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while success:
            if entry.th32ParentProcessID == parent_id:
                children.append(int(entry.th32ProcessID))
            success = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return children


def _descendant_processes(parent_id: int) -> set[int]:
    descendants: set[int] = set()
    pending = [parent_id]
    while pending:
        current = pending.pop()
        for child in _child_processes(current):
            if child in descendants:
                continue
            descendants.add(child)
            pending.append(child)
    return descendants


def _process_image(process_id: int) -> Path | None:
    if os.name != "nt":
        return None
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, process_id)
    if not handle:
        return None
    size = wintypes.DWORD(32768)
    buffer = ctypes.create_unicode_buffer(size.value)
    try:
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return None
        return Path(buffer.value).resolve()
    finally:
        kernel32.CloseHandle(handle)


def _assert_no_tcp_listener(process_ids: set[int]) -> None:
    netstat = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32" / "netstat.exe"
    completed = subprocess.run(
        [str(netstat), "-ano", "-p", "tcp"],
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=15,
    )
    if completed.returncode != 0:
        raise PortableVerificationError(f"netstat failed: {completed.stderr.strip()}")
    listeners = []
    for line in completed.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 5 and fields[0].upper() == "TCP" and fields[-2].upper() == "LISTENING":
            try:
                process_id = int(fields[-1])
            except ValueError:
                continue
            if process_id in process_ids:
                listeners.append(line.strip())
    if listeners:
        raise PortableVerificationError(f"product process opened TCP listeners: {listeners}")


def _launch_desktop(root: Path, timeout: float) -> dict[str, Any]:
    executable = root / "PilotAssessment.exe"
    process = subprocess.Popen(
        [str(executable)],
        cwd=root,
        env=_restricted_environment(),
    )
    window: int | None = None
    desktop_id: int | None = None
    descendant_ids: set[int] = set()
    descendant_images: dict[int, Path] = {}
    packaged_sidecars: list[int] = []
    expected_desktop = (root / "app" / "PilotAssessment.Desktop.exe").resolve()
    expected_python = (root / "runtime" / "python" / "python.exe").resolve()
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise PortableVerificationError(
                    f"desktop process exited before verification with code {process.returncode}"
                )
            descendant_ids = _descendant_processes(process.pid)
            descendant_images = {
                process_id: image
                for process_id in descendant_ids
                if (image := _process_image(process_id)) is not None
            }
            for process_id in descendant_ids:
                if descendant_images.get(process_id) == expected_desktop:
                    desktop_id = process_id
                    break
            window = _window_for_process(desktop_id) if desktop_id is not None else None
            packaged_sidecars = [
                process_id
                for process_id, image in descendant_images.items()
                if image == expected_python
            ]
            if window and packaged_sidecars:
                break
            time.sleep(0.25)
        if not window:
            raise PortableVerificationError("desktop main window did not appear")
        if not packaged_sidecars:
            raise PortableVerificationError(
                f"desktop did not start packaged Python sidecar; descendants={descendant_images}"
            )
        _assert_no_tcp_listener({process.pid, *descendant_ids})
        return {
            "launcher_pid": process.pid,
            "desktop_pid": desktop_id,
            "window_handle": window,
            "packaged_sidecar_pids": packaged_sidecars,
        }
    finally:
        if process.poll() is None and window:
            ctypes.windll.user32.PostMessageW(window, 0x0010, 0, 0)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def verify(
    root: Path,
    *,
    editable_source: bool,
    operator_extension: bool,
    launch_desktop: bool,
    desktop_timeout: float,
) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise PortableVerificationError(f"package root does not exist: {root}")
    root_surface = _required_layout(root)
    release_identity = _verify_release_identity(root)
    checksum_count = _verify_checksums(root)
    documentation = _verify_documentation(root)
    source_count = _verify_source_baseline(root)
    system_model = _verify_system_model_baseline(root)
    _verify_content_policy(root)
    imported = _run_private_import(root)
    sidecar = _sidecar_roundtrip(root)
    _verify_runtime_system_model(sidecar["system_model"], system_model)
    edit_marker = _verify_editable_source(root) if editable_source else None
    extension = _verify_operator_extension(root) if operator_extension else None
    if editable_source or operator_extension:
        _verify_checksums(root, ignore_mutable_system=True)
        _verify_source_baseline(root)
    desktop = _launch_desktop(root, desktop_timeout) if launch_desktop else None
    return {
        "package_root": str(root),
        "root_surface": root_surface,
        "release_identity": release_identity,
        "checksummed_files": checksum_count,
        "documentation": documentation,
        "backend_source_files": source_count,
        "system_model": system_model,
        "private_python_import": imported,
        "sidecar": sidecar,
        "editable_source_marker": edit_marker,
        "operator_extension": extension,
        "desktop": desktop,
        "status": "PASS",
    }


def main() -> int:
    args = _arguments()
    try:
        result = verify(
            args.package_root,
            editable_source=args.verify_editable_source,
            operator_extension=args.verify_operator_extension,
            launch_desktop=args.launch_desktop,
            desktop_timeout=args.desktop_timeout,
        )
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        print(f"Pilot Assessment portable verification failed: {error}", file=sys.stderr)
        return 1
    except PortableVerificationError as error:
        print(f"Pilot Assessment portable verification failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
