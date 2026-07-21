# M8E Final Release Candidate Implementation Plan

> **For agentic workers:** REQUIRED execution mode is **INLINE** in the current task. Do not create a large subagent fan-out. Track steps with checkboxes and commit each coherent slice.

**Goal:** Build and verify `v0.1.0-rc.1`, including D-055 single-English current model content, the complete bilingual M8C-1 manual set, candidate screenshots, clean tagged-source release metadata, and a repository-external Windows x64 acceptance ZIP.

**Architecture:** Keep the WinUI → JSON-RPC sidecar → Python domain-service boundary. Add a new current-model contract while retaining explicit legacy readers and immutable historical run payloads. Keep Markdown as documentation authority and deterministically generate 24 DOCX files. Capture the explicitly selected current `system/`; run all mutation tests only on disposable copies.

**Tech Stack:** Python 3.11, Pydantic 2, SQLite, JSON Schema, JSON-RPC 2.0, C# 14, .NET 10, WinUI 3, pytest, xUnit, python-docx, headless DOCX render QA, PowerShell and Git.

---

| Field | Value |
|---|---|
| Approved design | [M8E Final Release Candidate Design](../specs/2026-07-21-m8e-final-release-candidate-and-handoff-design.md) |
| Candidate | `v0.1.0-rc.1` |
| Product version | `0.1.0` |
| Execution | INLINE, contract-first, selective lightweight tests |
| System source | `.pilot-assessment-local/system`, explicitly selected |
| User acceptance | Pending until the complete candidate is tested |
| Scientific status | `engineering-only`; `formal_run_authorized=false` |

## File map

- `src/pilot_assessment/contracts/model_workspace.py` — current v0.2 node/scheme and v0.3 graph contracts.
- `src/pilot_assessment/contracts/model_workspace_legacy.py` — immutable legacy v0.1 bilingual readers.
- `src/pilot_assessment/model_workspace/content_migration.py` — current-content normalization and lineage.
- `src/pilot_assessment/persistence/` — durable row migration and read-boundary compatibility.
- `src/PilotAssessment.Desktop.Core/` and `src/PilotAssessment.Desktop/` — current DTOs, editors and UI localization.
- `docs/product/manuals/` and `tools/documentation/` — 22 maintained module sources, generated bilingual master manuals and candidate screenshots.
- `tools/release/` and `docs/product/release/` — tagged candidate build, verification and handoff files.

## Task 1: Formalise the M8E gate replacement

**Files:**

- Modify: `docs/product/DECISIONS.md`
- Modify: `docs/product/specs/2026-07-18-m8-productization-editable-python-documentation-and-handoff-outline.md`
- Modify: `docs/product/plans/2026-07-18-m8-pre-uat-implementation-outline.md`
- Modify: `docs/product/reviews/README.md`

- [x] Add D-078 through D-081 exactly as approved: deferred intermediate UAT, `rc.1` identity, candidate screenshots and two-layer acceptance evidence.
- [x] Replace current Gate 0 flow with `M7 engineering verified -> D-055/M8C-1/M8E -> rc.1 -> user acceptance`.
- [x] Preserve that final `v0.1.0` cannot be called accepted before the user test.
- [x] Run:

```powershell
rg -n "M7 user acceptance.*hard|M7 用户.*硬|Gate 0" README.md docs/product -g "*.md"
git diff --check
```

- [x] Commit (`0605fb8`):

```powershell
git add docs/product/DECISIONS.md docs/product/specs docs/product/plans docs/product/reviews/README.md
git commit -m "docs: adopt M8E release candidate gate"
```

## Task 2: Add current single-English contracts and legacy readers

**Files:**

- Create: `src/pilot_assessment/contracts/model_workspace_legacy.py`
- Modify: `src/pilot_assessment/contracts/model_workspace.py`
- Modify: `src/pilot_assessment/contracts/run.py`
- Modify: `src/pilot_assessment/contracts/__init__.py`
- Test: `tests/contracts/test_model_workspace.py`
- Test: `tests/contracts/test_run_contracts.py`

- [x] Add failing tests requiring current serialized objects to contain only:

```python
assert payload["contract_version"] == "0.2.0"
assert payload["name"] == "Trajectory Precision"
assert payload["short_name"] == "Precision"
assert payload["description"] == "Tracks commanded position."
assert not ({"name_zh", "name_en", "short_name_zh", "short_name_en"} & payload)
assert payload["definition"]["help_text"]
```

- [x] Add a test proving existing v0.2 historical run JSON still validates with unchanged bytes/hash, while a new current snapshot uses `0.3.0`.
- [x] Run the focused tests and confirm the new assertions fail:

```powershell
.\.tools\uv\uv.exe run pytest tests\contracts\test_model_workspace.py tests\contracts\test_run_contracts.py -q
```

- [x] Freeze the exact old bilingual node, definition and scheme models as `Legacy*V010` types in the compatibility module.
- [x] Replace current fields with:

```python
class ModelNode(StrictContractModel):
    contract_id: Literal["model-node"] = "model-node"
    contract_version: Literal["0.2.0"] = "0.2.0"
    name: HumanLabel
    short_name: ShortLabel
    description: HumanText

class RawInputNodeDefinition(StrictContractModel):
    help_text: HumanText
```

- [x] Apply the same `help_text` shape to Evidence and BN definitions; remove localized-pair validation only from current types.
- [x] Bind historical run snapshot classes to legacy types; add `ModelGraphSnapshot 0.3.0`, `CurrentModelRunSnapshotV3` and `AssessmentRunV3` for new runs.
- [x] Rerun focused contract tests and commit (`ab76368`):

```powershell
git add src/pilot_assessment/contracts tests/contracts
git commit -m "feat: add single-English current model contracts"
```

## Task 3: Migrate durable current content without rewriting historical runs

**Files:**

- Create: `src/pilot_assessment/model_workspace/content_migration.py`
- Modify: `src/pilot_assessment/persistence/migrations.py`
- Modify: `src/pilot_assessment/persistence/model_workspace_repository.py`
- Modify: `src/pilot_assessment/runtime/system_application.py`
- Modify: `src/pilot_assessment/model_workspace/edit_session.py`
- Test: `tests/model_workspace/test_content_migration.py`
- Test: `tests/model_workspace/test_edit_session.py`
- Test: `tests/persistence/test_migrations.py`

- [x] Add normalizer tests that prefer nonblank English and emit `MODEL_CONTENT_ENGLISH_FALLBACK_PRESERVED` when only legacy non-English text exists.
- [x] Add database migration version 6 with an append-only `model_content_migration_events` table containing object identity, old/new versions and hashes, legacy payload, diagnostics and migrated timestamp.
- [x] Implement `normalise_legacy_model_node`, `normalise_legacy_task_scheme` and `decode_current_model_object`. Use one complete canonical-text selector shared by both normalizers:

```python
def _select_canonical_text(
    payload: Mapping[str, JsonValue],
    *,
    english_key: str,
    alternate_key: str,
) -> tuple[str, bool]:
    english = payload.get(english_key)
    if isinstance(english, str) and english.strip():
        return english.strip(), False
    alternate = payload.get(alternate_key)
    if isinstance(alternate, str) and alternate.strip():
        return alternate.strip(), True
    raise CurrentModelContentMigrationError(
        f"legacy payload has no nonblank {english_key!r} or {alternate_key!r}"
    )
```

- [x] Implement an idempotent content migration that validates all replacements before writing, updates current JSON/indexed hashes, records lineage and never touches run/result/artifact payloads.
- [x] Migrate canonical state before service composition. Rebuild a clean staging workspace; migrate a dirty staging workspace without deleting its history; stop with a stable error if either path fails.
- [x] Route repository current-row and undo/redo snapshot decoding through `decode_current_model_object`; retain old event bytes.
- [x] Run:

```powershell
.\.tools\uv\uv.exe run pytest tests\model_workspace\test_content_migration.py tests\model_workspace\test_edit_session.py tests\persistence\test_migrations.py -q
```

Implementation evidence (2026-07-21): the exact focused gate passed `10 passed`; the
extended persistence gate including `test_project_database.py` passed `15 passed`.
Focused Ruff and `ty check` gates for the migration/runtime path also passed. The dirty
legacy staging test preserves session identity, cursor, latest sequence, transaction/method
history and draft content while migrating both live rows and every stored checkpoint.

- [x] Commit (`0e7aebc`):

```powershell
git add src/pilot_assessment/model_workspace src/pilot_assessment/persistence src/pilot_assessment/runtime tests/model_workspace tests/persistence
git commit -m "feat: migrate current model content to English"
```

## Task 4: Update services, execution, RPC and schemas

**Files:**

- Modify: `src/pilot_assessment/model_workspace/migration.py`
- Modify: `src/pilot_assessment/model_workspace/operations.py`
- Modify: `src/pilot_assessment/model_workspace/service.py`
- Modify: `src/pilot_assessment/model_workspace/execution.py`
- Modify: `src/pilot_assessment/sidecar/methods.py`
- Modify: `src/pilot_assessment/schemas/export.py`
- Generate: `schemas/model-node-0.2.0.schema.json`
- Generate: `schemas/task-scheme-0.2.0.schema.json`
- Generate: `schemas/model-graph-snapshot-0.3.0.schema.json`
- Generate: `schemas/current-model-run-snapshot-0.3.0.schema.json`
- Generate: `schemas/assessment-run-0.3.0.schema.json`
- Generate matching package resources under `src/pilot_assessment/schema_resources/`
- Test: `tests/model_workspace/`, `tests/sidecar/test_methods.py`, `tests/schemas/test_schema_export.py`

- [x] Convert starter materialization, copy/update/search and execution code to `name/short_name/description/help_text`.
- [x] Make current RPC mutations accept and return only the single current fields; legacy normalization remains internal.
- [x] Freeze new runs as v0.3 and let persistence/result readers discriminate old and new versions.
- [x] Export additive v0.2/v0.3 schemas without deleting historical schema files:

```powershell
.\.tools\uv\uv.exe run python -m pilot_assessment.schemas.export
```

- [x] Run focused backend gates:

```powershell
.\.tools\uv\uv.exe run pytest tests\model_workspace tests\sidecar\test_methods.py tests\schemas\test_schema_export.py -q
.\.tools\uv\uv.exe run ruff check src\pilot_assessment tests
.\.tools\uv\uv.exe run ty check src\pilot_assessment
```

Implementation evidence (2026-07-21): the exact focused backend gate passed `77 passed`;
the current-run/persistence/provenance gate passed `10 passed`; and the extended
subprocess, integration, source-provenance and release-capture regression gate passed
`18 passed`. Full Ruff and `ty check` gates passed. Historical v0.1/v0.2 schemas remain
byte-preserved package resources while new current schemas are additive. The release
capture tool now recognises SQLite schema v6 and continues to reject future v7.

- [x] Commit (`b5872a8`):

```powershell
git add src/pilot_assessment schemas tests
git commit -m "feat: expose single-English current model RPC"
```

## Task 5: Update C# current contracts and core projections

**Files:**

- Modify: `src/PilotAssessment.Desktop.Core/Contracts/ModelWorkspaceContracts.cs`
- Modify: `src/PilotAssessment.Desktop.Core/Contracts/ModelWorkspaceRpcContracts.cs`
- Modify: `src/PilotAssessment.Desktop.Core/Contracts/RunContracts.cs`
- Modify: `src/PilotAssessment.Desktop.Core/Contracts/PilotAssessmentJsonContext.cs`
- Modify: `src/PilotAssessment.Desktop.Core/State/ModelNodeDraftFactory.cs`
- Modify: `src/PilotAssessment.Desktop.Core/State/ModelNodeDraftRebaser.cs`
- Modify: `src/PilotAssessment.Desktop.Core/State/ModelDisplayNameResolver.cs`
- Modify: `src/PilotAssessment.Desktop.Core/State/GraphProjection.cs`
- Modify: `src/PilotAssessment.Desktop.Core/ViewModels/TaskSchemeListViewModel.cs`
- Modify: `src/PilotAssessment.Desktop/Services/Backend/ModelWorkspaceClient.cs`
- Test: desktop unit and contract suites

- [x] Add a failing C# serialization test for `model-node/0.2.0` with `Name`, `ShortName`, `Description` and definition `HelpText`.
- [x] Replace current typed DTOs and RPC payloads; keep explicit legacy snapshot DTOs only for historical fixtures.
- [x] Remove bilingual selection from display resolution, graph search, draft/rebase and task scheme list.
- [x] Confirm current client payloads contain no null bilingual keys.
- [x] Run:

```powershell
dotnet test tests\PilotAssessment.Desktop.UnitTests\PilotAssessment.Desktop.UnitTests.csproj -c Debug --nologo
dotnet test tests\PilotAssessment.Desktop.ContractTests\PilotAssessment.Desktop.ContractTests.csproj -c Debug -p:Platform=x64 --nologo
```

- [x] Commit (`ce816e8`, combined with Task 6 to preserve a buildable desktop slice):

```powershell
git add src/PilotAssessment.Desktop.Core src/PilotAssessment.Desktop/Services tests/PilotAssessment.Desktop.UnitTests tests/PilotAssessment.Desktop.ContractTests
git commit -m "feat: consume single-English model contracts in desktop core"
```

## Task 6: Replace bilingual expert-content editors and audit localization

**Files:**

- Modify: `src/PilotAssessment.Desktop/ViewModels/RawInputEditorViewModel.cs`
- Modify: `src/PilotAssessment.Desktop/ViewModels/EvidenceEditorViewModel.cs`
- Modify: `src/PilotAssessment.Desktop/ViewModels/BnNodeEditorViewModel.cs`
- Modify: `src/PilotAssessment.Desktop/Controls/Editors/RawInputEditor.xaml`
- Modify: `src/PilotAssessment.Desktop/Controls/Editors/EvidenceEditor.xaml`
- Modify: `src/PilotAssessment.Desktop/Controls/Editors/BnNodeEditor.xaml`
- Modify: `src/PilotAssessment.Desktop/Controls/TaskSchemeSidebar.xaml`
- Modify: `src/PilotAssessment.Desktop/Controls/TaskSchemeSidebar.xaml.cs`
- Modify: `src/PilotAssessment.Desktop/Controls/Graph/NodeCreationDialog.xaml`
- Modify: `src/PilotAssessment.Desktop/Controls/Graph/NodeCreationDialog.xaml.cs`
- Modify: `src/PilotAssessment.Desktop/Strings/en-US/Resources.resw`
- Modify: `src/PilotAssessment.Desktop/Strings/zh-CN/Resources.resw`
- Test: desktop editor/localization unit tests

- [x] Replace paired editor state with single `Name`, `Description` and `HelpText` properties.
- [x] Replace paired XAML fields with one canonical field and localized hint:

```xml
<TextBox Header="{Binding [Editor_CanonicalName], Source={StaticResource Localization}}"
         Text="{Binding Name, Mode=TwoWay}" />
<TextBlock Text="{Binding [Editor_CanonicalEnglishHint], Source={StaticResource Localization}}" />
```

- [x] Use `名称（模型内容使用英文）` in Chinese and `Name (canonical content in English)` in English.
- [x] Remove obsolete paired resource keys only after all references are gone; keep unrelated UI localization.
- [x] Add a test proving language switching changes UI labels but does not mutate or rewrite model content.
- [x] Run unit tests and an x64 Debug visible WinUI smoke; close normally with `CloseMainWindow` before current-system capture.
- [x] Commit (`ce816e8`, combined with Task 5 to preserve a buildable desktop slice):

```powershell
git add src/PilotAssessment.Desktop tests/PilotAssessment.Desktop.UnitTests
git commit -m "feat: use canonical English fields in model editors"
```

Implementation evidence (2026-07-21): desktop unit tests passed `105 passed`, the
real-sidecar contract suite passed `4 passed`, and the x64 Debug WinUI build completed
with zero warnings and zero errors. The rebuilt desktop process opened a responsive
main window with a non-zero window handle. Current serialized model payload tests
explicitly reject legacy bilingual keys; the immutable v0.2 run fixture still round-trips
through an opaque legacy DTO while the new v0.3 fixture uses current single-English nodes.

## Task 7: Rehearse and apply D-055 current-system migration

**Files:**

- Create: `tests/integration/test_m8e_current_system_migration.py`
- Modify only through normal runtime migration: `.pilot-assessment-local/system/` (Git-ignored)

- [x] Inspect and record the read-only source identity, clean edit state, user-owned row counts and transient count.
- [x] `copytree` the complete system to a temporary root and open the copy with the new runtime.
- [x] Assert counts/parents/CPT/recipe/activation/layout are preserved, all current objects use v0.2 single fields, and historical run bytes remain unchanged.
- [x] If the copy passes and the source identity still matches, open/close the selected system through `SystemApplication`; do not run a one-off SQL patch.
- [x] Re-inspect: same library ID and `54 / 2`, new content identity due only to contract migration, no user-owned rows or WAL/SHM, and explicit migration lineage.
- [x] Commit only the integration test (`9635e56`):

```powershell
git add tests/integration/test_m8e_current_system_migration.py
git commit -m "test: verify current system English migration"
```

Implementation evidence (2026-07-21): a disposable complete legacy system, including
its clean staging database and baseline snapshot, was copied and migrated through normal
`SystemApplication` composition. The focused gate passed `2 passed` when the explicit
selected-system gate was enabled. The selected current system retained its model-library
ID, `54` nodes and `2` schemes; its `56` append-only lineage rows map every v0.1 object to
one v0.2 object. Structural projections prove parents, CPTs, Evidence recipes, activation
sets and layouts are unchanged. User-owned tables, historical Run rows and WAL/SHM files
are empty. The normal WinUI smoke opened and cleanly closed this selected system; no
one-off SQL patch was applied.

## Task 8: Complete documentation aggregation and screenshot contracts

**Files:**

- Modify: `docs/product/manuals/catalog.json`
- Modify: `docs/product/manuals/schemas/document-metadata.schema.json`
- Modify: `docs/product/manuals/assets/screenshots/manifest.json`
- Modify: `tools/documentation/manual_common.py`
- Modify: `tools/documentation/validate_manuals.py`
- Modify: `tools/documentation/build_manuals.py`
- Modify: `tools/documentation/render_manuals.py`
- Create: `tools/documentation/register_screenshots.py`
- Create: `tests/documentation/test_manual_pipeline.py`

- [x] Add failing tests requiring 12 logical documents, 24 released language outputs, an 11-module generated master and ten unique candidate screenshot assets.
- [x] Add catalog fields `release_channel=release-candidate`, `release_label=v0.1.0-rc.1`, `user_acceptance=pending`; set every module variant to `released`.
- [x] Let the technical-reference variants use `source: null` and generate their metadata/body from `aggregate_sources`; do not create a third Markdown authority.
- [x] Implement deterministic heading shifting and page breaks when aggregating 11 module bodies.
- [x] Validate screenshot file/hash/language/dimensions/source identity/privacy; accept `release-candidate` only for a candidate catalog with pending acceptance.
- [x] Add `register_screenshots.py` to hash and register existing PNGs; it must not capture screens or generate product data.
- [x] Run:

```powershell
.\.tools\uv\uv.exe run pytest tests\documentation\test_manual_pipeline.py -q
.\.tools\uv\uv.exe run python tools\documentation\validate_manuals.py --status released
```

- [x] Commit (`f56e5c2`):

```powershell
git add docs/product/manuals/catalog.json docs/product/manuals/schemas docs/product/manuals/assets/screenshots tools/documentation tests/documentation
git commit -m "feat: add M8C release-candidate documentation contracts"
```

## Task 9: Write eleven bilingual module manuals

**Files:**

- Modify: `docs/product/manuals/zh-CN/01-product-overview-and-architecture.md`
- Modify: `docs/product/manuals/en-GB/01-product-overview-and-architecture.md`
- Create: `docs/product/manuals/zh-CN/02-installation-startup-quick-start.md`
- Create: `docs/product/manuals/en-GB/02-installation-startup-quick-start.md`
- Create: `docs/product/manuals/zh-CN/03-evaluator-user-guide.md`
- Create: `docs/product/manuals/en-GB/03-evaluator-user-guide.md`
- Create: `docs/product/manuals/zh-CN/04-evidence-task-scheme-expert-guide.md`
- Create: `docs/product/manuals/en-GB/04-evidence-task-scheme-expert-guide.md`
- Create: `docs/product/manuals/zh-CN/05-bayesian-network-cpt-expert-guide.md`
- Create: `docs/product/manuals/en-GB/05-bayesian-network-cpt-expert-guide.md`
- Create: `docs/product/manuals/zh-CN/06-session-bundle-input-interface-reference.md`
- Create: `docs/product/manuals/en-GB/06-session-bundle-input-interface-reference.md`
- Create: `docs/product/manuals/zh-CN/07-python-operator-source-extension.md`
- Modify: `docs/product/manuals/en-GB/07-python-operator-source-extension.md`
- Create: `docs/product/manuals/zh-CN/08-python-core-maintenance-reference.md`
- Create: `docs/product/manuals/en-GB/08-python-core-maintenance-reference.md`
- Create: `docs/product/manuals/zh-CN/09-sidecar-protocol-csharp-development-reference.md`
- Create: `docs/product/manuals/en-GB/09-sidecar-protocol-csharp-development-reference.md`
- Create: `docs/product/manuals/zh-CN/10-system-distribution-project-portability-troubleshooting.md`
- Create: `docs/product/manuals/en-GB/10-system-distribution-project-portability-troubleshooting.md`
- Create: `docs/product/manuals/zh-CN/11-release-build-delivery-acceptance.md`
- Create: `docs/product/manuals/en-GB/11-release-build-delivery-acceptance.md`

- [x] Write task-focused quick-start/evaluator paths: unzip, automatic backend/SQLite, project, import, partial modalities, run/result, diagnostics and shutdown.
- [x] Write expert Evidence/BN paths: five layers, recipes/operators, parents/closure, states/CPT, task activation, staged save/discard/cancel and scientific boundary.
- [x] Write input/source/protocol references: X/U/I/G/P, EEG/ECG/pilot-camera, canonical/raw input, missing modalities, Python source identity and C# typed-intent boundary.
- [x] Write portability/release paths: current `system/`, whole-project copy, no backup product, source divergence, hashes/SBOM/licenses, candidate acceptance and final promotion.
- [x] Keep language metadata parity; localize prose while leaving code, paths, IDs, RPC fields and canonical model values English.
- [x] Validate and commit (`b9f2bfa`):

```powershell
.\tools\documentation\build_docs.ps1 validate -Status released
git add docs/product/manuals/zh-CN docs/product/manuals/en-GB docs/product/manuals/catalog.json
git commit -m "docs: complete bilingual M8C module manuals"
```

## Task 10: Capture candidate screenshots and build 24 DOCX files

**Files:**

- Create: `docs/product/manuals/assets/screenshots/zh-CN/ui-project-launcher.png`
- Create: `docs/product/manuals/assets/screenshots/zh-CN/ui-five-layer-model-studio.png`
- Create: `docs/product/manuals/assets/screenshots/zh-CN/ui-evidence-node-editor.png`
- Create: `docs/product/manuals/assets/screenshots/zh-CN/ui-bn-cpt-editor.png`
- Create: `docs/product/manuals/assets/screenshots/zh-CN/ui-run-results-diagnostics.png`
- Create: `docs/product/manuals/assets/screenshots/en-GB/ui-project-launcher.png`
- Create: `docs/product/manuals/assets/screenshots/en-GB/ui-five-layer-model-studio.png`
- Create: `docs/product/manuals/assets/screenshots/en-GB/ui-evidence-node-editor.png`
- Create: `docs/product/manuals/assets/screenshots/en-GB/ui-bn-cpt-editor.png`
- Create: `docs/product/manuals/assets/screenshots/en-GB/ui-run-results-diagnostics.png`
- Modify: `docs/product/manuals/assets/screenshots/manifest.json`
- Generate: `dist/documentation/PilotAssessment-0.1.0-docs/`
- Generate QA: `build/documentation/rendered/`

- [x] Build a clean pre-capture UI and record its UI source-tree SHA-256; do not change UI code afterward.
- [x] Create an anonymous disposable project outside the repo/release solely for screenshots; never package it.
- [x] Capture project launcher, five-layer Model Studio, Evidence editor, BN/CPT editor and Run/Results/Diagnostics in Chinese and English.
- [x] Register ten PNGs and confirm no username, user-home path, real Session/biometric content or external identifier.
- [x] Build and render:

```powershell
.\tools\documentation\build_docs.ps1 all -Status released
```

- [x] Require 24 DOCX outputs and visually inspect rendered pages for clipping, overlap, blank pages, table overflow, unreadable images and broken navigation.
- [x] Commit authoritative sources/assets/tool changes, not generated `dist/` or `build/` artifacts (`894947a`, `58a781c`):

```powershell
git add docs/product/manuals tools/documentation tests/documentation
git commit -m "docs: complete M8C release-candidate manuals"
```

## Task 11: Add tagged release-candidate metadata and handoff files

**Files:**

- Modify: `tools/release/build_portable.py`
- Modify: `tools/release/verify_portable.py`
- Modify: `tools/release/verify_archive_external.py`
- Modify: `tools/release/README.md`
- Create: `docs/product/release/RELEASE-NOTES-0.1.0-rc.1.md`
- Create: `docs/product/release/ACCEPTANCE-CHECKLIST.md`
- Modify: `docs/product/release/README-PORTABLE.md`
- Modify: `docs/product/release/KNOWN-LIMITATIONS.md`
- Test: `tests/release/test_release_candidate.py`
- Test: `tests/release/test_system_model_capture.py`

- [x] Add failing tests for product `0.1.0`, channel `release-candidate`, candidate `rc.1`, label/tag `v0.1.0-rc.1`, pending acceptance, clean Git and 24 released docs.
- [x] Add explicit CLI args: `--release-label`, `--release-channel`, `--candidate`, `--user-acceptance`, `--documentation-status`.
- [x] Candidate mode refuses dirty source, mismatched/non-annotated tag, wrong base version and final candidate `--skip-archive`.
- [x] Name output `PilotAssessment-0.1.0-rc.1-win-x64`; set `build_kind=m8e-release-candidate`.
- [x] Copy release notes, acceptance checklist, candidate README and limitations into the package root.
- [x] Write an outer delivery JSON with ZIP name/bytes/hash, tag/commit, system identity/counts, docs/SBOM hashes and acceptance status; never include absolute source paths.
- [x] Extend packaged/external verifiers for candidate fields, 24 docs, ten screenshots, acceptance files, restricted PATH, visible desktop and zero TCP listener.
- [x] Run and commit (`0496cef`):

```powershell
.\.tools\uv\uv.exe run pytest tests\release\test_release_candidate.py tests\release\test_system_model_capture.py -q
.\.tools\uv\uv.exe run ruff check tools\release tests\release
git add tools/release tests/release docs/product/release
git commit -m "feat: build tagged M8E release candidates"
```

## Task 12: Close source documentation and create the clean tag

**Files:**

- Modify: `README.md`
- Modify: `docs/product/README.md`
- Modify: `docs/product/01_PRODUCT_OVERVIEW.md`
- Modify: `docs/product/09_VALIDATION_AND_HANDOFF.md`
- Modify: `docs/product/11_IMPLEMENTATION_STATUS.md`
- Modify: `docs/product/GLOSSARY.md`
- Modify: `docs/product/reviews/README.md`
- Modify: this plan

- [x] Record `M8E release candidate implementation complete / final candidate verification pending`, `user acceptance pending`, and `formal_run_authorized=false`.
- [x] Remove stale current-status statements that D-055/M8C-1 implementation remains pending; retain dated history only when labelled.
- [x] Run released-document validation and `git diff --check` (`5 passed`; `24` released variants; render QA `PASS`).
- [x] Commit this source-preparation slice:

```powershell
git add README.md docs/product
git commit -m "docs: prepare v0.1.0-rc.1 release source"
```

- [x] Require a clean worktree, create annotated tag and prove it peels to `HEAD` (`v0.1.0-rc.1` peels to `c736bf7ad58bd24212b8997c5bbbf427b96e2692`):

```powershell
git status --short
git tag -a v0.1.0-rc.1 -m "Pilot Assessment System v0.1.0-rc.1"
git rev-parse HEAD
git rev-parse v0.1.0-rc.1^{}
```

## Task 13: Build, externally verify and record `v0.1.0-rc.1`

**Files:**

- Generate: `dist/releases/PilotAssessment-0.1.0-rc.1-win-x64/`
- Generate: `dist/releases/PilotAssessment-0.1.0-rc.1-win-x64.zip`
- Generate: `dist/releases/PilotAssessment-0.1.0-rc.1-win-x64.zip.sha256`
- Generate: `dist/releases/PilotAssessment-0.1.0-rc.1-win-x64.delivery.json`
- Create: `docs/product/reviews/2026-07-21-m8e-release-candidate-verification.md`
- Modify: this plan

- [x] Run fresh focused Python, schema, documentation, release, desktop unit/contract and x64 Release build gates.
- [x] Capture source-system file hashes, model identity, `54 / 2`, clean edit state, schema versions, user-owned counts and zero transients.
- [x] Build:

```powershell
.\.tools\uv\uv.exe run python tools\release\build_portable.py `
  --system-source .pilot-assessment-local\system `
  --release-label v0.1.0-rc.1 `
  --release-channel release-candidate `
  --candidate rc.1 `
  --user-acceptance pending `
  --documentation-status released
```

- [x] Verify outside the repository:

```powershell
.\.tools\uv\uv.exe run python tools\release\verify_archive_external.py `
  --dist dist\releases\PilotAssessment-0.1.0-rc.1-win-x64.zip `
  --verify-editable-source `
  --verify-operator-extension `
  --launch-desktop `
  --restricted-path
```

- [x] Re-inspect source and candidate: no source-system change, no WAL/SHM/process leftovers, all mutations confined to disposed copies.
- [x] Scan ZIP names, extracted text and DOCX XML for private paths, projects/sessions/results, caches, PDBs and unlisted files.
- [x] Record exact tag/commit, toolchain, ZIP hash/bytes, system identity/counts, docs count/hash/pages, test totals, external verifier and remaining boundaries.
- [x] Mark every completed checkbox and commit evidence without moving the existing tag:

```powershell
git add docs/product/reviews/2026-07-21-m8e-release-candidate-verification.md docs/product/plans/2026-07-21-m8e-final-release-candidate-implementation-plan.md
git commit -m "docs: record v0.1.0-rc.1 verification"
```

## Plan self-review

- Spec coverage: D-055 is Tasks 2–7; M8C-1 is Tasks 8–10; tagged candidate and handoff are Tasks 11–13.
- Type consistency: current node/scheme `0.2.0`; new graph/run containers `0.3.0`; base product `0.1.0`; release label `v0.1.0-rc.1`.
- Documentation consistency: module sources are `released`; screenshots are `release-candidate`; user acceptance remains `pending`.
- Scope: no installer, signing, update service, cloud, backup product or scientific calibration.
- Test weight: no large multimodal fixtures or exact D/A/U goldens; high-risk persistence/release boundaries receive focused automated tests and docs receive structural/privacy/render checks.
- Execution: inline only, one coherent commit per slice, no large subagent fan-out.
