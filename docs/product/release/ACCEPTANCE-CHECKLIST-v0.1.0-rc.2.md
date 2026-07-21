# User acceptance checklist — v0.1.0-rc.2

Initial status: `user_acceptance=pending`. Complete this checklist on the extracted candidate.

## Root layout and lifecycle

- [ ] The ZIP hash matches the supplied `.zip.sha256` file.
- [ ] The product root contains exactly eight semantic directories: `app`, `backend`,
  `developer`, `docs`, `licenses`, `manifest`, `runtime` and `system`.
- [ ] The only root launchable file is `PilotAssessment.exe`; framework DLLs, WinMD files,
  language-resource directories and the real desktop executable are contained under `app\`.
- [ ] `README.txt` gives the short start and directory explanation.
- [ ] `PilotAssessment.exe` starts without Visual Studio, Python, .NET or SQLite setup.
- [ ] Closing the main window closes the desktop, launcher and private Python sidecar.
- [ ] Chinese and English UI switching behaves as expected.

## Projects, Sessions and runs

- [ ] A first project can be created in an empty user-selected directory.
- [ ] A second project can be created or opened without changing the software-wide model library.
- [ ] A simulator `streams\` plus optional `annotations\` export imports without modifying its
  source directory.
- [ ] A partial-modality Session reports missing inputs explicitly and still computes independent
  Evidence.
- [ ] Preflight, run progress, Results and Diagnostics are understandable.

## Expert model editing and extension

- [ ] The five-layer canvas shows Raw Input, Extracted Data, Evidence, Sub-skill and Competency.
- [ ] Nodes can be copied, pasted, renamed, edited, activated/deactivated and arranged.
- [ ] Evidence recipes/operator parameters and BN parents/states/CPTs can be inspected and saved.
- [ ] Save All persists staged changes after restart; Discard All and close-with-No do not.
- [ ] The exposed Python source and operator example are present and match the manuals.
- [ ] Copying the complete closed software directory preserves `system\` and Python source, while
  copying a project preserves only that project's Sessions and history.

## Boundary

- [ ] The product contains no user project, Session, result or biometric data.
- [ ] RC.1 is recorded as `changes-required`; RC.2 remains `pending` until this checklist is
  signed off.
- [ ] The starter model is labelled engineering-only and `formal_run_authorized=false`.

