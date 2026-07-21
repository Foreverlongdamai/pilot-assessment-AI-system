"""Render generated manuals to page PNGs for repeatable visual QA."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import fitz
from manual_common import (
    DOCUMENTATION_BUILD,
    DocumentationError,
    add_selection_arguments,
    load_catalog,
    output_root,
    read_json,
    result_payload,
    sha256_file,
    write_json,
)
from PIL import Image


def _find_soffice() -> Path:
    configured = os.environ.get("PILOT_ASSESSMENT_SOFFICE")
    discovered = shutil.which("soffice") or shutil.which("soffice.com")
    candidates = [
        Path(configured) if configured else None,
        Path(discovered) if discovered else None,
        Path(r"C:\Program Files\LibreOffice\program\soffice.com"),
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate.resolve()
    raise DocumentationError(
        "LibreOffice is required for DOCX render QA; set PILOT_ASSESSMENT_SOFFICE"
    )


def _selected_outputs(
    manifest: dict[str, Any],
    *,
    language: str | None,
    document_id: str | None,
) -> list[dict[str, Any]]:
    outputs = manifest.get("outputs")
    if not isinstance(outputs, list):
        raise DocumentationError("documentation build manifest has no outputs array")
    selected = [
        item
        for item in outputs
        if isinstance(item, dict)
        and (language is None or item.get("language") == language)
        and (document_id is None or item.get("document_id") == document_id)
    ]
    if document_id and not selected:
        raise DocumentationError(f"built documentation has no output for {document_id}")
    return selected


def _render_one(*, soffice: Path, source: Path, output_directory: Path) -> dict[str, Any]:
    output_directory.mkdir(parents=True, exist_ok=True)
    for stale in output_directory.glob("page-*.png"):
        stale.unlink()
    with tempfile.TemporaryDirectory(
        prefix="pilot-assessment-lo-", dir=DOCUMENTATION_BUILD
    ) as profile_directory:
        profile_uri = Path(profile_directory).resolve().as_uri()
        completed = subprocess.run(
            [
                str(soffice),
                "--headless",
                f"-env:UserInstallation={profile_uri}",
                "--convert-to",
                "pdf",
                "--outdir",
                str(output_directory),
                str(source),
            ],
            cwd=source.parent,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
    pdf = output_directory / f"{source.stem}.pdf"
    if completed.returncode != 0 or not pdf.is_file() or pdf.stat().st_size == 0:
        raise DocumentationError(
            f"LibreOffice render failed for {source.name}: "
            f"stdout={completed.stdout.strip()!r}, stderr={completed.stderr.strip()!r}"
        )
    page_records: list[dict[str, Any]] = []
    with fitz.open(pdf) as document:
        if document.page_count == 0:
            raise DocumentationError(f"rendered PDF has no pages: {pdf}")
        for page_number, page in enumerate(document, start=1):
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            png = output_directory / f"page-{page_number:03d}.png"
            pixmap.save(png)
            with Image.open(png) as image:
                width, height = image.size
            if width < 1000 or height < 1000:
                raise DocumentationError(f"rendered page resolution is unexpectedly low: {png}")
            page_records.append(
                {
                    "page": page_number,
                    "png": png.name,
                    "width": width,
                    "height": height,
                    "sha256": sha256_file(png),
                }
            )
    return {
        "pdf": pdf.name,
        "pdf_sha256": sha256_file(pdf),
        "page_count": len(page_records),
        "pages": page_records,
    }


def render(*, status: str, language: str | None, document_id: str | None) -> dict[str, Any]:
    catalog = load_catalog()
    built_root = output_root(catalog)
    manifest_path = built_root / "documentation-manifest.json"
    if not manifest_path.is_file():
        raise DocumentationError("documentation is not built; run build_docs.ps1 build first")
    manifest = read_json(manifest_path)
    if manifest.get("build_status") != status:
        raise DocumentationError(
            f"built status is {manifest.get('build_status')!r}, "
            f"requested render status is {status!r}"
        )
    selected = _selected_outputs(manifest, language=language, document_id=document_id)
    soffice = _find_soffice()
    rendered: list[dict[str, Any]] = []
    for item in selected:
        source = built_root / str(item["output"])
        if not source.is_file():
            raise DocumentationError(f"built DOCX is missing: {source}")
        output_directory = (
            DOCUMENTATION_BUILD / "rendered" / str(item["language"]) / str(item["document_id"])
        )
        rendered.append(
            {
                "document_id": item["document_id"],
                "language": item["language"],
                "source_sha256": sha256_file(source),
                "output_directory": str(output_directory),
                **_render_one(
                    soffice=soffice,
                    source=source,
                    output_directory=output_directory,
                ),
            }
        )
    report = {
        "schema_version": "pilot-assessment-document-render-report-v1",
        "product_version": catalog["product_version"],
        "build_status": status,
        "renderer": str(soffice),
        "documents": rendered,
        "status": "PASS",
    }
    report_path = DOCUMENTATION_BUILD / "render-report.json"
    write_json(report_path, report)
    return {**report, "report": str(report_path)}


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    add_selection_arguments(parser)
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    try:
        result = render(
            status=args.status,
            language=args.language,
            document_id=args.document_id,
        )
    except (DocumentationError, OSError, subprocess.SubprocessError, ValueError) as error:
        print(f"documentation render failed: {error}", file=sys.stderr)
        return 1
    print(result_payload(**result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
