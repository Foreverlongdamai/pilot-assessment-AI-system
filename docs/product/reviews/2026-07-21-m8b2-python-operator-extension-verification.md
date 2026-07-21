# M8B-2 Python Operator Extension Handoff Verification

| 字段 | 结果 |
|---|---|
| 日期 | 2026-07-21 |
| 范围 | 普通 Python 扩展入口、通用 schema UI、私有依赖工具、发布副本 extension/run 闭环 |
| 结论 | **PASS — M8B-2 engineering gate closed；M8B complete** |
| 科学边界 | 只证明工程扩展与追溯路径；不证明示例 operator、starter Evidence、BN 或 CPT 科学有效 |

## 1. 已交付能力

- `backend/src/pilot_assessment/evidence/extensions/__init__.py` 是唯一、显式、普通 Python 的本地扩展注册入口；它在 built-ins 之后、source identity 冻结之前执行；
- 扩展与 built-in 共用 `OperatorDefinition`、`OperatorRegistry`、recipe compiler、executor、catalog 和 trace，不存在第二套 plugin runtime；重复 operator identity 明确失败，不静默覆盖；
- `developer/examples/operator-extension/` 提供可复制的 typed operator、parameter JSON schema、注册步骤和 stdlib 最小测试；示例不被 clean product import，也不进入 starter system model；
- `developer/tools/manage_python_dependencies.ps1` 提供 `list`、`add`、`remove`、`sync`，只使用当前解压副本中的 private Python 与 bundled `uv.exe`，修改 `backend/pyproject.toml`、`backend/uv.lock` 和 `runtime/site-packages`；
- 已有 WinUI generic JSON-schema form 对 `trusted_extension` 使用同一条 EvidenceRecipe 编辑路径，不增加 operator-specific C# 页面；
- 发布文档明确区分：参数、recipe、parents、states、CPT、任务激活在前端修改；只有现有计算机制无法表达新目标时才改 Python 并重启；
- M8B-1 自动把源码树、dependency manifest 和 operator catalog 的变化冻结进新 RunSnapshot 与 content-addressed source artifact。

## 2. Fresh focused gates

### Python 与静态检查

```powershell
.\.tools\uv\uv.exe run pytest tests\evidence\test_extension_registration.py -q
.\.tools\uv\uv.exe run ruff check <M8B-2 changed Python paths>
.\.tools\uv\uv.exe run ruff format --check <M8B-2 changed Python paths>
```

结果：`3 passed in 2.91s`；Ruff check PASS；`7 files already formatted`。PowerShell parser 对依赖工具 PASS。

### Desktop 与真实 sidecar

```powershell
dotnet test tests\PilotAssessment.Desktop.UnitTests\PilotAssessment.Desktop.UnitTests.csproj -c Debug --no-restore
dotnet test tests\PilotAssessment.Desktop.ContractTests\PilotAssessment.Desktop.ContractTests.csproj -c Debug --no-restore
dotnet build src\PilotAssessment.Desktop\PilotAssessment.Desktop.csproj -c Debug -p:Platform=x64 --no-restore
```

结果：Desktop Unit `103/103`；real-sidecar Contract `4/4`；x64 Debug build `0 warning / 0 error`。新增测试证明 `trusted_extension` 的参数由既有通用 schema form 编辑并写回既有 recipe model。

### 私有依赖闭环

在 disposable release directory 中执行：

1. `list` 返回当前私有 runtime 的 `16` 个 packages；
2. `add 'typing-extensions==4.16.0'` 把依赖写入 release 副本的 `backend/pyproject.toml` 并同步私有 runtime；
3. `remove 'typing-extensions'` 删除 direct dependency 并再次同步；
4. 删除后 `pyproject.toml` 无残留；它仍作为 Pydantic 等包的合法 transitive dependency 出现在私有 runtime；
5. 全过程退出码为 `0`，不读取或修改全局 Python 环境。

## 3. Clean ZIP 与外部 release-copy 证据

正式构建命令：

```powershell
.\.tools\uv\uv.exe run python tools\release\build_portable.py
```

| 产物 | 实测值 |
|---|---:|
| package directory | `766,126,891` bytes |
| checksummed files | `4,283` |
| first-party backend files | `294` |
| ZIP | `261,438,185` bytes |
| ZIP SHA-256 | `a39321eceedca55bb929122d1fcc57fdef5eba51a8de698e1b9d0c157c739dab` |
| clean source tree / release baseline | `fbab5bd3c29ffbc589366e6118b87774b3aa23383b1e7fe8c20816ee387fe0e1` |
| clean combined backend identity | `97a19659bfb90c89c206f4760e9aa85592837c3779b02823b312f11e48bf8295` |
| clean catalog | `45` operators |

构建器首先在 disposable verification copy 中执行 M8B-2 vertical slice。随后把 ZIP 解压到仓库外的短路径，再运行：

```powershell
runtime\python\python.exe -I -B -X utf8 `
  developer\build\release\verify_portable.py <release-root> `
  --verify-editable-source --verify-operator-extension --launch-desktop
```

外部验证结果为 PASS：

- clean source 可被直接修改并在重启后实际 import；
- 旧 sidecar 在新增 extension 源码后报告 `runtime_restart_required=true`；
- 重启后 catalog 从 `45` 增至 `46`，出现 `extension.example.scalar-offset`，并暴露 required `offset` number schema；
- generic recipe 得到确定性 `2.75 / desired`，trace 指向该 extension；
- `201` 行、`2 s` 的轻量 Session 完成完整 assessment run，没有构造万行压力数据；
- extension source identity 为 `ce7d40c05cbdeccff22bfa0a67cf501696fe7ee858f632d4a6779c59d9731362`；对应 source artifact 为 `artifact.607ce378e013b611635ce99579d34ccc419ea55bb3154c79cb27cb3bd9f73505`；
- WinUI 获得非零窗口句柄，packaged sidecar 由桌面进程启动并在验证后关闭；
- verifier 恢复 extension 注册文件并删除临时 operator；正式 ZIP 保持 `53` 个 system nodes、`1` 个 scheme、clean edit session，且不含用户 project/session/result。

第一次把 ZIP 解压到仓库深层临时目录时，某文件绝对路径达到 `271` 字符并触发传统 Win32 path limit；改用仓库外短路径后内容、checksum、桌面与 sidecar 全部通过。因此交付文档要求用户把产品解压到合理短路径，例如 `D:\PilotAssessment`，而不是把该环境限制误判为 ZIP 内容缺失。

## 4. 收口结论

M8B-0、M8B-1、M8B-2 均已关闭工程门：一套软件副本拥有一个全局 system model library、一棵可直接编辑的 active Python source tree，以及可追溯的 RunSnapshot source identity。M8B 不关闭 M7 人工验收、D-055、M8C–M8E 或领域专家科学校准。下一阶段是 M8C 文档基础设施与权威原稿。
