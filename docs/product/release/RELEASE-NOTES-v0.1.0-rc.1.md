# Release notes — v0.1.0-rc.1

Release channel: `release-candidate`  
Candidate: `rc.1`  
User acceptance: `pending`  
Scientific status: `engineering-only`; `formal_run_authorized=false`

## Included

- Self-contained Windows x64 WinUI desktop app with an automatically supervised private Python
  JSON-RPC sidecar and embedded SQLite files; no Python, .NET or database setup is required.
- Software-wide editable model library containing Raw Input, Evidence and BN nodes, task schemes,
  fixed parents, ordered states, CPTs, layouts, recipes and operator parameters.
- Five-layer Model Studio projection, copy/paste, activation closure, staged Save All/Discard All,
  multiple floating editors, Undo, Chinese/English UI switching and English canonical model data.
- Managed Session import from canonical bundles or simulator `streams/` plus optional
  `annotations/`; missing modalities remain explicit and do not prevent unrelated Evidence from
  computing.
- Immutable RunSnapshots, Evidence observations, BN posteriors, diagnostics, source provenance
  and content-addressed result artifacts inside user-selected projects.
- Exposed first-party Python source, frozen private dependency closure, dependency helper,
  desktop source, release tools and a copyable operator-extension example.
- Twelve logical manuals in Chinese and English (24 DOCX files), including the generated master
  technical reference and ten privacy-reviewed candidate screenshots.
- Checksums, source and system-model baselines, SPDX SBOM, third-party notices and collected
  licence files.

## Deliberately not included

- User projects, Sessions, result data, biometric data, simulator samples or synthetic test data.
- A dedicated Backup/Restore product feature; close the app and copy the complete software or
  project directory instead.
- Scientific calibration, expert endorsement, certification, code signing, installer/MSIX,
  automatic update or store distribution.

Engineering automation and repository-external verification do not change the acceptance state.
Only the user's independent test can replace `user_acceptance=pending` with an accepted result.
