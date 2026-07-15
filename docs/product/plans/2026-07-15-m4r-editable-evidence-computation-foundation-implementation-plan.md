# M4R Editable Evidence Computation Foundation Implementation Plan

> 状态：Approved / active implementation entry  
> 执行方式：INLINE，严格按任务顺序推进；不启用 subagent  
> 工程方式：平台关键不变量采用轻量 test-first；算子封装、资源迁移和 starter recipes 先实现再做 focused smoke  
> 权威规格：[Expert-Editable Evidence and Assessment Model Design](../specs/2026-07-15-expert-editable-evidence-and-model-design.md)

## 1. 目标

M4R 建立一个专家可编辑、前后端共用同一 canonical object 的 Evidence 计算基础。完成后，专家可以只修改数据化 EvidenceRecipe 就创建、复制、停用、重连和调参，不需要为普通 Anchor 新增或发布 Python whole-Anchor plugin。

本计划只验证平台能够准确保存、校验、编译和执行用户 recipe。它不证明任何 starter Anchor、阈值、AOI、EEG/ECG 公式或能力映射具有科学有效性。

## 2. 实现边界

### 2.1 本里程碑交付

- EvidenceRecipe、OperatorDefinition、typed port、binding、graph、output、scoring、documentation 和 UI metadata 合同；
- 可由 WinUI/C# 消费的确定性 JSON Schema；
- trusted operator registry 与实现协议；
- 允许 incomplete draft 的技术校验器；
- 确定性 DAG compiler、generic executor、逐节点 trace 和错误定位；
- 第一批 Input、Temporal、Gaze/vision、Statistics、Composition、Aggregation、Scoring 算子；
- backend-only create/edit/clone/disable/preview/apply/replay；
- O1–O12、H1–H5、O13 的 starter recipe resources，其中现有 15 个插件仅作为 legacy/reference migration source；
- 一个轻量端到端示例：扰动窗口内关注目标 AOI，修改参数后 preview 改变，apply 后旧 revision 仍可 replay。

### 2.2 本里程碑不交付

- BN 图、CPT、BN inference 和 Evidence-to-BN binding；它们属于 M5；
- SQLite/project persistence、JSON-RPC sidecar 和 run orchestration；它们属于 M6；
- WinUI graph editor；它属于 M7；
- 任意 Python/eval 编辑器；
- 每个 starter recipe 的独立 scientific golden；
- 原始数据质量研究或按表现好坏过滤 evidence。

### 2.3 选择性测试策略

测试不是保护当前 provisional 科学算法不被专家修改，而是保护专家编辑平台能忠实保存和执行 recipe。

以下关键平台不变量采用轻量 test-first，并实际观察 focused RED：

- strict/frozen canonical contracts 与跨语言 schema parity；
- registry identity、unknown operator 和 definition/implementation 一致性；
- dangling reference、DAG、port/type/unit/cardinality 和 parameter technical validation；
- compiler order、executor edge propagation、node-localized error；
- safe-formula 允许列表与逃逸阻断；
- draft optimistic revision、apply immutable snapshot 和 replay。

以下内容允许先做最小实现，再运行 focused smoke：

- 对现有 pure primitives 的 operator wrapper；
- 普通 statistics/temporal/gaze/flight/signal operator；
- starter recipe JSON、catalog wiring 和 legacy migration；
- 文档、UI metadata 和 lightweight E2E assembly。

不为单个专家 recipe、每次参数修改或 starter Anchor 科学合理性编写独立 golden。发现平台 bug 时，先增加能够复现该 bug 的 failing test，再修复。

## 3. 固定模块布局

新主路径放在 src/pilot_assessment/evidence/，不继续扩大 legacy src/pilot_assessment/anchors/plugins/。

| 路径 | 职责 |
|---|---|
| src/pilot_assessment/contracts/evidence_recipe.py | 前后端公共 DTO |
| src/pilot_assessment/evidence/operators.py | operator implementation protocol 与 runtime value boundary |
| src/pilot_assessment/evidence/registry.py | trusted operator definition/implementation registry |
| src/pilot_assessment/evidence/validation.py | only-technical validation 与 diagnostics |
| src/pilot_assessment/evidence/compiler.py | DAG compile 和 immutable executable plan |
| src/pilot_assessment/evidence/executor.py | generic execution、outputs 和 per-node trace |
| src/pilot_assessment/evidence/builtins/ | built-in reusable operators |
| src/pilot_assessment/evidence/repository.py | draft/applied revision repository protocol 与 M4R in-memory implementation |
| src/pilot_assessment/evidence/service.py | create/edit/clone/disable/preview/apply/replay use cases |
| src/pilot_assessment/evidence/profile_data/recipes/ | starter recipe JSON resources |
| schemas/ 与 src/pilot_assessment/schema_resources/ | byte-identical exported contracts |

## 4. 核心合同冻结

### 4.1 Draft 与 executable 的边界

EvidenceRecipe 的 Pydantic 合同只负责 JSON 形状、稳定 ID、有限数值和 immutable snapshot。它允许下列 incomplete 状态被保存：

- edge 暂时悬空；
- required input 暂时未连接；
- required parameter 暂时缺失；
- output 或 scorer 暂时未绑定；
- graph 暂时有环；
- 引用的 operator 暂时未安装。

这些状态由 validation.py 返回结构化 diagnostics；只有 apply 和 execute 要求 disposition=executable。DTO 解析失败、非法 ID、非有限数字和非 JSON parameter 则不进入 canonical draft。

### 4.2 Port 兼容规则 v0.1

PortType 包含 value_type、cardinality、temporal_semantics 和 unit。

- value_type 相同即可连接；any 可与任意 value_type 连接；
- cardinality one/optional 接受最多一条入边，many 接受多条入边；
- required one 必须有一条入边，optional 可无入边；
- 两端 unit 均非空时必须相同；任一端为 null 表示该算子对单位透明；
- temporal_semantics 相同即可连接；timeless 参数可以进入接受 timeless 的端口，不做隐式 resample；
- 所有隐式转换禁止。单位转换、resample、left-hold 和 interval clip 必须由显式 operator node 表达。

### 4.3 Canonical DTO 形状

以下名称在 Task 1 中按 Pydantic strict/frozen contract 实现：

    EvidenceRecipe
      contract_id = "evidence-recipe"
      contract_version = "0.1.0"
      recipe_id: StableId
      recipe_version: positive integer
      anchor: RecipeAnchor
      inputs: tuple[RecipeInputBinding, ...]
      graph: RecipeGraph
      outputs: tuple[RecipeOutputBinding, ...]
      scoring: RecipeScoring | None
      documentation: RecipeDocumentation
      ui: RecipeUiMetadata

    OperatorDefinition
      contract_id = "operator-definition"
      contract_version = "0.1.0"
      operator_id: StableId
      implementation_version: StableId
      family: OperatorFamily
      name/description/pseudocode
      input_ports/output_ports: tuple[OperatorPortDefinition, ...]
      parameter_schema: JSON object
      parameter_ui: tuple[ParameterUiDefinition, ...]
      trace_capability: none | summary | full
      implementation_source: built_in | trusted_extension
      implementation_ref: StableId

RecipeNode 只保存 operator_id、operator_version 和该实例的 parameters。RecipeEdge 保存显式 source node/port 与 target node/port。RecipeOutputBinding 使用 role=primary_value/raw_metric/breakdown/trace 和显式 node/port，不根据 Anchor ID 猜测。

## 5. 逐任务实施

### Task 0：批准状态与实施入口

文件：

- Modify: docs/product/specs/2026-07-15-expert-editable-evidence-and-model-design.md
- Create: docs/product/plans/2026-07-15-m4r-editable-evidence-computation-foundation-implementation-plan.md
- Modify: docs/product/README.md
- Modify: docs/product/11_IMPLEMENTATION_STATUS.md

步骤：

- [x] 将合并规格从 Review candidate 改为 Approved。
- [x] 明确 M4R 已开始，但任何代码能力尚须逐项验证。
- [x] 把本计划登记为当前执行入口。
- [x] 运行文档引用检查：

      rg -n "awaiting final|M4R not started|新 M4R plan 尚未编写" docs/product -g "!2026-07-15-m4r-editable-evidence-computation-foundation-implementation-plan.md"

  结果：当前权威文档无过期状态；旧历史计划中的 superseded 描述保留。

- [x] 提交：

      git add docs/product
      git commit -m "docs: approve and plan M4R evidence foundation"

### Task 1：EvidenceRecipe 与 OperatorDefinition 公共合同

文件：

- Create: src/pilot_assessment/contracts/evidence_recipe.py
- Modify: src/pilot_assessment/contracts/__init__.py
- Create: tests/contracts/test_evidence_recipe.py

RED：

- [x] 先写合同测试，覆盖完整 recipe/definition round-trip、frozen nested parameters、非法 ID/NaN/extra field 拒绝，以及 incomplete graph 可以解析。
- [x] 运行：

      .venv\Scripts\python.exe -m pytest tests/contracts/test_evidence_recipe.py -q

  结果：collection 因 evidence_recipe 模块不存在而失败，确认 RED 有效。

GREEN：

- [x] 实现枚举 RecipeLifecycle、RecipeScientificStatus、InputBindingKind、OperatorFamily、PortCardinality、TemporalSemantics、TraceCapability、OperatorImplementationSource、OutputRole 和 ScoringMode。
- [x] 实现 PortType、OperatorPortDefinition、ParameterUiDefinition、OperatorDefinition。
- [x] 实现 RecipeAnchor、RecipeInputBinding、NodePortReference、RecipeNode、RecipeEdge、RecipeGraph、RecipeOutputBinding、RecipeScoring、RecipeDocumentation、RecipeUiMetadata、EvidenceRecipe。
- [x] 对所有 JSON mapping 使用 freeze_json_mapping；仅做结构约束，不在 DTO 层阻断 incomplete graph。
- [x] 从 contracts/__init__.py 导出公共类型。
- [x] 再运行 focused test：7 passed。
- [x] 运行：

      .venv\Scripts\python.exe -m ruff check src/pilot_assessment/contracts/evidence_recipe.py tests/contracts/test_evidence_recipe.py
      .venv\Scripts\ty.exe check src/pilot_assessment/contracts/evidence_recipe.py

  结果：两项均 exit 0；contracts 回归 354 passed。

- [x] 提交：

      git add src/pilot_assessment/contracts tests/contracts/test_evidence_recipe.py
      git commit -m "feat: define editable evidence recipe contracts"

### Task 2：跨语言 JSON Schema 与 canonical bytes

文件：

- Modify: src/pilot_assessment/schemas/export.py
- Create: schemas/evidence-recipe-0.1.0.schema.json
- Create: schemas/operator-definition-0.1.0.schema.json
- Create: src/pilot_assessment/schema_resources/evidence-recipe-0.1.0.schema.json
- Create: src/pilot_assessment/schema_resources/operator-definition-0.1.0.schema.json
- Modify: tests/schemas/test_schema_export.py

RED：

- [x] 添加 schema 名称、URN、title、contract version、byte-identical 双目标和 Draft 2020-12 validation 测试。
- [x] 添加 incomplete recipe 可被 schema 接受、非法结构 ID 被拒绝的 parity 测试；非有限数字由 canonical JSON 编码与 Pydantic 合同拒绝。
- [x] 运行：

      .venv\Scripts\python.exe -m pytest tests/schemas/test_evidence_recipe_schema.py -q

  结果：3 项均因缺少两个 schema key 失败，确认 RED 有效。

GREEN：

- [x] 将 EvidenceRecipe 和 OperatorDefinition 加入确定性 exporter。
- [x] 导出两份 schema 到 repository root 与 package resources。
- [x] 运行完整 schema suite：34 passed。
- [x] 运行：

      .venv\Scripts\python.exe -m pilot_assessment.schemas.export
      .venv\Scripts\python.exe -m pytest tests/schemas -q

  结果：双目标 byte-identical 测试、ruff、ty 和 git diff --check 均 exit 0。

- [x] 提交：

      git add src/pilot_assessment/schemas schemas src/pilot_assessment/schema_resources tests/schemas
      git commit -m "feat: export evidence recipe schemas"

### Task 3：Trusted Operator Registry

文件：

- Create: src/pilot_assessment/evidence/__init__.py
- Create: src/pilot_assessment/evidence/operators.py
- Create: src/pilot_assessment/evidence/registry.py
- Create: tests/evidence/test_operator_registry.py

实现接口：

    class OperatorImplementation(Protocol):
        def execute(
            self,
            inputs: Mapping[str, object],
            parameters: Mapping[str, JsonValue],
            context: OperatorExecutionContext,
        ) -> Mapping[str, object]: ...

    class OperatorRegistry:
        def register(definition, implementation) -> None: ...
        def definition(operator_id, version) -> OperatorDefinition: ...
        def implementation(operator_id, version) -> OperatorImplementation: ...
        def catalog() -> tuple[OperatorDefinition, ...]: ...

步骤：

- [x] RED：测试重复 identity、definition/implementation 不匹配、未知 operator、确定性 catalog order 和 trusted identity。
- [x] 运行 focused test：因 evidence package 不存在而 collection 失败，确认 RED 有效。
- [x] GREEN：实现显式注册，无 dynamic import、无 eval、无 whole-Anchor fallback。
- [x] Registry 按 operator_id/version 唯一索引；catalog 返回 canonical sorted definitions。
- [x] 运行 focused test：7 passed；ruff、ty 均 exit 0。
- [x] 提交：

      git add src/pilot_assessment/evidence tests/evidence/test_operator_registry.py
      git commit -m "feat: add trusted operator registry"

### Task 4：Only-Technical Recipe Validator

文件：

- Create: src/pilot_assessment/evidence/validation.py
- Create: tests/evidence/test_recipe_validation.py

诊断合同：

    RecipeValidationOutcome
      disposition: incomplete | executable
      diagnostics: tuple[RecipeDiagnostic, ...]

    RecipeDiagnostic
      code: StableId
      severity: error | warning
      location: stable JSON-pointer-like path
      message: human-readable technical reason

步骤：

- [x] RED：用 8 个代表测试覆盖 duplicate IDs、dangling graph/binding/output、unknown operator、cycle、required/cardinality input、port type/unit/temporal、parameters、primary output 和 scorer。
- [x] 明确测试：starter_template recipe 可直接成为 executable；validator 不接收科学认可状态或 preview 表现值，因此不会据此阻断。
- [x] GREEN：用 jsonschema Draft202012Validator 校验每个 node/custom scorer parameters；error path 定位到具体 node/parameter。
- [x] 使用 Kahn topological sort 检测 cycle；不执行 operator。
- [x] incomplete draft 返回 diagnostics，不抛出科学合理性异常。
- [x] 运行：

      .venv\Scripts\python.exe -m pytest tests/evidence/test_recipe_validation.py -q
      .venv\Scripts\python.exe -m ruff check src/pilot_assessment/evidence tests/evidence
      .venv\Scripts\ty.exe check src/pilot_assessment/evidence

  结果：validator focused 8 passed；相关 contracts/schemas/evidence 56 passed；ruff、ty exit 0。

- [x] 提交：

      git add src/pilot_assessment/evidence/validation.py tests/evidence/test_recipe_validation.py
      git commit -m "feat: validate editable evidence recipes"

### Task 5：Deterministic Compiler 与 Generic Executor

文件：

- Create: src/pilot_assessment/evidence/compiler.py
- Create: src/pilot_assessment/evidence/executor.py
- Create: tests/evidence/test_recipe_compiler.py
- Create: tests/evidence/test_recipe_executor.py

计划与结果：

    CompiledRecipe
      recipe snapshot
      canonical topological node order
      resolved operator definitions
      incoming edge bindings
      output bindings

    RecipeExecutionResult
      recipe_id/version
      outputs by stable output_id
      node traces in execution order

步骤：

- [ ] RED：compiler 拒绝 non-executable recipe；同层 node 以 node_id 稳定排序；compile 不调用 implementation。
- [ ] GREEN：compiler 只消费 validator=executable 的 recipe，并冻结 exact recipe snapshot。
- [ ] RED：executor 按 edge 传值、支持 external input binding、收集 selected trace，并把异常定位到 node_id/operator identity。
- [ ] GREEN：executor 不根据 Anchor ID 分支，不读取 hidden parameter，不隐式转换单位或时间网格。
- [ ] 运行：

      uv run pytest tests/evidence/test_recipe_compiler.py tests/evidence/test_recipe_executor.py -q
      uv run ruff check src/pilot_assessment/evidence tests/evidence
      uv run ty check src/pilot_assessment/evidence

  预期：exit 0。

- [ ] 提交：

      git add src/pilot_assessment/evidence tests/evidence
      git commit -m "feat: compile and execute evidence recipes"

### Task 6：最小 Built-in Operator Vertical Slice

文件：

- Create: src/pilot_assessment/evidence/builtins/__init__.py
- Create: src/pilot_assessment/evidence/builtins/core.py
- Create: src/pilot_assessment/evidence/builtins/statistics.py
- Create: src/pilot_assessment/evidence/builtins/scoring.py
- Create: tests/evidence/builtins/test_core.py
- Create: tests/evidence/builtins/test_statistics.py
- Create: tests/evidence/builtins/test_scoring.py
- Create: tests/evidence/test_parameter_edit_vertical_slice.py

首批 operator identity：

- input.binding@0.1.0
- constant.number@0.1.0
- composition.safe-formula@0.1.0
- statistics.mean@0.1.0
- statistics.sum-duration@0.1.0
- statistics.ratio@0.1.0
- aggregation.event@0.1.0
- scoring.ordered-dau@0.1.0

步骤：

- [ ] 先实现最小 operator definitions/implementations，并直接组合一个可运行 recipe。
- [ ] 实现后增加每个 operator 1–3 个 focused behavior/parameter-contract smoke；不建立逐 Anchor golden。
- [ ] safe-formula 只允许常量、已声明变量、算术、比较、布尔、min/max/abs/clip；禁止 attribute、subscript、import、call 任意函数和名称逃逸。
- [ ] ordered-dau 输出 EvidenceState 与三状态 likelihood，不把表现极差视为 missing。
- [ ] 垂直切片 recipe 使用 input.binding -> safe-formula -> ordered-dau；只改 recipe parameter 即改变输出，Python 文件和 registry identity 不变。
- [ ] 运行：

      uv run pytest tests/evidence/builtins tests/evidence/test_parameter_edit_vertical_slice.py -q

  预期：exit 0。

- [ ] 提交：

      git add src/pilot_assessment/evidence/builtins tests/evidence
      git commit -m "feat: add editable core evidence operators"

### Task 7：Temporal、Event 与 Gaze/AOI 示例算子

文件：

- Create: src/pilot_assessment/evidence/builtins/temporal.py
- Create: src/pilot_assessment/evidence/builtins/gaze.py
- Create: tests/evidence/builtins/test_temporal.py
- Create: tests/evidence/builtins/test_gaze.py
- Create: tests/evidence/test_disturbance_aoi_recipe.py

operator identity：

- temporal.event-select@0.1.0
- temporal.event-window@0.1.0
- temporal.interval-intersect@0.1.0
- gaze.aoi-intervals@0.1.0
- gaze.aoi-filter@0.1.0
- gaze.first-match-latency@0.1.0
- gaze.dwell-ratio@0.1.0

步骤：

- [ ] 先包装现有 anchors/primitives/events.py、gaze_aoi.py 和 fixation.py 中可复用 pure logic；不复制一份 Anchor-specific 算法。
- [ ] 支持 assigned AOI label mode；geometry-association mode 只在 recipe 显式选择时启用。
- [ ] 使用小型内存 frame/interval fixture，不生成四套 90 秒或万行级数据。
- [ ] 端到端 recipe：EventSelect(disturbance) -> EventWindow -> GazeAoiIntervals -> IntervalIntersect -> AoiFilter -> FirstMatchLatency/DwellRatio -> EventAggregate -> OrderedDau。
- [ ] 修改 expected AOI 或 window end_offset 后 preview 应机械改变；不评价哪组参数更科学。
- [ ] 实现完成后补充并运行 focused smoke，预期 exit 0。
- [ ] 提交：

      git add src/pilot_assessment/evidence/builtins tests/evidence
      git commit -m "feat: compose disturbance AOI evidence recipe"

### Task 8：Flight、Control、Physiology 所需 Operator Families

文件：

- Create: src/pilot_assessment/evidence/builtins/signal.py
- Create: src/pilot_assessment/evidence/builtins/events.py
- Create: src/pilot_assessment/evidence/builtins/flight.py
- Modify: src/pilot_assessment/evidence/builtins/statistics.py
- Create: tests/evidence/builtins/test_signal.py
- Create: tests/evidence/builtins/test_events.py
- Create: tests/evidence/builtins/test_flight.py

至少实现：

- field/channel select、unit conversion、difference、smooth、detrend；
- threshold crossing、hold/run、peak、turning point、movement、reversal、recovery；
- target/reference error、envelope membership、distance、angle、capture；
- count、duration、RMS、median、percentile、rate、pooled ratio；
- per-window/per-event/per-phase/session worst/best/mean/median。

步骤：

- [ ] 优先实现对现有 movement、reversal、envelopes、reference_join 和 preprocessing pure functions 的薄包装。
- [ ] 实现后以代表输入 smoke reusable operator 的平台行为和错误边界；不为每个 Anchor 建一套重复 golden。
- [ ] EEG/ECG 通过 field/channel/signal/statistics/scoring 组合进入 recipe；异常数值仍参与计算，不做 performance quality gate。
- [ ] 运行 builtins focused suite、ruff、ty，预期 exit 0。
- [ ] 提交：

      git add src/pilot_assessment/evidence/builtins tests/evidence/builtins
      git commit -m "feat: expand reusable evidence operator library"

### Task 9：Backend-only Draft、Preview、Apply 与 Replay

文件：

- Create: src/pilot_assessment/evidence/repository.py
- Create: src/pilot_assessment/evidence/service.py
- Create: tests/evidence/test_recipe_repository.py
- Create: tests/evidence/test_recipe_service.py

M4R 使用进程内 repository；M6 在不改变 service use cases 的前提下替换为持久化实现。

API：

    create_draft(recipe, author_id)
    save_draft(recipe, expected_draft_revision)
    clone_draft(source_recipe_id, new_recipe_id)
    set_lifecycle(recipe_id, active|disabled|retired)
    preview(recipe_id, execution_inputs)
    apply(recipe_id, optional_note)
    get_applied_revision(revision_id)
    replay(revision_id, execution_inputs)

步骤：

- [ ] RED：autosave 接受 incomplete draft；optimistic revision 防止覆盖较新编辑；clone 生成独立 recipe identity；disabled/retired 不删除历史。
- [ ] RED：apply 只在 technical executable 时成功；不要求人工审批、pytest、scientific status 或文献。
- [ ] RED：applied revision immutable；后续 draft 修改不改变旧 revision；replay 使用 exact applied snapshot。
- [ ] GREEN：实现 canonical content identity、author/time/diff metadata；note 可空。
- [ ] preview 不创建 applied revision，错误返回 node-localized diagnostics。
- [ ] 运行 focused tests、ruff、ty，预期 exit 0。
- [ ] 提交：

      git add src/pilot_assessment/evidence/repository.py src/pilot_assessment/evidence/service.py tests/evidence
      git commit -m "feat: manage editable evidence recipe revisions"

### Task 10：Starter Recipe Resources 与 Legacy Migration

文件：

- Create: src/pilot_assessment/evidence/profile_data/__init__.py
- Create: src/pilot_assessment/evidence/profile_data/recipes/*.json
- Create: src/pilot_assessment/evidence/catalog.py
- Create: tests/evidence/test_starter_recipe_catalog.py
- Create: tests/evidence/test_legacy_recipe_comparison_smoke.py

步骤：

- [ ] 为 O1–O12、H1–H5、O13 建立 18 个 starter recipe resources；全部标记 scientific_status=starter_template。
- [ ] O1–O12/H1–H3 从现有插件、parameter resources 和 primitives 迁移；现有 Python plugin 保留且标记 legacy/reference，不再是新 Anchor 默认扩展方式。
- [ ] H4/H5/O13 直接使用 operator composition，不新增 whole-Anchor plugin。
- [ ] catalog 不固定 expert model cardinality；18 只是 packaged starter inventory。
- [ ] 资源完成后只选 trajectory/control、gaze、physiology 三个代表 recipe 做 legacy comparison smoke，以发现明显 wiring 错误；不要求所有 expert 后续修改保持旧数值等价。
- [ ] 测试任意第 19 个 recipe 可注册、执行和应用，orchestrator 无 Anchor-ID 分支。
- [ ] 运行：

      uv run pytest tests/evidence/test_starter_recipe_catalog.py tests/evidence/test_legacy_recipe_comparison_smoke.py -q

  预期：exit 0。

- [ ] 提交：

      git add src/pilot_assessment/evidence/profile_data src/pilot_assessment/evidence/catalog.py tests/evidence
      git commit -m "feat: migrate starter anchors to editable recipes"

### Task 11：M4R 轻量端到端验收与文档收尾

文件：

- Create: tests/e2e/test_m4r_editable_evidence_workflow.py
- Modify: docs/product/02_ASSESSMENT_CORE_DESIGN.md
- Modify: docs/product/07_RUNTIME_PROTOCOL_DESIGN.md
- Modify: docs/product/09_VALIDATION_AND_HANDOFF.md
- Modify: docs/product/11_IMPLEMENTATION_STATUS.md
- Modify: docs/product/GLOSSARY.md
- Modify: docs/product/README.md

E2E 流程：

1. 加载一个小型 aligned session fixture；
2. 创建 disturbance-AOI recipe draft；
3. autosave incomplete graph；
4. 补全连接并通过 technical validation；
5. preview；
6. 修改 window/AOI/scorer 参数并再次 preview，结果改变；
7. apply 为 immutable revision A；
8. 继续修改并 apply revision B；
9. replay A，确认仍得到 A 的执行路径与结果；
10. clone 为新 Anchor，disabled 后历史 revision 仍可读取；
11. 全流程没有新增 Python whole-Anchor plugin。

步骤：

- [ ] 先用已有 service/runtime 组装最小 E2E，再补一个 focused workflow smoke。
- [ ] 运行 focused E2E，预期 exit 0 且不生成万行级 fixture。
- [ ] 更新文档，明确完成的是工程平台能力，不是科学验证。
- [ ] 运行全量轻量回归：

      uv run pytest -q
      uv run ruff check .
      uv run ty check src/pilot_assessment
      uv build

  预期：全部 exit 0。

- [ ] 检查工作树和改动范围：

      git status --short
      git diff --check

- [ ] 提交：

      git add src tests schemas docs pyproject.toml
      git commit -m "feat: complete M4R editable evidence foundation"

## 6. M4R 完成门

只有以下条件全部有新鲜命令证据时才报告 M4R complete：

1. 前端可消费 schema 与后端运行时使用同一个 EvidenceRecipe DTO；
2. incomplete draft 可保存，apply 只执行 only-technical checks；
3. 无 Anchor-ID 分支的 compiler/executor 可以运行任意 cardinality recipe catalog；
4. 普通参数、binding、node、edge、formula、aggregation 和 scorer 修改不需要 Python 发布；
5. disturbance-AOI 轻量 E2E 完成 preview/change/apply/replay；
6. O1–O13/H1–H5 都存在 starter recipe，且明确不是科学有效性声明；
7. 新增第 19 个 recipe 不修改 orchestrator；
8. 15 个旧 whole-Anchor plugins 保留为 legacy/reference/replay source；
9. 全量 pytest、ruff、ty、build 在最终工作树上通过；
10. 状态文档不把 M5 BN、M6 runtime、M7 WinUI 或 M8 packaging 误报为已完成。

## 7. 计划自审

- 规格覆盖：本计划逐项覆盖规格 §3–§10 和 M4R §11，不把 M5–M8 混入实现。
- 修改自由：参数和图结构只在 recipe 中；普通编辑不需要 plugin version、审核、golden 或 build。
- 前后端一致：合同与 JSON Schema 是唯一来源，C# 后续只渲染/编辑 canonical DTO。
- Draft 语义：结构 DTO 与 executable validation 分离，允许自动保存 incomplete graph。
- 技术边界：validator 只判断 schema、binding、DAG、port、unit、parameter、output/scorer 可执行性。
- 数据边界：坏表现仍产生 evidence；无原始质量过滤和科学合理性 gate。
- 测试成本：只对平台关键不变量 test-first；算子和资源实现后 smoke；使用一个小型 E2E 和三个代表 migration smoke，不恢复四套 90 秒或逐 Anchor 重型 golden。
- 迁移边界：不删除旧代码；新代码位于 evidence package；H4/H5/O13 不走 whole-Anchor plugin。
- 类型一致：合同、registry、compiler、executor、service 使用相同 operator identity、node/port reference 和 recipe snapshot。
- 文档完整：没有 TODO、TBD、占位验收数字或待用户选择项。
