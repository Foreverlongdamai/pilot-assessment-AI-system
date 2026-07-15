from __future__ import annotations

from dataclasses import dataclass

import polars as pl
import pytest
from pydantic import ValidationError

from pilot_assessment.anchors.catalog import load_parameter_schema
from pilot_assessment.anchors.plugins.o6_control_magnitude_rms import create_plugin
from pilot_assessment.anchors.protocols import (
    AnchorPluginContext,
    ProjectedSemanticScope,
    ResolvedDependencies,
    TabularArtifactPayload,
)
from pilot_assessment.anchors.scoring import classify_computed_metrics, compile_scorer_policy
from pilot_assessment.contracts.anchor import EvidenceState
from pilot_assessment.contracts.anchor_execution import (
    ControlEffectMapping,
    ResolvedInputFieldContract,
    ResolvedInputTableContract,
)
from pilot_assessment.contracts.anchor_v2 import AnchorArtifactRef
from pilot_assessment.contracts.synchronization import SessionWindow
from pilot_assessment.synchronization.models import AlignedStreamView
from tests.m4_support.micro_inputs import tiny_u_table

NS = 1_000_000_000
SHA_A = "a" * 64


def _mapping(
    channel_id: str,
    *,
    lower: float = -1.0,
    trim: float = 0.0,
    upper: float = 1.0,
) -> ControlEffectMapping:
    return ControlEffectMapping(
        control_mapping_id=f"mapping-{channel_id}",
        state_axis_id=f"axis-{channel_id}",
        control_channel_id=channel_id,
        correct_sign=1,
        state_unit="m",
        control_unit="ratio",
        lower=lower,
        trim=trim,
        upper=upper,
    )


def _contract(*channels: str) -> ResolvedInputTableContract:
    return ResolvedInputTableContract(
        modality="U",
        table_role="samples",
        stream_aligned_schema_id="u-aligned-v0.1",
        table_aligned_schema_id="u-samples-aligned-v0.1",
        coordinate_frame_id="cockpit-controls",
        fields=(
            ResolvedInputFieldContract(
                field_name="source_row_index", dtype_id="u64", unit="index", nullable=False
            ),
            ResolvedInputFieldContract(
                field_name="t_ns", dtype_id="i64", unit="ns", nullable=False
            ),
            ResolvedInputFieldContract(
                field_name="in_session", dtype_id="bool", unit="bool", nullable=False
            ),
            *tuple(
                ResolvedInputFieldContract(
                    field_name=channel, dtype_id="f64", unit="ratio", nullable=False
                )
                for channel in channels
            ),
        ),
    )


def _phases(*spans: tuple[str, int, int]) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "phase_id": phase_id,
            "start_t_ns": start,
            "end_t_ns": end,
            "include_session_terminal_point": index == len(spans) - 1,
        }
        for index, (phase_id, start, end) in enumerate(spans)
    )


def _context(
    table: pl.DataFrame,
    mappings: tuple[ControlEffectMapping, ...],
    contract: ResolvedInputTableContract,
    end_t_ns: int,
) -> AnchorPluginContext:
    stream = AlignedStreamView(
        modality="U",
        source_schema_id="u-raw-v0.1",
        aligned_schema_id="u-aligned-v0.1",
        clock_id="master-clock",
        tables={"samples": table},
        json_artifacts={},
        file_artifacts={},
        source_checksums={"samples": SHA_A},
    )
    return AnchorPluginContext(
        session_id="session-1",
        session_window=SessionWindow(end_t_ns=end_t_ns, source="master-clock-x-mapped-coverage-v1"),
        streams={"U": stream},
        context={},
        references={},
        semantic_scope=ProjectedSemanticScope(
            values={
                "semantic.control_mappings": [
                    mapping.model_dump(mode="json") for mapping in mappings
                ]
            }
        ),
        input_table_contracts=(contract,),
    )


def _recipe(
    phases: tuple[dict[str, object], ...],
    mappings: tuple[ControlEffectMapping, ...],
    contract: ResolvedInputTableContract,
    *,
    gap_threshold_ns: int = 2 * NS,
) -> dict[str, object]:
    return {
        "window_policy": "bound-phase-windows-v1",
        "window_id_prefix": "o6",
        "scope_ids": [phase["phase_id"] for phase in phases],
        "phase_bindings": list(phases),
        "control_mapping_ids": sorted(mapping.control_mapping_id for mapping in mappings),
        "input_table_contracts": [contract.model_dump(mode="json")],
        "table_role": "samples",
        "timestamp_column": "t_ns",
        "in_session_column": "in_session",
        "stable_keys": ["source_row_index"],
        "gap_threshold_ns": gap_threshold_ns,
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
            producer_anchor_id="O6",
            producer_plugin_id="o6-control-magnitude-rms",
            producer_plugin_version="0.1.0",
            parameter_hash=SHA_A,
            dependency_fingerprints=(),
        )

    def stage_blob(self, artifact_id, payload):  # pragma: no cover - O6 is table-only
        raise AssertionError((artifact_id, payload))


def _compute(
    table: pl.DataFrame,
    mappings: tuple[ControlEffectMapping, ...],
    weights: tuple[tuple[str, float], ...],
    phases: tuple[dict[str, object], ...],
    *,
    gap_threshold_ns: int = 2 * NS,
):
    channels = tuple(sorted({mapping.control_channel_id for mapping in mappings}))
    contract = _contract(*channels)
    end_t_ns = max(int(phase["end_t_ns"]) for phase in phases)
    emitter = _Emitter([])
    measurement = create_plugin().compute(
        _context(table, mappings, contract, end_t_ns),
        {
            "channel_weights": [
                {"channel_id": channel_id, "weight": weight} for channel_id, weight in weights
            ]
        },
        _recipe(phases, mappings, contract, gap_threshold_ns=gap_threshold_ns),
        ResolvedDependencies(results={}, artifacts={}, algorithm_profiles={}, preprocessing={}),
        emitter,
    )
    return measurement, emitter


def _state(value: float) -> EvidenceState:
    annotation = load_parameter_schema("o6-parameters-0.1")["x-scorer-policy-default"]
    assert isinstance(annotation, dict)
    state, _score, _likelihood = classify_computed_metrics(
        value, {}, None, compile_scorer_policy(annotation)
    )
    return state


def test_o6_definition_declares_exact_stream_semantic_and_artifact_contract() -> None:
    definition = create_plugin().definition()

    assert definition.anchor_id == "O6"
    assert definition.required_streams == ("U",)
    assert definition.required_semantic_paths == ("semantic.control_mappings",)
    assert definition.dependencies == ()
    assert tuple(recipe.artifact_id for recipe in definition.artifact_recipes) == (
        "rms-contribution-trace",
    )


def test_o6_uses_both_piecewise_branches_and_exact_fifty_boundary() -> None:
    mapping = _mapping("stick", lower=-2.0, trim=0.0, upper=1.0)
    table = tiny_u_table(
        (0, NS, 2 * NS, 3 * NS),
        {"stick": (-1.0, -1.0, 0.5, 0.5)},
    )

    measurement, emitter = _compute(
        table,
        (mapping,),
        (("stick", 1.0),),
        _phases(("phase-1", 0, 4 * NS)),
    )

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(50.0)
    assert _state(measurement.primary_value.value) is EvidenceState.ADEQUATE
    assert len(emitter.payloads) == 1
    artifact_id, payload = emitter.payloads[0]
    assert artifact_id == "rms-contribution-trace"
    assert payload.frame.to_dicts() == [
        {
            "phase_id": "phase-1",
            "channel_id": "stick",
            "start_t_ns": 0,
            "end_t_ns": 4 * NS,
            "rms": pytest.approx(50.0),
            "weight": 1.0,
        }
    ]


@pytest.mark.parametrize(
    ("value", "expected_state"),
    ((0.3, EvidenceState.DESIRED), (0.5, EvidenceState.ADEQUATE)),
)
def test_o6_exact_thirty_and_fifty_thresholds(value: float, expected_state: EvidenceState) -> None:
    mapping = _mapping("stick")
    measurement, _emitter = _compute(
        tiny_u_table((0, NS), {"stick": (value, value)}),
        (mapping,),
        (("stick", 1.0),),
        _phases(("phase-1", 0, 2 * NS)),
    )

    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(value * 100.0)
    assert _state(measurement.primary_value.value) is expected_state


def test_o6_integrates_left_hold_per_segment_without_crossing_gap() -> None:
    mapping = _mapping("stick")
    measurement, _emitter = _compute(
        tiny_u_table(
            (0, NS, 10 * NS, 11 * NS),
            {"stick": (1.0, 0.0, 1.0, 0.0)},
        ),
        (mapping,),
        (("stick", 1.0),),
        _phases(("phase-1", 0, 12 * NS)),
        gap_threshold_ns=2 * NS,
    )

    # Support is [0,1) + [10,12), not the unobserved nine-second gap.
    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(100.0 * (2.0 / 3.0) ** 0.5)
    assert measurement.raw_metrics["observed-support-duration"].value == 3 * NS
    assert measurement.raw_metrics["gap-count"].value == 1


def test_o6_pools_channel_energy_with_nonnegative_unit_sum_weights() -> None:
    mappings = (_mapping("pedals"), _mapping("stick"))
    measurement, emitter = _compute(
        tiny_u_table((0, NS), {"pedals": (0.0, 0.0), "stick": (1.0, 1.0)}),
        mappings,
        (("pedals", 0.75), ("stick", 0.25)),
        _phases(("phase-1", 0, 2 * NS)),
    )

    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(50.0)
    rows = emitter.payloads[0][1].frame.to_dicts()
    assert [(row["channel_id"], row["rms"], row["weight"]) for row in rows] == [
        ("pedals", 0.0, 0.75),
        ("stick", 100.0, 0.25),
    ]


def test_o6_pools_phase_energy_over_support_instead_of_averaging_phase_percentages() -> None:
    mapping = _mapping("stick")
    measurement, _emitter = _compute(
        tiny_u_table((0, NS), {"stick": (1.0, 0.0)}),
        (mapping,),
        (("stick", 1.0),),
        _phases(("phase-1", 0, NS), ("phase-2", NS, 10 * NS)),
    )

    # Phase RMS values are 100 and 0, but their observed durations are 1 s and 9 s.
    assert tuple(
        item.primary_value.value for item in measurement.phase_results if item.primary_value
    ) == pytest.approx((100.0, 0.0))
    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(100.0 / (10.0**0.5))


def test_o6_partial_support_still_computes_without_a_coverage_gate() -> None:
    mapping = _mapping("stick")
    measurement, _emitter = _compute(
        tiny_u_table((5 * NS,), {"stick": (0.4,)}),
        (mapping,),
        (("stick", 1.0),),
        _phases(("phase-1", 0, 10 * NS)),
    )

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(40.0)
    assert measurement.raw_metrics["observed-support-duration"].value == 5 * NS


def test_o6_finite_values_outside_endpoints_are_computed_above_one_hundred() -> None:
    mapping = _mapping("stick")
    measurement, _emitter = _compute(
        tiny_u_table((0, NS), {"stick": (2.0, 2.0)}),
        (mapping,),
        (("stick", 1.0),),
        _phases(("phase-1", 0, 2 * NS)),
    )

    assert measurement.calculation_status.value == "computed"
    assert measurement.primary_value is not None
    assert measurement.primary_value.value == pytest.approx(200.0)
    assert _state(measurement.primary_value.value) is EvidenceState.UNACCEPTABLE


def test_o6_rejects_invalid_calibration_and_invalid_weight_snapshots() -> None:
    with pytest.raises(ValidationError, match="lower < trim < upper"):
        _mapping("stick", lower=0.0, trim=0.0, upper=1.0)

    mapping = _mapping("stick")
    table = tiny_u_table((0, NS), {"stick": (0.0, 0.0)})
    phases = _phases(("phase-1", 0, 2 * NS))
    contract = _contract("stick")
    context = _context(table, (mapping,), contract, 2 * NS)
    recipe = _recipe(phases, (mapping,), contract)
    dependencies = ResolvedDependencies(
        results={}, artifacts={}, algorithm_profiles={}, preprocessing={}
    )

    for invalid in (
        [{"channel_id": "stick", "weight": -0.1}],
        [{"channel_id": "stick", "weight": 0.9}],
        [{"channel_id": "other", "weight": 1.0}],
    ):
        with pytest.raises(ValueError, match="weight"):
            create_plugin().compute(
                context,
                {"channel_weights": invalid},
                recipe,
                dependencies,
                _Emitter([]),
            )


def test_o6_does_not_publish_a_partial_session_score_when_one_phase_has_no_rows() -> None:
    mapping = _mapping("stick")
    measurement, emitter = _compute(
        tiny_u_table((0, NS), {"stick": (0.2, 0.2)}),
        (mapping,),
        (("stick", 1.0),),
        _phases(("phase-1", 0, 2 * NS), ("phase-2", 2 * NS, 4 * NS)),
    )

    assert measurement.calculation_status.value == "missing_input"
    assert measurement.primary_value is None
    assert tuple(item.calculation_status.value for item in measurement.phase_results) == (
        "computed",
        "missing_input",
    )
    assert emitter.payloads == []
