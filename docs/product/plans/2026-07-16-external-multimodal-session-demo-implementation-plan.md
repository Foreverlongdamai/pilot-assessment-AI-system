# Captured-Format Multimodal Software Demo Plan

| Field | Value |
|---|---|
| Date | 2026-07-16 |
| Status | Completed |
| Execution mode | Inline, one lightweight fixture |

## Goal

Use the captured-format X/U CSV plus synthetic missing modalities to verify one
complete M6 workflow without adding synthetic generation to the product.

## Completed steps

- [x] Manually generate one deterministic full Session Bundle through the
  existing engineering fixture CLI.
- [x] Keep the generated Session, runner, managed copy and results under
  `../data/pilot_assessment_demo`, outside product Git and runtime APIs.
- [x] Inspect and import the bundle through the M6 sidecar.
- [x] Preserve the first real failure and trace it to an incompatible synthetic
  event label used by H2.
- [x] Add one focused regression assertion, correct the fixture label to
  `attention_cue`, and run the 32-test synthetic suite.
- [x] Regenerate the one fixture and rerun the complete seeded Hover scheme.
- [x] Confirm 18/18 Evidence executions, exact BN inference, durable artifacts,
  clean sidecar stderr and a completed terminal state.
- [x] Remove the redundant first bundle/project/result directories.
- [x] Record exact commands, output paths and scientific limitations in the
  external demo README.

## Non-goals

- no automatic filling of absent modalities;
- no JSON-RPC or UI synthetic-generation method;
- no scientific validation of generated values, starter Evidence or BN output;
- no heavy multi-dataset or large-image test campaign;
- no M7 frontend or final installer work.

## Verification commands

```powershell
& .\.tools\uv\uv.exe run pytest tests/synthetic -q

& .\.tools\uv\uv.exe run python `
  ..\data\pilot_assessment_demo\tools\run_m6_sidecar_demo.py `
  --bundle ..\data\pilot_assessment_demo\full_multimodal_session_ready `
  --project ..\data\pilot_assessment_demo\managed_project_run2 `
  --results ..\data\pilot_assessment_demo\results_run2
```

Expected verified outcomes: `32 passed`; final run state `completed`; 18
Evidence result artifacts; 18 Evidence trace artifacts; posterior and inference
trace artifacts present; `scientific_status=not_supported`.
