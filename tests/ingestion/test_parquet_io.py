from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from pilot_assessment.ingestion.parquet_io import (
    read_profiled_parquet_metadata,
    write_profiled_parquet,
)


def test_profiled_parquet_writer_is_deterministic_and_embeds_contract_metadata(
    tmp_path: Path,
) -> None:
    frame = pl.DataFrame(
        {
            "sample_index": pl.Series([0, 1, 2], dtype=pl.UInt64),
            "source_timestamp_s": pl.Series([0.0, 0.01, 0.02], dtype=pl.Float64),
            "value": pl.Series([1.0, 2.0, 3.0], dtype=pl.Float32),
        }
    )
    first = tmp_path / "first.parquet"
    second = tmp_path / "second.parquet"

    write_profiled_parquet(frame, first, schema_id="fixture-table-raw-v0.1")
    write_profiled_parquet(frame, second, schema_id="fixture-table-raw-v0.1")

    assert first.read_bytes() == second.read_bytes()
    assert read_profiled_parquet_metadata(first) == {
        "contract_version": "0.1.0",
        "schema_id": "fixture-table-raw-v0.1",
    }
    assert pl.read_parquet(first).equals(frame)


def test_profiled_parquet_writer_rejects_invalid_contract_inputs(tmp_path: Path) -> None:
    frame = pl.DataFrame({"value": [1]})
    with pytest.raises(ValueError):
        write_profiled_parquet(frame, tmp_path / "bad.parquet", schema_id="bad id")
    with pytest.raises(FileExistsError):
        existing = tmp_path / "existing.parquet"
        existing.write_bytes(b"do not overwrite")
        write_profiled_parquet(frame, existing, schema_id="fixture-v0.1")


def test_profiled_parquet_writer_requires_existing_parent(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        write_profiled_parquet(
            pl.DataFrame({"value": [1]}),
            tmp_path / "missing" / "table.parquet",
            schema_id="fixture-v0.1",
        )
