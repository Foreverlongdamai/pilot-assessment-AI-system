# Pilot Assessment System v0.1.0-rc.4

This Windows x64 release candidate incorporates the active-save, persistent-drag and Model Studio
toolbar corrections requested after RC.3 user acceptance, while preserving the RC.3 run, icon,
global deletion and portable-layout corrections. Its status remains `user_acceptance=pending`; it
is not the accepted `v0.1.0` release.

## Start

1. Verify the adjacent `.zip.sha256` file if supplied.
2. Extract the entire ZIP to a normal user-writable directory.
3. Double-click the sole root launcher, `PilotAssessment.exe`.
4. Do not activate Python or start SQLite manually. The launcher opens the WinUI payload under
   `app\`, and the desktop app supervises its private Python sidecar automatically.
5. Create a project in an empty user-selected directory, or open an existing project.
6. Import a canonical Session Bundle or simulator `streams\` plus optional `annotations\`, select
   a task scheme and run technical preflight.
7. Preview, Software Test and Assessment purposes can run when preflight is technically ready.
   Assessment shows a warning while `formal_run_authorized=false` and does not imply scientific
   calibration.

## Product directory

```text
PilotAssessment.exe   sole launcher
README.txt             this quick handoff
app\                   WinUI/.NET/Windows App SDK runtime payload
backend\               active editable Python source
system\                software-wide Evidence/BN/task model library
runtime\               private Python and dependencies
developer\             source, build tools and extension example
docs\                   manuals, release notes and acceptance material
licenses\               third-party notices and licences
manifest\               checksums, SBOM and provenance
```

Do not move `PilotAssessment.exe`, `app\` or any semantic directory independently. User projects
remain outside the product and are never bundled with a software release.

## Editing and extension

Routine Evidence, BN, parent, state, CPT, recipe, parameter and task-activation changes belong in
Model Studio. Press and hold a normal node or one of the five green Raw Input Family roots to drag
it; the released position is staged and remains in place. **Delete node from system model** archives
the global current node and removes its dependent active closure from affected task schemes after a
confirmation. These are staged changes: Ctrl+Z and Ctrl+Y operate the edit history, while **Save
All** or `Ctrl+S` commits all open editors and pending layouts without closing the software.
Discard/close semantics remain session-wide, and historical RunSnapshots remain immutable.

When the operator catalog cannot express a new computation, close the app, edit the exposed
source under `backend\src\pilot_assessment`, and restart. The bilingual manuals under
`docs\en-GB\` and `docs\zh-CN\` describe both workflows.

## Boundary

RC.1, RC.2 and RC.3 remain immutable `changes-required` candidates. RC.4 is a new candidate, not a
rewritten package. The starter Evidence, BN and CPT content is an editable engineering template;
it has not been scientifically calibrated and keeps `formal_run_authorized=false` even when an
Assessment-purpose engineering run completes.
