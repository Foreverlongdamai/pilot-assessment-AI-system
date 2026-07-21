# M8E `v0.1.0-rc.1` Release Candidate Verification

| 字段 | 结果 |
|---|---|
| 日期 | 2026-07-21 |
| 候选标签 | annotated `v0.1.0-rc.1` |
| 标签提交 | `c736bf7ad58bd24212b8997c5bbbf427b96e2692` |
| 结论 | **PASS — M8E engineering gate closed；candidate ready for user acceptance** |
| 用户状态 | `user_acceptance=pending` |
| 科学状态 | starter/synthetic `formal_run_authorized=false` |

## 1. 验证范围与边界

本记录验证最终 Windows x64 portable 候选的可追溯身份、current-system 捕获、完整文档、checksums/SBOM、私有运行环境、可编辑 Python 源码、operator 扩展、轻量 assessment run、WinUI 启动、仓库外 restricted-PATH 运行和内容隔离。

它不代表用户已经接受界面、交互或实际实验工作流，也不证明 starter Evidence、operator 参数、阈值、BN 拓扑、CPT 或能力后验具有科学有效性。当前 18 个 Evidence、11 个 sub-skills、4 个 competencies 与 Hover 方案继续只是专家可编辑的 `starter_template` / `engineering_default`。

## 2. 候选身份与工具链

| 项目 | 实测值 |
|---|---|
| product / candidate | `0.1.0 / rc.1` |
| release label / channel | `v0.1.0-rc.1 / release-candidate` |
| Git tag type | annotated tag |
| tag peel | `v0.1.0-rc.1 -> c736bf7ad58bd24212b8997c5bbbf427b96e2692` |
| Git source state | `dirty=false` |
| host | Windows 11 x64 `10.0.26200` |
| .NET SDK / MSBuild | `10.0.302 / 18.6.11` |
| development uv / Python | `uv 0.11.28 / CPython 3.11.15` |
| packaged private Python | CPython `3.11.9` |
| Git | `2.53.0.windows.2` |

标签在候选实现和格式检查干净后创建。最终证据文档属于计划明确允许的 post-tag commit，因此不会移动或重写该标签。

## 3. Fresh source gates

执行范围覆盖 current-model contracts/workspace、persistence、managed assessment integration、schema、documentation、release builder/verifier 和真实 sidecar：

| Gate | 结果 |
|---|---:|
| Python focused suite | `132 passed in 108.19s` |
| Desktop Unit, Release | `106 / 106` |
| Desktop Contract, Release x64 | `4 / 4`，约 `36 s` |
| Ruff lint | PASS |
| Ruff format | `197 files already formatted` |
| `ty check src` | PASS |
| x64 Release build | `0 warning / 0 error`，`19.07 s` |
| affected documentation/release regression | `27 passed` |
| release regression after verifier-path fix | `22 passed` |
| released-document validation | `5 passed`，render QA `PASS` |

代表性命令：

```powershell
.\.tools\uv\uv.exe run pytest `
  tests\contracts\test_model_workspace.py `
  tests\model_workspace `
  tests\persistence\test_system_store.py `
  tests\persistence\test_model_workspace_repository.py `
  tests\integration\test_m8e_current_system_migration.py `
  tests\integration\test_m6_managed_assessment.py `
  tests\runtime\test_current_preflight.py `
  tests\runtime\test_current_run_snapshot.py `
  tests\schemas\test_schema_export.py `
  tests\documentation `
  tests\release `
  tests\sidecar\test_methods.py -q
.\.tools\uv\uv.exe run ruff check src tests tools
.\.tools\uv\uv.exe run ruff format --check src tests tools
.\.tools\uv\uv.exe run ty check src
dotnet test tests\PilotAssessment.Desktop.UnitTests\PilotAssessment.Desktop.UnitTests.csproj -c Release --nologo
dotnet test tests\PilotAssessment.Desktop.ContractTests\PilotAssessment.Desktop.ContractTests.csproj -c Release -p:Platform=x64 --nologo
dotnet build src\PilotAssessment.Desktop\PilotAssessment.Desktop.csproj -c Release -p:Platform=x64 --nologo
```

本轮没有恢复大型多模态 fixture 或把 provisional D/A/U 数值当作科学 golden；release-copy run 使用 `201` 行轻量输入验证完整技术闭环。

## 4. Released documentation

| 项目 | 实测值 |
|---|---:|
| released DOCX | `24` |
| candidate screenshots | `10` |
| rendered documents / pages | `24 / 277` |
| zh-CN / en-GB 技术总册 | `65 / 56` 页 |
| documentation manifest SHA-256 | `774ed8369d64b01a398c5e6f0f61925627b800bfbef8426099ff33bc5bef5f10` |
| source catalog SHA-256 | `de08f3aa57e5ced4d0c3ea444f4328418952f8b920624e17c1de75b969c245e5` |
| screenshot manifest SHA-256 | `4b0bd8254a5d5c050c8b39e4cd7921ca1d7e1152b1fc9d486b795293c8e30ce5` |

全部 DOCX 已执行结构验证；受影响的架构状态页、发布手册页和两份技术总册对应页完成逐页视觉复核，没有发现 clipping、overlap 或异常空页。

## 5. Source current-system 前后不变性

构建前、内部验证后和仓库外验证后检查 `.pilot-assessment-local/system`，得到相同结果：

| 字段 | 值 |
|---|---|
| model library ID | `model-library.9890442fd6564251b37a699fa0cebd35` |
| model identity SHA-256 | `79efc59cb38242a7edfa1c85a5311729c40a769bcbf7256b2f5f1d5cb0400a1e` |
| node / scheme count | `54 / 2` |
| DB / system schema | `6 / 1` |
| system format | `0.1.0` |
| edit base fingerprint | `3bba2da15aef2bb079c90e10f9f2ed55e85ef1faad3d95317e67989178541335` |
| edit baseline state hash | `5bcdac1a91a5353432bd6a3824b62a5e57db33e82853121b82c037e087706469` |
| user-owned table rows | all `0` |
| WAL / SHM / matching process leftovers | `0 / 0 / 0` |

Source 文件 hash：

| 文件 | SHA-256 |
|---|---|
| `.system-writer.lock` | `6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d` |
| `model-library.sqlite3` | `d2fa5c7eba29e9750358f70f71f56657760c53179a8f34164d05f414d5615591` |
| `staging/model-edit/workspace.sqlite3` | `9bb50d01750e82148f76f78bcc4d4e98f6bb8c14170ccce06201af23eb172488` |
| `system.json` | `fc9be96dec9769f05119334e41cb2bf0c143a2613a74e0b49dea7f746a78e717` |

验证创建的 project、source edit、extension 和 run 全部局限于 disposable package copies；source system 未被验证过程写入。

## 6. 最终候选产物

| 产物 | 实测值 |
|---|---:|
| directory | `dist/releases/PilotAssessment-0.1.0-rc.1-win-x64/` |
| directory files / bytes | `4,332 / 793,023,050` |
| checksummed files | `4,331` |
| first-party backend source files | `301` |
| ZIP | `PilotAssessment-0.1.0-rc.1-win-x64.zip` |
| ZIP bytes | `287,355,423` |
| ZIP SHA-256 | `56cc4cf7ec95edb551626d620424080e52604cc06ad9b5462bb83d8796d7a5ff` |
| release manifest SHA-256 | `2773513eb5811c79434813d806c02be834ae0b80af011210ea68944a0ae3d4a9` |
| SPDX SBOM SHA-256 | `b4b55919643680224f7f815083def53bec6447aab3c9eba22a297ddaac5dc182` |
| delivery record | `PilotAssessment-0.1.0-rc.1-win-x64.delivery.json` |

构建命令：

```powershell
.\.tools\uv\uv.exe run python tools\release\build_portable.py `
  --system-source .pilot-assessment-local\system `
  --release-label v0.1.0-rc.1 `
  --release-channel release-candidate `
  --candidate rc.1 `
  --user-acceptance pending `
  --documentation-status released
```

## 7. Internal 与 repository-external verification

内部 disposable-copy verifier 为 `PASS`，随后执行：

```powershell
.\.tools\uv\uv.exe run python tools\release\verify_archive_external.py `
  --dist dist\releases\PilotAssessment-0.1.0-rc.1-win-x64.zip `
  --verify-editable-source `
  --verify-operator-extension `
  --launch-desktop `
  --restricted-path
```

仓库外验证为 `PASS`：

- ZIP hash、outer delivery identity、4,331 个 checksums、release manifest、SBOM、24 份文档和 10 张截图一致；
- 仅使用候选自带的 CPython 3.11.9 和 16 个依赖即可 import backend 并启动 sidecar；stdout 是协议流，stderr 为空；
- clean backend source tree 含 301 个文件，baseline source-tree SHA-256 为 `5dc147d1a9a7c32aef4eee5df214e737a3af47d1e74525a89afa6444e782d65e`；
- 直接编辑唯一活动源码后，旧进程报告 `runtime_restart_required=true`；重启读取新源码，随后恢复 disposable copy；
- operator catalog 从 `45` 增至 `46`，新增 `extension.example.scalar-offset` 及其 number schema；recipe 输出 `2.75 / desired`，轻量 assessment run 为 `completed`，source rows 为 `201`；
- disposable copy 创建 `2` 个 project；候选内置 system model 始终保持相同 library ID、identity 和 `54 / 2`；
- WinUI 获得非零窗口句柄，桌面端自动启动 packaged sidecar，验证完成后两者均关闭；
- restricted PATH 为 `true`，因此验证不依赖开发机全局 Python、dotnet CLI 或仓库源文件。

ZIP entry、提取文本和 `360` 个 DOCX XML 文件的联合扫描未发现开发机私有绝对路径、用户 projects/sessions/results、PDB、cache 或未列入 manifest 的文件。交付包只包含系统、current model、runtime、完整可编辑一方 Python source、文档、schemas、licenses 和交付元数据。

## 8. 验证过程中捕获并关闭的问题

第一次完整构建在内部验证阶段拒绝了固定名 `build/portable-release/verification-copy`：candidate verifier 正确要求被验证根目录保持 `PilotAssessment-0.1.0-rc.1-win-x64` 身份。修复采用候选包名建立 verification copy，并新增回归测试；没有放宽 verifier。修复后 release focused tests 为 `22 passed`，重新从 clean source 创建 annotated tag 并完整重建、复验。

Ruff format gate 也在冻结前发现 5 个文件的格式漂移；格式化后全量为 `197 files already formatted`。上述两类问题均在最终候选形成前关闭，早期本地标签未发布、未交付。最终标签只指向本记录顶部的唯一提交。

## 9. 结论与下一门

M8E engineering gate 已关闭。`PilotAssessment-0.1.0-rc.1-win-x64.zip` 是当前可交付、可解压、可运行、可修改并具有完整工程追溯的候选。

下一门只有用户对实际界面和工作流的独立验收，以及其后可能产生的返修。用户接受前保持 `user_acceptance=pending`；领域专家完成校准与科学研究前保持 `formal_run_authorized=false`。任何返修应形成新提交和必要的新候选身份，不得移动或改写本次 `v0.1.0-rc.1` 标签。
