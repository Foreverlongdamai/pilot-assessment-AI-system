+++
document_id = "PAS-PORTABILITY-001"
language = "en-GB"
title = "System Distribution, Project Portability and Troubleshooting"
short_title = "Portability and Troubleshooting"
product_version = "0.1.0"
document_version = "0.1.0"
status = "released"
audience = ["evaluator", "expert", "developer", "maintainer", "release"]
information_types = ["how-to", "reference"]
scope = "Copying the software/system or a user project, recovering from common failures and preserving source/model/run identities."
prerequisites = ["The application can be closed before copying", "Access to the complete source directory being moved"]
scientific_status = "engineering-only"
related_documents = ["PAS-QUICKSTART-001", "PAS-SESSION-001", "PAS-PYTHON-EXT-001", "PAS-RELEASE-001"]
support = "Retain the original ZIP, release hash, Diagnostics summary and a privacy-safe directory inventory before attempting recovery."
release_channel = "release-candidate"
release_label = "v0.1.0-rc.3"
user_acceptance = "pending"
+++

# System Distribution, Project Portability and Troubleshooting

## 1. Two independent things can be copied

The product intentionally has no separate proprietary Backup/Restore archive. Windows directory copying is the complete portability mechanism, but the scope matters:

| Copy | Contains | Does not contain |
|---|---|---|
| Whole unpacked software directory | executable/runtime, editable Python, dependencies, global `system\` model library, manuals and release manifests | user projects and Sessions stored elsewhere |
| Whole user project root | project metadata, SQLite database, managed Sessions, RunSnapshots, runs, results, artifacts, logs and staging metadata | Python source and global system model |

Copying the software transfers its current Evidence/BN/task-scheme library and any Python modifications. Copying a project transfers its data/history. They can be moved independently because project records use contained relative paths.

## 2. Move or duplicate the software/system

1. Save or discard all staged system-model edits.
2. Close every app instance and confirm the root launcher, `app/PilotAssessment.Desktop.exe` and its child Python process have exited.
3. Copy the complete product root to the destination. Do not select only the EXE, `system\` database or `backend\` folder.
4. Start the sole entry point, `PilotAssessment.exe`, from the destination product root.
5. Open Diagnostics and confirm product/release label, model library identity and counts, source identity and dependency/operator identity.

The copied software and original become independent after the copy. Changes in one do not synchronize to the other. Keep the original candidate ZIP and `.sha256` as the delivered baseline.

## 3. Move or duplicate a project

1. Wait for imports and runs to reach a durable final state.
2. Close the app so SQLite, logs and artifacts have no open writer.
3. Copy the complete project root, including hidden/empty managed directories.
4. In the destination software choose **Open project** and select the copied root.
5. Review compatibility and recovery diagnostics before starting a new run.

Do not copy only `project.sqlite3`; its managed Session files and content-addressed artifacts are part of the same project. Do not place a project inside the product root if the product will later be replaced or redistributed.

Historical runs retain frozen model/source identities. Opening a project with a software copy whose current global model differs does not rewrite them. A future run uses the destination software's current saved model.

## 4. Reproduce or recover a software baseline

To recover unmodified delivered code, extract the original verified ZIP into a new directory. Do not extract over a locally modified copy. Then choose whether to:

- open an existing project from the clean software; or
- copy the complete intended `system\` by copying its whole software directory before launch.

There is no supported “merge two system databases” button in this candidate. Preserve two parallel software copies when two independently evolved global model libraries must remain available.

## 5. Understand source divergence

Direct edits under `backend/src/pilot_assessment/`, `backend/pyproject.toml`, `backend/uv.lock` or private dependencies intentionally change the backend identity and make it differ from the release baseline. This is allowed and visible in Diagnostics.

After editing:

1. close and restart the application;
2. confirm `restart_required` is cleared;
3. verify the operator catalog/dependencies;
4. run one small relevant workflow;
5. retain the new source artifact with new runs.

Do not “repair” the checksum manifest by manually replacing hashes to make a modified system look unmodified. Provenance should describe the difference.

## 6. Startup troubleshooting

| Symptom | Check | Action |
|---|---|---|
| Nothing opens | ZIP fully extracted, path writable, EXE not isolated from siblings | Re-extract whole ZIP to a short writable directory |
| Windows App Runtime missing | correct self-contained candidate contents and architecture | Use the complete candidate package; record exact dialog if still shown |
| Backend startup failed | Diagnostics/stderr, active source syntax/import, private runtime files | Restore/fix named source or dependency; restart whole app |
| Repeated project chooser | selected root missing/invalid or no current project | Create a new project or open the complete existing root |
| File locked | another desktop/sidecar process still holds system/project | Close all instances; do not copy while active |

## 7. Import and run troubleshooting

| Symptom | Check | Action |
|---|---|---|
| Raw export not recognized | top-level `streams\`, optional `annotations\`, adapter diagnostics | Correct the expected directory shape or add a trusted adapter |
| Checksum mismatch | copied source bytes changed | Re-export/re-copy; never ignore integrity failure |
| Some Evidence unavailable | missing modality/input binding in managed manifest | Accept partial inference or supply a real Session with that modality |
| Preflight blocked | incomplete CPT, missing operator, cycle, dirty edit session or incompatible schema | Follow the exact blocking diagnostic; do not fabricate data |
| Poor score unexpectedly marked missing | method/adapter returned wrong status | Treat finite poor performance as computed and fix the mechanism |
| Run interrupted | Diagnostics recovery state | Reopen project and reconcile/retry from durable boundary |

## 8. Model-edit troubleshooting

| Symptom | Check | Action |
|---|---|---|
| Child activates other nodes | fixed ancestor closure | Expected behaviour; inspect the child's complete parents |
| Parent cannot be disabled silently | active downstream impact | Review listed descendants, continue cascade or cancel |
| Edit affects several tasks | the same complete node is shared | Copy it for task-specific differences, then change activation |
| Parent differs by task | one node was being overloaded | Create a distinct copied child with its own fixed parents |
| Close dialog appears | staged system edits exist | Save all and close, discard all and close, or cancel |
| Revision conflict | another saved state superseded the expected revision | Reload/rebase; do not overwrite blindly |

## 9. Privacy-safe support package

Start with release label, UI language, stable error code/trace ID, Diagnostics summary, model/source identities and a directory tree containing names/sizes only. Remove user name/home paths and project participant identifiers. Never include raw gaze, EEG, ECG, pilot-camera images or Session rows unless an authorized data-governance process explicitly requires them.

## 10. Portability checklist

- [ ] Correct scope chosen: whole software or whole project;
- [ ] app and child process closed;
- [ ] source directory copied completely;
- [ ] original ZIP/hash retained;
- [ ] destination opens and Diagnostics identities recorded;
- [ ] historical runs remain unchanged;
- [ ] no user project/Session is inserted into a redistributed product ZIP;
- [ ] no private path or biometric content is included in support material.
