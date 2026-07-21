"""Shared paths, contracts and parsers for the M8C documentation pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TOOL_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = TOOL_ROOT.parents[1]
MANUAL_ROOT = REPOSITORY_ROOT / "docs" / "product" / "manuals"
CATALOG_PATH = MANUAL_ROOT / "catalog.json"
METADATA_SCHEMA_PATH = MANUAL_ROOT / "schemas" / "document-metadata.schema.json"
DOCUMENTATION_DIST = REPOSITORY_ROOT / "dist" / "documentation"
DOCUMENTATION_BUILD = REPOSITORY_ROOT / "build" / "documentation"

LANGUAGES = ("zh-CN", "en-GB")
SOURCE_STATUSES = ("draft", "review", "released", "superseded")
BUILD_STATUSES = ("draft", "review", "released")
STATUS_RANK = {"draft": 0, "review": 1, "released": 2, "superseded": 3}
DOC_REFERENCE_PATTERN = re.compile(r"\[\[DOC:(PAS-[A-Z-]+-[0-9]{3})\]\]")
ASSET_REFERENCE_PATTERN = re.compile(r"\[\[ASSET:([a-z0-9][a-z0-9-]*)\]\]")


class DocumentationError(RuntimeError):
    """Stable failure raised by the documentation toolchain."""


@dataclass(frozen=True)
class ManualSource:
    path: Path
    metadata: dict[str, Any]
    body: str


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DocumentationError(f"cannot read JSON {path}: {error}") from error
    if not isinstance(payload, dict):
        raise DocumentationError(f"JSON root must be an object: {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def load_catalog() -> dict[str, Any]:
    return read_json(CATALOG_PATH)


def catalog_documents(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    documents = catalog.get("documents")
    if not isinstance(documents, list) or not all(isinstance(item, dict) for item in documents):
        raise DocumentationError("catalog.documents must be an array of objects")
    return documents


def document_index(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["document_id"]): item for item in catalog_documents(catalog)}


def parse_manual_source(path: Path) -> ManualSource:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise DocumentationError(f"cannot read manual source {path}: {error}") from error
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "+++":
        raise DocumentationError(f"manual must start with TOML front matter: {path}")
    closing = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "+++"), None
    )
    if closing is None:
        raise DocumentationError(f"manual front matter is not closed: {path}")
    raw_metadata = "".join(lines[1:closing])
    try:
        metadata = tomllib.loads(raw_metadata)
    except tomllib.TOMLDecodeError as error:
        raise DocumentationError(f"invalid TOML front matter in {path}: {error}") from error
    body = "".join(lines[closing + 1 :]).lstrip("\r\n")
    if not body.strip():
        raise DocumentationError(f"manual body is empty: {path}")
    return ManualSource(path=path, metadata=metadata, body=body)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_manual_path(relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise DocumentationError(f"manual catalog path must be relative and contained: {relative}")
    resolved = (MANUAL_ROOT / candidate).resolve()
    if MANUAL_ROOT.resolve() not in resolved.parents:
        raise DocumentationError(f"manual catalog path escapes source root: {relative}")
    return resolved


def add_selection_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--status", choices=BUILD_STATUSES, default="review")
    parser.add_argument("--language", choices=LANGUAGES)
    parser.add_argument("--document-id")


def selected_variants(
    catalog: dict[str, Any],
    *,
    status: str,
    language: str | None,
    document_id: str | None,
) -> list[tuple[dict[str, Any], str, dict[str, Any]]]:
    selected: list[tuple[dict[str, Any], str, dict[str, Any]]] = []
    threshold = STATUS_RANK[status]
    for document in sorted(catalog_documents(catalog), key=lambda item: int(item["order"])):
        if document_id and document.get("document_id") != document_id:
            continue
        language_records = document.get("languages")
        if not isinstance(language_records, dict):
            raise DocumentationError(f"{document.get('document_id')} languages must be an object")
        for current_language in LANGUAGES:
            if language and language != current_language:
                continue
            variant = language_records.get(current_language)
            if not isinstance(variant, dict):
                raise DocumentationError(
                    f"{document.get('document_id')} is missing {current_language} metadata"
                )
            source = variant.get("source")
            source_status = str(variant.get("status"))
            if source is None or source_status == "planned":
                continue
            if source_status not in STATUS_RANK:
                raise DocumentationError(
                    f"{document.get('document_id')} {current_language} "
                    f"has invalid status {source_status}"
                )
            if source_status == "superseded" or STATUS_RANK[source_status] < threshold:
                continue
            selected.append((document, current_language, variant))
    if document_id and not selected:
        raise DocumentationError(
            f"no buildable source matched document_id={document_id!r}, "
            f"language={language!r}, status={status!r}"
        )
    return selected


def output_root(catalog: dict[str, Any]) -> Path:
    version = str(catalog["product_version"])
    return DOCUMENTATION_DIST / f"PilotAssessment-{version}-docs"


def replace_document_references(
    text: str,
    *,
    catalog: dict[str, Any],
    language: str,
) -> str:
    index = document_index(catalog)

    def replacement(match: re.Match[str]) -> str:
        document_id = match.group(1)
        target = index.get(document_id)
        if target is None:
            raise DocumentationError(f"unknown stable document reference: {document_id}")
        variant = target["languages"][language]
        title = str(variant["title"])
        output = variant.get("output")
        if output:
            return f"[{title} ({document_id})]({output})"
        return f"{title} ({document_id})"

    return DOC_REFERENCE_PATTERN.sub(replacement, text)


def result_payload(**values: Any) -> str:
    return json.dumps(values, ensure_ascii=False, indent=2, sort_keys=True)


__all__ = [
    "ASSET_REFERENCE_PATTERN",
    "BUILD_STATUSES",
    "CATALOG_PATH",
    "DOC_REFERENCE_PATTERN",
    "DOCUMENTATION_BUILD",
    "DOCUMENTATION_DIST",
    "DocumentationError",
    "LANGUAGES",
    "MANUAL_ROOT",
    "METADATA_SCHEMA_PATH",
    "ManualSource",
    "REPOSITORY_ROOT",
    "TOOL_ROOT",
    "add_selection_arguments",
    "catalog_documents",
    "document_index",
    "load_catalog",
    "output_root",
    "parse_manual_source",
    "read_json",
    "replace_document_references",
    "result_payload",
    "safe_manual_path",
    "selected_variants",
    "sha256_file",
    "write_json",
]
