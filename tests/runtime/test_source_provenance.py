from __future__ import annotations

import io
import json
import os
import zipfile
from pathlib import Path

from pilot_assessment.evidence.registry import OperatorRegistry
from pilot_assessment.runtime.source_provenance import (
    SNAPSHOT_MANIFEST_PATH,
    BackendSourceLayout,
    BackendSourceProvenance,
)


def _layout(root: Path, *, portable: bool = False) -> BackendSourceLayout:
    metadata = root / "backend" if portable else root
    source = metadata / "src" / "pilot_assessment"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8", newline="\n")
    (source / "Module.py").write_text("def value(): return 2\n", encoding="utf-8", newline="\n")
    (metadata / "pyproject.toml").write_text(
        "[project]\nname='provenance-fixture'\nversion='0.0.0'\n",
        encoding="utf-8",
        newline="\n",
    )
    (metadata / "uv.lock").write_text("version = 1\n", encoding="utf-8", newline="\n")
    return BackendSourceLayout(
        product_root=root,
        source_root=source,
        active_source_root=("backend/src/pilot_assessment" if portable else "src/pilot_assessment"),
        pyproject_path=metadata / "pyproject.toml",
        uv_lock_path=metadata / "uv.lock",
        baseline_path=None,
    )


def _capture(root: Path, *, portable: bool = False) -> BackendSourceProvenance:
    return BackendSourceProvenance(_layout(root, portable=portable), OperatorRegistry())


def test_tree_identity_ignores_install_path_mtime_and_windows_path_case(tmp_path) -> None:
    first = _capture(tmp_path / "one")
    second_layout = _layout(tmp_path / "two")
    module = second_layout.source_root / "Module.py"
    os.utime(module, (module.stat().st_atime + 30, module.stat().st_mtime + 30))
    module.rename(second_layout.source_root / "module.py")
    second = BackendSourceProvenance(second_layout, OperatorRegistry())

    assert first.loaded_identity.source_tree_sha256 == second.loaded_identity.source_tree_sha256
    assert first.loaded_identity.pyproject_sha256 == second.loaded_identity.pyproject_sha256
    assert first.loaded_identity.uv_lock_sha256 == second.loaded_identity.uv_lock_sha256


def test_disk_status_reports_add_modify_delete_and_lock_drift(tmp_path) -> None:
    provenance = _capture(tmp_path / "product")
    source = provenance.layout.source_root
    (source / "added.py").write_text("ADDED = True\n", encoding="utf-8", newline="\n")
    (source / "Module.py").write_text("CHANGED = True\n", encoding="utf-8", newline="\n")
    (source / "__init__.py").unlink()
    provenance.layout.uv_lock_path.write_text("version = 2\n", encoding="utf-8", newline="\n")

    status = provenance.disk_status()

    assert status.runtime_restart_required is True
    assert "backend/src/pilot_assessment/added.py" in status.loaded_to_disk_changes.added
    assert "backend/src/pilot_assessment/module.py" in status.loaded_to_disk_changes.modified
    assert "backend/src/pilot_assessment/__init__.py" in status.loaded_to_disk_changes.deleted
    assert "backend/uv.lock" in status.loaded_to_disk_changes.modified


def test_portable_baseline_and_snapshot_are_deterministic_and_private(tmp_path) -> None:
    layout = _layout(tmp_path / "portable", portable=True)
    first_without_baseline = BackendSourceProvenance(layout, OperatorRegistry())
    files = []
    for item in first_without_baseline._loaded_tree.files:  # focused white-box baseline fixture
        files.append(
            {
                "path": item.logical_path,
                "sha256": item.sha256,
                "bytes": len(item.payload),
            }
        )
    baseline_path = layout.product_root / "manifest" / "source-baseline.json"
    baseline_path.parent.mkdir(parents=True)
    baseline_path.write_text(
        json.dumps(
            {
                "schema_version": "pilot-assessment-source-baseline-v2",
                "active_source_root": "backend/src/pilot_assessment",
                "tree_algorithm": "pilot-assessment-source-tree-v2",
                "tree_sha256": first_without_baseline.loaded_identity.source_tree_sha256,
                "files": files,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    with_baseline = BackendSourceProvenance(
        BackendSourceLayout(
            product_root=layout.product_root,
            source_root=layout.source_root,
            active_source_root=layout.active_source_root,
            pyproject_path=layout.pyproject_path,
            uv_lock_path=layout.uv_lock_path,
            baseline_path=baseline_path,
        ),
        OperatorRegistry(),
    )
    repeated = BackendSourceProvenance(with_baseline.layout, OperatorRegistry())

    assert with_baseline.loaded_identity.baseline_available is True
    assert with_baseline.loaded_identity.locally_modified is False
    assert with_baseline.snapshot_bytes == repeated.snapshot_bytes
    with zipfile.ZipFile(io.BytesIO(with_baseline.snapshot_bytes)) as archive:
        names = archive.namelist()
        assert names == sorted(names, key=str.casefold)
        assert SNAPSHOT_MANIFEST_PATH in names
        assert "backend/pyproject.toml" in names
        assert "backend/uv.lock" in names
        assert all(str(tmp_path) not in name for name in names)
