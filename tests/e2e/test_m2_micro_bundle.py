from __future__ import annotations

import csv
import io
from pathlib import Path

from pilot_assessment.contracts.ingestion import ReadinessDisposition, StreamReadiness
from pilot_assessment.ingestion import inspect_ingestion_readiness
from pilot_assessment.synthetic import generate_synthetic_bundle

_HEADERS = (
    "Simulation time",
    "Xe m",
    "Ye m",
    "Ze m",
    "Ground Elevation m",
    "V_ex m/s",
    "V_ey m/s",
    "V_ez m/s",
    "V_ex kts",
    "V_ey kts",
    "V_ez kts",
    "V_bx m/s",
    "V_by m/s",
    "V_bz m/s",
    "phi deg",
    "theta deg",
    "psi deg",
    "p deg/s",
    "q deg/s",
    "r deg/s",
    "ax m/s^2",
    "ay m/s^2",
    "az m/s^2",
    "alpha deg",
    "beta deg",
    "Control_Mode",
    "Pilot Yaw",
    "Pilot Lon",
    "Pilot Lat",
    "Pilot Heave",
    "Time Delay s",
    "Lon Frequency rad/s",
    "Long Damping",
)
_KNOTS_PER_METRE_PER_SECOND = 1.9438444924406048


def _write_micro_csv(path: Path) -> None:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(_HEADERS)
    for index in range(201):
        time_s = index / 100.0
        velocities = (0.1 * time_s, -0.2 * time_s, 0.05 * time_s)
        writer.writerow(
            [
                time_s,
                0.75 * time_s,
                0,
                -31.668,
                21.008,
                *velocities,
                *(value * _KNOTS_PER_METRE_PER_SECOND for value in velocities),
                *velocities,
                0,
                0,
                270,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                1,
                0,
                -100.0 * index / 200,
                0,
                0,
                0.2,
                8,
                0.8,
            ]
        )
    path.write_bytes(output.getvalue().encode("utf-8"))


def test_micro_csv_runs_through_full_m2_readiness(tmp_path: Path) -> None:
    source = tmp_path / "simulator_micro.csv"
    _write_micro_csv(source)

    bundle = generate_synthetic_bundle(source, tmp_path / "bundle", seed=20260711)
    outcome = inspect_ingestion_readiness(bundle)

    assert outcome.report.disposition is ReadinessDisposition.READY
    assert all(
        result.readiness is StreamReadiness.READY
        for result in outcome.report.stream_results.values()
    )
    assert outcome.report.task_reference_result is not None
    assert outcome.report.task_reference_result.readiness is StreamReadiness.READY
    assert outcome.report.can_continue_to_synchronization is True
    assert outcome.report.formal_run_authorized is False
    assert outcome.report.source_classification == "synthetic-test-data"
    assert outcome.report.synthetic_provenance is not None
    assert outcome.report.synthetic_provenance.scientific_validation_status == ("not_supported")
    assert outcome.prepared_session is not None
    assert {
        modality: stream.primary_table.height
        for modality, stream in outcome.prepared_session.streams.items()
    } == {
        "X": 201,
        "U": 201,
        "I": 61,
        "G": 241,
        "EEG": 513,
        "ECG": 501,
        "pilot_camera": 31,
    }
    assert outcome.prepared_session.task_reference is not None
    assert outcome.prepared_session.task_reference.primary_table.height == 201
