"""Calculate the deterministic identity of the tracked WinUI source tree."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

from manual_common import REPOSITORY_ROOT, DocumentationError, result_payload

UI_SOURCE_ROOTS = (
    "src/PilotAssessment.Desktop",
    "src/PilotAssessment.Desktop.Core",
)


def calculate_ui_source_tree_sha256(repository_root: Path = REPOSITORY_ROOT) -> str:
    """Hash tracked relative paths and their current worktree bytes in stable order."""

    completed = subprocess.run(
        ["git", "ls-files", "-z", "--", *UI_SOURCE_ROOTS],
        cwd=repository_root,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise DocumentationError(f"cannot enumerate tracked UI source: {detail}")
    relative_paths = sorted(
        (value.decode("utf-8") for value in completed.stdout.split(b"\0") if value),
        key=str.casefold,
    )
    if not relative_paths:
        raise DocumentationError("tracked UI source tree is empty")

    digest = hashlib.sha256()
    for relative in relative_paths:
        path = (repository_root / relative).resolve()
        if repository_root.resolve() not in path.parents or not path.is_file():
            raise DocumentationError(f"tracked UI source is missing: {relative}")
        payload = path.read_bytes()
        relative_bytes = relative.replace("\\", "/").encode("utf-8")
        digest.update(len(relative_bytes).to_bytes(8, byteorder="big"))
        digest.update(relative_bytes)
        digest.update(len(payload).to_bytes(8, byteorder="big"))
        digest.update(payload)
    return digest.hexdigest()


def main() -> int:
    try:
        identity = calculate_ui_source_tree_sha256()
    except (DocumentationError, OSError) as error:
        print(f"UI source identity failed: {error}", file=sys.stderr)
        return 1
    print(
        result_payload(
            algorithm="tracked-path-and-worktree-bytes-sha256-v1",
            roots=list(UI_SOURCE_ROOTS),
            ui_source_tree_sha256=identity,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
