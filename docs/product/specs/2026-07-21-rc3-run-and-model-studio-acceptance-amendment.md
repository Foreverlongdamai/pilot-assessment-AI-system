# RC.3 Run and Model Studio Acceptance Amendment

**Status:** accepted implementation amendment  
**Date:** 2026-07-21  
**Scope:** four RC.2 user-acceptance defects only

## 1. Purpose

This amendment creates `v0.1.0-rc.3` without changing the assessment architecture, starter
Evidence/BN science, portable root layout, system/project ownership or immutable RunSnapshot
model. It separates technical execution from scientific authorization and closes three desktop
interaction defects.

## 2. Assessment-purpose execution

`RunPurpose.ASSESSMENT` is the evaluator's intended-use label stored in the frozen RunSnapshot.
It is not itself a claim that the selected model is scientifically calibrated.

When every technical preflight condition is ready, both `software_test` and `assessment` may
create and complete a run. If the exact session/policy/model is not formally authorized,
preflight returns `formal_run_authorized=false` plus the stable warning
`run.assessment_not_authorized`; it must not convert technical disposition to `blocked`.
The frozen preflight provenance preserves that false value and results remain engineering-only.

Technical contract errors, unavailable required operators, invalid model structure, stale source,
dirty system edits and other existing blockers remain blockers.

## 3. Global node deletion

Model Studio provides **Delete node from system model** in the toolbar and node context menu.
Deletion means staged archival from the software-wide current model, not physical erasure of
historical records.

After explicit confirmation, the backend performs one atomic edit-session transaction:

- deactivate the node and its dependent downstream closure in every affected TaskScheme;
- remove affected scheme outputs and active edges;
- archive the node from the current global library;
- return the affected scheme identities so the UI can report the impact.

The action participates in global Undo/Redo and the application's Save All / Discard All close
decision. Historical RunSnapshots, completed runs, results and artifacts remain immutable.

## 4. Press-and-drag

Holding the primary button and moving at least 4 px starts node movement; no dwell timer is
required. A stationary press remains a normal selection click. Pointer events handled internally
by the WinUI `Button` must still reach the graph control. Movement is measured in a coordinate
system that does not move with the rendered button. During dragging the node follows the pointer;
release queues one staged layout update. Layout changes do not alter semantic node identity or
topology.

## 5. Published icon

The main and floating windows resolve `Assets/AppIcon.ico` from `AppContext.BaseDirectory` and
pass an absolute path to `AppWindow.SetIcon`. The asset must be copied into both build and publish
outputs. The release verifier treats `app/Assets/AppIcon.ico` as required payload.

## 6. Acceptance boundary

RC.3 must pass focused Python/C# tests, full repository gates, x64 Release build, bilingual manual
generation/render review, tagged clean-source packaging and repository-external restricted-PATH
verification. Automated gates leave `user_acceptance=pending`; only the user's next independent
use can accept RC.3.
