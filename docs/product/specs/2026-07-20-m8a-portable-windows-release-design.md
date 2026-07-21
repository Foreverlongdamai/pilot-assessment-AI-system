# M8A Portable Windows Release Design

| 字段 | 值 |
|---|---|
| 里程碑 | M8A — Portable Runtime and Distribution |
| 日期 | 2026-07-20 |
| 状态 | **已批准；已实现并通过工程验收（2026-07-20）** |
| 批准依据 | 用户于 2026-07-20 明确要求执行既定 M8 计划并开始打包整个项目 |
| 目标 | Windows x64、本地离线、解压即用、后端自动启动 |
| 科学状态 | Starter algorithms、thresholds、BN topology 与 CPT 未经专家校准；`formal_run_authorized=false` |

## 1. 范围与状态边界

本规格把既有 M8 候选大纲中的 M8A 收口为可执行合同。用户本次授权允许在 M7 人工验收尚未完全关闭时先完成便携运行时、发布目录和工程验证；这不等于宣告 M7 用户验收完成。M7 人工验收仍是 M8E 最终交付候选的前置条件。

M8A 只证明系统能够作为独立 Windows 产品目录运行，不证明 starter Evidence、BN 或 CPT 科学有效，也不包含领域专家校准。

## 2. 发布形态

首个交付形态固定为：

- Windows x64；
- unpackaged、self-contained、side-by-side directory deployment；
- ZIP 解压后直接运行 `PilotAssessment.Desktop.exe`；
- .NET 与 Windows App SDK 文件随桌面端发布；
- CPython 以产品私有 embedded distribution 随包提供；
- Python sidecar 继续使用 JSON-RPC 2.0 / JSONL over stdin/stdout，不监听网络端口；
- 目标机不要求安装 Visual Studio、.NET SDK、系统 Python、Conda、uv 或开发仓库；
- 第一阶段不提供安装器、MSIX、自动更新或单文件封装。

Microsoft 将 xcopy/ZIP 分发对应到 unpackaged + self-contained 模式；Windows App SDK self-contained 输出会把依赖放到应用旁边。Python 官方把 embeddable distribution 定义为可随另一应用提供的私有最小 Python 环境。本项目采用这两个公开支持的部署模型。

## 3. 冻结工具链

M8A 首个工程包冻结：

| 项目 | 版本/合同 |
|---|---|
| 产品版本 | `0.1.0`，来自根 `pyproject.toml` |
| 目标 RID | `win-x64` |
| .NET target | `net10.0-windows10.0.26100.0` |
| .NET publish | self-contained、非 single-file、非 trimmed |
| Windows App SDK | `2.3.1`，`WindowsAppSDKSelfContained=true` |
| CPython | 官方 Windows embeddable x64 `3.11.9` |
| Python dependency source | `uv.lock` 的 frozen production closure；不安装本项目 wheel |
| uv build tool | 仓库固定 `.tools/uv/uv.exe`，只在构建机使用，不进入普通运行路径 |

Python 3.11.9 embedded ZIP 的下载地址和 SHA-256 必须同时固定在构建脚本中；下载后先验 hash 再解压。第三方 Python 依赖由 `uv export --frozen --no-dev --no-emit-project` 导出，并按 Windows x64 / Python 3.11 wheel closure 安装到私有 `runtime/site-packages`。

Release 使用 `PublishTrimmed=false`。当前桌面端、WinUI 与 host/JSON 组合优先保证可移植可靠性；体积优化不属于 M8A 完成门。

## 4. 正式发布目录

```text
PilotAssessment-0.1.0-win-x64/
  PilotAssessment.Desktop.exe
  *.dll / *.json / WinUI assets       # self-contained desktop output
  runtime/
    python/                            # isolated CPython embedded runtime
    site-packages/                     # locked third-party wheels only
  backend/
    src/pilot_assessment/              # 唯一活动的第一方 Python backend tree
    pyproject.toml
    uv.lock
    .python-version
    README-DEVELOPMENT.md
  docs/
    README-PORTABLE.md
    KNOWN-LIMITATIONS.md
  developer/
    desktop-source/                    # C#/WinUI 与 Desktop.Core 源码
    build/                             # portable build/verify scripts
  licenses/
    python-3.11.9.txt
    python-packages/                   # wheel 内随附的 license 文件（若提供）
    THIRD-PARTY-NOTICES.md
  manifest/
    release-manifest.json
    source-baseline.json
    checksums.sha256
    sbom.spdx.json
  README.txt
```

M8A 不再额外复制一套可编辑 starter/schema 到顶层 `resources/`。这些资源已经位于唯一活动的 `backend/src/pilot_assessment/**/profile_data` 和 `schema_resources` 中；再复制会制造“改哪份才生效”的歧义。后续文档只链接到活动源码树。

## 5. 后端定位与源码唯一性

桌面端启动后按以下优先级定位后端：

1. **Portable mode**：只检查 `AppContext.BaseDirectory` 下的 `runtime/python/python.exe`、`runtime/site-packages`、`backend/src/pilot_assessment` 和 backend metadata；
2. **Development mode**：若 portable layout 不存在，才从应用目录或当前目录向上寻找仓库 `.tools/uv/uv.exe`、`pyproject.toml` 与 `src/pilot_assessment`。

Portable mode 必须直接运行：

```text
runtime/python/python.exe -I -B -u -X utf8 -m pilot_assessment.sidecar
```

embedded Python 的 `python311._pth` 只加入标准库、`runtime/site-packages` 和 `backend/src`。发布依赖中不得安装 `pilot-assessment-system` wheel、editable `.pth` 或另一份 `pilot_assessment`，从而保证 `backend/src/pilot_assessment/` 是唯一活动第一方实现。

专家修改发布副本中的 `.py` 后关闭并重启软件，修改对该软件副本的所有项目和后续运行全局生效。普通 Evidence/BN/CPT/task 参数编辑仍通过前端完成，不要求改 Python。

## 6. 产品与用户数据隔离

发布包只包含系统。以下内容禁止进入产品目录和 ZIP：

- `local_data/`、用户选择的 project roots、SQLite project database；
- Session Bundle、simulator raw source、X/U/I/G/EEG/ECG/pilot-camera 数据；
- 运行结果、artifact、日志、最近项目和窗口偏好；
- repository-external 样例与临时 synthetic 数据；
- `.git`、`.venv`、`bin`、`obj`、缓存、PDB、临时文件和开发机私有绝对路径。

UI 偏好继续保存在 `%LOCALAPPDATA%\PilotAssessmentSystem`。用户项目继续由用户在前端选择位置；SQLite 是项目内部实现，不是需要单独启动的服务。

## 7. 构建、清单与可追溯性

单一构建入口必须完成：

1. self-contained 发布桌面端；
2. 验证并解压官方 private Python；
3. 从 frozen lock 安装 production-only third-party wheels；
4. 复制唯一活动 backend source、桌面源码和最小发布文档；
5. 生成 release manifest、backend source baseline、SHA-256 文件清单和基础 SPDX 2.3 SBOM；
6. 收集 Python runtime 与 wheel 中已经随附的 license 文件；
7. 扫描禁止目录、禁止数据扩展名、私有路径与隐藏第一方 package copy；
8. 生成产品目录和 ZIP。

工程包允许从 dirty working tree 构建，以便本轮包含尚未提交的 M7 用户返修；manifest 必须明确记录 `git.dirty=true`。只有 M8E 正式 release candidate 才要求 clean、tagged source。

## 8. 轻量验证与完成门

M8A 验证只覆盖产品化不变量：

- checksum、source baseline、layout 和内容扫描通过；
- private Python 在受限 `PATH` 下可导入，且 `pilot_assessment.__file__` 位于 package 的 `backend/src`；
- stdio sidecar 完成 hello/shutdown，stdout 每行都是 JSON-RPC；
- 在 disposable package 副本中修改一个 backend `.py` 可观察到重启后的 handshake 变化，随后恢复原文件；
- 桌面 EXE 从仓库外目录启动、主窗口出现、后端进入 Ready；
- app 与 sidecar 没有 TCP listener；
- 包内不存在用户 project/session/result 或开发机私有路径。

当前开发机上的 restricted-PATH / repository-external smoke 可以关闭 M8A 工程门；“完全没有已安装 .NET/Windows App Runtime/Python 的干净机器”仍须在 M8E 交付验收矩阵中再次执行。

## 9. 非目标

- 不做科学校准或真实飞行员评估结论验收；
- 不把测试数据或 demo Session 内置成产品功能；
- 不实现 Python 源码编辑器、远程 shell 或前端任意代码执行；
- 不在 M8A 完成项目备份/恢复 UI、十二类 DOCX 手册或最终签名安装包；
- 不因本地源码偏离 baseline 而阻止应用启动。
