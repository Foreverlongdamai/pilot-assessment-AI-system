# Pilot Assessment System

本目录是 “Development of AI-Based System for Evaluating eVTOL Pilot Training Effectiveness” 项目的产品化工作区。系统目标是把多模态飞行训练 session 转换为可追溯的证据锚点，并通过可编辑的贝叶斯网络输出飞行员能力后验分布。

当前状态：**产品设计基线 v0.1 已建立；后端 M1/M2 已实现并通过软件检查；M3 native-rate synchronization 的规格、D-016–D-020 和实施计划已批准，但同步代码尚未实现。18 个 anchor、BN、runtime 和 WinUI 也尚未实现。科学状态仍为 `engineering_default`。**

## 从这里开始

- 产品设计文档中心：[docs/product/README.md](docs/product/README.md)
- 当前实现状态与验证命令：[docs/product/11_IMPLEMENTATION_STATUS.md](docs/product/11_IMPLEMENTATION_STATUS.md)
- 后端 M1 实施计划：[docs/product/plans/2026-07-11-backend-foundation-m1-implementation-plan.md](docs/product/plans/2026-07-11-backend-foundation-m1-implementation-plan.md)
- M3 Native-Rate Time Synchronization 规格：[docs/product/specs/2026-07-12-m3-native-time-synchronization-design.md](docs/product/specs/2026-07-12-m3-native-time-synchronization-design.md)
- M3 实施计划：[docs/product/plans/2026-07-12-m3-native-time-synchronization-implementation-plan.md](docs/product/plans/2026-07-12-m3-native-time-synchronization-implementation-plan.md)
- 当前设计决策：[docs/product/DECISIONS.md](docs/product/DECISIONS.md)
- 术语表：[docs/product/GLOSSARY.md](docs/product/GLOSSARY.md)
- 历史后端草案：[docs/superpowers/specs/2026-07-08-backend-core-runtime-adapter-design.md](docs/superpowers/specs/2026-07-08-backend-core-runtime-adapter-design.md)（仅保留追溯，不再是实现依据）

## 目录边界

后续前端、后端、模型资源、测试、示例 session 和安装资源均应放在本目录内。项目根目录中的研究论文、实验数据和讨论材料可以作为输入来源，但不应成为产品运行时的隐式依赖。

当前实现目录：

```text
src/pilot_assessment/     # Python Core（当前为 contracts、ingestion、schema export）
tests/                    # unit、contract 与 directory-bundle integrity tests
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
uv run ty check
uv build
```

上述命令验证当前已实现的 M1/M2 软件合同与构建；M3 synchronization 代码、完整 anchor/BN pipeline 和 Windows 应用仍未完成，因此不代表完整评估系统已经可以运行。

## 当前产品方向

- Windows 原生前端：WinUI 3。
- 本地后端：Python Assessment Core。
- 进程桥接：JSON-RPC 2.0 / JSONL over stdin/stdout。
- 数据方式：session bundle 文件路径、manifest 与校验和；视频和生理信号不进入 JSON 消息。
- 模型方式：18 个参考 evidence nodes、11 个 latent sub-skills、4 个 aggregate competencies。
- 编辑方式：前端可拖拽新增、删除、移动节点和边；后端负责验证、CPT 迁移、版本化和持久化。

## 重要边界

默认 anchor 算法、阈值、子技能映射和 CPT 是工程参考值，不是航空认证标准。产品必须允许领域专家在有审计和版本控制的前提下修改这些内容。
