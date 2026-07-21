# RC.2 Portable Root Layout and Sole Launcher Amendment

> **状态：已由用户在 RC.1 独立验收中以 `changes-required` 明确授权。** 本修订只改变便携产品的物理目录与启动边界，不改变 Evidence、BN、任务方案、Session、RunSnapshot 或科学状态。

## 1. 背景与验收事实

`v0.1.0-rc.1` 把 self-contained WinUI/.NET publish 直接复制到产品根目录，形成 94 个根目录文件夹和 374 个根目录文件。大量 DLL、WinMD、框架语言资源与运行时目录遮蔽了 `backend/`、`system/`、`runtime/`、`developer/` 和 `docs/` 等产品入口。用户验收结论为 `changes-required`。

RC.1 的 annotated tag、ZIP、checksum 和验证记录保持不可变；修订必须进入 `v0.1.0-rc.2`。

## 2. RC.2 根目录合同

产品根目录只允许：

```text
PilotAssessment.exe   # 唯一可启动入口
README.txt
app/                   # 完整 WinUI/.NET/Windows App SDK 运行载荷
backend/               # 活动、可编辑 Python 源码
system/                # 全局 Evidence/BN/任务方案模型库
runtime/               # 私有 Python 与依赖
developer/             # C# 源码、发布工具、operator 扩展示例
docs/                  # 双语手册、发布说明、验收清单
licenses/              # 第三方许可与 notices
manifest/              # release identity、checksums、SBOM、baseline
```

根目录禁止出现桌面 payload DLL、WinMD、PRI、语言资源目录或第二个可启动脚本/EXE。`app/PilotAssessment.Desktop.exe` 是内部桌面载荷，不是用户入口。

## 3. 启动与运行时定位

`PilotAssessment.exe` 是 self-contained 单文件 Windows 启动器，使用随产品提供的图标，从产品根目录启动 `app/PilotAssessment.Desktop.exe` 并等待它退出。参数原样传递；桌面载荷缺失或启动失败时显示明确错误。

由于 WinUI 的 `AppContext.BaseDirectory` 变为 `app/`，后端定位器必须在该目录名为 `app` 时向上一层解析产品根目录，并从根目录加载 `runtime/python/python.exe`、`backend/src/pilot_assessment` 与 `system/`。开发仓库的 uv fallback 保持不变。

## 4. 发布与验证合同

- release manifest 升级为 `pilot-assessment-release-manifest-v3`；
- `entrypoint=PilotAssessment.exe`；
- `portable_layout` 明确 launcher、desktop payload root、desktop executable 和语义目录集合；
- checksums/SBOM 继续覆盖 `app/` 内全部运行载荷；
- portable verifier 对根目录执行精确白名单检查，并通过根启动器观察 WinUI 窗口、私有 Python 后代进程和零 TCP listener；
- 仓库外 ZIP 验证继续使用 private Python，不依赖系统 Python、.NET SDK、Visual Studio 或数据库服务。

## 5. 文档与兼容性

短启动说明保留在根 `README.txt`，完整 release notes、acceptance checklist 和 known limitations 收纳到 `docs/`。手册统一指导用户双击根 `PilotAssessment.exe`，不再指导直接进入 `app/`。

本修订取代 D-064 中“根目录直接运行 `PilotAssessment.Desktop.exe`”以及 M8A/M8E 文档中的旧物理布局口径；D-064 的 unpackaged、self-contained、无预装工具链目标继续有效。

