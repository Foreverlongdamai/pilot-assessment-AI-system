# Pilot Assessment System — Portable Release Candidate

This directory contains Pilot Assessment System `v0.1.0-rc.2` for Windows x64. Its acceptance
state is `pending`; it is not yet the accepted final release and is not a scientifically calibrated
pilot-rating product.

## Start

1. Extract the complete ZIP to a normal user-writable folder.
2. Double-click the sole root launcher `PilotAssessment.exe`. The WinUI/.NET payload remains
   contained under `app\`.
3. The app starts its private Python backend automatically. Do not start Python or SQLite manually.
4. Model Studio is immediately available from the software-owned current system model; no
   project is required to inspect or edit Evidence, BN, CPT or task schemes.
5. Create a project by entering a readable name and selecting an empty folder, or open an existing
   project. The backend generates its technical project ID.
6. Import your own canonical Session Bundle or simulator `streams/` + `annotations/` source.

Keep the directory structure intact. Moving only the launcher or files from `app\` will disconnect
the desktop from the private runtime, system model and backend source.

## What is and is not in this package

The package contains the desktop app, private runtimes, editable first-party Python source,
starter resources, the captured current `system\` model library, desktop source, release tools, a
copyable operator example, bundled private dependency helper/uv, manifests and 24 released DOCX
manuals. It contains no user project, Session, simulator sample, biometric data, result or artifact.

The generated DOCX catalog is in `docs\documentation-manifest.json`; Chinese and English manuals
are in `docs\zh-CN\` and `docs\en-GB\`.

User projects remain in the locations selected in the app. UI preferences and recent-project
links are stored under `%LOCALAPPDATA%\PilotAssessmentSystem` on each Windows account.

`system\model-library.sqlite3` owns the current Evidence/BN/CPT/task-scheme definitions for this
entire extracted software copy. Every project opened by this copy sees the same model edits.
Projects own only their Sessions, immutable RunSnapshots, runs, results and artifacts. Copying the
whole software directory creates an independent model/source copy; copying only a project does not.

## Copying the software or a project

Close the app before copying either the software directory or a project directory. Do not copy an
open SQLite database piecemeal.

- Copy the complete extracted software directory to transfer the current `system\` model library,
  editable `backend\src\` Python source, private runtime, desktop app and manifests as one
  independent software copy.
- Copy the complete project root to transfer that project's managed Sessions, immutable
  RunSnapshots, runs, results and artifacts. Open the copied root from the destination software.
- Future runs in a copied project use the destination software copy's current system model and
  Python source. Historical RunSnapshots and their stored source identities remain unchanged.
- Recent-project shortcuts are per Windows account; after copying a project, select its new folder
  once in the app.

This product has no dedicated Backup/Restore command or proprietary project-backup archive. A
normal whole-directory filesystem copy is the supported portability operation.

## Editing

Normal Evidence, BN, CPT and task-scheme edits should be made in the graphical interface. If the
existing backend mechanisms cannot express a new calculation, the active Python source is under
`backend\src\pilot_assessment`. Close the app completely before editing and restart it afterward.
See `backend\README-DEVELOPMENT.md` before changing source.

The dedicated English guide is under `docs\en-GB\` with document ID `PAS-PYTHON-EXT-001`.
Local operators register through
`backend\src\pilot_assessment\evidence\extensions\__init__.py`; their JSON parameter schema uses
the same generic EvidenceRecipe editor as packaged operators and does not require a new C# page.

## Integrity and scientific status

`manifest\checksums.sha256` records the original delivered files, while
`manifest\system-model-baseline.json` identifies the current system captured for that build and
`manifest\source-baseline.json` identifies the delivered first-party Python tree. Diagnostics
shows the exact loaded source, private Python, dependency and operator-catalog identities. A local
source difference is recorded but does not block use. If files change while the app is already
running, new preflight is blocked only until the app is restarted so one run cannot mix old
in-memory code with new disk bytes.

Every new run stores its exact backend identity and a deterministic source snapshot in that
project's content-addressed artifacts. The snapshot is for explanation and maintenance; the app
never auto-executes source from a historical artifact. Normal model edits and local Python edits
naturally make the running copy differ from its delivered manifest. To transfer those edits, close
the app and copy the complete software directory. User projects remain separate and are never part
of a software re-extraction.

The included starter Evidence rules, thresholds, topology and CPTs are engineering defaults that
require domain-expert calibration. `formal_run_authorized=false`; software execution is not proof
of scientific validity, certification or fitness for operational decisions.
