+++
document_id = "PAS-QUICKSTART-001"
language = "zh-CN"
title = "安装、启动与快速开始"
short_title = "快速开始"
product_version = "0.1.0"
document_version = "0.1.0"
status = "released"
audience = ["evaluator", "expert", "maintainer"]
information_types = ["tutorial", "how-to"]
scope = "说明如何解压、启动并完成第一次不含隐私样例数据的工程评估，无需单独安装或启动后端与数据库服务。"
prerequisites = ["Windows 10 19041 或更高版本（x64）", "可写的本地目录", "用户自己的 Session 数据源"]
scientific_status = "engineering-only"
related_documents = ["PAS-ARCH-001", "PAS-EVALUATOR-001", "PAS-SESSION-001", "PAS-PORTABILITY-001"]
support = "记录发布标签、可见错误消息和 Diagnostics 摘要；除非经过授权的支持流程明确要求，不要发送原始生理或 Session 数据。"
release_channel = "release-candidate"
release_label = "v0.1.0-rc.4"
user_acceptance = "pending"
+++

# 安装、启动与快速开始

## 1. 交付内容

交付物是一份 Windows x64 ZIP，其中包括 WinUI 前端、私有 .NET/Windows App SDK、私有 Python 运行时、可编辑 Python 源码、当前系统模型、手册和完整性清单。ZIP 不包含任何用户 project、Session、结果、样例生理数据或测试数据集。

当前是 `user_acceptance=pending` 的发布候选。starter Evidence、BN 和 CPT 是可编辑的工程模板，尚未完成领域科学校准。

## 2. 完整解压

1. 如果交付目录同时提供 `.sha256`，先校验 ZIP。
2. 把整个压缩包解压到较短且可写的本地路径，例如 `D:\PilotAssessment-0.1.0-rc.4`。
3. 保持根目录中的 `app\`、`backend\`、`system\`、`runtime\`、`developer\`、`docs\`、`licenses\` 与 `manifest\` 不变，不要单独移动启动器或 `app\` 中的文件。
4. 不要覆盖已经修改过的旧软件副本；解压到并列新目录，以便保留旧副本的 Python 源码和 `system\`。

候选包是 self-contained 的。正常使用时不需要另外安装或激活 Python、.NET、SQLite、Visual Studio，也不需要启动数据库服务。

## 3. 启动与关闭

双击产品根目录唯一的启动器 `PilotAssessment.exe`。启动器会从 `app\` 打开 WinUI 桌面载荷；前端随后自动启动一个本地 Python sidecar 子进程。JSON-RPC 只通过 stdin/stdout 传输，不监听 TCP 端口。SQLite 是由 Python 进程直接读写的嵌入式文件数据库，不是需要单独启动的程序。

正常关闭前端时，sidecar 会一起退出。工作过程中可随时点击主工具栏“保存全部”或按 `Ctrl+S`，在不关闭软件的情况下提交全部模型与布局修改。如果关闭时仍有暂存修改，对话框会询问“保存全部更改并关闭”“放弃全部更改并关闭”或“取消关闭”。保存或导入进行中时不要强行结束进程。

## 4. 创建第一个项目

[[SCREENSHOT:ui-project-launcher]]

1. 选择“创建项目”。
2. 输入容易理解的项目名称；技术 ID 由后端生成，用户无需手工填写 UUID。
3. 在解压软件目录之外选择一个空的可写目录。
4. 确认创建并等待项目工作区打开。

project 只拥有导入的 Session revisions、RunSnapshots、runs、results 和 artifacts，不拥有全局 Evidence/BN 模型。当前软件副本的 `system\` 会被该副本打开的所有项目共享。

## 5. 导入 Session

进入 Session 导入功能，选择以下任一来源：

- 已包含 `manifest.json` 的 canonical Session Bundle；
- 只包含 `streams\` 和可选 `annotations\` 的仿真器导出目录。

对于仿真器原始目录，系统只读检查外部文件，识别支持的 stream 映射，生成受管 manifest，并把接受的内容复制到 project。外部来源不会被修改。导出文件没有声明的单位会保持 undeclared，软件不会要求评估用户猜测单位。

允许缺少模态。产品不会自动生成 I/G/EEG/ECG/camera 数据；只依赖现有输入的 Evidence 仍可计算，依赖缺失输入的 Evidence 会形成明确的 unavailable observation。

## 6. 完成第一次工程评估

1. 打开“模型工作室”，选择需要使用的任务方案。
2. 确认系统模型 edit session 为 clean；运行前应保存或放弃暂存修改。
3. 打开“运行”，选择已导入的 Session revision 和任务方案，请求 preflight。
4. 检查技术 readiness 与缺失输入 diagnostics。
5. 只有 preflight 允许时才启动 run。
6. 完成后打开“结果”，查看 Evidence 连续值、D/A/U observation、BN posterior、缺失 Evidence、影响信息和 provenance。

运行用途可选择“预览”“软件测试”或“评估”。只要 technical preflight 为 ready，评估用途也可以完成整条工程管线；starter 模板仍保持 `formal_run_authorized=false`，界面会显示未正式授权 warning，run 关联的 frozen preflight provenance 保留该状态。run 完成只证明工程执行通顺，不代表科学有效或可用于真实运行决策。

## 7. 快速健康检查

当启动、导入或运行状态不明确时打开 Diagnostics，确认：

- backend ready，且没有 restart required；
- current system model 有明确 identity 和当前动态 node/scheme 数量；
- project 已打开且 compatible；
- 已加载 Python source 和 operator catalog 都有 identity；
- 最近错误包含稳定 error code 与 trace ID。

长 hash 和技术 ID 只应出现在 Diagnostics 与 provenance 区域；普通列表和结果卡片使用简洁名称。

## 8. 关闭、复制与重新打开

复制前必须完整关闭软件。迁移 project 时复制整个 project 根目录，再从目标软件副本打开新位置；需要同时传递模型库和 Python 修改时，复制整个解压软件目录。本产品不提供单独的 Backup/Restore 归档格式。

完整评估流程见 [[DOC:PAS-EVALUATOR-001]]；迁移和故障排查见 [[DOC:PAS-PORTABILITY-001]]。

## 9. 第一次使用检查单

- [ ] 已校验 ZIP hash；
- [ ] 已完整解压到可写目录；
- [ ] 未手动启动 Python/SQLite，桌面程序可以正常打开；
- [ ] project 创建在产品目录之外；
- [ ] Session 已导入受管存储；
- [ ] 已检查 preflight 并完成一次轻量 run；
- [ ] 已打开 result 与 provenance；
- [ ] 软件已正常关闭。
