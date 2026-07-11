"""Finite resource budgets shared by trusted M2 ingestion adapters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from pilot_assessment.contracts.errors import DomainErrorData, ErrorSeverity
from pilot_assessment.ingestion.adapters.base import AdapterInspectionError


@dataclass(frozen=True, slots=True)
class AdapterResourceLimits:
    """Approved upper bounds applied before eager artifact materialization."""

    max_csv_bytes: int = 512 * 1024 * 1024
    max_csv_rows: int = 10_000_000
    max_csv_columns: int = 512
    max_csv_header_bytes: int = 256 * 1024
    max_csv_field_chars: int = 16 * 1024
    max_parquet_bytes: int = 16 * 1024 * 1024 * 1024
    max_parquet_rows: int = 100_000_000
    max_parquet_columns: int = 512
    max_parquet_string_chars: int = 4096
    max_json_bytes: int = 4 * 1024 * 1024
    max_json_string_chars: int = 4096

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_ADAPTER_RESOURCE_LIMITS = AdapterResourceLimits()


def enforce_resource_limit(
    *,
    limit_name: str,
    limit: int,
    observed: int,
    field_or_path: str | Path,
) -> None:
    """Raise one stable typed adapter error when an approved budget is exceeded."""

    if observed <= limit:
        return
    _fail_resource_limit(
        limit_name=limit_name,
        limit=limit,
        observed=observed,
        field_or_path=str(field_or_path),
    )


def _fail_resource_limit(
    *,
    limit_name: str,
    limit: int,
    observed: int,
    field_or_path: str,
) -> NoReturn:
    raise AdapterInspectionError(
        DomainErrorData(
            error_code="ADAPTER_RESOURCE_LIMIT_EXCEEDED",
            severity=ErrorSeverity.ERROR,
            recoverable=True,
            message="Artifact exceeds an approved ingestion adapter resource limit",
            field_or_path=field_or_path,
            remediation="Reduce or split the artifact, or configure an explicitly approved limit.",
            diagnostics={
                "limit_name": limit_name,
                "limit": limit,
                "observed": observed,
            },
        )
    )


__all__ = [
    "AdapterResourceLimits",
    "DEFAULT_ADAPTER_RESOURCE_LIMITS",
    "enforce_resource_limit",
]
