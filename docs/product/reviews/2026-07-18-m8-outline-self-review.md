# M8 Pre-UAT Outline Self-Review

| 字段 | 值 |
|---|---|
| 日期 | 2026-07-18 |
| 审查对象 | M8 candidate design outline + pre-UAT implementation outline |
| 审查类型 | 文档边界、产品一致性、范围和可执行性自审 |
| 结论 | **可作为 pre-UAT 候选大纲保存；不可批准或执行** |

## 1. 审查对象

- [M8 Productization, Editable Python Source, Documentation and Handoff Design Outline](../specs/2026-07-18-m8-productization-editable-python-documentation-and-handoff-outline.md)
- [M8 Pre-UAT Implementation Outline](../plans/2026-07-18-m8-pre-uat-implementation-outline.md)
- 当前 M7 规格、路线图、产品 README、实施状态和 D-031–D-053。

## 2. 结论摘要

本轮 M8 文档满足用户最新限制：只制定大纲，不实施。它覆盖便携分发、发布包中直接可编辑的完整 Python backend、分类文档/DOCX、项目迁移/诊断和最终交付验收，但没有写入产品代码、正式 D-编号或逐文件执行任务。

M8 的硬 Gate 0 已明确为“M7 用户手工验收 + 必要返修收口”。因此当前 M7 可以继续保留 engineering verified 的客观事实，同时不能再被表述为已完成用户验收或最终产品验收。

## 3. 产品核心一致性检查

| 检查项 | 结果 | 说明 |
|---|---|---|
| 三类节点、两类边 | 通过 | 保留 Raw Input/Evidence/BN 与 extraction/probabilistic edge 区分 |
| 全局完整节点 + TaskScheme 激活 | 通过 | M8 不重新引入同节点 task-specific version slot |
| 节点定义完整固定 parents | 通过 | 新任务差异仍通过复制/新建完整节点表达 |
| canonical BN 方向 | 通过 | 保留 Competency → Sub-skill → Evidence；posterior overlay 不反转存储边 |
| 前端自由修改与 Python canonical state | 通过 | “Python 负责计算”未被写成“Python 决定科学内容” |
| 普通编辑无需 Python | 通过 | recipe/parameter/node/parents/states/CPT/task 修改继续通过前端提交 backend canonical state |
| 新计算机制可扩展 | 通过 | 仅现有方法无法达到目标时直接修改唯一活动 Python source tree；不要求 plugin package |
| 单一系统全局语义 | 通过 | 源码修改作用于当前解压软件副本的全部项目和 future runs；无 project source overlay |
| 历史 replay | 通过 | source/operator/runtime identity 和 content-addressed source snapshot 进入 RunSnapshot/artifact |
| 用户数据与产品包分离 | 通过 | session/project/result 明确禁止进入通用发布包 |
| 科学校准边界 | 通过 | M8 completion 不含专家 calibration，`formal_run_authorized=false` 保留 |
| 无网络端口 | 通过 | 继续使用 supervised stdio sidecar，不引入 HTTP 服务 |
| 轻量验证 | 通过 | 只要求 platform vertical slices，不要求 starter scientific golden |

## 4. M7/M8 状态边界检查

发现当前文档中心和 root README 把“M7 engineering exit gate closed”简写为“完整 M7 已完成”，容易让人误解为用户已经亲自验收。该事实不否定现有 84/84 Unit、4/4 Contract、build 和 visible run 证据，但需要补充以下口径：

- M7 engineering verified；
- M7 user acceptance pending；
- 用户验收可能产生 M7 返修；
- M8 当前只有 pre-UAT outline；
- M8A–M8E 未批准、未实施。

本轮只更新状态与索引，不改写 M7 历史代码/测试证据，也不把预期返修伪造成已发现缺陷。

## 5. 规范和方法使用比例检查

### 5.1 ISO/IEC/IEEE 26514:2022

官方摘要说明该标准面向软件用户信息的结构、内容、格式及其开发维护过程。本大纲只采用“从用户和任务出发、定义信息结构和维护状态”这些高层原则，没有复制付费标准正文，也没有声称合规或认证。

结果：**使用适量**。

### 5.2 ISO/IEC/IEEE 42010:2022

官方摘要强调 architecture description、关注者、关注点、viewpoint 和 model kind，而不是规定具体架构方法或记录格式。本大纲只用它提醒文档说明角色、关注点和不同架构视图，没有建立繁重的 architecture framework。

结果：**使用适量**。

### 5.3 Diátaxis

官方框架区分 tutorials、how-to guides、reference 和 explanation。本大纲把十二类手册映射到这些用途，并要求章节目的明确；没有为了框架而把每份手册机械拆成四份。

结果：**使用适量，项目任务优先**。

### 5.4 C4

C4 官方说明 context/container 通常已经足够，component 图只在确有价值时使用。本大纲只提供 context 和 container 候选图，并把 live-source/release component 图延后到正式子规格。

结果：**使用适量，未过度绘图**。

官方入口：

- [ISO/IEC/IEEE 26514:2022](https://www.iso.org/standard/77451.html)
- [ISO/IEC/IEEE 42010:2022](https://www.iso.org/standard/74393.html)
- [Diátaxis](https://diataxis.fr/)
- [C4 diagrams](https://c4model.com/diagrams)

## 6. 完整性检查

| M8 必须覆盖的主题 | 覆盖位置 |
|---|---|
| M7 用户验收前置门 | 设计 §4；路线图 §3 |
| 解压即用 Windows 交付 | 设计 §7；路线图 §4 |
| 私有 Python/backend runtime | 设计 §7；路线图 M8A |
| 打包后直接修改 Python/new operator | 设计 §8；路线图 M8B |
| 前端正常参数/Evidence/BN 自由修改 | 设计 §8.1；路线图 §5.2/§5.4 |
| 源码修改全局作用范围 | 设计 §8.2；路线图 §5.2/§5.5 |
| 源码 identity 与历史 snapshot | 设计 §8.7；路线图 §5.3/§5.7 |
| 十二类文档 | 设计 §9.4；路线图 M8C |
| Markdown → versioned DOCX | 设计 §9；路线图 M8C |
| C4/Diátaxis/标准轻量应用 | 设计 §6/§9.2；路线图 §6.4 |
| 项目备份、恢复和迁移 | 设计 §10；路线图 M8D |
| 脱敏诊断包 | 设计 §10.3；路线图 M8D |
| clean-machine 验收 | 设计 §11；路线图 M8E |
| SBOM/checksum/licenses/source identity | 设计 §11；路线图 M8E |
| 用户数据不随系统打包 | 设计 §7.3；路线图 M8A/M8E |
| 科学校准明确排除 | 设计 §3/§14；路线图各 exit gate |

结果：**大纲覆盖完整**。

## 7. 非实施边界检查

检查结果：

- 没有修改 `src/`、`tests/`、`schemas/` 或 C# project；
- 没有安装或锁定新的工具；
- 没有生成 ZIP、DOCX、live-source release layout 或 backup；
- 没有新增 D-编号；
- 没有把候选 runtime 版本写成正式版本；
- 没有把工作流表述为已经完成；
- 路线图标题、metadata、开头指令和停止点均标明不可执行。

结果：**通过**。

## 8. 当前保留风险

这些风险不能在 M7 用户验收前合理关闭：

1. M7 真实操作反馈可能改变截图、字段、窗口和帮助入口；
2. 便携 Python/runtime 的精确版本和依赖兼容尚未冻结；
3. production sidecar 如何只从 live source tree 导入、同时隔离第三方 runtime，尚未冻结；
4. source baseline/hash/modified summary/content-addressed snapshot 的精确合同尚未冻结；
5. 随包依赖管理工具和专家增加第三方依赖的精确命令尚未冻结；
6. 项目 backup schema、容量边界和 migration policy 尚未冻结；
7. 中英文全部手册的工作量与最终翻译复核方式尚未确认；
8. clean-machine 测试环境和支持的 Windows build 尚未冻结；
9. 是否随产品附带极小无身份教学 bundle 尚未确认。

这些都是正式 M8A–M8E 规格的输入，不是当前大纲的遗漏。

## 9. 自审后的处理建议

1. 保存本候选规格、大纲和自审；
2. 更新文档索引和实施状态，使 M7 user acceptance pending、M8 outline-only 清楚可见；
3. 不写 `DECISIONS.md`；
4. 不开始 M8A；
5. 等用户完成 M7 手工使用和返修后，再逐项确认 C-M8-01–C-M8-08；
6. 批准后按 M8A–M8E 分别编写正式规格和可执行计划。
