> **Status: SUPERSEDED (2026-07-10).** This document is retained only as historical design context. The authoritative product baseline is [../../product/README.md](../../product/README.md). In particular, its older anchor inventory, phase boundary, and limited graph-edit assumptions must not be used for implementation.

# Backend Core Package + Runtime Adapter Design

Date: 2026-07-08
Project root: `C:\Users\long\Desktop\CranfieldOffer\proj\pilot_assessment_system`
Approved direction: Core package + runtime adapter

## Goal

Build the backend as a standalone Python package that can run independently now and later be launched by a Windows desktop application as a local sidecar process. The backend must preserve the research design:

`raw multimodal streams -> deterministic anchor extraction -> evidence scoring -> Bayesian-network inference -> four competency outputs`

The backend is not a black-box training pipeline. It is an interpretable assessment engine whose nodes, edges, anchor thresholds, and CPT parameters can be loaded, inspected, edited, and saved.

## Product Boundary

This design covers the backend only. The Windows frontend will come later. The backend must still be prepared for it:

- The frontend can start the backend process.
- The frontend can submit session files.
- The frontend can ask what input modalities are supported.
- The frontend can request the Bayesian-network graph as structured JSON.
- The frontend can inspect and update node CPT parameters.
- The frontend can run inference and receive competency outputs, evidence traces, and diagnostic messages.

## Technical Direction

Use a modern Python package with a `src/` layout and `uv` tooling. The backend exposes three layers:

1. A pure Python core API for tests and notebooks.
2. A command/runtime adapter for desktop sidecar integration.
3. Configuration files for anchors, BN graph structure, and CPT defaults.

The first implementation should avoid a web-server-first design. A local HTTP API can be added later, but the first bridge should be command oriented and sidecar friendly.

## Proposed Directory Structure

```text
pilot_assessment_system/
  pyproject.toml
  README.md
  docs/
    backend_architecture.md
    module_plan.md
    superpowers/
      specs/
        2026-07-08-backend-core-runtime-adapter-design.md
  resources/
    sample_data/
      README.md
  src/
    pilot_assessment/
      __init__.py
      config/
        anchors.yaml
        bn_structure.yaml
        cpt_defaults.yaml
      data/
        __init__.py
        csv_loader.py
        modality_registry.py
        session_schema.py
      anchors/
        __init__.py
        objective.py
        human_factor.py
        scoring.py
      bn/
        __init__.py
        graph.py
        cpt.py
        inference.py
      pipeline/
        __init__.py
        evidence_builder.py
        result_builder.py
        run_session.py
      app_bridge/
        __init__.py
        commands.py
        sidecar_protocol.py
      reports/
        __init__.py
        summaries.py
  tests/
    test_csv_loader.py
    test_anchor_scoring.py
    test_bn_graph.py
```

## Module Responsibilities

### `data`

Owns input normalization.

- `session_schema.py`: typed structures for a pilot session, time series, available modalities, phase markers, event markers, and missing streams.
- `csv_loader.py`: loads the current simulator CSV format, including `Simulation time`, flight state columns, and pilot controls.
- `modality_registry.py`: records whether `X(t)`, `U(t)`, `I(t)`, `G(t)`, and `P(t)` are present, missing, or future placeholders.

The first real data sample is:

`C:\Users\long\Desktop\CranfieldOffer\proj\data\S_101500_Time_2026_05_14_16_48_54_P_1.csv`

It has 2902 rows, 33 columns, and covers 0 to 29.01 seconds at about 100 Hz. Phase 1 must support this file directly.

### `anchors`

Owns deterministic feature extraction and evidence scoring.

- `objective.py`: computes objective anchors from `X(t)` and `U(t)` first.
- `human_factor.py`: defines interfaces for H1 and H4 even while gaze and physiology files are not yet extracted.
- `scoring.py`: converts scalar anchor values into `Desired`, `Adequate`, `Unacceptable`, or `Missing`.

Phase 1 active evidence follows `bn_design_v0.md`:

- `O1.T`, `O1.D`, `O1.H`
- `O2`
- `O5`
- `O8`
- `H1`
- `H4`

Because current CSV only contains `X(t)` and `U(t)`, the first executable version should compute the supported objective anchors and mark H1/H4 as missing evidence. Missing evidence must not crash inference.

### `bn`

Owns graph structure, CPT handling, and inference.

- `graph.py`: loads nodes and edges from `bn_structure.yaml`; exports graph JSON for a future frontend.
- `cpt.py`: loads, validates, updates, and saves CPT tables.
- `inference.py`: computes posterior distributions from scored evidence.

The BN is preliminary and must remain editable. The backend should not hard-code the final graph in Python. YAML configuration is the source of truth for the first implementation.

### `pipeline`

Owns the end-to-end computation.

- `evidence_builder.py`: maps loaded sessions to anchor values and evidence states.
- `run_session.py`: executes one session from input files to outputs.
- `result_builder.py`: formats competency posteriors, confidence, evidence trace, missing-evidence report, and weak-skill diagnosis.

### `app_bridge`

Owns the future desktop integration boundary.

- `commands.py`: command functions such as `inspect_inputs`, `load_graph`, `update_cpt`, `run_session`, and `export_result`.
- `sidecar_protocol.py`: JSON request/response schema for a Windows app to call the backend process.

The initial bridge can be CLI/JSON based. The frontend can later spawn the backend executable and send commands through process arguments, files, or standard input/output.

### `config`

Stores editable model configuration.

- `anchors.yaml`: anchor definitions, thresholds, modality requirements, and phase relevance.
- `bn_structure.yaml`: node IDs, labels, node types, layers, states, and directed edges.
- `cpt_defaults.yaml`: default CPTs used when no user-edited project file exists.

Future frontend edits should write to a project-specific runtime copy of these files, not overwrite the packaged defaults.

## Data Flow

1. User selects session data in the future Windows app.
2. App launches backend sidecar and calls `run_session`.
3. Backend loads available streams into a session object.
4. Modality registry marks `X(t)` and `U(t)` present; `I(t)`, `G(t)`, and `P(t)` may be missing initially.
5. Anchor extractors compute available deterministic anchors.
6. Scoring converts anchor values to evidence states.
7. BN inference combines evidence and missing-evidence rules.
8. Backend returns:
   - four competency posterior distributions,
   - confidence or evidence coverage,
   - evidence trace by anchor,
   - missing modality report,
   - weak-skill diagnosis.

## Frontend-Facing Backend Commands

These commands should exist even before the frontend is built:

- `inspect_backend`: version, config paths, supported commands.
- `inspect_inputs`: supported modalities and required file types.
- `load_graph`: BN nodes, edges, layers, node labels, states.
- `get_node`: one node's metadata and CPT if applicable.
- `update_cpt`: validate and update one node CPT.
- `run_session`: run a session from provided file paths.
- `export_result`: save output JSON and optional summary files.

## Error Handling

Errors should be structured, not printed as loose text.

- Missing file: return a typed file error.
- Unsupported CSV columns: return the missing/extra column list.
- Missing modality: mark evidence as missing and continue when allowed.
- Invalid CPT: reject update with the exact node ID and probability-sum issue.
- Inference failure: return graph/CPT diagnostics and no false competency result.

## Testing Strategy

Use test-first development for the core.

Initial tests:

- `test_csv_loader.py`: loads the current CSV sample, checks row count, time range, key columns, and modality presence.
- `test_anchor_scoring.py`: verifies threshold mapping to Desired/Adequate/Unacceptable/Missing.
- `test_bn_graph.py`: loads graph config, verifies node IDs, directed edges, and acyclic structure.

Later tests:

- CPT validation.
- Missing evidence behavior.
- End-to-end run result schema.
- Round-trip CPT update and save.

## First Implementation Slice

The first coding slice should create only the minimum useful backend:

1. Project scaffold with `uv`, `pyproject.toml`, and `src/` package.
2. YAML configs for Phase 1 graph and anchor metadata.
3. CSV loader for the current simulator file.
4. Session schema and modality registry.
5. Basic objective anchor/evidence placeholder functions.
6. BN graph loader and JSON exporter.
7. CLI command to inspect graph and load the sample CSV.
8. Tests proving the loader and graph config work.

No Windows UI work belongs in this slice.

## Design Decisions

- Backend is a Python package first, not a notebook or loose script.
- Runtime adapter is command/sidecar ready, not HTTP-first.
- BN graph and CPTs live in editable config files.
- Missing modalities are first-class states.
- Phase 1 focuses on real CSV-supported `X(t)` and `U(t)` while preserving interfaces for `I(t)`, `G(t)`, and `P(t)`.
- The 18-vs-19 anchor mismatch is not silently resolved in code; configs should document the current active subset and full-spec ambiguity.

## Open Questions For Later

- Exact phase segmentation for Translation, Deceleration, and Hover stabilization in the current CSV.
- Exact O1 envelope geometry and thresholds in simulator coordinates.
- Exact W_min derivation for O5/O8.
- Whether to implement inference with a lightweight internal discrete BN first or add an external BN library once graph/CPT requirements stabilize.
- Runtime bridge transport for the Windows app: command files, stdin/stdout JSON, named pipes, or local HTTP.
