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
SCREENSHOT_REFERENCE_PATTERN = re.compile(
    r"\[\[SCREENSHOT:([a-z0-9][a-z0-9-]*)\]\]"
)
AGGREGATE_PAGE_BREAK = "@@PA_MODULE_PAGE_BREAK@@"
MARKDOWN_HEADING_PATTERN = re.compile(r"^(#{1,6})([ \t]+.*)$")


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
            is_aggregate = bool(document.get("aggregate_sources"))
            if (source is None and not is_aggregate) or source_status == "planned":
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


def shift_markdown_headings(body: str, *, drop_title: bool, levels: int = 1) -> str:
    """Shift Markdown ATX headings without touching fenced code blocks."""

    shifted: list[str] = []
    title_dropped = False
    fence: str | None = None
    for line in body.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            fence = None if fence == marker else marker
            shifted.append(line)
            continue
        match = MARKDOWN_HEADING_PATTERN.match(line) if fence is None else None
        if match is None:
            shifted.append(line)
            continue
        current_level = len(match.group(1))
        if drop_title and not title_dropped and current_level == 1:
            title_dropped = True
            continue
        shifted.append("#" * min(6, current_level + levels) + match.group(2))
    return "\n".join(shifted).strip()


def aggregate_manual_source(
    catalog: dict[str, Any],
    document: dict[str, Any],
    language: str,
) -> tuple[ManualSource, list[dict[str, str]]]:
    """Generate the master manual from the eleven authoritative module sources."""

    aggregate_ids = document.get("aggregate_sources")
    if not isinstance(aggregate_ids, list) or len(aggregate_ids) != 11:
        raise DocumentationError("aggregate manual must declare exactly eleven module IDs")
    index = document_index(catalog)
    variant = document["languages"][language]
    modules: list[dict[str, str]] = []
    sections: list[str] = []
    for position, document_id in enumerate(aggregate_ids, start=1):
        module = index.get(str(document_id))
        if module is None:
            raise DocumentationError(f"aggregate source is unknown: {document_id}")
        module_variant = module["languages"][language]
        source_value = module_variant.get("source")
        if not isinstance(source_value, str):
            raise DocumentationError(f"aggregate module has no source: {document_id}:{language}")
        source_path = safe_manual_path(source_value)
        source = parse_manual_source(source_path)
        if source.metadata.get("status") != "released":
            raise DocumentationError(
                f"aggregate module is not released: {document_id}:{language}"
            )
        if position > 1:
            sections.append(AGGREGATE_PAGE_BREAK)
        sections.append(f"## {module_variant['title']}")
        sections.append(shift_markdown_headings(source.body, drop_title=True, levels=1))
        modules.append(
            {
                "document_id": str(document_id),
                "source": source_value,
                "sha256": sha256_file(source_path),
            }
        )

    title = str(variant["title"])
    introduction = (
        "本总册由 11 份已发布模块手册自动聚合。模块 Markdown 是唯一人工维护正文；"
        "本总册不建立第三份内容来源。"
        if language == "zh-CN"
        else (
            "This master reference is generated from the eleven released module manuals. "
            "Their Markdown remains the only maintained prose; this document introduces no "
            "third content authority."
        )
    )
    metadata: dict[str, Any] = {
        "document_id": str(document["document_id"]),
        "language": language,
        "title": title,
        "short_title": "系统技术参考总册" if language == "zh-CN" else "Master Technical Reference",
        "product_version": str(catalog["product_version"]),
        "document_version": str(catalog["document_set_version"]),
        "status": str(variant["status"]),
        "audience": ["evaluator", "expert", "developer", "maintainer", "release"],
        "information_types": ["tutorial", "how-to", "reference", "explanation"],
        "scope": (
            "汇总产品架构、操作、专家建模、数据接口、开发维护、迁移和发布验收。"
            if language == "zh-CN"
            else (
                "Aggregates architecture, operation, expert modelling, input interfaces, "
                "development, maintenance, portability and release acceptance."
            )
        ),
        "prerequisites": [],
        "scientific_status": "engineering-only",
        "related_documents": [str(value) for value in aggregate_ids],
        "support": (
            "报告问题时提供产品版本、文档 ID、Diagnostics 摘要和不含隐私数据的复现步骤。"
            if language == "zh-CN"
            else (
                "Report the product version, document ID, Diagnostics summary and "
                "privacy-safe reproduction steps."
            )
        ),
        "release_channel": str(catalog["release_channel"]),
        "release_label": str(catalog["release_label"]),
        "user_acceptance": str(catalog["user_acceptance"]),
    }
    body = f"# {title}\n\n{introduction}\n\n" + "\n\n".join(sections) + "\n"
    virtual_path = MANUAL_ROOT / language / "_generated-master-technical-reference.md"
    return ManualSource(path=virtual_path, metadata=metadata, body=body), modules


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
    "AGGREGATE_PAGE_BREAK",
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
    "SCREENSHOT_REFERENCE_PATTERN",
    "TOOL_ROOT",
    "add_selection_arguments",
    "aggregate_manual_source",
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
    "shift_markdown_headings",
    "write_json",
]
