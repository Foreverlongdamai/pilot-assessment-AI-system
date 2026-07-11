# Backend Foundation Milestone 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. If that skill is unavailable, execute the same tasks inline and preserve every RED/GREEN verification record.

**Goal:** 建立可安装、可测试的 Python Assessment Core 基础层，冻结 v0.1 的 SessionManifest、StreamDescriptor 与 AnchorResult 合同，并提供安全 manifest loader 和可交付 JSON Schema。

**Architecture:** 本里程碑只实现 `contracts` 与 `ingestion` 的稳定边界；不实现真实流解析、同步、18 个 anchor、BN、JSON-RPC 或 WinUI。Pydantic v2 是运行时合同权威，导出的 JSON Schema 是跨语言/交付合同；loader 只接收 bundle root，验证 UTF-8 JSON、schema、路径边界和 `present` 文件的存在性/checksum，且不修改原始数据。

**Tech Stack:** Python 3.11、uv、Pydantic 2、pytest、Ruff、ty、uv_build、SHA-256、JSON Schema 2020-12。

---

## 0. 范围与权威来源

本计划遵守以下当前正式设计：

- `pilot_assessment_system/docs/product/02_ASSESSMENT_CORE_DESIGN.md`
- `pilot_assessment_system/docs/product/03_SESSION_BUNDLE_SPEC.md`
- `pilot_assessment_system/docs/product/04_REFERENCE_MODEL_V0_1.md`
- `pilot_assessment_system/docs/product/07_RUNTIME_PROTOCOL_DESIGN.md`
- `pilot_assessment_system/docs/product/09_VALIDATION_AND_HANDOFF.md`
- `pilot_assessment_system/docs/product/DECISIONS.md`

本里程碑明确不做：Parquet/EDF/视频 adapter、时间同步、anchor 计算、evidence scorer、BN inference、模型图编辑、sidecar、数据库和 Windows UI。

Git 当前不可用（工作目录不是有效 repository）。下述逻辑提交点必须保留，但本轮不得擅自 `git init`；仓库修复后再按任务边界提交。

## Task 1: Bootstrap the isolated Python project

**Files:**

- Create: `pilot_assessment_system/pyproject.toml`
- Create: `pilot_assessment_system/.python-version`
- Create: `pilot_assessment_system/.gitignore`
- Create: `pilot_assessment_system/src/pilot_assessment/__init__.py`
- Create: `pilot_assessment_system/tests/test_package_metadata.py`

**Step 1: Install a project-local uv executable**

Use the official pinned installer `https://astral.sh/uv/0.11.28/install.ps1` with `UV_INSTALL_DIR` set to `pilot_assessment_system/.tools/uv` and `UV_NO_MODIFY_PATH=1`. Do not modify the shared Anaconda environment. The installed Windows x86-64 `uv.exe` used for this milestone has SHA-256 `533fe4044bc50b05ac89f4d07925597fdb5285369724e8986ecab356818f09ee`.

**Step 2: Write the failing package metadata test**

Test that `pilot_assessment.__version__ == "0.1.0"` and that the package imports from the src layout.

**Step 3: Run the test to verify RED**

Run:

```powershell
python -m pytest tests/test_package_metadata.py -q
```

Expected: FAIL during import because `pilot_assessment` does not yet exist.

**Step 4: Add the minimal package and project configuration**

Use `uv_build`, `requires-python = ">=3.11"`, runtime dependency `pydantic>=2.12,<3`, and development dependencies for pytest, Ruff, ty and build verification. Configure Ruff for Python 3.11 and a 100-character line length. Configure pytest to use `tests` and strict markers/config.

**Step 5: Sync and verify GREEN**

Run:

```powershell
& .\.tools\uv\uv.exe sync --all-groups
& .\.tools\uv\uv.exe run pytest tests/test_package_metadata.py -q
```

Expected: PASS.

**Logical commit after Git repair:** `build: bootstrap Python assessment core`

## Task 2: Define shared primitives and secure relative paths

**Files:**

- Create: `pilot_assessment_system/tests/contracts/test_common.py`
- Create: `pilot_assessment_system/src/pilot_assessment/contracts/common.py`
- Create: `pilot_assessment_system/src/pilot_assessment/contracts/__init__.py`

**Step 1: Write failing tests**

Cover:

- stable IDs are 1–128 characters, start with an ASCII letter or digit, and contain only ASCII letters, digits, `.`, `_`, `-`;
- `streams/x.parquet` is accepted;
- absolute POSIX paths, drive paths, UNC paths, backslashes, empty paths, `.`, `..`, traversal and URI-like values are rejected;
- SHA-256 values contain exactly 64 hexadecimal characters and canonicalize to lowercase;
- finite probability/quality numbers reject NaN and infinity.

**Step 2: Verify RED**

Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/contracts/test_common.py -q
```

Expected: FAIL because common contract types do not exist.

**Step 3: Implement the minimum shared types**

Implement constrained aliases/helpers for `StableId`, `BundleRelativePath`, `Sha256Digest` and a common strict Pydantic base model. Use one canonical path validator for stream, annotation, integrity and derived-artifact paths.

**Step 4: Verify GREEN**

Run the same pytest command and expect PASS.

**Logical commit after Git repair:** `feat: add stable identifiers and safe path contracts`

## Task 3: Freeze SessionManifest and StreamDescriptor v0.1

**Files:**

- Create: `pilot_assessment_system/tests/fixtures/session_manifest_valid.json`
- Create: `pilot_assessment_system/tests/contracts/test_session_manifest.py`
- Create: `pilot_assessment_system/src/pilot_assessment/contracts/session.py`
- Modify: `pilot_assessment_system/src/pilot_assessment/contracts/__init__.py`

**Step 1: Add a valid fixture and failing tests**

The fixture must contain all seven descriptors: `X`, `U`, `I`, `G`, `EEG`, `ECG`, `pilot_camera`. X/U are `present`; the remaining modalities are `export_pending`.

Test at least:

- the valid fixture round-trips without changing `export_pending` to `missing`;
- all required top-level fields exist and unknown top-level fields are rejected;
- unknown extension data is preserved only inside `extensions`;
- `bundle_schema_version` is SemVer with supported major `0` and `created_at` is timezone-aware RFC 3339;
- all seven core stream descriptors exist; `P` is not a stream key;
- a later `0.x` manifest may add optional stable stream IDs; unknown optional descriptors are preserved and left to the adapter registry rather than rejected by the base DTO;
- stream map key equals `descriptor.modality`;
- status is one of `present`, `export_pending`, `missing`, `invalid`, `not_applicable`;
- a `present` stream has at least one path and a matching checksum for every path;
- `export_pending` has empty paths and checksums;
- `sample_rate_hz` is null or positive;
- coverage values are in `[0,1]` and all clock numbers are finite;
- annotation and integrity paths use the common secure relative-path contract.

Do not make `format` a closed enum; adapter support belongs to the future ingestion registry.

**Step 2: Verify RED**

Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/contracts/test_session_manifest.py -q
```

Expected: FAIL because session models do not exist.

**Step 3: Implement the minimum strict Pydantic models**

Implement `CoreModality`, `StreamStatus`, `ClockSync`, `QualitySummary`, `StreamDescriptor`, the manifest nested DTOs, and `SessionManifest`. `CoreModality` identifies the seven required descriptors, while the stream map and descriptor modality use `StableId` so same-major optional streams can round-trip. Nested objects use explicit fields plus their own `extensions` where forward-compatible data is permitted. Keep external URI references unsupported in v0.1 rather than accepting arbitrary URI strings in `paths`.

An `invalid` descriptor may retain paths/checksums so diagnostics can refer to the files; do not impose the `export_pending` empty-path rule on `invalid`.

**Step 4: Verify GREEN**

Run the same pytest command and expect PASS.

**Logical commit after Git repair:** `feat: add versioned session manifest contracts`

## Task 4: Freeze the unified AnchorResult contract

**Files:**

- Create: `pilot_assessment_system/tests/fixtures/anchor_result_computed.json`
- Create: `pilot_assessment_system/tests/contracts/test_anchor_result.py`
- Create: `pilot_assessment_system/src/pilot_assessment/contracts/anchor.py`
- Modify: `pilot_assessment_system/src/pilot_assessment/contracts/__init__.py`

The DTO freezes these top-level rules:

| Field group | M1 rule |
|---|---|
| `anchor_id`, `model_version`, `calculation_status`, `parameter_hash` | Always required |
| `evidence_state`, `continuous_score`, `evidence_likelihood` | Required only for `computed`; forbidden otherwise |
| `raw_metrics`, `phase_results`, `event_results`, `source_windows`, `derived_artifacts`, `thresholds_used`, `diagnostics` | Always present, may be empty |
| `primary_value` | Optional because a valid anchor may use multiple raw metrics without one scalar primary value |
| `quality`, `parameters_used`, `dependencies`, `input_status_snapshot`, `provenance` | Always required |
| Additional fields | Rejected unless placed in the explicit `extensions` object |

**Step 1: Write failing tests**

Cover:

- all seven `calculation_status` values;
- a `computed` result requires evidence state, likelihood, continuous score and passed quality;
- canonical likelihood order is exactly `[unacceptable, adequate, desired]`;
- likelihood has three finite non-negative values with sum `1 ± 1e-9`;
- continuous score equals `(P(adequate) + 2 * P(desired)) / 2` within `1e-9`;
- when `parameters_used.scoring_transform == hard_threshold_v1`, likelihood is one-hot and evidence state matches it;
- a versioned soft scorer can return non-one-hot likelihood, including a tie only when its parameters declare an explicit `tie_policy`;
- any non-computed result omits evidence state, likelihood and continuous score;
- `invalid_quality` requires `quality.passed == false`;
- quality score and valid coverage stay in `[0,1]`;
- source windows have `end_t_ns > start_t_ns`;
- derived artifact paths use the common safe relative-path contract;
- the result includes a SHA-256 `parameter_hash` in addition to parameter details;
- phase/event breakdown remains metadata; the future evidence/inference milestone owns the test that it creates only one BN observation.

`observation_mode` is deliberately not extractor-controlled; it will be derived by the future evidence/inference layer.

**Step 2: Verify RED**

Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/contracts/test_anchor_result.py -q
```

Expected: FAIL because anchor models do not exist.

**Step 3: Implement the minimum strict models**

Implement `CalculationStatus`, `EvidenceState`, `EvidenceLikelihood`, `PrimaryValue`, `SourceWindow`, `DerivedArtifact`, `AnchorQuality`, `Dependencies`, `Provenance` and `AnchorResult`. Use a single module constant for probability tolerance.

**Step 4: Verify GREEN**

Run the same pytest command and expect PASS.

**Logical commit after Git repair:** `feat: add unified anchor result contract`

## Task 5: Add a safe directory-bundle manifest loader

**Files:**

- Create: `pilot_assessment_system/tests/ingestion/test_manifest_loader.py`
- Create: `pilot_assessment_system/src/pilot_assessment/ingestion/__init__.py`
- Create: `pilot_assessment_system/src/pilot_assessment/ingestion/manifest_loader.py`

**Step 1: Write failing integration tests**

Using pytest temporary directories, cover:

- valid UTF-8 `manifest.json` loads into `SessionManifest`;
- missing, malformed, non-object and non-UTF-8 manifests return typed errors;
- bundle root must be a directory in M1; zip support is explicitly deferred;
- `present` files, annotation files and the integrity checksum file must exist and remain under the resolved bundle root;
- the SHA-256 checksum manifest is parsed and all declared bundle-local file hashes are verified;
- checksum entries exactly equal the declared present-stream and annotation paths; undeclared entries are rejected and never opened;
- duplicate JSON keys, nonstandard constants and parser limit errors return typed manifest errors;
- configurable metadata, path-count, checksum-entry and hash-byte limits prevent unbounded inspect work;
- symlink/junction escape is rejected before reading;
- duplicate paths under Windows case-insensitive normalization are rejected;
- `export_pending`, `missing` and `not_applicable` files are not fabricated or opened;
- the loader never rewrites the manifest or source files.

**Step 2: Verify RED**

Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/ingestion/test_manifest_loader.py -q
```

Expected: FAIL because the loader does not exist.

**Step 3: Implement the loader and typed errors**

Implement shared `DomainErrorData`, plus `ManifestLoader`, `LoadedManifest` and typed exception classes using the frozen error fields: error code, severity, recoverable, message, field/path, remediation and diagnostics, with optional request/trace context. Use stable codes such as `INVALID_MANIFEST`, `SCHEMA_INCOMPATIBLE` and `CHECKSUM_MISMATCH`. Keep schema validation separate from filesystem validation. Resolve every local referenced path and verify it remains under the real bundle root before reading or hashing. M1 reports structural and declared-file integrity validation; it must not claim that deferred modality adapters or synchronization gates have passed.

M1 `ManifestLoader` is the implementation of `session.inspect`, not `session.import`. It must label its result `inspect_only_structure_and_declared_file_integrity`. Because inspection does not create an immutable managed snapshot, it cannot authorize formal import/run; a later importer must validate final Windows paths/reparse points, hash and copy from the same secured handles.

**Step 4: Verify GREEN**

Run the same pytest command and expect PASS.

**Logical commit after Git repair:** `feat: validate session manifests and bundle integrity`

## Task 6: Export versioned JSON Schemas

**Files:**

- Create: `pilot_assessment_system/tests/schemas/test_schema_export.py`
- Create: `pilot_assessment_system/src/pilot_assessment/schemas/__init__.py`
- Create: `pilot_assessment_system/src/pilot_assessment/schemas/export.py`
- Create: `pilot_assessment_system/schemas/session-manifest-0.1.0.schema.json`
- Create: `pilot_assessment_system/schemas/anchor-result-0.1.0.schema.json`

**Step 1: Write the failing schema-export tests**

Test deterministic output, JSON Schema 2020-12 declaration, and byte-for-byte agreement between generated schemas and committed files. Freeze identifiers as:

- Session manifest: `$id = urn:cranfield:pilot-assessment:schema:session-manifest:0.1.0`, title `Pilot Assessment Session Manifest 0.1.0`;
- Anchor result: `$id = urn:cranfield:pilot-assessment:schema:anchor-result:0.1.0`, title `Pilot Assessment Anchor Result 0.1.0`.

**Step 2: Verify RED**

Run:

```powershell
& .\.tools\uv\uv.exe run pytest tests/schemas/test_schema_export.py -q
```

Expected: FAIL because the exporter and committed schemas do not exist.

**Step 3: Implement and export**

Provide a module command:

```powershell
& .\.tools\uv\uv.exe run python -m pilot_assessment.schemas.export
```

It writes canonical UTF-8 JSON with sorted keys and a final newline. Generated files must remain inside `pilot_assessment_system/schemas`.

**Step 4: Verify GREEN and determinism**

Run the exporter twice and then the schema test. The second run must produce no content difference.

**Logical commit after Git repair:** `feat: publish deterministic JSON schemas`

## Task 7: Complete verification and handoff documentation

**Files:**

- Modify: `pilot_assessment_system/README.md`
- Modify: `pilot_assessment_system/docs/product/README.md`
- Modify: `pilot_assessment_system/docs/product/09_VALIDATION_AND_HANDOFF.md`
- Create: `pilot_assessment_system/docs/product/11_IMPLEMENTATION_STATUS.md`

**Step 1: Run the full fresh verification suite**

From `pilot_assessment_system`:

```powershell
& .\.tools\uv\uv.exe run pytest -q
& .\.tools\uv\uv.exe run ruff check .
& .\.tools\uv\uv.exe run ruff format --check .
& .\.tools\uv\uv.exe run ty check
& .\.tools\uv\uv.exe build
```

Also run the schema exporter and re-run the schema determinism test after the build.

**Step 2: Update the handoff state**

Record exactly what M1 implements, the commands that passed, deferred subsystems, schema IDs, scientific status (`engineering_default`) and software status (`in_progress`, not fully verified for reference v0.1). Do not change the product-level 18-anchor scientific claims.

**Step 3: Independent review**

Ask a read-only reviewer to inspect contract/design alignment, test omissions, security boundary and documentation accuracy. Resolve all P0/P1 findings, then rerun the full suite.

**Logical commit after Git repair:** `docs: record backend foundation milestone`

## Definition of Done

M1 is complete only when:

1. a clean `uv sync --all-groups` creates the environment;
2. all contract, loader and schema tests pass;
3. Ruff check/format, ty and `uv build` pass;
4. generated schemas are deterministic and committed under `schemas/`;
5. no path traversal, absolute path, checksum mismatch or symlink escape fixture is accepted;
6. `export_pending` remains distinct from `missing`;
7. non-computed AnchorResult objects cannot carry evidence state, likelihood or continuous score; the inference observation-filter gate is deferred;
8. docs state that ingestion adapters, synchronization, anchors, BN, runtime and UI remain unimplemented;
9. the result is not described as scientifically validated.
