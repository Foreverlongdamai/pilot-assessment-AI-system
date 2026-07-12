# M3 Native-Rate Time Synchronization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert one M2-validated multimodal Session Bundle into deterministic native-rate aligned views and a public `SynchronizationReport`, while preserving every raw row and keeping formal assessment authorization false.

**Architecture:** A single M1 `LoadedManifest` snapshot feeds M2 inspection and an internal `SynchronizationInput`. Versioned temporal bindings route point, interval, inherited, and untimed artifact roles through one Decimal/round-half-even clock kernel; the service returns an in-process immutable `AlignedSession` plus a Pydantic/JSON-Schema report. M3 performs no interpolation or resampling; M4 owns anchor-specific grids and windows.

**Tech Stack:** Python 3.11, Pydantic 2, Polars 1.x, Decimal, importlib.resources, JSON Schema Draft 2020-12, pytest, Ruff, ty, uv.

---

## Approved source of truth

- Design: `docs/product/specs/2026-07-12-m3-native-time-synchronization-design.md`
- Upstream contracts: M1 loader, M2 `PreparedSession`, `IngestionReadinessReport`, and `m2-profiles-0.1.json`
- Frozen decisions to ratify: D-016 through D-020
- Frozen scope: native-rate mapping only; no signal interpolation/resampling/window grid
- Frozen session window: `[0, max(mapped X primary t_ns)]`
- Frozen mapping: `round_half_even(source_s × scale × 1e9 + offset_ns)`; drift is diagnostic only
- Frozen report field: `source_snapshot_fingerprint`
- Frozen task-reference runtime key: stream schema `task-reference-normalized-v0.1`, role `commanded_path`
- Frozen source-data role: the repository-external CSV is a captured format sample only, with no valid trajectory, task ground truth, expert phase labels, or performance meaning
- Frozen interpretation: X-derived session end is a technical time boundary only; synthetic reference/annotations are interface fixtures and cannot support tracking or competency claims

## Locked production structure

~~~text
src/pilot_assessment/
  contracts/
    synchronization.py
  synchronization/
    __init__.py
    models.py
    clock.py
    profiles.py
    bindings.py
    annotations.py
    quality.py
    service.py
    profile_data/
      __init__.py
      m3-temporal-bindings-0.1.json

schemas/
  synchronization-report-0.1.0.schema.json

tests/
  contracts/test_synchronization.py
  synchronization/test_clock.py
  synchronization/test_models.py
  synchronization/test_profiles.py
  synchronization/test_bindings.py
  synchronization/test_annotations.py
  synchronization/test_reference.py
  synchronization/test_scene_gaze.py
  synchronization/test_quality.py
  synchronization/test_service.py
  synchronization/test_fingerprint.py
  e2e/test_m3_micro_bundle.py
  e2e/test_m3_format_sample_csv_local.py
  fixtures/synchronization_report_ready.json
~~~

## Dependency order and parallel boundary

Task 0 and Task 1 run first. After Task 2, Tasks 3–5 are independent and may run in parallel. Task 6 depends on Tasks 2–5 and establishes both immutable models and the fingerprint primitives required by orchestration. The remaining dependency chain is Task 6 → Task 7 → Tasks 8–9 → Task 10 → Task 11 → Task 12 replay hardening → Task 13 → Task 14.

### Task 0: Ratify M3 cross-document contracts

**Files:**
- Modify: `docs/product/DECISIONS.md`
- Modify: `docs/product/01_PRODUCT_OVERVIEW.md`
- Modify: `docs/product/02_ASSESSMENT_CORE_DESIGN.md`
- Modify: `docs/product/03_SESSION_BUNDLE_SPEC.md`
- Modify: `docs/product/07_RUNTIME_PROTOCOL_DESIGN.md`
- Modify: `docs/product/09_VALIDATION_AND_HANDOFF.md`
- Modify: `docs/product/10_DESIGN_SELF_REVIEW.md`
- Modify: `docs/product/11_IMPLEMENTATION_STATUS.md`
- Modify: `docs/product/GLOSSARY.md`
- Modify: `docs/product/README.md`
- Modify: `README.md`
- Modify: `docs/product/specs/2026-07-12-m3-native-time-synchronization-design.md`

- [ ] **Step 1: Run the decision/read-order check and observe RED**

~~~powershell
$decisionText = Get-Content -Raw -Encoding UTF8 docs/product/DECISIONS.md
foreach ($number in 16..20) {
  $id = 'D-{0:D3}' -f $number
  if ($decisionText -notmatch "(?ms)^## $([regex]::Escape($id))：.*?^- 状态：已接受\s*$") {
    Write-Error "$id is missing or not accepted"
  }
}
if ($Error.Count) { throw 'M3 decisions are not ratified' }
~~~

Expected: RED because D-016–D-020 are not yet in `DECISIONS.md`.

- [ ] **Step 2: Append the five accepted decisions**

Write full decision records with these exact semantics:

~~~markdown
## D-016：M3 只产生 native-rate aligned views

- 状态：已接受
- 决策：M3 只映射原生采样行并追加 aligned time/flags；不插值、不重采样、不建立 anchor-specific analysis/window grid。
- 理由：插值和窗口参数依赖 AnchorPlugin/model revision，提前全局冻结会制造未经专家批准的信号值。
- 影响：M3 报告 interpolated_rows=0；M4 按 anchor 定义建立 grid/window。

## D-017：Clock scale 是唯一映射权威

- 状态：已接受
- 决策：唯一公式为 round-half-even(source_s × scale × 1e9 + offset_ns)；drift_ppm 只与 scale 做一致性审计，不再次参与计算。同 clock_id 必须共享 method/scale/offset/drift mapping；per-stream residual 可以不同。
- 理由：同时施加 scale 和 drift 会重复校正并破坏可复现性。
- 影响：M3 对 scale/drift、residual 顺序、same-clock mapping 和 int64 overflow 执行结构门；task/anchor-specific residual tolerance 留给后续 gate。

## D-018：v0.1 session window 由 master-clock X 推导

- 状态：已接受
- 决策：v0.1 只支持 origin=session_start；window 为 [0,max(mapped X primary t_ns)]，source=master-clock-x-mapped-coverage-v1。
- 理由：manifest 0.1 没有独立 duration/end；X 仅是 v0.1 session-end 的技术时间边界来源，不是 commanded trajectory、任务标准或表现权威。
- 影响：synthetic duration_s 仅作 golden cross-check；未来显式 window 必须走新的 schema/decision。

## D-019：Annotation 与 reference 在 M3 分流

- 状态：已接受
- 决策：synthetic annotation 的 *_s 是 session-relative seconds；正式 session-time annotation 直接声明 t_ns。Bundle reference 在 M3 对齐；model-bundle reference 返回 deferred_model_bundle_resolution。
- 理由：annotation 没有 device clock，而 model reference 只有锁定 revision 后才能解析。
- 影响：M3 不猜 annotation clock/response semantics，也不把 deferred model reference 误报 missing。

## D-020：M3 使用独立 snapshot input 和 report

- 状态：已接受
- 决策：内部 SynchronizationInput 组合同一次 LoadedManifest、PreparedSession 和 IngestionReadinessReport；输出内部 AlignedSession 与公共 SynchronizationReport。
- 理由：PreparedSession 不应吸收 bundle I/O/clock/annotation 责任，M1 也不应重复 load/hash。
- 影响：SynchronizationReport 与 IngestionReadinessReport/RunPreflightReport 分离，始终 formal_run_authorized=false，并绑定 source/policy/catalog/alignment fingerprints。
~~~

- [ ] **Step 3: Reconcile the formal product documents**

Apply all of the following literal changes:

- `03` §§6–9/11: raw schemas require source time + stable ID; only `*-aligned-v0.1` adds authoritative ns fields; add D-017 formula, D-018 window, synthetic/canonical annotation split, model-reference deferred status, and `SynchronizationReport`.
- `02` §§3/4.1/6.1/9/10/13: add `SynchronizationInput`, `AlignedSession`, `SynchronizationReport`; state no M3 resampling; route readiness → alignment → model lock/reference resolution → Run Preflight; add synchronization fingerprint provenance.
- `09` header/§2.2/§2.4/§3: say M2 verified and M3 approved/planned; replace boundary interpolation with native mapping/half-even/window/duplicate/overflow tests; move interpolation/window testing to M4.
- `10` header/§5.3/§6: preserve the historical review date but remove claims that code, schemas, tests, or Git do not exist; record M1/M2 complete and M3 planned.
- `GLOSSARY`: define Native-rate alignment, Clock mapping, Session window, SynchronizationInput, AlignedStreamView, AlignedSession, and SynchronizationReport.
- Product/root READMEs: add M3 spec and this plan, say M2 verified/M3 planned, and keep synchronization unimplemented until later tasks finish.
- M3 spec §18: mark D-016–D-020 and the document coordination as ratified after these edits.

Do not label M3 implemented or verified in this task.

- [ ] **Step 4: Run the document acceptance gate**

~~~powershell
$required = @(
  @{ Path='docs/product/03_SESSION_BUNDLE_SPEC.md'; Pattern='master-clock-x-mapped-coverage-v1' },
  @{ Path='docs/product/03_SESSION_BUNDLE_SPEC.md'; Pattern='deferred_model_bundle_resolution' },
  @{ Path='docs/product/03_SESSION_BUNDLE_SPEC.md'; Pattern='SynchronizationReport' },
  @{ Path='docs/product/GLOSSARY.md'; Pattern='SynchronizationInput' },
  @{ Path='docs/product/GLOSSARY.md'; Pattern='AlignedSession' },
  @{ Path='docs/product/GLOSSARY.md'; Pattern='SynchronizationReport' },
  @{ Path='docs/product/11_IMPLEMENTATION_STATUS.md'; Pattern='采集格式样例' },
  @{ Path='docs/product/specs/2026-07-11-multimodal-synthetic-foundation-design.md'; Pattern='不得用其轨迹或操纵内容验证 anchor' },
  @{ Path='docs/product/specs/2026-07-12-m3-native-time-synchronization-design.md'; Pattern='task_validity=not_asserted' },
  @{ Path='docs/product/README.md'; Pattern='2026-07-12-m3-native-time-synchronization-design.md' },
  @{ Path='docs/product/README.md'; Pattern='2026-07-12-m3-native-time-synchronization-implementation-plan.md' }
)
foreach ($check in $required) {
  if (-not (Select-String -Quiet -LiteralPath $check.Path -Pattern $check.Pattern)) {
    throw "Missing $($check.Pattern) in $($check.Path)"
  }
}
$reviewedDocs = @(
  'README.md',
  'docs/product/02_ASSESSMENT_CORE_DESIGN.md',
  'docs/product/03_SESSION_BUNDLE_SPEC.md',
  'docs/product/07_RUNTIME_PROTOCOL_DESIGN.md',
  'docs/product/09_VALIDATION_AND_HANDOFF.md',
  'docs/product/10_DESIGN_SELF_REVIEW.md',
  'docs/product/11_IMPLEMENTATION_STATUS.md',
  'docs/product/GLOSSARY.md',
  'docs/product/README.md'
)
$stale = Select-String -LiteralPath $reviewedDocs -Pattern @(
  'Backend Foundation M1 verified',
  '当前后端 M1 为 in_progress',
  '尚无正式代码、schema 文件或自动化测试',
  '\.git 目录不可用',
  '边界插值',
  '建立统一 analysis/window grids',
  '至少包含 `source_timestamp`、`t_ns` 和 task profile',
  '至少包含各有效 control channel、`source_timestamp` 和 `t_ns`'
)
if ($stale) { $stale; throw 'Stale M1/M3 terminology remains' }
git diff --check
~~~

Expected: all checks exit 0.

- [ ] **Step 5: Commit**

~~~powershell
git add README.md docs/product
git commit -m "docs: ratify M3 synchronization contracts"
~~~

### Task 1: Make format-sample provenance explicit and fix exact gaze/frame assignment

**Files:**
- Modify: `src/pilot_assessment/synthetic/generator.py`
- Modify: `src/pilot_assessment/synthetic/modalities.py`
- Modify: `tests/synthetic/test_generator.py`
- Modify: `tests/synthetic/test_modalities.py`
- Modify: `tests/contracts/test_ingestion.py`
- Modify: `tests/fixtures/ingestion_readiness_ready.json`
- Move: `tests/e2e/test_real_csv_local.py` → `tests/e2e/test_format_sample_csv_local.py`

- [ ] **Step 1: Write the failing provenance-boundary test**

Extend the generator test with:

~~~python
source_extensions = manifest.source_session.extensions
assert source_extensions["source_artifact_role"] == "captured-format-sample-xu"
assert source_extensions["task_validity"] == "not_asserted"
assert source_extensions["ground_truth_status"] == "absent"
assert manifest.task.task_profile_id == "synthetic-interface-fixture-v0.1"
assert manifest.task.scenario_id == "synthetic-format-sample-01"
assert manifest.task.reference is not None
assert manifest.task.reference.reference_id == "synthetic-format-fixture-path-v0.1"
assert manifest.extensions["synthetic"]["provenance_scope"] == (
    "captured-format-sample-xu-plus-synthetic-modalities"
)
reference_metadata = manifest.streams["task_reference"].metadata
assert reference_metadata["reference_validity"] == "synthetic-format-fixture-only"
assert reference_metadata["trajectory_standard_status"] == "not_asserted"
~~~

Add a readiness-fixture drift regression using the existing `readiness_data` fixture:

~~~python
def test_ready_fixture_uses_actual_runtime_stream_schema_ids(
    readiness_data: dict[str, Any],
) -> None:
    expected = {
        "X": "flight-state-normalized-v0.1",
        "U": "control-input-normalized-v0.1",
        "I": "vr-scene-source-bundle-v0.1",
        "G": "gaze-source-bundle-v0.1",
        "EEG": "eeg-source-bundle-v0.1",
        "ECG": "ecg-source-bundle-v0.1",
        "pilot_camera": "pilot-camera-source-bundle-v0.1",
    }
    assert {
        modality: result["normalized_schema_id"]
        for modality, result in readiness_data["stream_results"].items()
    } == expected
    assert readiness_data["task_reference_result"]["normalized_schema_id"] == (
        "task-reference-normalized-v0.1"
    )
~~~

- [ ] **Step 2: Run provenance RED**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/synthetic/test_generator.py::test_generator_writes_a_complete_deterministic_bundle -v
~~~

Expected: FAIL on the old `real-simulator-xu`/task/reference wording.

- [ ] **Step 3: Implement unambiguous software-fixture provenance**

Update the generator docstring and manifest payload to use the exact values from Step 1. Also change `build_task_reference` documentation to state that source X values are copied only to exercise the reference schema/time path, not to define a commanded or acceptable trajectory. State that the internally named `control_activity` trace is only a `synthetic_control_driver` with no workload, control-quality, physiology, O13, or performance meaning. Set every row's `envelope_profile_id` to `synthetic-format-fixture-envelope-v0.1`.

Update the canonical readiness fixture provenance scope to `captured-format-sample-xu-plus-synthetic-modalities`. Also replace its five stale invented composite `*-normalized-v0.1` IDs with the actual runtime `NormalizedStream.schema_id` values asserted above. Do not change the source SHA-256, row values, clock truth, or `scientific_validation_status=not_supported`.

- [ ] **Step 4: Run provenance GREEN**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/synthetic/test_generator.py tests/contracts/test_ingestion.py -q
~~~

Expected: generator/ingestion provenance tests pass.

- [ ] **Step 5: Write the failing frame-boundary regression**

Add:

~~~python
def test_gaze_frame_binding_uses_exact_rate_indices_at_scene_boundaries() -> None:
    scene = build_scene(duration_s=29.01, seed=20260711)
    gaze = build_gaze(duration_s=29.01, seed=20260711, scene=scene)

    boundary = gaze.samples.filter(pl.col("gaze_sample_id") == 492).row(0, named=True)
    assert boundary["source_timestamp_s"] == 4.1
    assert boundary["scene_frame_id"] == 123

    expected = [
        min((sample_id * 30) // 120, scene.frame_index.height - 1)
        for sample_id in gaze.samples["gaze_sample_id"].to_list()
    ]
    assert gaze.samples["scene_frame_id"].to_list() == expected
~~~

- [ ] **Step 6: Run frame-boundary RED**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/synthetic/test_modalities.py::test_gaze_frame_binding_uses_exact_rate_indices_at_scene_boundaries -v
~~~

Expected: FAIL with `actual 122`, `expected 123`.

- [ ] **Step 7: Replace float multiplication with exact rate-index arithmetic**

In `build_gaze`, define integer rates and calculate IDs from the stable sample index:

~~~python
gaze_rate_hz = 120
scene_rate_hz = 30
times = source_grid(duration_s=duration_s, sample_rate_hz=float(gaze_rate_hz))
count = len(times)
last_frame_id = scene.frame_index.height - 1
frame_ids = [
    min((index * scene_rate_hz) // gaze_rate_hz, last_frame_id)
    for index in range(count)
]
~~~

Do not change sample counts, timestamps, PRNG coordinates, or §17 golden counts.

- [ ] **Step 8: Rename the opt-in M2 E2E around its actual role**

Move the test file and rename:

~~~python
FORMAT_SAMPLE_CSV_ENV = "PILOT_ASSESSMENT_FORMAT_SAMPLE_CSV"
EXPECTED_FORMAT_SAMPLE_CSV_SHA256 = (
    "19bf804253d841de9c9de299ac96e9e1b693b2dbfae2f3eaeac5d7dc044e4f52"
)


def test_format_sample_csv_generates_a_full_ready_bundle_without_source_mutation(
    tmp_path: Path,
) -> None:
    source = Path(os.environ[FORMAT_SAMPLE_CSV_ENV])
~~~

The skip reason must say `repository-external captured format-sample simulator CSV not configured`. Keep all byte/hash/row assertions; add no flight-performance assertion.

- [ ] **Step 9: Run GREEN and the synthetic/M2 suites**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/synthetic/test_modalities.py::test_gaze_frame_binding_uses_exact_rate_indices_at_scene_boundaries -v
& .\.tools\uv\uv.exe run pytest tests/synthetic tests/contracts/test_ingestion.py tests/e2e/test_m2_micro_bundle.py -q
~~~

Expected: the new regression and all synthetic tests pass.

- [ ] **Step 10: Commit**

~~~powershell
git add src/pilot_assessment/synthetic tests/synthetic tests/contracts/test_ingestion.py tests/fixtures/ingestion_readiness_ready.json tests/e2e/test_format_sample_csv_local.py
git add -u tests/e2e/test_real_csv_local.py
git commit -m "fix: label format sample and bind exact gaze frames"
~~~

### Task 2: Define the public synchronization contract and JSON Schema

**Files:**
- Create: `src/pilot_assessment/contracts/synchronization.py`
- Modify: `src/pilot_assessment/contracts/__init__.py`
- Modify: `src/pilot_assessment/schemas/export.py`
- Create: `tests/contracts/test_synchronization.py`
- Modify: `tests/schemas/test_schema_export.py`
- Create: `tests/fixtures/synchronization_report_ready.json`
- Create: `schemas/synchronization-report-0.1.0.schema.json`

- [ ] **Step 1: Write the first public-contract RED tests**

Create tests with these exact names:

~~~python
import json
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from pilot_assessment.contracts import (
    CORE_MODALITIES,
    SynchronizationDisposition,
    SynchronizationPolicy,
    SynchronizationReport,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "synchronization_report_ready.json"


def test_default_synchronization_policy_matches_v0_1() -> None:
    policy = SynchronizationPolicy()
    assert policy.contract_version == "0.1.0"
    assert policy.policy_id == "native-alignment-engineering-v0.1"
    assert policy.gap_detection_multiplier == 5.0
    assert policy.clock_consistency_tolerance_ppm == 0.000001


def ready_report_data() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(FIXTURE.read_text(encoding="utf-8")),
    )


def test_ready_synchronization_fixture_round_trips() -> None:
    payload = ready_report_data()
    report = SynchronizationReport.model_validate(payload)
    assert report.disposition is SynchronizationDisposition.READY
    assert report.can_continue_to_anchor_availability is True
    assert report.formal_run_authorized is False
    assert set(report.stream_results) == set(CORE_MODALITIES)


def test_report_requires_exact_seven_core_stream_result_keys() -> None:
    payload = ready_report_data()
    payload["stream_results"]["task_reference"] = payload["stream_results"]["X"]
    with pytest.raises(ValidationError):
        SynchronizationReport.model_validate(payload)
~~~

Also add separate negative tests for `ready + can_continue=false`, `blocked + can_continue=true`, non-blocked without window, deferred core status, task-reference mixed into core, aligned core/reference with non-present declaration or inconsistent clock, `formal_run_authorized=true`, and string-coerced JSON scalars.

- [ ] **Step 2: Run RED**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/contracts/test_synchronization.py -v
~~~

Expected: import failure because `contracts.synchronization` does not exist.

- [ ] **Step 3: Implement the strict public DTOs**

Freeze the following exact imports/types and public DTO fields. `SynchronizationPolicy` v0.1 uses literals so callers cannot silently change engineering parameters while retaining the same policy ID; a future tunable policy requires a new contract/policy revision.

~~~python
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, StrictBool, StringConstraints, model_validator

from pilot_assessment.contracts.common import (
    BundleRelativePath,
    FiniteFloat,
    Int64,
    NonNegativeFiniteFloat,
    NonNegativeInt,
    NonNegativeInt64,
    Sha256Digest,
    StableId,
    StrictContractModel,
    UnitInterval,
)
from pilot_assessment.contracts.errors import DomainErrorData
from pilot_assessment.contracts.ingestion import StreamReadiness, SyntheticSourceProvenance
from pilot_assessment.contracts.session import CORE_MODALITIES, StreamStatus

NonEmptyString = Annotated[str, StringConstraints(min_length=1, max_length=512)]
BLOCKING_SYNCHRONIZATION_ERROR_CODES = frozenset(
    {
        "SYNCHRONIZATION_INPUT_BLOCKED",
        "SOURCE_CHANGED_DURING_SYNCHRONIZATION",
        "SYNCHRONIZATION_INTERNAL_ERROR",
    }
)


class SynchronizationDisposition(StrEnum):
    READY = "ready"
    READY_PARTIAL = "ready_partial"
    BLOCKED = "blocked"


class SynchronizationItemStatus(StrEnum):
    ALIGNED = "aligned"
    NOT_ATTEMPTED = "not_attempted"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"
    NOT_APPLICABLE = "not_applicable"
    DEFERRED_MODEL_BUNDLE_RESOLUTION = "deferred_model_bundle_resolution"


class SessionWindow(StrictContractModel):
    start_t_ns: Literal[0] = 0
    end_t_ns: NonNegativeInt64
    source: Literal["master-clock-x-mapped-coverage-v1"]

    @model_validator(mode="after")
    def require_positive_end(self) -> Self:
        if self.end_t_ns <= 0:
            raise ValueError("session end must be positive")
        return self


class SynchronizationPolicy(StrictContractModel):
    contract_version: Literal["0.1.0"] = "0.1.0"
    policy_id: Literal["native-alignment-engineering-v0.1"] = (
        "native-alignment-engineering-v0.1"
    )
    gap_detection_multiplier: Literal[5.0] = 5.0
    clock_consistency_tolerance_ppm: Literal[0.000001] = 0.000001


class ClockMappingSummary(StrictContractModel):
    clock_id: StableId
    method: StableId
    scale: Annotated[float, Field(strict=True, gt=0.0, allow_inf_nan=False)]
    offset_ns: Int64
    drift_ppm: FiniteFloat
    residual_rms_ms: NonNegativeFiniteFloat
    residual_max_ms: NonNegativeFiniteFloat
    declaration_consistent: StrictBool


class SessionInterval(StrictContractModel):
    start_t_ns: NonNegativeInt64
    end_t_ns: NonNegativeInt64

    @model_validator(mode="after")
    def require_positive_interval(self) -> Self:
        if self.end_t_ns <= self.start_t_ns:
            raise ValueError("end_t_ns must be greater than start_t_ns")
        return self


class PhaseInterval(SessionInterval):
    phase_id: StableId
    label: NonEmptyString | None = None
    source: StableId | None = None
    confidence: UnitInterval | None = None
    extensions: dict[str, JsonValue] = Field(default_factory=dict)


class EventMarker(StrictContractModel):
    event_id: StableId
    event_type: StableId
    t_ns: NonNegativeInt64
    duration_ns: NonNegativeInt64 | None = None
    source: StableId | None = None
    confidence: UnitInterval | None = None
    response_mapping: dict[str, JsonValue] | None = None
    extensions: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_zero_duration(self) -> Self:
        if self.duration_ns is not None and self.duration_ns <= 0:
            raise ValueError("duration_ns must be positive when present")
        return self


class BaselineInterval(SessionInterval):
    interval_id: StableId
    condition: StableId | None = None
    valid: StrictBool | None = None
    exclusion_reason: NonEmptyString | None = None
    extensions: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_invalid_reason(self) -> Self:
        if self.valid is False and self.exclusion_reason is None:
            raise ValueError("invalid baseline requires exclusion_reason")
        return self
~~~

Use a discriminated metrics union so point/inherit and interval rows cannot populate mutually meaningless fields:

~~~python
class PointTemporalArtifactMetrics(StrictContractModel):
    artifact_role: StableId
    binding_mode: Literal["point", "inherit"]
    source_schema_id: StableId
    aligned_schema_id: StableId
    total_rows: NonNegativeInt
    in_session_rows: NonNegativeInt
    before_session_rows: NonNegativeInt
    after_session_rows: NonNegativeInt
    first_mapped_t_ns: Int64 | None = None
    last_mapped_t_ns: Int64 | None = None
    in_session_start_t_ns: NonNegativeInt64 | None = None
    in_session_end_t_ns: NonNegativeInt64 | None = None
    in_session_span_ns: NonNegativeInt64 | None = None
    session_span_ratio: UnitInterval | None = None
    duplicate_timestamp_groups: NonNegativeInt = 0
    duplicate_timestamp_rows: NonNegativeInt = 0
    median_period_ns: NonNegativeFiniteFloat | None = None
    gap_threshold_ns: NonNegativeInt64 | None = None
    gap_count: NonNegativeInt = 0
    max_gap_ns: NonNegativeInt64 | None = None
    interpolated_rows: Literal[0] = 0

    @model_validator(mode="after")
    def validate_point_metrics(self) -> Self:
        if self.in_session_rows + self.before_session_rows + self.after_session_rows != self.total_rows:
            raise ValueError("point row partitions must sum to total_rows")
        if not self.aligned_schema_id.endswith("-aligned-v0.1"):
            raise ValueError("aligned_schema_id must end with -aligned-v0.1")
        if self.duplicate_timestamp_rows > self.total_rows:
            raise ValueError("duplicate_timestamp_rows cannot exceed total_rows")
        if self.duplicate_timestamp_groups == 0 and self.duplicate_timestamp_rows != 0:
            raise ValueError("duplicate rows require duplicate groups")
        if self.duplicate_timestamp_groups > 0 and self.duplicate_timestamp_rows < 2 * self.duplicate_timestamp_groups:
            raise ValueError("each duplicate group must contain at least two rows")
        first, last = self.first_mapped_t_ns, self.last_mapped_t_ns
        if self.total_rows == 0 and (first is not None or last is not None):
            raise ValueError("empty artifacts cannot claim mapped bounds")
        if self.total_rows > 0 and (first is None or last is None or first > last):
            raise ValueError("non-empty artifacts require ordered mapped bounds")
        inner = (
            self.in_session_start_t_ns,
            self.in_session_end_t_ns,
            self.in_session_span_ns,
            self.session_span_ratio,
        )
        if self.in_session_rows == 0 and any(value is not None for value in inner):
            raise ValueError("no in-session rows means no in-session bounds")
        if self.in_session_rows > 0:
            if any(value is None for value in inner):
                raise ValueError("in-session rows require bounds, span, and ratio")
            start = self.in_session_start_t_ns
            end = self.in_session_end_t_ns
            span = self.in_session_span_ns
            assert start is not None and end is not None and span is not None
            if end < start or span != end - start:
                raise ValueError("in-session span must match ordered bounds")
        if self.median_period_ns is None:
            if self.gap_threshold_ns is not None or self.max_gap_ns is not None or self.gap_count:
                raise ValueError("gap statistics require a median period")
        elif self.gap_threshold_ns is None or self.max_gap_ns is None:
            raise ValueError("median period requires threshold and max gap")
        return self


class IntervalTemporalArtifactMetrics(StrictContractModel):
    artifact_role: StableId
    binding_mode: Literal["interval"]
    source_schema_id: StableId
    aligned_schema_id: StableId
    total_rows: NonNegativeInt
    before_session_rows: NonNegativeInt
    after_session_rows: NonNegativeInt
    overlapping_session_rows: NonNegativeInt
    fully_in_session_rows: NonNegativeInt
    first_start_t_ns: Int64 | None = None
    last_end_t_ns: Int64 | None = None
    interpolated_rows: Literal[0] = 0

    @model_validator(mode="after")
    def validate_interval_metrics(self) -> Self:
        if self.before_session_rows + self.after_session_rows + self.overlapping_session_rows != self.total_rows:
            raise ValueError("interval row partitions must sum to total_rows")
        if self.fully_in_session_rows > self.overlapping_session_rows:
            raise ValueError("fully in-session intervals must overlap the session")
        if not self.aligned_schema_id.endswith("-aligned-v0.1"):
            raise ValueError("aligned_schema_id must end with -aligned-v0.1")
        first, last = self.first_start_t_ns, self.last_end_t_ns
        if self.total_rows == 0 and (first is not None or last is not None):
            raise ValueError("empty interval artifacts cannot claim bounds")
        if self.total_rows > 0 and (first is None or last is None or first >= last):
            raise ValueError("non-empty interval artifacts require ordered bounds")
        return self


TemporalArtifactMetrics = Annotated[
    PointTemporalArtifactMetrics | IntervalTemporalArtifactMetrics,
    Field(discriminator="binding_mode"),
]


class SceneGazeMetrics(StrictContractModel):
    evaluated_in_session_gaze_rows: NonNegativeInt
    valid_association_rows: NonNegativeInt
    invalid_association_count: NonNegativeInt
    gaze_minus_frame_start_min_ns: NonNegativeInt64 | None = None
    gaze_minus_frame_start_max_ns: NonNegativeInt64 | None = None
    bounded_invalid_gaze_sample_ids: tuple[NonNegativeInt, ...] = ()

    @model_validator(mode="after")
    def validate_scene_gaze_metrics(self) -> Self:
        if self.valid_association_rows + self.invalid_association_count != self.evaluated_in_session_gaze_rows:
            raise ValueError("valid and invalid scene/gaze rows must partition evaluated rows")
        if len(self.bounded_invalid_gaze_sample_ids) > 10:
            raise ValueError("scene/gaze examples are bounded at ten IDs")
        bounds = (
            self.gaze_minus_frame_start_min_ns,
            self.gaze_minus_frame_start_max_ns,
        )
        if self.valid_association_rows == 0 and any(value is not None for value in bounds):
            raise ValueError("no valid associations means no delta bounds")
        if self.valid_association_rows > 0:
            low, high = bounds
            if low is None or high is None or low > high:
                raise ValueError("valid associations require ordered delta bounds")
        return self
~~~

Clock declaration validation, including `residual_max_ms >= residual_rms_ms`, remains in the clock kernel rather than the report DTO so an `invalid` result can faithfully report the received inconsistent declaration and its issue.

Define result/report DTOs exactly as follows:

~~~python
class StreamSynchronizationResult(StrictContractModel):
    modality: StableId
    declared_status: StreamStatus
    required_for_import: StrictBool
    input_readiness: StreamReadiness
    synchronization_status: SynchronizationItemStatus
    clock: ClockMappingSummary | None = None
    source_schema_id: StableId | None = None
    aligned_schema_id: StableId | None = None
    artifacts: dict[StableId, TemporalArtifactMetrics] = Field(default_factory=dict)
    scene_gaze_metrics: SceneGazeMetrics | None = None
    issues: tuple[DomainErrorData, ...] = ()

    @model_validator(mode="after")
    def validate_stream_result(self) -> Self:
        if self.synchronization_status is SynchronizationItemStatus.DEFERRED_MODEL_BUNDLE_RESOLUTION:
            raise ValueError("core stream cannot defer model-bundle resolution")
        if any(key != value.artifact_role for key, value in self.artifacts.items()):
            raise ValueError("artifact keys must match artifact_role")
        aligned = self.synchronization_status is SynchronizationItemStatus.ALIGNED
        if aligned:
            if (
                self.declared_status is not StreamStatus.PRESENT
                or self.input_readiness is not StreamReadiness.READY
            ):
                raise ValueError("aligned stream requires present/ready M2 input")
            if (
                self.clock is None
                or self.source_schema_id is None
                or self.aligned_schema_id is None
                or not self.artifacts
            ):
                raise ValueError("aligned stream requires clock, schemas, and artifacts")
            if not self.clock.declaration_consistent:
                raise ValueError("aligned stream requires a consistent clock declaration")
            if not self.aligned_schema_id.endswith("-aligned-v0.1"):
                raise ValueError("stream aligned_schema_id must end with -aligned-v0.1")
            if self.modality == "G" and self.scene_gaze_metrics is None:
                raise ValueError("aligned gaze requires scene/gaze relationship metrics")
            if self.modality != "G" and self.scene_gaze_metrics is not None:
                raise ValueError("scene/gaze metrics belong only to modality G")
        else:
            if self.aligned_schema_id is not None or self.artifacts:
                raise ValueError("non-aligned stream cannot claim aligned schema or artifacts")
            if self.scene_gaze_metrics is not None and (
                self.modality != "G"
                or self.synchronization_status is not SynchronizationItemStatus.INVALID
            ):
                raise ValueError("only invalid gaze may retain relationship diagnostics")
        return self


class TaskReferenceSynchronizationResult(StrictContractModel):
    reference_id: StableId
    source: Literal["bundle", "model_bundle"]
    declared_status: StreamStatus | None = None
    required_for_import: StrictBool | None = None
    input_readiness: StreamReadiness | None = None
    synchronization_status: SynchronizationItemStatus
    clock: ClockMappingSummary | None = None
    source_schema_id: StableId | None = None
    aligned_schema_id: StableId | None = None
    source_checksums: dict[BundleRelativePath, Sha256Digest] = Field(default_factory=dict)
    artifacts: dict[StableId, TemporalArtifactMetrics] = Field(default_factory=dict)
    issues: tuple[DomainErrorData, ...] = ()

    @model_validator(mode="after")
    def validate_reference_result(self) -> Self:
        if any(key != value.artifact_role for key, value in self.artifacts.items()):
            raise ValueError("reference artifact keys must match artifact_role")
        if self.source == "model_bundle":
            if self.synchronization_status is not SynchronizationItemStatus.DEFERRED_MODEL_BUNDLE_RESOLUTION:
                raise ValueError("model_bundle reference must be deferred in M3")
            claimed = (
                self.required_for_import,
                self.input_readiness,
                self.declared_status,
                self.clock,
                self.source_schema_id,
                self.aligned_schema_id,
            )
            if any(value is not None for value in claimed) or self.source_checksums or self.artifacts:
                raise ValueError("deferred model reference cannot claim bundle alignment")
            return self
        if self.synchronization_status is SynchronizationItemStatus.DEFERRED_MODEL_BUNDLE_RESOLUTION:
            raise ValueError("bundle reference cannot use deferred model status")
        if (
            self.required_for_import is None
            or self.input_readiness is None
            or self.declared_status is None
        ):
            raise ValueError("bundle reference requires declared/import/readiness state")
        aligned = self.synchronization_status is SynchronizationItemStatus.ALIGNED
        if aligned:
            if (
                self.declared_status is not StreamStatus.PRESENT
                or self.input_readiness is not StreamReadiness.READY
            ):
                raise ValueError("aligned bundle reference requires present/ready M2 input")
            if (
                self.clock is None
                or self.source_schema_id is None
                or self.aligned_schema_id is None
                or not self.source_checksums
                or not self.artifacts
            ):
                raise ValueError("aligned bundle reference requires complete alignment provenance")
            if not self.clock.declaration_consistent:
                raise ValueError("aligned bundle reference requires a consistent clock declaration")
            if not self.aligned_schema_id.endswith("-aligned-v0.1"):
                raise ValueError("reference aligned_schema_id must end with -aligned-v0.1")
        elif self.aligned_schema_id is not None or self.artifacts:
            raise ValueError("non-aligned bundle reference cannot claim aligned output")
        return self


class AnnotationSynchronizationResult(StrictContractModel):
    synchronization_status: SynchronizationItemStatus
    revision: StableId | None = None
    phase_schema_id: StableId | None = None
    event_schema_id: StableId | None = None
    baseline_schema_id: StableId | None = None
    phase_count: NonNegativeInt | None = None
    event_count: NonNegativeInt | None = None
    baseline_count: NonNegativeInt | None = None
    unannotated_intervals: tuple[SessionInterval, ...] = ()
    synthetic_semantics_unvalidated: StrictBool | None = None
    issues: tuple[DomainErrorData, ...] = ()

    @model_validator(mode="after")
    def validate_annotation_result(self) -> Self:
        allowed = {
            SynchronizationItemStatus.ALIGNED,
            SynchronizationItemStatus.NOT_ATTEMPTED,
            SynchronizationItemStatus.INVALID,
            SynchronizationItemStatus.UNSUPPORTED,
        }
        if self.synchronization_status not in allowed:
            raise ValueError("unsupported annotation synchronization status")
        content = (
            self.revision,
            self.phase_schema_id,
            self.event_schema_id,
            self.baseline_schema_id,
            self.phase_count,
            self.event_count,
            self.baseline_count,
            self.synthetic_semantics_unvalidated,
        )
        if self.synchronization_status is SynchronizationItemStatus.ALIGNED:
            if any(value is None for value in content):
                raise ValueError("aligned annotations require schemas, counts, and provenance")
        elif any(value is not None for value in content[4:]) or self.unannotated_intervals:
            raise ValueError("non-aligned annotations cannot claim aligned counts or intervals")
        return self


class SynchronizationReport(StrictContractModel):
    contract_version: Literal["0.1.0"]
    validation_scope: Literal["native_rate_session_time_alignment_v1"]
    session_id: StableId
    source_snapshot_fingerprint: Sha256Digest
    source_classification: StableId
    synthetic_provenance: SyntheticSourceProvenance | None
    policy: SynchronizationPolicy
    policy_fingerprint: Sha256Digest
    binding_catalog_fingerprint: Sha256Digest
    session_window: SessionWindow | None
    disposition: SynchronizationDisposition
    can_continue_to_anchor_availability: StrictBool
    formal_run_authorized: Literal[False]
    stream_results: dict[StableId, StreamSynchronizationResult]
    task_reference_result: TaskReferenceSynchronizationResult | None
    annotation_result: AnnotationSynchronizationResult | None
    global_issues: tuple[DomainErrorData, ...] = ()
    synchronization_fingerprint: Sha256Digest

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        synthetic = self.source_classification == "synthetic-test-data"
        if synthetic != (self.synthetic_provenance is not None):
            raise ValueError("synthetic classification and provenance must appear together")
        if set(self.stream_results) != set(CORE_MODALITIES):
            raise ValueError("synchronization report requires exactly seven core modalities")
        if any(key != result.modality for key, result in self.stream_results.items()):
            raise ValueError("stream result keys must match modality")
        required_core_failed = any(
            result.required_for_import
            and result.synchronization_status is not SynchronizationItemStatus.ALIGNED
            for result in self.stream_results.values()
        )
        optional_degraded = any(
            not result.required_for_import
            and result.synchronization_status
            in {
                SynchronizationItemStatus.NOT_ATTEMPTED,
                SynchronizationItemStatus.UNAVAILABLE,
                SynchronizationItemStatus.INVALID,
                SynchronizationItemStatus.UNSUPPORTED,
            }
            for result in self.stream_results.values()
        )
        annotation_failed = (
            self.annotation_result is None
            or self.annotation_result.synchronization_status
            is not SynchronizationItemStatus.ALIGNED
        )
        reference_blocked = False
        reference_degraded = False
        reference = self.task_reference_result
        if reference is not None and reference.source == "bundle":
            reference_aligned = reference.synchronization_status is SynchronizationItemStatus.ALIGNED
            reference_blocked = bool(reference.required_for_import) and not reference_aligned
            reference_degraded = (
                reference.required_for_import is False
                and not reference_aligned
                and reference.synchronization_status is not SynchronizationItemStatus.NOT_APPLICABLE
            )
        global_blocking = any(
            issue.error_code in BLOCKING_SYNCHRONIZATION_ERROR_CODES
            for issue in self.global_issues
        )
        blocked = (
            self.session_window is None
            or required_core_failed
            or annotation_failed
            or reference_blocked
            or global_blocking
        )
        expected = (
            SynchronizationDisposition.BLOCKED
            if blocked
            else SynchronizationDisposition.READY_PARTIAL
            if optional_degraded or reference_degraded
            else SynchronizationDisposition.READY
        )
        if self.disposition is not expected:
            raise ValueError("disposition must match synchronization item states")
        if self.can_continue_to_anchor_availability != (not blocked):
            raise ValueError("only non-blocked reports can continue")
        return self
~~~

Explicitly export the public names from both `contracts/synchronization.py::__all__` and `contracts/__init__.py`. A blocked report may retain a successfully derived `session_window`; an upstream M2-blocked report has `session_window=None`. A model-bundle reference is neutral while deferred. Required core/reference or annotation failure blocks; optional core/reference failure yields `ready_partial`.

In `tests/contracts/test_synchronization.py`, make the checked-in JSON fixture derive from one exact canonical builder. Use these helpers/specs; the `artifacts` tuple entries are `(role, mode, source_schema_id, aligned_schema_id)`:

~~~python
ArtifactFixtureSpec = tuple[str, str, str, str]
StreamFixtureSpec = tuple[str, str, bool, str, tuple[ArtifactFixtureSpec, ...]]

STREAM_FIXTURE_SPECS: dict[str, StreamFixtureSpec] = {
    "X": (
        "flight-state-normalized-v0.1",
        "flight-state-aligned-v0.1",
        True,
        "sim_clock",
        (("samples", "point", "flight-state-normalized-v0.1", "flight-state-aligned-v0.1"),),
    ),
    "U": (
        "control-input-normalized-v0.1",
        "control-input-aligned-v0.1",
        True,
        "sim_clock",
        (("samples", "point", "control-input-normalized-v0.1", "control-input-aligned-v0.1"),),
    ),
    "I": (
        "vr-scene-source-bundle-v0.1",
        "vr-scene-aligned-v0.1",
        False,
        "vr_scene_clock",
        (
            ("frame_index", "point", "vr-frame-index-raw-v0.1", "vr-frame-index-aligned-v0.1"),
            ("aoi_instances", "inherit", "vr-aoi-instance-raw-v0.1", "vr-aoi-instance-aligned-v0.1"),
        ),
    ),
    "G": (
        "gaze-source-bundle-v0.1",
        "gaze-aligned-v0.1",
        False,
        "gaze_clock",
        (
            ("gaze_samples", "point", "gaze-sample-raw-v0.1", "gaze-sample-aligned-v0.1"),
            ("fixations", "interval", "gaze-fixation-raw-v0.1", "gaze-fixation-aligned-v0.1"),
        ),
    ),
    "EEG": (
        "eeg-source-bundle-v0.1",
        "eeg-aligned-v0.1",
        False,
        "eeg_clock",
        (("samples", "point", "eeg-sample-raw-v0.1", "eeg-sample-aligned-v0.1"),),
    ),
    "ECG": (
        "ecg-source-bundle-v0.1",
        "ecg-aligned-v0.1",
        False,
        "ecg_clock",
        (
            ("samples", "point", "ecg-sample-raw-v0.1", "ecg-sample-aligned-v0.1"),
            ("r_peaks", "point", "ecg-r-peak-raw-v0.1", "ecg-r-peak-aligned-v0.1"),
        ),
    ),
    "pilot_camera": (
        "pilot-camera-source-bundle-v0.1",
        "pilot-camera-aligned-v0.1",
        False,
        "pilot_camera_clock",
        (("frame_index", "point", "pilot-camera-frame-index-raw-v0.1", "pilot-camera-frame-index-aligned-v0.1"),),
    ),
}


def _clock(clock_id: str) -> dict[str, Any]:
    return {
        "clock_id": clock_id,
        "method": "fixture-declared-v0.1",
        "scale": 1.0,
        "offset_ns": 0,
        "drift_ppm": 0.0,
        "residual_rms_ms": 0.0,
        "residual_max_ms": 0.0,
        "declaration_consistent": True,
    }


def _point(role: str, mode: str, source: str, aligned: str) -> dict[str, Any]:
    return {
        "artifact_role": role,
        "binding_mode": mode,
        "source_schema_id": source,
        "aligned_schema_id": aligned,
        "total_rows": 1,
        "in_session_rows": 1,
        "before_session_rows": 0,
        "after_session_rows": 0,
        "first_mapped_t_ns": 0,
        "last_mapped_t_ns": 0,
        "in_session_start_t_ns": 0,
        "in_session_end_t_ns": 0,
        "in_session_span_ns": 0,
        "session_span_ratio": 0.0,
        "duplicate_timestamp_groups": 0,
        "duplicate_timestamp_rows": 0,
        "median_period_ns": None,
        "gap_threshold_ns": None,
        "gap_count": 0,
        "max_gap_ns": None,
        "interpolated_rows": 0,
    }


def _interval(role: str, source: str, aligned: str) -> dict[str, Any]:
    return {
        "artifact_role": role,
        "binding_mode": "interval",
        "source_schema_id": source,
        "aligned_schema_id": aligned,
        "total_rows": 1,
        "before_session_rows": 0,
        "after_session_rows": 0,
        "overlapping_session_rows": 1,
        "fully_in_session_rows": 1,
        "first_start_t_ns": 0,
        "last_end_t_ns": 1_000_000_000,
        "interpolated_rows": 0,
    }


def _stream(modality: str) -> dict[str, Any]:
    source, aligned, required, clock_id, artifact_specs = STREAM_FIXTURE_SPECS[modality]
    artifacts = {
        role: (
            _interval(role, artifact_source, artifact_aligned)
            if mode == "interval"
            else _point(role, mode, artifact_source, artifact_aligned)
        )
        for role, mode, artifact_source, artifact_aligned in artifact_specs
    }
    result: dict[str, Any] = {
        "modality": modality,
        "declared_status": "present",
        "required_for_import": required,
        "input_readiness": "ready",
        "synchronization_status": "aligned",
        "clock": _clock(clock_id),
        "source_schema_id": source,
        "aligned_schema_id": aligned,
        "artifacts": artifacts,
        "issues": [],
    }
    if modality == "G":
        result["scene_gaze_metrics"] = {
            "evaluated_in_session_gaze_rows": 1,
            "valid_association_rows": 1,
            "invalid_association_count": 0,
            "gaze_minus_frame_start_min_ns": 0,
            "gaze_minus_frame_start_max_ns": 0,
            "bounded_invalid_gaze_sample_ids": [],
        }
    return result
~~~

The complete top-level builder is:

~~~python
def ready_fixture_data() -> dict[str, Any]:
    return {
        "contract_version": "0.1.0",
        "validation_scope": "native_rate_session_time_alignment_v1",
        "session_id": "synthetic-session-20260711-001",
        "source_snapshot_fingerprint": "1" * 64,
        "source_classification": "synthetic-test-data",
        "synthetic_provenance": {
            "generator_id": "synthetic-multimodal-generator-v0.1",
            "seed": 20260711,
            "scientific_validation_status": "not_supported",
            "source_xu_sha256": "a" * 64,
            "lock_fingerprint": "b" * 64,
            "provenance_scope": "captured-format-sample-xu-plus-synthetic-modalities",
            "formal_assessment_supported": False,
        },
        "policy": {
            "contract_version": "0.1.0",
            "policy_id": "native-alignment-engineering-v0.1",
            "gap_detection_multiplier": 5.0,
            "clock_consistency_tolerance_ppm": 0.000001,
        },
        "policy_fingerprint": "2" * 64,
        "binding_catalog_fingerprint": "3" * 64,
        "session_window": {
            "start_t_ns": 0,
            "end_t_ns": 2_000_000_000,
            "source": "master-clock-x-mapped-coverage-v1",
        },
        "disposition": "ready",
        "can_continue_to_anchor_availability": True,
        "formal_run_authorized": False,
        "stream_results": {modality: _stream(modality) for modality in sorted(CORE_MODALITIES)},
        "task_reference_result": {
            "reference_id": "synthetic-format-fixture-path-v0.1",
            "source": "bundle",
            "declared_status": "present",
            "required_for_import": True,
            "input_readiness": "ready",
            "synchronization_status": "aligned",
            "clock": _clock("sim_clock"),
            "source_schema_id": "task-reference-normalized-v0.1",
            "aligned_schema_id": "task-reference-path-aligned-v0.1",
            "source_checksums": {"references/commanded_path.parquet": "c" * 64},
            "artifacts": {
                "commanded_path": _point(
                    "commanded_path",
                    "point",
                    "task-reference-path-raw-v0.1",
                    "task-reference-path-aligned-v0.1",
                )
            },
            "issues": [],
        },
        "annotation_result": {
            "synchronization_status": "aligned",
            "revision": "synthetic-unvalidated-v0.1",
            "phase_schema_id": "phases-synthetic-v0.1",
            "event_schema_id": "events-synthetic-v0.1",
            "baseline_schema_id": "baseline-intervals-synthetic-v0.1",
            "phase_count": 3,
            "event_count": 2,
            "baseline_count": 1,
            "unannotated_intervals": [],
            "synthetic_semantics_unvalidated": True,
            "issues": [],
        },
        "global_issues": [],
        "synchronization_fingerprint": "4" * 64,
    }


def test_ready_fixture_matches_canonical_builder() -> None:
    assert ready_report_data() == ready_fixture_data()
    SynchronizationReport.model_validate(ready_report_data())
~~~

Create `tests/fixtures/synchronization_report_ready.json` with `apply_patch` so its decoded value exactly equals `ready_fixture_data()`; the bidirectional test is the drift guard. The task-reference stream/artifact aligned schema is deliberately the single approved `task-reference-path-aligned-v0.1`, not a newly invented `task-reference-aligned-v0.1`.

- [ ] **Step 4: Run contract GREEN**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/contracts/test_synchronization.py -v
~~~

Expected: all synchronization contract tests pass.

- [ ] **Step 5: Add exporter/schema parity and observe RED**

Update schema tests to expect exactly four files and add:

~~~python
def test_synchronization_report_schema_matches_checked_in_artifact() -> None:
    rendered = render_schemas()["synchronization-report-0.1.0.schema.json"]
    checked_in = PROJECT_ROOT / "schemas" / "synchronization-report-0.1.0.schema.json"
    assert rendered == checked_in.read_bytes()
~~~

Add acceptance-matrix cases for dispositions, exact core keys, deferred core, formal authorization, and strict scalar types. Run the test and observe RED because the exporter has no fourth schema.

- [ ] **Step 6: Export the fourth public schema and run GREEN**

Add schema ID/title constants and a `_synchronization_report_schema()` builder. Pydantic model validators are not automatically represented in JSON Schema, so manually encode these five groups with Draft 2020-12 `properties/required/additionalProperties:false` plus `allOf` `if/then/else` clauses:

1. `stream_results` has exactly the seven named properties, each required, no additional properties; each property fixes its own `modality` constant and prohibits deferred status;
2. `synchronization_status=aligned` requires present declaration, ready input, consistent clock, aligned `-aligned-v0.1` schema, and non-empty artifacts (plus G scene/gaze metrics); every non-aligned status forbids aligned schema/artifacts, while only `modality=G,status=invalid` may retain scene/gaze diagnostic metrics;
3. `source_classification=synthetic-test-data` requires non-null synthetic provenance, while every other classification requires `synthetic_provenance=null`;
4. `disposition=blocked` requires continuation false; non-blocked requires non-null window and continuation true; `formal_run_authorized` is always false;
5. required core/bundle-reference, non-aligned annotation, or a global `SYNCHRONIZATION_INPUT_BLOCKED`/`SOURCE_CHANGED_DURING_SYNCHRONIZATION`/`SYNCHRONIZATION_INTERNAL_ERROR` forces blocked; optional core/reference degradation forces `ready_partial`; model-bundle deferred is permitted and neutral.

Add paired Pydantic/JSON-Schema tests named `test_schema_and_pydantic_agree_on_exact_core_inventory`, `..._aligned_payload_invariants`, `..._synthetic_provenance_coupling`, `..._window_and_continuation`, and `..._reference_annotation_disposition`. Each test feeds at least one valid and one invalid mutation to both validators; include ready+annotation-invalid, ready+required-reference-invalid, ready+model-reference-deferred, partial+optional-reference-invalid, and ready+blocking-global-error cases. Add the file to `render_schemas()`, run:

~~~powershell
& .\.tools\uv\uv.exe run python -m pilot_assessment.schemas.export
& .\.tools\uv\uv.exe run pytest tests/contracts/test_synchronization.py tests/schemas/test_schema_export.py -v
~~~

Expected: committed schema parity and Pydantic/JSON-Schema acceptance matrix pass; session-manifest schema bytes remain unchanged.

- [ ] **Step 7: Commit**

~~~powershell
git add src/pilot_assessment/contracts src/pilot_assessment/schemas tests/contracts/test_synchronization.py tests/schemas/test_schema_export.py tests/fixtures/synchronization_report_ready.json schemas
git commit -m "feat: define synchronization report contract"
~~~

### Task 3: Preserve one loaded M1/M2 snapshot for M3

**Files:**
- Modify: `src/pilot_assessment/ingestion/readiness.py`
- Modify: `src/pilot_assessment/ingestion/__init__.py`
- Modify: `tests/ingestion/test_readiness.py`

- [ ] **Step 1: Write the loaded-snapshot seam RED tests**

Add tests that load once, call the new `inspect_loaded_ingestion_readiness` API, and assert the fingerprint:

~~~python
def test_loaded_readiness_reuses_the_exact_m1_snapshot(tmp_path: Path) -> None:
    ready_bundle = _full_bundle(tmp_path)
    loaded = ManifestLoader().load(ready_bundle)
    outcome = inspect_loaded_ingestion_readiness(loaded)
    assert outcome.report.source_snapshot_fingerprint == source_snapshot_fingerprint(loaded)
    assert outcome.prepared_session is not None
~~~

Add a monkeypatch count test proving `inspect_ingestion_readiness(path)` invokes `ManifestLoader.load` exactly once.

- [ ] **Step 2: Run RED**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/ingestion/test_readiness.py -v
~~~

Expected: import failure for `inspect_loaded_ingestion_readiness` and `source_snapshot_fingerprint`.

- [ ] **Step 3: Extract the loaded entry without changing M2 behavior**

Use these signatures:

~~~python
def source_snapshot_fingerprint(loaded: LoadedManifest) -> str:
    return _source_fingerprint(loaded)


def inspect_loaded_ingestion_readiness(
    loaded: LoadedManifest,
    *,
    registry: AdapterRegistry | None = None,
) -> IngestionReadinessOutcome:
    return _inspect_loaded_ingestion_readiness(loaded, registry=registry)


def inspect_ingestion_readiness(
    bundle_root: str | Path,
    *,
    loader: ManifestLoader | None = None,
    registry: AdapterRegistry | None = None,
) -> IngestionReadinessOutcome:
    loaded = (loader or ManifestLoader()).load(bundle_root)
    return inspect_loaded_ingestion_readiness(loaded, registry=registry)
~~~

Move the current body after `ManifestLoader().load` into the loaded function. Keep report bytes, issue ordering, adapter dispatch, and old public imports source-compatible.

- [ ] **Step 4: Run GREEN and full M2 regression**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/ingestion/test_readiness.py tests/e2e/test_m2_micro_bundle.py -v
~~~

Expected: new seam and all existing M2 behavior pass.

- [ ] **Step 5: Commit**

~~~powershell
git add src/pilot_assessment/ingestion tests/ingestion/test_readiness.py
git commit -m "refactor: expose loaded ingestion snapshot"
~~~

### Task 4: Add the versioned temporal-binding catalog

**Files:**
- Create: `src/pilot_assessment/synchronization/__init__.py`
- Create: `src/pilot_assessment/synchronization/profile_data/__init__.py`
- Create: `src/pilot_assessment/synchronization/profile_data/m3-temporal-bindings-0.1.json`
- Create: `src/pilot_assessment/synchronization/profiles.py`
- Create: `tests/synchronization/test_profiles.py`
- Modify: `tests/test_package_metadata.py`

- [ ] **Step 1: Write catalog/resource RED tests**

Create tests named:

~~~python
def test_builtin_temporal_catalog_covers_every_m2_artifact_role() -> None:
    catalog = load_builtin_temporal_catalog()
    assert set(catalog.streams_by_schema) == {
        "flight-state-normalized-v0.1",
        "control-input-normalized-v0.1",
        "vr-scene-source-bundle-v0.1",
        "gaze-source-bundle-v0.1",
        "eeg-source-bundle-v0.1",
        "ecg-source-bundle-v0.1",
        "pilot-camera-source-bundle-v0.1",
        "task-reference-normalized-v0.1",
    }


def test_task_reference_binding_uses_commanded_path_role_from_m2() -> None:
    profile = load_builtin_temporal_catalog().streams_by_schema[
        "task-reference-normalized-v0.1"
    ]
    assert profile.bindings_by_role["commanded_path"].expected_artifact_schema_id == (
        "task-reference-path-raw-v0.1"
    )
~~~

Also add `test_temporal_catalog_matches_m2_profile_artifact_roles`. It loads `load_builtin_profiles()` and compares every catalog `expected_artifact_schema_id` to the packaged M2 authority: five `CompositeProfile.artifact_roles` role-by-role; X/U against their runtime normalized schema IDs; task reference against the packaged `task-reference-path-raw-v0.1` `TableProfile`. Then test duplicate schema/role rejection, no heuristic fallback, only `-aligned-v0.1` output IDs, stable catalog fingerprint, and installed-resource presence.

- [ ] **Step 2: Run RED**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/synchronization/test_profiles.py tests/test_package_metadata.py -v
~~~

Expected: import/resource failure because the synchronization package/catalog does not exist.

- [ ] **Step 3: Implement strict profile DTOs and loader**

Define the binding DTOs and read-only lookup properties exactly:

~~~python
from collections.abc import Mapping
from types import MappingProxyType
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator


class PointBinding(StrictContractModel):
    mode: Literal["point"]
    artifact_role: StableId
    expected_artifact_schema_id: StableId
    aligned_artifact_schema_id: StableId
    source_timestamp_column: StableId
    target_timestamp_column: Literal["t_ns"] = "t_ns"
    in_session_column: Literal["in_session"] = "in_session"
    stable_keys: tuple[StableId, ...]

    @model_validator(mode="after")
    def validate_point(self) -> Self:
        if not self.stable_keys or len(self.stable_keys) != len(set(self.stable_keys)):
            raise ValueError("point stable_keys must be non-empty and unique")
        if not self.aligned_artifact_schema_id.endswith("-aligned-v0.1"):
            raise ValueError("point aligned schema must end with -aligned-v0.1")
        return self


class IntervalBinding(StrictContractModel):
    mode: Literal["interval"]
    artifact_role: StableId
    expected_artifact_schema_id: StableId
    aligned_artifact_schema_id: StableId
    source_start_column: StableId
    source_end_column: StableId
    target_start_column: Literal["start_t_ns"] = "start_t_ns"
    target_end_column: Literal["end_t_ns"] = "end_t_ns"
    overlaps_session_column: Literal["overlaps_session"] = "overlaps_session"
    fully_in_session_column: Literal["fully_in_session"] = "fully_in_session"
    stable_keys: tuple[StableId, ...]

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        if not self.stable_keys or len(self.stable_keys) != len(set(self.stable_keys)):
            raise ValueError("interval stable_keys must be non-empty and unique")
        if not self.aligned_artifact_schema_id.endswith("-aligned-v0.1"):
            raise ValueError("interval aligned schema must end with -aligned-v0.1")
        return self


class InheritBinding(StrictContractModel):
    mode: Literal["inherit"]
    artifact_role: StableId
    expected_artifact_schema_id: StableId
    aligned_artifact_schema_id: StableId
    parent_role: StableId
    parent_key_columns: tuple[StableId, ...]
    foreign_key_columns: tuple[StableId, ...]
    target_timestamp_column: Literal["t_ns"] = "t_ns"
    in_session_column: Literal["in_session"] = "in_session"
    stable_keys: tuple[StableId, ...]

    @model_validator(mode="after")
    def validate_inherit(self) -> Self:
        if (
            not self.stable_keys
            or not self.parent_key_columns
            or len(self.parent_key_columns) != len(self.foreign_key_columns)
            or len(self.stable_keys) != len(set(self.stable_keys))
        ):
            raise ValueError("inherit keys must be non-empty, unique, and paired")
        if not self.aligned_artifact_schema_id.endswith("-aligned-v0.1"):
            raise ValueError("inherit aligned schema must end with -aligned-v0.1")
        return self


class UntimedBinding(StrictContractModel):
    mode: Literal["untimed"]
    artifact_role: StableId
    expected_artifact_schema_id: StableId


TemporalBinding = Annotated[
    PointBinding | IntervalBinding | InheritBinding | UntimedBinding,
    Field(discriminator="mode"),
]


class TemporalStreamProfile(StrictContractModel):
    stream_schema_id: StableId
    aligned_stream_schema_id: StableId
    bindings: tuple[TemporalBinding, ...]

    @model_validator(mode="after")
    def validate_profile(self) -> Self:
        roles = [binding.artifact_role for binding in self.bindings]
        if not roles or len(roles) != len(set(roles)):
            raise ValueError("stream binding roles must be non-empty and unique")
        if not self.aligned_stream_schema_id.endswith("-aligned-v0.1"):
            raise ValueError("aligned stream schema must end with -aligned-v0.1")
        return self

    @property
    def bindings_by_role(self) -> Mapping[str, TemporalBinding]:
        return MappingProxyType({binding.artifact_role: binding for binding in self.bindings})


class TemporalBindingCatalog(StrictContractModel):
    catalog_version: Literal["0.1.0"]
    streams: tuple[TemporalStreamProfile, ...]

    @model_validator(mode="after")
    def validate_catalog(self) -> Self:
        schema_ids = [profile.stream_schema_id for profile in self.streams]
        if not schema_ids or len(schema_ids) != len(set(schema_ids)):
            raise ValueError("catalog stream schema IDs must be non-empty and unique")
        return self

    @property
    def streams_by_schema(self) -> Mapping[str, TemporalStreamProfile]:
        return MappingProxyType({profile.stream_schema_id: profile for profile in self.streams})
~~~

The loader must expose `load_builtin_temporal_catalog() -> TemporalBindingCatalog` and `builtin_temporal_catalog_fingerprint() -> str`, use `importlib.resources.files`, strict UTF-8 JSON, duplicate-key/NaN rejection, immutable lookups, and SHA-256 over the exact packaged bytes. On first load it cross-validates the catalog against `load_builtin_profiles()` using the same rules as `test_temporal_catalog_matches_m2_profile_artifact_roles`; a mismatch is a packaged configuration error, not an observed DataFrame schema. Service trusts only this cross-validated built-in catalog. Unknown schema/role returns `TEMPORAL_BINDING_NOT_FOUND`; there is no heuristic fallback. The parent `synchronization/__init__.py` is created here and initially exports only the catalog DTO/loader/fingerprint API so the Task 4 wheel import is valid; later tasks extend the same public module.

- [ ] **Step 4: Write the complete catalog**

Declare 11 timed roles and three untimed roles. Freeze stream-level aligned IDs as `flight-state-aligned-v0.1`, `control-input-aligned-v0.1`, `vr-scene-aligned-v0.1`, `gaze-aligned-v0.1`, `eeg-aligned-v0.1`, `ecg-aligned-v0.1`, `pilot-camera-aligned-v0.1`, and (because it is a single-table stream) `task-reference-path-aligned-v0.1`:

| Runtime stream schema | Role | Mode | Source artifact → aligned artifact | Stable/foreign key |
|---|---|---|---|---|
| `flight-state-normalized-v0.1` | samples | point | `flight-state-normalized-v0.1` → `flight-state-aligned-v0.1` | source_row_index |
| `control-input-normalized-v0.1` | samples | point | `control-input-normalized-v0.1` → `control-input-aligned-v0.1` | source_row_index |
| `vr-scene-source-bundle-v0.1` | frame_index | point | `vr-frame-index-raw-v0.1` → `vr-frame-index-aligned-v0.1` | frame_id |
| `vr-scene-source-bundle-v0.1` | aoi_instances | inherit | `vr-aoi-instance-raw-v0.1` → `vr-aoi-instance-aligned-v0.1` | frame_id → frame_index.frame_id |
| `gaze-source-bundle-v0.1` | gaze_samples | point | `gaze-sample-raw-v0.1` → `gaze-sample-aligned-v0.1` | gaze_sample_id |
| `gaze-source-bundle-v0.1` | fixations | interval | `gaze-fixation-raw-v0.1` → `gaze-fixation-aligned-v0.1` | fixation_id |
| `eeg-source-bundle-v0.1` | samples | point | `eeg-sample-raw-v0.1` → `eeg-sample-aligned-v0.1` | sample_index |
| `ecg-source-bundle-v0.1` | samples | point | `ecg-sample-raw-v0.1` → `ecg-sample-aligned-v0.1` | sample_index |
| `ecg-source-bundle-v0.1` | r_peaks | point | `ecg-r-peak-raw-v0.1` → `ecg-r-peak-aligned-v0.1` | peak_id |
| `pilot-camera-source-bundle-v0.1` | frame_index | point | `pilot-camera-frame-index-raw-v0.1` → `pilot-camera-frame-index-aligned-v0.1` | frame_id |
| `task-reference-normalized-v0.1` | commanded_path | point | `task-reference-path-raw-v0.1` → `task-reference-path-aligned-v0.1` | reference_sample_id |

Untimed bindings are scene `frame_images/png-rgb8-v0.1`, EEG `sidecar/eeg-sidecar-v0.1`, and camera `frame_images/png-rgb8-v0.1`; preserve their existing schema/content and never assign an aligned artifact schema ID.

Every point binding uses `source_time_s` only for X/U and `source_timestamp_s` for all other point roles, appending `t_ns/in_session`. The fixation interval uses `start_source_timestamp_s/end_source_timestamp_s` and appends `start_t_ns/end_t_ns/overlaps_session/fully_in_session`. AOI inherit uses `parent_role=frame_index`, `parent_key_columns=("frame_id",)`, `foreign_key_columns=("frame_id",)`, and `stable_keys=("frame_id","aoi_id")`; all other stable keys are exactly those in the final table column.

- [ ] **Step 5: Run GREEN and wheel-resource smoke**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/synchronization/test_profiles.py tests/test_package_metadata.py -v
& .\.tools\uv\uv.exe build
$wheel=(Get-ChildItem dist -Filter '*.whl' | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
& .\.tools\uv\uv.exe run --isolated --no-project --with $wheel python -c "from pilot_assessment.synchronization.profiles import load_builtin_temporal_catalog; assert len(load_builtin_temporal_catalog().streams) == 8"
~~~

Expected: source tests and isolated wheel resource load pass.

- [ ] **Step 6: Commit**

~~~powershell
git add src/pilot_assessment/synchronization tests/synchronization/test_profiles.py tests/test_package_metadata.py
git commit -m "feat: add M3 temporal binding catalog"
~~~

### Task 5: Implement the Decimal clock kernel

**Files:**
- Create: `src/pilot_assessment/synchronization/clock.py`
- Create: `tests/synchronization/test_clock.py`
- Modify: `src/pilot_assessment/synthetic/timelines.py`
- Modify: `tests/synthetic/test_timelines.py`

- [ ] **Step 1: Write scalar round/mapping RED tests**

Add tests for positive/negative half-even ties, exact signed-int64 boundaries, both overflows, scale applied once, and Decimal string semantics:

~~~python
def test_clock_mapping_uses_scale_exactly_once() -> None:
    assert map_source_seconds_to_session_ns(
        10.0,
        scale=1.00002,
        offset_ns=0,
    ) == 10_000_200_000


def test_clock_mapping_uses_decimal_string_semantics() -> None:
    assert map_source_seconds_to_session_ns(
        29.008333333333333,
        scale=1.00002,
        offset_ns=7_000_000,
    ) == 29_015_913_500
~~~

Test `round_decimal_ns(Decimal("0.5")) == 0`, `1.5→2`, `2.5→2`, `-0.5→0`, `-1.5→-2`, `-2.5→-2`.

- [ ] **Step 2: Run RED**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/synchronization/test_clock.py -v
~~~

Expected: import failure because the clock kernel does not exist.

- [ ] **Step 3: Implement the sole scalar mapper**

Use only Decimal string semantics:

~~~python
_BILLION = Decimal(1_000_000_000)
_MILLION = Decimal(1_000_000)
_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1


def round_decimal_ns(value: Decimal) -> int:
    result = int(value.to_integral_value(rounding=ROUND_HALF_EVEN))
    if not _INT64_MIN <= result <= _INT64_MAX:
        raise ValueError("TIMESTAMP_OUT_OF_INT64_RANGE")
    return result


def map_source_seconds_to_session_ns(
    source_time_s: float,
    *,
    scale: float,
    offset_ns: int,
) -> int:
    if isinstance(source_time_s, bool) or not math.isfinite(source_time_s):
        raise ValueError("source timestamp must be finite")
    if isinstance(scale, bool) or not math.isfinite(scale) or scale <= 0:
        raise ValueError("clock scale must be positive and finite")
    if isinstance(offset_ns, bool) or not _INT64_MIN <= offset_ns <= _INT64_MAX:
        raise ValueError("offset_ns must be signed int64")
    mapped = Decimal(str(source_time_s)) * Decimal(str(scale)) * _BILLION
    return round_decimal_ns(mapped + Decimal(offset_ns))
~~~

Add `session_seconds_to_ns` as scale=1/offset=0. Make `synthetic.timelines.map_source_seconds_to_session_ns` a compatibility wrapper that derives scale once from drift and calls this kernel; do not maintain a second rounding implementation.

- [ ] **Step 4: Add clock-declaration RED tests**

Test exact tolerance acceptance, over-tolerance rejection, residual max below RMS, same-clock mapping mismatch, and same-clock different residual acceptance.

- [ ] **Step 5: Implement declaration/inventory validation**

`validate_clock_declaration(clock, policy)` must compare:

~~~python
declared = Decimal(str(clock.drift_ppm))
derived = (Decimal(str(clock.scale)) - Decimal(1)) * _MILLION
tolerance = Decimal(str(policy.clock_consistency_tolerance_ppm))
if abs(declared - derived) > tolerance:
    raise ValueError("CLOCK_DECLARATION_INCONSISTENT")
if clock.residual_max_ms < clock.residual_rms_ms:
    raise ValueError("CLOCK_DECLARATION_INCONSISTENT")
~~~

`validate_same_clock_mappings` groups ready descriptors by `clock_id` and compares method/scale/offset/drift only; residual values may differ.

- [ ] **Step 6: Run GREEN and commit**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/synchronization/test_clock.py tests/synthetic/test_timelines.py -v
git add src/pilot_assessment/synchronization/clock.py src/pilot_assessment/synthetic/timelines.py tests/synchronization/test_clock.py tests/synthetic/test_timelines.py
git commit -m "feat: add deterministic session clock mapping"
~~~

### Task 6: Define immutable synchronization inputs, aligned models, and fingerprint primitives

**Files:**
- Create: `src/pilot_assessment/synchronization/models.py`
- Create: `src/pilot_assessment/synchronization/fingerprint.py`
- Modify: `src/pilot_assessment/synchronization/__init__.py`
- Create: `tests/synchronization/test_models.py`
- Create: `tests/synchronization/test_fingerprint.py`

- [ ] **Step 1: Write internal-model RED tests**

Add tests named:

- `test_synchronization_input_rejects_blocked_readiness`
- `test_synchronization_input_rejects_snapshot_fingerprint_mismatch`
- `test_synchronization_input_rejects_ready_inventory_mismatch`
- `test_aligned_stream_view_freezes_all_mappings`
- `test_aligned_session_keeps_task_reference_outside_core_streams`
- `test_hash_part_uses_unambiguous_tag_and_length_framing`
- `test_policy_fingerprint_is_canonical_and_replay_stable`
- `test_catalog_fingerprint_matches_packaged_resource_bytes`

Use production `ManifestLoader`/M2 outcomes for input tests and small Polars tables for immutability.

- [ ] **Step 2: Run RED**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/synchronization/test_models.py tests/synchronization/test_fingerprint.py -v
~~~

Expected: import failure because models/fingerprint primitives do not exist.

- [ ] **Step 3: Implement exact frozen dataclasses**

~~~python
@dataclass(frozen=True, slots=True)
class SynchronizationInput:
    loaded_manifest: LoadedManifest
    readiness_report: IngestionReadinessReport
    prepared_session: PreparedSession


@dataclass(frozen=True, slots=True)
class AlignedStreamView:
    modality: str
    source_schema_id: str
    aligned_schema_id: str
    clock_id: str
    tables: Mapping[str, pl.DataFrame]
    json_artifacts: Mapping[str, Mapping[str, JsonValue]]
    file_artifacts: Mapping[str, tuple[str, ...]]
    source_checksums: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class AlignedAnnotations:
    revision: str
    phases: tuple[PhaseInterval, ...]
    events: tuple[EventMarker, ...]
    baseline_intervals: tuple[BaselineInterval, ...]
    source_schema_ids: Mapping[str, str]
    synthetic_semantics_unvalidated: bool


@dataclass(frozen=True, slots=True)
class AlignedSession:
    session_id: str
    window: SessionWindow
    streams: Mapping[str, AlignedStreamView]
    context: Mapping[str, JsonValue]
    annotations: AlignedAnnotations
    task_reference: AlignedStreamView | None
    source_snapshot_fingerprint: str
    synchronization_fingerprint: str


@dataclass(frozen=True, slots=True)
class SynchronizationOutcome:
    report: SynchronizationReport
    aligned_session: AlignedSession | None
~~~

`SynchronizationInput.__post_init__` checks non-blocked/continuation, session IDs, exact snapshot fingerprint, and ready inventory. Freeze all mappings with copied `MappingProxyType`; require task reference outside `streams`.

Implement the fingerprint primitives before any service can construct a strict report:

~~~python
import hashlib
import json
from typing import Protocol


class HashWriter(Protocol):
    def update(self, data: bytes) -> object: ...


def hash_part(hasher: HashWriter, *, tag: str, payload: bytes) -> None:
    tag_bytes = tag.encode("utf-8")
    hasher.update(len(tag_bytes).to_bytes(4, "big", signed=False))
    hasher.update(tag_bytes)
    hasher.update(len(payload).to_bytes(8, "big", signed=False))
    hasher.update(payload)


def canonical_json_bytes(value: JsonValue) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def fingerprint_canonical_json(tag: str, value: JsonValue) -> str:
    hasher = hashlib.sha256()
    hash_part(hasher, tag=tag, payload=canonical_json_bytes(value))
    return hasher.hexdigest()


def fingerprint_policy(policy: SynchronizationPolicy) -> str:
    return fingerprint_canonical_json("synchronization-policy", policy.model_dump(mode="json"))


def fingerprint_synchronization(
    *,
    source_snapshot_fingerprint: str,
    policy_fingerprint: str,
    binding_catalog_fingerprint: str,
    aligned_time_parts: Mapping[str, bytes],
    aligned_annotations_json: bytes,
    statuses_and_issues_json: bytes,
) -> str:
    hasher = hashlib.sha256()
    hash_part(
        hasher,
        tag="source-snapshot-fingerprint",
        payload=source_snapshot_fingerprint.encode("ascii"),
    )
    hash_part(hasher, tag="policy-fingerprint", payload=policy_fingerprint.encode("ascii"))
    hash_part(
        hasher,
        tag="binding-catalog-fingerprint",
        payload=binding_catalog_fingerprint.encode("ascii"),
    )
    for logical_key in sorted(aligned_time_parts):
        hash_part(
            hasher,
            tag=f"aligned-time:{logical_key}",
            payload=aligned_time_parts[logical_key],
        )
    hash_part(hasher, tag="aligned-annotations", payload=aligned_annotations_json)
    hash_part(hasher, tag="statuses-and-issues", payload=statuses_and_issues_json)
    return hasher.hexdigest()
~~~

`fingerprint_synchronization` sorts `aligned_time_parts` by logical `stream/role/column` key and feeds every part through `hash_part`. Int64 payloads use signed little-endian 8-byte values; booleans use single bytes `0`/`1`. Canonical JSON uses UTF-8, sorted keys, compact separators, and `allow_nan=False`. Absolute paths, host/wall time, issue insertion order, and the output fingerprint field itself are forbidden inputs.

- [ ] **Step 4: Run GREEN and commit**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/synchronization/test_models.py tests/synchronization/test_fingerprint.py -v
git add src/pilot_assessment/synchronization tests/synchronization/test_models.py tests/synchronization/test_fingerprint.py
git commit -m "feat: add aligned models and fingerprint primitives"
~~~

### Task 7: Align point tables and derive the canonical session window

**Files:**
- Create: `src/pilot_assessment/synchronization/bindings.py`
- Create: `tests/synchronization/test_bindings.py`

- [ ] **Step 1: Write point/window RED tests**

Implement the exact tests listed below one at a time:

- `test_point_binding_appends_int64_time_and_boolean_mask_without_mutating_raw`
- `test_point_binding_preserves_raw_column_order_values_and_row_count`
- `test_point_binding_uses_closed_session_window`
- `test_point_binding_keeps_before_and_after_session_rows`
- `test_point_binding_preserves_duplicate_mapped_ns_in_stable_key_order`
- `test_point_binding_requires_declared_stable_keys`
- `test_session_window_uses_max_mapped_x_time_not_synthetic_duration`
- `test_session_window_requires_session_start_origin`
- `test_session_window_requires_x_clock_to_match_master_clock`
- `test_session_window_requires_positive_end`
- `test_shared_xu_have_identical_time_columns_and_masks`

The first table must include mapped values `[-1, 0, end, end+1]` and assert masks `[False, True, True, False]` without filtering.

- [ ] **Step 2: Run the first RED**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/synchronization/test_bindings.py::test_point_binding_appends_int64_time_and_boolean_mask_without_mutating_raw -v
~~~

Expected: import failure because the binding executor does not exist.

- [ ] **Step 3: Implement point mapping without sorting/filtering**

`map_point_artifact(frame, binding, clock)` converts the declared source column to a Polars Int64 target series and validates existing `(t_ns, stable_keys)` order. `apply_point_window(frame, binding, window)` appends Boolean mask. Both return new DataFrames; no mutation, aggregation, sort, or filter.

Use:

~~~python
mapped = [
    map_source_seconds_to_session_ns(value, scale=clock.scale, offset_ns=clock.offset_ns)
    for value in frame[binding.source_timestamp_column].to_list()
]
aligned = frame.with_columns(pl.Series(binding.target_timestamp_column, mapped, dtype=pl.Int64))
inside = [window.start_t_ns <= value <= window.end_t_ns for value in mapped]
return aligned.with_columns(pl.Series(binding.in_session_column, inside, dtype=pl.Boolean))
~~~

- [ ] **Step 4: Implement D-018 window derivation**

Use the already mapped X table; do not map X a second time. The exact signature is:

~~~python
def derive_session_window(
    sync_input: SynchronizationInput,
    aligned_x: pl.DataFrame,
    binding: PointBinding,
) -> SessionWindow:
    manifest = sync_input.loaded_manifest.manifest
    if manifest.session_timebase.origin != "session_start":
        raise ValueError("SESSION_WINDOW_UNAVAILABLE")
    x_result = sync_input.readiness_report.stream_results["X"]
    x_stream = sync_input.prepared_session.streams["X"]
    if (
        x_result.readiness is not StreamReadiness.READY
        or x_stream.clock_id != manifest.session_timebase.master_clock_id
        or binding.target_timestamp_column not in aligned_x.columns
        or aligned_x.schema[binding.target_timestamp_column] != pl.Int64
    ):
        raise ValueError("SESSION_WINDOW_UNAVAILABLE")
    mapped_x_times = cast(list[int], aligned_x[binding.target_timestamp_column].to_list())
    if not mapped_x_times or max(mapped_x_times) <= 0:
        raise ValueError("SESSION_WINDOW_UNAVAILABLE")
    return SessionWindow(
        start_t_ns=0,
        end_t_ns=max(mapped_x_times),
        source="master-clock-x-mapped-coverage-v1",
    )
~~~

Ignore `extensions.synthetic.duration_s` as authority; a test sets it to a conflicting value.

- [ ] **Step 5: Run all point/window GREEN tests and commit**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/synchronization/test_bindings.py -k "point or session_window or shared_xu" -v
git add src/pilot_assessment/synchronization/bindings.py tests/synchronization/test_bindings.py
git commit -m "feat: align native point streams"
~~~

### Task 8: Align interval, inherited, and untimed roles

**Files:**
- Modify: `src/pilot_assessment/synchronization/bindings.py`
- Modify: `tests/synchronization/test_bindings.py`

- [ ] **Step 1: Write secondary-role RED tests**

Add:

- `test_fixation_interval_maps_both_endpoints_and_classifies_window_relation`
- `test_fixation_interval_preserves_source_duration_and_row_count`
- `test_interval_binding_rejects_end_not_after_start`
- `test_ecg_r_peaks_are_aligned_as_an_independent_point_role`
- `test_aoi_rows_inherit_frame_time_without_reordering_children`
- `test_inherit_binding_rejects_missing_parent_key`
- `test_inherit_binding_rejects_duplicate_parent_key`
- `test_untimed_sidecars_and_image_paths_remain_byte_and_value_identical`

Run the first test and confirm RED because interval support is absent.

- [ ] **Step 2: Implement interval mapping**

Freeze the callable boundary as `map_interval_artifact(frame: pl.DataFrame, binding: IntervalBinding, clock: ClockSync, window: SessionWindow) -> pl.DataFrame`. All point/interval/inherit executors translate structural failures through one internal `TemporalAlignmentError(issue: DomainErrorData)`; service catches that type and never a raw Polars/KeyError/ValueError.

Map both source endpoints through the same clock. Require `end_t_ns > start_t_ns`; append:

~~~python
overlaps = end_t_ns >= window.start_t_ns and start_t_ns <= window.end_t_ns
fully_inside = start_t_ns >= window.start_t_ns and end_t_ns <= window.end_t_ns
~~~

Preserve source duration, raw order, and every row.

- [ ] **Step 3: Implement inherited time**

Freeze the callable boundary as `inherit_point_time(child: pl.DataFrame, parent: pl.DataFrame, binding: InheritBinding) -> pl.DataFrame`.

Build a unique parent key→(`t_ns`,`in_session`) mapping, reject missing/duplicate keys with `TEMPORAL_PARENT_KEY_INVALID`, and append values to children in existing child order. Do not use a Polars join that changes order without an explicit stable row index assertion.

- [ ] **Step 4: Preserve untimed artifacts**

Return the existing immutable JSON/file mappings unchanged; do not add time columns or assign an aligned artifact schema to PNG/sidecar roles.

- [ ] **Step 5: Run GREEN and commit**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/synchronization/test_bindings.py -v
git add src/pilot_assessment/synchronization/bindings.py tests/synchronization/test_bindings.py
git commit -m "feat: align secondary temporal artifacts"
~~~

### Task 9: Parse and align annotations safely

**Files:**
- Create: `src/pilot_assessment/synchronization/annotations.py`
- Create: `tests/synchronization/test_annotations.py`

- [ ] **Step 1: Write bounded strict-reader RED tests**

Add exact cases for invalid UTF-8, duplicate JSON keys, NaN/Infinity, file >4 MiB, >100,000 records, path/snapshot digest change. Each must produce a domain-safe code, especially `SOURCE_CHANGED_DURING_SYNCHRONIZATION`, rather than leak JSON/OS exceptions.

- [ ] **Step 2: Run RED**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/synchronization/test_annotations.py -k "reader" -v
~~~

Expected: import failure because annotation reader does not exist.

- [ ] **Step 3: Implement verified bounded JSON reading**

Use these exact public-within-package APIs:

~~~python
@dataclass(frozen=True, slots=True)
class AnnotationReadLimits:
    max_bytes: int = 4 * 1024 * 1024
    max_records: int = 100_000


class AnnotationAlignmentError(Exception):
    def __init__(self, issue: DomainErrorData) -> None:
        self.issue = issue
        super().__init__(issue.message)
~~~

The frozen function signatures are:

- `read_verified_annotation(loaded: LoadedManifest, relative_path: str, *, record_field: Literal["phases", "events", "baseline_intervals"], limits: AnnotationReadLimits = AnnotationReadLimits()) -> dict[str, JsonValue]`
- `align_annotations(sync_input: SynchronizationInput, window: SessionWindow, *, limits: AnnotationReadLimits = AnnotationReadLimits()) -> tuple[AlignedAnnotations, AnnotationSynchronizationResult]`

`read_verified_annotation` resolves below `loaded.bundle_root`, rejects link/path escape, requires the path/digest in `loaded.verified_digests`, reads at most `max_bytes + 1`, rechecks SHA-256, strict-decodes UTF-8, rejects duplicate keys and non-standard constants, requires the target value to be a list, and caps it at `max_records`. Snapshot/path/digest changes raise `SOURCE_CHANGED_DURING_SYNCHRONIZATION`; bounded decode/shape failures raise `ANNOTATION_SEMANTICS_INVALID`; unknown schema IDs raise `ANNOTATION_SCHEMA_UNSUPPORTED`. All OS/JSON exceptions are translated to bounded `DomainErrorData` without raw payloads.

- [ ] **Step 4: Write and run annotation temporal-structure/self-consistency RED tests**

Add:

- `test_synthetic_annotation_seconds_use_shared_half_even_converter_without_device_clock`
- `test_synthetic_annotation_provenance_remains_semantically_unvalidated`
- `test_unknown_annotation_schema_is_rejected_without_guessing`
- `test_phase_ids_are_unique_and_match_manifest_order`
- `test_phases_must_be_ordered_non_overlapping_and_fully_in_session`
- `test_phase_gaps_are_allowed_and_reported`
- `test_last_phase_includes_exact_session_endpoint`
- `test_point_events_accept_both_closed_window_boundaries`
- `test_duration_event_requires_positive_duration_and_session_overlap`
- `test_event_response_mapping_is_validated_but_not_executed`
- `test_baseline_must_be_positive_and_fully_in_session`
- `test_invalid_baseline_requires_exclusion_reason`
- `test_baseline_phase_overlap_is_allowed`

- [ ] **Step 5: Implement the six registered annotation schemas**

Support exactly the three current synthetic schemas plus `phases-session-time-v0.1`, `events-session-time-v0.1`, and `baseline-intervals-session-time-v0.1`. Synthetic seconds call `session_seconds_to_ns` and preserve `synthetic_semantics_unvalidated=true`; canonical ns values are strict int64 and receive no clock transform. Implement §9 phase/event/baseline temporal contract/self-consistency rules and return `AlignedAnnotations` plus `AnnotationSynchronizationResult`; passing them never asserts expert-label or task correctness.

Freeze these six minimal registered shapes in parameterized tests (extra fields remain forbidden by the per-schema validators):

~~~json
{"schema_id":"phases-synthetic-v0.1","generator_id":"fixture-v0.1","seed":1,"synthetic_semantics_unvalidated":true,"phases":[{"phase_id":"p1","start_s":0.0,"end_s":1.0}]}
{"schema_id":"events-synthetic-v0.1","generator_id":"fixture-v0.1","seed":1,"synthetic_semantics_unvalidated":true,"events":[{"event_id":"e1","event_type":"disturbance","time_s":0.5}]}
{"schema_id":"baseline-intervals-synthetic-v0.1","generator_id":"fixture-v0.1","seed":1,"synthetic_semantics_unvalidated":true,"baseline_intervals":[{"interval_id":"b1","start_s":0.0,"end_s":0.2}]}
{"schema_id":"phases-session-time-v0.1","annotation_revision":"expert-revision-1","timebase":{"origin":"session_start","unit":"ns"},"annotation_source":"expert","phases":[{"phase_id":"p1","label":"phase one","start_t_ns":0,"end_t_ns":1000000000,"source":"expert","confidence":1.0}]}
{"schema_id":"events-session-time-v0.1","annotation_revision":"expert-revision-1","timebase":{"origin":"session_start","unit":"ns"},"annotation_source":"expert","events":[{"event_id":"e1","event_type":"disturbance","t_ns":500000000,"source":"expert","confidence":1.0}]}
{"schema_id":"baseline-intervals-session-time-v0.1","annotation_revision":"expert-revision-1","timebase":{"origin":"session_start","unit":"ns"},"annotation_source":"expert","baseline_intervals":[{"interval_id":"b1","start_t_ns":0,"end_t_ns":200000000,"condition":"nominal","valid":true}]}
~~~

- [ ] **Step 6: Run GREEN and commit**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/synchronization/test_annotations.py -v
git add src/pilot_assessment/synchronization/annotations.py tests/synchronization/test_annotations.py
git commit -m "feat: align session annotations"
~~~

### Task 10: Compute deterministic quality and scene/gaze metrics

**Files:**
- Create: `src/pilot_assessment/synchronization/quality.py`
- Create: `tests/synchronization/test_quality.py`
- Create: `tests/synchronization/test_scene_gaze.py`

- [ ] **Step 1: Write point-quality RED tests**

Add tests for before/inside/after counts; `[0,0,1,2,2,2]` as 2 duplicate groups/5 participating rows; strict `delta > 5×median` gap rule; equality not counted; single-row null period/zero span; interpolated rows zero; descriptor residuals preserved.

- [ ] **Step 2: Run RED**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/synchronization/test_quality.py -v
~~~

Expected: import failure because quality metrics do not exist.

- [ ] **Step 3: Implement point/interval metrics**

Freeze these call boundaries:

- `compute_point_metrics(frame: pl.DataFrame, binding: PointBinding | InheritBinding, clock: ClockMappingSummary, window: SessionWindow, policy: SynchronizationPolicy) -> PointTemporalArtifactMetrics`
- `compute_interval_metrics(frame: pl.DataFrame, binding: IntervalBinding, clock: ClockMappingSummary, window: SessionWindow) -> IntervalTemporalArtifactMetrics`

Compute period/gap metrics from mapped rows with `in_session=true` in their preserved stable order. Count duplicate timestamp groups/participating rows first, then remove zero deltas from the period/gap sequence; never reorder or deduplicate the DataFrame itself. The median is the exact median of positive integer deltas (an even-sized sample may yield `.5`), `gap_threshold_ns=round_half_even(median_period_ns × policy.gap_detection_multiplier)`, and a gap is counted only when `delta > gap_threshold_ns`. `max_gap_ns` is the maximum positive delta when a median exists. Zero/one usable timestamp yields `median_period_ns/gap_threshold_ns/max_gap_ns=None`, `gap_count=0`, and no NaN/Infinity. Report the exact DTO fields; diagnostics never alter DataFrames or disposition.

- [ ] **Step 4: Write scene/gaze RED tests**

Add exact interval-boundary, last-frame, out-of-session exclusion, delta min/max, and invalid-count tests. With Task 1 applied, micro and 29.01 s synthetic inputs must report zero invalid in-session associations.

- [ ] **Step 5: Implement presentation-interval validation**

Freeze the call boundary as `validate_scene_gaze_time(scene_frames: pl.DataFrame, gaze_samples: pl.DataFrame, window: SessionWindow, *, max_examples: int = 10) -> SceneGazeMetrics`.

For each in-session gaze row, resolve its referenced frame and require:

~~~text
frame_t_ns <= gaze_t_ns < next_frame_t_ns
~~~

For the last in-session frame use `<= session_window.end_t_ns`. Report `SCENE_GAZE_TIME_MISMATCH` with bounded example IDs when invalid; service marks G `invalid` but preserves `SceneGazeMetrics` as diagnostics, so optional G degrades and required G blocks. Out-of-session rows remain counted but not classified as relationship errors.

- [ ] **Step 6: Run GREEN and commit**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/synchronization/test_quality.py tests/synchronization/test_scene_gaze.py -v
git add src/pilot_assessment/synchronization/quality.py tests/synchronization/test_quality.py tests/synchronization/test_scene_gaze.py
git commit -m "feat: report native synchronization quality"
~~~

### Task 11: Orchestrate reference, disposition, and M1→M3 flow

**Files:**
- Create: `src/pilot_assessment/synchronization/service.py`
- Modify: `src/pilot_assessment/synchronization/__init__.py`
- Create: `tests/synchronization/test_reference.py`
- Create: `tests/synchronization/test_service.py`

- [ ] **Step 1: Write reference RED tests**

Add bundle-reference own-clock/checksum alignment, required no-in-session block, clock failure block, model reference deferred, and separation from core metrics.

- [ ] **Step 2: Write service/disposition RED tests**

Add:

- `test_m2_blocked_returns_blocked_report_without_constructing_input`
- `test_required_alignment_failure_blocks_and_returns_no_aligned_session`
- `test_optional_alignment_failure_returns_ready_partial`
- `test_annotation_semantics_failure_blocks`
- `test_clock_conflict_blocks_with_stable_error_code`
- `test_missing_required_binding_blocks`
- `test_missing_optional_binding_returns_ready_partial`
- `test_ready_outcome_has_aligned_session_and_anchor_continuation`
- `test_all_service_paths_keep_formal_run_unauthorized`
- `test_global_issues_are_sorted_deterministically`

- [ ] **Step 3: Run RED**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/synchronization/test_reference.py tests/synchronization/test_service.py -v
~~~

Expected: import failure because service API does not exist.

- [ ] **Step 4: Implement the exact service API**

~~~python
def synchronize_session(
    sync_input: SynchronizationInput,
    *,
    policy: SynchronizationPolicy | None = None,
) -> SynchronizationOutcome:
    active_policy = policy or SynchronizationPolicy()
    return _synchronize_valid_input(sync_input, active_policy)


def synchronize_bundle(
    bundle_root: str | Path,
    *,
    policy: SynchronizationPolicy | None = None,
    loader: ManifestLoader | None = None,
    registry: AdapterRegistry | None = None,
) -> SynchronizationOutcome:
    active_loader = loader or ManifestLoader()
    loaded = active_loader.load(bundle_root)
    ingestion = inspect_loaded_ingestion_readiness(loaded, registry=registry)
    if ingestion.prepared_session is None:
        return _blocked_from_ingestion(loaded, ingestion.report, policy or SynchronizationPolicy())
    sync_input = SynchronizationInput(
        loaded_manifest=loaded,
        readiness_report=ingestion.report,
        prepared_session=ingestion.prepared_session,
    )
    return synchronize_session(sync_input, policy=policy)
~~~

Implement every private helper referenced above with these exact signatures; none is a placeholder:

~~~python
def _item_status_from_readiness(
    readiness: StreamReadiness,
    *,
    attempted: bool,
) -> SynchronizationItemStatus:
    if readiness is StreamReadiness.READY:
        if attempted:
            raise ValueError("attempted ready inputs require an explicit M3 result")
        return SynchronizationItemStatus.NOT_ATTEMPTED
    return {
        StreamReadiness.UNAVAILABLE: SynchronizationItemStatus.UNAVAILABLE,
        StreamReadiness.INVALID: SynchronizationItemStatus.INVALID,
        StreamReadiness.UNSUPPORTED: SynchronizationItemStatus.UNSUPPORTED,
        StreamReadiness.NOT_APPLICABLE: SynchronizationItemStatus.NOT_APPLICABLE,
    }[readiness]


def _derive_disposition(
    *,
    session_window: SessionWindow | None,
    streams: Mapping[str, StreamSynchronizationResult],
    task_reference: TaskReferenceSynchronizationResult | None,
    annotations: AnnotationSynchronizationResult | None,
    global_issues: tuple[DomainErrorData, ...],
) -> SynchronizationDisposition:
    required_core_failed = any(
        result.required_for_import
        and result.synchronization_status is not SynchronizationItemStatus.ALIGNED
        for result in streams.values()
    )
    optional_core_failed = any(
        not result.required_for_import
        and result.synchronization_status
        not in {SynchronizationItemStatus.ALIGNED, SynchronizationItemStatus.NOT_APPLICABLE}
        for result in streams.values()
    )
    reference_blocked = bool(
        task_reference is not None
        and task_reference.source == "bundle"
        and task_reference.required_for_import
        and task_reference.synchronization_status is not SynchronizationItemStatus.ALIGNED
    )
    reference_degraded = bool(
        task_reference is not None
        and task_reference.source == "bundle"
        and task_reference.required_for_import is False
        and task_reference.synchronization_status
        not in {SynchronizationItemStatus.ALIGNED, SynchronizationItemStatus.NOT_APPLICABLE}
    )
    annotation_failed = (
        annotations is None
        or annotations.synchronization_status is not SynchronizationItemStatus.ALIGNED
    )
    global_blocking = any(
        issue.error_code in BLOCKING_SYNCHRONIZATION_ERROR_CODES for issue in global_issues
    )
    if (
        session_window is None
        or required_core_failed
        or reference_blocked
        or annotation_failed
        or global_blocking
    ):
        return SynchronizationDisposition.BLOCKED
    if optional_core_failed or reference_degraded:
        return SynchronizationDisposition.READY_PARTIAL
    return SynchronizationDisposition.READY
~~~

The two orchestration helper signatures are frozen as `_blocked_from_ingestion(loaded: LoadedManifest, readiness: IngestionReadinessReport, policy: SynchronizationPolicy) -> SynchronizationOutcome` and `_synchronize_valid_input(sync_input: SynchronizationInput, policy: SynchronizationPolicy) -> SynchronizationOutcome`.

`_item_status_from_readiness` maps `UNAVAILABLE/INVALID/UNSUPPORTED/NOT_APPLICABLE` one-to-one; `READY` maps to `NOT_ATTEMPTED` when `attempted=false` and may become `ALIGNED` or `INVALID/UNSUPPORTED` only after an actual binding attempt. `_derive_disposition` duplicates the public DTO invariant exactly: missing window, required core/reference failure, or non-aligned annotations blocks; otherwise any optional core/reference failure is partial; model-reference deferred is neutral.

`_blocked_from_ingestion` must:

1. create exactly seven core results from the M2 inventory, using `attempted=false`, with no aligned schema/artifacts;
2. translate a bundle reference the same way, return model reference as deferred, or use `None` when no reference exists;
3. create an annotation result with `NOT_ATTEMPTED`, the manifest revision/schema IDs when known, no counts/intervals, and a bounded `SYNCHRONIZATION_INPUT_BLOCKED` issue;
4. use `session_window=None`, `aligned_time_parts={}`, aligned annotation JSON `null`, sorted status/issue canonical JSON, the Task 6 policy/catalog fingerprint functions, and then the synchronization fingerprint;
5. construct a strict blocked `SynchronizationReport` and return `SynchronizationOutcome(report=report, aligned_session=None)`.

`_synchronize_valid_input` processes in this exact order: load catalog/hash → policy hash → validate clock inventory → map X once → derive X window → align all M2-ready core streams → translate non-ready optional streams → align/defer reference → align annotations → compute quality and scene/gaze checks → sort issues → derive disposition → build framed fingerprint inputs → compute synchronization fingerprint → construct report → construct `AlignedSession` only when non-blocked. The same fingerprint is written into report and aligned session. Any required failure returns no aligned session; `ready_partial` keeps only successfully aligned optional streams and still returns an aligned session. All result constructors populate every Task 2 field from M2 readiness, descriptor clock, binding profile, metrics, checksums, and bounded issues; no raw Polars/Pydantic/OS exception crosses the service boundary.

Freeze exception translation in tests and implementation:

| Caught condition | Result/status | Stable issue |
|---|---|---|
| `TemporalAlignmentError` on a core/reference role | affected item `invalid`; required blocks, optional degrades | the contained temporal issue |
| missing built-in binding | affected item `unsupported`; required blocks, optional degrades | `TEMPORAL_BINDING_NOT_FOUND` |
| clock declaration conflict | all affected same-clock items `invalid` | `CLOCK_DECLARATION_INCONSISTENT` |
| mapped int64 overflow | affected item `invalid` | `TIMESTAMP_OUT_OF_INT64_RANGE` |
| `AnnotationAlignmentError` | annotation `invalid` or `unsupported`; always blocks | contained annotation/source-changed issue |
| source/snapshot digest change | no aligned session | `SOURCE_CHANGED_DURING_SYNCHRONIZATION` |
| unexpected implementation exception | no aligned session; no raw message/type in diagnostics | bounded `SYNCHRONIZATION_INTERNAL_ERROR` |

- [ ] **Step 5: Implement status translation and reference semantics**

Add direct tests for each helper mapping and disposition branch. M2 blocked gets seven complete core results using `not_attempted` or the original unavailable/invalid/unsupported/not-applicable status. Bundle reference uses `task-reference-normalized-v0.1/commanded_path` and the single-table aligned stream schema `task-reference-path-aligned-v0.1`; model reference returns `deferred_model_bundle_resolution` and does not block. Annotation error names containing “semantics” refer only to the frozen session-time contract/self-consistency rules, never expert-label or task correctness.

- [ ] **Step 6: Run GREEN and M2 regression**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/synchronization/test_reference.py tests/synchronization/test_service.py tests/ingestion/test_readiness.py -v
~~~

Expected: all new service/reference and old readiness tests pass.

- [ ] **Step 7: Commit**

~~~powershell
git add src/pilot_assessment/synchronization tests/synchronization/test_reference.py tests/synchronization/test_service.py
git commit -m "feat: orchestrate native session synchronization"
~~~

### Task 12: Harden deterministic synchronization fingerprint replay

**Files:**
- Modify: `src/pilot_assessment/synchronization/fingerprint.py`
- Modify: `src/pilot_assessment/synchronization/service.py`
- Modify: `tests/synchronization/test_fingerprint.py`

- [ ] **Step 1: Write fingerprint RED tests**

Add replay-stable, root-independent, policy-fingerprint-sensitive, aligned-time-sensitive, and issue-order-independent tests. Because the v0.1 policy fields are literals, the sensitivity test changes the `policy_fingerprint` input to `fingerprint_synchronization`; it does not construct an invalid v0.1 policy.

- [ ] **Step 2: Run RED**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/synchronization/test_fingerprint.py -v
~~~

Expected: primitive framing tests already pass, while at least one full-outcome replay/root/order/mutation test exposes a missing canonical input or incorrect service integration.

- [ ] **Step 3: Implement canonical fingerprinting**

Harden the Task 6 primitive and service integration so the full outcome hashes, in order:

1. M2 `source_snapshot_fingerprint` bytes;
2. framed `policy_fingerprint` bytes; that digest is itself the Task 6 hash of canonical policy JSON;
3. temporal catalog resource fingerprint;
4. sorted stream/role IDs and each appended int64 column encoded little-endian signed 8-byte values;
5. Boolean flags as bytes 0/1;
6. canonical aligned annotation JSON;
7. sorted status/issues excluding the fingerprint field itself.

Every item is length-framed with `hash_part`; do not concatenate unframed strings/arrays. Do not include absolute roots, wall time, host, Polars serialization, or issue insertion order.

- [ ] **Step 4: Run GREEN and commit**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/synchronization/test_fingerprint.py -v
git add src/pilot_assessment/synchronization/fingerprint.py src/pilot_assessment/synchronization/service.py tests/synchronization/test_fingerprint.py
git commit -m "feat: fingerprint aligned session time"
~~~

### Task 13: Prove the micro M1→M2→M3 workflow

**Files:**
- Create: `tests/e2e/test_m3_micro_bundle.py`

- [ ] **Step 1: Write the full micro RED test**

Generate the same 2 s/201-row CSV shape as M2 E2E, snapshot all generated raw files, call `synchronize_bundle`, and assert:

~~~python
assert outcome.report.session_window == SessionWindow(
    start_t_ns=0,
    end_t_ns=2_000_000_000,
    source="master-clock-x-mapped-coverage-v1",
)
assert outcome.report.disposition is SynchronizationDisposition.READY
assert outcome.report.can_continue_to_anchor_availability is True
assert outcome.report.formal_run_authorized is False
assert outcome.aligned_session is not None
~~~

Freeze primary totals/in-session:

~~~text
X 201/201; U 201/201; I frame_index 61/60; G gaze_samples 241/240;
EEG samples 513/509; ECG samples 501/498; pilot_camera frame_index 31/30;
task_reference commanded_path 201/201.
~~~

Freeze secondary metrics: AOI 122/120; fixations 4 total/4 overlap/3 full; R-peaks 3/3; scene/gaze invalid 0. Assert every pre/post raw checksum and source CSV byte sequence is identical.

- [ ] **Step 2: Run RED, then integrate only missing registrations**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/e2e/test_m3_micro_bundle.py -v
~~~

Expected: first unmet registration/metric fails; do not relax frozen counts.

- [ ] **Step 3: Run GREEN and commit**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/e2e/test_m3_micro_bundle.py tests/e2e/test_m2_micro_bundle.py -v
git add src/pilot_assessment tests/e2e/test_m3_micro_bundle.py
git commit -m "test: prove M3 micro synchronization workflow"
~~~

### Task 14: Prove format-sample M3, update handoff, and run the completion gate

**Files:**
- Create: `tests/e2e/test_m3_format_sample_csv_local.py`
- Modify: `docs/product/11_IMPLEMENTATION_STATUS.md`
- Modify: `docs/product/README.md`
- Modify: `README.md`
- Modify: `docs/product/09_VALIDATION_AND_HANDOFF.md`
- Modify: `docs/product/specs/2026-07-12-m3-native-time-synchronization-design.md`
- Modify: `docs/product/plans/2026-07-12-m3-native-time-synchronization-implementation-plan.md`

- [ ] **Step 1: Write the opt-in format-sample E2E test**

Use `PILOT_ASSESSMENT_FORMAT_SAMPLE_CSV`, verify source SHA-256 `19bf804253d841de9c9de299ac96e9e1b693b2dbfae2f3eaeac5d7dc044e4f52`, generate a fresh bundle after Task 1, snapshot all raw Parquet/PNG/annotation/reference hashes, and assert only software-interface/time facts:

~~~text
window 0..29_010_000_000 ns
X 2902/2902; U 2902/2902; I 871/871; G 3482/3481;
EEG 7427/7423; ECG 7253/7251; camera 436/435; reference 2902/2902;
AOI 1742/1742; fixations 59 total/59 overlap/58 full; R-peaks 37/37;
scene/gaze invalid association 0.
~~~

Assert source and every raw bundle hash remain unchanged after synchronization.

Also assert captured-format provenance, `task_validity=not_asserted`, `ground_truth_status=absent`, synthetic reference validity, `scientific_validation_status=not_supported`, and `formal_run_authorized=false`. Do not assert trajectory accuracy, phase correctness, control quality, anchor values, or pilot ability.

- [ ] **Step 2: Run the format-sample E2E**

~~~powershell
try {
  $env:PILOT_ASSESSMENT_FORMAT_SAMPLE_CSV='C:\Users\long\Desktop\CranfieldOffer\proj\data\S_101500_Time_2026_05_14_16_48_54_P_1.csv'
  & .\.tools\uv\uv.exe run pytest tests/e2e/test_m3_format_sample_csv_local.py -v
  if($LASTEXITCODE -ne 0){throw 'Format-sample M3 E2E failed'}
} finally {
  Remove-Item Env:PILOT_ASSESSMENT_FORMAT_SAMPLE_CSV -ErrorAction SilentlyContinue
}
~~~

Expected: `1 passed`; invalid association must be zero, never the pre-fix value 10. Passing means format/time/interface compatibility only.

- [ ] **Step 3: Update implementation/handoff status with measured evidence**

Change M3 status only after fresh results. Record exact test count, primary/secondary golden counts, report/fingerprint scope, source hash, no-resampling boundary, synthetic scientific status, and M4 as next milestone. Mark this plan completed by changing all checkboxes only after their commits exist.

- [ ] **Step 4: Run the full completion gate**

~~~powershell
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-NativeChecked {
  param([string]$Label,[string]$FilePath,[string[]]$Arguments)
  & $FilePath @Arguments
  $exitCode=$LASTEXITCODE
  if($exitCode -ne 0){throw "$Label failed with exit code $exitCode"}
}

$git=(Get-Command git -ErrorAction Stop).Source
$repoRootText=& $git rev-parse --show-toplevel
if($LASTEXITCODE -ne 0){throw "git rev-parse failed with exit code $LASTEXITCODE"}
$repoRoot=(Resolve-Path -LiteralPath ([string]$repoRootText).Trim()).Path
Set-Location -LiteralPath $repoRoot
$uv=(Resolve-Path -LiteralPath '.\.tools\uv\uv.exe').Path
$formatSampleCsv=(Resolve-Path -LiteralPath 'C:\Users\long\Desktop\CranfieldOffer\proj\data\S_101500_Time_2026_05_14_16_48_54_P_1.csv').Path
$envName='PILOT_ASSESSMENT_FORMAT_SAMPLE_CSV'
$previousValue=[Environment]::GetEnvironmentVariable($envName,[EnvironmentVariableTarget]::Process)
try {
  [Environment]::SetEnvironmentVariable($envName,$formatSampleCsv,[EnvironmentVariableTarget]::Process)
  Invoke-NativeChecked 'M2/M3 captured format-sample E2E' $uv @(
    'run','pytest','tests/e2e/test_format_sample_csv_local.py',
    'tests/e2e/test_m3_format_sample_csv_local.py','-q'
  )
} finally {
  [Environment]::SetEnvironmentVariable($envName,$previousValue,[EnvironmentVariableTarget]::Process)
}

Invoke-NativeChecked 'JSON Schema regeneration' $uv @('run','python','-m','pilot_assessment.schemas.export')
Invoke-NativeChecked 'full pytest suite' $uv @('run','pytest','-q')
Invoke-NativeChecked 'Ruff format check' $uv @('run','ruff','format','--check','.')
Invoke-NativeChecked 'Ruff lint check' $uv @('run','ruff','check','.')
Invoke-NativeChecked 'ty type check' $uv @('run','ty','check','src')
Invoke-NativeChecked 'package build' $uv @('build')
Invoke-NativeChecked 'git diff whitespace check' $git @('diff','--check')

$trackedPathspecs=@(
  ':(icase,glob)local_data/**',
  ':(icase,glob)**/*.edf',
  ':(icase,glob)**/*.edf+',
  ':(icase,glob)**/*.mp4',
  ':(icase,glob)**/*.parquet'
)
$trackedDataRaw=@(& $git ls-files -- $trackedPathspecs)
$gitExitCode=$LASTEXITCODE
if($gitExitCode -ne 0){throw "git ls-files failed with exit code $gitExitCode"}
$trackedData=@(
  $trackedDataRaw | Where-Object {-not [string]::IsNullOrWhiteSpace([string]$_)}
)
if($trackedData.Count -ne 0){throw "Tracked local/full data is forbidden:`n$($trackedData -join "`n")"}

$expectedWheel=Join-Path $repoRoot 'dist\pilot_assessment_system-0.1.0-py3-none-any.whl'
if(-not (Test-Path -LiteralPath $expectedWheel -PathType Leaf)){throw "Expected wheel not produced: $expectedWheel"}
Invoke-NativeChecked 'git status inspection' $git @('status','--short')
~~~

Expected: all commands exit 0; two default skips are allowed only for the opt-in M2/M3 format-sample tests; no local/full data is tracked.

- [ ] **Step 5: Run isolated-wheel API/resource/micro smoke**

~~~powershell
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-NativeChecked {
  param([string]$Label,[string]$FilePath,[string[]]$Arguments)
  & $FilePath @Arguments
  $exitCode=$LASTEXITCODE
  if($exitCode -ne 0){throw "$Label failed with exit code $exitCode"}
}

function Get-VerifiedSmokePath {
  param([string]$Candidate)
  $tempRoot=(Resolve-Path -LiteralPath ([IO.Path]::GetTempPath())).Path.TrimEnd([char[]]'\/')
  $candidateFull=([IO.Path]::GetFullPath($Candidate)).TrimEnd([char[]]'\/')
  $tempPrefix=$tempRoot+[IO.Path]::DirectorySeparatorChar
  if(-not $candidateFull.StartsWith($tempPrefix,[StringComparison]::OrdinalIgnoreCase)){
    throw "Refusing smoke path outside TEMP: $candidateFull"
  }
  if(-not [IO.Path]::GetFileName($candidateFull).StartsWith('pilot-assessment-m3-wheel-smoke-',[StringComparison]::OrdinalIgnoreCase)){
    throw "Refusing smoke path without required unique prefix: $candidateFull"
  }
  return $candidateFull
}

function Assert-NoReparsePointTree {
  param([string]$Root)
  $stack=New-Object System.Collections.Stack
  $stack.Push($Root)
  while($stack.Count -gt 0){
    $current=[string]$stack.Pop()
    $item=Get-Item -LiteralPath $current -Force -ErrorAction Stop
    if(($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){
      throw "Refusing recursive deletion; reparse point found: $($item.FullName)"
    }
    if(-not $item.PSIsContainer){continue}
    foreach($child in @(Get-ChildItem -LiteralPath $item.FullName -Force -ErrorAction Stop)){
      if(($child.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){
        throw "Refusing recursive deletion; reparse point found: $($child.FullName)"
      }
      if($child.PSIsContainer){$stack.Push($child.FullName)}
    }
  }
}

$git=(Get-Command git -ErrorAction Stop).Source
$repoRootText=& $git rev-parse --show-toplevel
if($LASTEXITCODE -ne 0){throw "git rev-parse failed with exit code $LASTEXITCODE"}
$repoRoot=(Resolve-Path -LiteralPath ([string]$repoRootText).Trim()).Path
Set-Location -LiteralPath $repoRoot
$uv=(Resolve-Path -LiteralPath '.\.tools\uv\uv.exe').Path
$microTest=(Resolve-Path -LiteralPath 'tests\e2e\test_m3_micro_bundle.py').Path
Invoke-NativeChecked 'fresh wheel build' $uv @('build')
$wheelCandidate=Join-Path $repoRoot 'dist\pilot_assessment_system-0.1.0-py3-none-any.whl'
if(-not (Test-Path -LiteralPath $wheelCandidate -PathType Leaf)){throw "Expected wheel not produced: $wheelCandidate"}
$wheel=(Resolve-Path -LiteralPath $wheelCandidate).Path
$smokeCandidate=Join-Path ([IO.Path]::GetTempPath()) ('pilot-assessment-m3-wheel-smoke-'+[Guid]::NewGuid().ToString('N'))
$smokeRoot=Get-VerifiedSmokePath $smokeCandidate
if(Test-Path -LiteralPath $smokeRoot){throw "Unique smoke path unexpectedly exists: $smokeRoot"}
New-Item -ItemType Directory -Path $smokeRoot -ErrorAction Stop | Out-Null
$previousPythonPath=[Environment]::GetEnvironmentVariable('PYTHONPATH',[EnvironmentVariableTarget]::Process)
try {
  Set-Location -LiteralPath $smokeRoot
  [Environment]::SetEnvironmentVariable('PYTHONPATH',$null,[EnvironmentVariableTarget]::Process)
  $catalogSmoke=@"
from importlib.metadata import version
from pilot_assessment.synchronization import synchronize_bundle
from pilot_assessment.synchronization.profiles import load_builtin_temporal_catalog
assert version("pilot-assessment-system") == "0.1.0"
assert callable(synchronize_bundle)
assert len(load_builtin_temporal_catalog().streams) == 8
"@
  Invoke-NativeChecked 'isolated wheel API/resource smoke' $uv @(
    'run','--isolated','--no-project','--with',$wheel,'python','-c',$catalogSmoke
  )
  $pytestTemp=Join-Path $smokeRoot 'pytest-temp'
  Invoke-NativeChecked 'isolated wheel micro M1-to-M3 E2E' $uv @(
    'run','--isolated','--no-project','--with',$wheel,'--with','pytest==9.1.1',
    'python','-m','pytest',$microTest,'-q','-p','no:cacheprovider','--basetemp',$pytestTemp
  )
} finally {
  [Environment]::SetEnvironmentVariable('PYTHONPATH',$previousPythonPath,[EnvironmentVariableTarget]::Process)
  Set-Location -LiteralPath $repoRoot
  if(Test-Path -LiteralPath $smokeRoot){
    $verifiedCleanup=Get-VerifiedSmokePath $smokeRoot
    if(-not $verifiedCleanup.Equals($smokeRoot,[StringComparison]::OrdinalIgnoreCase)){
      throw "Smoke cleanup path changed unexpectedly: $verifiedCleanup"
    }
    Assert-NoReparsePointTree $verifiedCleanup
    Remove-Item -LiteralPath $verifiedCleanup -Recurse -Force -ErrorAction Stop
    if(Test-Path -LiteralPath $verifiedCleanup){throw 'Smoke cleanup did not remove verified TEMP directory'}
  }
}
~~~

Expected: with the repository root absent from `PYTHONPATH`, the isolated wheel exposes the public API/resource and passes the frozen micro M1→M3 E2E; cleanup occurs only after TEMP-prefix and reparse-point checks.

- [ ] **Step 6: Commit the verified M3 handoff**

~~~powershell
git add README.md docs/product tests/e2e/test_m3_format_sample_csv_local.py
git commit -m "feat: complete M3 native time synchronization"
~~~

Do not push unless the user explicitly requests a remote update.

## Plan self-review checklist

- D-016–D-020 each map to Task 0 and executable acceptance searches.
- Every production module/function first appears behind a named RED test.
- Public field names consistently use `source_snapshot_fingerprint` and full `policy` plus fingerprint.
- Runtime task-reference binding consistently uses `task-reference-normalized-v0.1/commanded_path`.
- The captured CSV is format-only; no test/report may assert trajectory, phase, workload, control quality, physiology, anchor, or pilot ability from it.
- The temporal catalog is cross-validated against packaged M2 per-role profiles before service use; the stale readiness fixture IDs are corrected in Task 1.
- Every aligned stream/artifact schema ends `-aligned-v0.1`; untimed artifacts retain original schemas.
- M2 blocked reports have exact seven core results using `not_attempted` where alignment never ran.
- Scale is applied once; drift is consistency-only; same-clock residual summaries may differ.
- Native rows remain unfiltered and unsorted; duplicate mapped ns require stable keys.
- M3 performs no interpolation/resampling/window grid; all reported interpolation counts are zero.
- Synthetic annotations remain semantically unvalidated; model-bundle reference remains deferred.
- The gaze boundary regression is fixed before scene/gaze and format-sample E2E acceptance.
- §17 primary/secondary counts are frozen and cannot be changed to make a failing implementation pass.
- The final gate covers schema regeneration, full tests, format, lint, type checking, build, wheel resource/API smoke, format-sample opt-in E2E, source immutability, and Git tracking boundaries.
