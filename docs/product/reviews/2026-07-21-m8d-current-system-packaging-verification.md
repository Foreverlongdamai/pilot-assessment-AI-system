# M8D Current-System Packaging, Project Portability and Diagnostics Verification

| 字段 | 结果 |
|---|---|
| 日期 | 2026-07-21 |
| 结论 | **PASS — M8D engineering gate closed** |
| 范围 | 显式 current-system capture、动态 model baseline、project directory portability、system/project Diagnostics、disposable package verification |
| 不覆盖 | M7 用户验收、D-055、M8C-1、M8E clean-machine/final release、领域专家科学校准 |

## 1. 实现切片

| Commit | 内容 |
|---|---|
| `ae3139e` | M8D current-system packaging 正式规格 |
| `249422d` | INLINE 实施计划与自审 |
| `b669c24` | source system 锁、完整性、clean-state 与一致捕获合同 |
| `5a0ad08` | builder、v2 dynamic baseline、manifest 与 verifier 接入 |
| `5157de0` | backend `runtime.status` system/project compatibility |
| `a39532a` | typed WinUI Diagnostics 与中英文资源 |
| `172f9d3` | 完整 project 目录 copy/reopen/replay 与 portable 说明 |
| `9203a2d` | 目标包安全清除 source-local legacy import receipt |
| `110fd6c` | immutable read-only inspection，不在 source 生成 WAL/SHM |
| `bbedc08` | isolated packaged verifier 加载 sibling capture contract |
| `9abc3a6` | 状态、手册原稿、Known Limitations 与本验证记录收口；最终工程包从该 clean commit 构建 |

`legacy_system_model_import_receipts` 只记录旧 project 模型迁入 system 的本地迁移血缘，可能包含旧 project ID，不属于 Evidence/BN/CPT/TaskScheme。M8D 允许它存在于被选 source，但在目标 SQLite 中启用 secure delete、删除并压实；源表保持原样。真正的 project/session/run/result/artifact owner tables 仍必须全部为空。

## 2. Current system 前后不变性

构建前后两次在 writer lock 下检查 `.pilot-assessment-local/system`，结果完全相同：

| 字段 | 值 |
|---|---|
| model library ID | `model-library.9890442fd6564251b37a699fa0cebd35` |
| model identity SHA-256 | `10032f0c1a30abcc8dbede8fb97b62081c557b3dfab6f5751e31319f317172a4` |
| node / scheme count | `54 / 2` |
| system format / DB schema / system schema | `0.1.0 / 5 / 1` |
| locator SHA-256 | `fc9be96dec9769f05119334e41cb2bf0c143a2613a74e0b49dea7f746a78e717` |
| canonical source SHA-256 | `c789bf2a3cefbed9f75fdfd27cae3d2b26526b3d8e90af26a7f9c2e5a9a710ac` |
| edit base fingerprint | `1750c3d595812d1a409425ec3bfc73d5bd44c4e652301305778cfe36bd0693fc` |
| edit baseline state hash | `c65b176dff6fc1034038176e539141ffd26dbe1402791358835a3592033835d2` |
| source transient files after inspection/build | `0` |

十个真正的 user-owner tables 在 source/target 中均为 `0`。捕获的 target 仍为相同模型身份和 `54 / 2`，但 clean edit workspace 从 canonical state 重新建立，不携带旧 undo/redo history。

## 3. Fresh focused gates

```powershell
.\.tools\uv\uv.exe run pytest `
  tests\release\test_system_model_capture.py `
  tests\sidecar\test_methods.py::test_system_model_is_browsable_and_editable_without_an_open_project `
  tests\integration\test_m6_managed_assessment.py -q

dotnet test tests\PilotAssessment.Desktop.UnitTests\PilotAssessment.Desktop.UnitTests.csproj -c Debug --nologo
dotnet test tests\PilotAssessment.Desktop.ContractTests\PilotAssessment.Desktop.ContractTests.csproj -c Debug -p:Platform=x64 --nologo
dotnet build src\PilotAssessment.Desktop\PilotAssessment.Desktop.csproj -c Debug -p:Platform=x64 --nologo
```

结果：Python `14/14`；Desktop Unit `104/104`；real-sidecar Contract `4/4`；x64 Debug build `0 warning / 0 error`。WinUI 修改后真实启动获得非零主窗口句柄和标题 `Pilot Assessment System`；最终验证使用 `CloseMainWindow` 正常关闭，不再强制终止持有 system 的进程。

project portability 测试不是目录 rename：它用 `shutil.copytree` 保留原目录并创建第二个完整目录。复制后重新打开仍保持 project ID、managed Session revision、exact scheme/component hashes、result-by-ID、result-by-run、observation artifact bytes 和 rebased draft state。

## 4. Disposable package vertical slice

```powershell
.\.tools\uv\uv.exe run python tools\release\build_portable.py `
  --system-source .pilot-assessment-local\system `
  --output-root build\m8d-acceptance `
  --skip-archive
```

工程包 `PilotAssessment-0.1.0-win-x64` 的内置 disposable-copy verifier 为 `PASS`：

- package size：`768,862,128` bytes；checksummed files：`4,289`；backend source files：`294`；
- release manifest Git state：`9abc3a6ca9f0b801a8fb1f6fa368cd183af16834 / dirty=false`；
- manifest build kind：`m8d-current-system-engineering`，capture mode：`explicit-current-system`；
- package runtime 报告相同 model library、model identity、`54 / 2`、DB schema `5`、clean edit session 和空 recovery diagnostics；
- sidecar 在 disposable copy 创建并切换 `2` 个 project，切换前后 system identity 不变；stdout `11` 行均为协议消息，stderr 为空；
- clean operator catalog 为 `45`；disposable extension 后为 `46`，示例 recipe 为 `2.75 / desired`，轻量 `201` 行 Session run 完成；
- backend source baseline 为 `3edddeedb208dadf64a058a999332d946e9141a8051fd0e788311225b5679b8d`；
- 文档仍严格为 `3 review / 0 released`；本轮按计划不生成 ZIP，不能冒充 M8E release candidate。

## 5. Privacy、路径与固定规模审计

- package text 与 DOCX XML 中没有 `C:\Users\long`、仓库绝对路径或 source-system 绝对路径；release manifest 只保存相对路径与 hash；
- content policy 明确为 `user_projects/session_data/result_artifacts/synthetic_demo_data = false`；
- package system 的 project/session/run/result/artifact owner rows 全部为 `0`；legacy import receipt target count 为 `0`；
- package 只有 `system/model-library.sqlite3` 与 `system/staging/model-edit/workspace.sqlite3` 两个 SQLite 文件；
- release truth files 没有 `53 nodes / 1 scheme` 或等价固定 cardinality 约束；实际值来自 manifest 的 `54 / 2`；
- Backup/Restore 只以“没有专用功能、整目录复制是支持的 portability 操作”的否定边界出现；
- data-like suffix scan 只发现 NumPy/SciPy 依赖包自带的测试向量，没有 pilot project、Session、result、artifact、simulator stream 或 pilot-camera 数据。

## 6. 结论与下一门

M8D 已证明：专家保存的 current system 可以在不修改 source 的前提下进入新工程包；模型规模不再是 engine/release 常量；完整 project 可通过普通目录复制迁移；系统、源码、runtime 与 project compatibility 可从 Diagnostics 区分。

该结论不证明 starter Evidence、threshold、BN topology、CPT 或评分科学有效。`formal_run_authorized=false` 保持不变。M7 用户验收、D-055、M8C-1 和 M8E 仍为 pending；下一步应先回到用户手工验收，再依据真实返修后的 UI 完成最终双语手册和 clean release candidate。
