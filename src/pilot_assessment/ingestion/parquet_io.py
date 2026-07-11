"""Single authority for deterministic, contract-profiled Parquet files."""

from __future__ import annotations

from pathlib import Path

import polars as pl
from pydantic import TypeAdapter

from pilot_assessment.contracts.common import StableId

_STABLE_ID_ADAPTER = TypeAdapter(StableId)
_CONTRACT_VERSION = "0.1.0"
_PROFILE_METADATA_KEYS = ("contract_version", "schema_id")


def write_profiled_parquet(
    frame: pl.DataFrame,
    path: str | Path,
    *,
    schema_id: str,
) -> None:
    """Write one immutable Parquet artifact with its contract identity embedded."""

    validated_schema_id = _STABLE_ID_ADAPTER.validate_python(schema_id)
    destination = Path(path)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    if destination.exists():
        raise FileExistsError(destination)

    frame.write_parquet(
        destination,
        compression="zstd",
        compression_level=3,
        statistics=True,
        row_group_size=65_536,
        metadata={
            "contract_version": _CONTRACT_VERSION,
            "schema_id": validated_schema_id,
        },
    )


def read_profiled_parquet_metadata(path: str | Path) -> dict[str, str]:
    """Read and validate the two metadata fields required by the M2 contract."""

    metadata = pl.read_parquet_metadata(path)
    try:
        contract_version = metadata["contract_version"]
        schema_id = metadata["schema_id"]
    except KeyError as error:
        raise ValueError(f"missing required Parquet metadata: {error.args[0]}") from error

    if contract_version != _CONTRACT_VERSION:
        raise ValueError(f"unsupported contract_version: {contract_version}")
    _STABLE_ID_ADAPTER.validate_python(schema_id)
    return dict(zip(_PROFILE_METADATA_KEYS, (contract_version, schema_id), strict=True))


__all__ = ["read_profiled_parquet_metadata", "write_profiled_parquet"]
