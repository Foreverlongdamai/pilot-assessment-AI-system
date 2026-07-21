+++
document_id = "PAS-SESSION-001"
language = "en-GB"
title = "Session Bundle and Raw Input Interface Reference"
short_title = "Session and Input Interfaces"
product_version = "0.1.0"
document_version = "0.1.0"
status = "released"
audience = ["evaluator", "expert", "developer", "maintainer"]
information_types = ["how-to", "reference", "explanation"]
scope = "Canonical Session Bundle, raw simulator import, seven physical modalities, annotations, timing, units, privacy and missing-input behaviour."
prerequisites = ["Access to a simulator export or canonical bundle", "Knowledge of the exported column and timestamp meanings"]
scientific_status = "engineering-only"
related_documents = ["PAS-QUICKSTART-001", "PAS-EVALUATOR-001", "PAS-PYTHON-EXT-001", "PAS-PORTABILITY-001"]
support = "Provide a privacy-safe directory tree, adapter diagnostic and manifest excerpt; never send biometric files through an unauthorised channel."
release_channel = "release-candidate"
release_label = "v0.1.0-rc.3"
user_acceptance = "pending"
+++

# Session Bundle and Raw Input Interface Reference

## 1. Two accepted source shapes

The application accepts either:

1. a **canonical Session Bundle** with a UTF-8 `manifest.json`; or
2. a **raw simulator export** whose useful public surface is `streams\` and optional `annotations\`.

The simulator is not required to generate the product's manifest, checksums, canonical annotation file or internal index. For a raw export, the application inspects the source read-only, selects a trusted adapter, generates those records inside project staging and copies accepted files to a managed Session revision. The external directory remains unchanged.

Importing is therefore an adaptation and provenance operation, not a requirement that every simulator adopt this repository's internal layout.

## 2. Why `manifest.json` exists

The manifest makes one Session self-describing and reproducible after it has entered managed storage. It records at least:

- Session/contract identity and duration declaration;
- one descriptor for every formal modality;
- file paths, formats, schema IDs and checksums;
- clock IDs and source-to-session time mappings;
- units or an explicit empty unit declaration;
- annotation/reference descriptors;
- privacy classification and provenance;
- missing/export-pending/not-applicable status.

It does not invent sensor meaning. A generated manifest is reliable only to the extent that the selected adapter correctly maps the simulator's files and columns. The inspection screen must expose that mapping before import.

## 3. Raw-input families and physical modalities

The five large canvas families provide a stable expert vocabulary:

| Family | Physical content | Typical use |
|---|---|---|
| `X(t)` | flight state: position, velocity, attitude, angular rate, acceleration | trajectory, envelope and disturbance-response Evidence |
| `U(t)` | pilot controls: yaw, longitudinal, lateral, heave and device-specific axes | workload, reversal, smoothness and control-coupling Evidence |
| `I(t)` | first-person VR scene actually shown in the headset as head pose changes | visible scene/object/AOI context |
| `G(t)` | gaze ray/point, fixation or stare and AOI relationship on dynamic `I(t)` | attention allocation and first-fixation Evidence |
| `P(t)` | physiology grouping | EEG- and ECG-derived Evidence |

The canonical manifest declares seven physical modality descriptors: `X`, `U`, `I`, `G`, `EEG`, `ECG` and `pilot_camera`. `P(t)` is a canvas grouping, not an ambiguous single stream key: EEG and ECG retain independent sample rates, units, clocks and status. `pilot_camera` is a separate optional pilot-facing camera and is not the first-person VR scene.

Fine-grained Raw Input nodes in the second canvas layer bind exact fields/resources under these families. A recipe uses those typed bindings rather than guessing CSV column positions.

## 4. Recommended physical forms

- Numeric time series: Parquet is preferred; a documented CSV adapter is supported.
- EEG/ECG: Parquet or EDF/EDF+ plus companion metadata for clock, channel/lead, unit and Session mapping.
- `I(t)` and `pilot_camera`: frame files or video plus a frame index carrying stable frame ID and source timestamp.
- `G(t)`: a table with source timestamp, gaze origin/direction or viewport point, validity, associated scene frame and AOI/fixation fields when available.
- `annotations`: task events/segments with stable IDs and time boundaries.
- `references`: commanded path or other task reference when required by the selected scheme.

Images and dense time series never travel through JSON-RPC. They stay in managed project files and are addressed by Session/artifact identities.

## 5. Minimal semantics by modality

### 5.1 `X(t)` and `U(t)`

Preserve raw numeric values, timestamps, axis direction and any declared units/normalisation. A legacy combined simulator CSV may map selected columns into both logical streams; the managed manifest records the column mapping and the physical artifact identity so the file is not duplicated accidentally.

### 5.2 `I(t)`

`I(t)` is the dynamic first-person image the pilot saw in VR, not an external chase or cockpit camera. Its frame index should identify the image/video frame, timestamp, dimensions, head pose/FOV and calibration or scene metadata needed to connect gaze. Scene graphs, object-ID buffers or AOI masks may be auxiliary resources but do not replace the presented image.

### 5.3 `G(t)`

Gaze must declare its coordinate space and relation to dynamic `I(t)`: viewport point, headset-relative ray or world/scene ray. Store source validity as technical metadata, plus fixation/stare segments and AOI taxonomy when the acquisition system provides them. The assessment layer does not discard parseable poor performance merely because the gaze is off-task.

### 5.4 EEG and ECG

Keep raw or nearest-to-raw channels and stable metadata. EEG should declare channels/montage; ECG should declare lead/channel. Both need source clock and unit when known. Baselines and derived bands/R-peaks remain explicit derived products with provenance. Extreme finite values can be meaningful negative Evidence and are not filtered by a generic “quality” score.

### 5.5 `pilot_camera`

Pilot camera contains face or upper-body imagery on its own clock and privacy classification. It is optional and cannot be labelled as `I(t)`. A task may ignore it completely.

## 6. Stream status and missing modalities

Each formal descriptor uses one of these interface statuses:

| Status | Meaning | Runtime consequence |
|---|---|---|
| `present` | readable files and complete interface declaration exist | eligible for ingestion/synchronization |
| `invalid` | files exist but the structural/schema/time contract cannot be used | excluded with an explicit technical diagnostic |
| `export_pending` | data belongs to the experiment but has not yet been exported | no files; dependent Evidence unavailable |
| `missing` | expected data was not captured or supplied | no files; dependent Evidence unavailable |
| `not_applicable` | the task intentionally has no such modality | no files; dependent Evidence not applicable/unavailable |

`invalid` is not a judgement that the pilot flew badly or the physiology looks abnormal. Finite poor performance remains data and should produce poor Evidence according to the configured method.

A Session with only `X` and `U` can still be imported and assessed. The active graph computes all Evidence whose required inputs exist. Missing Evidence is retained as unavailable and marginalized during BN inference; the product neither blocks the entire run automatically nor fabricates ideal/synthetic measurements.

## 7. Timestamps and synchronization

Every present stream declares a source clock. The synchronization layer maps native timestamps to signed-int64 Session `t_ns` while preserving native rows and stable duplicate-time order. It does not rewrite source files or force all modalities into one dense table.

Clock mapping can include scale, offset and drift. Streams sharing a clock must share that declaration. Synchronization reports coverage and residual diagnostics; Evidence recipes consume deterministic aligned views or native-rate segments as specified.

## 8. Units and undeclared values

The `units` field always exists but may be an empty object. If neither the original export nor a trusted adapter profile declares a unit, the importer keeps the numeric value unchanged as `undeclared-pass-through-v1`. It does not ask the user to guess, infer a unit from magnitude or apply a hidden conversion.

The fixed Evidence method may still consume that field according to its documented adapter assumption. Provenance must make the undeclared status visible. Experts should correct the adapter/profile or method when the true meaning becomes known.

## 9. Integrity, privacy and lifecycle

All managed paths are project-relative and checked against traversal/case collisions. Checksums protect imported bytes; mismatch is a fatal integrity error rather than a downgraded stream status. Derived artifacts never overwrite the Session Bundle.

Do not place names, contact details or unrelated identity fields in the manifest. Gaze, EEG, ECG and pilot-camera content are sensitive research data. The product package contains none of them; each user supplies and governs their own Session data.

To move an imported Session, close the app and copy the complete project root. See [[DOC:PAS-PORTABILITY-001]].

## 10. Adapter extension checklist

- [ ] External source is inspected read-only;
- [ ] file/column mappings are deterministic and visible;
- [ ] raw bytes are copied and checksummed before use;
- [ ] every formal modality receives an explicit descriptor/status;
- [ ] timestamps and clocks are not guessed silently;
- [ ] absent units remain undeclared;
- [ ] privacy fields exclude direct identity;
- [ ] missing modalities do not trigger synthetic product data;
- [ ] a new format is implemented as an adapter, not a one-off manual rewrite.
