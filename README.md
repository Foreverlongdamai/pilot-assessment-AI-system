# Pilot Assessment System

本目录是 “Development of AI-Based System for Evaluating eVTOL Pilot Training Effectiveness” 项目的产品化工作区。系统目标是把多模态飞行训练 session 转换为可追溯的证据锚点，并通过可编辑的贝叶斯网络输出飞行员能力后验分布。

当前状态：**产品设计基线 v0.1 已建立；后端 M1/M2/M3 已实现并通过工程完成门。M3 只完成 native-rate 时间对齐，不包含插值、重采样或 anchor window grid。M4 的 O1–O13、H1–H5 主规格、轻量、Task 3/7/8 定向修订与 replacement 实施计划均已于 2026-07-13 获明确或授权默认批准，D-026–D-030 已接受；原四套 90 秒 fixture 实施计划已被取代且不再授权执行。Replacement Task 0–28 已完成，M4-A/M4-B framework、M4-C/M4-D/M4-E stage gates、O1–O12、H1–H3、共享 primitives 与三个 reference preprocessing providers 已进入生产代码和可信注册表，相关 capability 均为 `available`。真实状态为 18/18 specified、15/18 production plugins 已实现、M4-C/M4-D/M4-E software-verified；下一步是 Task 29 H4，M4 整体尚未 engineering verified，`formal_run_authorized=false`。完整产品仍为 `in_progress`，Gate B 尚未通过；其余 H4/H5/O13 三个 AnchorPlugin、BN、runtime 和 WinUI 仍未实现。参考评估模型的科学状态仍为 `engineering_default`，synthetic fixture 为 `not_supported`；现有软件测试不构成科学有效性声明。**

## 从这里开始

- 产品设计文档中心：[docs/product/README.md](docs/product/README.md)
- 当前实现状态与验证命令：[docs/product/11_IMPLEMENTATION_STATUS.md](docs/product/11_IMPLEMENTATION_STATUS.md)
- 后端 M1 实施计划：[docs/product/plans/2026-07-11-backend-foundation-m1-implementation-plan.md](docs/product/plans/2026-07-11-backend-foundation-m1-implementation-plan.md)
- M3 Native-Rate Time Synchronization 规格：[docs/product/specs/2026-07-12-m3-native-time-synchronization-design.md](docs/product/specs/2026-07-12-m3-native-time-synchronization-design.md)
- M3 实施计划：[docs/product/plans/2026-07-12-m3-native-time-synchronization-implementation-plan.md](docs/product/plans/2026-07-12-m3-native-time-synchronization-implementation-plan.md)
- M4 Anchor Calculation and Evidence Availability 规格：[docs/product/specs/2026-07-13-m4-anchor-evidence-availability-design.md](docs/product/specs/2026-07-13-m4-anchor-evidence-availability-design.md)（已批准）
- M4 原实施计划：[docs/product/plans/2026-07-13-m4-anchor-evidence-availability-implementation-plan.md](docs/product/plans/2026-07-13-m4-anchor-evidence-availability-implementation-plan.md)（历史上已批准，现已被取代且不得执行）
- M4 轻量工作流验证修订：[docs/product/specs/2026-07-13-m4-lightweight-workflow-validation-amendment.md](docs/product/specs/2026-07-13-m4-lightweight-workflow-validation-amendment.md)（已批准）
- M4 Task 3 Reference Candidate Binding 修订：[docs/product/specs/2026-07-13-m4-task3-reference-candidate-binding-amendment.md](docs/product/specs/2026-07-13-m4-task3-reference-candidate-binding-amendment.md)（已于 2026-07-13 批准；D-028）
- M4 Task 7 Catalog and Resource Identity 修订：[docs/product/specs/2026-07-13-m4-task7-catalog-resource-identity-amendment.md](docs/product/specs/2026-07-13-m4-task7-catalog-resource-identity-amendment.md)（已按授权默认批准；D-029）
- M4 Task 8 Canonical Fingerprint and Runtime Identity 修订：[docs/product/specs/2026-07-13-m4-task8-canonical-fingerprint-runtime-identity-amendment.md](docs/product/specs/2026-07-13-m4-task8-canonical-fingerprint-runtime-identity-amendment.md)（已按授权默认批准；D-030）
- M4 replacement 实施计划：[docs/product/plans/2026-07-13-m4-anchor-evidence-availability-replacement-implementation-plan.md](docs/product/plans/2026-07-13-m4-anchor-evidence-availability-replacement-implementation-plan.md)（已于 2026-07-13 批准并按方案 A 修订；Task 0–28 已完成，M4-C/M4-D/M4-E 已关闭，下一步为 Task 29 H4）
- 当前设计决策：[docs/product/DECISIONS.md](docs/product/DECISIONS.md)
- 术语表：[docs/product/GLOSSARY.md](docs/product/GLOSSARY.md)
- 历史后端草案：[docs/superpowers/specs/2026-07-08-backend-core-runtime-adapter-design.md](docs/superpowers/specs/2026-07-08-backend-core-runtime-adapter-design.md)（仅保留追溯，不再是实现依据）

## 目录边界

后续前端、后端、模型资源、测试、示例 session 和安装资源均应放在本目录内。项目根目录中的研究论文、实验数据和讨论材料可以作为输入来源，但不应成为产品运行时的隐式依赖。

当前实现目录：

```text
src/pilot_assessment/     # Python Core（contracts、ingestion、synchronization、M4 binding/catalog/request、schema export）
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

这些结果只验证相应的软件合同和运行路径。格式样例是一次随意飞行记录，只用于格式、接口和时间路径；结果不证明轨迹、任务、表现、生理指标、anchor 或飞行员能力有效。M4 replacement Task 0–28 已完成；Task 28 H3 focused/M4-E 受控 gates 分别为 `12 passed`、`244 passed`，registry verify、Ruff/format、ty/diff gates 均通过；最新 full-repository、build 与 isolated-wheel stage 证据仍是 Task 20 的 `1275 passed, 3 skipped` 及其完成门。O1–O12/H1–H3 是当前仅有的十五个 production capabilities，三个 reference preprocessing providers 均已 `available`；真实计数为 18/18 specified、15/18 production plugins、M4-C/M4-D/M4-E software-verified；M4 整体仍未 engineering verified，所有路径保持 `formal_run_authorized=false`，也不构成科学有效性证明。

## 当前产品方向

- Windows 原生前端：WinUI 3。
- 本地后端：Python Assessment Core。
- 进程桥接：JSON-RPC 2.0 / JSONL over stdin/stdout。
- 数据方式：session bundle 文件路径、manifest 与校验和；视频和生理信号不进入 JSON 消息。
- 模型方式：18 个参考 evidence nodes、11 个 latent sub-skills、4 个 aggregate competencies。
- 编辑方式：前端可拖拽新增、删除、移动节点和边；后端负责验证、CPT 迁移、版本化和持久化。
- M4 计算边界：进入 M4 的 aligned input 假定已满足 M1–M3 结构合同；M4 不设置原始数据质量门。极差轨迹、剧烈控制、极端生理指标、未响应、未恢复或未注视都按规则形成 D/A/U，而不是被过滤。
- Evidence availability：`computed + Unacceptable` 是有效负面 evidence，raw availability=1；M4 不生成 `invalid_quality`，coverage/availability 不代表表现好坏。

## 重要边界

默认 anchor 算法、阈值、子技能映射和 CPT 是工程参考值，不是航空认证标准。产品必须允许领域专家在有审计和版本控制的前提下修改这些内容。

当前 `anchor-result-0.1.0` 合同属于 M1 legacy foundation，不是 M4 AnchorResult v0.2 的已实现版本。M4 书面规格、后续实施计划、代码实现和工程验证必须分别报告。
