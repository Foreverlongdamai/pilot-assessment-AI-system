# Release notes — v0.1.0-rc.4

Release channel: `release-candidate`

Candidate: `rc.4`

User acceptance: `pending`

Scientific status: `engineering-only`; starter `formal_run_authorized=false`

## RC.3 acceptance corrections

RC.3 preserved the prior portable/run/icon/delete improvements but was marked `changes-required`
after independent use found three remaining editing defects; a subsequent toolbar review also found
misleading hints and two low-feedback controls. RC.4 corrects these points without moving any prior
tag:

- the main command surface now exposes active **Save All** and `Ctrl+S`; it flushes floating node
  editors, forms, CPT changes and pending layout, atomically commits through the existing Python
  model edit transaction, reloads current system state and keeps the software open;
- normal graph nodes lock their target at pointer press and use the stable XamlRoot coordinate
  space, so virtualization cannot clear the target and the node no longer returns to its original
  position on release;
- the five green Raw Input Family roots are now draggable and their display-only coordinates are
  persisted in each TaskScheme's layout overrides without becoming ModelNodes or entering
  Evidence/BN/CPT and RunSnapshot semantics;
- the Model Studio toolbar removes the low-feedback multi-select and clear-selection icons while
  retaining copy/paste and context-menu additive selection; all seven remaining actions now show
  their actual localized purpose instead of the unrelated `Ctrl+C` hint.

RC.4 also retains the RC.3 corrections: technically ready Assessment-purpose runs complete with an
explicit not-authorized warning, the packaged eVTOL icon resolves from the executable directory,
global node deletion archives through the backend edit transaction, and Chinese/English switching
uses the explicit application resource context.

## Preserved product capabilities

- The root remains eight semantic directories, two files and one launcher, with runtime payload
  contained under `app\`.
- Private Python sidecar and embedded SQLite start automatically; no system Python, .NET SDK,
  Visual Studio or database service is required.
- Missing Session modalities remain explicit; independent Evidence and BN inference can proceed.
- The software-wide model library, exposed Python source, extension example, bilingual manuals,
  checksums, SBOM, provenance and licences remain included.
- User projects, Sessions, results, biometric data and synthetic test data remain excluded.

Engineering verification does not change acceptance. Only independent use of the exact RC.4 ZIP
can replace `user_acceptance=pending` with an accepted or further change-required result.
