# M8E release-candidate tools

From the tagged, clean repository root, build the Windows x64 candidate with:

```powershell
.\.tools\uv\uv.exe run python tools\release\build_portable.py `
  --system-source .pilot-assessment-local\system `
  --release-label v0.1.0-rc.2 `
  --release-channel release-candidate `
  --candidate rc.2 `
  --user-acceptance pending `
  --documentation-status released
```

The builder publishes WinUI/.NET/Windows App SDK self-contained, verifies the pinned official
CPython embedded ZIP, installs the frozen production dependency closure, copies the one active
first-party Python source tree, captures the explicitly selected saved current `system/`, writes
checksums/baselines/SBOM, runs a disposable-copy verification, and creates:

- `dist/releases/PilotAssessment-0.1.0-rc.2-win-x64.zip`;
- its independent `.zip.sha256` file; and
- `PilotAssessment-0.1.0-rc.2-win-x64.delivery.json`.

Candidate mode requires an annotated release-label tag that peels to `HEAD` and a clean worktree.
Candidate names must match `rc.<positive-integer>`.
It refuses `--skip-archive`, review-status manuals, ambiguous identity and an accepted/final state.
The command never guesses a system source. If it reports a lock or unsaved edits, close the app
after choosing Save All or Discard All; the builder does not modify or replace that source.

Run a direct package-directory check with:

```powershell
.\.tools\uv\uv.exe run python tools\release\verify_portable.py `
  dist\releases\PilotAssessment-0.1.0-rc.2-win-x64 `
  --verify-editable-source `
  --verify-operator-extension `
  --launch-desktop
```

Product users only unzip the ZIP and run the sole root launcher `PilotAssessment.exe`. The actual
WinUI/.NET payload is contained under `app/`; the root retains the editable/semantic directories
`backend/`, `system/`, `runtime/`, `developer/`, `docs/`, `licenses/` and `manifest/`. The stronger delivery gate
extracts the ZIP to a disposable repository-external directory and uses only its private Python:

```powershell
.\.tools\uv\uv.exe run python tools\release\verify_archive_external.py `
  --dist dist\releases\PilotAssessment-0.1.0-rc.2-win-x64.zip `
  --verify-editable-source `
  --verify-operator-extension `
  --launch-desktop `
  --restricted-path
```

The external verifier checks the delivery JSON/hash, scans 24 DOCX XML payloads for private paths,
verifies editable source and a new operator, launches the visible desktop, and confirms zero TCP
listeners. Automated verification leaves `user_acceptance=pending`.
