# User acceptance checklist — v0.1.0-rc.3

Initial status: `user_acceptance=pending`. Complete this checklist on the extracted candidate.

## Root layout, startup and icon

- [ ] The ZIP hash matches the supplied `.zip.sha256` file.
- [ ] The product root contains exactly `app`, `backend`, `developer`, `docs`, `licenses`,
  `manifest`, `runtime` and `system`, plus `PilotAssessment.exe` and `README.txt`.
- [ ] `PilotAssessment.exe` starts without manually installing or starting Python, .NET or SQLite.
- [ ] The eVTOL product icon appears in the window title and Windows taskbar after root-launcher
  startup.
- [ ] Closing the main window closes the desktop, launcher and private Python sidecar.
- [ ] Chinese and English UI switching behaves as expected.

## Projects, Sessions and runs

- [ ] A project can be created or opened outside the product directory.
- [ ] Simulator `streams\` plus optional `annotations\` imports without modifying the source.
- [ ] A partial-modality Session reports missing inputs and still computes independent Evidence.
- [ ] With a technically ready preflight, purpose **Assessment** can start and complete while the
  UI/frozen preflight provenance keeps `formal_run_authorized=false` and shows the warning.
- [ ] True technical errors still block Start run and identify a stable diagnostic.
- [ ] Results and Diagnostics remain understandable and preserve provenance.

## Expert model editing

- [ ] The five-layer canvas shows Raw Input, Extracted Data, Evidence, Sub-skill and Competency.
- [ ] Holding the primary button and moving a node at least 4 px visibly drags it; an ordinary
  click still selects it, release stages the new position, Ctrl+Z restores it, and Save All
  persists it after restart.
- [ ] Toolbar and context menu both expose **Delete node from system model**.
- [ ] Delete asks for confirmation, removes affected active downstream closure, archives the node,
  reports affected task schemes, supports Ctrl+Z and does not alter historical RunSnapshots.
- [ ] Copy/paste, rename, activation, Evidence/operator parameters, BN parents/states/CPT and
  Save All / Discard All continue to work.
- [ ] Exposed Python source and the operator example match the manuals.

## Boundary

- [ ] The product contains no user project, Session, result or biometric data.
- [ ] RC.1 and RC.2 are recorded as `changes-required`; RC.3 remains `pending` until this exact
  checklist is signed off.
- [ ] An Assessment-purpose run is not represented as scientifically validated while
  `formal_run_authorized=false`.
