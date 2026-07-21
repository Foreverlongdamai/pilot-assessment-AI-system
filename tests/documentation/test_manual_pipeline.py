from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DOCUMENTATION_TOOLS = REPOSITORY_ROOT / "tools" / "documentation"
sys.path.insert(0, str(DOCUMENTATION_TOOLS))

from manual_common import (  # noqa: E402
    AGGREGATE_PAGE_BREAK,
    aggregate_manual_source,
    load_catalog,
    read_json,
    shift_markdown_headings,
)
from register_screenshots import register  # noqa: E402


def test_release_candidate_catalog_defines_twelve_logical_and_twenty_four_outputs() -> None:
    catalog = load_catalog()
    documents = catalog["documents"]

    assert catalog["release_channel"] == "release-candidate"
    assert catalog["release_label"] == "v0.1.0-rc.3"
    assert catalog["user_acceptance"] == "pending"
    assert len(documents) == 12
    assert sum(len(item["languages"]) for item in documents) == 24
    assert {
        variant["status"] for document in documents for variant in document["languages"].values()
    } == {"released"}

    master = next(item for item in documents if item["document_id"] == "PAS-TECHREF-001")
    assert len(master["aggregate_sources"]) == 11
    assert all(variant["source"] is None for variant in master["languages"].values())


def test_heading_shift_drops_module_title_and_does_not_rewrite_fenced_code() -> None:
    body = """# Module title

## Procedure

```text
# code heading
```

### Detail
"""

    shifted = shift_markdown_headings(body, drop_title=True, levels=1)

    assert shifted.startswith("### Procedure")
    assert "# code heading" in shifted
    assert "#### Detail" in shifted
    assert "# Module title" not in shifted


def test_master_manual_is_generated_from_all_eleven_released_module_sources() -> None:
    catalog = load_catalog()
    master = next(item for item in catalog["documents"] if item["document_id"] == "PAS-TECHREF-001")

    source, modules = aggregate_manual_source(catalog, master, "en-GB")

    assert source.metadata["status"] == "released"
    assert source.metadata["release_label"] == "v0.1.0-rc.3"
    assert len(modules) == 11
    assert source.body.count(AGGREGATE_PAGE_BREAK) == 10
    assert [item["document_id"] for item in modules] == master["aggregate_sources"]
    assert all(len(item["sha256"]) == 64 for item in modules)


def test_c4_diagram_inputs_avoid_randomised_shapes_and_use_stable_ids() -> None:
    config = read_json(DOCUMENTATION_TOOLS / "mermaid-config.json")

    assert config["deterministicIds"] is True
    assert config["deterministicIDSeed"] == "pilot-assessment-docs-v1"
    for filename in ("c4-system-context.mmd", "c4-container.mmd"):
        source = (
            REPOSITORY_ROOT / "docs" / "product" / "manuals" / "assets" / "diagrams" / filename
        ).read_text(encoding="utf-8")
        assert '(["' not in source


def test_registers_ten_existing_candidate_screenshots_without_capturing(
    tmp_path: Path,
) -> None:
    source_manifest = read_json(
        REPOSITORY_ROOT
        / "docs"
        / "product"
        / "manuals"
        / "assets"
        / "screenshots"
        / "manifest.json"
    )
    assert all(
        "\ufffd" not in str(item[field])
        for item in source_manifest["screenshots"]
        for field in ("caption", "alt_text")
    )
    manual_root = tmp_path / "manuals"
    manifest_path = manual_root / "assets" / "screenshots" / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(source_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for index, item in enumerate(source_manifest["screenshots"]):
        path = manual_root / item["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (800, 500), color=(20 + index, 80, 120)).save(path, format="PNG")

    result = register(
        manifest_path=manifest_path,
        manual_root=manual_root,
        ui_source_tree_sha256="a" * 64,
        captured_at="2026-07-21T18:45:00Z",
        reviewer="release-test",
        privacy_reviewed=True,
    )

    registered = read_json(manifest_path)
    assert result["status"] == "PASS"
    assert len(result["registered"]) == 10
    assert (
        len({(item["screenshot_id"], item["language"]) for item in registered["screenshots"]}) == 10
    )
    assert {item["status"] for item in registered["screenshots"]} == {"release-candidate"}
    assert all(item["privacy_review"]["status"] == "passed" for item in registered["screenshots"])
    assert all(
        item["captured_for_release_label"] == "v0.1.0-rc.3" for item in registered["screenshots"]
    )


def test_selective_screenshot_registration_preserves_explicit_reuse_provenance(
    tmp_path: Path,
) -> None:
    source_manifest = read_json(
        REPOSITORY_ROOT
        / "docs"
        / "product"
        / "manuals"
        / "assets"
        / "screenshots"
        / "manifest.json"
    )
    manual_root = tmp_path / "manuals"
    manifest_path = manual_root / "assets" / "screenshots" / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(source_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for index, item in enumerate(source_manifest["screenshots"]):
        path = manual_root / item["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (800, 500), color=(20 + index, 80, 120)).save(path, format="PNG")

    old_identity = source_manifest["screenshots"][0]["ui_source_tree_sha256"]
    register(
        manifest_path=manifest_path,
        manual_root=manual_root,
        ui_source_tree_sha256="b" * 64,
        captured_at="2026-07-21T19:30:00Z",
        reviewer="release-test",
        privacy_reviewed=True,
        screenshot_ids={"ui-five-layer-model-studio"},
    )

    registered = read_json(manifest_path)
    recaptured = [
        item
        for item in registered["screenshots"]
        if item["screenshot_id"] == "ui-five-layer-model-studio"
    ]
    reused = [
        item
        for item in registered["screenshots"]
        if item["screenshot_id"] != "ui-five-layer-model-studio"
    ]
    assert all(item["ui_source_tree_sha256"] == "b" * 64 for item in recaptured)
    assert all(item["captured_for_release_label"] == "v0.1.0-rc.3" for item in recaptured)
    assert all(item["ui_source_tree_sha256"] == old_identity for item in reused)
    assert all(item["reused_from_release_label"] == "v0.1.0-rc.2" for item in reused)
    assert all(item["reuse_reason"] for item in reused)
