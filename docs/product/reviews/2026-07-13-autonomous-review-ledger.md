# 2026-07-13 Autonomous Review Ledger

| 字段 | 当前值 |
|---|---|
| 授权来源 | 用户于 2026-07-13 明确要求持续推进，并声明休息期间的中间复核方案默认批准 |
| 适用目标 | 完成 M4，并形成、复核和保存 M5/M6 正式规格与实施计划 |
| 结束条件 | 用户明确要求恢复逐次批准模式 |
| 不授权事项 | 自动 push、发布、外部消息、科学有效性声明，或超出 M4–M6 既定产品边界的不可逆变更 |

## Review protocol

1. 每个新设计或定向修订都必须写入 `docs/product/specs/`，完成 placeholder、矛盾、类型和 scope 自审。
2. 重要合同、ownership、状态或 provenance 变化至少接受两路独立 P1 复核；发现 P1 后修订并重新复核到 PASS。
3. 方案在本授权窗口内可记录为“默认批准”并继续实施，不需要等待聊天确认；但必须保留规格、review 结论和独立 Git 提交。
4. 行为实现坚持 RED→GREEN；每个任务按 replacement plan 的文件和提交边界执行，并在进入下一任务前运行聚焦验证。
5. 公式、阈值、M4/M5/M6 ownership 或正式运行授权语义若需要改变，必须另写 amendment。若变化超出已有目标或可能造成不可逆兼容性后果，则只形成候选并列入用户后续复核，不自动实施。
6. 外部 Claude/Codex/Gemini CLI 仅在用户授权范围内用于只读复核；记录实际模型、模式、输入范围和输出结论。工具不可用时如实记录，不伪称已复核。

## Review entries

### AR-001 — M4 Task 3 Reference Candidate Binding Amendment

| 字段 | 记录 |
|---|---|
| Artifact | `docs/product/specs/2026-07-13-m4-task3-reference-candidate-binding-amendment.md` |
| Candidate commit | `5aca9e2` |
| Approval | 用户于 2026-07-13 明确批准该修订候选 |
| Independent reviews | 两路只读子代理复核；每轮只报告 P1 |
| 主要关闭项 | M3 mapping provenance、required-reference inventory、pre-request/report 分界、artifact side channel、M3 annotation identity、Task 32/35 producer 边界、单一 reference cardinality |
| 最终结论 | 两路均 PASS；随后执行 D-028、主规格和 replacement plan 迁移 |
| 未覆盖 | Task 3 生产代码、Task 8 canonical fingerprints、Task 35 packaged producer 尚需各自 TDD/完成门 |

后续 review entry 采用 `AR-002` 起的连续编号追加，不覆盖 AR-001。

### AR-002 — M4 Task 3 Authority Migration and Request Closure

| 字段 | 记录 |
|---|---|
| Artifacts | M4 主规格、Task 3 binding amendment、replacement plan、D-028、status/overview/validation/self-review/glossary/session-bundle 口径与本 review ledger |
| Baseline | `5aca9e2`（candidate 文档 commit）；本 entry 复核其后的 docs-only authority migration working tree |
| Approval | 用户于 2026-07-13 批准修订候选，并在休息期间明确授权中间方案默认批准、保存复核证据后持续推进 |
| Internal reviewers | 两路独立只读子代理：一条检查跨文档迁移/状态/错误语义，一条检查 DTO、M3 现实模型与 Task 4/8/13 实现可行性 |
| External reviewer | WSL Claude CLI `2.1.195`，显式模型 `claude-fable-5`、`--effort xhigh`、safe/plan/read-only tools；prompt 含 `ultracode`，但实际 ultracode activation 无法验证，因此不作此声明 |
| External successful findings | 首轮指出 dynamic AOI 未闭合 current I view + plan profile contract、applicability inventory 未在 Task 4/13 落地；后续轮指出 input dtype 词表、active lifecycle、input-contract tamper vector 与 core-stream finite-scan ownership需明确 |
| 主要关闭项 | 新增并冻结两层 `ResolvedInputTableContract`；`CoreModality`/primitive dtype/active-only plan；report-aligned modalities 与 runtime views 双向等价；五类 optional non-aligned 状态下沉 `missing_input`；dynamic AOI 条件 live binding；applicability exact inventory；aligned-content schema fingerprint 参数；binder/request 两阶段稳定错误及 deterministic precedence；pre-request 无 M4 report；Task 8/13 tamper/no-bypass tests |
| Final internal result | 两路均 P0=0、P1=0、PASS；Markdown relative links、fence parity 与 diff checks 通过 |
| Final external retry | 第一次返回 Claude server `529 Overloaded`；第二次返回 session limit。未获得最终 external PASS，不把成功的早期 finding review 冒充最终确认 |
| Release conclusion | 依据两路最终内部 PASS，docs-only migration 可提交并进入 replacement Task 3 TDD；Task 3/8/13/35 的代码能力仍必须分别通过计划中的 RED→GREEN gate |

### AR-003 — M4 Task 4 Catalog, Plan, and Request Contracts

| 字段 | 记录 |
|---|---|
| Artifacts | `contracts/anchor_execution.py`、`anchors/models.py`、两份 Task 4 聚焦测试与 replacement plan Task 4 口径 |
| Approval | 用户已批准 replacement M4 plan，并授权休息期间的中间收口默认批准；本次未改变 M4/M5/M6 ownership 或科学口径 |
| TDD evidence | 初始 RED 为缺少 catalog/plan/request DTO；联合实现后 31 tests GREEN；对抗复核新增 annotation/baseline exact identity、applicability scope/status、dynamic AOI order、runtime type guard、model/task profile 解耦、inline schema 和 registry canonical closure 等 RED→GREEN 回归，最终 Task 4 focused 39 passed |
| First internal review | 两路独立只读复核发现：错误地令 assessment `model_profile_id` 等于 simulator `task_profile_id`；blob byte/media contract 不完整；registry closure 未排序；同一 schema ID 可映射不同 descriptor；table descriptor 未完全 typed；少量稳定错误与优先级测试缺口 |
| Resolutions | 解耦两个 profile namespace；blob 固定 `media_type`/`content_encoding`；table field 固定 `name/dtype/unit/nullable` 与 primitive dtype；definition/catalog/plan 强制 schema-ID descriptor 唯一；members/runtimes/registry maps 强制 canonical order；补齐完整 baseline/schema/applicability/AOI 及错误优先级校验，且不加入有限值扫描或数据质量 gate |
| Final internal result | 两路复核均 P0=0、P1=0、PASS；其中一路运行反向最小探针，确认逆序 closure、untyped descriptor、非法 dtype 与 schema-ID 冲突均被拒绝 |
| External retry | WSL Claude CLI 显式请求 `claude-fable-5`、`--effort xhigh`、plan/read-only tools，prompt 说明 ultracode-style；服务返回 session limit，未产生本轮外部复核结论，也不声明 ultracode activation 已验证 |
| Release conclusion | Task 4 contract closure 可提交并进入 Task 5；残余建议仅为轻量 P2 测试细化，不阻塞合同边界 |

### AR-004 — M4 Task 5 Measurement, Report, and Runtime Boundary Contracts

| Field | Record |
|---|---|
| Artifacts | `contracts/common.py`, `contracts/errors.py`, `contracts/anchor_v2.py`, `contracts/anchor_execution.py`, `anchors/protocols.py`, the Task 5 contract test/fixture, and the checked Task 5 plan section |
| Approval | Covered by the user-approved replacement M4 plan and the user's temporary authorization to treat intermediate closures as approved while preserving review evidence |
| TDD evidence | Initial RED was missing Task 5 contracts/protocols. Adversarial REDs then covered non-JSON/non-finite projections, aliasing, mutable table exposure, wrapper mismatch, key/object identity, recursively mutable diagnostic/profile JSON, inconsistent artifact row/bounds/grid identity, and list-shape serialization warnings |
| First internal findings | Two independent read-only reviewers found shallow runtime validation, writable DataFrame/JSON surfaces, missing stream/reference key identity, incomplete ref/payload closure, and a tuple-based JSON array freeze that changed equality and emitted Pydantic serialization warnings |
| Resolutions | Added strict runtime ID/hash/literal/tuple validation; clone-on-read tables and source-isolated context views; recursive list-compatible JSON snapshots; exact stream/reference key identity; ref/payload schema/kind/hash/bounds plus table row/grid closure; and explicit Task 11/13 ownership notes for the remaining external closures |
| Final internal result | Two independent final reviews PASS with P0=0 and P1=0. Focused Task 5 + AnchorResult v0.2: 77 passed; contracts/reference/request regression: 380 passed; Ruff and ty passed; serialization, RFC 8785, schema, and package probes passed with zero warnings |
| Deferred by plan | Task 11 owns descriptor/column/order/logical-hash recomputation and atomic artifact publication. Task 13 owns authoritative catalog order, declared-only service projection, and report scientific-status equality with the frozen plan |
| External review | No new successful Claude verdict was claimed for this task; prior authorized Fable5 retries were unavailable due service/session limits |
| Release conclusion | Task 5 contract/runtime slice may be committed and Task 6 TDD may begin. This does not implement a production AnchorPlugin, authorize a formal run, or establish scientific validity |

### AR-005 — M4 Task 6 Contract Schema Publication

| Field | Record |
|---|---|
| Artifacts | Authoritative schema exporter, ten new root M4 schemas, fourteen package schema resources including the four frozen legacy schemas, schema/package tests, and the checked Task 6 plan section |
| Approval | Covered by the approved replacement M4 plan and the user's temporary default-approval authorization; no model ownership or scientific boundary changed |
| TDD evidence | Initial Task 6 RED was 6 failed / 25 passed because the ten M4 schemas, package resources, and dual export path were absent. Adversarial REDs then proved single-target API breakage, publish-failure split state, partial temp leakage, and interruption without rollback |
| First internal findings | Independent reviewers found that a default second target caused hidden source-tree writes, sequential replacement could leave root/package versions split, the currently written temp could survive a stage error, and KeyboardInterrupt/SystemExit bypassed an Exception-only rollback guard |
| Resolutions | Retained `export_schemas(custom_directory)` as a one-target API; made the CLI request both official targets explicitly; staged all bytes first; snapshotted prior destination bytes; rolled back on every BaseException; cleaned every stage/rollback temporary; and rejected identical resolved targets |
| Final internal result | Two independent final reviews PASS with P0=0 and P1=0. Focused schema/package gate: 36 passed; contracts/schema regression: 376 passed; Ruff/format/ty passed; repeated CLI export was stable; fresh sdist/wheel build succeeded |
| Package evidence | The fresh wheel contains exactly fourteen schema resources; all wheel/root/package members have matching SHA-256 values. The four legacy root schemas retain their frozen hashes |
| Residual P2 | Fixed temporary names and concurrent exporter locking remain a development-tool hardening item; current serialized CLI use and failure rollback satisfy the Task 6 gate. Wheel-member assertions are acceptance evidence rather than a self-building unit test |
| Release conclusion | M4-A contract/schema slice is complete; catalog resources and canonical identity remain Tasks 7–8. Production plugin count remains 0/18 and every M4 report remains non-formal |

### AR-006 — M4 Task 7 Catalog and Resource Identity Amendment

| Field | Record |
|---|---|
| Artifact | `specs/2026-07-13-m4-task7-catalog-resource-identity-amendment.md` plus the corresponding Task 7/12/13/14/18/20/31 replacement-plan closures |
| Baseline | `9f1236d` with a docs-only amendment working tree; no Task 7 production code was claimed during design review |
| Approval | The user explicitly approved the revision candidate and separately authorized intermediate M4–M6 designs to proceed as default-approved while resting, provided review evidence was saved and major boundary changes remained visible |
| First internal findings | Independent read-only reviewers found non-unique parameter-schema serialization/fragments, incomplete scorer-annotation-to-DTO hashing, undefined O1/O5/O7 profile payloads, O6 selecting too broad a channel set, a not-applicable O6 empty-array conflict, duplicate mapping-to-channel calibration ambiguity, and missing implementation-plan owners |
| Second internal findings | Review then found the literal property matrices still lacked exact per-property constraints, Task 12/13 did not yet schedule scorer/instance/profile compilation or runtime `jsonschema`, and mutable nested `ScorerPolicy`/plan JSON allowed a validation-to-use identity change |
| Resolutions | Froze exact-18 catalog/dependency/artifact descriptors, six provider descriptors, 24 canonical parameter schemas with complete literal property matrices and raw-byte hashes, exact scorer shape/hash, O6 applicability-scoped materialization, seven-key O13 profiles, deep JSON snapshots, Task 12/13 validation owners, and versioned shared pure O1/O5/O7/movement/scorer kernel callables/tests |
| Final internal result | Two independent final read-only reviews reported P0=0, P1=0, PASS; one explicitly reported no blocking P2. UTF-8/fence/diff checks were clean |
| External review attempt | The authorized WSL Claude CLI check was attempted, but `claude --help` returned `claude: command not found` in the current WSL environment. No Fable5 or ultracode verdict was produced or claimed for this amendment |
| Release conclusion | The amendment is accepted under the user's authorization and may drive Task 7 TDD. This approves resource/identity engineering defaults only; it does not implement a plugin, change a formula/golden, or establish scientific validity |

### AR-007 — M4 Task 8 Canonical Fingerprint and Runtime Identity Amendment

| Field | Record |
|---|---|
| Artifact | `specs/2026-07-13-m4-task8-canonical-fingerprint-runtime-identity-amendment.md` plus replacement Task 8 identity callables/tests |
| Baseline | Same `9f1236d` docs-only candidate sequence as AR-006; Task 8 code remained pending |
| Approval | Covered by the user's 2026-07-13 default-approval authorization after saved independent review; no irreversible external action was taken |
| Review focus | RFC 8785 input domain and typed framing; exact logical-table/reference/result/report payloads; scorer/profile hash separation; self-field rejection owners; Windows `SOABI`/`EXT_SUFFIX`; wheel `RECORD`; and two-install-root equality |
| Findings closed | Added the safe integer range, complete row-array validation/order semantics, scorer-policy projection, algorithm-profile reuse of `parameter-snapshot`, exact-three-cell RECORD parsing, duplicate-key rejection, strict ABI tag grammar, code-point path ordering, self-field ownership, and one-build/two-venv root-independent proof |
| Final internal result | An initial dedicated Task 8 review and the two later combined Task 7/8 final reviews found P0=0 and P1=0. The amendment and replacement plan agree on callable surface and deferred mismatch owners |
| External review attempt | Same current WSL result as AR-006: Claude CLI unavailable, so no external final PASS or verified ultracode activation is claimed |
| Release conclusion | The amendment is accepted and may drive Task 8 TDD after Task 7. Approval freezes byte identity only; catalog/runtime/artifact code and all later-owner rejection tests remain pending until their scheduled RED→GREEN gates |

### AR-008 — M4 Task 7/8 Authority Migration Final Audit

| Field | Record |
|---|---|
| Artifacts | Product README/overview/reference-model/validation/self-review/status/decisions, M4 main and targeted amendments, replacement plan, and this review ledger |
| Audit focus | Accepted-state consistency; D-029/D-030 authority; Task 7/8 approval-versus-implementation boundary; exact O2 parameter/scorer projection; navigation and relative-link closure |
| Initial result | One reviewer reported P1=1 because `04_REFERENCE_MODEL_V0_1.md` retained an old O2 example with editable algorithm parameters and a flattened scorer; it also reported P2=1 because the product overview omitted Task 7/8 amendments and this ledger. A separate reviewer found no P0/P1/P2 in the remaining status and authority migration |
| Resolutions | Replaced the O2 example with an explicitly non-loadable resolved projection using `parameters={}`, fixed algorithm invariants, and the exact four-key scorer/five-key parameter shape; added Task 7/8 and review-ledger links to the product overview |
| Final internal result | Targeted re-review PASS with P0=0, P1=0, P2=0; all overview-relative links resolved. The independent status audit also PASSed with Task 7/8 still unimplemented, 18/18 specified, 0/18 production plugins, and M4 not engineering-verified |
| Release conclusion | The docs-only Task 7/8 authority migration is consistent and may be committed. Task 7 remains the next implementation task; no formula, threshold, golden number, production-plugin count, formal-run authorization, or scientific-validity claim changed |

### AR-009 — M4 Task 7 Exact Catalog and Resource Implementation

| Field | Record |
|---|---|
| Artifacts | `anchors/catalog.py`, the exact-18 packaged catalog, 24 canonical parameter-schema resources, honest zero registry, deep-frozen plan/descriptor contracts, package tests, and the checked replacement Task 7 section |
| Approval | Covered by the accepted Task 7 amendment and the user's temporary default-approval authorization; no formula, threshold, golden value, production-plugin claim, or formal-run boundary changed |
| TDD evidence | Initial RED collected 60 tests: 29 passed and 31 failed because the loader/resources were absent and four required nested JSON surfaces were mutable. After implementation and adversarial hardening, focused Task 7 is `77 passed`; post-hardening full regression is `921 passed, 2 skipped`, with only two repository-external captured-format samples skipped |
| First independent findings | Three read-only reviews found incomplete dependency/descriptor semantic locking, parameter/scorer mutations accepted after canonical reserialization, false mutation coverage caused by noncanonical test bytes, missing provider/profile oracles, a mutable artifact descriptor, and incomplete exact package assertions |
| Late blocking finding | Final code review found both preprocessing output descriptors remained mutable after validation. New RED tests proved caller-owned and post-construction mutations; both `PreprocessingProviderDefinition` and `ResolvedPreprocessingRecipe` now recursively copy and freeze their descriptor snapshots |
| Resolutions | Locked all 18 dependency/artifact records, all 24 raw resource identities, scorer annotations, six provider descriptors, three algorithm profiles, canonical semantic mutation paths, descriptor and plan-time JSON immutability, traversal/alias rejection, exact catalog/registry/parameter package inventory, and the public `Sha256Digest` return annotation |
| Final internal result | Three independent final reviews PASS with P0=0, P1=0, P2=0. Ruff, format, ty, `git diff --check`, fresh wheel inventory/source-byte equality, isolated installed-resource loading, independent hardcoded hashes, and generic-catalog non-pollution probes all passed |
| Commit | `583a1e7` (`feat: package M4 reference anchor catalog`) |
| External review | The authorized WSL Claude CLI remained unavailable in the current environment (`claude: command not found`); no Fable5/ultracode verdict is claimed |
| Release conclusion | Task 7 is complete and Task 8 is next. The catalog still carries the approved temporary zero fingerprint sentinel until Task 8 atomically replaces and validates it; production plugins remain 0/18, M4 remains not engineering-verified, and `formal_run_authorized=false` |

### AR-010 — M4 Task 8 Canonical Fingerprints and Runtime Identity (INLINE finalization)

| Field | Record |
|---|---|
| Artifacts | `anchors/fingerprint.py` (RFC 8785 JCS + typed SHA-256 surface; logical table/reference/result/report/plugin/registry/catalog/scorer fingerprints; Python + numeric runtime identity), the real computed catalog fingerprint replacing the Task 7 zero sentinel in `catalog.py` and `reference-model-v0.1-anchor-catalog.json`, four fingerprint test modules, and the checked replacement Task 8 section |
| Approval | Covered by the accepted Task 8 amendment; no formula, threshold, golden value, production-plugin claim, or formal-run boundary changed |
| Finalization mode | **Finalized INLINE by Claude** to conserve codex/subagent quota. The Task 8 code and tests were authored by the prior subagent run and left uncommitted when quota stopped; Claude verified and committed them without re-running the plan's subagent protocol |
| TDD evidence | Verified before commit: focused `tests/anchors/test_fingerprint*.py` + `test_catalog.py` = `149 passed, 1 skipped` (host-symlink test skipped); full suite `1025 passed, 3 skipped`; `ruff check` clean; `ruff format` clean on Task 8 files; `ty check src/` = All checks passed |
| Independent review | **NONE.** The plan's two independent review subagents (specification review + code-quality review) were NOT dispatched. No three-way / two-way final review is claimed |
| External review | **NONE claimed.** |
| Commit | `3e1a006` (`feat: add canonical M4 fingerprints`); docs `7328c05` (plan checkboxes + completion note) plus this ledger/status alignment |
| Release conclusion | Task 8 complete; Task 9 (trusted packaged registry + implementation-closure verifier) is next. Production plugins remain 0/18, M4 remains not engineering-verified, `formal_run_authorized=false`. Because independent review was skipped, codex or a future reviewer may re-audit `fingerprint.py` if a stronger gate is later desired |

### AR-011 — M4 Task 9 Trusted Packaged Registry and Closure Verifier (INLINE finalization)

| Field | Record |
|---|---|
| Artifacts | `anchors/registry.py` (trusted loader + `verify_implementation_closure`/`verify_preprocessing_closure` + `PluginRegistry` capability/resolve/from_factories_for_testing + `verify`/`refresh`/`refresh-preprocessor` CLI), `tests/anchors/fakes.py`, `tests/anchors/test_registry.py`, the extended `tests/test_package_metadata.py`, and the checked replacement Task 9 section |
| Approval | Covered by the accepted M4 main design §13.6 and the user's standing inline authorization; no formula, threshold, golden value, production-plugin claim, or formal-run boundary changed |
| Finalization mode | **Finalized INLINE by Claude** to conserve codex/subagent quota. Code and tests were authored together in one inline pass, verified green before commit; the plan's RED-first subagent ritual was not run as a separate phase |
| TDD evidence | Verified before commit: focused `tests/anchors/test_registry.py` + `tests/test_package_metadata.py` = `43 passed`; full suite `1062 passed, 3 skipped` (host-symlink + two repository-external captured-format samples skipped); `ruff check` clean; `ty check src/` = All checks passed. Tamper tests assert `RegistryError` on wrong parameter/measurement/definition/artifact hash, member under/over-declaration, digest, python-runtime, and plugin-version mismatch; closure tests reject dynamic imports and namespace crossing; runtime-lock tests reject python mismatch, numeric under/over-declaration, and install drift; CLI tests cover verify/refresh/refresh-preprocessor and error paths |
| Independent review | **NONE.** The plan's two independent review subagents (specification review + code-quality review) were NOT dispatched. No three-way / two-way final review is claimed |
| External review | **NONE claimed.** |
| Claude implementation decisions | Registry-local capability mapping (`plugin_unavailable` = plugin id known at another version, `not_implemented` = id absent, `incompatible` = entry present but closure fails); closure member namespace = `plugins.*`/`primitives.*` with an explicit framework allowlist and all other `pilot_assessment.*` imports treated as violations; runtime lock verifies live `python_runtime_identity()` equality plus closure-imported permitted numeric distributions (numpy/scipy/polars/pyarrow) against installed wheel identities. These are consistent with §13.6 but not spelled out there; a later reviewer may re-audit |
| Commit | `cac645f` (`feat: add trusted anchor plugin registry`); docs (plan checkboxes + completion note, status top-table, this ledger entry) committed separately |
| Release conclusion | Task 9 complete; Task 10 (segment-aware temporal support, grids, windows) is next. `registry-v1.json` stays empty so all 18 reference capabilities are `not_implemented`; production plugins remain 0/18, M4 remains not engineering-verified, and `formal_run_authorized=false` |

### AR-012 — M4 Task 10 Segment-Aware Temporal Primitives (INLINE finalization)

| Field | Record |
|---|---|
| Artifacts | `anchors/temporal.py` (`SupportInterval`, `TemporalSupport`, point-support reconstruction, M3 gap-metric validation, Decimal grid, left-hold integral, nearest matching, semantic windows) and `tests/anchors/test_temporal.py` |
| Approval | Covered by the accepted M4 design §10 and replacement Task 10 plus the user's explicit instruction to continue this project inline; no anchor formula, scorer threshold, production-plugin count, formal-run boundary, or scientific-validity claim changed |
| Finalization mode | **Implemented and self-reviewed INLINE** to conserve quota. No subagent was created and no independent/external verdict is claimed |
| TDD evidence | RED: expected `ModuleNotFoundError` for the absent temporal module. GREEN: `tests/anchors/test_temporal.py tests/synchronization/test_models.py` = `25 passed`; Ruff check and format check clean; `ty check src/pilot_assessment/anchors/temporal.py` = All checks passed. Per the new lightweight cadence, Task 10 did not repeat the full repository suite; Task 9's `1062 passed, 3 skipped` remains the latest full-suite evidence |
| Inline self-review decisions saved for later audit | `source_row_index` addresses the caller's original DataFrame order; left-hold integration returns value-nanoseconds; a gap is strictly `delta > gap_threshold_ns`; only the final support row extends to an explicit semantic end; nearest matching returns original right indexes, forbids extrapolation outside the right time range, and resolves ties by earlier timestamp then stable ID; semantic windows use the explicit `semantic-span-v1` or `fixed-full-with-end-tail-v1` policy, with short spans kept whole and at most one deduplicated end-aligned tail |
| Commit | `6db08c9` (`feat: add segment-aware M4 temporal support`); docs/status closure committed separately |
| Release conclusion | Task 10 complete; Task 11 transactional content-addressed artifact publication is next. The temporal layer introduces no coverage threshold or raw-data quality filter. Production plugins remain 0/18, M4 remains not engineering-verified, and `formal_run_authorized=false` |

### AR-013 — M4 Task 11 Transactional Artifact Publication (INLINE finalization)

| Field | Record |
|---|---|
| Artifacts | `anchors/artifacts.py`, the transaction ports added to `anchors/protocols.py`, and `tests/anchors/test_artifacts.py` |
| Approval | Covered by accepted M4 design §13.2/§13.4–§13.6 and replacement Task 11 plus the user's explicit inline continuation instruction; it changes no anchor formula, scorer threshold, CPT, production-plugin count, formal-run boundary, or scientific-validity claim |
| Finalization mode | **Implemented and self-reviewed INLINE** to conserve quota. No subagent was created and no independent/external verdict is claimed |
| TDD evidence | RED: expected `ModuleNotFoundError` for the absent artifacts module. GREEN: Task 11 focused = `18 passed`; focused run with the existing anchor measurement/artifact contract = `49 passed`; Ruff check, Ruff format check and `ty check` clean for all Task 11 files. No full-suite rerun was made; Task 9's `1062 passed, 3 skipped` remains the latest full-suite evidence |
| Inline self-review decisions saved for later audit | The plugin sees only a two-method staging emitter; artifact IDs bind exact declaration-order recipes rather than kind/schema lookup; table identity hashes canonical logical rows and excludes storage metadata; blob logical/storage digests both hash raw bytes; refs become resolvable only after the producing anchor commits; exact staged/returned ref equality is mandatory; an anchor abort is isolated while evaluation abort/publish failure invalidates all local resolution; preprocessing identity includes complete scope; the sink has no Session Bundle or durable-root path surface |
| Commit | `da8cb42` (`feat: add transactional M4 artifact sink`); docs/status closure committed separately |
| Release conclusion | Task 11 complete; Task 12 central scoring and breakdown aggregation is next. Durable artifact persistence remains M6 ownership. Production plugins remain 0/18, M4 remains not engineering-verified, and `formal_run_authorized=false` |

### AR-014 — M4 Task 12 Central Evidence Scoring (INLINE finalization)

| Field | Record |
|---|---|
| Artifacts | `anchors/scoring.py` and `tests/anchors/test_scoring.py` |
| Approval | Covered by accepted M4 design §10.2/§11, Task 7 §8.1/§8.4, Task 8 §3.1/§5 and replacement Task 12 plus the user's explicit inline continuation instruction; it changes no packaged threshold, anchor formula, CPT, production-plugin count, formal-run boundary, or scientific-validity claim |
| Finalization mode | **Implemented and self-reviewed INLINE** to conserve quota. No subagent was created and no independent/external verdict is claimed |
| TDD evidence | RED: expected `ModuleNotFoundError` for the absent scoring module. GREEN: Task 12 focused = `35 passed`; scorer plus existing fingerprint/result/measurement compatibility = `163 passed`; Ruff check, Ruff format check and `ty check` clean. The corrected runtime quality-field scan is clean. No full-suite rerun was made; Task 9's `1062 passed, 3 skipped` remains the latest full-suite evidence |
| Inline self-review decisions saved for later audit | `hard_threshold_v1` is selected only by scorer ID/version and never by anchor ID; the exact Task 7 four-key annotation compiles without flattening its five-key parameters; every use revalidates shape, vocabulary, canonical order and Task 8 fingerprint; D then A conjunction uses only declared metrics/units; overrides are allowlisted computed-U vetoes; plugin-produced session primary values retain anchor-specific worst or pooled numeric aggregation while the central scorer controls breakdown observations and the fixed non-computed priority; audit diagnostics and unused coverage/gap/sync metrics never enter classification; result fingerprints use the Task 8 logical-artifact projection |
| Scan correction | The replacement plan's original broad literal scan false-positive matched only `catalog.py::_PROHIBITED_KEYS`, the Task 7 denylist that rejects quality-gate fields. The scan now excludes that defensive file while covering the remaining M4 runtime/scoring code and AnchorResult v0.2; the denylist and its tests remain intact |
| Commit | `d6d8288` (`feat: add central M4 evidence scoring`); docs/status closure committed separately |
| Release conclusion | Task 12 complete; Task 13 typed DAG, preprocessing resolver, evaluator/public API and M4-B stage gate is next. Production plugins remain 0/18, M4 remains not engineering-verified, and `formal_run_authorized=false` |

### AR-015 — M4 Task 13 Typed DAG, Resolver, Evaluator and Public API (INLINE finalization)

| Field | Record |
|---|---|
| Artifacts | `anchors/dag.py`, `anchors/preprocessing.py`, `anchors/service.py`, `anchors/api.py`, the lazy package export, runtime `jsonschema` dependency, supporting protocol/artifact/registry/fingerprint changes, and `test_dag.py`/`test_preprocessing.py`/`test_service.py` plus compatibility tests |
| Approval | Covered by accepted M4 design §13/§15, replacement Task 13 and the user's explicit inline continuation instruction; it changes no anchor formula, threshold, CPT, production-plugin count, formal-run boundary or scientific-validity claim |
| Finalization mode | **Implemented and self-reviewed INLINE** to conserve quota. No subagent was created and no independent/external verdict is claimed |
| TDD evidence | RED was observed independently for the absent DAG, preprocessing and service modules. GREEN: Task 13 focused = `31 passed`; contracts/anchors gate = `425 passed, 1 skipped`; fresh full repository gate = `1158 passed, 3 skipped` (host-symlink plus two repository-external captured-format samples skipped). Schema export has zero drift; Ruff check/format, `ty check src`, build and `git diff --check` pass. A fresh isolated wheel imports runtime `jsonschema` and the lazy public `evaluate` API without a runpy warning |
| Inline self-review decisions saved for later audit | A production plan must exactly match the trusted packaged catalog inventory, not merely carry its fingerprint; optional dependency absence is not a required-dependency failure; preprocessing input fingerprints enter producer, artifact and downstream dependency identity; public package export is lazy to keep module execution clean; public API cannot inject registry/policy/fault hooks; request validation remains first and idempotent at both boundaries |
| Commit | `498f611` (`feat: execute M4 plans through plugin protocol`); docs/status closure committed separately |
| Release conclusion | Task 13 complete and the M4-B framework gate is engineering-verified. Both packaged registry maps remain empty, so the honest state is 18/18 specified, 0/18 production plugins, M4 overall not engineering-verified, and `formal_run_authorized=false`. Task 14 O1 Phase-state Precision is next |

### AR-016 — M4 Task 14 O1 Phase-state Precision (INLINE)

| Field | Record |
|---|---|
| Artifacts | `anchors/primitives/models.py`, `anchors/primitives/envelopes.py`, `anchors/plugins/o1_phase_state_precision.py`, O1 micro constructors/oracles, O1 focused tests, packaged registry entry and registry/plan compatibility tests |
| Approval | Covered by the approved replacement Task 14 and the user's explicit inline continuation instruction; no formula, CPT, formal-run boundary or scientific-validity claim changed |
| Finalization mode | **Implemented and self-reviewed INLINE** to conserve quota. No subagent was created and no independent/external verdict is claimed |
| TDD evidence | RED: 12 focused failures while the O1 capability and primitives were absent. GREEN: O1 + registry focused `51 passed`; wider anchors/contracts/package `400 passed, 1 skipped`; fresh full repository `1175 passed, 3 skipped`. Registry verify, zero-drift schema export, Ruff check/format, `ty check src`, `git diff --check`, fresh sdist/wheel build and repository-external isolated-wheel capability loading passed |
| Inline self-review decisions saved for later audit | O1 uses native X left-hold support, strict gap splitting and full applicable-phase wall-clock denominators without a coverage/quality gate; finite poor values remain computed U; missing phase support is `missing_input`, missing phase envelope is `not_computable`; all applicable phases are evaluated after an early U; the plugin stages the exact per-axis + joint trace but delegates calculation to the shared pure kernel; entry-level input-contract projections must exactly match the authoritative plan; the already frozen M4 temporal module is a trusted registry framework dependency rather than plugin-owned closure |
| Identity | Packaged registry fingerprint `dfa7b3a3fec7251b2d4c5535e38adfaaa147d09c38dcf60a24538646c3ff41cd`; O1 implementation digest `36be1bf1d8409ab74d805a3eadb26c58b75ca898c2a8e780df5ced02a2a8ef23` |
| Commits | `ee67364` (`fix: canonicalize catalog input projections`) and `b1d1fc9` (`feat: add phase-state precision anchor`) |
| Release conclusion | Task 14 is complete and O1 is the sole available packaged production capability. The honest state is 18/18 specified, 1/18 production plugins; M4-C and M4 overall remain incomplete, `formal_run_authorized=false`, and Task 15 O2 Peak Tracking Excursion is next |

### AR-017 — M4 Task 15 O2 Peak Tracking Excursion (INLINE)

| Field | Record |
|---|---|
| Artifacts | `anchors/primitives/reference_join.py`, `anchors/plugins/o2_peak_tracking_excursion.py`, O2 micro constructors/tests, packaged registry entry and catalog/registry/package honesty tests |
| Approval | Covered by the approved replacement Task 15 and the user's explicit INLINE continuation instruction; no accepted formula, threshold, CPT, formal-run boundary or scientific-validity claim changed |
| Finalization mode | **Implemented and self-reviewed INLINE** to conserve quota. No subagent was created and no independent/external verdict is claimed |
| TDD evidence | RED: 15 focused failures while O2 was absent; four registry failures before registration; one finite-extreme overflow failure during numerical self-review. GREEN: final O2/catalog/registry/package `110 passed`; fresh full repository `1193 passed, 3 skipped`. Registry verify, zero-drift schema export, Ruff check/format, `ty check src`, `git diff --check`, fresh sdist/wheel build and repository-external isolated-wheel O1/O2 capability loading passed |
| Inline self-review decisions saved for later audit | Evaluation grid is applicable native X timestamps; exact reference duplicates choose lowest stable row; interpolation is same-segment linear only, with no extrapolation, gap bridging, nearest-path or actual-X fallback; reference units convert to metre before an explicit plan-hashed affine frame transform and errors output in ft; transform binding is immutable plan input rather than O2 `{}` parameters; all joined points across applicable phases contribute to the session maximum; peak ties use earliest timestamp then stable X row; stable `math.hypot` keeps representable finite extreme performance computed U rather than overflowing into extractor error |
| Identity | Packaged registry fingerprint `752f680401c5482df3897db9dcaa06e4787aa4a54290045285c1bb086760982c`; O2 implementation digest `60638db920b8f3865365625e812104956b9160ca962a116121d8365460ae9966` |
| Commit | `b1a8743` (`feat: add peak tracking excursion anchor`); docs/status closure committed separately |
| Release conclusion | Task 15 is complete and O1/O2 are the only available packaged production capabilities. The honest state is 18/18 specified, 2/18 production plugins; M4-C and M4 overall remain incomplete, `formal_run_authorized=false`, and Task 16 O3 Terminal Capture Quality is next |

### AR-018 — M4 Task 16 O3 Terminal Capture Quality (INLINE)

| Field | Record |
|---|---|
| Artifacts | `anchors/primitives/envelopes.py`, `anchors/plugins/o3_terminal_capture_quality.py`, O3 micro constructors/tests, event-identity contract regression, packaged registry entry and catalog/registry/package honesty tests |
| Approval | Covered by the approved replacement Task 16 and the user's explicit INLINE continuation instruction; no accepted formula, threshold, CPT, formal-run boundary or scientific-validity claim changed |
| Finalization mode | **Implemented and self-reviewed INLINE** to conserve quota. No subagent was created and no independent/external verdict is claimed |
| TDD evidence | RED: 13 focused failures while O3/capture behavior were absent. GREEN: O3/catalog/registry/contracts/package `137 passed`; fresh full repository `1210 passed, 3 skipped`. Registry verify, zero-drift schema export, Ruff check/format, `ty check src`, `git diff --check`, fresh sdist/wheel build and repository-external isolated-wheel O1/O2/O3 capability loading passed |
| Inline self-review decisions saved for later audit | O3 binds ordered X position fields to three target components, requires exact frame identity and deterministic length conversion, normalizes a finite nonzero arrival axis, uses native X left-hold support without crossing gaps, confirms the full hold but records latency at its start, clips only by event `opportunity_end_t_ns`, emits finite observed wait on misses, computes every applicable event, applies miss veto and otherwise aggregates both raw metrics component-wise by maximum; distinct events in one phase are keyed by `event_id` before `phase_id` |
| Identity | Packaged registry fingerprint `b30fa47e0d8dacf3896dd35a808c1b271b21b41953e8525b76b10a76259575d3`; O3 implementation digest `532f02d8c0a41c36d0c4208f2e25c5be839d801a257d93cb984aa89f45f7838a`; final documentation-bearing isolated wheel SHA-256 `dea3c6ac78e3c2c136947d14b5a2e849faf2619dbfe638c05b949f882b9372b7` |
| Commit | `f7d5261` (`feat: add terminal capture quality anchor`); docs/status closure committed separately |
| Release conclusion | Task 16 is complete and O1/O2/O3 are the only available packaged production capabilities. The honest state is 18/18 specified, 3/18 production plugins; M4-C and M4 overall remain incomplete, `formal_run_authorized=false`, and Task 17 O4 Sustained Hover Time is next |

### AR-019 — M4 Task 17 O4 Sustained Hover Time (INLINE)

| Field | Record |
|---|---|
| Artifacts | `anchors/primitives/envelopes.py`, `anchors/plugins/o4_sustained_hover_time.py`, O4 micro tests, exact `stable-hover-mask-v0.1` artifact, packaged registry entry and catalog/registry/package honesty tests |
| Approval | Covered by the approved replacement Task 17 and the user's explicit INLINE continuation instruction; no accepted threshold, CPT, formal-run boundary or scientific-validity claim changed |
| Finalization mode | **Implemented and self-reviewed INLINE** to conserve quota. No subagent was created and no independent/external verdict is claimed |
| TDD evidence | RED: 14 focused failures while O4/kernel were absent, then five registry-honesty failures before O4 registration and the required O1/O3 shared-source digest refresh. GREEN: hardened O4 `19 passed`; O1/O3/O4/catalog/registry/package `141 passed`; lightweight M4 anchors/contracts/package `755 passed, 1 skipped` (host symlink only). In accordance with the user's lightweight-test instruction, the three-minute full repository suite was not repeated for this single anchor; Task 16's `1210 passed, 3 skipped` remains the latest full-suite evidence. Registry verify, double zero-drift schema export, Ruff check/format, `ty check src`, `git diff --check`, fresh build and repository-external isolated-wheel O1/O2/O3/O4 capability loading passed |
| Inline self-review decisions saved for later audit | Exact five-key `phase_bindings` make applicability explicit because the catalog intentionally projects only `semantic.envelopes`; bindings are session-bounded and non-overlapping, and O4 never guesses or joins phases. Stable is the conjunction of all configured desired limits over native X left-hold support. Optional `max_behavioral_excursion_ns` bridges only a bounded internal false run within one continuous support segment; it never bridges leading/trailing false, M3 gaps or phase boundaries. The effective mask is published for O9. All applicable phases execute, any non-computed phase prevents a partial session score, and otherwise the session primary is the maximum phase longest duration. Finite extreme poor behavior remains computed U; all-false behavior is exactly `0 s + computed U`; no raw quality gate is introduced |
| Identity | Packaged registry fingerprint `87f047b4497544de8c7c4b8d4609fd6d315d47f696c2f7c98a9cb75f8ac060d3`; O1 digest `1086389e8ff8cc4318f2e50e8b07893aac0c76756fff5f4e72efba739e5a8480`; O2 digest `60638db920b8f3865365625e812104956b9160ca962a116121d8365460ae9966`; O3 digest `fbd7b5e969adec626ceb419ca00b5dbdb9a06c974da35ac21cc3db52ad602ee0`; O4 digest `18ea08a73bdb972a67c279d2b2ebc985909bf3a3a64113e8ca7a1aea1ca0c95f`; final documentation-bearing isolated wheel is 331,578 bytes with SHA-256 `9eff9b6effa427e53967c33022dfcebe14c1ecb04b8eae917da18992f58a9c71` |
| Commit | `056d9d5` (`feat: add sustained hover anchor`); docs/status closure committed separately |
| Release conclusion | Task 17 is complete and O1/O2/O3/O4 are the only available packaged production capabilities. The honest state is 18/18 specified, 4/18 production plugins; M4-C and M4 overall remain incomplete, `formal_run_authorized=false`, and Task 18 O5 Workload Rate is next |

### AR-020 — M4 Task 18 O5 Workload Rate and Movement Provider (INLINE)

| Field | Record |
|---|---|
| Artifacts | `anchors/primitives/movement.py`, `anchors/plugins/o5_workload_rate.py`, the provider input-contract projection in `protocols.py`/`service.py`, O5/movement micro tests, packaged O5/provider registry entries and catalog/registry/package honesty tests |
| Approval | Covered by the approved replacement Task 18 and the user's explicit INLINE continuation instruction; the provider-contract closure changes no accepted movement formula, O5 threshold, public schema, CPT, formal-run boundary or scientific-validity claim |
| Finalization mode | **Implemented and self-reviewed INLINE** to conserve quota. No subagent was created and no independent/external verdict is claimed |
| TDD evidence | RED: two collection errors while movement/O5 modules were absent; three registry/package honesty failures before registration; one exact `U/samples` role failure before field-shape guessing was removed. GREEN: movement/O5 `18 passed`; exact Task 18 movement/O5/preprocessing/registry `59 passed`; controlled O1–O5 runtime/DAG/request/contracts/catalog/package regression `261 passed`. Task 16's `1210 passed, 3 skipped` remains the latest full-suite evidence by the user's lightweight-test policy. Registry verify, double zero-drift schema export, Ruff check/format, `ty check src`, `git diff --check`, fresh build and repository-external isolated-wheel O1–O5/provider loading passed |
| Inline self-review decisions saved for later audit | Provider context now receives immutable validated table contracts for required modalities and stream fingerprints bind those contracts. `movement-events-v1` explicitly selects `U/samples`; other U table roles are harmless. The session-scoped provider preserves each support segment with `support-start`/`support-end` rows in its existing event table, so O5 reconstructs exact phase/channel denominators without crossing gaps; only true movement rows are re-staged as the public O5 artifact. Zero-movement configured channels remain valid zero evidence, finite extremes and high workload remain computed, and no raw quality gate is introduced |
| Identity | Packaged registry fingerprint `c7d3344f748c9572854a6933f6c1a4dc7b5432fb91adc4be46bd76928f384b33`; O5 digest `13a1a0b1f2bd33341205792e059d60de41df48fbfccbe44044314d8e3b9cc0aa`; `movement-events-v1` digest `2ca02450424cda13c0efde6f36400fac6e2af7998c2bfd3f9e9b2eecd89a7bcc`; documentation-bearing isolated wheel is 346,272 bytes with SHA-256 `93129b95a13fbf46af154590f6285fcf6dabf8b40a8a1630da5d3aa7ca68c52e` |
| Commit | `1a119af` (`feat: add deterministic workload-rate anchor`); docs/status closure committed separately |
| Release conclusion | Task 18 is complete; O1/O2/O3/O4/O5 are the only available packaged production capabilities and `movement-events-v1` is the only available preprocessing provider. The honest state is 18/18 specified, 5/18 production plugins; M4-C and M4 overall remain incomplete, `formal_run_authorized=false`, and Task 19 O6 Control Magnitude RMS is next |

### AR-021 — M4 Task 19 O6 Control Magnitude RMS (INLINE)

| Field | Record |
|---|---|
| Artifacts | `anchors/plugins/o6_control_magnitude_rms.py`, native-time O6 kernel, exact `rms-contribution-trace-v0.1` artifact, focused normalization/integration tests, packaged O6 registry entry and catalog/registry/package honesty tests |
| Approval | Covered by the approved replacement Task 19 and the user's explicit INLINE continuation instruction; no accepted O6 formula, threshold, public schema, CPT, formal-run boundary or scientific-validity claim changed |
| Finalization mode | **Implemented and self-reviewed INLINE** to conserve quota. No subagent was created and no independent/external verdict is claimed |
| TDD evidence | RED: expected collection failure while O6 was absent; three registry failures before registration; two stale package/catalog O1–O5 count assertions during controlled regression. GREEN: focused O6 `11 passed`; exact O6/registry `50 passed`; O6 plus registry/catalog/package `52 passed`; controlled O1–O6 runtime/DAG/request/contracts/catalog/package `361 passed, 1 skipped` (host symlink only). Task 16's `1210 passed, 3 skipped` remains the latest full-suite evidence under the lightweight-test policy. Registry verify, double zero-drift schema export, schema tests, Ruff check/format, `ty check src`, `git diff --check`, fresh build and repository-external isolated-wheel O1–O6/provider loading passed |
| Inline self-review decisions saved for later audit | O6 selects the exact validated `U/samples` contract and immutable applicability mappings; lower/trim/upper are never estimated from pilot performance. Each finite value uses the un-clipped piecewise normalization. Native left-hold energy is integrated only over reconstructed support segments, partial support has no coverage gate, and phase energies are pooled by summed energy and observed duration rather than averaged percentages. Any non-computed applicable phase prevents a partial session score; endpoint-exceeding finite control remains computed negative evidence |
| Identity | Packaged registry fingerprint `136e2b3d94bed59c61fdc6b8fb68c53974e8ecd9cf061ea3f4b8a0d2ccdca9dd`; O6 digest `af352fa2ff55d58c53fe89e5b8ff23b188ca6c38e03df9522001898ec6fc8d09`; final documentation-bearing isolated wheel is 353,755 bytes with SHA-256 `5888c15671ac6ff13ee1015abd159cc6c835baeb94e5d4f284d63ec12d1921ba` |
| Commit | `2ca3540` (`feat: add control magnitude RMS anchor`); docs/status closure committed separately |
| Release conclusion | Task 19 is complete; O1/O2/O3/O4/O5/O6 are the only available packaged production capabilities and `movement-events-v1` is the only available preprocessing provider. The honest state is 18/18 specified, 6/18 production plugins; M4-C and M4 overall remain incomplete, `formal_run_authorized=false`, and Task 20 O7 Control Reversal Rate is next |

### AR-022 — M4 Task 20 O7 Control Reversal Rate and M4-C Stage Gate (INLINE)

| Field | Record |
|---|---|
| Artifacts | `anchors/primitives/reversal.py`, O7 DTOs in `anchors/primitives/models.py`, `anchors/plugins/o7_control_reversal_rate.py`, exact `reversal-events-v0.1` artifact, focused boundary/status tests, packaged O7 registry entry and catalog/registry/package honesty tests |
| Approval | Covered by the approved replacement Task 20 and the user's explicit INLINE continuation instruction; no accepted O7 formula, threshold, public schema, CPT, formal-run boundary or scientific-validity claim changed |
| Finalization mode | **Implemented and self-reviewed INLINE** to conserve quota. No subagent was created and no independent/external verdict is claimed |
| TDD evidence | RED: expected collection error while O7 was absent; one subsequent `1.5 Hz` versus `1.0 Hz` failure exposed cross-phase boundary pairing; four registry failures then proved O7 absence and shared-model digest invalidation; two package/catalog failures proved the stale 6-anchor honesty boundary. GREEN: focused O7 `14 passed`; exact M4-C O1–O7/movement/preprocessing/registry `153 passed`; fresh full repository `1275 passed, 3 skipped` in 285.79 s. Registry verify, double zero-drift schema export, schema tests (`31 passed`), Ruff check/format, `ty check src`, `git diff --check`, fresh build and repository-external isolated-wheel O1–O7/provider loading passed |
| Inline self-review decisions saved for later audit | O7 consumes the exact registered O5 movement profile and delegates reversal logic to one pure callable shared with future O13. Only adjacent turning points assigned to the same support segment may pair; a timestamp shared by contiguous phase intervals belongs deterministically to the later segment. Channel rates pool qualifying counts over the same O5 observed-support denominator and session takes the configured-channel maximum. Zero reversals remain computed zero, finite extreme frequency remains computed negative evidence, and any non-computed applicable phase prevents a partial session score. Two isolated-wheel launcher-only failures (Windows quote loss, then enum/string test assumption) were corrected without production changes before the final pass |
| Identity | Packaged registry fingerprint `008de732d473f48e884adbc7bf91e4a068f23daafcd5cddf262a3888e8451c2c`; O7 digest `9980be18a95de3d4a367b5297689b6dcce998d722af9968fad78e49e3b6420bd`; final documentation-bearing isolated wheel is 360,781 bytes with SHA-256 `cfd07e0902af129ffa1babb29b5cdfbe9748a8ba5ff3459edf636e3974936229` |
| Commit | `eb9cca6` (`feat: add control reversal anchor and close M4-C`); docs/status closure committed separately |
| Release conclusion | Task 20 and the M4-C stage gate are complete. O1–O7 are the only available packaged production capabilities and `movement-events-v1` is the only available preprocessing provider. The honest state is 18/18 specified, 7/18 production plugins; M4 overall remains incomplete, `formal_run_authorized=false`, and Task 21 O8 TPX Composite is next |

### AR-023 — M4 Task 21 O8 TPX Composite (INLINE)

| Field | Record |
|---|---|
| Artifacts | `anchors/plugins/o8_tpx_composite.py`, exact typed O1/O5 result dependencies, `tpx-component-trace-v0.1` publication, focused formula/state/dependency tests, packaged O8 registry entry and registry/catalog honesty updates |
| Approval | Covered by the approved replacement Task 21 and the user's explicit INLINE continuation instruction; no accepted O8 formula, 0.4/0.6 threshold, public schema, CPT, formal-run boundary or scientific-validity claim changed |
| Finalization mode | **Implemented and self-reviewed INLINE** to conserve quota. No subagent was created and no independent/external verdict is claimed |
| TDD evidence | RED: expected collection error while O8 was absent; three registry failures before registration; two sequential catalog-honesty failures exposed stale raw-JSON and validated-DTO O1–O7 boundaries. GREEN: focused O8 `8 passed`; controlled O8/registry/catalog/DAG/service/scoring gate `161 passed`. Registry verify, full-project Ruff check/format, `ty check src` and `git diff --check` passed. The full repository/build/isolated-wheel gates were intentionally not repeated for this one derived anchor; Task 20 remains the latest stage-gate evidence |
| Inline self-review decisions saved for later audit | Computed O1/O5 results remain usable even when their evidence state is Unacceptable; absent or non-computed dependencies produce `dependency_missing`. O5 already publishes `workload_ratio=W/W_min`, so O8 uses the exact equivalent `(P/100)^2/sqrt(max(workload_ratio,1))` and does not duplicate `w_min_hz`. The formula-defined clamp is retained without introducing an outlier or performance-quality filter. The component trace binds upstream anchor IDs, result fingerprints, states and canonical scores |
| Identity | Packaged registry fingerprint `0697427a836ea88fd98404e9ffe1aebf6215fcc1e5e9d9e086f0c72fc2906d89`; O8 digest `5575610b31ca3dd0654a7b2cb54265c0420634d722a1d27a7fb117c278936b0d`; no new wheel identity was claimed for this single-anchor checkpoint |
| Commit | `15da2ea` (`feat: add TPX composite anchor`); docs/status closure committed separately |
| Release conclusion | Task 21 is complete and M4-D has started. O1–O8 are the only available packaged production capabilities and `movement-events-v1` is the only available preprocessing provider. The honest state is 18/18 specified, 8/18 production plugins; M4-D and M4 overall remain incomplete, `formal_run_authorized=false`, and Task 22 O9 Dead-band Activity is next |

### AR-024 — M4 Task 22 O9 Dead-band Activity (INLINE)

| Field | Record |
|---|---|
| Artifacts | `anchors/plugins/o9_dead_band_activity.py`, exact O1/O4 mask and `movement-events-v1` dependencies, `micro-movement-events-v0.1` publication, focused precedence/matching/boundary tests, packaged O9 registry entry and registry/catalog honesty updates |
| Approval | Covered by the approved replacement Task 22 and the user's explicit INLINE continuation instruction; no accepted O9 formula, 1/2 Hz threshold, public schema, CPT, formal-run boundary or scientific-validity claim changed |
| Finalization mode | **Implemented and self-reviewed INLINE** to conserve quota. No subagent was created and no independent/external verdict is claimed |
| TDD evidence | RED: expected collection error while O9 was absent; four registry/catalog failures before registration; one explicit X-mask-gap binding test failed until omission was rejected; ownership review then produced a RED proving O9 incorrectly duplicated the provider-owned `0.5%` lower bound. GREEN: focused O9 `10 passed`; controlled O9/registry/catalog/DAG/service/scoring/artifact/temporal/O1/O4/movement gate `237 passed`. A submission-time package honesty run exposed a stale O1–O7 package-metadata assertion; `e86a53d` updated it to O1–O9 and the package-metadata/registry/catalog gate passed `97 passed`. Registry verify, full-project Ruff check/format (`149 files`), `ty check src` and `git diff --check` passed. The full repository/build/isolated-wheel gates were intentionally not repeated for this one anchor; Task 20 remains the latest stage-gate evidence |
| Inline self-review decisions saved for later audit | O1 is reduced to joint desired per native X sample before exact O4 join. Missing mask inventory is a contract error, while a non-empty all-false mask is observed `no_stable_hover`. X-mask gaps are explicitly bound and never inferred from U. Raw U nearest matching precedes provider-support intersection; matched spans and movement membership are half-open. The movement provider owns the inclusive lower amplitude threshold; O9 trusts its product and applies only its own inclusive maximum, so the default reference combination remains `[0.5%,5%]` without duplicating an expert-editable parameter. Partial matches without a coverage threshold, per-channel denominator, maximum-channel aggregation, and no undeclared detector invocation are locked. The registry closure deliberately treats `temporal.py` as trusted framework and binds O9 plus shared movement code and NumPy/Polars/SciPy runtimes |
| Identity | Packaged registry fingerprint `125f46e10c68b01fae169e6aab9b14efbac12e593b94af1fd6b53d9af27440f4`; O9 digest `9ec9f39fba59f593838f5356e6742e7cd56e0b8760366913972aa27783f43104`; no new wheel identity was claimed for this single-anchor checkpoint |
| Commit | `db2b5da` (`feat: add dead-band activity anchor`), `a76abde` (`fix: honor movement provider amplitude ownership`) and `e86a53d` (`test: sync packaged O9 registry coverage`); docs/status closure committed separately |
| Release conclusion | Task 22 is complete. O1–O9 are the only available packaged production capabilities and `movement-events-v1` is the only available preprocessing provider. The honest state is 18/18 specified, 9/18 production plugins; M4-D and M4 overall remain incomplete, `formal_run_authorized=false`, and Task 23 O10 Recovery Time is next |

### AR-025 — M4 Task 23 O10 Recovery Time (INLINE)

| Field | Record |
|---|---|
| Artifacts | `anchors/primitives/events.py`, `anchors/plugins/o10_recovery_time.py`, causal boolean interval/run models, exact `recovery-events-v0.1` artifact, focused onset/horizon/hold/miss/multi-event/status tests, packaged O10 registry entry and registry/catalog/package honesty updates |
| Approval | Covered by the approved replacement Task 23 and the user's explicit INLINE continuation instruction; no accepted O10 formula, 5/10-second threshold, public schema, CPT, formal-run boundary or scientific-validity claim changed |
| Finalization mode | **Implemented and self-reviewed INLINE** to conserve quota. No subagent was created and no independent/external verdict is claimed |
| TDD evidence | RED: expected collection errors while the shared `events` primitive and O10 plugin were absent; registry/catalog/package assertions then exposed the expected O1–O9 inventory boundary. GREEN: focused event/O10 gate `17 passed`; controlled O10/events/O1–O10 registry/catalog/service/scoring/artifact/temporal gate `258 passed`. Registry verify, full-project Ruff check/format (`153 files`), `ty check src` and `git diff --check` passed. The full repository/build/isolated-wheel gates were intentionally not repeated for this one anchor; Task 20 remains the latest stage-gate evidence |
| Inline self-review decisions saved for later audit | Declared marker events have priority; adequate-envelope exits are inferred only when marker IDs are absent. Later confirmation never shifts the causal first-outside onset. Boolean support uses native left-hold intervals and never bridges explicit gaps. Event windows are clipped by horizon, phase, opportunity and session boundaries. The 2-second desired hold must be observed fully but latency is measured at hold onset. A short observable horizon remains finite `computed + U + recovery_missed`; all applicable event traces survive an early miss and any miss vetoes the session. No marker/exit is `not_applicable`, true X absence is `missing_input`, and no performance-quality or coverage gate is introduced |
| Identity | Packaged registry fingerprint `1d8bcd84f4ea490abc1b83eba1f316249a3952ede4539960b965b34dfc13ec34`; O10 digest `20dd10667c160e61c2246bf69d290013fbab267cfecd948b2f423cd337b162bf`; no new wheel identity was claimed for this single-anchor checkpoint |
| Commit | `87aed10` (`feat: add recovery-time anchor`); docs/status closure committed separately |
| Release conclusion | Task 23 is complete. O1–O10 are the only available packaged production capabilities and `movement-events-v1` is the only available preprocessing provider. The honest state is 18/18 specified, 10/18 production plugins; M4-D and M4 overall remain incomplete, `formal_run_authorized=false`, and Task 24 O11 Disturbance Latency is next |

### AR-026 — M4 Task 24 O11 Disturbance Latency (INLINE)

| Field | Record |
|---|---|
| Artifacts | `anchors/plugins/o11_disturbance_latency.py`, shared gap-aware trailing causal median in `anchors/primitives/events.py`, exact `response-events-v0.1` artifact, focused baseline/filter/sign/threshold/boundary/miss/multi-event/status tests, packaged O11 registry entry and registry/catalog/package honesty updates |
| Approval | Covered by the approved replacement Task 24 and the user's explicit INLINE continuation instruction; no accepted O11 formula, 500/1000-millisecond threshold, public schema, CPT, formal-run boundary or scientific-validity claim changed |
| Finalization mode | **Implemented and self-reviewed INLINE** to conserve quota. No subagent was created and no independent/external verdict is claimed |
| TDD evidence | RED: expected collection error while O11 was absent; four registry/catalog/package failures after registration proved the stale O1–O10 inventory boundary. GREEN: focused O11 `18 passed`; controlled events/O10/O11/registry/catalog/DAG/service/scoring/artifact/temporal/package gate `229 passed`. Registry verify, full-project Ruff check/format (`155 files`), `ty check src` and `git diff --check` passed. The full repository/build/isolated-wheel gates were intentionally not repeated for this one anchor; Task 20 remains the latest stage-gate evidence |
| Inline self-review decisions saved for later audit | Exact event IDs and phase/U temporal bindings are compiled inputs; event-owned control mapping IDs select channels and signs. Raw control is normalized through lower/trim/upper before a timestamp-based inclusive 20 ms trailing median that cannot cross support segments. The baseline uses nonempty same-phase filtered samples from at most the preceding second and falls back to mapping trim only when none exist. Correct and wrong runs use strict `>5%` and inclusive `>=100 ms`; later confirmation retains causal onset. The earliest correct mapped channel wins unless a qualifying wrong run occurred strictly earlier. Subthreshold noise does not veto. A short/no-response horizon remains finite computed-U evidence, all event traces are retained, and no coverage or performance-quality filter is introduced |
| Identity | Packaged registry fingerprint `51af85c150678406cc8d1f83d2e357717b75fc69300363e7015dc478779a7477`; O11 digest `8618bb2d9e41e1d346f80abd4ce8d0de2fff57260029005fb7acd776c8a394c6`; refreshed O10 digest `b86a83189cb8ae5e7da965cbab0293ad928a0cefb9155f4c95594e3226854d6f`; no new wheel identity was claimed for this single-anchor checkpoint |
| Commit | `8672c74` (`feat: add disturbance-latency anchor`); docs/status closure committed separately |
| Release conclusion | Task 24 is complete. O1–O11 are the only available packaged production capabilities and `movement-events-v1` is the only available preprocessing provider. The honest state is 18/18 specified, 11/18 production plugins; M4-D and M4 overall remain incomplete, `formal_run_authorized=false`, and Task 25 O12 Envelope-drift Latency is next |

### AR-027 — M4 Task 25 O12 Envelope-drift Latency (INLINE)

| Field | Record |
|---|---|
| Artifacts | `anchors/plugins/o12_envelope_drift_latency.py`, reused causal-run/trailing-median behavior from `anchors/primitives/events.py`, exact `correction-events-v0.1` artifact, focused exit/sign/baseline/threshold/boundary/miss/multi-event/status tests, packaged O12 registry entry and registry/catalog/package honesty updates |
| Approval | Covered by the approved replacement Task 25 and the user's explicit INLINE continuation instruction; no accepted O12 formula, 300/800-millisecond threshold, public schema, CPT, formal-run boundary or scientific-validity claim changed |
| Finalization mode | **Implemented and self-reviewed INLINE** to conserve quota. No subagent was created and no independent/external verdict is claimed |
| TDD evidence | RED: expected collection error while O12 was absent; four registry/catalog/package failures after registration proved the stale O1–O11 inventory boundary. GREEN: focused O12 `21 passed`; controlled O8–O12/events/registry/catalog/DAG/service/scoring/artifact/temporal/package gate `269 passed`. Registry verify, full-project Ruff check/format (`157 files`), `ty check src` and `git diff --check` passed. The full repository/build/isolated-wheel gates were intentionally not repeated for this one anchor; Task 20 remains the latest full stage-gate evidence |
| Inline self-review decisions saved for later audit | X confirms a desired-envelope exit at inclusive 100 ms but keeps the first outside sample as `t_exit`. Signed state error is bound at that onset; mapping `correct_sign` defines the correction direction for positive error and is multiplied by the observed error sign. X/U use separate exact native-table contracts and M3-derived gap thresholds. U normalization, causal median, short nonempty baseline and trim fallback match O11. Strict `>5%`, inclusive `>=100 ms`, earliest mapped correct response, qualifying wrong-first veto, subthreshold-noise behavior, finite two-second miss, complete multi-exit trace, and no quality/coverage filter are locked |
| Identity | Packaged registry fingerprint `02ed9e1882e04d71b384b55366ee09080ec785d04883039e2ded7b7d2d7c68c6`; O12 digest `f4136c632dd2f303d9636a0ad67f0c597217cd96bf44d621a51f96f134aaf5b7`; unchanged O10/O11 digests `b86a83189cb8ae5e7da965cbab0293ad928a0cefb9155f4c95594e3226854d6f` and `8618bb2d9e41e1d346f80abd4ce8d0de2fff57260029005fb7acd776c8a394c6`; no new wheel identity was claimed for this single-anchor checkpoint |
| Commit | `e41d0e6` (`feat: add envelope-drift latency and close M4-D`); docs/status closure committed separately |
| Release conclusion | Task 25 and M4-D are complete. O1–O12 are the only available packaged production capabilities and `movement-events-v1` is the only available preprocessing provider. The honest state is 18/18 specified, 12/18 production plugins; M4 overall remains incomplete, `formal_run_authorized=false`, and Task 26 H1 AOI Dwell is next |

### AR-028 — M4 Task 26 H1 AOI Dwell (INLINE)

| Field | Record |
|---|---|
| Artifacts | `anchors/primitives/gaze_aoi.py`, `anchors/plugins/h1_aoi_dwell.py`, `gaze-aoi-intervals-v1`, exact `phase-dwell-v0.1` publication, focused gaze/AOI/dwell tests, packaged H1/provider registry entries and registry/catalog/package honesty updates |
| Approval | Covered by the approved replacement Task 26 and the user's explicit INLINE continuation instruction; no accepted H1 formula, 85/70-percent threshold, public schema, CPT, formal-run boundary or scientific-validity claim changed |
| Finalization mode | **Implemented and self-reviewed INLINE** to conserve quota. No subagent was created and no independent/external verdict is claimed |
| TDD evidence | RED: the expected two collection failures while gaze-AOI/H1 modules were absent; after registration, stale registry/catalog/package inventory expectations were updated explicitly. GREEN: focused gaze/H1 `14 passed`; controlled H1/preprocessing/registry/catalog/DAG/service/scoring/artifact/temporal/package gate `212 passed`. Registry verify, Ruff check/format, `ty check src` and `git diff --check` passed. The full repository/build/isolated-wheel gates were intentionally not repeated for this one anchor; Task 20 remains the latest full stage-gate evidence (`1275 passed, 3 skipped`) |
| Inline self-review decisions saved for later audit | The provider ignores precomputed AOI assignment and associates raw gaze with the actual first-person frame presentation at gaze time. It supports static/dynamic 2D, static/dynamic 3D and one taxonomy catch-all; deterministic overlap resolution is nearest positive 3D depth, then higher priority, then stable AOI ID. Low confidence is retained; blink, binocular-invalid, scene-invalid, mismatched and unprojectable observations stay in the denominator as `other_scene`. Gaps and phase clipping use native-time support; H1 pools durations rather than phase percentages. All off-task is computed zero evidence, and present input with no nonzero dwell is computed-U rather than filtered. Dynamic AOI geometry and frame starts are pre-indexed once so real-rate gaze does not trigger repeated full-table scans |
| Identity | Packaged registry fingerprint `51b3bc525b5647513852680d1b0fd5c5f49bc63cf31cb48e531880279024b434`; H1 digest `4de79001cff14d43dd6f64350a4734762a9abd92b79c93d7b74f30f7bfa20350`; `gaze-aoi-intervals-v1` digest `079f9216918449c179e81f13442328b8aaf7766c6f9d33b995c589a8a1d2b8b0`; no new wheel identity was claimed for this single-anchor checkpoint |
| Commit | `2d223a7` (`feat: add AOI dwell anchor`); docs/status closure committed separately |
| Release conclusion | Task 26 is complete and M4-E has started. O1–O12/H1 are the only available packaged production capabilities; `movement-events-v1` and `gaze-aoi-intervals-v1` are the only available preprocessing providers. The honest state is 18/18 specified, 13/18 production plugins; M4-E and M4 overall remain incomplete, `formal_run_authorized=false`, and Task 27 H2 First Fixation Latency is next |

### AR-029 — M4 Task 27 H2 First Fixation Latency (INLINE)

| Field | Record |
|---|---|
| Artifacts | `anchors/primitives/fixation.py`, `anchors/plugins/h2_first_fixation_latency.py`, `fixation-intervals-v1`, exact `event-fixation-trace-v0.1` publication, focused raw-gaze/fixation/event tests, packaged H2/provider registry entries and registry/catalog/package honesty updates |
| Approval | Covered by the approved replacement Task 27 and the user's explicit INLINE continuation instruction; no accepted H2 formula, 500/1000-millisecond threshold, public schema, CPT, formal-run boundary or scientific-validity claim changed |
| Finalization mode | **Implemented and self-reviewed INLINE** to conserve quota. No subagent was created and no independent/external verdict is claimed |
| TDD evidence | RED: expected two collection failures while fixation/H2 modules were absent; after registration, four inventory-honesty failures proved the stale 13-plugin/two-provider boundary before explicit updates. GREEN: focused fixation/H2 `18 passed`; controlled H1/H2/preprocessing/registry/catalog/DAG/service/scoring/artifact/temporal/package gate `231 passed`; final H2/registry/catalog/package checkpoint `120 passed`. Registry verify, Ruff check/format, `ty check src` and `git diff --check` passed. The full repository/build/isolated-wheel gates were intentionally not repeated; Task 20 remains the latest full stage-gate evidence (`1275 passed, 3 skipped`) |
| Inline self-review decisions saved for later audit | Reference fixation is recomputed only from authoritative raw aligned G; the compatibility/device fixation table is never read. Angular velocity uses the shortest sphere angle, duplicate timestamps keep the stable first row, exact 100 deg/s and 100 ms bounds are inclusive, gaps above 50 ms plus blink/tracking loss cut segments, and finite low confidence is not a quality filter. Fixation AOI/role comes from the raw gaze assignment bound to semantic AOI IDs. H2 uses I scene temporal support only as opportunity availability, starts at cue availability rather than a pilot movement, clips by horizon/session/event opportunity, accepts the earliest overlapping relevant fixation, takes worst successful latency, and lets any miss veto without skipping other event traces. Empty raw gaze with present I/G and cue is observed negative evidence, not missing input |
| Identity | Packaged registry fingerprint `90df48976a6b4b508f24ab58827a2266a35a7df2be4a18ce735ae6ac02366389`; H2 digest `49a179b7ad08e46bce611f7f418c837b1fc8722608546bd67dc3f4b18547ae1f`; `fixation-intervals-v1` digest `e3751b783b37ff0e1c6cc68dfdd752b6c38ca92a434c3b38373a0cae5a8fe72a`; no new wheel identity was claimed for this single-anchor checkpoint |
| Commit | `ed9cf24` (`feat: add first-fixation latency anchor`); docs/status closure committed separately |
| Release conclusion | Task 27 is complete. O1–O12/H1/H2 are the only available packaged production capabilities and all three reference preprocessing providers through fixation are available. The honest state is 18/18 specified, 14/18 production plugins; M4-E and M4 overall remain incomplete, `formal_run_authorized=false`, and Task 28 H3 Off-task Dwell is next |
