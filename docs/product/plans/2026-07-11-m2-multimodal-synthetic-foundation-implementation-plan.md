# M2 Multimodal Synthetic Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a tested M2 ingestion foundation that reads the real combined simulator CSV as shared X/U, validates ideal I/G/EEG/ECG/pilot-camera source contracts, generates a deterministic synthetic multimodal Session Bundle, and emits an `IngestionReadinessReport` that can enter M3 but never authorize a formal assessment run.

**Architecture:** M1 remains the secure manifest/integrity boundary. M2 adds versioned package-resource profiles and trusted adapters that normalize raw source artifacts into an internal `PreparedSession`; Polars is internal only, while Pydantic/JSON Schema define the public readiness report. A deterministic generator creates a real-X/U plus synthetic-modalities bundle, which is re-read through the same M1/M2 path used for external data.

**Tech Stack:** Python 3.11, uv, Pydantic 2, Polars 1.x native CSV/Parquet, Pillow 11/12, pytest, Ruff, ty, JSON Schema Draft 2020-12.

---

## Scope and checkpoints

This plan implements only M2. It does not align `t_ns`, calculate anchors, score evidence, run a Bayesian network, expose JSON-RPC, or build WinUI.

- Slice A: the real combined CSV becomes X/U and returns `ready_partial` while unexported modalities remain explicit.
- Slice B: a two-second generated micro bundle returns `ready` for all seven core modalities and its task reference.
- Slice C: the repository-external 29.01-second CSV generates and validates a local full bundle.

## Locked file structure

~~~text
src/pilot_assessment/
  contracts/
    session.py
    ingestion.py
  ingestion/
    manifest_loader.py
    models.py
    parquet_io.py
    profiles.py
    readiness.py
    adapters/
      __init__.py
      base.py
      registry.py
      profiled_csv.py
      parquet_table.py
      image_sequence.py
      composite.py
    profile_data/
      __init__.py
      m2-profiles-0.1.json
  synthetic/
    __init__.py
    prng.py
    timelines.py
    modalities.py
    generator.py
    __main__.py

tests/
  contracts/test_ingestion.py
  ingestion/test_profiles.py
  ingestion/test_readiness.py
  ingestion/adapters/test_profiled_csv.py
  ingestion/adapters/test_parquet_table.py
  ingestion/adapters/test_image_sequence.py
  ingestion/adapters/test_composite.py
  synthetic/test_prng.py
  synthetic/test_timelines.py
  synthetic/test_modalities.py
  synthetic/test_generator.py
  e2e/test_m2_micro_bundle.py
  e2e/test_real_csv_local.py
~~~

### Task 0: Ratify the reviewed contracts

**Files:**
- Modify: `docs/product/DECISIONS.md`
- Modify: `docs/product/README.md`
- Modify: `docs/product/02_ASSESSMENT_CORE_DESIGN.md`
- Modify: `docs/product/03_SESSION_BUNDLE_SPEC.md`
- Modify: `docs/product/05_BAYESIAN_NETWORK_AND_CPT_DESIGN.md`
- Modify: `docs/product/06_VISUAL_GRAPH_EDITOR_DESIGN.md`
- Modify: `docs/product/07_RUNTIME_PROTOCOL_DESIGN.md`
- Modify: `docs/product/09_VALIDATION_AND_HANDOFF.md`
- Modify: `docs/product/11_IMPLEMENTATION_STATUS.md`
- Modify: `docs/product/GLOSSARY.md`
- Modify: `docs/product/specs/2026-07-11-multimodal-synthetic-foundation-design.md`

- [x] **Step 1: Record D-011 through D-015**

The accepted decisions freeze shared X/U artifacts, synthetic scientific status, ingestion-readiness naming, task-reference indirection, and the 33-node reference graph boundary.

- [x] **Step 2: Reconcile the product documents**

The canonical bundle-local reference path is `references/commanded_path.parquet`, addressed through `task.reference.stream_id=task_reference`; `IngestionReadinessReport` and `RunPreflightReport` are distinct names; the graph editor cannot add context or structural derived-evidence edges to reference-model-v0.1.

- [x] **Step 3: Run the documentation checks**

Run:

~~~powershell
git diff --check
$reviewedDocs=Get-ChildItem -Recurse -File docs/product -Filter '*.md' | Where-Object Name -ne '2026-07-11-m2-multimodal-synthetic-foundation-implementation-plan.md'
$stale=$reviewedDocs | Select-String -Pattern 'Review candidate','\bPreflightReport\b','streams/task_reference'
if($stale){$stale;throw 'Stale M2 terminology remains'}
~~~

Expected: `git diff --check` exits 0; the search has no stale M2 status, old report class, or old physical reference path.

- [x] **Step 4: Commit the contract closure and this plan**

~~~powershell
git add docs/product
git commit -m "docs: reconcile M2 contracts and plan implementation"
~~~

### Task 1: Add locked runtime dependencies

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `tests/test_package_metadata.py`

- [ ] **Step 1: Write the failing dependency smoke test**

Add this behavior to `tests/test_package_metadata.py`:

~~~python
def test_m2_runtime_dependencies_are_importable() -> None:
    import PIL
    import polars

    assert polars.__version__
    assert PIL.__version__
~~~

- [ ] **Step 2: Run RED**

Run:

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/test_package_metadata.py::test_m2_runtime_dependencies_are_importable -v
~~~

Expected: FAIL because Polars and/or Pillow are not project dependencies.

- [ ] **Step 3: Add dependencies through uv**

Run:

~~~powershell
& .\.tools\uv\uv.exe add "polars>=1,<2" "Pillow>=11,<13"
~~~

Expected: `pyproject.toml` and `uv.lock` change; no requirements file is created.

- [ ] **Step 4: Run GREEN and the existing suite**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/test_package_metadata.py -v
& .\.tools\uv\uv.exe run pytest -q
~~~

Expected: all tests pass.

- [ ] **Step 5: Commit**

~~~powershell
git add pyproject.toml uv.lock tests/test_package_metadata.py
git commit -m "build: add M2 columnar and image dependencies"
~~~

### Task 2: Close SessionManifest reference, status, privacy, and shared-artifact contracts

**Files:**
- Modify: `src/pilot_assessment/contracts/session.py`
- Modify: `src/pilot_assessment/schemas/export.py`
- Modify: `src/pilot_assessment/ingestion/manifest_loader.py`
- Modify: `src/pilot_assessment/contracts/__init__.py`
- Modify: `tests/contracts/test_session_manifest.py`
- Modify: `tests/ingestion/test_manifest_loader.py`
- Modify: `tests/schemas/test_schema_export.py`
- Modify: `tests/fixtures/session_manifest_valid.json`
- Regenerate: `schemas/session-manifest-0.1.0.schema.json`

- [ ] **Step 1: Write failing contract tests**

Add focused tests that exercise the wished-for API:

~~~python
def test_bundle_reference_requires_task_reference_stream(manifest_data: dict[str, object]) -> None:
    manifest_data["task"]["reference"] = {
        "source": "bundle",
        "reference_id": "commanded-path-v0.1",
        "stream_id": "task_reference",
    }
    manifest_data["streams"]["task_reference"] = task_reference_descriptor()
    manifest = SessionManifest.model_validate(manifest_data)
    assert manifest.task.reference is not None
    assert manifest.task.reference.stream_id == "task_reference"


@pytest.mark.parametrize("status", ["missing", "not_applicable"])
def test_fileless_statuses_reject_paths(manifest_data: dict[str, object], status: str) -> None:
    stream = manifest_data["streams"]["I"]
    stream.update(
        status=status,
        paths=["streams/scene.mp4"],
        checksums={"streams/scene.mp4": "c" * 64},
    )
    with pytest.raises(ValidationError):
        SessionManifest.model_validate(manifest_data)


def test_non_synthetic_real_biometrics_require_privacy_flag(
    manifest_data: dict[str, object],
) -> None:
    make_present(manifest_data["streams"]["EEG"], "streams/eeg.parquet")
    manifest_data["privacy"]["biometric_modalities_export_pending"] = ["G", "ECG", "pilot_camera"]
    with pytest.raises(ValidationError):
        SessionManifest.model_validate(manifest_data)
~~~

Also add schema symmetry cases for `stream_id`, each status row, duplicate pending modalities, and synthetic-present physiology.

- [ ] **Step 2: Run RED**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/contracts/test_session_manifest.py tests/schemas/test_schema_export.py -v
~~~

Expected: FAIL because `TaskReference.stream_id` and the full cross-field validators do not exist.

- [ ] **Step 3: Implement the contract**

Implement these public shapes in `contracts/session.py`:

~~~python
class TaskReference(StrictContractModel):
    source: Literal["bundle", "model_bundle"]
    reference_id: StableId
    stream_id: StableId | None = None
    extensions: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_source(self) -> Self:
        if self.source == "bundle" and self.stream_id is None:
            raise ValueError("bundle references require stream_id")
        if self.source == "model_bundle" and self.stream_id is not None:
            raise ValueError("model_bundle references must not declare stream_id")
        return self
~~~

Extend `StreamDescriptor.validate_status_and_files()` with the approved five-row matrix. Extend `SessionManifest.validate_stream_inventory()` to resolve bundle references to modality `task_reference`; require `present/invalid` paths below `references/`, while preserving fileless `export_pending/missing/not_applicable`; validate privacy/pending consistency. Keep model-bundle references backward-compatible.

Update schema runtime invariants and conditional status rules so JSON Schema rejects every value rejected by Pydantic.

- [ ] **Step 4: Run GREEN and regenerate schema**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/contracts/test_session_manifest.py tests/schemas/test_schema_export.py -v
& .\.tools\uv\uv.exe run python -m pilot_assessment.schemas.export
& .\.tools\uv\uv.exe run pytest tests/schemas/test_schema_export.py -v
~~~

Expected: contract and schema tests pass; committed schema equals deterministic export.

- [ ] **Step 5: Write and verify shared X/U loader tests**

Add tests that construct X/U descriptors with the same exact path and assert:

~~~python
loaded = ManifestLoader().load(bundle_root)
assert loaded.declared_reference_count == 6
assert loaded.unique_artifact_count == 5
assert loaded.verified_paths.count("streams/simulator.csv") == 1
~~~

Negative tests must change exactly one of digest, format, schema ID, shared source ID, view ID, case-only spelling, owner pair, or artifact role.

Run the new tests and confirm RED because M1 currently rejects every duplicate path.

- [ ] **Step 6: Implement safe physical-artifact grouping**

Replace untyped `(path, kind)` tuples with an immutable declaration:

~~~python
@dataclass(frozen=True, slots=True)
class DeclaredArtifactReference:
    relative_path: str
    role: Literal["stream", "reference", "annotation", "integrity"]
    owner_id: str
    digest: str | None
    format: str | None
    schema_id: str | None
    shared_source_id: str | None
    view_id: str | None
~~~

Validate that only the owner set `{X, U}` may share an exact path and that every D-011 field matches. Reject case-fold aliases and cross-role collisions. Deduplicate only after validation, then resolve/hash by unique path. Include `invalid` stream paths in integrity verification.

- [ ] **Step 7: Run GREEN and commit**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/contracts/test_session_manifest.py tests/ingestion/test_manifest_loader.py tests/schemas/test_schema_export.py -v
git add src/pilot_assessment/contracts src/pilot_assessment/ingestion/manifest_loader.py src/pilot_assessment/schemas tests schemas/session-manifest-0.1.0.schema.json
git commit -m "feat: support shared XU and bundle task references"
~~~

### Task 3: Define the public ingestion-readiness contract

**Files:**
- Create: `src/pilot_assessment/contracts/ingestion.py`
- Modify: `src/pilot_assessment/contracts/__init__.py`
- Modify: `src/pilot_assessment/schemas/export.py`
- Create: `tests/contracts/test_ingestion.py`
- Modify: `tests/schemas/test_schema_export.py`
- Create: `tests/fixtures/ingestion_readiness_ready.json`
- Create: `schemas/ingestion-readiness-report-0.1.0.schema.json`

- [ ] **Step 1: Write failing DTO tests**

~~~python
def test_ready_report_never_authorizes_a_formal_run() -> None:
    report = IngestionReadinessReport.model_validate(ready_report_data())
    assert report.disposition is ReadinessDisposition.READY
    assert report.can_continue_to_synchronization is True
    assert report.formal_run_authorized is False
    assert set(report.stream_results) == set(CORE_MODALITIES)
    assert report.task_reference_result is not None


def test_formal_run_authorized_cannot_be_true() -> None:
    candidate = ready_report_data()
    candidate["formal_run_authorized"] = True
    with pytest.raises(ValidationError):
        IngestionReadinessReport.model_validate(candidate)
~~~

- [ ] **Step 2: Run RED**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/contracts/test_ingestion.py -v
~~~

Expected: import failure because the contract module does not exist.

- [ ] **Step 3: Implement strict DTOs**

Create enums `StreamReadiness` and `ReadinessDisposition`, then implement:

~~~python
class StreamReadinessResult(StrictContractModel):
    modality: StableId
    declared_status: StreamStatus
    required_for_import: StrictBool
    readiness: StreamReadiness
    adapter_id: StableId | None = None
    adapter_version: StableId | None = None
    source_paths: tuple[BundleRelativePath, ...]
    source_checksums: dict[BundleRelativePath, Sha256Digest]
    normalized_schema_id: StableId | None = None
    row_count: NonNegativeInt | None = None
    artifact_row_counts: dict[StableId, NonNegativeInt] = Field(default_factory=dict)
    source_time_start_s: NonNegativeFiniteFloat | None = None
    source_time_end_s: NonNegativeFiniteFloat | None = None
    observed_sample_rate_hz: PositiveFiniteFloat | None = None
    canonical_fields: tuple[StableId, ...] = ()
    units: dict[str, str] = Field(default_factory=dict)
    quality_summary: dict[str, JsonValue] = Field(default_factory=dict)
    assumptions: tuple[StableId, ...] = ()
    issues: tuple[DomainErrorData, ...] = ()

    @model_validator(mode="after")
    def validate_readiness_payload(self) -> Self:
        if self.readiness is StreamReadiness.READY:
            if self.adapter_id is None or self.adapter_version is None:
                raise ValueError("ready results require adapter identity")
            if self.row_count is None or self.normalized_schema_id is None:
                raise ValueError("ready results require normalized content summary")
        if self.readiness in {
            StreamReadiness.UNAVAILABLE,
            StreamReadiness.UNSUPPORTED,
            StreamReadiness.NOT_APPLICABLE,
        }:
            claimed = (
                self.adapter_id,
                self.adapter_version,
                self.normalized_schema_id,
                self.row_count,
                self.source_time_start_s,
                self.source_time_end_s,
                self.observed_sample_rate_hz,
            )
            if any(value is not None for value in claimed) or self.artifact_row_counts:
                raise ValueError("uninspected results must not claim normalized content")
        return self


class IngestionReadinessReport(StrictContractModel):
    contract_version: Literal["0.1.0"]
    validation_scope: Literal["inspect_only_ingestion_content_v1"]
    session_id: StableId
    manifest_version: BundleSchemaVersion
    disposition: ReadinessDisposition
    can_continue_to_synchronization: StrictBool
    formal_run_authorized: Literal[False]
    stream_results: dict[StableId, StreamReadinessResult]
    task_reference_result: StreamReadinessResult | None
    global_issues: tuple[DomainErrorData, ...] = ()
    deferred_checks: tuple[StableId, ...]
    source_snapshot_fingerprint: Sha256Digest

    @model_validator(mode="after")
    def validate_disposition(self) -> Self:
        if set(self.stream_results) != set(CORE_MODALITIES):
            raise ValueError("readiness report requires exactly seven core modalities")
        if any(key != result.modality for key, result in self.stream_results.items()):
            raise ValueError("stream result keys must match modality")
        if self.task_reference_result is not None and self.task_reference_result.modality != "task_reference":
            raise ValueError("task_reference_result must describe task_reference")
        results = list(self.stream_results.values())
        if self.task_reference_result is not None:
            results.append(self.task_reference_result)
        blocked = any(
            result.required_for_import
            and result.readiness is not StreamReadiness.READY
            for result in results
        )
        degraded = any(
            result.readiness
            in {StreamReadiness.UNAVAILABLE, StreamReadiness.INVALID, StreamReadiness.UNSUPPORTED}
            for result in self.stream_results.values()
        )
        if self.task_reference_result is not None:
            degraded = degraded or self.task_reference_result.readiness is not StreamReadiness.READY
        expected = (
            ReadinessDisposition.BLOCKED
            if blocked
            else ReadinessDisposition.READY_PARTIAL
            if degraded
            else ReadinessDisposition.READY
        )
        if self.disposition is not expected:
            raise ValueError("disposition must match stream readiness")
        if self.can_continue_to_synchronization == blocked:
            raise ValueError("blocked reports cannot continue to synchronization")
        return self
~~~

`READY` is valid only when every applicable core result is ready and the declared bundle reference is ready; `READY_PARTIAL` covers optional unavailable/invalid/unsupported inputs; `BLOCKED` covers any non-ready required input. Add negative tests for contradictory disposition/continuation flags, wrong task-reference modality, and payload fields that falsely claim an adapter inspected an unavailable stream.

- [ ] **Step 4: Export and test JSON Schema**

Add the third schema to `render_schemas()`, validate Draft 2020-12, compare Pydantic/Schema negative cases, and regenerate committed files.

~~~powershell
& .\.tools\uv\uv.exe run python -m pilot_assessment.schemas.export
& .\.tools\uv\uv.exe run pytest tests/contracts/test_ingestion.py tests/schemas/test_schema_export.py -v
~~~

Expected: all tests pass and the export contains exactly three schema files.

- [ ] **Step 5: Commit**

~~~powershell
git add src/pilot_assessment/contracts src/pilot_assessment/schemas tests schemas
git commit -m "feat: define ingestion readiness report contract"
~~~

### Task 4: Add internal stream models, versioned profiles, and trusted adapter registry

**Files:**
- Create: `src/pilot_assessment/ingestion/models.py`
- Create: `src/pilot_assessment/ingestion/profiles.py`
- Create: `src/pilot_assessment/ingestion/profile_data/__init__.py`
- Create: `src/pilot_assessment/ingestion/profile_data/m2-profiles-0.1.json`
- Create: `src/pilot_assessment/ingestion/adapters/__init__.py`
- Create: `src/pilot_assessment/ingestion/adapters/base.py`
- Create: `src/pilot_assessment/ingestion/adapters/registry.py`
- Create: `tests/ingestion/test_profiles.py`

- [ ] **Step 1: Write failing profile and registry tests**

~~~python
def test_packaged_m2_profiles_load_with_unique_schema_ids() -> None:
    catalog = load_builtin_profiles()
    assert "cranfield-simulator-combined-csv-raw-v0.1" in catalog
    assert "eeg-source-bundle-v0.1" in catalog


def test_registry_uses_exact_trusted_keys() -> None:
    registry = AdapterRegistry()
    registry.register(FakeAdapter())
    assert registry.resolve("csv", "fixture-v0.1") is not None
    with pytest.raises(AdapterNotFoundError):
        registry.resolve("csv", "unregistered-v0.1")
~~~

- [ ] **Step 2: Run RED**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/ingestion/test_profiles.py -v
~~~

Expected: import failure because profiles and registry do not exist.

- [ ] **Step 3: Implement focused internal units**

Use frozen dataclasses for Polars-bearing objects:

~~~python
@dataclass(frozen=True, slots=True)
class NormalizedStream:
    modality: str
    schema_id: str
    clock_id: str
    source_timestamp_column: str
    primary_table_role: str
    tables: Mapping[str, pl.DataFrame]
    json_artifacts: Mapping[str, Mapping[str, JsonValue]]
    file_artifacts: Mapping[str, tuple[str, ...]]
    source_paths: tuple[str, ...]
    source_checksums: Mapping[str, str]

    @property
    def primary_table(self) -> pl.DataFrame:
        return self.tables[self.primary_table_role]


@dataclass(frozen=True, slots=True)
class PreparedSession:
    streams: Mapping[str, NormalizedStream]
    context: Mapping[str, JsonValue]
    task_reference: NormalizedStream | None
~~~

Define the adapter boundary in `adapters/base.py` in the same task:

~~~python
@dataclass(frozen=True, slots=True)
class AdapterRequest:
    bundle_root: Path
    descriptors: Mapping[str, StreamDescriptor]
    source_paths: tuple[str, ...]
    verified_digests: Mapping[str, str]
    profile: ArtifactProfile


@dataclass(frozen=True, slots=True)
class AdapterArtifactSummary:
    role: str
    paths: tuple[str, ...]
    row_count: int | None


@dataclass(frozen=True, slots=True)
class AdapterResult:
    streams: Mapping[str, NormalizedStream]
    context: Mapping[str, JsonValue]
    artifact_summaries: tuple[AdapterArtifactSummary, ...]
    issues: tuple[DomainErrorData, ...] = ()


class AdapterInspectionError(Exception):
    def __init__(self, issue: DomainErrorData) -> None:
        super().__init__(issue.message)
        self.issue = issue


class ArtifactAdapter(Protocol):
    adapter_id: str
    adapter_version: str
    keys: frozenset[tuple[str, str]]

    def inspect(self, request: AdapterRequest) -> AdapterResult: ...
~~~

The protocol ellipsis is Python's required stub body, not an omitted implementation. Add tests that an adapter result can retain both gaze tables, both ECG tables, EEG samples plus sidecar JSON, and image path references without embedding pixels.

Define strict Pydantic profile DTOs for exact columns/dtypes, sort keys, rate, artifact roles, header mappings, context columns, and unit checks. Load only the packaged JSON through `importlib.resources`; reject duplicate schema IDs. `AdapterRegistry` accepts concrete trusted adapter instances and never imports a class named by a manifest.

- [ ] **Step 4: Test installed-resource behavior**

Build a wheel, install it into an isolated uv environment, and import the profile resource:

~~~powershell
& .\.tools\uv\uv.exe build
& .\.tools\uv\uv.exe run pytest tests/ingestion/test_profiles.py -v
$wheel=(Get-ChildItem -LiteralPath dist -Filter '*.whl' | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
& .\.tools\uv\uv.exe run --isolated --no-project --with $wheel python -c "from pilot_assessment.ingestion.profiles import load_builtin_profiles; print(len(load_builtin_profiles()))"
~~~

Expected: profile tests pass from source, the package build succeeds, and the isolated wheel process prints a positive profile count.

- [ ] **Step 5: Commit**

~~~powershell
git add src/pilot_assessment/ingestion tests/ingestion/test_profiles.py
git commit -m "feat: add versioned ingestion profiles and registry"
~~~

### Task 5: Implement the shared X/U profiled CSV adapter

**Files:**
- Create: `src/pilot_assessment/ingestion/adapters/profiled_csv.py`
- Create: `tests/ingestion/adapters/test_profiled_csv.py`
- Create: `tests/fixtures/m2/simulator_micro.csv`

- [ ] **Step 1: Write the valid-case failing test**

~~~python
def test_combined_csv_produces_x_u_and_context(csv_request: AdapterRequest) -> None:
    result = ProfiledCsvAdapter().inspect(csv_request)
    assert set(result.streams) == {"X", "U"}
    assert result.streams["X"].primary_table.height == 201
    assert result.streams["U"].primary_table["control.longitudinal_raw"].min() == -100.0
    assert result.context["context.time_delay_s"] == 0.2
    assert "Time Delay s" not in result.streams["X"].primary_table.columns
    assert result.streams["X"].primary_table.schema["source_row_index"] == pl.UInt64
~~~

- [ ] **Step 2: Run RED**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/ingestion/adapters/test_profiled_csv.py::test_combined_csv_produces_x_u_and_context -v
~~~

Expected: import failure because the adapter does not exist.

- [ ] **Step 3: Implement minimal valid parsing**

The adapter must strict-decode UTF-8/UTF-8-SIG, use `csv.reader` to preserve and validate raw headers/row width, then use `pl.read_csv` with explicit schema overrides. It must add stable UInt64 `source_row_index`, map normalized headers from the packaged profile, preserve `source_time_s`, create independent X/U DataFrames, and promote constant experiment-condition columns to canonical `context.*` keys.

The public adapter shape is:

~~~python
class ProfiledCsvAdapter:
    adapter_id = "profiled-csv"
    adapter_version = "0.1.0"
    keys = frozenset({("csv", "cranfield-simulator-combined-csv-raw-v0.1")})

    def inspect(self, request: AdapterRequest) -> AdapterResult:
        profile = request.profile
        source_path = request.bundle_root.joinpath(*request.source_paths[0].split("/"))
        payload = source_path.read_bytes()
        raw_headers = validate_csv_structure(payload, profile)
        frame = pl.read_csv(
            BytesIO(payload),
            has_header=True,
            schema_overrides={name: pl.Float64 for name in raw_headers},
            row_index_name="source_row_index",
            try_parse_dates=False,
            truncate_ragged_lines=False,
            raise_if_empty=True,
        ).with_columns(pl.col("source_row_index").cast(pl.UInt64))
        canonical = normalize_and_validate_csv(frame, raw_headers, profile)
        streams = build_xu_views(canonical, request.descriptors, profile)
        context = extract_constant_context(canonical, profile)
        return AdapterResult(streams=streams, context=context, artifact_summaries=())
~~~

The implementation body must return typed `DomainErrorData` through `AdapterInspectionError`; it must not expose Polars in public contracts.

- [ ] **Step 4: Add one failing test per quality rule, then make each green**

Cover malformed row width, trim collision, missing required column, non-numeric value, null, NaN/Inf, duplicate/out-of-order time, 100 Hz tolerance, gap, non-constant context, and m/s↔kt warning/error. For each case: write the fixture mutation, run the single test to observe the expected RED, add the smallest validation branch, then rerun GREEN.

- [ ] **Step 5: Run the adapter suite and commit**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/ingestion/adapters/test_profiled_csv.py -v
& .\.tools\uv\uv.exe run ruff check src/pilot_assessment/ingestion tests/ingestion/adapters/test_profiled_csv.py
git add src/pilot_assessment/ingestion tests/ingestion/adapters tests/fixtures/m2/simulator_micro.csv
git commit -m "feat: ingest combined simulator CSV as shared XU"
~~~

### Task 6: Implement exact Parquet and JSON sidecar validation

**Files:**
- Create: `src/pilot_assessment/ingestion/parquet_io.py`
- Create: `src/pilot_assessment/ingestion/adapters/parquet_table.py`
- Create: `tests/ingestion/adapters/test_parquet_table.py`

- [ ] **Step 1: Write failing exact-schema tests**

~~~python
def test_parquet_table_requires_profile_schema_id(tmp_path: Path, gaze_profile: TableProfile) -> None:
    path = tmp_path / "gaze_samples.parquet"
    write_test_parquet(path, valid_gaze_frame(), metadata={"schema_id": "wrong-v0.1"})
    with pytest.raises(AdapterInspectionError) as caught:
        inspect_parquet_table(path, gaze_profile)
    assert caught.value.issue.error_code == "STREAM_SCHEMA_MISMATCH"
~~~

Add independent cases for ordered columns, exact Polars dtype, required nulls, sort-key uniqueness/order, finite values, normalized ranges, and observed sample rate.

- [ ] **Step 2: Run RED**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/ingestion/adapters/test_parquet_table.py -v
~~~

Expected: import failure because the table inspector does not exist.

- [ ] **Step 3: Implement the isolated Parquet wrapper**

Use native Polars only:

~~~python
def write_profiled_parquet(frame: pl.DataFrame, path: Path, schema_id: str) -> None:
    frame.write_parquet(
        path,
        compression="zstd",
        compression_level=3,
        statistics=True,
        row_group_size=65_536,
        metadata={"schema_id": schema_id, "contract_version": "0.1.0"},
    )


def inspect_parquet_table(path: Path, profile: TableProfile) -> pl.DataFrame:
    metadata = pl.read_parquet_metadata(path)
    schema = pl.read_parquet_schema(path)
    if metadata.get("schema_id") != profile.schema_id:
        raise AdapterInspectionError(schema_mismatch_issue(path, profile.schema_id))
    if list(schema.items()) != list(profile.polars_schema().items()):
        raise AdapterInspectionError(dtype_mismatch_issue(path, schema, profile))
    frame = pl.read_parquet(path, schema=profile.polars_schema(), missing_columns="raise")
    validate_required_values(frame, profile)
    validate_sort_key(frame, profile)
    validate_table_ranges_and_rate(frame, profile)
    return frame
~~~

Put `write_profiled_parquet` in `ingestion/parquet_io.py`; `adapters/parquet_table.py` imports it only in tests, and `synthetic/modalities.py` imports the same writer for generation. This is the single metadata/compression/row-group authority. Keep experimental metadata read/write calls behind these two focused modules and pin them through `uv.lock` plus golden tests.

- [ ] **Step 4: Add strict sidecar validation**

Test and implement strict UTF-8 JSON parsing with duplicate-key rejection for `eeg_sidecar.json`; validate schema ID, channel order/units, rate, clock ID, generator/seed, and `synthetic_not_neurophysiological=true` for synthetic data.

- [ ] **Step 5: Run GREEN and commit**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/ingestion/adapters/test_parquet_table.py -v
git add src/pilot_assessment/ingestion/parquet_io.py src/pilot_assessment/ingestion/adapters/parquet_table.py tests/ingestion/adapters/test_parquet_table.py
git commit -m "feat: validate profiled Parquet and sidecar artifacts"
~~~

### Task 7: Implement image-sequence and composite stream validation

**Files:**
- Create: `src/pilot_assessment/ingestion/adapters/image_sequence.py`
- Create: `src/pilot_assessment/ingestion/adapters/composite.py`
- Modify: `src/pilot_assessment/ingestion/adapters/__init__.py`
- Create: `tests/ingestion/adapters/test_image_sequence.py`
- Create: `tests/ingestion/adapters/test_composite.py`

- [ ] **Step 1: Write failing PNG safety tests**

~~~python
def test_scene_image_must_match_index_dimensions(scene_artifacts: SceneArtifacts) -> None:
    scene_artifacts.index = scene_artifacts.index.with_columns(pl.lit(65).alias("width"))
    with pytest.raises(AdapterInspectionError) as caught:
        inspect_image_sequence(scene_artifacts)
    assert caught.value.issue.error_code == "STREAM_SCHEMA_MISMATCH"
~~~

Add tests for RGB8, exact synthetic sizes, missing/undeclared images, animated images, ancillary metadata, path traversal, and the 16-megapixel ceiling.

- [ ] **Step 2: Run RED, implement bounded image inspection, run GREEN**

Open each image with Pillow under decompression-bomb warnings-as-errors; call `verify()`, reopen for mode/size/frame count, and close immediately. Keep only index rows and paths in `PreparedSession`; never retain decoded pixels.

- [ ] **Step 3: Write failing composite-role tests**

Test exact/prefix `artifact_roles`, one-role-per-path, required roles, and no filename guessing. Then test scene frame↔AOI, EEG channel↔sidecar, ECG peak range, and camera index↔PNG.

- [ ] **Step 4: Implement composite adapters and cross-file checks**

Register trusted composite adapters for:

~~~python
COMPOSITE_KEYS = {
    ("image_sequence+parquet_index", "vr-scene-source-bundle-v0.1"),
    ("parquet", "gaze-source-bundle-v0.1"),
    ("parquet+json_sidecar", "eeg-source-bundle-v0.1"),
    ("parquet", "ecg-source-bundle-v0.1"),
    ("image_sequence+parquet_index", "pilot-camera-source-bundle-v0.1"),
}
~~~

The single-file task reference is handled directly by the profiled Parquet adapter with schema ID `task-reference-path-raw-v0.1`.

- [ ] **Step 5: Run GREEN and commit**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/ingestion/adapters/test_image_sequence.py tests/ingestion/adapters/test_composite.py -v
git add src/pilot_assessment/ingestion/adapters tests/ingestion/adapters
git commit -m "feat: validate image sequences and composite streams"
~~~

### Task 8: Implement deterministic synthetic primitives and modality writers

**Files:**
- Create: `src/pilot_assessment/synthetic/__init__.py`
- Create: `src/pilot_assessment/synthetic/prng.py`
- Create: `src/pilot_assessment/synthetic/timelines.py`
- Create: `src/pilot_assessment/synthetic/modalities.py`
- Create: `tests/synthetic/test_prng.py`
- Create: `tests/synthetic/test_timelines.py`
- Create: `tests/synthetic/test_modalities.py`

- [ ] **Step 1: Write the PRNG golden test**

~~~python
def test_sha256_counter_prng_has_frozen_golden_values() -> None:
    assert uniform53(20260711, "EEG", "Fp1", 0, 0).hex() == "0x1.6af3eebf91787p-2"
    assert triangular_noise(20260711, "EEG", "Fp1", 0).hex() == "-0x1.4d47ba0000000p-2"
~~~

The constants above come from the accepted byte formula and are independent of production code. Observe RED because the production functions are absent.

- [ ] **Step 2: Implement the exact hash-counter algorithm**

Use SHA-256 over the approved prefix, ASCII seed/modality/channel, big-endian index/lane; convert the high 53 bits with `(m+0.5)/2**53`; combine lanes as `u0+u1-1`; quantize output through little-endian IEEE-754 Float32 packing.

- [ ] **Step 3: Write and implement timeline tests**

~~~python
def test_source_grid_includes_the_last_sample_not_after_duration() -> None:
    grid = source_grid(duration_s=2.0, sample_rate_hz=120.0)
    assert len(grid) == 241
    assert grid[0] == 0.0
    assert grid[-1] == 2.0
~~~

Also freeze offset/drift mapping and in-session boundary cases.

- [ ] **Step 4: Write and implement modality generator tests**

Generate pure Polars tables for scene/AOI, gaze/fixations, EEG/sidecar, ECG/R-peaks, camera index, commanded reference, and annotation JSON. Assert exact columns/dtypes/rates, deterministic values, valid foreign keys, and the synthetic flags. Write PNGs as RGB8 with compression level 9, `optimize=False`, and no ancillary metadata.

- [ ] **Step 5: Run GREEN and commit**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/synthetic/test_prng.py tests/synthetic/test_timelines.py tests/synthetic/test_modalities.py -v
git add src/pilot_assessment/synthetic tests/synthetic
git commit -m "feat: add deterministic multimodal synthetic primitives"
~~~

### Task 9: Build the deterministic full-bundle generator

**Files:**
- Create: `src/pilot_assessment/synthetic/generator.py`
- Create: `src/pilot_assessment/synthetic/__main__.py`
- Modify: `src/pilot_assessment/synthetic/__init__.py`
- Modify: `pyproject.toml`
- Create: `tests/synthetic/test_generator.py`

- [ ] **Step 1: Write the failing micro-bundle test**

~~~python
def test_generator_writes_a_complete_deterministic_bundle(
    tmp_path: Path,
    simulator_micro_csv: Path,
) -> None:
    first = generate_synthetic_bundle(simulator_micro_csv, tmp_path / "first", seed=20260711)
    second = generate_synthetic_bundle(simulator_micro_csv, tmp_path / "second", seed=20260711)
    assert snapshot(first) == snapshot(second)
    manifest = SessionManifest.model_validate_json((first / "manifest.json").read_bytes())
    assert manifest.streams["X"].paths == manifest.streams["U"].paths
    assert manifest.task.reference.stream_id == "task_reference"
    assert manifest.streams["task_reference"].paths == ["references/commanded_path.parquet"]
    assert manifest.streams["task_reference"].schema_id == "task-reference-path-raw-v0.1"
    assert all(manifest.streams[key].status is StreamStatus.PRESENT for key in CORE_MODALITIES)
    assert manifest.privacy.classification == "synthetic-test-data"
    assert manifest.privacy.contains_biometric_data is False
    assert manifest.privacy.biometric_modalities_export_pending == []
    assert manifest.extensions["synthetic"]["scientific_validation_status"] == "not_supported"
    assert manifest.extensions["synthetic"]["seed"] == 20260711
    assert manifest.extensions["synthetic"]["lock_fingerprint"]
    assert manifest.extensions["synthetic"]["source_xu_sha256"] == hashlib.sha256(
        simulator_micro_csv.read_bytes()
    ).hexdigest()
    expected_clocks = {
        "X": (0, 0.0),
        "U": (0, 0.0),
        "I": (4_000_000, 0.0),
        "G": (7_000_000, 20.0),
        "EEG": (-12_000_000, -15.0),
        "ECG": (9_000_000, 10.0),
        "pilot_camera": (15_000_000, 0.0),
    }
    for modality, (offset_ns, drift_ppm) in expected_clocks.items():
        assert_clock_truth(manifest, modality, offset_ns=offset_ns, drift_ppm=drift_ppm)
    assert set(manifest.streams["I"].metadata["artifact_roles"]) == {
        "frame_index",
        "aoi_instances",
        "frame_images",
    }
~~~

- [ ] **Step 2: Run RED**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/synthetic/test_generator.py::test_generator_writes_a_complete_deterministic_bundle -v
~~~

Expected: import failure because the generator does not exist.

- [ ] **Step 3: Implement generation and canonical integrity**

The generator must:

1. copy the source CSV byte-for-byte to `streams/simulator.csv`;
2. derive duration/control activity through the profiled CSV parser;
3. write all synthetic artifacts and annotations;
4. derive a stable session ID from source hash, generator ID, and seed;
5. use fixed or explicit RFC 3339 `created_at`;
6. build all seven present descriptors plus `task_reference`;
7. write one checksum line per unique physical file;
8. write canonical UTF-8 JSON with sorted keys and LF;
9. run `ManifestLoader` on the result before returning; Task 10 upgrades this final self-check to include M2 readiness as soon as the orchestrator exists;
10. refuse output outside the caller-selected directory, path counts above loader limits, existing non-empty output, network access, system time, random UUIDs, or host metadata.

- [ ] **Step 4: Add CLI and negative tests**

Expose:

~~~powershell
& .\.tools\uv\uv.exe run python -m pilot_assessment.synthetic --xu-csv tests/fixtures/m2/simulator_micro.csv --output local_data/m2-micro --seed 20260711
~~~

Test non-empty output, bad CSV, path budget, changed seed, and source bytes unchanged.

- [ ] **Step 5: Run GREEN and commit**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/synthetic/test_generator.py -v
git add src/pilot_assessment/synthetic tests/synthetic/test_generator.py pyproject.toml uv.lock
git commit -m "feat: generate deterministic synthetic session bundles"
~~~

### Task 10: Orchestrate ingestion readiness

**Files:**
- Create: `src/pilot_assessment/ingestion/readiness.py`
- Modify: `src/pilot_assessment/ingestion/__init__.py`
- Modify: `src/pilot_assessment/synthetic/generator.py`
- Modify: `tests/synthetic/test_generator.py`
- Create: `tests/ingestion/test_readiness.py`

- [ ] **Step 1: Write failing status-matrix tests**

~~~python
def test_minimal_xu_is_ready_partial_and_can_enter_sync(minimal_xu_bundle: Path) -> None:
    outcome = inspect_ingestion_readiness(minimal_xu_bundle)
    assert outcome.report.disposition is ReadinessDisposition.READY_PARTIAL
    assert outcome.report.stream_results["X"].readiness is StreamReadiness.READY
    assert outcome.report.stream_results["I"].readiness is StreamReadiness.UNAVAILABLE
    assert outcome.report.can_continue_to_synchronization is True
    assert outcome.report.formal_run_authorized is False
~~~

Parametrize present/export_pending/missing/invalid/not_applicable and required/optional combinations. Test deterministic issue ordering and the separate task-reference result.

- [ ] **Step 2: Run RED**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/ingestion/test_readiness.py -v
~~~

Expected: import failure because readiness orchestration does not exist.

- [ ] **Step 3: Implement orchestration**

Implement:

~~~python
@dataclass(frozen=True, slots=True)
class IngestionReadinessOutcome:
    report: IngestionReadinessReport
    prepared_session: PreparedSession | None


def inspect_ingestion_readiness(
    bundle_root: Path,
    *,
    registry: AdapterRegistry | None = None,
) -> IngestionReadinessOutcome:
    loaded = ManifestLoader().load(bundle_root)
    active_registry = registry or build_default_registry()
    profiles = load_builtin_profiles()
    adapter_results = inspect_declared_stream_groups(loaded, active_registry, profiles)
    prepared = build_prepared_session(loaded.manifest, adapter_results)
    cross_stream_issues = validate_cross_stream_links(prepared)
    report = build_readiness_report(loaded, adapter_results, cross_stream_issues)
    return IngestionReadinessOutcome(
        report=report,
        prepared_session=None if report.disposition is ReadinessDisposition.BLOCKED else prepared,
    )
~~~

Use real in-process fake adapters only for narrow failure injection; normal tests use actual adapters. Convert adapter exceptions to stable `DomainErrorData`. Re-hash each artifact after content inspection and return `SOURCE_CHANGED_DURING_READINESS` if it differs from the verified descriptor.

- [ ] **Step 4: Add cross-modal and deterministic fingerprint tests**

Validate gaze scene-frame/AOI membership after all streams load. Build the fingerprint from canonical manifest version, sorted source checksums, profile versions, adapter versions, report statuses, and issues; exclude absolute paths and runtime timestamps.

Then change `generate_synthetic_bundle()` to call `inspect_ingestion_readiness(output_root)` after `ManifestLoader`. Reject the generated bundle unless disposition is `ready`, task reference is ready, `can_continue_to_synchronization=true`, and `formal_run_authorized=false`. Add a generator regression test that injects a broken gaze frame reference and observes generation fail at this final self-check.

- [ ] **Step 5: Run GREEN and commit**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/ingestion/test_readiness.py -v
git add src/pilot_assessment/ingestion src/pilot_assessment/synthetic/generator.py tests/ingestion/test_readiness.py tests/synthetic/test_generator.py
git commit -m "feat: orchestrate deterministic ingestion readiness"
~~~

### Task 11: Prove the M2 workflow end to end

**Files:**
- Create: `tests/e2e/test_m2_micro_bundle.py`
- Create: `tests/e2e/test_real_csv_local.py`
- Modify: `docs/product/11_IMPLEMENTATION_STATUS.md`
- Modify: `docs/product/README.md`

- [ ] **Step 1: Write and run the failing micro end-to-end test**

~~~python
def test_micro_bundle_runs_from_csv_to_ready_report(tmp_path: Path) -> None:
    bundle = generate_synthetic_bundle(MICRO_CSV, tmp_path / "bundle", seed=20260711)
    outcome = inspect_ingestion_readiness(bundle)
    assert outcome.report.disposition is ReadinessDisposition.READY
    assert all(result.readiness is StreamReadiness.READY for result in outcome.report.stream_results.values())
    assert outcome.report.task_reference_result.readiness is StreamReadiness.READY
    assert outcome.report.can_continue_to_synchronization is True
    assert outcome.report.formal_run_authorized is False
~~~

Run it before integration and observe the first unmet contract as RED; integrate only the minimum missing registration/profile until GREEN.

- [ ] **Step 2: Add the opt-in real CSV test**

~~~python
REAL_CSV_ENV = "PILOT_ASSESSMENT_REAL_CSV"


@pytest.mark.skipif(REAL_CSV_ENV not in os.environ, reason="repository-external CSV not configured")
def test_real_csv_full_bundle_is_ready(tmp_path: Path) -> None:
    source = Path(os.environ[REAL_CSV_ENV])
    source_bytes = source.read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    assert source_hash == "19bf804253d841de9c9de299ac96e9e1b693b2dbfae2f3eaeac5d7dc044e4f52"
    bundle = generate_synthetic_bundle(source, tmp_path / "full", seed=20260711)
    outcome = inspect_ingestion_readiness(bundle)
    assert outcome.prepared_session is not None
    x = outcome.prepared_session.streams["X"].primary_table
    u = outcome.prepared_session.streams["U"].primary_table
    assert x.height == 2_902
    assert u.height == 2_902
    assert x["source_time_s"].min() == 0.0
    assert x["source_time_s"].max() == 29.01
    assert u["control.longitudinal_raw"].min() == -100.0
    assert u["control.longitudinal_raw"].max() == 0.0
    assert outcome.prepared_session.context["context.control_mode_raw"] == 1.0
    assert outcome.prepared_session.context["context.time_delay_s"] == 0.2
    assert outcome.prepared_session.context["context.longitudinal_frequency_rad_s"] == 8.0
    assert outcome.prepared_session.context["context.longitudinal_damping_ratio"] == 0.8
    assert outcome.report.stream_results["X"].observed_sample_rate_hz == pytest.approx(100.0)
    assert outcome.report.disposition is ReadinessDisposition.READY
    assert (bundle / "streams" / "simulator.csv").read_bytes() == source_bytes
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
~~~

- [ ] **Step 3: Run both end-to-end paths**

~~~powershell
& .\.tools\uv\uv.exe run pytest tests/e2e/test_m2_micro_bundle.py -v
$env:PILOT_ASSESSMENT_REAL_CSV='C:\Users\long\Desktop\CranfieldOffer\proj\data\S_101500_Time_2026_05_14_16_48_54_P_1.csv'
& .\.tools\uv\uv.exe run pytest tests/e2e/test_real_csv_local.py -v
Remove-Item Env:PILOT_ASSESSMENT_REAL_CSV
~~~

Expected: both pass; the real source hash remains `19bf804253d841de9c9de299ac96e9e1b693b2dbfae2f3eaeac5d7dc044e4f52`.

- [ ] **Step 4: Update implementation status with measured evidence**

Record the exact dependency versions, test counts, generated modality row/frame counts, report disposition, source hash, local output boundary, and deferred M3 checks. Do not call synthetic output scientifically validated.

- [ ] **Step 5: Run the full completion gate**

~~~powershell
& .\.tools\uv\uv.exe run pytest -q
& .\.tools\uv\uv.exe run ruff format --check .
& .\.tools\uv\uv.exe run ruff check .
& .\.tools\uv\uv.exe run ty check src
& .\.tools\uv\uv.exe build
git diff --check
git status --short
git ls-files local_data '*.edf' '*.mp4' '*.parquet'
~~~

Expected: tests, format, lint, type check, and build exit 0; diff check is clean; no real/local bundle is tracked. Committed synthetic Parquet is allowed only below `tests/fixtures/` and must carry synthetic provenance.

- [ ] **Step 6: Wheel smoke and final commit**

Install the built wheel into a temporary uv environment, load packaged profiles, generate the micro bundle, and inspect readiness. Then commit only source, tests, schemas, lockfile, and docs:

~~~powershell
$wheel=(Get-ChildItem -LiteralPath dist -Filter '*.whl' | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
$smoke=Join-Path $env:TEMP 'pilot-assessment-m2-wheel-smoke'
$resolvedSmoke=[IO.Path]::GetFullPath($smoke)
$resolvedTemp=[IO.Path]::GetFullPath($env:TEMP).TrimEnd([IO.Path]::DirectorySeparatorChar)+[IO.Path]::DirectorySeparatorChar
if(-not $resolvedSmoke.StartsWith($resolvedTemp,[StringComparison]::OrdinalIgnoreCase)){throw 'Wheel smoke path escaped TEMP'}
if(Test-Path -LiteralPath $smoke){Remove-Item -Recurse -Force -LiteralPath $smoke}
& .\.tools\uv\uv.exe run --isolated --no-project --with $wheel python -m pilot_assessment.synthetic --xu-csv tests/fixtures/m2/simulator_micro.csv --output $smoke --seed 20260711
& .\.tools\uv\uv.exe run --isolated --no-project --with $wheel python -c "from pathlib import Path; from pilot_assessment.ingestion import inspect_ingestion_readiness; r=inspect_ingestion_readiness(Path(r'$smoke')).report; assert r.disposition.value == 'ready'; assert r.formal_run_authorized is False"
Remove-Item -Recurse -Force -LiteralPath $smoke
git add pyproject.toml uv.lock src tests schemas docs/product
git commit -m "feat: complete M2 multimodal synthetic ingestion"
~~~

Do not push unless the user explicitly requests a remote update.

## Plan self-review

- Every approved M2 requirement maps to a task and an observable exit condition.
- Public naming consistently uses `IngestionReadinessReport`; `run.preflight` remains future `RunPreflightReport` work.
- Task reference is a non-core logical stream with physical path under `references/` and a single checksum authority.
- Production code in every task follows an observed RED before GREEN.
- The plan preserves raw source timestamps and defers authoritative `t_ns` to M3.
- The full 29-second generated bundle stays outside Git; CI uses a two-second micro source.
- No task implements anchors, evidence scoring, BN inference, RPC, or WinUI.
