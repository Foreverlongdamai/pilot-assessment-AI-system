# M8A Portable Windows Release Verification

| 字段 | 值 |
|---|---|
| Review ID | M8A-PORTABLE-VERIFY-2026-07-20 |
| 日期 | 2026-07-20 |
| 结论 | **PASS — M8A engineering gate closed** |
| 产品版本 | `0.1.0` |
| 目标 | Windows x64 unpackaged self-contained portable directory/ZIP |
| 构建基线 | Git `9236af94231b6815e4899162b80ce2054e023efa`；工作树 `dirty=true` |
| 科学状态 | `formal_run_authorized=false`；未执行或声称专家科学校准 |

## 1. 复核范围

本记录只验证 M8A 的便携发布合同：自包含桌面端、私有 Python、唯一活动的第一方 Python source tree、无网络端口 sidecar、系统与用户数据分离、发布元数据以及仓库外解压运行。它不表示 M7 用户验收已结束，也不表示 M8B–M8E、领域专家校准或科学有效性已经完成。

## 2. 构建产物

| 产物 | 结果 |
|---|---:|
| 产品目录 | `dist/releases/PilotAssessment-0.1.0-win-x64/` |
| ZIP | `dist/releases/PilotAssessment-0.1.0-win-x64.zip` |
| ZIP 大小 | `234,987,956` bytes（约 224 MiB） |
| 解压目录大小 | `686,693,069` bytes（约 655 MiB） |
| ZIP SHA-256 | `570ccd46ad6dc077c00ef9f7a97ca3b48a5007dd959a9e10c67d866ba39dc0af` |
| checksummed files | `4,260` |
| backend source files | `282` |
| 私有 CPython | `3.11.9` embedded x64 |
| Windows App SDK | `2.3.1` self-contained |

发布目录中的 `manifest/release-manifest.json`、`manifest/source-baseline.json`、`manifest/checksums.sha256` 与 `manifest/sbom.spdx.json` 均已生成。manifest 明确记录：不包含用户 project、session、result artifact 或 synthetic demo data；当前第一方 backend 只从 `backend/src/pilot_assessment` 运行，不安装本项目 wheel。

## 3. 可重复命令

在仓库根目录执行：

```powershell
.\.venv\Scripts\python.exe tools\release\build_portable.py
.\.venv\Scripts\python.exe tools\release\verify_archive_external.py dist\releases\PilotAssessment-0.1.0-win-x64.zip --verify-editable-source --launch-desktop
```

第二条命令把 ZIP 安全解压到仓库外的新临时目录，完全使用解压包内的私有 Python 与验证器，不借用系统 Python 或仓库 import path；验证结束后清理该临时副本。

## 4. 实测结果

### 4.1 仓库外便携运行

- checksum、source baseline、目录结构和内容政策检查全部通过；
- `pilot_assessment.__file__` 位于解压包的 `backend/src/pilot_assessment/__init__.py`；
- `pilot_assessment.__version__ == 0.1.0`；
- sidecar 完成 protocol `1.0` hello/shutdown，stdout 只有两条合法 JSON-RPC response，stderr 为空；
- 可见 WinUI 主窗口成功出现；
- 桌面进程的 Python child image 精确指向该解压包的 `runtime/python/python.exe`；
- 桌面端和 sidecar 的 TCP listener 数量为 `0`。

### 4.2 唯一活动源码与可编辑性

验证器临时修改发布副本中的第一方 source version marker，重启后实际读到 `0.1.0+m8a-live-source-smoke`；随后恢复原文件并重新通过全部 checksum。该结果证明运行时没有优先加载隐藏 wheel、仓库源码或第二棵第一方 Python copy。

### 4.3 内容和隐私边界

- 产品包内无用户 session、受管 project、result、artifact 或仓库外测试数据；
- 无 `.venv`、`.git`、pytest/mypy/ruff cache、PDB、开发测试目录或第一方 installed wheel；
- 产品只携带系统 runtime、应用、完整 backend source、维护所需 C# source、发布工具、starter 系统资源、许可证和最小发布文档；
- Python 在 isolated/no-bytecode 模式启动，运行后不会把 `__pycache__` 写回 checksummed source tree。

## 5. 回归验证

| 检查 | 结果 |
|---|---:|
| Python package metadata | `8 passed` |
| Ruff lint | PASS |
| Ruff format check | `4 files already formatted` |
| `ty check src/pilot_assessment` | PASS |
| Desktop Unit | `101 passed` |
| Desktop real-sidecar Contract | `4 passed` |
| Release publish | PASS，0 errors |
| ZIP hash independent recheck | MATCH |

这些测试只覆盖 M8A 改动及必要回归，没有重新运行科研样例或建立 starter 算法的科学 golden。

## 6. 自审

| 风险 | 关闭方式 | 状态 |
|---|---|---|
| 发布端误用开发仓库/系统 Python | portable-first locator、受限环境仓库外验证、精确 process image 检查 | closed |
| 第一方源码出现隐藏第二副本 | 不安装项目 wheel、origin 检查、live edit/restart smoke | closed |
| 运行产生 bytecode 导致 checksum 漂移 | launcher 显式使用 `-B`，运行后重验 checksum | closed |
| 产品包混入用户数据 | allow-list 复制、内容扫描、manifest flags、外部 ZIP 验证 | closed |
| 只验证 staging 目录而未验证 ZIP | 对最终 ZIP 做仓库外解压与完整 smoke | closed |
| 把工程包误称最终产品 | manifest 使用 `m8a-engineering`，状态文档保留 M8B–M8E 和 M7 UAT 门 | closed |

未发现开放的 P0/P1 M8A 缺陷。

## 7. 残余限制与下一阶段

1. 本包来自包含既有 M7 工作树修改的工程基线，因此 manifest 如实记录 `dirty=true`；M8E 正式候选必须来自 clean、tagged、可追溯基线。
2. 当前已完成“live source 是唯一实际执行源码”的 M8A 基础证明；源码 identity、modified-file visibility、RunSnapshot source snapshot、第三方依赖扩展流程和完整开发者手册属于 M8B。
3. 分类 Markdown/DOCX 文档属于 M8C；backup/restore/migration/diagnostics 属于 M8D。
4. 无 Visual Studio、无 .NET SDK、无系统 Python 的独立 Windows clean-machine 矩阵与最终用户交付验收属于 M8E。当前仓库外验证已隔离路径和运行时，但不能冒充另一台干净机器。
5. M7 用户手工验收仍在进行，并继续作为 M8E 最终交付候选的硬门槛。

因此，本记录关闭 **M8A engineering gate**，不关闭整个 M8。
