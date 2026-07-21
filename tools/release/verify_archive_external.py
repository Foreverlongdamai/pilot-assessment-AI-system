"""Extract a release ZIP outside the repository and verify it with its private Python."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
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
    parser.add_argument("archive", nargs="?", type=Path)
    parser.add_argument("--dist", type=Path, help="Release ZIP to verify.")
    parser.add_argument("--delivery", type=Path)
    parser.add_argument("--launch-desktop", action="store_true")
    parser.add_argument("--verify-editable-source", action="store_true")
    parser.add_argument("--verify-operator-extension", action="store_true")
    parser.add_argument("--restricted-path", action="store_true")
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_outer_delivery(archive: Path, delivery_path: Path) -> dict[str, object]:
    hash_path = Path(f"{archive}.sha256")
    if not delivery_path.is_file() or not hash_path.is_file():
        raise ExternalArchiveVerificationError("delivery JSON or independent ZIP hash is missing")
    archive_sha256 = _sha256(archive)
    hash_line = hash_path.read_text(encoding="utf-8").strip()
    if hash_line != f"{archive_sha256}  {archive.name}":
        raise ExternalArchiveVerificationError("independent ZIP hash file differs")
    delivery = json.loads(delivery_path.read_text(encoding="utf-8"))
    expected_identity = {
        "schema_version": "pilot-assessment-delivery-v1",
        "product_version": "0.1.0",
        "release_channel": "release-candidate",
        "user_acceptance": "pending",
        "build_kind": "m8e-release-candidate",
    }
    if {key: delivery.get(key) for key in expected_identity} != expected_identity:
        raise ExternalArchiveVerificationError("outer delivery candidate identity differs")
    candidate = delivery.get("candidate")
    release_label = delivery.get("release_label")
    if not isinstance(candidate, str) or re.fullmatch(r"rc\.[1-9][0-9]*", candidate) is None:
        raise ExternalArchiveVerificationError("outer delivery candidate sequence is invalid")
    if release_label != f"v{expected_identity['product_version']}-{candidate}":
        raise ExternalArchiveVerificationError("outer delivery release label differs")
    if (
        archive.stem
        != f"PilotAssessment-{expected_identity['product_version']}-{candidate}-win-x64"
    ):
        raise ExternalArchiveVerificationError("archive name differs from candidate identity")
    archive_record = delivery.get("archive")
    expected_archive = {
        "file": archive.name,
        "bytes": archive.stat().st_size,
        "sha256": archive_sha256,
        "sha256_file": hash_path.name,
    }
    if archive_record != expected_archive:
        raise ExternalArchiveVerificationError("outer delivery ZIP facts differ")
    return delivery


def _scan_archive_content(archive: Path) -> dict[str, int]:
    forbidden_directories = {
        ".git",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "projects",
        "sessions",
        "results",
        "local_data",
    }
    private_path = re.compile(
        rb"(?:[a-z]:[\\/]+users[\\/]+[^\\/\x00]+|/users/[^/\x00]+)",
        re.IGNORECASE,
    )
    docx_count = 0
    xml_count = 0
    with zipfile.ZipFile(archive) as package:
        names = [member.filename for member in package.infolist()]
        for name in names:
            parts = [part.casefold() for part in Path(name).parts]
            if any(part in forbidden_directories for part in parts):
                raise ExternalArchiveVerificationError(f"forbidden archive directory: {name}")
            if name.casefold().endswith((".pdb", ".pyc", ".pyo", ".sqlite3-wal", ".sqlite3-shm")):
                raise ExternalArchiveVerificationError(f"forbidden archive file: {name}")
            if not name.casefold().endswith(".docx"):
                continue
            docx_count += 1
            with zipfile.ZipFile(io.BytesIO(package.read(name))) as document:
                for member in document.infolist():
                    if not member.filename.casefold().endswith(".xml"):
                        continue
                    xml_count += 1
                    if private_path.search(document.read(member)):
                        raise ExternalArchiveVerificationError(
                            f"private user-home path in DOCX XML: {name}!{member.filename}"
                        )
    if docx_count != 24:
        raise ExternalArchiveVerificationError(
            f"release archive must contain 24 DOCX manuals, got {docx_count}"
        )
    return {"docx_files": docx_count, "docx_xml_files_scanned": xml_count}


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
    operator_extension: bool,
    restricted_path: bool,
    delivery_path: Path | None = None,
) -> dict[str, object]:
    archive = archive.resolve()
    if not archive.is_file():
        raise ExternalArchiveVerificationError(f"release ZIP is missing: {archive}")
    delivery_path = (
        delivery_path.resolve()
        if delivery_path is not None
        else archive.with_suffix(".delivery.json")
    )
    delivery = _verify_outer_delivery(archive, delivery_path)
    privacy_scan = _scan_archive_content(archive)
    temp_parent = Path(tempfile.gettempdir()).resolve()
    temp_root = Path(tempfile.mkdtemp(prefix="PilotAssessment-M8E-external-", dir=temp_parent))
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
        if operator_extension:
            command.append("--verify-operator-extension")
        if launch_desktop:
            command.extend(["--launch-desktop", "--desktop-timeout", "45"])
        environment = os.environ.copy()
        if restricted_path:
            environment["PATH"] = str(
                Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32"
            )
        environment.pop("PYTHONHOME", None)
        environment.pop("PYTHONPATH", None)
        completed = subprocess.run(
            command,
            cwd=product_root,
            env=environment,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=600,
        )
        if completed.returncode != 0:
            raise ExternalArchiveVerificationError(
                f"packaged verifier failed:\n{completed.stdout}\n{completed.stderr}"
            )
        packaged = json.loads(completed.stdout)
        packaged_identity = packaged.get("release_identity")
        if not isinstance(packaged_identity, dict) or any(
            packaged_identity.get(key) != delivery.get(key)
            for key in ("product_version", "release_label", "candidate", "user_acceptance")
        ):
            raise ExternalArchiveVerificationError(
                "packaged release identity differs from outer delivery JSON"
            )
        return {
            "archive_file": archive.name,
            "archive_sha256": delivery["archive"]["sha256"],
            "delivery_file": delivery_path.name,
            "restricted_path": restricted_path,
            "privacy_scan": privacy_scan,
            "packaged_verifier": packaged,
            "status": "PASS",
        }
    finally:
        if temp_root.is_relative_to(temp_parent):
            shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    args = _arguments()
    archive = args.dist or args.archive
    if archive is None or (args.dist is not None and args.archive is not None):
        print("M8E external archive verification requires exactly one archive", file=sys.stderr)
        return 2
    try:
        result = verify_archive(
            archive,
            launch_desktop=args.launch_desktop,
            editable_source=args.verify_editable_source,
            operator_extension=args.verify_operator_extension,
            restricted_path=args.restricted_path,
            delivery_path=args.delivery,
        )
    except (OSError, ValueError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        print(f"M8E external archive verification failed: {error}", file=sys.stderr)
        return 1
    except ExternalArchiveVerificationError as error:
        print(f"M8E external archive verification failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
