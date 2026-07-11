"""Read-only loader for a directory-form Session Bundle manifest."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, Literal, NoReturn

from pydantic import JsonValue, TypeAdapter, ValidationError

from pilot_assessment.contracts.common import BundleRelativePath
from pilot_assessment.contracts.errors import DomainErrorData, ErrorSeverity
from pilot_assessment.contracts.session import SessionManifest, StreamStatus

_CHECKSUM_LINE = re.compile(r"^([0-9A-Fa-f]{64})[ \t]+\*?(.+)$")
_BUNDLE_PATH_ADAPTER: Final = TypeAdapter(BundleRelativePath)
_VALIDATION_SCOPE: Final = "inspect_only_structure_and_declared_file_integrity"


class _DuplicateJsonKey(ValueError):
    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"duplicate JSON key: {key}")


class _NonstandardJsonConstant(ValueError):
    def __init__(self, constant: str) -> None:
        self.constant = constant
        super().__init__(f"nonstandard JSON constant: {constant}")


@dataclass(frozen=True, slots=True)
class ManifestLoaderLimits:
    max_manifest_bytes: int = 4 * 1024 * 1024
    max_checksum_bytes: int = 8 * 1024 * 1024
    max_declared_paths: int = 10_000
    max_checksum_entries: int = 10_000
    max_single_file_bytes: int = 64 * 1024 * 1024 * 1024
    max_total_hash_bytes: int = 256 * 1024 * 1024 * 1024

    def __post_init__(self) -> None:
        limits = (
            self.max_manifest_bytes,
            self.max_checksum_bytes,
            self.max_declared_paths,
            self.max_checksum_entries,
            self.max_single_file_bytes,
            self.max_total_hash_bytes,
        )
        if any(limit <= 0 for limit in limits):
            raise ValueError("all ManifestLoaderLimits values must be positive")


@dataclass(frozen=True, slots=True)
class LoadedManifest:
    manifest: SessionManifest
    bundle_root: Path
    manifest_path: Path
    verified_paths: tuple[str, ...]
    validation_scope: Literal["inspect_only_structure_and_declared_file_integrity"] = (
        _VALIDATION_SCOPE
    )


class ManifestLoadError(Exception):
    """Raised when a bundle cannot cross the M1 inspect-only validation boundary."""

    def __init__(self, error: DomainErrorData) -> None:
        self.error = error
        super().__init__(error.message)


class ManifestLoader:
    """Inspect a directory bundle without modifying or authorizing import.

    The result is intentionally not an immutable import snapshot. A later
    managed-storage importer must validate and copy from the same secured file
    handles before a session can be registered for formal assessment.
    """

    def __init__(self, limits: ManifestLoaderLimits | None = None) -> None:
        self._limits = limits or ManifestLoaderLimits()

    def load(self, bundle_root: str | Path) -> LoadedManifest:
        root = self._resolve_bundle_root(Path(bundle_root))
        manifest_path = self._resolve_manifest_path(root)
        raw_manifest = self._read_json_object(manifest_path)
        self._reject_unsupported_major(raw_manifest)
        manifest = self._validate_contract(raw_manifest)

        declared_paths = self._declared_local_paths(manifest)
        if len(declared_paths) > self._limits.max_declared_paths:
            self._fail_limit(
                limit_name="max_declared_paths",
                limit=self._limits.max_declared_paths,
                observed=len(declared_paths),
                field_or_path="manifest.json",
            )
        self._reject_duplicate_paths(declared_paths)
        resolved_declared = {
            relative_path: self._resolve_declared_file(root, relative_path, kind)
            for relative_path, kind in declared_paths
        }

        checksum_relative = manifest.integrity.checksum_file
        checksum_path = resolved_declared[checksum_relative]
        checksum_entries = self._parse_checksum_file(checksum_path)
        required_paths = self._require_declared_checksums(
            manifest,
            declared_paths,
            checksum_entries,
        )

        verified_paths: list[str] = []
        total_hashed_bytes = 0
        for relative_path in required_paths:
            expected_digest = checksum_entries[relative_path]
            resolved = resolved_declared[relative_path]
            file_size = self._file_size(resolved, relative_path)
            if file_size > self._limits.max_single_file_bytes:
                self._fail_limit(
                    limit_name="max_single_file_bytes",
                    limit=self._limits.max_single_file_bytes,
                    observed=file_size,
                    field_or_path=relative_path,
                )
            if total_hashed_bytes + file_size > self._limits.max_total_hash_bytes:
                self._fail_limit(
                    limit_name="max_total_hash_bytes",
                    limit=self._limits.max_total_hash_bytes,
                    observed=total_hashed_bytes + file_size,
                    field_or_path=relative_path,
                )
            remaining_total = self._limits.max_total_hash_bytes - total_hashed_bytes
            actual_digest, bytes_hashed = self._sha256(
                resolved,
                relative_path=relative_path,
                max_bytes=min(self._limits.max_single_file_bytes, remaining_total),
            )
            total_hashed_bytes += bytes_hashed
            if actual_digest != expected_digest:
                self._fail(
                    error_code="CHECKSUM_MISMATCH",
                    message="File content does not match its declared SHA-256 checksum",
                    field_or_path=relative_path,
                    remediation="Restore the original file or regenerate the bundle and checksums.",
                    diagnostics={
                        "expected_sha256": expected_digest,
                        "actual_sha256": actual_digest,
                    },
                )
            verified_paths.append(relative_path)

        return LoadedManifest(
            manifest=manifest,
            bundle_root=root,
            manifest_path=manifest_path,
            verified_paths=tuple(sorted(verified_paths)),
        )

    def _resolve_bundle_root(self, bundle_root: Path) -> Path:
        try:
            resolved = bundle_root.resolve(strict=True)
        except OSError:
            self._fail(
                error_code="INVALID_MANIFEST",
                message="Session bundle root does not exist",
                field_or_path=str(bundle_root),
                remediation="Select an existing directory-form Session Bundle.",
            )
        if not resolved.is_dir():
            self._fail(
                error_code="INVALID_MANIFEST",
                message="Session bundle root must be a directory in backend milestone M1",
                field_or_path=str(bundle_root),
                remediation="Select an unpacked bundle directory; zip support is deferred.",
            )
        return resolved

    def _resolve_manifest_path(self, root: Path) -> Path:
        manifest_path = root / "manifest.json"
        try:
            resolved = manifest_path.resolve(strict=True)
        except OSError:
            self._fail(
                error_code="INVALID_MANIFEST",
                message="Session bundle has no manifest.json",
                field_or_path="manifest.json",
                remediation="Place a UTF-8 manifest.json at the bundle root.",
            )
        if not resolved.is_relative_to(root) or not resolved.is_file():
            self._fail(
                error_code="INVALID_MANIFEST",
                message="manifest.json must be a regular file inside the bundle root",
                field_or_path="manifest.json",
                remediation="Replace the manifest link or special file with a local regular file.",
            )
        return resolved

    def _read_json_object(self, manifest_path: Path) -> dict[str, object]:
        payload = self._read_limited(
            manifest_path,
            max_bytes=self._limits.max_manifest_bytes,
            limit_name="max_manifest_bytes",
            field_or_path="manifest.json",
        )
        try:
            text = payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            self._fail(
                error_code="INVALID_MANIFEST",
                message="manifest.json must be readable UTF-8",
                field_or_path="manifest.json",
                remediation="Export the manifest as UTF-8 without binary or legacy encoding.",
                diagnostics={"exception_type": type(error).__name__},
            )
        try:
            value = json.loads(
                text,
                object_pairs_hook=self._json_object_without_duplicate_keys,
                parse_constant=self._reject_nonstandard_json_constant,
            )
        except _DuplicateJsonKey as error:
            self._fail(
                error_code="INVALID_MANIFEST",
                message="manifest.json contains a duplicate object key",
                field_or_path="manifest.json",
                remediation="Keep exactly one value for every JSON object key.",
                diagnostics={
                    "json_error_type": "duplicate_key",
                    "duplicate_json_key": error.key,
                },
            )
        except _NonstandardJsonConstant as error:
            self._fail(
                error_code="INVALID_MANIFEST",
                message="manifest.json contains a nonstandard numeric constant",
                field_or_path="manifest.json",
                remediation="Replace NaN or Infinity with a valid finite JSON value.",
                diagnostics={
                    "json_error_type": "nonstandard_constant",
                    "constant": error.constant,
                },
            )
        except (json.JSONDecodeError, ValueError, RecursionError) as error:
            diagnostics: dict[str, JsonValue] = {
                "json_error_type": type(error).__name__,
            }
            if isinstance(error, json.JSONDecodeError):
                diagnostics.update({"line": error.lineno, "column": error.colno})
            self._fail(
                error_code="INVALID_MANIFEST",
                message="manifest.json contains invalid JSON",
                field_or_path="manifest.json",
                remediation="Correct the JSON syntax and retry validation.",
                diagnostics=diagnostics,
            )
        if not isinstance(value, dict):
            self._fail(
                error_code="INVALID_MANIFEST",
                message="manifest.json must contain a JSON object",
                field_or_path="manifest.json",
                remediation="Export the SessionManifest as a top-level JSON object.",
            )
        return value

    @staticmethod
    def _json_object_without_duplicate_keys(
        pairs: list[tuple[str, object]],
    ) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise _DuplicateJsonKey(key)
            result[key] = value
        return result

    @staticmethod
    def _reject_nonstandard_json_constant(constant: str) -> NoReturn:
        raise _NonstandardJsonConstant(constant)

    def _reject_unsupported_major(self, raw_manifest: dict[str, object]) -> None:
        version = raw_manifest.get("bundle_schema_version")
        if isinstance(version, str):
            match = re.match(r"^(\d+)\.", version)
            if match is not None and int(match.group(1)) != 0:
                self._fail(
                    error_code="SCHEMA_INCOMPATIBLE",
                    message=f"Bundle schema major {match.group(1)} is not supported",
                    field_or_path="bundle_schema_version",
                    remediation="Use a compatible 0.x bundle or install a compatible core version.",
                    diagnostics={"supported_major": 0, "received_version": version},
                )

    def _validate_contract(self, raw_manifest: dict[str, object]) -> SessionManifest:
        try:
            return SessionManifest.model_validate(raw_manifest)
        except ValidationError as error:
            validation_errors = [
                {
                    "location": [str(part) for part in item["loc"]],
                    "message": item["msg"],
                    "type": item["type"],
                }
                for item in error.errors(
                    include_url=False,
                    include_context=False,
                    include_input=False,
                )
            ]
            self._fail(
                error_code="INVALID_MANIFEST",
                message="manifest.json does not satisfy SessionManifest 0.x",
                field_or_path="manifest.json",
                remediation=(
                    "Correct the reported fields using the published SessionManifest schema."
                ),
                diagnostics={"validation_errors": validation_errors},
            )

    def _declared_local_paths(self, manifest: SessionManifest) -> list[tuple[str, str]]:
        declared: list[tuple[str, str]] = []
        for descriptor in manifest.streams.values():
            if descriptor.status is StreamStatus.PRESENT:
                declared.extend((path, "stream") for path in descriptor.paths)
        declared.extend(
            [
                (manifest.annotations.phases, "annotation"),
                (manifest.annotations.events, "annotation"),
                (manifest.annotations.baseline_intervals, "annotation"),
                (manifest.integrity.checksum_file, "integrity"),
            ]
        )
        return declared

    def _reject_duplicate_paths(self, declared_paths: list[tuple[str, str]]) -> None:
        by_casefold: dict[str, list[str]] = {}
        for relative_path, _kind in declared_paths:
            by_casefold.setdefault(relative_path.casefold(), []).append(relative_path)
        duplicates = [paths for paths in by_casefold.values() if len(paths) > 1]
        if duplicates:
            self._fail(
                error_code="INVALID_MANIFEST",
                message="Bundle declares duplicate paths under Windows case-insensitive rules",
                field_or_path="manifest.json",
                remediation="Give every declared artifact a unique canonical relative path.",
                diagnostics={"duplicate_paths": duplicates},
            )

    def _resolve_declared_file(self, root: Path, relative_path: str, kind: str) -> Path:
        error_code = "STREAM_MISSING" if kind == "stream" else "INVALID_MANIFEST"
        return self._resolve_file_below_root(
            root,
            relative_path,
            error_code=error_code,
            missing_message=f"Declared {kind} file is missing",
        )

    def _resolve_file_below_root(
        self,
        root: Path,
        relative_path: str,
        *,
        error_code: str,
        missing_message: str,
    ) -> Path:
        candidate = root.joinpath(*PurePosixPath(relative_path).parts)
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            self._fail(
                error_code=error_code,
                message=missing_message,
                field_or_path=relative_path,
                remediation="Restore the declared file or regenerate the Session Bundle.",
            )
        if not resolved.is_relative_to(root):
            self._fail(
                error_code="INVALID_MANIFEST",
                message="Declared file resolves outside the bundle root",
                field_or_path=relative_path,
                remediation=(
                    "Remove the escaping symlink, junction or path and package the file locally."
                ),
            )
        if not resolved.is_file():
            self._fail(
                error_code=error_code,
                message="Declared bundle path is not a regular file",
                field_or_path=relative_path,
                remediation="Replace it with the declared regular file.",
            )
        return resolved

    def _parse_checksum_file(self, checksum_path: Path) -> dict[str, str]:
        payload = self._read_limited(
            checksum_path,
            max_bytes=self._limits.max_checksum_bytes,
            limit_name="max_checksum_bytes",
            field_or_path=checksum_path.name,
        )
        try:
            lines = payload.decode("utf-8", errors="strict").splitlines()
        except UnicodeDecodeError as error:
            self._fail(
                error_code="INVALID_MANIFEST",
                message="Checksum manifest must be readable UTF-8",
                field_or_path=checksum_path.name,
                remediation="Regenerate integrity/checksums.sha256 as UTF-8 text.",
                diagnostics={"exception_type": type(error).__name__},
            )

        entries: dict[str, str] = {}
        casefold_paths: set[str] = set()
        for line_number, line in enumerate(lines, start=1):
            if not line or line.startswith("#"):
                continue
            match = _CHECKSUM_LINE.fullmatch(line)
            if match is None:
                self._fail(
                    error_code="INVALID_MANIFEST",
                    message="Checksum manifest contains an invalid line",
                    field_or_path=f"{checksum_path.name}:{line_number}",
                    remediation="Use '<64-hex-sha256>  <POSIX-relative-path>' per line.",
                )
            digest, unvalidated_path = match.groups()
            try:
                relative_path = _BUNDLE_PATH_ADAPTER.validate_python(unvalidated_path)
            except ValidationError:
                self._fail(
                    error_code="INVALID_MANIFEST",
                    message="Checksum manifest contains an unsafe relative path",
                    field_or_path=f"{checksum_path.name}:{line_number}",
                    remediation="Use a canonical POSIX path contained by the bundle root.",
                    diagnostics={"declared_path": unvalidated_path},
                )
            folded = relative_path.casefold()
            if folded in casefold_paths:
                self._fail(
                    error_code="INVALID_MANIFEST",
                    message="Checksum manifest contains a duplicate path",
                    field_or_path=f"{checksum_path.name}:{line_number}",
                    remediation="Keep exactly one checksum entry per canonical file path.",
                )
            if len(entries) >= self._limits.max_checksum_entries:
                self._fail_limit(
                    limit_name="max_checksum_entries",
                    limit=self._limits.max_checksum_entries,
                    observed=len(entries) + 1,
                    field_or_path=checksum_path.name,
                )
            casefold_paths.add(folded)
            entries[relative_path] = digest.lower()
        if not entries:
            self._fail(
                error_code="INVALID_MANIFEST",
                message="Checksum manifest contains no file entries",
                field_or_path=checksum_path.name,
                remediation="Regenerate checksums for all declared bundle-local files.",
            )
        return entries

    def _require_declared_checksums(
        self,
        manifest: SessionManifest,
        declared_paths: list[tuple[str, str]],
        checksum_entries: dict[str, str],
    ) -> tuple[str, ...]:
        checksum_file = manifest.integrity.checksum_file
        required_paths = {path for path, _kind in declared_paths if path != checksum_file}
        missing = sorted(required_paths - checksum_entries.keys())
        undeclared = sorted(checksum_entries.keys() - required_paths)
        if missing or undeclared:
            self._fail(
                error_code="INVALID_MANIFEST",
                message="Checksum manifest scope must exactly match declared bundle-local files",
                field_or_path=checksum_file,
                remediation=(
                    "Regenerate the checksum manifest with exactly the present streams "
                    "and annotation files declared by manifest.json."
                ),
                diagnostics={
                    "missing_checksum_paths": missing,
                    "undeclared_checksum_paths": undeclared,
                },
            )

        for descriptor in manifest.streams.values():
            if descriptor.status is not StreamStatus.PRESENT:
                continue
            for relative_path, descriptor_digest in descriptor.checksums.items():
                checksum_digest = checksum_entries.get(relative_path)
                if checksum_digest != descriptor_digest:
                    self._fail(
                        error_code="CHECKSUM_MISMATCH",
                        message="Stream descriptor and checksum manifest disagree",
                        field_or_path=relative_path,
                        remediation=(
                            "Regenerate the manifest and checksum file from the same export."
                        ),
                        diagnostics={
                            "stream_descriptor_sha256": descriptor_digest,
                            "checksum_manifest_sha256": checksum_digest,
                        },
                    )
        return tuple(sorted(required_paths))

    def _read_limited(
        self,
        path: Path,
        *,
        max_bytes: int,
        limit_name: str,
        field_or_path: str,
    ) -> bytes:
        try:
            with path.open("rb") as source:
                payload = source.read(max_bytes + 1)
        except OSError as error:
            self._fail(
                error_code="INVALID_MANIFEST",
                message="Declared bundle metadata could not be read",
                field_or_path=field_or_path,
                remediation="Restore file access and retry bundle inspection.",
                diagnostics={"exception_type": type(error).__name__},
            )
        if len(payload) > max_bytes:
            self._fail_limit(
                limit_name=limit_name,
                limit=max_bytes,
                observed=len(payload),
                field_or_path=field_or_path,
            )
        return payload

    def _file_size(self, path: Path, relative_path: str) -> int:
        try:
            return path.stat().st_size
        except OSError as error:
            self._fail(
                error_code="INVALID_MANIFEST",
                message="Declared bundle file changed or became inaccessible",
                field_or_path=relative_path,
                remediation="Stop modifying the source bundle and retry inspection.",
                diagnostics={"exception_type": type(error).__name__},
            )

    def _sha256(
        self,
        path: Path,
        *,
        relative_path: str,
        max_bytes: int,
    ) -> tuple[str, int]:
        digest = hashlib.sha256()
        bytes_hashed = 0
        try:
            with path.open("rb") as source:
                while chunk := source.read(min(1024 * 1024, max_bytes - bytes_hashed + 1)):
                    bytes_hashed += len(chunk)
                    if bytes_hashed > max_bytes:
                        self._fail_limit(
                            limit_name="hash_byte_budget",
                            limit=max_bytes,
                            observed=bytes_hashed,
                            field_or_path=relative_path,
                        )
                    digest.update(chunk)
        except ManifestLoadError:
            raise
        except OSError as error:
            self._fail(
                error_code="INVALID_MANIFEST",
                message="Declared bundle file changed or could not be hashed",
                field_or_path=relative_path,
                remediation="Stop modifying the source bundle, restore access and retry.",
                diagnostics={"exception_type": type(error).__name__},
            )
        return digest.hexdigest(), bytes_hashed

    @classmethod
    def _fail_limit(
        cls,
        *,
        limit_name: str,
        limit: int,
        observed: int,
        field_or_path: str,
    ) -> NoReturn:
        cls._fail(
            error_code="INVALID_MANIFEST",
            message="Session Bundle inspection limit exceeded",
            field_or_path=field_or_path,
            remediation="Reduce the bundle metadata or configure an approved higher limit.",
            diagnostics={
                "limit_name": limit_name,
                "limit": limit,
                "observed": observed,
            },
        )

    @staticmethod
    def _fail(
        *,
        error_code: str,
        message: str,
        field_or_path: str | None,
        remediation: str,
        diagnostics: dict[str, JsonValue] | None = None,
    ) -> NoReturn:
        raise ManifestLoadError(
            DomainErrorData(
                error_code=error_code,
                severity=ErrorSeverity.ERROR,
                recoverable=True,
                message=message,
                field_or_path=field_or_path,
                remediation=remediation,
                diagnostics=diagnostics or {},
            )
        )


__all__ = [
    "LoadedManifest",
    "ManifestLoadError",
    "ManifestLoader",
    "ManifestLoaderLimits",
]
