"""Process-frozen provenance for the editable first-party Python backend."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import sys
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Final

from pilot_assessment.contracts.source_provenance import (
    BackendSourceDiskStatus,
    BackendSourceIdentity,
    DependencyManifestIdentity,
    OperatorCatalogIdentity,
    PythonRuntimeIdentity,
    SourceChangeSummary,
    SourceFileDigest,
    SourceSnapshotManifest,
)
from pilot_assessment.evidence.registry import OperatorRegistry
from pilot_assessment.model_library.identity import jcs_bytes, typed_content_sha256

PRODUCT_ROOT_ENV: Final = "PILOT_ASSESSMENT_PRODUCT_ROOT"
TREE_ALGORITHM: Final = "pilot-assessment-source-tree-v2"
IDENTITY_ALGORITHM: Final = "pilot-assessment-backend-identity-v1"
CANONICAL_ARCHIVE_SOURCE_ROOT: Final = "backend/src/pilot_assessment"
CANONICAL_ARCHIVE_PROJECT: Final = "backend/pyproject.toml"
CANONICAL_ARCHIVE_LOCK: Final = "backend/uv.lock"
SNAPSHOT_MANIFEST_PATH: Final = "manifest/source-snapshot.json"

_EXCLUDED_DIRECTORY_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".ty",
    "__pycache__",
}
_EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".tmp", ".temp", ".swp"}
_EXCLUDED_FILE_NAMES = {"thumbs.db", ".ds_store"}


class BackendSourceProvenanceError(RuntimeError):
    """Raised when the active backend cannot be identified without ambiguity."""


@dataclass(frozen=True, slots=True)
class BackendSourceLayout:
    product_root: Path
    source_root: Path
    active_source_root: str
    pyproject_path: Path
    uv_lock_path: Path
    baseline_path: Path | None

    @classmethod
    def discover(cls, product_root: str | Path | None = None) -> BackendSourceLayout:
        explicit = product_root or os.environ.get(PRODUCT_ROOT_ENV)
        module_path = Path(__file__).resolve()
        derived_root = (
            module_path.parents[4]
            if module_path.parents[3].name.casefold() == "backend"
            else module_path.parents[3]
        )
        root = Path(explicit).expanduser().resolve() if explicit is not None else derived_root
        portable_source = root / "backend" / "src" / "pilot_assessment"
        development_source = root / "src" / "pilot_assessment"
        if portable_source.is_dir():
            source = portable_source
            active = "backend/src/pilot_assessment"
            metadata_root = root / "backend"
            candidate_baseline = root / "manifest" / "source-baseline.json"
            baseline = candidate_baseline if candidate_baseline.is_file() else None
        elif development_source.is_dir():
            source = development_source
            active = "src/pilot_assessment"
            metadata_root = root
            baseline = None
        else:
            raise BackendSourceProvenanceError(
                "product root does not contain one active pilot_assessment source tree"
            )
        pyproject = metadata_root / "pyproject.toml"
        lock = metadata_root / "uv.lock"
        for label, path in (("pyproject.toml", pyproject), ("uv.lock", lock)):
            if not path.is_file():
                raise BackendSourceProvenanceError(f"active backend is missing {label}")
        return cls(
            product_root=root,
            source_root=source,
            active_source_root=active,
            pyproject_path=pyproject,
            uv_lock_path=lock,
            baseline_path=baseline,
        )


@dataclass(frozen=True, slots=True)
class _CapturedFile:
    relative_path: str
    logical_path: str
    payload: bytes
    sha256: str


@dataclass(frozen=True, slots=True)
class _CapturedTree:
    files: tuple[_CapturedFile, ...]
    tree_sha256: str

    @property
    def logical_hashes(self) -> dict[str, str]:
        return {item.logical_path: item.sha256 for item in self.files}


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_path_key(value: str) -> str:
    return value.replace("\\", "/").casefold()


def _is_included_source_file(path: Path, source_root: Path) -> bool:
    relative = path.relative_to(source_root)
    if any(part.casefold() in _EXCLUDED_DIRECTORY_NAMES for part in relative.parts[:-1]):
        return False
    name = relative.name.casefold()
    if name in _EXCLUDED_FILE_NAMES or name.endswith("~"):
        return False
    return path.suffix.casefold() not in _EXCLUDED_SUFFIXES


def _capture_source_tree(source_root: Path) -> _CapturedTree:
    candidates = [
        path
        for path in source_root.rglob("*")
        if path.is_file() and not path.is_symlink() and _is_included_source_file(path, source_root)
    ]
    entries: list[_CapturedFile] = []
    seen: set[str] = set()
    for path in sorted(
        candidates, key=lambda item: _canonical_path_key(item.relative_to(source_root).as_posix())
    ):
        relative = path.relative_to(source_root).as_posix()
        key = _canonical_path_key(relative)
        if key in seen:
            raise BackendSourceProvenanceError(
                f"source tree contains a case-insensitive path collision: {relative}"
            )
        seen.add(key)
        payload = path.read_bytes()
        entries.append(
            _CapturedFile(
                relative_path=key,
                logical_path=f"{CANONICAL_ARCHIVE_SOURCE_ROOT}/{key}",
                payload=payload,
                sha256=_sha256_bytes(payload),
            )
        )
    if not entries:
        raise BackendSourceProvenanceError("active backend source tree is empty")
    digest = hashlib.sha256()
    digest.update(TREE_ALGORITHM.encode("ascii") + b"\0")
    for item in entries:
        path_bytes = item.relative_path.encode("utf-8")
        digest.update(len(path_bytes).to_bytes(8, "big"))
        digest.update(path_bytes)
        digest.update(len(item.payload).to_bytes(8, "big"))
        digest.update(item.payload)
    return _CapturedTree(files=tuple(entries), tree_sha256=digest.hexdigest())


def _change_summary(
    reference: dict[str, str],
    candidate: dict[str, str],
) -> SourceChangeSummary:
    reference_keys = set(reference)
    candidate_keys = set(candidate)
    added = tuple(sorted(candidate_keys - reference_keys, key=_canonical_path_key))
    deleted = tuple(sorted(reference_keys - candidate_keys, key=_canonical_path_key))
    modified = tuple(
        sorted(
            (
                path
                for path in reference_keys & candidate_keys
                if reference[path] != candidate[path]
            ),
            key=_canonical_path_key,
        )
    )
    return SourceChangeSummary(added=added, modified=modified, deleted=deleted)


def _baseline(layout: BackendSourceLayout) -> tuple[str | None, dict[str, str] | None]:
    if layout.baseline_path is None:
        return None, None
    try:
        payload = json.loads(layout.baseline_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BackendSourceProvenanceError("release source baseline is unreadable") from error
    files = payload.get("files")
    if not isinstance(files, list):
        raise BackendSourceProvenanceError("release source baseline does not contain a file list")
    hashes: dict[str, str] = {}
    for raw in files:
        if (
            not isinstance(raw, dict)
            or not isinstance(raw.get("path"), str)
            or not isinstance(raw.get("sha256"), str)
        ):
            raise BackendSourceProvenanceError("release source baseline file entry is invalid")
        path = raw["path"].replace("\\", "/")
        if path.startswith("src/pilot_assessment/"):
            path = f"backend/{path}"
        elif not path.startswith(f"{CANONICAL_ARCHIVE_SOURCE_ROOT}/"):
            path = f"{CANONICAL_ARCHIVE_SOURCE_ROOT}/{path.lstrip('/')}"
        path = _canonical_path_key(path)
        if path in hashes:
            raise BackendSourceProvenanceError("release source baseline contains duplicate paths")
        hashes[path] = raw["sha256"].lower()
    baseline_hash = payload.get("tree_sha256") or payload.get("aggregate_sha256")
    if not isinstance(baseline_hash, str) or len(baseline_hash) != 64:
        raise BackendSourceProvenanceError("release source baseline hash is invalid")
    return baseline_hash.lower(), hashes


def _python_runtime_identity(product_root: Path) -> PythonRuntimeIdentity:
    executable = Path(sys.executable).resolve()
    if not executable.is_file():
        raise BackendSourceProvenanceError("active Python executable cannot be hashed")
    runtime_root = (product_root / "runtime" / "python").resolve()
    private = executable == runtime_root or executable.is_relative_to(runtime_root)
    payload = {
        "implementation": platform.python_implementation(),
        "version": platform.python_version(),
        "executable_name": executable.name,
        "executable_sha256": _sha256_file(executable),
        "private_runtime": private,
    }
    identity = typed_content_sha256("python-runtime-identity", "0.1.0", payload)
    return PythonRuntimeIdentity(**payload, identity_sha256=identity)


def _dependency_identity() -> DependencyManifestIdentity:
    packages: dict[str, str] = {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata["Name"]
        if not name:
            continue
        normalized = name.casefold().replace("_", "-")
        version = distribution.version
        existing = packages.get(normalized)
        if existing is not None and existing != version:
            raise BackendSourceProvenanceError(
                f"multiple installed versions found for dependency {normalized!r}"
            )
        packages[normalized] = version
    manifest = [{"name": name, "version": packages[name]} for name in sorted(packages)]
    return DependencyManifestIdentity(
        package_count=len(manifest),
        manifest_sha256=typed_content_sha256(
            "installed-python-dependency-manifest",
            "0.1.0",
            manifest,
        ),
    )


def _operator_catalog_identity(registry: OperatorRegistry) -> OperatorCatalogIdentity:
    catalog = [definition.model_dump(mode="json") for definition in registry.catalog()]
    return OperatorCatalogIdentity(
        operator_count=len(catalog),
        catalog_sha256=typed_content_sha256("operator-catalog", "0.1.0", catalog),
    )


def _identity_hash_payload(identity: dict[str, object]) -> dict[str, object]:
    """Return only execution-bearing fields; baseline labels are descriptive."""

    return {
        "identity_algorithm": identity["identity_algorithm"],
        "tree_algorithm": identity["tree_algorithm"],
        "source_tree_sha256": identity["source_tree_sha256"],
        "source_file_count": identity["source_file_count"],
        "pyproject_sha256": identity["pyproject_sha256"],
        "uv_lock_sha256": identity["uv_lock_sha256"],
        "python_runtime": identity["python_runtime"],
        "dependencies": identity["dependencies"],
        "operator_catalog": identity["operator_catalog"],
    }


class BackendSourceProvenance:
    """Own the exact source bytes and identities loaded by one sidecar process."""

    def __init__(
        self,
        layout: BackendSourceLayout,
        operator_registry: OperatorRegistry,
    ) -> None:
        self.layout = layout
        self._loaded_tree = _capture_source_tree(layout.source_root)
        self._pyproject_bytes = layout.pyproject_path.read_bytes()
        self._uv_lock_bytes = layout.uv_lock_path.read_bytes()
        baseline_hash, baseline_files = _baseline(layout)
        current_files = self._loaded_tree.logical_hashes
        changes = (
            SourceChangeSummary()
            if baseline_files is None
            else _change_summary(baseline_files, current_files)
        )
        runtime = _python_runtime_identity(layout.product_root)
        dependencies = _dependency_identity()
        operators = _operator_catalog_identity(operator_registry)
        raw: dict[str, object] = {
            "identity_algorithm": IDENTITY_ALGORITHM,
            "tree_algorithm": TREE_ALGORITHM,
            "active_source_root": layout.active_source_root,
            "source_tree_sha256": self._loaded_tree.tree_sha256,
            "source_file_count": len(self._loaded_tree.files),
            "release_baseline_sha256": baseline_hash,
            "baseline_available": baseline_files is not None,
            "locally_modified": None
            if baseline_files is None
            else bool(changes.added or changes.modified or changes.deleted),
            "baseline_changes": changes,
            "pyproject_sha256": _sha256_bytes(self._pyproject_bytes),
            "uv_lock_sha256": _sha256_bytes(self._uv_lock_bytes),
            "python_runtime": runtime,
            "dependencies": dependencies,
            "operator_catalog": operators,
        }
        identity_hash = typed_content_sha256(
            "backend-source-identity",
            "0.1.0",
            _identity_hash_payload(
                {
                    **raw,
                    "python_runtime": runtime.model_dump(mode="json"),
                    "dependencies": dependencies.model_dump(mode="json"),
                    "operator_catalog": operators.model_dump(mode="json"),
                }
            ),
        )
        self.loaded_identity = BackendSourceIdentity.model_validate(
            {**raw, "identity_sha256": identity_hash}
        )
        self.snapshot_bytes = self._build_snapshot_bytes()
        self.snapshot_sha256 = _sha256_bytes(self.snapshot_bytes)

    @classmethod
    def capture(
        cls,
        operator_registry: OperatorRegistry,
        *,
        product_root: str | Path | None = None,
    ) -> BackendSourceProvenance:
        return cls(BackendSourceLayout.discover(product_root), operator_registry)

    def disk_status(self) -> BackendSourceDiskStatus:
        current = _capture_source_tree(self.layout.source_root)
        pyproject_hash = _sha256_file(self.layout.pyproject_path)
        uv_lock_hash = _sha256_file(self.layout.uv_lock_path)
        loaded_hashes = self._loaded_tree.logical_hashes | {
            CANONICAL_ARCHIVE_PROJECT: self.loaded_identity.pyproject_sha256,
            CANONICAL_ARCHIVE_LOCK: self.loaded_identity.uv_lock_sha256,
        }
        current_hashes = current.logical_hashes | {
            CANONICAL_ARCHIVE_PROJECT: pyproject_hash,
            CANONICAL_ARCHIVE_LOCK: uv_lock_hash,
        }
        changes = _change_summary(loaded_hashes, current_hashes)
        restart = bool(changes.added or changes.modified or changes.deleted)
        return BackendSourceDiskStatus(
            loaded_identity=self.loaded_identity,
            disk_source_tree_sha256=current.tree_sha256,
            disk_pyproject_sha256=pyproject_hash,
            disk_uv_lock_sha256=uv_lock_hash,
            loaded_to_disk_changes=changes,
            runtime_restart_required=restart,
        )

    def _build_snapshot_bytes(self) -> bytes:
        payloads: dict[str, bytes] = {
            item.logical_path: item.payload for item in self._loaded_tree.files
        }
        payloads[CANONICAL_ARCHIVE_PROJECT] = self._pyproject_bytes
        payloads[CANONICAL_ARCHIVE_LOCK] = self._uv_lock_bytes
        manifest_files = tuple(
            SourceFileDigest(
                path=path,
                sha256=_sha256_bytes(payload),
                byte_size=len(payload),
            )
            for path, payload in sorted(
                payloads.items(), key=lambda item: _canonical_path_key(item[0])
            )
        )
        manifest = SourceSnapshotManifest(
            backend_identity=self.loaded_identity,
            files=manifest_files,
        )
        payloads[SNAPSHOT_MANIFEST_PATH] = jcs_bytes(manifest.model_dump(mode="json"))
        output = BytesIO()
        with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_STORED) as archive:
            for path, payload in sorted(
                payloads.items(), key=lambda item: _canonical_path_key(item[0])
            ):
                info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_STORED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, payload)
        return output.getvalue()


__all__ = [
    "BackendSourceLayout",
    "BackendSourceProvenance",
    "BackendSourceProvenanceError",
    "CANONICAL_ARCHIVE_LOCK",
    "CANONICAL_ARCHIVE_PROJECT",
    "CANONICAL_ARCHIVE_SOURCE_ROOT",
    "IDENTITY_ALGORITHM",
    "PRODUCT_ROOT_ENV",
    "SNAPSHOT_MANIFEST_PATH",
    "TREE_ALGORITHM",
]
