# M5 Shared Versioned Model Library and Bayesian Workspace Implementation Plan

> 状态：Approved / active implementation；Task 1–5 已完成，Task 6 为下一执行入口
> 执行方式：INLINE，严格按任务顺序推进；不启用 subagent
> 工程方式：平台不变量采用轻量 test-first；starter resources、迁移和组装采用 focused smoke
> 权威规格：[M5 Shared Versioned Model Library and Bayesian Workspace Design](../specs/2026-07-16-m5-shared-versioned-model-library-and-bayesian-workspace-design.md)
> 决策基线：[D-031–D-040](../DECISIONS.md)

## 1. 目标

M5 把 M4R 已实现的单个 `EvidenceRecipe` 编辑/执行能力提升为完整的专家模型工作区后端。完成后，系统能够：

1. 保存全局 `EvidenceConcept`、`BnNodeConcept` 及任意数量并行 immutable versions；
2. 让不同 `AssessmentSchemeVersion` 精确选择组件版本，不使用 `latest`；
3. 从任意历史方案创建 draft，修改 Evidence、BN、state、edge 或 CPT，并以 copy-on-write 原子发布新方案；
4. 严格区分 extraction dependency、probabilistic BN dependency 与只读 posterior influence overlay；
5. 从 session 提取 Evidence observation，再用有限离散 BN exact inference 计算能力 posterior；
6. 保留旧 M4R 资源与 lineage，同时阻止 Evidence-to-Evidence extraction 静默进入当前高层模型；
7. 为 M6 persistence/JSON-RPC 和 M7 WinUI 提供 transport-neutral contracts 与 services。

本计划验证平台能忠实保存、组合、运行和重放专家模型。它不证明 Hover starter、18 个 Evidence、11 个 sub-skills、4 个 competencies、阈值或 CPT 具有科学有效性。

## 2. 实现边界

### 2.1 本里程碑交付

- 全局 component concept/version 合同、typed content identity、lineage 和 exact query；
- `TaskProfileVersion`、`CoverageReportingPolicyVersion`、`LayoutVersion`、`AssessmentSchemeVersion` 与 scheme draft；
- `ExtractionEdge`、`BayesianDependencyEdge`、`InferenceInfluenceEdge` 三个互不兼容的 DTO；
- component/scheme reference closure、source provenance、DAG、state、CPT 与 observation 的最小技术校验；
- in-memory repositories、draft autosave、optimistic revision、undo/redo、preview 和 atomic publish；
- 通用 BN state/CPT 编辑、独立性保持的 add-parent 迁移、显式权重的 remove-parent 迁移；
- NumPy 实现的有限离散 exact variable elimination；
- hard、virtual likelihood 与 omitted observation；
- M4R migration preflight、legacy O8 保存和新的 raw/task-derived TPX parallel version；
- Hover starter component package 与一个轻量方案派生/重放工作流。

### 2.2 本里程碑不交付

- SQLite、project database、managed artifact root、跨进程 transaction 或 JSON-RPC；属于 M6；
- WinUI 3 画布、Library Browser、Inspector、CPT 表格和 inference overlay 页面；属于 M7；
- installer、自动更新、备份/恢复、完整用户手册或 operator SDK；属于 M8；
- 任意 Python/eval 编辑器；
- 自动学习 BN topology/CPT；
- 重型长 session、多模态性能 fixture 或每次专家编辑后的 pytest；
- starter 算法、映射、拓扑、阈值或 CPT 的科学审批。

### 2.3 测试强度

以下平台不变量采用轻量 test-first，并实际观察 focused RED：

- typed JCS identity、immutable version 与 exact pin；
- concept parallel versions、copy-on-write 与 atomic publish；
- draft optimistic revision、undo/redo 与 incomplete autosave；
- extraction/probabilistic/inference 三种 edge 不可互换；
- source provenance closure 与 D-040 migration compatibility；
- BN DAG、state/CPT shape、概率范围/归一化；
- 小型手算 BN 的 exact posterior；
- hard/virtual/omitted observation 语义。

以下内容先做最小实现，再运行 focused smoke：

- Hover starter JSON resources 与 layout；
- M4R 17 个 compatible recipes 的导入和新 TPX resource；
- starter CPT materialization；
- 轻量方案派生、preview、publish 和 replay 组装。

不为每个 starter Evidence 建 scientific golden，不生成约一万行/模态的数据，不把 exact-18 数值等价作为 M5 完成门。发现平台 bug 时，先增加能复现该 bug 的 failing test，再修复。

## 3. 固定模块布局

| 路径 | 职责 |
|---|---|
| `src/pilot_assessment/contracts/model_components.py` | concepts、immutable component versions、lineage、ID-only internal refs 与 exact scheme pins |
| `src/pilot_assessment/contracts/bayesian.py` | states、CPT、typed edges、observations、posterior 与 trace DTO |
| `src/pilot_assessment/contracts/assessment_scheme.py` | task/profile/policy/layout/scheme versions、draft 与 publish DTO |
| `src/pilot_assessment/model_library/identity.py` | generic RFC 8785 typed content identity |
| `src/pilot_assessment/model_library/sources.py` | raw/session/task/derived/evidence-observation source descriptors 与 provenance closure |
| `src/pilot_assessment/model_library/repository.py` | component library protocol 与 in-memory implementation |
| `src/pilot_assessment/model_library/service.py` | concept/version create、exact get/list、archive metadata 与 lineage query |
| `src/pilot_assessment/model_library/migration.py` | M4R compatibility preflight、legacy preservation 与 active-version preparation |
| `src/pilot_assessment/schemes/repository.py` | scheme/draft repository、operation history 与 in-memory unit of work |
| `src/pilot_assessment/schemes/operations.py` | 前端意图对应的 typed domain operations |
| `src/pilot_assessment/schemes/validation.py` | reference closure、typed graph 与 executable scheme validation |
| `src/pilot_assessment/schemes/service.py` | draft/autosave/undo/redo/preview/publish/replay use cases |
| `src/pilot_assessment/bayesian/factors.py` | deterministic finite-discrete factor algebra |
| `src/pilot_assessment/bayesian/validation.py` | BN DAG、state、CPT 和 observation validation |
| `src/pilot_assessment/bayesian/inference.py` | compile/observe/infer/explain 与 exact variable elimination |
| `src/pilot_assessment/model_library/profile_data/hover/` | Hover starter manifest、source descriptors、components、CPT、layout 与 scheme resources |
| `schemas/` 与 `src/pilot_assessment/schema_resources/` | byte-identical public JSON Schema |

M5 不把 `src/pilot_assessment/evidence/catalog.py::EvidenceRecipeCatalog` 扩大成全局模型库。该 catalog 继续服务 M4R starter/legacy resource loading；M5 通过 migration adapter 读取它。

## 4. 核心合同冻结

### 4.1 ID、hash 与内部引用

M5 复用 M4 已验证的 RFC 8785、NUL/uint64 framing 和 I-JSON safe integer domain，但发布新的 generic utility 与 type IDs：

| Type ID | Schema version |
|---|---|
| `evidence-concept` | `0.1.0` |
| `evidence-version` | `0.1.0` |
| `bn-node-concept` | `0.1.0` |
| `bn-node-version` | `0.1.0` |
| `evidence-binding-version` | `0.1.0` |
| `cpt-version` | `0.1.0` |
| `task-profile-version` | `0.1.0` |
| `coverage-reporting-policy-version` | `0.1.0` |
| `layout-version` | `0.1.0` |
| `assessment-scheme-version` | `0.1.0` |
| `source-descriptor` | `0.1.0` |

规则：

- backend 通过可注入 `IdFactory` 签发 version ID，通过可注入 `Clock` 记录 audit time；
- `content_hash` 只覆盖决定该对象语义或执行的 canonical payload，不覆盖 ID、author、timestamp 和 lineage note；
- 两个不同 version IDs 可以拥有相同 content hash；它们仍是两个 lineage records；
- version 内部交叉引用使用 `ComponentIdRef(kind, version_id)`，避免 BN node/CPT 双向引用造成递归 hash；
- `AssessmentSchemeVersion` 使用 `PinnedComponentRef(kind, version_id, content_hash)` 保存 dependency closure；
- repository 保证同一 version ID 的 bytes 永不改变；scheme validator 重算每个 pinned component hash；
- 所有将一起发布的 IDs 先分配，再构造交叉引用、计算 hashes、验证完整 batch，最后一次提交；
- 不提供 `get_latest`、`resolve_latest` 或隐式升级 operation。版本列表返回全部记录，并以 `(created_at, version_id)` 稳定排序；选择由用户或 exact scheme ref 完成。

`src/pilot_assessment/anchors/fingerprint.py` 中公开 legacy hash 函数保留名称和输出；它们改为调用 generic primitive 前必须通过现有 hash regression，不能改变 M1–M4 identities。

### 4.2 Component contracts

Task 2 按 strict/frozen Pydantic contracts 实现以下语义：

```text
EvidenceConcept
  concept_id, name, description, tags, lifecycle

EvidenceVersion
  evidence_version_id, concept_id
  recipe: EvidenceRecipe
  scientific_status, lineage, content_hash

BnNodeConcept
  concept_id, name, description, node_role, tags, lifecycle

BnNodeVersion
  bn_node_version_id, concept_id
  ordered_states
  ordered_probabilistic_parent_ids
  cpt_version_id
  documentation, scientific_status, lineage, content_hash

EvidenceBindingVersion
  evidence_binding_version_id
  evidence_version_id
  ordered_observation_states
  observation_mapping
  ordered_probabilistic_parent_ids
  cpt_version_id
  observation_policy, modality_attribution_weights
  lineage, content_hash

CptVersion
  cpt_version_id
  child_variable_id
  ordered_parent_variable_ids
  child_state_ids
  ordered_parent_state_ids
  materialized_probabilities
  mode, generator_metadata, source, lineage, content_hash
```

`EvidenceVersion.recipe.inputs` 是 extraction source bindings 的唯一 canonical 表达，不再复制第二份 `source_bindings` 字段。M4R 的 `recipe_version` 保留为 recipe/migration metadata；M5 exact identity 是 `evidence_version_id + content_hash`。

`EvidenceBindingVersion.modality_attribution_weights` 只做 reporting/coverage attribution：key 必须来自 target EvidenceVersion source-provenance closure 中的 core raw modalities，值 finite、非负且和为 1。它不改变 Evidence likelihood，不是数据质量权重，也不复制 extraction bindings。

Published concept records 与 versions 均不可原地修改。新建 concept 的 draft 在首次 publish 前可改；首次发布后，科学含义变化应创建新 concept，算法/参数/显示说明变化可在原 concept 下创建新 version。`archived/retired` 是 library lifecycle metadata，不删除历史 version，也不影响 exact replay。

### 4.3 Source provenance 与 D-040

`SourceDescriptor` 使用下列互斥 kind：

- `raw_stream`：X、U、I、G、EEG、ECG、pilot_camera；
- `session_semantic`：例如 duration；
- `task_semantic`：task reference、phase/event/AOI/expected envelope；
- `derived_artifact`：必须列出稳定 source dependencies，且递归闭合到前三类；
- `evidence_observation`：另一条已评分 Evidence 的 state/score/likelihood；不能成为 active `EvidenceVersion` extraction input。

Migration validator 不按 `anchor_id` 分支。它逐个解析 `recipe.inputs[*].source_id`：未知 source、provenance cycle、无法闭合的 derived artifact 或 `evidence_observation` 都返回结构化 incompatibility diagnostic。Hover starter 为现有 `semantic.*`、`derived.*` 资源提供显式 descriptors；`anchor.O1-score`、`anchor.O5-score` 由 namespace resolver 归类为 `evidence_observation`，因此旧 O8 自然被拦截。

M5 v0 active import 支持 direct raw/session/task source 与已在 source catalog 中证明闭包的 typed derived artifact；不接受无 descriptor 的字符串约定。

### 4.4 Scheme、draft 与原子发布

```text
TaskProfileVersion
  task_profile_version_id, task_concept_id
  task semantics, required source descriptors, reference/annotation/AOI parameters
  lineage, content_hash

CoverageReportingPolicyVersion
  policy_version_id, applicability/coverage/output rules, content_hash

LayoutVersion
  layout_version_id, node positions/groups/viewport metadata, content_hash

AssessmentSchemeVersion
  scheme_version_id, scheme_concept_id
  pinned task profile
  pinned EvidenceVersion/EvidenceBindingVersion/BnNodeVersion/CptVersion refs
  pinned reporting policy/layout refs
  output node IDs, lineage, content_hash

SchemeDraft
  draft_id, base_scheme_version_id
  graph_version, layout_version, history_cursor
  exact retained refs + candidate component snapshots
  validation state and diagnostics
```

Draft 允许 dangling edge、缺 CPT、缺 state、缺 output 和不完整 candidate，因此 DTO 可保存而 executable validator 返回 `draft_incomplete` 或 `draft_invalid`。非法 JSON、非法 ID、非有限数字不能进入 canonical draft。

所有 graph operations 都必须携带 `expected_graph_version`；纯布局 operation 携带 `expected_layout_version`，不递增 graph version。成功 operation 返回完整 canonical draft、structured diff 和新 version；冲突不修改 draft。

Publish 分两阶段但只允许一次可见提交：

1. `prepare_publication` 在内存中分配候选 IDs、重写 candidate refs、计算 hashes、构造 closure 并完成技术校验；
2. `WorkspaceUnitOfWork.publish_atomic(prepared)` 在一个 repository transaction 中写入 concepts/components/scheme 并更新 draft base；任一步异常恢复 publication 前 snapshot。

M5 的 in-memory unit of work 用复制后的 maps/staged batch 实现原子性；M6 必须用数据库 transaction 实现同一 protocol。Service 不允许通过“先写 components、再写 scheme、失败后尽力删除”模拟原子性。

### 4.5 三种 edge

```text
ExtractionEdge
  source_descriptor_id -> evidence candidate/version input binding

BayesianDependencyEdge
  parent BN variable version/candidate -> child BN variable or Evidence binding

InferenceInfluenceEdge
  observed variable -> queried variable, read-only posterior propagation path
```

- `ExtractionEdge` 只修改 `EvidenceVersion.recipe.inputs` 或内部 typed operator graph；
- `BayesianDependencyEdge` 修改 child 的 ordered parents 和 CPT；
- `InferenceInfluenceEdge` 只出现在 `InferenceTrace`，没有对应 mutation operation；
- graph operation 使用不同 command classes，不能接收 union 后再靠 runtime string 猜 edge type；
- operator node 是 Evidence 内部细节，不成为第四类高层节点。

### 4.6 CPT canonical shape 与迁移

- variable state IDs 在各自 ordered state space 内唯一；
- CPT 变量顺序固定为 `ordered parents` 后接 `child`；
- `materialized_probabilities` 是 parent assignment row-major、每行按 child state order 展开的有限 float 数组；
- 行数等于 parent cardinalities 的乘积，列数等于 child cardinality；root prior 有一行；
- 每项 `0 <= p <= 1`，每行和在绝对误差 `1e-9` 内等于 1；
- validator 在 materialization 前检查最大 cells，v0 默认 `250_000`，避免专家误建不可控表；该限制是计算资源边界，不是科学门；
- add-parent 默认复制旧 CPT row 到新 parent 的每个 state，保持 child 暂时独立于新 parent；
- remove-parent 必须随 operation 提供该 parent ordered states 的显式 marginal weights，非负且和为 1；后端按权重求和，不猜 prior；
- 改 state space 会把所有受影响 CPT 标记 incomplete，直到用户选择 generator、提交完整 materialized table 或显式 migration；后端不静默删列/归一化；
- generated CPT 保存 generator metadata 和完整 materialized table；inference 只读 materialized table；
- manual、非单调但合法的 CPT 只产生 warning，不阻止 publish。

Hover starter：root competency 使用 uniform prior；单父使用 `05_BAYESIAN_NETWORK_AND_CPT_DESIGN.md §5.1` 的 0.79/0.20/0.01、0.17/0.66/0.17、0.01/0.20/0.79 表；多父 Evidence 使用 §5.2 的 ranked-node 公式、等权、`weakest_link=0.50`、`sigma=0.60`。全部标记 `engineering_default`，并物化成普通 CPT。

### 4.7 Exact inference

`InferenceEngine` 暴露 transport-neutral 方法：

```text
compile(scheme_version) -> InferencePlan
observe(plan, evidence_observations) -> ObservationSet
infer(plan, observations, query_node_ids) -> PosteriorResult
explain(plan, observations, query_node_ids) -> InferenceTrace
```

v0 使用 NumPy factor algebra 和 deterministic variable elimination，不引入 pgmpy：

- factor 支持 multiply、condition/reduce、sum_out、normalize 和 marginal；
- elimination order 使用 deterministic min-fill；fill 数相同时按 stable variable ID 排序；
- hard observation 转成 one-hot unary likelihood；
- virtual evidence 是与 state order 对齐、非负、至少一个正值的 unary likelihood；不要求输入和为 1，进入 factor 后统一归一化 posterior；
- omitted observation 不增加 factor；`computed + Unacceptable` 是正常 hard/virtual observation；
- impossible evidence（归一化常数为 0）返回结构化 inference error，不伪造 uniform posterior；
- `PosteriorResult` 同时记录 prior、posterior、exact scheme/component identities 和 observation set hash；
- `InferenceTrace` 记录 elimination order、factor scopes、observed/query variables 和只读 sensitivity overlay，不声称提供因果归因或科学贡献率；
- `explain()` 对每个 observation 执行按需 leave-one-observation-out counterfactual，记录 query posterior 的 L1 delta；只有超过数值容差的 pair 才产生 `InferenceInfluenceEdge`，并附 stable canonical path 作为导航提示；
- `InferenceInfluenceEdge.method_id=leave-one-observation-out-v1`，只表示“在当前模型/其他 observations 固定时移除此 observation 会改变该 posterior”，不能保存回 topology，也不能解释为真实世界因果效应。

## 5. 逐任务实施

### Task 0：路线审计、D-040 与实施入口

文件：

- Modify: `docs/product/DECISIONS.md`
- Modify: `docs/product/README.md`
- Modify: `docs/product/06_VISUAL_GRAPH_EDITOR_DESIGN.md`
- Modify: `docs/product/08_WINDOWS_FRONTEND_DESIGN.md`
- Modify: `docs/product/GLOSSARY.md`
- Modify: `docs/product/10_DESIGN_SELF_REVIEW.md`
- Modify: `docs/product/11_IMPLEMENTATION_STATUS.md`
- Modify: `README.md`
- Modify: `docs/product/specs/2026-07-16-m5-shared-versioned-model-library-and-bayesian-workspace-design.md`
- Create: `docs/product/plans/2026-07-16-m5-shared-versioned-model-library-and-bayesian-workspace-implementation-plan.md`

步骤：

- [x] 为 D-001–D-040 增加当前适用性索引，保留历史但明确 starter、部分取代和历史完成门范围。
- [x] 将 D-007 收口为“专家决定模型内容，后端维护 canonical state/version/execution consistency”。
- [x] 新增 D-040，冻结旧 O8 保留、新 TPX parallel version 和 generic migration preflight。
- [x] 将 M5 规格改为 Approved，并把本文登记为 implementation entry。
- [x] 完成文档中心、状态、术语、自审和 root README 同步。
- [x] 执行 §6 的文档自审命令；不进入 production code。

### Task 1：Generic typed content identity

文件：

- Create: `src/pilot_assessment/model_library/__init__.py`
- Create: `src/pilot_assessment/model_library/identity.py`
- Modify: `src/pilot_assessment/anchors/fingerprint.py`
- Create: `tests/model_library/test_identity.py`
- Modify: `tests/anchors/test_fingerprint.py`

RED：

- [x] 写 safe integer、surrogate、non-string key、NaN/Infinity、map-order independence、type/schema separation 和 deterministic hash tests。
- [x] 写 legacy `typed_json_sha256`/known fingerprint regression，确保 refactor 前后 bytes/hash 不变。
- [x] 运行：

      .venv\Scripts\python.exe -m pytest tests/model_library/test_identity.py tests/anchors/test_fingerprint.py -q

  实测 RED：两个目标测试模块均因 `ModuleNotFoundError: pilot_assessment.model_library` 在 collection 阶段失败；这是新增兼容性测试也直接导入尚不存在 generic primitive 所致，失败原因与目标缺口一致。

GREEN：

- [x] 实现 `jcs_bytes()`、`typed_content_sha256()` 与 frozen semantic projection helper。
- [x] legacy functions 仅委托 generic primitives，不改变公开名称、type IDs 或输出。
- [x] 复跑 focused tests：`67 passed`；扩展 fingerprint regression：`118 passed, 1 skipped`，skip 原因为 host 不允许创建测试 symlink；本次文件的 Ruff、format 与定向 ty 均通过。

提交边界：`feat: add generic model component identity`

### Task 2：M5 public contracts 与 JSON Schema

文件：

- Create: `src/pilot_assessment/contracts/model_components.py`
- Create: `src/pilot_assessment/contracts/bayesian.py`
- Create: `src/pilot_assessment/contracts/assessment_scheme.py`
- Modify: `src/pilot_assessment/contracts/__init__.py`
- Modify: `src/pilot_assessment/schemas/export.py`
- Create: `tests/contracts/test_model_components.py`
- Create: `tests/contracts/test_bayesian_contracts.py`
- Create: `tests/contracts/test_assessment_scheme.py`
- Modify: `tests/schemas/test_schema_export.py`
- Create: `schemas/evidence-concept-0.1.0.schema.json`
- Create: `schemas/evidence-version-0.1.0.schema.json`
- Create: `schemas/bn-node-concept-0.1.0.schema.json`
- Create: `schemas/bn-node-version-0.1.0.schema.json`
- Create: `schemas/evidence-binding-version-0.1.0.schema.json`
- Create: `schemas/cpt-version-0.1.0.schema.json`
- Create: `schemas/task-profile-version-0.1.0.schema.json`
- Create: `schemas/coverage-reporting-policy-version-0.1.0.schema.json`
- Create: `schemas/layout-version-0.1.0.schema.json`
- Create: `schemas/assessment-scheme-version-0.1.0.schema.json`
- Create: `schemas/source-descriptor-0.1.0.schema.json`
- Create: `schemas/scheme-draft-0.1.0.schema.json`
- Create: `schemas/inference-plan-0.1.0.schema.json`
- Create: `schemas/observation-set-0.1.0.schema.json`
- Create: `schemas/posterior-result-0.1.0.schema.json`
- Create: `schemas/inference-trace-0.1.0.schema.json`
- Create: byte-identical files with the same names under `src/pilot_assessment/schema_resources/`

RED：

- [x] 覆盖 strict/frozen round-trip、extra fields、duplicate states、NaN、invalid IDs、ID-only internal ref、pinned ref、draft incomplete parse 和三种 edge DTO 不可互换。
- [x] 覆盖 schema filename/ID、deterministic bytes 与双目录 byte parity。
- [x] 运行：

      .venv\Scripts\python.exe -m pytest tests/contracts/test_model_components.py tests/contracts/test_bayesian_contracts.py tests/contracts/test_assessment_scheme.py tests/schemas/test_schema_export.py -q

  实测 RED：三个目标测试模块分别因 `pilot_assessment.contracts.model_components`、`bayesian`、`assessment_scheme` 不存在而在 collection 阶段失败，原因与目标缺口一致。

GREEN：

- [x] 按 §4 实现 contracts；所有 published semantic DTO 使用 strict/frozen nested data。
- [x] 为 M5 public DTO 注册 Draft 2020-12 schemas，并执行：

      .venv\Scripts\python.exe -m pilot_assessment.schemas.export

- [x] 复跑 focused tests：`46 passed`；提交前完整 `tests/contracts` + schema-export regression 为 `403 passed`；16 类新增 schema 在 root/package 双目录 byte-identical，legacy schema hash regression 保持通过；本次生产与测试文件定向 Ruff、format、ty 通过。

提交边界：`feat: define M5 model and scheme contracts`

### Task 3：Source catalog 与 migration compatibility preflight

文件：

- Create: `src/pilot_assessment/model_library/sources.py`
- Create: `src/pilot_assessment/model_library/migration.py`
- Create: `tests/model_library/test_sources.py`
- Create: `tests/model_library/test_m4r_migration_preflight.py`
- Create: `src/pilot_assessment/model_library/profile_data/hover/source-descriptors.json`

RED：

- [x] 覆盖 raw/session/task root、合法 derived closure、unknown source、cycle、evidence-observation rejection 和 structured path diagnostic。
- [x] 对全部 packaged M4R recipes 运行 generic preflight；断言旧 O8 因两个 `anchor.*` bindings 不兼容，且诊断不依赖 `recipe_id`/`anchor_id` 特判。
- [x] 运行：

      .venv\Scripts\python.exe -m pytest tests/model_library/test_sources.py tests/model_library/test_m4r_migration_preflight.py -q

  实际 RED：测试收集阶段分别因 `pilot_assessment.model_library.sources` 与 `.migration` 不存在产生预期 `ModuleNotFoundError`；没有先写生产实现。

GREEN：

- [x] 实现 descriptor registry、仅用于识别 legacy Evidence observation 的窄 namespace fallback、provenance DFS 与 compatibility report；active raw/session/task/derived sources 均要求显式 descriptor。
- [x] 为 starter raw/session/task、`semantic.*`/`derived.*` bindings 保存 20 个 typed provenance descriptors，覆盖 X/U/I/G/EEG/ECG/pilot_camera；未知 source 默认拒绝 active import。
- [x] 旧 recipe bytes 不改写，migration result 只产生 lineage 与 compatibility metadata；全部 18 个 packaged recipes 使用同一预检，17 个 compatible，旧 `starter.o8` 因两个 `anchor.*` inputs 自然为 legacy-only。
- [x] 复跑 focused tests：`11 passed`；`tests/model_library` + M4R starter catalog regression 为 `29 passed`；定向 Ruff、format、ty 与 `git diff --check` 通过。

提交边界：`feat: validate M4R source provenance for M5`

### Task 4：Global component library

文件：

- Create: `src/pilot_assessment/model_library/repository.py`
- Create: `src/pilot_assessment/model_library/service.py`
- Create: `tests/model_library/test_repository.py`
- Create: `tests/model_library/test_service.py`

RED：

- [x] 覆盖 concept create、同 concept 多个 parallel versions、不同 concepts 同名、exact get、stable list、lineage query、archive metadata、duplicate ID 不可覆盖和 hash claim mismatch。
- [x] 明确断言 service 没有 `latest` resolution；调用不存在的 version 必须 exact not-found。
- [x] 运行：

      .venv\Scripts\python.exe -m pytest tests/model_library/test_repository.py tests/model_library/test_service.py -q

  实际 RED：测试收集阶段因 `pilot_assessment.model_library.repository` 不存在产生预期 `ModuleNotFoundError`；未先写生产实现。

GREEN：

- [x] 实现 protocol、in-memory store、injected Clock/IdFactory 和 immutable snapshot boundary；同 kind/exact ID 永不可覆盖，所有 hash-bearing records 入库前重算 typed content hash。
- [x] list/filter 允许按 concept/type/lifecycle/tags 查询，以 `(created_at, record_id)` 为主键稳定排序，但不替用户选择版本；archive/retire 是独立 library metadata，不删除或改写 frozen item。
- [x] 复跑 focused tests：`8 passed`；完整 `tests/model_library` 为 `34 passed`，并覆盖 Task 3 SourceDescriptor identity 原样入库；定向 Ruff、format、ty 与 `git diff --check` 通过。

提交边界：`feat: add global versioned model library`

### Task 5：Scheme reference closure 与 technical validation

文件：

- Create: `src/pilot_assessment/schemes/__init__.py`
- Create: `src/pilot_assessment/schemes/validation.py`
- Create: `tests/schemes/test_reference_closure.py`
- Create: `tests/schemes/test_validation.py`
- Create: `tests/schemes/support.py`

RED：

- [x] 覆盖缺 parent/CPT/evidence/binding/operator/source/task semantic/output、hash mismatch、duplicate variable、两类 DAG cycle、orphan pin 和 exact valid closure。
- [x] 覆盖 generic 2-state/4-state、任意 ID/数量合法；测试不得引用 Hover ID。
- [x] 覆盖科学未校准、non-monotonic CPT、非 starter topology 只 warning 或通过，不成为 blocker。
- [x] 运行：

      .venv\Scripts\python.exe -m pytest tests/schemes/test_reference_closure.py tests/schemes/test_validation.py -q

  实测 RED：测试收集阶段因 `pilot_assessment.schemes` 尚不存在产生预期 `ModuleNotFoundError`；未先写生产实现。

GREEN：

- [x] 实现 draft 与 executable 两级 diagnostics，location 使用稳定 JSON Pointer/component ID。
- [x] executable disposition 只受 M5 规格 §11 的技术错误影响；科学未校准只返回 warning，合法的非单调 CPT 不被新增门禁拦截。
- [x] 复跑 focused tests：`15 passed`；`tests/schemes` + `tests/model_library` + recipe-validation regression 为 `58 passed`；定向 Ruff、format、ty、generic-ID scan 与 `git diff --check` 均通过。

提交边界：`feat: validate exact-pinned assessment schemes`

### Task 6：Draft operations、undo/redo 与 atomic publish

文件：

- Create: `src/pilot_assessment/schemes/operations.py`
- Create: `src/pilot_assessment/schemes/repository.py`
- Create: `src/pilot_assessment/schemes/service.py`
- Create: `tests/schemes/test_operations.py`
- Create: `tests/schemes/test_draft_repository.py`
- Create: `tests/schemes/test_publish.py`

RED：

- [ ] 覆盖从任意 scheme 建 draft、autosave incomplete、expected graph/layout revision、canonical state return、operation diff、undo、redo 和 redo-branch truncation。
- [ ] 覆盖 clone/replace EvidenceVersion、add/remove component、update recipe/scorer、update BN states/CPT、两类 edge add/remove 和 output selection。
- [ ] 覆盖 publish 只创建 changed versions、复用 unchanged pins、旧 scheme 不变、failure injection 无 partial component/scheme、replay exact hashes。
- [ ] 运行：

      .venv\Scripts\python.exe -m pytest tests/schemes/test_operations.py tests/schemes/test_draft_repository.py tests/schemes/test_publish.py -q

  预期 RED：operations/repository/service 尚不存在。

GREEN：

- [ ] 实现 typed command dispatch；不提供无类型 `edge.add` domain method。
- [ ] 实现 in-memory `WorkspaceUnitOfWork` staged-batch transaction 和 failure injection hook。
- [ ] publish 返回 new component refs、new scheme ref、retained refs 和 structured diff。
- [ ] 复跑 focused tests。

提交边界：`feat: publish scheme drafts atomically`

### Task 7：BN/CPT validation、materialization 与 migration

文件：

- Create: `src/pilot_assessment/bayesian/__init__.py`
- Create: `src/pilot_assessment/bayesian/validation.py`
- Create: `tests/bayesian/test_cpt_validation.py`
- Create: `tests/bayesian/test_cpt_migration.py`
- Create: `tests/bayesian/test_ranked_cpt.py`

RED：

- [ ] 覆盖 root/单父/多父 shape、parent order、negative/>1/NaN、row sum tolerance、cell cap、state mismatch 和 valid manual non-monotonic warning。
- [ ] 覆盖 add-parent row replication；remove-parent 缺 weights 拒绝、显式 weights 加权结果；state edit 使 dependent CPT incomplete。
- [ ] 手算 ranked generator 一组 parent assignment，并断言 materialized table 行序稳定。
- [ ] 运行：

      .venv\Scripts\python.exe -m pytest tests/bayesian/test_cpt_validation.py tests/bayesian/test_cpt_migration.py tests/bayesian/test_ranked_cpt.py -q

  预期 RED：BN validation 尚不存在。

GREEN：

- [ ] 实现 generic validators 和 pure migration functions；不引用 Hover IDs。
- [ ] 实现 uniform prior、ordered single-parent 与 ranked-node materializer helpers，参数全部显式输入。
- [ ] 复跑 focused tests。

提交边界：`feat: validate and migrate editable CPTs`

### Task 8：Finite-discrete exact inference

文件：

- Create: `src/pilot_assessment/bayesian/factors.py`
- Create: `src/pilot_assessment/bayesian/inference.py`
- Create: `tests/bayesian/test_factors.py`
- Create: `tests/bayesian/test_inference.py`
- Create: `tests/bayesian/test_observations.py`
- Create: `tests/bayesian/test_inference_trace.py`

RED：

- [ ] 用 2-node 与 collider 小 BN 手算 prior/posterior，覆盖反向 posterior propagation、multi-query 和 stable min-fill order。
- [ ] 覆盖 hard、unnormalized virtual、omitted、computed Unacceptable、impossible evidence 和 state-order mismatch。
- [ ] 覆盖 `InferenceInfluenceEdge` 只能由 `explain()` 返回，leave-one-observation-out delta 与手算一致，零 delta 不生成 overlay edge，传入 scheme operation 在 DTO 层即失败。
- [ ] 运行：

      .venv\Scripts\python.exe -m pytest tests/bayesian/test_factors.py tests/bayesian/test_inference.py tests/bayesian/test_observations.py tests/bayesian/test_inference_trace.py -q

  预期 RED：factor/inference modules 尚不存在。

GREEN：

- [ ] 实现 factor algebra、compile、observe、infer、explain 与 deterministic trace。
- [ ] inference 输入只接受已通过 closure/CPT validation 的 immutable plan。
- [ ] 复跑 focused tests。

提交边界：`feat: add exact Bayesian inference engine`

### Task 9：M4R active import 与 compliant TPX version

文件：

- Create: `src/pilot_assessment/model_library/profile_data/hover/evidence-concepts.json`
- Create: `src/pilot_assessment/model_library/profile_data/hover/tpx-raw-task-v1.json`
- Create: `src/pilot_assessment/model_library/profile_data/hover/migration-manifest.json`
- Modify: `src/pilot_assessment/model_library/migration.py`
- Create: `tests/model_library/test_hover_evidence_migration.py`
- Create: `tests/model_library/test_tpx_compliant_version.py`

步骤：

- [ ] 保存旧 `src/pilot_assessment/evidence/profile_data/recipes/o8.json` 的原 bytes/hash；不修改该文件。
- [ ] 导入通过 provenance preflight 的 M4R recipes，并记录原 recipe ID/version/hash/applied revision lineage。
- [ ] 创建同一 TPX concept 下的新 parallel version。其 direct inputs 为 `X.state-vector`、`U.channels` 和 `session.duration-s`；内部复用 envelope membership、movement detection、ratio 与 safe-formula operators，工程初值公式为：

      precision_ratio = inside_expected_envelope_duration / session_duration
      workload_score = 1 / (1 + movement_rate)
      tpx = (precision_ratio + workload_score) / 2

  expected envelope 作为该 EvidenceVersion 中由 task profile 派生并冻结的参数，不读取 O1/O5 observation。
- [ ] focused smoke 断言旧 O8 `legacy_only=true` 且不能进入 active scheme，新版本 source provenance 合法并可由 M4R compiler/executor 执行。
- [ ] 运行：

      .venv\Scripts\python.exe -m pytest tests/model_library/test_hover_evidence_migration.py tests/model_library/test_tpx_compliant_version.py -q

提交边界：`feat: migrate M4R evidence into M5 library`

### Task 10：Hover starter BN component package

文件：

- Create: `src/pilot_assessment/model_library/profile_data/__init__.py`
- Create: `src/pilot_assessment/model_library/profile_data/hover/__init__.py`
- Create: `src/pilot_assessment/model_library/profile_data/hover/bn-node-concepts.json`
- Create: `src/pilot_assessment/model_library/profile_data/hover/bn-node-versions.json`
- Create: `src/pilot_assessment/model_library/profile_data/hover/evidence-bindings.json`
- Create: `src/pilot_assessment/model_library/profile_data/hover/cpts.json`
- Create: `src/pilot_assessment/model_library/profile_data/hover/task-profile.json`
- Create: `src/pilot_assessment/model_library/profile_data/hover/reporting-policy.json`
- Create: `src/pilot_assessment/model_library/profile_data/hover/layout.json`
- Create: `src/pilot_assessment/model_library/profile_data/hover/scheme.json`
- Create: `src/pilot_assessment/model_library/profile_data/hover/manifest.json`
- Create: `src/pilot_assessment/model_library/profile_data/generate_hover_starter.py`
- Create: `src/pilot_assessment/model_library/profile.py`
- Create: `tests/model_library/test_hover_starter_package.py`

步骤：

- [ ] 由 generator 物化 Hover starter resources；生成器的输入是显式 Python data definitions，输出使用 deterministic sorted JSON/UTF-8/LF。
- [ ] 资源声明 4 root competencies、11 sub-skills、18 active Evidence bindings、当前文档映射和工程默认 CPT；这些数量只在 starter-specific test 中断言。
- [ ] manifest 保存每个 resource checksum、type/schema ID、stable version ID 与 dependency closure。
- [ ] generic loader 仅按 manifest/type dispatch，不按 O1/TCP/Hover 写分支。
- [ ] 运行两次 generator，并断言第二次 `git diff` 为空；运行：

      .venv\Scripts\python.exe -m pytest tests/model_library/test_hover_starter_package.py -q

提交边界：`feat: add Hover starter scheme package`

### Task 11：Scheme preview、posterior overlay 与 lightweight workflow

文件：

- Modify: `src/pilot_assessment/schemes/service.py`
- Create: `tests/integration/test_m5_lightweight_workflow.py`

轻量流程只使用几个内存数值和一个 2-state/3-state mini BN，不生成 physical images 或长 session：

1. 加载 Hover starter metadata，创建基于它的另一 task scheme draft；
2. 为“轨迹偏差”concept 创建一个 parallel EvidenceVersion，替换 draft 中 exact ref；
3. 修改一个 BN edge/CPT，preview 锁定 draft hash；
4. 注入一个 hard 和一个 virtual Evidence observation，计算 posterior/trace；
5. publish 创建 changed component versions + new scheme，旧 Hover scheme pins/hashes 不变；
6. replay 两套 scheme，证明选择不同 parallel versions；
7. failure injection 证明 publish 不留下半成品；
8. old O8 仍可 legacy load/replay，但不能被 active scheme closure 接受。

运行：

    .venv\Scripts\python.exe -m pytest tests/integration/test_m5_lightweight_workflow.py -q

提交边界：`feat: complete lightweight M5 model workflow`

### Task 12：M5 completion gate 与交接

文件：

- Modify: `README.md`
- Modify: `docs/product/README.md`
- Modify: `docs/product/09_VALIDATION_AND_HANDOFF.md`
- Modify: `docs/product/10_DESIGN_SELF_REVIEW.md`
- Modify: `docs/product/11_IMPLEMENTATION_STATUS.md`
- Modify: `docs/product/GLOSSARY.md`
- Modify: `docs/product/plans/2026-07-16-m5-shared-versioned-model-library-and-bayesian-workspace-implementation-plan.md`

步骤：

- [ ] 运行所有 M5 focused tests：

      .venv\Scripts\python.exe -m pytest tests/model_library tests/schemes tests/bayesian tests/integration/test_m5_lightweight_workflow.py -q

- [ ] 运行现有 M4R regression：

      .venv\Scripts\python.exe -m pytest tests/evidence -q

- [ ] 仅在里程碑关闭时运行一次 repository gate：

      .venv\Scripts\python.exe -m pytest -q
      .venv\Scripts\ruff.exe check src tests
      .venv\Scripts\ruff.exe format --check src tests
      .venv\Scripts\ty.exe check
      .venv\Scripts\python.exe -m pilot_assessment.schemas.export
      git diff --check

- [ ] 记录实际测试数、耗时、commit 和未实现边界；不得预填通过数字。
- [ ] 只有以上 fresh evidence 全部通过，才能将 M5 标记为 engineering verified。
- [ ] M5 关闭后下一份规格是 M6 persistence/runtime protocol，不直接实现 WinUI。

提交边界：`docs: close M5 model workspace milestone`

## 6. 本计划文档自审

在开始 Task 1 前执行：

```powershell
git diff --check
rg -n "D-031–D-039|D-036–D-039|待书面复核|implementation plan 尚未|后端权威" README.md docs/product -g "!2026-07-16-m5-shared-versioned-model-library-and-bayesian-workspace-implementation-plan.md"
rg -n "T[B]D|T[O]DO|implement[ ]later|后续[ ]补充|待[ ]定|占[ ]位" docs/product/plans/2026-07-16-m5-shared-versioned-model-library-and-bayesian-workspace-implementation-plan.md
```

允许保留的命中必须位于明确标记的历史段落或 M6 protocol placeholder；当前状态、当前权威和下一步不得再出现旧口径。

Markdown 相对链接必须解析到仓库内真实文件；fenced code blocks 必须成对；新计划不得写入尚未实测的 pass count、commit hash 或 software-complete 声明。

## 7. M5 完成定义

只有同时满足以下条件，M5 才能标记 `engineering verified`：

- global library 可保存同 concept 的并行 immutable versions，且没有 `latest` 隐式选择；
- scheme exact-pin IDs/hashes，copy-on-write 后旧 scheme/run 不改变；
- component + scheme publication 经 failure injection 证明原子；
- draft incomplete autosave、undo/redo、optimistic revision 可工作；
- extraction/probabilistic/inference edge DTO 与 operation 不可互换；
- generic scheme 支持任意合法 state count、node count 和 DAG，不依赖 Hover/18/11/4；
- CPT validation/migration 和小型 exact posterior 与手算一致；
- hard/virtual/omitted/Unacceptable observation 语义正确；
- M4R migration 通用检查全部 source provenance；旧 O8 bytes/hash 保留且 active import 被拒，新 TPX version 可运行；
- Hover starter 是 package resource，不是 generic engine 分支；
- JSON Schema 双目录 byte-identical；
- M5 focused、M4R regression、full repository、Ruff、format、ty 和 diff gates 有 fresh passing evidence；
- 状态文档仍明确 `formal_run_authorized=false`，M6/M7/M8 未被冒充完成。
