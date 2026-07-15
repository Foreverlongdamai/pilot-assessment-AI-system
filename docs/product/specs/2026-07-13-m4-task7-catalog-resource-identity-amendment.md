# M4 Task 7 Catalog and Resource Identity Amendment

**Status:** Accepted on 2026-07-13 under the user's autonomous-continuation authorization after two independent P0/P1 reviews reached PASS  
**Date:** 2026-07-13  
**Applies to:** M4 replacement plan Task 7 and the catalog/resource inputs consumed by Tasks 8, 9, 11, 13, and 14–31  
**Precedence:** This document narrows machine identities left open by the approved M4 design and replacement plan. It does not change an anchor formula, threshold, golden value, topology level, M4/M5/M6 ownership, or scientific status.

## 1. Problem being closed

The approved M4 design freezes the 18 algorithms and describes their principal artifacts in domain language. The strict Task 4 contracts require more exact information before Task 7 can create a valid `AnchorCatalog`:

- exact plugin, parameter-schema, dependency, artifact, kind, and schema IDs;
- a complete inline descriptor and canonical row order for every artifact schema;
- an exact vocabulary for `required_inputs`;
- a temporary value for the required `catalog_fingerprint` field before Task 8 owns RFC 8785 hashing;
- an exact distinction between H4 result availability and its optional signed-HR trace for O13;
- a clear statement that the O10–O12 event primitive is implementation code, not a seventh preprocessing provider.

Task 7 must not fill these gaps differently in tests, resources, and later plugins. This amendment freezes one engineering-default identity set.

## 2. Global catalog constants

The packaged reference catalog is exact:

| Field | Value |
|---|---|
| `contract_id` | `anchor-catalog` |
| `contract_version` | `0.1.0` |
| `profile_id` | `reference-model-v0.1` |
| `profile_version` | `0.1.0` |
| `scientific_validation_status` | `engineering_default` |
| entry order | `O1`–`O13`, then `H1`–`H5` |
| entry `definition_version` | `0.1.0` |
| entry `plugin_version` | `0.1.0` |
| entry `lifecycle` | `active` |
| entry `required` | `true` |
| entry `canonical_order` | zero-based position `0..17` |
| entry `scorer_id` | `hard_threshold_v1` |
| plugin API used later | `0.1.0` |
| measurement schema used later | `anchor-measurement-0.1.0` |

Task 7 uses exactly 64 lowercase zeroes as `catalog_fingerprint`. This is a named `task8-uncomputed-sentinel`, not a digest claim. Task 8 must replace it with the RFC 8785 typed digest and add a packaged-loader test that rejects a remaining sentinel. No execution plan, registry verification, result, or report may treat the sentinel as canonical identity.

Generic `AnchorCatalog` remains cardinality-agnostic. The exact cardinality, order, status, and sentinel rule belong only to `load_packaged_catalog("reference-model-v0.1")` and its reference-profile validator.

## 3. Required-input vocabulary

`AnchorCatalogEntry.required_inputs` uses only these prefixed Stable IDs. They are inventory labels, not an alternative routing system:

- streams: `stream.X`, `stream.U`, `stream.I`, `stream.G`, `stream.ECG`, `stream.EEG`;
- reference: `reference.task_reference`;
- semantic: `semantic.phases`, `semantic.events`, `semantic.aois`, `semantic.baselines`, `semantic.targets`, `semantic.envelopes`, `semantic.control_mappings`;

There are no `context.*` labels in the reference catalog. Under the accepted Task 3 ownership boundary, envelope/hover limits, active control channels and calibration come from `SessionSemanticSnapshot.envelopes/control_mappings`; EEG/ECG role channels come from `baselines.channel_bindings`; AOI weights/off-task roles come from `aois`. `W_min`, channel aggregation weights, D/A/U thresholds, temporal/DSP/grid settings, and scorer policy are plan/parameter-snapshot values. They are not duplicated into `AlignedSession.context` or into semantic snapshot fields.

Later plugin definitions still route streams through `required_streams`, aligned-session context through `required_context_paths`, task semantics through `required_semantic_paths`, and the task reference through `required_reference_ids`. Code must not parse `required_inputs` to bypass those typed fields.

## 4. Exact reference entry matrix

Within each tuple, order is authoritative. Empty means `()`.

| # | Anchor / plugin ID | `required_inputs` | dependencies | artifact recipe |
|---:|---|---|---|---|
| 0 | `O1` / `o1-phase-state-precision` | `stream.X`, `semantic.phases`, `semantic.envelopes` | — | `desired-envelope-mask / sample_mask / desired-envelope-mask-v0.1` |
| 1 | `O2` / `o2-peak-tracking-excursion` | `stream.X`, `reference.task_reference`, `semantic.phases` | — | `tracking-error-trace / sample_trace / tracking-error-trace-v0.1` |
| 2 | `O3` / `o3-terminal-capture-quality` | `stream.X`, `semantic.targets`, `semantic.events`, `semantic.envelopes` | — | `capture-trace / event_trace / capture-trace-v0.1` |
| 3 | `O4` / `o4-sustained-hover-time` | `stream.X`, `semantic.envelopes` | — | `stable-hover-mask / sample_mask / stable-hover-mask-v0.1` |
| 4 | `O5` / `o5-workload-rate` | `stream.U`, `semantic.control_mappings` | `movement-events` | `movement-events / event_trace / movement-events-v0.1` |
| 5 | `O6` / `o6-control-magnitude-rms` | `stream.U`, `semantic.control_mappings` | — | `rms-contribution-trace / component_trace / rms-contribution-trace-v0.1` |
| 6 | `O7` / `o7-control-reversal-rate` | `stream.U`, `semantic.control_mappings` | `movement-events` | `reversal-events / event_trace / reversal-events-v0.1` |
| 7 | `O8` / `o8-tpx-composite` | — | `o1-result`, `o5-result` | `tpx-component-trace / component_trace / tpx-component-trace-v0.1` |
| 8 | `O9` / `o9-dead-band-activity` | `stream.U` | `o1-mask`, `o4-mask`, `movement-events` | `micro-movement-events / event_trace / micro-movement-events-v0.1` |
| 9 | `O10` / `o10-recovery-time` | `stream.X`, `semantic.events`, `semantic.envelopes` | — | `recovery-events / event_trace / recovery-events-v0.1` |
| 10 | `O11` / `o11-disturbance-latency` | `stream.U`, `semantic.events`, `semantic.control_mappings` | — | `response-events / event_trace / response-events-v0.1` |
| 11 | `O12` / `o12-envelope-drift-latency` | `stream.X`, `stream.U`, `semantic.envelopes`, `semantic.control_mappings` | — | `correction-events / event_trace / correction-events-v0.1` |
| 12 | `O13` / `o13-physio-control-coupling` | `stream.X`, `stream.U`, `stream.ECG`, `semantic.phases` | `o1-profile`, `o5-profile`, `o7-profile`, `h4-result`, `h4-trace` | `joined-coupling-windows / window_trace / joined-coupling-windows-v0.1` |
| 13 | `H1` / `h1-aoi-dwell` | `stream.I`, `stream.G`, `semantic.aois`, `semantic.phases` | `gaze-aoi-intervals` | `phase-dwell / phase_trace / phase-dwell-v0.1` |
| 14 | `H2` / `h2-first-fixation-latency` | `stream.I`, `stream.G`, `semantic.events`, `semantic.aois` | `fixation-intervals` | `event-fixation-trace / event_trace / event-fixation-trace-v0.1` |
| 15 | `H3` / `h3-off-task-dwell` | `stream.I`, `stream.G`, `semantic.aois`, `semantic.phases` | `gaze-aoi-intervals` | `phase-off-task-dwell / phase_trace / phase-off-task-dwell-v0.1` |
| 16 | `H4` / `h4-ecg-fluctuation` | `stream.ECG`, `semantic.baselines`, `semantic.phases` | `control-physio-windows`, `ecg-hr-trace` | `control-physio-trace / window_trace / control-physio-trace-v0.1` |
| 17 | `H5` / `h5-eeg-fluctuation` | `stream.EEG`, `semantic.baselines`, `semantic.phases` | `eeg-engagement-windows` | `engagement-trace / window_trace / engagement-trace-v0.1` |

Every entry has exactly one table artifact recipe. That does not require every calculation state to emit a row or artifact; Task 11 permits a declaration-order subsequence. O5 may re-stage rows derived from its preprocessing product as a public anchor artifact: provider identity and anchor-producer identity remain different even if logical rows are equal.

O10–O12 share an event-detection helper inside the versioned plugin implementation closure. It is not a registered preprocessing recipe and does not create a seventh provider.

## 5. Exact dependency records

These are the only dependency objects in the packaged catalog. `anchor-result-0.2.0` is the expected session-result schema.

| ID | Kind | target | expected schema | expected kind | required |
|---|---|---|---|---|---:|
| `movement-events` | `preprocessing_dependency` | resource `movement-events-v1` | `movement-events-v1-output-v0.1` | `movement-events-table` | true |
| `o1-result` | `result_dependency` | anchor `O1` | `anchor-result-0.2.0` | — | true |
| `o5-result` | `result_dependency` | anchor `O5` | `anchor-result-0.2.0` | — | true |
| `o1-mask` | `artifact_dependency` | anchor `O1`, resource `desired-envelope-mask` | `desired-envelope-mask-v0.1` | `sample_mask` | true |
| `o4-mask` | `artifact_dependency` | anchor `O4`, resource `stable-hover-mask` | `stable-hover-mask-v0.1` | `sample_mask` | true |
| `o1-profile` | `algorithm_profile_dependency` | resource `o1-algorithm-profile` | `o1-algorithm-profile-output-v0.1` | — | true |
| `o5-profile` | `algorithm_profile_dependency` | resource `o5-algorithm-profile` | `o5-algorithm-profile-output-v0.1` | — | true |
| `o7-profile` | `algorithm_profile_dependency` | resource `o7-algorithm-profile` | `o7-algorithm-profile-output-v0.1` | — | true |
| `h4-result` | `result_dependency` | anchor `H4` | `anchor-result-0.2.0` | — | true |
| `h4-trace` | `artifact_dependency` | anchor `H4`, resource `control-physio-trace` | `control-physio-trace-v0.1` | `window_trace` | false |
| `gaze-aoi-intervals` | `preprocessing_dependency` | resource `gaze-aoi-intervals-v1` | `gaze-aoi-intervals-v1-output-v0.1` | `gaze-aoi-intervals-table` | true |
| `fixation-intervals` | `preprocessing_dependency` | resource `fixation-intervals-v1` | `fixation-intervals-v1-output-v0.1` | `fixation-intervals-table` | true |
| `control-physio-windows` | `preprocessing_dependency` | resource `control-physio-windows-v2` | `control-physio-windows-v2-output-v0.1` | `control-physio-windows-table` | true |
| `ecg-hr-trace` | `preprocessing_dependency` | resource `ecg-hr-trace-v1` | `ecg-hr-trace-v1-output-v0.1` | `ecg-hr-trace-table` | true |
| `eeg-engagement-windows` | `preprocessing_dependency` | resource `eeg-engagement-windows-v1` | `eeg-engagement-windows-v1-output-v0.1` | `eeg-engagement-windows-table` | true |

The required H4 result plus optional H4 trace is intentional. H4 `computed + U` without a signed-HR trace lets O13 produce `computed + U + physio_trace_unavailable`; a genuinely non-computed H4 result remains a required dependency failure.

## 6. Inline table descriptor rules

Every descriptor is:

```json
{
  "type": "table",
  "fields": [
    {"name": "...", "dtype": "...", "unit": "...", "nullable": false}
  ],
  "canonical_order_keys": ["..."]
}
```

No extra descriptor member is used in v0.1. Fields below are non-nullable unless the field name carries `?`, which means the descriptor has `nullable=true`. Text IDs use `utf8/id`; SHA-256 text uses `utf8/hex`; time uses `i64/ns`; counts use `i64/count`; booleans use `bool/bool`. Numeric units are explicit. A missed recovery/response/correction retains its finite observed wait and `missed=true`, while its nonexistent recovery/response onset is null; it is never replaced by the observation end and mislabeled as an actual onset.

| Schema ID | Ordered fields (`name:dtype:unit`) | Canonical order keys |
|---|---|---|
| `desired-envelope-mask-v0.1` | `phase_id:utf8:id`, `t_ns:i64:ns`, `source_row_id:i64:index`, `axis_order:i64:index`, `axis_id:utf8:id`, `inside:bool:bool` | `phase_id,t_ns,source_row_id,axis_order,axis_id` |
| `tracking-error-trace-v0.1` | `phase_id:utf8:id`, `t_ns:i64:ns`, `source_row_id:i64:index`, `error_x:f64:ft`, `error_y:f64:ft`, `error_z:f64:ft`, `error_norm:f64:ft` | `phase_id,t_ns,source_row_id` |
| `capture-trace-v0.1` | `event_id:utf8:id`, `t_ns:i64:ns`, `source_row_id:i64:index`, `overshoot:f64:ft`, `inside_hover:bool:bool` | `event_id,t_ns,source_row_id` |
| `stable-hover-mask-v0.1` | `phase_id:utf8:id`, `t_ns:i64:ns`, `source_row_id:i64:index`, `stable:bool:bool` | `phase_id,t_ns,source_row_id` |
| `movement-events-v0.1` | `phase_id:utf8:id`, `channel_id:utf8:id`, `event_t_ns:i64:ns`, `event_id:utf8:id`, `event_kind:utf8:id`, `amplitude:f64:percent_full_travel` | `phase_id,channel_id,event_t_ns,event_id` |
| `rms-contribution-trace-v0.1` | `phase_id:utf8:id`, `channel_id:utf8:id`, `start_t_ns:i64:ns`, `end_t_ns:i64:ns`, `rms:f64:percent_full_travel`, `weight:f64:ratio` | `phase_id,channel_id,start_t_ns,end_t_ns` |
| `reversal-events-v0.1` | `phase_id:utf8:id`, `channel_id:utf8:id`, `event_t_ns:i64:ns`, `event_id:utf8:id`, `amplitude:f64:percent_full_travel` | `phase_id,channel_id,event_t_ns,event_id` |
| `tpx-component-trace-v0.1` | `component_id:utf8:id`, `source_anchor_id:utf8:id`, `source_result_fingerprint:utf8:hex`, `state:utf8:id`, `score:f64:ratio` | `component_id` |
| `micro-movement-events-v0.1` | `phase_id:utf8:id`, `channel_id:utf8:id`, `event_t_ns:i64:ns`, `event_id:utf8:id`, `amplitude:f64:percent_full_travel` | `phase_id,channel_id,event_t_ns,event_id` |
| `recovery-events-v0.1` | `event_id:utf8:id`, `onset_t_ns:i64:ns`, `recovered_t_ns?:i64:ns`, `latency_ms:f64:ms`, `missed:bool:bool` | `event_id,onset_t_ns` |
| `response-events-v0.1` | `event_id:utf8:id`, `channel_id:utf8:id`, `onset_t_ns?:i64:ns`, `latency_ms:f64:ms`, `correct_sign:bool:bool`, `missed:bool:bool` | `event_id,channel_id` |
| `correction-events-v0.1` | `event_id:utf8:id`, `channel_id:utf8:id`, `exit_t_ns:i64:ns`, `onset_t_ns?:i64:ns`, `latency_ms:f64:ms`, `correct_sign:bool:bool`, `missed:bool:bool` | `event_id,exit_t_ns,channel_id` |
| `joined-coupling-windows-v0.1` | `window_id:utf8:id`, `start_t_ns:i64:ns`, `end_t_ns:i64:ns`, `phase_id:utf8:id`, `signed_delta_hr:f64:percent`, `control_score:f64:ratio`, `coupling_loss:f64:percent`, `window_hash:utf8:hex` | `start_t_ns,end_t_ns,window_id` |
| `phase-dwell-v0.1` | `phase_id:utf8:id`, `role_id:utf8:id`, `dwell_ns:i64:ns`, `weighted_dwell_ns:f64:ns`, `total_dwell_ns:i64:ns` | `phase_id,role_id` |
| `event-fixation-trace-v0.1` | `event_id:utf8:id`, `fixation_id:utf8:id`, `start_t_ns:i64:ns`, `end_t_ns:i64:ns`, `aoi_id:utf8:id`, `latency_ms:f64:ms` | `event_id,start_t_ns,fixation_id` |
| `phase-off-task-dwell-v0.1` | `phase_id:utf8:id`, `role_id:utf8:id`, `off_task:bool:bool`, `dwell_ns:i64:ns`, `total_dwell_ns:i64:ns` | `phase_id,role_id` |
| `control-physio-trace-v0.1` | `window_id:utf8:id`, `start_t_ns:i64:ns`, `end_t_ns:i64:ns`, `phase_id:utf8:id`, `median_hr_bpm:f64:bpm`, `signed_delta_hr:f64:percent`, `window_hash:utf8:hex` | `start_t_ns,end_t_ns,window_id` |
| `engagement-trace-v0.1` | `window_id:utf8:id`, `start_t_ns:i64:ns`, `end_t_ns:i64:ns`, `phase_id:utf8:id`, `channel_id:utf8:id`, `engagement_ratio:f64:ratio`, `delta_engagement:f64:percent`, `window_hash:utf8:hex` | `start_t_ns,end_t_ns,window_id,channel_id` |

For O1, `axis_id` has one row per envelope `metric_id` plus exactly one `joint` row for every `(phase_id,t_ns,source_row_id)`. Metric rows use the zero-based semantic envelope axis position as `axis_order`; the joint row uses `axis_order=len(axis_limits)`. Consumers such as O9 select only `axis_id="joint"`. This preserves the approved per-axis and joint masks without a profile-specific wide schema.

The declared `kind` is the middle value in section 4, and every recipe has `payload_kind="table"`.

## 7. Six preprocessing identities

These are the only Task 7 provider parameter resources. Provider implementations and registry entries remain absent until their scheduled tasks.

For the six reference recipes only, `recipe_id` and `provider_id` use the same string shown below. A `preprocessing_dependency.target_resource_id` still resolves in the execution-plan recipe namespace; equal spelling never authorizes a direct provider-registry lookup or bypasses `ResolvedPreprocessingRecipe` validation.

| Recipe/provider | version | parameter schema | output schema | artifact kind |
|---|---|---|---|---|
| `movement-events-v1` | `1.0.0` | `movement-events-v1-parameters-0.1` | `movement-events-v1-output-v0.1` | `movement-events-table` |
| `gaze-aoi-intervals-v1` | `1.0.0` | `gaze-aoi-intervals-v1-parameters-0.1` | `gaze-aoi-intervals-v1-output-v0.1` | `gaze-aoi-intervals-table` |
| `fixation-intervals-v1` | `1.0.0` | `fixation-intervals-v1-parameters-0.1` | `fixation-intervals-v1-output-v0.1` | `fixation-intervals-table` |
| `control-physio-windows-v2` | `2.0.0` | `control-physio-windows-v2-parameters-0.1` | `control-physio-windows-v2-output-v0.1` | `control-physio-windows-table` |
| `ecg-hr-trace-v1` | `1.0.0` | `ecg-hr-trace-v1-parameters-0.1` | `ecg-hr-trace-v1-output-v0.1` | `ecg-hr-trace-table` |
| `eeg-engagement-windows-v1` | `1.0.0` | `eeg-engagement-windows-v1-parameters-0.1` | `eeg-engagement-windows-v1-output-v0.1` | `eeg-engagement-windows-table` |

The provider output descriptors are exact, use `payload_kind="table"`, and follow the same primitive/nullable rules as section 6:

| Output schema | Ordered fields (`name:dtype:unit`) | Canonical order keys |
|---|---|---|
| `movement-events-v1-output-v0.1` | `phase_id:utf8:id`, `channel_id:utf8:id`, `event_t_ns:i64:ns`, `event_id:utf8:id`, `event_kind:utf8:id`, `amplitude:f64:percent_full_travel` | `phase_id,channel_id,event_t_ns,event_id` |
| `gaze-aoi-intervals-v1-output-v0.1` | `interval_id:utf8:id`, `start_t_ns:i64:ns`, `end_t_ns:i64:ns`, `gaze_source_row_id:i64:index`, `frame_id:utf8:id`, `aoi_id:utf8:id`, `role_id:utf8:id`, `association_valid:bool:bool` | `start_t_ns,end_t_ns,interval_id` |
| `fixation-intervals-v1-output-v0.1` | `fixation_id:utf8:id`, `start_t_ns:i64:ns`, `end_t_ns:i64:ns`, `aoi_id:utf8:id`, `role_id:utf8:id` | `start_t_ns,end_t_ns,fixation_id` |
| `control-physio-windows-v2-output-v0.1` | `window_id:utf8:id`, `start_t_ns:i64:ns`, `end_t_ns:i64:ns`, `phase_id:utf8:id`, `window_hash:utf8:hex` | `start_t_ns,end_t_ns,window_id` |
| `ecg-hr-trace-v1-output-v0.1` | `second_peak_id:utf8:id`, `second_peak_t_ns:i64:ns`, `rr_seconds:f64:s`, `hr_bpm:f64:bpm` | `second_peak_t_ns,second_peak_id` |
| `eeg-engagement-windows-v1-output-v0.1` | `window_id:utf8:id`, `start_t_ns:i64:ns`, `end_t_ns:i64:ns`, `phase_id:utf8:id`, `channel_id:utf8:id`, `engagement_ratio:f64:ratio`, `epsilon_used:f64:V^2`, `window_hash:utf8:hex` | `start_t_ns,end_t_ns,window_id,channel_id` |

A provider output schema ID never aliases a public anchor artifact schema ID. Task 7 tests keep these descriptors as an independent expected matrix; Task 9/13 later bind the same bytes into provider definitions and execution recipes.

## 8. Parameter schema resources

There are exactly 24 files: 18 anchor files plus the six provider files above. Filenames and `schema_id` use `*-parameters-0.1`, not `*-parameters-v0.1`. `load_parameter_schema(schema_id)` requires a separator-free Stable ID equal to the filename stem and performs exactly one lookup under `pilot_assessment.anchors.profile_data/parameters/`; it never scans, guesses aliases, or accepts a path.

Every file is a Draft 2020-12 object schema with:

- `$schema="https://json-schema.org/draft/2020-12/schema"`;
- a unique `$id` under `urn:cranfield:pilot-assessment:parameters:<schema_id>`;
- `x-schema-id` equal to the filename stem;
- `x-scientific-status="engineering_default"`;
- `type="object"` and `additionalProperties=false`;
- explicit `properties`, `required`, units, default values, and exact comparator/boundary metadata for every scoring or algorithm parameter used by the approved M4 design;
- no `quality`, `quality_gate`, `quality_gates`, `quality_transform`, `min_valid_coverage`, `failed_quality`, `invalid_quality`, or `binary_quality_v1` key at any depth.

The schemas must encode the engineering defaults already frozen in M4 design section 12, including strict/open comparator differences. A generic `direction=lower_is_better` is insufficient for O7, O9, O13, H3, or H4; their exact `<`, `<=`, `>=`, and band boundaries are explicit data.

Task 7 validates schema documents in tests using the development `jsonschema` dependency. Production parameter-instance validation belongs to Task 13; before that service is shipped, `jsonschema` must move to runtime dependencies or an equivalently specified validator must be approved. Task 7 does not silently add a second validator.

### 8.0 Authoritative bytes and property fragments

The packaged UTF-8 bytes are authoritative. Every parameter schema is serialized with the exact equivalent of:

```python
(json.dumps(document, ensure_ascii=False, allow_nan=False,
            sort_keys=True, indent=2) + "\n").encode("utf-8")
```

There is no BOM and exactly one terminal LF. Loading rejects duplicate JSON object keys, a non-canonical byte sequence, an `x-schema-id`/filename mismatch, or a schema that is not valid Draft 2020-12. `parameter_schema_sha256` is lowercase `SHA256(authoritative_file_bytes).hexdigest()` with no typed wrapper. It is intentionally distinct from `parameter_snapshot_fingerprint`, which hashes a materialized parameter value under Task 8.

The root object has exactly these members in its parsed form: `$schema`, `$id`, `x-schema-id`, `x-scientific-status`, `x-fixed-algorithm`, `type`, `properties`, `required`, and `additionalProperties`; each of the 18 anchor schemas additionally has exactly `x-scorer-policy-default`, while each of the six provider schemas forbids that member. `required` is the lexicographically sorted complete `properties` key set; the empty schema uses `[]`. No definition/reference/composition keyword or undeclared annotation is permitted.

Property fragments are exact rather than generator-private:

- a static number or integer property has exactly `type`, `default`, the applicable standard constraint members (`minimum`, `exclusiveMinimum`, `maximum`, `exclusiveMaximum`, or `enum`), `x-unit`, `x-owner`, and `x-comparison`; only constraint members required by the §8.2/§8.3 matrices are present;
- a static string property has exactly `type`, `default`, optional `enum`, `x-unit`, `x-owner`, and `x-comparison`; `x-unit="id"` and `x-comparison="exact"` apply when the matrix gives no numeric unit/comparator;
- a session-shaped array has exactly `type="array"`, `minItems`, its exact `items` object schema, `x-owner`, `x-default-source`, `x-unit`, and `x-comparison`; it has no JSON Schema `default`. `minItems=1` except O6 `channel_weights`, whose schema has `minItems=0` so a semantically not-applicable O6 can materialize `[]`;
- each array-item object has exactly `type`, `properties`, `required`, and `additionalProperties=false`; its `required` list is the lexicographically sorted complete item-property set. Nested item leaves contain `type`, applicable standard constraint members, `x-unit`, `x-owner`, and `x-comparison`, but neither `default` nor `x-default-source` because the complete array is materialized as one top-level value;
- `x-unit`, `x-owner`, `x-comparison`, and `x-default-source` values are strings. The owner is `anchor_plugin` for §8.2 and `preprocessing_provider` for §8.3.

Every top-level property has exactly one of `default` or `x-default-source`. The `x-comparison` vocabulary is exact: `gt`, `gte`, `lt`, `lte`, `closed_interval`, `left_closed_right_open`, `abs_lte`, `enum`, `exact`, or `cross_field`. The table text maps `>x` to `exclusiveMinimum=x`/`gt`, `>=x` to `minimum=x`/`gte`, `<x` to `exclusiveMaximum=x`/`lt`, `<=x` to `maximum=x`/`lte`, a closed interval to both inclusive bounds/`closed_interval`, and `[x,y)` to inclusive minimum plus exclusive maximum/`left_closed_right_open`. A phrase such as “positive” means `exclusiveMinimum=0`; “non-negative” means `minimum=0`. A parameter governed only by a multi-property or session-inventory relation uses `cross_field`; an unconstrained exact string uses `exact`; enum values use `enum`; nearest absolute-time tolerance uses `abs_lte`. Cross-field relations such as sum-to-one, `step<=length`, band ordering, semantic inventory equality, and Nyquist compatibility remain Task 13 checks and therefore do not invent an approximate single-property bound.

### 8.1 Exact annotation shape and ownership

Each resource validates only the `parameters` mapping passed to its named anchor plugin or preprocessing provider. Scorer thresholds are not visible to plugin code. An anchor resource carries this exact root annotation, compiled later into `ScorerPolicy`:

```text
"x-scorer-policy-default": {
  "scorer_id": "hard_threshold_v1",
  "scorer_version": "0.1.0",
  "policy_schema_id": "ordered-dau-threshold-policy-v0.1"
                      or "dau-conjunction-policy-v0.1",
  "parameters": {
    "state_order": ["unacceptable", "adequate", "desired"],
    "evaluation_order": ["desired", "adequate"],
    "rules": [
      {
        "state": "desired" or "adequate",
        "conditions": [
          {
            "metric_id": "primary_value" or a frozen raw-metric ID,
            "operator": "<" or "<=" or ">" or ">=",
            "value": finite number,
            "unit": unit ID
          }
        ]
      }
    ],
    "fallback_state": "unacceptable",
    "computed_u_overrides": [stable reason IDs in sorted order]
  }
}
```

The annotation object has exactly the four top-level members shown and `parameters` has exactly the five members shown. Each rule has exactly `state` and `conditions`; each condition has exactly `metric_id`, `operator`, `value`, and `unit`. Rules are evaluated in `evaluation_order` D-then-A order; the fallback is U. `state_order` remains the frozen likelihood-vector order `[unacceptable, adequate, desired]`. O3 uses two conditions per rule and the conjunction policy. The compiler constructs strict `ScorerPolicy(scorer_id, scorer_version, policy_schema_id, parameters, policy_hash)` without renaming or flattening a member, where:

```text
policy_hash = typed_json_sha256(
  "scorer-policy", "0.1.0",
  [scorer_id, scorer_version, policy_schema_id, parameters]
)
```

It validates that stored `policy_hash` by recomputation before plan acceptance. The annotation is never copied into `AnchorExecutionEntry.parameters`. M5-only likelihood strengths/dependence groups are absent.

Identity validation and later use share one immutable snapshot. `ScorerPolicy.parameters`, `AnchorExecutionEntry.parameters`, `AnchorExecutionEntry.temporal_recipe`, and `ResolvedPreprocessingRecipe.parameters` must each be recursively copied and frozen at contract construction with the existing dict/list-compatible `freeze_json_mapping`; a frozen outer Pydantic model alone is insufficient. Caller-owned nested mutations and post-construction item/list operations must therefore be unable to change a validated plan or scorer. Task 7 adds this contract hardening before any packaged scorer is consumed, and Tasks 8/12/13 retain recomputation at their named trust boundaries.

Every resource also carries:

```text
"x-fixed-algorithm": {
  "implementation_id": plugin or provider ID,
  "implementation_version": version,
  "source_spec": "m4-anchor-evidence-availability-design-2026-07-13",
  "source_section": "12.1" through "12.18"
}
```

For anchor schemas, `source_section` is the matching `12.1`–`12.18`. Provider schemas use the sections that define their algorithm: movement `12.5`, gaze AOI `12.14`, fixation `12.15`, control-physio windows `12.13`, ECG HR `12.17`, and EEG engagement `12.18`. Behavior outside the listed editable properties requires a new plugin/provider version rather than a same-version parameter edit, including O2 interpolation/extrapolation family, tie-breaks, formula aggregation, provided-R-peak mode, or EEG Welch construction. Property annotations use only `x-unit`, `x-owner` (`anchor_plugin` or `preprocessing_provider`), `x-comparison`, and optional `x-default-source`. Every materialized parameter is required before hashing. A static engineering default uses JSON Schema `default`; a session-shaped collection uses an exact `x-default-source` rule and is materialized before validation/hash. Empty parameter schemas are exactly `properties={}`, `required=[]`, `additionalProperties=false`.

Task 13 enforces cross-field rules that JSON Schema cannot express compactly: unique channel IDs, exact semantic channel inventory, positive conversions, weight sum 1, ordered bands/activation limits, and Nyquist compatibility. Session semantic/reference/runtime values are projections, not hidden defaults:

- envelope/hover limits, phases/events/applicability, targets/arrival axes, AOIs/weights/off-task roles, baselines/channel selection, active control channels, control lower/trim/upper and correct sign come only from `SessionSemanticSnapshot`;
- commanded path/frame/unit/table contracts come only from the resolved reference set;
- gap/support/source ordering/sampling identity come only from M3 and live input-table contracts;
- `W_min`, O6 channel weights, EEG unit conversion/mains setting, thresholds, DSP/grid and scorer settings come only from the parameter/execution-plan snapshot.

### 8.2 Exact anchor parameter properties

All integer durations are nanoseconds and remain inside the Task 8 safe-integer range. `{}` means the exact empty schema described above.

| Schema | Required parameter properties and defaults | Cross-field/default-source rule |
|---|---|---|
| `o1-parameters-0.1` | `{}` | native left-hold/per-axis+joint/minimum aggregation are fixed invariants |
| `o2-parameters-0.1` | `{}` | time-aligned-linear-v1, no extrapolation, 3D L2 and earliest/stable tie are fixed invariants |
| `o3-parameters-0.1` | `capture_hold_ns: integer=2000000000` (`ns`, `>=`) | optional shorter horizon comes from semantic event `opportunity_end_t_ns` |
| `o4-parameters-0.1` | `max_behavioral_excursion_ns: integer=0` (`ns`, `>=0`) | zero means no behavioral-excursion tolerance; never a data-gap repair |
| `o5-parameters-0.1` | `w_min_hz: number=1.0` (`Hz`, `>0`) | fixed plan value, never estimated from current pilot data |
| `o6-parameters-0.1` | `channel_weights: array<object>`; each item exactly `channel_id:string`, `weight:number>=0` | `x-default-source=equal_weights_over_o6_applicability_control_mappings_v1`; unique exact channel set and sum `1` after materialization |
| `o7-parameters-0.1` | `minimum_reversal_amplitude_pct: number=2.0` (`percent_full_travel`, `>=`); `minimum_reversal_separation_ns: integer=150000000` (`ns`, `>=`) | movement primitive remains provider-owned |
| `o8-parameters-0.1` | `{}` | TPX formula and `[0,1]` clip are fixed invariants; reads O1 precision and O5 normalized `W/W_min` primary, so O8 does not duplicate `w_min_hz` |
| `o9-parameters-0.1` | `nearest_match_tolerance_ns: integer=20000000` (`ns`, `abs(dt)<=`); `micro_movement_max_amplitude_pct: number=5.0` (`percent_full_travel`, `<=`) | inclusive lower amplitude comes from the bound movement provider's `0.5%` parameter, not a duplicate |
| `o10-parameters-0.1` | `adequate_exit_confirmation_ns: integer=100000000`; `recovery_horizon_ns: integer=15000000000`; `desired_hold_ns: integer=2000000000` | durations are positive except confirmation/hold allow `>=0`; actual end is clipped by semantic phase/opportunity/session |
| `o11-parameters-0.1` | `causal_median_window_ns=20000000`; `baseline_lookback_ns=1000000000`; `response_horizon_ns=2000000000`; `control_excursion_threshold_pct=5.0`; `minimum_excursion_duration_ns=100000000` | integer durations positive; excursion qualifies with strict `>5%` held `>=100 ms` |
| `o12-parameters-0.1` | `exit_confirmation_ns=100000000`; `causal_median_window_ns=20000000`; `baseline_lookback_ns=1000000000`; `correction_horizon_ns=2000000000`; `control_excursion_threshold_pct=5.0`; `minimum_excursion_duration_ns=100000000` | same type/unit rules as O11; independent ownership is intentional because no seventh event provider exists |
| `o13-parameters-0.1` | `control_weight_o1=0.50`; `control_weight_o5=0.25`; `control_weight_o7=0.25` (`ratio`, each `>=0`); `signed_hr_activation_start_pct=10.0`; `signed_hr_activation_full_pct=20.0` (`percent`) | weights sum `1`; activation start `<` full; O1/O5/O7 settings come only from algorithm-profile dependencies |
| `h1-parameters-0.1` | `{}` | AOI weights and pooled denominators are semantic/fixed-algorithm values |
| `h2-parameters-0.1` | `fixation_horizon_ns: integer=2000000000` (`ns`, `>0`) | actual end clips to semantic opportunity/session |
| `h3-parameters-0.1` | `{}` | AOI off-task roles and pooled denominator are semantic/fixed-algorithm values |
| `h4-parameters-0.1` | `{}` | HR mode/windows/epsilon owners are its provider dependencies |
| `h5-parameters-0.1` | `{}` | reads `epsilon_used` from the bound EEG provider rows; all rows must declare the same provider parameter value |

The following literal-fragment matrix, not the shorthand above, uniquely determines every non-empty anchor `properties` member. “source” means `x-default-source` and forbids `default`; every other row has the shown JSON `default`. `item.*` rows are nested leaves and therefore have neither. Constraints are exact JSON Schema members; `—` means none.

| Schema | Property | Type | Default/source | `x-unit` | `x-comparison` | Exact constraints |
|---|---|---|---|---|---|---|
| O3 | `capture_hold_ns` | integer | `2000000000` | `ns` | `gte` | `minimum=0` |
| O4 | `max_behavioral_excursion_ns` | integer | `0` | `ns` | `gte` | `minimum=0` |
| O5 | `w_min_hz` | number | `1.0` | `Hz` | `gt` | `exclusiveMinimum=0` |
| O6 | `channel_weights` | array | source `equal_weights_over_o6_applicability_control_mappings_v1` | `ratio` | `cross_field` | `minItems=0`; exact item object below |
| O6 | `item.channel_id` | string | — | `id` | `exact` | `pattern=^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$` |
| O6 | `item.weight` | number | — | `ratio` | `gte` | `minimum=0` |
| O7 | `minimum_reversal_amplitude_pct` | number | `2.0` | `percent_full_travel` | `gte` | `minimum=0` |
| O7 | `minimum_reversal_separation_ns` | integer | `150000000` | `ns` | `gte` | `minimum=0` |
| O9 | `nearest_match_tolerance_ns` | integer | `20000000` | `ns` | `abs_lte` | `minimum=0` |
| O9 | `micro_movement_max_amplitude_pct` | number | `5.0` | `percent_full_travel` | `lte` | `minimum=0` |
| O10 | `adequate_exit_confirmation_ns` | integer | `100000000` | `ns` | `gte` | `minimum=0` |
| O10 | `recovery_horizon_ns` | integer | `15000000000` | `ns` | `gt` | `exclusiveMinimum=0` |
| O10 | `desired_hold_ns` | integer | `2000000000` | `ns` | `gte` | `minimum=0` |
| O11 | `causal_median_window_ns` | integer | `20000000` | `ns` | `gt` | `exclusiveMinimum=0` |
| O11 | `baseline_lookback_ns` | integer | `1000000000` | `ns` | `gt` | `exclusiveMinimum=0` |
| O11 | `response_horizon_ns` | integer | `2000000000` | `ns` | `gt` | `exclusiveMinimum=0` |
| O11 | `control_excursion_threshold_pct` | number | `5.0` | `percent_full_travel` | `gt` | `minimum=0` |
| O11 | `minimum_excursion_duration_ns` | integer | `100000000` | `ns` | `gte` | `minimum=0` |
| O12 | `exit_confirmation_ns` | integer | `100000000` | `ns` | `gte` | `minimum=0` |
| O12 | `causal_median_window_ns` | integer | `20000000` | `ns` | `gt` | `exclusiveMinimum=0` |
| O12 | `baseline_lookback_ns` | integer | `1000000000` | `ns` | `gt` | `exclusiveMinimum=0` |
| O12 | `correction_horizon_ns` | integer | `2000000000` | `ns` | `gt` | `exclusiveMinimum=0` |
| O12 | `control_excursion_threshold_pct` | number | `5.0` | `percent_full_travel` | `gt` | `minimum=0` |
| O12 | `minimum_excursion_duration_ns` | integer | `100000000` | `ns` | `gte` | `minimum=0` |
| O13 | `control_weight_o1` | number | `0.50` | `ratio` | `cross_field` | `minimum=0` |
| O13 | `control_weight_o5` | number | `0.25` | `ratio` | `cross_field` | `minimum=0` |
| O13 | `control_weight_o7` | number | `0.25` | `ratio` | `cross_field` | `minimum=0` |
| O13 | `signed_hr_activation_start_pct` | number | `10.0` | `percent` | `cross_field` | — |
| O13 | `signed_hr_activation_full_pct` | number | `20.0` | `percent` | `cross_field` | — |
| H2 | `fixation_horizon_ns` | integer | `2000000000` | `ns` | `gt` | `exclusiveMinimum=0` |

The schema column abbreviates the matching lowercase `*-parameters-0.1` resource ID. O1/O2/O8/H1/H3/H4/H5 have no property rows because their empty schemas are exact. For O6, `items` is exactly the object fragment from §8.0 with the two listed leaves, `required=["channel_id","weight"]`, and `additionalProperties=false`.

For O6, the compiler selects only the matching O6 `AnchorApplicability.control_mapping_ids` and resolves each ID against `SessionSemanticSnapshot.control_mappings`. Duplicate mapping IDs are already forbidden, but several mappings may legitimately name one `control_channel_id`. Such mappings must have identical `(control_unit, lower, trim, upper)` calibration; disagreement is a compile error. `state_axis_id` and `correct_sign` do not participate in O6 magnitude calibration. For a repeated channel the lexicographically lowest `control_mapping_id` is its canonical calibration binding. The canonical channel inventory is the ASCII-lexicographically sorted unique channel-ID set.

When O6 is applicable, this inventory must be non-empty. If `channel_weights` is not supplied, the compiler materializes exactly one `{channel_id, weight=IEEE-754-binary64(1.0/N)}` item for each canonical channel. If an expert supplies explicit values, the compiler sorts them by `channel_id` and requires exact channel-set equality without duplicates. Every weight must be finite and non-negative, with `abs(math.fsum(weights) - 1.0) <= 1e-12`. When O6 is not applicable, its applicability references are empty by contract and exactly `channel_weights=[]` is required. The parameter snapshot is hashed only after this materialization and normalization. Task 13 enforces the complete matrix and never widens the set to event mappings, another anchor's applicability, or every session control channel. Calibration remains solely in the semantic snapshot; the equal-weight default does not make semantic control mappings the owner of weight values.

For O13, the three exact algorithm profiles below bind the resolved O1/O5/O7 closure; O13 does not keep a second copy.

### 8.3 Exact preprocessing-provider properties

| Schema | Required parameter properties and defaults |
|---|---|
| `movement-events-v1-parameters-0.1` | `grid_period_ns: integer=10000000`; `lowpass_cutoff_hz: number=5.0`; `lowpass_order: integer=4`; `filtfilt_padtype: string="odd"`; `filtfilt_padlen_cap_samples: integer=15`; `minimum_filter_sample_count: integer=3`; `derivative_deadband_pct_per_s: number=0.5`; `minimum_sign_run_ns: integer=50000000`; `minimum_movement_amplitude_pct: number=0.5` |
| `gaze-aoi-intervals-v1-parameters-0.1` | `{}`; ray/scene association, nearest positive depth, priority/stable-ID tie and `other_scene` mapping are fixed invariants |
| `fixation-intervals-v1-parameters-0.1` | `angular_velocity_threshold_deg_s: number=100.0`; `minimum_fixation_duration_ns: integer=100000000` |
| `control-physio-windows-v2-parameters-0.1` | `window_length_ns: integer=30000000000`; `window_step_ns: integer=5000000000` |
| `ecg-hr-trace-v1-parameters-0.1` | `{}`; `provided_r_peaks_v1`, second-peak RR assignment and median aggregation are fixed invariants |
| `eeg-engagement-windows-v1-parameters-0.1` | exact matrix below |

The following literal-fragment matrix uniquely determines every non-empty provider `properties` member. It uses the same Default/source, nested-item, owner, and exact-constraint rules as the anchor matrix; every row has `x-owner="preprocessing_provider"`.

| Schema | Property | Type | Default/source | `x-unit` | `x-comparison` | Exact constraints |
|---|---|---|---|---|---|---|
| movement | `grid_period_ns` | integer | `10000000` | `ns` | `gt` | `exclusiveMinimum=0` |
| movement | `lowpass_cutoff_hz` | number | `5.0` | `Hz` | `cross_field` | `exclusiveMinimum=0` |
| movement | `lowpass_order` | integer | `4` | `count` | `gt` | `exclusiveMinimum=0` |
| movement | `filtfilt_padtype` | string | `"odd"` | `id` | `enum` | `enum=["constant","even","odd"]` |
| movement | `filtfilt_padlen_cap_samples` | integer | `15` | `count` | `cross_field` | `minimum=0` |
| movement | `minimum_filter_sample_count` | integer | `3` | `count` | `gte` | `minimum=1` |
| movement | `derivative_deadband_pct_per_s` | number | `0.5` | `percent_full_travel_per_s` | `gt` | `minimum=0` |
| movement | `minimum_sign_run_ns` | integer | `50000000` | `ns` | `gte` | `minimum=0` |
| movement | `minimum_movement_amplitude_pct` | number | `0.5` | `percent_full_travel` | `gte` | `minimum=0` |
| fixation | `angular_velocity_threshold_deg_s` | number | `100.0` | `deg_per_s` | `lte` | `minimum=0` |
| fixation | `minimum_fixation_duration_ns` | integer | `100000000` | `ns` | `gte` | `minimum=0` |
| control-physio | `window_length_ns` | integer | `30000000000` | `ns` | `gt` | `exclusiveMinimum=0` |
| control-physio | `window_step_ns` | integer | `5000000000` | `ns` | `cross_field` | `exclusiveMinimum=0` |
| EEG | `channel_conversions` | array | source `selected_baseline_channels_uV_to_V_v1` | `unit_conversion` | `cross_field` | `minItems=1`; exact item object below |
| EEG | `item.channel_id` | string | — | `id` | `exact` | `pattern=^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$` |
| EEG | `item.input_unit` | string | — | `unit` | `exact` | `pattern=^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$` |
| EEG | `item.scale_to_volts` | number | — | `V_per_input_unit` | `gt` | `exclusiveMinimum=0` |
| EEG | `bandpass_low_hz` | number | `3.0` | `Hz` | `cross_field` | `exclusiveMinimum=0` |
| EEG | `bandpass_high_hz` | number | `35.0` | `Hz` | `cross_field` | `exclusiveMinimum=0` |
| EEG | `bandpass_order` | integer | `4` | `count` | `gt` | `exclusiveMinimum=0` |
| EEG | `bandpass_padtype` | string | `"odd"` | `id` | `enum` | `enum=["constant","even","odd"]` |
| EEG | `bandpass_padlen_cap_samples` | integer | `27` | `count` | `cross_field` | `minimum=0` |
| EEG | `minimum_filter_sample_count` | integer | `4` | `count` | `gte` | `minimum=1` |
| EEG | `minimum_psd_sample_count` | integer | `2` | `count` | `gte` | `minimum=2` |
| EEG | `mains_frequency_hz` | number | `50.0` | `Hz` | `enum` | `enum=[50.0,60.0]` |
| EEG | `notch_q` | number | `30.0` | `ratio` | `gt` | `exclusiveMinimum=0` |
| EEG | `notch_padtype` | string | `"odd"` | `id` | `enum` | `enum=["constant","even","odd"]` |
| EEG | `notch_padlen_cap_samples` | integer | `6` | `count` | `cross_field` | `minimum=0` |
| EEG | `window_length_ns` | integer | `4000000000` | `ns` | `gt` | `exclusiveMinimum=0` |
| EEG | `window_step_ns` | integer | `2000000000` | `ns` | `cross_field` | `exclusiveMinimum=0` |
| EEG | `welch_segment_length_ns` | integer | `2000000000` | `ns` | `gt` | `exclusiveMinimum=0` |
| EEG | `welch_overlap_fraction` | number | `0.5` | `ratio` | `left_closed_right_open` | `minimum=0`; `exclusiveMaximum=1` |
| EEG | `theta_low_hz` | number | `4.0` | `Hz` | `cross_field` | `minimum=0` |
| EEG | `theta_high_hz` | number | `8.0` | `Hz` | `cross_field` | `minimum=0` |
| EEG | `alpha_low_hz` | number | `8.0` | `Hz` | `cross_field` | `minimum=0` |
| EEG | `alpha_high_hz` | number | `13.0` | `Hz` | `cross_field` | `minimum=0` |
| EEG | `beta_low_hz` | number | `13.0` | `Hz` | `cross_field` | `minimum=0` |
| EEG | `beta_high_hz` | number | `30.0` | `Hz` | `cross_field` | `minimum=0` |
| EEG | `minimum_finite_bins_per_band` | integer | `2` | `count` | `gte` | `minimum=2` |
| EEG | `epsilon` | number | `1e-12` | `V^2` | `gt` | `exclusiveMinimum=0` |

The schema abbreviations are exact: movement=`movement-events-v1-parameters-0.1`, fixation=`fixation-intervals-v1-parameters-0.1`, control-physio=`control-physio-windows-v2-parameters-0.1`, and EEG=`eeg-engagement-windows-v1-parameters-0.1`. Gaze-AOI and ECG-HR are the exact empty provider schemas. EEG `channel_conversions.items` has exactly the three listed leaves, `required=["channel_id","input_unit","scale_to_volts"]`, and `additionalProperties=false`.

Movement comparisons are exact: filtering when `n>=3`, derivative sign only strictly outside `±0.5%/s`, run duration `>=50 ms`, and movement amplitude `>=0.5%`. Fixation qualifies at angular velocity `<=100 deg/s` for `>=100 ms`. Window length/step are positive and `step<=length`; phase-start, short-phase whole window, end-aligned tail, dedupe and half-open spans are fixed provider-v2 invariants.

EEG provider properties are exact:

| Property | Type/default | Unit/comparison |
|---|---|---|
| `channel_conversions` | array of exact `{channel_id:string,input_unit:string,scale_to_volts:number}`; no literal list default | `x-default-source=selected_baseline_channels_uV_to_V_v1`; exact selected channel set/live units; scale `>0` |
| `bandpass_low_hz`, `bandpass_high_hz` | number `3.0`, `35.0` | Hz; `0<low<high<Nyquist` |
| `bandpass_order` | integer `4` | count, `>0` |
| `bandpass_padtype` | string `"odd"` | ID |
| `bandpass_padlen_cap_samples` | integer `27` | count, `>=0` |
| `minimum_filter_sample_count` | integer `4` | count; filter iff `n>=4` |
| `minimum_psd_sample_count` | integer `2` | count; PSD iff `n>=2` |
| `mains_frequency_hz` | number `50.0`, enum `[50.0,60.0]` | Hz; explicit plan parameter, notch only when `<Nyquist` |
| `notch_q` | number `30.0` | ratio, `>0` |
| `notch_padtype` | string `"odd"` | ID |
| `notch_padlen_cap_samples` | integer `6` | count, `>=0` |
| `window_length_ns`, `window_step_ns` | integer `4000000000`, `2000000000` | ns; positive, step `<=` length |
| `welch_segment_length_ns` | integer `2000000000` | ns, positive |
| `welch_overlap_fraction` | number `0.5` | ratio, `[0,1)` |
| `theta_low_hz`, `theta_high_hz` | number `4.0`, `8.0` | Hz, `[low,high)` |
| `alpha_low_hz`, `alpha_high_hz` | number `8.0`, `13.0` | Hz, `[low,high)` |
| `beta_low_hz`, `beta_high_hz` | number `13.0`, `30.0` | Hz, `[low,high]` |
| `minimum_finite_bins_per_band` | integer `2` | count, `>=2` |
| `epsilon` | number `1e-12` | `V^2`, `>0` |

Every channel-conversion item has `additionalProperties=false`; the array is non-empty with unique channel IDs. The default-source rule materializes one `uV`/`1e-6` entry per semantic EEG baseline channel for the reference synthetic profile; another real input unit requires an explicit parameter revision, never runtime guessing. Constant demean/linear detrend, zero-phase SOS, periodic Hann, density/one-sided Welch, `detrend=false`, next-power-of-two FFT, trapezoidal bands, CAR, channel/baseline median, earliest-max tie, no ICA/clipping/channel removal and exact band endpoint inclusion are `x-fixed-algorithm` invariants.

### 8.4 Exact scorer defaults

The following table is serialized into the root annotation shape in §8.1. “A” is evaluated only after D fails; U is fallback. Override lists are sorted in the JSON resource.

| Anchor | D rule | A rule | Unit | computed-U overrides |
|---|---|---|---|---|
| O1 | `primary_value >= 90` | `primary_value >= 70` | percent | — |
| O2 | `primary_value <= 2` | `primary_value <= 5` | ft | — |
| O3 | `overshoot <=2` and `settling_time <=3` | `overshoot <=5` and `settling_time <=5` | ft, s | `capture_missed` |
| O4 | `primary_value >=10` | `primary_value >=5` | s | — |
| O5 | `primary_value <=2` | `primary_value <=4` | ratio | — |
| O6 | `primary_value <=30` | `primary_value <=50` | percent_full_travel | — |
| O7 | `primary_value <2` | `primary_value <4` | Hz | — |
| O8 | `primary_value >=0.6` | `primary_value >=0.4` | ratio | — |
| O9 | `primary_value <1` | `primary_value <2` | Hz | `no_stable_hover` |
| O10 | `primary_value <=5` | `primary_value <=10` | s | `recovery_missed` |
| O11 | `primary_value <=500` | `primary_value <=1000` | ms | `response_missed` |
| O12 | `primary_value <=300` | `primary_value <=800` | ms | `correction_missed` |
| O13 | `primary_value <5` | `primary_value <20` | percent | `physio_trace_unavailable` |
| H1 | `primary_value >=85` | `primary_value >=70` | percent | `no_gaze_dwell` |
| H2 | `primary_value <=500` | `primary_value <=1000` | ms | `fixation_missed` |
| H3 | `primary_value <5` | `primary_value <15` | percent | `no_gaze_dwell` |
| H4 | `primary_value <20` | `primary_value <40` | percent | `ecg_baseline_nonpositive`, `ecg_rr_unavailable`, `physio_trace_unavailable` |
| H5 | `primary_value <=20` | `primary_value <=50` | percent | `eeg_baseline_degenerate`, `eeg_spectrum_degenerate` |

`computed_u_overrides` are allowed only for an otherwise `computed` measurement and force U before scalar rules. They never convert missing/config/error states to computed. O3's metric IDs are exactly `overshoot` and `settling_time`; its normal `primary_value` remains null by design.

### 8.5 Exact O13 algorithm-profile closure

The three dependency outputs use the existing strict `ResolvedAlgorithmProfile` DTO without adding shadow fields:

| `profile_id` | `profile_version` | source anchor | `output_schema_id` |
|---|---|---|---|
| `o1-algorithm-profile` | `0.1.0` | O1 | `o1-algorithm-profile-output-v0.1` |
| `o5-algorithm-profile` | `0.1.0` | O5 | `o5-algorithm-profile-output-v0.1` |
| `o7-algorithm-profile` | `0.1.0` | O7 | `o7-algorithm-profile-output-v0.1` |

For each row, `ResolvedAlgorithmProfile.parameters` is an exact JSON object with these seven members and no others:

```text
{
  "semantic_snapshot_fingerprint": execution-plan semantic snapshot fingerprint,
  "source_entry": complete strict AnchorExecutionEntry JSON dump,
  "parameter_schema_sha256": authoritative resource SHA-256,
  "applicability": complete matching AnchorApplicability JSON dump,
  "input_table_contracts": [complete ResolvedInputTableContract dumps],
  "semantic_projection": {
    "phases": [complete SemanticPhase dumps],
    "envelopes": [complete EnvelopeDefinition dumps],
    "control_mappings": [complete ControlEffectMapping dumps]
  },
  "preprocessing_recipes": [complete ResolvedPreprocessingRecipe dumps]
}
```

The compiler reconstructs this complete expected object from the authoritative execution plan, semantic snapshot, registry, and packaged schema bytes; it does not validate the profile by trusting field-by-field copies inside the profile. It first validates every source self claim: source-entry definition/parameter/scorer, parameter-schema, preprocessing definition/implementation/schema/parameter, semantic-snapshot, and registry identities must already equal their recomputed values. It then selects values exactly:

- `source_entry` is the complete unique same-plan O1, O5, or O7 execution entry; exactly `source_entry.applicability == applicability.status`, `source_entry.phase_scope == applicability.phase_ids`, and `source_entry.event_scope == applicability.event_ids`;
- `semantic_snapshot_fingerprint` equals the execution plan and validated semantic snapshot value;
- `input_table_contracts` contains every plan input contract whose modality is in `source_entry.required_streams`, in canonical `(modality.value, table_role)` order, and no other contract;
- `applicability` is the complete one entry whose `anchor_id` is the source anchor;
- `phases` is the complete exact set named by `applicability.phase_ids`, in that already sorted ID order;
- O1 `envelopes` is the complete exact set named by `applicability.envelope_ids`, in that sorted order, and its `control_mappings` is empty;
- O5/O7 `control_mappings` is the complete exact set named by `applicability.control_mapping_ids`, in that sorted order, and their `envelopes` are empty;
- O1 `preprocessing_recipes` is empty; O5/O7 each contains exactly the resolved `movement-events-v1` recipe used by that source entry. Both may contain equal recipe dumps, but neither is inferred from the other profile.

Selection requires exact ID-set equality: an unknown, duplicate, missing, extra, or out-of-order projection is a compile error. For O1, every selected phase's non-null `envelope_id` must be in the selected envelope set and no selected envelope may be unreachable from the selected phases. For O5/O7, the selected control-channel set is the lexicographically sorted unique projection of the selected mappings; it must equal the channels materialized for that source algorithm. These are semantic-closure checks, not data-quality checks.

The outer DTO fields are exact:

```text
parameter_hash = parameter_snapshot_fingerprint(parameters)
               = typed_json_sha256("parameter-snapshot", "0.1.0", parameters)
implementation_digest = source_entry.implementation_digest
output_schema_id = the table value above
profile_version = source_entry.definition_version = "0.1.0"
```

The profile hash therefore binds the complete source algorithm configuration, scorer, semantic projection, input contract, and nested provider recipe; the outer implementation digest separately binds the executable source plugin. Task 13 reconstructs the entire expected `parameters` object, recomputes its hash, and requires `profile.implementation_digest == source_entry.implementation_digest ==` the verified registry implementation digest before accepting the plan. It also recomputes `source_entry.parameter_hash`, its scorer-policy hash, and every nested movement-recipe/provider identity. An applicable O13 requires its phase scope to be a subset of each source profile's applicable phase set and all three sources to be applicable for every O13 window phase; otherwise plan compilation rejects the inconsistent semantic closure.

O13 consumes only these three validated profiles plus its own declared X/U/ECG/phase and H4 dependencies. It does not instantiate O1/O5/O7 plugins or the movement provider through the registry, because an `AnchorPluginContext` intentionally has no registry/factory authority and source-plugin artifact emission would be incorrect. O1, O5, O7, the movement provider, the central scorer, and O13 instead call versioned shared pure algorithm/scoring primitives. Every primitive module used by O13 is listed in O13's implementation members and in each owning source plugin/provider implementation closure; the nested profile identities bind the corresponding configuration and implementation claims. For every control-physio window O13 clips the selected phases to the window and calls those pure primitives with the same support semantics, while emitting only O13 artifacts. It never reads session-wide O1/O5/O7 results, reconstructs a missing profile from catalog defaults, or replaces an unsupported component with `q=0`.

## 9. Honest registry resource

`anchors/registry-v1.json` is exactly:

```json
{
  "contract_id": "anchor-runtime-registry",
  "contract_version": "0.1.0",
  "entries": [],
  "preprocessors": []
}
```

It parses as `AnchorRuntimeRegistry`. Empty registry maps are not replaced with 18 fake `not_implemented` entries. Providers do not count toward the exact-18 anchor cardinality. The honest state after Task 7 remains 18/18 specified and 0/18 implemented.

## 10. Acceptance and mutation tests

Task 7 is complete only when lightweight resource tests prove items 1–7 and 10 below. Items 8–9 are frozen here but execute at their already scheduled owners, Task 8 for canonical hash vectors and Task 13 for complete plan/profile compilation and rejection:

1. exact entry IDs/order/versions/lifecycle/required/scorer/input/dependency/artifact matrix;
2. every inline descriptor has the exact ordered fields and order keys above;
3. reference profile rejects 17, 19, duplicate, reordered, gapped-order, non-active, or sentinel-missing catalogs, while generic catalogs may use another cardinality;
4. all 24 parameter schema filenames, canonical UTF-8 bytes, raw-byte SHA-256 values, `x-schema-id` values, exact root/property meta-contracts, defaults, comparator metadata, and recursive prohibited-field rules;
5. separator, traversal, alias, unknown profile, and unknown schema IDs fail before resource lookup can escape its package;
6. zero-entry registry parses and both executable inventories remain empty;
7. the wheel contains exactly one catalog, 24 explicit parameter schemas, the zero-entry registry, and package initializers;
8. exact scorer-annotation shape plus deterministic `ScorerPolicy` compilation/hash vectors at Task 8/13;
9. exact O1/O5/O7 algorithm-profile payload selection, hash and output identities, including mutation/rejection of every closure member at Task 8/13;
10. no test imports or invokes a production plugin, generates a session, or performs a performance/data-quality experiment.

Task 8 must replace the catalog sentinel and add canonical identity tests before M4-A is fully closed.

## 11. Self-review and expert boundary

- This amendment chooses stable engineering IDs and typed audit rows; it does not claim they are expert-validated aviation measures.
- Every artifact field is an algorithm output or provenance key already implied by the approved rule. No new scoring input is introduced.
- No row is filtered because performance or physiology is extreme. Missing mathematical output follows existing M4 statuses.
- O13's H4 distinction preserves, rather than changes, the approved `physio_trace_unavailable` semantics.
- Experts may later add/remove fields, change a formula, or alter a dependency through a new schema/plugin/model revision. Historical revisions remain replayable.
- Any change to the IDs, field order, units, dependencies, or comparator metadata in this document requires a new amendment or version; it is not an unreviewed JSON edit.
