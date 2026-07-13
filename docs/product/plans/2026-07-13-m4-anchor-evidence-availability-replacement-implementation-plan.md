# M4 Anchor Calculation and Evidence Availability Replacement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved M4 contract, deterministic plugin runtime, all 18 reference AnchorPlugins, a lightweight layered verification pyramid, and one public 10-second M1-to-M4 wheel smoke without introducing a performance-quality gate or claiming scientific validation.

**Architecture:** M4 consumes one immutable M3 `AlignedSession` plus its matching `SynchronizationReport`, a frozen semantic/reference snapshot, and an already compiled execution plan. A trusted packaged registry resolves versioned plugins; a typed DAG schedules them; each plugin emits raw `AnchorMeasurement` and staged artifacts; a central scorer produces `AnchorResultV2`; the evaluation report exposes complete inventory, raw availability, deterministic fingerprints, and `formal_run_authorized=false`. Generic engine code never switches on O1-O13/H1-H5 IDs, while `reference-model-v0.1` is an exact, versioned 18-anchor profile. Verification is deliberately layered: exact per-anchor micro inputs prove algorithms, compact aligned tables prove complete real-plugin scenarios and state semantics, and one generated 10-second multimodal bundle proves the physical M1-to-M4 path.

**Tech Stack:** Python 3.11, Pydantic 2, Polars 1.x, NumPy 2.3.x, SciPy 1.17.x, RFC 8785 JCS, Decimal, JSON Schema Draft 2020-12, pytest, Ruff, ty, uv, PowerShell.

---

## Plan status and authority boundary

- Design sources of truth: `docs/product/specs/2026-07-13-m4-anchor-evidence-availability-design.md`, the accepted `docs/product/specs/2026-07-13-m4-lightweight-workflow-validation-amendment.md`, and the accepted `docs/product/specs/2026-07-13-m4-task3-reference-candidate-binding-amendment.md`. The lightweight amendment takes precedence for verification scope; the Task 3 amendment takes precedence for semantic/reference contracts, binding, fingerprint ownership, and candidate producer boundaries.
- Accepted decisions: D-021 through D-028 in `docs/product/DECISIONS.md`.
- Plan status on 2026-07-13: explicitly approved by the user after approval of the lightweight amendment; Tasks 0–2 were completed in commits `bc544bf`, `f56365c`, and `928e9a4`; the user then explicitly approved the Task 3 candidate-binding amendment, Task 3 is complete under the checked section below, and Task 4 is next.
- Current implementation truth: 18/18 reference anchors specified, 0/18 production plugins implemented; M4 is not engineering verified.
- Scientific truth: `reference-model-v0.1` remains `engineering_default`; every synthetic M4 fixture plan/report is `not_supported`. M4 copies the frozen plan status and never promotes it because a calculation or software test passed.
- Runtime truth: every M4 report remains `formal_run_authorized=false`; M6 alone may authorize a formal assessment run.
- Scope truth: M4 consumes a compiled plan. Building/editing/publishing a ModelBundle, graph, CPT, or plan compiler belongs to M5.
- Data truth: the repository-external 2,902-row simulator CSV is only a captured-format sample. It is not a trajectory standard, commanded path, label, or M4 golden input.
- Git boundary: commit each task separately, never push automatically, and stop for a design re-approval if implementation would change an accepted formula, state, threshold, fixture recipe, or ownership boundary.

## Approval-recording precondition before Task 0 — user approval received

The user explicitly approved this replacement plan on 2026-07-13. This authority migration is a docs-only prerequisite, not part of Task 0; it must be committed before deleting provisional files or changing implementation code.

**Files:**
- Modify: `README.md`
- Modify: `docs/product/README.md`
- Modify: `docs/product/01_PRODUCT_OVERVIEW.md`
- Modify: `docs/product/04_REFERENCE_MODEL_V0_1.md`
- Modify: `docs/product/09_VALIDATION_AND_HANDOFF.md`
- Modify: `docs/product/10_DESIGN_SELF_REVIEW.md`
- Modify: `docs/product/11_IMPLEMENTATION_STATUS.md`
- Modify: `docs/product/specs/2026-07-13-m4-anchor-evidence-availability-design.md`
- Modify: `docs/product/specs/2026-07-13-m4-lightweight-workflow-validation-amendment.md`
- Modify: `docs/product/plans/2026-07-13-m4-anchor-evidence-availability-replacement-implementation-plan.md`

Required migration performed by this docs-only change:

1. record the exact approval date and state that execution is authorized from Task 0 under this plan;
2. check only the amendment §8 item for replacement-plan approval; leave every implementation/engineering-verification item unchecked;
3. at approval time, update current entry/status surfaces to record that the replacement plan was approved and implementation had not yet begun;
4. preserve `18/18 specified, 0/18 implemented`, `formal_run_authorized=false`, `engineering_default`, and synthetic `not_supported`;
5. do not edit D-021-D-027 semantics or claim any RED/GREEN/test evidence.

~~~powershell
$approvalFiles = @(
  'README.md',
  'docs/product/README.md',
  'docs/product/01_PRODUCT_OVERVIEW.md',
  'docs/product/04_REFERENCE_MODEL_V0_1.md',
  'docs/product/09_VALIDATION_AND_HANDOFF.md',
  'docs/product/10_DESIGN_SELF_REVIEW.md',
  'docs/product/11_IMPLEMENTATION_STATUS.md',
  'docs/product/specs/2026-07-13-m4-anchor-evidence-availability-design.md',
  'docs/product/specs/2026-07-13-m4-lightweight-workflow-validation-amendment.md',
  'docs/product/plans/2026-07-13-m4-anchor-evidence-availability-replacement-implementation-plan.md'
)
$stalePatterns = @(
  ('replacement plan ' + '尚待'),
  ('replacement plan ' + 'pending'),
  ('Review ' + 'candidate'),
  ('no implementation task is ' + 'authorized'),
  ('still requires separate ' + 'approval')
)
foreach ($pattern in $stalePatterns) {
  $stale = Select-String -Path $approvalFiles -Pattern $pattern -SimpleMatch
  if ($stale) { $stale; throw "replacement-plan approval migration is incomplete: $pattern" }
}
git diff --check
git add -- $approvalFiles
git diff --cached --stat
git commit -m "docs: approve replacement lightweight M4 implementation plan"
~~~

Only after this docs-only authority commit may Task 0 begin. If the approval scope is later changed, pause M4 and revise the plan instead of running implementation commands.

## Subagent-driven execution protocol

For every task after plan approval:

1. Dispatch one fresh implementation subagent with only the task text, approved spec, and current repository state.
2. For a behavior-implementation task, require the subagent to write the RED test first, run it, and report the exact expected failure before production code. For explicitly labeled verification-only Task 1, require the prescribed first-run PASS; any failure follows the task's stop/corrective protocol rather than being treated as intentional RED. Task 36 is evidence/documentation closure and starts from the already passing durable gate.
3. After implementation, dispatch a fresh specification-review subagent. It checks only conformance to the task/spec and returns concrete findings.
4. Fix specification findings, then dispatch a different code-quality-review subagent.
5. Run the task's focused GREEN command and the stated regression command in the primary agent.
6. Inspect `git diff --check`, stage only intentional files, and create the task commit.
7. Immediately before that commit, mark only the current task's completed step checkboxes, stage this plan file in addition to the task-specific `git add` list, and commit code/tests/evidence tracking together. Never pre-check a later task.

A subagent may not edit the approved spec to make its code pass. Test-only generic plans and registries must still be internally complete and explicitly injected; the public API always uses packaged trusted resources.

Every `git add` block below lists the task-specific files. Tasks 0-35 must additionally stage `docs/product/plans/2026-07-13-m4-anchor-evidence-availability-replacement-implementation-plan.md` after checking that task's steps; Task 36 already stages all `docs/product` files. This keeps the tree clean between tasks and makes checkbox state auditable in the same commit as its evidence.

## Frozen public names and module boundaries

The implementation must use these names consistently:

~~~text
legacy read-only contract   pilot_assessment.contracts.anchor.AnchorResult
M4 contract                pilot_assessment.contracts.anchor_v2.AnchorResultV2
public M4 entry             pilot_assessment.anchors.api.evaluate(request, sink)
internal service            pilot_assessment.anchors.service.AnchorEvaluator
public result schema        anchor-result-0.2.0
public report schema        anchor-evaluation-report-0.1.0
reference profile           reference-model-v0.1
packaged registry           pilot_assessment/anchors/registry-v1.json
fixture contract            m4-workflow-smoke-fixture-v1
fixture generator           m4-lightweight-workflow-builder-v1
physical fixture ID         m4-workflow-smoke-v0.1
fixture seed                20260713
~~~

Do not rename the legacy `AnchorResult` import to v0.2. Consumers must opt into `AnchorResultV2`, so no historical reader silently changes semantics.

## Locked production structure

~~~text
src/pilot_assessment/
  contracts/
    anchor.py                              # legacy v0.1, byte-frozen
    anchor_v2.py                           # measurement/result/artifact/trace DTOs
    anchor_execution.py                    # semantic/catalog/plan/inventory/report DTOs
  anchors/
    __init__.py
    api.py
    models.py
    protocols.py
    catalog.py
    fingerprint.py
    registry.py
    reference_resolution.py
    dag.py
    temporal.py
    artifacts.py
    preprocessing.py
    scoring.py
    service.py
    registry-v1.json
    profile_data/
      __init__.py
      reference-model-v0.1-anchor-catalog.json
      parameters/
        __init__.py
        o1-parameters-0.1.json
        o2-parameters-0.1.json
        o3-parameters-0.1.json
        o4-parameters-0.1.json
        o5-parameters-0.1.json
        o6-parameters-0.1.json
        o7-parameters-0.1.json
        o8-parameters-0.1.json
        o9-parameters-0.1.json
        o10-parameters-0.1.json
        o11-parameters-0.1.json
        o12-parameters-0.1.json
        o13-parameters-0.1.json
        h1-parameters-0.1.json
        h2-parameters-0.1.json
        h3-parameters-0.1.json
        h4-parameters-0.1.json
        h5-parameters-0.1.json
        movement-events-v1-parameters-0.1.json
        gaze-aoi-intervals-v1-parameters-0.1.json
        fixation-intervals-v1-parameters-0.1.json
        control-physio-windows-v2-parameters-0.1.json
        ecg-hr-trace-v1-parameters-0.1.json
        eeg-engagement-windows-v1-parameters-0.1.json
    primitives/
      __init__.py
      envelopes.py
      reference_join.py
      movement.py
      events.py
      gaze_aoi.py
      fixation.py
      physio_windows.py
      ecg.py
      eeg.py
    plugins/
      __init__.py
      o1_phase_state_precision.py
      o2_peak_tracking_excursion.py
      o3_terminal_capture_quality.py
      o4_sustained_hover_time.py
      o5_workload_rate.py
      o6_control_magnitude_rms.py
      o7_control_reversal_rate.py
      o8_tpx_composite.py
      o9_dead_band_activity.py
      o10_recovery_time.py
      o11_disturbance_latency.py
      o12_envelope_drift_latency.py
      o13_physio_control_coupling.py
      h1_aoi_dwell.py
      h2_first_fixation_latency.py
      h3_off_task_dwell.py
      h4_ecg_fluctuation.py
      h5_eeg_fluctuation.py
  schema_resources/
    __init__.py
    *.schema.json
  verification/
    __init__.py
    m4_fixture.py
    m4_smoke.py
    profile_data/
      __init__.py
      m4-smoke-fixture-index-v0.1.json
      cases/
        m4-workflow-smoke-v0.1/
          session-semantic-snapshot.json
          resolved-reference-set.json
          execution-plan.json
          runtime-manifest.json

schemas/
  anchor-result-0.2.0.schema.json
  anchor-measurement-0.1.0.schema.json
  anchor-plugin-definition-0.1.0.schema.json
  preprocessing-provider-definition-0.1.0.schema.json
  anchor-catalog-0.1.0.schema.json
  anchor-runtime-registry-0.1.0.schema.json
  anchor-execution-plan-0.1.0.schema.json
  session-semantic-snapshot-0.1.0.schema.json
  resolved-reference-set-0.1.0.schema.json
  anchor-evaluation-report-0.1.0.schema.json

tests/
  __init__.py
  conftest.py
  m4_support/
    __init__.py
    fixture_builder.py
    oracle.py
    micro_inputs.py
    micro_oracles.py
    scenario_inputs.py
    request_builder.py
    extension_plugins.py
  fixtures/m4/
    m4-workflow-smoke-recipe-v0.1.json
    m4-workflow-smoke-expected-v0.1.json
    m4-workflow-smoke-source-hashes-v0.1.json
    m4-scenario-expected-v0.1.json
    cases/
      m4-workflow-smoke-v0.1/
        session-semantic-snapshot.json
        resolved-reference-set.json
        execution-plan.json
        runtime-manifest.json
    extension-catalog-v1.json
    extension-catalog-v2-retired.json
  contracts/
    test_anchor_result_v2.py
    test_anchor_execution.py
  anchors/
    fakes.py
    test_lightweight_fixture_contract.py
    test_catalog.py
    test_fingerprint.py
    test_registry.py
    test_dag.py
    test_temporal.py
    test_artifacts.py
    test_preprocessing.py
    test_scoring.py
    test_service.py
    test_lightweight_scenario_contract.py
    test_reference_profile_completeness.py
    test_no_quality_gate.py
    test_reference_scenarios.py
    test_state_matrix.py
    test_data_to_anchor_perturbations.py
    test_extension_replay.py
    test_cross_process_determinism.py
  e2e/
    test_m4_workflow_smoke_ingestion.py
    test_m4_workflow_smoke.py
    test_m4_source_immutability.py
  verification/
    test_m4_fixture.py
    test_m4_smoke.py

scripts/
  verify_m4.ps1
~~~

## Dependency order and parallel boundary

Task 0 is the specification-required first lightweight fixture RED gate; after observing RED it locks the numeric/JCS dependencies, freezes the one input-only 10-second recipe and its independent exact-18 expected vector, and proves M1-M3 ingestion before any production `AnchorPlugin` exists. Task 1 independently audits that committed runtime lock. Tasks 2-7 establish the M4-A contracts, schemas, catalog, and parameter resources; Task 8 gives those resources canonical identity, closes M4-A, and establishes the first M4-B fingerprint primitive. Tasks 9-13 complete M4-B and may use only injected fake anchor/provider factories; at its completion the packaged catalog contains 18 definitions but both `registry-v1.json` maps still have zero executable entries. Tasks 14-20 implement M4-C, Tasks 21-25 implement M4-D, Tasks 26-28 implement M4-E, and Tasks 29-31 implement M4-F. Tasks 32-33 prove compact real-plugin scenarios, state semantics, perturbations, and extension/replay without physical bundles; Tasks 34-36 run and deliver the single physical M1-to-M4 smoke and close M4.

Within a stage, tasks whose prerequisites are complete may be implemented by separate subagents, but commits remain ordered and each task is reviewed against the repository state produced by all earlier commits.

## Global TDD invariants

Every plugin task must test all of the following in addition to its anchor-specific cases:

- normal Desired, Adequate, and Unacceptable observations;
- exact threshold boundaries and values just outside each boundary;
- phase/event/session aggregation and completion of all breakdown traces;
- relevant missed/no-stable/no-gaze/degenerate override;
- missing input, missing configuration, not-applicable, and dependency behavior;
- parameter change changes parameter/result/evaluation fingerprints;
- deterministic replay and source/aligned view immutability;
- applicable sampling-rate invariance;
- finite but extreme or poor values remain `computed + unacceptable`;
- no result or parameter contains `invalid_quality`, `quality_gates`, `min_valid_coverage`, `failed_quality`, `binary_quality_v1`, or quality likelihood mixing.
- raw/aligned input perturbations change every dependent measurement/result/evaluation fingerprint while at least one explicitly unrelated anchor remains unchanged.

Tests for a new plugin must invoke the injected `AnchorEvaluator` or public `evaluate()` boundary. They must not import the not-yet-created plugin module merely to produce a collection error; RED must fail on missing behavior or capability. Per-anchor tests use `tests/m4_support/micro_inputs.py` for generic compact raw/aligned-table constructors and test-local rows, plus test-local literals or `tests/m4_support/micro_oracles.py` for independent expected values. These helpers create no physical Session Bundle, import no production anchor implementation when calculating expectations, and never contain `AnchorMeasurement`, `AnchorResult`, state, likelihood, or precomputed composite inputs. Task 14 creates the generic helpers; Tasks 15-31 normally add only their own test module data. Any later shared-helper change must be explicitly listed and staged in that task's commit.

## M4 prerequisites

### Task 0: Lock the numeric runtime and freeze the single lightweight workflow-smoke contract

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/m4_support/__init__.py`
- Create: `tests/m4_support/fixture_builder.py`
- Create: `tests/m4_support/oracle.py`
- Create: `tests/fixtures/m4/m4-workflow-smoke-recipe-v0.1.json`
- Create: `tests/fixtures/m4/m4-workflow-smoke-expected-v0.1.json`
- Create: `tests/fixtures/m4/m4-workflow-smoke-source-hashes-v0.1.json`
- Create: `tests/anchors/test_lightweight_fixture_contract.py`
- Create: `tests/e2e/test_m4_workflow_smoke_ingestion.py`
- Remove provisional untracked files only after the safety check: `tests/anchors/__init__.py`, `tests/anchors/test_fixture_contract.py`, `tests/fixtures/m4/fixture-recipe-v1.json`, `tests/fixtures/m4/fixture-manifest-v1.json`, `tests/fixtures/m4/expected-oracle-v1.json`, and the four provisional `tests/fixtures/m4/cases/*/{session-semantic-snapshot,resolved-reference-set}.json` pairs

- [x] **Step 0: Prove the provisional heavy files are disposable and preserve the runtime lock**

Run the following before deleting anything:

~~~powershell
git status --short
git diff -- pyproject.toml uv.lock
$provisional = @(
  'tests/anchors/__init__.py',
  'tests/anchors/test_fixture_contract.py',
  'tests/m4_support/fixture_builder.py',
  'tests/m4_support/oracle.py',
  'tests/fixtures/m4/fixture-recipe-v1.json',
  'tests/fixtures/m4/fixture-manifest-v1.json',
  'tests/fixtures/m4/expected-oracle-v1.json',
  'tests/fixtures/m4/cases/m4-all-desired-v0.1/session-semantic-snapshot.json',
  'tests/fixtures/m4/cases/m4-all-desired-v0.1/resolved-reference-set.json',
  'tests/fixtures/m4/cases/m4-all-unacceptable-v0.1/session-semantic-snapshot.json',
  'tests/fixtures/m4/cases/m4-all-unacceptable-v0.1/resolved-reference-set.json',
  'tests/fixtures/m4/cases/m4-mixed-v0.1/session-semantic-snapshot.json',
  'tests/fixtures/m4/cases/m4-mixed-v0.1/resolved-reference-set.json',
  'tests/fixtures/m4/cases/m4-state-matrix-v0.1/session-semantic-snapshot.json',
  'tests/fixtures/m4/cases/m4-state-matrix-v0.1/resolved-reference-set.json'
)
foreach ($path in $provisional) {
  git ls-files --error-unmatch -- $path 2>$null
  if ($LASTEXITCODE -eq 0) { throw "provisional path is tracked; stop before removal: $path" }
}
~~~

Expected: every provisional path is untracked. The only `pyproject.toml`/`uv.lock` change is the NumPy/SciPy/rfc8785 dependency lock. Remove the listed provisional source/JSON files one by one with `apply_patch`; do not use a recursive delete, reset, or checkout. Ignored `__pycache__` files may remain unstaged. Preserve `pyproject.toml` and `uv.lock` because these are production DSP/JCS dependencies, not heavy-fixture debris.

- [x] **Step 1: Write the lightweight RED contract before any production plugin exists**

The two test modules must initially use only the standard library at collection time and define these gates:

1. `test_lightweight_recipe_identity_rates_and_budget`;
2. `test_recipe_rejects_answer_echo_shapes`;
3. `test_builder_and_oracle_are_independent_of_production_anchors`;
4. `test_expected_vector_is_separate_and_has_exactly_18_ids`;
5. `test_workflow_bundle_runs_public_m1_m2_m3_and_matches_frozen_source_hashes`;
6. `test_dense_assets_are_temporary_and_untracked`.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_lightweight_fixture_contract.py tests/e2e/test_m4_workflow_smoke_ingestion.py -v
~~~

Expected: RED because the lightweight recipe, builder, oracle, and expected resources do not exist. Collection must not fail because NumPy/SciPy/rfc8785 is not yet imported. The tests reject `production_output`, `expected_anchor_results`, serialized `AnchorResult`/`AnchorMeasurement` shapes, precomputed `q_control`, precomputed O8/O13 composites, and anchor-keyed result maps. An AST/import audit rejects `pilot_assessment.anchors` imports from the builder or oracle.

- [x] **Step 2: Lock and audit the numeric/JCS dependencies**

Keep exactly these project dependency ranges:

~~~toml
"numpy>=2.3.4,<2.4",
"rfc8785>=0.1.4,<0.2",
"scipy>=1.17,<1.18",
~~~

~~~powershell
& .\.tools\uv\uv.exe lock --check
if ($LASTEXITCODE -ne 0) { & .\.tools\uv\uv.exe lock }
& .\.tools\uv\uv.exe lock --check
& .\.tools\uv\uv.exe sync --all-groups
& .\.tools\uv\uv.exe run python -c "import numpy, rfc8785, scipy; print(numpy.__version__, scipy.__version__)"
~~~

The oracle must use this locked NumPy/SciPy implementation for the approved DSP definitions and `rfc8785` for canonical JSON. It may not substitute a host package or a simplified standard-library DSP approximation.

- [x] **Step 3: Implement the input-only 10-second builder**

Expose these exact callable boundaries and a matching module CLI:

~~~text
build_fixture(recipe_path: Path, case_id: str, output_root: Path) -> Path
source_hash_manifest(bundle_root: Path) -> dict[str, str]
validate_input_recipe(recipe: Mapping[str, object]) -> None
~~~

Only `case_id="m4-workflow-smoke-v0.1"` is legal. Freeze the accepted amendment's `[0,10 s]` source session, baseline `[0,4)`, Translation `[4,6)`, Deceleration `[6,8)`, Hover `[8,10)`, exact events, X/reference/envelope behavior, U signals, gaze/AOI allocation, R-peaks, EEG recipe, semantic/config bindings, and pilot-camera semantics. Explicitly select `mains_frequency_hz=50` for the smoke EEG profile. Use existing M2/M3 profile IDs, rates, schemas, and identity clock mappings; do not add a high-rate fixture profile or increase M1's default path budget.

Use Decimal/round-half-even for `t_ns=round_half_even(k*1e9/f)`. The deterministic physical budget is:

~~~text
VR RGB8 PNG                         301
pilot-camera RGB8 PNG               151
total PNG                           452
manifest declared-path references   468
physical source-table rows        9,331  (must also remain <= 9,500)
~~~

The 9,331 rows are shared X/U=1,001 physical rows counted once, independent reference=1,001, I index=301, AOI=602, raw G=1,201, one compatibility fixation row ignored by H2, EEG=2,561, ECG=2,501, provided R-peaks=11, and pilot-camera index=151. The 16 non-image manifest references are X/U descriptor references=2 even though they share one path, I index/AOI=2, raw G/compatibility fixation=2, EEG/sidecar=2, ECG/R-peaks=2, pilot-camera index=1, task reference=1, phase/event/baseline annotations=3, and integrity checksum file=1; adding 452 image references yields exactly 468. H2 must later recompute fixation from raw G; the compatibility row cannot feed H2. Generate dense CSV/Parquet/PNG only below the caller-provided temporary root. `tests/conftest.py` exposes one session-scoped `m4_workflow_bundle`, so one pytest process builds the bundle only once. The builder performs M1 self-validation; the ingestion test then uses public M2 and M3 entry points and proves non-blocked output, independent commanded reference, RGB8 decode, source hashes, pilot-camera provenance, `formal_run_authorized=false`, and `scientific_validation_status=not_supported`.

- [x] **Step 4: Freeze an independent exact-18 expected vector without answer echo**

Expose this exact callable and CLI behavior:

~~~text
evaluate_recipe(recipe: Mapping[str, object]) -> dict[str, object]
~~~

`m4-workflow-smoke-expected-v0.1.json` is generated from the input recipe alone, before any production `AnchorPlugin` exists. The oracle does not read the generated bundle, import the builder, import `pilot_assessment.anchors`, or consume a production result. The builder does not import/read the oracle or expected JSON. Production code may never import `tests` or read expected vectors. Source-hash JSON contains only bundle-relative input paths and SHA-256 values.

The oracle must mechanically freeze all O1-O13/H1-H5 raw values, states, overrides, time/count fields, and tolerances. The non-DSP sentinel values are:

~~~text
O1=75% A; O2=3 ft A; O3=capture_missed U; O4=1.5 s U;
O5=1.5 D; O6=70% U; O7=1.5 Hz D;
O8=(0.75^2)*sqrt(1/1.5)=0.4592793267718459 A;
O9=2/1.5=1.3333333333333333 Hz A;
O10=recovery_missed U; O11=250 ms D; O12=150 ms D;
O13≈12.500000129375% A, derived from the exact RR timestamps and worst-phase Q_control=0.75;
H1=85% D; H2=250 ms D; H3=15% U;
H4≈15.00000005175% D, derived from the exact RR timestamps;
H5≈35.0018596859% A, with the canonical value and tolerance generated by the full approved Float32-uV/SciPy §12.18 pipeline using the locked runtime and 50 Hz mains profile.
~~~

Do not round H4/O13/H5 to the displayed approximations in the expected JSON. Persist the oracle's canonical numeric values and tolerances, then have the contract test verify the expected file has exactly the canonical 18 IDs and is byte-stable on regeneration. A later recipe/expected change requires a new fixture version or renewed design approval; production output can never be used to rewrite it.

- [x] **Step 5: Prove the lightweight gate is GREEN and bounded**

~~~powershell
$elapsed = Measure-Command {
  & .\.tools\uv\uv.exe run pytest tests/anchors/test_lightweight_fixture_contract.py tests/e2e/test_m4_workflow_smoke_ingestion.py -v
  if ($LASTEXITCODE -ne 0) { throw 'lightweight fixture gate failed' }
}
$elapsed
& .\.tools\uv\uv.exe lock --check
& .\.tools\uv\uv.exe run ruff format --check tests/m4_support tests/anchors/test_lightweight_fixture_contract.py tests/e2e/test_m4_workflow_smoke_ingestion.py tests/conftest.py
& .\.tools\uv\uv.exe run ruff check tests/m4_support tests/anchors/test_lightweight_fixture_contract.py tests/e2e/test_m4_workflow_smoke_ingestion.py tests/conftest.py
$dense = git ls-files tests/fixtures/m4 | Select-String -Pattern '\.(csv|parquet|png)$'
if ($dense) { $dense; throw 'dense M4 fixture asset is tracked' }
git diff --check
~~~

Expected: PASS. Record elapsed time for the handoff, but do not create a machine-speed assertion. This focused gate targets well below 30 seconds and commits no generated dense asset.

- [x] **Step 6: Commit only the lightweight prerequisite**

~~~powershell
git add pyproject.toml uv.lock tests/__init__.py tests/conftest.py tests/m4_support tests/fixtures/m4/m4-workflow-smoke-recipe-v0.1.json tests/fixtures/m4/m4-workflow-smoke-expected-v0.1.json tests/fixtures/m4/m4-workflow-smoke-source-hashes-v0.1.json tests/anchors/test_lightweight_fixture_contract.py tests/e2e/test_m4_workflow_smoke_ingestion.py
git diff --cached --stat
git commit -m "test: freeze lightweight M4 workflow fixture"
~~~

No production `src/pilot_assessment/anchors/` file may enter this commit, and this task does not run M4 because the production plugins do not yet exist.

### Task 1: Audit the locked M4 numerical and canonicalization runtime

**Files:**
- Modify: `tests/test_package_metadata.py`
- Create: `tests/anchors/test_runtime_dependencies.py`

- [x] **Step 1: Add and run the post-lock dependency/provenance verification**

Assert that the runtime can import `numpy`, `scipy`, and `rfc8785`; that the resolved versions satisfy `numpy>=2.3.4,<2.4`, `scipy>=1.17,<1.18`, and `rfc8785>=0.1.4,<0.2`; and that stable distribution `RECORD` rows can be enumerated/verified without using an absolute installation path, installer-generated launcher, or mutable installation metadata as hash input.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_runtime_dependencies.py tests/test_package_metadata.py -v
~~~

Expected: PASS on first execution because Task 0 has already locked and synced the exact dependencies. This is an explicit verification-only task. If it fails, stop before M4-A and add a separately reviewed corrective task/commit naming the exact `pyproject.toml`/`uv.lock`/test change and rerunning Task 0's lightweight dependency/fixture gate; do not weaken the version, import, or stable-`RECORD` assertions inside Task 1.

- [x] **Step 2: Verify the lock and stable installed-distribution surface**

~~~powershell
& .\.tools\uv\uv.exe lock --check
& .\.tools\uv\uv.exe run python -c "import importlib.metadata as m; print([(n, m.version(n)) for n in ('numpy','scipy','rfc8785')])"
~~~

- [x] **Step 3: Re-run the focused verification**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_runtime_dependencies.py tests/test_package_metadata.py -v
& .\.tools\uv\uv.exe lock --check
~~~

Expected: PASS. Record the exact resolved versions in the task handoff; do not hard-code an environment-specific `RECORD` digest in source.

- [x] **Step 4: Commit**

~~~powershell
git add tests/test_package_metadata.py tests/anchors/test_runtime_dependencies.py
git commit -m "test: verify locked M4 numeric runtime"
~~~

## M4-A: contracts and schemas

### Task 2: Add `AnchorResultV2` without changing legacy v0.1

**Files:**
- Create: `src/pilot_assessment/contracts/anchor_v2.py`
- Modify: `src/pilot_assessment/contracts/__init__.py`
- Create: `tests/contracts/test_anchor_result_v2.py`
- Create: `tests/fixtures/anchor_result_v2_computed.json`
- Modify: `tests/contracts/test_anchor_result.py`

- [x] **Step 1: Write RED tests for the breaking contract**

Freeze these current legacy SHA-256 values in the test:

~~~text
src/pilot_assessment/contracts/anchor.py
8e70b3e8adb65dcf87d8de7f4ae853700f40af62470827e7659b983ef7474526

schemas/anchor-result-0.1.0.schema.json
c8b6cea319c377b8a61923c5f1122c3e70a79b59f054637ff0334082b2deb5f5
~~~

Test computed/non-computed field matrices, finite JSON numbers, exact integer serialization for counts/t_ns, float serialization for continuous metrics, null-primary reasons, breakdown status/trace, one-hot order, result fingerprint shape, and rejection of all v0.1 quality fields/statuses.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/contracts/test_anchor_result.py tests/contracts/test_anchor_result_v2.py -v
~~~

Expected: RED because `AnchorResultV2` does not exist.

- [x] **Step 2: Implement the typed v0.2 result family**

The module must define exactly the public v0.2 fields shown below; adding/removing a public field requires a new contract version:

~~~python
class AnchorCalculationStatusV2(StrEnum):
    COMPUTED = "computed"
    MISSING_INPUT = "missing_input"
    NOT_APPLICABLE = "not_applicable"
    NOT_COMPUTABLE = "not_computable"
    DEPENDENCY_MISSING = "dependency_missing"
    EXTRACTOR_ERROR = "extractor_error"

class MetricValue(StrictContractModel):
    scalar_kind: Literal["integer", "float"]
    value: Int64 | FiniteFloat
    unit: StableId

class ClassificationOverride(StrictContractModel):
    code: StableId
    details: dict[str, JsonValue] = Field(default_factory=dict)

class SourceWindowV2(StrictContractModel):
    window_id: StableId
    start_t_ns: NonNegativeInt64
    end_t_ns: NonNegativeInt64
    phase_id: StableId | None
    event_id: StableId | None
    include_session_terminal_point: StrictBool = False

class AnchorArtifactRef(StrictContractModel):
    artifact_id: StableId
    kind: StableId
    schema_id: StableId
    logical_content_sha256: Sha256Digest
    storage_file_sha256: Sha256Digest | None
    row_count: NonNegativeInt
    start_t_ns: NonNegativeInt64 | None
    end_t_ns: NonNegativeInt64 | None
    grid_hash: Sha256Digest | None
    producer_anchor_id: StableId
    producer_plugin_id: StableId
    producer_plugin_version: StableId
    parameter_hash: Sha256Digest
    dependency_fingerprints: tuple[Sha256Digest, ...]

class ComputationTrace(StrictContractModel):
    sample_count: NonNegativeInt
    source_start_t_ns: NonNegativeInt64 | None
    source_end_t_ns: NonNegativeInt64 | None
    analysis_start_t_ns: NonNegativeInt64 | None
    analysis_end_t_ns: NonNegativeInt64 | None
    grid_id: StableId | None
    window_ids: tuple[StableId, ...]
    interpolation_method: StableId | None
    matching_method: StableId | None
    diagnostics: tuple[DomainErrorData, ...]

class AnchorBreakdownResult(StrictContractModel):
    breakdown_id: StableId
    calculation_status: AnchorCalculationStatusV2
    evidence_state: EvidenceState | None
    evidence_likelihood: EvidenceLikelihood | None
    continuous_score: UnitInterval | None
    primary_value: MetricValue | None
    primary_value_reason: StableId | None
    raw_metrics: dict[StableId, MetricValue]
    classification_override: ClassificationOverride | None
    trace: ComputationTrace
    diagnostics: tuple[DomainErrorData, ...]

class AnchorResultProvenance(StrictContractModel):
    plugin_id: StableId
    plugin_version: StableId
    implementation_digest: Sha256Digest
    parameter_hash: Sha256Digest
    dependency_fingerprints: tuple[Sha256Digest, ...]
    computation_trace: ComputationTrace

class AnchorResultV2(StrictContractModel):
    contract_id: Literal["anchor-result"] = "anchor-result"
    contract_version: Literal["0.2.0"] = "0.2.0"
    anchor_id: StableId
    calculation_status: AnchorCalculationStatusV2
    evidence_state: EvidenceState | None
    evidence_likelihood: EvidenceLikelihood | None
    continuous_score: UnitInterval | None
    primary_value: MetricValue | None
    primary_value_reason: StableId | None
    classification_override: ClassificationOverride | None
    raw_metrics: dict[StableId, MetricValue]
    phase_results: tuple[AnchorBreakdownResult, ...]
    event_results: tuple[AnchorBreakdownResult, ...]
    derived_artifacts: tuple[AnchorArtifactRef, ...]
    diagnostics: tuple[DomainErrorData, ...]
    provenance: AnchorResultProvenance
    result_fingerprint: Sha256Digest
~~~

Model validators must encode design §7 exactly. `scalar_kind=integer` requires a strict JSON integer (never bool or `1.0`), while `scalar_kind=float` requires a finite strict float; the declared measurement schema fixes the kind for every metric ID. Counts and t_ns values therefore remain exact JCS integers. An override may only select Unacceptable; it cannot force Adequate or Desired.

- [x] **Step 3: Run GREEN and verify legacy bytes**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/contracts/test_anchor_result.py tests/contracts/test_anchor_result_v2.py -v
git diff --exit-code -- src/pilot_assessment/contracts/anchor.py schemas/anchor-result-0.1.0.schema.json
~~~

Expected: PASS and no legacy diff.

- [x] **Step 4: Commit**

~~~powershell
git add src/pilot_assessment/contracts/anchor_v2.py src/pilot_assessment/contracts/__init__.py tests/contracts/test_anchor_result.py tests/contracts/test_anchor_result_v2.py tests/fixtures/anchor_result_v2_computed.json
git commit -m "feat: add M4 anchor result v0.2"
~~~

## Task 3 amendment migration precondition — completed

The user explicitly approved the Task 3 Reference Candidate Binding amendment on 2026-07-13 after Tasks 0–2. Candidate commit `5aca9e2` contains the written review artifact; this separate docs-only migration activates D-028 and the revised Task 3 before any Task 3 production file exists. It must not be backdated into the historical pre-Task-0 approval record above.

**Files:**
- Modify: `README.md`
- Modify: `docs/product/README.md`
- Modify: `docs/product/01_PRODUCT_OVERVIEW.md`
- Modify: `docs/product/03_SESSION_BUNDLE_SPEC.md`
- Modify: `docs/product/04_REFERENCE_MODEL_V0_1.md`
- Modify: `docs/product/09_VALIDATION_AND_HANDOFF.md`
- Modify: `docs/product/10_DESIGN_SELF_REVIEW.md`
- Modify: `docs/product/11_IMPLEMENTATION_STATUS.md`
- Modify: `docs/product/DECISIONS.md`
- Modify: `docs/product/GLOSSARY.md`
- Modify: `docs/product/specs/2026-07-13-m4-anchor-evidence-availability-design.md`
- Modify: `docs/product/specs/2026-07-13-m4-lightweight-workflow-validation-amendment.md`
- Modify: `docs/product/specs/2026-07-13-m4-task3-reference-candidate-binding-amendment.md`
- Modify: `docs/product/plans/2026-07-13-m4-anchor-evidence-availability-replacement-implementation-plan.md`
- Create: `docs/product/reviews/README.md`
- Create: `docs/product/reviews/2026-07-13-autonomous-review-ledger.md`

- [x] **Step 1: Activate the approved amendment and D-028**

Record the amendment as approved, add D-028, migrate M4 design §§5–8/15–17, and update every current status surface without claiming Task 3 code or any production plugin.

- [x] **Step 2: Replace all affected plan duties**

Replace Task 3's two-parameter binder and migrate Tasks 4/8/13/32/34/35 plus the coverage matrix exactly as required by amendment §10. Preserve the four-production-file/two-test-file Task 3 boundary and all lightweight test constraints.

- [x] **Step 3: Preserve independent review evidence and verify the docs-only change**

~~~powershell
$required = @(
  'docs/product/03_SESSION_BUNDLE_SPEC.md',
  'docs/product/GLOSSARY.md',
  'docs/product/specs/2026-07-13-m4-task3-reference-candidate-binding-amendment.md',
  'docs/product/reviews/README.md',
  'docs/product/reviews/2026-07-13-autonomous-review-ledger.md'
)
foreach ($path in $required) {
  if (-not (Test-Path -LiteralPath $path)) { throw "missing Task 3 migration artifact: $path" }
}
git diff --cached --check
git diff --cached --stat
~~~

Expected: only the files listed above are staged; two independent internal P1 reviews pass; any completed external read-only review is appended to the ledger; no Python/schema/test file changes. The Git commit containing this checked section is the Task 3 authority-migration commit.

### Task 3: Define semantic and resolved-reference snapshot contracts

**Files:**
- Create: `src/pilot_assessment/contracts/anchor_execution.py`
- Create: `src/pilot_assessment/anchors/__init__.py`
- Create: `src/pilot_assessment/anchors/models.py`
- Create: `src/pilot_assessment/anchors/reference_resolution.py`
- Create: `tests/contracts/test_anchor_execution.py`
- Create: `tests/anchors/test_reference_resolution.py`

- [x] **Step 1: Write the complete lightweight RED matrix from the approved Task 3 amendment**

In `tests/contracts/test_anchor_execution.py`, cover the exact public surface and JSON round trip; strict/frozen/extra-forbid behavior; phase/event/opportunity/session bounds including terminal ownership and event duration; duplicate/dangling IDs; vector dimension/finite/frame/unit rules; dynamic/static AOI geometry; control/baseline/applicability matrices; reference present/absent fields; zero-or-one total descriptor cardinality; and rejection of multiple ModelBundle or mixed bundle/ModelBundle inventories.

In `tests/anchors/test_reference_resolution.py`, use one minimal `AlignedSession` and one two-row Polars table. Cover exact present/absent candidate inventory, session/mapping replay rejection, bundle/ModelBundle ownership, view/DataFrame identity preservation, schema/clock/table/frame/unit/resource/content/alignment mismatches, Decimal scale/drift consistency, stable-row field separation, checksum aliases, artifact side channels, dtype/null/non-finite/order-key/mask violations, and shape-guessing rejection. Do not generate a Session Bundle or execute any anchor.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/contracts/test_anchor_execution.py tests/anchors/test_reference_resolution.py -v
~~~

Expected: RED because `pilot_assessment.contracts.anchor_execution` and the `pilot_assessment.anchors` runtime binder do not exist. Record the exact import/collection failure before creating production files.

- [x] **Step 2: Implement the approved serializable contracts and internal runtime boundary**

Implement every field, enum, canonical-order validator and cross-reference rule from the approved Task 3 amendment §§4–6 in `contracts/anchor_execution.py`. Reuse common strict types and `BundleRelativePath` safety semantics without changing `contracts/common.py`; do not export JSON Schema in this task. Use strict Pydantic for serializable snapshots and frozen dataclasses for objects containing Polars views:

~~~python
@dataclass(frozen=True, slots=True)
class ReferenceViewCandidate:
    reference_id: StableId
    source_kind: ReferenceSourceKind
    session_identity: ReferenceSessionIdentity
    aligned_view: AlignedStreamView
    alignment_contract: ReferenceAlignmentContract
    table_contract: ReferenceTableContract
    resource_fingerprint: Sha256Digest
    aligned_content_fingerprint: Sha256Digest
    alignment_fingerprint: Sha256Digest


@dataclass(frozen=True, slots=True)
class ResolvedReference:
    descriptor: ResolvedReferenceDescriptor
    aligned_view: AlignedStreamView | None

@dataclass(frozen=True, slots=True)
class ResolvedReferenceSet:
    session_identity: ReferenceSessionIdentity
    entries: Mapping[str, ResolvedReference]
    reference_set_fingerprint: Sha256Digest

~~~

`SessionSemanticSnapshot` and `ResolvedReferenceSetSnapshot` are the serializable `0.1.0` contracts. `ReferenceViewCandidate`, `ResolvedReference`, and `ResolvedReferenceSet` are internal frozen runtime dataclasses and must never serialize an `AlignedStreamView`. Freeze mappings through `MappingProxyType`; preserve the original descriptor, view and DataFrame object identities.

The binder is exact:

~~~python
def bind_resolved_reference_snapshot(
    snapshot: ResolvedReferenceSetSnapshot,
    aligned_session: AlignedSession,
    candidates: Mapping[str, ReferenceViewCandidate],
) -> ResolvedReferenceSet:
    """Bind only exact, independently described reference candidates."""
~~~

Implement the exact session gate, candidate inventory, source ownership, table/schema/frame/unit/resource/alignment comparisons and stable `ReferenceBindingError.code` allowlist from amendment §8. Task 3 validates declared digests and Decimal scale/drift consistency but does not compute canonical fingerprints; Task 8 owns those callables. Bundle provenance against `SynchronizationReport` belongs to Task 4 request construction. An explicitly absent descriptor remains an entry with `aligned_view=None`; any present mismatch fails and never degrades to absent. Do not add a reference-table non-empty requirement or any performance/data-quality gate.

- [x] **Step 3: Run GREEN**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/contracts/test_anchor_execution.py tests/anchors/test_reference_resolution.py -v
~~~

Expected: PASS. Runtime reference views remain immutable, the exact three-parameter binder passes the approved matrix, and no M3 contract or production AnchorPlugin is changed.

- [x] **Step 4: Commit**

~~~powershell
git add src/pilot_assessment/contracts/anchor_execution.py src/pilot_assessment/anchors/__init__.py src/pilot_assessment/anchors/models.py src/pilot_assessment/anchors/reference_resolution.py tests/contracts/test_anchor_execution.py tests/anchors/test_reference_resolution.py
git commit -m "feat: define M4 semantic and reference contracts"
~~~

### Task 4: Define plugin, catalog, dependency, and execution-plan contracts

**Files:**
- Modify: `src/pilot_assessment/contracts/anchor_execution.py`
- Modify: `src/pilot_assessment/anchors/models.py`
- Create: `tests/contracts/test_anchor_catalog_plan.py`
- Create: `tests/anchors/test_request_validation.py`

- [ ] **Step 1: Write RED contract-matrix tests**

Test exact dependency kinds, plugin/API/version identities, parameter schema/hash, temporal recipe, scorer policy, canonical order, required/optional policy, the exact catalog lifecycle enum and active-only execution-entry literal, artifact recipes, scientific status, and the complete serialized runtime-registry field matrix. Require strict rejection of unknown/missing registry fields, duplicate anchor/provider keys, duplicate artifact recipe IDs, any deprecated/retired execution entry, duplicate/unsorted input-table keys, empty/duplicate input fields, unknown/nested/alias input dtypes, inconsistent stream schemas within one modality, missing contracts for a required modality, contracts for an unused modality, or non-CoreModality `required_streams`. Artifact dependencies must resolve one exact producer recipe/kind/schema; also reject provider parameter-schema mismatches, context/semantic path namespace ambiguity, provider-dependency cycles, cross-`scope_policy` provider edges, duplicate IDs, non-finite parameters, unknown dependency kinds, semantic cycles represented in the contract, a client-supplied `test_only_partial_plan` field, and all quality-gate field names. The request test covers aligned/semantic/resolved-output session identity plus source/synchronization/semantic/reference/plan fingerprint agreement. It first proves exact two-way equivalence between report `aligned` modalities and `aligned_session.streams`, rejecting both aligned-without-view and non-aligned-with-view as `request_session_mismatch`. It then proves every aligned plan-required core stream has exact live table-role inventory, stream-level schema against `AlignedStreamView`, table-role-level schema against `SynchronizationReport`, full ordered names/primitive dtypes, and zero nulls in non-nullable columns; nullable columns may contain nulls or not. Optional `not_attempted/unavailable/invalid/unsupported/not_applicable` states each pass without a view and later yield per-anchor `missing_input` when required by the plan; required-for-import non-aligned is already an M3 blocked case. A dynamic AOI source always resolves one exact I plan input-table contract and matches its table-level schema, coordinate frame, frame/AOI keys, ordered geometry fields and geometry unit; only when I is aligned does it also require the live I view/report/table exact match. It also proves `set(snapshot.applicability.anchor_id) == set(plan.entries.anchor_id)`; missing/extra/cross-revision applicability fails with `request_semantic_identity_mismatch` before service access. Required reference descriptor IDs must equal the union of every `AnchorExecutionEntry.required_reference_ids` and `ResolvedPreprocessingRecipe.required_reference_ids`; all execution entries are active by construction. Missing/extra IDs reject request construction, while a structurally valid explicit absent entry remains available for downstream `not_computable`.

Add minimal M3 provenance cases: a present bundle reference must exactly match `SynchronizationReport.task_reference_result` reference ID, source, aligned status, clock method/scale/offset/drift, source/aligned schema and checksums, and its mapping policy must match `SynchronizationReport.policy.policy_id`; bundle absent accepts no record or the same ID's legal non-aligned bundle record but cannot hide an aligned/different-source record. A ModelBundle reference requires the same ID, `source=model_bundle`, and `deferred_model_bundle_resolution` before accepting the M6 mapping contract. Any mismatch fails before `AnchorEvaluationRequest` exists and leaves evaluator/plugin/provider/sink calls at zero. A real M3 `SynchronizationOutcome` with `disposition=blocked` has `aligned_session=None` and must fail at the same boundary.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/contracts/test_anchor_catalog_plan.py tests/anchors/test_request_validation.py -v
~~~

Expected: RED because the DTO family is incomplete.

- [ ] **Step 2: Implement the catalog/plan contract and request**

The dependency enum is exact:

~~~python
class DependencyKind(StrEnum):
    RESULT = "result_dependency"
    ARTIFACT = "artifact_dependency"
    ALGORITHM_PROFILE = "algorithm_profile_dependency"
    PREPROCESSING = "preprocessing_dependency"
~~~

Only result/artifact dependencies create anchor-to-anchor DAG edges. Algorithm-profile dependencies resolve frozen resources. Preprocessing dependencies resolve versioned dynamic products through their own provider dependency order and evaluation-local memoization; they do not move H1/H3 or O13 into false anchor topology levels.

The public contract fields are exact:

~~~text
ScientificValidationStatus values:
  engineering_default, expert_reviewed, calibrated,
  internally_validated, externally_validated, not_supported

AnchorLifecycle values:
  active, deprecated, retired

AnchorDependency:
  dependency_id: StableId
  kind: DependencyKind
  target_anchor_id: StableId | None
  target_resource_id: StableId | None
  expected_schema_id: StableId | None
  expected_artifact_kind: StableId | None
  required: StrictBool

AnchorArtifactRecipe:
  artifact_id: StableId
  kind: StableId
  schema_id: StableId
  schema_descriptor: dict[StableId, JsonValue]
  payload_kind: Literal["table", "blob"]

PreprocessingDependencySpec:
  dependency_id: StableId
  expected_schema_id: StableId
  expected_artifact_kind: StableId

ResolvedPreprocessingDependencyBinding:
  dependency_id: StableId
  target_recipe_id: StableId

AnchorPluginDefinition:
  contract_id="anchor-plugin-definition", contract_version="0.1.0"
  anchor_id, definition_version, plugin_id, plugin_version, api_version
  required_streams: tuple[CoreModality, ...]
  required_context_paths, required_semantic_paths,
  required_reference_ids, dependencies, parameter_schema_id,
  measurement_schema_id, artifact_recipes

PreprocessingProviderDefinition:
  contract_id="preprocessing-provider-definition", contract_version="0.1.0"
  provider_id: StableId
  provider_version: StableId
  api_version: Literal["0.1.0"]
  required_streams: tuple[CoreModality, ...]
  required_context_paths: tuple[StableId, ...]
  required_semantic_paths: tuple[StableId, ...]
  required_reference_ids: tuple[StableId, ...]
  dependencies: tuple[PreprocessingDependencySpec, ...]
  parameter_schema_id: StableId
  output_schema_id: StableId
  output_schema_descriptor: dict[StableId, JsonValue]
  artifact_kind: StableId
  output_payload_kind: Literal["table", "blob"]

ContentMemberIdentity:
  package_relative_path: str
  content_sha256: Sha256Digest

PythonRuntimeIdentity:
  implementation_name: str
  version: tuple[int, int, int]
  cache_tag: str
  soabi: str

NumericRuntimeIdentity:
  normalized_name: str
  version: str
  record_content_sha256: Sha256Digest

PluginRegistryEntry:
  anchor_id: StableId
  definition_version: StableId
  plugin_id: StableId
  plugin_version: StableId
  api_version: Literal["0.1.0"]
  factory_module: str
  factory_symbol: str
  allowed_package_namespace: str
  definition_fingerprint: Sha256Digest
  parameter_schema_id: StableId
  parameter_schema_sha256: Sha256Digest
  measurement_schema_id: StableId
  measurement_schema_sha256: Sha256Digest
  artifact_schema_hashes: dict[StableId, Sha256Digest]
  implementation_members: tuple[ContentMemberIdentity, ...]
  resource_members: tuple[ContentMemberIdentity, ...]
  python_runtime: PythonRuntimeIdentity
  numeric_runtimes: tuple[NumericRuntimeIdentity, ...]
  implementation_digest: Sha256Digest

PreprocessingRegistryEntry:
  provider_id: StableId
  provider_version: StableId
  api_version: Literal["0.1.0"]
  factory_module: str
  factory_symbol: str
  allowed_package_namespace: str
  definition_fingerprint: Sha256Digest
  parameter_schema_id: StableId
  parameter_schema_sha256: Sha256Digest
  output_schema_id: StableId
  output_schema_sha256: Sha256Digest
  artifact_kind: StableId
  output_payload_kind: Literal["table", "blob"]
  implementation_members: tuple[ContentMemberIdentity, ...]
  resource_members: tuple[ContentMemberIdentity, ...]
  python_runtime: PythonRuntimeIdentity
  numeric_runtimes: tuple[NumericRuntimeIdentity, ...]
  implementation_digest: Sha256Digest

AnchorRuntimeRegistry:
  contract_id="anchor-runtime-registry", contract_version="0.1.0"
  entries: tuple[PluginRegistryEntry, ...]
  preprocessors: tuple[PreprocessingRegistryEntry, ...]

AnchorCatalogEntry:
  anchor_id, definition_version
  lifecycle: AnchorLifecycle
  required, canonical_order
  plugin_id, plugin_version, parameter_schema_id, scorer_id
  required_inputs, dependencies, artifact_recipes

AnchorCatalog:
  contract_id="anchor-catalog", contract_version="0.1.0"
  profile_id, profile_version, scientific_validation_status
  entries, catalog_fingerprint

ResolvedAlgorithmProfile:
  profile_id, profile_version, parameters, parameter_hash,
  implementation_digest, output_schema_id

ResolvedInputFieldContract:
  field_name: StableId
  dtype_id: StableId
  unit: UnitName
  nullable: StrictBool

ResolvedInputTableContract:
  modality: CoreModality
  table_role: StableId
  stream_aligned_schema_id: StableId
  table_aligned_schema_id: StableId
  coordinate_frame_id: StableId
  fields: tuple[ResolvedInputFieldContract, ...]

ResolvedPreprocessingRecipe:
  recipe_id: StableId
  recipe_version: StableId
  provider_id: StableId
  provider_version: StableId
  api_version: Literal["0.1.0"]
  definition_fingerprint: Sha256Digest
  implementation_digest: Sha256Digest
  parameter_schema_id: StableId
  parameter_schema_sha256: Sha256Digest
  parameters: dict[StableId, JsonValue]
  parameter_hash: Sha256Digest
  required_streams: tuple[CoreModality, ...]
  required_context_paths: tuple[StableId, ...]
  required_semantic_paths: tuple[StableId, ...]
  required_reference_ids: tuple[StableId, ...]
  dependency_specs: tuple[PreprocessingDependencySpec, ...]
  dependency_bindings: tuple[ResolvedPreprocessingDependencyBinding, ...]
  output_schema_id: StableId
  output_schema_descriptor: dict[StableId, JsonValue]
  output_schema_sha256: Sha256Digest
  artifact_kind: StableId
  output_payload_kind: Literal["table", "blob"]
  scope_policy: Literal["session", "phase", "event", "window"]

ScorerPolicy:
  scorer_id: StableId
  scorer_version: StableId
  policy_schema_id: StableId
  parameters: dict[StableId, JsonValue]
  policy_hash: Sha256Digest

AnchorExecutionEntry:
  anchor_id, definition_version
  lifecycle: Literal["active"]
  canonical_order
  plugin_id, plugin_version, api_version, definition_fingerprint,
  implementation_digest
  parameter_schema_id, parameters, parameter_hash
  required_streams: tuple[CoreModality, ...]
  required_context_paths, required_semantic_paths,
  required_reference_ids
  applicability, phase_scope, event_scope, dependencies
  measurement_schema_id, result_schema_id, artifact_recipes
  temporal_recipe, scorer_policy

AnchorExecutionPlan:
  contract_id="anchor-execution-plan", contract_version="0.1.0"
  plan_id, model_profile_id, scientific_validation_status
  catalog_fingerprint, registry_fingerprint, source_snapshot_fingerprint,
  synchronization_fingerprint, semantic_snapshot_fingerprint,
  reference_set_fingerprint, entries, input_table_contracts, algorithm_profiles,
  preprocessing_recipes, parameter_fingerprint, plan_fingerprint
~~~

`input_table_contracts` is the M5-compiled complete table projection of locked profiles for exactly the core modalities in the union of active `AnchorExecutionEntry.required_streams` and `ResolvedPreprocessingRecipe.required_streams`; it is not metadata inferred from live values. Contracts are unique and canonically ordered by `(modality, table_role)`; every required modality has at least one, no unused modality has one, fields are non-empty/name-unique/in physical DataFrame order, and `dtype_id` uses exactly `bool/i8/i16/i32/i64/u8/u16/u32/u64/f32/f64/utf8` with a fixed Polars primitive mapping. Nested dtypes, aliases, and unknown strings reject the plan. `stream_aligned_schema_id` binds `AlignedStreamView.aligned_schema_id`; `table_aligned_schema_id` binds `SynchronizationReport.stream_results[modality].artifacts[table_role].aligned_schema_id`.

Before table validation, request construction requires `set(aligned_session.streams) == {m | synchronization_report.stream_results[m].synchronization_status == aligned}`. Report-aligned/view-missing and report-non-aligned/view-injected both raise `request_session_mismatch`. A non-blocked M3 report may legitimately leave an optional stream in `not_attempted/unavailable/invalid/unsupported/not_applicable`; each has no live view or exact-table check, and a plan that needs it later produces per-anchor `missing_input` with that status as the reason. A required-for-import non-aligned stream already makes M3 blocked and cannot enter the request.

For every aligned required stream, request construction requires its live table-role inventory to equal the plan inventory and validates both schema levels, complete ordered columns/dtypes, and non-nullable columns; nullable columns may contain nulls or not. A dynamic AOI always finds exactly one `(I, dynamic_source.table_role)` contract and matches `dynamic_source.aligned_schema_id` to the contract's table-level schema plus coordinate frame, key fields, ordered geometry fields and unit. Only when I is aligned does it also require the live I view/report/table match. Core-stream finite/range constraints remain owned by the M1-M3 structural contracts and are not rescanned here. This is contract validation, never a performance/data-quality gate.

`preprocessing_dependency` targets a `ResolvedPreprocessingRecipe`: it is a dynamic, memoized session/scope product such as movement events, gaze-AOI intervals, fixation intervals, R-peak/HR traces, or EEG windows. It is not merely a static profile and is not an anchor DAG edge. A provider definition declares stable dependency slots plus expected schema/kind; each resolved recipe copies that complete definition projection into `dependency_specs` and binds every slot exactly once through `dependency_bindings` to one plan-unique `target_recipe_id`, with no extras. Provider IDs are never used as dependency targets. In v0.1 every bound provider-to-provider edge must have the same `scope_policy` at both ends; plan validation rejects a cross-policy edge rather than inventing session/phase/event/window projection semantics. Task 13 implements its resolver/cache.

All serialized DTOs above, including the runtime registry and both runtime-identity DTOs, are strict Pydantic contract models in `contracts/anchor_execution.py`; Task 8 computes their values and Task 9 consumes the same models rather than defining a second registry representation. Typed derived/preprocessing table/blob schemas are authoritative inline canonical descriptors: each `AnchorArtifactRecipe.schema_descriptor` and `PreprocessingProviderDefinition.output_schema_descriptor` is the only schema bytes for that ID/version. A table descriptor must declare its ordered fields and `canonical_order_keys`; a blob descriptor must declare its byte/media contract and has no order keys. Task 8 hashes `[schema_id, descriptor]`; registry refresh recomputes `artifact_schema_hashes`/`output_schema_sha256` from those descriptors, and emitter/resolver require exact descriptor/payload-kind equality plus exact `TabularArtifactPayload.order_keys == descriptor.canonical_order_keys` before publication. No implementation may look for an undeclared schema file or infer a descriptor/order from observed rows. `artifact_schema_hashes` has canonical schema-ID order when serialized, and registry validation binds every declared schema/resource hash before a factory can be resolved. Each `AnchorExecutionEntry` and `ResolvedPreprocessingRecipe` carries enough immutable definition fields plus `definition_fingerprint` to reconstruct its strict plugin/provider definition and compare it to the registry snapshot without importing or calling a factory. Only after complete request/plan/registry/DAG validation may the factory be resolved; its live `definition()` must then equal the already validated snapshot before `compute()`. Anchor/provider `required_context_paths` resolve only against `AlignedSession.context`; `required_semantic_paths` resolve only against `SessionSemanticSnapshot` and populate `ProjectedSemanticScope`. Bare or cross-namespace paths are rejected, so one declaration can never be routed to both projections. Every artifact dependency names `(target_anchor_id, target_resource_id)`; `target_resource_id` must match exactly one recipe `artifact_id` in that producer definition/plan entry, with matching kind/schema, or plan validation blocks.

M4 validates/executes `AnchorExecutionPlan`; it does not compile a ModelBundle into one.

Add the final immutable runtime request only after `AnchorExecutionPlan` exists:

~~~python
@dataclass(frozen=True, slots=True)
class AnchorEvaluationRequest:
    aligned_session: AlignedSession
    synchronization_report: SynchronizationReport
    session_semantic_snapshot: SessionSemanticSnapshot
    execution_plan: AnchorExecutionPlan
    resolved_references: ResolvedReferenceSet
~~~

`AnchorRequestValidationError(ValueError)` is the stable pre-request exception. Its v0.1 `code` allowlist is `request_session_mismatch`, `request_semantic_identity_mismatch`, `request_reference_inventory_mismatch`, `request_reference_provenance_mismatch`, and `request_fingerprint_mismatch`; details identify the failed field without embedding a path or mutable object representation.

`AnchorEvaluationRequest` is intentionally a non-blocked-M3 request: `aligned_session` and the semantic/reference snapshots are not optional, `synchronization_report.disposition` must be non-blocked, and `can_continue_to_anchor_availability` must be true. Its constructor first validates exact report/view inventory equivalence, then complete session/source/synchronization/window identity, M3 annotation identity, every aligned required core stream against the frozen input-table contracts, dynamic AOI against its frozen contract and, when I is aligned, the current I view, exact applicability equality with `execution_plan.entries`, the exact required-reference union, and the bundle/ModelBundle provenance rules above before any service access. Candidate inventory/ownership/identity/table mismatch has already failed in Task 3 with `ReferenceBindingError`; the request contains only the successful `ResolvedReferenceSet` and never accepts a candidate. A blocked M3 outcome or post-binding semantic/reference/provenance closure mismatch raises `AnchorRequestValidationError`, stops request construction, and cannot be converted into an M4 report. A legitimately non-aligned optional `not_attempted/unavailable/invalid/unsupported/not_applicable` required-by-plan stream has no injected view and does not fail request construction; affected anchors later return `missing_input` with the status reason. Task 8 fingerprints are not yet implemented here; Task 13 later performs their canonical recomputation at every evaluator entry. `AnchorEvaluationReport.disposition=blocked` is reserved for failures that arise after a valid request can be constructed, such as an incompatible/invalid plan, registry, schema, dependency graph, or final transaction.

- [ ] **Step 3: Run GREEN**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/contracts/test_anchor_catalog_plan.py tests/anchors/test_request_validation.py -v
~~~

Expected: PASS; public DTOs reject undeclared fields, the public request has no test-only bypass, blocked M3 and every semantic/reference/provenance mismatch fail before request construction, explicit absent remains representable, and no evaluator/plugin/provider/sink call occurs for a pre-request failure.

- [ ] **Step 4: Commit**

~~~powershell
git add src/pilot_assessment/contracts/anchor_execution.py src/pilot_assessment/anchors/models.py tests/contracts/test_anchor_catalog_plan.py tests/anchors/test_request_validation.py
git commit -m "feat: define M4 catalog and plan contracts"
~~~

### Task 5: Define measurement, artifact, inventory, and report contracts

**Files:**
- Modify: `src/pilot_assessment/contracts/anchor_v2.py`
- Modify: `src/pilot_assessment/contracts/anchor_execution.py`
- Create: `src/pilot_assessment/anchors/protocols.py`
- Create: `tests/contracts/test_anchor_measurement_report.py`
- Create: `tests/fixtures/anchor_evaluation_report_ready.json`

- [ ] **Step 1: Write RED status/disposition tests**

Cover capability `available/plugin_unavailable/not_implemented/incompatible`, plan `compiled/blocked`, inventory `executed/not_attempted`, result status, and report `ready/ready_partial/blocked` as distinct enums. Assert that every executed inventory item references exactly one canonical `results` entry, non-blocked reference runs can expose all 18 `AnchorResultV2` objects for M5, blocked reports have expected/not-attempted inventory but no fabricated result, and raw availability is `computed_count/applicable_count` with computed U included and zero denominator represented by null. Freeze both callable signatures, including the plugin's current-entry `temporal_recipe`, its narrow `AnchorArtifactEmitter`, and the provider's resolved `PreprocessingScope` plus dependency projection; introspection tests reject a complete request/plan/transaction/cache parameter or any commit/abort/resolve member on the emitter.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/contracts/test_anchor_measurement_report.py -v
~~~

Expected: RED because measurement/report models do not exist.

- [ ] **Step 2: Implement the exact models and invariants**

Expose exactly these contract and runtime field sets; adding/removing a public contract field requires a new contract version:

~~~text
AnchorBreakdownMeasurement:
  breakdown_id: StableId
  calculation_status: AnchorCalculationStatusV2
  primary_value: MetricValue | None
  primary_value_reason: StableId | None
  raw_metrics: dict[StableId, MetricValue]
  classification_override_candidate: ClassificationOverride | None
  trace: ComputationTrace
  diagnostics: tuple[DomainErrorData, ...]

AnchorMeasurement:
  contract_id="anchor-measurement", contract_version="0.1.0"
  anchor_id: StableId
  calculation_status: AnchorCalculationStatusV2
  primary_value: MetricValue | None
  primary_value_reason: StableId | None
  raw_metrics: dict[StableId, MetricValue]
  phase_results: tuple[AnchorBreakdownMeasurement, ...]
  event_results: tuple[AnchorBreakdownMeasurement, ...]
  classification_override_candidate: ClassificationOverride | None
  source_windows: tuple[SourceWindowV2, ...]
  derived_artifacts: tuple[AnchorArtifactRef, ...]
  trace: ComputationTrace
  diagnostics: tuple[DomainErrorData, ...]

AnchorInventoryItem:
  anchor_id: StableId
  capability_status: AnchorCapabilityStatus
  evaluation_status: AnchorInventoryStatus
  result_fingerprint: Sha256Digest | None
  global_block_reason: StableId | None
  diagnostics: tuple[DomainErrorData, ...]

AnchorPluginContext (frozen runtime dataclass):
  session_id: str
  session_window: SessionWindow
  streams: Mapping[str, AlignedStreamView]              # declared streams only
  context: Mapping[str, JsonValue]                      # declared paths only
  references: Mapping[str, ResolvedReference]           # declared IDs only
  semantic_scope: ProjectedSemanticScope                # declared phase/event/AOI paths only

ProjectedSemanticScope (frozen runtime dataclass):
  values: Mapping[str, JsonValue]

ArtifactProducer (frozen runtime dataclass):
  anchor_id: str
  plugin_id: str
  plugin_version: str
  implementation_digest: Sha256Digest
  parameter_hash: Sha256Digest
  dependency_fingerprints: tuple[Sha256Digest, ...]

AnchorArtifactEmitter (narrow runtime protocol):
  stage_table(artifact_id: str, payload: TabularArtifactPayload) -> AnchorArtifactRef
  stage_blob(artifact_id: str, payload: BlobArtifactPayload) -> AnchorArtifactRef

PreprocessingScope (frozen runtime dataclass):
  kind: Literal["session", "phase", "event", "window"]
  scope_id: str
  start_t_ns: int
  end_t_ns: int
  phase_id: str | None
  event_id: str | None
  window_id: str | None

PreprocessingProducer (frozen runtime dataclass):
  recipe_id: str
  recipe_version: str
  provider_id: str
  provider_version: str
  implementation_digest: Sha256Digest
  parameter_schema_id: str
  parameter_schema_sha256: Sha256Digest
  parameter_hash: Sha256Digest
  output_schema_id: str
  output_schema_sha256: Sha256Digest
  artifact_kind: str
  output_payload_kind: Literal["table", "blob"]
  scope_kind: Literal["session", "phase", "event", "window"]
  scope_id: str
  scope_start_t_ns: int
  scope_end_t_ns: int
  phase_id: str | None
  event_id: str | None
  window_id: str | None
  dependency_fingerprints: tuple[Sha256Digest, ...]

ResolvedArtifactDependency (frozen runtime dataclass):
  ref: AnchorArtifactRef
  payload: ReadOnlyTabularPayload | ReadOnlyBlobPayload

PreprocessingArtifactIdentity (frozen runtime dataclass):
  recipe_id: str
  recipe_version: str
  provider_id: str
  provider_version: str
  implementation_digest: Sha256Digest
  parameter_schema_id: str
  parameter_schema_sha256: Sha256Digest
  parameter_hash: Sha256Digest
  scope_kind: Literal["session", "phase", "event", "window"]
  scope_id: str
  scope_start_t_ns: int
  scope_end_t_ns: int
  phase_id: str | None
  event_id: str | None
  window_id: str | None
  schema_id: str
  schema_sha256: Sha256Digest
  artifact_kind: str
  payload_kind: Literal["table", "blob"]
  logical_content_sha256: Sha256Digest
  dependency_fingerprints: tuple[Sha256Digest, ...]

ResolvedPreprocessingDependency (frozen runtime dataclass):
  identity: PreprocessingArtifactIdentity
  payload: ReadOnlyTabularPayload | ReadOnlyBlobPayload

ResolvedDependencies (frozen runtime dataclass):
  results: Mapping[str, AnchorResultV2]
  artifacts: Mapping[str, ResolvedArtifactDependency]
  algorithm_profiles: Mapping[str, ResolvedAlgorithmProfile]
  preprocessing: Mapping[str, ResolvedPreprocessingDependency]

TabularArtifactPayload (frozen runtime dataclass):
  schema_id: str
  schema_descriptor: Mapping[str, JsonValue]
  frame: pl.DataFrame
  order_keys: tuple[str, ...]
  artifact_kind: str
  grid_hash: Sha256Digest | None
  start_t_ns: int | None
  end_t_ns: int | None

BlobArtifactPayload (frozen runtime dataclass):
  schema_id: str
  payload_bytes: bytes
  artifact_kind: str
  start_t_ns: int | None
  end_t_ns: int | None

ReadOnlyTabularPayload and ReadOnlyBlobPayload expose the same fields as their
payload counterparts, but clone/freeze the frame or bytes at construction and
add logical_content_sha256: Sha256Digest.
~~~

The report contract is:

~~~python
class AnchorEvaluationReport(StrictContractModel):
    contract_id: Literal["anchor-evaluation-report"] = "anchor-evaluation-report"
    contract_version: Literal["0.1.0"] = "0.1.0"
    session_id: StableId
    disposition: AnchorEvaluationDisposition
    inventory: tuple[AnchorInventoryItem, ...]
    results: tuple[AnchorResultV2, ...]
    expected_count: NonNegativeInt
    executed_count: NonNegativeInt
    applicable_count: NonNegativeInt
    computed_count: NonNegativeInt
    raw_availability: UnitInterval | None
    catalog_fingerprint: Sha256Digest
    registry_fingerprint: Sha256Digest
    execution_plan_fingerprint: Sha256Digest
    evaluation_fingerprint: Sha256Digest
    formal_run_authorized: Literal[False] = False
    scientific_validation_status: ScientificValidationStatus
    diagnostics: tuple[DomainErrorData, ...]
~~~

`AnchorArtifactRef` must distinguish logical content hash from optional storage-file hash and distinguish `sample_mask` from window/event traces.

`results` is canonical catalog order and is the direct M5 consumption surface. An inventory item's result fingerprint must resolve to exactly one member of `results`; `not_attempted` items cannot reference a result. `scientific_validation_status` must equal the frozen execution-plan field: normal `reference-model-v0.1` plans start as `engineering_default`, while every synthetic fixture plan is explicitly `not_supported`.

After `AnchorMeasurement` exists, define the exact production plugin boundary:

~~~text
AnchorPlugin.definition() -> AnchorPluginDefinition
AnchorPlugin.compute(
    context: AnchorPluginContext,
    parameters: Mapping[str, JsonValue],
    temporal_recipe: Mapping[str, JsonValue],
    dependencies: ResolvedDependencies,
    artifacts: AnchorArtifactEmitter
) -> AnchorMeasurement

PreprocessingProvider.definition() -> PreprocessingProviderDefinition
PreprocessingProvider.compute(
    context: AnchorPluginContext,
    recipe: ResolvedPreprocessingRecipe,
    scope: PreprocessingScope,
    dependencies: Mapping[str, ResolvedPreprocessingDependency]
) -> TabularArtifactPayload | BlobArtifactPayload
~~~

The service constructs `AnchorPluginContext` by two explicit positive projections: `context` only from declared `required_context_paths`, and `semantic_scope` only from declared `required_semantic_paths`; it never passes the complete `AnchorEvaluationRequest`, complete `AlignedSession.streams`, or undeclared references/context/semantics to plugin/provider code. A plugin receives only its current execution entry's immutable `temporal_recipe`, never the complete plan or another anchor's recipe. Its `AnchorArtifactEmitter` exposes staging only: no commit, abort, resolve, other producer, or storage path. Each `stage_*` call names one declared `artifact_id`; the emitter rejects an unknown/duplicate recipe ID or payload kind/schema mismatch, so two artifacts with the same kind/schema remain unambiguous. Emitted IDs must be a declaration-order subsequence of `artifact_recipes`, which makes public artifact order deterministic while allowing a declared recipe not to emit for a particular calculation state. A provider receives the one resolved scope instance selected under its recipe's `scope_policy`; its dependency map contains only the already resolved provider-definition dependency slots, keyed by `dependency_id` after plan bindings resolve each unique `target_recipe_id`, so it cannot see sibling products or the cache. The provider parameter object is validated against the registry-bound parameter schema before provider factory/compute access. Both `PreprocessingProducer` and `PreprocessingArtifactIdentity` copy the complete scope (kind, ID, bounds, and phase/event/window identity), and that complete identity enters every downstream dependency fingerprint even when two scopes happen to produce identical payload bytes. The read-only payload wrappers expose cloned/frozen table views or immutable bytes and carry the logical hash used by dependency fingerprints.

- [ ] **Step 3: Run GREEN**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/contracts/test_anchor_measurement_report.py -v
~~~

Expected: PASS; result/inventory cardinalities are canonical, report scientific status is copied from the plan, and runtime protocol objects expose only the exact positive projections above.

- [ ] **Step 4: Commit**

~~~powershell
git add src/pilot_assessment/contracts/anchor_v2.py src/pilot_assessment/contracts/anchor_execution.py src/pilot_assessment/anchors/protocols.py tests/contracts/test_anchor_measurement_report.py tests/fixtures/anchor_evaluation_report_ready.json
git commit -m "feat: define M4 measurement and report contracts"
~~~

### Task 6: Export all M4 schemas and package them in the wheel

**Files:**
- Modify: `src/pilot_assessment/schemas/export.py`
- Create: `src/pilot_assessment/schema_resources/__init__.py`
- Create: `src/pilot_assessment/schema_resources/*.schema.json`
- Create: `schemas/anchor-result-0.2.0.schema.json`
- Create: `schemas/anchor-measurement-0.1.0.schema.json`
- Create: `schemas/anchor-plugin-definition-0.1.0.schema.json`
- Create: `schemas/preprocessing-provider-definition-0.1.0.schema.json`
- Create: `schemas/anchor-catalog-0.1.0.schema.json`
- Create: `schemas/anchor-runtime-registry-0.1.0.schema.json`
- Create: `schemas/anchor-execution-plan-0.1.0.schema.json`
- Create: `schemas/session-semantic-snapshot-0.1.0.schema.json`
- Create: `schemas/resolved-reference-set-0.1.0.schema.json`
- Create: `schemas/anchor-evaluation-report-0.1.0.schema.json`
- Modify: `tests/schemas/test_schema_export.py`
- Modify: `tests/test_package_metadata.py`

- [ ] **Step 1: Write RED export/symmetry tests**

Require deterministic root and package-resource bytes, Draft 2020-12 IDs/titles, public fixtures validating against schemas, `formal_run_authorized=false`, and explicit schema rejection of `invalid_quality` and quality-gate fields. Freeze the v0.1 root schema hash.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/schemas/test_schema_export.py tests/test_package_metadata.py -v
~~~

Expected: RED because M4 schemas/resources are absent.

- [ ] **Step 2: Extend the authoritative exporter**

Render every schema from the Pydantic contract and write the same bytes atomically to root `schemas/` and package `schema_resources/`. Do not hand-edit committed JSON.

~~~powershell
& .\.tools\uv\uv.exe run python -m pilot_assessment.schemas.export
~~~

- [ ] **Step 3: Prove schema symmetry and build inclusion**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/contracts tests/schemas/test_schema_export.py tests/test_package_metadata.py -q
& .\.tools\uv\uv.exe run python -m pilot_assessment.schemas.export
git diff --exit-code -- schemas src/pilot_assessment/schema_resources
& .\.tools\uv\uv.exe build
~~~

Expected: PASS; a second export is byte-identical and the wheel contains every M4 schema resource.

- [ ] **Step 4: Commit and record the M4-A gate**

~~~powershell
git add src/pilot_assessment/schemas/export.py src/pilot_assessment/schema_resources schemas tests/schemas/test_schema_export.py tests/test_package_metadata.py
git commit -m "feat: publish M4 contract schemas"
~~~

After this commit the only valid claim is: `M4-A contract/schema slice complete; catalog resources and canonical identity remain Tasks 7-8; 18/18 specified; 0/18 plugins implemented; formal_run_authorized=false`.

### Task 7: Package the exact-18 reference catalog and all editable parameter schemas

**Files:**
- Create: `src/pilot_assessment/anchors/catalog.py`
- Create: `src/pilot_assessment/anchors/profile_data/__init__.py`
- Create: `src/pilot_assessment/anchors/profile_data/reference-model-v0.1-anchor-catalog.json`
- Create: `src/pilot_assessment/anchors/profile_data/parameters/__init__.py`
- Create: `src/pilot_assessment/anchors/profile_data/parameters/o1-parameters-0.1.json`
- Create: `src/pilot_assessment/anchors/profile_data/parameters/o2-parameters-0.1.json`
- Create: `src/pilot_assessment/anchors/profile_data/parameters/o3-parameters-0.1.json`
- Create: `src/pilot_assessment/anchors/profile_data/parameters/o4-parameters-0.1.json`
- Create: `src/pilot_assessment/anchors/profile_data/parameters/o5-parameters-0.1.json`
- Create: `src/pilot_assessment/anchors/profile_data/parameters/o6-parameters-0.1.json`
- Create: `src/pilot_assessment/anchors/profile_data/parameters/o7-parameters-0.1.json`
- Create: `src/pilot_assessment/anchors/profile_data/parameters/o8-parameters-0.1.json`
- Create: `src/pilot_assessment/anchors/profile_data/parameters/o9-parameters-0.1.json`
- Create: `src/pilot_assessment/anchors/profile_data/parameters/o10-parameters-0.1.json`
- Create: `src/pilot_assessment/anchors/profile_data/parameters/o11-parameters-0.1.json`
- Create: `src/pilot_assessment/anchors/profile_data/parameters/o12-parameters-0.1.json`
- Create: `src/pilot_assessment/anchors/profile_data/parameters/o13-parameters-0.1.json`
- Create: `src/pilot_assessment/anchors/profile_data/parameters/h1-parameters-0.1.json`
- Create: `src/pilot_assessment/anchors/profile_data/parameters/h2-parameters-0.1.json`
- Create: `src/pilot_assessment/anchors/profile_data/parameters/h3-parameters-0.1.json`
- Create: `src/pilot_assessment/anchors/profile_data/parameters/h4-parameters-0.1.json`
- Create: `src/pilot_assessment/anchors/profile_data/parameters/h5-parameters-0.1.json`
- Create: `src/pilot_assessment/anchors/profile_data/parameters/movement-events-v1-parameters-0.1.json`
- Create: `src/pilot_assessment/anchors/profile_data/parameters/gaze-aoi-intervals-v1-parameters-0.1.json`
- Create: `src/pilot_assessment/anchors/profile_data/parameters/fixation-intervals-v1-parameters-0.1.json`
- Create: `src/pilot_assessment/anchors/profile_data/parameters/control-physio-windows-v2-parameters-0.1.json`
- Create: `src/pilot_assessment/anchors/profile_data/parameters/ecg-hr-trace-v1-parameters-0.1.json`
- Create: `src/pilot_assessment/anchors/profile_data/parameters/eeg-engagement-windows-v1-parameters-0.1.json`
- Create: `src/pilot_assessment/anchors/registry-v1.json`
- Create: `tests/anchors/test_catalog.py`
- Modify: `tests/test_package_metadata.py`

- [ ] **Step 1: Write RED catalog/resource tests**

Assert exact reference order:

~~~text
O1 O2 O3 O4 O5 O6 O7 O8 O9 O10 O11 O12 O13 H1 H2 H3 H4 H5
~~~

Assert 18 unique active anchor definitions, stable versions, declared input/typed-dependency/artifact/scorer schemas, lifecycle, canonical order, one parameter schema resource per anchor definition, and six separately named preprocessing parameter schemas for the six reference provider recipes. Reject duplicate IDs/order, an exact-reference catalog with 17 or 19 entries, a missing/extra provider parameter schema, and any parameter schema containing a prohibited quality field. Also prove a generic test catalog can have cardinality other than 18. Canonical catalog/parameter fingerprints are added in Task 8 after the JCS primitive exists.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_catalog.py tests/test_package_metadata.py -v
~~~

Expected: RED because packaged resources/loaders do not exist.

- [ ] **Step 2: Implement catalog loading without executable plugins**

Expose:

~~~text
load_packaged_catalog(profile_id: str = "reference-model-v0.1") -> AnchorCatalog
load_parameter_schema(schema_id: str) -> Mapping[str, JsonValue]
~~~

`load_parameter_schema` performs one deterministic package lookup at `pilot_assessment.anchors.profile_data/parameters/<schema_id>.json`; `schema_id` is a separator-free `StableId` equal to the filename stem. It never scans or guesses aliases. Freeze every design §12 engineering default, unit, boundary policy, temporal recipe, scorer ID, and typed dependency in the catalog/parameter resources. `registry-v1.json` must be valid but contain both `"entries": []` and `"preprocessors": []`; M4-B must not pretend any anchor algorithm or shared preprocessing provider is implemented.

- [ ] **Step 3: Run GREEN and package-resource regression**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_catalog.py tests/test_package_metadata.py -v
& .\.tools\uv\uv.exe build
~~~

Expected: PASS; the wheel contains the exact catalog plus all 24 explicit parameter resources (18 anchor + 6 preprocessing), while executable anchor/provider capability remains honestly empty.

- [ ] **Step 4: Commit**

~~~powershell
git add src/pilot_assessment/anchors/catalog.py src/pilot_assessment/anchors/profile_data src/pilot_assessment/anchors/registry-v1.json tests/anchors/test_catalog.py tests/test_package_metadata.py
git commit -m "feat: package M4 reference anchor catalog"
~~~

## M4-B: execution framework with injected fake plugins

### Task 8: Implement RFC 8785 typed fingerprints and numeric runtime identity

**Files:**
- Create: `src/pilot_assessment/anchors/fingerprint.py`
- Modify: `src/pilot_assessment/anchors/catalog.py`
- Modify: `src/pilot_assessment/anchors/profile_data/reference-model-v0.1-anchor-catalog.json`
- Create: `tests/anchors/test_fingerprint.py`
- Modify: `tests/anchors/test_catalog.py`

- [ ] **Step 1: Write RED canonical-byte vectors**

Cover JCS map ordering, Unicode, ECMAScript numbers, rejection of NaN/Infinity, the exact NUL/uint64 framing, canonical inline schema-descriptor hashes, canonical tabular row order, logical-vs-storage hashes, absolute-path exclusion, Python implementation/version/ABI identity, runtime distribution identity, definition/implementation/registry/catalog/parameter/plan/result/evaluation fingerprints, and equal hashes across fresh subprocesses. Add the six Task 3 amendment reference/semantic fingerprints and prove that any resource checksum, frame/unit/table field, row value/order, session/window, clock/schema, mapping method/policy/scale/offset/drift/rounding/mask mutation changes the appropriate digest. Explicitly prove that changing any valid `ResolvedInputFieldContract`/`ResolvedInputTableContract` member—including modality/table role, either schema level, frame, unit, dtype, nullable, or physical field order—changes `plan_fingerprint`. Reordering the outer table-contract tuple is non-canonical and must be rejected before hashing; no alternate fingerprint is expected for that invalid object. Build/install the same locked wheel/runtime into two different temporary venv roots and require identical numeric-runtime identities, specifically guarding against path-bearing generated console launchers. Prove that changing a self-reported fingerprint/digest field or `storage_file_sha256` does not change the corresponding canonical payload/hash, while changing any inline schema descriptor, logical result field, logical artifact identity, upstream dependency fingerprint, catalog field, plan field, parameter, or registry/preprocessor entry does. Separately prove that a changed self-reported fingerprint/digest is rejected by validation rather than silently trusted.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_fingerprint.py -v
~~~

Expected: RED because M4 fingerprint functions do not exist.

- [ ] **Step 2: Implement the fixed callable surface**

~~~text
jcs_bytes(value: object) -> bytes
typed_json_sha256(type_id: str, schema_version: str, value: object) -> str
schema_descriptor_sha256(
    schema_id: str,
    descriptor: Mapping[str, JsonValue]
) -> str
logical_table_sha256(
    schema_id: str,
    schema_descriptor: Mapping[str, JsonValue],
    rows: Sequence[Mapping[str, JsonValue]],
    order_keys: Sequence[str]
) -> str
session_semantic_snapshot_fingerprint(
    snapshot: SessionSemanticSnapshot
) -> Sha256Digest
reference_table_contract_fingerprint(
    contract: ReferenceTableContract
) -> Sha256Digest
reference_resource_fingerprint(
    descriptor: ResolvedReferenceDescriptor
) -> Sha256Digest
aligned_reference_content_fingerprint(
    table: pl.DataFrame,
    aligned_schema_id: StableId,
    contract: ReferenceTableContract
) -> Sha256Digest
reference_alignment_fingerprint(
    descriptor: ResolvedReferenceDescriptor,
    session_identity: ReferenceSessionIdentity
) -> Sha256Digest
resolved_reference_set_fingerprint(
    snapshot: ResolvedReferenceSetSnapshot
) -> Sha256Digest
distribution_content_identity(distribution_name: str) -> NumericRuntimeIdentity
python_runtime_identity() -> PythonRuntimeIdentity
logical_artifact_identity_payload(ref: AnchorArtifactRef) -> dict[str, JsonValue]
validate_logical_artifact_ref(
    ref: AnchorArtifactRef,
    resolved: ResolvedArtifactDependency
) -> None
anchor_result_fingerprint_payload(result: AnchorResultV2) -> dict[str, JsonValue]
evaluation_fingerprint_payload(report: AnchorEvaluationReport) -> dict[str, JsonValue]
catalog_fingerprint_payload(catalog: AnchorCatalog) -> dict[str, JsonValue]
execution_plan_fingerprint_payload(plan: AnchorExecutionPlan) -> dict[str, JsonValue]
plugin_definition_fingerprint(definition: AnchorPluginDefinition) -> str
preprocessing_definition_fingerprint(definition: PreprocessingProviderDefinition) -> str
plugin_implementation_digest_payload(entry: PluginRegistryEntry) -> dict[str, JsonValue]
preprocessing_implementation_digest_payload(
    entry: PreprocessingRegistryEntry
) -> dict[str, JsonValue]
runtime_registry_fingerprint(registry: AnchorRuntimeRegistry) -> str
packaged_catalog_fingerprint(profile_id: str = "reference-model-v0.1") -> str
parameter_snapshot_fingerprint(parameters: Mapping[str, JsonValue]) -> str
~~~

`typed_json_sha256` must compute exactly:

~~~text
SHA256(ASCII(type_id) || 0x00 || ASCII(schema_version) || 0x00 ||
       uint64_big_endian(len(JCS(value))) || JCS(value))
~~~

The runtime identities are the exact strict `PythonRuntimeIdentity` and `NumericRuntimeIdentity` contract models defined in Task 4; Task 8 constructs them and does not introduce parallel dataclasses:

~~~text
PythonRuntimeIdentity:
  implementation_name: str
  version: tuple[int, int, int]
  cache_tag: str
  soabi: str

NumericRuntimeIdentity:
  normalized_name: str
  version: str
  record_content_sha256: Sha256Digest
~~~

`PythonRuntimeIdentity` reads `sys.implementation.name`, exact major/minor/micro, `sys.implementation.cache_tag`, and `sysconfig.get_config_var("SOABI")`; a missing ABI tag is rejected for a production registry entry. Distribution identity covers normalized name, exact version, and a deterministic digest of stable wheel-content declarations:

1. parse the installed distribution's CSV `RECORD`;
2. normalize each member to POSIX form and retain only rows whose path stays inside the site-packages distribution root (no absolute path and no `..` component), has a declared `sha256` digest and size, and is not the `RECORD` file itself, `INSTALLER`, `REQUESTED`, or `direct_url.json`;
3. recompute every retained installed file's SHA-256/size and reject a mismatch with the declared row;
4. hash the JCS canonical lexicographically ordered arrays `[relative_path, "sha256", declared_urlsafe_digest, size]`.

This intentionally excludes installer-generated `../../Scripts/*` launchers whose bytes embed a venv path, mutable install metadata, cache files, and the installation root, while still detecting changes to stable package code/native libraries/resources.

The module CLI `python -m pilot_assessment.anchors.fingerprint runtime-identity numpy scipy rfc8785` emits one canonical JSON array for the two-venv equality test and later build diagnostics.

The canonical projections are fixed as follows:

1. `logical_artifact_identity_payload` includes every `AnchorArtifactRef` field except `storage_file_sha256`; no path, compression option, writer metadata, host, or wall time enters it.
2. `anchor_result_fingerprint_payload` includes every `AnchorResultV2` field except `result_fingerprint`; each `derived_artifacts` member is replaced by `logical_artifact_identity_payload(ref)` in declared order.
3. `evaluation_fingerprint_payload` is a pure projection: it includes every report field except `evaluation_fingerprint`; `results` is replaced by canonical-order `result_fingerprint` values, and a second canonical-order list contains the logical artifact identity payloads reachable from those results. It does not pretend that a ref alone contains payload bytes.
4. `catalog_fingerprint_payload` and `execution_plan_fingerprint_payload` include every public field except their own `catalog_fingerprint` or `plan_fingerprint`, respectively. The plan therefore binds its case-specific source, synchronization, semantic, reference, catalog, registry, parameters, recipes, provider identities, and ordered execution entries.
5. `schema_descriptor_sha256` hashes the canonical array `[schema_id, descriptor]` with type `typed-inline-schema-descriptor`/version `0.1.0`; the same schema ID cannot appear with two descriptors in one definition/plan. Each definition fingerprint hashes the complete strict model dump with its contract type/version. Each implementation-digest payload includes every corresponding registry-entry field except `implementation_digest`; it therefore binds the definition fingerprint, all recomputed inline/packaged schema hashes, exact factory/namespace binding, sorted implementation/resource members, Python identity, and sorted numeric runtime identities without a self-reference. `runtime_registry_fingerprint` hashes the complete validated `AnchorRuntimeRegistry`, including every declared implementation digest and both ordered maps; the registry has no self-fingerprint field.
6. Immediately before result/evaluation hashing, the service recomputes each result self-fingerprint, resolves every `AnchorArtifactRef` through the live `EvaluationArtifactTransaction`, and calls `validate_logical_artifact_ref(ref, resolved)` to recompute logical content from the immutable payload. Only after all checks pass does it call the pure evaluation projection. A mismatched request/catalog/plan/result dependency fingerprint blocks before execution when it is an input contract mismatch. A plugin-emitted measurement/artifact/result self-mismatch maps only that anchor to `extractor_error`; it is never repaired by trusting the claimed hash.

The six semantic/reference functions use the exact type IDs, versions and canonical payload exclusions in the approved Task 3 amendment §6.4. In particular, resource identity binds ordered checksums; aligned content binds its explicit `aligned_schema_id` argument, ordered fields, every logical row and canonical order keys; alignment identity binds complete `ReferenceSessionIdentity` plus complete mapping contract; set identity excludes only its own self-field. Task 8 computes these values but does not resolve a source or construct a candidate.

- [ ] **Step 3: Run GREEN twice in separate processes**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_fingerprint.py tests/anchors/test_catalog.py -v
& .\.tools\uv\uv.exe run pytest tests/anchors/test_fingerprint.py tests/anchors/test_catalog.py -v
~~~

Expected: both runs PASS with byte-identical typed hashes; storage-only changes preserve logical hashes, and every logical tamper vector is either rejected or changes the downstream hash exactly as specified.

- [ ] **Step 4: Commit**

~~~powershell
git add src/pilot_assessment/anchors/fingerprint.py src/pilot_assessment/anchors/catalog.py src/pilot_assessment/anchors/profile_data/reference-model-v0.1-anchor-catalog.json tests/anchors/test_fingerprint.py tests/anchors/test_catalog.py
git commit -m "feat: add canonical M4 fingerprints"
~~~

After this commit the only valid claim is: `M4-A complete; M4-B fingerprint primitive established; 18/18 specified; 0/18 plugins implemented; formal_run_authorized=false`.

### Task 9: Implement the trusted packaged registry and implementation-closure verifier

**Files:**
- Create: `src/pilot_assessment/anchors/registry.py`
- Create: `tests/anchors/fakes.py`
- Create: `tests/anchors/test_registry.py`
- Modify: `tests/test_package_metadata.py`

- [ ] **Step 1: Write RED registry security/identity tests**

Test exact-version anchor and preprocessing-provider lookup, duplicate key/digest/binding rejection in each namespace, namespace allowlists, no directory scanning, no entry points, no `eval`, definition/parameter/measurement/output/artifact schema hash verification, local import closure under/over-declaration, dynamic local import rejection, numeric-runtime allowlist equality, duplicate/invalid provider-definition dependency-slot rejection, and implementation digest changes for source/resource/runtime/schema changes. CLI tests start from `entries=[]` and `preprocessors=[]`; monkeypatched allowlisted modules prove the exact anchor/provider bootstrap forms without creating a fake production implementation. Explicitly reject omitted factory bindings for absent entries, external namespaces, missing symbols, non-callables, unbound provider parameter schemas, and definition/catalog/recipe identity mismatches before factory compute access. Target-recipe resolution, recipe-level cycles, schema/kind compatibility, and scope-policy compatibility belong to Task 13 plan validation because targets and `scope_policy` are frozen in `ResolvedPreprocessingRecipe`, not the registry entry.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_registry.py tests/test_package_metadata.py -v
~~~

Expected: RED because the registry loader/verifier does not exist.

- [ ] **Step 2: Implement trusted resolution and test-only injection**

~~~text
PluginKey = tuple[str, str]
PreprocessorKey = tuple[str, str]

Registry payload types:
  ContentMemberIdentity, PythonRuntimeIdentity, NumericRuntimeIdentity,
  PluginRegistryEntry, PreprocessingRegistryEntry, AnchorRuntimeRegistry
  are imported unchanged from contracts.anchor_execution (Task 4)

PluginCapability (frozen runtime dataclass):
  status: AnchorCapabilityStatus
  entry: PluginRegistryEntry | None
  diagnostics: tuple[DomainErrorData, ...]

PreprocessingCapability (frozen runtime dataclass):
  status: Literal["available", "provider_unavailable", "not_implemented", "incompatible"]
  entry: PreprocessingRegistryEntry | None
  diagnostics: tuple[DomainErrorData, ...]

PluginRegistry.capability(plugin_id: str, plugin_version: str) -> PluginCapability
PluginRegistry.resolve(
    plugin_id: str,
    plugin_version: str,
    implementation_digest: str
) -> AnchorPlugin
PluginRegistry.preprocessing_capability(
    provider_id: str,
    provider_version: str
) -> PreprocessingCapability
PluginRegistry.resolve_preprocessor(
    provider_id: str,
    provider_version: str,
    implementation_digest: str
) -> PreprocessingProvider
PluginRegistry.from_factories_for_testing(
    factories: Mapping[PluginKey, Callable[[], AnchorPlugin]],
    preprocessors: Mapping[PreprocessorKey, Callable[[], PreprocessingProvider]]
) -> PluginRegistry
load_packaged_registry() -> PluginRegistry
packaged_registry_fingerprint() -> str
verify_implementation_closure(entry: PluginRegistryEntry) -> None
verify_preprocessing_closure(entry: PreprocessingRegistryEntry) -> None
~~~

`registry-v1.json` is parsed directly as `AnchorRuntimeRegistry` and has the exact top-level fields `contract_id="anchor-runtime-registry"`, `contract_version="0.1.0"`, `entries`, and `preprocessors`. No loader-local or dataclass shadow DTO is allowed. Parameter schemas resolve only through `profile_data/parameters/<schema_id>.json`; exported measurement/report contract schemas resolve only through `schema_resources/<schema-id>.schema.json`; derived artifact and preprocessing output schemas resolve only from the factory definition's inline canonical descriptors. The verifier hashes the authoritative bytes/descriptor for each class and rejects any declared hash mismatch before factory resolution. Anchor cardinality is computed only from `entries`; provider entries never count toward 18/18. The registry fingerprint is computed from the complete canonical model dump and therefore binds both ordered maps.

The module CLI must implement these exact forms:

~~~text
python -m pilot_assessment.anchors.registry verify
python -m pilot_assessment.anchors.registry refresh --anchor <ID>
python -m pilot_assessment.anchors.registry refresh --anchor <ID> \
  --factory-module pilot_assessment.anchors.plugins.<module> \
  --factory-symbol create_plugin
python -m pilot_assessment.anchors.registry refresh-preprocessor --provider <ID> \
  --factory-module pilot_assessment.anchors.primitives.<module> \
  --factory-symbol create_provider
~~~

`<ID>` and `<module>` are CLI metavariables, not unresolved file paths. An absent entry requires explicit factory module/symbol; an existing entry reuses its stored binding. Each command imports only that explicit allowlisted module, never scans. `refresh` derives definition/schema/member/resource/runtime hashes from the factory and replaces only that anchor's entry deterministically; `refresh-preprocessor` does the same only in the independent provider map. Both report old/new digests. During this first unpublished implementation plan, every change to a shared closure member must refresh every already-registered anchor/provider consumer in the same task. After Task 34 establishes the first freeze boundary, a later behavior-closure change requires a new plugin/provider version and model revision rather than an in-place historical rewrite.

The public loader imports only explicitly listed `pilot_assessment.anchors.plugins.*` anchor factories and `pilot_assessment.anchors.primitives.*` preprocessing factories. Fake factories live under tests and are reachable only through `from_factories_for_testing`.

- [ ] **Step 3: Prove the empty production registry reports 0/18 honestly**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_registry.py tests/anchors/test_catalog.py -v
~~~

Expected: PASS. Because all 18 packaged definitions exist and the registry is empty, all 18 reference capabilities are exactly `not_implemented`; no result exists.

- [ ] **Step 4: Commit**

~~~powershell
git add src/pilot_assessment/anchors/registry.py tests/anchors/fakes.py tests/anchors/test_registry.py tests/test_package_metadata.py
git commit -m "feat: add trusted anchor plugin registry"
~~~

### Task 10: Implement segment-aware temporal support, grids, and windows

**Files:**
- Create: `src/pilot_assessment/anchors/temporal.py`
- Create: `tests/anchors/test_temporal.py`

- [ ] **Step 1: Write RED support/gap/grid golden tests**

Test stable `(t_ns, source_row_id)` ordering, strict `delta > gap_threshold_ns` splitting, equality not splitting, duplicate timestamps adding no duration, no extension across gaps, terminal extension only to explicit semantic end, half-open phase clipping, Decimal round-half-even grids, nearest ties to earlier timestamp/stable row, no extrapolation, and M3 `gap_count/max_gap_ns` mismatch raising `AnchorRequestValidationError(code="request_semantic_identity_mismatch")` with no M4 report.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_temporal.py -v
~~~

Expected: RED because M4 temporal primitives are absent.

- [ ] **Step 2: Implement immutable temporal primitives**

~~~python
@dataclass(frozen=True, slots=True)
class SupportInterval:
    start_t_ns: int
    end_t_ns: int
    source_row_index: int

@dataclass(frozen=True, slots=True)
class TemporalSupport:
    intervals: tuple[SupportInterval, ...]
    segment_bounds: tuple[tuple[int, int], ...]
    observed_duration_ns: int
    gap_count: int
    max_gap_ns: int | None

~~~

Required callables:

~~~text
reconstruct_point_support(
    frame: pl.DataFrame,
    timestamp_column: str,
    stable_keys: Sequence[str],
    in_session_column: str,
    gap_threshold_ns: int | None,
    semantic_end_t_ns: int | None
) -> TemporalSupport
validate_reported_gap_metrics(
    support: TemporalSupport,
    reported: PointTemporalArtifactMetrics
) -> None
~~~

`validate_reported_gap_metrics` is reused by the Task 13 shared request validator. A count/max mismatch raises `AnchorRequestValidationError(code="request_semantic_identity_mismatch")`; it is never converted into a blocked report or per-anchor status.

The remaining callable surface is exact:

~~~text
decimal_grid_v1(start_t_ns: int, end_t_ns: int, rate_hz: Decimal) -> tuple[int, ...]
left_hold_integral_v1(values: Sequence[float], support: TemporalSupport) -> float
nearest_within_v1(
    left_t_ns: Sequence[int], right_t_ns: Sequence[int],
    right_stable_ids: Sequence[str], tolerance_ns: int
) -> tuple[int | None, ...]
build_semantic_windows_v1(
    semantic_scope: ProjectedSemanticScope,
    temporal_recipe: Mapping[str, JsonValue]
) -> tuple[SourceWindowV2, ...]
~~~

None accepts a coverage threshold.

- [ ] **Step 3: Run GREEN and source-view immutability checks**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_temporal.py tests/synchronization/test_models.py -v
~~~

Expected: PASS; all temporal outputs are stable under input view cloning and no operation crosses a reconstructed gap.

- [ ] **Step 4: Commit**

~~~powershell
git add src/pilot_assessment/anchors/temporal.py tests/anchors/test_temporal.py
git commit -m "feat: add segment-aware M4 temporal support"
~~~

### Task 11: Implement transactional content-addressed artifact publication

**Files:**
- Create: `src/pilot_assessment/anchors/artifacts.py`
- Modify: `src/pilot_assessment/anchors/protocols.py`
- Create: `tests/anchors/test_artifacts.py`

- [ ] **Step 1: Write RED transaction tests**

Cover independent per-anchor staging, contract validation before publish, read-after-anchor-commit within the same evaluation, immutable payload resolution for downstream levels, abort on plugin/schema failure, global abort on final report commit failure, logical table hash independent of path/compression/writer metadata, opaque blob logical/storage equality, descriptor-declared canonical row order, sample-mask/window-trace kind separation, and zero writes inside Session Bundle. Freeze the least-capability emitter surface: it can only stage table/blob payloads against the immutable recipe table supplied at `begin_anchor` and cannot commit, abort, resolve, enumerate another producer, or discover a storage path. Add explicit rejection probes for an unknown or duplicate artifact ID, out-of-declaration-order staging, kind/schema/payload-kind/descriptor/order-key mismatch, two declared IDs sharing kind/schema but remaining separately addressable, an unstaged returned ref, a staged-but-unreturned ref, reordered returned refs, duplicate refs, and a staged payload whose ref is altered before return.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_artifacts.py -v
~~~

Expected: RED because the sink protocols have no implementation.

- [ ] **Step 2: Implement protocol and in-memory reference sink**

~~~text
DerivedArtifactSink.begin_evaluation(evaluation_key: str) -> EvaluationArtifactTransaction
EvaluationArtifactTransaction.begin_anchor(
    producer: ArtifactProducer,
    artifact_recipes: tuple[AnchorArtifactRecipe, ...]
) -> AnchorArtifactTransaction
EvaluationArtifactTransaction.resolve(
    ref: AnchorArtifactRef
) -> ResolvedArtifactDependency
EvaluationArtifactTransaction.stage_preprocessing(
    producer: PreprocessingProducer,
    payload: TabularArtifactPayload | BlobArtifactPayload
) -> ResolvedPreprocessingDependency
EvaluationArtifactTransaction.commit() -> None
EvaluationArtifactTransaction.abort() -> None
AnchorArtifactTransaction.emitter() -> AnchorArtifactEmitter
AnchorArtifactTransaction.staged_refs() -> tuple[AnchorArtifactRef, ...]
AnchorArtifactTransaction.commit() -> tuple[AnchorArtifactRef, ...]
AnchorArtifactTransaction.abort() -> None
~~~

`begin_anchor()` freezes the current entry's exact recipe map together with an `ArtifactProducer` containing the current anchor ID; it rejects duplicate recipe IDs before returning an emitter. `AnchorArtifactTransaction.emitter()` returns the narrow `AnchorArtifactEmitter` protocol from Task 5; its `stage_table(artifact_id, ...)`/`stage_blob(artifact_id, ...)` methods look up that exact recipe, validate/clone the payload kind/schema, compute a ref with the producer anchor/plugin identity, and append it to transaction-owned canonical order. Unknown or duplicate emissions are rejected; artifact identity never falls back to kind/schema. The transaction itself owns commit/abort and is never passed to plugin code. Before commit, the service must require exact ordered equality between `measurement.derived_artifacts` and `transaction.staged_refs()`; any missing, extra, duplicate, reordered, mutated, or otherwise schema-invalid ref aborts that anchor and maps to `extractor_error`. `AnchorArtifactTransaction.commit()` revalidates its staged payload set and makes it resolvable inside the evaluation transaction but does not publish it outside that transaction. `EvaluationArtifactTransaction.resolve()` verifies the complete ref/logical hash and returns an immutable payload handle; after abort it must reject every handle. `stage_preprocessing()` validates/clones a provider payload, computes `PreprocessingArtifactIdentity`, and returns an evaluation-local immutable handle; preprocessing products are never added to an anchor's public `derived_artifacts`. Provide `InMemoryDerivedArtifactSink` for tests/smoke. M6 will later own managed durable storage.

- [ ] **Step 3: Run GREEN**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_artifacts.py -v
~~~

Expected: PASS; downstream reads resolve immutable logical payloads only after anchor commit, and evaluation abort leaves no published artifact.

- [ ] **Step 4: Commit**

~~~powershell
git add src/pilot_assessment/anchors/artifacts.py src/pilot_assessment/anchors/protocols.py tests/anchors/test_artifacts.py
git commit -m "feat: add transactional M4 artifact sink"
~~~

### Task 12: Implement central scoring and breakdown aggregation

**Files:**
- Create: `src/pilot_assessment/anchors/scoring.py`
- Create: `tests/anchors/test_scoring.py`

- [ ] **Step 1: Write RED scorer tests**

Test higher-is-better `>=`, lower-is-better `<=`, open/closed asymmetric boundaries, conjunction, worst/veto, pooled numerators/denominators, one-hot state order, continuous scores 0/0.5/1, override allowlist, and the session non-computed priority `extractor_error > dependency_missing > missing_input > not_computable`. Prove diagnostics/coverage/gaps/sync flags cannot affect evidence.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_scoring.py -v
~~~

Expected: RED because no central scorer exists.

- [ ] **Step 2: Implement policy-based scoring without anchor-ID switches**

~~~text
score_measurement(
    measurement: AnchorMeasurement,
    policy: ScorerPolicy,
    provenance: AnchorResultProvenance
) -> AnchorResultV2
~~~

Register scorer behavior by versioned `scorer_id`, not by O/H ID. A computed-U override remains computed and participates in the declared aggregation. If any applicable breakdown is non-computed, the session result has no likelihood even when other breakdowns are good.

- [ ] **Step 3: Run GREEN and prohibited-field scan**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_scoring.py -v
$matches = & rg -n "invalid_quality|quality_gates|min_valid_coverage|failed_quality|binary_quality_v1" src/pilot_assessment/anchors src/pilot_assessment/contracts/anchor_v2.py 2>$null
if ($LASTEXITCODE -eq 0) { $matches; throw "prohibited M4 quality field found" }
if ($LASTEXITCODE -ne 1) { throw "rg quality-field scan failed" }
~~~

Expected: tests PASS; scan returns no production M4 match.

- [ ] **Step 4: Commit**

~~~powershell
git add src/pilot_assessment/anchors/scoring.py tests/anchors/test_scoring.py
git commit -m "feat: add central M4 evidence scoring"
~~~

### Task 13: Implement typed DAG validation, deterministic scheduling, and the public API

**Files:**
- Create: `src/pilot_assessment/anchors/dag.py`
- Create: `src/pilot_assessment/anchors/preprocessing.py`
- Create: `src/pilot_assessment/anchors/service.py`
- Create: `src/pilot_assessment/anchors/api.py`
- Modify: `src/pilot_assessment/anchors/__init__.py`
- Create: `tests/anchors/test_dag.py`
- Create: `tests/anchors/test_preprocessing.py`
- Create: `tests/anchors/test_service.py`

- [ ] **Step 1: Write RED plan/service tests with injected fakes**

Cover duplicate/missing dependency, schema/type mismatch, anchor cycle, preprocessing-provider cycle, unique recipe dependency resolution, cross-`scope_policy` provider-edge rejection, exact registry identity, canonical topological levels, canonical semantic/reference fingerprint recomputation before evaluator construction, valid-request checks before any plugin call, M4 plan/registry blocked reporting, independent-node continuation, true-downstream `dependency_missing`, computed-U dependency availability, plugin/provider exception and artifact failure isolation, global transaction failure, canonical report order independent of completion order, complete inventory, and raw availability.

The RED suite must include these executable security/lifecycle probes:

1. constructing `AnchorEvaluationRequest` from a real M3 `blocked` outcome fails because `aligned_session=None`; the harness never calls `AnchorEvaluator.evaluate`, and plugin factory, provider factory, plugin `compute`, provider `compute`, and sink `begin_evaluation` spies all remain exactly zero. Separately, a type-correct non-blocked-M3 request with an invalid/incompatible M4 plan returns the inventory-complete M4 `blocked` report with those same call counts at zero;
2. a fake plugin/provider declaring only stream X, one context/semantic path, one reference ID, and one upstream preprocessing dependency can access exactly those projections plus that one resolved immutable dependency; it cannot discover U, G, ECG, undeclared context/semantic paths, undeclared references, sibling preprocessing products/cache entries, the complete request, the complete plan, or the complete aligned-stream map;
3. a fake plugin receives exactly its current `AnchorExecutionEntry.temporal_recipe` and no other entry or recipe; the service binds the current anchor's immutable `artifact_recipes` at `begin_anchor`, its emitter can stage a table by exact artifact ID, return that exact ref in `AnchorMeasurement.derived_artifacts`, commit through the service, and let a declared `(target_anchor_id, target_resource_id)` downstream artifact dependency resolve the immutable payload. Separate malicious fakes using unknown/duplicate IDs, kind/schema/payload mismatches, returning an unstaged ref, omitting a staged ref, reordering refs, duplicating a ref, or mutating a returned ref each abort only that anchor as `extractor_error`; two declared IDs with the same kind/schema remain separately addressable, and the emitter cannot commit, abort, resolve, inspect another producer, or see a storage path;
4. two fake consumers requesting the same preprocessing recipe/provider/parameters/input fingerprints/exact `PreprocessingScope` trigger provider `compute` exactly once, the provider receives that exact scope plus only its declared dependency-slot mapping keyed by `dependency_id` (resolved from each binding's unique `target_recipe_id`), and both consumers receive the same logical content hash;
5. a changed scope kind/ID/start/end/phase/event/window identity, parameter-schema hash, parameter hash, declared input fingerprint, provider version, or upstream preprocessing fingerprint produces a different key and a separate computation. Even when two such scopes produce byte-identical payload rows, their `PreprocessingArtifactIdentity`, downstream dependency fingerprint, result fingerprint, and evaluation fingerprint differ;
6. a provider failure gives `dependency_missing` only to anchors that require that product, while independent anchors continue;
7. the public request schema rejects `test_only_partial_plan`; a test evaluator may accept only a fully valid injected `test-*` plan whose every listed entry resolves;
8. internal fault hooks can (a) map `(O1, X)` to a consumer-local direct-stream projection miss and canonical `missing_input` without calling O1, while all other X consumers retain X, (b) map `(O5, movement-events-v1)` to consumer-local `dependency_missing` while O7/O9/O13 retain the normal memoized product, and (c) map O4 to a consumer-local artifact-transaction commit failure after O4 compute/staging so only O4 becomes `extractor_error`, its ordered breakdown diagnostics are retained, its derived artifacts are absent, and independent anchors continue. Hook diagnostics enter the affected result fingerprint, but hook configuration is unavailable from public DTOs/API and never enters a plan.
9. exercise the stable precedence matrix in both the public boundary and `AnchorEvaluator.for_testing(...).evaluate()`: session/window identity tamper returns `request_session_mismatch`; M3 annotation, input-table, dynamic-AOI or applicability relation tamper returns `request_semantic_identity_mismatch`; missing/extra required reference IDs returns `request_reference_inventory_mismatch`; M3 report/checksum/mapping provenance tamper returns `request_reference_provenance_mismatch`. Only when all earlier relations remain valid but a claimed canonical digest is stale—such as a semantic target-only value change, an in-contract aligned reference row-value change that preserves order/schema, a plan scorer field change, or changing only a self-reported digest—does it return `request_fingerprint_mismatch`. In every case no M4 report is produced and factory/provider/plugin/sink call counts stay zero. By contrast, an invalid plan presented with otherwise valid recomputed request identity enters validated evaluation and returns the inventory-complete M4 `blocked` report. Include an explicit absent-reference case proving it passes without a runtime content/alignment hash.
10. independently inject report=`aligned` without the matching view and a non-aligned report with an injected view; both return `request_session_mismatch`. For each optional status `not_attempted/unavailable/invalid/unsupported/not_applicable`, omit I from `aligned_session.streams`, prove request construction succeeds, and prove only I-dependent anchors later become `missing_input` with the exact status reason. Separately change a dynamic AOI table role/table-level schema/frame/geometry unit/key or ordered geometry field; for any aligned required core stream change its live table inventory, stream-level schema, report artifact table-level schema, ordered columns/dtypes/nulls, one matching plan input-table contract field, or the applicability ID set. These relation mismatches return `request_semantic_identity_mismatch` before evaluator construction and all service spies remain zero. A matching compact I table with intentionally extreme but finite AOI geometry is not rejected as “low quality”; only its declared structural constraints apply.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_dag.py tests/anchors/test_preprocessing.py tests/anchors/test_service.py -v
~~~

Expected: RED because DAG/service/API do not exist.

- [ ] **Step 2: Implement plan validation and levels**

~~~python
@dataclass(frozen=True, slots=True)
class ValidatedExecutionPlan:
    plan: AnchorExecutionPlan
    levels: tuple[tuple[str, ...], ...]
    registry_fingerprint: str

@dataclass(frozen=True, slots=True)
class PlanValidationOutcome:
    disposition: Literal["valid", "blocked"]
    validated_plan: ValidatedExecutionPlan | None
    diagnostics: tuple[DomainErrorData, ...]

@dataclass(frozen=True, slots=True)
class EvaluationPolicy:
    require_packaged_registry_fingerprint: bool
    allow_injected_test_profile_ids: bool

@dataclass(frozen=True, slots=True)
class TestFaultHooks:
    direct_stream_projection_failures: Mapping[
        tuple[str, str], DomainErrorData
    ]
    preprocessing_resolution_failures: Mapping[
        tuple[str, str], DomainErrorData
    ]
    anchor_transaction_failures: Mapping[
        str, DomainErrorData
    ]

~~~

Required callables:

~~~text
validate_execution_plan(
    plan: AnchorExecutionPlan,
    registry: PluginRegistry
) -> PlanValidationOutcome
topological_levels(entries: Sequence[AnchorExecutionEntry]) -> tuple[tuple[str, ...], ...]
validate_anchor_evaluation_request(request: AnchorEvaluationRequest) -> None
~~~

Reference level 0 is O1-O7/O10-O12/H1-H5; level 1 is O8/O9/O13. Canonical report order comes from catalog, not scheduler completion. The idempotent request validator first rechecks exact two-way equality between report-aligned modalities and `aligned_session.streams`, then checks all aligned plan-required core streams against their complete input-table contracts, dynamic AOI against its plan contract and conditionally aligned I view, and exact applicability equality with `plan.entries` before any plan or factory access. Optional `not_attempted/unavailable/invalid/unsupported/not_applicable` streams bypass only the live table comparison and remain available to the normal per-anchor `missing_input` path with exact status reason. Stable validation precedence is session identity, then semantic/annotation/input-table/applicability relations, then reference inventory/provenance, then canonical fingerprints; a mutation that both breaks a semantic relation and leaves a stale plan fingerprint therefore returns `request_semantic_identity_mismatch`, while an otherwise relationally valid stale digest returns `request_fingerprint_mismatch`. Before factory access, plan validation reconstructs each plugin/provider definition from the execution-entry/recipe snapshot, recomputes its `definition_fingerprint`, and matches the registry entry. It then builds the provider-recipe DAG: each recipe's copied dependency spec is matched by exactly one binding with the same `dependency_id`; each binding's `target_recipe_id` resolves to exactly one plan recipe whose output schema/kind matches the spec; no extra binding is allowed; and every edge has exactly equal upstream/downstream `scope_policy` in v0.1. Missing/duplicate/extra/unresolved/schema-kind-mismatched/cyclic/cross-policy edges block before registry factory, provider, plugin, or sink access.

- [ ] **Step 3: Implement the dynamic preprocessing resolver/cache**

The exact cache key is a typed fingerprint over this frozen dataclass:

~~~text
PreprocessingCacheKey:
  recipe_id: str
  recipe_version: str
  provider_id: str
  provider_version: str
  implementation_digest: Sha256Digest
  parameter_hash: Sha256Digest
  scope_kind: Literal["session", "phase", "event", "window"]
  scope_id: str
  scope_start_t_ns: int
  scope_end_t_ns: int
  phase_id: str | None
  event_id: str | None
  window_id: str | None
  input_fingerprints: tuple[tuple[str, str, Sha256Digest], ...]
  dependency_fingerprints: tuple[Sha256Digest, ...]
~~~

`input_fingerprints` is canonical order over only the recipe's declared stream, context, semantic, and reference projections. The provider parameter schema ID/hash is registry-bound and included through the validated recipe/producer identity. The remaining scope fields are copied from one validated `PreprocessingScope`, so two equal labels with different interval or phase/event/window identity cannot alias. Build a provider-only topological order from the already validated target-recipe bindings; it is separate from the anchor DAG. `PreprocessingResolver.resolve(recipe, context, scope, evaluation_transaction)` resolves the exact provider/version/digest from the independent registry map, validates parameters against the exact registry-bound schema before factory access, recursively resolves each binding's `target_recipe_id` using the same exact scope, passes that scope and only the resulting `Mapping[dependency_id, ResolvedPreprocessingDependency]` positive projection into provider `compute`, computes once per cache key, stages the immutable payload through `stage_preprocessing()`, verifies schema/kind/hash, and memoizes the returned handle only for that evaluation. `dependency_fingerprints` is canonical provider-definition dependency-slot order. `PreprocessingProducer` and `PreprocessingArtifactIdentity` copy the full scope and parameter-schema identity; downstream dependency fingerprints hash that identity plus logical content, not logical content alone. The resolver never accepts a complete request or undeclared input. There is no cross-session process cache in v0.1.

- [ ] **Step 4: Implement service and fixed public entry**

~~~text
AnchorEvaluator(registry: PluginRegistry, policy: EvaluationPolicy)
AnchorEvaluator.for_testing(
    registry: PluginRegistry,
    policy: EvaluationPolicy,
    fault_hooks: TestFaultHooks | None = None
) -> AnchorEvaluator
AnchorEvaluator.evaluate(
    request: AnchorEvaluationRequest,
    sink: DerivedArtifactSink
) -> AnchorEvaluationReport
public evaluate(
    request: AnchorEvaluationRequest,
    sink: DerivedArtifactSink
) -> AnchorEvaluationReport
~~~

The public `evaluate` first calls `validate_anchor_evaluation_request(request)`. `AnchorEvaluator.evaluate()` also calls the same function as its first idempotent operation, before plan validation, factory resolution or sink access; therefore `AnchorEvaluator.for_testing()` cannot waive identity/fingerprint/provenance validation. Only after public validation returns does `evaluate` construct `AnchorEvaluator(load_packaged_registry(), EvaluationPolicy(require_packaged_registry_fingerprint=True, allow_injected_test_profile_ids=False))`; the internal second call verifies the unchanged request again before beginning validated evaluation.

The validator always recomputes the semantic snapshot fingerprint and resolved-reference-set fingerprint. For every declared descriptor it always recomputes the table-contract fingerprint. For `present`, it additionally requires a view and recomputes resource, aligned-content and alignment fingerprints; for `absent`, it requires no view plus empty checksums and null resource/content/alignment fingerprints and does **not** call a content or alignment hash function. It also rechecks session identity, report/view inventory equivalence, exact applicability inventory, every aligned required core stream's view/report/table identity, dynamic AOI/plan input-table identity plus conditional live I identity, exact required-reference inventory and M3 provenance in the precedence above. Any mismatch raises the stable request error and produces no M4 report; only plan/registry/DAG/transaction failures after this validator returns use the M4 `blocked` report.

For each executable entry the service constructs only that entry's separately declared context/semantic/dependency projections, resolves preprocessing with a validated `PreprocessingScope`, starts one anchor transaction with `ArtifactProducer(anchor_id=entry.anchor_id, ...)` plus `tuple(entry.artifact_recipes)`, and calls the plugin with `entry.temporal_recipe` plus `anchor_transaction.emitter()`. It validates the returned measurement/schema, requires exact ordered equality between `measurement.derived_artifacts` and `anchor_transaction.staged_refs()`, then commits the anchor transaction before a later DAG level may resolve those refs. Any plugin exception, invalid measurement, unknown/duplicate/mismatched artifact recipe use, unstaged/staged-missing/reordered/mutated ref, staging error, or anchor-commit error aborts that transaction and yields only the canonical `extractor_error` result for that anchor; independent nodes continue and true downstream dependencies become `dependency_missing`. A final report/evaluation commit error aborts the whole evaluation transaction.

The public function does not accept an arbitrary registry, policy, or fault hook. Test injection occurs only through `AnchorEvaluator.for_testing`; `EvaluationPolicy` and `TestFaultHooks` are internal frozen dataclasses absent from every DTO/schema/JSON resource. A direct-stream hook is consulted after the positive context projection and before plugin invocation; it removes only that consumer's declared stream, emits canonical `missing_input` plus the hook diagnostic, and leaves the immutable session/request unchanged. A preprocessing hook is consulted only after valid plan/provider resolution and before returning that one consumer's dependency; it cannot mutate the provider cache or affect another consumer. An anchor-transaction hook is consulted only after measurement/schema and staged-ref validation but immediately before commit; it fails and aborts only the named anchor transaction, preserves ordered diagnostics in that anchor's `extractor_error`, and cannot affect another transaction or the evaluation sink. Even in tests these mechanisms cannot waive schema, fingerprint, dependency, cycle, or per-entry registry validation.

- [ ] **Step 5: Run GREEN and the M4-B completion gate**

~~~powershell
& .\.tools\uv\uv.exe run python -m pilot_assessment.schemas.export
git diff --exit-code -- schemas src/pilot_assessment/schema_resources
& .\.tools\uv\uv.exe run pytest tests/contracts/test_anchor_result.py tests/contracts/test_anchor_result_v2.py tests/contracts/test_anchor_execution.py tests/anchors -q
& .\.tools\uv\uv.exe run pytest -q
& .\.tools\uv\uv.exe run ruff format --check .
& .\.tools\uv\uv.exe run ruff check .
& .\.tools\uv\uv.exe run ty check src
& .\.tools\uv\uv.exe build
git diff --check
~~~

Expected: PASS. The exact-18 production plan remains blocked because both packaged registry maps still have zero executable entries; fully valid injected test profiles pass only through `AnchorEvaluator.for_testing`. Positive-projection, blocked-M3/request-fingerprint rejection without an M4 report, valid-request M4-plan-blocked reporting, memoization, and provider-failure isolation probes all pass.

- [ ] **Step 6: Commit and record the M4-B gate**

~~~powershell
git add src/pilot_assessment/anchors/dag.py src/pilot_assessment/anchors/preprocessing.py src/pilot_assessment/anchors/service.py src/pilot_assessment/anchors/api.py src/pilot_assessment/anchors/__init__.py tests/anchors/test_dag.py tests/anchors/test_preprocessing.py tests/anchors/test_service.py
git commit -m "feat: execute M4 plans through plugin protocol"
~~~

After this commit the only valid claim is: `M4-B framework engineering-verified; 18/18 specified; 0/18 reference plugins implemented; formal_run_authorized=false`.

## M4-C: O1-O7 task/control anchors

Each task below adds exactly one production registry entry and one executable factory. Run the registry closure verifier after updating the entry; never hand-copy an old digest. The expected implementation count is cumulative and must be asserted in `tests/anchors/test_registry.py`.

### Task 14: Implement O1 Phase-state Precision

**Files:**
- Create: `src/pilot_assessment/anchors/primitives/__init__.py`
- Create: `src/pilot_assessment/anchors/primitives/envelopes.py`
- Create: `src/pilot_assessment/anchors/plugins/__init__.py`
- Create: `src/pilot_assessment/anchors/plugins/o1_phase_state_precision.py`
- Create: `tests/m4_support/micro_inputs.py`
- Create: `tests/m4_support/micro_oracles.py`
- Create: `tests/anchors/test_o1_phase_state_precision.py`
- Modify: `src/pilot_assessment/anchors/registry-v1.json`
- Modify: `tests/anchors/test_registry.py`

- [ ] **Step 1: Write RED behavior and boundary tests through `AnchorEvaluator`**

Create only generic constructors for tiny aligned X/reference/U/I/G/EEG/ECG/R-peak tables and independent scalar/threshold helpers. They may not import production plugins or store expected result objects. O1's concrete rows and expected states remain in `test_o1_phase_state_precision.py`; later plugin tests reuse the constructors with their own local rows.

Required named cases:

~~~text
test_o1_desired_adequate_unacceptable_and_exact_boundaries
test_o1_partial_support_is_scored_against_full_phase_without_quality_gate
test_o1_noncomputed_later_phase_prevents_partial_session_score
test_o1_computes_all_phase_traces_after_early_unacceptable
test_o1_gap_does_not_extend_inside_duration
test_o1_parameter_change_changes_result_fingerprint
~~~

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_o1_phase_state_precision.py -v
~~~

Expected: RED because O1 capability is unavailable.

- [ ] **Step 2: Implement the shared envelope primitive and plugin**

For every applicable phase compute:

~~~text
P_phase = 100 * inside_joint_desired_envelope_duration / phase_duration
session_primary = min(P_phase)
D if P >= 90; A if P >= 70; otherwise U
~~~

Use native X left-hold support, full phase wall-clock denominator, no minimum duration/coverage gate, and a typed `desired-envelope mask` artifact. Missing phase X support is `missing_input`; missing envelope definition is `not_computable`; finite large errors are computed U.

- [ ] **Step 3: Register/verify the exact implementation closure and run GREEN**

~~~powershell
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh --anchor O1 --factory-module pilot_assessment.anchors.plugins.o1_phase_state_precision --factory-symbol create_plugin
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry verify
& .\.tools\uv\uv.exe run pytest tests/anchors/test_o1_phase_state_precision.py tests/anchors/test_registry.py -v
~~~

Expected: PASS; production capability count is 1/18.

- [ ] **Step 4: Commit**

~~~powershell
git add src/pilot_assessment/anchors/primitives src/pilot_assessment/anchors/plugins src/pilot_assessment/anchors/registry-v1.json tests/m4_support/micro_inputs.py tests/m4_support/micro_oracles.py tests/anchors/test_o1_phase_state_precision.py tests/anchors/test_registry.py
git commit -m "feat: add phase-state precision anchor"
~~~

### Task 15: Implement O2 Peak Tracking Excursion

**Files:**
- Create: `src/pilot_assessment/anchors/primitives/reference_join.py`
- Create: `src/pilot_assessment/anchors/plugins/o2_peak_tracking_excursion.py`
- Create: `tests/anchors/test_o2_peak_tracking_excursion.py`
- Modify: `src/pilot_assessment/anchors/registry-v1.json`
- Modify: `tests/anchors/test_registry.py`

- [ ] **Step 1: Write RED join/error tests**

Test exact timestamp ties, same-segment linear interpolation, no extrapolation/cross-gap join, earliest peak tie, unit/frame conversion, tiny nonzero overlap still computed, no overlap `not_computable + no_reference_overlap`, missing independent reference, and an explicit assertion that actual X cannot satisfy commanded reference.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_o2_peak_tracking_excursion.py -v
~~~

Expected: RED because O2 is unavailable.

- [ ] **Step 2: Implement the exact reference join and metric**

~~~text
evaluation grid = applicable native X timestamps
e(t) = L2(position(t) - transformed_interpolated_reference(t))
E_peak = max(e(t)); ties choose earliest t_ns then stable row
D <= 2 ft; A <= 5 ft; U > 5 ft
~~~

Save per-axis error and tracking-error trace. Never fall back to nearest-path or actual X.

- [ ] **Step 3: Register, verify, and run GREEN**

~~~powershell
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh --anchor O2 --factory-module pilot_assessment.anchors.plugins.o2_peak_tracking_excursion --factory-symbol create_plugin
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry verify
& .\.tools\uv\uv.exe run pytest tests/anchors/test_o2_peak_tracking_excursion.py tests/anchors/test_registry.py -v
~~~

Expected: PASS; capability count is 2/18.

- [ ] **Step 4: Commit**

~~~powershell
git add src/pilot_assessment/anchors/primitives/reference_join.py src/pilot_assessment/anchors/plugins/o2_peak_tracking_excursion.py src/pilot_assessment/anchors/registry-v1.json tests/anchors/test_o2_peak_tracking_excursion.py tests/anchors/test_registry.py
git commit -m "feat: add peak tracking excursion anchor"
~~~

### Task 16: Implement O3 Terminal Capture Quality

**Files:**
- Create: `src/pilot_assessment/anchors/plugins/o3_terminal_capture_quality.py`
- Create: `tests/anchors/test_o3_terminal_capture_quality.py`
- Modify: `src/pilot_assessment/anchors/primitives/envelopes.py`
- Modify: `src/pilot_assessment/anchors/registry-v1.json`
- Modify: `tests/anchors/test_registry.py`

- [ ] **Step 1: Write RED capture-conjunction tests**

Test finite/nonzero arrival-axis validation, D-to-H horizon clipping, overshoot direction, full 2-second hold confirmation with latency recorded at hold start, exact D/A conjunctions, normal `primary_value=null + composite_conjunction`, and missed capture `computed U + capture_missed` with finite observed wait.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_o3_terminal_capture_quality.py -v
~~~

Expected: RED because O3 and its capture-envelope behavior do not exist.

- [ ] **Step 2: Implement the exact two-metric observation**

~~~text
overshoot = max(0, max(arrival_axis dot (position - hover_target)))
settling_time = D-to-H boundary to start of first envelope hold lasting 2 s
D: overshoot <=2 ft AND settling <=3 s
A: overshoot <=5 ft AND settling <=5 s
otherwise U
~~~

Missing target/frame/axis is not-computable. Never use Infinity for a miss.

- [ ] **Step 3: Register and run GREEN**

~~~powershell
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh --anchor O1
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh --anchor O3 --factory-module pilot_assessment.anchors.plugins.o3_terminal_capture_quality --factory-symbol create_plugin
& .\.tools\uv\uv.exe run pytest tests/anchors/test_o1_phase_state_precision.py tests/anchors/test_o3_terminal_capture_quality.py tests/anchors/test_registry.py -v
~~~

Expected: PASS; count is 3/18.

- [ ] **Step 4: Commit**

~~~powershell
git add src/pilot_assessment/anchors/primitives/envelopes.py src/pilot_assessment/anchors/plugins/o3_terminal_capture_quality.py src/pilot_assessment/anchors/registry-v1.json tests/anchors/test_o3_terminal_capture_quality.py tests/anchors/test_registry.py
git commit -m "feat: add terminal capture quality anchor"
~~~

### Task 17: Implement O4 Sustained Hover Time

**Files:**
- Create: `src/pilot_assessment/anchors/plugins/o4_sustained_hover_time.py`
- Create: `tests/anchors/test_o4_sustained_hover_time.py`
- Modify: `src/pilot_assessment/anchors/primitives/envelopes.py`
- Modify: `src/pilot_assessment/anchors/registry-v1.json`
- Modify: `tests/anchors/test_registry.py`

- [ ] **Step 1: Write RED stable-run tests**

Test the conjunction of hover envelope/speed/angular-rate, exact 5/10-second thresholds, gap splitting, optional explicit behavioral excursion tolerance, and stable mask all false producing `0 s + computed U` rather than missing/invalid.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_o4_sustained_hover_time.py -v
~~~

Expected: RED because O4 stable-run behavior does not exist.

- [ ] **Step 2: Implement longest continuous stable duration**

~~~text
stable = inside_hover_envelope AND speed_within_limit AND angular_rate_within_limit
primary = longest_continuous_stable_duration
D >= 10 s; A >= 5 s; otherwise U
~~~

Do not repair collection gaps. Any behavioral tolerance must be the explicit versioned `max_behavioral_excursion_s` parameter.

- [ ] **Step 3: Register and run GREEN**

~~~powershell
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh --anchor O1
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh --anchor O3
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh --anchor O4 --factory-module pilot_assessment.anchors.plugins.o4_sustained_hover_time --factory-symbol create_plugin
& .\.tools\uv\uv.exe run pytest tests/anchors/test_o1_phase_state_precision.py tests/anchors/test_o3_terminal_capture_quality.py tests/anchors/test_o4_sustained_hover_time.py tests/anchors/test_registry.py -v
~~~

Expected: PASS; count is 4/18.

- [ ] **Step 4: Commit**

~~~powershell
git add src/pilot_assessment/anchors/primitives/envelopes.py src/pilot_assessment/anchors/plugins/o4_sustained_hover_time.py src/pilot_assessment/anchors/registry-v1.json tests/anchors/test_o4_sustained_hover_time.py tests/anchors/test_registry.py
git commit -m "feat: add sustained hover anchor"
~~~

### Task 18: Implement O5 Workload Rate and the shared movement detector

**Files:**
- Create: `src/pilot_assessment/anchors/primitives/movement.py`
- Create: `src/pilot_assessment/anchors/plugins/o5_workload_rate.py`
- Create: `tests/anchors/test_movement.py`
- Create: `tests/anchors/test_o5_workload_rate.py`
- Modify: `src/pilot_assessment/anchors/registry-v1.json`
- Modify: `tests/anchors/test_registry.py`

- [ ] **Step 1: Write RED primitive and O5 golden tests**

Cover 100 Hz phase-start grids per support segment; 5 Hz fourth-order Butterworth SOS; `sosfiltfilt(padtype=odd,padlen=min(15,n-1))`; n<3 bypass; central/one-sided derivative; ±0.5%/s sign deadband; 50 ms left-hold run; zero-platform termination; opposite-run turning points; flat-extreme midpoint rounded half-even; 0.5% travel movement threshold; configured zero-movement channels retained; and no cross-gap movement.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_movement.py tests/anchors/test_o5_workload_rate.py -v
~~~

Expected: RED because movement/O5 are absent.

- [ ] **Step 2: Implement the detector and score**

~~~text
W_channel = movement_count / observed_support_duration_s
W = mean(W_channel across every configured active channel)
ratio = W / fixed task-profile W_min
D ratio <=2; A ratio <=4; otherwise U
~~~

A single point with zero support duration is not-computable. Any finite partial support with a valid denominator is computed. Six-Hz violent control is computed U. Do not infer `W_min` from the pilot/session.

`movement.py` also exposes `create_provider()` for `movement-events-v1`/`1.0.0`. Its provider definition declares U, active-channel semantics, the exact movement profile, no provider dependency, and a typed movement-event table. O5 consumes that dynamic preprocessing recipe; it does not call an unregistered helper through a hidden path.

- [ ] **Step 3: Register with exact NumPy/SciPy runtime provenance and run GREEN**

~~~powershell
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh-preprocessor --provider movement-events-v1 --factory-module pilot_assessment.anchors.primitives.movement --factory-symbol create_provider
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh --anchor O5 --factory-module pilot_assessment.anchors.plugins.o5_workload_rate --factory-symbol create_plugin
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry verify
& .\.tools\uv\uv.exe run pytest tests/anchors/test_movement.py tests/anchors/test_o5_workload_rate.py tests/anchors/test_preprocessing.py tests/anchors/test_registry.py -v
~~~

Expected: PASS; O5/provider closures declare NumPy/SciPy, anchor count is 5/18, provider count is 1, and the provider product hash is a declared O5 dependency fingerprint.

- [ ] **Step 4: Commit**

~~~powershell
git add src/pilot_assessment/anchors/primitives/movement.py src/pilot_assessment/anchors/plugins/o5_workload_rate.py src/pilot_assessment/anchors/registry-v1.json tests/anchors/test_movement.py tests/anchors/test_o5_workload_rate.py tests/anchors/test_registry.py
git commit -m "feat: add deterministic workload-rate anchor"
~~~

### Task 19: Implement O6 Control Magnitude RMS

**Files:**
- Create: `src/pilot_assessment/anchors/plugins/o6_control_magnitude_rms.py`
- Create: `tests/anchors/test_o6_control_magnitude_rms.py`
- Modify: `src/pilot_assessment/anchors/registry-v1.json`
- Modify: `tests/anchors/test_registry.py`

- [ ] **Step 1: Write RED normalization/integration tests**

Test `lower < trim < upper`, nonnegative weights summing to one, both piecewise branches, left-hold integration per segment, exact 30/50% thresholds, partial support, and finite values outside endpoints producing valid values above 100% without clipping.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_o6_control_magnitude_rms.py -v
~~~

Expected: RED because O6 normalization/integration behavior does not exist.

- [ ] **Step 2: Implement the exact formula**

~~~text
u_norm=(u-trim)/(upper-trim) when u>=trim
u_norm=(u-trim)/(trim-lower) when u<trim
RMS_channel=sqrt(integral(u_norm^2 dt)/observed_support_duration)
RMS_total=100*sqrt(sum(weight*RMS_channel^2))
D <=30%; A <=50%; otherwise U
~~~

No runtime trim estimation and no endpoint clipping.

- [ ] **Step 3: Register and run GREEN**

~~~powershell
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh --anchor O6 --factory-module pilot_assessment.anchors.plugins.o6_control_magnitude_rms --factory-symbol create_plugin
& .\.tools\uv\uv.exe run pytest tests/anchors/test_o6_control_magnitude_rms.py tests/anchors/test_registry.py -v
~~~

Expected: PASS; count is 6/18.

- [ ] **Step 4: Commit**

~~~powershell
git add src/pilot_assessment/anchors/plugins/o6_control_magnitude_rms.py src/pilot_assessment/anchors/registry-v1.json tests/anchors/test_o6_control_magnitude_rms.py tests/anchors/test_registry.py
git commit -m "feat: add control magnitude RMS anchor"
~~~

### Task 20: Implement O7 Control Reversal Rate and close M4-C

**Files:**
- Create: `src/pilot_assessment/anchors/plugins/o7_control_reversal_rate.py`
- Create: `tests/anchors/test_o7_control_reversal_rate.py`
- Modify: `src/pilot_assessment/anchors/registry-v1.json`
- Modify: `tests/anchors/test_registry.py`

- [ ] **Step 1: Write RED shared-profile/reversal tests**

Prove O7 reuses the exact O5 grid/filter/sign-run/turning-point profile; qualifying peak/valley amplitude is >=2% travel and separation >=0.15 s; denominator equals O5 support duration; session takes channel max; and boundaries are D `<2 Hz`, A `2<=x<4 Hz`, U `>=4 Hz`.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_o7_control_reversal_rate.py -v
~~~

Expected: RED because O7 is not registered and no consumer proves movement-profile reuse.

- [ ] **Step 2: Implement O7 without copying the movement algorithm**

Declare the existing `movement-events-v1` preprocessing recipe and consume its immutable product; do not call/copy the detector outside the provider registry. Extreme reversal frequency remains computed U. Missing configured mapping is not-computable; a configured channel with zero reversals remains valid.

- [ ] **Step 3: Register and run the M4-C gate**

~~~powershell
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh --anchor O7 --factory-module pilot_assessment.anchors.plugins.o7_control_reversal_rate --factory-symbol create_plugin
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry verify
& .\.tools\uv\uv.exe run pytest tests/anchors/test_o1_phase_state_precision.py tests/anchors/test_o2_peak_tracking_excursion.py tests/anchors/test_o3_terminal_capture_quality.py tests/anchors/test_o4_sustained_hover_time.py tests/anchors/test_movement.py tests/anchors/test_o5_workload_rate.py tests/anchors/test_o6_control_magnitude_rms.py tests/anchors/test_o7_control_reversal_rate.py tests/anchors/test_preprocessing.py tests/anchors/test_registry.py -q
~~~

Expected: PASS; exactly 7/18 production capabilities are available and software-verified.

- [ ] **Step 4: Commit**

~~~powershell
git add src/pilot_assessment/anchors/plugins/o7_control_reversal_rate.py src/pilot_assessment/anchors/registry-v1.json tests/anchors/test_o7_control_reversal_rate.py tests/anchors/test_registry.py
git commit -m "feat: add control reversal anchor and close M4-C"
~~~

## M4-D: O8-O12 derived/event anchors

### Task 21: Implement O8 TPX Composite

**Files:**
- Create: `src/pilot_assessment/anchors/plugins/o8_tpx_composite.py`
- Create: `tests/anchors/test_o8_tpx_composite.py`
- Modify: `src/pilot_assessment/anchors/registry-v1.json`
- Modify: `tests/anchors/test_registry.py`

- [ ] **Step 1: Write RED dependency/composite tests**

Test O1/O5 computed D/A/U combinations, upstream computed-U still available, upstream non-computed producing `dependency_missing`, exact 0.4/0.6 boundaries, bounded output, and a component trace that references upstream result fingerprints.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_o8_tpx_composite.py -v
~~~

Expected: RED because O8 and its typed result dependencies do not exist.

- [ ] **Step 2: Implement the exact derived formula**

~~~text
TPX=(P/100)^2*sqrt(W_min/max(W,W_min))
TPX=clip(TPX,0,1)
D >=0.6; A >=0.4; otherwise U
~~~

The clamp is formula-defined, not outlier filtering. M5, not M4, applies `likelihood_strength=0.50`.

- [ ] **Step 3: Register and run GREEN**

~~~powershell
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh --anchor O8 --factory-module pilot_assessment.anchors.plugins.o8_tpx_composite --factory-symbol create_plugin
& .\.tools\uv\uv.exe run pytest tests/anchors/test_o8_tpx_composite.py tests/anchors/test_registry.py -v
~~~

Expected: PASS; count is 8/18.

- [ ] **Step 4: Commit**

~~~powershell
git add src/pilot_assessment/anchors/plugins/o8_tpx_composite.py src/pilot_assessment/anchors/registry-v1.json tests/anchors/test_o8_tpx_composite.py tests/anchors/test_registry.py
git commit -m "feat: add TPX composite anchor"
~~~

### Task 22: Implement O9 Dead-band Activity

**Files:**
- Create: `src/pilot_assessment/anchors/plugins/o9_dead_band_activity.py`
- Create: `tests/anchors/test_o9_dead_band_activity.py`
- Modify: `src/pilot_assessment/anchors/registry-v1.json`
- Modify: `tests/anchors/test_registry.py`

- [ ] **Step 1: Write RED mask/matching precedence tests**

The first assertion must lock the unique precedence: if O1 desired-mask ∩ O4 stable-mask is all false, return `computed + U + no_stable_hover` even if there is no matchable U support. Only when stable spans exist and all have zero nearest-within-20-ms U matches may O9 return `missing_input + no_temporal_support_U`. Also test partial matches without a coverage gate, [0.5%,5%] movements, support-duration denominator, max-channel aggregation, and 1/2 Hz boundaries.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_o9_dead_band_activity.py -v
~~~

Expected: RED because O9 mask/artifact dependency behavior does not exist.

- [ ] **Step 2: Implement mask-first logic and reuse the movement primitive**

~~~text
DBA_channel=micro_movement_count/matched_stable_duration_s
DBA=max(DBA_channel)
D <1 Hz; A 1<=x<2 Hz; U >=2 Hz
~~~

Do not create 0 Hz when no stable opportunity exists; primary is null for `no_stable_hover`. O9 declares the same `movement-events-v1` provider plus O1/O4 artifact dependencies and receives the provider product through `ResolvedDependencies`; it does not invoke an undeclared detector.

- [ ] **Step 3: Register and run GREEN**

~~~powershell
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh --anchor O9 --factory-module pilot_assessment.anchors.plugins.o9_dead_band_activity --factory-symbol create_plugin
& .\.tools\uv\uv.exe run pytest tests/anchors/test_o9_dead_band_activity.py tests/anchors/test_registry.py -v
~~~

Expected: PASS; count is 9/18.

- [ ] **Step 4: Commit**

~~~powershell
git add src/pilot_assessment/anchors/plugins/o9_dead_band_activity.py src/pilot_assessment/anchors/registry-v1.json tests/anchors/test_o9_dead_band_activity.py tests/anchors/test_registry.py
git commit -m "feat: add dead-band activity anchor"
~~~

### Task 23: Implement O10 Recovery Time and the event primitive

**Files:**
- Create: `src/pilot_assessment/anchors/primitives/events.py`
- Create: `src/pilot_assessment/anchors/plugins/o10_recovery_time.py`
- Create: `tests/anchors/test_events.py`
- Create: `tests/anchors/test_o10_recovery_time.py`
- Modify: `src/pilot_assessment/anchors/registry-v1.json`
- Modify: `tests/anchors/test_registry.py`

- [ ] **Step 1: Write RED event/horizon/recovery tests**

Test marker start or first sample of a later-confirmed 100 ms adequate-envelope exit; start must not shift to confirmation time. Test earliest of event+15 s/phase end/session end, 2-second desired-envelope hold confirmed fully but latency recorded at onset, <=5/<=10 s boundaries, finite missed wait, multi-event worst/veto, all-event traces after early miss, and no opportunity as not-applicable.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_events.py tests/anchors/test_o10_recovery_time.py -v
~~~

Expected: RED because the shared event primitive and O10 do not exist.

- [ ] **Step 2: Implement reusable causal event/run primitives and O10**

Never convert a short observable horizon into missing data. If the observation end is reached without recovery, emit `computed + U + recovery_missed` with finite wait.

- [ ] **Step 3: Register and run GREEN**

~~~powershell
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh --anchor O10 --factory-module pilot_assessment.anchors.plugins.o10_recovery_time --factory-symbol create_plugin
& .\.tools\uv\uv.exe run pytest tests/anchors/test_events.py tests/anchors/test_o10_recovery_time.py tests/anchors/test_registry.py -v
~~~

Expected: PASS; count is 10/18.

- [ ] **Step 4: Commit**

~~~powershell
git add src/pilot_assessment/anchors/primitives/events.py src/pilot_assessment/anchors/plugins/o10_recovery_time.py src/pilot_assessment/anchors/registry-v1.json tests/anchors/test_events.py tests/anchors/test_o10_recovery_time.py tests/anchors/test_registry.py
git commit -m "feat: add recovery-time anchor"
~~~

### Task 24: Implement O11 Disturbance Latency

**Files:**
- Create: `src/pilot_assessment/anchors/plugins/o11_disturbance_latency.py`
- Create: `tests/anchors/test_o11_disturbance_latency.py`
- Modify: `src/pilot_assessment/anchors/primitives/events.py`
- Modify: `src/pilot_assessment/anchors/registry-v1.json`
- Modify: `tests/anchors/test_registry.py`

- [ ] **Step 1: Write RED causal-response tests**

Test 20 ms trailing causal median, event-preceding 1-second median, shorter nonempty phase pre-window, neutral/trim fallback only when no sample exists, mapped correct sign, `>5%` for `>=100 ms`, `earliest_any_mapped_correct`, exact 500/1000 ms boundaries, wrong-direction first then correct still `response_missed`, threshold noise not wrong response, finite 2-second miss, and complete multi-event traces.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_o11_disturbance_latency.py -v
~~~

Expected: RED because O11 and the shared causal-response behavior do not exist.

- [ ] **Step 2: Implement O11 with no retrospective/noncausal filter**

The wrong-direction override is `computed + U`, primary null, one-hot U. Missing event-channel mapping is not-computable; truly missing U is missing-input.

- [ ] **Step 3: Register and run GREEN**

~~~powershell
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh --anchor O10
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh --anchor O11 --factory-module pilot_assessment.anchors.plugins.o11_disturbance_latency --factory-symbol create_plugin
& .\.tools\uv\uv.exe run pytest tests/anchors/test_o10_recovery_time.py tests/anchors/test_o11_disturbance_latency.py tests/anchors/test_registry.py -v
~~~

Expected: PASS; count is 11/18.

- [ ] **Step 4: Commit**

~~~powershell
git add src/pilot_assessment/anchors/primitives/events.py src/pilot_assessment/anchors/plugins/o11_disturbance_latency.py src/pilot_assessment/anchors/registry-v1.json tests/anchors/test_o11_disturbance_latency.py tests/anchors/test_registry.py
git commit -m "feat: add disturbance-latency anchor"
~~~

### Task 25: Implement O12 Envelope-drift Latency and close M4-D

**Files:**
- Create: `src/pilot_assessment/anchors/plugins/o12_envelope_drift_latency.py`
- Create: `tests/anchors/test_o12_envelope_drift_latency.py`
- Modify: `src/pilot_assessment/anchors/primitives/events.py`
- Modify: `src/pilot_assessment/anchors/registry-v1.json`
- Modify: `tests/anchors/test_registry.py`

- [ ] **Step 1: Write RED exit/correction tests**

Test 100 ms exit confirmation with latency starting at the first out-of-envelope sample, signed state-error/effect mapping, the same baseline fallback as O11, correct `>5%`/`>=100 ms` input, exact 300/800 ms boundaries, 2-second finite miss, wrong direction, multi-event worst/veto, all traces after a miss, and never leaving the envelope as not-applicable rather than Desired.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_o12_envelope_drift_latency.py -v
~~~

Expected: RED because O12 correction behavior is unavailable.

- [ ] **Step 2: Implement O12 through shared event primitives**

Do not reuse confirmation timestamp as `t_exit`. A missing effect mapping is not-computable. A qualifying wrong-direction action or no action is `computed + U + correction_missed`.

- [ ] **Step 3: Register and run the M4-D gate**

~~~powershell
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh --anchor O10
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh --anchor O11
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh --anchor O12 --factory-module pilot_assessment.anchors.plugins.o12_envelope_drift_latency --factory-symbol create_plugin
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry verify
& .\.tools\uv\uv.exe run pytest tests/anchors/test_o8_tpx_composite.py tests/anchors/test_o9_dead_band_activity.py tests/anchors/test_events.py tests/anchors/test_o10_recovery_time.py tests/anchors/test_o11_disturbance_latency.py tests/anchors/test_o12_envelope_drift_latency.py tests/anchors/test_registry.py -q
~~~

Expected: PASS; exactly 12/18 production plugins are software-verified.

- [ ] **Step 4: Commit**

~~~powershell
git add src/pilot_assessment/anchors/primitives/events.py src/pilot_assessment/anchors/plugins/o12_envelope_drift_latency.py src/pilot_assessment/anchors/registry-v1.json tests/anchors/test_o12_envelope_drift_latency.py tests/anchors/test_registry.py
git commit -m "feat: add envelope-drift latency and close M4-D"
~~~

## M4-E: H1-H3 visual attention anchors

### Task 26: Implement H1 AOI Dwell and the gaze-AOI interval primitive

**Files:**
- Create: `src/pilot_assessment/anchors/primitives/gaze_aoi.py`
- Create: `src/pilot_assessment/anchors/plugins/h1_aoi_dwell.py`
- Create: `tests/anchors/test_gaze_aoi.py`
- Create: `tests/anchors/test_h1_aoi_dwell.py`
- Modify: `src/pilot_assessment/anchors/registry-v1.json`
- Modify: `tests/anchors/test_registry.py`

- [ ] **Step 1: Write RED scene/AOI/denominator tests**

Cover stable gaze order, first-person I frame at gaze time, 3D nearest positive depth then priority/stable ID, 2D priority/stable ID, full-view `other_scene`, phase clipping, gap behavior, and pooled phase numerator/denominator. Deliberately supply conflicting precomputed `assigned_aoi_id`; the primitive must use scene/gaze/AOI semantics. Deliberately set finite rows to low confidence, `binocular_valid=false`, blink, or tracking loss: finite observed intervals are not discarded; blink/tracking-loss/unprojectable intervals map to `other_scene`.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_gaze_aoi.py tests/anchors/test_h1_aoi_dwell.py -v
~~~

Expected: RED because gaze-AOI/H1 are absent.

- [ ] **Step 2: Implement gaze intervals and H1**

~~~text
R_AOI=100*sum(role_weight*gaze_dwell_role)/total_gaze_dwell
Primary/Secondary weight=1; Off-task/other_scene=0
D >=85%; A >=70%; otherwise U
~~~

Use gaze-interval duration, not fixation duration. If G stream is truly absent/zero temporal support as an input, use missing-input except the controlled observed-opportunity rule. When G is present across applicable phases but produces zero nonzero dwell, emit `computed + U + no_gaze_dwell`.

`gaze_aoi.py` exposes `create_provider()` for `gaze-aoi-intervals-v1`/`1.0.0`, declaring only I, G, AOI/phase semantics, and the typed gaze-interval output. H1 consumes the registered dynamic recipe.

- [ ] **Step 3: Register and run GREEN**

~~~powershell
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh-preprocessor --provider gaze-aoi-intervals-v1 --factory-module pilot_assessment.anchors.primitives.gaze_aoi --factory-symbol create_provider
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh --anchor H1 --factory-module pilot_assessment.anchors.plugins.h1_aoi_dwell --factory-symbol create_plugin
& .\.tools\uv\uv.exe run pytest tests/anchors/test_gaze_aoi.py tests/anchors/test_h1_aoi_dwell.py tests/anchors/test_preprocessing.py tests/anchors/test_registry.py -v
~~~

Expected: PASS; anchor count is 13/18 and provider count is 2.

- [ ] **Step 4: Commit**

~~~powershell
git add src/pilot_assessment/anchors/primitives/gaze_aoi.py src/pilot_assessment/anchors/plugins/h1_aoi_dwell.py src/pilot_assessment/anchors/registry-v1.json tests/anchors/test_gaze_aoi.py tests/anchors/test_h1_aoi_dwell.py tests/anchors/test_registry.py
git commit -m "feat: add AOI dwell anchor"
~~~

### Task 27: Implement H2 First Fixation Latency

**Files:**
- Create: `src/pilot_assessment/anchors/primitives/fixation.py`
- Create: `src/pilot_assessment/anchors/plugins/h2_first_fixation_latency.py`
- Create: `tests/anchors/test_fixation.py`
- Create: `tests/anchors/test_h2_first_fixation_latency.py`
- Modify: `src/pilot_assessment/anchors/registry-v1.json`
- Modify: `tests/anchors/test_registry.py`

- [ ] **Step 1: Write RED raw-gaze I-VT tests**

Test shortest-sphere angular velocity, duplicate-timestamp stable-first behavior, 100 deg/s threshold, 100 ms minimum, cue-available start, 2-second horizon clipping, exact 500/1000 ms boundaries, finite miss, and multi-event veto. Insert deliberately contradictory `G.tables["fixations"]`; H2 must recompute from 120 Hz raw gaze and ignore that derived table.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_fixation.py tests/anchors/test_h2_first_fixation_latency.py -v
~~~

Expected: RED because fixation provider/H2 do not exist.

- [ ] **Step 2: Implement fixation-v1 and H2**

The pilot not turning cannot delay the cue start. No relevant-AOI fixation by observation end is `computed + U + fixation_missed`, primary null, finite wait. Missing cue/AOI mapping is not-computable; absent G is missing-input.

`fixation.py` exposes `create_provider()` for `fixation-intervals-v1`/`1.0.0`, declaring raw G plus cue/AOI semantics and a typed fixation-interval output. It does not consume `G.tables["fixations"]`.

- [ ] **Step 3: Register and run GREEN**

~~~powershell
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh-preprocessor --provider fixation-intervals-v1 --factory-module pilot_assessment.anchors.primitives.fixation --factory-symbol create_provider
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh --anchor H2 --factory-module pilot_assessment.anchors.plugins.h2_first_fixation_latency --factory-symbol create_plugin
& .\.tools\uv\uv.exe run pytest tests/anchors/test_fixation.py tests/anchors/test_h2_first_fixation_latency.py tests/anchors/test_preprocessing.py tests/anchors/test_registry.py -v
~~~

Expected: PASS; anchor count is 14/18 and provider count is 3.

- [ ] **Step 4: Commit**

~~~powershell
git add src/pilot_assessment/anchors/primitives/fixation.py src/pilot_assessment/anchors/plugins/h2_first_fixation_latency.py src/pilot_assessment/anchors/registry-v1.json tests/anchors/test_fixation.py tests/anchors/test_h2_first_fixation_latency.py tests/anchors/test_registry.py
git commit -m "feat: add first-fixation latency anchor"
~~~

### Task 28: Implement H3 Off-task Dwell and close M4-E

**Files:**
- Create: `src/pilot_assessment/anchors/plugins/h3_off_task_dwell.py`
- Create: `tests/anchors/test_h3_off_task_dwell.py`
- Modify: `src/pilot_assessment/anchors/registry-v1.json`
- Modify: `tests/anchors/test_registry.py`

- [ ] **Step 1: Write RED shared-allocation tests**

Prove H3 consumes the exact same memoized `gaze-aoi-intervals-v1` logical product/hash as H1 with provider `compute` called once, includes `other_scene` in the off-task numerator/denominator, pools all phase numerators/denominators, uses D `<5%`, A `5<=x<15%`, U `>=15%`, and never converts a zero denominator to `0% Desired`. Test complete finite off-task gaze as computed U.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_h3_off_task_dwell.py -v
~~~

Expected: RED because H3 is unavailable even though the shared gaze provider already exists.

- [ ] **Step 2: Implement H3 without duplicating gaze allocation**

~~~text
OffTaskDwell=100*off_task_gaze_dwell/total_gaze_dwell
~~~

No nonzero dwell produces `computed + U + no_gaze_dwell`. M5 later declares H1/H3 in the same `gaze_allocation` dependence group; M4 does not apply that likelihood strength.

- [ ] **Step 3: Register and run the M4-E gate**

~~~powershell
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh --anchor H3 --factory-module pilot_assessment.anchors.plugins.h3_off_task_dwell --factory-symbol create_plugin
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry verify
& .\.tools\uv\uv.exe run pytest tests/anchors/test_gaze_aoi.py tests/anchors/test_h1_aoi_dwell.py tests/anchors/test_fixation.py tests/anchors/test_h2_first_fixation_latency.py tests/anchors/test_h3_off_task_dwell.py tests/anchors/test_preprocessing.py tests/anchors/test_registry.py -q
~~~

Expected: PASS; exactly 15/18 production plugins and 3 preprocessing providers are software-verified.

- [ ] **Step 4: Commit**

~~~powershell
git add src/pilot_assessment/anchors/plugins/h3_off_task_dwell.py src/pilot_assessment/anchors/registry-v1.json tests/anchors/test_h3_off_task_dwell.py tests/anchors/test_registry.py
git commit -m "feat: add off-task dwell anchor and close M4-E"
~~~

## M4-F: H4/H5/O13 physiology and coupling anchors

### Task 29: Implement H4 ECG Fluctuation and control-physio windows

**Files:**
- Create: `src/pilot_assessment/anchors/primitives/physio_windows.py`
- Create: `src/pilot_assessment/anchors/primitives/ecg.py`
- Create: `src/pilot_assessment/anchors/plugins/h4_ecg_fluctuation.py`
- Create: `tests/anchors/test_physio_windows.py`
- Create: `tests/anchors/test_ecg.py`
- Create: `tests/anchors/test_h4_ecg_fluctuation.py`
- Modify: `src/pilot_assessment/anchors/registry-v1.json`
- Modify: `tests/anchors/test_registry.py`

- [ ] **Step 1: Write RED exact-window/RR tests**

Lock phase-start zero windows exactly:

~~~text
10 s -> [0,10)
30 s -> [0,30)
31 s -> [0,30),[1,31)
35 s -> [0,30),[5,35)
36 s -> [0,30),[5,35),[6,36)
~~~

Also test no cross-phase windows, deterministic JCS-based IDs, RR from adjacent peak timestamps assigned to the second peak, one pre-window peak allowed, baseline median, earliest max-absolute tie, and exact 20/40% open/closed boundaries. Deliberately corrupt `rr_interval_ms` and set `detection_confidence=0`; finite provided peak timestamps must still drive the same result.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_physio_windows.py tests/anchors/test_ecg.py tests/anchors/test_h4_ecg_fluctuation.py -v
~~~

Expected: RED because H4 primitives/plugin are absent.

- [ ] **Step 2: Implement provided-R-peak mode and finite overrides**

~~~text
HR=60/RR_seconds
HR0=median(finite positive baseline HR)
signed_delta_HR=100*(median(HR_window)/HR0-1)
fluctuation=abs(signed_delta_HR)
D <20%; A 20<=x<40%; U >=40%
~~~

Use only packaged `provided_r_peaks_v1`; never auto-fallback to raw peak detection. Extreme finite HR is computed. Existing stream/baseline with unusable RR, nonpositive HR0, or degenerate window is the specified computed-U override (`ecg_rr_unavailable`, `ecg_baseline_nonpositive`, or `physio_trace_unavailable`), not a quality rejection.

`physio_windows.py` exposes provider `control-physio-windows-v2`/`2.0.0`; `ecg.py` exposes provider `ecg-hr-trace-v1`/`1.0.0`. The former declares phase semantics and emits the exact window table; the latter declares ECG/baseline semantics and emits timestamped RR/HR. H4 declares both recipes. Neither provider silently falls back to another mode.

- [ ] **Step 3: Register and run GREEN**

~~~powershell
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh-preprocessor --provider control-physio-windows-v2 --factory-module pilot_assessment.anchors.primitives.physio_windows --factory-symbol create_provider
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh-preprocessor --provider ecg-hr-trace-v1 --factory-module pilot_assessment.anchors.primitives.ecg --factory-symbol create_provider
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh --anchor H4 --factory-module pilot_assessment.anchors.plugins.h4_ecg_fluctuation --factory-symbol create_plugin
& .\.tools\uv\uv.exe run pytest tests/anchors/test_physio_windows.py tests/anchors/test_ecg.py tests/anchors/test_h4_ecg_fluctuation.py tests/anchors/test_preprocessing.py tests/anchors/test_registry.py -v
~~~

Expected: PASS; anchor count is 16/18, provider count is 5, and signed-HR window trace is available for O13.

- [ ] **Step 4: Commit**

~~~powershell
git add src/pilot_assessment/anchors/primitives/physio_windows.py src/pilot_assessment/anchors/primitives/ecg.py src/pilot_assessment/anchors/plugins/h4_ecg_fluctuation.py src/pilot_assessment/anchors/registry-v1.json tests/anchors/test_physio_windows.py tests/anchors/test_ecg.py tests/anchors/test_h4_ecg_fluctuation.py tests/anchors/test_registry.py
git commit -m "feat: add ECG fluctuation anchor"
~~~

### Task 30: Implement H5 EEG Fluctuation

**Files:**
- Create: `src/pilot_assessment/anchors/primitives/eeg.py`
- Create: `src/pilot_assessment/anchors/plugins/h5_eeg_fluctuation.py`
- Create: `tests/anchors/test_eeg.py`
- Create: `tests/anchors/test_h5_eeg_fluctuation.py`
- Modify: `src/pilot_assessment/anchors/registry-v1.json`
- Modify: `tests/anchors/test_registry.py`

- [ ] **Step 1: Write RED DSP vectors and state-boundary tests**

Cover plan-time Nyquist `>35 Hz`; declared physical-unit conversion before all signal processing; per baseline/phase/support-segment constant demean + linear detrend before windows; 4th-order zero-phase 3-35 Hz SOS with exact padlen; 50/60 Hz Q=30 notch only below Nyquist; explicit bypass for 2/3 samples; CAR; 4 s/2 s phase-start windows with one deduplicated end-aligned tail; and the fixed Welch settings. Two physically identical arrays expressed in volts and microvolts with corresponding frozen conversion factors must produce the same numerical metric/evidence, while their parameter/plan/preprocessing/result fingerprints differ because the declared unit provenance differs. Assert theta `[4,8)`, alpha `[8,13)`, beta `[13,30]`, two finite bins per band, trapezoidal integration, channel median, baseline median, earliest max tie, and D `<=20`, A `<=50`, U `>50`.

Include a real locked-runtime numerical golden with at least 4 seconds of 256 Hz baseline and 4 seconds of 256 Hz task data across Fp1/Fp2/C3/C4. Use Float32 microvolt source values, phase offsets `0, pi/2, pi, 3*pi/2`, 50 Hz mains, CAR, baseline beta amplitude 1, and task beta amplitude `sqrt(1.35)`. Run the complete approved SciPy filter/notch/Welch pipeline and compare to the independently generated canonical `micro_oracles.py` value/tolerance; the state must be A and the metric must remain near the nominal 35% change, but the exact 4-second golden is frozen from this test vector rather than copied from the separate 2-second-phase workflow smoke. Do not replace this with a prefilled engagement value or a helper-only algebra test.

Deliberately set finite EEG rows to `signal_valid=false` and nonempty `artifact_code`; no row/window/channel may be removed. Missing channel/baseline configuration is not-computable, fewer than two samples is insufficient mathematical support, while configured spectrum/baseline degeneracy is a computed-U override. Lock the exact override codes `eeg_spectrum_degenerate` and `eeg_baseline_degenerate`. An unknown, non-linear, non-finite, or non-positive declared unit conversion blocks plan validation; a live stream unit descriptor that differs from the compiled descriptor blocks request validation before provider/plugin/sink access.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_eeg.py tests/anchors/test_h5_eeg_fluctuation.py -v
~~~

Expected: RED because EEG DSP/H5 are absent.

- [ ] **Step 2: Implement the exact versioned pipeline**

Use explicit SciPy arguments rather than library defaults:

~~~text
nperseg=min(round_half_even(2*fs),window_sample_count)
noverlap=floor(nperseg/2)
nfft=next_power_of_two(nperseg)
window=periodic Hann; scaling=density; detrend=false; one-sided
E_channel=beta/(alpha+theta+1e-12)
E_window=median(configured channel E)
E0=median(baseline E_window)
delta_E=100*((E_window+1e-12)/(E0+1e-12)-1)
primary=max(abs(delta_E))
~~~

Convert every configured channel with the frozen `input_unit` plus finite positive `scale_to_volts` before demean/detrend/filtering. Both fields enter the preprocessing parameter hash, execution-plan fingerprint, and H5 dependency fingerprint. Reference mode performs no ICA, amplitude clipping, medical-range filtering, validity-flag admission, automatic channel removal, or runtime unit guessing.

`eeg.py` exposes `create_provider()` for `eeg-engagement-windows-v1`/`1.0.0`; it declares EEG, baseline/channel/phase semantics, the exact DSP recipe, and a typed engagement-window table. H5 consumes this registered product.

- [ ] **Step 3: Register exact NumPy/SciPy closure and run GREEN**

~~~powershell
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh-preprocessor --provider eeg-engagement-windows-v1 --factory-module pilot_assessment.anchors.primitives.eeg --factory-symbol create_provider
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh --anchor H5 --factory-module pilot_assessment.anchors.plugins.h5_eeg_fluctuation --factory-symbol create_plugin
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry verify
& .\.tools\uv\uv.exe run pytest tests/anchors/test_eeg.py tests/anchors/test_h5_eeg_fluctuation.py tests/anchors/test_preprocessing.py tests/anchors/test_registry.py -v
~~~

Expected: PASS; anchor count is 17/18 and provider count is 6. DSP float goldens pass `abs<=1e-6 OR rel<=1e-6`; boundary constructions lie outside tolerance.

- [ ] **Step 4: Commit**

~~~powershell
git add src/pilot_assessment/anchors/primitives/eeg.py src/pilot_assessment/anchors/plugins/h5_eeg_fluctuation.py src/pilot_assessment/anchors/registry-v1.json tests/anchors/test_eeg.py tests/anchors/test_h5_eeg_fluctuation.py tests/anchors/test_registry.py
git commit -m "feat: add EEG fluctuation anchor"
~~~

### Task 31: Implement O13 Physio-control Coupling and close M4-F

**Files:**
- Create: `src/pilot_assessment/anchors/plugins/o13_physio_control_coupling.py`
- Create: `tests/anchors/test_o13_physio_control_coupling.py`
- Modify: `src/pilot_assessment/anchors/primitives/physio_windows.py`
- Modify: `src/pilot_assessment/anchors/registry-v1.json`
- Modify: `tests/anchors/test_registry.py`

- [ ] **Step 1: Write RED per-window dependency/coupling tests**

Repeat exact 10/30/31/35/36-second window/ID vectors. Prove O13 recomputes O1/O5/O7 through frozen algorithm profiles inside each window rather than reading their session states; uses signed H4 HR delta rather than absolute fluctuation; retains partial support; and does not impose a minimum window/coverage count. Test negative signed HR activation=0, exact 5/20% state boundaries, earliest max tie, and all window traces.

State split must be exact: a control component lacking mathematical support in any window makes session `dependency_missing`; H4 missing/config/error also causes dependency-missing; but H4 `computed U` without signed trace produces `computed + U + physio_trace_unavailable`.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_o13_physio_control_coupling.py -v
~~~

Expected: RED because O13 is unavailable.

- [ ] **Step 2: Implement continuous coupling**

~~~text
qO1,qO5,qO7 = D/A/U -> 1/0.5/0
Q_control=0.50*qO1+0.25*qO5+0.25*qO7
activation=clip((signed_delta_HR_pct-10)/(20-10),0,1)
coupling_loss=100*activation*(1-Q_control)
O13=max(coupling_loss over windows)
D <5%; A 5<=x<20%; U >=20%
~~~

The window ID is `cpw-` plus the first 24 lowercase hex of SHA-256 over the RFC 8785 canonical array `['control-physio-grid-v2', phase_id, start_t_ns, end_t_ns]`; store the full hash too. M5 later applies `likelihood_strength=0.50`.

- [ ] **Step 3: Register and run the M4-F gate**

~~~powershell
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh-preprocessor --provider control-physio-windows-v2
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh --anchor H4
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry refresh --anchor O13 --factory-module pilot_assessment.anchors.plugins.o13_physio_control_coupling --factory-symbol create_plugin
& .\.tools\uv\uv.exe run python -m pilot_assessment.anchors.registry verify
& .\.tools\uv\uv.exe run pytest tests/anchors/test_physio_windows.py tests/anchors/test_ecg.py tests/anchors/test_h4_ecg_fluctuation.py tests/anchors/test_eeg.py tests/anchors/test_h5_eeg_fluctuation.py tests/anchors/test_o13_physio_control_coupling.py tests/anchors/test_preprocessing.py tests/anchors/test_registry.py -q
~~~

Expected: PASS; registry/catalog closure is exact, 18/18 individual production plugins and all 6 preprocessing providers are software-verified, and both H4 and O13 pass after the shared window-provider refresh.

- [ ] **Step 4: Commit**

~~~powershell
git add src/pilot_assessment/anchors/primitives/physio_windows.py src/pilot_assessment/anchors/plugins/o13_physio_control_coupling.py src/pilot_assessment/anchors/registry-v1.json tests/anchors/test_o13_physio_control_coupling.py tests/anchors/test_registry.py
git commit -m "feat: add physio-control coupling and close M4-F"
~~~

## M4-G: lightweight workflows, one physical smoke, determinism, wheel, and handoff

### Task 32: Assemble compact real-plugin scenarios and the single smoke candidate plan

**Files:**
- Create: `tests/m4_support/scenario_inputs.py`
- Create: `tests/m4_support/request_builder.py`
- Create: `tests/fixtures/m4/m4-scenario-expected-v0.1.json`
- Create: `tests/fixtures/m4/cases/m4-workflow-smoke-v0.1/session-semantic-snapshot.json`
- Create: `tests/fixtures/m4/cases/m4-workflow-smoke-v0.1/resolved-reference-set.json`
- Create: `tests/fixtures/m4/cases/m4-workflow-smoke-v0.1/execution-plan.candidate.json`
- Create: `tests/anchors/test_lightweight_scenario_contract.py`
- Create: `tests/anchors/test_reference_profile_completeness.py`
- Create: `tests/anchors/test_no_quality_gate.py`
- Modify: `tests/anchors/test_registry.py`
- Modify: `tests/anchors/test_lightweight_fixture_contract.py`

- [ ] **Step 1: Write RED tests for compact inputs, one candidate plan, and exact profile coverage**

The tests must initially require:

1. `all_desired_aligned_input()`, `all_unacceptable_aligned_input()`, and `mixed_aligned_input()` factories;
2. a separate expected-scenario resource whose canonical ID order is exactly O1-O13 then H1-H5;
3. exactly one persisted candidate plan, bound to `m4-workflow-smoke-v0.1`;
4. an exact-18 catalog/registry coverage ledger containing every plugin, parameter resource, preprocessing provider, dependency, artifact, D/A/U micro test, boundary, override, missing/config/dependency case, fingerprint test, and unrelated-anchor perturbation assertion;
5. no `invalid_quality`, quality gate, result-like object, precomputed `q_control`, or precomputed O8/O13 value in any scenario input;
6. no all-desired/all-unacceptable/mixed/state physical bundle or sidecar directory.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_lightweight_scenario_contract.py tests/anchors/test_reference_profile_completeness.py tests/anchors/test_no_quality_gate.py tests/anchors/test_registry.py -v
~~~

Expected: RED because the compact factories, separate scenario expected vector, candidate sidecars, and coverage ledger do not exist.

- [ ] **Step 2: Implement compact raw/aligned scenario factories and freeze expected vectors**

`tests/m4_support/scenario_inputs.py` exposes only these high-level factories:

~~~text
all_desired_aligned_input() -> CompactScenarioInput
all_unacceptable_aligned_input() -> CompactScenarioInput
mixed_aligned_input() -> CompactScenarioInput
state_matrix_base_input() -> CompactScenarioInput
~~~

`CompactScenarioInput` contains small raw/aligned X, independent reference, U, scene/AOI, raw gaze, EEG, ECG/R-peak tables plus semantic/config bindings and events. It contains no `AnchorMeasurement`, `AnchorResult`, evidence state, likelihood, expected result map, precomputed `q_control`, or derived O8/O13 number. It creates no Session Bundle, CSV, Parquet, image, or other dense file. Its request builder constructs one test-only in-memory `AlignedSession`, one reference view and matching `ReferenceViewCandidate` from those same objects, then calls the exact binder; it must not claim this compact path passed M1–M3. The real production evaluator and packaged registry consume the bound request.

Freeze `m4-scenario-expected-v0.1.json` independently from production results. It contains all-desired, all-unacceptable, mixed, and state-matrix expected vectors, but `scenario_inputs.py` may not import or read it. The mixed vector remains:

~~~text
O1=90% D; O2=3 ft A; O3=(1 ft,6 s) U; O4=10 s D;
O5=3.0 A; O6=70% U; O7=1 Hz D;
O8=0.81*sqrt(1/3) A; O9=1.5 Hz A;
O10=recovery_missed U; O11=250 ms D; O12=500 ms A;
O13≈6.25% A from signed HR and per-window control components;
H1=85% D; H2=750 ms A; H3=15% U; H4≈15% D;
H5=the independently recomputed §12.18 numerical value in state A.
~~~

The input tables must mechanically produce each value. Expected JSON is loaded only after evaluation. Regeneration uses test-local formulas/`micro_oracles.py`, never production plugin code or a saved production result.

- [ ] **Step 3: Assemble exactly one smoke candidate plan from immutable M1-M3 output**

`tests/m4_support/request_builder.py` runs public M1 loading, M2 ingestion, and M3 synchronization on the Task 0 session-scoped bundle. The smoke assembler constructs the bundle `ReferenceViewCandidate` only from that same live M1–M3 outcome and the locked test source contract, binds the frozen resolved-reference snapshot through the exact three-parameter binder, and then hand-binds the approved exact catalog, parameters, registry and semantic snapshot into a new request. It resolves trusted packaged factories only to verify `definition()` and implementation closure; it never calls `compute()` while constructing the plan, reads production output to form expectations, reads a ModelBundle, or implements a general plan compiler. This smoke path is distinct from the compact in-memory path above.

Expose these boundaries:

~~~text
assemble_smoke_candidate(bundle_root: Path, output_root: Path) -> Path
build_compact_request(scenario: CompactScenarioInput) -> AnchorEvaluationRequest
write_runtime_manifest(case_root: Path, output_path: Path) -> Path
~~~

The only persisted case is `m4-workflow-smoke-v0.1`. The candidate plan records exact source, synchronization, semantic, resolved-reference, catalog, registry, parameter, provider, plugin-definition, and implementation-closure fingerprints; it fixes `scientific_validation_status=not_supported` and `formal_run_authorized=false`. The three candidate sidecars are small JSON resources. Dense bundle files stay in the temporary directory and are never copied below `tests/fixtures/m4`.

- [ ] **Step 4: Close the exact-18 profile and no-quality-gate ledger**

Assert:

- catalog IDs, registry plugin factories, parameter files, provider factories, dependency edges, and artifact kinds are exact and complete;
- every Task 14-31 plugin has focused D/A/U, exact boundary, override, missing/config/dependency, version/fingerprint, finite-extreme, and unrelated-anchor invariance coverage;
- all-Unacceptable inputs are finite and mathematically supported, so every plugin remains computed rather than filtered;
- central engine source contains no O1-O13/H1-H5 dispatch switch;
- M2 diagnostic validity/confidence fields never become M4 admission or likelihood controls;
- the smoke candidate is the only persisted execution plan candidate.

- [ ] **Step 5: Run GREEN and commit**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_lightweight_scenario_contract.py tests/anchors/test_reference_profile_completeness.py tests/anchors/test_no_quality_gate.py tests/anchors/test_registry.py tests/anchors/test_lightweight_fixture_contract.py -v
rg -n 'if anchor_id|match anchor_id|O1.*O2.*O3|H1.*H2.*H3' src/pilot_assessment/anchors
git diff --check
~~~

Expected: tests PASS and the dispatch scan finds no central anchor-ID switch. Review any benign definition/resource hits rather than suppressing the scan.

~~~powershell
git add tests/m4_support/scenario_inputs.py tests/m4_support/request_builder.py tests/fixtures/m4/m4-scenario-expected-v0.1.json tests/fixtures/m4/cases/m4-workflow-smoke-v0.1 tests/anchors/test_lightweight_scenario_contract.py tests/anchors/test_reference_profile_completeness.py tests/anchors/test_no_quality_gate.py tests/anchors/test_registry.py tests/anchors/test_lightweight_fixture_contract.py
git commit -m "test: assemble lightweight M4 verification inputs"
~~~

### Task 33: Verify compact real-plugin scenarios, state semantics, perturbations, and extension/replay

**Files:**
- Create: `tests/anchors/test_reference_scenarios.py`
- Create: `tests/anchors/test_state_matrix.py`
- Create: `tests/anchors/test_data_to_anchor_perturbations.py`
- Create: `tests/anchors/test_extension_replay.py`
- Create: `tests/m4_support/extension_plugins.py`
- Create: `tests/fixtures/m4/extension-catalog-v1.json`
- Create: `tests/fixtures/m4/extension-catalog-v2-retired.json`

- [ ] **Step 1: Add the compact real-plugin verification tests and require first-run PASS**

This is verification-only for already implemented Tasks 13-31. Write the assertions, then run:

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_reference_scenarios.py tests/anchors/test_state_matrix.py tests/anchors/test_data_to_anchor_perturbations.py -v
~~~

Expected: PASS on first execution. A failure is an implementation/spec mismatch: stop, create a separately numbered corrective task and commit, rerun the failing per-anchor gate, then restart Task 33. Do not edit the input or expected resource to match production output.

Required assertions are:

1. all-desired calls public `evaluate()` with all 18 production plugins and yields expected=18, executed=18, computed=18, all D;
2. all-unacceptable calls the same boundary and yields 18/18 computed U, applicable=18, raw availability=1, including finite extreme values and deliberately poor M2 diagnostics with no quality filtering;
3. mixed yields the separately frozen, mechanically recomputable D/A/U vector and executes real O8/O9/O13 dependency edges;
4. state-matrix uses `AnchorEvaluator.for_testing` exact hooks only for O1's consumer-local X projection miss, O4's anchor-transaction failure, and O5's consumer-local `movement-events-v1` failure. O2 receives a declared commanded-reference view whose timestamps have no joinable temporal overlap, so the real O2 plugin returns `not_computable`; O3 is marked non-applicable by the frozen task semantics, so the real O3 plugin returns `not_applicable`. O8 and O9 propagate dependency-missing through real edges; the other 11 are computed; report=`ready_partial`; expected=18, executed=18, not_applicable=1, applicable=17, computed=11, raw availability=`11/17`;
5. no state scenario corrupts source input, mutates the public plan/registry, fails a shared provider globally, or requires a production plugin to throw;
6. input and expected bytes are independent, and production modules never import expected JSON.

The perturbation matrix is exact:

| Perturbation | Must change | Must remain unchanged |
|---|---|---|
| X/reference error | O2 and its dependent closure | H5 |
| U turning/step signal | corresponding control anchors/dependents | H4 and H5 |
| gaze/AOI allocation | H1 and H3 | O2 |
| provided R-peaks | H4 and O13 | H5 |
| EEG beta component | H5 | H4 |

Each perturbation must also change the relevant input/result/evaluation fingerprint. A source checksum alone is not sufficient evidence.

- [ ] **Step 2: Write the extension/replay RED test**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_extension_replay.py -v
~~~

Expected: RED because the tiny extension catalogs and test factories do not exist. This RED must not generate a Session Bundle or image.

- [ ] **Step 3: Implement the in-memory extension/replay fixture**

Use a tiny explicit catalog and minimal aligned input to prove:

- adding X1 increases only the new revision's canonical inventory; no central engine switch changes;
- retiring X1 affects only the next revision; replay of the old revision produces identical results/fingerprints;
- parameter revision changes parameter/result/evaluation fingerprints;
- plugin version, provider version, or implementation digest changes implementation/result/evaluation identity even if a constructed raw value is numerically equal;
- an unknown or untrusted implementation is blocked before factory/provider/sink access;
- source inputs and the old published revision remain immutable.

- [ ] **Step 4: Run the combined lightweight scenario gate and commit**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/anchors/test_reference_scenarios.py tests/anchors/test_state_matrix.py tests/anchors/test_data_to_anchor_perturbations.py tests/anchors/test_extension_replay.py tests/anchors/test_reference_profile_completeness.py tests/anchors/test_no_quality_gate.py -v
& .\.tools\uv\uv.exe run pytest tests/anchors -q
git diff --check
~~~

Expected: PASS without creating a physical fixture outside Task 0's temporary session fixture.

~~~powershell
git add tests/anchors/test_reference_scenarios.py tests/anchors/test_state_matrix.py tests/anchors/test_data_to_anchor_perturbations.py tests/anchors/test_extension_replay.py tests/m4_support/extension_plugins.py tests/fixtures/m4/extension-catalog-v1.json tests/fixtures/m4/extension-catalog-v2-retired.json
git commit -m "test: verify lightweight M4 scenarios and replay"
~~~

### Task 34: Run and freeze the single public 10-second M1-to-M4 workflow

**Files:**
- Create: `tests/e2e/test_m4_workflow_smoke.py`
- Create: `tests/e2e/test_m4_source_immutability.py`
- Create: `tests/anchors/test_cross_process_determinism.py`
- Modify: `tests/m4_support/request_builder.py`
- Modify: `tests/anchors/test_no_quality_gate.py`
- Modify: `tests/anchors/test_reference_profile_completeness.py`
- Modify: `tests/anchors/test_lightweight_fixture_contract.py`
- Move after verification: `tests/fixtures/m4/cases/m4-workflow-smoke-v0.1/execution-plan.candidate.json` to `tests/fixtures/m4/cases/m4-workflow-smoke-v0.1/execution-plan.json`
- Create after verification: `tests/fixtures/m4/cases/m4-workflow-smoke-v0.1/runtime-manifest.json`

- [ ] **Step 1: Add the public workflow, immutability, and determinism tests**

Use one session-scoped bundle generated from Task 0's frozen recipe. The test path is exactly:

~~~text
public M1 load -> public M2 ingestion -> public M3 synchronization
-> construct bundle ReferenceViewCandidate from that live M1-M3 outcome
-> bind frozen ResolvedReferenceSetSnapshot with the exact binder
-> construct a new AnchorEvaluationRequest from validated frozen sidecars
-> public anchors.api.evaluate(request, sink)
~~~

Assert:

- 452 PNG, 468 declared path references, exactly 9,331 physical source-table rows, and no tracked dense asset;
- 18 expected, 18 executed, 18 computed, with at least one D, one A, and one U;
- the full result vector equals the separate Task 0 expected vector within its frozen per-value tolerance;
- O8, O9, and O13 execute real typed-DAG dependencies;
- O2, O6, H1/H3, H4, and H5 can each be independently recomputed from source inputs and equal production results;
- pilot-camera rows and provenance survive M1-M3 although no current anchor consumes that modality;
- source files and M3 aligned frames remain byte/value/order identical before and after M4;
- repeated reports, logical artifacts, result fingerprints, and evaluation fingerprints are deterministic;
- `formal_run_authorized=false` and `scientific_validation_status=not_supported`.

Cross-process tests run two subprocesses against the same bundle path while varying working directory, TEMP location, and ready-node scheduler order. They must not generate another fixture family or use an absolute path in canonical identity.

- [ ] **Step 2: Require first-run PASS or use the corrective-task protocol**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/e2e/test_m4_workflow_smoke.py tests/e2e/test_m4_source_immutability.py tests/anchors/test_cross_process_determinism.py -v
~~~

Expected: PASS against Tasks 0-33. If it fails, stop before freezing any executable plan. Add a separately reviewed corrective task/commit naming the exact plugin/framework defect, rerun its focused test and Task 33, then restart this task. Never weaken or regenerate expected values from production output.

- [ ] **Step 3: Measure the lightweight gates without creating timing assertions**

~~~powershell
$smokeTime = Measure-Command {
  & .\.tools\uv\uv.exe run pytest tests/e2e/test_m4_workflow_smoke.py -q
  if ($LASTEXITCODE -ne 0) { throw 'M4 workflow smoke failed' }
}
$focusedTime = Measure-Command {
  & .\.tools\uv\uv.exe run pytest tests/anchors tests/e2e/test_m4_workflow_smoke.py tests/e2e/test_m4_source_immutability.py -q
  if ($LASTEXITCODE -ne 0) { throw 'focused M4 suite failed' }
}
$smokeTime
$focusedTime
~~~

Record both durations in the task handoff. The targets are below 30 seconds for the smoke and below 60 seconds for the focused suite on the current Windows development environment, but pytest must not assert machine-dependent elapsed time.

- [ ] **Step 4: Promote only the verified smoke plan and write one runtime manifest**

Promote the candidate bytes without normalization, then hash/validate the final sidecars:

~~~powershell
$caseRoot = 'tests/fixtures/m4/cases/m4-workflow-smoke-v0.1'
git mv (Join-Path $caseRoot 'execution-plan.candidate.json') (Join-Path $caseRoot 'execution-plan.json')
if ($LASTEXITCODE -ne 0) { throw 'smoke candidate promotion failed' }
& .\.tools\uv\uv.exe run python -m tests.m4_support.request_builder write-runtime-manifest --case-root $caseRoot --output (Join-Path $caseRoot 'runtime-manifest.json')
if ($LASTEXITCODE -ne 0) { throw 'runtime manifest generation failed' }
~~~

`runtime-manifest.json` hashes the semantic snapshot, resolved-reference set, final execution plan, source/synchronization identity, catalog/registry/parameters, every plugin/provider definition and implementation closure, plus itself by excluding only its own fingerprint field. There is exactly one runtime manifest.

- [ ] **Step 5: Rerun from final filenames and commit the freeze**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/e2e/test_m4_workflow_smoke.py tests/e2e/test_m4_source_immutability.py tests/anchors/test_cross_process_determinism.py tests/anchors/test_reference_scenarios.py tests/anchors/test_state_matrix.py tests/anchors/test_data_to_anchor_perturbations.py tests/anchors/test_extension_replay.py tests/anchors/test_no_quality_gate.py tests/anchors/test_reference_profile_completeness.py tests/anchors/test_lightweight_fixture_contract.py -v
git diff --check
~~~

Expected: PASS from final filenames. This is the first executable smoke-plan freeze boundary; future behavior changes require new plugin/provider versions and a new execution-plan revision.

~~~powershell
git add tests/e2e/test_m4_workflow_smoke.py tests/e2e/test_m4_source_immutability.py tests/anchors/test_cross_process_determinism.py tests/m4_support/request_builder.py tests/anchors/test_no_quality_gate.py tests/anchors/test_reference_profile_completeness.py tests/anchors/test_lightweight_fixture_contract.py tests/fixtures/m4/cases/m4-workflow-smoke-v0.1
git commit -m "test: freeze deterministic M4 workflow smoke"
~~~

### Task 35: Package the one-case smoke profile and add the durable isolated-wheel gate

**Files:**
- Create: `src/pilot_assessment/verification/__init__.py`
- Create: `src/pilot_assessment/verification/m4_fixture.py`
- Create: `src/pilot_assessment/verification/m4_smoke.py`
- Create: `src/pilot_assessment/verification/profile_data/__init__.py`
- Create: `src/pilot_assessment/verification/profile_data/m4-smoke-fixture-index-v0.1.json`
- Create: `src/pilot_assessment/verification/profile_data/cases/m4-workflow-smoke-v0.1/session-semantic-snapshot.json`
- Create: `src/pilot_assessment/verification/profile_data/cases/m4-workflow-smoke-v0.1/resolved-reference-set.json`
- Create: `src/pilot_assessment/verification/profile_data/cases/m4-workflow-smoke-v0.1/execution-plan.json`
- Create: `src/pilot_assessment/verification/profile_data/cases/m4-workflow-smoke-v0.1/runtime-manifest.json`
- Create: `tests/verification/test_m4_fixture.py`
- Create: `tests/verification/test_m4_smoke.py`
- Create: `scripts/verify_m4.ps1`
- Modify: `tests/test_package_metadata.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write RED public-loader and CLI tests**

The fixed CLI is:

~~~powershell
python -m pilot_assessment.verification.m4_smoke --fixture <bundle-root>
~~~

Stdout is one canonical JSON object with disposition, expected/executed/computed counts, D/A/U counts, evaluation fingerprint, ordered result fingerprints, ordered logical artifact hashes, import origin, `formal_run_authorized=false`, and `scientific_validation_status=not_supported`.

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/verification/test_m4_fixture.py tests/verification/test_m4_smoke.py -v
~~~

Expected: RED because the verification package and packaged smoke resources do not exist.

- [ ] **Step 2: Implement the one-case package loader and smoke runner**

The loader boundary is exact:

~~~python
def load_packaged_m4_fixture_request(
    bundle_root: str | Path,
) -> AnchorEvaluationRequest:
    """Load the allowlisted 10-second software fixture through public M1-M3 and frozen M4 sidecars."""
~~~

The index contains exactly one `m4-workflow-smoke-v0.1` entry with contract ID/version, expected session ID, resource prefix, and canonical index fingerprint. The loader runs public M1-M3, requires a non-blocked synchronized session, validates all four packaged sidecars and their fingerprints, validates live source/synchronization identity, recomputes the bundle `ReferenceViewCandidate`, calls the exact binder, and constructs a new runtime request. The four packaged sidecar byte sequences remain unchanged; no serialized request object is returned unchanged.

It never imports `tests`, reads repository paths, compiles a ModelBundle, derives/rebinds a plan fingerprint, scans plugin directories, dynamically imports a caller path, or accepts caller sidecars. An unknown session ID, mutated source/sidecar, fingerprint mismatch, or descriptor/view mismatch fails before any factory, provider, or sink access. This loader is the only current production-like bundle candidate producer; general bundle and ModelBundle resource resolution/candidate production remain M5/M6 responsibilities.

Tests prove:

1. AST/import and isolated-process guards find no `tests`, compiler, scan, or dynamic-import dependency;
2. the valid smoke fixture builds a fresh request from live M1–M3, a recomputed bundle candidate, the exact binder and byte-identical frozen sidecars, then yields exactly 18 results;
3. unknown/mutated inputs fail with factory/provider/sink call counts all zero;
4. the four packaged sidecars are byte-identical to Task 34's frozen resources;
5. wheel metadata includes v0.2 contracts/schemas, catalog, registry, 18 anchor factories, six provider factories, implementation closure, parameters, one index, four sidecars, loader, and runner.

- [ ] **Step 3: Implement `scripts/verify_m4.ps1` as the durable lightweight gate**

The script requires `-FormatSampleCsv` or `PILOT_ASSESSMENT_FORMAT_SAMPLE_CSV`, creates a verified TEMP root, generates `m4-workflow-smoke-v0.1` exactly once from the frozen recipe, and exports that path as `PILOT_ASSESSMENT_M4_SMOKE_BUNDLE`. `tests/conftest.py` reuses the environment path read-only instead of rebuilding. The installed-wheel smoke later consumes the same bundle root.

Execute in this order:

1. lightweight recipe/expected/source-hash contract;
2. schema regeneration and no diff;
3. per-anchor micro suites;
4. compact all-D/all-U/mixed/state real-plugin tests;
5. data-to-anchor perturbations and no-quality-gate checks;
6. extension/retire/version replay;
7. one physical M1-M4 smoke, source immutability, and cross-process determinism;
8. repository-external M2/M3 format-interface tests using the supplied CSV only as a format sample;
9. full pytest with unexpected skips treated as failure;
10. Ruff format, Ruff lint, and `ty check src`;
11. one fresh wheel build and member/import-origin audit;
12. one repository-external isolated-venv CLI smoke with `PYTHONPATH` cleared and the same bundle root;
13. `git diff --check`, no tracked CSV/Parquet/PNG under `tests/fixtures/m4`, and clean source boundaries.

The script exports frozen runtime dependencies, builds exactly one wheel, installs it into a Python 3.11 isolated environment, changes working directory outside the repository, and invokes:

~~~powershell
& $isolatedPython -I -m pilot_assessment.verification.m4_smoke --fixture $bundleRoot
~~~

Before cleanup, resolve the temporary root and prove it is below the resolved system TEMP directory, its leaf starts with `pilot-assessment-m4-wheel-smoke-`, and it is not a reparse point. Never recursively delete an unverified computed path. The long 90-second fixture is absent from this script and from M4 completion.

- [ ] **Step 4: Run focused GREEN and the complete durable gate**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/verification/test_m4_fixture.py tests/verification/test_m4_smoke.py tests/test_package_metadata.py -v
& .\scripts\verify_m4.ps1 -FormatSampleCsv $env:PILOT_ASSESSMENT_FORMAT_SAMPLE_CSV
~~~

Expected: PASS. Record fresh test counts/skips, dependency versions, one recipe/expected/source-hash/runtime-manifest fingerprint set, 452/468/9,331 budgets, compact scenario counts, wheel SHA-256, installed import origin, smoke summary, and measured smoke/focused durations. Timing is a handoff metric, not a brittle assertion.

- [ ] **Step 5: Commit**

~~~powershell
git add src/pilot_assessment/verification tests/verification/test_m4_fixture.py tests/verification/test_m4_smoke.py scripts/verify_m4.ps1 tests/test_package_metadata.py tests/conftest.py
git commit -m "feat: add lightweight M4 delivery verification"
~~~
### Task 36: Run the fresh completion gate and close M4 documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/product/README.md`
- Modify: `docs/product/01_PRODUCT_OVERVIEW.md`
- Modify: `docs/product/04_REFERENCE_MODEL_V0_1.md`
- Modify: `docs/product/09_VALIDATION_AND_HANDOFF.md`
- Modify: `docs/product/10_DESIGN_SELF_REVIEW.md`
- Modify: `docs/product/11_IMPLEMENTATION_STATUS.md`
- Modify: `docs/product/specs/2026-07-13-m4-anchor-evidence-availability-design.md`
- Modify: `docs/product/specs/2026-07-13-m4-lightweight-workflow-validation-amendment.md`
- Modify: `docs/product/specs/2026-07-13-m4-task3-reference-candidate-binding-amendment.md`
- Modify: `docs/product/reviews/2026-07-13-autonomous-review-ledger.md`
- Modify: `docs/product/plans/2026-07-13-m4-anchor-evidence-availability-implementation-plan.md`
- Modify: `docs/product/plans/2026-07-13-m4-anchor-evidence-availability-replacement-implementation-plan.md`

- [ ] **Step 1: Start from a clean tree and run the durable gate again**

~~~powershell
git status --short
& .\scripts\verify_m4.ps1 -FormatSampleCsv $env:PILOT_ASSESSMENT_FORMAT_SAMPLE_CSV
~~~

Expected: empty status before the run and full PASS. If any command is stale/failing, fix code/tests/script in a separate implementation commit and rerun from the beginning.

- [ ] **Step 2: Update only evidence-backed status statements**

Record:

- implementation commit range and final implementation commit;
- exact 18/18 plugin, compact all-D/all-U/mixed, and state-matrix counts;
- fresh pytest count and every skip reason;
- one recipe/expected-vector/source-hash/runtime-manifest fingerprint set;
- exact 452 PNG, 468 declared-path-reference, and 9,331 physical-row budgets;
- registry/catalog/evaluation and wheel hashes;
- isolated import origin, one public/isolated smoke summary, and measured smoke/focused durations;
- source-byte immutability result;
- `formal_run_authorized=false`; reference model `scientific_validation_status=engineering_default`; synthetic fixture report status `not_supported`;
- remaining M5/M6/Windows frontend work.

Change `docs/product/10_DESIGN_SELF_REVIEW.md` candidate-only language to historical approved language. Do not change D-021-D-028 semantics.

In the accepted lightweight amendment, update §6 to identify the approved/completed replacement plan and check only those §8 implementation items supported by this fresh gate. Preserve the original heavy-fixture measurements as historical rationale. Keep the superseded plan as a historical stub; it must not regain executable tasks or imply current authority.

- [ ] **Step 3: Mark all genuinely completed checkboxes and run documentation checks**

~~~powershell
$tokens = @('TO'+'DO', 'TB'+'D', 'FIX'+'ME')
foreach ($token in $tokens) {
  if (Select-String -Path docs/product/plans/2026-07-13-m4-anchor-evidence-availability-replacement-implementation-plan.md -Pattern $token -SimpleMatch) {
    throw "unresolved placeholder token: $token"
  }
}
$statusFiles = @(
  'README.md',
  'docs/product/README.md',
  'docs/product/01_PRODUCT_OVERVIEW.md',
  'docs/product/04_REFERENCE_MODEL_V0_1.md',
  'docs/product/09_VALIDATION_AND_HANDOFF.md',
  'docs/product/10_DESIGN_SELF_REVIEW.md',
  'docs/product/11_IMPLEMENTATION_STATUS.md',
  'docs/product/specs/2026-07-13-m4-anchor-evidence-availability-design.md',
  'docs/product/specs/2026-07-13-m4-lightweight-workflow-validation-amendment.md',
  'docs/product/specs/2026-07-13-m4-task3-reference-candidate-binding-amendment.md',
  'docs/product/reviews/2026-07-13-autonomous-review-ledger.md',
  'docs/product/plans/2026-07-13-m4-anchor-evidence-availability-implementation-plan.md',
  'docs/product/plans/2026-07-13-m4-anchor-evidence-availability-replacement-implementation-plan.md'
)
$stalePhrases = @(
  ('18/18 reference anchors specified, ' + '0/18 implemented'),
  ('18/18 已设计、' + '0/18 已实现'),
  ('实施计划已形成并' + '等待批准'),
  ('实施计划已形成并' + '等待用户批准'),
  ('implementation plan ' + 'awaits approval'),
  ('plan ' + 'awaiting approval'),
  ('replacement plan ' + '尚待'),
  ('Review ' + 'candidate'),
  ('written for review; no task below is ' + 'authorized'),
  ('尚未开始' + '执行')
)
foreach ($phrase in $stalePhrases) {
  $hits = Select-String -Path $statusFiles -Pattern $phrase -SimpleMatch
  if ($hits) { $hits; throw "stale M4 status remains: $phrase" }
}
git diff --check
~~~

Expected: entry documents consistently state `M4 engineering-verified`, 18/18 implemented, `formal_run_authorized=false`, reference-model status `engineering_default`, synthetic fixture status `not_supported`, and M5/M6/frontend still pending; no approval/0-of-18 wording survives in a current-status surface.

- [ ] **Step 4: Commit the docs-only closure**

~~~powershell
git add README.md docs/product
git commit -m "docs: close M4 implementation plan"
~~~

- [ ] **Step 5: Verify the committed handoff**

~~~powershell
git status --short
git log -3 --oneline
~~~

Expected: clean tree. Only now may the project state say `M4 engineering-verified`; this still does not authorize BN inference, a formal assessment run, or a scientific/aviation-valid performance claim.

## Specification-to-task coverage matrix

| Approved design section | Implementation tasks |
|---|---|
| §1 goals and captured-format boundary | 0-1, 32-36 |
| §2 exclusions and M4/M5/M6 separation | 3-7, 13, 32, 35-36 |
| §3 M4-A through M4-G approach | 2-36 stage gates |
| §4 extensibility, negative evidence, honest capability | 5, 7, 9, 12-13, 14-31, 32-34 |
| §5 architecture/ownership | 3-13, 35 |
| §6 input/core contract/compiled plan | 3-7, 13, 32 |
| §7 AnchorResult v0.2 | 2, 5-6, 12 |
| §8 blocked/per-anchor states | 3-5, 9, 12-13, 33 |
| §9 typed dependency DAG | 4, 7, 9, 13, 21-22, 31 |
| §10 temporal/grid/gap/aggregation | 10, 12, 14-31, 34 |
| §11 scoring | 12, 14-31 |
| §12 O1-O13/H1-H5 algorithms | 14-31 |
| §13 execution/artifact/fingerprint/registry | 8-13, 32, 34-35 |
| §14 fixtures and completion commands | 0, 32-36 |
| §15 milestone completion gates | 6, 13, 20, 25, 28, 31, 36 |
| §16 documentation migration | 36 |
| §17 written-spec gate | Task 36 rechecks authority/status; the original design gate was satisfied by commit `bc08771`, the lightweight amendment and replacement plan were approved on 2026-07-13, and the Task 3 candidate-binding amendment was approved before the revised Task 3 |
| Lightweight amendment §3.1 contract/framework layer | 2-13 |
| Lightweight amendment §3.2 per-anchor micro layer | 14-31 |
| Lightweight amendment §3.3 compact real-plugin scenarios | 32-33 |
| Lightweight amendment §3.4 extension/replay | 33 |
| Lightweight amendment §3.5 one 10-second physical workflow | 0, 32, 34-35 |
| Lightweight amendment §4 answer isolation and perturbation | 0, 14-35 |
| Lightweight amendment §5 performance/execution boundary | 34-36 |
| Task 3 binding amendment §§4–6 serializable semantic/reference contracts | 3-4, 6 |
| Task 3 binding amendment §§6.4 canonical fingerprints | 8, 13, 35 |
| Task 3 binding amendment §§7–8 runtime candidate/binder/producer boundaries | 3-4, 13, 32, 34-35 |

## Final self-review checklist recorded before implementation approval

- [x] Every design §1-§17 row maps to an executable task or an explicit already-satisfied precondition that is rechecked at closure.
- [x] Every behavior-implementation task names exact create/modify/test files, a RED command/failure, minimal implementation behavior, a GREEN command, and a commit; verification-only/closure tasks instead name their first-run PASS gate and corrective protocol.
- [x] Contract/class names are consistent across Tasks 2-13 and plugin tasks.
- [x] The legacy v0.1 contract/schema remain byte-frozen and separately named.
- [x] The single input-only recipe and independent exact-18 expected-vector freeze precede every production plugin.
- [x] Generic engine cardinality and exact-18 reference profile are both tested.
- [x] Registry stays 0/18 through M4-B and grows only with real factories.
- [x] Poor finite performance and specified behavioral misses always remain computed U.
- [x] M2 validity/confidence/artifact fields do not become a hidden quality gate.
- [x] No task moves ModelBundle/BN/CPT/persistence/Windows frontend ownership into M4.
- [x] Task 3 uses one session-bound candidate and exact three-parameter binder; M3 remains unchanged, bundle provenance is mechanically bound, and ModelBundle mapping remains M5/M6-owned.
- [x] Per-anchor micro goldens, compact all-D/all-U/mixed/state workflows, perturbations, extension, one physical public workflow, deterministic replay, source immutability, schema symmetry, type/lint, build, and isolated-wheel smoke all have explicit gates.
- [x] Final status remains `formal_run_authorized=false`; reference-model status remains `engineering_default`, and synthetic fixtures remain `not_supported`.

## Definition of done

M4 is done only when all Tasks 0-36 are checked, every task has its reviewed commit, and `scripts/verify_m4.ps1` passes freshly from a clean tree with the external format sample supplied. Completion requires all 18 production plugins exactly registered; every per-anchor D/A/U, boundary, override, dependency, finite-extreme, and fingerprint micro gate; compact real-plugin all-D, 18/18 computed all-U, mixed, and exact state-matrix workflows; data-to-anchor perturbations; extension/retire/version replay; the single frozen 10-second public and isolated-wheel M1-to-M4 smoke with 452 PNG, 468 declared references, and 9,331 physical rows; cross-process determinism; unchanged source bytes; no tracked dense fixture assets; installed-code import origin; and the docs-only closure commit. A 90-second soak/performance bundle is explicitly outside M4 Definition of Done. Anything less remains an intermediate M4-A through M4-F state, not M4 engineering verification.
