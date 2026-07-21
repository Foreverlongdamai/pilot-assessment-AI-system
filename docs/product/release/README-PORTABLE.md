# Pilot Assessment System — Portable Engineering Build

This directory contains the Windows x64 Pilot Assessment System. It is an M8B engineering build,
not the final M8E release candidate and not a scientifically calibrated pilot-rating product.

## Start

1. Extract the complete ZIP to a normal user-writable folder.
2. Double-click `PilotAssessment.Desktop.exe`.
3. The app starts its private Python backend automatically. Do not start Python or SQLite manually.
4. Model Studio is immediately available from the software-owned starter model library; no
   project is required to inspect or edit Evidence, BN, CPT or task schemes.
5. Create a project by entering a readable name and selecting an empty folder, or open an existing
   project. The backend generates its technical project ID.
6. Import your own canonical Session Bundle or simulator `streams/` + `annotations/` source.

Keep the directory structure intact. Moving only the EXE will disconnect it from the private
runtime and backend source.

## What is and is not in this package

The package contains the desktop app, private runtimes, editable first-party Python source,
starter resources, one clean `system\` model library, desktop source, release tools, a copyable
operator example, bundled private dependency helper/uv, manifests and minimal release
documentation. It contains no user project, Session, simulator sample, biometric data, result or
artifact.

User projects remain in the locations selected in the app. UI preferences and recent-project
links are stored under `%LOCALAPPDATA%\PilotAssessmentSystem` on each Windows account.

`system\model-library.sqlite3` owns the current Evidence/BN/CPT/task-scheme definitions for this
entire extracted software copy. Every project opened by this copy sees the same model edits.
Projects own only their Sessions, immutable RunSnapshots, runs, results and artifacts. Copying the
whole software directory creates an independent model/source copy; copying only a project does not.

## Editing

Normal Evidence, BN, CPT and task-scheme edits should be made in the graphical interface. If the
existing backend mechanisms cannot express a new calculation, the active Python source is under
`backend\src\pilot_assessment`. Close the app completely before editing and restart it afterward.
See `backend\README-DEVELOPMENT.md` before changing source.

The dedicated instructions are in `docs\python-operator-extension-development.md`. Local
operators register through
`backend\src\pilot_assessment\evidence\extensions\__init__.py`; their JSON parameter schema uses
the same generic EvidenceRecipe editor as packaged operators and does not require a new C# page.

## Integrity and scientific status

`manifest\checksums.sha256` records the original delivered files, while
`manifest\system-model-baseline.json` identifies the clean starter model and
`manifest\source-baseline.json` identifies the delivered first-party Python tree. Diagnostics
shows the exact loaded source, private Python, dependency and operator-catalog identities. A local
source difference is recorded but does not block use. If files change while the app is already
running, new preflight is blocked only until the app is restarted so one run cannot mix old
in-memory code with new disk bytes.

Every new run stores its exact backend identity and a deterministic source snapshot in that
project's content-addressed artifacts. The snapshot is for explanation and maintenance; the app
never auto-executes source from a historical artifact. Normal model edits and local Python edits
naturally change their respective baselines. Preserve a clean copy or re-extract the ZIP for
recovery; user projects are not part of that reset.

The included starter Evidence rules, thresholds, topology and CPTs are engineering defaults that
require domain-expert calibration. `formal_run_authorized=false`; software execution is not proof
of scientific validity, certification or fitness for operational decisions.
