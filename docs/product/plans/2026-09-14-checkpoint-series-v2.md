# Checkpoint raw-series v2 implementation plan

> For agentic workers: implement the file ownership tasks below with independent tests before implementation. Existing uncommitted scene-studio work is the base; do not reset it or modify DECISIONS.md.

Goal: ship the approved checkpoint-organized raw input, signed target-relative grading, checklist simplification, four-item SCN-001, and evidence timelines in the existing desktop application.

Architecture: keep the standalone Python scene RPC and WinUI Model Studio. Publish catalog/config/input/report schema 2.0; retain explicit schema 1.0 backend access for old fixtures without silently importing v1 configuration into the v2 workspace. Phase segmentation remains outside this application. Whole-flight Bayesian formula selection is pending user clarification; no raw-frame independent accumulation or fabricated calibrated score.

Tech stack: existing Python 3.11 project .venv, pytest, .NET 10 Desktop.Core/xUnit and WinUI. No new dependencies.

## Shared wire contract (fixed for this implementation)

Catalog retains existing metric/item/checkpoint IDs structures. Add `assessment_kind: checklist|flight` to items, `input_kind: series|scalar` and `comparison: linear|angle_degrees` to metrics. Rules remain `interval`, `must_be_true`, `zero_events`. New numeric metric IDs identify actual quantities rather than maximum absolute deviations. Metric IDs remain globally unique so configuration parameters can remain a flat dictionary.

Configuration retains `parameters[metric_id] = {expected, desired:{lower,upper,unbounded_upper}, acceptable:{...}}` with schema_version 2.0. All numeric defaults are null, unbounded_upper is false. Bounds are signed deviations, D is a strict subinterval of A, both include zero. Heading difference lies in [-180,180). Skill model structure remains editable for flight items; defaults use null entries and parameter_source=unconfigured, not demonstration probabilities. A pending model must not block deterministic evaluation.

Input schema 2.0 replaces flat results with:

```json
{
  "schema_version": "2.0",
  "scene_id": "SCN-001",
  "items": {
    "A-S2-08": {
      "checkpoints": {
        "A-S2-08-01": {
          "values": {"initial_hover_duration_s": null},
          "samples": [
            {"start_s": 0, "end_s": 1, "values": {"initial_hover_height_m": 100}}
          ]
        }
      }
    }
  }
}
```

Above is a shape example, not a complete scene input or recommended threshold. Templates contain every required item/checkpoint, scalar values null and samples empty. Each sample's values contains exactly that checkpoint's series metrics. Scalar/checklist/event facts belong in that checkpoint's values, never an extra phase-identification layer. The sample explicitly represents [start_s,end_s); timestamps are supplied by the external producer, never inferred. Consecutive subdivisions with identical values preserve duration results. No input clipping, resorting, interpolation, or last-frame extrapolation. Reject overlapping/out-of-order/nonpositive/nonfinite intervals; gaps are explicitly reported as missing coverage and cannot silently produce a complete Pass. Time axes are supplied flight-relative seconds so separate checkpoints can be displayed in the same flight context without matching or cutting intervals.

Report retains existing item/checkpoint/metric envelope, snapshots and issues. Each metric result adds `expected`, `deviation`, `timeline` (list below), `distribution` (object below), `episodes` (list below). Scalar metrics use existing value plus expected/deviation and an empty timeline; facts have no numeric expected/deviation. A metric's grade is its worst valid sample grade, missing results remain missing; known U is preserved when other evidence is missing. Composite checkpoint time trace grades are the worst of its series metrics on the common supplied sample grid; scalar facts affect its final rule grade but are not repeated as time evidence.

```json
{
  "timeline": [{"start_s":0,"end_s":1,"value":103,"expected":100,"deviation":3,"grade":"A"}],
  "distribution": {"duration_s":1,"span_s":1,"gap_s":0,"durations":{"D":0,"A":1,"U":0},"proportions":{"D":0,"A":1,"U":0}},
  "episodes": [{"start_s":0,"end_s":1,"grade":"A","duration_s":1,"max_abs_deviation":3}]
}
```

Checkpoint results also add `timeline:[{start_s,end_s,grade}]`, `distribution` of the same shape. Group contiguous A/U metric intervals into episodes without crossing gaps; keep signed point deviations for direction. Full JSON reports retain all samples; desktop drawing may decimate visually but never use reduced data for calculation. No automatic item time aggregate across nonaligned checkpoints.

Flight item skill_quantification remains an explicit status with no numerical posterior/score when the aggregate Bayesian method is pending; checklist is not_applicable. Keep flight CPT editing and structure visualization, label as unconfigured/draft. Do not invoke v1 quantify_item on a sequence's worst grade and call it a whole-flight score.

Versioning: load_catalog(scene_id, schema_version="2.0") is current, schema_version="1.0" explicitly serves the old definition. Configuration evaluation dispatches to its schema. RPC scene.catalog accepts optional schema_version; current scene list points to v2. Scene-specific RPC message limit is 64 MiB on both ends; preserve the legacy sidecar default. Unknown versions/IDs return a clear validation error. The desktop workspace rejects cross-version inputs/configs with instructions to use the new template; no silent conversion.

## Tasks and ownership

### 1. Python engine — core_rebuild_audit

Files: scene_assessment/catalog.py, calculator.py, validation.py or new series_calculator.py/series_validation.py, server.py; tests/scene_assessment. Root owns new scn001_v2.json.

- [x] Write failing v2 tests for expected=100 with signed offsets, asymmetric tolerances, 359→1 and ±180 angle cases, nested CP routing, booleans/null, unequal durations, interval subdivision invariance, gaps/overlap, composite series, failure retention and no invented BN scores.
- [x] Run `.venv/Scripts/python.exe -m pytest tests/scene_assessment -q` with appropriate v1 fixtures explicitly versioned; capture the relevant initial v2 failures.
- [x] Implement version dispatch, templates, strict validation and detached reports. Preserve v1 behavior behind explicit access.
- [x] Run scene tests plus Ruff on changed Python files. Add stdio v2 request/report round-trip with real source data.

### 2. Desktop.Core — dual_outputs_alignment

Files: src/PilotAssessment.Desktop.Core/SceneAssessment/*; tests/PilotAssessment.Desktop.UnitTests/Scene*; tests/PilotAssessment.Desktop.ContractTests/SceneAssessmentContractTests.cs.

- [x] Write failing DTO/workspace tests for nested inputs and new report fields, v1 rejection in v2 workspace, cloning/invalidating reports, nonblocking blank CPTs and checklist graph structure.
- [x] Extend source-generated JSON DTOs without loosening unknown-field validation. Keep v1 Results optional with correct version checks.
- [x] Preserve model editing; new null-cell models are drafts, not inference-ready demonstrations. Checklist has no skill model.
- [x] Run both UnitTests and scene real-backend ContractTests. Coordinate exact new field names with root/Python.

### 3. WinUI — desktop_rebuild_audit

Files: SceneAssessmentWindow*, SceneItemParameterEditor, SceneSkillModelEditor, SceneModelCanvas, new timeline rendering control; SceneBackendConnection (64 MiB only).

- [x] Keep global Studio and navigation; update text and CPT/checklist distinctions. Avoid default demonstration probabilities in v2.
- [x] Editor clearly labels actual target and D/A deviation bounds; support asymmetric signs. Checklist shows completion rules.
- [x] Report displays raw/target/deviation/grade timelines, duration proportions, A/U episodes and full-detail access; handle many samples without rendering a control per sample.
- [x] Keep flight CPT editing reachable but label pending aggregation honestly. Do not display fabricated EAP.
- [x] Compile existing WinUI project; root owns final shared build/release and visible verification.

### 4. Integration, catalog, examples and launch — root

- [x] Create scn001_v2.json retaining four items; convert six preflight AOIs to named procedure completion checks, preserve ten flight checkpoints while changing numeric inputs to actual scalar or series quantities. Use explicit position components; do not create geometric extraction.
- [x] Generate new complete blank configuration/input and clearly marked synthetic engineering examples only; no simulator sample inspection. Source links retain official/project distinctions.
- [x] Run cross-language evaluation and end-to-end file round trips. Verify saved reports include exact input/configuration and new result fields.
- [x] Update guide, handoff and stage README with implemented versus pending functionality.
- [x] Build desktop output, inspect the actual desktop shortcut target and launch the new executable. Verify version, four items, signed editor and report in the running application where native tooling permits; describe any verification limit accurately.

## Scope decisions

The user has already approved implementation; do not ask again for plan approval. Outstanding Bayesian formula preference was asked asynchronously while these independent changes proceed. Do not turn absence of a reply into approval of a statistical formula. No git reset/cleanup, no changes to DECISIONS.md, no project environment migration, no sample-data detector work.
