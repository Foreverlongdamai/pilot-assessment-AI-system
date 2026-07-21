"""Verify a Pilot Assessment portable product directory without dev dependencies."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any

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
USER_OWNED_SYSTEM_TABLES = (
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


def _required_layout(root: Path) -> None:
    required_files = [
        "PilotAssessment.Desktop.exe",
        "runtime/python/python.exe",
        "runtime/python/python311._pth",
        "backend/src/pilot_assessment/__init__.py",
        "backend/src/pilot_assessment/sidecar/__main__.py",
        "backend/pyproject.toml",
        "backend/uv.lock",
        "manifest/release-manifest.json",
        "manifest/source-baseline.json",
        "manifest/system-model-baseline.json",
        "manifest/checksums.sha256",
        "manifest/sbom.spdx.json",
        "README.txt",
        "system/system.json",
        "system/model-library.sqlite3",
        "system/staging/model-edit/workspace.sqlite3",
    ]
    missing = [relative for relative in required_files if not (root / relative).is_file()]
    if missing:
        raise PortableVerificationError(f"portable layout is incomplete: {missing}")
    if not (root / "runtime" / "site-packages").is_dir():
        raise PortableVerificationError("runtime/site-packages is missing")


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


def _verify_system_model_baseline(root: Path) -> dict[str, Any]:
    baseline = json.loads(
        (root / "manifest" / "system-model-baseline.json").read_text(encoding="utf-8")
    )
    if baseline.get("schema_version") != "pilot-assessment-system-model-baseline-v1":
        raise PortableVerificationError("system model baseline version is unsupported")
    actual_system_files = {
        path.relative_to(root).as_posix() for path in (root / "system").rglob("*") if path.is_file()
    }
    if actual_system_files != SYSTEM_MODEL_FILES:
        raise PortableVerificationError(
            f"starter system file set is invalid: {sorted(actual_system_files)}"
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
        raise PortableVerificationError("starter canonical model database hash differs")
    if _sha256(edit_path) != baseline["edit_workspace"]["sha256"]:
        raise PortableVerificationError("starter edit workspace database hash differs")

    canonical = sqlite3.connect(canonical_path)
    edit = sqlite3.connect(edit_path)
    try:
        model_identity, node_count, scheme_count = _model_identity(canonical)
        metadata = canonical.execute(
            "SELECT model_library_id, clean_shutdown FROM system_metadata WHERE singleton = 1"
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
    finally:
        canonical.close()
        edit.close()

    if metadata is None or state is None:
        raise PortableVerificationError("starter system metadata or edit state is missing")
    model_library_id = str(metadata[0])
    if not (
        model_library_id == baseline["model_library_id"] == locator.get("model_library_id")
        and str(state[0]) == model_library_id
    ):
        raise PortableVerificationError("starter model-library identities differ")
    if int(metadata[1]) != 1 or int(state[3]) != 0 or int(state[4]) != 0:
        raise PortableVerificationError("starter system is not cleanly closed and edit-clean")
    if (
        str(state[1]) != baseline["edit_workspace"]["base_fingerprint"]
        or str(state[2]) != baseline["edit_workspace"]["baseline_state_hash"]
        or baseline["edit_workspace"].get("dirty") is not False
    ):
        raise PortableVerificationError("starter edit baseline identity differs")
    if (
        model_identity != baseline["model_identity_sha256"]
        or node_count != baseline["node_count"]
        or scheme_count != baseline["scheme_count"]
    ):
        raise PortableVerificationError("starter system model identity differs")
    if user_counts != baseline["user_owned_row_counts"] or any(user_counts.values()):
        raise PortableVerificationError(f"starter system contains user-owned rows: {user_counts}")
    return {
        "model_library_id": model_library_id,
        "model_identity_sha256": model_identity,
        "node_count": node_count,
        "scheme_count": scheme_count,
        "edit_session_dirty": False,
    }


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
            "starter_scheme_count": len(schemes_before),
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
    executable = root / "PilotAssessment.Desktop.exe"
    process = subprocess.Popen(
        [str(executable)],
        cwd=root,
        env=_restricted_environment(),
    )
    window: int | None = None
    child_ids: list[int] = []
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise PortableVerificationError(
                    f"desktop process exited before verification with code {process.returncode}"
                )
            window = _window_for_process(process.pid)
            child_ids = _child_processes(process.pid)
            if window and child_ids:
                break
            time.sleep(0.25)
        if not window:
            raise PortableVerificationError("desktop main window did not appear")
        expected_python = (root / "runtime" / "python" / "python.exe").resolve()
        child_images = {
            process_id: image
            for process_id in child_ids
            if (image := _process_image(process_id)) is not None
        }
        packaged_sidecars = [
            process_id for process_id, image in child_images.items() if image == expected_python
        ]
        if not packaged_sidecars:
            raise PortableVerificationError(
                f"desktop did not start packaged Python sidecar; children={child_images}"
            )
        _assert_no_tcp_listener({process.pid, *child_ids})
        return {
            "desktop_pid": process.pid,
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
    launch_desktop: bool,
    desktop_timeout: float,
) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise PortableVerificationError(f"package root does not exist: {root}")
    _required_layout(root)
    checksum_count = _verify_checksums(root)
    source_count = _verify_source_baseline(root)
    system_model = _verify_system_model_baseline(root)
    _verify_content_policy(root)
    imported = _run_private_import(root)
    sidecar = _sidecar_roundtrip(root)
    edit_marker = _verify_editable_source(root) if editable_source else None
    if editable_source:
        _verify_checksums(root, ignore_mutable_system=True)
        _verify_source_baseline(root)
    desktop = _launch_desktop(root, desktop_timeout) if launch_desktop else None
    return {
        "package_root": str(root),
        "checksummed_files": checksum_count,
        "backend_source_files": source_count,
        "system_model": system_model,
        "private_python_import": imported,
        "sidecar": sidecar,
        "editable_source_marker": edit_marker,
        "desktop": desktop,
        "status": "PASS",
    }


def main() -> int:
    args = _arguments()
    try:
        result = verify(
            args.package_root,
            editable_source=args.verify_editable_source,
            launch_desktop=args.launch_desktop,
            desktop_timeout=args.desktop_timeout,
        )
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        print(f"M8B portable verification failed: {error}", file=sys.stderr)
        return 1
    except PortableVerificationError as error:
        print(f"M8B portable verification failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
