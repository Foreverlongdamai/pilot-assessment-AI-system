"""Hash and register already captured release-candidate screenshots."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from manual_common import (
    MANUAL_ROOT,
    DocumentationError,
    read_json,
    result_payload,
    sha256_file,
    write_json,
)
from PIL import Image

MANIFEST_PATH = MANUAL_ROOT / "assets" / "screenshots" / "manifest.json"
SHA256 = re.compile(r"[0-9a-f]{64}")


def _utc_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise DocumentationError("captured-at must be an ISO-8601 timestamp") from error
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise DocumentationError("captured-at must use UTC offset Z")
    return parsed.isoformat().replace("+00:00", "Z")


def register(
    *,
    manifest_path: Path,
    manual_root: Path,
    ui_source_tree_sha256: str,
    captured_at: str,
    reviewer: str,
    privacy_reviewed: bool,
) -> dict[str, Any]:
    if not SHA256.fullmatch(ui_source_tree_sha256):
        raise DocumentationError("ui-source-tree-sha256 must be a lowercase SHA-256")
    timestamp = _utc_timestamp(captured_at)
    if not reviewer.strip():
        raise DocumentationError("reviewer must not be blank")
    if not privacy_reviewed:
        raise DocumentationError(
            "registration requires an explicit privacy review of every screenshot"
        )
    manifest = read_json(manifest_path)
    entries = manifest.get("screenshots")
    if not isinstance(entries, list) or len(entries) != 10:
        raise DocumentationError("screenshot manifest must define exactly ten assets")
    registered: list[dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            raise DocumentationError("screenshot entry must be an object")
        relative = item.get("path")
        if not isinstance(relative, str):
            raise DocumentationError("screenshot entry path is missing")
        path = (manual_root / relative).resolve()
        if manual_root.resolve() not in path.parents or not path.is_file():
            raise DocumentationError(f"screenshot file is missing or outside manuals: {relative}")
        try:
            with Image.open(path) as image:
                if image.format != "PNG":
                    raise DocumentationError(f"screenshot is not PNG: {relative}")
                width, height = image.size
                image.verify()
        except OSError as error:
            raise DocumentationError(f"cannot inspect screenshot {relative}: {error}") from error
        if width < 800 or height < 500:
            raise DocumentationError(f"screenshot resolution is too small: {relative}")
        item.update(
            {
                "status": "release-candidate",
                "sha256": sha256_file(path),
                "width": width,
                "height": height,
                "captured_at": timestamp,
                "ui_source_tree_sha256": ui_source_tree_sha256,
                "privacy_review": {
                    "status": "passed",
                    "reviewer": reviewer.strip(),
                    "reviewed_at": timestamp,
                },
            }
        )
        registered.append(
            {
                "screenshot_id": item["screenshot_id"],
                "language": item["language"],
                "path": relative,
                "sha256": item["sha256"],
                "width": width,
                "height": height,
            }
        )
    manifest["ui_source_tree_sha256"] = ui_source_tree_sha256
    write_json(manifest_path, manifest)
    return {
        "manifest": str(manifest_path),
        "ui_source_tree_sha256": ui_source_tree_sha256,
        "registered": registered,
        "status": "PASS",
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ui-source-tree-sha256", required=True)
    parser.add_argument("--captured-at", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--privacy-reviewed", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    try:
        result = register(
            manifest_path=MANIFEST_PATH,
            manual_root=MANUAL_ROOT,
            ui_source_tree_sha256=args.ui_source_tree_sha256,
            captured_at=args.captured_at,
            reviewer=args.reviewer,
            privacy_reviewed=args.privacy_reviewed,
        )
    except (DocumentationError, OSError, ValueError) as error:
        print(f"screenshot registration failed: {error}", file=sys.stderr)
        return 1
    print(result_payload(**result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
