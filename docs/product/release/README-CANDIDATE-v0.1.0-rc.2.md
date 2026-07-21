# Pilot Assessment System v0.1.0-rc.2

This Windows x64 release candidate incorporates the root-layout correction requested during
RC.1 user acceptance. Its status remains `user_acceptance=pending`; it is not the accepted
`v0.1.0` release.

## Start

1. Verify the adjacent `.zip.sha256` file if supplied.
2. Extract the entire ZIP to a normal user-writable directory.
3. Double-click the sole root launcher, `PilotAssessment.exe`.
4. Do not activate Python or start SQLite manually. The launcher opens the WinUI payload under
   `app\`, and the desktop app supervises its private Python sidecar automatically.
5. Create a project in an empty user-selected directory, or open an existing project.
6. Import a canonical Session Bundle or a simulator export containing `streams\` and optional
   `annotations\`, select a task scheme, run preflight and start an assessment.

## Product directory

The root intentionally exposes only these product areas:

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
Model Studio and are saved to this software copy's `system\` model library. When the operator
catalog cannot express a new computation, close the app, edit the exposed source under
`backend\src\pilot_assessment`, and restart. The bilingual manuals under `docs\en-GB\` and
`docs\zh-CN\` describe both workflows.

## Boundary

RC.1 remains an immutable `changes-required` candidate. RC.2 is a new candidate, not a rewritten
RC.1 package. The starter Evidence, BN and CPT content remains an editable engineering template;
it has not been scientifically calibrated and keeps `formal_run_authorized=false`.

