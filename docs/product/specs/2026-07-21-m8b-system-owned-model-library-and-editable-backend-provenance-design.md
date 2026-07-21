# M8B System-Owned Model Library and Editable Backend Provenance Design

| 字段 | 值 |
|---|---|
| 里程碑 | M8B — System-Owned Model Library and Editable Backend Source |
| 日期 | 2026-07-21 |
| 状态 | **Review candidate；核心存储方案已由用户选择方案 1** |
| 上游 | M7 current-model workspace；M8A portable Windows release |
| 取代口径 | “global model library” 不再表示单个 project 内全局，而表示单个解压软件副本内全局 |
| 科学状态 | Starter Evidence、BN、CPT 与任务方案仍为工程模板；`formal_run_authorized=false` |

## 1. 设计目的

M8A 已证明一套解压后的 `PilotAssessment/` 可以独立启动 WinUI、私有 Python 和唯一活动 backend source，但当前 M6/M7 实现仍把 `model_nodes`、`task_schemes` 和模型 edit session 放在用户选择的 `project.sqlite3`/`project/staging` 中。因此，当前所谓“全局节点库”实际只在一个 project 内跨任务共享：Project A 的专家修改不会自动出现在 Project B。

这与用户已经确认的最终产品分层不一致。M8B 必须将模型定义提升为**软件副本拥有的系统状态**，同时保持用户项目只承载待评估数据和不可变历史记录：

```text
一套解压软件副本
├── Python backend source                    # 全系统计算机制
├── system model library                     # 全局 Evidence / BN / CPT / TaskScheme
└── zero or more user projects               # Session / RunSnapshot / result / artifact
```

本规格同时完成原 M8B 的 editable-source provenance：普通专家通过前端修改系统模型；只有现有 operator/core 无法表达新机制时，具备 Python 能力的专家才直接修改当前软件副本的 backend source。每次运行冻结 exact 模型和 exact source identity，因此全局自由修改不能改写历史结果。

## 2. 明确目标

M8B 必须实现：

1. 每套解压软件只有一个系统级 canonical ModelNode/TaskScheme 库；
2. 系统模型库存放在该软件副本自己的 `system/` 目录，不使用 `%LOCALAPPDATA%`，也不放入用户 project；
3. 同一软件副本打开的全部 project 立即看到同一套模型及专家修改；
4. Model Studio 在没有打开 project 时也可以浏览和编辑系统模型；
5. project create/open/import/run 不复制一套可继续编辑的 canonical 模型；
6. 每次 run 把 exact TaskScheme、active ModelNodes、operator/source/runtime identities 冻结到目标 project 的 RunSnapshot 和 artifacts；
7. 现有 project-local 模型无损迁移到系统库，冲突不得覆盖系统对象；
8. 发布副本继续直接运行公开的 `backend/src/pilot_assessment`，本地源码偏离只记录、不审批、不阻止运行；
9. 不改变 M7 已确认的 staged edit、Save all/Discard all、Ctrl+Z/Ctrl+Y、任务激活、CPT 和 parent closure 语义；
10. 构建与验证保持轻量，不重新运行大规模科研数据。

## 3. 非目标

M8B 不实现：

- 云端、多用户或跨电脑实时共享模型库；
- 每个 project 单独选择 backend source 或模型库；
- plugin marketplace、动态不可信代码加载、内置 IDE、Python REPL 或任意代码执行 RPC；
- 模型科学校准、专家审批流程或 per-edit 强制测试；
- 完整 project/system backup UI、自动升级合并或诊断包，这些属于 M8D；
- 十二类最终 DOCX 和技术总册，这些属于 M8C；
- clean-machine final candidate，这属于 M8E。

## 4. 权威所有权边界

| 内容 | 权威 owner | 是否跨 project 共享 | 历史运行如何保存 |
|---|---|---:|---|
| Python operators、adapters、BN engine、sidecar/core | 当前软件副本 `backend/src` | 是 | source snapshot artifact + source identity |
| Current ModelNodes、EvidenceRecipe、parents、states、CPT | 当前软件副本 `system/model-library.sqlite3` | 是 | RunSnapshot 冻结完整 active nodes |
| Current TaskSchemes、activation、task bindings、layout | 当前软件副本 `system/model-library.sqlite3` | 是 | RunSnapshot 冻结完整 scheme |
| Model edit session、undo/redo、Save/Discard | 当前软件副本 `system/staging/model-edit/` | 是 | 只在 Save all 后改变 canonical system state |
| Session、受管原始文件与同步/ingestion 报告 | 用户 project | 否 | exact managed revision |
| Run、result、trace、artifact | 用户 project | 否 | immutable project records |
| Source/model execution materialization | 用户 project | 否 | content-addressed immutable artifacts/records |
| UI 语言、窗口和 recent-project links | `%LOCALAPPDATA%` | 当前 Windows 账户 | 不进入科学/运行身份 |

“系统级”表示**每个解压软件副本一个 owner**。复制完整 `PilotAssessment/` 目录会复制当前系统模型和 Python source；两个副本随后独立修改。只复制 project 不会复制当前系统模型，但 project 内历史 RunSnapshot 仍包含过去运行所需的 exact 定义。

## 5. 产品目录

M8B 在 M8A layout 中增加：

```text
PilotAssessment/
  PilotAssessment.Desktop.exe
  backend/
    src/pilot_assessment/              # 唯一活动第一方 Python source
    pyproject.toml
    uv.lock
    README-DEVELOPMENT.md
  runtime/
    python/
    site-packages/
  system/
    system.json                        # 相对 locator、format、model_library_id
    model-library.sqlite3              # mutable canonical model state
    staging/
      model-edit/
        workspace.sqlite3              # crash-safe staged edit state（需要时创建）
  manifest/
    release-manifest.json
    source-baseline.json
    system-model-baseline.json
    checksums.sha256
    sbom.spdx.json
```

`system/model-library.sqlite3` 属于产品系统状态，不是用户 project 或测试 Session。首个 ZIP 可以携带由 starter resources 确定性初始化的 baseline 数据库，使第一次启动、尚未创建 project 时 Model Studio 已有基础节点和方案。

用户修改系统模型后，baseline checksum 发生变化是正常状态。发布完整性与当前系统状态必须分开表达：

- `checksums.sha256` 描述原始交付 baseline；
- `system-model-baseline.json` 描述出厂模型 identity；
- runtime 计算当前 `SystemModelIdentity` 并显示 `locally_modified`；
- 偏离 baseline 不阻止启动、编辑或运行；
- 恢复出厂状态的首阶段方法是关闭软件并重新解压原始 ZIP，不提供隐藏回退副本。

应用目录必须可写。若 `system/` 不可写，启动明确失败并提示把整套软件移动到普通用户可写目录；不得静默改用 `%LOCALAPPDATA%`，否则同一软件副本的 ownership 会失真。

## 6. 运行时组合

### 6.1 `SystemApplication`

sidecar 启动时、任何 project 打开之前，先创建或打开一个 `SystemApplication`。它拥有：

- system locator/database 和独立 migration history；
- `CurrentModelWorkspaceService`；
- system-owned `ModelEditSessionManager`；
- current ModelNode/TaskScheme repositories、audit/idempotency；
- operator/source-provider registries；
- backend source、dependency、runtime 和 operator-catalog identity services；
- starter seed receipt 和 legacy model import receipts。

所有 `model.node.*`、`model.scheme.*`、`model.graph.*`、`model.edge.*`、`model.cpt.*`、`model.edit.*` 和 operator catalog 方法都绑定 `SystemApplication`，即使没有打开 project 也可调用。

### 6.2 `ProjectApplication`

`ProjectApplication` 只在用户创建或打开 project 后存在。它拥有：

- project locator/database；
- managed sessions、artifacts、runs、results、progress/cancel/recovery；
- project audit/idempotency；
- 把 system model exact closure 物化为当前 project 的 run preflight/snapshot/artifact 的服务。

`ProjectApplication` 通过构造注入只读访问当前 `SystemApplication`；不得自行 seed 或维护第二套 current model workspace。

### 6.3 Sidecar 生命周期

```text
sidecar launch
  -> locate portable/development system root
  -> acquire single-writer system lock
  -> open SystemApplication
  -> hello / Ready（Model Studio 已可用）
  -> optional project.create/open
  -> optional session import and run
  -> close project（system model remains open）
  -> app close resolves system edit session
  -> sidecar shutdown closes system lock
```

一套软件副本同时只允许一个 sidecar 写系统模型。第二个主进程发现锁被占用时返回稳定、可本地化的错误；节点浮窗仍属于同一 WinUI/sidecar，不受限制。

## 7. System Model Store 合同

`system/system.json` 至少记录：

- `format_version`；
- `model_library_id`；
- `database_path = model-library.sqlite3`；
- `created_from_product_version`；
- `starter_seed_id` 与 seed manifest hash。

locator 不保存绝对路径。`model_library_id` 标识一套可迁移系统状态，但不参与科学计算；模型语义仍由 scheme/node hashes 决定。

System database 使用独立 migration namespace。M8B v1 可以复用现有 SQLite kernel 和表定义，但 owner 外的表必须保持为空且不可通过 system service 访问。canonical model state 只允许出现在 system database；新 project 不得写 `model_nodes`、`task_schemes` 或 model edit-session rows。

当前 contracts 中以下 project-scoped 语义需要升版：

- `ModelGraphSnapshot.project_id` → v0.2 `model_library_id`；
- `ModelEditSessionStatus.project_id` → v0.2 `model_library_id`；
- `CurrentModelWorkspaceService(project_id=...)` → `model_library_id=...`；
- `model_graph_semantic_hash()` 不再包含 project ID，而包含模型库 ID、scheme identity、node hashes 和 edges；
- C# typed contracts 同步升版，不使用字符串补丁或 UI-only alias。

旧 v0.1 RunSnapshot、graph record 和 project database 保持可读；兼容读取不得把旧 project-local canonical state重新写回 current system state。

## 8. 新建和打开 Project

### 8.1 第一次使用

产品 ZIP 不携带用户 project。用户第一次启动即可先浏览/编辑系统 starter，也可以在“项目”页：

1. 输入可读项目名称；
2. 由后端自动生成 stable project ID，普通 UI 不要求用户维护随机 ID；
3. 选择不存在或为空的外部目录；
4. 创建并打开 project；
5. 导入自己的 Session。

创建 project 不再 seed ModelNodes 或 TaskSchemes。项目页的说明必须改为：project 保存 Session、运行、结果和 artifacts；Evidence/BN/TaskScheme 由当前软件副本的系统模型库统一提供。

### 8.2 Project 切换

切换或关闭 project：

- 不关闭或替换 SystemApplication；
- 不改变当前 TaskScheme、节点或 model edit session；
- 清空 Session/Run/Result 页面中的 project context；
- Model Studio 继续显示同一系统模型；
- dirty model edit session 不因 project 切换自动保存或放弃，仍只在应用关闭时统一询问。

### 8.3 Project 可迁移性

project 整体移动后，历史 Session/Run/Result/RunSnapshot 继续可读。若在另一套软件副本中打开，它使用那套软件当前的系统模型执行**新的**运行；旧运行仍显示自身冻结的 exact model/source，不重新解析为新系统的 current model。

## 9. Run Preflight 与不可变快照

运行必须同时锁定两类 owner：

```text
Project owner                         System owner
managed SessionRevision              current TaskScheme
run ID / purpose                     active ModelNode closure
result/artifact destination          operator catalog
                                      backend source/runtime/dependencies
```

流程为：

1. 从 project 锁定 exact managed SessionRevision；
2. 从 system store 读取 clean current TaskScheme 和 active closure；
3. 计算 `SystemModelIdentity`、graph hash、operator/source/runtime identities；
4. 在 project preflight 中保存这些 identity；
5. run creation 前重新读取 system state，任何 revision/hash 变化都产生 stale error；
6. 将完整 TaskScheme、active ModelNodes 和现有 legacy execution materialization写入 project-owned immutable records；
7. 将 `CurrentModelRunSnapshot` 原子写入 project database；
8. 后续 pipeline 只读取 frozen snapshot/materialization，不再读取 mutable system model。

`RunRepository.create_current()` 不再到 project database 查询 `task_schemes/model_nodes` 证明 current state；它验证 snapshot 自身、persisted preflight 和由 SystemApplication 在 project transaction 前提供的 exact lock。项目数据库中不需要一份可编辑 current model 才能运行。

## 10. 现有 Project 的无损迁移

任何 legacy project 均保持原目录和原始数据库 bytes，迁移不得先删除或覆盖其 model tables。

### 10.1 识别

打开 v0.1 project 时，迁移器计算：

- canonical project-local ModelNode/TaskScheme fingerprint；
- 是否存在未完成的 project-local model edit session；
- system store 中是否已有相同 migration receipt。

同一 fingerprint 已处理时幂等 no-op。

### 10.2 Canonical 对象合并

导入按一个 system transaction 执行：

| 情况 | 行为 |
|---|---|
| 相同 ID、相同 semantic/layout hashes | 复用 system 对象，不新增副本 |
| system 中不存在该 ID | 保留原 ID 导入 |
| 相同 ID、内容不同 | 创建确定性的 imported node/scheme ID，不覆盖 system 对象 |

发生 ID remap 时，必须递归改写并重新校验：

- copied-from references；
- Evidence raw bindings；
- Evidence/BN parent refs 与 CPT child/parent axes；
- TaskScheme explicit/closure/output/layout node IDs；
- scheme lineage；
- task bindings 中由明确 schema 声明为 model reference 的字段。

迁移器不得在任意 JSON 字符串中按文本猜测并替换 node ID。没有 typed reference schema 的 task-binding 内容保持原 bytes；若其技术校验因此无法解析 imported closure，则本次 transaction 失败并返回明确 diagnostic，而不是生成语义不明的方案。

导入对象使用清晰原名称；迁移来源进入 provenance/tags/Technical identity，不把 project ID 或 hash 拼到普通显示名称。完整图技术校验通过后才提交 system transaction 和 receipt；任一对象失败则全部不变。

### 10.3 未提交 edit session

若 legacy project 存在 dirty model edit session：

1. 先把 project canonical state按上述规则导入 system canonical；
2. 将 legacy draft 的映射后状态恢复为 system-owned dirty edit session；
3. 启动后明确显示 recovered edits；
4. 用户仍使用现有 Save all/Discard all 选择；
5. 在用户决定前不得 preview/preflight/run。

不得静默丢弃 dirty edits，也不得自动把它们提交为 canonical。

系统同一时间只允许一个 dirty edit session。若 system store 已经有未解决的 dirty edits，又打开另一个带 dirty legacy draft 的 project，迁移器保留第二个 project draft 原文件并返回 recoverable conflict；用户先 Save/Discard 当前 system session，再重试迁移。不得自动合并两套未提交草稿。

### 10.4 Legacy 数据保留

迁移后，旧 project 中的 current-model tables 和 staging edit database只作为 compatibility/replay 资产保留；M8B runtime 不再写入或把它们当作 current source。迁移 receipt 记录 legacy fingerprint、system mapping、时间、结果和 tool version，使重复打开安全幂等。

## 11. Backend Source Identity

M8B 引入只读 `BackendSourceIdentity`：

- active source root 相对路径；
- canonical source-tree SHA-256；
- release baseline SHA-256；
- `baseline_available`；
- `locally_modified`；
- added/modified/deleted file summary；
- `pyproject.toml` 和 `uv.lock` hashes；
- private Python/runtime identity；
- operator catalog identity；
- identity algorithm/version。

tree hash 对 `backend/src/pilot_assessment` 下所有第一方普通文件按规范化相对路径、原始 bytes 和排序清单计算；排除 `__pycache__`、`.pyc` 和临时文件。hash 不使用 mtime、绝对路径或 Windows 路径大小写。

sidecar 启动完成 import 前计算并冻结本进程的 `loaded_source_identity`。`runtime.status`、diagnostics 和 run preflight 返回该 identity。发布包存在 baseline 时，added/modified/deleted summary 与 baseline 比较；开发仓库没有 release baseline 时仍计算 current hash，但不得伪称官方或 locally modified。

preflight 还会重新计算磁盘上的 current tree/lock identity。若应用运行期间源码或 dependency lock 被修改，磁盘 identity 与 `loaded_source_identity` 不一致，必须返回 `runtime_restart_required` 并阻止该次 run；这是为了避免“快照记录新文件、进程却执行旧 import”的错误 provenance。用户重启后，本地修改仍可正常运行，不因偏离 release baseline 被阻止。

源码偏离永远不作为科学/运行审批门。语法或 import 错误可能导致 sidecar 无法启动，WinUI launcher 必须显示真实 stderr/诊断，不得退回隐藏旧实现。

## 12. Source Snapshot Artifact

每个新的 source-tree hash 首次用于某个 project run 时，系统创建一个确定性 source snapshot：

- 只包含第一方 active backend tree、`pyproject.toml`、`uv.lock` 和 snapshot manifest；
- 文件排序、路径分隔符和 archive metadata 固定；
- 不包含 project、Session、结果、环境变量、绝对路径、third-party wheel bytes 或 caches；
- 以 snapshot bytes SHA-256 进入当前 project 的 content-addressed artifact store；
- 同一 project 中相同 source hash 复用 artifact；
- RunSnapshot 保存 source identity 和 artifact reference。

source snapshot 用于解释和维护，不由运行时自动执行。恢复或重新执行旧代码需要维护者从 artifact 提取到独立的软件副本，避免当前系统静默切换 backend。

## 13. 两层专家修改流程

### 13.1 正常模型编辑

```text
WinUI 节点/方案编辑器
  -> typed system-model operation
  -> system-owned persistent edit session
  -> Ctrl+Z/Ctrl+Y / technical validation
  -> 应用关闭时 Save all 或 Discard all
  -> 后续所有 project 使用新 canonical system state
```

参数、recipe、节点、边、parents、states、CPT、任务方案和 layout 均走此路径，不改 Python，也不要求发布或测试审批。

### 13.2 新计算机制或 core 修改

```text
确认现有 operator/core 无法表达目标
  -> 完全关闭应用与 sidecar
  -> 复制整套软件目录或保留原始 ZIP
  -> 编辑 backend/src/pilot_assessment
  -> 必要时用随包工具更新 private dependencies 与 lock
  -> 重启
  -> diagnostics 查看 source identity / import error
  -> 用一个微型 Evidence/BN 路径验证
  -> future run 自动保存 source identity/snapshot
```

不提供内置 source editor、修改 API 或项目级 source overlay。修改只作用于当前软件副本；要并列保留另一套 core，复制整套软件目录。

## 14. Python Operator 扩展交付

发布包继续完整暴露：

- `backend/src/pilot_assessment/evidence/builtins/`；
- `evidence/registry.py`；
- `evidence/builtins/__init__.py::register_builtin_operators()`；
- contracts、schemas、compiler/executor/validation；
- `pyproject.toml`、`uv.lock` 和固定版本依赖管理工具。

新增 operator 仍为 ordinary Python source change：实现 callable 和 `OperatorDefinition`、注册、重启，然后在前端 EvidenceRecipe 中选择。`parameter_schema`/UI hints 驱动结构化表单；C# 不为每个 operator 写专用计算代码。

M8B 验证使用一个最小演示 operator 证明 catalog、recipe、run 和 source snapshot 路径。该 operator 只证明扩展机制，不成为新的科学 starter Evidence，也不进入正式 Hover 默认方案。

## 15. WinUI 行为修订

### 15.1 Project 页

- 第一次启动无 project 是正常状态；
- “创建受管项目”只说明 Session/Run/Result/artifact ownership；
- Stable project ID 由后端生成，普通创建表单不再要求用户编辑长随机 ID；
- recent projects 仍只是 `%LOCALAPPDATA%` 中的本地快捷链接。

### 15.2 Model Studio

- backend Ready 后即加载 system model，不等待 project；
- 页面顶部显示当前软件副本的 model-library name/status，技术 ID 默认折叠；
- project 切换不刷新成另一套节点；
- source/model `locally_modified` 只在 diagnostics/technical area 显示，不污染节点名称；
- dirty edit session 的关闭提示保持“保存全部并关闭／放弃全部并关闭／取消”。

### 15.3 Session、Runs 与 Results

- 无 project 时明确禁用并提示先创建/打开 project；
- 打开 project 后使用系统当前方案做新 preflight/run；
- 历史结果显示 frozen scheme/source identity，不把当前系统状态冒充历史状态。

## 16. 错误与恢复

| 条件 | 行为 |
|---|---|
| `system/` 不可写 | 启动失败并提示移动整套软件；不回退到其他目录 |
| system locator/database 缺失 | 开发态可从 starter 初始化；正式包缺失则显示可恢复的产品完整性错误 |
| system DB migration 比 runtime 新 | fail closed，不降级写入 |
| model import collision | deterministic remap；绝不覆盖 existing system object |
| legacy migration 中途失败 | system transaction rollback；project 不变；receipt 不写 |
| dirty legacy edit session | 恢复为 system dirty session，等待 Save/Discard |
| source syntax/import error | 显示真实 sidecar startup diagnostic；不加载隐藏 baseline |
| source baseline 不同 | 标记 locally modified，继续运行 |
| 当前进程启动后 source/lock 又被修改 | 阻止 run 并要求重启，避免记录与实际执行不一致 |
| preflight 后模型或源码变化 | stale error，要求重新 preflight |
| 历史 source snapshot 缺失 | 历史结果仍可读，但 diagnostics 明确 provenance artifact missing |

## 17. 轻量验证策略

M8B 不恢复重型 fixture。完成门使用以下小型纵向切片：

1. **No-project model smoke**：sidecar Ready 后不打开 project，列出 starter nodes/schemes，修改草稿、undo、discard；
2. **Two-project sharing**：创建两个空 project，在系统库复制并修改一个 Evidence；A/B 都读取相同 node hash，两个 project database 不出现第二份 editable canonical state；
3. **Snapshot isolation**：Project A 运行一次，修改 system node，再由 Project B 运行；A 的旧 RunSnapshot/result bytes 不变，B 锁定新 hash；
4. **Project move**：移动 Project A 后仍可打开历史 run；新 run 使用当前软件副本的 system model；
5. **Legacy import**：一个微型 v0.1 project 分别覆盖 exact reuse、new ID、conflicting ID remap、dirty draft recovery 和幂等 reopen；
6. **Source identity**：未修改、修改、增加、删除文件状态正确，路径/mtime 不影响 tree hash；
7. **Source snapshot**：相同 hash 在同一 project 复用 artifact，修改后产生新 artifact，archive 不含用户数据；
8. **Minimal operator extension**：在 disposable release copy 增加 operator、重启、catalog 出现、微型 recipe/run 成功并记录新 source hash，随后删除副本；
9. **WinUI focused smoke**：无 project 可打开 Model Studio，创建 project 后导入/运行入口可用，关闭 dirty model session 仍显示三选项；
10. **Portable rebuild**：M8A builder 生成含 system baseline 的 ZIP，仓库外解压后模型编辑跨两个 project 共享，zero TCP listener 保持不变。

测试只断言持久化、共享、快照和扩展工作流，不断言 starter Evidence 的 D/A/U 或能力 posterior 科学正确。

## 18. 分阶段实施

M8B 拆为三个连续、可独立验证的内部阶段：

| 阶段 | 内容 | 退出条件 |
|---|---|---|
| M8B-0 Ownership correction | SystemApplication、system store、project/model 分离、no-project model RPC、legacy migration | 两 project 共享模型且历史 snapshot 不变 |
| M8B-1 Source provenance | source/dependency/operator identities、preflight/run contract、source snapshot artifact、diagnostics | 修改 source 后新 run 锁定新 identity，旧 run 不变 |
| M8B-2 Extension handoff | private dependency tool、最小 operator 示例路径、portable rebuild/smoke、M8B 开发文档 | release copy 可完成新增 operator 轻量闭环 |

执行继续采用 INLINE、小型垂直切片与 focused tests。每个阶段只在必要边界使用 contract-first；不为普通专家每次保存增加测试门、审批或发布操作。

## 19. M8B 完成定义

只有同时满足以下条件，M8B 才可称为 engineering verified：

- 当前软件副本只有一个 system model library 和一棵 active backend source；
- Project A/B 共享节点与方案，project creation 不复制 editable model；
- Model Studio 无 project 可用，Session/Run 明确要求 project；
- legacy project-local models 和 dirty edits 无损、幂等迁移；
- 每次 run 在 project 中冻结 exact model/source/runtime/operator identity；
- 系统模型或源码改变不改写历史 result；
- 专家可通过前端自由改模型，通过普通编辑器自由改 Python core；
- source/model divergence 只记录、不阻止运行；
- portable ZIP 从仓库外通过双 project、live source 和 zero-listener smoke；
- 文档明确区分 system、project、source、RunSnapshot 和科学状态。

M8B 完成不表示 M8C/M8D/M8E、M7 用户最终验收或专家科学校准完成。

## 20. 候选决策

以下口径在用户确认本书面规格后写入 `DECISIONS.md`：

| 候选 ID | 决策 |
|---|---|
| C-M8B-01 | 每套解压软件副本在 `system/` 中拥有唯一 canonical ModelNode/TaskScheme 库；不使用 `%LOCALAPPDATA%` 或 project-local current model |
| C-M8B-02 | SystemApplication 在 project 之前启动，Model Studio 无 project 可用；ProjectApplication 只拥有 Session/Run/Result/artifact |
| C-M8B-03 | run 从 system current state 冻结 exact model closure 和 source identities 到 project RunSnapshot，之后只执行 snapshot |
| C-M8B-04 | legacy project-local model 自动、事务化、无覆盖合并；dirty draft 恢复为 system dirty edit session |
| C-M8B-05 | source/model baseline 偏离只记录，不审批、不阻止；语法/import/contract 错误不得静默回退 |
| C-M8B-06 | 项目切换不切换 system model/edit session；复制整套软件才形成并列 system/source 分支 |

## 21. 受影响文档

规格批准后必须同步修订：

- `DECISIONS.md`：正式加入 M8B ownership/provenance 决策，并限定 D-041/D-042/D-048/D-056 的 project/global 措辞；
- `01_PRODUCT_OVERVIEW.md`：加入 system model store 与 project data store 的三层图；
- `06_VISUAL_GRAPH_EDITOR_DESIGN.md`、M7 规格：把“global”明确为 software-copy scope；
- M6 runtime/persistence 规格：ProjectApplication 不再拥有 current model；
- M8 总体路线图、M8A 发布规格、release README：加入 `system/`、baseline 与首次创建项目流程；
- `11_IMPLEMENTATION_STATUS.md`：按 M8B-0/1/2 的真实完成状态更新，不提前宣告整个 M8B 完成。
