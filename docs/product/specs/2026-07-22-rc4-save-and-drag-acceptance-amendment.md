# RC.4 Active Save and Persistent Drag Acceptance Amendment

| Field | Value |
|---|---|
| Date | 2026-07-22 |
| Replacement candidate | `v0.1.0-rc.4` |
| Replaces for acceptance | `v0.1.0-rc.3` (`changes-required`) |
| Scientific boundary | unchanged; starter `formal_run_authorized=false` |

## 1. Purpose

RC.4 packages the already implemented D-088 and D-089 corrections without changing the assessment
architecture, starter Evidence calculations, BN topology or CPT values. It preserves the RC.3
Assessment, icon, global deletion and portable-layout corrections.

## 2. Required behaviour

1. The main command surface exposes **Save All** and `Ctrl+S` while the application stays open.
2. Save All flushes floating node editors, forms, CPT changes, pending graph layout and window
   placement before using the existing backend `model.edit.commit` transaction.
3. A successful commit reloads the current system model and leaves the editor usable; failure keeps
   the staged workspace available for retry. The close-time Save/Discard/Cancel workflow remains a
   fallback, not the only save path.
4. Drag coordinates use a stable root coordinate space and lock the selected projection at pointer
   press. Release and pointer cancellation share a one-time completion path, so virtualization cannot
   clear the target before the layout update is submitted.
5. `raw-family.X/U/I/G/P` are draggable display-only layout targets stored in each TaskScheme's
   `layout_overrides`. They remain outside canonical ModelNode, Evidence/BN/CPT, activation closure
   and RunSnapshot semantics.
6. Save All followed by restart restores both canonical-node and raw-family-root positions.
7. The Model Studio toolbar keeps seven direct actions (new, details, activate, deactivate, delete,
   copy and paste), removes the low-feedback multi-select and clear-selection buttons, and gives each
   retained action a localized tooltip. Page-level accelerators must not leak `Ctrl+C` into unrelated
   button hints; additive selection remains available from the node context action.

## 3. Candidate and distribution identity

- RC.1, RC.2 and RC.3 tags remain immutable historical identities.
- RC.4 starts with `user_acceptance=pending` even though automated engineering verification passes.
- The package keeps one root launcher, the WinUI payload under `app/`, editable Python under
  `backend/`, the global model library under `system/`, and no user project or Session data.
- The maintainer may remove obsolete local artifacts from `dist/releases`; this does not delete Git
  history or claim that an older candidate never existed.

## 4. Lightweight differential evidence

RC.4 does not repeat the full M8E/RC.3 acceptance matrix. It reuses the preserved historical source,
documentation, portability, editable-source, operator-extension and lightweight-run evidence, and
adds only the evidence needed for this delta:

- focused C# tests for Save All, canonical drag, Raw Input Family layout and toolbar structure;
- the focused Python layout contract and lint for touched backend files;
- one x64 Release build;
- documentation identity/structure validation and normal package generation, without repeating the
  281-page visual review;
- ZIP/hash/privacy/root-layout integrity plus one real root-launcher startup from an external
  extraction.

Static screenshots may be explicitly reused from RC.3 where they still describe the visible
surface. Save and drag correctness must come from the focused live interaction evidence already
recorded for D-088/D-089, not from a static image. Scientific calibration, full repository tests,
the editable-source exercise, operator-extension exercise and assessment-run matrix are not repeated
as separate RC.4 acceptance activities.

Automated lightweight evidence leaves `user_acceptance=pending`. Only the user's operation of the
exact RC.4 ZIP may change that state.
