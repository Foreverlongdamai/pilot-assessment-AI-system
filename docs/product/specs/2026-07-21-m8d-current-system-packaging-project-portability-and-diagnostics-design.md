# M8D Current-System Packaging, Project Portability and Diagnostics Design

> **状态：用户已于 2026-07-21 批准取消专用 backup/restore 功能，并确认发布包应携带当前已保存的 system model；同日完成规格复核、实施与 fresh engineering verification。M8C-1、M8E 和 M7 用户验收仍未关闭。**

| 字段 | 值 |
|---|---|
| 里程碑 | M8D |
| 执行方式 | INLINE、轻量垂直切片 |
| 上游 | M6 managed project、M8A portable builder、M8B system ownership/source provenance、M8C-0 documentation pipeline |
| 下游 | M8C-1 final manuals、M8E clean release candidate |
| 科学边界 | 不校准 Evidence、BN、阈值或 CPT；`formal_run_authorized=false` |

## 1. 目标

M8D 不再建设 `.paprojbackup`、Backup/Restore UI 或另一套项目封装格式。它只关闭三个实际交付缺口：

1. 正式打包能够携带专家已经在前端保存的当前 `system/model-library.sqlite3`，而不是静默回退到 starter seed；
2. 用户 project 继续作为自包含目录，在软件关闭后通过普通文件夹复制完成移动；
3. 现有 Diagnostics 页面和发布清单能够说明当前系统模型、Python source、runtime 和 project compatibility 状态。

这使产品保持一套清晰 ownership：系统模型随软件副本交付，用户数据留在用户 project 中。

## 2. 已确认的实现缺口

M8B 已让每套软件副本拥有自己的 `system/`，但当前 `tools/release/build_portable.py` 仍在每次构建时调用 starter initializer，并硬编码期待 `53` 个节点和 `1` 个 TaskScheme。开发版 WinUI 实际使用仓库下的 `.pilot-assessment-local/system/`。

因此，专家在前端新增、复制或修改节点后，即使选择“保存全部”，旧构建器也不会把这套 current system 带入新 ZIP。当前开发 system 已经可以与 starter cardinality 不同，这正是通用专家设计器的正常状态，不应被发布流程重置。

M8D 必须删除这一静默回退。发布成功只能表示“明确选定的 current system 已被捕获”，不能表示“重新生成了一套看似干净但丢失专家修改的 starter system”。

## 3. 方案选择

### 3.1 采用：显式选择 current system 作为发布输入

正式构建命令使用显式 `--system-source <system-directory>`。典型输入是：

- 开发版：`.pilot-assessment-local/system/`；
- 某个已解压软件副本：`<PilotAssessment>/system/`。

构建器不根据最近打开目录、环境变量或时间戳猜测 system，也不在输入缺失或无效时回退到 starter seed。工程测试若需要全新 starter system，必须使用单独、明确标记为 engineering-only 的 seed fixture 路径。

### 3.2 不采用：继续每次重新 seed

该方案可重复，但会丢失前端保存的 current nodes、TaskSchemes、CPT 和布局，直接违背系统级模型库的产品含义。

### 3.3 不采用：把整个现有软件目录直接冒充新正式 release

关闭软件后复制整个目录可以形成独立工作副本，也能保留 `system/` 和 `backend/src/`；但旧 checksums、baseline 和 release manifest 会把后续修改正确标记为 local divergence。它适合工作副本传递，不应冒充重新基线化的 M8E 正式 release。

## 4. 权威 ownership

```text
一套软件副本
├── backend/src/                         当前 Python 实现
├── system/model-library.sqlite3         已保存的 current Evidence/BN/CPT/task/layout
├── system/staging/model-edit/            当前软件副本的编辑会话
└── manifest/                             本次打包捕获的 source/model identities

用户 project
├── project.json + project.sqlite3
├── sessions/
├── artifacts/
└── immutable RunSnapshots/results
```

- 前端普通模型编辑先进入 `system/staging/model-edit/`；只有“保存全部”后才成为 canonical system state。
- Python 修改进入当前活动 `backend/src/pilot_assessment/`，关闭并重启软件后生效。
- 每次 run 继续把 exact system model closure 和 loaded Python source identity 冻结到目标 project。
- project 不拥有 current model library；system 不拥有 Session、Run、Result 或用户 artifact。

## 5. Current-system capture contract

### 5.1 构建前置条件

构建器必须在复制前验证：

1. `--system-source` 是现有目录，且 `system.json`、`model-library.sqlite3` 存在；
2. system writer lock 可以非阻塞取得，证明该软件副本没有运行；
3. canonical SQLite integrity、foreign keys、schema 和 locator identity 有效；
4. `clean_shutdown=1`；
5. edit workspace 与 canonical 基线一致且没有未保存修改；
6. 不存在 WAL/SHM 等活动数据库临时状态；
7. system database 中的 project/session/run/result/artifact owner tables 没有用户数据；
8. system schema 不高于构建器支持的版本。

任何一项失败都必须停止构建并给出可操作信息，例如“关闭软件”“先选择保存全部或放弃全部”“选择正确的 system 目录”。不得自动放弃草稿、覆盖输入或新建 starter fallback。

### 5.2 一致复制

构建器先证明 source 不存在 WAL/SHM，再以 `mode=ro&immutable=1` 打开 SQLite，使检查本身也不会在 source 生成共享内存文件；随后在持有 source lock 时使用 SQLite consistency mechanism 创建目标 canonical database，而不是在数据库可能变化时做无保护的字节复制。目标包创建一套与 copied canonical state 对齐的 clean edit workspace；不需要把原软件副本的 undo/redo 历史、lock handle 或 transient files 交给下一位用户。

`legacy_system_model_import_receipts` 是旧 project 模型迁入 system 时留下的源软件本地迁移收据，不是 Evidence、BN、CPT 或任务方案定义。它可能包含旧 project ID，因此允许它存在于被选中的 source system，但捕获过程必须在目标 SQLite 中安全清除并压实该表，同时保持 source 完全不变。真正的 project/session/run/result/artifact owner tables 仍必须为空；不得以此放宽用户数据边界。

这项内部一致复制只是 release staging mechanism，不是面向用户的备份产品，也不产生 `.paprojbackup`。

### 5.3 任意模型规模

发布验证不得再要求 exactly `53` nodes / `1` scheme。它从 captured system 计算并记录：

- `model_library_id`；
- canonical model identity hash；
- node/scheme counts；
- starter lineage；
- capture mode；
- canonical/edit-workspace hashes；
- source schema/format version。

验证器只比较 manifest 声明与包内事实，不把任何 starter 数量、名称或连接方式当作 engine limit。

### 5.4 发布时点与“同步”含义

前端保存后，修改立即对同一软件副本打开的所有项目和未来 run 生效。执行一次新的正式构建后，该时点的 canonical system snapshot 进入新发布包。

这里的“同步”不是云同步或对已分发副本的远程更新。已经交给其他人的旧软件目录继续独立演化；需要分发新模型时重新生成并交付一个新包。

## 6. Python source 边界

M8A/M8B 构建器继续从当前开发 source tree 打包 Python、C#、依赖声明和工具。M8D 不创建第二套 Python source owner，也不从 system database 生成 Python 代码。

若专家修改的是一个已解压产品中的 `backend/src/`：

- 该副本立即使用这套 source；
- 关闭后复制整个软件目录可以传递工作副本；
- 需要重新生成具有新 checksums/SBOM/baseline 的正式 release 时，应在完整开发/发布源树中纳入相同修改后运行 M8E builder。

M8D 不建设应用内源码编辑器或“把任意安装目录反编译为开发仓库”的流程。

## 7. Project portability

用户 project 已使用相对受管引用。项目移动采用普通文件系统语义：

1. 完全关闭 Pilot Assessment 软件，确保 SQLite 和 artifact transactions 已关闭；
2. 复制完整 project 根目录，不能只复制数据库或 `sessions/`；
3. 在目标机器/目录通过“打开项目”选择复制后的 project；
4. backend 执行现有 locator、path containment、integrity、schema compatibility 和 recovery checks；
5. 历史 RunSnapshot、result 和 artifacts 保持原 identity；未来 run 使用目标软件副本当前的 system model。

M8D 不提供 Backup、Restore、Merge、Cloud Sync 或覆盖目标目录的按钮。应用运行时复制 project 不属于支持流程，因为 SQLite/WAL 或进行中的 artifact transaction 可能尚未完成。

## 8. Compatibility 与 diagnostics

现有 schema migration registry 和 transaction rollback 继续负责软件可理解的旧 project。较新且不受支持的 schema 必须拒绝打开，不得猜测降级。

M8D 复用现有 Diagnostics 页面，不生成包含原始 Session 的 support archive。页面或可复制文本至少应能说明：

- product/backend/protocol/runtime version；
- active system model identity 与 node/scheme counts；
- loaded backend source identity、baseline divergence 和 restart-required 状态；
- 当前 project 是否打开、project format/schema 与 recovery state；
- operator catalog identity；
- 最近 sidecar error。

普通界面继续隐藏 UUID/hash；Diagnostics 属于明确的技术区域，可以展示精确 identity。任何将来新增的诊断导出默认不得包含 raw modalities、pilot-camera、participant identity 或 project absolute path。

## 9. M8C 文档迁移

文档 catalog 中未发布的 `PAS-BACKUP-001` 改为：

| 字段 | 新值 |
|---|---|
| document ID | `PAS-PORTABILITY-001` |
| 中文标题 | 系统分发、项目迁移与故障排查 |
| 英文标题 | System Distribution, Project Portability and Troubleshooting |
| dependency | M8D |

该手册说明 current-system packaging、整个软件目录复制、整个 project 目录复制、关闭应用要求、版本兼容和 diagnostics。它不得暗示产品存在 `.paprojbackup` 或 Backup/Restore UI。

M8C-1 与总册的聚合引用相应迁移到新 document ID。旧 M8 roadmap/self-review 中关于 backup 的文字保留为历史提案时，必须增加被本规格和 D-077 取代的明确适用性说明。

## 10. Failure semantics

| 条件 | 行为 |
|---|---|
| system 正在使用 | 构建失败，要求关闭软件 |
| 有未保存模型编辑 | 构建失败，要求在前端保存或放弃并关闭 |
| system integrity/schema/identity 不一致 | 构建失败，不创建可交付 ZIP |
| system 含 user-owned rows | 构建失败，列出违规 owner 类别，不复制数据 |
| source system 在 staging 中途发生错误 | 删除构建 staging；source system 不变 |
| project copy 缺文件或损坏 | 正常 project.open 校验失败；不自动“修复”或覆盖 |
| 新版本无法理解 project/system schema | 明确 compatibility error；不静默 seed 或降级 |

## 11. 轻量验证

M8D 只需要以下小型证据：

1. 在 disposable system 中复制/修改一个节点和一个 TaskScheme，Save All、关闭，再作为 `--system-source` 构建；目标包精确包含修改后的 identity/counts/content；
2. 有 dirty edit session、活动 writer、损坏 database 或 user-owned rows 时构建被拒绝；
3. captured package 的 clean edit workspace 可启动、再次编辑、保存和运行；
4. 发布包扫描不含 project、Session、Result、pilot-camera 或开发机绝对路径；
5. 一个 micro project 在软件关闭后整体复制到新目录，能够 reopen 并回读已有 Session/RunSnapshot/result/artifacts；
6. Diagnostics 显示与 manifest/backend 实际一致的 system/source/runtime identities；
7. 现有 focused Python、desktop unit、real-sidecar contract 和 portable verifier 保持通过。

不生成长 session、大量图像、全模态压力 fixture 或领域科学 golden。

## 12. 明确排除

- `.paprojbackup` 或 `.pasystembackup`；
- Backup/Restore UI、自动周期备份、云同步和多用户 merge；
- 自动更新已经分发的软件副本；
- 把用户 project 或测试 Session 放进产品 ZIP；
- 自动覆盖旧软件目录或现有 project；
- 默认加密、密钥管理或上传 diagnostics；
- 从 historical RunSnapshot 自动执行旧 Python source；
- 专家 Evidence/BN/CPT 的科学审批或校准。

## 13. 退出门

M8D 只有在以下条件全部满足后才完成：

- 正式 builder 不会静默回退到 starter system；
- 明确选定、已保存并关闭的 current system 被一致捕获到 package；
- 任意 node/scheme cardinality 可通过 manifest 驱动的验证；
- 用户数据不进入产品包；
- 整体 project 目录复制后的 reopen/replay 通过；
- Diagnostics 足以区分 system model、Python source、runtime 和 project compatibility；
- catalog、路线图、README、known limitations 与手册不再承诺 backup/restore 功能；
- 轻量验证记录已保存，M8C-1/M8E 仍按真实状态保持未完成。

## 14. 决策取代关系

本规格和 D-077 取代：

- M8 Productization Design Outline §10 中 `.paprojbackup` 候选；
- M8 Pre-UAT Implementation Outline §7 中 Backup/Restore UI、restore contract 和 backup tests；
- C-M8-07/C-M8-08 中把 backup 作为 M8 completion gate 的部分；
- M8C catalog 的未发布 `PAS-BACKUP-001`。

M6/M8B 关于 managed project、relative references、system ownership、RunSnapshot 和 source identity 的现有实现继续有效。
