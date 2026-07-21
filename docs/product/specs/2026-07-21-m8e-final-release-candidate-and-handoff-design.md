# M8E Final Release Candidate and Handoff Design

> **状态：方案 A 已由用户于 2026-07-21 明确批准。** 用户不再单独执行 M7 中间验收，而是在完整最终发布候选交付后统一验收。本规格允许构建 `v0.1.0-rc.1`，但在用户实际验收前不得把候选写成“已接受的正式版本”。

| 字段 | 值 |
|---|---|
| 里程碑 | M8E — Final Release Candidate and Handoff |
| 候选身份 | `v0.1.0-rc.1` |
| 产品版本 | `0.1.0` |
| 发布通道 | `release-candidate` |
| 用户验收 | `pending`，由用户直接验收完整候选 |
| 实施方式 | INLINE、小型垂直切片、选择性轻量验证 |
| 上游 | M8A、M8B、M8C-0、M8D；D-055；M8C-1 |
| 科学状态 | `engineering-only`；`formal_run_authorized=false` |

## 1. 目标

M8E 把已经工程验证的便携运行时、专家可编辑 Python、current system、项目可移植性和文档流水线收口为一个可由用户直接验收的 Windows x64 发布候选。候选必须：

1. 解压后直接运行，不要求安装 Visual Studio、.NET SDK、系统 Python 或开发仓库；
2. 携带明确选定且已保存的 current system，不重新生成或静默回退到 starter；
3. 保留前端修改 Evidence、BN、CPT、任务方案并写入全局 `system/` 的路径；
4. 完整暴露实际运行的 Python backend source，专家修改后重启即对该软件副本全局生效；
5. 不携带任何用户 project、Session、result、artifact、个人路径或测试数据；
6. 交付双语分类手册、双语技术总册、checksums、SBOM、licenses、release notes、known limitations 和验收记录；
7. 明确区分“自动工程验证通过”和“用户最终验收通过”。

M8E 不进行飞行员能力科学校准，不证明 starter Evidence、threshold、BN topology 或 CPT 科学有效，也不增加 installer、auto-update、cloud sync、backup/restore 或源码编辑 UI。

## 2. 取代旧的中间验收门

旧 M8 路线把 M7 用户验收设为 M8C-1/M8E 的构建前硬门。2026-07-21 用户选择直接验收完整最终候选，因此改为：

```text
M7 engineering verified
        |
        v
D-055 + M8C-1 + M8E implementation
        |
        v
v0.1.0-rc.1 complete delivery candidate
        |
        v
user acceptance of the complete candidate
        |
        +---- accepted ----> rebuild/promote from the accepted source as v0.1.0
        |
        +---- changes  ----> repair and issue v0.1.0-rc.2
```

这项取代只改变验收时机：

- 可以在 M7 中间人工验收未单独关闭时完成候选代码、手册、截图和 ZIP；
- 候选 manifest、文档封面、release notes 和验收记录必须显示 `user_acceptance=pending`；
- 不得把 `v0.1.0-rc.1` 冒充 `v0.1.0 final`；
- 用户验收时发现的 UI、合同、文档或运行问题进入 `rc.2`，不回写或覆盖 `rc.1`；
- 若用户接受且源码、system、文档与截图均不再变化，从同一已接受 source commit 重建 `v0.1.0`，不能只重命名旧 ZIP。

## 3. M8E 前置收口

### 3.1 D-055 单一英文 canonical 模型内容

M8E 先执行已批准的 D-055 和既有实施计划：

- current `ModelNode`、`TaskScheme` 和 definition help text 只保存一套 `name`、`short_name`、`description`、`help_text`；
- application chrome、字段标签、提示、对话框和错误继续通过中英文资源完整切换；
- 模型内容不随界面语言切换，不产生 revision/hash mutation；
- legacy bilingual current records 在事务内迁移，优先采用英文值；英文缺失时保留原内容并写 migration diagnostic，不调用翻译服务；
- immutable historical RunSnapshot 保持原 payload 与 hash，通过兼容 adapter 只读回放；
- current system 的节点数、方案数、parents、CPT、recipe、activation 和 layout 不因语言合同迁移而被删减或重置。

D-055 迁移必须先在副本上验证，再由正常数据库迁移路径应用到明确选择的 current system。它不是 backup/restore 产品，也不得建立第二套长期模型库。

### 3.2 M8C-1 最终候选手册

M8C-1 完成 12 类 logical documents 的中文和英文版本：

1. 产品总览与系统架构；
2. 安装、启动与快速开始；
3. 普通评估用户操作手册；
4. Evidence 与任务方案专家设计手册；
5. BN、父节点、状态与 CPT 专家手册；
6. Session Bundle 与五类原始输入接口手册；
7. Python operator 与源码扩展开发手册；
8. Python 核心代码维护手册；
9. 前后端协议与 C# 开发手册；
10. 系统分发、项目迁移与故障排查；
11. 发布构建与交付验收手册；
12. 从前 11 类自动聚合的系统技术参考总册。

结果为 24 份版本化 DOCX。Markdown 仍是唯一人工维护正文；DOCX 不手工编辑。每份手册必须有静态目录、真实 Heading、页眉页脚、版本、科学状态、交叉引用和适合目标读者的任务路径。

### 3.3 候选截图

D-075 的“最终截图必须先经过 M7 中间验收”被候选状态细化取代：

- 从 `v0.1.0-rc.1` 对应 build 捕获中英文候选截图；
- screenshot manifest 状态为 `release-candidate`，而不是 `final`；
- 每张记录 stable ID、product/candidate version、language、theme、source build identity、SHA-256、captured-at 和 privacy review；
- 截图不能包含用户名、绝对路径、真实受试者、真实生物数据或用户项目；
- 可使用仓库外一次性工程项目生成 UI 画面，但该项目和 Session 不进入 release；
- 用户接受且 UI 未变化时，同一 image bytes 可在 `v0.1.0` 重建中晋升为 final；若 UI 变化则重新捕获并重新审计。

至少覆盖以下五类界面，每类具有中文和英文候选图：

1. project launcher；
2. five-layer Model Studio；
3. Evidence node editor；
4. BN/CPT editor；
5. Run/Results/Diagnostics。

## 4. 候选身份与可追溯性

### 4.1 版本字段

产品核心版本继续为 `0.1.0`，发布身份增加独立字段：

```json
{
  "product_version": "0.1.0",
  "release_channel": "release-candidate",
  "candidate": "rc.1",
  "release_label": "v0.1.0-rc.1",
  "user_acceptance": "pending",
  "scientific_status": "engineering-only",
  "formal_run_authorized": false
}
```

候选目录和 ZIP 固定命名：

```text
PilotAssessment-0.1.0-rc.1-win-x64/
PilotAssessment-0.1.0-rc.1-win-x64.zip
PilotAssessment-0.1.0-rc.1-win-x64.zip.sha256
```

Python package/runtime contract version不因发布通道而改写。候选身份属于 release manifest，不伪装成 Python API semantic version。

### 4.2 Git 来源

- 候选必须从 clean working tree 构建；
- source commit 必须由 annotated tag `v0.1.0-rc.1` 指向；
- builder 验证 `HEAD`、tag、release label 与 manifest 一致；
- 构建后修改验证记录不改变候选 source identity；记录必须说明候选由哪个 tagged commit 构建；
- 若候选源码、current system 或 released documentation bytes 变化，必须产生新的 candidate sequence。

### 4.3 Current system 身份

builder 继续要求显式 `--system-source`，并沿用 M8D：

- app 已关闭、single-writer lock 可取得、edit session clean；
- SQLite integrity、schema 和 canonical/edit baseline 一致；
- user-owned project/session/run/result/artifact rows 全为空；
- 动态记录 model library ID、model identity、node count、scheme count；
- capture 前后 source file bytes 和 model identity 不变；
- target 清除 source-local legacy import receipt，不清除模型内容。

不得把 `54 nodes / 2 schemes` 写成 engine 常量；它只是当前候选实际捕获值。

## 5. 发布内容

### 5.1 ZIP 内

```text
PilotAssessment-0.1.0-rc.1-win-x64/
├── PilotAssessment.Desktop.exe
├── runtime/                       # private CPython and site-packages
├── backend/src/pilot_assessment/  # only active first-party Python tree
├── system/                        # captured clean current model
├── developer/                     # Python/C#/schemas/build and extension guidance
├── docs/
│   ├── zh-CN/                     # 12 released-candidate DOCX
│   ├── en-GB/                     # 12 released-candidate DOCX
│   ├── source-catalog.json
│   └── documentation-manifest.json
├── licenses/
├── manifest/
│   ├── release-manifest.json
│   ├── checksums.sha256
│   ├── sbom.spdx.json
│   └── backend-source-baseline.json
├── RELEASE_NOTES.md
├── KNOWN_LIMITATIONS.md
├── ACCEPTANCE_CHECKLIST.md
└── README.txt
```

### 5.2 ZIP 外

交付目录同时包含：

- ZIP；
- ZIP 的独立 `.sha256` 文件；
- machine-readable delivery manifest；
- M8E acceptance evidence；
- 简短中文交付说明，告诉用户如何校验、解压、启动和记录验收结果。

### 5.3 严格排除

- `.git`、`.venv`、build cache、test cache、IDE metadata、PDB 和开发日志；
- 用户 project、Session、result、artifact、preferences 或 recent-project history；
- repository-external demo、synthetic input、真实 simulator data 或截图 fixture；
- `C:\Users\...` 等绝对私有路径；
- 隐藏的第二份 first-party Python implementation；
- installer、MSIX、code-signing 声明、automatic update 或网络服务。

## 6. 两层验收证据

### 6.1 构建机自动隔离验收

当前会话没有提权权限，不能启用 Windows Sandbox。因此 `rc.1` 在交付前执行可自动复现的隔离验证：

1. 从 tagged clean source 构建；
2. 将 ZIP 复制到仓库外短路径并解压；
3. 使用受限 `PATH`，不调用系统 `python`、`dotnet`、`uv` 或 Visual Studio；
4. 使用包内 private Python 验证 manifest、checksums、SBOM、docs、system identity 和 source baseline；
5. 自动启动 sidecar，确认 stdout 只有 JSON-RPC、stderr 空或只含允许日志、无 TCP listener；
6. 创建两个一次性项目并切换，确认 system identity 不变；
7. 导入一次性最小 canonical Bundle 与 raw `streams/`/`annotations/` source；
8. 修改 Evidence 参数、BN CPT 和 TaskScheme，保存、重启并确认；
9. 修改 release 副本 Python source、新增一个最小 operator、重启并完成一次 201 行以内轻量 run；
10. 复制完整 project 目录到第二路径，重新打开历史 run/result/artifact；
11. 启动真实 WinUI，取得非零窗口句柄后正常关闭；
12. 扫描 ZIP 和解压目录，确认没有用户数据、私有路径、开发缓存或未声明文件。

所有变更只发生在 disposable copy。被交付候选目录和 selected current system source 保持不变。

### 6.2 用户最终验收

用户直接验收完整 `rc.1`，至少确认：

- 解压、启动、自动 sidecar 和 SQLite 无需手工激活环境；
- 创建/打开/切换项目；
- canonical/raw Session 导入；
- 五层画布、任务切换、active/dim、拖动、undo/redo 和关闭保存决策；
- 节点复制、Evidence recipe/parameter、BN parent/state/CPT 编辑；
- 运行、结果、Diagnostics；
- 中英文 UI 和单一英文模型内容；
- Python operator 源码扩展路径；
- project 整目录复制迁移；
- 双语手册可读且与实际软件一致。

用户结果只允许：

```text
accepted
accepted-with-documentation-only-corrections
changes-required
```

`accepted-with-documentation-only-corrections` 仍需重建 final 文档和 ZIP；任何 artifact bytes 变化都生成新的 hashes。

## 7. 错误处理与停止条件

M8E 遇到以下情况停止发布而不是降级：

- working tree dirty、tag/HEAD/manifest 不一致；
- current system 有 dirty edit session、writer lock、integrity/schema failure 或 user-owned rows；
- D-055 migration 丢失文本、改变历史 RunSnapshot 或删除节点/方案；
- 任一双语手册缺失、metadata/parity/links/DOCX render 失败；
- screenshot privacy 未通过或候选 build identity 不匹配；
- package 依赖系统 Python/.NET、出现 TCP listener 或存在第二份 first-party backend；
- checksums/SBOM/license/source baseline 与实际文件不一致；
- ZIP 含用户数据、绝对私有路径或测试 fixture；
- disposable verification 不能完成 project/session/edit/run/source-extension/portability 闭环。

失败时保留日志和证据，但不发布不完整 ZIP，不静默删除功能，不回退 starter model。

## 8. 选择性测试策略

测试只覆盖平台与发布不变量：

- D-055 legacy-to-current migration、current DTO/schema、hash/lineage 和旧 RunSnapshot replay；
- C# serialization、单字段编辑器、resource parity 和语言切换不修改模型；
- documentation catalog/front matter/parity、links/assets/privacy、DOCX structure/render；
- release label/tag/clean source、dynamic current-system capture、package content policy；
- package-internal vertical slice 与仓库外 ZIP verification；
- x64 release build 和一次可见 WinUI smoke。

不建立大规模多模态 fixture，不要求 starter Evidence 输出特定 D/A/U，不测试其科学正确性，不为专家每次参数修改建立审批门。

## 9. 文档与状态更新

候选产生后必须同步：

- root `README.md`；
- `docs/product/README.md`；
- `01_PRODUCT_OVERVIEW.md`；
- `09_VALIDATION_AND_HANDOFF.md`；
- `11_IMPLEMENTATION_STATUS.md`；
- `DECISIONS.md`；
- M8 roadmap；
- `Known Limitations`、release notes、review index；
- manual catalog、screenshot/diagram manifests 和 documentation manifest。

准确状态为：

```text
M8E release candidate engineering verified
user acceptance pending
scientific validation not performed
formal_run_authorized=false
```

只有用户验收后才允许写成 `v0.1.0 accepted release`。

## 10. 候选决策

本规格批准后写入以下正式决策：

- **D-078：** 取消单独 M7 中间用户验收硬门，改为直接验收完整 M8E 候选；候选构建不等于用户接受。
- **D-079：** 首个最终验收候选为 tagged clean-source `v0.1.0-rc.1`，manifest 独立记录产品版本、通道、候选序号和 acceptance 状态。
- **D-080：** M8C-1 可使用隐私审核后的 release-candidate screenshots；只有用户接受且 UI 未变化后才能晋升为 final。
- **D-081：** 构建机 disposable/restricted-PATH 自动验证与用户独立验收分别记录；当前无提权 Windows Sandbox 时不得伪称 Sandbox/clean-machine 已执行。

## 11. 完成定义

`v0.1.0-rc.1` 只有在以下条件同时满足时才可交付：

- D-055 已实现并验证；
- current system 完成兼容迁移、clean save 和显式 capture；
- M8C-1 的 24 份 DOCX 与 10 张候选截图通过结构、render、parity、hash 和 privacy audit；
- source commit clean 且由 `v0.1.0-rc.1` annotated tag 指向；
- ZIP、独立 hash、SBOM、licenses、source baseline、release notes、known limitations 和 acceptance checklist 齐全；
- 仓库外自动隔离验收全部通过；
- 发布源 system、交付候选和仓库工作区无验证副作用；
- 状态仍明确为 `user acceptance pending` 和 `formal_run_authorized=false`。

这关闭 M8E 候选工程门，不关闭用户最终验收或科学验证。
