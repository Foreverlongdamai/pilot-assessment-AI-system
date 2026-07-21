# Portable release tools

From the repository root, build the Windows x64 product directory and ZIP with:

```powershell
.\.tools\uv\uv.exe run python tools\release\build_portable.py `
  --system-source .pilot-assessment-local\system
```

The builder publishes WinUI/.NET/Windows App SDK self-contained, verifies the pinned official
CPython embedded ZIP, installs the frozen production dependency closure, copies the single live
backend source tree, consistently captures the explicitly selected saved current `system/` model
library, rebuilds a clean edit workspace around it, writes dynamic
manifests/checksums/SBOM, runs a no-project/two-project headless verification on a disposable copy,
and creates `dist/releases/PilotAssessment-<version>-win-x64.zip`.

The command never guesses a system source and never falls back to a new starter model. If it says
the source is locked, close the desktop app. If it reports unsaved edits, reopen that software copy
and choose Save All or Discard All before closing. Integrity, schema, identity or user-owned-row
failures require selecting or repairing the intended system directory; the builder will not modify
or replace it automatically.

Run the stronger local verification, including temporary live-source editing and visible desktop
startup, with:

```powershell
.\.venv\Scripts\python.exe tools\release\verify_portable.py `
  dist\releases\PilotAssessment-0.1.0-win-x64 `
  --verify-editable-source `
  --launch-desktop
```

These are build-machine commands. Product users only unzip the ZIP and run
`PilotAssessment.Desktop.exe`.

Verify the ZIP after extracting it to a fresh repository-external temporary directory with its
own private Python:

```powershell
.\.venv\Scripts\python.exe tools\release\verify_archive_external.py `
  dist\releases\PilotAssessment-0.1.0-win-x64.zip `
  --verify-editable-source `
  --launch-desktop
```
