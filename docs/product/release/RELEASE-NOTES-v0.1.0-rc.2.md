# Release notes — v0.1.0-rc.2

Release channel: `release-candidate`

Candidate: `rc.2`

User acceptance: `pending`

Scientific status: `engineering-only`; `formal_run_authorized=false`

## RC.1 acceptance correction

RC.1 was marked `changes-required` because its product root exposed 94 directories and 374
files. Self-contained WinUI/.NET DLLs, WinMD files, language resources and framework directories
obscured the product's semantic entry points.

RC.2 corrects that layout without moving or rewriting the RC.1 tag or package:

- all WinUI, .NET and Windows App SDK runtime payload is contained under `app\`;
- the root exposes one self-contained launcher, `PilotAssessment.exe`;
- the root keeps `backend\`, `system\`, `runtime\`, `developer\`, `docs\`, `licenses\` and
  `manifest\` clearly visible;
- the desktop runtime locates the product root from its nested `app\` location;
- the release manifest and verifier enforce the root whitelist and reject leaked runtime files;
- handoff documents live under `docs\`, while root `README.txt` provides the short start guide.

## Preserved product capabilities

- Private Python sidecar and embedded SQLite start automatically; no system Python, .NET SDK,
  Visual Studio or database service is required on the target machine.
- The software-wide editable model library contains Raw Input, Evidence and BN nodes, task
  schemes, parents, states, CPTs, layouts, recipes and operator parameters.
- Managed Session import accepts canonical bundles or simulator `streams\` plus optional
  `annotations\`; missing modalities remain explicit and unrelated Evidence can still run.
- Exposed Python source, extension example, developer source, 24 bilingual DOCX manuals,
  checksums, SBOM, provenance and third-party licences remain included.
- User projects, Sessions, results, biometric data and synthetic test data remain excluded.

Engineering verification does not change acceptance. Only independent use of the exact RC.2 ZIP
can replace `user_acceptance=pending` with an accepted or further change-required result.

