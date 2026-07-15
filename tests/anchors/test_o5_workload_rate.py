from __future__ import annotations

from dataclasses import dataclass

import polars as pl
import pytest

from pilot_assessment.anchors.catalog import load_parameter_schema
from pilot_assessment.anchors.fingerprint import schema_descriptor_sha256
from pilot_assessment.anchors.primitives.movement import movement_kernel_from_table
from pilot_assessment.anchors.protocols import (
    AnchorPluginContext,
    PreprocessingArtifactIdentity,
    ProjectedSemanticScope,
    ReadOnlyTabularPayload,
    ResolvedDependencies,
    ResolvedPreprocessingDependency,
    TabularArtifactPayload,
)
from pilot_assessment.anchors.scoring import classify_computed_metrics, compile_scorer_policy
from pilot_assessment.contracts.anchor import EvidenceState
from pilot_assessment.contracts.anchor_execution import ControlEffectMapping
from pilot_assessment.contracts.anchor_v2 import AnchorArtifactRef
from pilot_assessment.contracts.synchronization import SessionWindow

NS = 1_000_000_000
SHA_A = "a" * 64
SHA_B = "b" * 64


def _definition():
    from pilot_assessment.anchors.plugins.o5_workload_rate import create_plugin

    return create_plugin().definition()


def _mapping(channel_id: str) -> ControlEffectMapping:
    return ControlEffectMapping(
        control_mapping_id=f"mapping-{channel_id}",
        state_axis_id=f"axis-{channel_id}",
        control_channel_id=channel_id,
        correct_sign=1,
        state_unit="m",
        control_unit="ratio",
        lower=-1.0,
        trim=0.0,
        upper=1.0,
    )


def _rows(*, omit_phase_2_support: bool = False, high_rate: bool = False) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for phase_index, phase_id in enumerate(("phase-1", "phase-2")):
        phase_start = phase_index * NS
        for channel_id in ("cyclic", "unused"):
            if omit_phase_2_support and phase_id == "phase-2":
                continue
            rows.extend(
                (
                    {
                        "phase_id": phase_id,
                        "channel_id": channel_id,
                        "event_t_ns": phase_start,
                        "event_id": f"{phase_id}-{channel_id}-support-0-start",
                        "event_kind": "support-start",
                        "amplitude": 0.0,
                    },
                    {
                        "phase_id": phase_id,
                        "channel_id": channel_id,
                        "event_t_ns": phase_start + NS,
                        "event_id": f"{phase_id}-{channel_id}-support-0-end",
                        "event_kind": "support-end",
                        "amplitude": 0.0,
                    },
                )
            )
        movement_count = 10 if high_rate else 1
        for index in range(movement_count):
            rows.append(
                {
                    "phase_id": phase_id,
                    "channel_id": "cyclic",
                    "event_t_ns": phase_start + (index + 1) * 100_000_000,
                    "event_id": f"{phase_id}-cyclic-movement-{index}",
                    "event_kind": "movement",
                    "amplitude": 10.0,
                }
            )
    return pl.DataFrame(
        rows,
        schema={
            "phase_id": pl.String,
            "channel_id": pl.String,
            "event_t_ns": pl.Int64,
            "event_id": pl.String,
            "event_kind": pl.String,
            "amplitude": pl.Float64,
        },
    ).sort(["phase_id", "channel_id", "event_t_ns", "event_id"], maintain_order=True)


def _dependency(frame: pl.DataFrame) -> ResolvedPreprocessingDependency:
    descriptor = {
        "type": "table",
        "fields": [
            {"name": "phase_id", "dtype": "utf8", "unit": "id", "nullable": False},
            {"name": "channel_id", "dtype": "utf8", "unit": "id", "nullable": False},
            {"name": "event_t_ns", "dtype": "i64", "unit": "ns", "nullable": False},
            {"name": "event_id", "dtype": "utf8", "unit": "id", "nullable": False},
            {"name": "event_kind", "dtype": "utf8", "unit": "id", "nullable": False},
            {
                "name": "amplitude",
                "dtype": "f64",
                "unit": "percent_full_travel",
                "nullable": False,
            },
        ],
        "canonical_order_keys": ["phase_id", "channel_id", "event_t_ns", "event_id"],
    }
    payload = ReadOnlyTabularPayload(
        schema_id="movement-events-v1-output-v0.1",
        schema_descriptor=descriptor,
        frame=frame,
        order_keys=("phase_id", "channel_id", "event_t_ns", "event_id"),
        artifact_kind="movement-events-table",
        grid_hash=None,
        start_t_ns=0,
        end_t_ns=2 * NS,
        logical_content_sha256=SHA_A,
    )
    identity = PreprocessingArtifactIdentity(
        recipe_id="movement-events-v1",
        recipe_version="0.1.0",
        provider_id="movement-events-v1",
        provider_version="1.0.0",
        implementation_digest=SHA_A,
        parameter_schema_id="movement-events-v1-parameters-0.1",
        parameter_schema_sha256=SHA_B,
        parameter_hash=SHA_A,
        scope_kind="session",
        scope_id="session-1",
        scope_start_t_ns=0,
        scope_end_t_ns=2 * NS,
        phase_id=None,
        event_id=None,
        window_id=None,
        schema_id=payload.schema_id,
        schema_sha256=schema_descriptor_sha256(payload.schema_id, descriptor),
        artifact_kind=payload.artifact_kind,
        payload_kind="table",
        logical_content_sha256=SHA_A,
        input_fingerprints=(("stream", "U", SHA_A),),
        dependency_fingerprints=(),
    )
    return ResolvedPreprocessingDependency(identity=identity, payload=payload)


def _context() -> AnchorPluginContext:
    mappings = (_mapping("cyclic"), _mapping("unused"))
    return AnchorPluginContext(
        session_id="session-1",
        session_window=SessionWindow(end_t_ns=2 * NS, source="master-clock-x-mapped-coverage-v1"),
        streams={},
        context={},
        references={},
        semantic_scope=ProjectedSemanticScope(
            values={
                "semantic.control_mappings": [item.model_dump(mode="json") for item in mappings]
            }
        ),
    )


def _temporal_recipe() -> dict[str, object]:
    return {
        "window_policy": "bound-phase-windows-v1",
        "window_id_prefix": "o5",
        "scope_ids": ["phase-1", "phase-2"],
        "phase_bindings": [
            {
                "phase_id": "phase-1",
                "start_t_ns": 0,
                "end_t_ns": NS,
                "include_session_terminal_point": False,
            },
            {
                "phase_id": "phase-2",
                "start_t_ns": NS,
                "end_t_ns": 2 * NS,
                "include_session_terminal_point": True,
            },
        ],
        "control_mapping_ids": ["mapping-cyclic", "mapping-unused"],
    }


@dataclass
class _Emitter:
    payloads: list[tuple[str, TabularArtifactPayload]]

    def stage_table(self, artifact_id: str, payload: TabularArtifactPayload) -> AnchorArtifactRef:
        self.payloads.append((artifact_id, payload))
        return AnchorArtifactRef(
            artifact_id=artifact_id,
            kind=payload.artifact_kind,
            schema_id=payload.schema_id,
            logical_content_sha256=SHA_A,
            storage_file_sha256=None,
            row_count=payload.frame.height,
            start_t_ns=payload.start_t_ns,
            end_t_ns=payload.end_t_ns,
            grid_hash=payload.grid_hash,
            producer_anchor_id="O5",
            producer_plugin_id="o5-workload-rate",
            producer_plugin_version="0.1.0",
            parameter_hash=SHA_A,
            dependency_fingerprints=(SHA_A,),
        )

    def stage_blob(self, artifact_id, payload):  # pragma: no cover - O5 is table-only
        raise AssertionError((artifact_id, payload))


def _compute(frame: pl.DataFrame):
    emitter = _Emitter([])
    measurement = (
        __import__("pilot_assessment.anchors.plugins.o5_workload_rate", fromlist=["create_plugin"])
        .create_plugin()
        .compute(
            _context(),
            {"w_min_hz": 1.0},
            _temporal_recipe(),
            ResolvedDependencies(
                results={},
                artifacts={},
                algorithm_profiles={},
                preprocessing={"movement-events": _dependency(frame)},
            ),
            emitter,
        )
    )
    return measurement, emitter


def test_o5_definition_binds_shared_preprocessing_dependency() -> None:
    definition = _definition()
    assert definition.anchor_id == "O5"
    assert definition.required_streams == ("U",)
    assert definition.required_semantic_paths == ("semantic.control_mappings",)
    assert tuple(item.dependency_id for item in definition.dependencies) == ("movement-events",)


def test_o5_aggregates_all_phases_and_keeps_configured_zero_channel() -> None:
    measurement, emitter = _compute(_rows())

    # cyclic=1 Hz, unused=0 Hz, mean=0.5 Hz, W_min=1 Hz
    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(0.5)
    assert tuple(item.breakdown_id for item in measurement.phase_results) == (
        "phase-1",
        "phase-2",
    )
    assert all(item.primary_value.value == pytest.approx(0.5) for item in measurement.phase_results)
    assert len(emitter.payloads) == 1
    artifact_id, payload = emitter.payloads[0]
    assert artifact_id == "movement-events"
    assert payload.frame["event_kind"].to_list() == ["movement", "movement"]
    assert set(payload.frame["channel_id"].to_list()) == {"cyclic"}


def test_o5_does_not_publish_partial_session_score_when_later_phase_has_no_support() -> None:
    measurement, emitter = _compute(_rows(omit_phase_2_support=True))

    assert measurement.calculation_status.value == "missing_input"
    assert measurement.primary_value is None
    assert tuple(item.calculation_status.value for item in measurement.phase_results) == (
        "computed",
        "missing_input",
    )
    assert emitter.payloads == []


def test_o5_high_finite_rate_is_computed_negative_evidence_not_quality_filtered() -> None:
    measurement, _emitter = _compute(_rows(high_rate=True))

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(5.0)
    parameter_schema = load_parameter_schema("o5-parameters-0.1")
    scorer_annotation = parameter_schema["x-scorer-policy-default"]
    assert isinstance(scorer_annotation, dict)
    state, _score, _likelihood = classify_computed_metrics(
        measurement.primary_value.value,
        {},
        None,
        compile_scorer_policy(scorer_annotation),
    )
    assert state is EvidenceState.UNACCEPTABLE


def test_o5_no_movements_is_a_valid_computed_zero_not_missing_data() -> None:
    support_only = _rows().filter(pl.col("event_kind") != "movement")

    measurement, emitter = _compute(support_only)

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(0.0)
    assert emitter.payloads == []


def test_dependency_table_round_trip_preserves_support_and_movements() -> None:
    kernel = movement_kernel_from_table(
        _rows(),
        phase_ids=("phase-1", "phase-2"),
        channel_ids=("cyclic", "unused"),
    )

    assert kernel.status == "computed"
    assert tuple(channel.channel_id for channel in kernel.channels) == ("cyclic", "unused")
    assert tuple(len(channel.movements) for channel in kernel.channels) == (2, 0)
    assert all(channel.observed_support_duration_ns == 2 * NS for channel in kernel.channels)


def test_o5_plugin_reuses_the_shared_o5_kernel(monkeypatch: pytest.MonkeyPatch) -> None:
    from pilot_assessment.anchors.plugins import o5_workload_rate

    real_kernel = o5_workload_rate.compute_o5_kernel
    calls: list[tuple[str, ...]] = []

    def spy_kernel(movement, channel_ids, w_min_hz):
        calls.append(channel_ids)
        return real_kernel(movement, channel_ids, w_min_hz)

    monkeypatch.setattr(o5_workload_rate, "compute_o5_kernel", spy_kernel)

    measurement, _emitter = _compute(_rows())

    assert measurement.calculation_status.value == "computed"
    assert calls == [("cyclic", "unused")] * 3
