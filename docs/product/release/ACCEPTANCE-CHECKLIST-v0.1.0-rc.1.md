# User acceptance checklist — v0.1.0-rc.1

Initial status: `user_acceptance=pending`. Complete this checklist on the extracted candidate; do
not rename it to a final `v0.1.0` release merely because automated engineering checks passed.

## Installation and lifecycle

- [ ] The ZIP hash matches the supplied `.zip.sha256` file.
- [ ] The complete ZIP extracts to a user-writable directory.
- [ ] `PilotAssessment.Desktop.exe` starts without Visual Studio, Python or SQLite setup.
- [ ] Closing the main window closes the private Python sidecar and leaves no product process.
- [ ] Chinese and English UI switching behaves as expected.

## Projects, Sessions and runs

- [ ] A first project can be created in an empty user-selected directory.
- [ ] A second project can be created or opened without changing the software-wide model library.
- [ ] A simulator `streams/` plus optional `annotations/` export imports into managed project
  storage without modifying the source directory.
- [ ] A partial-modality Session reports missing inputs explicitly and still computes independent
  Evidence.
- [ ] Technical preflight, run progress, Results and Diagnostics are understandable.
- [ ] Historical results reopen with their immutable RunSnapshot and provenance.

## Expert model editing

- [ ] The five-layer canvas shows Raw Input, Extracted Data, Evidence, Sub-skill and Competency.
- [ ] Nodes can be copied, pasted, renamed, edited, activated/deactivated and arranged.
- [ ] Evidence recipes/operator parameters and BN parents/states/CPTs can be inspected and saved.
- [ ] Save All persists staged changes after restart; Discard All and close-with-No do not.
- [ ] Parent activation and downstream-deactivation confirmation behave as documented.
- [ ] Two task schemes can select different subsets from the shared global node library.

## Extension, portability and boundaries

- [ ] The exposed Python source and operator example are present and match the manuals.
- [ ] Copying the entire closed software directory preserves its current `system/` and Python
  source; copying a project preserves only that project's Sessions and history.
- [ ] The product package contains no user project, Session, result or biometric data.
- [ ] The starter model is clearly labelled engineering-only and
  `formal_run_authorized=false`.
- [ ] Any accepted, rejected or change-required outcome is recorded separately with date,
  candidate hash and observations; until then the status remains `pending`.
