# Release notes — v0.1.0-rc.3

Release channel: `release-candidate`

Candidate: `rc.3`

User acceptance: `pending`

Scientific status: `engineering-only`; starter `formal_run_authorized=false`

## RC.2 acceptance corrections

RC.2 retained its verified portable root but was marked `changes-required` after independent use
found four interaction defects. RC.3 corrects them without moving either prior tag:

- a technically ready Assessment-purpose run can now complete; false scientific authorization is
  preserved as `run.assessment_not_authorized` warning and frozen provenance instead of a block;
- main and floating windows resolve the packaged eVTOL icon by absolute executable-relative path,
  and the icon is required in build/publish payload;
- Model Studio exposes global **Delete node** in the toolbar and context menu; one staged backend
  transaction cascades affected task deactivation and archives the node while preserving history;
- held-pointer drag now receives handled WinUI Button pointer events, uses a 4 px movement
  threshold instead of a fragile dwell timer, and follows a stable coordinate system before
  queuing one layout update on release.

Visible RC.3 verification also exposed and corrected a WinUI runtime crash in the existing
Chinese/English toggle. Language changes now replace the application's explicit resource context
without changing the process-wide platform language override.

## Preserved product capabilities

- The root remains eight semantic directories, two files and one launcher, with runtime payload
  contained under `app\`.
- Private Python sidecar and embedded SQLite start automatically; no system Python, .NET SDK,
  Visual Studio or database service is required.
- Missing Session modalities remain explicit; independent Evidence and BN inference can proceed.
- The software-wide model library, exposed Python source, extension example, bilingual manuals,
  checksums, SBOM, provenance and licences remain included.
- User projects, Sessions, results, biometric data and synthetic test data remain excluded.

Engineering verification does not change acceptance. Only independent use of the exact RC.3 ZIP
can replace `user_acceptance=pending` with an accepted or further change-required result.
