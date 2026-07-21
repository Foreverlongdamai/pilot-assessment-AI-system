# M8B-2 Implementation Plan Self-Review

| 字段 | 值 |
|---|---|
| Review ID | M8B2-PLAN-SELF-REVIEW-2026-07-21 |
| 日期 | 2026-07-21 |
| Artifact | `plans/2026-07-21-m8b2-python-operator-extension-handoff-implementation-plan.md` |
| Reviewer | 主代理 inline self-review |
| 结论 | **通过；M8B-1 完成后可实施** |

## 1. 覆盖性结论

计划形成了用户要求的真实源码自由度：发布包暴露 Python 源码；普通参数和网络关系仍由前端保存；只有新增底层计算机制时才编辑 Python、注册并重启。它没有引入第二套产品、插件市场或人工发布流程。

## 2. 关键边界复核

- operator 不进入主 DAG 画布；它通过 EvidenceRecipe 被 Evidence 节点引用；
- 新 operator 不要求为每个算法手写 C# 页面，参数界面由 schema 驱动；
- extension entry point 是显式普通源码，不隐藏在 build-time generator；
- demo 只存在于开发模板和 disposable verification copy；
- starter/Hover 不自动启用 demo，不声称其科学有效；
- 依赖工具使用 bundled private runtime，不污染用户全局 Python；
- M8B-1 会自动把源码、依赖和 operator catalog 变化写入新 run identity。

## 3. 主要风险与控制

| 风险 | 控制 |
|---|---|
| 扩展入口变成另一套 plugin framework | 只提供普通 package、显式 import/register function |
| 前端对每个 operator 产生专用代码 | 强制使用 catalog parameter schema 的通用表单 |
| 示例污染基础模型 | 仅在 developer example/disposable copy 创建，验证 starter hash 不变 |
| 用户误以为改参数也要改源码 | 文档首屏给出“前端修改 / Python 修改”决策表 |
| 全局依赖环境不可迁移 | dependency tool 始终定位 release 内 private Python/uv |

未发现开放 P0/P1 计划问题。

