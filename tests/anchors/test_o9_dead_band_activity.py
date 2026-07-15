from __future__ import annotations

from dataclasses import dataclass

import polars as pl
import pytest

from pilot_assessment.anchors.catalog import load_parameter_schema
from pilot_assessment.anchors.fingerprint import schema_descriptor_sha256
from pilot_assessment.anchors.plugins.o9_dead_band_activity import create_plugin
from pilot_assessment.anchors.protocols import (
    AnchorPluginContext,
    PreprocessingArtifactIdentity,
    ProjectedSemanticScope,
    ReadOnlyTabularPayload,
    ResolvedArtifactDependency,
    ResolvedDependencies,
    ResolvedPreprocessingDependency,
    TabularArtifactPayload,
)
from pilot_assessment.anchors.scoring import classify_computed_metrics, compile_scorer_policy
from pilot_assessment.contracts.anchor import EvidenceState
from pilot_assessment.contracts.anchor_v2 import AnchorArtifactRef
from pilot_assessment.contracts.synchronization import SessionWindow
from pilot_assessment.synchronization.models import AlignedStreamView

NS = 1_000_000_000
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _u_table(timestamps: tuple[int, ...]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "source_row_index": pl.Series(
                "source_row_index", range(len(timestamps)), dtype=pl.UInt64
            ),
            "t_ns": pl.Series("t_ns", timestamps, dtype=pl.Int64),
            "in_session": pl.Series("in_session", [True] * len(timestamps), dtype=pl.Boolean),
            "cyclic": pl.Series("cyclic", [0.0] * len(timestamps), dtype=pl.Float64),
            "pedals": pl.Series("pedals", [0.0] * len(timestamps), dtype=pl.Float64),
        }
    )


def _context(timestamps: tuple[int, ...], end_t_ns: int) -> AnchorPluginContext:
    stream = AlignedStreamView(
        modality="U",
        source_schema_id="u-raw-v0.1",
        aligned_schema_id="u-aligned-v0.1",
        clock_id="master-clock",
        tables={"samples": _u_table(timestamps)},
        json_artifacts={},
        file_artifacts={},
        source_checksums={"samples": SHA_A},
    )
    return AnchorPluginContext(
        session_id="session-1",
        session_window=SessionWindow(
            end_t_ns=end_t_ns,
            source="master-clock-x-mapped-coverage-v1",
        ),
        streams={"U": stream},
        context={},
        references={},
        semantic_scope=ProjectedSemanticScope(values={}),
    )


def _descriptor(fields: tuple[tuple[str, str, str], ...], order: tuple[str, ...]):
    return {
        "type": "table",
        "fields": [
            {"name": name, "dtype": dtype, "unit": unit, "nullable": False}
            for name, dtype, unit in fields
        ],
        "canonical_order_keys": list(order),
    }


O1_DESCRIPTOR = _descriptor(
    (
        ("phase_id", "utf8", "id"),
        ("t_ns", "i64", "ns"),
        ("source_row_id", "i64", "id"),
        ("axis_order", "i64", "index"),
        ("axis_id", "utf8", "id"),
        ("inside", "bool", "bool"),
    ),
    ("phase_id", "t_ns", "source_row_id", "axis_order", "axis_id"),
)
O4_DESCRIPTOR = _descriptor(
    (
        ("phase_id", "utf8", "id"),
        ("t_ns", "i64", "ns"),
        ("source_row_id", "i64", "id"),
        ("stable", "bool", "bool"),
    ),
    ("phase_id", "t_ns", "source_row_id"),
)
MOVEMENT_DESCRIPTOR = _descriptor(
    (
        ("phase_id", "utf8", "id"),
        ("channel_id", "utf8", "id"),
        ("event_t_ns", "i64", "ns"),
        ("event_id", "utf8", "id"),
        ("event_kind", "utf8", "id"),
        ("amplitude", "f64", "percent_full_travel"),
    ),
    ("phase_id", "channel_id", "event_t_ns", "event_id"),
)


def _artifact_dependency(
    *,
    anchor_id: str,
    artifact_id: str,
    schema_id: str,
    artifact_kind: str,
    descriptor: dict[str, object],
    frame: pl.DataFrame,
    order_keys: tuple[str, ...],
    end_t_ns: int,
    digest: str,
) -> ResolvedArtifactDependency:
    payload = ReadOnlyTabularPayload(
        schema_id=schema_id,
        schema_descriptor=descriptor,
        frame=frame,
        order_keys=order_keys,
        artifact_kind=artifact_kind,
        grid_hash=None,
        start_t_ns=0,
        end_t_ns=end_t_ns,
        logical_content_sha256=digest,
    )
    ref = AnchorArtifactRef(
        artifact_id=artifact_id,
        kind=artifact_kind,
        schema_id=schema_id,
        logical_content_sha256=digest,
        storage_file_sha256=None,
        row_count=frame.height,
        start_t_ns=0,
        end_t_ns=end_t_ns,
        grid_hash=None,
        producer_anchor_id=anchor_id,
        producer_plugin_id=f"{anchor_id.lower()}-test-plugin",
        producer_plugin_version="0.1.0",
        parameter_hash=SHA_A,
        dependency_fingerprints=(),
    )
    return ResolvedArtifactDependency(ref=ref, payload=payload)


def _mask_dependencies(
    timestamps: tuple[int, ...],
    desired: tuple[bool, ...],
    stable: tuple[bool, ...],
    end_t_ns: int,
) -> dict[str, ResolvedArtifactDependency]:
    assert len(timestamps) == len(desired) == len(stable)
    o1 = pl.DataFrame(
        {
            "phase_id": pl.Series("phase_id", ["phase-1"] * len(timestamps), dtype=pl.String),
            "t_ns": pl.Series("t_ns", timestamps, dtype=pl.Int64),
            "source_row_id": pl.Series("source_row_id", range(len(timestamps)), dtype=pl.Int64),
            "axis_order": pl.Series("axis_order", [0] * len(timestamps), dtype=pl.Int64),
            "axis_id": pl.Series("axis_id", ["position"] * len(timestamps), dtype=pl.String),
            "inside": pl.Series("inside", desired, dtype=pl.Boolean),
        }
    )
    o4 = pl.DataFrame(
        {
            "phase_id": pl.Series("phase_id", ["phase-1"] * len(timestamps), dtype=pl.String),
            "t_ns": pl.Series("t_ns", timestamps, dtype=pl.Int64),
            "source_row_id": pl.Series("source_row_id", range(len(timestamps)), dtype=pl.Int64),
            "stable": pl.Series("stable", stable, dtype=pl.Boolean),
        }
    )
    return {
        "o1-mask": _artifact_dependency(
            anchor_id="O1",
            artifact_id="desired-envelope-mask",
            schema_id="desired-envelope-mask-v0.1",
            artifact_kind="sample_mask",
            descriptor=O1_DESCRIPTOR,
            frame=o1,
            order_keys=("phase_id", "t_ns", "source_row_id", "axis_order", "axis_id"),
            end_t_ns=end_t_ns,
            digest=SHA_B,
        ),
        "o4-mask": _artifact_dependency(
            anchor_id="O4",
            artifact_id="stable-hover-mask",
            schema_id="stable-hover-mask-v0.1",
            artifact_kind="sample_mask",
            descriptor=O4_DESCRIPTOR,
            frame=o4,
            order_keys=("phase_id", "t_ns", "source_row_id"),
            end_t_ns=end_t_ns,
            digest=SHA_C,
        ),
    }


def _movement_frame(
    end_t_ns: int,
    events: dict[str, tuple[tuple[int, float], ...]],
    *,
    with_support: bool = True,
) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for channel_id in sorted(events):
        if with_support:
            rows.extend(
                (
                    {
                        "phase_id": "phase-1",
                        "channel_id": channel_id,
                        "event_t_ns": 0,
                        "event_id": f"phase-1-{channel_id}-support-start",
                        "event_kind": "support-start",
                        "amplitude": 0.0,
                    },
                    {
                        "phase_id": "phase-1",
                        "channel_id": channel_id,
                        "event_t_ns": end_t_ns,
                        "event_id": f"phase-1-{channel_id}-support-end",
                        "event_kind": "support-end",
                        "amplitude": 0.0,
                    },
                )
            )
        for index, (event_t_ns, amplitude) in enumerate(events[channel_id]):
            rows.append(
                {
                    "phase_id": "phase-1",
                    "channel_id": channel_id,
                    "event_t_ns": event_t_ns,
                    "event_id": f"phase-1-{channel_id}-movement-{index:06d}",
                    "event_kind": "movement",
                    "amplitude": amplitude,
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


def _movement_dependency(frame: pl.DataFrame, end_t_ns: int) -> ResolvedPreprocessingDependency:
    payload = ReadOnlyTabularPayload(
        schema_id="movement-events-v1-output-v0.1",
        schema_descriptor=MOVEMENT_DESCRIPTOR,
        frame=frame,
        order_keys=("phase_id", "channel_id", "event_t_ns", "event_id"),
        artifact_kind="movement-events-table",
        grid_hash=None,
        start_t_ns=0,
        end_t_ns=end_t_ns,
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
        scope_end_t_ns=end_t_ns,
        phase_id=None,
        event_id=None,
        window_id=None,
        schema_id=payload.schema_id,
        schema_sha256=schema_descriptor_sha256(payload.schema_id, MOVEMENT_DESCRIPTOR),
        artifact_kind=payload.artifact_kind,
        payload_kind="table",
        logical_content_sha256=SHA_A,
        input_fingerprints=(("stream", "U", SHA_A),),
        dependency_fingerprints=(),
    )
    return ResolvedPreprocessingDependency(identity=identity, payload=payload)


def _recipe(end_t_ns: int, channel_ids: tuple[str, ...]) -> dict[str, object]:
    return {
        "window_policy": "bound-phase-windows-v1",
        "window_id_prefix": "o9",
        "scope_ids": ["phase-1"],
        "phase_bindings": [
            {
                "phase_id": "phase-1",
                "start_t_ns": 0,
                "end_t_ns": end_t_ns,
                "include_session_terminal_point": True,
            }
        ],
        "control_channel_ids": list(channel_ids),
        "table_role": "samples",
        "timestamp_column": "t_ns",
        "in_session_column": "in_session",
        "stable_keys": ["source_row_index"],
        "mask_gap_threshold_ns": 2 * NS,
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
            producer_anchor_id="O9",
            producer_plugin_id="o9-dead-band-activity",
            producer_plugin_version="0.1.0",
            parameter_hash=SHA_A,
            dependency_fingerprints=(SHA_A, SHA_B, SHA_C),
        )

    def stage_blob(self, artifact_id, payload):  # pragma: no cover - O9 is table-only
        raise AssertionError((artifact_id, payload))


def _compute(
    *,
    mask_times: tuple[int, ...],
    desired: tuple[bool, ...],
    stable: tuple[bool, ...],
    u_times: tuple[int, ...],
    events: dict[str, tuple[tuple[int, float], ...]],
    end_t_ns: int,
    with_movement_support: bool = True,
    include_mask_gap_binding: bool = True,
):
    channel_ids = tuple(sorted(events))
    masks = _mask_dependencies(mask_times, desired, stable, end_t_ns)
    movement = _movement_dependency(
        _movement_frame(end_t_ns, events, with_support=with_movement_support), end_t_ns
    )
    emitter = _Emitter([])
    recipe = _recipe(end_t_ns, channel_ids)
    if not include_mask_gap_binding:
        recipe.pop("mask_gap_threshold_ns")
    measurement = create_plugin().compute(
        _context(u_times, end_t_ns),
        {
            "micro_movement_max_amplitude_pct": 5.0,
            "nearest_match_tolerance_ns": 20_000_000,
        },
        recipe,
        ResolvedDependencies(
            results={},
            artifacts=masks,
            algorithm_profiles={},
            preprocessing={"movement-events": movement},
        ),
        emitter,
    )
    return measurement, emitter


def _state(value: float) -> EvidenceState:
    annotation = load_parameter_schema("o9-parameters-0.1")["x-scorer-policy-default"]
    assert isinstance(annotation, dict)
    state, _score, _likelihood = classify_computed_metrics(
        value, {}, None, compile_scorer_policy(annotation)
    )
    return state


def test_o9_definition_declares_exact_masks_movement_provider_and_artifact() -> None:
    definition = create_plugin().definition()

    assert definition.anchor_id == "O9"
    assert definition.required_streams == ("U",)
    assert definition.required_semantic_paths == ()
    assert tuple(item.dependency_id for item in definition.dependencies) == (
        "o1-mask",
        "o4-mask",
        "movement-events",
    )
    assert tuple(item.artifact_id for item in definition.artifact_recipes) == (
        "micro-movement-events",
    )


def test_o9_no_stable_hover_precedes_absent_u_and_movement_support() -> None:
    measurement, emitter = _compute(
        mask_times=(0, NS),
        desired=(True, True),
        stable=(False, False),
        u_times=(),
        events={"cyclic": ()},
        end_t_ns=2 * NS,
        with_movement_support=False,
    )

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is None
    assert measurement.primary_value_reason == "no_stable_hover"
    assert measurement.classification_override_candidate is not None
    assert measurement.classification_override_candidate.code == "no_stable_hover"
    assert measurement.raw_metrics["stable-opportunity-duration"].value == pytest.approx(0.0)
    assert emitter.payloads == []


def test_o9_only_reports_no_u_temporal_support_after_observing_stable_spans() -> None:
    measurement, emitter = _compute(
        mask_times=(0, NS),
        desired=(True, True),
        stable=(True, True),
        u_times=(),
        events={"cyclic": ()},
        end_t_ns=2 * NS,
    )

    assert measurement.calculation_status.value == "missing_input"
    assert measurement.primary_value is None
    assert measurement.classification_override_candidate is None
    assert measurement.raw_metrics["stable-opportunity-duration"].value == pytest.approx(2.0)
    assert measurement.raw_metrics["matched-stable-duration"].value == pytest.approx(0.0)
    assert measurement.diagnostics[0].error_code == "anchor.o9.no_temporal_support_U"
    assert emitter.payloads == []


def test_o9_partial_matches_use_support_duration_bounds_and_channel_maximum() -> None:
    measurement, emitter = _compute(
        mask_times=(0, NS, 2 * NS, 3 * NS),
        desired=(True, True, True, True),
        stable=(True, True, True, True),
        u_times=(0, 3 * NS),
        events={
            "cyclic": (
                (100_000_000, 0.5),
                (200_000_000, 0.499),
                (2_500_000_000, 1.0),
                (3_100_000_000, 5.0),
                (3_200_000_000, 5.001),
            ),
            "pedals": (
                (300_000_000, 0.5),
                (400_000_000, 1.0),
                (3_300_000_000, 5.0),
            ),
        },
        end_t_ns=4 * NS,
    )

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(1.5)
    assert _state(measurement.primary_value.value) is EvidenceState.ADEQUATE
    assert measurement.raw_metrics["matched-stable-duration"].value == pytest.approx(2.0)
    assert measurement.raw_metrics["micro-movement-count"].value == 3
    assert len(emitter.payloads) == 1
    artifact_id, payload = emitter.payloads[0]
    assert artifact_id == "micro-movement-events"
    assert payload.frame.height == 5
    assert payload.frame["amplitude"].to_list() == pytest.approx([0.5, 5.0, 0.5, 1.0, 5.0])


@pytest.mark.parametrize(
    ("event_count", "expected_state"),
    (
        (0, EvidenceState.DESIRED),
        (1, EvidenceState.ADEQUATE),
        (2, EvidenceState.UNACCEPTABLE),
    ),
)
def test_o9_exact_one_and_two_hz_boundaries(
    event_count: int, expected_state: EvidenceState
) -> None:
    events = tuple((100_000_000 + index * 100_000_000, 1.0) for index in range(event_count))
    measurement, _emitter = _compute(
        mask_times=(0, NS),
        desired=(True, True),
        stable=(True, True),
        u_times=(0, NS),
        events={"cyclic": events},
        end_t_ns=NS,
    )

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(float(event_count))
    assert _state(measurement.primary_value.value) is expected_state


def test_o9_does_not_invoke_an_undeclared_movement_detector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pilot_assessment.anchors.primitives import movement

    def forbidden(*args, **kwargs):
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(movement, "detect_movement_events", forbidden)
    measurement, _emitter = _compute(
        mask_times=(0, NS),
        desired=(True, True),
        stable=(True, True),
        u_times=(0, NS),
        events={"cyclic": ((200_000_000, 1.0),)},
        end_t_ns=NS,
    )

    assert measurement.calculation_status.value == "computed"


def test_o9_requires_an_explicit_x_mask_gap_binding() -> None:
    with pytest.raises(ValueError, match="mask_gap_threshold_ns"):
        _compute(
            mask_times=(0, NS),
            desired=(True, True),
            stable=(True, True),
            u_times=(0, NS),
            events={"cyclic": ()},
            end_t_ns=NS,
            include_mask_gap_binding=False,
        )
