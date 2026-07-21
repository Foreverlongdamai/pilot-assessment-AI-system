# `v0.1.0-rc.2` Portable Root Layout Verification

| Field | Verified value |
|---|---|
| Date | 2026-07-21 |
| Candidate | `v0.1.0-rc.2` |
| Annotated tag peel | `865c3e993ac2c74cc8161fc5d65cf2e108d07001` |
| User acceptance | `pending` |
| Scientific status | `formal_run_authorized=false` |
| Verification environment | Current Windows host plus repository-external disposable extraction with restricted `PATH` |

## 1. Root acceptance correction

The built and externally extracted product root contains exactly:

```text
PilotAssessment.exe
README.txt
app/
backend/
developer/
docs/
licenses/
manifest/
runtime/
system/
```

| Measure | RC.1 observation | RC.2 verified result |
|---|---:|---:|
| root directories | 94 | 8 |
| root files | 374 | 2 |
| root launchers | unclear among payload | 1 (`PilotAssessment.exe`) |
| desktop payload root | product root | `app/` |

The packaged verifier uses an exact whitelist and rejects leaked DLL, WinMD, language-resource or
additional launcher entries at the root. The release manifest is
`pilot-assessment-release-manifest-v3`, with `entrypoint=PilotAssessment.exe` and
`desktop_executable=app/PilotAssessment.Desktop.exe`.

## 2. Build identity and artifacts

| Artifact/fact | Value |
|---|---|
| product directory | `dist/releases/PilotAssessment-0.1.0-rc.2-win-x64/` |
| directory files | 4,334 |
| directory bytes | 804,343,304 |
| checksummed files | 4,333 (all files except the checksum inventory itself) |
| ZIP | `PilotAssessment-0.1.0-rc.2-win-x64.zip` |
| ZIP bytes | 293,346,576 |
| ZIP SHA-256 | `ebc5978075f399063c2c6b40f2d0a2594635713d56475f977c181ba7d612610a` |
| model identity | `79efc59cb38242a7edfa1c85a5311729c40a769bcbf7256b2f5f1d5cb0400a1e` |
| model size | 54 nodes / 2 schemes |

The annotated RC.1 tag still peels to
`c736bf7ad58bd24212b8997c5bbbf427b96e2692`; the RC.2 tag is independent and clean.

## 3. Fresh gates

| Gate | Result |
|---|---|
| Desktop Unit Tests | 107/107 passed |
| real-sidecar Contract Tests | 4/4 passed |
| release + documentation tests | 28/28 passed |
| focused release tests | 11/11 passed |
| x64 Release desktop build | 0 warnings / 0 errors |
| launcher publish | self-contained trimmed single `PilotAssessment.exe` |
| released manuals | 24/24 generated and validated |
| package-internal operator extension | passed; 46 operators after temporary extension, recipe value 2.75, completed run |

## 4. Repository-external restricted-PATH verification

The final ZIP was extracted below a fresh `%TEMP%` directory outside the repository. Its packaged
private Python executed the verifier with editable-source, operator-extension and desktop launch
gates enabled.

Observed process chain:

```text
PilotAssessment.exe (launcher PID 43968)
└── app/PilotAssessment.Desktop.exe (desktop PID 22676, window handle 1969486)
    └── runtime/python/python.exe (sidecar PID 44088)
```

The window appeared, the packaged sidecar reported ready, the product opened the captured root
`system/` model from the nested desktop location, and all product processes closed after the
verifier posted a normal window close. No product process opened a TCP listener.

The same extraction also proved:

- live edit/restart loading from `backend/src/pilot_assessment`;
- temporary operator registration, parameter schema, Evidence recipe and completed run;
- two disposable project workflows and source-artifact provenance;
- 24 DOCX files and 360 DOCX XML parts free of private user-home paths;
- 10 registered screenshots, checksums, source/system baselines, SBOM and licences;
- zero dependency on repository Python, system Python, .NET SDK, Visual Studio or a separate
  SQLite service at runtime.

## 5. Verdict

The RC.1 root-layout acceptance defect is closed at the engineering-candidate level in RC.2.
`v0.1.0-rc.2` is ready for the user's next independent acceptance pass. This evidence does not
change `user_acceptance=pending`, does not certify the starter assessment model and does not set
`formal_run_authorized=true`.

