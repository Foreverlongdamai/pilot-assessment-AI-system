# External Multimodal Session Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: execute this plan inline. The user has explicitly rejected subagent-driven execution for this project because of quota cost. Use lightweight test-first checks and verification-before-completion.

**Goal:** Build an external, inspectable multimodal Session Bundle from the captured X/U CSV and drive the unchanged M6 stdio sidecar through one complete software-test assessment attempt.

**Architecture:** All fixture-generation and demo-runner files live under the sibling `data/pilot_assessment_demo` directory, outside the installable product and its Git repository. The builder writes contract-compatible raw files and validates them through the product's input boundary; the runner behaves like the future frontend by using only JSON-RPC/JSONL sidecar methods. No `src/pilot_assessment` file is changed and `pilot_assessment.synthetic` is neither imported nor called.

**Tech Stack:** Python 3.11, Polars/Parquet, Pillow PNG, Pydantic product contracts, M1/M2/M3 validation services, JSON-RPC 2.0 over stdio, pytest for one lightweight external smoke.

---

**Design source:** [External Multimodal Session Demo Design](../specs/2026-07-16-external-multimodal-session-demo-design.md)

**Execution mode:** INLINE in the current session. Generated data is intentionally outside Git; only this plan and the already-approved design are version-controlled.

## File map

| Path | Responsibility |
|---|---|
| `../data/pilot_assessment_demo/README.md` | Exact commands, directory explanation, scientific disclaimer, and observed run outcome |
| `../data/pilot_assessment_demo/tools/external_fixture_model.py` | Standalone deterministic I/G/EEG/ECG/camera/reference/annotation builders; no product synthetic import |
| `../data/pilot_assessment_demo/tools/build_external_fixture.py` | CLI orchestration, captured CSV inspection, artifact writing, manifest/checksum creation, and M1/M2 self-validation |
| `../data/pilot_assessment_demo/tools/rpc_client.py` | Small JSON-RPC subprocess client with transcript capture and notification handling |
| `../data/pilot_assessment_demo/tools/run_m6_sidecar_demo.py` | Project/session/run orchestration through the public M6 method set |
| `../data/pilot_assessment_demo/tools/test_external_demo.py` | One lightweight contract/count/import guard; no scientific golden values |
| `../data/pilot_assessment_demo/full_multimodal_session/` | Generated external Session Bundle retained for inspection |
| `../data/pilot_assessment_demo/managed_project/` | M6-owned portable project created by the sidecar |
| `../data/pilot_assessment_demo/results/` | RPC transcript, run summary, artifact index, and terminal diagnostics |

## Task 1: Create the external tool boundary and failing smoke

**Files:**
- Create: `../data/pilot_assessment_demo/README.md`
- Create: `../data/pilot_assessment_demo/tools/test_external_demo.py`
- Create: `../data/pilot_assessment_demo/tools/external_fixture_model.py`

- [ ] **Step 1: Create only the external directories**

Create `data/pilot_assessment_demo/tools` and an initial README that states:

```markdown
# Pilot Assessment External Multimodal Demo

This directory is test input and output, not a product feature. The product never fills missing modalities or generates visual/physiological data.
```

- [ ] **Step 2: Write the lightweight failing test**

```python
from external_fixture_model import DemoRates, expected_counts


def test_29_second_lightweight_profile_has_expected_counts() -> None:
    rates = DemoRates(scene_hz=2.0, gaze_hz=120.0, eeg_hz=256.0, ecg_hz=250.0, camera_hz=1.0)
    assert expected_counts(29.01, rates) == {
        "scene_frames": 59,
        "gaze_samples": 3482,
        "eeg_samples": 7427,
        "ecg_samples": 7253,
        "camera_frames": 30,
    }
```

- [ ] **Step 3: Run the test and verify the missing API**

Run from `pilot_assessment_system`:

```powershell
& .\.tools\uv\uv.exe run pytest ..\data\pilot_assessment_demo\tools\test_external_demo.py -q
```

Expected: collection/import failure because `DemoRates` and `expected_counts` do not yet exist.

- [ ] **Step 4: Implement the profile and exact retained-grid rule**

```python
from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR


@dataclass(frozen=True, slots=True)
class DemoRates:
    scene_hz: float = 2.0
    gaze_hz: float = 120.0
    eeg_hz: float = 256.0
    ecg_hz: float = 250.0
    camera_hz: float = 1.0


def sample_count(duration_s: float, rate_hz: float) -> int:
    if duration_s <= 0.0 or rate_hz <= 0.0:
        raise ValueError("duration and rate must be positive")
    return int((Decimal(str(duration_s)) * Decimal(str(rate_hz))).to_integral_value(rounding=ROUND_FLOOR)) + 1


def expected_counts(duration_s: float, rates: DemoRates) -> dict[str, int]:
    return {
        "scene_frames": sample_count(duration_s, rates.scene_hz),
        "gaze_samples": sample_count(duration_s, rates.gaze_hz),
        "eeg_samples": sample_count(duration_s, rates.eeg_hz),
        "ecg_samples": sample_count(duration_s, rates.ecg_hz),
        "camera_frames": sample_count(duration_s, rates.camera_hz),
    }
```

- [ ] **Step 5: Run the smoke and confirm it passes**

Expected: `1 passed`.

## Task 2: Implement standalone external modality builders

**Files:**
- Modify: `../data/pilot_assessment_demo/tools/external_fixture_model.py`
- Modify: `../data/pilot_assessment_demo/tools/test_external_demo.py`

- [ ] **Step 1: Extend the smoke with structural assertions**

Add a test that calls `build_modalities(duration_s=29.01, source_times_s=(0.0, 29.01), source_x_m=(0.0, -445.01), controls=(0.0, 0.0), seed=20260716)` and asserts:

```python
assert artifacts.scene.frame_index.height == 59
assert artifacts.scene.aoi_instances.height == 118
assert artifacts.gaze.samples.height == 3482
assert artifacts.eeg.samples.height == 7427
assert artifacts.ecg.samples.height == 7253
assert artifacts.camera.height == 30
assert artifacts.gaze.samples["scene_frame_id"].max() == 58
assert artifacts.eeg.sidecar["synthetic_not_neurophysiological"] is True
assert artifacts.ecg.sidecar["synthetic_not_physiological"] is True
```

- [ ] **Step 2: Verify the structural test fails**

Expected: failure because `build_modalities` is missing.

- [ ] **Step 3: Implement deterministic external builders**

Implement these exact units in `external_fixture_model.py`:

```python
@dataclass(frozen=True, slots=True)
class SceneArtifacts:
    frame_index: pl.DataFrame
    aoi_instances: pl.DataFrame

@dataclass(frozen=True, slots=True)
class GazeArtifacts:
    samples: pl.DataFrame
    fixations: pl.DataFrame

@dataclass(frozen=True, slots=True)
class SignalArtifacts:
    samples: pl.DataFrame
    sidecar: dict[str, object]

@dataclass(frozen=True, slots=True)
class ExternalArtifacts:
    scene: SceneArtifacts
    gaze: GazeArtifacts
    eeg: SignalArtifacts
    ecg: SignalArtifacts
    r_peaks: pl.DataFrame
    camera: pl.DataFrame
    reference: pl.DataFrame
    annotations: dict[str, dict[str, object]]
```

Use the following fixed meanings:

- scene frames contain head pose/FOV plus `primary_flight_display` and `outside_view` AOI rectangles;
- gaze alternates deterministic on-task/off-task intervals, maps each sample to `floor(time * scene_hz)` bounded to the last frame, and records binocular validity, pupil size, ray, AOI, and confidence;
- fixations use contiguous 0.5-second intervals;
- EEG uses eight channels `Fp1,Fp2,F3,F4,C3,C4,P3,P4`, sine-plus-seeded-noise values, `signal_valid=true`, and explicit non-neurophysiological sidecar metadata;
- ECG uses one `synthetic_lead_ii_mV` column, deterministic R-like peaks, `signal_valid=true`, an R-peak table, and explicit non-physiological metadata;
- pilot-camera rows contain image paths plus head and left/right-eye normalized boxes with `privacy_class=synthetic-no-identity`;
- reference copies the X timeline only to exercise the interface and records no acceptable-trajectory meaning;
- annotations contain translation/deceleration/hover-stabilization phases, two synthetic disturbance events, and one baseline interval, all with `synthetic_semantics_unvalidated=true`.

Use a local SHA-256 keyed noise function, not `pilot_assessment.synthetic.prng`:

```python
def unit_noise(seed: int, *parts: object) -> float:
    payload = "\0".join((str(seed), *(str(part) for part in parts))).encode("utf-8")
    integer = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
    return integer / 2**64
```

- [ ] **Step 4: Generate schematic PNG bytes outside the product**

Provide `write_scene_png` and `write_camera_png` using Pillow. Scene frames draw sky, horizon, a dark instrument panel, and two coloured instruments; camera frames draw a neutral head oval and two eye boxes. Dimensions remain 64x36 and 48x48. No identity or photorealism is implied.

- [ ] **Step 5: Run the external smoke**

Expected: `2 passed` with no import whose module name starts with `pilot_assessment.synthetic`.

## Task 3: Assemble and validate the complete external Session Bundle

**Files:**
- Create: `../data/pilot_assessment_demo/tools/build_external_fixture.py`
- Modify: `../data/pilot_assessment_demo/tools/test_external_demo.py`

- [ ] **Step 1: Add a temporary-directory bundle test**

The test invokes `build_bundle(source_csv, output, seed=20260716)` and asserts:

```python
from pathlib import Path


SOURCE_CSV = Path(__file__).resolve().parents[2] / "S_101500_Time_2026_05_14_16_48_54_P_1.csv"


def test_external_bundle_is_ready_and_preserves_source(tmp_path: Path) -> None:
    source_csv = SOURCE_CSV
    output = tmp_path / "bundle"
    build_bundle(source_csv, output, seed=20260716)
    readiness = inspect_ingestion_readiness(output)

    assert (output / "manifest.json").is_file()
    assert len(list((output / "streams/vr_scene/frames").glob("*.png"))) == 59
    assert len(list((output / "streams/pilot_camera/frames").glob("*.png"))) == 30
    assert (output / "streams/simulator.csv").read_bytes() == source_csv.read_bytes()
    assert readiness.report.disposition.value == "ready"
    assert readiness.report.formal_run_authorized is False
```

- [ ] **Step 2: Verify the bundle test fails**

Expected: failure because `build_bundle` is missing.

- [ ] **Step 3: Implement captured CSV inspection and artifact writing**

Use `ProfiledCsvAdapter` with packaged schema `cranfield-simulator-combined-csv-raw-v0.1` to obtain normalized X/U columns. Copy the source CSV byte-for-byte to `streams/simulator.csv`. Write Parquet with `write_profiled_parquet` and these schema IDs:

```text
vr-frame-index-raw-v0.1
vr-aoi-instance-raw-v0.1
gaze-sample-raw-v0.1
gaze-fixation-raw-v0.1
eeg-sample-raw-v0.1
ecg-sample-raw-v0.1
ecg-r-peak-raw-v0.1
pilot-camera-frame-index-raw-v0.1
task-reference-path-raw-v0.1
```

Write canonical UTF-8 JSON with sorted keys and a final newline. Refuse an existing non-empty output rather than deleting it.

- [ ] **Step 4: Build strict manifest/checksum provenance**

Create one `SessionManifest` with:

```python
privacy={
    "classification": "synthetic-test-data",
    "direct_identifiers_removed": True,
    "contains_biometric_data": False,
    "biometric_modalities_export_pending": [],
    "permitted_use": "software-testing-only",
}
```

Declare X/U as required shared physical CSV streams; declare I/G/EEG/ECG/pilot_camera as present composite streams; declare the bundled reference and three annotations. Store per-path SHA-256 values and `integrity/checksums.sha256`. Synthetic provenance must include the source CSV digest, fixed seed, external generator ID, exact rates, `scientific_validation_status=not_supported`, and `formal_assessment_supported=false`.

- [ ] **Step 5: Self-validate through product input boundaries**

Run `ManifestLoader().load(output)` followed by `inspect_ingestion_readiness(output)`. Fail the CLI unless disposition is `ready`, prepared session exists, and formal authorization is false. Print a JSON summary containing duration, row/frame counts, total bytes, manifest session ID, and source digest.

- [ ] **Step 6: Run the smoke and build the retained bundle**

```powershell
& .\.tools\uv\uv.exe run pytest ..\data\pilot_assessment_demo\tools\test_external_demo.py -q
& .\.tools\uv\uv.exe run python ..\data\pilot_assessment_demo\tools\build_external_fixture.py `
  --source ..\data\S_101500_Time_2026_05_14_16_48_54_P_1.csv `
  --output ..\data\pilot_assessment_demo\full_multimodal_session `
  --seed 20260716
```

Expected: external smoke passes and the builder reports a ready software-test bundle with 59 scene and 30 camera frames.

## Task 4: Implement the external JSON-RPC client and M6 runner

**Files:**
- Create: `../data/pilot_assessment_demo/tools/rpc_client.py`
- Create: `../data/pilot_assessment_demo/tools/run_m6_sidecar_demo.py`
- Modify: `../data/pilot_assessment_demo/tools/test_external_demo.py`

- [ ] **Step 1: Add a framing-only client test**

Test that `RpcTranscript.write_message` writes one valid compact JSON object per line and that response/notification classification preserves request IDs and methods. The test must not start the full assessment.

- [ ] **Step 2: Verify the client test fails**

Expected: failure because `rpc_client` is missing.

- [ ] **Step 3: Implement the subprocess client**

`SidecarClient` must start `[sys.executable, "-m", "pilot_assessment.sidecar"]`, keep stdout and stderr separate, serialize requests with monotonically increasing IDs, collect notifications while waiting for the matching response, enforce per-call timeouts, and append every sent/received message to `results/rpc-transcript.jsonl`. Any JSON-RPC error raises `SidecarCallError` carrying `error.code`, `error.message`, and `error.data`.

- [ ] **Step 4: Implement the exact demo call sequence**

The runner performs:

```text
runtime.hello
project.create
session.inspect
session.import
scheme.version.list
scheme.version.get
run.preflight(purpose=software_test)
run.start
run.status (poll)
run.events.list
result.get (only when completed)
result.artifact.get (for every result artifact reference)
project.close
runtime.shutdown
```

All mutation requests use stable transaction IDs and `actor=external.demo`. After `session.import`, rename `full_multimodal_session` to `full_multimodal_session.imported-offline`, run from the managed copy, and restore the original name in `finally`. Refuse to overwrite an existing `managed_project` or `results` directory.

- [ ] **Step 5: Persist honest terminal output**

Always write `results/run-summary.json`. On completion include exact scheme/component IDs, Evidence count/statuses, posterior/artifact references, event count, and elapsed time. On preflight or run failure include the stable JSON-RPC error or terminal event diagnostics. Never initiate the minimal O1 scheme automatically.

- [ ] **Step 6: Run the client smoke**

Expected: all lightweight external tests pass.

## Task 5: Execute the complete starter attempt and inspect the artifacts

**Files:**
- Generate: `../data/pilot_assessment_demo/managed_project/`
- Generate: `../data/pilot_assessment_demo/results/`
- Modify: `../data/pilot_assessment_demo/README.md`

- [ ] **Step 1: Run the M6 sidecar demo**

```powershell
& .\.tools\uv\uv.exe run python ..\data\pilot_assessment_demo\tools\run_m6_sidecar_demo.py `
  --bundle ..\data\pilot_assessment_demo\full_multimodal_session `
  --project ..\data\pilot_assessment_demo\managed_project `
  --results ..\data\pilot_assessment_demo\results
```

Expected: the script reaches a recorded terminal state. `completed` is desirable but not assumed; a real `failed` state with exact diagnostics remains valid evidence of the first full starter attempt.

- [ ] **Step 2: Inspect result/artifact content**

Use the managed artifact references to summarize:

```text
ingestion disposition
synchronization disposition
locked Evidence count
computed/missing/error Evidence statuses
posterior variable count
four competency posterior distributions when present
run terminal state and duration
```

- [ ] **Step 3: Reopen the project through a fresh sidecar**

Call `project.open`, `session.get`, `run.status`, `run.events.list`, `result.get`, and `result.artifact.get` against the existing project. Confirm exact IDs and artifact checksums survive restart, then shut down cleanly.

- [ ] **Step 4: Complete the external README**

Document exact commands, observed file counts/sizes, the actual terminal result, where to find sample images and Parquet files, and why none of the numeric Evidence/posterior output evaluates the real pilot.

## Task 6: Final separation and verification gate

**Files:**
- Verify: `../data/pilot_assessment_demo/**`
- Verify unchanged: `src/pilot_assessment/**`

- [ ] **Step 1: Run fresh external verification**

```powershell
& .\.tools\uv\uv.exe run pytest ..\data\pilot_assessment_demo\tools\test_external_demo.py -q
& .\.tools\uv\uv.exe run python -m pilot_assessment.sidecar
```

For the second command, send only `runtime.hello` and `runtime.shutdown`; verify every stdout line is valid JSON-RPC.

- [ ] **Step 2: Verify source and bundle integrity**

Recompute the original CSV SHA-256, load the manifest, verify all checksums, and compare actual row/frame counts against declared rates. Confirm the external bundle name was restored after the managed-copy proof.

- [ ] **Step 3: Verify product separation**

```powershell
git status --short
git diff --exit-code -- src/pilot_assessment
rg -n "pilot_assessment\.synthetic" ..\data\pilot_assessment_demo\tools
```

Expected: no product-source diff and no external-tool import/call of `pilot_assessment.synthetic`. Documentation commits may exist; generated demo files remain outside the repository.

- [ ] **Step 4: Report exact outcome**

Report generated paths, counts, sizes, commands, test output, terminal run state, Evidence/BN artifact locations, any blocker, and the scientific disclaimer. Do not claim a completed assessment unless the fresh terminal state is `completed`.

## Completion condition

The plan is complete only when the external data is inspectable under `data`, the unchanged M6 sidecar has produced and persisted a real terminal outcome for the complete starter scheme, restart/replay has been checked, and Git proves that no product source was changed for synthetic generation.
