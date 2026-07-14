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
