# Two Scenes and Item Frames v3 Implementation Plan

> For agentic workers: implement the bounded tasks below in parallel after agreeing the shared contract. User explicitly authorised implementation on 2026-09-15; no further design approval is required for this scope.

**Goal:** Make both SCN-001 and SCN-002 available in the desktop application with item-organised exact-timestamp input, editable assessment rules, shared Model Studio and honest frame reports.

**Architecture:** Retain the existing Python scene calculator and WinUI shell. Add an explicit 3.0 document version; retain old 1.0/2.0 paths for replay without silent conversion. Register both scenes in one v3 catalog registry used by navigation, templates and assessment.

**Tech Stack:** Existing Python 3.11 legacy project environment, pytest, .NET 10, WinUI 3, existing JSON-RPC transport. No new dependencies or environment.

## Shared contract

Input remains one scene per document:

```json
{
  "schema_version": "3.0",
  "scene_id": "SCN-002",
  "items": {
    "A-S2-01": {
      "frames": [
        {"timestamp_s": 12.0, "phase_id": "lower_1", "values": {"hover_lower_height_m": null}},
        {"timestamp_s": 12.1, "phase_id": "lower_1", "values": {"hover_lower_height_m": null}}
      ]
    }
  }
}
```

The example is a shape illustration, not a complete usable flight. Every actual item has `frames`; each frame has `timestamp_s`, `phase_id`, `values` and optional `controls` (Pilot Lon/Lat/Yaw/Heave), all source data retained in reports. No input start/end interval, checkpoint arrays, event detector or segment extraction.

Catalog additions:

- Catalog `phase_sequence`: scene-wide order of already supplied phases. Same-name phases in different items must have matching first/last timestamps (1e-9 arithmetic tolerance); successive phases cannot overlap or reverse, but may meet at the same boundary instant. Gaps are not filled. This catches inconsistent input evidence, not aircraft events.
- Optional item `equivalent_values` lists pairs of metric IDs representing the same physical raw value in the same frame; if both are finite they must agree within 1e-9. The quick-stop item pairs stop_height_m and quickstop_height_m. Validation reports inconsistencies without changing values or tolerances.

- Item `phases`: ordered list of `{phase_id,name,single_frame,required_duration_s}`. A single-frame phase is an explicitly supplied event state, not a detected event. Required duration is null except the four user-prescribed 5-second hover phases. Each listed phase must be present. Per-item timestamps increase, phases follow declared order without returning to an earlier occurrence.
- Metric `phase_ids`: phases in which that metric is required; value keys remain metric IDs. `input_kind` is `frame`. Distinct lower/upper metric IDs support separately editable target heights and laser geometry while reusing checkpoints.
- `rule` stays `interval`, `must_be_true` or `zero_events`; interval `comparison` adds `radial` alongside `linear` and `angle_degrees`. Model draft state lists therefore keep D/A/U for radial.
- Linear/heading parameters retain `{expected,desired:{lower,upper,unbounded_upper},acceptable:{...}}`; targets/tolerances stay null unless mathematically or user-defined (stationary velocity target 0). UI labels explain allowed amounts below/above target and preserve signed storage.
- Radial value: `{status:"hit",u_m:...,v_m:...}`, or `{status:"miss",u_m:null,v_m:null}`, or unavailable. Each lower/upper metric already identifies its expected target; no independent target_id required. Wrong-target evidence must be supplied as miss. Missing/unavailable is an input issue, not U.
- Radial parameters add `center_u`, `center_v`, `target_radius`; `expected=0`, both interval lowers=0, finite upper bounds are R_D/R_A. Require 0 <= R_D < R_A < target_radius. No numerical radius or centre default. Distance is computed by the calculator from raw coordinates.
- Optional controls are explanatory inputs, never graded by assuming zero/low control deflection is good. Unknown or invalid required data/configuration cannot yield complete Pass.

Report stays structurally compatible (`items/checkpoints/metrics`) but v3 timelines use `timestamp_s`, `phase_id`, value/expected/deviation/grade/status/reason. Exact timestamps do not acquire invented start/end durations. Add `frame_distribution` with `{counts:{D,A,U},proportions:{D,A,U},valid_frame_count,missing_frame_count}` at metric/checkpoint/item level. Per-phase summaries distinguish four holds and three transfers. Preserve incomplete status and definite U; no synthetic probability, score or time integration. `skill_quantification.status` stays `pending_method` for flight items, with editable draft CPT independent from assessment configuration validation.

Hover duration checks use observed first/last timestamps within each supplied phase to ensure at least 5 seconds of span; do not claim that endpoints prove continuous sampling quality. Missing/interior unobserved frames remain unknown. Reports state this coverage meaning explicitly. No phase auto-selection, best-window search, timestamp extrapolation or clock reset on U.

## Task 1 — Python engine (core_rebuild_audit)

Files: new `src/pilot_assessment/scene_assessment/frame_calculator.py` and supporting validation if needed; update `calculator.py`, `server.py`; new `tests/scene_assessment/test_frames.py`.

- [x] Add failing tests for item frame parsing, signed/heading grading, lower/upper applicability, terminal-only position, radial boundaries/miss/missing, missing phases, bad timestamps and single-frame rules.
- [x] Implement v3 dispatch and evaluation using the contract above; preserve older version tests with explicit version requests.
- [x] Test combined U cannot be diluted, incomplete input cannot Pass, one frame is one frame in distributions, and controls survive round trips without scoring.
- [x] Keep scene JSON/catalog registry changes owned by root.

## Task 2 — Scene definitions and templates (root)

Files: new `scn001_v3.json`, `scn002_v3.json`; modify `catalog.py`; new catalog tests and `examples/scenes/*/v3/`.

- [x] Verify SCN-001 uses preflight checklist, start positioning, air taxi, quick stop; replace old takeoff hover check and remove quick-stop trigger checkpoint.
- [x] Evaluate quick-stop endpoint position only at explicitly supplied `stop` phase. Preserve process and prohibited-event checks with honest source labels.
- [x] Register the four SCN-002 items and lower/up/lower/up 5-second phases, plus three transfers. No added landing or departure task.
- [x] Export empty input/config templates and clearly labelled synthetic examples for software verification only. Templates do not prefill performance tolerances or Bayesian probabilities.

## Task 3 — Desktop (desktop_rebuild_audit)

Files: `src/PilotAssessment.Desktop.Core/SceneAssessment/`, relevant `Scene*` editors/graph/window files and corresponding unit/contract tests.

- [x] Add v3 DTOs and strict round-trip handling; preserve legacy DTO properties only for explicit old documents.
- [x] Make the shared catalog render both scenes in Model Studio and the left menu; scene state, saved files and reports remain separate.
- [x] Add signed allowance labels, radial centre/radius editor and exact-frame timeline/phase labels/distribution display.
- [x] Verify edits synchronise across scene and Studio views, invalidate old reports, and retain incomplete model drafts.

## Task 4 — Integration, packaging and handoff (root)

- [x] Run focused Python and .NET unit/contract tests, then the appropriate full scene suites and a Debug x64 build using the existing output directory or a versioned directory if locked.
- [x] Independently evaluate both synthetic inputs through actual JSON-RPC; check exported input/config/report round trips.
- [x] Inspect the real launcher/shortcut and running executable path. Launch the built visible application for the user; do not kill unrelated old processes.
- [x] Update product handoff, current-stage entry and usage guide with actual supported features, v3 file locations, verification evidence and pending Bayesian method.

No edits or commits to protected `DECISIONS.md`; preserve unrelated dirty files and existing environments. No automatic conversion of old files or changes to the presentation deck.

