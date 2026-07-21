# M8B-0 System Model Ownership Verification

| 字段 | 值 |
|---|---|
| Review ID | M8B0-VERIFY-2026-07-21 |
| 日期 | 2026-07-21 |
| 范围 | software-copy system model ownership、project/run 隔离、legacy import、无 project Model Studio 与 portable baseline |
| 实施依据 | [M8B Design](../specs/2026-07-21-m8b-system-owned-model-library-and-editable-backend-provenance-design.md)、[M8B-0 Plan](../plans/2026-07-21-m8b0-system-model-ownership-implementation-plan.md)、D-066–D-071 |
| 结论 | **Engineering verified** |
| 最终 source baseline | 构建后填写 |

## 1. 结论边界

M8B-0 已把 current ModelNode、TaskScheme、CPT、layout 和 staged edit session 的 owner 从单个 project 提升为每套开发/解压软件副本的 `system/`。Project 只拥有 Session、不可变 execution materialization/RunSnapshot、result 与 artifacts。该结论只证明软件 ownership、事务、迁移、运行隔离和分发行为；不证明 starter Evidence、BN、CPT、阈值或能力结论科学有效。

M8B-0 不关闭 M7 用户手工验收、D-055、M8B-1 loaded-source provenance、M8B-2 新 operator 扩展闭环、M8C–M8E 或领域专家校准。

## 2. Fresh verification gate

以下命令均在最终提交/构建轮次重新执行；测试只使用微型图、两个临时 project 与最小 Session，没有建立万行多模态 fixture。

### 2.1 Python ownership vertical slice

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/contracts/test_system.py `
  tests/persistence/test_system_store.py `
  tests/model_workspace/test_edit_session.py `
  tests/model_workspace/test_legacy_import.py `
  tests/runtime/test_system_application.py `
  tests/runtime/test_application.py `
  tests/runtime/test_current_preflight.py `
  tests/runtime/test_pipeline.py `
  tests/runtime/test_preflight.py `
  tests/sidecar/test_methods.py `
  tests/sidecar/test_server_subprocess.py `
  tests/integration/test_m7a_current_model_workflow.py `
  tests/integration/test_m8b_system_model_project_boundary.py -q
```

结果：`22 passed in 134.99s`。

### 2.2 C# UI/contracts/build

```powershell
dotnet test tests\PilotAssessment.Desktop.UnitTests\PilotAssessment.Desktop.UnitTests.csproj -c Debug --no-restore
dotnet test tests\PilotAssessment.Desktop.ContractTests\PilotAssessment.Desktop.ContractTests.csproj -c Debug --no-restore
dotnet build src\PilotAssessment.Desktop\PilotAssessment.Desktop.csproj -c Debug -p:Platform=x64 --no-restore
```

结果：desktop Unit `102/102`；real-sidecar Contract `4/4`；x64 Debug build `0 warning / 0 error`。

### 2.3 Static and repository hygiene

```powershell
.\.venv\Scripts\python.exe -m ruff check src\pilot_assessment tests tools
.\.venv\Scripts\python.exe -m ruff format --check src\pilot_assessment tests tools
.\.venv\Scripts\python.exe -m ty check src\pilot_assessment
git diff --check
```

结果：Ruff lint 通过；`363 files already formatted`；`ty` 通过；diff whitespace 通过。

## 3. Ownership invariants verified

| 不变量 | 验证结果 |
|---|---|
| sidecar 先打开唯一 `SystemApplication` | 无 project 即可列出 starter scheme 与读取 Model Studio graph |
| 一套软件副本只有一个 system writer | 第二 writer 获得稳定锁冲突；没有放宽产品锁来迁就测试 |
| project 不拥有 current model | 新建 Project A/B 的 current-model tables 均为空 |
| 不同 project 共享 system model | Project B 保存的 system BN 修改在移动并重开 Project A 后可见 |
| 历史 run 不随 system model 改写 | Project A 旧 RunSnapshot、result 与 materialized closure 在 system 修改后保持不变 |
| staged edit 与 project 生命周期解耦 | project close/switch 不清空 system edit session |
| legacy import 不覆盖 system objects | same ID/hash 复用；same ID/different content 使用确定性 imported ID；重复打开幂等 |
| legacy dirty edit 可恢复 | 最多一套旧 edit session 作为单一 staged checkpoint 恢复；system 已 dirty 时拒绝第二套 |

## 4. Portable artifact

最终 clean-commit rebuild 后填写：

| 字段 | 最终值 |
|---|---|
| ZIP | `dist/releases/PilotAssessment-0.1.0-win-x64.zip` |
| Bytes | 构建后填写 |
| SHA-256 | 构建后填写 |
| Build kind | `m8b0-engineering` |
| Checksummed files | `4,270` |
| Public backend source files | `287` |
| System model library | `model-library.system.default` |
| System model identity | `c8e8a97c2c60d94ff8323aa2ac630ec3d3c63b557d529e608b3159e8c496a951` |
| Starter baseline | `53` nodes、`1` TaskScheme、edit workspace clean |

发布 baseline 的所有 user-owned table row count 必须为 0，包括 project metadata、Session、SessionRevision、run/preflight/result、artifact reference 与 run-model link。`system/` 只允许 canonical `model-library.sqlite3` 和 clean `staging/model-edit/workspace.sqlite3` 两个 SQLite 文件；lock、WAL、SHM 和临时 project 不得进入 ZIP。

## 5. Repository-external archive verification

```powershell
.\.venv\Scripts\python.exe tools\release\verify_archive_external.py `
  dist\releases\PilotAssessment-0.1.0-win-x64.zip `
  --verify-editable-source --launch-desktop
```

最终 clean-commit rebuild 后再次执行。验收条件：

- 在仓库外临时目录解压；
- 包内 private Python 从公开 `backend/src/pilot_assessment` 导入；
- 临时把 source marker 改为 `0.1.0+m8b0-live-source-smoke`，重启 sidecar 后必须观察到该值；
- sidecar 无 project 可读取 system model，并创建两个临时 project 验证共享模型；
- 桌面窗口出现，child sidecar image 位于解压目录；
- app/sidecar 不监听 TCP；
- 临时 project 位于 package 外且验证后清理；
- external verifier 返回 `status: PASS`。

## 6. 未关闭事项

- M7 用户在真实操作中的最终 UAT 与其可能返修；
- D-055 单一英文 canonical content contract/database migration；
- M8B-1 loaded source/runtime/dependency/operator identity、disk drift 与 RunSnapshot source artifact；
- M8B-2 新增 Python operator 的发布副本闭环及维护手册；
- M8C 分类 Markdown/DOCX 文档、M8D backup/restore/migration、M8E clean-machine final candidate；
- 真实 exporter/device profiles 与领域专家科学校准。
