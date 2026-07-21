# M8B-0 System Model Ownership Implementation Plan

> **执行方式：INLINE。** 本计划只迁移模型 ownership，不验证 starter Evidence/BN/CPT 的科学正确性，也不引入重型多模态数据。

| 字段 | 值 |
|---|---|
| 里程碑 | M8B-0 — System-Owned Model Library |
| 日期 | 2026-07-21 |
| 状态 | **Approved for implementation** |
| 设计依据 | [M8B System-Owned Model Library and Editable Backend Provenance Design](../specs/2026-07-21-m8b-system-owned-model-library-and-editable-backend-provenance-design.md) |
| 上游 | M7 staged model editing；M8A portable engineering build |
| 停止边界 | 完成 system ownership、双项目共享、不可变运行快照和 portable rebuild；source provenance 与新 operator 闭环留给 M8B-1/M8B-2 |

## 1. 完成标准

M8B-0 完成时必须同时满足：

1. 每套开发/发布软件副本只有一个 `system/model-library.sqlite3` canonical 模型库；
2. `Model Studio` 在没有打开 project 时可读取和修改 ModelNode、TaskScheme、edge、CPT 和 layout；
3. Project 创建不复制或 seed 可编辑模型，Project A/B 看到同一 system 模型；
4. 关闭或切换 project 不关闭 system 模型库，也不丢失 system edit session；
5. run preflight 从 system 锁定 clean exact model closure，并把执行副本写入目标 project 的不可变 RunSnapshot/materialization；
6. system 模型随后改变，不会改变已有 run 的 snapshot、result 或 replay 语义；
7. 旧 project-local 模型只读保留，并可按确定性、幂等、无覆盖规则导入 system store；
8. 新 portable package 携带 starter-initialized `system/`，不携带用户 project/session/result；
9. 仅运行微型图、两个空 project 和最小 Session 的 focused tests/build/smoke。

## 2. 实施顺序

### Task 0 — 正式化决策与状态口径

**文件**

- 修改：`docs/product/DECISIONS.md`
- 修改：`docs/product/README.md`
- 修改：`docs/product/11_IMPLEMENTATION_STATUS.md`
- 修改：`docs/product/plans/2026-07-18-m8-pre-uat-implementation-outline.md`
- 修改：`docs/product/specs/2026-07-21-m8b-system-owned-model-library-and-editable-backend-provenance-design.md`
- 修改：`docs/product/reviews/2026-07-21-m8b-system-owned-model-library-design-self-review.md`

**动作**

- [ ] 写入 D-066–D-071：software-copy system owner、无 project Model Studio、project/run boundary、legacy import、single-writer、loaded-source identity 边界。
- [ ] 将 M8B 设计和自审状态从 review candidate 改为已批准。
- [ ] 更新路线图：M8B-0 先修正 ownership，M8B-1/2 再实现 source provenance/operator 扩展闭环。
- [ ] 明确 M8B-0 未完成前，M8A ZIP 仍是旧 project-scoped engineering build。

### Task 1 — 建立独立 System Model Store

**文件**

- 新增：`src/pilot_assessment/contracts/system.py`
- 新增：`src/pilot_assessment/persistence/system.py`
- 修改：`src/pilot_assessment/contracts/__init__.py`
- 修改：`src/pilot_assessment/persistence/__init__.py`
- 新增：`tests/contracts/test_system.py`
- 新增：`tests/persistence/test_system_store.py`

**动作**

- [ ] 定义 `SystemDescriptor`，只保存相对 `database_path`、`model_library_id`、format/product/seed identity 和创建时间。
- [ ] 实现 `SystemStore.create/open/open_or_create()`，固定目录为 `system.json`、`model-library.sqlite3`、`staging/model-edit/`。
- [ ] 复用 SQLite kernel/migrations，但 system service 不暴露 project/session/run 表。
- [ ] 校验目录可写、locator 不含绝对路径、descriptor/database metadata 一致。
- [ ] 用独占 lock file 保证同一软件副本只有一个 system writer；正常关闭释放，陈旧锁按进程身份安全恢复。

**轻量验证**

```powershell
.\.tools\uv\uv.exe run pytest tests/contracts/test_system.py tests/persistence/test_system_store.py -q
```

### Task 2 — 将 current-model 合同从 project scope 升为 model-library scope

**文件**

- 修改：`src/pilot_assessment/contracts/model_workspace.py`
- 修改：`src/pilot_assessment/model_workspace/hashing.py`
- 修改：`src/pilot_assessment/model_workspace/service.py`
- 修改：`src/pilot_assessment/model_workspace/edit_session.py`
- 修改：`src/pilot_assessment/model_workspace/execution.py`
- 修改：`src/PilotAssessment.Desktop.Core/Contracts/ModelWorkspaceRpcContracts.cs`
- 修改：`src/PilotAssessment.Desktop.Core/Contracts/PilotAssessmentJsonContext.cs`
- 修改相应 Python/C# tests

**动作**

- [ ] 发布 `ModelGraphSnapshot` v0.2：使用 `model_library_id`，不再把 project ID 写入 current graph identity。
- [ ] 发布 `ModelEditSessionStatus` v0.2：使用 `model_library_id`。
- [ ] `CurrentModelWorkspaceService`、edit session 和 semantic hash 全部使用 model-library scope。
- [ ] 保留旧 v0.1 RunSnapshot/历史 JSON 的兼容读取，不做字符串字段替换。
- [ ] 同步 C# source-generated contract，普通 UI 不显示 model library ID。

**轻量验证**

```powershell
.\.tools\uv\uv.exe run pytest tests/model_workspace -q
dotnet test tests/PilotAssessment.Desktop.UnitTests/PilotAssessment.Desktop.UnitTests.csproj -c Debug --filter "FullyQualifiedName~Contract"
```

### Task 3 — 引入 `SystemApplication` composition root

**文件**

- 新增：`src/pilot_assessment/runtime/system_application.py`
- 修改：`src/pilot_assessment/runtime/application.py`
- 修改：`src/pilot_assessment/sidecar/server.py`
- 修改：`src/pilot_assessment/sidecar/methods.py`
- 新增：`tests/runtime/test_system_application.py`
- 修改：`tests/sidecar/test_methods.py`
- 修改：`tests/sidecar/test_server_subprocess.py`

**动作**

- [ ] sidecar 启动即定位并打开 `SystemApplication`，无 project 也完成 starter seed。
- [ ] `SystemApplication` 独占 current model、model edit session、component/scheme compatibility services、operator/source registries与 system audit/idempotency。
- [ ] 所有 `model.*`、`operator.*` 与兼容 model-library RPC 路由到 system app。
- [ ] `runtime.status` 分别返回 `system_ready` 与 `project_open`；关闭 project 不关闭 system app。
- [ ] model mutation 的 transaction/audit/checkpoint 全部落 system database/edit workspace。

**轻量验证**

```powershell
.\.tools\uv\uv.exe run pytest tests/runtime/test_system_application.py tests/sidecar/test_methods.py -q
```

### Task 4 — 把 `ProjectApplication` 收口为 Session/Run owner

**文件**

- 修改：`src/pilot_assessment/runtime/application.py`
- 修改：`src/pilot_assessment/runtime/current_preflight.py`
- 修改：`src/pilot_assessment/runtime/repository.py`
- 修改：`src/pilot_assessment/model_workspace/execution.py`
- 修改相关 runtime/persistence tests

**动作**

- [ ] `ProjectApplication.create/open` 注入已打开的 `SystemApplication`。
- [ ] 删除新 project 的 starter/current-model seed；project model tables 保留为空的兼容结构。
- [ ] project 继续拥有 immutable execution component materialization，但输入来自 system 的 exact clean closure。
- [ ] preflight 同时记录 SessionRevision lock 与 system model lock；run start 前重新检查 stale。
- [ ] `RunRepository.create_current()` 只验证已冻结 snapshot/preflight，不查询 project-local current nodes/schemes。
- [ ] pipeline 只使用 project-owned frozen materialization，run 开始后不读取 mutable system store。

**轻量验证**

```powershell
.\.tools\uv\uv.exe run pytest tests/runtime tests/persistence/test_project.py -q
```

### Task 5 — 无 project 的 Model Studio 与简化 Project 创建

**文件**

- 修改：`src/PilotAssessment.Desktop.Core/Protocol/BackendRuntimeLocator.cs`
- 修改：`src/PilotAssessment.Desktop.Core/ViewModels/ProjectLauncherViewModel.cs`
- 修改：`src/PilotAssessment.Desktop.Core/ViewModels/TaskSchemeListViewModel.cs`
- 修改：`src/PilotAssessment.Desktop/ViewModels/ModelStudioViewModel.cs`
- 修改：`src/PilotAssessment.Desktop/Views/Pages/ProjectLauncherPage.xaml`
- 修改：`src/PilotAssessment.Desktop/Views/MainWindow.xaml.cs`
- 修改中英文资源与相关 tests

**动作**

- [ ] portable mode 将软件根目录显式传给 sidecar；development mode 使用 repo-local ignored system root。
- [ ] backend 生成 stable project ID；项目页只要求可读名称和空目录。
- [ ] sidecar Ready 后立即加载 TaskScheme/Model Studio，不等待 project activation。
- [ ] project close/switch 只清理 Session/Run/Result context，不清理模型列表或 dirty model edit session。
- [ ] 项目页说明改为“项目保存 Session、运行、结果和 artifacts；系统模型由当前软件副本共享”。

**轻量验证**

```powershell
dotnet test tests/PilotAssessment.Desktop.UnitTests/PilotAssessment.Desktop.UnitTests.csproj -c Debug
dotnet test tests/PilotAssessment.Desktop.ContractTests/PilotAssessment.Desktop.ContractTests.csproj -c Debug
dotnet build src/PilotAssessment.Desktop/PilotAssessment.Desktop.csproj -c Debug -p:Platform=x64
```

### Task 6 — Legacy project-local model 无损导入

**文件**

- 新增：`src/pilot_assessment/model_workspace/legacy_import.py`
- 修改：`src/pilot_assessment/persistence/migrations.py`
- 修改：`src/pilot_assessment/runtime/application.py`
- 新增：`tests/model_workspace/test_legacy_import.py`

**动作**

- [ ] 为 legacy fingerprint/import receipt 增加 system-owned migration records。
- [ ] 相同 ID/hash 复用；缺失 ID 原样导入；同 ID/不同内容生成确定性 imported ID。
- [ ] 只改写 typed node/scheme/parent/CPT/layout references；无法验证则整笔回滚。
- [ ] 导入成功后 legacy tables 保持原样只读；重复打开幂等 no-op。
- [ ] 最多恢复一套 legacy dirty edit session；第二套冲突保留原 workspace 并返回 recoverable error。

**轻量验证**

```powershell
.\.tools\uv\uv.exe run pytest tests/model_workspace/test_legacy_import.py -q
```

### Task 7 — 双项目共享与历史快照隔离验收

**文件**

- 新增：`tests/integration/test_system_model_project_boundary.py`
- 修改：必要的 sidecar subprocess tests

**场景**

- [ ] 无 project：列出 starter scheme，修改一个微型 layout/参数并 Save all。
- [ ] 创建 Project A 与 Project B：两者都看到同一修改，数据库均无 current-model rows。
- [ ] 在 A 用微型 Session 创建 run snapshot；随后修改 system node。
- [ ] A 的旧 snapshot/hash 不变；B 的新 preflight 使用新 identity。
- [ ] 移动 A 整个目录后仍可打开和读取旧 run。
- [ ] sidecar 第二 writer 被稳定拒绝。

```powershell
.\.tools\uv\uv.exe run pytest tests/integration/test_system_model_project_boundary.py tests/sidecar/test_server_subprocess.py -q
```

### Task 8 — Portable baseline 与 M8B-0 收尾

**文件**

- 修改：`tools/build_portable_release.ps1`
- 修改：`tools/verify_portable_release.ps1`
- 修改：`docs/product/release/README-PORTABLE.md`
- 新增：`docs/product/reviews/2026-07-21-m8b0-system-model-ownership-verification.md`
- 修改：`README.md`、`docs/product/README.md`、`docs/product/11_IMPLEMENTATION_STATUS.md`

**动作**

- [ ] 构建时确定性创建 starter `system/` 与 `system-model-baseline.json`。
- [ ] release 扫描继续阻止用户 project/session/result，但允许系统 baseline 数据库。
- [ ] 从仓库外启动产品：未打开 project 进入 Model Studio；创建两个项目；验证共享模型。
- [ ] ZIP 不包含测试产生的 project/session/result，系统 baseline 保持 clean。
- [ ] 记录版本、hash、命令、通过项与明确未完成项。
- [ ] 只选择性提交 M8B-0 文件，不卷入当前工作树无关改动。

## 3. 自审门槛

实施期间每完成一个 Task，检查以下不变量：

- current canonical ModelNode/TaskScheme 只写 system database；
- project database 只保存运行所需的 immutable model copy，不成为下一次编辑源；
- UI 只发送 typed intent，C# 不复制 Evidence/BN/operator 算法；
- system dirty edit session 与 project 生命周期解耦；
- 用户可自由修改 starter，不增加审批、发布或 per-save test gate；
- 旧项目和历史 run 不被覆盖；
- 所有临时 project 与测试 system root 位于 pytest temp/build scratch，不进入发布包。

## 4. M8B-0 明确不关闭的事项

- M8B-1：loaded source/runtime/dependency/operator identity、disk drift、source snapshot artifact；
- M8B-2：从发布副本新增最小 Python operator、注册、重启、前端配置与 run 的完整闭环；
- M8C：最终 Markdown/DOCX 手册体系；
- M8D：系统模型和 project 的正式 backup/restore/migration UI；
- M8E：clean tagged release candidate 与用户最终验收；
- 专家科学校准、真实 CPT/threshold/anchor 有效性。
