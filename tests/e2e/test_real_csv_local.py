from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from pilot_assessment.contracts.ingestion import ReadinessDisposition, StreamReadiness
from pilot_assessment.ingestion import inspect_ingestion_readiness
from pilot_assessment.synthetic import generate_synthetic_bundle

REAL_CSV_ENV = "PILOT_ASSESSMENT_REAL_CSV"
EXPECTED_REAL_CSV_SHA256 = "19bf804253d841de9c9de299ac96e9e1b693b2dbfae2f3eaeac5d7dc044e4f52"


@pytest.mark.skipif(
    REAL_CSV_ENV not in os.environ,
    reason="repository-external real simulator CSV not configured",
)
def test_real_csv_generates_a_full_ready_bundle_without_source_mutation(
    tmp_path: Path,
) -> None:
    source = Path(os.environ[REAL_CSV_ENV])
    source_bytes = source.read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    assert source_hash == EXPECTED_REAL_CSV_SHA256

    bundle = generate_synthetic_bundle(source, tmp_path / "full", seed=20260711)
    outcome = inspect_ingestion_readiness(bundle)

    assert outcome.prepared_session is not None
    x = outcome.prepared_session.streams["X"].primary_table
    u = outcome.prepared_session.streams["U"].primary_table
    assert x.height == 2_902
    assert u.height == 2_902
    assert x["source_time_s"].min() == 0.0
    assert x["source_time_s"].max() == 29.01
    assert u["control.longitudinal_raw"].min() == -100.0
    assert u["control.longitudinal_raw"].max() == 0.0
    assert outcome.prepared_session.context == {
        "context.control_mode_raw": 1.0,
        "context.time_delay_s": 0.2,
        "context.longitudinal_frequency_rad_s": 8.0,
        "context.longitudinal_damping_ratio": 0.8,
    }
    assert outcome.report.stream_results["X"].observed_sample_rate_hz == pytest.approx(100.0)
    assert outcome.report.disposition is ReadinessDisposition.READY
    assert all(
        result.readiness is StreamReadiness.READY
        for result in outcome.report.stream_results.values()
    )
    assert outcome.report.task_reference_result is not None
    assert outcome.report.task_reference_result.readiness is StreamReadiness.READY
    assert outcome.report.formal_run_authorized is False
    assert (bundle / "streams" / "simulator.csv").read_bytes() == source_bytes
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
