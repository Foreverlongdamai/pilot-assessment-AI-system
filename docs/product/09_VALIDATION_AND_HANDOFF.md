# Validation and Handoff

| 字段 | 值 |
|---|---|
| 设计版本 | v0.1 |
| 当前软件状态 | in_progress（M1/M2 verified；M3 规格与实施计划已批准，代码尚未实现） |
| 当前科学状态 | engineering_default（not scientifically validated） |
| 目的 | 定义验证门槛、证据、交付物和接手方式 |

## 1. 两条独立的验证轴

系统必须同时报告但绝不能混淆：

### 1.1 Software verification

回答“软件是否按声明的合同正确计算”。它覆盖 schema、同步、算法实现、概率计算、事务、协议、UI 和可重现性。

建议状态：

- not_started；
- in_progress；
- verified_for_reference_v0_1；
- failed；
- superseded。

### 1.2 Scientific validation

回答“这些 anchor、阈值、技能映射、CPT 和后验是否真实、可靠、可推广地反映飞行员表现”。它需要领域专家、真实样本和统计研究。

建议状态：

- engineering_default；
- expert_reviewed；
- calibrated；
- internally_validated；
- externally_validated；
- not_supported。

一个 model revision 可以软件已验证而科学状态仍是 engineering_default。UI、导出和报告必须同时携带两种状态。

## 2. 验证层级

### 2.1 静态合同

- JSON Schema / typed contract 可解析；
- ID 唯一、引用可解析、版本字段完整；
- 单位、坐标系、time base 和 state order 明确；
- model bundle content hash 可重建；
- 文档链接、文件路径和示例一致；
- 未使用旧 H6、旧 O2 或 19-node 口径。

### 2.2 Unit 与 property tests

- ingestion adapter：正常、缺列、错单位、损坏、gap、duplicate、out-of-order；
- M3 synchronization：Decimal round-half-even、已知 scale/offset、scale/drift 一致性、same-clock mapping、int64 边界/overflow、master-clock X session window、negative/tail rows、duplicate mapped ns、稳定排序和 source-row preservation；
- M4 AnchorPlugin temporal processing：按 anchor revision 测试 interpolation/resampling、analysis/window grid、partial-window policy、valid-fraction 与 sampling-rate invariance；
- 每个 AnchorPlugin：手算 golden case、阈值边界、sampling-rate invariance、missing/invalid/not_applicable；
- evidence scoring：D/A/U 单调性和边界包含规则；
- CPT：维度、非负、有限数、每行和为 1；
- BN：小型手算网络的 prior/posterior、缺失 evidence 边缘化和 virtual evidence；
- graph operations：cycle、duplicate、AnchorBinding、state migration、size caps、atomic rollback、undo/redo；
- layout operations：layout_version conflict、批量位置保存且不改变 semantic hash；
- model revision：hash、immutability、parent chain 和 publish gate。

对概率和浮点算法使用明确 tolerance；不能用“看起来接近”代替断言。

### 2.3 Component contract tests

- SessionManifest 与每种文件 adapter；
- AnchorPlugin API 与 registry；
- model bundle loader 与 BN engine adapter；
- JSON-RPC Python server 与 .NET client；
- backend error_code 与 UI recovery action；
- artifact export/import round trip。

### 2.4 Integration tests

- 多模态 bundle → `IngestionReadinessReport` → `SynchronizationInput` → native-rate `AlignedSession` + `SynchronizationReport` → model lock/reference resolution → `RunPreflightReport`；
- aligned session → 18 AnchorResult → evidence；
- evidence → BN posterior、coverage、explanation；
- graph/binding edit → CPT migration → validate → publish；
- published revision → run → reproducible result；
- cancel、crash、restart 与 interrupted recovery。

### 2.5 End-to-end tests

至少维护三类 golden bundle：

1. format-sample-XU：只有 simulator 采集格式样例 X/U，用于接口、解析、时间与缺失模态处理；该记录不提供标准轨迹、任务 ground truth 或能力标签；
2. synthetic-multimodal：含可控 offset/drift、VR/gaze、EEG/ECG 和已知答案；
3. de-identified-reference：经批准的真实 session，用于回归，不进入公开仓库。

通过 WinUI 执行：创建项目、导入、修复或接受 warning、编辑图、发布模型、运行、查看 trace、导出结果。

## 3. 子系统验证矩阵

| 子系统 | 必须证明 | 主要证据 |
|---|---|---|
| Session bundle | 格式、checksum、单位、状态语义正确 | schema tests、corrupt fixtures |
| 时间同步 | native-rate rows 按唯一 clock mapping 对齐、window/越界/重复/误差可见且不改 source 值 | half-even、scale/offset、overflow、same-clock、window、duplicate 和 row-preservation synthetic tests |
| Anchor temporal processing | 插值、重采样与 analysis/window grid 只按锁定 AnchorPlugin/model revision 建立 | M4 per-anchor interpolation/window/sampling-rate tests |
| Anchors | 实现与正式定义、参数和质量门一致 | per-anchor golden tests |
| Evidence | 阈值方向和缺失策略正确 | boundary/property tests |
| BN/CPT | 图合法、概率正确、缺失可边缘化 | hand-computable BN tests |
| Graph editor | 前后端一一对应、失败原子回滚 | .NET/Python contract + UI tests |
| Revisions | 发布不可变、运行可重现 | hash and replay tests |
| Runtime | framing、取消、错误、崩溃恢复 | protocol fault-injection |
| Results | posterior、coverage、trace 和版本完整 | golden result snapshots |
| Privacy | 导出和日志默认脱敏 | privacy inspection tests |

## 4. Graph 与 CPT 发布门槛

draft 只有满足以下全部条件才能 publish：

- node_id、edge_id、anchor binding 唯一且可解析；
- 无 self-loop、duplicate edge 或 directed cycle；
- Guided Mode 类型规则满足，或明确以 Advanced DAG Mode 保存；
- 每个节点 state space 非空、名称唯一且顺序固定；
- parent order 与 CPT dimension 一致；
- 所有 CPT 数值有限、非负、每行和为 1；
- 每个 published evidence node 都有唯一、有效且可解析的 AnchorBinding；unbound node 只能存在于 incomplete draft；
- parent count 与 CPT cell count 不超过项目安全上限；
- AnchorPlugin、参数 schema、依赖 DAG 和 engine 兼容；
- 模型可以编译；
- prior-only、单 evidence、missing evidence 和 all-state smoke inference 均成功；
- manual non-monotonic CPT 必须附 monotonicity_waiver（reviewer、reason、affected rows、scientific rationale）；否则阻止 publish；
- 其他可豁免 validation warnings 已确认并记录理由；
- revision manifest、diff、作者、理由、时间和 hash 完整。

## 5. 科学校准路线

### Stage S0：专家内容审查

- 审查 18 个 anchor 的构念、公式、方向、适用阶段和质量门；
- 审查 11 个 sub-skill、4 个 competency 及共享 evidence 连接；
- 确认 task profile、reference path、phase/event 与安全边界；
- 对每条意见记录 accept/reject/defer 和理由。

输出：expert_reviewed model revision，不等同于统计验证。

### Stage S1：参数校准

- 使用匿名真实 session 和可说明的专家评分；
- 按 task、phase、设备和 pilot cohort 检查分布；
- 优先使用任务/安全界限，其次采用专家成功样本分位数；
- 拟合或 elicitation CPT 时保留样本数、不确定度和 regularization；
- 通过交叉验证或留一 pilot 评估过拟合；
- 冻结 calibrated revision 后再测试，避免数据泄漏。

### Stage S2：内部有效性

建议至少评估：

- known-groups validity：专家/新手或成功/失败组；
- convergent validity：与独立专家评分、HQR、TLX 或其他已批准量表的关联；
- discriminant validity：不同技能维度不应全部退化为同一 workload 指标；
- reliability：重复 session、不同分段或不同 scorer 的稳定性；
- calibration：posterior 与真实/专家标签的匹配；
- decision utility：弱项诊断对训练反馈是否有用；
- sensitivity/specificity 或 ordinal metrics，取决于预注册研究问题。

### Stage S3：稳健性与推广

- leave-one-modality-out 与 missingness ablation；
- threshold、CPT、同步误差和 quality weighting 敏感性；
- 不同 pilot、场景、任务难度、设备和日期的外部验证；
- subgroup performance 和潜在偏差；
- distribution shift 与 out-of-scope 检测；
- 新 model revision 与旧 revision 的纵向可比性。

任何对评估结论有意义的算法或 CPT 变化都需要重新判断适用的验证范围。

## 6. v0.1 软件发布 Gate

### Gate A：设计就绪

- 本目录文档完成并通过一致性自审；
- 所有跨模块决策有 DECISIONS 记录；
- schema、示例和验收标准可实现；
- 未解决问题有 owner 和阻断级别。

### Gate B：Core alpha

- minimal-XU 与 synthetic-multimodal bundle 可运行；
- 18 个 AnchorPlugin 合同齐全，未有数据的插件正确返回状态；
- BN、missing evidence、coverage 和 provenance 可验证；
- CLI/test harness 可在无 UI 情况运行。

### Gate C：Desktop beta

- WinUI 自动管理 sidecar；
- session explorer、graph editor、revision、run、results 和 diagnostics 完整；
- contract/E2E/crash tests 通过；
- 安装、升级、卸载和项目保留策略验证。

### Gate D：Research release

- 专家确认产品边界和报告措辞；
- 至少有一个 expert_reviewed 或 calibrated model revision；
- 数据保护、脱敏、同意和保留策略获项目批准；
- 已知限制与 scientific status 随产品交付。

Research release 不自动意味着 operational certification。

## 7. 可追溯性要求

每次 AssessmentResult 必须能回答：

- 哪个 session 与 session revision；
- 哪个 published model revision 与 bundle hash；
- 使用了哪些 engine、plugin、algorithm 和 parameter version；
- 哪些原始文件、phase/event 和 source window 支撑每个 anchor；
- continuous value 如何转为 D/A/U；
- 哪些 evidence 缺失、无效或不适用；
- 每项 competency 的 coverage；
- 哪些 evidence 对 posterior 贡献最大；
- 谁在何时发布模型，经过哪些验证。

没有这些信息的结果不能称为可重现正式结果。

## 8. 产品交付包

建议交付结构：

~~~text
PilotAssessment/
  app/                         # signed Windows frontend
  runtime/                     # packaged Python sidecar
  models/reference-v0.1/       # read-only reference model bundle
  docs/product/                # 本设计文档中心
  samples/
    minimal-xu/
    synthetic-multimodal/
  schemas/
  licenses/
  THIRD_PARTY_NOTICES
  VERSION
  CHECKSUMS
  INSTALL.md
  USER_GUIDE.md
  RELEASE_NOTES.md
~~~

研究原始数据、身份映射、内部论文库和未获许可材料不进入通用交付包。

## 9. 接手清单

### 产品/项目负责人

- 阅读 01、DECISIONS 和本文件；
- 确认产品用途、用户群、数据责任和 scientific status；
- 指定模型发布审批人及数据保护责任人。

### 后端开发

- 阅读 02、03、04、05、06、07；
- 从 contract、schema 与 synthetic fixtures 开始；
- 不把 reference model 写死在 Python；
- 保持 BN engine adapter 可替换。

### 前端开发

- 阅读 06、07、08；
- 以 fake backend 建 UI，再执行 .NET/Python contract tests；
- 始终以 canonical graph 和 version 为准。

### 领域专家

- 从 04 和 05 开始；
- 在产品中修改参数、mapping、edge 和 CPT；
- 每次发布填写理由、依据和适用范围；
- 不需要修改源代码。

### 测试/审查人员

- 使用本文件的验证矩阵和发布 Gate；
- 复核原始 evidence trace，而不是只看 UI 截图；
- 分开签署 software verification 与 scientific validation。

## 10. 文档自审流程

每次设计版本变更至少执行：

1. 列出所有 Markdown 文件并验证相对链接；
2. 搜索旧口径：H6、19 anchors、O2 旧名称、FastAPI required、topology read-only；
3. 核对 18 anchors、11 sub-skills、4 competencies 和共享 evidence mapping；
4. 核对 I(t)/G(t)、EEG/ECG 和模态状态语义；
5. 核对 frontend、runtime 与 backend 方法名；
6. 核对新增/删除 edge 的 CPT migration；
7. 核对 missing evidence、coverage 和 validation status；
8. 由未参与起草的人进行一次独立审查；
9. 把发现、修复和遗留风险写入 10_DESIGN_SELF_REVIEW.md。

## 11. 当前已知风险

- reference anchor threshold 与多数 CPT 仍是工程默认，需专家和样本校准；
- EEG/ECG、VR/gaze 的实际导出格式尚未冻结；
- reference trajectory、phase/event annotation 的生产方式需与实验团队确认；
- shared-evidence 多 parent CPT 会指数增长；v0.1 已设 parent/row/cell/size 硬上限，但数值仍需性能基准和专家审查后才能提高；
- WinUI 图编辑控件选型和无障碍支持需原型验证；
- 后端 M1/M2 已有合同、directory-bundle loader、JSON Schema、版本化 adapters、deterministic multimodal software fixtures、`IngestionReadinessReport` 和自动化测试；M3 native-rate synchronization 规格与实施计划已批准但代码尚未实现，18 个 AnchorPlugin、BN、runtime 与 WinUI 也尚未实现。因此完整产品 software verification 仍为 in_progress，Gate B 尚未通过。
