# M8B-1 Backend Source Provenance and Snapshot Implementation Plan

> **执行方式：INLINE。** 本计划只证明“某次运行实际加载了哪一份 Python 后端、依赖、operator catalog，并可用不可变源码快照追溯”；不判断 starter Evidence、BN、CPT 或 operator 的科学正确性。

| 字段 | 值 |
|---|---|
| 里程碑 | M8B-1 — Backend Source Provenance and Immutable Snapshot |
| 日期 | 2026-07-21 |
| 状态 | **Implemented / engineering verified** |
| 设计依据 | [M8B System-Owned Model Library and Editable Backend Provenance Design](../specs/2026-07-21-m8b-system-owned-model-library-and-editable-backend-provenance-design.md) §11–§13、§17–§18 |
| 上游 | M8B-0 System-Owned Model Library |
| 下游 | M8B-2 Python Operator Extension Handoff |

## 1. 完成标准

M8B-1 完成时必须同时满足：

1. sidecar 启动时冻结 loaded backend identity，不在运行中悄悄改写；
2. identity 覆盖一方 Python 源码树、`pyproject.toml`、`uv.lock`、私有 Python/runtime、已安装依赖清单和 operator catalog；
3. portable release 可把 loaded 源码与 release baseline 比较，并给出 added/modified/deleted；开发环境没有 baseline 时明确返回 unavailable，而不是伪称 clean；
4. preflight 和 run start 都重扫磁盘；若源码在当前 sidecar 启动后改变，则返回 `runtime_restart_required` 并阻止新 run；
5. 重启后允许加载已修改源码，且把新 identity 写入新 run；旧 run identity 与 artifact 保持不变；
6. 某个 project 第一次使用某个 source identity 时写入确定性、内容寻址的 source snapshot artifact；同一 identity 后续复用；
7. snapshot 只包含一方源码、`pyproject.toml`、`uv.lock` 和 manifest，不包含用户数据、绝对路径、虚拟环境、第三方包字节、缓存或临时文件；
8. `runtime.status` 与 Diagnostics 页面能显示技术身份和 restart-required 状态；
9. 旧 v0.1 preflight/run snapshot 仍可读取，新 run 使用严格的新合同，不用可空字段掩盖缺失 provenance；
10. 使用微型 Session 和 focused tests 验证，不扩展重型多模态测试。

## 2. 实施任务

### Task 1 — 定义版本化源码身份合同

**文件**

- 新增：`src/pilot_assessment/contracts/source_provenance.py`
- 修改：`src/pilot_assessment/contracts/run.py`
- 修改：`src/pilot_assessment/contracts/__init__.py`
- 新增：`tests/contracts/test_source_provenance.py`

**动作**

- [x] 定义 `BackendSourceIdentity`、change summary、snapshot manifest 和 disk comparison 合同；
- [x] 固定 identity algorithm/version、路径正规化和 canonical JSON 规则；
- [x] 新增严格的 current preflight/run snapshot v0.2 合同，保留 v0.1 历史合同；
- [x] 确保 UI/导出字段没有绝对路径或本机用户名。

### Task 2 — 实现启动时冻结的 source provenance service

**文件**

- 新增：`src/pilot_assessment/runtime/source_provenance.py`
- 修改：`src/pilot_assessment/runtime/system_application.py`
- 修改：`src/pilot_assessment/runtime/application.py`
- 新增：`tests/runtime/test_source_provenance.py`

**动作**

- [x] 通过显式 product root 定位 release 源码，通过模块位置定位 development 源码；
- [x] 对排序后的 normalized relative path 与原始字节计算 tree hash；
- [x] 排除 `__pycache__`、`.pyc`、缓存、临时文件和构建输出；mtime、绝对路径与文件系统大小写不进入 hash；
- [x] 读取 release source baseline 并生成 added/modified/deleted；baseline 缺失时返回 unknown；
- [x] 记录 Python/runtime、依赖 manifest 与 operator catalog identity；
- [x] 在 `SystemApplication` composition root 启动时冻结 loaded identity 与 snapshot bytes；
- [x] 提供当前磁盘重扫与 restart-required 比较。

### Task 3 — 建立确定性源码快照 artifact

**文件**

- 修改：`src/pilot_assessment/runtime/current_preflight.py`
- 修改：`src/pilot_assessment/runtime/repository.py`
- 修改：`src/pilot_assessment/persistence/artifacts.py`（仅在现有 owner/ref 不足时）
- 新增：`tests/runtime/test_source_snapshot_artifact.py`

**动作**

- [x] 用固定条目顺序、固定 ZIP 元数据和 normalized archive path 生成 snapshot；
- [x] 先确定 artifact ID，再把 source identity/ref 写入 preflight；
- [x] 用 `RUN_PREFLIGHT` owner 和稳定 role 保存 artifact，同一字节自动去重；
- [x] v0.2 `CurrentModelRunSnapshot` 必须携带 source identity/ref；
- [x] 旧 snapshot 读取路径不变，新 run 不允许退回 v0.1 provenance。

### Task 4 — 在 preflight/run 边界阻止未重启源码漂移

**文件**

- 修改：`src/pilot_assessment/runtime/current_preflight.py`
- 修改：`src/pilot_assessment/runtime/coordinator.py`（若 run start 在此二次校验）
- 修改：`src/pilot_assessment/runtime/pipeline.py`（仅适配严格 snapshot 类型）
- 修改：相关 runtime/integration tests

**动作**

- [x] preflight 前重扫源码、配置与 lock file；
- [x] drift 时生成稳定的 `runtime.restart_required` error diagnostic，不创建 ready preflight；
- [x] run start 再比较，防止 preflight 后到启动前发生修改；
- [x] sidecar 重启后把修改后的源码视为新的 loaded identity，允许运行；
- [x] 证明旧 run snapshot/artifact hash 不变，新 run 使用新 hash。

### Task 5 — 暴露 runtime status 与 WinUI Diagnostics

**文件**

- 修改：`src/pilot_assessment/sidecar/methods.py`
- 修改：`src/PilotAssessment.Desktop.Core/Contracts/RunRpcContracts.cs`
- 修改：`src/PilotAssessment.Desktop.Core/Contracts/PilotAssessmentJsonContext.cs`
- 修改：`src/PilotAssessment.Desktop/ViewModels/DiagnosticsViewModel.cs`
- 修改：`src/PilotAssessment.Desktop/Views/Pages/DiagnosticsPage.xaml`
- 修改：中英文 UI 资源和 focused C# tests

**动作**

- [x] `runtime.status` 返回 loaded identity、baseline 状态、local modifications 和 restart-required；
- [x] Diagnostics 只展示技术状态，不显示为专家审批或科学有效性判断；
- [x] 中文界面使用中文标签、英文界面使用英文标签；完整 hash 位于可选择复制的只读技术文本框；
- [x] 不在普通 Model Studio 画布加入 provenance/operator 技术节点。

### Task 6 — 升级 portable baseline 与验证器

**文件**

- 修改：`tools/release/build_portable.py`
- 修改：`tools/release/verify_portable.py`
- 修改：`docs/product/release/README-PORTABLE.md`

**动作**

- [x] build 与 runtime 共用 source identity 语义，发布 `source-baseline-v2`；
- [x] verifier 独立重算 tree hash、逐文件 hash 和 package manifest；
- [x] release-copy 验证启动后 baseline available/clean；
- [x] 临时修改副本源码后验证 restart-required，重启后验证 locally-modified/new identity；
- [x] 不把修改过的临时副本写回正式 ZIP。

### Task 7 — 轻量闭环与文档收口

**验证**

- [x] unchanged/add/modify/delete；
- [x] mtime、安装绝对路径和路径大小写不改变 identity；
- [x] snapshot 同 identity 复用、不同 identity 新建；
- [x] old run unchanged/new run changed；
- [x] Python focused tests、C# focused tests、x64 build、release-copy smoke；
- [x] 写入独立 verification report，并更新状态、README、计划和决策适用性。

## 3. 自审不变量

- provenance 只证明“执行了什么”，不证明“算法科学上正确”；
- 普通参数/CPT/关系编辑仍从前端写入 system model library，不需要改 Python；
- 修改 Python 后端是一套软件级改动，影响重启后的所有 project，但历史 run 保持冻结；
- 没有审批、发布或 per-save test gate；restart-required 只防止一个进程混用两份代码；
- source snapshot 用于审计与恢复阅读，不从 project artifact 自动执行；
- portable package 不携带任何本机 project/session/result。
