# M7 Simulator Raw Session Import Adapter Implementation Plan

> **For agentic workers:** Execute inline in this repository. Keep each task bounded, preserve the existing dirty M7 worktree, and use focused tests rather than large synthetic datasets.

> **Implementation record — 2026-07-20:** The code and verification portions of Tasks 1–8 have been implemented through Python, managed persistence, JSON-RPC, C# contracts/ViewModel and WinUI. The approved tiny fixture was kept in-memory inside focused tests rather than added as a repository data tree, preserving the user's lightweight-test boundary. Fresh evidence: Python format/lint/type checks pass; raw-focused tests `10/10`; combined sidecar regression `17/17`; Desktop Unit `98/98`; real-sidecar Contract `4/4`; x64 Debug build `0 warnings / 0 errors`; the real WinUI Sessions page was launched with backend `Ready` and retained for user acceptance. A feature commit is deliberately deferred because this workspace already contains overlapping uncommitted M7 user work; M7 user acceptance remains open, and no scientific claim is made.

**Goal:** Let the desktop product import a simulator folder containing only `streams/` and `annotations/`, generate a canonical manifest inside managed project storage, and continue partial assessment without asking users to supply missing units.

**Architecture:** A pure Python raw-source inspector/materializer recognizes the existing Cranfield X/U CSV profile and the already-supported optional multimodal layouts. `SessionImportService` dispatches canonical bundles to the unchanged exact-copy path and raw sources to a staging materialization path, then both converge on the same manifest/readiness/hash/promotion code. New JSON-RPC and C# contracts expose one auto-detecting source workflow; WinUI shows source kind, profile, mappings, declared/undeclared units, and partial readiness without exposing manifest authoring.

**Tech Stack:** Python 3.12, Pydantic v2, Polars, SQLite, JSON-RPC 2.0/JSONL, C#/.NET 10, WinUI 3, xUnit, pytest, uv.

---

## File map

**Create**

- `src/pilot_assessment/contracts/session_source.py` — cross-layer source-inspection and raw-import DTOs.
- `src/pilot_assessment/ingestion/raw_session.py` — safe source detection, profile matching, annotation normalization, and deterministic manifest materialization.
- `tests/ingestion/test_raw_session.py` — lightweight pure inspector/materializer tests.
- `tests/fixtures/raw_session_minimal/` — one tiny X/U plus empty/canonical annotation shape, with no synthetic missing modalities.

**Modify**

- `src/pilot_assessment/contracts/__init__.py` — export new contracts.
- `src/pilot_assessment/persistence/sessions.py` — add source dispatch and converge both import paths after staging.
- `src/pilot_assessment/sidecar/methods.py` — register and implement `session.source.inspect/import`.
- `src/pilot_assessment/sidecar/errors.py` — map stable raw-import failures.
- `src/PilotAssessment.Desktop.Core/Contracts/ProjectSessionRpcContracts.cs` — C# wire contracts.
- `src/PilotAssessment.Desktop.Core/Contracts/PilotAssessmentJsonContext.cs` — source-generated JSON metadata.
- `src/PilotAssessment.Desktop.Core/ViewModels/ProjectSessionAbstractions.cs` — unified gateway methods.
- `src/PilotAssessment.Desktop/Services/Backend/ProjectSessionClient.cs` — new RPC calls.
- `src/PilotAssessment.Desktop.Core/ViewModels/SessionExplorerViewModel.cs` — source-kind and raw-preview state.
- `src/PilotAssessment.Desktop/Views/Pages/SessionExplorerPage.xaml` — unified folder picker and raw preview.
- `src/PilotAssessment.Desktop/Strings/en-US/Resources.resw` and `zh-CN/Resources.resw` — complete localization.
- focused Python/C# tests and product docs/decisions/status.

## Task 1: Raw-source contracts

- [x] Create the discriminated source contract.

```python
class SessionSourceKind(StrEnum):
    CANONICAL_BUNDLE = "canonical_bundle"
    SIMULATOR_RAW = "simulator_raw"

class RawFieldMapping(StrictContractModel):
    source_path: BundleRelativePath
    source_field: str
    canonical_field: str
    modality: str
    declared_unit: str | None = None
    unit_provenance: Literal["source", "profile", "undeclared"]

class RawSessionInspection(StrictContractModel):
    contract_version: Literal["0.1.0"] = "0.1.0"
    source_snapshot_fingerprint: Sha256Digest
    detected_profile_id: StableId
    files: tuple[RawSourceFile, ...]
    field_mappings: tuple[RawFieldMapping, ...]
    modality_proposals: dict[StableId, RawModalityProposal]
    annotation_mappings: tuple[RawAnnotationMapping, ...]
    required_user_inputs: tuple[RawRequiredInput, ...] = ()
    warnings: tuple[DomainErrorData, ...] = ()
    can_materialize: StrictBool

class SessionSourceInspection(StrictContractModel):
    source_kind: SessionSourceKind
    report: IngestionReadinessReport | None = None
    raw: RawSessionInspection | None = None
```

- [x] Validate that exactly one payload matches `source_kind`, all seven core modalities appear in raw proposals, and `declared_unit=None` never creates a required input.
- [x] Export the types from `contracts/__init__.py`.
- [x] Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/contracts -q
```

Expected: existing contract tests remain green.

## Task 2: Read-only raw inspection

- [x] Add a minimal in-memory fixture containing `streams/simulator.csv` and `annotations/` only. Use 4-8 CSV rows copied from the captured header shape; do not generate visual, gaze or physiology data.
- [x] Write focused tests asserting:

```python
inspection = inspect_session_source(raw_root)
assert inspection.source_kind is SessionSourceKind.SIMULATOR_RAW
assert inspection.raw is not None
assert inspection.raw.detected_profile_id == "cranfield-simulator-combined-csv-raw-v0.1"
assert inspection.raw.modality_proposals["X"].status == "present"
assert inspection.raw.modality_proposals["U"].status == "present"
assert inspection.raw.modality_proposals["G"].status == "missing"
assert inspection.raw.required_user_inputs == ()
assert snapshot(raw_root) == before
```

- [x] Implement `detect_session_source(root)` with fail-closed rules: valid `manifest.json` selects canonical; invalid manifest never falls back; raw requires both directories; `_pilot_assessment/` is reserved.
- [x] Match CSV files below `streams/` by normalized headers against the packaged Cranfield CSV profile. Zero or multiple matching files return typed recoverable errors.
- [x] Detect optional I/G/EEG/ECG/pilot-camera conventional layouts using the existing exact paths and schema IDs; absent layouts become `missing`, never files.
- [x] Preserve declared profile units, drop `unknown_raw` from unit declarations, mark remaining unknown fields `undeclared`, and never ask for unit input.
- [x] Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/ingestion/test_raw_session.py -q
```

Expected: the small raw fixture passes and source bytes remain unchanged.

## Task 3: Canonical materialization

- [x] Write focused tests for `materialize_raw_session(inspection, raw_root, staging_root, identity)`.
- [x] Copy only `streams/` and `annotations/` into the same staging-relative paths using exclusive writes and streaming SHA-256 verification.
- [x] Normalize recognized session-time annotations. For absent/unrecognized categories write explicit empty documents:

```json
{"schema_id":"phases-session-time-v0.1","phases":[]}
```

with corresponding events and baseline shapes below `_pilot_assessment/annotations/`; preserve original annotation bytes untouched.
- [x] Generate all seven stream descriptors. X/U share the recognized CSV path and shared-source metadata; missing descriptors use empty paths/checksums, null clock sync/quality, and `units: {}`.
- [x] Generate `manifest.json` with anonymous deterministic source/participant defaults, unclassified task defaults, no task reference, the X master clock, non-synthetic privacy, and `extensions.raw_import` provenance.
- [x] Generate `_pilot_assessment/integrity/checksums.sha256` for exactly the declared stream and canonical annotation paths, sorted by POSIX path.
- [x] Load the result through `ManifestLoader` and `inspect_loaded_ingestion_readiness`; assert `ready_partial`, X/U ready, missing modalities unavailable, and no generated modality artifacts.
- [x] Run the focused raw-ingestion and adjacent manifest/readiness tests.

## Task 4: Managed persistence convergence

- [x] Refactor `SessionImportService.import_bundle` so exact-copy and raw materialization share one finalization function after staging.
- [x] Add:

```python
def inspect_source(self, external_root: str | Path) -> SessionSourceInspection: ...

def import_source(
    self,
    external_root: str | Path,
    *,
    inspected_fingerprint: str,
    transaction_id: str,
    imported_by: str,
) -> SessionImportResult: ...
```

- [x] Preserve `inspect()` and `import_bundle()` byte-for-byte wire behavior for canonical callers.
- [x] On raw import, re-inspect before copying and raise a stable source-changed error when the fingerprint differs.
- [x] Derive raw `session_id` from transaction/source identity so idempotent replay returns the same session while a deliberate new transaction does not silently merge.
- [x] Verify failure recovery removes only project staging, never external source.
- [x] Add persistence tests for successful raw import, exact manifest load, missing descriptors, replay after source deletion, source-changed rejection, and legacy bundle import.
- [x] Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/persistence/test_session_import.py tests/ingestion/test_raw_session.py -q
```

## Task 5: JSON-RPC surface

- [x] Register `session.source.inspect` and `session.source.import` while retaining existing methods.
- [x] Implement responses:

```json
{"source_kind":"simulator_raw","report":null,"raw":{}}
```

and the existing `SessionImportResponse` shape after import.
- [x] Add stable raw-source/import error codes in the session RPC error range.
- [x] Add sidecar tests that create a project, inspect the tiny raw fixture, import with the returned fingerprint, list the managed revision, and verify legacy `session.inspect/import` still work.
- [x] Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/sidecar/test_methods.py tests/sidecar/test_server_subprocess.py -q
```

## Task 6: C# contracts and backend client

- [x] Mirror the Python enums/records in `ProjectSessionRpcContracts.cs`, using nullable `DeclaredUnit` and no editable unit field.
- [x] Register every request/response/nested record in `PilotAssessmentJsonContext`.
- [x] Replace gateway methods with unified source inspect/import while keeping compatibility helpers if existing tests or pages require them.
- [x] Make `ProjectSessionClient` call the new methods and send the inspection fingerprint on import.
- [x] Add serialization fixtures/tests for both source kinds and `declared_unit: null`.
- [x] Run:

```powershell
& 'D:\dotnet\dotnet.exe' test tests\PilotAssessment.Desktop.UnitTests\PilotAssessment.Desktop.UnitTests.csproj -c Debug
& 'D:\dotnet\dotnet.exe' test tests\PilotAssessment.Desktop.ContractTests\PilotAssessment.Desktop.ContractTests.csproj -c Debug
```

## Task 7: WinUI Session workflow

- [x] Use source/session-data picker wording without exposing new technical IDs.
- [x] Store `SessionSourceInspection`, source kind, raw profile display name, and inspected fingerprint in `SessionExplorerViewModel`.
- [x] For canonical sources continue showing the existing readiness cards.
- [x] For raw sources show detected profile and seven modality proposals; display declared units read-only and `未声明`/`Not declared` for null units.
- [x] Never create a unit TextBox/ComboBox and never disable import solely because a unit is absent.
- [x] Import through `session.source.import`, reconcile to the returned managed revision, then show the generated readiness report.
- [x] Update en-US/zh-CN resources for source-kind, profile, generated-manifest explanation, undeclared units, partial import, and errors.
- [x] Update ViewModel tests: picker cancellation is inert, raw inspection enables import with undeclared units, import reconciles, and canonical inspection remains unchanged.

## Task 8: Documentation decisions and focused verification

- [x] Record D-060 and D-061 exactly as approved.
- [x] Amend M6 §6.1, M7 Session Import, `03_SESSION_BUNDLE_SPEC.md`, README, glossary, product docs index and implementation status without changing scientific claims.
- [x] Run Python focused suites and the adjacent lightweight sidecar regression.
- [x] Build the WinUI app:

```powershell
dotnet build src\PilotAssessment.Desktop\PilotAssessment.Desktop.csproj -c Debug -p:Platform=x64
```

- [x] Launch the generated executable, verify a responsive main window and Session page, and leave the final verified instance open for manual acceptance.
- [x] Confirm `git diff --check` and review files touched for this feature.
- [ ] Commit feature slices without staging unrelated dirty M7 files. Deferred because multiple shared files already contain overlapping uncommitted M7 user work.

## Completion boundary

The feature is complete only when a folder containing exactly `streams/` and `annotations/` can be selected in WinUI, inspected without modification, imported into managed storage with a generated valid manifest, reopened as a SessionRevision, and shown as partial when modalities are missing. This proves software workflow only; it does not validate simulator semantics, units, Evidence science or BN calibration.
