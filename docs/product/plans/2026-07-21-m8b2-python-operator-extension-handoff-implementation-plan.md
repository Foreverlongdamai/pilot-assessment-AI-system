# M8B-2 Python Operator Extension Handoff Implementation Plan

> **执行方式：INLINE。** 本计划证明解压后的同一套软件可以直接修改暴露的 Python 源码、增加一个新 operator、重启并由通用前端配置/执行；不引入插件市场、审批流、另一个产品或专家科学校准。

| 字段 | 值 |
|---|---|
| 里程碑 | M8B-2 — Editable Python Operator Extension Handoff |
| 日期 | 2026-07-21 |
| 状态 | **已由 2026-07-21 用户持续实施指令批准；等待 M8B-1 后实施** |
| 设计依据 | [M8B System-Owned Model Library and Editable Backend Provenance Design](../specs/2026-07-21-m8b-system-owned-model-library-and-editable-backend-provenance-design.md) §14–§18 |
| 上游 | M8B-1 Backend Source Provenance |
| 下游 | M8C Documentation System |

## 1. 完成标准

1. portable package 明确暴露一方 Python package、operator contracts、registry、built-ins、schema/compiler 与 examples；
2. 专家开发者可在解压目录内增加实现、`OperatorDefinition` 与注册语句，重启 app 后 catalog 立即出现；
3. 通用节点详情表单由 operator parameter schema 驱动，不为示例 operator 写专用 C# 页面；
4. 一个最小 extension operator 在 disposable release copy 内完成“新增源码 → 注册 → 重启 → catalog → recipe → 微型 run”闭环；
5. demo 不进入 starter/Hover system model library，不冒充科学有效 evidence；
6. 提供使用 bundled private Python 的依赖查看/安装/同步工具；依赖修改纳入 M8B-1 identity；
7. 文档清楚区分：改参数/关系/CPT 用前端，只有新计算机制才改 Python；
8. 不要求发布 operator version、审核或运行完整测试套件才能修改。

## 2. 实施任务

### Task 1 — 固定普通源码扩展入口

**文件**

- 新增：`src/pilot_assessment/evidence/extensions/__init__.py`
- 修改：`src/pilot_assessment/evidence/builtins/__init__.py` 或 composition root 注册入口
- 修改：`src/pilot_assessment/runtime/system_application.py`
- 新增：`tests/evidence/test_extension_registration.py`

**动作**

- [ ] 提供显式、可读、普通 Python 的 `register_extension_operators(registry)`；
- [ ] 注册顺序确定且 duplicate ID 返回清晰错误；
- [ ] 不使用动态下载、入口点市场、签名审批或隐藏生成代码；
- [ ] extension operator 与 built-in 使用同一合同、compiler 和 runtime。

### Task 2 — 暴露最小模板与依赖工具

**文件**

- 新增：`developer/examples/operator-extension/` 模板与说明
- 新增/修改：`tools/developer/manage_python_dependencies.ps1`
- 修改：`tools/release/build_portable.py`
- 修改：portable developer README

**动作**

- [ ] 模板包含 operator function、typed definition、parameter JSON schema、registration diff 和最小测试；
- [ ] 提供 `list`、`add`、`remove`、`sync` 操作，始终调用 release 内 private Python/uv；
- [ ] 不依赖全局 Python、全局 PATH 或 Visual Studio；
- [ ] tool 修改 `pyproject.toml`/`uv.lock` 后提示重启，source provenance 自动记录新依赖 identity。

### Task 3 — 确认通用前端 schema 闭环

**文件**

- 修改：必要的 operator RPC/C# contracts、节点详情 ViewModel/XAML
- 修改：中英文资源与 focused UI tests

**动作**

- [ ] operator catalog 返回 display name、description、input/output contract 和 parameter schema；
- [ ] 节点详情从 schema 生成可编辑参数，不增加 operator-specific switch；
- [ ] 保存仍写 system model library 的 EvidenceRecipe；
- [ ] operator 只出现在 operator 菜单和节点详情，不作为主画布节点。

### Task 4 — Disposable release-copy 扩展闭环

**文件**

- 修改：`tools/release/verify_portable.py`
- 新增：专用 minimal operator extension fixture（只复制到临时 release）

**动作**

- [ ] 复制正式 release 到临时目录；
- [ ] 按开发文档增加一个无科学含义的 arithmetic operator 并注册；
- [ ] 验证未重启旧 sidecar 报 restart-required；
- [ ] 重启后 catalog 出现新 ID，parameter schema 可读取；
- [ ] 创建非 starter 的临时 EvidenceRecipe，用微型 Session 得到确定结果；
- [ ] 新 run 保存新的 backend identity/source snapshot，正式 release 与 starter model 不被修改。

### Task 5 — 开发交接文档与 M8B 收口

**文件**

- 新增：`docs/product/manuals/python-operator-extension-development.md`
- 修改：`docs/product/release/README-DEVELOPMENT.md`
- 新增：`docs/product/reviews/2026-07-21-m8b2-python-operator-extension-verification.md`
- 修改：根 README、产品 README、实施状态、M8 大纲

**动作**

- [ ] 用实际文件、命令和故障信息写完整步骤；
- [ ] 说明前端模型编辑与 Python 机制开发的边界；
- [ ] 说明备份、重启、identity 与历史 run 不变性；
- [ ] 重建 clean ZIP，记录 SHA-256、focused tests、x64 build 和外部 release-copy 结果；
- [ ] M8B-0/1/2 全部满足后才把 M8B 标为 complete，随后进入 M8C。

## 3. 自审不变量

- 新 operator 是普通 Python 源码修改，不需要 plugin version 或发布 ceremony；
- 参数、阈值、父节点、边、CPT 与任务启用关系继续由前端修改；
- 一个 operator 可被多个 EvidenceRecipe 复用，operator 本身不成为 BN/DAG 主画布节点；
- 示例只证明工程扩展性，不进入基础 Hover 方案，也不代表推荐科学算法；
- 打包系统仍不携带任何用户 project/session/result。

