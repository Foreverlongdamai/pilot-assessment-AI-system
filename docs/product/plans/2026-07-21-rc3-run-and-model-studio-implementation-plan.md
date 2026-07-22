# RC.3 Run and Model Studio Implementation Plan

**Mode:** INLINE, lightweight tests first, then one complete release gate  
**Authority:** D-084–D-087 and the RC.3 acceptance amendment

## Task 1 — Freeze the RC.2 result

- [x] Record `v0.1.0-rc.2` as `changes-required` without moving its tag or rewriting evidence.
- [x] Assign every correction to a new `v0.1.0-rc.3` identity.

## Task 2 — Separate execution from scientific authorization

- [x] Change `run.assessment_not_authorized` from a blocking error to a warning.
- [x] Allow snapshot creation for technically ready Assessment runs.
- [x] Verify purpose and `formal_run_authorized=false` are both frozen in the RunSnapshot.

## Task 3 — Complete Model Studio interactions

- [x] Add typed `model.node.archive` client/coordinator/ViewModel wiring.
- [x] Add toolbar and context-menu Delete actions with destructive confirmation.
- [x] Atomically cascade task deactivation and archive the global node in the backend edit session.
- [x] Repair held-pointer routing and stable drag coordinates; use a movement threshold instead of
      a fragile dwell timer.
- [x] Preserve immediate Chinese/English switching by keeping runtime changes inside the explicit
      resource context instead of mutating WinUI's process-wide platform override.

## Task 4 — Repair release icon identity

- [x] Resolve window icon through an absolute executable-relative path.
- [x] Copy the icon asset to build and publish output.
- [x] Prove the asset exists in the final package and inspect the live taskbar/window presentation.

## Task 5 — Documentation and release evidence

- [x] Update current product status, glossary, bilingual manuals and RC.3 handoff files.
- [x] Rebuild and render all 24 DOCX manuals; inspect every rendered page.
- [x] Capture or register UI evidence against the final tracked UI source identity.
- [x] Run Python, C#, schema, style and documentation gates.
- [x] Run the final tagged release/package gates.
- [x] Create a clean annotated `v0.1.0-rc.3`, build the ZIP and verify it outside the repository
      with restricted `PATH`, Assessment execution and the published desktop/icon payload.
- [x] Push the source/evidence commits and annotated tag; keep RC.3 `user_acceptance=pending`.
