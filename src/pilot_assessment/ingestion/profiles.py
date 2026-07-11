"""Versioned, package-resource ingestion profile contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from enum import StrEnum
from functools import lru_cache
from importlib.resources import files
from types import MappingProxyType
from typing import Annotated, Literal, Self

import polars as pl
from pydantic import (
    AfterValidator,
    Field,
    JsonValue,
    StrictBool,
    StringConstraints,
    TypeAdapter,
    field_validator,
    model_validator,
)

from pilot_assessment.contracts.common import (
    BundleRelativePath,
    NonNegativeFiniteFloat,
    NonNegativeInt,
    PositiveFiniteFloat,
    StableId,
    StrictContractModel,
    UnitInterval,
)

NonEmptyString = Annotated[str, StringConstraints(min_length=1, max_length=1024)]
_BUNDLE_PATH_ADAPTER = TypeAdapter(BundleRelativePath)


class ProfileLoadError(ValueError):
    """Raised when a packaged profile resource cannot be parsed safely."""


class _DuplicateJsonKey(ValueError):
    pass


def _object_without_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def _validate_path_prefix(value: str) -> str:
    if not value.endswith("/"):
        raise ValueError("path_prefix must end with '/'")
    _BUNDLE_PATH_ADAPTER.validate_python(value[:-1])
    return value


CanonicalPathPrefix = Annotated[
    str,
    StringConstraints(min_length=2, max_length=1024),
    AfterValidator(_validate_path_prefix),
]


class PhysicalDType(StrEnum):
    U64 = "u64"
    U32 = "u32"
    F64 = "f64"
    F32 = "f32"
    BOOL = "bool"
    UTF8 = "utf8"

    def to_polars(self) -> type[pl.DataType]:
        return {
            PhysicalDType.U64: pl.UInt64,
            PhysicalDType.U32: pl.UInt32,
            PhysicalDType.F64: pl.Float64,
            PhysicalDType.F32: pl.Float32,
            PhysicalDType.BOOL: pl.Boolean,
            PhysicalDType.UTF8: pl.String,
        }[self]


class CsvColumnRole(StrEnum):
    X = "X"
    U = "U"
    CONTEXT = "context"
    QUALITY_CHECK = "quality_check"


class JsonFieldType(StrEnum):
    UTF8 = "utf8"
    STRING_LIST = "string_list"
    STRING_MAP = "string_map"
    F64 = "f64"
    I64 = "i64"
    BOOL = "bool"


class ColumnProfile(StrictContractModel):
    name: StableId
    dtype: PhysicalDType
    nullable: StrictBool
    unit: NonEmptyString
    minimum: NonNegativeFiniteFloat | None = None
    maximum: NonNegativeFiniteFloat | None = None
    finite: StrictBool = True
    is_bundle_path: StrictBool = False

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.minimum is not None and self.maximum is not None and self.maximum < self.minimum:
            raise ValueError("column maximum must be greater than or equal to minimum")
        if self.dtype not in {PhysicalDType.F32, PhysicalDType.F64} and not self.finite:
            raise ValueError("finite=false is meaningful only for floating point columns")
        if self.is_bundle_path and self.dtype is not PhysicalDType.UTF8:
            raise ValueError("bundle path columns must use utf8")
        return self


class TableProfile(StrictContractModel):
    kind: Literal["table"]
    schema_id: StableId
    media_type: Literal["application/vnd.apache.parquet"]
    columns: tuple[ColumnProfile, ...]
    sort_key: tuple[StableId, ...]
    source_timestamp_column: StableId | None = None
    expected_sample_rate_hz: PositiveFiniteFloat | None = None
    sample_rate_tolerance_fraction: UnitInterval = 0.01
    min_valid_fraction: UnitInterval = 0.98
    allow_extra_columns: Literal[False] = False
    allowed_provenance_columns: tuple[StableId, ...] = ()
    extensions: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_columns(self) -> Self:
        names = [column.name for column in self.columns]
        if not names:
            raise ValueError("table profiles require columns")
        if len(names) != len(set(names)):
            raise ValueError("table column names must be unique")
        if not self.sort_key:
            raise ValueError("table profiles require a sort key")
        unknown_sort = set(self.sort_key) - set(names)
        if unknown_sort:
            raise ValueError(f"sort key references unknown columns: {sorted(unknown_sort)}")
        nullable = {column.name for column in self.columns if column.nullable}
        if nullable.intersection(self.sort_key):
            raise ValueError("sort-key columns must be non-nullable")
        if self.source_timestamp_column is not None:
            by_name = {column.name: column for column in self.columns}
            timestamp = by_name.get(self.source_timestamp_column)
            if timestamp is None or timestamp.dtype is not PhysicalDType.F64:
                raise ValueError("source timestamp column must be a declared f64 column")
        if self.expected_sample_rate_hz is not None and self.source_timestamp_column is None:
            raise ValueError("fixed-rate tables require a source timestamp column")
        if set(self.allowed_provenance_columns).intersection(names):
            raise ValueError("provenance extension columns must not shadow physical columns")
        return self

    def polars_schema(self) -> Mapping[str, type[pl.DataType]]:
        """Return the exact ordered Polars schema for this physical table."""

        return {column.name: column.dtype.to_polars() for column in self.columns}


class CsvColumnProfile(StrictContractModel):
    source_header: NonEmptyString
    canonical_name: StableId
    role: CsvColumnRole
    unit: NonEmptyString
    required: Literal[True] = True
    engineering_assumption: StableId | None = None


class UnitConsistencyCheck(StrictContractModel):
    source_metric_column: StableId
    comparison_column: StableId
    comparison_per_metric: PositiveFiniteFloat
    warning_tolerance: PositiveFiniteFloat
    invalid_tolerance: PositiveFiniteFloat
    tolerance_unit: NonEmptyString

    @model_validator(mode="after")
    def validate_tolerances(self) -> Self:
        if self.invalid_tolerance <= self.warning_tolerance:
            raise ValueError("invalid tolerance must be greater than warning tolerance")
        return self


class CsvProfile(StrictContractModel):
    kind: Literal["csv"]
    schema_id: StableId
    format: Literal["csv"]
    delimiter: Literal[","]
    encodings: tuple[Literal["utf-8", "utf-8-sig"], ...]
    header_normalization: Literal["trim_outer_ascii_whitespace_v1"]
    source_row_index_dtype: Literal["u64"]
    source_timestamp_column: StableId
    expected_sample_rate_hz: PositiveFiniteFloat
    sample_rate_tolerance_fraction: UnitInterval
    gap_multiplier: PositiveFiniteFloat
    min_valid_fraction: UnitInterval
    columns: tuple[CsvColumnProfile, ...]
    context_columns: tuple[StableId, ...]
    unit_consistency_checks: tuple[UnitConsistencyCheck, ...]
    allow_extra_columns: Literal[True] = True
    extensions: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_mappings(self) -> Self:
        headers = [column.source_header for column in self.columns]
        canonical = [column.canonical_name for column in self.columns]
        if not headers:
            raise ValueError("CSV profiles require columns")
        if len(headers) != len(set(headers)):
            raise ValueError("CSV source headers must be unique after normalization")
        if len(canonical) != len(set(canonical)):
            raise ValueError("CSV canonical names must be unique")
        by_name = {column.canonical_name: column for column in self.columns}
        if self.source_timestamp_column not in by_name:
            raise ValueError("CSV source timestamp column must be declared")
        expected_context = {
            column.canonical_name for column in self.columns if column.role is CsvColumnRole.CONTEXT
        }
        if set(self.context_columns) != expected_context:
            raise ValueError("context_columns must exactly match context mappings")
        for check in self.unit_consistency_checks:
            if check.source_metric_column not in by_name:
                raise ValueError("unit check metric column must be declared")
            comparison = by_name.get(check.comparison_column)
            if comparison is None or comparison.role is not CsvColumnRole.QUALITY_CHECK:
                raise ValueError("unit check comparison must name a quality_check column")
        return self


class ExactPathsMatcher(StrictContractModel):
    kind: Literal["exact_paths"]
    paths: tuple[BundleRelativePath, ...]

    @field_validator("paths")
    @classmethod
    def require_unique_paths(
        cls, paths: tuple[BundleRelativePath, ...]
    ) -> tuple[BundleRelativePath, ...]:
        if not paths:
            raise ValueError("exact_paths matcher requires at least one path")
        folded = [path.casefold() for path in paths]
        if len(folded) != len(set(folded)):
            raise ValueError("exact matcher paths must be unique under case folding")
        return paths


class PathPrefixMatcher(StrictContractModel):
    kind: Literal["path_prefix"]
    path_prefix: CanonicalPathPrefix


ArtifactMatcher = Annotated[
    ExactPathsMatcher | PathPrefixMatcher,
    Field(discriminator="kind"),
]


class ArtifactRoleProfile(StrictContractModel):
    matcher: ArtifactMatcher
    media_type: NonEmptyString
    schema_id: StableId
    required: StrictBool


class CompositeProfile(StrictContractModel):
    kind: Literal["composite"]
    schema_id: StableId
    format: NonEmptyString
    primary_role: StableId
    artifact_roles: dict[StableId, ArtifactRoleProfile]
    extensions: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_roles(self) -> Self:
        if not self.artifact_roles:
            raise ValueError("composite profiles require artifact roles")
        if self.primary_role not in self.artifact_roles:
            raise ValueError("composite primary_role must be declared")
        if not self.artifact_roles[self.primary_role].required:
            raise ValueError("composite primary_role must be required")
        return self


class ImageDimension(StrictContractModel):
    width: Annotated[int, Field(strict=True, gt=0)]
    height: Annotated[int, Field(strict=True, gt=0)]


class ImageProfile(StrictContractModel):
    kind: Literal["image"]
    schema_id: StableId
    media_type: Literal["image/png"]
    mode: Literal["RGB"]
    bit_depth: Literal[8]
    allowed_dimensions: tuple[ImageDimension, ...]
    max_pixels: NonNegativeInt
    allow_animation: Literal[False]
    allow_ancillary_metadata: Literal[False]
    extensions: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_dimensions(self) -> Self:
        dimensions = [(item.width, item.height) for item in self.allowed_dimensions]
        if not dimensions or len(dimensions) != len(set(dimensions)):
            raise ValueError("image dimensions must be non-empty and unique")
        if self.max_pixels == 0:
            raise ValueError("image max_pixels must be positive")
        if any(width * height > self.max_pixels for width, height in dimensions):
            raise ValueError("allowed image dimensions exceed max_pixels")
        return self


class JsonFieldProfile(StrictContractModel):
    name: StableId
    field_type: JsonFieldType
    required: StrictBool


class JsonProfile(StrictContractModel):
    kind: Literal["json"]
    schema_id: StableId
    media_type: Literal["application/json"]
    fields: tuple[JsonFieldProfile, ...]
    allow_extra_fields: Literal[False]
    extensions: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_fields(self) -> Self:
        names = [field.name for field in self.fields]
        if not names or len(names) != len(set(names)):
            raise ValueError("JSON profile field names must be non-empty and unique")
        return self


ArtifactProfile = Annotated[
    CsvProfile | TableProfile | CompositeProfile | ImageProfile | JsonProfile,
    Field(discriminator="kind"),
]


class ProfileCatalog(StrictContractModel):
    catalog_version: Literal["0.1.0"]
    profiles: tuple[ArtifactProfile, ...]

    @model_validator(mode="after")
    def validate_catalog(self) -> Self:
        schema_ids = [profile.schema_id for profile in self.profiles]
        if not schema_ids:
            raise ValueError("profile catalog must not be empty")
        if len(schema_ids) != len(set(schema_ids)):
            raise ValueError("profile schema IDs must be unique")
        profiles = {profile.schema_id: profile for profile in self.profiles}
        for profile in self.profiles:
            if not isinstance(profile, CompositeProfile):
                continue
            for role, artifact in profile.artifact_roles.items():
                target = profiles.get(artifact.schema_id)
                if target is None:
                    raise ValueError(
                        f"composite role {profile.schema_id}.{role} references unknown schema"
                    )
                if isinstance(target, (CompositeProfile, CsvProfile)):
                    raise ValueError("composite roles must reference physical artifact profiles")
                expected_media_type = target.media_type
                if artifact.media_type != expected_media_type:
                    raise ValueError(
                        f"composite role {profile.schema_id}.{role} media type disagrees"
                    )
        return self


def parse_profile_catalog(payload: str | bytes) -> ProfileCatalog:
    """Parse strict UTF-8 JSON and reject duplicate keys or non-standard numbers."""

    try:
        text = payload.decode("utf-8", errors="strict") if isinstance(payload, bytes) else payload
        raw = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
        if not isinstance(raw, dict):
            raise ValueError("profile catalog root must be an object")
        return ProfileCatalog.model_validate(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, _DuplicateJsonKey, ValueError) as error:
        if isinstance(error, ProfileLoadError):
            raise
        raise ProfileLoadError(f"invalid ingestion profile catalog: {error}") from error


@lru_cache(maxsize=1)
def _builtin_catalog() -> ProfileCatalog:
    resource = files("pilot_assessment.ingestion.profile_data").joinpath("m2-profiles-0.1.json")
    return parse_profile_catalog(resource.read_bytes())


def load_builtin_profiles() -> Mapping[str, ArtifactProfile]:
    """Return an immutable schema-ID registry of validated built-in profiles."""

    return MappingProxyType({profile.schema_id: profile for profile in _builtin_catalog().profiles})


__all__ = [
    "ArtifactMatcher",
    "ArtifactProfile",
    "ArtifactRoleProfile",
    "ColumnProfile",
    "CompositeProfile",
    "CsvColumnProfile",
    "CsvColumnRole",
    "CsvProfile",
    "ExactPathsMatcher",
    "ImageDimension",
    "ImageProfile",
    "JsonFieldProfile",
    "JsonFieldType",
    "JsonProfile",
    "PathPrefixMatcher",
    "PhysicalDType",
    "ProfileCatalog",
    "ProfileLoadError",
    "TableProfile",
    "UnitConsistencyCheck",
    "load_builtin_profiles",
    "parse_profile_catalog",
]
