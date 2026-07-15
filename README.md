# Pilot Assessment System

本目录是 “Development of AI-Based System for Evaluating eVTOL Pilot Training Effectiveness” 项目的产品化工作区。系统目标是把多模态飞行训练 session 转换为可追溯的证据锚点，并通过可编辑的贝叶斯网络输出飞行员能力后验分布。

当前状态：**产品已于 2026-07-15 重基线为面向领域专家的可视化评估模型设计系统。M1/M2/M3 与 M4R Evidence Computation Foundation 已工程验证；旧 M4 Task 0–28 的 O1–O12/H1–H3 whole-Anchor plugins、共享 primitives 与三个 preprocessing providers 保留为迁移和历史重放来源，旧 Task 29–36 已停止。M4R 已实现 canonical `EvidenceRecipe`、typed operator graph、自动表单 metadata、only-technical validation、generic compiler/executor、backend-only draft/preview/apply/replay 和 18 个可编辑 starter resources；普通新增/修改 Anchor 和计算方法不需要 Python 发布、审批或逐次工程测试。M5 BN/model workspace、M6 runtime、M7 WinUI 与 M8 packaging 尚未完成，完整产品仍为 `in_progress`，`formal_run_authorized=false`。当前 18 个 Anchor 和 33-node BN 仅是 starter templates，不构成科学有效性声明。**

## 从这里开始

- 产品设计文档中心：[docs/product/README.md](docs/product/README.md)
- 当前实现状态与验证命令：[docs/product/11_IMPLEMENTATION_STATUS.md](docs/product/11_IMPLEMENTATION_STATUS.md)
- 当前专家可编辑架构规格：[docs/product/specs/2026-07-15-expert-editable-evidence-and-model-design.md](docs/product/specs/2026-07-15-expert-editable-evidence-and-model-design.md)
- M4R 已完成实施计划：[docs/product/plans/2026-07-15-m4r-editable-evidence-computation-foundation-implementation-plan.md](docs/product/plans/2026-07-15-m4r-editable-evidence-computation-foundation-implementation-plan.md)
- 后端 M1 实施计划：[docs/product/plans/2026-07-11-backend-foundation-m1-implementation-plan.md](docs/product/plans/2026-07-11-backend-foundation-m1-implementation-plan.md)
- M3 Native-Rate Time Synchronization 规格：[docs/product/specs/2026-07-12-m3-native-time-synchronization-design.md](docs/product/specs/2026-07-12-m3-native-time-synchronization-design.md)
- M3 实施计划：[docs/product/plans/2026-07-12-m3-native-time-synchronization-implementation-plan.md](docs/product/plans/2026-07-12-m3-native-time-synchronization-implementation-plan.md)
- M4 Anchor Calculation and Evidence Availability 规格：[docs/product/specs/2026-07-13-m4-anchor-evidence-availability-design.md](docs/product/specs/2026-07-13-m4-anchor-evidence-availability-design.md)（历史/迁移规格；当前权威已转移）
- M4 原实施计划：[docs/product/plans/2026-07-13-m4-anchor-evidence-availability-implementation-plan.md](docs/product/plans/2026-07-13-m4-anchor-evidence-availability-implementation-plan.md)（历史上已批准，现已被取代且不得执行）
- M4 轻量工作流验证修订：[docs/product/specs/2026-07-13-m4-lightweight-workflow-validation-amendment.md](docs/product/specs/2026-07-13-m4-lightweight-workflow-validation-amendment.md)（历史 fixed-plugin 验证修订）
- M4 Task 3 Reference Candidate Binding 修订：[docs/product/specs/2026-07-13-m4-task3-reference-candidate-binding-amendment.md](docs/product/specs/2026-07-13-m4-task3-reference-candidate-binding-amendment.md)（已于 2026-07-13 批准；D-028）
- M4 Task 7 Catalog and Resource Identity 修订：[docs/product/specs/2026-07-13-m4-task7-catalog-resource-identity-amendment.md](docs/product/specs/2026-07-13-m4-task7-catalog-resource-identity-amendment.md)（已按授权默认批准；D-029）
- M4 Task 8 Canonical Fingerprint and Runtime Identity 修订：[docs/product/specs/2026-07-13-m4-task8-canonical-fingerprint-runtime-identity-amendment.md](docs/product/specs/2026-07-13-m4-task8-canonical-fingerprint-runtime-identity-amendment.md)（已按授权默认批准；D-030）
- M4 replacement 实施计划：[docs/product/plans/2026-07-13-m4-anchor-evidence-availability-replacement-implementation-plan.md](docs/product/plans/2026-07-13-m4-anchor-evidence-availability-replacement-implementation-plan.md)（Task 0–28 的历史记录；Task 29–36 已暂停且不得继续执行）
- 当前设计决策：[docs/product/DECISIONS.md](docs/product/DECISIONS.md)
- 术语表：[docs/product/GLOSSARY.md](docs/product/GLOSSARY.md)
- 历史后端草案：[docs/superpowers/specs/2026-07-08-backend-core-runtime-adapter-design.md](docs/superpowers/specs/2026-07-08-backend-core-runtime-adapter-design.md)（仅保留追溯，不再是实现依据）

## 目录边界

后续前端、后端、模型资源、测试、示例 session 和安装资源均应放在本目录内。项目根目录中的研究论文、实验数据和讨论材料可以作为输入来源，但不应成为产品运行时的隐式依赖。

当前实现目录：

```text
src/pilot_assessment/     # Python Core（contracts、ingestion、synchronization、legacy anchors、editable evidence、schema export）
tests/                    # unit、contract、bundle integrity、synchronization 与 E2E tests
schemas/                  # 确定性生成的跨语言 JSON Schema
docs/product/             # 正式产品、实现和交付文档
```

## 开发验证

安装 [uv](https://docs.astral.sh/uv/) 后，在本目录运行：

```powershell
uv sync --all-groups
uv run python -m pilot_assessment.schemas.export
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run ty check src
uv build
```

2026-07-12 的 M3 完成门实测为 `694 passed, 2 skipped`；两个 skip 仅对应未显式提供 repository-external CSV 的 M2/M3 opt-in 格式样例测试。配置该 CSV 后，两条格式样例 E2E 为 `2 passed`。Schema regeneration、Ruff format/lint、`ty check src`、build、tracked raw-data scan 和隔离 wheel smoke 也均通过。详细数字、golden counts 与 wheel 证据见 [Implementation Status](docs/product/11_IMPLEMENTATION_STATUS.md)。

2026-07-15 的 M4R fresh gate 为 `1472 passed, 3 skipped`；新增的第三个 skip 是当前 Windows 主机不允许测试 symlink。Ruff lint/format、ty、schema regeneration 与 PEP 517 wheel build 通过；wheel 内含全部 18 个 starter recipes、catalog 和 EvidenceRecipe/OperatorDefinition schemas。M4R focused tests 只使用极小内存 fixture，不生成重型 session 资产。

这些结果只验证相应的软件合同和运行路径。格式样例是一次随意飞行记录，只用于格式、接口和时间路径；结果不证明轨迹、任务、表现、生理指标、Anchor 或飞行员能力有效。旧 M4 Task 0–28 的测试数字继续作为当时代码的历史工程证据，但不再充当 M4R 的完成门，也不要求专家后续修改维持这些 provisional 算法的输出等价。现有十五个 whole-Anchor capabilities 与三个 preprocessing providers 均保留；M4R 采用小型平台不变量测试、代表 operator/recipe smoke 和一个极轻 E2E 完成工程验证，所有路径保持 `formal_run_authorized=false`。

## 当前产品方向

- Windows 原生前端：WinUI 3。
- 本地后端：Python Assessment Core。
- 进程桥接：JSON-RPC 2.0 / JSONL over stdin/stdout。
- 数据方式：session bundle 文件路径、manifest 与校验和；视频和生理信号不进入 JSON 消息。
- 模型方式：Evidence Computation Graph 把多模态数据变成 evidence；与之联动的 BN Graph 把 evidence 连接到 sub-skill/competency。18/11/4 只是初始模板，不是通用引擎的数量限制。
- 编辑方式：前端可拖拽新增、删除、复制、停用、移动节点和边，并通过自动生成的表单修改输入、窗口、算子参数、公式、聚合、scorer 和 CPT；后端保存并执行同一个 canonical `EvidenceRecipe`/BN draft。
- 版本方式：普通修改自动保存为可恢复 draft；点击“应用到后续评估”后创建 immutable revision。只做 schema、引用、DAG、类型/单位、公式可编译和 CPT 可执行等最小技术校验，不做科学审批。
- 扩展方式：普通新 Anchor 使用已有 operators，不需要 Python；只有算子库缺少全新计算能力时才增加 trusted operator plugin。
- M4 计算边界：进入 M4 的 aligned input 假定已满足 M1–M3 结构合同；M4 不设置原始数据质量门。极差轨迹、剧烈控制、极端生理指标、未响应、未恢复或未注视都按规则形成 D/A/U，而不是被过滤。
- Evidence availability：`computed + Unacceptable` 是有效负面 evidence，raw availability=1；M4 不生成 `invalid_quality`，coverage/availability 不代表表现好坏。

## 重要边界

默认 Anchor 算法、阈值、子技能映射和 CPT 是可删除、可替换的 starter templates，不是航空认证标准。审计与版本记录由系统在后台自动完成，不能演变为专家修改前的审批或测试负担。

当前 `anchor-result-0.1.0` 合同属于 M1 legacy foundation，不是 M4 AnchorResult v0.2 的已实现版本。M4 书面规格、后续实施计划、代码实现和工程验证必须分别报告。
