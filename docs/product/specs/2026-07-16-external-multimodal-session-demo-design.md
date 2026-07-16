# Captured-Format Multimodal Software Demo

| Field | Value |
|---|---|
| Date | 2026-07-16 |
| Status | Executed |
| Scope | One engineering Session Bundle and one complete M6 software run |
| Scientific use | Not supported |

## Purpose

Exercise the complete backend on the captured-format simulator CSV at
`C:/Users/long/Desktop/CranfieldOffer/proj/data/S_101500_Time_2026_05_14_16_48_54_P_1.csv`.
The file supplies X and U only. Deterministic schematic I, G, EEG, ECG,
pilot-camera, reference and annotation fixtures complete the Session Bundle.

This is a software interface test. The source flight was not flown against a
validated task reference, and the generated modalities have no scientific or
physiological meaning. Evidence values and BN posteriors from this run must not
be interpreted as an assessment of the pilot.

## Product boundary

Synthetic completion remains outside the product workflow. The sidecar and the
future Windows client do not expose a generate-data or fill-missing-modalities
operation. A real incomplete Session stays incomplete.

For this one-off demo, the existing `pilot_assessment.synthetic` engineering
fixture CLI was invoked manually. It is a developer test utility, not a runtime
service. Its attention-event label was corrected from `critical_monitoring` to
the already-declared Hover starter input type `attention_cue`; this is fixture
compatibility work and does not change Evidence or BN algorithms.

## Actual input

The generated bundle is under the sibling `data/pilot_assessment_demo`
directory and is not part of the product Git repository. It retains the full
29.01-second X/U timeline and contains:

| Input | Retained rows or files |
|---|---:|
| X/U source rows | 2,902 each |
| VR frame index / PNG frames | 871 / 871 |
| VR AOI instances | 1,742 |
| Gaze samples / fixations | 3,482 / 59 |
| EEG samples | 7,427 |
| ECG samples / R peaks | 7,253 / 37 |
| Pilot-camera index / PNG frames | 436 / 436 |
| Task-reference rows | 2,902 |

The many image files are only 64x36 and 48x48 schematic PNGs, so the complete
input bundle is about 1.6 MB. Building a second low-rate generator solely to
reduce this already-small fixture was deliberately avoided.

## Executed workflow

The external demo runner uses only the public JSON-RPC sidecar boundary:

1. start the local sidecar and negotiate protocol 1.0;
2. create a managed project;
3. inspect the external bundle;
4. import it, copying the Session into managed project storage;
5. select the exact seeded Hover starter scheme;
6. run technical preflight with `purpose=software_test`;
7. execute synchronization and all 18 selected Evidence versions;
8. perform exact Bayesian inference;
9. persist and reopen Evidence results, traces, observations, posterior and
   inference trace artifacts;
10. shut down the sidecar.

The final run completed all 23 progress units, executed 18/18 Evidence recipes,
produced all declared artifacts, emitted no stderr and retained
`scientific_status=not_supported`.

## Completion boundary

This proves the current contracts and M6 backend can process one complete
multimodal software fixture end to end. It does not validate the starter anchor
definitions, thresholds, task reference, CPTs or competency estimates, and it
does not complete the Windows frontend or final packaging milestones.
