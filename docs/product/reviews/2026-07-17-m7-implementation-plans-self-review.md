# M7 Implementation Plans Self-Review

| Field | Value |
|---|---|
| Date | 2026-07-17 |
| Reviewed documents | M7 roadmap, M7A current-model runtime plan, M7B WinUI expert-designer plan |
| Review type | Product-semantics traceability, repository fit, compatibility, implementation order, verification weight and Windows feasibility |
| Result | Plans are internally consistent and ready for INLINE execution; M7 code has not been implemented by this documentation change |

## 1. User requirements traceability

| Confirmed requirement | Plan location | Result |
|---|---|---|
| Global library contains many complete Raw/Evidence/BN nodes | M7A Tasks 1–4; M7B Task 7 | Covered |
| Each visible node has one current complete definition | M7A §1.1 and Tasks 1/4 | Covered; revision is not a task version |
| Task schemes select nodes; active is bright and inactive is dim | M7A Tasks 5–6; M7B Tasks 6–8 | Covered |
| Same node may be shared by several tasks | M7A Tasks 4–5 | Covered; usage list and future-run impact are explicit |
| Different parents or calculation means a different node | M7A Tasks 1/7/8 | Covered; no scheme edge override |
| Enabling a child silently enables fixed parents | M7A Task 6; M7B Task 8 | Covered |
| Disabling a used parent shows Continue/Cancel | M7A Task 6; M7B Task 8 | Covered with revision-bound impact hash |
| Node copy keeps original fixed parents | M7A Task 7; M7B Task 8 | Covered |
| Scheme copy creates a parallel immediately editable task | M7A Task 5; M7B Task 6 | Covered |
| Front-end edit changes backend canonical computation | M7A Tasks 4–8/11; M7B Tasks 8/10–12 | Covered; no local fake graph/CPT |
| Multiple movable/resizable/maximizable node windows | M7B Task 9 | Covered through Window/AppWindow |
| Expert can inspect/edit recipe, parameters, states and CPT | M7B Tasks 10–11 | Covered with schema-driven forms |
| Immediate Chinese/English switching | M7B Task 13 | Covered without changing model identity |
| No Draft/Published/Apply/Publish normal workflow | Roadmap; M7A Tasks 5/10/11; M7B Tasks 6/14 | Covered |
| Every run freezes exact current state | M7A Task 10; M7B Task 14 | Covered with a new versioned snapshot |
| Final packaging and user-data exclusion wait for M8 | Roadmap; M7B Tasks 1/15 | Covered |

## 2. Repository-fit review

### 2.1 Reused foundations

The plans reuse rather than replace:

- M4R `EvidenceRecipe`, operator registry/compiler/executor and schema-driven parameters;
- M5 typed source descriptors, CPT validation/migration, finite-discrete inference and trace;
- M6 managed projects/sessions/artifacts, SQLite transactions, audit/idempotency, run repository/coordinator and JSON-RPC framing;
- the existing Hover starter package as migration input only.

The new code is additive under `model_workspace`, persistence migration v2, current preflight/execution and `model.*` RPC methods. This is a smaller and safer migration than rewriting M4R–M6.

### 2.2 Legacy compatibility

The plan does not delete or reinterpret old bytes:

- SQLite v1 tables and records remain;
- `RunSnapshot` v0.1 remains parseable;
- current runs use a separately versioned current-model snapshot containing an immutable legacy execution snapshot;
- current graphs are deterministically materialized into hidden immutable execution components for the existing pipeline;
- old component/scheme/publish RPC methods remain compatibility/migration methods;
- the M7 WinUI normal workflow consumes only the new current-workspace methods.

Conclusion: old run replay and the new free-to-modify editor can coexist without exposing legacy version/publish semantics to experts.

## 3. Canonical graph and transaction review

The plan preserves the complete-node invariant:

- extraction edges come only from an Evidence recipe's raw source bindings;
- probabilistic edges come only from the child node's fixed parents and CPT;
- a scheme owns activation/layout, not alternate edges or node definitions;
- edge/state/parent edits are child-node transactions that also migrate/rebuild CPT or mark the node incomplete;
- a failed edit rolls back canonical object, history, scheme status, idempotency response and audit event;
- enabling computes a parent closure in the backend;
- deactivation preview is revision/hash bound, so a stale dialog cannot remove a changed graph;
- shared-node edits recompute the technical status of all affected schemes for future runs.

No front-end-only operation can create a line that is absent from the backend calculation definition.

## 4. Run snapshot review

The most important compatibility choice is to add, not mutate, run contracts:

1. current preflight validates current node/scheme revisions and active closure;
2. deterministic materialization produces an immutable execution scheme usable by the verified M6 pipeline;
3. current run start freezes the full current scheme, active nodes, recipe/CPT definitions, operators and hashes;
4. the embedded legacy execution snapshot drives the existing pipeline;
5. the stored full current snapshot is the historical user-visible truth;
6. subsequent autosaves cannot change an old result.

This avoids the two unacceptable alternatives: running directly against mutable current rows, or forcing the expert to publish before every run.

## 5. WinUI feasibility review

### 5.1 Confirmed local constraint

The audit found a Windows SDK but no usable .NET SDK/Visual Studio/WinUI template. M7A is unaffected. M7B Task 1 explicitly stops for user authorization before invoking the bundled WinGet configuration because it changes the workstation and may enable Developer Mode/install Visual Studio workloads.

### 5.2 Platform choices

- unpackaged development mode supports command-line build and direct visible launch; M8 decides final packaging;
- AppWindow supports the required multiple top-level editor windows;
- ItemsRepeater plus a focused custom `VirtualizingLayout` addresses a large global node library without inventing an entire UI framework;
- a local typed clipboard implements same-project Ctrl+C/Ctrl+V without serializing canonical definitions into an untrusted shell command;
- `%LOCALAPPDATA%` stores only window/language/recent-project preferences, while project model state remains in managed SQLite;
- immediate language switching explicitly refreshes resources because changing the primary language override alone may not update already-loaded resources.

### 5.3 No duplicated scientific engine

M7B limits C# to typed transport, view state, form generation and intent. Recipe evaluation, CPT migration/validation, BN inference, activation closure and snapshot construction all remain backend calls. The only intentionally schema-dynamic values are operator parameters and diagnostic details.

## 6. Validation-weight review

The plans follow the user's lightweight requirement:

Required tests are platform invariants: contracts, persistence, revisions, closure, cascade, copy, CPT atomicity, snapshot/replay, framing, client state, localization, window registry, one tiny current-model execution and one visible-window launch.

They explicitly avoid:

- ten-thousand-row multimodal test expansion;
- four large synthetic performance categories;
- per-edit pytest/golden from the product;
- numerical claims that starter Evidence/CPT values are correct;
- packaging tests before M8.

The only 1,000-node input in M7B is an in-memory graph-projection performance fixture. It contains no session streams, invokes no Evidence/BN computation and is appropriate for verifying viewport virtualization.

## 7. Risks and controlled responses

| Risk | Control in plan | Blocking? |
|---|---|---|
| Current graph cannot map to legacy execution components | Deterministic materializer and focused current/legacy pipeline tests in M7A Task 10 | Blocks M7A gate if unresolved |
| Old project upgrades corrupt history | Additive SQLite v2, exact v1-row assertions and reopen tests | Blocks M7A gate if unresolved |
| Concurrent editor windows overwrite each other | Expected revision, canonical responses and Reload/Reapply flow | No silent overwrite allowed |
| Stale cascade dialog removes changed descendants | Scheme revision plus `impact_hash` | Stale request rejected |
| Large global graph becomes unreadable | active/all filters, search, viewport virtualization and minimap | Performance fixture in M7B Task 15 |
| Runtime language switch leaves stale labels | refreshable resource service and open-window notification tests | Blocks bilingual acceptance if unresolved |
| Machine setup is unexpectedly invasive | explicit authorization gate before WinGet configuration | M7B waits; M7A continues |
| Starter output is mistaken for validated assessment | persistent scientific-status banner and completion wording | Scientific validation remains separate |

## 8. Corrections made during self-review

1. Split M7 into ordered M7A/M7B plans so the UI cannot accidentally cement old draft/publish semantics.
2. Kept `RunSnapshot` v0.1 intact and introduced a separately versioned current snapshot plus deterministic execution compatibility layer.
3. Bound deactivation confirmation to both expected revision and impact hash.
4. Separated global node layout from scheme layout overrides and semantic hashes.
5. Required actual non-zero top-level window verification, not process/build success alone.
6. Added an explicit machine-mutation authorization gate for WinUI tool installation.
7. Chose a refreshable localization service instead of relying on `PrimaryLanguageOverride` alone.
8. Limited performance load to an in-memory graph projection rather than heavy multimodal sessions.

## 9. Final conclusion

The roadmap and both implementation plans preserve D-047–D-053, fit the existing M4R/M5/M6 codebase and define an executable, lightweight path to the requested expert-facing Windows product. Documentation is now ready for INLINE execution in this order:

1. M7A Tasks 1–12;
2. M7B toolchain authorization and Tasks 1–15;
3. M8 planning only after a visible M7 application passes its completion gate.

This review approves the plans as implementation-ready documents. It does not claim any M7 source code, WinUI window or scientific model has already been completed.
