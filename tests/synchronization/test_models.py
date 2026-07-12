from __future__ import annotations

import csv
import io
import json
import operator
from collections.abc import MutableSequence
from dataclasses import replace
from pathlib import Path
from typing import cast

import polars as pl
import pytest

from pilot_assessment.contracts.ingestion import (
    IngestionReadinessReport,
    ReadinessDisposition,
)
from pilot_assessment.contracts.synchronization import (
    BaselineInterval,
    EventMarker,
    PhaseInterval,
    SessionWindow,
)
from pilot_assessment.ingestion.manifest_loader import LoadedManifest, ManifestLoader
from pilot_assessment.ingestion.models import PreparedSession
from pilot_assessment.ingestion.readiness import (
    inspect_loaded_ingestion_readiness,
    source_snapshot_fingerprint,
)
from pilot_assessment.synchronization.models import (
    AlignedAnnotations,
    AlignedSession,
    AlignedStreamView,
    SynchronizationInput,
)
from pilot_assessment.synthetic.generator import generate_synthetic_bundle

_HEADERS = (
    "Simulation time",
    " Xe m",
    " Ye m",
    " Ze m",
    "Ground Elevation m",
    "V_ex m/s",
    "  V_ey m/s",
    " V_ez m/s",
    "V_ex kts",
    "  V_ey kts",
    " V_ez kts",
    "V_bx m/s",
    " V_by m/s",
    " V_bz m/s",
    "phi deg",
    " theta deg",
    " psi deg",
    "p deg/s",
    " q deg/s",
    " r deg/s",
    "ax m/s^2",
    " ay m/s^2",
    " az m/s^2",
    "alpha deg",
    " beta deg",
    "Control_Mode",
    "Pilot Yaw",
    " Pilot Lon",
    " Pilot Lat",
    " Pilot Heave",
    "Time Delay s",
    " Lon Frequency rad/s",
    " Long Damping ",
)
_KNOTS_PER_METRE_PER_SECOND = 1.9438444924406048


def _write_micro_csv(path: Path) -> None:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(_HEADERS)
    count = 201
    for index in range(count):
        time_s = index / 100.0
        velocities = (0.1 * time_s, -0.2 * time_s, 0.05 * time_s)
        writer.writerow(
            [
                str(time_s),
                str(0.75 * time_s),
                "0",
                "-31.668",
                "21.008",
                *(str(value) for value in velocities),
                *(str(value * _KNOTS_PER_METRE_PER_SECOND) for value in velocities),
                *(str(value) for value in velocities),
                "0",
                "0",
                "270",
                "0",
                "0",
                "0",
                "0",
                "0",
                "0",
                "0",
                "0",
                "1",
                "0",
                str(-100.0 * index / (count - 1)),
                "0",
                "0",
                "0.2",
                "8",
                "0.8",
            ]
        )
    path.write_bytes(output.getvalue().encode("utf-8"))


def _ready_parts(
    tmp_path: Path,
) -> tuple[LoadedManifest, IngestionReadinessReport, PreparedSession]:
    source = tmp_path / "micro.csv"
    _write_micro_csv(source)
    bundle = generate_synthetic_bundle(source, tmp_path / "bundle", seed=20260711)
    loaded = ManifestLoader().load(bundle)
    outcome = inspect_loaded_ingestion_readiness(loaded)
    assert outcome.prepared_session is not None
    return loaded, outcome.report, outcome.prepared_session


def _ready_parts_without_bundle_reference(
    tmp_path: Path,
    *,
    owner: str,
) -> tuple[LoadedManifest, IngestionReadinessReport, PreparedSession]:
    loaded, _report, _prepared = _ready_parts(tmp_path)
    manifest_path = loaded.bundle_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    descriptor = manifest["streams"].pop("task_reference")
    reference_path = descriptor["paths"][0]
    if owner == "model_bundle":
        manifest["task"]["reference"] = {
            "source": "model_bundle",
            "reference_id": "model-reference-fixture-v0.1",
            "extensions": {},
        }
    else:
        assert owner == "none"
        manifest["task"]["reference"] = None
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    checksum_path = loaded.bundle_root / "integrity" / "checksums.sha256"
    checksum_lines = [
        line
        for line in checksum_path.read_text(encoding="utf-8").splitlines()
        if not line.endswith(reference_path)
    ]
    checksum_path.write_text(
        "\n".join(checksum_lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    reloaded = ManifestLoader().load(loaded.bundle_root)
    outcome = inspect_loaded_ingestion_readiness(reloaded)
    assert outcome.prepared_session is not None
    return reloaded, outcome.report, outcome.prepared_session


def test_synchronization_input_rejects_blocked_readiness(tmp_path: Path) -> None:
    loaded, report, prepared = _ready_parts(tmp_path)
    blocked = report.model_copy(
        update={
            "disposition": ReadinessDisposition.BLOCKED,
            "can_continue_to_synchronization": False,
        }
    )

    with pytest.raises(ValueError, match="blocked readiness cannot construct"):
        SynchronizationInput(
            loaded_manifest=loaded,
            readiness_report=blocked,
            prepared_session=prepared,
        )


def test_synchronization_input_rejects_snapshot_fingerprint_mismatch(tmp_path: Path) -> None:
    loaded, report, prepared = _ready_parts(tmp_path)
    mismatched = report.model_copy(update={"source_snapshot_fingerprint": "0" * 64})

    with pytest.raises(ValueError, match="source snapshot fingerprint"):
        SynchronizationInput(
            loaded_manifest=loaded,
            readiness_report=mismatched,
            prepared_session=prepared,
        )


def test_synchronization_input_rejects_session_id_mismatch(tmp_path: Path) -> None:
    loaded, report, prepared = _ready_parts(tmp_path)
    mismatched = report.model_copy(update={"session_id": "different-session"})

    with pytest.raises(ValueError, match="session IDs"):
        SynchronizationInput(
            loaded_manifest=loaded,
            readiness_report=mismatched,
            prepared_session=prepared,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_core",
        "extra_core",
        "core_schema",
        "missing_reference",
        "reference_schema",
        "core_source_paths",
        "core_source_checksums",
        "core_primary_row_count",
        "core_artifact_role_count",
        "core_columns",
        "reference_source",
    ],
)
def test_synchronization_input_rejects_ready_inventory_mismatch(
    tmp_path: Path,
    mutation: str,
) -> None:
    loaded, report, prepared = _ready_parts(tmp_path)
    streams = dict(prepared.streams)
    reference = prepared.task_reference
    assert reference is not None
    if mutation == "missing_core":
        streams.pop("I")
    elif mutation == "extra_core":
        streams["invented"] = replace(streams["I"], modality="invented")
    elif mutation == "core_schema":
        streams["I"] = replace(streams["I"], schema_id="invented-normalized-v0.1")
    elif mutation == "missing_reference":
        reference = None
    elif mutation == "reference_schema":
        reference = replace(reference, schema_id="invented-reference-normalized-v0.1")
    elif mutation == "core_source_paths":
        streams["I"] = replace(
            streams["I"],
            source_paths=("streams/I/forged.parquet",),
            source_checksums={"streams/I/forged.parquet": "f" * 64},
        )
    elif mutation == "core_source_checksums":
        streams["I"] = replace(
            streams["I"],
            source_checksums={path: "f" * 64 for path in streams["I"].source_paths},
        )
    elif mutation == "core_primary_row_count":
        core = streams["I"]
        tables = dict(core.tables)
        tables[core.primary_table_role] = core.primary_table.head(core.primary_table.height - 1)
        streams["I"] = replace(core, tables=tables)
    elif mutation == "core_artifact_role_count":
        core = streams["I"]
        tables = dict(core.tables)
        assert "aoi_instances" in tables
        tables["aoi_instances"] = tables["aoi_instances"].head(tables["aoi_instances"].height - 1)
        streams["I"] = replace(core, tables=tables)
    elif mutation == "core_columns":
        core = streams["I"]
        tables = dict(core.tables)
        tables[core.primary_table_role] = core.primary_table.with_columns(
            pl.lit(1).alias("forged_column")
        )
        streams["I"] = replace(core, tables=tables)
    else:
        reference = replace(
            reference,
            source_checksums={path: "f" * 64 for path in reference.source_paths},
        )
    mismatched = PreparedSession(
        streams=streams,
        context=prepared.context,
        task_reference=reference,
    )

    with pytest.raises(ValueError, match="ready inventory"):
        SynchronizationInput(
            loaded_manifest=loaded,
            readiness_report=report,
            prepared_session=mismatched,
        )


def test_synchronization_input_accepts_frozen_xu_physical_to_logical_count_mapping(
    tmp_path: Path,
) -> None:
    loaded, report, prepared = _ready_parts(tmp_path)
    accepted = SynchronizationInput(
        loaded_manifest=loaded,
        readiness_report=report,
        prepared_session=prepared,
    )
    assert accepted.prepared_session.streams["X"].primary_table_role == "samples"
    assert set(report.stream_results["X"].artifact_row_counts) == {"simulator_csv"}

    streams = dict(prepared.streams)
    x_stream = streams["X"]
    streams["X"] = replace(
        x_stream,
        tables={"samples": x_stream.primary_table.head(x_stream.primary_table.height - 1)},
    )
    forged = PreparedSession(
        streams=streams,
        context=prepared.context,
        task_reference=prepared.task_reference,
    )
    with pytest.raises(ValueError, match="ready inventory"):
        SynchronizationInput(
            loaded_manifest=loaded,
            readiness_report=report,
            prepared_session=forged,
        )


def test_synchronization_input_rejects_core_clock_mismatch_with_loaded_manifest(
    tmp_path: Path,
) -> None:
    loaded, report, prepared = _ready_parts(tmp_path)
    streams = dict(prepared.streams)
    streams["I"] = replace(streams["I"], clock_id="forged-clock")

    with pytest.raises(ValueError, match="clock.*loaded manifest"):
        SynchronizationInput(
            loaded_manifest=loaded,
            readiness_report=report,
            prepared_session=PreparedSession(
                streams=streams,
                context=prepared.context,
                task_reference=prepared.task_reference,
            ),
        )


def test_synchronization_input_rejects_reference_clock_mismatch_with_loaded_manifest(
    tmp_path: Path,
) -> None:
    loaded, report, prepared = _ready_parts(tmp_path)
    reference = prepared.task_reference
    assert reference is not None

    with pytest.raises(ValueError, match="clock.*loaded manifest"):
        SynchronizationInput(
            loaded_manifest=loaded,
            readiness_report=report,
            prepared_session=PreparedSession(
                streams=prepared.streams,
                context=prepared.context,
                task_reference=replace(reference, clock_id="forged-reference-clock"),
            ),
        )


def test_synchronization_input_rejects_consistently_forged_core_source_identity(
    tmp_path: Path,
) -> None:
    loaded, report, prepared = _ready_parts(tmp_path)
    forged_path = "streams/I/forged.parquet"
    forged_checksums = {forged_path: "f" * 64}
    streams = dict(prepared.streams)
    streams["I"] = replace(
        streams["I"],
        source_paths=(forged_path,),
        source_checksums=forged_checksums,
    )
    stream_results = dict(report.stream_results)
    stream_results["I"] = stream_results["I"].model_copy(
        update={
            "source_paths": (forged_path,),
            "source_checksums": forged_checksums,
        }
    )

    with pytest.raises(ValueError, match="source identity.*loaded manifest"):
        SynchronizationInput(
            loaded_manifest=loaded,
            readiness_report=report.model_copy(update={"stream_results": stream_results}),
            prepared_session=PreparedSession(
                streams=streams,
                context=prepared.context,
                task_reference=prepared.task_reference,
            ),
        )


def test_synchronization_input_rejects_consistently_forged_reference_source_identity(
    tmp_path: Path,
) -> None:
    loaded, report, prepared = _ready_parts(tmp_path)
    reference = prepared.task_reference
    reference_result = report.task_reference_result
    assert reference is not None
    assert reference_result is not None
    forged_path = "references/forged.csv"
    forged_checksums = {forged_path: "f" * 64}

    with pytest.raises(ValueError, match="source identity.*loaded manifest"):
        SynchronizationInput(
            loaded_manifest=loaded,
            readiness_report=report.model_copy(
                update={
                    "task_reference_result": reference_result.model_copy(
                        update={
                            "source_paths": (forged_path,),
                            "source_checksums": forged_checksums,
                        }
                    )
                }
            ),
            prepared_session=PreparedSession(
                streams=prepared.streams,
                context=prepared.context,
                task_reference=replace(
                    reference,
                    source_paths=(forged_path,),
                    source_checksums=forged_checksums,
                ),
            ),
        )


def test_synchronization_input_accepts_shared_xu_loaded_source_identity(
    tmp_path: Path,
) -> None:
    loaded, report, prepared = _ready_parts(tmp_path)

    accepted = SynchronizationInput(
        loaded_manifest=loaded,
        readiness_report=report,
        prepared_session=prepared,
    )

    x_stream = accepted.prepared_session.streams["X"]
    u_stream = accepted.prepared_session.streams["U"]
    x_descriptor = loaded.manifest.streams["X"]
    u_descriptor = loaded.manifest.streams["U"]
    expected_checksums = {path: loaded.verified_digests[path] for path in x_descriptor.paths}
    assert x_stream.source_paths == u_stream.source_paths == tuple(x_descriptor.paths)
    assert x_descriptor.paths == u_descriptor.paths
    assert dict(x_stream.source_checksums) == dict(u_stream.source_checksums)
    assert dict(x_stream.source_checksums) == expected_checksums


def test_synchronization_input_bounds_missing_loaded_reference_descriptor(
    tmp_path: Path,
) -> None:
    loaded, report, prepared = _ready_parts(tmp_path)
    manifest_streams = dict(loaded.manifest.streams)
    manifest_streams.pop("task_reference")
    loaded_without_reference = replace(
        loaded,
        manifest=loaded.manifest.model_copy(
            update={
                "streams": manifest_streams,
            }
        ),
    )
    forged_report = report.model_copy(
        update={
            "source_snapshot_fingerprint": source_snapshot_fingerprint(loaded_without_reference)
        }
    )

    with pytest.raises(ValueError, match="ready inventory.*loaded manifest"):
        SynchronizationInput(
            loaded_manifest=loaded_without_reference,
            readiness_report=forged_report,
            prepared_session=prepared,
        )


def test_synchronization_input_requires_bundle_reference_readiness_inventory(
    tmp_path: Path,
) -> None:
    loaded, report, prepared = _ready_parts(tmp_path)
    payload = report.model_dump(mode="json")
    payload["task_reference_result"] = None
    missing_inventory = IngestionReadinessReport.model_validate(payload)

    with pytest.raises(ValueError, match="bundle task reference.*readiness inventory"):
        SynchronizationInput(
            loaded_manifest=loaded,
            readiness_report=missing_inventory,
            prepared_session=replace(prepared, task_reference=None),
        )


@pytest.mark.parametrize("owner", ["none", "model_bundle"])
def test_synchronization_input_rejects_orphan_bundle_reference_readiness_inventory(
    tmp_path: Path,
    owner: str,
) -> None:
    loaded, report, prepared = _ready_parts_without_bundle_reference(tmp_path, owner=owner)
    payload = report.model_dump(mode="json")
    payload["task_reference_result"] = {
        "modality": "task_reference",
        "declared_status": "missing",
        "required_for_import": False,
        "readiness": "unavailable",
        "source_paths": [],
        "source_checksums": {},
    }
    payload["disposition"] = "ready_partial"
    orphan_inventory = IngestionReadinessReport.model_validate(payload)

    with pytest.raises(ValueError, match="non-bundle task reference.*readiness inventory"):
        SynchronizationInput(
            loaded_manifest=loaded,
            readiness_report=orphan_inventory,
            prepared_session=prepared,
        )


@pytest.mark.parametrize("owner", ["none", "model_bundle"])
def test_synchronization_input_accepts_nonbundle_reference_without_bundle_inventory(
    tmp_path: Path,
    owner: str,
) -> None:
    loaded, report, prepared = _ready_parts_without_bundle_reference(tmp_path, owner=owner)

    accepted = SynchronizationInput(
        loaded_manifest=loaded,
        readiness_report=report,
        prepared_session=prepared,
    )

    assert accepted.readiness_report.task_reference_result is None
    assert accepted.prepared_session.task_reference is None


def _aligned_view(modality: str = "X") -> AlignedStreamView:
    table = pl.DataFrame({"source_row_index": [0], "t_ns": [0], "in_session": [True]})
    return AlignedStreamView(
        modality=modality,
        source_schema_id="flight-state-normalized-v0.1",
        aligned_schema_id="flight-state-aligned-v0.1",
        clock_id="sim-clock",
        tables={"samples": table},
        json_artifacts={"sidecar": {"unit": "m"}},
        file_artifacts={"images": ("streams/I/frame.png",)},
        source_checksums={"streams/XU.csv": "a" * 64},
    )


def test_aligned_stream_view_freezes_all_mappings() -> None:
    frame = pl.DataFrame({"sample_id": [1], "t_ns": [0], "in_session": [True]})
    tables = {"samples": frame}
    channel_names = ["Fz", "Cz"]
    calibration = {"gain": 1.0}
    sidecar = {
        "unit": "uV",
        "channels": {"names": channel_names},
        "calibration": [calibration],
    }
    json_artifacts = {"sidecar": sidecar}
    file_artifacts = {"images": ("streams/I/frame.png",)}
    checksums = {"streams/I/frame.png": "a" * 64}

    view = AlignedStreamView(
        modality="I",
        source_schema_id="vr-scene-source-bundle-v0.1",
        aligned_schema_id="vr-scene-aligned-v0.1",
        clock_id="scene-clock",
        tables=tables,
        json_artifacts=json_artifacts,
        file_artifacts=file_artifacts,
        source_checksums=checksums,
    )
    tables["other"] = frame
    sidecar["unit"] = "changed"
    channel_names.append("Pz")
    calibration["gain"] = 99.0
    json_artifacts["other"] = {}
    file_artifacts["other"] = ()
    checksums["other"] = "b" * 64

    assert view.tables == {"samples": frame}
    assert view.tables["samples"] is frame
    assert view.json_artifacts == {
        "sidecar": {
            "unit": "uV",
            "channels": {"names": ("Fz", "Cz")},
            "calibration": ({"gain": 1.0},),
        }
    }
    assert view.file_artifacts == {"images": ("streams/I/frame.png",)}
    assert view.source_checksums == {"streams/I/frame.png": "a" * 64}
    with pytest.raises(TypeError):
        cast(dict[str, pl.DataFrame], view.tables)["new"] = frame
    with pytest.raises(TypeError):
        cast(dict[str, object], view.json_artifacts["sidecar"])["new"] = 1
    channels = cast(dict[str, object], view.json_artifacts["sidecar"]["channels"])
    with pytest.raises(TypeError):
        channels["new"] = 1
    frozen_names = cast(tuple[str, ...], channels["names"])
    with pytest.raises(TypeError):
        operator.setitem(cast(MutableSequence[str], frozen_names), 0, "Pz")


def test_aligned_session_keeps_task_reference_outside_core_streams() -> None:
    x_view = _aligned_view()
    reference_view = replace(
        x_view,
        modality="task_reference",
        source_schema_id="task-reference-normalized-v0.1",
        aligned_schema_id="task-reference-path-aligned-v0.1",
    )
    annotations = AlignedAnnotations(
        revision="synthetic-v0.1",
        phases=(PhaseInterval(phase_id="phase-1", start_t_ns=0, end_t_ns=1),),
        events=(EventMarker(event_id="event-1", event_type="cue", t_ns=0),),
        baseline_intervals=(BaselineInterval(interval_id="baseline-1", start_t_ns=0, end_t_ns=1),),
        source_schema_ids={"phases": "phase-annotation-v0.1"},
        synthetic_semantics_unvalidated=True,
    )
    streams = {"X": x_view}
    phase_labels = ["takeoff", "landing"]
    context_metadata = {"labels": phase_labels}
    context = {
        "task_profile_id": "fixture-v0.1",
        "metadata": context_metadata,
    }
    session = AlignedSession(
        session_id="session-1",
        window=SessionWindow(
            end_t_ns=1,
            source="master-clock-x-mapped-coverage-v1",
        ),
        streams=streams,
        context=context,
        annotations=annotations,
        task_reference=reference_view,
        source_snapshot_fingerprint="a" * 64,
        synchronization_fingerprint="b" * 64,
    )
    streams["task_reference"] = reference_view
    context["other"] = True
    phase_labels.append("hover")
    context_metadata["invented"] = True

    assert session.streams == {"X": x_view}
    assert session.task_reference is reference_view
    assert session.context == {
        "task_profile_id": "fixture-v0.1",
        "metadata": {"labels": ("takeoff", "landing")},
    }
    frozen_metadata = cast(dict[str, object], session.context["metadata"])
    with pytest.raises(TypeError):
        frozen_metadata["invented"] = True
    frozen_labels = cast(tuple[str, ...], frozen_metadata["labels"])
    with pytest.raises(TypeError):
        operator.setitem(cast(MutableSequence[str], frozen_labels), 0, "hover")
    with pytest.raises(ValueError, match="task_reference.*dedicated"):
        AlignedSession(
            session_id="session-1",
            window=session.window,
            streams={"X": x_view, "task_reference": reference_view},
            context={},
            annotations=annotations,
            task_reference=None,
            source_snapshot_fingerprint="a" * 64,
            synchronization_fingerprint="b" * 64,
        )


def test_aligned_session_rejects_non_core_streams() -> None:
    invented = replace(_aligned_view(), modality="invented")
    annotations = AlignedAnnotations(
        revision="synthetic-v0.1",
        phases=(),
        events=(),
        baseline_intervals=(),
        source_schema_ids={},
        synthetic_semantics_unvalidated=True,
    )

    with pytest.raises(ValueError, match="non-core streams"):
        AlignedSession(
            session_id="session-1",
            window=SessionWindow(
                end_t_ns=1,
                source="master-clock-x-mapped-coverage-v1",
            ),
            streams={"invented": invented},
            context={},
            annotations=annotations,
            task_reference=None,
            source_snapshot_fingerprint="a" * 64,
            synchronization_fingerprint="b" * 64,
        )
