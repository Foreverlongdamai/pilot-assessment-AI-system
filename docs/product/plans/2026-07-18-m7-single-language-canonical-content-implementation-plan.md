# M7 Single-Language Canonical Content Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate full Chinese/English application localization from expert-authored model content so current nodes, task schemes, Evidence/BN help text, and future expert edits store one canonical English value instead of bilingual pairs.

**Architecture:** Introduce additive current-contract versions with single `name`, `short_name`, `description`, and `help_text` fields. Python remains the canonical serializer/migrator and accepts legacy v0.1 bilingual records through an explicit adapter; C# consumes only the normalized current DTO. Immutable historical snapshots retain their original payloads and replay path. WinUI resource strings continue switching the complete application chrome without mutating model state.

**Tech Stack:** Python 3.11, Pydantic 2, SQLite JSON persistence, JSON Schema, JSON-RPC 2.0, C# 14, .NET 10, WinUI 3, System.Text.Json, pytest, xUnit.

---

| Field | Value |
|---|---|
| Milestone | M7 contract/localization amendment |
| Approved design | [Raw Input Provenance and Single-Language Amendment](../specs/2026-07-18-m7-raw-input-provenance-and-single-language-model-content-amendment.md) |
| Decisions | D-055; supersedes only D-052 bilingual-model-metadata clause |
| Execution policy | Inline, compatibility-first, lightweight contract/UI tests |
| Out of scope | Automatic translation, scientific renaming, rewriting historical RunSnapshots |

## Task 1: Add normalized Python current contracts

**Files:**

- Modify: `src/pilot_assessment/contracts/model_workspace.py`
- Modify: `src/pilot_assessment/model_workspace/migration.py`
- Test: `tests/contracts/test_model_workspace_contract.py`

- [ ] Define current `ModelNode`/`TaskScheme` contract fields `name`, `short_name`, `description` and definition-level `help_text`.
- [ ] Remove bilingual-pair validation from the current contract while retaining strict nonblank/identifier rules.
- [ ] Write a deterministic legacy adapter: prefer nonblank English; otherwise preserve the legacy Chinese value with an explicit migration diagnostic rather than losing content.
- [ ] Keep old immutable snapshot models readable; do not silently rewrite persisted historical payloads.

## Task 2: Migrate current persistence and service operations

**Files:**

- Modify: `src/pilot_assessment/model_workspace/repository.py`
- Modify: `src/pilot_assessment/model_workspace/service.py`
- Modify: `src/pilot_assessment/model_workspace/execution.py`
- Modify: `src/pilot_assessment/model_workspace/migration.py`
- Test: `tests/model_workspace/`

- [ ] Normalize legacy current-object JSON at repository read/import boundaries.
- [ ] Make create/copy/update/search/display operations consume a single English field.
- [ ] Verify semantic/content hashes are computed from normalized canonical content and language switching is absent from backend operations.
- [ ] Preserve append-only change history, optimistic revisions, undo/redo, and old-run replay.

## Task 3: Update JSON-RPC and schemas

**Files:**

- Modify: `src/pilot_assessment/sidecar/methods.py`
- Modify: `src/pilot_assessment/schemas/export.py`
- Regenerate: `schemas/model-node-*.json`
- Regenerate: `schemas/task-scheme-*.json`
- Regenerate dependent graph/run schemas as required by references
- Test: `tests/sidecar/` and schema-drift tests

- [ ] Replace bilingual create/copy/update request fields with `name`, `short_name`, `description`, and `help_text`.
- [ ] Return normalized current DTOs only.
- [ ] Regenerate all dependent schemas; achieve zero schema drift.
- [ ] Add one legacy fixture that proves v0.1 records normalize without changing immutable run payloads.

## Task 4: Update C# contracts and projections

**Files:**

- Modify: `src/PilotAssessment.Desktop.Core/Contracts/ModelWorkspaceContracts.cs`
- Modify: `src/PilotAssessment.Desktop.Core/Contracts/ModelWorkspaceRpcContracts.cs`
- Modify: `src/PilotAssessment.Desktop.Core/State/GraphProjection.cs`
- Modify: `src/PilotAssessment.Desktop.Core/State/ModelNodeDraftFactory.cs`
- Modify: `src/PilotAssessment.Desktop.Core/State/ModelNodeDraftRebaser.cs`
- Test: `tests/PilotAssessment.Desktop.UnitTests/Contracts/ContractSerializationTests.cs`
- Test: `tests/PilotAssessment.Desktop.UnitTests/State/GraphProjectionTests.cs`

- [ ] Replace DTO bilingual properties with single canonical properties.
- [ ] Remove `BilingualTextSelector` from current model projections and searches.
- [ ] Keep UI language only in `GraphProjectionLabels` and application resources.
- [ ] Update JSON source-generation contexts and fixtures.

## Task 5: Replace bilingual editor fields with single English fields

**Files:**

- Modify: `src/PilotAssessment.Desktop/ViewModels/RawInputEditorViewModel.cs`
- Modify: `src/PilotAssessment.Desktop/ViewModels/EvidenceEditorViewModel.cs`
- Modify: `src/PilotAssessment.Desktop/ViewModels/BnNodeEditorViewModel.cs`
- Modify: `src/PilotAssessment.Desktop/Controls/Editors/RawInputEditor.xaml`
- Modify: `src/PilotAssessment.Desktop/Controls/Editors/EvidenceEditor.xaml`
- Modify: `src/PilotAssessment.Desktop/Controls/Editors/BnNodeEditor.xaml`
- Modify: `src/PilotAssessment.Desktop/Controls/TaskSchemeSidebar.xaml.cs`
- Modify: `src/PilotAssessment.Desktop/Services/Windowing/NodeWindowRegistry.cs`

- [ ] Present one Name, Short name, Description, and Help text input with localized field labels.
- [ ] Explain in localized helper text that expert model content is canonical English.
- [ ] Ensure autosave calls the matching typed backend single-field mutation.
- [ ] Remove every side-by-side English/Chinese expert-content editor from the current UI.

## Task 6: Audit complete application localization

**Files:**

- Modify: `src/PilotAssessment.Desktop/Strings/en-US/Resources.resw`
- Modify: `src/PilotAssessment.Desktop/Strings/zh-CN/Resources.resw`
- Test: localization/resource parity tests under `tests/PilotAssessment.Desktop.UnitTests/`

- [ ] Keep both resource files key-identical.
- [ ] Localize all application labels, prompts, statuses, dialog text, errors, and new helper text.
- [ ] Remove user-visible fallback markers and hard-coded bilingual concatenation.
- [ ] Confirm that canonical model strings remain unchanged when the application language switches.

## Task 7: Compatibility and end-to-end verification

- [ ] Run focused Python contract/repository/sidecar tests.
- [ ] Run schema generation and zero-drift verification.
- [ ] Run focused .NET serialization, editor, task-scheme, and graph-projection tests.
- [ ] Build and launch the x64 Debug desktop app.
- [ ] Verify Chinese mode shows Chinese application chrome only, English mode shows English application chrome only, and expert model values remain the same English strings in both modes.
- [ ] Verify a legacy bilingual workspace opens through migration and a historical run remains replayable.

## Plan self-review

- The plan separates UI language from scientific/model data instead of deleting localization.
- Compatibility is additive at the read boundary; historical snapshots are never rewritten.
- The backend remains canonical for persisted definitions but does not dictate expert scientific content.
- The migration has an explicit no-data-loss fallback when a legacy record lacks English text.
- No automatic translation service or duplicated model-language workflow is introduced.
