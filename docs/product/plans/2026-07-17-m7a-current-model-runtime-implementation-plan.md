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
| Status | Engineering verified; M7B WinUI remains pending |
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
- Generate: `schemas/assessment-run-0.2.0.schema.json`
- Generate: matching files under `src/pilot_assessment/schema_resources/`

- [x] Write strict contract tests for node-kind/definition discrimination, unique parent/state IDs, frozen mappings, bilingual non-empty fallback, UTC timestamps, finite CPT values, stable IDs and SHA-256 fields.
- [x] Test that an Evidence node cannot use Evidence or BN as a data source and cannot use Raw Input as a probabilistic parent.
- [x] Test that a BN node cannot contain an EvidenceRecipe and a Raw Input node cannot contain a CPT.
- [x] Test `TaskScheme` explicit/closure/output invariants, separate semantic/layout revisions and canonical ordering.
- [x] Add current preflight/snapshot/run contracts without changing the behavior of legacy v0.1 models.
- [x] Add `_M7_SCHEMA_MODELS` to the schema exporter and generate byte-identical root/package schemas.
- [x] Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/contracts/test_model_workspace.py tests/contracts/test_run_contracts.py tests/schemas/test_schema_export.py -q
& .\.tools\uv\uv.exe run python -m pilot_assessment.schemas.export
git diff --exit-code -- schemas src/pilot_assessment/schema_resources
```

Expected: focused tests pass; schema regeneration leaves no tracked drift after generated files are staged.

- [x] Commit:

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

- [x] Build tiny reusable Raw/Evidence/BN fixtures with no O/H-specific branching.
- [x] Project typed extraction/probabilistic edges from node definitions and reject dangling IDs, wrong edge kinds, duplicate axes and probabilistic cycles.
- [x] Compute deterministic ancestors, descendants, explicit activation closure and active edge sets using canonical node-ID ordering.
- [x] Keep Evidence extraction dependencies separate from probabilistic dependencies in DTOs and diagnostics.
- [x] Compute a semantic hash that excludes layout, timestamps, revision counters and transient technical status; compute a separate layout hash.
- [x] Return technical diagnostics as errors or warnings. Provisional descriptions, thresholds and CPT provenance produce warnings at most; missing operators, impossible CPT shapes, cycles and unavailable required source providers block run.
- [x] Test a 7-node graph for closure, descendants, active/inactive edge projection and stable hashes.
- [x] Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/model_workspace/test_graph.py tests/model_workspace/test_validation.py -q
```

Expected: graph rules pass without loading the Hover starter or a session dataset.

- [x] Commit:

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

- [x] Set `LATEST_SCHEMA_VERSION = 2` and write v2 DDL with foreign keys and query indexes.
- [x] Prove a fresh project applies v1 then v2 and an existing v1 project upgrades once without altering legacy rows.
- [x] Implement repository create/get/list/update/archive methods with `expected_semantic_revision` or `expected_layout_revision` and optional `join_existing=True` transactions.
- [x] On every successful mutation, append one immutable `model_change_events` row and advance the current head; revisions remain monotonic even when undo restores old content.
- [x] Implement undo/redo as head navigation with an auditable cursor event. A new edit after undo clears the redo pointer but leaves the old branch in the journal.
- [x] Ensure shared SQLite transactions can include repository updates, idempotency response and audit event.
- [x] Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/persistence/test_project_database.py tests/persistence/test_project_lifecycle.py tests/persistence/test_model_workspace_repository.py -q
```

Expected: fresh/open/upgrade/reopen tests pass and no v1 record changes.

- [x] Commit:

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

- [x] Compose one `CurrentModelWorkspaceService` per open managed project using the v2 repository, graph validator, operator registry and source catalog.
- [x] Implement node list/get/create/update/archive/usage-list/history/undo/redo.
- [x] Require transaction ID, actor and expected semantic revision for semantic writes; require expected layout revision for global-layout-only writes.
- [x] Return the canonical saved node, affected scheme IDs, new revisions, technical status and canonical diff from every mutation.
- [x] Allow saving structurally incomplete inactive nodes with explicit diagnostics. Prevent a physically archived node from remaining in any current active closure.
- [x] Updating a shared node must recompute technical status for every scheme that uses it, without cloning or silently forking the node.
- [x] Keep scientific warnings non-blocking and do not run scientific pytest/goldens per edit.
- [x] Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/model_workspace/test_node_service.py tests/runtime/test_application.py -q
```

Expected: node state persists across project reopen and revision conflicts return typed current state.

- [x] Commit:

```powershell
git add src/pilot_assessment/model_workspace/service.py src/pilot_assessment/runtime/application.py tests/model_workspace/test_node_service.py tests/runtime/test_application.py
git commit -m "feat: add current model node service"
```

## Task 5: Implement task scheme lifecycle and scheme copy

**Files:**

- Modify: `src/pilot_assessment/model_workspace/service.py`
- Create: `tests/model_workspace/test_scheme_service.py`

- [x] Implement scheme list/get/create/update metadata/archive/history/undo/redo.
- [x] Implement scheme copy as a new parallel `scheme_id` that shares node IDs and copies explicit activation, outputs, task/reference bindings, layout overrides, filters/group metadata and lineage.
- [x] Make the copied scheme immediately editable and runnable; do not create Draft/Published status fields.
- [x] Keep `semantic_revision` separate from `layout_revision`; switching the current front-end context is not a backend model mutation.
- [x] Return a complete canonical graph snapshot after operations that affect the visible task graph.
- [x] Verify copying one scheme does not copy any node and editing only its activation/layout does not affect the source scheme.
- [x] Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/model_workspace/test_scheme_service.py -q
```

Expected: parallel schemes persist and share exact nodes until an expert explicitly copies a node.

- [x] Commit:

```powershell
git add src/pilot_assessment/model_workspace/service.py tests/model_workspace/test_scheme_service.py
git commit -m "feat: add current task scheme service"
```

## Task 6: Implement activation closure and atomic deactivation impact

**Files:**

- Create: `src/pilot_assessment/model_workspace/activation.py`
- Modify: `src/pilot_assessment/model_workspace/service.py`
- Create: `tests/model_workspace/test_activation.py`

- [x] Implement child activation by adding the target to `explicit_active_node_ids`, recursively computing all data/probabilistic ancestors, validating the closure and saving one scheme event.
- [x] Return auto-enabled parent IDs and active edges in the canonical diff; do not require or expose a confirmation step.
- [x] Implement deactivation preview returning recursively impacted active downstream nodes/edges plus an `impact_hash` bound to the scheme revision and graph hashes.
- [x] Implement confirmed deactivation requiring expected scheme revision and exact `impact_hash`. In one transaction, remove the target and affected descendants from explicit activation, recompute closure and either save everything or nothing.
- [x] Treat Cancel as a client action that sends no mutation.
- [x] Recompute closure after child deactivation and retain ancestors still explicit or required by another active child.
- [x] Prove operations affect the current scheme only, even when another scheme uses the same nodes.
- [x] Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/model_workspace/test_activation.py -q
```

Expected: the 7-node fixture proves silent enable closure, impact-hash stale protection, atomic cascade and task isolation.

- [x] Commit:

```powershell
git add src/pilot_assessment/model_workspace/activation.py src/pilot_assessment/model_workspace/service.py tests/model_workspace/test_activation.py
git commit -m "feat: add task activation and cascade semantics"
```

## Task 7: Implement node-only copy and graph batch operations

**Files:**

- Create: `src/pilot_assessment/model_workspace/operations.py`
- Modify: `src/pilot_assessment/model_workspace/service.py`
- Create: `tests/model_workspace/test_copy_and_batch.py`

- [x] Implement node copy with a new opaque `node_id`, `copied_from_node_id`, copied bilingual metadata/recipe/states/CPT/help/global layout and unchanged fixed parent node IDs.
- [x] For an Evidence copy, keep recipe-local operator and port IDs scoped to the copied recipe; update only project-global child/node identity fields.
- [x] Update an embedded child CPT identity to the new node while preserving parent references and probabilities.
- [x] Implement paste-to-current-scheme as one transaction: create copied node, explicitly activate it, compute parent closure and add a scheme layout override offset from the source node.
- [x] Leave the source node active until the expert explicitly deactivates it; do not retarget old downstream children.
- [x] Add `model.graph.batch.apply` for multi-select copy/layout/activation using one expected revision set and one canonical diff.
- [x] Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/model_workspace/test_copy_and_batch.py -q
```

Expected: node-only copy creates one new node, zero parent copies and one atomic current-scheme update.

- [x] Commit:

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

- [x] Reuse M5 CPT validation/materialization/migration helpers rather than creating a second probability engine.
- [x] Implement probabilistic edge add/remove/reorder as child-node mutations that also migrate, materialize or explicitly mark the child CPT incomplete in the same transaction.
- [x] Implement state replacement with required CPT migration/rebuild input or explicit incomplete outcome; never save mismatched axes as runnable.
- [x] Implement extraction edge add/remove by changing the EvidenceRecipe source binding and validating required operator input ports; never save a standalone edge row.
- [x] Implement CPT cell/batch update with strict finite values, exact shape/order and row-sum validation.
- [x] At the domain boundary, roll back node, scheme technical status and history events together when migration, validation or persistence fails.
- [x] When Task 11 exposes these domain mutations, include their idempotency result and audit event in the same existing outer transaction; this protocol concern is deliberately not duplicated in Task 8.
- [x] Return regenerated editor axes/rows and canonical child definition for immediate UI reconciliation.
- [x] Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/model_workspace/test_edge_cpt_operations.py tests/bayesian/test_cpt_migration.py tests/bayesian/test_cpt_validation.py -q
```

Expected: add/remove/state/CPT cases pass; an injected failure leaves canonical bytes and revisions unchanged.

- [x] Commit:

```powershell
git add src/pilot_assessment/model_workspace tests/model_workspace/test_edge_cpt_operations.py
git commit -m "feat: make current node edges and CPT atomic"
```

## Task 9: Materialize the Hover starter into current complete nodes

**Files:**

- Create: `src/pilot_assessment/model_workspace/migration.py`
- Modify: `src/pilot_assessment/contracts/model_workspace.py`
- Modify: `src/pilot_assessment/persistence/migrations.py`
- Modify: `src/pilot_assessment/runtime/application.py`
- Modify: `src/pilot_assessment/runtime/__init__.py`
- Modify: `schemas/model-node-0.1.0.schema.json`
- Modify: `schemas/model-graph-snapshot-0.1.0.schema.json`
- Modify: `schemas/current-model-run-snapshot-0.1.0.schema.json`
- Modify: `schemas/assessment-run-0.2.0.schema.json`
- Modify: matching packaged copies under `src/pilot_assessment/schema_resources/`
- Create: `tests/model_workspace/test_hover_migration.py`
- Modify: `tests/runtime/test_application.py`
- Modify: `tests/persistence/test_project_database.py`
- Modify: `tests/persistence/test_project_lifecycle.py`

- [x] Convert every exact starter `SourceDescriptor` into a Raw Input node and classify physical streams under X/U/I/G/P/pilot-camera while keeping typed task/reference/session resources outside those physical families.
- [x] Combine each starter Evidence concept/version/binding/CPT/recipe into one complete Evidence node.
- [x] Combine each starter BN concept/version/CPT into one complete BN node.
- [x] Create one Base Scheme from the existing Hover scheme activation/output/task/reference/layout data.
- [x] Use deterministic IDs derived from canonical source content, such as `model-node.{kind}.{hash_prefix}` and `task-scheme.{hash_prefix}`; never derive generic behavior from Hover names.
- [x] Persist exact old-record-to-current-node mappings and a seed marker. Reopening the project verifies the mapping/object set without duplicating nodes or overwriting later expert edits.
- [x] Correct the mapping table to a many-to-many relation so one complete current node may combine several legacy records and one legacy concept may map to parallel current nodes.
- [x] If old records contain functionally different parallel versions, materialize separate node IDs; retain revision-only historical variants in the legacy archive/replay layer.
- [x] Assert migrated counts only as observed starter facts: 20 Raw Input + 18 Evidence + 15 BN = 53 nodes, one Base Scheme, 141 legacy mappings, 37 explicitly active nodes, 52 nodes in dependency closure and four outputs. The generic service remains count-free.
- [x] Keep pilot camera present as an independent Raw Input node but inactive/dim in the starter because the legacy starter scheme did not select it.
- [x] Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/model_workspace/test_hover_migration.py tests/runtime/test_application.py tests/model_library/test_hover_starter_package.py -q
```

Expected: migration is deterministic/idempotent and old starter hashes remain unchanged.

- [x] Commit:

```powershell
git add src/pilot_assessment/model_workspace/migration.py src/pilot_assessment/contracts/model_workspace.py src/pilot_assessment/persistence/migrations.py src/pilot_assessment/runtime/application.py src/pilot_assessment/runtime/__init__.py schemas src/pilot_assessment/schema_resources tests/model_workspace/test_hover_migration.py tests/runtime/test_application.py tests/persistence/test_project_database.py tests/persistence/test_project_lifecycle.py docs/product/plans/2026-07-17-m7a-current-model-runtime-implementation-plan.md
git commit -m "feat: migrate Hover starter to current model nodes"
```

## Task 10: Bridge current preview, preflight and immutable run snapshots

**Files:**

- Create: `src/pilot_assessment/model_workspace/execution.py`
- Create: `src/pilot_assessment/runtime/current_preflight.py`
- Modify: `src/pilot_assessment/model_workspace/__init__.py`
- Modify: `src/pilot_assessment/runtime/__init__.py`
- Modify: `src/pilot_assessment/runtime/repository.py`
- Modify: `src/pilot_assessment/runtime/pipeline.py`
- Modify: `src/pilot_assessment/runtime/coordinator.py`
- Modify: `src/pilot_assessment/runtime/application.py`
- Create: `tests/runtime/test_current_preflight.py`
- Create: `tests/runtime/test_current_run_snapshot.py`
- Modify: `tests/runtime/test_application.py`
- Modify: `tests/runtime/test_preflight.py`
- Verify unchanged compatibility coverage: `tests/runtime/test_pipeline.py`
- Verify unchanged compatibility coverage: `tests/runtime/test_run_repository.py`

- [x] Deterministically materialize a technically executable current active closure into hidden immutable legacy component/scheme records keyed by an exact semantic-graph/revision lock hash.
- [x] Tag/store the materialization under `compat.current.*` identities and `model_execution_materializations`; do not expose it as a task-specific version picker to M7.
- [x] Reuse existing EvidenceRecipe/operator/source/CPT/BN logic and produce the legacy `RunPreflightReport`/`RunSnapshot` required by the current pipeline.
- [x] Build `CurrentModelRunPreflightReport` from exact session revision, scheme revision, active nodes/hashes, technical diagnostics and execution preflight reference.
- [x] Build `CurrentModelRunSnapshot` with complete frozen current scheme/node JSON, exact operators/runtime identities, current-model hash and embedded legacy execution snapshot.
- [x] In run start, use one idempotent transaction to verify expected scheme/node revisions, freeze the snapshot, persist the current preflight link and create the queued run before enqueueing work. Exact retries return the existing run even after it progresses.
- [x] Adapt repository/coordinator/pipeline parsing so legacy v0.1 runs and current v0.2 runs coexist; the pipeline unwraps the immutable execution snapshot without consulting later current state.
- [x] Add read-only node-in-scheme and scheme preview that freezes an ephemeral current snapshot, creates no run row and never mutates model state.
- [x] Prove editing a shared node after one completed run changes a future snapshot but does not change the first snapshot/result replay, including after project reopen.
- [x] Preserve technical-only gating: starter scientific warnings remain visible but do not block `software_test` execution.
- [x] Make the legacy portability assertion check forbidden process-metadata keys rather than searching for the short decimal PID inside unrelated content hashes.
- [x] Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/runtime/test_current_preflight.py tests/runtime/test_current_run_snapshot.py tests/runtime/test_pipeline.py tests/runtime/test_run_repository.py tests/runtime/test_preflight.py -q
```

Expected: current and legacy runs both execute/reopen; old snapshots retain exact hashes.

- [x] Commit:

```powershell
git add src/pilot_assessment/model_workspace/execution.py src/pilot_assessment/model_workspace/__init__.py src/pilot_assessment/runtime tests/runtime/test_current_preflight.py tests/runtime/test_current_run_snapshot.py tests/runtime/test_application.py tests/runtime/test_preflight.py docs/product/plans/2026-07-17-m7a-current-model-runtime-implementation-plan.md
git commit -m "feat: run immutable snapshots from current schemes"
```

## Task 11: Expose additive current-workspace JSON-RPC methods

**Files:**

- Modify: `src/pilot_assessment/model_workspace/service.py`
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
model.node.states.replace
model.scheme.list / get / create / copy / update / archive
model.scheme.activate / deactivation.preview / deactivate
model.scheme.history.list / undo / redo
model.graph.get / batch.apply
model.edge.add / remove
model.edge.reorder
model.layout.update
model.cpt.validate / materialize / update
model.preview.node / scheme
model.run.preflight / start
```

- [x] Add capability `model.current-workspace.v1`; keep JSON-RPC envelope/protocol version 1.0 because the methods are additive.
- [x] Classify `component.*`, `scheme.version.*`, `scheme.draft.*` and old publish/run entry points as compatibility/migration capabilities. Do not remove them.
- [x] Route every current write through the existing idempotency/audit wrapper using transaction ID, actor and expected revision; current model repositories can now safely join that outer transaction.
- [x] Add stable error codes and structured data for node/scheme not found, revision conflict, stale deactivation impact, invalid dependency, CPT mismatch, incomplete active closure and unsupported operator.
- [x] Return canonical mutation responses, not a front-end echo of submitted parameters.
- [x] Keep stdout protocol-only and large artifacts/session arrays out of JSON; return IDs/references.
- [x] Expose atomic state replacement and probabilistic-parent reordering in addition to the planned method family, so the future BN editor does not fall back to unsafe generic writes.
- [x] Prove same-transaction retry returns the same response, mismatched retry is rejected and an actual subprocess supports hello → project open → graph get → edit → current preflight/start/result while the compatibility run still succeeds.
- [x] Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/sidecar/test_dispatcher.py tests/sidecar/test_methods.py tests/sidecar/test_server_subprocess.py -q
```

Expected: current methods and compatibility methods coexist; subprocess stderr contains logs only and stdout frames parse as JSON-RPC.

- [x] Commit:

```powershell
git add src/pilot_assessment/model_workspace/service.py src/pilot_assessment/sidecar tests/sidecar docs/product/plans/2026-07-17-m7a-current-model-runtime-implementation-plan.md
git commit -m "feat: expose M7 current model sidecar API"
```

## Task 12: Close the M7A lightweight vertical slice and completion gate

**Files:**

- Create: `tests/integration/test_m7a_current_model_workflow.py`
- Modify: `docs/product/11_IMPLEMENTATION_STATUS.md`
- Modify: `docs/product/README.md`
- Modify: `docs/product/plans/2026-07-17-m7a-current-model-runtime-implementation-plan.md`
- Modify: `docs/product/plans/2026-07-17-m7-winui-expert-designer-implementation-roadmap.md`

The deterministic Base migration necessarily creates the complete 53-node starter graph. The integration fixture nevertheless remains lightweight: it edits/copies one Evidence node, reduces the copied scheme's active execution closure to one Evidence plus two BN nodes, uses one managed micro session and two schemes, and creates no extra image sequence.

- [x] Create/open a project and verify deterministic Base Scheme migration.
- [x] Copy the Base Scheme; copy one node into the new scheme; rename/edit it; keep original fixed parents.
- [x] Enable a child and verify silent closure. Preview then confirm parent deactivation and verify only the copied scheme cascades.
- [x] Save an Evidence parameter and one CPT edit through the sidecar; close/reopen the project and verify canonical state.
- [x] Run current preflight/start; wait for completion; read Evidence/posterior/trace artifacts.
- [x] Modify the shared node after completion and prove the old run snapshot/result is unchanged while a new preflight hash changes.
- [x] Reopen one legacy published-scheme run fixture and prove v0.1 replay still works.
- [x] Run the focused regression set:

```powershell
& .\.tools\uv\uv.exe run pytest tests/model_workspace tests/persistence/test_model_workspace_repository.py tests/runtime/test_current_preflight.py tests/runtime/test_current_run_snapshot.py tests/sidecar tests/integration/test_m7a_current_model_workflow.py -q
& .\.tools\uv\uv.exe run pytest tests/evidence tests/model_library tests/schemes tests/bayesian tests/integration/test_m5_lightweight_workflow.py tests/integration/test_m6_managed_assessment.py -q
```

- [x] Run the repository completion gate:

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

Fresh Task 12 evidence: current-workspace/sidecar/integration focused gate `42 passed`; M4R/M5/M6 compatibility gate `151 passed`; full repository `1684 passed, 3 skipped`; 51 exported schemas showed zero drift; Ruff check and format check, `ty check src`, source/wheel build and repository-external wheel smoke all passed. The two symlink skips are host capability skips and the remaining skip is the optional repository-external captured-format sample. The wheel smoke imported the installed package, read a packaged M7 schema, negotiated the current-model capability, created/opened a project, read the 53-node graph and shut down cleanly.

The vertical slice also exposed and closed one compatibility-materialization defect: unchanged child definitions can compile to different legacy bytes after an upstream parent changes because remapped parent/version IDs change. Hidden compatibility IDs are now scoped to the full execution graph hash, so later graph edits create distinct immutable records while completed runs retain their original snapshots and results.

- [x] Update status documents with exact commands/counts and explicitly state: M7A engineering verified; M7B WinUI and M8 packaging not implemented; scientific validity not established.
- [ ] Record the Task 12 closing commit hash in this plan after the commit exists; Tasks 1–11 are recorded below.
- [ ] Commit:

```powershell
git add src/pilot_assessment/model_workspace/execution.py tests/integration/test_m7a_current_model_workflow.py docs/product
git commit -m "test: close M7A current model runtime"
```

## 2. Planned commit ledger

| Task | Planned commit | Actual commit |
|---:|---|---|
| 1 | `feat: add M7 current model contracts` | `8022e9c` |
| 2 | `feat: add current model graph rules` | `1a05e80` |
| 3 | `feat: persist M7 current model workspace` | `bca6495` |
| 4 | `feat: add current model node service` | `d4b6e44` |
| 5 | `feat: add current task scheme service` | `f907614` |
| 6 | `feat: add task activation and cascade semantics` | `32e6244` |
| 7 | `feat: add current node and graph copy operations` | `765ff4d` |
| 8 | `feat: make current node edges and CPT atomic` | `643489c` |
| 9 | `feat: migrate Hover starter to current model nodes` | `11a4d95` |
| 10 | `feat: run immutable snapshots from current schemes` | `09fa211` |
| 11 | `feat: expose M7 current model sidecar API` | `4da1d77` |
| 12 | `test: close M7A current model runtime` | Pending this closing commit |

## 3. M7A completion definition

Task 12 has recorded fresh completion evidence. The accurate project status is:

- M1–M3, M4R, M5, M6 and M7A: engineering verified;
- M7 design and both executable plans: written;
- M7A current-model runtime and additive sidecar surface: implemented and verified;
- M7B WinUI: not implemented;
- M8 packaging: not implemented;
- starter algorithms, thresholds and CPTs: not scientifically validated.
- M8 packaging/handoff: not implemented;
- starter scientific validity: not established.
