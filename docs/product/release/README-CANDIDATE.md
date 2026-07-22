# Pilot Assessment System v0.1.0-rc.1

This is the first complete Windows x64 release candidate for independent user acceptance.
Its current status is `user_acceptance=pending`; it is not yet the accepted `v0.1.0` release.

## Start

1. Verify the adjacent `.zip.sha256` file if it was supplied with the ZIP.
2. Extract the entire ZIP to a normal user-writable directory.
3. Double-click `PilotAssessment.Desktop.exe`.
4. Let the desktop app start its private Python sidecar and embedded SQLite storage automatically.
   Do not activate Python or start a database service by hand.
5. Create a new project in an empty directory, or open an existing Pilot Assessment project.
6. Import a canonical Session Bundle or a simulator export containing `streams/` and optional
   `annotations/`, choose a task scheme, run the technical preflight, and start an assessment.

Keep the complete directory together. The product contains one software-owned `system/` model
library and editable Python source under `backend/src/pilot_assessment`; user projects remain in
the directories selected by each user and are not part of this product package.

## Editing and extension

Routine Evidence, BN, parent, state, CPT, recipe, parameter and task-activation changes belong in
Model Studio. **Save all** on the main toolbar or `Ctrl+S` commits the staged global model while
the application remains open. The close dialog still offers save, discard or cancel when changes
remain.

When the existing operator catalog cannot express a genuinely new computation, close the app,
edit the exposed Python source, and restart. The bilingual manuals under `docs/en-GB/` and
`docs/zh-CN/` explain both workflows, including the operator extension example.

## Boundary

The starter Evidence, BN and CPT content is an editable engineering template. It has not been
scientifically calibrated, `formal_run_authorized=false`, and no result should be represented as
certified pilot competence or operational fitness. See `RELEASE-NOTES.md`,
`KNOWN-LIMITATIONS.md`, and `ACCEPTANCE-CHECKLIST.md` before recording acceptance.
