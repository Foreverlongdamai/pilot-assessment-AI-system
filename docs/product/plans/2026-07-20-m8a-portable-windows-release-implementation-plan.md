# M8A Portable Windows Release Implementation Plan

> **Execution mode:** INLINE。使用小型垂直切片与选择性验证；不重跑科研数据集，不生成或打包用户 Session。

| 字段 | 值 |
|---|---|
| 日期 | 2026-07-20 |
| 状态 | **已批准；已完成（2026-07-20）** |
| 规格 | [M8A Portable Windows Release Design](../specs/2026-07-20-m8a-portable-windows-release-design.md) |
| 输出 | 首个 Windows x64 portable engineering build 与可重复构建/验证入口 |

## Task 1 — 决策与文档收口

**Files**

- Modify: `docs/product/DECISIONS.md`
- Modify: `docs/product/specs/2026-07-18-m8-productization-editable-python-documentation-and-handoff-outline.md`
- Modify: `docs/product/plans/2026-07-18-m8-pre-uat-implementation-outline.md`
- Create: 本规格与本计划

**Work**

- 记录 portable self-contained、private Python、唯一活动 source tree、产品/用户数据分离；
- 明确本次授权启动 M8A，但不虚构 M7 用户验收已完成；
- 把 M8E clean-machine/final handoff 门保持为后续门槛。

**Verify**

- 文档状态、决策适用性和 M8A/M8E 边界没有冲突。

## Task 2 — Portable-first backend locator

**Files**

- Create: `src/PilotAssessment.Desktop.Core/Protocol/BackendRuntimeLocator.cs`
- Modify: `src/PilotAssessment.Desktop/Services/Backend/BackendConnectionService.cs`
- Delete: `src/PilotAssessment.Desktop/Services/Backend/DevelopmentBackendLocator.cs`
- Create: `tests/PilotAssessment.Desktop.UnitTests/Protocol/BackendRuntimeLocatorTests.cs`
- Modify: `src/pilot_assessment/__init__.py`

**Work**

- portable layout 优先，development uv fallback 次之；
- portable Python 使用 isolated args 并清除会污染 import 的环境变量；
- source-tree execution 在未安装本项目 wheel 时仍能读取产品版本；
- 错误消息同时说明 portable 与 development 缺失项。

**Verify**

- locator focused unit tests；
- package source-tree import smoke；
- 既有 backend connection/build 回归。

## Task 3 — Self-contained desktop publish contract

**Files**

- Create: `src/PilotAssessment.Desktop/Properties/PublishProfiles/win-x64.pubxml`
- Modify: `src/PilotAssessment.Desktop/PilotAssessment.Desktop.csproj` only if required

**Work**

- 固定 `win-x64`、.NET self-contained、Windows App SDK self-contained；
- 禁用 trim、single-file、PDB；
- 保持 unpackaged `WindowsPackageType=None`。

**Verify**

- fresh Release publish 0 errors；
- publish output 含 apphost、.NET runtime 与 Windows App SDK self-contained 文件。

## Task 4 — Reproducible portable builder

**Files**

- Create: `tools/release/build_portable.py`
- Create: `tools/release/verify_portable.py`
- Create: `tools/release/README.md`
- Create: `docs/product/release/README-PORTABLE.md`
- Create: `docs/product/release/README-DEVELOPMENT.md`
- Create: `docs/product/release/KNOWN-LIMITATIONS.md`
- Create: `docs/product/release/THIRD-PARTY-NOTICES.md`

**Work**

- 下载缓存和 SHA-256 验证 Python 3.11.9 embedded x64；
- frozen export/install production dependency closure；
- 复制 desktop output、live backend source、开发源码和发布文档；
- 生成 manifest、source baseline、checksums、license inventory、SPDX SBOM；
- 运行隐私/内容扫描并生成目录与 ZIP。

**Verify**

- 重复构建可成功；
- 包内没有 hidden first-party wheel/copy、dev dependency、cache、PDB 或用户数据。

## Task 5 — Repository-external portable verification

**Files**

- Generated only: `dist/releases/PilotAssessment-0.1.0-win-x64/`
- Generated only: `dist/releases/PilotAssessment-0.1.0-win-x64.zip`

**Work**

- 把产品包复制/解压到仓库外临时普通目录；
- 使用受限 PATH 验证 private Python origin 和 sidecar hello/shutdown；
- 临时修改并恢复 dispatcher source，验证重启确实加载 live `.py`；
- 启动桌面端，确认窗口和 Ready，检查 app/sidecar TCP listener；
- 不导入 repository-external 用户数据，不执行科学结果断言。

**Verify**

- verifier 全部 PASS；
- visible desktop smoke；
- 关闭临时实例并最后从正式 M8A 产品目录留一个已验证实例供用户检查。

## Task 6 — 状态、自审与交付

**Files**

- Modify: `docs/product/11_IMPLEMENTATION_STATUS.md`
- Modify: `docs/product/README.md`
- Create: `docs/product/reviews/2026-07-20-m8a-portable-windows-release-verification.md`

**Work**

- 记录构建命令、包路径、大小、hash、验证结果和残余限制；
- 明确 engineering build 与 final M8E release candidate 的区别；
- 不把 M8A 写成整个 M8 完成，也不把工程验证写成科学验证。

**Completion gate**

- 可重复构建和验证脚本已提交到工作树；
- 首个 ZIP 真实生成；
- 产品目录从仓库外运行并自动启动 packaged backend；
- manifest/checksums/source baseline/content scan 一致；
- M8B–M8E 仍按既定顺序继续。

## Completion record

2026-07-20，Task 1–6 已完成。构建生成 `PilotAssessment-0.1.0-win-x64/` 与最终 ZIP；仓库外解压验证确认 self-contained WinUI、包内私有 Python、唯一活动 backend source、JSON-RPC Ready/shutdown、可见窗口与零 TCP listener。临时源码修改在重启后实际生效，恢复后 checksum 再次一致。精确命令、大小、SHA-256、回归结果和残余 M8E 门见 [M8A verification record](../reviews/2026-07-20-m8a-portable-windows-release-verification.md)。
