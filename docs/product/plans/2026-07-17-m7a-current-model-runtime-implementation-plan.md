# M7A Current Model Runtime Implementation Plan

> **For agentic workers:** Execute INLINE, one task at a time. Do not spawn subagents. Steps use checkbox (`- [ ]`) syntax so execution can resume safely after interruption. Use focused platform tests; do not add scientific goldens for starter Evidence or CPT values.

**Goal:** Implement the canonical current-node/task-activation backend required by the M7 expert designer while preserving all M5/M6 immutable records and historical run replay.

**Architecture:** Add a current `ModelNode`/`TaskScheme` domain beside the legacy component-version workspace. Persist current objects and append-only change events in SQLite schema v2; derive graph edges and activation closure from complete node definitions; materialize technically valid current graphs into deterministic hidden legacy execution components for the existing Evidence/BN pipeline; freeze the full current graph in a new immutable run snapshot; expose additive `model.*` JSON-RPC methods. Old publish APIs remain compatibility-only.

**Tech Stack:** Python 3.11, Pydantic 2, SQLite, existing EvidenceRecipe/operator engine, finite-discrete BN runtime, JSON-RPC 2.0 over JSONL stdio, pytest, Ruff, ty, uv.

---

| Field | Value |
|---|---|
| Milestone | M7A |
| Date | 2026-07-17 |
| Status | Ready for INLINE execution |
| Parent roadmap | [M7 Implementation Roadmap](2026-07-17-m7-winui-expert-designer-implementation-roadmap.md) |
| Authoritative design | [M7 Design](../specs/2026-07-17-m7-winui-expert-designer-and-task-activation-workspace-design.md) |
| Decisions | D-047–D-053 |
| Compatibility baseline | M4R EvidenceRecipe/operator, M5 BN inference, M6 project/SQLite/run/sidecar |
| Completion boundary | Backend and sidecar only; WinUI is M7B |

## 0. Execution rules

1. Work on the existing `main` worktree and preserve unrelated user changes.
2. Execute tasks in order. Commit after each task or after the explicitly grouped substeps.
3. Prefer a small failing test before a new invariant when that test is cheap and stable. Do not build ceremony around trivial wiring.
4. Every write path must use the existing idempotency/audit transaction boundary and optimistic expected revision.
5. A warning about provisional scientific content never blocks save. Only structural inability to execute an active graph blocks preview/run.
6. Do not remove legacy tables, component records, APIs, schemas or tests.
7. Do not add task names, O/H IDs or fixed counts to generic loaders and services.
8. Run focused tests after each task. Run the full gate only in Task 12.

Common commands from the repository root:

```powershell
& .\.tools\uv\uv.exe run pytest tests/model_workspace -q
& .\.tools\uv\uv.exe run ruff check src/pilot_assessment tests/model_workspace
& .\.tools\uv\uv.exe run ruff format --check src/pilot_assessment tests/model_workspace
```

## 1. Frozen domain choices

### 1.1 Current node identity

`node_id` identifies one complete current functional definition. `semantic_revision` supports optimistic concurrency, history and autosave; it is not a task-selectable business version. If an expert needs different parents, states, CPT, recipe or meaning, copy/create a different `node_id`.

The new strict DTO family is defined in `contracts/model_workspace.py`:

- `ModelNodeKind`: `raw_input | evidence | bn`;
- `ModelNodeLifecycle`: `active | archived`;
- `RawInputFamily`: `x | u | i | g | p`;
- `BilingualText` and bilingual node/scheme identity fields;
- `NodeLayout` for global presentation coordinates, excluded from semantic hash;
- `RawInputNodeDefinition` containing an exact `SourceDescriptor` and display/resource family metadata;
- `EvidenceNodeDefinition` containing `EvidenceRecipe`, observation states/mapping, fixed probabilistic parent IDs, node CPT/CPD, attribution/provenance and help metadata;
- `BnNodeDefinition` containing role, states, fixed probabilistic parent IDs, node CPT/CPD, reporting/provenance and help metadata;
- discriminated `ModelNode` with one definition matching `node_kind`;
- `TaskScheme` with explicit activation, computed closure, outputs, task/reference bindings, layout overrides, revisions, technical status and lineage;
- `ModelGraphSnapshot`, `CanonicalModelDiff`, `DeactivationImpact`, `ModelChangeEvent` and typed mutation responses.

### 1.2 Edge ownership

- data/extraction edges are projected from EvidenceRecipe input bindings to Raw Input nodes;
- probabilistic edges are projected from the child Evidence/BN node's fixed parent IDs;
- `TaskScheme` never stores alternate parents or independent edges;
- add/remove/reorder operations update the child definition and its CPT/recipe atomically.

### 1.3 Run compatibility

Do not modify `RunSnapshot` v0.1 bytes or meaning. Add:

- `CurrentModelRunPreflightReport` v0.1;
- `CurrentModelRunSnapshot` v0.1, embedding the exact current scheme, active nodes, hashes, operator/runtime identities and a deterministic legacy `execution_snapshot`;
- `AssessmentRunV2` v0.2, whose snapshot is `CurrentModelRunSnapshot`;
- repository parsing that reads both legacy `AssessmentRun`/`RunSnapshot` and current `AssessmentRunV2`/`CurrentModelRunSnapshot`.

The existing pipeline unwraps the immutable `execution_snapshot`; the full current definitions remain the canonical historical record visible to M7.

## Task 1: Add current model contracts and JSON Schemas

**Files:**

- Create: `src/pilot_assessment/contracts/model_workspace.py`
- Modify: `src/pilot_assessment/contracts/run.py`
- Modify: `src/pilot_assessment/contracts/__init__.py`
- Modify: `src/pilot_assessment/schemas/export.py`
- Create: `tests/contracts/test_model_workspace.py`
- Modify: `tests/contracts/test_run_contracts.py`
- Modify: `tests/schemas/test_schema_export.py`
- Generate: `schemas/model-node-0.1.0.schema.json`
- Generate: `schemas/task-scheme-0.1.0.schema.json`
- Generate: `schemas/model-graph-snapshot-0.1.0.schema.json`
- Generate: `schemas/model-change-event-0.1.0.schema.json`
- Generate: `schemas/current-model-run-preflight-report-0.1.0.schema.json`
- Generate: `schemas/current-model-run-snapshot-0.1.0.schema.json`
- Generate: matching files under `src/pilot_assessment/schema_resources/`

- [ ] Write strict contract tests for node-kind/definition discrimination, unique parent/state IDs, frozen mappings, bilingual non-empty fallback, UTC timestamps, finite CPT values, stable IDs and SHA-256 fields.
- [ ] Test that an Evidence node cannot use Evidence or BN as a data source and cannot use Raw Input as a probabilistic parent.
- [ ] Test that a BN node cannot contain an EvidenceRecipe and a Raw Input node cannot contain a CPT.
- [ ] Test `TaskScheme` explicit/closure/output invariants, separate semantic/layout revisions and canonical ordering.
- [ ] Add current preflight/snapshot/run contracts without changing the behavior of legacy v0.1 models.
- [ ] Add `_M7_SCHEMA_MODELS` to the schema exporter and generate byte-identical root/package schemas.
- [ ] Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/contracts/test_model_workspace.py tests/contracts/test_run_contracts.py tests/schemas/test_schema_export.py -q
& .\.tools\uv\uv.exe run python -m pilot_assessment.schemas.export
git diff --exit-code -- schemas src/pilot_assessment/schema_resources
```

Expected: focused tests pass; schema regeneration leaves no tracked drift after generated files are staged.

- [ ] Commit:

```powershell
git add src/pilot_assessment/contracts src/pilot_assessment/schemas/export.py schemas src/pilot_assessment/schema_resources tests/contracts tests/schemas/test_schema_export.py
git commit -m "feat: add M7 current model contracts"
```

## Task 2: Implement graph projection, hashing and technical validation

**Files:**

- Create: `src/pilot_assessment/model_workspace/__init__.py`
- Create: `src/pilot_assessment/model_workspace/graph.py`
- Create: `src/pilot_assessment/model_workspace/hashing.py`
- Create: `src/pilot_assessment/model_workspace/validation.py`
- Create: `tests/model_workspace/__init__.py`
- Create: `tests/model_workspace/support.py`
- Create: `tests/model_workspace/test_graph.py`
- Create: `tests/model_workspace/test_validation.py`

- [ ] Build tiny reusable Raw/Evidence/BN fixtures with no O/H-specific branching.
- [ ] Project typed extraction/probabilistic edges from node definitions and reject dangling IDs, wrong edge kinds, duplicate axes and probabilistic cycles.
- [ ] Compute deterministic ancestors, descendants, explicit activation closure and active edge sets using canonical node-ID ordering.
- [ ] Keep Evidence extraction dependencies separate from probabilistic dependencies in DTOs and diagnostics.
- [ ] Compute a semantic hash that excludes layout, timestamps, revision counters and transient technical status; compute a separate layout hash.
- [ ] Return technical diagnostics as errors or warnings. Provisional descriptions, thresholds and CPT provenance produce warnings at most; missing operators, impossible CPT shapes, cycles and unavailable required source providers block run.
- [ ] Test a 7-node graph for closure, descendants, active/inactive edge projection and stable hashes.
- [ ] Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/model_workspace/test_graph.py tests/model_workspace/test_validation.py -q
```

Expected: graph rules pass without loading the Hover starter or a session dataset.

- [ ] Commit:

```powershell
git add src/pilot_assessment/model_workspace tests/model_workspace
git commit -m "feat: add current model graph rules"
```

## Task 3: Add additive SQLite schema v2 and repositories

**Files:**

- Modify: `src/pilot_assessment/persistence/migrations.py`
- Create: `src/pilot_assessment/persistence/model_workspace_repository.py`
- Create: `tests/persistence/test_model_workspace_repository.py`
- Modify: `tests/persistence/test_project_database.py`
- Modify: `tests/persistence/test_project_lifecycle.py`

SQLite migration v2 must add, without deleting v1 tables:

- `model_nodes`: current canonical JSON, lifecycle, semantic/layout revisions, semantic/layout hashes, technical status, head/redo event IDs and timestamps;
- `task_schemes`: equivalent current scheme head fields;
- `model_change_events`: append-only before/after canonical JSON, canonical diff, predecessor event, revisions, actor, transaction and timestamp;
- `model_starter_mappings`: deterministic legacy-record-to-current-node/scheme mappings and seed identity;
- `model_execution_materializations`: current graph hash to immutable legacy execution scheme mapping;
- `model_run_preflights`: current-model preflight JSON and exact legacy execution preflight reference;
- `model_run_links`: run ID to current preflight/snapshot identity.

- [ ] Set `LATEST_SCHEMA_VERSION = 2` and write v2 DDL with foreign keys and query indexes.
- [ ] Prove a fresh project applies v1 then v2 and an existing v1 project upgrades once without altering legacy rows.
- [ ] Implement repository create/get/list/update/archive methods with `expected_semantic_revision` or `expected_layout_revision` and optional `join_existing=True` transactions.
- [ ] On every successful mutation, append one immutable `model_change_events` row and advance the current head; revisions remain monotonic even when undo restores old content.
- [ ] Implement undo/redo as head navigation with an auditable cursor event. A new edit after undo clears the redo pointer but leaves the old branch in the journal.
- [ ] Ensure shared SQLite transactions can include repository updates, idempotency response and audit event.
- [ ] Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/persistence/test_project_database.py tests/persistence/test_project_lifecycle.py tests/persistence/test_model_workspace_repository.py -q
```

Expected: fresh/open/upgrade/reopen tests pass and no v1 record changes.

- [ ] Commit:

```powershell
git add src/pilot_assessment/persistence tests/persistence
git commit -m "feat: persist M7 current model workspace"
```

## Task 4: Implement current node lifecycle service

**Files:**

- Create: `src/pilot_assessment/model_workspace/service.py`
- Create: `tests/model_workspace/test_node_service.py`
- Modify: `src/pilot_assessment/runtime/application.py`
- Modify: `tests/runtime/test_application.py`

- [ ] Compose one `CurrentModelWorkspaceService` per open managed project using the v2 repository, graph validator, operator registry and source catalog.
- [ ] Implement node list/get/create/update/archive/usage-list/history/undo/redo.
- [ ] Require transaction ID, actor and expected semantic revision for semantic writes; require expected layout revision for global-layout-only writes.
- [ ] Return the canonical saved node, affected scheme IDs, new revisions, technical status and canonical diff from every mutation.
- [ ] Allow saving structurally incomplete inactive nodes with explicit diagnostics. Prevent a physically archived node from remaining in any current active closure.
- [ ] Updating a shared node must recompute technical status for every scheme that uses it, without cloning or silently forking the node.
- [ ] Keep scientific warnings non-blocking and do not run scientific pytest/goldens per edit.
- [ ] Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/model_workspace/test_node_service.py tests/runtime/test_application.py -q
```

Expected: node state persists across project reopen and revision conflicts return typed current state.

- [ ] Commit:

```powershell
git add src/pilot_assessment/model_workspace/service.py src/pilot_assessment/runtime/application.py tests/model_workspace/test_node_service.py tests/runtime/test_application.py
git commit -m "feat: add current model node service"
```

## Task 5: Implement task scheme lifecycle and scheme copy

**Files:**

- Modify: `src/pilot_assessment/model_workspace/service.py`
- Create: `tests/model_workspace/test_scheme_service.py`

- [ ] Implement scheme list/get/create/update metadata/archive/history/undo/redo.
- [ ] Implement scheme copy as a new parallel `scheme_id` that shares node IDs and copies explicit activation, outputs, task/reference bindings, layout overrides, filters/group metadata and lineage.
- [ ] Make the copied scheme immediately editable and runnable; do not create Draft/Published status fields.
- [ ] Keep `semantic_revision` separate from `layout_revision`; switching the current front-end context is not a backend model mutation.
- [ ] Return a complete canonical graph snapshot after operations that affect the visible task graph.
- [ ] Verify copying one scheme does not copy any node and editing only its activation/layout does not affect the source scheme.
- [ ] Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/model_workspace/test_scheme_service.py -q
```

Expected: parallel schemes persist and share exact nodes until an expert explicitly copies a node.

- [ ] Commit:

```powershell
git add src/pilot_assessment/model_workspace/service.py tests/model_workspace/test_scheme_service.py
git commit -m "feat: add current task scheme service"
```

## Task 6: Implement activation closure and atomic deactivation impact

**Files:**

- Create: `src/pilot_assessment/model_workspace/activation.py`
- Modify: `src/pilot_assessment/model_workspace/service.py`
- Create: `tests/model_workspace/test_activation.py`

- [ ] Implement child activation by adding the target to `explicit_active_node_ids`, recursively computing all data/probabilistic ancestors, validating the closure and saving one scheme event.
- [ ] Return auto-enabled parent IDs and active edges in the canonical diff; do not require or expose a confirmation step.
- [ ] Implement deactivation preview returning recursively impacted active downstream nodes/edges plus an `impact_hash` bound to the scheme revision and graph hashes.
- [ ] Implement confirmed deactivation requiring expected scheme revision and exact `impact_hash`. In one transaction, remove the target and affected descendants from explicit activation, recompute closure and either save everything or nothing.
- [ ] Treat Cancel as a client action that sends no mutation.
- [ ] Recompute closure after child deactivation and retain ancestors still explicit or required by another active child.
- [ ] Prove operations affect the current scheme only, even when another scheme uses the same nodes.
- [ ] Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/model_workspace/test_activation.py -q
```

Expected: the 7-node fixture proves silent enable closure, impact-hash stale protection, atomic cascade and task isolation.

- [ ] Commit:

```powershell
git add src/pilot_assessment/model_workspace/activation.py src/pilot_assessment/model_workspace/service.py tests/model_workspace/test_activation.py
git commit -m "feat: add task activation and cascade semantics"
```

## Task 7: Implement node-only copy and graph batch operations

**Files:**

- Create: `src/pilot_assessment/model_workspace/operations.py`
- Modify: `src/pilot_assessment/model_workspace/service.py`
- Create: `tests/model_workspace/test_copy_and_batch.py`

- [ ] Implement node copy with a new opaque `node_id`, `copied_from_node_id`, copied bilingual metadata/recipe/states/CPT/help/global layout and unchanged fixed parent node IDs.
- [ ] For an Evidence copy, keep recipe-local operator and port IDs scoped to the copied recipe; update only project-global child/node identity fields.
- [ ] Update an embedded child CPT identity to the new node while preserving parent references and probabilities.
- [ ] Implement paste-to-current-scheme as one transaction: create copied node, explicitly activate it, compute parent closure and add a scheme layout override offset from the source node.
- [ ] Leave the source node active until the expert explicitly deactivates it; do not retarget old downstream children.
- [ ] Add `model.graph.batch.apply` for multi-select copy/layout/activation using one expected revision set and one canonical diff.
- [ ] Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/model_workspace/test_copy_and_batch.py -q
```

Expected: node-only copy creates one new node, zero parent copies and one atomic current-scheme update.

- [ ] Commit:

```powershell
git add src/pilot_assessment/model_workspace/operations.py src/pilot_assessment/model_workspace/service.py tests/model_workspace/test_copy_and_batch.py
git commit -m "feat: add current node and graph copy operations"
```

## Task 8: Implement typed edge, state and CPT atomic edits

**Files:**

- Create: `src/pilot_assessment/model_workspace/cpt.py`
- Modify: `src/pilot_assessment/model_workspace/operations.py`
- Modify: `src/pilot_assessment/model_workspace/service.py`
- Create: `tests/model_workspace/test_edge_cpt_operations.py`

- [ ] Reuse M5 CPT validation/materialization/migration helpers rather than creating a second probability engine.
- [ ] Implement probabilistic edge add/remove/reorder as child-node mutations that also migrate, materialize or explicitly mark the child CPT incomplete in the same transaction.
- [ ] Implement state replacement with required CPT migration/rebuild input or explicit incomplete outcome; never save mismatched axes as runnable.
- [ ] Implement extraction edge add/remove by changing the EvidenceRecipe source binding and validating required operator input ports; never save a standalone edge row.
- [ ] Implement CPT cell/batch update with strict finite values, exact shape/order and row-sum validation.
- [ ] If any migration/validation/write step fails, roll back node, scheme technical status, history event, idempotency result and audit event.
- [ ] Return regenerated editor axes/rows and canonical child definition for immediate UI reconciliation.
- [ ] Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/model_workspace/test_edge_cpt_operations.py tests/bayesian/test_cpt_migration.py tests/bayesian/test_cpt_validation.py -q
```

Expected: add/remove/state/CPT cases pass; an injected failure leaves canonical bytes and revisions unchanged.

- [ ] Commit:

```powershell
git add src/pilot_assessment/model_workspace tests/model_workspace/test_edge_cpt_operations.py
git commit -m "feat: make current node edges and CPT atomic"
```

## Task 9: Materialize the Hover starter into current complete nodes

**Files:**

- Create: `src/pilot_assessment/model_workspace/migration.py`
- Modify: `src/pilot_assessment/runtime/application.py`
- Create: `tests/model_workspace/test_hover_migration.py`
- Modify: `tests/runtime/test_application.py`

- [ ] Convert every exact starter `SourceDescriptor` into a Raw Input node and classify it under X/U/I/G/P plus typed task/reference resources.
- [ ] Combine each starter Evidence concept/version/binding/CPT/recipe into one complete Evidence node.
- [ ] Combine each starter BN concept/version/CPT into one complete BN node.
- [ ] Create one Base Scheme from the existing Hover scheme activation/output/task/reference/layout data.
- [ ] Use deterministic IDs derived from canonical source content, such as `model-node.{kind}.{hash_prefix}` and `task-scheme.{hash_prefix}`; never derive generic behavior from Hover names.
- [ ] Persist exact old-record-to-current-node mappings and a seed marker. Reopening the project must not duplicate or mutate the current starter.
- [ ] If old records contain functionally different parallel versions, materialize separate node IDs; retain revision-only historical variants in the legacy archive/replay layer.
- [ ] Assert migrated counts from the package as observed facts while keeping the generic service count-free.
- [ ] Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/model_workspace/test_hover_migration.py tests/runtime/test_application.py tests/model_library/test_hover_starter_package.py -q
```

Expected: migration is deterministic/idempotent and old starter hashes remain unchanged.

- [ ] Commit:

```powershell
git add src/pilot_assessment/model_workspace/migration.py src/pilot_assessment/runtime/application.py tests/model_workspace/test_hover_migration.py tests/runtime/test_application.py
git commit -m "feat: migrate Hover starter to current model nodes"
```

## Task 10: Bridge current preview, preflight and immutable run snapshots

**Files:**

- Create: `src/pilot_assessment/model_workspace/execution.py`
- Create: `src/pilot_assessment/runtime/current_preflight.py`
- Modify: `src/pilot_assessment/runtime/repository.py`
- Modify: `src/pilot_assessment/runtime/pipeline.py`
- Modify: `src/pilot_assessment/runtime/application.py`
- Create: `tests/runtime/test_current_preflight.py`
- Create: `tests/runtime/test_current_run_snapshot.py`
- Modify: `tests/runtime/test_pipeline.py`
- Modify: `tests/runtime/test_run_repository.py`

- [ ] Deterministically materialize a technically executable current active closure into hidden immutable legacy component/scheme records keyed by current graph content hash.
- [ ] Tag/store the materialization as an internal execution compatibility asset; do not expose it as a task-specific version picker to M7.
- [ ] Reuse existing EvidenceRecipe/operator/source/CPT/BN logic and produce the legacy `RunPreflightReport`/`RunSnapshot` required by the current pipeline.
- [ ] Build `CurrentModelRunPreflightReport` from exact session revision, scheme revision, active nodes/hashes, technical diagnostics and execution preflight reference.
- [ ] Build `CurrentModelRunSnapshot` with complete frozen current scheme/node JSON, exact operators/runtime identities, current-model hash and embedded legacy execution snapshot.
- [ ] In run start, use one idempotent transaction to verify expected scheme/node revisions, freeze the snapshot, persist the current preflight link and create the queued run before enqueueing work.
- [ ] Adapt repository/pipeline parsing so legacy v0.1 runs and current v0.2 runs coexist; the pipeline unwraps the immutable execution snapshot without consulting later current state.
- [ ] Add read-only node/scheme preview that freezes an ephemeral current snapshot and never mutates model state.
- [ ] Prove editing a shared node after one completed run changes a future snapshot but does not change the first snapshot/result replay.
- [ ] Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/runtime/test_current_preflight.py tests/runtime/test_current_run_snapshot.py tests/runtime/test_pipeline.py tests/runtime/test_run_repository.py tests/runtime/test_preflight.py -q
```

Expected: current and legacy runs both execute/reopen; old snapshots retain exact hashes.

- [ ] Commit:

```powershell
git add src/pilot_assessment/model_workspace/execution.py src/pilot_assessment/runtime src/pilot_assessment/contracts/run.py tests/runtime
git commit -m "feat: run immutable snapshots from current schemes"
```

## Task 11: Expose additive current-workspace JSON-RPC methods

**Files:**

- Modify: `src/pilot_assessment/sidecar/methods.py`
- Modify: `src/pilot_assessment/sidecar/dispatcher.py`
- Modify: `src/pilot_assessment/sidecar/errors.py`
- Modify: `tests/sidecar/test_dispatcher.py`
- Modify: `tests/sidecar/test_methods.py`
- Modify: `tests/sidecar/test_server_subprocess.py`

Add the normal M7 method family:

```text
model.node.list / get / create / copy / update / archive
model.node.usage.list / history.list / undo / redo
model.scheme.list / get / create / copy / update / archive
model.scheme.activate / deactivation.preview / deactivate
model.scheme.history.list / undo / redo
model.graph.get / batch.apply
model.edge.add / remove
model.layout.update
model.cpt.validate / materialize / update
model.preview.node / scheme
model.run.preflight / start
```

- [ ] Add capability `model.current-workspace.v1`; keep JSON-RPC envelope/protocol version 1.0 because the methods are additive.
- [ ] Classify `component.*`, `scheme.version.*`, `scheme.draft.*` and old publish/run entry points as compatibility/migration capabilities. Do not remove them.
- [ ] Route every current write through the existing idempotency/audit wrapper using transaction ID, actor and expected revision.
- [ ] Add stable error codes and structured data for node/scheme not found, revision conflict, stale deactivation impact, invalid dependency, CPT mismatch, incomplete active closure and unsupported operator.
- [ ] Return canonical mutation responses, not a front-end echo of submitted parameters.
- [ ] Keep stdout protocol-only and large artifacts/session arrays out of JSON; return IDs/references.
- [ ] Prove same-transaction retry returns the same response, mismatched retry is rejected and an actual subprocess supports hello → project open → graph get → edit → current preflight.
- [ ] Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/sidecar/test_dispatcher.py tests/sidecar/test_methods.py tests/sidecar/test_server_subprocess.py -q
```

Expected: current methods and compatibility methods coexist; subprocess stderr contains logs only and stdout frames parse as JSON-RPC.

- [ ] Commit:

```powershell
git add src/pilot_assessment/sidecar tests/sidecar
git commit -m "feat: expose M7 current model sidecar API"
```

## Task 12: Close the M7A lightweight vertical slice and completion gate

**Files:**

- Create: `tests/integration/test_m7a_current_model_workflow.py`
- Modify: `docs/product/11_IMPLEMENTATION_STATUS.md`
- Modify: `docs/product/README.md`
- Modify: `docs/product/plans/2026-07-17-m7a-current-model-runtime-implementation-plan.md`
- Modify: `docs/product/plans/2026-07-17-m7-winui-expert-designer-implementation-roadmap.md`

The integration fixture must remain small: one managed micro session, at most two Evidence nodes, two BN nodes, two schemes and no generated image sequence beyond what the existing smallest fixture already requires.

- [ ] Create/open a project and verify deterministic Base Scheme migration.
- [ ] Copy the Base Scheme; copy one node into the new scheme; rename/edit it; keep original fixed parents.
- [ ] Enable a child and verify silent closure. Preview then confirm parent deactivation and verify only the copied scheme cascades.
- [ ] Save an Evidence parameter and one CPT edit through the sidecar; close/reopen the project and verify canonical state.
- [ ] Run current preflight/start; wait for completion; read Evidence/posterior/trace artifacts.
- [ ] Modify the shared node after completion and prove the old run snapshot/result is unchanged while a new preflight hash changes.
- [ ] Reopen one legacy published-scheme run fixture and prove v0.1 replay still works.
- [ ] Run the focused regression set:

```powershell
& .\.tools\uv\uv.exe run pytest tests/model_workspace tests/persistence/test_model_workspace_repository.py tests/runtime/test_current_preflight.py tests/runtime/test_current_run_snapshot.py tests/sidecar tests/integration/test_m7a_current_model_workflow.py -q
& .\.tools\uv\uv.exe run pytest tests/evidence tests/model_library tests/schemes tests/bayesian tests/integration/test_m5_lightweight_workflow.py tests/integration/test_m6_managed_assessment.py -q
```

- [ ] Run the repository completion gate:

```powershell
& .\.tools\uv\uv.exe run pytest -q
& .\.tools\uv\uv.exe run python -m pilot_assessment.schemas.export
git diff --exit-code -- schemas src/pilot_assessment/schema_resources
& .\.tools\uv\uv.exe run ruff check .
& .\.tools\uv\uv.exe run ruff format --check .
& .\.tools\uv\uv.exe run ty check src
& .\.tools\uv\uv.exe build
```

Expected: all gates pass. Then install the new wheel in a repository-external temporary directory and run import, schema-resource read, project create/open, sidecar hello, current graph read and clean shutdown smoke.

- [ ] Update status documents with exact commands/counts and explicitly state: M7A engineering verified; M7B WinUI and M8 packaging not implemented; scientific validity not established.
- [ ] Record actual task commit hashes in this plan.
- [ ] Commit:

```powershell
git add tests/integration/test_m7a_current_model_workflow.py docs/product
git commit -m "test: close M7A current model runtime"
```

## 2. Planned commit ledger

| Task | Planned commit | Actual commit |
|---:|---|---|
| 1 | `feat: add M7 current model contracts` | Not executed |
| 2 | `feat: add current model graph rules` | Not executed |
| 3 | `feat: persist M7 current model workspace` | Not executed |
| 4 | `feat: add current model node service` | Not executed |
| 5 | `feat: add current task scheme service` | Not executed |
| 6 | `feat: add task activation and cascade semantics` | Not executed |
| 7 | `feat: add current node and graph copy operations` | Not executed |
| 8 | `feat: make current node edges and CPT atomic` | Not executed |
| 9 | `feat: migrate Hover starter to current model nodes` | Not executed |
| 10 | `feat: run immutable snapshots from current schemes` | Not executed |
| 11 | `feat: expose M7 current model sidecar API` | Not executed |
| 12 | `test: close M7A current model runtime` | Not executed |

## 3. M7A completion definition

M7A is complete only after Task 12 records fresh evidence. Creating these plan files, adding contracts without persistence, or passing only focused tests does not complete M7A. Until then the accurate project status remains:

- M1–M3, M4R, M5 and M6: engineering verified;
- M7 design and plan: written;
- M7A current-model runtime: not yet implemented or partially implemented according to the ledger;
- M7B WinUI: not implemented;
- M8 packaging/handoff: not implemented;
- starter scientific validity: not established.
