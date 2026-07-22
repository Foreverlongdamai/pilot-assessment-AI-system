+++
document_id = "PAS-RELEASE-001"
language = "en-GB"
title = "Release Build and Delivery Acceptance Guide"
short_title = "Release and Acceptance"
product_version = "0.1.0"
document_version = "0.1.0"
status = "released"
audience = ["maintainer", "release"]
information_types = ["tutorial", "how-to", "reference"]
scope = "Building, externally verifying and handing off the Windows x64 v0.1.0-rc.4 candidate without claiming final user acceptance."
prerequisites = ["Clean source checkout at the intended annotated tag", "Explicit saved current system model", "Windows x64 build environment"]
scientific_status = "engineering-only"
related_documents = ["PAS-ARCH-001", "PAS-QUICKSTART-001", "PAS-PORTABILITY-001", "PAS-PYTHON-CORE-001"]
support = "Retain the delivery JSON, ZIP hash, tag/commit, build log, verification evidence and signed-off acceptance checklist."
release_channel = "release-candidate"
release_label = "v0.1.0-rc.4"
user_acceptance = "pending"
+++

# Release Build and Delivery Acceptance Guide

## 1. Candidate identity and boundary

This manual applies to:

| Field | Required value |
|---|---|
| Product version | `0.1.0` |
| Release channel | `release-candidate` |
| Candidate | `rc.4` |
| Release label/tag | `v0.1.0-rc.4` |
| User acceptance | `pending` |
| Scientific status | `engineering-only` |
| Formal assessment | `formal_run_authorized=false` for the supplied starter |

An engineering-verified candidate is not the final accepted `v0.1.0`. The user must operate and inspect this exact ZIP before acceptance can be recorded. Documentation-only corrections may be recorded explicitly; code/model changes require a new candidate identity.

RC.4 preserves Assessment technical execution, the taskbar icon and global node deletion, and corrects active Save All, normal-node snapback and non-draggable green Raw Input Family roots. Screenshots whose static surface remains truthful may be explicitly recorded as reused from RC.3. Save and drag are interactions and require real WinUI runtime evidence rather than inference from a static image.

## 2. Release inputs

The build has four authorities:

1. a clean Git commit referenced by the annotated candidate tag;
2. an explicitly selected, clean current `system\` model library;
3. the released bilingual Markdown catalog and registered candidate screenshots;
4. the frozen Python/.NET dependency and toolchain inputs.

The builder must never guess a system source or silently fall back to a starter. The selected model is captured read-only after proving its library identity, dynamic node/scheme counts, database/schema compatibility, clean edit session, absence of user-owned rows and absence of WAL/SHM transients.

## 3. Required product contents

The Windows x64 ZIP contains:

- the sole self-contained root launcher `PilotAssessment.exe`, plus `PilotAssessment.Desktop.exe`, private .NET/Windows App SDK files and language resources contained under `app\`;
- clearly visible root semantic directories `backend\`, `system\`, `runtime\`, `developer\`, `docs\`, `licenses\` and `manifest\`;
- private Python runtime and private dependencies;
- exposed active `backend/src/pilot_assessment/` source, lock and dependency helper;
- selected current `system\` model library;
- schemas, integrity manifest, SBOM and third-party notices/licenses;
- release notes, known limitations, portable README and acceptance checklist;
- 24 generated DOCX manuals: 11 modules plus one generated master in Chinese and English;
- the ten registered privacy-reviewed UI screenshots used by those manuals.

It contains no user project, Session, result, biometric data, test fixture, cache, build directory, source-control metadata or PDB.

## 4. Prepare the source and documentation

1. Complete all source/manual changes and released-document validation.
2. Capture screenshots from the exact final UI source tree and register their file/hash/language/dimensions/source identity/privacy review.
3. Build all 24 DOCX files and render every page for visual inspection.
4. Run focused backend, schema, documentation, release, C# unit/contract and x64 Release gates.
5. Confirm `git status --short` is empty.
6. Create the annotated `v0.1.0-rc.4` tag and prove it peels to `HEAD`.

Do not edit UI code after candidate screenshot capture. Any such change invalidates screenshot source identity and requires recapture.

## 5. Build the candidate

From the tagged repository root, with the desktop application closed:

```powershell
.\.tools\uv\uv.exe run python tools\release\build_portable.py `
  --system-source .pilot-assessment-local\system `
  --release-label v0.1.0-rc.4 `
  --release-channel release-candidate `
  --candidate rc.4 `
  --user-acceptance pending `
  --documentation-status released
```

Expected external delivery artifacts are:

```text
PilotAssessment-0.1.0-rc.4-win-x64.zip
PilotAssessment-0.1.0-rc.4-win-x64.zip.sha256
PilotAssessment-0.1.0-rc.4-win-x64.delivery.json
```

The delivery JSON records file name/bytes/SHA-256, tag/commit, system identity/counts, documentation/SBOM hashes and pending acceptance without exposing absolute build-machine paths.

## 6. Verify outside the repository

The authoritative acceptance rehearsal extracts the ZIP to a fresh repository-external temporary directory and uses only packaged runtimes:

```powershell
.\.tools\uv\uv.exe run python tools\release\verify_archive_external.py `
  --dist dist\releases\PilotAssessment-0.1.0-rc.4-win-x64.zip `
  --verify-editable-source `
  --verify-operator-extension `
  --launch-desktop `
  --restricted-path
```

The verifier must demonstrate:

- archive and internal checksum integrity;
- no dependency on repository/system Python/dotnet/PATH tools;
- headless no-project and two-disposable-project workflows;
- visible desktop startup and clean shutdown;
- automatic sidecar/private SQLite behaviour and zero TCP listeners;
- current system identity/counts and clean edit state;
- live Python source modification/restart identity on a disposable copy;
- operator-extension example and dependency metadata;
- 24 documents, ten screenshots, SBOM/licenses and acceptance files;
- no source-system mutation or surviving process/WAL/SHM files.

## 7. Privacy and archive scan

Inspect ZIP member names, extracted text and DOCX XML for:

- build-machine user names and absolute home/repository paths;
- user project/Session/result identifiers or data rows;
- gaze, EEG, ECG, pilot-camera or participant content;
- caches, test data, `.git`, `.venv`, `__pycache__`, logs or PDBs;
- unlisted executables or licenses missing from the SBOM.

Candidate screenshots must come from an anonymous disposable project outside the release and must not display private paths or real Session content.

## 8. Delivery to the user

Deliver the ZIP, `.sha256`, delivery JSON, release notes, known limitations and acceptance checklist together. The receiving user should:

1. verify the ZIP SHA-256;
2. extract to a clean writable directory;
3. create a project outside the product root;
4. import their own Session, including a partial-modality case;
5. run and inspect Evidence/BN results and diagnostics;
6. edit/copy/save model nodes and task schemes, then confirm persistence after restart;
7. optionally inspect and modify Python source on a copied software directory;
8. record accepted, documentation-only corrections, or changes required.

Until that checklist is returned, all release records remain `user_acceptance=pending`.

## 9. Promote or replace the candidate

- If accepted without product changes, create the final release procedure that records the user's evidence and promotes a clean final identity; do not merely rename the candidate ZIP.
- If only documentation corrections are accepted under the agreed category, record exact corrected document hashes and status.
- If code, model, runtime, screenshots or executable behaviour changes, create a later candidate, recapture affected evidence and repeat external verification.
- Scientific calibration, expert endorsement and authorization are future work and are not implied by software acceptance.

## 10. Release-maintainer checklist

- [ ] clean annotated tag equals intended commit;
- [ ] explicit saved system selected and captured read-only;
- [ ] 24 DOCX manuals rendered and visually inspected;
- [ ] ten candidate screenshots registered and privacy-reviewed;
- [ ] focused Python/C#/release gates pass;
- [ ] external restricted-PATH verification passes;
- [ ] ZIP/privacy/SBOM/license scan passes;
- [ ] source system unchanged and no process/lock remains;
- [ ] ZIP hash and delivery JSON recorded;
- [ ] candidate delivered with `user_acceptance=pending`.
