+++
document_id = "PAS-QUICKSTART-001"
language = "en-GB"
title = "Installation, Startup and Quick Start"
short_title = "Quick Start"
product_version = "0.1.0"
document_version = "0.1.0"
status = "released"
audience = ["evaluator", "expert", "maintainer"]
information_types = ["tutorial", "how-to"]
scope = "Unpack, start and complete the first privacy-safe engineering assessment without installing a separate backend or database service."
prerequisites = ["Windows 10 19041 or later on x64", "A writable local folder", "A Session source supplied by the user"]
scientific_status = "engineering-only"
related_documents = ["PAS-ARCH-001", "PAS-EVALUATOR-001", "PAS-SESSION-001", "PAS-PORTABILITY-001"]
support = "Record the release label, visible error message and Diagnostics summary; do not send raw biometric or Session data unless an authorised support process requests it."
release_channel = "release-candidate"
release_label = "v0.1.0-rc.2"
user_acceptance = "pending"
+++

# Installation, Startup and Quick Start

## 1. What you receive

The delivery is one Windows x64 ZIP. It contains the WinUI desktop app, a private .NET and Windows App SDK deployment, a private Python runtime, editable Python source, the current system model, manuals and integrity manifests. It contains no user project, Session, result, sample biometric record or test dataset.

This is a release candidate with `user_acceptance=pending`. Its starter Evidence, BN and CPT content is an editable engineering template and has not been scientifically calibrated.

## 2. Unpack the complete product

1. Verify the separate `.sha256` file if it is supplied with the ZIP.
2. Extract the whole archive to a short, writable local path such as `D:\PilotAssessment-0.1.0-rc.2`.
3. Keep the root `app\`, `backend\`, `system\`, `runtime\`, `developer\`, `docs\`, `licenses\` and `manifest\` directories together; do not move the launcher or files from `app\` on their own.
4. Do not extract over an older modified copy. Use a parallel directory so its Python source and `system\` remain recoverable.

The candidate is self-contained. Do not install or activate Python, .NET, SQLite, Visual Studio or a database server merely to run it.

## 3. Start and stop

Double-click the sole root launcher, `PilotAssessment.exe`. It opens the WinUI desktop payload from `app\`; the front end then starts one local Python sidecar as its child process. JSON-RPC travels through stdin/stdout; there is no TCP service. SQLite is an embedded file database used by that Python process, not a separately started application.

On normal shutdown the desktop app stops the sidecar. If system-model edits are staged, the close dialog asks whether to save all changes and close, discard all changes and close, or cancel closing. Do not terminate the process while a save or import is in progress.

## 4. Create the first project

[[SCREENSHOT:ui-project-launcher]]

1. Choose **Create project**.
2. Enter a readable project name. The backend creates its technical ID; the UI does not ask you to invent a UUID.
3. Select an empty writable directory outside the extracted product.
4. Confirm creation and wait for the project workspace to open.

A project owns imported Session revisions, RunSnapshots, runs, results and artifacts. It does not own the global Evidence/BN model. The software copy's `system\` is shared by every project opened by that copy.

## 5. Import a Session

Choose the Session import action and select either:

- a canonical Session Bundle containing `manifest.json`; or
- a simulator export directory containing `streams\` and optional `annotations\`.

For a raw simulator source, the product inspects the directory read-only, determines supported stream mappings, generates the managed manifest and copies the accepted files into the project. The external source is not modified. A unit that is absent from the export remains undeclared; the importer does not ask the evaluator to guess one.

Missing modalities are allowed. The product does not generate synthetic I/G/EEG/ECG/camera content. Evidence that can use the available inputs may still run; dependent Evidence reports an explicit unavailable observation.

## 6. Run the first engineering assessment

1. Open **Model Studio** and select the intended task scheme.
2. Confirm that any system-model edit session is clean. Save or discard staged edits before running.
3. Open **Runs**, select the imported Session revision and the task scheme, then request preflight.
4. Review technical readiness and missing-input diagnostics.
5. Start the run only when preflight permits it.
6. Open **Results** after completion to inspect Evidence values, D/A/U observations, BN posteriors, missing Evidence, influence information and provenance.

`formal_run_authorized=false` remains true for the starter template. A completed run proves engineering execution, not scientific validity or operational fitness.

## 7. Quick health checks

Use **Diagnostics** when startup, import or execution is unclear. Confirm:

- the backend is ready and no restart is required;
- the current system model has an identity and expected dynamic node/scheme counts;
- a project is open and compatible;
- the loaded Python source and operator catalog have identities;
- the latest error includes a stable error code and trace ID.

Long hashes and technical IDs belong in Diagnostics and provenance views. Ordinary lists and result cards use concise names.

## 8. Close, copy and reopen

Close the application before copying data. To move a project, copy its complete root directory and open the copied root from the destination software. To transfer the model library and Python modifications together, copy the complete extracted software directory. There is no separate Backup/Restore archive.

See [[DOC:PAS-EVALUATOR-001]] for the full evaluation workflow and [[DOC:PAS-PORTABILITY-001]] for migration and troubleshooting.

## 9. First-use checklist

- [ ] ZIP hash checked;
- [ ] complete archive extracted to a writable path;
- [ ] desktop opened without manually starting Python or SQLite;
- [ ] project created outside the product directory;
- [ ] Session imported into managed storage;
- [ ] preflight reviewed and one lightweight run completed;
- [ ] result and provenance opened;
- [ ] application closed normally.
