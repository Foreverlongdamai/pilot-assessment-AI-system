# M8D Current-System Packaging, Project Portability and Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED EXECUTION MODE is **INLINE**. Execute this plan task-by-task, keep the checkboxes current, and do not dispatch a large subagent fan-out. The user has already approved the written M8D design and preselected inline execution.

**Goal:** Make every formal portable build capture one explicitly selected, saved and closed current system; verify its actual model identity and cardinality; prove whole-project directory portability; and expose system/project compatibility through the existing Diagnostics page.

**Architecture:** A stdlib-only release capture module obtains the existing cross-process writer lock, inspects the source SQLite stores read-only, and creates a consistent canonical copy. The packaged Python runtime rebuilds a clean edit workspace from that captured canonical database. Existing `runtime.status` gains structured system/project compatibility data, and WinUI renders that typed response without owning model logic.

**Tech Stack:** Python 3.11, SQLite backup API, pytest, JSON-RPC 2.0/JSONL, C#/.NET 10, WinUI 3, xUnit, existing M8A/M8B portable builder and verifier.

---

## 1. File map and responsibility boundaries

### New files

- `tools/release/system_model_capture.py` — stdlib-only writer-lock probe, source inspection, clean/dirty checks, schema checks, user-row checks, SQLite-consistent canonical capture and immutable report.
- `tests/release/__init__.py` — release-tool test package marker.
- `tests/release/test_system_model_capture.py` — small disposable-system contract tests for dynamic capture and deterministic refusal paths.
- `docs/product/reviews/2026-07-21-m8d-current-system-packaging-verification.md` — fresh engineering evidence and exact remaining M8C/M8E boundaries.

### Modified files

- `tools/release/build_portable.py` — require `--system-source`, replace starter initialization with current-system capture, create a clean target edit workspace, write v2 dynamic system baseline and manifest summary.
- `tools/release/verify_portable.py` — verify captured facts rather than fixed starter counts and assert runtime diagnostics match the manifest.
- `tools/release/README.md` — document the explicit current-system build command and failure recovery.
- `src/pilot_assessment/model_workspace/hashing.py` — provide one backend model-library identity function for runtime diagnostics.
- `src/pilot_assessment/sidecar/methods.py` — extend `runtime.status` with structured system model and project compatibility objects.
- `tests/sidecar/test_methods.py` — prove diagnostics are dynamic and remain available without a project.
- `src/PilotAssessment.Desktop.Core/Contracts/RunRpcContracts.cs` — typed `SystemModelRuntimeStatus` and `ProjectCompatibilityStatus` records.
- `src/PilotAssessment.Desktop.Core/Contracts/PilotAssessmentJsonContext.cs` — source-generation registrations for the new records.
- `tests/PilotAssessment.Desktop.UnitTests/Contracts/ContractSerializationTests.cs` — snake-case JSON round-trip for the extended runtime status.
- `src/PilotAssessment.Desktop/ViewModels/DiagnosticsViewModel.cs` — localized system/project diagnostic text projection.
- `src/PilotAssessment.Desktop/Views/Pages/DiagnosticsPage.xaml` — visible current-system and project-compatibility regions.
- `src/PilotAssessment.Desktop/Strings/en-US/Resources.resw` and `src/PilotAssessment.Desktop/Strings/zh-CN/Resources.resw` — complete language-switch resources for the new regions.
- `tests/integration/test_m6_managed_assessment.py` — strengthen the existing micro workflow from rename/reopen to close/copy/reopen while preserving Session, RunSnapshot, result and artifacts.
- `docs/product/release/README-PORTABLE.md` — explain captured current system and whole-directory portability.
- `README.md`, `docs/product/11_IMPLEMENTATION_STATUS.md`, M8 roadmap/spec/review indexes and `docs/product/release/KNOWN-LIMITATIONS.md` — record only verified M8D status.

No application Backup/Restore command, archive format, cloud synchronization, source editor or model-science gate is introduced.

## 2. Locked contracts

The implementation uses these exact public release-tool shapes:

```python
@dataclass(frozen=True, slots=True)
class SystemCaptureReport:
    model_library_id: str
    system_format_version: str
    database_schema_version: int
    system_schema_version: int
    starter_seed_id: str
    starter_seed_hash: str
    model_identity_sha256: str
    node_count: int
    scheme_count: int
    source_locator_sha256: str
    source_canonical_sha256: str
    base_fingerprint: str
    baseline_state_hash: str
    user_owned_row_counts: dict[str, int]


INSPECT_SIGNATURE = "inspect_system_source(source_root: Path) -> SystemCaptureReport"
CAPTURE_SIGNATURE = (
    "capture_current_system(source_root: Path, destination_root: Path) "
    "-> SystemCaptureReport"
)
```

The release CLI becomes:

```powershell
.\.tools\uv\uv.exe run python tools\release\build_portable.py `
  --system-source .pilot-assessment-local\system `
  --output-root build\m8d-acceptance `
  --skip-archive
```

The JSON-RPC response remains backward compatible and adds:

```json
{
  "system_model": {
    "model_library_id": "model-library.example",
    "model_identity_sha256": "<64 lowercase hex>",
    "format_version": "0.1.0",
    "database_schema_version": 5,
    "node_count": 54,
    "scheme_count": 2,
    "edit_session_dirty": false,
    "recovery_diagnostics": []
  },
  "project_compatibility": {
    "project_id": "project.example",
    "format_version": "0.1.0",
    "database_schema_version": 5,
    "compatibility": "compatible",
    "recovery_diagnostics": [],
    "recovered_run_count": 0
  }
}
```

When no project is open, `project_compatibility` is `null`. The existing top-level `model_library_id`, `project_open` and `project_id` fields remain present.

## 3. Task sequence

### Task 1: Implement read-only current-system inspection and canonical capture

**Files:**

- Create: `tools/release/system_model_capture.py`
- Create: `tests/release/__init__.py`
- Create: `tests/release/test_system_model_capture.py`

- [x] **Step 1: Write the dynamic capture test**

Create a disposable `SystemApplication`, copy one node and one TaskScheme through `model_edits.workspace`, commit, close, capture it, initialize the destination once with `SystemApplication.open_or_create`, and assert the source and destination identities/counts match exactly:

```python
def test_capture_preserves_saved_dynamic_model_and_rebuilds_clean_workspace(tmp_path: Path) -> None:
    source = tmp_path / "source-system"
    target = tmp_path / "captured-system"
    app = SystemApplication.open_or_create(source, clock=lambda: NOW)
    base_node = app.editable_model.list_nodes()[0]
    base_scheme = app.editable_model.list_schemes()[0]
    app.editable_model.copy_node(
        base_node.node_id,
        transaction_id="tx.m8d.copy-node",
        actor_id="expert.test",
    )
    app.editable_model.copy_scheme(
        base_scheme.scheme_id,
        new_scheme_id="task-scheme.m8d.parallel",
        name_zh=None,
        name_en="M8D Parallel",
        transaction_id="tx.m8d.copy-scheme",
        actor_id="expert.test",
    )
    app.model_edits.commit(transaction_id="tx.m8d.save", actor_id="expert.test")
    expected_nodes = len(app.current_model.list_nodes())
    expected_schemes = len(app.current_model.list_schemes())
    app.close()

    source_report = capture_current_system(source, target)
    captured = SystemApplication.open_or_create(target, clock=lambda: NOW)
    captured.close()
    target_report = inspect_system_source(target)

    assert target_report.model_library_id == source_report.model_library_id
    assert target_report.model_identity_sha256 == source_report.model_identity_sha256
    assert (target_report.node_count, target_report.scheme_count) == (
        expected_nodes,
        expected_schemes,
    )
```

- [x] **Step 2: Run the focused test and confirm the missing module failure**

Run:

```powershell
.\.tools\uv\uv.exe run pytest tests\release\test_system_model_capture.py -q
```

Expected: collection fails because `tools.release.system_model_capture` does not yet exist.

- [x] **Step 3: Implement the stdlib-only capture module**

Implement all of the following, with no dependency on a project or the running sidecar:

```python
SYSTEM_FORMAT_VERSION = "0.1.0"
SUPPORTED_DATABASE_SCHEMA_VERSION = 5
SUPPORTED_SYSTEM_SCHEMA_VERSION = 1
USER_OWNED_SYSTEM_TABLES = (
    "project_metadata",
    "sessions",
    "session_revisions",
    "managed_artifacts",
    "artifact_references",
    "run_preflights",
    "runs",
    "run_results",
    "model_run_preflights_v2",
    "model_run_links_v2",
)

SOURCE_LOCAL_SYSTEM_TABLES = ("legacy_system_model_import_receipts",)


class SystemCaptureError(RuntimeError):
    """A selected system cannot be safely used as a release input."""
```

The module must:

1. resolve and validate `system.json`, `model-library.sqlite3` and `staging/model-edit/workspace.sqlite3`;
2. acquire `.system-writer.lock` non-blockingly with `msvcrt` on Windows and `fcntl` elsewhere;
3. reject any `*.sqlite3-wal` or `*.sqlite3-shm` below the source root;
4. after proving no WAL/SHM exists, open both databases with SQLite URI `mode=ro&immutable=1` so inspection itself cannot create source-side shared-memory files;
5. require `PRAGMA integrity_check == ('ok',)` and an empty `PRAGMA foreign_key_check`;
6. require contiguous schema migrations no newer than `5`, system schema no newer than `1`, locator/database identity agreement and `clean_shutdown=1`;
7. compute the exact edit-session dirty state by reproducing the revision-excluding `_workspace_fingerprint` byte contract from each row's `canonical_json`, and require the canonical revision-aware fingerprint to equal `base_fingerprint`;
8. reject non-zero project/session/run/result/artifact owner row counts; allow the source-local legacy import receipt but securely delete and compact it from the captured target without changing the source;
9. compute model identity from ordered `(kind, id, content_hash, layout_hash)` rows;
10. use `sqlite3.Connection.backup()` to create the destination canonical database while holding the source writer lock;
11. copy canonical locator bytes, create only the target staging directory, and remove a newly created target on any failure;
12. never write to the source system and never seed a fallback.

- [x] **Step 4: Add deterministic refusal tests**

Add five small tests: the four refusal cases below plus one capture case proving a
legacy import receipt is absent (including raw SQLite bytes) from the target while
the source receipt remains unchanged.

```python
def create_closed_system(root: Path) -> Path:
    app = SystemApplication.open_or_create(root, clock=lambda: NOW)
    app.close()
    return root


def test_inspection_rejects_active_writer(tmp_path: Path) -> None:
    root = tmp_path / "system"
    app = SystemApplication.open_or_create(root, clock=lambda: NOW)
    try:
        with pytest.raises(SystemCaptureError, match="close the application"):
            inspect_system_source(root)
    finally:
        app.close()


def test_inspection_rejects_closed_but_dirty_edit_session(tmp_path: Path) -> None:
    root = tmp_path / "system"
    app = SystemApplication.open_or_create(root, clock=lambda: NOW)
    current = app.editable_model.list_nodes()[0]
    proposal = current.model_copy(update={"name_en": f"{current.name_en} Draft"})
    with app.model_edits.database.transaction() as connection:
        app.editable_model.update_node(
            proposal,
            expected_semantic_revision=current.semantic_revision,
            expected_layout_revision=None,
            transaction_id="tx.m8d.dirty",
            actor_id="expert.test",
        )
        app.model_edits.capture_checkpoint(
            connection,
            transaction_id="tx.m8d.dirty",
            method="model.node.update",
        )
    app.close()
    with pytest.raises(SystemCaptureError, match="save or discard"):
        inspect_system_source(root)


def test_inspection_rejects_user_owned_rows(tmp_path: Path) -> None:
    root = create_closed_system(tmp_path / "system")
    database = sqlite3.connect(root / "model-library.sqlite3")
    try:
        database.execute(
            """
            INSERT INTO project_metadata(
                singleton, project_id, format_version, name, created_at,
                clean_shutdown, last_opened_at, last_closed_at
            ) VALUES (1, 'project.forbidden', '0.1.0', 'Forbidden', ?, 1, ?, ?)
            """,
            (NOW.isoformat(), NOW.isoformat(), NOW.isoformat()),
        )
        database.commit()
    finally:
        database.close()
    with pytest.raises(SystemCaptureError, match="user-owned rows"):
        inspect_system_source(root)


def test_inspection_rejects_corrupt_or_future_schema(tmp_path: Path) -> None:
    future = create_closed_system(tmp_path / "future-system")
    database = sqlite3.connect(future / "model-library.sqlite3")
    try:
        database.execute(
            "INSERT INTO schema_migrations(version, name, applied_at) VALUES (6, ?, ?)",
            ("future_schema", NOW.isoformat()),
        )
        database.commit()
    finally:
        database.close()
    with pytest.raises(SystemCaptureError, match="unsupported schema"):
        inspect_system_source(future)

    corrupt = create_closed_system(tmp_path / "corrupt-system")
    (corrupt / "model-library.sqlite3").write_bytes(b"not a SQLite database")
    with pytest.raises(SystemCaptureError, match="integrity|database"):
        inspect_system_source(corrupt)
```

Each test must assert a stable actionable phrase: `close the application`, `save or discard`, `user-owned rows`, or `unsupported schema`/`integrity`.

- [x] **Step 5: Run the focused release tests**

Run:

```powershell
.\.tools\uv\uv.exe run pytest tests\release\test_system_model_capture.py -q
```

Expected: all release-capture tests pass in under a few seconds and no large Session fixture is created.

- [x] **Step 6: Commit Task 1**

```powershell
git add tools/release/system_model_capture.py tests/release
git commit -m "feat: add current system capture contract"
```

### Task 2: Integrate explicit capture into builder, manifest and verifier

**Files:**

- Modify: `tools/release/build_portable.py`
- Modify: `tools/release/verify_portable.py`
- Modify: `tests/release/test_system_model_capture.py`
- Modify: `tools/release/README.md`

- [x] **Step 1: Add a failing baseline/verifier test**

Extend the release test to construct a minimal package root containing the captured system, call the builder's baseline function, write `manifest/system-model-baseline.json`, and call `_verify_system_model_baseline`:

```python
baseline = _system_model_baseline(package_root, capture_report=source_report)
assert baseline["schema_version"] == "pilot-assessment-system-model-baseline-v2"
assert baseline["capture_mode"] == "explicit-current-system"
assert baseline["node_count"] == source_report.node_count
assert baseline["scheme_count"] == source_report.scheme_count
_write_json(package_root / "manifest" / "system-model-baseline.json", baseline)
verified = _verify_system_model_baseline(package_root)
assert verified["model_identity_sha256"] == source_report.model_identity_sha256
```

- [x] **Step 2: Run the focused test and confirm v1/fixed-builder failure**

Run:

```powershell
.\.tools\uv\uv.exe run pytest tests\release\test_system_model_capture.py -q
```

Expected: failure because the builder still initializes the starter and emits baseline v1.

- [x] **Step 3: Make `--system-source` required and remove fallback seeding**

Change argument parsing and build signature to:

```python
parser.add_argument(
    "--system-source",
    type=Path,
    required=True,
    help="Saved and closed system directory to capture into this release.",
)


BUILD_SIGNATURE = (
    "_build(output_root: Path, *, system_source: Path, skip_archive: bool) "
    "-> dict[str, Any]"
)
```

Delete `_initialize_system_model` and the `SYSTEM_MODEL_LIBRARY_ID` fixed identity. Call `capture_current_system(system_source, package_root / "system")`, then invoke packaged Python once to open/close the target system and build a fresh `staging/model-edit/workspace.sqlite3`. Remove only the target lock file after the packaged process exits. Assert the post-initialization model identity/counts equal the capture report.

- [x] **Step 4: Emit manifest-driven baseline v2**

The v2 baseline must include:

```python
{
    "schema_version": "pilot-assessment-system-model-baseline-v2",
    "capture_mode": "explicit-current-system",
    "model_library_id": report.model_library_id,
    "system_format_version": report.system_format_version,
    "database_schema_version": report.database_schema_version,
    "system_schema_version": report.system_schema_version,
    "starter_lineage": {
        "starter_seed_id": report.starter_seed_id,
        "starter_seed_hash": report.starter_seed_hash,
    },
    "model_identity_sha256": model_identity,
    "node_count": node_count,
    "scheme_count": scheme_count,
    "capture_source": {
        "locator_sha256": report.source_locator_sha256,
        "canonical_database_sha256": report.source_canonical_sha256,
    },
    "canonical_database": {
        "path": "system/model-library.sqlite3",
        "sha256": target_canonical_sha256,
    },
    "edit_workspace": {
        "path": "system/staging/model-edit/workspace.sqlite3",
        "sha256": target_workspace_sha256,
        "base_fingerprint": target_base_fingerprint,
        "baseline_state_hash": target_baseline_state_hash,
        "cursor": 0,
        "latest_sequence": 0,
        "dirty": False,
    },
    "user_owned_row_counts": user_owned_row_counts,
}
```

Do not record the absolute `--system-source` path. Add a compact `system_model` summary to `release-manifest.json`, update `build_kind` to `m8d-current-system-engineering`, and retain `system_model_baseline_sha256` for compatibility.

- [x] **Step 5: Update verifier to compare declared facts with packaged facts**

Import the capture module's shared constants and identity helper. Require baseline v2, `capture_mode=explicit-current-system`, a clean target workspace, zero user rows, matching hashes/format/schema/identity/counts and a release-manifest summary identical to those facts. Remove wording and checks that assume a starter model or `53/1`.

In `_sidecar_roundtrip`, compare the existing top-level runtime model-library ID and actual scheme count with the verified baseline, and rename `starter_scheme_count` to `scheme_count`. Task 3 introduces `runtime.status.system_model` and then tightens this to exact structured identity/node/scheme comparison; keeping that assertion with the field-introducing task avoids an impossible pre-field dependency.

- [x] **Step 6: Update release-tool usage documentation**

Document this exact example and the three expected corrective actions:

```powershell
.\.tools\uv\uv.exe run python tools\release\build_portable.py `
  --system-source .pilot-assessment-local\system
```

- close the desktop if the source is locked;
- save all or discard all if the edit session is dirty;
- select another valid system directory if schema/integrity/user-row validation fails.

- [x] **Step 7: Run focused tests and static checks**

Run:

```powershell
.\.tools\uv\uv.exe run pytest tests\release\test_system_model_capture.py -q
.\.tools\uv\uv.exe run ruff check tools\release tests\release
.\.tools\uv\uv.exe run ty check tools\release\system_model_capture.py
```

Expected: all commands pass. If `ty` cannot resolve the script namespace, record that tool limitation and keep pytest/ruff as the required gate; do not alter product import paths solely for `ty`.

- [x] **Step 8: Commit Task 2**

```powershell
git add tools/release tests/release
git commit -m "feat: package the selected current system"
```

### Task 3: Expose system and project compatibility through `runtime.status`

**Files:**

- Modify: `src/pilot_assessment/model_workspace/hashing.py`
- Modify: `src/pilot_assessment/sidecar/methods.py`
- Modify: `tests/sidecar/test_methods.py`
- Modify: `tools/release/verify_portable.py`
- Modify: `tests/release/test_system_model_capture.py`

- [x] **Step 1: Extend the existing no-project sidecar test first**

After obtaining the initial status, assert:

```python
system_model = status["system_model"]
assert system_model["model_library_id"] == status["model_library_id"]
assert len(system_model["model_identity_sha256"]) == 64
assert system_model["node_count"] == 53
assert system_model["scheme_count"] == 1
assert system_model["edit_session_dirty"] is False
assert status["project_compatibility"] is None
```

After the existing scheme copy and `model.edit.commit`, call `runtime.status` again and assert `scheme_count == 2` and the model identity changed. Open a micro project and assert `project_compatibility.compatibility == "compatible"`, format `0.1.0`, schema `5`, and no recovery diagnostics.

- [x] **Step 2: Run the focused test and confirm missing fields**

Run:

```powershell
.\.tools\uv\uv.exe run pytest tests\sidecar\test_methods.py::test_system_model_is_browsable_and_editable_without_an_open_project -q
```

Expected: failure because `system_model` and `project_compatibility` are absent.

- [x] **Step 3: Add one model-library identity helper**

Add this backend API and export it from `hashing.py`:

```python
def model_library_identity(
    nodes: Iterable[ModelNode],
    schemes: Iterable[TaskScheme],
) -> str:
    """Hash ordered current node/scheme semantic and layout identities."""
```

It must use the same `kind + NUL + id + NUL + content_hash + NUL + layout_hash + LF` byte stream as the release baseline.

- [x] **Step 4: Extend `_runtime_status` without removing old fields**

Return `system_model` and nullable `project_compatibility` using current in-memory services and existing descriptors. Derive database schema version from `schema_migrations`; use `system.store.recovery_diagnostics` and `project.recovery_diagnostics`; include `len(app.run_recovery)` without reading raw Session files. Never return an absolute project or system path.

- [x] **Step 5: Run the focused and sidecar contract tests**

Run:

```powershell
.\.tools\uv\uv.exe run pytest `
  tests\sidecar\test_methods.py::test_system_model_is_browsable_and_editable_without_an_open_project `
  tests\sidecar\test_server_subprocess.py -q
```

Expected: all selected tests pass and stdout remains JSONL-only.

Also compare the typed runtime `system_model` with the captured v2 baseline in
the portable verifier. A focused drift test must prove that a manifest/runtime
identity mismatch is rejected.

- [x] **Step 6: Commit Task 3**

```powershell
git add src/pilot_assessment/model_workspace/hashing.py src/pilot_assessment/sidecar/methods.py tests/sidecar/test_methods.py tools/release/verify_portable.py tests/release/test_system_model_capture.py docs/product/plans/2026-07-21-m8d-current-system-packaging-implementation-plan.md
git commit -m "feat: report system and project compatibility"
```

### Task 4: Render typed compatibility diagnostics in WinUI

**Files:**

- Modify: `src/PilotAssessment.Desktop.Core/Contracts/RunRpcContracts.cs`
- Modify: `src/PilotAssessment.Desktop.Core/Contracts/PilotAssessmentJsonContext.cs`
- Modify: `tests/PilotAssessment.Desktop.UnitTests/Contracts/ContractSerializationTests.cs`
- Modify: `src/PilotAssessment.Desktop/ViewModels/DiagnosticsViewModel.cs`
- Modify: `src/PilotAssessment.Desktop/Views/Pages/DiagnosticsPage.xaml`
- Modify: `src/PilotAssessment.Desktop/Strings/en-US/Resources.resw`
- Modify: `src/PilotAssessment.Desktop/Strings/zh-CN/Resources.resw`

- [x] **Step 1: Write the typed JSON round-trip test**

Deserialize an inline `runtime.status` JSON containing both new objects and assert:

```csharp
Assert.Equal(54, status.SystemModel!.NodeCount);
Assert.Equal(2, status.SystemModel.SchemeCount);
Assert.False(status.SystemModel.EditSessionDirty);
Assert.Equal("compatible", status.ProjectCompatibility!.Compatibility);
Assert.Equal(5, status.ProjectCompatibility.DatabaseSchemaVersion);
```

Serialize with `PilotAssessmentJsonContext.Default.RuntimeStatusResponse` and require semantic JSON equivalence.

- [x] **Step 2: Run the contract test and confirm the typed fields are absent**

Run:

```powershell
dotnet test tests\PilotAssessment.Desktop.UnitTests\PilotAssessment.Desktop.UnitTests.csproj `
  -c Debug --filter "FullyQualifiedName~ContractSerializationTests" --nologo
```

Expected: compile failure until the two records and response fields exist.

- [x] **Step 3: Add the typed records and source-generation entries**

Add:

```csharp
public sealed record SystemModelRuntimeStatus(
    string ModelLibraryId,
    string ModelIdentitySha256,
    string FormatVersion,
    int DatabaseSchemaVersion,
    int NodeCount,
    int SchemeCount,
    bool EditSessionDirty,
    string[] RecoveryDiagnostics);

public sealed record ProjectCompatibilityStatus(
    string ProjectId,
    string FormatVersion,
    int DatabaseSchemaVersion,
    string Compatibility,
    string[] RecoveryDiagnostics,
    int RecoveredRunCount);
```

Append nullable `SystemModel` and `ProjectCompatibility` parameters to `RuntimeStatusResponse`, retaining all existing constructor parameters and JSON-null behavior.

- [x] **Step 4: Add localized Diagnostics projections**

Add observable `SystemModelText` and `ProjectCompatibilityText`. Use existing `L(key, fallback)` for every user-facing label. System text shows model library ID, model identity, format/schema and node/scheme counts. Project text shows `not open` or project ID, compatibility, format/schema, recovery diagnostics and recovered-run count. Do not display absolute paths.

Add two visible sections to `DiagnosticsPage.xaml`, and add matching English/Chinese keys such as `Diagnostics_SystemModel`, `Diagnostics_ModelCounts`, `Diagnostics_ProjectCompatibility`, `Diagnostics_ProjectNotOpen`, `Diagnostics_Compatible`, `Diagnostics_RecoveryDiagnostics` and `Diagnostics_RecoveredRuns`.

- [x] **Step 5: Run desktop unit tests and resource parity checks**

Run:

```powershell
dotnet test tests\PilotAssessment.Desktop.UnitTests\PilotAssessment.Desktop.UnitTests.csproj -c Debug --nologo
```

Expected: all tests pass, including contract serialization, accessibility surface and English/Chinese resource parity.

- [x] **Step 6: Commit Task 4**

```powershell
git add src/PilotAssessment.Desktop.Core src/PilotAssessment.Desktop tests/PilotAssessment.Desktop.UnitTests
git commit -m "feat: show model compatibility diagnostics"
```

### Task 5: Prove whole-project directory copy and update product instructions

**Files:**

- Modify: `tests/integration/test_m6_managed_assessment.py`
- Modify: `docs/product/release/README-PORTABLE.md`

- [x] **Step 1: Strengthen the existing micro portability test**

Replace the same-volume directory rename with:

```python
shutil.copytree(project_root, copied_root)
assert project_root.is_dir()
assert copied_root.is_dir()

reopened = ProjectApplication.open(copied_root, system=system, clock=lambda: NOW)
```

Retain the existing assertions for project ID, managed Session revision, exact scheme replay, result equality, result-by-run equality and verified observation artifact bytes. This is a filesystem copy, not a product backup API.

- [x] **Step 2: Run the micro project test**

Run:

```powershell
.\.tools\uv\uv.exe run pytest tests\integration\test_m6_managed_assessment.py -q
```

Expected: one micro test passes without generating large modalities or image sets.

- [x] **Step 3: Update portable user instructions**

Replace “clean starter model” language with “captured current system.” State explicitly:

1. close the app before copying either directory;
2. copy the entire product directory to transfer current `system/` plus `backend/src/` as an independent software copy;
3. copy the entire project root to move Session/RunSnapshot/result/artifacts;
4. opening a copied project uses the destination software's current system for future runs while historical RunSnapshots remain unchanged;
5. no dedicated Backup/Restore feature exists.

- [x] **Step 4: Commit Task 5**

```powershell
git add tests/integration/test_m6_managed_assessment.py docs/product/release/README-PORTABLE.md
git commit -m "test: verify project directory portability"
```

### Task 6: Run one M8D vertical build and close documentation truthfully

**Files:**

- Modify: `README.md`
- Modify: `docs/product/11_IMPLEMENTATION_STATUS.md`
- Modify: `docs/product/plans/2026-07-18-m8-pre-uat-implementation-outline.md`
- Modify: `docs/product/specs/2026-07-21-m8d-current-system-packaging-project-portability-and-diagnostics-design.md`
- Modify: `docs/product/release/KNOWN-LIMITATIONS.md`
- Modify: `docs/product/reviews/README.md`
- Create: `docs/product/reviews/2026-07-21-m8d-current-system-packaging-verification.md`
- Modify: this implementation plan's checkboxes/status notes

- [ ] **Step 1: Verify the current source system without mutating it**

Run the inspector against `.pilot-assessment-local/system` and record only model library ID, identity, node/scheme counts, schema versions and clean/dirty outcome. Do not print or store absolute paths in release manifests.

- [ ] **Step 2: Build one repository-local engineering package from the explicit source**

Run:

```powershell
.\.tools\uv\uv.exe run python tools\release\build_portable.py `
  --system-source .pilot-assessment-local\system `
  --output-root build\m8d-acceptance `
  --skip-archive
```

Expected: builder succeeds; its internal verification copy passes; `system-model-baseline.json`, `release-manifest.json` and runtime diagnostics agree with the source identity and actual dynamic counts. The source system hashes and clean state remain unchanged after the build.

- [ ] **Step 3: Run focused regression gates**

Run:

```powershell
.\.tools\uv\uv.exe run pytest `
  tests\release\test_system_model_capture.py `
  tests\sidecar\test_methods.py::test_system_model_is_browsable_and_editable_without_an_open_project `
  tests\integration\test_m6_managed_assessment.py -q

dotnet test tests\PilotAssessment.Desktop.UnitTests\PilotAssessment.Desktop.UnitTests.csproj -c Debug --nologo
dotnet test tests\PilotAssessment.Desktop.ContractTests\PilotAssessment.Desktop.ContractTests.csproj -c Debug -p:Platform=x64 --nologo
dotnet build src\PilotAssessment.Desktop\PilotAssessment.Desktop.csproj -c Debug -p:Platform=x64 --nologo
```

Expected: all focused Python tests, desktop unit tests, real-sidecar contract tests and x64 desktop build pass. Do not run the entire scientific/anchor suite unless a focused failure points there.

- [ ] **Step 4: Perform privacy and fixed-count scans**

Require no developer absolute path in package text, no user project/Session/result/pilot-camera file, no `53/1` release constraint and no active Backup/Restore promise. Confirm the only packaged SQLite files are the canonical system store and clean edit workspace.

- [ ] **Step 5: Write the verification record and update status**

The verification record must include:

- commit hashes for each implementation slice;
- exact commands and pass counts;
- captured source/target model identity and dynamic node/scheme counts;
- evidence that source hashes/clean state did not change;
- project copy/reopen/replay evidence;
- Diagnostics protocol/UI evidence;
- privacy/fixed-count scans;
- explicit `formal_run_authorized=false`;
- M7 user acceptance, M8C-1 and M8E still pending.

Only then mark M8D engineering implementation complete in README/status/roadmap. Do not mark M8, M7 UAT, M8C-1 or M8E complete.

- [ ] **Step 6: Run documentation and Git checks**

Run:

```powershell
python -m json.tool docs\product\manuals\catalog.json > $null
.\.tools\uv\uv.exe run python tools\documentation\validate_manuals.py --status review
git diff --check
```

Expected: catalog parses, review documentation validates, and Git reports no whitespace errors.

- [ ] **Step 7: Commit M8D completion evidence**

```powershell
git add README.md docs/product
git commit -m "docs: close M8D engineering implementation"
```

## 4. Stop conditions and recovery

- If the selected source is locked or dirty, stop the build, leave the source unchanged and remove only newly created output staging; do not terminate the user's app or discard edits automatically.
- If source inspection fails schema, integrity, locator or user-row checks, do not seed a replacement system.
- If target initialization changes model identity/counts, delete only the new package staging directory and retain the source untouched.
- If Diagnostics contract changes break an older nullable response fixture, keep the new fields nullable and preserve old top-level fields.
- If the full engineering package is expensive, run it once after all focused gates; do not create multiple multi-hundred-megabyte packages for test permutations.
- If any failure suggests scientific starter content is weak, record it as expert calibration scope; do not turn M8D into algorithm validation.

## 5. Plan self-review

### Spec coverage

- Explicit source, no fallback, lock, clean shutdown, dirty edit, schema/integrity, user rows and consistent SQLite capture: Task 1–2.
- Arbitrary model size, dynamic identity/counts and manifest-driven verification: Task 2.
- Clean target edit workspace without source undo history: Task 2.
- Python source remains development-tree-owned: unchanged M8B behavior, verified by existing portable gate in Task 6.
- Whole-project copy/reopen/replay: Task 5.
- System/source/runtime/project Diagnostics: Task 3–4 plus existing source/runtime fields.
- No backup archive/UI/support bundle and no user data in product: Task 5–6 scans and documentation.
- Lightweight evidence only: one disposable system, one existing micro project and one final package build.

### Placeholder scan

The plan contains no unresolved implementation marker. Ellipses appear only in the locked public-signature illustration; every implementation step defines required behavior, files, commands and expected outcomes.

### Type consistency

- Python uses `SystemCaptureReport`, `system_model` and `project_compatibility` consistently across capture, manifest, verifier and JSON-RPC.
- C# uses `SystemModelRuntimeStatus` and `ProjectCompatibilityStatus`, appended as nullable `RuntimeStatusResponse` fields for compatibility.
- The model identity byte stream is identical in release capture, verifier and backend runtime helper.
- Counts are always dynamic and never used as engine constraints.

## 6. Execution handoff

The user already selected **Inline Execution** for this project. After this plan is committed, continue Task 1 through Task 6 in the current task with concise checkpoints; do not pause for a second execution-mode choice.
