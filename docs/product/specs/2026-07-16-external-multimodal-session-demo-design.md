# External Multimodal Session Demo Design

| Field | Value |
|---|---|
| Date | 2026-07-16 |
| Status | Approved for external demo implementation |
| Scope | External test-data preparation and one M6 software-test run |
| Product impact | None: no synthetic-data capability is added to runtime, sidecar, or UI |

## 1. Purpose

Use the captured simulator CSV at
`C:/Users/long/Desktop/CranfieldOffer/proj/data/S_101500_Time_2026_05_14_16_48_54_P_1.csv`
as the real X/U portion of one test Session Bundle. Prepare lightweight synthetic I/G/EEG/ECG/pilot-camera artifacts outside the product, then submit the completed bundle to the unchanged M6 backend.

The demo answers one engineering question: can the current input contracts, managed import, synchronization, Evidence execution, Bayesian inference, persistence, artifacts, and stdio protocol operate as one continuous workflow on this captured-format sample?

It does not assess the pilot represented by the CSV. The source flight is not a task-performance reference, and all generated modalities, annotations, AOIs, reference data, Evidence values, and posterior values are software-test material only.

## 2. Mandatory separation boundary

The product remains a consumer of acquired data. This demo must not add any of the following:

- a synthetic-data method in the M6 JSON-RPC sidecar;
- a generate/fill-missing-data action in the future WinUI client;
- automatic substitution when a real Session lacks I, G, EEG, ECG, or pilot-camera data;
- a runtime dependency on the external fixture builder;
- a claim that synthetic values represent physiology, attention, workload, task performance, or pilot competency.

The external builder and its outputs live under `C:/Users/long/Desktop/CranfieldOffer/proj/data/pilot_assessment_demo/`, outside the `pilot_assessment_system` Git repository. The demo may import the product's public contracts and validation entry points to prove compatibility, but it must not import, call, or modify `pilot_assessment.synthetic`.

The existing `pilot_assessment.synthetic` package remains unchanged during this work. Its eventual relocation or exclusion from a final installer is a packaging decision, not part of this demo.

## 3. Output layout

```text
data/pilot_assessment_demo/
├── README.md
├── tools/
│   ├── build_external_fixture.py
│   └── run_m6_sidecar_demo.py
├── full_multimodal_session/
│   ├── manifest.json
│   ├── streams/
│   ├── references/
│   ├── annotations/
│   └── integrity/
├── managed_project/
└── results/
    ├── rpc-transcript.jsonl
    ├── run-summary.json
    └── artifact-index.json
```

`full_multimodal_session` is the inspectable external input. `managed_project` is the portable copy owned by M6 after import. `results` contains human-readable demonstration evidence. Deleting the entire `pilot_assessment_demo` directory must have no effect on product code.

## 4. External fixture content

The complete 29.01-second source timeline is retained.

| Modality | Source | Demo rate/content |
|---|---|---|
| X/U | Captured CSV | Original file copied byte-for-byte; about 100 Hz and 2,902 data rows |
| I: VR scene | External schematic frames | 2 Hz, about 59 RGB PNG frames, 64x36 |
| G: gaze/fixation | External deterministic fixture | 120 Hz gaze plus half-second fixations; gaze associates with the latest available scene frame |
| EEG | External deterministic fixture | 256 Hz, eight named channels, explicitly non-neurophysiological |
| ECG | External deterministic fixture | 250 Hz plus R-peak table, explicitly non-physiological |
| pilot camera | External schematic frames | 1 Hz, about 30 RGB PNG frames, 48x48, no real identity |
| task reference | External software fixture | Same time domain, explicitly not a commanded or acceptable trajectory |
| annotations | External software fixture | Three phases, disturbance events, and baseline interval, all marked semantically unvalidated |

The images are small, inspectable geometric placeholders. They demonstrate timestamped image paths, head/eye boxes, AOI geometry, gaze-to-frame association, checksums, and managed copying; they are not photorealistic training data.

All generated artifacts use one fixed seed and record their provenance. The manifest classifies the bundle as synthetic software-test data even though X/U originated from a captured-format CSV. Consequently, `purpose=software_test` is allowed when technical preflight is ready, while formal assessment remains unauthorized.

## 5. Backend execution flow

`run_m6_sidecar_demo.py` exercises the same local process boundary intended for M7:

1. start `python -m pilot_assessment.sidecar`;
2. call `runtime.hello`;
3. create or cleanly recreate `managed_project` for this explicit demo run;
4. call `session.inspect` and save the ingestion summary;
5. call `session.import`, causing M6 to copy the bundle into managed project storage;
6. temporarily rename the external bundle after import, proving that execution no longer reads it, and restore it in a `finally` path;
7. select the exact pre-seeded Hover starter scheme version;
8. call `run.preflight` with `purpose=software_test`;
9. call `run.start`, then read `run.status` and `run.events.list` until terminal;
10. retrieve `result.get` and all declared result artifacts;
11. call `runtime.shutdown` and save the complete JSON-RPC transcript.

The first attempt uses the complete starter scheme and its full Evidence closure. It must not silently replace that scheme with the minimal O1 integration fixture. If the full scheme fails, the transcript and exact technical error become the result of the demo; a smaller diagnostic run may be added only as a separately labelled investigation.

## 6. Result presentation

The README and `run-summary.json` explain:

- exact input file, duration, per-modality row/frame counts, file sizes, and checksums;
- ingestion and synchronization dispositions;
- exact scheme/component identities;
- Evidence calculation status and values produced by the configured starter recipes;
- BN posterior output and artifact references when inference completes;
- run events, terminal state, elapsed time, and any stable error code;
- the scientific disclaimer that no output is a valid evaluation of the pilot.

The demo does not suppress poor numerical performance or unusual signals. It only rejects malformed contracts or other failures that make the configured computation technically impossible.

## 7. Verification and failure handling

Before reporting success, verify:

1. the source CSV in `data` is unchanged;
2. every manifest path exists and every checksum matches;
3. expected low image counts and declared sample rates match generated tables;
4. M1 readiness and M3 synchronization accept the bundle for software testing;
5. sidecar stdout contains only JSON-RPC messages;
6. imported execution reads the managed copy rather than the external source;
7. result and artifact references reopen after sidecar restart;
8. no tracked product source file changed merely to generate the demo data.

If a product defect blocks the run, preserve the generated bundle and transcript, identify the failing product boundary, and report it before changing production code. Scientific or starter-model disagreement is not a platform defect and must not be “fixed” to force a pleasing score.

## 8. Completion boundary

This work is complete when the external bundle and scripts are inspectable under `data`, the unchanged M6 sidecar has been exercised, and the real terminal outcome is recorded. A completed software demo does not complete M7, M8, real exporter integration, or expert validation.
