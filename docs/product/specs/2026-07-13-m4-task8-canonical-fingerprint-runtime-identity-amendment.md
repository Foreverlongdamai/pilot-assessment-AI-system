# M4 Task 8 Canonical Fingerprint and Runtime Identity Amendment

**Status:** Accepted on 2026-07-13 under the user's autonomous-continuation authorization after two independent P0/P1 reviews reached PASS  
**Date:** 2026-07-13  
**Applies to:** M4 replacement plan Task 8 and the canonical-identity consumers in Tasks 9, 11, 13, 32, 34, and 35  
**Precedence:** This document closes representation and runtime-identity details left open by the approved M4 design, Task 3 amendment, and replacement plan. It changes no anchor formula, threshold, golden value, topology, scientific status, or M4/M5/M6 boundary.

> **2026-07-15 authority note:** Canonical-byte and replay identities remain valid for legacy Task 8 resources. The current M4R completion/extension architecture is [Expert-Editable Evidence and Assessment Model Design](2026-07-15-expert-editable-evidence-and-model-design.md); new recipe/operator identities will be specified thereunder.

## 1. Problems being closed

Task 8 already owns RFC 8785 typed hashes and installed numeric-runtime identity. Seven details must be exact before implementation:

1. RFC 8785 serializes IEEE-754 JSON numbers and the selected Python library rejects integers outside the I-JSON interoperable range; the accepted integer domain must not depend on library accident.
2. CPython on Windows may report no `SOABI` while providing an ABI-bearing `EXT_SUFFIX`.
3. Logical tables need one byte-level row representation rather than an informal “hash the rows” rule.
4. A wheel `RECORD` identity must exclude installation-root artifacts without silently omitting stable package members.
5. Pure fingerprint functions exclude their own claimed digest, but rejection of a false claimed digest belongs to the boundary that owns the complete object and bytes.
6. The Task 7 scorer annotation needs one exact non-recursive `ScorerPolicy.policy_hash` projection.
7. O13's three `ResolvedAlgorithmProfile.parameter_hash` values must reuse, rather than fork, the existing exact parameter-snapshot projection.

This amendment fixes those details while retaining the callable surface and ownership in the replacement plan.

## 2. Canonical JSON input domain

`jcs_bytes(value)` accepts only this recursive JSON domain:

- `None`, exact `bool`, exact `str`;
- exact `int` in `[-9007199254740991, 9007199254740991]`;
- finite exact `float` accepted by RFC 8785/ECMAScript number serialization;
- mappings whose keys are exact strings and whose values are in this domain;
- lists and tuples whose members are in this domain.

The projector checks `bool` before `int`. It rejects bytes, paths, sets, arbitrary iterables, non-string keys, NaN, positive/negative infinity, and integers outside the safe range. It does not stringify keys, convert a large integer to a decimal string, sort caller-owned sequences, or use `repr`. Contract models and enums are converted by the owning typed function with `model_dump(mode="json")`; arbitrary model objects are not accepted by `jcs_bytes` itself.

Mappings are copied to plain JSON mappings without changing key text. Tuples become JSON arrays. RFC 8785 owns UTF-16 object-key ordering, Unicode escaping without normalization, negative-zero handling, and finite float formatting. An unsupported Python shape raises `TypeError`; an unsafe integer, non-finite value, unpaired surrogate, or RFC 8785 serialization failure raises `ValueError`. Domain services later translate either to their already specified stable error code.

The safe-integer rule applies to every fingerprint payload, including offsets, timestamps, row IDs, table rows, parameters, and runtime metadata. A contract may accept a wider integer for storage, but it is not canonically hashable in M4 v0.1 and must fail before execution-plan acceptance. Current M4 session limits remain inside this domain.

## 3. Typed framing and fixed identity table

Every typed digest retains the approved framing:

```text
SHA256(ASCII(type_id) || 0x00 || ASCII(schema_version) || 0x00 ||
       uint64_big_endian(len(JCS(payload))) || JCS(payload))
```

`type_id` and `schema_version` must be non-empty ASCII strings without NUL. The length is the JCS byte length, not character count. The following identities are exact:

| Callable or projection | type ID | version |
|---|---|---|
| inline descriptor | `typed-inline-schema-descriptor` | `0.1.0` |
| logical table | `logical-table` | `0.1.0` |
| semantic snapshot | `session-semantic-snapshot` | `0.1.0` |
| reference table contract | `reference-table-contract` | `0.1.0` |
| reference resource | `reference-resource` | `0.1.0` |
| reference alignment | `reference-alignment` | `0.1.0` |
| resolved reference set | `resolved-reference-set` | `0.1.0` |
| anchor catalog | `anchor-catalog` | `0.1.0` |
| execution plan | `anchor-execution-plan` | `0.1.0` |
| anchor plugin definition | `anchor-plugin-definition` | `0.1.0` |
| preprocessing definition | `preprocessing-provider-definition` | `0.1.0` |
| plugin implementation | `plugin-implementation` | `0.1.0` |
| preprocessing implementation | `preprocessing-implementation` | `0.1.0` |
| runtime registry | `anchor-runtime-registry` | `0.1.0` |
| numeric runtime RECORD | `numeric-runtime-record` | `0.1.0` |
| parameter snapshot | `parameter-snapshot` | `0.1.0` |
| scorer policy | `scorer-policy` | `0.1.0` |
| anchor result | `anchor-result` | `0.2.0` |
| evaluation report | `anchor-evaluation-report` | `0.1.0` |

`logical_artifact_identity_payload` is a nested projection used by result/report identities, not a separately typed digest. `PythonRuntimeIdentity` and `NumericRuntimeIdentity` are strict identity records embedded in implementation payloads, not self-fingerprinted objects.

Definition, catalog, plan, result, report, and registry projections use the contract ID/version in their strict model. A mismatch between the expected literal and the model is impossible after strict parsing and must never be replaced by a caller-supplied type ID.

### 3.1 Scorer and algorithm-profile callables

`scorer_policy_fingerprint(policy)` hashes this exact payload with `scorer-policy/0.1.0`:

```text
[
  policy.scorer_id,
  policy.scorer_version,
  policy.policy_schema_id,
  policy.parameters
]
```

It excludes only `policy.policy_hash`. A scorer annotation compiler first builds the other four strict fields, computes this digest, then constructs `ScorerPolicy`; a plan loader recomputes and rejects any stale claim before use.

`ResolvedAlgorithmProfile.parameter_hash` is exactly `parameter_snapshot_fingerprint(profile.parameters)`, using the already fixed `parameter-snapshot/0.1.0` identity. It excludes the outer `parameter_hash`, `implementation_digest`, profile ID/version, and output-schema ID because those are separate strict outer fields bound by the complete execution-plan fingerprint. The Task 7 amendment fixes the exact permitted inner member set and selection rules. Task 13 first validates every nested claim, recomputes this parameter hash, checks the exact profile ID/version/output-schema triple and source-plugin implementation digest, and only then exposes the profile to O13. Neither callable repairs a stale claim, and no second algorithm-profile hash type is introduced.

## 4. Exact logical-table payload

`schema_descriptor_sha256(schema_id, descriptor)` hashes:

```text
[schema_id, complete_schema_descriptor]
```

using the inline-descriptor identity above. No wrapper key is added.

`logical_table_sha256(schema_id, schema_descriptor, rows, order_keys)` hashes this exact payload:

```text
[
  [schema_id, complete_schema_descriptor, [order_key, ...]],
  [
    [row_0_field_0, row_0_field_1, ...],
    [row_1_field_0, row_1_field_1, ...]
  ]
]
```

The descriptor must have exactly `type`, `fields`, and `canonical_order_keys`; each field has exactly `name`, `dtype`, `unit`, and `nullable`. Its ordered `fields` list is authoritative for row-array order. Every row mapping must have exactly that field-name set; no missing or extra field is tolerated. Values must match the declared primitive strictly, including integer dtype bounds, the JCS safe range, exact bool-vs-int separation, nullable/null rules, finite floats, and Unicode strings without unpaired surrogates. `order_keys` must equal the descriptor's `canonical_order_keys`, each key must name a non-nullable field, and the incoming rows must be strictly increasing by the complete declared key tuple. For this tuple comparison, signed/unsigned integers and finite floats use mathematical numeric order within their declared dtype, booleans use `false < true`, and strings use lexicographic Unicode scalar-value/code-point order; fields of different declared dtypes are never compared as aliases. The function validates and hashes; it never sorts or coerces rows. Zero rows are allowed when the surrounding artifact contract permits them.

Logical identity excludes path, compression, writer version/options, row-group layout, host, wall time, and storage checksum. The ordered descriptor, schema ID, canonical order keys, row count implied by the array, every logical value, and row order are bound.

For `aligned_reference_content_fingerprint`, `ReferenceTableContract` maps to this exact inline descriptor without aliases:

```text
{
  "type": "table",
  "fields": [
    {
      "name": field.field_name,
      "dtype": field.dtype_id,
      "unit": field.unit,
      "nullable": field.nullable
    }
    for field in contract.fields in declared order
  ],
  "canonical_order_keys": list(contract.canonical_order_keys)
}
```

Polars values are projected to the same JSON primitives and the rows must already satisfy `(t_ns, stable_row_id_field)`. No DataFrame repr, Arrow metadata, or physical file detail enters the digest.

## 5. Result and evaluation projections

`logical_artifact_identity_payload(ref)` is `ref.model_dump(mode="json")` excluding only `storage_file_sha256`. It retains artifact/kind/schema IDs, logical content hash, row count, bounds, grid hash, producer identity, parameter hash, and ordered dependency fingerprints.

`anchor_result_fingerprint_payload(result)` is the complete strict JSON dump excluding only `result_fingerprint`; its `derived_artifacts` value is replaced in declared order by `logical_artifact_identity_payload(ref)` for each ref.

`evaluation_fingerprint_payload(report)` is the complete strict JSON dump excluding only `evaluation_fingerprint`, with exactly two projection changes:

1. `results` becomes the array of already recomputed and validated `result_fingerprint` values in canonical report-result order;
2. a new key `reachable_logical_artifacts` contains the flattened artifact payloads in that same result order and, within each result, `derived_artifacts` declaration order.

The flattened list is not sorted or deduplicated. A blocked report has empty `results` and `reachable_logical_artifacts`. Inventory result fingerprints, counts, diagnostics, catalog/registry/plan identities, scientific status, and `formal_run_authorized` remain in the complete report projection. Task 11/13 validates each result and artifact against live immutable payloads before this pure projection is called.

## 6. Exact semantic/reference projections

The Task 3 amendment §6.4 remains authoritative:

- semantic snapshot: complete strict dump excluding only `semantic_snapshot_fingerprint`;
- table contract: complete strict dump excluding only `table_contract_fingerprint`;
- resource: `[reference_id, source_kind, runtime_view_role, source_schema_id, table_contract_fingerprint, [[path, checksum], ...]]`;
- aligned content: the logical-table representation from §4 with the explicit aligned schema ID;
- alignment: complete session identity, reference/source/runtime role, complete alignment contract, clock/source/aligned schema IDs, and table/resource/content fingerprints;
- resolved set: complete strict dump excluding only `reference_set_fingerprint`.

The alignment payload is this exact named object and is valid only for a `present` descriptor:

```text
{
  "session_identity": complete ReferenceSessionIdentity dump,
  "reference_id": descriptor.reference_id,
  "source_kind": descriptor.source_kind,
  "runtime_view_role": descriptor.runtime_view_role,
  "alignment_contract": complete ReferenceAlignmentContract dump,
  "clock_id": descriptor.clock_id,
  "source_schema_id": descriptor.source_schema_id,
  "aligned_schema_id": descriptor.aligned_schema_id,
  "table_contract_fingerprint": descriptor.table_contract.table_contract_fingerprint,
  "resource_fingerprint": descriptor.resource_fingerprint,
  "aligned_content_fingerprint": descriptor.aligned_content_fingerprint
}
```

An absent descriptor participates only in the resolved-set projection. Resource, content, and alignment functions reject it rather than inventing empty hashes.

Task 8 computes these identities from already bound objects. It does not resolve a source, construct a reference candidate, guess a frame/unit, or repair row order.

## 7. Self-field exclusion and rejection ownership

Changing only a self-reported digest does not change its recomputed value because the corresponding projection excludes that field. That is necessary to avoid recursion; it does not make the claim trustworthy.

| Object/claim | Task 8 proof | Boundary that rejects a false claim |
|---|---|---|
| packaged catalog fingerprint/sentinel | recompute; packaged loader rejects sentinel or mismatch | Task 8 catalog loader |
| distribution `RECORD` digest/size | recompute installed member bytes | Task 8 runtime-identity function |
| logical artifact ref | recompute logical payload and compare immutable resolved dependency | Task 8 `validate_logical_artifact_ref` and later transaction use |
| plugin/provider definition and implementation digest | expose pure recomputation | Task 9 registry verifier |
| semantic/reference snapshots | expose pure recomputation | Task 13 evaluator boundary and Task 35 packaged loader |
| execution plan/request | expose pure recomputation | Task 13 request/plan validation |
| result/report | expose pure recomputation | Tasks 11 and 13 transaction/evaluator closure |

Task 8 tests must prove projection exclusion for every owned pure function, but they assert mismatch rejection only at the three Task 8-owned boundaries above. Catalog/runtime mismatches reject before plugin execution; an emitted artifact ref necessarily rejects after its producer ran but before downstream consumption or evaluation commit. Later-task rejection tests remain mandatory and are not falsely claimed complete in Task 8.

`validate_logical_artifact_ref` first requires the returned ref to equal the immutable resolved ref, then recomputes content from the immutable payload. Table payloads use `logical_table_sha256`; opaque blobs use raw `SHA256(payload_bytes)` and require logical and storage digests to be equal. The validator also checks exact artifact/kind/schema identity, row count, optional bounds, and grid hash. It never trusts a plugin-returned ref to locate or reinterpret payload bytes.

The Task 7 catalog's 64-zero `task8-uncomputed-sentinel` is replaced after the real catalog digest is generated. From that point `load_packaged_catalog()` rejects both the sentinel and any stale digest; it never silently repairs packaged bytes.

## 8. Python runtime ABI identity

`python_runtime_identity()` reads:

- `sys.implementation.name`;
- exact `sys.version_info[:3]`;
- `sys.implementation.cache_tag`;
- ABI tag by the following precedence.

ABI precedence is exact:

1. use non-empty `sysconfig.get_config_var("SOABI")`;
2. only on Windows, when `SOABI` is missing, parse non-empty `EXT_SUFFIX` matching exact ASCII `\.([A-Za-z0-9][A-Za-z0-9_-]*)\.pyd` and use capture group 1 as the complete `<abi-tag>` (for example `cp311-win_amd64` or a future debug/free-threaded variant);
3. otherwise reject runtime identity construction.

The parser rejects path separators, additional suffix components, empty tags, and non-`.pyd` Windows values. It does not synthesize an ABI from Python version or platform strings. A missing implementation name, cache tag, or exact three-part version is also rejected.

## 9. Installed distribution identity

Distribution names use PEP 503 normalization: lowercase and collapse every run of `-`, `_`, or `.` to one `-`. The installed distribution's metadata `Name` is authoritative. CLI inputs that resolve to duplicate normalized names are rejected before hashing; output identities are sorted by normalized name.

`distribution_content_identity(name)` rejects editable installs and requires a wheel-style `RECORD`. Before excluding mutable metadata, it reads the owning `.dist-info/direct_url.json` when present with a duplicate-key-rejecting strict JSON decoder; if the strict JSON object has `dir_info.editable is true`, identity construction rejects. A duplicate key, malformed `direct_url.json`, non-boolean `editable`, or editable install without wheel `RECORD` also rejects. A non-editable direct URL does not enter the digest. It then parses `RECORD` once, requires exactly three CSV cells in every row, and classifies every row:

1. require a relative POSIX path and reject an absolute path, backslash, empty component, `.` component, duplicate normalized path, or case-fold alias;
2. resolve the raw relative path lexically from the distribution root without following a symlink; a path containing `..` is excluded only when it resolves to a member under the active interpreter's exact `sysconfig.get_path("scripts")` directory, otherwise it is rejected as traversal/alias input;
3. exclude the owning distribution's own `RECORD`, `INSTALLER`, `REQUESTED`, and `direct_url.json` entries, plus `__pycache__` members and `.pyc`/`.pyo`; a package resource elsewhere with one of those basenames is not excluded;
4. require every remaining member to resolve inside the installed site-packages distribution root and require exactly a `sha256=<urlsafe-base64-no-padding>` declaration plus a non-negative decimal byte size;
5. reject a retained symlink or a retained member whose real path escapes the site-packages root; otherwise read that installed file, recompute SHA-256 and size, and reject any mismatch or missing file;
6. sort by relative POSIX path using lexicographic Unicode scalar-value/code-point order after rejecting unpaired surrogates, and hash the JCS array `[relative_path, "sha256", declared_urlsafe_digest, size]` for every retained member with type `numeric-runtime-record` / version `0.1.0`.

The declared URL-safe digest must decode to exactly 32 bytes and re-encode to the identical canonical unpadded text. An in-root stable member without a declared SHA-256/size is an error, not an omitted row. Excluded mutable/install-root members do not enter the digest. At least one retained stable member is required.

The replacement plan's `NumericRuntimeIdentity.record_content_sha256` is the digest from step 6. This proves content-declaration identity for the installed wheel; it is not a claim that two independently built wheels are reproducible.

## 10. CLI and two-environment test

The module CLI:

```text
python -m pilot_assessment.anchors.fingerprint runtime-identity numpy scipy rfc8785
```

writes exactly one RFC-8785 canonical JSON value plus one LF:

```text
[
  {complete PythonRuntimeIdentity fields},
  [
    {complete NumericRuntimeIdentity fields in normalized-name order}
  ]
]
```

It writes diagnostics to stderr and returns non-zero on an invalid/duplicate distribution, editable install, invalid `RECORD`, missing ABI identity, or canonicalization failure. Absolute paths never appear in stdout.

The packaging test uses the same Python micro version/platform, builds the project wheel once, installs that same wheel plus the same locked dependency wheels into two temporary venv roots, changes the child working directory outside the repository, clears `PYTHONPATH`, invokes the installed module CLI in each, and compares stdout bytes. One invocation reverses the distribution argument order and must still emit the same normalized-name order. It does not build twice and therefore proves install-root independence, not build reproducibility. This is the sole environment-level Task 8 test; all other tests use tiny in-memory JSON/table vectors and fresh subprocesses, never generated session data.

## 11. Acceptance and mutation tests

Task 8 is complete only when lightweight tests prove:

1. published RFC 8785/JCS vectors, exact typed framing, Unicode/map/float behavior, non-finite rejection, and both safe-integer boundaries plus one value outside each boundary;
2. exact type/version constants above, exact scorer/profile projections and self-field exclusions, and no caller-selected identity for strict contract types;
3. descriptor and logical-table row-array payloads, exact-field closure, declared order, duplicate-key rejection, and storage/path independence;
4. all Task 3 semantic/reference mutation vectors and self-field exclusions;
5. catalog sentinel replacement plus stale/sentinel loader rejection;
6. Windows `SOABI` preference, valid `EXT_SUFFIX` fallback, preservation of ABI suffix variants, and invalid/missing tag rejection through monkeypatching;
7. PEP 503 normalization, duplicate CLI names, duplicate `direct_url.json` keys, exact-three-cell RECORD rows, traversal/alias/editable/missing/member/hash/size failures, exclusion rules, code-point path order, and stable-member changes;
8. byte-identical CLI output from the same wheel installed under two roots;
9. definition, implementation, registry, catalog, parameter, plan, artifact, result, and report projections change for every logical field specified by the replacement plan while their own self-field is excluded;
10. owned mismatch rejection occurs before the relevant value is trusted or consumed—catalog/runtime before plugin execution and artifact ref before downstream consumption/evaluation commit—and later-owner tests remain explicitly pending.

Task 8 runs twice in fresh processes. No test creates a dense multimodal fixture, evaluates an anchor formula, or makes a data-quality judgment.

## 12. Self-review and expert boundary

- The amendment defines byte identity and replay evidence only; it cannot make an engineering-default anchor scientifically valid.
- Extreme but finite simulator performance/physiology remains hashable and is not filtered. Only values outside the canonical data type, such as non-finite JSON numbers or unsafe integers, are representation errors.
- Runtime content identity detects code/resource/runtime changes without binding a machine path. It does not certify supply-chain provenance or independently reproducible builds.
- Self-field exclusion is explicit and paired with a named validation owner; no layer may cite pure recomputation as proof that an untrusted claim was checked.
- Changes to canonical payloads, type IDs, integer range, ABI precedence, or `RECORD` inclusion rules require a new version or amendment because they change replay identity.
