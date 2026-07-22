# RC.4 Active Save and Persistent Drag Implementation Plan

| Field | Value |
|---|---|
| Date | 2026-07-22 |
| Execution mode | INLINE |
| Authorisation | user directed local-source synchronisation, old local release cleanup and latest package rebuild |

## Tasks

- [x] Implement active Save All / `Ctrl+S` through the existing backend commit transaction.
- [x] Verify Save All keeps the application open and reloads committed system state.
- [x] Lock drag target and use stable root coordinates so normal nodes do not snap back.
- [x] Add layout-only drag persistence for `raw-family.X/U/I/G/P`.
- [x] Preserve Evidence/BN/CPT, activation and immutable RunSnapshot boundaries.
- [x] Remove the opaque multi-select/clear-selection toolbar buttons while retaining copy/paste and
      context-menu additive selection; bind seven localized action tooltips and hide ancestor
      accelerator placement so unrelated buttons never show `Ctrl+C`.
- [x] Record RC.3 user acceptance as `changes-required` and assign RC.4 identity.
- [x] Update bilingual manuals, handoff material, catalog, tests and release commands to RC.4.
- [x] Run focused Save All/drag/toolbar C# tests, the focused Python layout contract, touched-file lint,
      x64 Release build and documentation identity/structure validation; do not repeat the full
      repository or rendered-page acceptance matrix.
- [x] Commit clean source and create annotated `v0.1.0-rc.4` at that exact commit.
- [x] Remove obsolete local `dist/releases` artifacts and build only RC.4.
- [x] Verify ZIP/hash/privacy/root layout outside the repository with restricted `PATH` and one
      visible desktop launch. Reuse preserved editable-source/operator/run evidence instead of
      repeating those acceptance exercises.
- [x] Record exact hashes/counts, push source and tag, and leave the new local release ready for
      independent user acceptance.

## Stop conditions

Do not build from a dirty worktree, an untagged commit, a locked/dirty current system, an ambiguous
candidate identity, or a package containing user projects/Sessions. Any failed verification remains
a failure until rerun successfully after correction.
