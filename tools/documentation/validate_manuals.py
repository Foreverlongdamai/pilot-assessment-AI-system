"""Validate M8C catalog, Markdown metadata, references, assets and language parity."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from manual_common import (
    ASSET_REFERENCE_PATTERN,
    DOC_REFERENCE_PATTERN,
    LANGUAGES,
    MANUAL_ROOT,
    METADATA_SCHEMA_PATH,
    SCREENSHOT_REFERENCE_PATTERN,
    DocumentationError,
    add_selection_arguments,
    aggregate_manual_source,
    catalog_documents,
    document_index,
    load_catalog,
    parse_manual_source,
    read_json,
    result_payload,
    safe_manual_path,
    selected_variants,
    sha256_file,
)
from PIL import Image

MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
PRIVATE_PATH = re.compile(r"(?i)(?:[A-Z]:\\Users\\[^\\\s]+|/Users/[^/\s]+|/home/[^/\s]+)")
UNRESOLVED = re.compile(
    r"(?i)\b(?:TODO|TBD|FIXME)\b|\[\[(?!DOC:|ASSET:|SCREENSHOT:)[A-Z][^\]]*\]\]"
)


def _catalog_errors(catalog: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if catalog.get("schema_version") != "pilot-assessment-document-catalog-v1":
        errors.append("catalog schema_version must be pilot-assessment-document-catalog-v1")
    if catalog.get("languages") != list(LANGUAGES):
        errors.append("catalog languages must be exactly ['zh-CN', 'en-GB']")
    if catalog.get("release_channel") != "release-candidate":
        errors.append("catalog release_channel must be release-candidate")
    if catalog.get("release_label") != "v0.1.0-rc.3":
        errors.append("catalog release_label must be v0.1.0-rc.3")
    if catalog.get("user_acceptance") != "pending":
        errors.append("catalog user_acceptance must be pending")
    documents = catalog_documents(catalog)
    if len(documents) != 12:
        errors.append(f"catalog must define exactly 12 logical documents, found {len(documents)}")
    ids = [str(item.get("document_id")) for item in documents]
    orders = [item.get("order") for item in documents]
    if len(ids) != len(set(ids)):
        errors.append("catalog document IDs are not unique")
    if orders != list(range(1, 13)):
        errors.append(f"catalog orders must be 1..12 in order, found {orders}")
    for document in documents:
        document_id = document.get("document_id")
        variants = document.get("languages")
        if not isinstance(variants, dict) or set(variants) != set(LANGUAGES):
            errors.append(f"{document_id} must define exactly zh-CN and en-GB")
            continue
        for language, variant in variants.items():
            if not isinstance(variant, dict):
                errors.append(f"{document_id} {language} variant must be an object")
                continue
            source = variant.get("source")
            output = variant.get("output")
            status = variant.get("status")
            is_aggregate = bool(document.get("aggregate_sources"))
            if source is None and status != "planned" and not is_aggregate:
                errors.append(f"{document_id} {language}: null source requires planned status")
            if source is not None:
                try:
                    source_path = safe_manual_path(str(source))
                except DocumentationError as error:
                    errors.append(str(error))
                else:
                    if not source_path.is_file():
                        errors.append(f"{document_id} {language} source is missing: {source}")
                if (
                    not isinstance(output, str)
                    or not output.endswith(".docx")
                    or Path(output).name != output
                ):
                    errors.append(f"{document_id} {language} has invalid DOCX output name")
    master = next(
        (item for item in documents if item.get("document_id") == "PAS-TECHREF-001"), None
    )
    if not master or len(master.get("aggregate_sources", [])) != 11:
        errors.append("PAS-TECHREF-001 must aggregate exactly the other 11 documents")
    elif set(master["aggregate_sources"]) != set(ids) - {"PAS-TECHREF-001"}:
        errors.append("PAS-TECHREF-001 aggregate_sources do not match documents 1..11")
    return errors


def _source_errors(
    catalog: dict[str, Any],
    document: dict[str, Any],
    language: str,
    variant: dict[str, Any],
    schema_validator: Draft202012Validator,
    diagram_ids: set[str],
    screenshot_ids: set[tuple[str, str]],
) -> tuple[list[str], dict[str, Any]]:
    document_id = str(document["document_id"])
    is_aggregate = variant.get("source") is None
    if is_aggregate:
        source, _ = aggregate_manual_source(catalog, document, language)
        path = source.path
    else:
        path = safe_manual_path(str(variant["source"]))
        source = parse_manual_source(path)
    metadata = source.metadata
    errors = [
        f"{path}: metadata {error.json_path} {error.message}"
        for error in sorted(schema_validator.iter_errors(metadata), key=lambda item: item.json_path)
    ]
    expected = {
        "document_id": document_id,
        "language": language,
        "title": variant["title"],
        "product_version": catalog["product_version"],
        "status": variant["status"],
        "release_channel": catalog["release_channel"],
        "release_label": catalog["release_label"],
        "user_acceptance": catalog["user_acceptance"],
    }
    for field, value in expected.items():
        if metadata.get(field) != value:
            errors.append(f"{path}: metadata {field!r} must equal catalog value {value!r}")
    if not source.body.lstrip().startswith(f"# {variant['title']}"):
        errors.append(f"{path}: first body heading must be '# {variant['title']}'")
    known_documents = set(document_index(catalog))
    for reference in DOC_REFERENCE_PATTERN.findall(source.body):
        if reference not in known_documents:
            errors.append(f"{path}: unknown document reference {reference}")
    for asset_id in ASSET_REFERENCE_PATTERN.findall(source.body):
        if asset_id not in diagram_ids:
            errors.append(f"{path}: unknown diagram asset {asset_id}")
    for screenshot_id in SCREENSHOT_REFERENCE_PATTERN.findall(source.body):
        if (screenshot_id, language) not in screenshot_ids:
            errors.append(f"{path}: unknown screenshot asset {screenshot_id}:{language}")
    if not is_aggregate:
        for raw_target in MARKDOWN_LINK.findall(source.body):
            target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            relative_target = target.split("#", 1)[0]
            if relative_target and not (path.parent / relative_target).resolve().exists():
                errors.append(f"{path}: broken relative link {target}")
    if PRIVATE_PATH.search(source.body):
        errors.append(f"{path}: contains a private user-home absolute path")
    unresolved = UNRESOLVED.search(source.body)
    if unresolved:
        errors.append(f"{path}: unresolved placeholder {unresolved.group(0)!r}")
    return errors, metadata


def _screenshot_errors(
    catalog: dict[str, Any],
    manifest: dict[str, Any],
    *,
    require_candidate: bool,
) -> tuple[list[str], set[tuple[str, str]]]:
    errors: list[str] = []
    if manifest.get("schema_version") != "pilot-assessment-screenshot-manifest-v1":
        errors.append("screenshot manifest schema_version is invalid")
    for field in ("product_version", "release_channel", "release_label", "user_acceptance"):
        if manifest.get(field) != catalog.get(field):
            errors.append(f"screenshot manifest {field} does not match catalog")
    entries = manifest.get("screenshots")
    if not isinstance(entries, list):
        return [*errors, "screenshot manifest screenshots must be an array"], set()
    keys = {
        (str(item.get("screenshot_id")), str(item.get("language")))
        for item in entries
        if isinstance(item, dict)
    }
    if len(entries) != 10 or len(keys) != 10:
        errors.append("screenshot manifest must contain ten unique language assets")
    expected_ids = {
        "ui-project-launcher",
        "ui-five-layer-model-studio",
        "ui-evidence-node-editor",
        "ui-bn-cpt-editor",
        "ui-run-results-diagnostics",
    }
    if keys != {(asset_id, language) for asset_id in expected_ids for language in LANGUAGES}:
        errors.append("screenshot manifest IDs/languages do not match the candidate contract")
    if not require_candidate:
        return errors, keys
    source_identity = manifest.get("ui_source_tree_sha256")
    if not isinstance(source_identity, str) or not re.fullmatch(r"[0-9a-f]{64}", source_identity):
        errors.append("screenshot manifest ui_source_tree_sha256 is invalid")
    for item in entries:
        if not isinstance(item, dict):
            errors.append("screenshot manifest entry must be an object")
            continue
        key = f"{item.get('screenshot_id')}:{item.get('language')}"
        if item.get("status") != "release-candidate":
            errors.append(f"screenshot {key} is not release-candidate")
            continue
        relative = item.get("path")
        if not isinstance(relative, str):
            errors.append(f"screenshot {key} has no path")
            continue
        path = MANUAL_ROOT / relative
        if not path.is_file():
            errors.append(f"screenshot {key} file is missing: {relative}")
            continue
        if item.get("sha256") != sha256_file(path):
            errors.append(f"screenshot {key} SHA-256 mismatch")
        try:
            with Image.open(path) as image:
                dimensions = image.size
                image.verify()
        except (OSError, ValueError) as error:
            errors.append(f"screenshot {key} is invalid: {error}")
            continue
        if [*dimensions] != [item.get("width"), item.get("height")]:
            errors.append(f"screenshot {key} dimensions mismatch")
        privacy = item.get("privacy_review")
        if not isinstance(privacy, dict) or privacy.get("status") != "passed":
            errors.append(f"screenshot {key} privacy review is not passed")
        entry_identity = item.get("ui_source_tree_sha256")
        if not isinstance(entry_identity, str) or not re.fullmatch(r"[0-9a-f]{64}", entry_identity):
            errors.append(f"screenshot {key} UI source identity is invalid")
        elif entry_identity != source_identity:
            reused_from = item.get("reused_from_release_label")
            reuse_reason = item.get("reuse_reason")
            if not isinstance(reused_from, str) or not reused_from.strip():
                errors.append(f"screenshot {key} UI source identity mismatch")
            if not isinstance(reuse_reason, str) or not reuse_reason.strip():
                errors.append(f"screenshot {key} reuse reason is missing")
        elif item.get("captured_for_release_label") not in {
            None,
            manifest.get("release_label"),
        }:
            errors.append(f"screenshot {key} captured release label mismatch")
    return errors, keys


def validate(*, status: str, language: str | None, document_id: str | None) -> dict[str, Any]:
    catalog = load_catalog()
    errors = _catalog_errors(catalog)
    schema = read_json(METADATA_SCHEMA_PATH)
    schema_validator = Draft202012Validator(schema)
    diagram_manifest = read_json(MANUAL_ROOT / "assets" / "diagrams" / "manifest.json")
    screenshot_manifest = read_json(MANUAL_ROOT / "assets" / "screenshots" / "manifest.json")
    diagram_ids = {
        str(item["asset_id"])
        for item in diagram_manifest.get("diagrams", [])
        if isinstance(item, dict) and "asset_id" in item
    }
    screenshot_errors, screenshot_ids = _screenshot_errors(
        catalog,
        screenshot_manifest,
        require_candidate=status == "released",
    )
    errors.extend(screenshot_errors)
    selected = selected_variants(catalog, status=status, language=language, document_id=document_id)
    metadata_by_document: dict[str, dict[str, dict[str, Any]]] = {}
    for document, current_language, variant in selected:
        source_errors, metadata = _source_errors(
            catalog,
            document,
            current_language,
            variant,
            schema_validator,
            diagram_ids,
            screenshot_ids,
        )
        errors.extend(source_errors)
        metadata_by_document.setdefault(str(document["document_id"]), {})[current_language] = (
            metadata
        )
    for current_document_id, language_metadata in metadata_by_document.items():
        if set(language_metadata) != set(LANGUAGES):
            continue
        zh = language_metadata["zh-CN"]
        en = language_metadata["en-GB"]
        for field in (
            "document_id",
            "product_version",
            "document_version",
            "status",
            "scientific_status",
        ):
            if zh.get(field) != en.get(field):
                errors.append(f"{current_document_id}: language parity mismatch for {field}")
        if set(zh.get("related_documents", [])) != set(en.get("related_documents", [])):
            errors.append(f"{current_document_id}: language parity mismatch for related_documents")
    if status == "released" and len(selected) != 24:
        errors.append(f"released build must select 24 language variants, found {len(selected)}")
    if errors:
        raise DocumentationError("documentation validation failed:\n- " + "\n- ".join(errors))
    return {
        "catalog_documents": len(catalog_documents(catalog)),
        "selected_sources": len(selected),
        "validated_language_variants": sorted(
            f"{document['document_id']}:{current_language}"
            for document, current_language, _ in selected
        ),
        "diagram_ids": sorted(diagram_ids),
        "pending_screenshots": len(
            [
                item
                for item in screenshot_manifest.get("screenshots", [])
                if isinstance(item, dict) and item.get("status") != "release-candidate"
            ]
        ),
        "status": "PASS",
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    add_selection_arguments(parser)
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    try:
        result = validate(
            status=args.status,
            language=args.language,
            document_id=args.document_id,
        )
    except DocumentationError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(result_payload(**result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
