"""Render controlled Mermaid diagram sources and update their content hashes."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from manual_common import (
    DOCUMENTATION_BUILD,
    MANUAL_ROOT,
    TOOL_ROOT,
    DocumentationError,
    read_json,
    result_payload,
    sha256_file,
    write_json,
)
from PIL import Image

DIAGRAM_ROOT = MANUAL_ROOT / "assets" / "diagrams"
MANIFEST_PATH = DIAGRAM_ROOT / "manifest.json"


def _find_browser() -> Path:
    configured = os.environ.get("PILOT_ASSESSMENT_BROWSER")
    candidates = [
        Path(configured) if configured else None,
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate.resolve()
    raise DocumentationError(
        "Mermaid rendering requires Microsoft Edge or Chrome; set PILOT_ASSESSMENT_BROWSER"
    )


def _find_node() -> Path:
    configured = os.environ.get("PILOT_ASSESSMENT_NODE")
    candidate = configured or shutil.which("node")
    if not candidate:
        raise DocumentationError("Node.js is required to run the pinned Mermaid renderer")
    path = Path(candidate).resolve()
    if not path.is_file():
        raise DocumentationError(f"configured Node.js does not exist: {path}")
    return path


def _run_mermaid(
    *, node: Path, cli: Path, source: Path, output: Path, browser_config: Path
) -> None:
    command = [
        str(node),
        str(cli),
        "--input",
        str(source),
        "--output",
        str(output),
        "--configFile",
        str(TOOL_ROOT / "mermaid-config.json"),
        "--puppeteerConfigFile",
        str(browser_config),
        "--backgroundColor",
        "transparent",
        "--width",
        "1800",
        "--scale",
        "1",
        "--quiet",
    ]
    completed = subprocess.run(
        command,
        cwd=TOOL_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if completed.returncode != 0:
        raise DocumentationError(
            f"Mermaid failed for {source.name}: "
            f"stdout={completed.stdout.strip()!r}, stderr={completed.stderr.strip()!r}"
        )


def render_diagrams() -> dict[str, Any]:
    manifest = read_json(MANIFEST_PATH)
    diagrams = manifest.get("diagrams")
    if not isinstance(diagrams, list):
        raise DocumentationError("diagram manifest must contain a diagrams array")
    node = _find_node()
    cli = TOOL_ROOT / "node_modules" / "@mermaid-js" / "mermaid-cli" / "src" / "cli.js"
    if not cli.is_file():
        raise DocumentationError(
            "pinned Mermaid renderer is not installed; run build_docs.ps1 setup"
        )
    browser = _find_browser()
    DOCUMENTATION_BUILD.mkdir(parents=True, exist_ok=True)
    rendered: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(
        prefix="pilot-assessment-mermaid-", dir=DOCUMENTATION_BUILD
    ) as temporary:
        browser_config = Path(temporary) / "puppeteer.json"
        browser_config.write_text(
            json.dumps(
                {
                    "executablePath": str(browser),
                    "headless": "shell",
                    "args": ["--disable-gpu", "--no-first-run", "--disable-extensions"],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        for item in diagrams:
            if not isinstance(item, dict):
                raise DocumentationError("diagram manifest entries must be objects")
            source = DIAGRAM_ROOT / str(item["source"])
            if not source.is_file():
                raise DocumentationError(f"diagram source is missing: {source}")
            stem = source.stem
            svg = DIAGRAM_ROOT / f"{stem}.svg"
            png = DIAGRAM_ROOT / f"{stem}.png"
            _run_mermaid(
                node=node,
                cli=cli,
                source=source,
                output=svg,
                browser_config=browser_config,
            )
            _run_mermaid(
                node=node,
                cli=cli,
                source=source,
                output=png,
                browser_config=browser_config,
            )
            with Image.open(png) as image:
                width, height = image.size
            item.update(
                {
                    "status": "rendered",
                    "renderer_version": "11.16.0",
                    "source_sha256": sha256_file(source),
                    "svg": svg.name,
                    "svg_sha256": sha256_file(svg),
                    "png": png.name,
                    "png_sha256": sha256_file(png),
                    "png_width": width,
                    "png_height": height,
                }
            )
            rendered.append(
                {
                    "asset_id": item["asset_id"],
                    "source_sha256": item["source_sha256"],
                    "png_sha256": item["png_sha256"],
                    "size": [width, height],
                }
            )
    write_json(MANIFEST_PATH, manifest)
    return {
        "browser": browser.name,
        "node": str(node),
        "renderer": "@mermaid-js/mermaid-cli@11.16.0",
        "rendered": rendered,
        "status": "PASS",
    }


def main() -> int:
    try:
        result = render_diagrams()
    except (DocumentationError, OSError, subprocess.SubprocessError) as error:
        print(f"diagram rendering failed: {error}", file=sys.stderr)
        return 1
    print(result_payload(**result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
