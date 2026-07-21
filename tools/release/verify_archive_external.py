"""Extract a release ZIP outside the repository and verify it with its private Python."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


class ExternalArchiveVerificationError(RuntimeError):
    """Raised when the repository-external archive verification cannot complete."""


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--launch-desktop", action="store_true")
    parser.add_argument("--verify-editable-source", action="store_true")
    return parser.parse_args()


def _safe_extract(archive: Path, destination: Path) -> None:
    destination_root = destination.resolve()
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            output = (destination / member.filename).resolve()
            if not output.is_relative_to(destination_root):
                raise ExternalArchiveVerificationError(f"unsafe ZIP entry: {member.filename}")
        package.extractall(destination)


def verify_archive(
    archive: Path,
    *,
    launch_desktop: bool,
    editable_source: bool,
) -> dict[str, object]:
    archive = archive.resolve()
    if not archive.is_file():
        raise ExternalArchiveVerificationError(f"release ZIP is missing: {archive}")
    temp_parent = Path(tempfile.gettempdir()).resolve()
    temp_root = Path(tempfile.mkdtemp(prefix="PilotAssessment-M8B0-external-", dir=temp_parent))
    temp_root = temp_root.resolve()
    if not temp_root.is_relative_to(temp_parent):
        raise ExternalArchiveVerificationError(f"unsafe temporary path: {temp_root}")
    try:
        _safe_extract(archive, temp_root)
        product_roots = [path for path in temp_root.iterdir() if path.is_dir()]
        if len(product_roots) != 1:
            raise ExternalArchiveVerificationError(
                f"release ZIP must contain one product root: {product_roots}"
            )
        product_root = product_roots[0]
        python = product_root / "runtime" / "python" / "python.exe"
        verifier = product_root / "developer" / "build" / "release" / "verify_portable.py"
        command = [
            str(python),
            "-I",
            "-B",
            "-X",
            "utf8",
            str(verifier),
            str(product_root),
        ]
        if editable_source:
            command.append("--verify-editable-source")
        if launch_desktop:
            command.extend(["--launch-desktop", "--desktop-timeout", "45"])
        environment = os.environ.copy()
        environment["PATH"] = str(Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32")
        completed = subprocess.run(
            command,
            cwd=product_root,
            env=environment,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=180,
        )
        if completed.returncode != 0:
            raise ExternalArchiveVerificationError(
                f"packaged verifier failed:\n{completed.stdout}\n{completed.stderr}"
            )
        return {
            "archive": str(archive),
            "external_root": str(product_root),
            "packaged_verifier": json.loads(completed.stdout),
            "status": "PASS",
        }
    finally:
        if temp_root.is_relative_to(temp_parent):
            shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    args = _arguments()
    try:
        result = verify_archive(
            args.archive,
            launch_desktop=args.launch_desktop,
            editable_source=args.verify_editable_source,
        )
    except (OSError, ValueError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        print(f"M8B-0 external archive verification failed: {error}", file=sys.stderr)
        return 1
    except ExternalArchiveVerificationError as error:
        print(f"M8B-0 external archive verification failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
