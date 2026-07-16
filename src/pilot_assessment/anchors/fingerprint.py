"""Canonical M4 fingerprints and installed numeric-runtime identities.

This module is deliberately limited to pure identity projections plus the
three Task 8-owned trust boundaries: packaged catalog identity (called by the
catalog loader), installed wheel ``RECORD`` identity, and immutable logical
artifact validation.  Registry, result, report, and request claim validation
remain owned by their later M4 tasks.
"""

from __future__ import annotations

import base64
import binascii
import csv
import hashlib
import io
import json
import os
import re
import sys
import sysconfig
from collections.abc import Mapping, Sequence
from importlib.metadata import distribution
from pathlib import Path, PurePosixPath
from typing import NoReturn, cast

import polars as pl
from pydantic import BaseModel, JsonValue

from pilot_assessment.anchors.protocols import (
    ReadOnlyBlobPayload,
    ReadOnlyTabularPayload,
    ResolvedArtifactDependency,
)
from pilot_assessment.contracts.anchor_execution import (
    REFERENCE_DTYPE_IDS,
    AnchorCatalog,
    AnchorEvaluationReport,
    AnchorExecutionPlan,
    AnchorPluginDefinition,
    AnchorRuntimeRegistry,
    NumericRuntimeIdentity,
    PluginRegistryEntry,
    PreprocessingProviderDefinition,
    PreprocessingRegistryEntry,
    PythonRuntimeIdentity,
    ReferenceSessionIdentity,
    ReferenceTableContract,
    ResolvedReferenceDescriptor,
    ResolvedReferenceSetSnapshot,
    ScorerPolicy,
    SessionSemanticSnapshot,
)
from pilot_assessment.contracts.anchor_v2 import AnchorArtifactRef, AnchorResultV2
from pilot_assessment.contracts.common import Sha256Digest, StableId
from pilot_assessment.model_library.identity import (
    I_JSON_SAFE_INTEGER_MAX,
    jcs_bytes,
    typed_content_sha256,
)
from pilot_assessment.model_library.identity import (
    canonical_json_value as _json_projection,
)

_SAFE_INTEGER = I_JSON_SAFE_INTEGER_MAX
_F32_MAX = 3.4028234663852886e38
_TYPE_VERSION = "0.1.0"
_TABLE_DESCRIPTOR_KEYS = frozenset({"type", "fields", "canonical_order_keys"})
_TABLE_FIELD_KEYS = frozenset({"name", "dtype", "unit", "nullable"})
_BLOB_DESCRIPTOR_KEYS = frozenset({"type", "media_type", "content_encoding"})
_INTEGER_BOUNDS: dict[str, tuple[int, int]] = {
    "i8": (-(2**7), 2**7 - 1),
    "i16": (-(2**15), 2**15 - 1),
    "i32": (-(2**31), 2**31 - 1),
    "i64": (-(2**63), 2**63 - 1),
    "u8": (0, 2**8 - 1),
    "u16": (0, 2**16 - 1),
    "u32": (0, 2**32 - 1),
    "u64": (0, 2**64 - 1),
}
_WINDOWS_EXT_SUFFIX = re.compile(r"\.([A-Za-z0-9][A-Za-z0-9_-]*)\.pyd", re.ASCII)
_PEP503_RUN = re.compile(r"[-_.]+")
_CANONICAL_SHA256_B64 = re.compile(r"[A-Za-z0-9_-]{43}", re.ASCII)
_CANONICAL_NONNEGATIVE_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)", re.ASCII)


def typed_json_sha256(type_id: str, schema_version: str, value: object) -> str:
    """Preserve the legacy public API while using the shared primitive."""

    return typed_content_sha256(type_id, schema_version, value)


def _require_plain_sequence(value: object, *, label: str) -> list[object]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{label} must be an ordered JSON array")
    return list(value)


def _validate_inline_descriptor(
    descriptor: Mapping[str, JsonValue],
) -> tuple[list[dict[str, JsonValue]], list[str]] | None:
    if not isinstance(descriptor, Mapping):
        raise TypeError("schema descriptor must be a mapping")
    keys = frozenset(descriptor)
    descriptor_type = descriptor.get("type")
    if descriptor_type == "table":
        if keys != _TABLE_DESCRIPTOR_KEYS:
            raise ValueError("table descriptor has an incomplete or extra field set")
        raw_fields = _require_plain_sequence(descriptor["fields"], label="descriptor fields")
        raw_order_keys = _require_plain_sequence(
            descriptor["canonical_order_keys"], label="canonical order keys"
        )
        if not raw_fields or not raw_order_keys:
            raise ValueError("table descriptor fields and order keys must be non-empty")
        fields: list[dict[str, JsonValue]] = []
        names: list[str] = []
        nullable_by_name: dict[str, bool] = {}
        for raw_field in raw_fields:
            if not isinstance(raw_field, Mapping) or frozenset(raw_field) != _TABLE_FIELD_KEYS:
                raise ValueError("table descriptor fields must have exactly four members")
            name = raw_field.get("name")
            dtype = raw_field.get("dtype")
            unit = raw_field.get("unit")
            nullable = raw_field.get("nullable")
            if type(name) is not str or not name:
                raise ValueError("table descriptor field names must be non-empty strings")
            if type(dtype) is not str or dtype not in REFERENCE_DTYPE_IDS:
                raise ValueError("table descriptor dtype is not an allowed primitive")
            if type(unit) is not str or not unit:
                raise ValueError("table descriptor units must be non-empty strings")
            if type(nullable) is not bool:
                raise ValueError("table descriptor nullable must be an exact boolean")
            _json_projection(name)
            _json_projection(unit)
            names.append(name)
            nullable_by_name[name] = nullable
            fields.append({"name": name, "dtype": dtype, "unit": unit, "nullable": nullable})
        if len(names) != len(set(names)):
            raise ValueError("table descriptor field names must be unique")
        order_keys: list[str] = []
        for raw_key in raw_order_keys:
            if type(raw_key) is not str or raw_key not in nullable_by_name:
                raise ValueError("canonical order keys must name declared fields")
            if nullable_by_name[raw_key]:
                raise ValueError("canonical order keys must be non-nullable")
            order_keys.append(raw_key)
        if len(order_keys) != len(set(order_keys)):
            raise ValueError("canonical order keys must be unique")
        return fields, order_keys
    if descriptor_type == "blob":
        if keys != _BLOB_DESCRIPTOR_KEYS:
            raise ValueError("blob descriptor has an incomplete or extra field set")
        media_type = descriptor.get("media_type")
        content_encoding = descriptor.get("content_encoding")
        if (
            type(media_type) is not str
            or not media_type
            or media_type.strip() != media_type
            or "/" not in media_type
            or type(content_encoding) is not str
            or not content_encoding
            or content_encoding.strip() != content_encoding
        ):
            raise ValueError("blob descriptor requires canonical media type and encoding")
        _json_projection(descriptor)
        return None
    raise ValueError("schema descriptor type must be table or blob")


def schema_descriptor_sha256(schema_id: str, descriptor: Mapping[str, JsonValue]) -> str:
    _validate_inline_descriptor(descriptor)
    return typed_json_sha256(
        "typed-inline-schema-descriptor", _TYPE_VERSION, [schema_id, descriptor]
    )


def _validate_table_value(value: object, *, dtype: str, nullable: bool) -> JsonValue:
    if value is None:
        if nullable:
            return None
        raise ValueError("non-nullable logical-table field contains null")
    if dtype == "bool":
        if type(value) is not bool:
            raise TypeError("bool logical-table fields require exact booleans")
        return value
    if dtype in _INTEGER_BOUNDS:
        if type(value) is not int:
            raise TypeError("integer logical-table fields require exact integers")
        lower, upper = _INTEGER_BOUNDS[dtype]
        if not lower <= value <= upper:
            raise ValueError("logical-table integer lies outside its declared dtype")
        return _json_projection(value)
    if dtype in {"f32", "f64"}:
        if type(value) is not float:
            raise TypeError("float logical-table fields require exact floats")
        if dtype == "f32" and abs(value) > _F32_MAX:
            raise ValueError("logical-table float lies outside finite IEEE-754 f32 bounds")
        return _json_projection(value)
    if dtype == "utf8":
        if type(value) is not str:
            raise TypeError("utf8 logical-table fields require exact strings")
        return _json_projection(value)
    raise ValueError("logical-table dtype is not supported")


def _compare_order_values(left: object, right: object, dtype: str) -> int:
    if dtype == "bool":
        left_value = int(cast(bool, left))
        right_value = int(cast(bool, right))
        return (left_value > right_value) - (left_value < right_value)
    elif dtype in _INTEGER_BOUNDS:
        left_value = cast(int, left)
        right_value = cast(int, right)
        return (left_value > right_value) - (left_value < right_value)
    elif dtype in {"f32", "f64"}:
        left_value = cast(float, left)
        right_value = cast(float, right)
        return (left_value > right_value) - (left_value < right_value)
    elif dtype == "utf8":
        left_value = cast(str, left)
        right_value = cast(str, right)
        return (left_value > right_value) - (left_value < right_value)
    else:  # pragma: no cover - descriptor validation owns this branch
        raise ValueError("logical-table order dtype is not supported")


def _strictly_increasing_key(
    current: tuple[object, ...],
    previous: tuple[object, ...],
    dtypes: tuple[str, ...],
) -> bool:
    for left, right, dtype in zip(current, previous, dtypes, strict=True):
        comparison = _compare_order_values(left, right, dtype)
        if comparison:
            return comparison > 0
    return False


def logical_table_sha256(
    schema_id: str,
    schema_descriptor: Mapping[str, JsonValue],
    rows: Sequence[Mapping[str, JsonValue]],
    order_keys: Sequence[str],
) -> str:
    validated = _validate_inline_descriptor(schema_descriptor)
    if validated is None:
        raise ValueError("logical tables require a table schema descriptor")
    fields, descriptor_order_keys = validated
    if not isinstance(order_keys, (list, tuple)) or any(type(key) is not str for key in order_keys):
        raise TypeError("logical-table order keys must be an ordered string sequence")
    if list(order_keys) != descriptor_order_keys:
        raise ValueError("logical-table order keys do not match the descriptor")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise TypeError("logical-table rows must be an ordered sequence")

    field_names = [cast(str, field["name"]) for field in fields]
    expected_names = frozenset(field_names)
    field_by_name = {cast(str, field["name"]): field for field in fields}
    order_dtypes = tuple(cast(str, field_by_name[key]["dtype"]) for key in descriptor_order_keys)
    row_arrays: list[list[JsonValue]] = []
    previous_key: tuple[object, ...] | None = None
    for row in rows:
        if not isinstance(row, Mapping) or frozenset(row) != expected_names:
            raise ValueError("logical-table rows must have exactly the declared fields")
        projected_by_name: dict[str, JsonValue] = {}
        for field in fields:
            name = cast(str, field["name"])
            projected_by_name[name] = _validate_table_value(
                row[name],
                dtype=cast(str, field["dtype"]),
                nullable=cast(bool, field["nullable"]),
            )
        key = tuple(projected_by_name[key_name] for key_name in descriptor_order_keys)
        if previous_key is not None and not _strictly_increasing_key(
            key, previous_key, order_dtypes
        ):
            raise ValueError("logical-table rows must be strictly increasing by the full key")
        previous_key = key
        row_arrays.append([projected_by_name[name] for name in field_names])

    # Keep the complete caller descriptor in the identity, after closed validation.
    payload = [[schema_id, schema_descriptor, list(order_keys)], row_arrays]
    return typed_json_sha256("logical-table", _TYPE_VERSION, payload)


def _model_payload(model: BaseModel, *, excluded: set[str]) -> dict[str, JsonValue]:
    dumped = model.model_dump(mode="json", exclude=excluded)
    return cast(dict[str, JsonValue], dumped)


def session_semantic_snapshot_fingerprint(snapshot: SessionSemanticSnapshot) -> Sha256Digest:
    return typed_json_sha256(
        "session-semantic-snapshot",
        _TYPE_VERSION,
        _model_payload(snapshot, excluded={"semantic_snapshot_fingerprint"}),
    )


def reference_table_contract_fingerprint(contract: ReferenceTableContract) -> Sha256Digest:
    return typed_json_sha256(
        "reference-table-contract",
        _TYPE_VERSION,
        _model_payload(contract, excluded={"table_contract_fingerprint"}),
    )


def _require_present_reference(descriptor: ResolvedReferenceDescriptor) -> None:
    if descriptor.resolution_status.value != "present":
        raise ValueError("the reference identity is defined only for present descriptors")


def reference_resource_fingerprint(descriptor: ResolvedReferenceDescriptor) -> Sha256Digest:
    _require_present_reference(descriptor)
    payload = [
        descriptor.reference_id,
        descriptor.source_kind.value,
        descriptor.runtime_view_role,
        descriptor.source_schema_id,
        descriptor.table_contract.table_contract_fingerprint,
        [[item.path, item.checksum] for item in descriptor.resource_checksums],
    ]
    return typed_json_sha256("reference-resource", _TYPE_VERSION, payload)


def _reference_inline_descriptor(contract: ReferenceTableContract) -> dict[str, JsonValue]:
    return {
        "type": "table",
        "fields": [
            {
                "name": field.field_name,
                "dtype": field.dtype_id,
                "unit": field.unit,
                "nullable": field.nullable,
            }
            for field in contract.fields
        ],
        "canonical_order_keys": list(contract.canonical_order_keys),
    }


def aligned_reference_content_fingerprint(
    table: pl.DataFrame,
    aligned_schema_id: StableId,
    contract: ReferenceTableContract,
) -> Sha256Digest:
    if not isinstance(table, pl.DataFrame):
        raise TypeError("aligned reference content must be a Polars DataFrame")
    declared_columns = [field.field_name for field in contract.fields]
    if table.columns != declared_columns:
        raise ValueError("aligned reference columns must match declared physical order")
    return logical_table_sha256(
        aligned_schema_id,
        _reference_inline_descriptor(contract),
        table.to_dicts(),
        contract.canonical_order_keys,
    )


def reference_alignment_fingerprint(
    descriptor: ResolvedReferenceDescriptor,
    session_identity: ReferenceSessionIdentity,
) -> Sha256Digest:
    _require_present_reference(descriptor)
    payload = {
        "session_identity": session_identity.model_dump(mode="json"),
        "reference_id": descriptor.reference_id,
        "source_kind": descriptor.source_kind.value,
        "runtime_view_role": descriptor.runtime_view_role,
        "alignment_contract": descriptor.alignment_contract.model_dump(mode="json"),
        "clock_id": descriptor.clock_id,
        "source_schema_id": descriptor.source_schema_id,
        "aligned_schema_id": descriptor.aligned_schema_id,
        "table_contract_fingerprint": descriptor.table_contract.table_contract_fingerprint,
        "resource_fingerprint": descriptor.resource_fingerprint,
        "aligned_content_fingerprint": descriptor.aligned_content_fingerprint,
    }
    return typed_json_sha256("reference-alignment", _TYPE_VERSION, payload)


def resolved_reference_set_fingerprint(
    snapshot: ResolvedReferenceSetSnapshot,
) -> Sha256Digest:
    return typed_json_sha256(
        "resolved-reference-set",
        _TYPE_VERSION,
        _model_payload(snapshot, excluded={"reference_set_fingerprint"}),
    )


def logical_artifact_identity_payload(ref: AnchorArtifactRef) -> dict[str, JsonValue]:
    return _model_payload(ref, excluded={"storage_file_sha256"})


def validate_logical_artifact_ref(
    ref: AnchorArtifactRef,
    resolved: ResolvedArtifactDependency,
) -> None:
    """Reject an emitted ref unless immutable resolved content proves every claim."""

    if not isinstance(ref, AnchorArtifactRef) or not isinstance(
        resolved, ResolvedArtifactDependency
    ):
        raise TypeError("artifact validation requires typed reference and resolved dependency")
    if ref != resolved.ref:
        raise ValueError("artifact reference does not equal the immutable resolved reference")
    payload = resolved.payload
    if (
        ref.schema_id != payload.schema_id
        or ref.kind != payload.artifact_kind
        or ref.start_t_ns != payload.start_t_ns
        or ref.end_t_ns != payload.end_t_ns
        or ref.logical_content_sha256 != payload.logical_content_sha256
    ):
        raise ValueError("artifact reference identity does not match immutable payload metadata")
    if isinstance(payload, ReadOnlyTabularPayload):
        if ref.row_count != payload.frame.height or ref.grid_hash != payload.grid_hash:
            raise ValueError("table artifact shape, bounds, or grid identity does not match")
        recomputed = logical_table_sha256(
            payload.schema_id,
            payload.schema_descriptor,
            payload.frame.to_dicts(),
            payload.order_keys,
        )
    elif isinstance(payload, ReadOnlyBlobPayload):
        if ref.row_count != 0 or ref.grid_hash is not None:
            raise ValueError("blob artifacts require zero rows and no grid")
        recomputed = hashlib.sha256(payload.payload_bytes).hexdigest()
        if ref.storage_file_sha256 != recomputed:
            raise ValueError("blob logical and storage digests must both equal raw content")
    else:  # pragma: no cover - protected by the frozen dependency contract
        raise TypeError("resolved artifact payload kind is not supported")
    if recomputed != ref.logical_content_sha256 or recomputed != payload.logical_content_sha256:
        raise ValueError("artifact logical digest does not match immutable content")


def anchor_result_fingerprint_payload(result: AnchorResultV2) -> dict[str, JsonValue]:
    payload = _model_payload(result, excluded={"result_fingerprint"})
    payload["derived_artifacts"] = [
        logical_artifact_identity_payload(ref) for ref in result.derived_artifacts
    ]
    return payload


def evaluation_fingerprint_payload(report: AnchorEvaluationReport) -> dict[str, JsonValue]:
    payload = _model_payload(report, excluded={"evaluation_fingerprint"})
    payload["results"] = [result.result_fingerprint for result in report.results]
    payload["reachable_logical_artifacts"] = [
        logical_artifact_identity_payload(ref)
        for result in report.results
        for ref in result.derived_artifacts
    ]
    return payload


def catalog_fingerprint_payload(catalog: AnchorCatalog) -> dict[str, JsonValue]:
    return _model_payload(catalog, excluded={"catalog_fingerprint"})


def execution_plan_fingerprint_payload(plan: AnchorExecutionPlan) -> dict[str, JsonValue]:
    input_contract_keys = tuple(
        (contract.modality.value, contract.table_role) for contract in plan.input_table_contracts
    )
    if len(input_contract_keys) != len(set(input_contract_keys)) or input_contract_keys != tuple(
        sorted(input_contract_keys)
    ):
        raise ValueError("input table contracts must use unique canonical outer order")
    return _model_payload(plan, excluded={"plan_fingerprint"})


def plugin_definition_fingerprint(definition: AnchorPluginDefinition) -> str:
    return typed_json_sha256(
        "anchor-plugin-definition", _TYPE_VERSION, definition.model_dump(mode="json")
    )


def preprocessing_definition_fingerprint(definition: PreprocessingProviderDefinition) -> str:
    return typed_json_sha256(
        "preprocessing-provider-definition", _TYPE_VERSION, definition.model_dump(mode="json")
    )


def plugin_implementation_digest_payload(
    entry: PluginRegistryEntry,
) -> dict[str, JsonValue]:
    return _model_payload(entry, excluded={"implementation_digest"})


def preprocessing_implementation_digest_payload(
    entry: PreprocessingRegistryEntry,
) -> dict[str, JsonValue]:
    return _model_payload(entry, excluded={"implementation_digest"})


def runtime_registry_fingerprint(registry: AnchorRuntimeRegistry) -> str:
    return typed_json_sha256(
        "anchor-runtime-registry", _TYPE_VERSION, registry.model_dump(mode="json")
    )


def packaged_catalog_fingerprint(profile_id: str = "reference-model-v0.1") -> str:
    # Local import prevents a catalog-loader validation import cycle.
    from pilot_assessment.anchors.catalog import load_packaged_catalog

    catalog = load_packaged_catalog(profile_id)
    return typed_json_sha256("anchor-catalog", _TYPE_VERSION, catalog_fingerprint_payload(catalog))


def parameter_snapshot_fingerprint(parameters: Mapping[str, JsonValue]) -> str:
    return typed_json_sha256("parameter-snapshot", _TYPE_VERSION, parameters)


def scorer_policy_fingerprint(policy: ScorerPolicy) -> Sha256Digest:
    payload = [
        policy.scorer_id,
        policy.scorer_version,
        policy.policy_schema_id,
        policy.parameters,
    ]
    return typed_json_sha256("scorer-policy", _TYPE_VERSION, payload)


def python_runtime_identity() -> PythonRuntimeIdentity:
    implementation_name = sys.implementation.name
    cache_tag = sys.implementation.cache_tag
    version = tuple(sys.version_info[:3])
    if type(implementation_name) is not str or not implementation_name:
        raise ValueError("Python implementation name is unavailable")
    if type(cache_tag) is not str or not cache_tag:
        raise ValueError("Python cache tag is unavailable")
    if len(version) != 3 or any(type(member) is not int or member < 0 for member in version):
        raise ValueError("Python runtime requires an exact non-negative three-part version")

    soabi = sysconfig.get_config_var("SOABI")
    if type(soabi) is str and soabi:
        abi_tag = soabi
    elif sys.platform == "win32":
        suffix = sysconfig.get_config_var("EXT_SUFFIX")
        if type(suffix) is not str:
            raise ValueError("Windows Python runtime has no usable extension suffix")
        match = _WINDOWS_EXT_SUFFIX.fullmatch(suffix)
        if match is None:
            raise ValueError("Windows Python extension suffix is not canonical")
        abi_tag = match.group(1)
    else:
        raise ValueError("Python runtime has no SOABI identity")
    return PythonRuntimeIdentity(
        implementation_name=implementation_name,
        version=cast(tuple[int, int, int], version),
        cache_tag=cache_tag,
        soabi=abi_tag,
    )


def _normalized_distribution_name(name: str) -> str:
    if type(name) is not str or not name:
        raise ValueError("distribution names must be non-empty strings")
    normalized = _PEP503_RUN.sub("-", name).lower()
    if not normalized:
        raise ValueError("distribution name cannot normalize to empty")
    return normalized


def _reject_duplicate_json_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON metadata contains a duplicate key")
        result[key] = value
    return result


def _validate_direct_url(raw: str | None) -> None:
    if raw is None:
        return
    try:
        document = json.loads(raw, object_pairs_hook=_reject_duplicate_json_pairs)
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise ValueError("direct_url.json is not strict duplicate-free JSON") from error
    if not isinstance(document, dict):
        raise ValueError("direct_url.json must be a JSON object")
    dir_info = document.get("dir_info")
    if dir_info is None:
        return
    if not isinstance(dir_info, dict):
        raise ValueError("direct_url.json dir_info must be an object")
    if "editable" not in dir_info:
        return
    editable = dir_info["editable"]
    if type(editable) is not bool:
        raise ValueError("direct_url.json editable must be an exact boolean")
    if editable:
        raise ValueError("editable distributions have no stable wheel RECORD identity")


def _distribution_root(installed: object) -> Path:
    locate_file = getattr(installed, "locate_file", None)
    if not callable(locate_file):
        raise ValueError("installed distribution cannot locate its site-packages root")
    root = Path(locate_file("")).absolute()
    if not root.is_dir():
        raise ValueError("installed distribution root does not exist")
    return root


def _owning_dist_info_relative(installed: object, root: Path) -> PurePosixPath:
    metadata_path = getattr(installed, "_path", None)
    if metadata_path is None:
        raise ValueError("installed distribution does not expose its owning metadata directory")
    path = Path(metadata_path).absolute()
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise ValueError("distribution metadata directory lies outside site-packages") from error
    posix = PurePosixPath(relative.as_posix())
    if len(posix.parts) != 1 or not posix.name.endswith(".dist-info"):
        raise ValueError("installed distribution is not wheel-style dist-info metadata")
    return posix


def _relative_posix_path(raw: str) -> PurePosixPath:
    if type(raw) is not str or not raw or "\\" in raw:
        raise ValueError("RECORD paths must be non-empty relative POSIX paths")
    try:
        raw.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise ValueError("RECORD paths must not contain unpaired surrogates") from error
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise ValueError("RECORD paths must be relative")
    raw_parts = raw.split("/")
    if any(part in {"", "."} for part in raw_parts):
        raise ValueError("RECORD paths must not contain empty or dot components")
    path = PurePosixPath(raw)
    if path.is_absolute():
        raise ValueError("RECORD paths must be relative")
    return path


def _lexical_path(root: Path, parts: tuple[str, ...]) -> Path:
    return Path(os.path.abspath(os.path.normpath(os.path.join(os.fspath(root), *parts))))


def _is_within(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((os.fspath(path), os.fspath(root))) == os.fspath(root)
    except ValueError:
        return False


def _decode_declared_sha256(text: str) -> bytes:
    if _CANONICAL_SHA256_B64.fullmatch(text) is None:
        raise ValueError("RECORD SHA-256 declaration is not canonical unpadded base64url")
    try:
        decoded = base64.urlsafe_b64decode(text + "=")
    except (ValueError, binascii.Error) as error:
        raise ValueError("RECORD SHA-256 declaration cannot be decoded") from error
    if len(decoded) != 32:
        raise ValueError("RECORD SHA-256 declaration must decode to 32 bytes")
    canonical = base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii")
    if canonical != text:
        raise ValueError("RECORD SHA-256 declaration is not in canonical form")
    return decoded


def _read_distribution_text(installed: object, filename: str) -> str | None:
    read_text = getattr(installed, "read_text", None)
    if not callable(read_text):
        raise ValueError("installed distribution cannot read metadata")
    value = read_text(filename)
    if value is not None and type(value) is not str:
        raise ValueError("distribution metadata text is not a string")
    return value


def distribution_content_identity(distribution_name: str) -> NumericRuntimeIdentity:
    """Construct a root-independent identity from verified installed wheel members."""

    installed = distribution(distribution_name)
    metadata = getattr(installed, "metadata", None)
    if metadata is None:
        raise ValueError("installed distribution metadata is unavailable")
    project_name = metadata.get("Name")
    if type(project_name) is not str or not project_name:
        raise ValueError("installed distribution has no authoritative Name metadata")
    normalized_name = _normalized_distribution_name(project_name)
    version = getattr(installed, "version", None)
    if type(version) is not str or not version:
        raise ValueError("installed distribution has no exact version")

    _validate_direct_url(_read_distribution_text(installed, "direct_url.json"))
    record_text = _read_distribution_text(installed, "RECORD")
    if record_text is None:
        raise ValueError("installed distribution has no wheel-style RECORD")
    try:
        record_rows = list(csv.reader(io.StringIO(record_text, newline=""), strict=True))
    except csv.Error as error:
        raise ValueError("installed distribution RECORD is malformed CSV") from error
    if not record_rows:
        raise ValueError("installed distribution RECORD is empty")

    root = _distribution_root(installed)
    own_dist_info = _owning_dist_info_relative(installed, root)
    scripts_raw = sysconfig.get_path("scripts")
    if type(scripts_raw) is not str or not scripts_raw:
        raise ValueError("active interpreter scripts directory is unavailable")
    scripts_root = Path(scripts_raw).absolute()
    excluded_own_names = {"RECORD", "INSTALLER", "REQUESTED", "direct_url.json"}
    seen_paths: set[str] = set()
    seen_casefold: set[str] = set()
    retained: list[list[JsonValue]] = []

    for cells in record_rows:
        if len(cells) != 3:
            raise ValueError("every RECORD row must contain exactly three CSV cells")
        raw_path, hash_cell, size_cell = cells
        relative = _relative_posix_path(raw_path)
        normalized_path = relative.as_posix()
        folded = normalized_path.casefold()
        if normalized_path in seen_paths or folded in seen_casefold:
            raise ValueError("RECORD contains duplicate or case-fold alias paths")
        seen_paths.add(normalized_path)
        seen_casefold.add(folded)

        if ".." in relative.parts:
            lexical = _lexical_path(root, relative.parts)
            if _is_within(lexical, scripts_root):
                continue
            raise ValueError("RECORD traversal is allowed only for interpreter scripts launchers")

        is_own_mutable_metadata = (
            len(relative.parts) == 2
            and relative.parts[0] == own_dist_info.as_posix()
            and relative.parts[1] in excluded_own_names
        )
        is_cache = "__pycache__" in relative.parts
        is_bytecode = relative.suffix in {".pyc", ".pyo"}
        if is_own_mutable_metadata or is_cache or is_bytecode:
            continue

        lexical = _lexical_path(root, relative.parts)
        if not _is_within(lexical, root):
            raise ValueError("retained RECORD member lies outside site-packages")
        if lexical.is_symlink():
            raise ValueError("retained RECORD members must not be symlinks")
        real_path = Path(os.path.realpath(lexical))
        if not _is_within(real_path, Path(os.path.realpath(root))):
            raise ValueError("retained RECORD member resolves outside site-packages")
        if not lexical.is_file():
            raise ValueError("retained RECORD member is missing or not a regular file")
        if not hash_cell.startswith("sha256=") or hash_cell.count("=") != 1:
            raise ValueError("retained RECORD members require an exact SHA-256 declaration")
        declared_text = hash_cell.removeprefix("sha256=")
        declared_digest = _decode_declared_sha256(declared_text)
        if _CANONICAL_NONNEGATIVE_DECIMAL.fullmatch(size_cell) is None:
            raise ValueError("retained RECORD members require a canonical non-negative size")
        declared_size = int(size_cell)
        if declared_size > _SAFE_INTEGER:
            raise ValueError("RECORD member size exceeds the canonical integer domain")
        content = lexical.read_bytes()
        if len(content) != declared_size or hashlib.sha256(content).digest() != declared_digest:
            raise ValueError("installed member bytes do not match their RECORD declaration")
        retained.append([normalized_path, "sha256", declared_text, declared_size])

    if not retained:
        raise ValueError("installed distribution has no retained stable wheel members")
    retained.sort(key=lambda row: cast(str, row[0]))
    digest = typed_json_sha256("numeric-runtime-record", _TYPE_VERSION, retained)
    return NumericRuntimeIdentity(
        normalized_name=normalized_name,
        version=version,
        record_content_sha256=digest,
    )


def _cli_error(message: str) -> NoReturn:
    raise ValueError(message)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        if len(arguments) < 2 or arguments[0] != "runtime-identity":
            _cli_error("usage: runtime-identity DISTRIBUTION [DISTRIBUTION ...]")
        requested_names = arguments[1:]
        normalized_requests = [_normalized_distribution_name(name) for name in requested_names]
        if len(normalized_requests) != len(set(normalized_requests)):
            _cli_error("duplicate normalized distribution names are not allowed")
        identities = [distribution_content_identity(name) for name in requested_names]
        identity_names = [identity.normalized_name for identity in identities]
        if len(identity_names) != len(set(identity_names)):
            _cli_error("resolved distributions have duplicate authoritative names")
        identities.sort(key=lambda identity: identity.normalized_name)
        payload = [
            python_runtime_identity().model_dump(mode="json"),
            [identity.model_dump(mode="json") for identity in identities],
        ]
        sys.stdout.buffer.write(jcs_bytes(payload) + b"\n")
        return 0
    except Exception as error:
        sys.stderr.buffer.write(
            f"runtime identity error: {error}\n".encode("utf-8", errors="replace")
        )
        return 2


if __name__ == "__main__":  # pragma: no cover - exercised through the module CLI
    raise SystemExit(main())


__all__ = [
    "aligned_reference_content_fingerprint",
    "anchor_result_fingerprint_payload",
    "catalog_fingerprint_payload",
    "distribution_content_identity",
    "evaluation_fingerprint_payload",
    "execution_plan_fingerprint_payload",
    "jcs_bytes",
    "logical_artifact_identity_payload",
    "logical_table_sha256",
    "main",
    "packaged_catalog_fingerprint",
    "parameter_snapshot_fingerprint",
    "plugin_definition_fingerprint",
    "plugin_implementation_digest_payload",
    "preprocessing_definition_fingerprint",
    "preprocessing_implementation_digest_payload",
    "python_runtime_identity",
    "reference_alignment_fingerprint",
    "reference_resource_fingerprint",
    "reference_table_contract_fingerprint",
    "resolved_reference_set_fingerprint",
    "runtime_registry_fingerprint",
    "schema_descriptor_sha256",
    "scorer_policy_fingerprint",
    "session_semantic_snapshot_fingerprint",
    "typed_json_sha256",
    "validate_logical_artifact_ref",
]
