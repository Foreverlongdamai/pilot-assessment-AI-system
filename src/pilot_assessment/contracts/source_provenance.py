"""Immutable identities for the exact editable Python backend used by a run."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import StrictBool, StringConstraints, model_validator

from pilot_assessment.contracts.common import (
    BundleRelativePath,
    NonNegativeInt,
    NonNegativeInt64,
    Sha256Digest,
    StrictContractModel,
)

ShortText = Annotated[str, StringConstraints(min_length=1, max_length=256)]


def _require_canonical_paths(values: tuple[str, ...], label: str) -> None:
    folded = tuple(value.casefold() for value in values)
    if len(folded) != len(set(folded)):
        raise ValueError(f"{label} must not contain case-insensitive duplicates")
    if folded != tuple(sorted(folded)):
        raise ValueError(f"{label} must use canonical case-insensitive path order")


class SourceFileDigest(StrictContractModel):
    """One normalized first-party file identity."""

    path: BundleRelativePath
    sha256: Sha256Digest
    byte_size: NonNegativeInt64


class SourceChangeSummary(StrictContractModel):
    """Difference between a loaded tree and a reference tree."""

    added: tuple[BundleRelativePath, ...] = ()
    modified: tuple[BundleRelativePath, ...] = ()
    deleted: tuple[BundleRelativePath, ...] = ()

    @model_validator(mode="after")
    def validate_paths(self) -> Self:
        for label, values in (
            ("added paths", self.added),
            ("modified paths", self.modified),
            ("deleted paths", self.deleted),
        ):
            _require_canonical_paths(values, label)
        combined = tuple(value.casefold() for value in (*self.added, *self.modified, *self.deleted))
        if len(combined) != len(set(combined)):
            raise ValueError("one path cannot appear in multiple source change categories")
        return self


class PythonRuntimeIdentity(StrictContractModel):
    implementation: ShortText
    version: ShortText
    executable_name: ShortText
    executable_sha256: Sha256Digest
    private_runtime: StrictBool
    identity_sha256: Sha256Digest


class DependencyManifestIdentity(StrictContractModel):
    package_count: NonNegativeInt
    manifest_sha256: Sha256Digest


class OperatorCatalogIdentity(StrictContractModel):
    operator_count: NonNegativeInt
    catalog_sha256: Sha256Digest


class BackendSourceIdentity(StrictContractModel):
    """Frozen technical identity of one imported backend process."""

    contract_id: Literal["backend-source-identity"] = "backend-source-identity"
    contract_version: Literal["0.1.0"] = "0.1.0"
    identity_algorithm: Literal["pilot-assessment-backend-identity-v1"] = (
        "pilot-assessment-backend-identity-v1"
    )
    tree_algorithm: Literal["pilot-assessment-source-tree-v2"] = "pilot-assessment-source-tree-v2"
    active_source_root: BundleRelativePath
    source_tree_sha256: Sha256Digest
    source_file_count: NonNegativeInt
    release_baseline_sha256: Sha256Digest | None
    baseline_available: StrictBool
    locally_modified: StrictBool | None
    baseline_changes: SourceChangeSummary
    pyproject_sha256: Sha256Digest
    uv_lock_sha256: Sha256Digest
    python_runtime: PythonRuntimeIdentity
    dependencies: DependencyManifestIdentity
    operator_catalog: OperatorCatalogIdentity
    identity_sha256: Sha256Digest

    @model_validator(mode="after")
    def validate_baseline_state(self) -> Self:
        if self.baseline_available:
            if self.release_baseline_sha256 is None or self.locally_modified is None:
                raise ValueError("available release baseline requires hash and comparison result")
        elif self.release_baseline_sha256 is not None or self.locally_modified is not None:
            raise ValueError("unavailable release baseline cannot claim hash or modified state")
        if self.locally_modified is False and any(
            (
                self.baseline_changes.added,
                self.baseline_changes.modified,
                self.baseline_changes.deleted,
            )
        ):
            raise ValueError("clean baseline comparison cannot contain changed paths")
        return self


class BackendSourceDiskStatus(StrictContractModel):
    """Current disk comparison against the process-frozen loaded identity."""

    contract_id: Literal["backend-source-disk-status"] = "backend-source-disk-status"
    contract_version: Literal["0.1.0"] = "0.1.0"
    loaded_identity: BackendSourceIdentity
    disk_source_tree_sha256: Sha256Digest
    disk_pyproject_sha256: Sha256Digest
    disk_uv_lock_sha256: Sha256Digest
    loaded_to_disk_changes: SourceChangeSummary
    runtime_restart_required: StrictBool


class SourceSnapshotManifest(StrictContractModel):
    """Deterministic manifest embedded in a project source snapshot archive."""

    contract_id: Literal["backend-source-snapshot-manifest"] = "backend-source-snapshot-manifest"
    contract_version: Literal["0.1.0"] = "0.1.0"
    archive_schema: Literal["pilot-assessment-backend-source-snapshot-v1"] = (
        "pilot-assessment-backend-source-snapshot-v1"
    )
    backend_identity: BackendSourceIdentity
    files: tuple[SourceFileDigest, ...]

    @model_validator(mode="after")
    def validate_files(self) -> Self:
        paths = tuple(item.path for item in self.files)
        _require_canonical_paths(paths, "snapshot files")
        return self


__all__ = [
    "BackendSourceDiskStatus",
    "BackendSourceIdentity",
    "DependencyManifestIdentity",
    "OperatorCatalogIdentity",
    "PythonRuntimeIdentity",
    "SourceChangeSummary",
    "SourceFileDigest",
    "SourceSnapshotManifest",
]
