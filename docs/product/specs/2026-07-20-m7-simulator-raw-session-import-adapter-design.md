# M7 Simulator Raw Session Import Adapter Amendment

| 字段 | 值 |
|---|---|
| 设计基线 | M7 v0.4 amendment |
| 日期 | 2026-07-20 |
| 状态 | Review candidate；产品概念已确认，书面合同待复核 |
| 上游 | M6 Local Runtime Persistence and Protocol Design；M7 WinUI Expert Designer Design；Session Bundle Specification |
| 拟写决策 | D-060、D-061 |
| 科学状态 | 不改变 starter Evidence、BN、CPT 或 `formal_run_authorized=false` |

## 1. 目的

模拟器的正常导出边界允许只有：

```text
<raw-session-root>/
  streams/
  annotations/
```

用户不需要在模拟器侧生成 `manifest.json`、checksum 清单、标准 annotation
文件、任务 reference 或未采集模态。产品必须在导入期间把该原始目录转换为项目内的
canonical Session Bundle，并继续兼容已经包含 `manifest.json` 的标准 Bundle。

本修订解决当前 M6/M7 将“外部原始导出”和“内部标准 Bundle”混为同一输入合同的问题。
它不改变 M1-M6 对 canonical Session Bundle、同步、Evidence、BN、RunSnapshot 和受管项目
存储的权威语义。

## 2. 不变量

1. 原始目录只读；导入不得写入、重命名或删除其中任何文件。
2. 缺失模态只声明 `missing` 或 `not_applicable`，不得生成合成 EEG、ECG、Gaze、图像或其他传感器值。
3. manifest 是项目内 canonical Session Bundle 的系统合同，不是要求模拟器提供的采集文件。
4. 用户输入单位、任务、参与者等元数据不会改写原始值，只影响明确的解释、映射和后续计算。
5. 当前可计算 Evidence 正常执行；依赖缺失输入的 Evidence 产生 omitted observation，不把缺失解释为差表现。
6. 轨迹飞得差、控制剧烈或生理数值异常仍是可计算表现，不得被 raw import adapter 当作质量门槛过滤。
7. 标准 Bundle 的 byte-preserving managed import、历史 session revision 和历史 RunSnapshot 不变。

## 3. 方案选择

### 3.1 采用：受管 staging 中生成 canonical Bundle

产品先只读检查原始目录，用户补齐无法可靠推断的语义字段；导入时把原始文件复制到项目
staging，生成 canonical annotation、manifest 和 checksum，完成全部既有 M1/M2 校验后再原子
promote。这是唯一采用的产品路径。

优点：不污染原始数据；保留现有运行合同；结果可迁移、可校验、可复现；标准 Bundle 与原始
导出的后续流程可以汇合。

### 3.2 不采用：在模拟器原始目录中写 manifest

该方案会修改用户原始采集目录，可能遇到只读介质、权限、文件同步和误删问题，也无法保证
manifest 与受管副本完全一致。

### 3.3 不采用：取消 manifest，每次运行重新扫描文件

该方案会让字段、单位、时钟、缺失状态和文件身份在每次运行时重新猜测，破坏 immutable
RunSnapshot、session revision 与可重复计算。

## 4. 两种外部来源

统一产品入口名为“导入 Session 数据”／“Import Session Data”。后端自动识别：

| `source_kind` | 判定 | 行为 |
|---|---|---|
| `canonical_bundle` | 根目录存在普通文件 `manifest.json` | 委托既有 `session.inspect`/managed import，不重写 manifest |
| `simulator_raw` | 无 manifest，存在普通目录 `streams/` 和 `annotations/` | 进入本修订的 probe、mapping、resolution 和 materialization 流程 |

不得仅根据任意子目录名或某个 CSV 文件猜测 `simulator_raw`。两类均拒绝 symlink、junction、
reparse point、路径穿越、非常规文件和越界路径。存在 manifest 但 manifest 无效时必须按无效标准
Bundle 报错，不能静默降级为 raw import。

## 5. Raw inspect 合同

### 5.1 只读 probe

`simulator_raw` inspect：

1. 枚举 `streams/` 与 `annotations/` 的安全相对路径、byte size、media candidate 和 SHA-256；
2. 以已注册 profile 的文件 matcher、表头和 schema signature 选择零个或一个明确 profile；
3. 读取有界的结构信息，例如 CSV header、Parquet schema、图像尺寸和 annotation JSON shape；
4. 生成 modality、字段、时间戳、单位和 annotation 的提议映射；
5. 列出所有必须由用户确认的 unresolved inputs；
6. 产生 `source_snapshot_fingerprint`，但不创建 session ID、不复制文件、不写数据库。

profile 匹配有多个同优先级候选时不得自行选择；inspect 返回候选和稳定错误码，要求用户选择。

### 5.2 Inspect 输出

`RawSessionInspection` 至少包含：

```text
source_kind
source_snapshot_fingerprint
detected_profile_id / profile_candidates
files[]
field_mappings[]
annotation_mappings[]
modality_proposals{}
required_user_inputs[]
warnings[]
can_materialize
```

每个 `field_mapping` 包含 raw path、raw field、canonical field、modality、physical dtype、unit、
unit source、timestamp role 和 resolution status。技术 ID 默认只在“高级详情”展示；普通界面使用
简短语义名称。

## 6. Adapter profile 与用户补充

### 6.1 信息来源优先级

manifest 字段只允许从下列来源产生，并记录 provenance：

1. 文件自身明确声明；
2. 用户选择的、带版本号的 simulator adapter profile；
3. 当前导入界面中用户明确输入或确认；
4. 系统生成的身份、时间、路径和 checksum。

不得从数值范围、列名相似度或样例数据表现静默推断工程语义。

### 6.2 单位规则

- 文件或 profile 已明确单位时，导入预览展示其来源，用户可以修正；
- 未明确单位的映射字段必须在界面中显示为“需要输入”；
- 用户可以从常用单位选择，也可以输入规范化 unit symbol；
- 时间戳单位必须单独确认，不能由采样间隔静默猜测；
- 导入前 backend 验证单位与 canonical field 的物理维度兼容；
- 未解决的必需单位使 `can_materialize=false`，但 inspect 本身成功；
- 用户确认的单位与字段映射保存为可复用 mapping preset，并把 preset ID、版本和 exact resolved
  mapping 写入本次 session provenance。以后修改 preset 不改变既有 SessionRevision。

自由文本单位不会绕过维度校验。若用户确需新增系统不认识的单位，应先在 adapter profile 的 unit
registry 中明确换算或 identity 语义；系统不得仅因为字符串非空就假定可计算。

可信解析代码、schema 和 unit registry 属于系统级、带版本的 adapter profile；用户确认的纯数据
映射属于当前受管项目的 `session_import_profiles` preset，不包含或执行 Python 代码。M7 v0.4 支持
同一项目内复用；跨项目导入/导出 preset 留给 M8 交付工具，不影响每个 SessionRevision 已冻结的
exact mapping。

### 6.3 其他用户输入

界面只要求补齐无法可靠推断且当前导入所需的内容。系统可为非语义身份字段给出安全默认值，
例如随机 pseudonymous ID、文件夹名派生的可读 source label 和当前导入时间；用户可以在导入前修改。
需要处理的字段包括：

- participant pseudonymous ID；
- source session/campaign 的可读名称；
- task profile/scenario；
- task reference 来源与 reference ID（如适用）；
- timestamp unit、master clock 和跨设备 clock mapping（如文件/profile 未声明）；
- 字段单位、坐标系、轴方向或 control convention（仅对应已映射字段）；
- 缺失模态属于 `missing` 还是当前任务明确 `not_applicable`；
- 生理/图像数据存在时的 privacy declaration。

任务方案可以提供 task metadata 和 ModelBundle reference 的默认提议，但导入不会把 Session 永久
绑定到一个 assessment scheme；实际运行仍由用户选择 TaskScheme，并由 preflight 校验兼容性。

## 7. Canonical materialization

### 7.1 受管目录

raw import 在项目 staging 中构造：

```text
staging/imports/<transaction-id>/bundle/
  source/
    streams/                 # 原始 bytes，保留原相对路径 provenance
    annotations/             # 原始 bytes，保留原相对路径 provenance
  annotations/
    phases.json              # canonical；可为空但不得伪造条目
    events.json              # canonical；可为空但不得伪造条目
    baseline_intervals.json  # canonical；可为空但不得伪造条目
  integrity/
    checksums.sha256
  manifest.json
```

manifest stream paths 可以指向 `source/streams/...`，避免复制大型视觉数据两次。若 annotation 输入
已经满足 canonical contract，仍保留 source copy，并由 deterministic normalizer 生成 canonical
representation；空 canonical 文档必须带有“source category absent” provenance，而不是伪造 phase、
event 或 baseline。

### 7.2 manifest 生成来源

| manifest 部分 | 生成来源 |
|---|---|
| `bundle_schema_version` | 当前受支持的 canonical schema |
| `session_id`、`created_at` | import transaction 中生成；inspect 不生成 |
| `source_session` | raw root provenance、profile 和用户输入 |
| `participant` | 用户输入或明确 source mapping |
| `task` | annotation/profile/用户确认；reference 可为 `model_bundle` |
| `session_timebase` | resolved timestamp/clock mapping |
| `streams` | resolved file-to-modality mappings；所有 core modality 均有 descriptor |
| `annotations` | canonical annotation paths 与生成 revision |
| `integrity` | 系统固定 SHA-256 合同和 checksum path |
| `privacy` | 检测到的 biometric modality 与用户确认 |
| `extensions.raw_import` | adapter/preset version、原始相对路径、source fingerprint 和 exact mapping provenance |

`present` stream 必须有路径、checksum、schema、单位和 clock mapping；未采集 stream 使用
`missing`、空 paths/checksums、null clock sync 和非必需 import 状态。不得用 `invalid` 描述差表现。

### 7.3 原子导入

`session.source.import` 带稳定 `transaction_id` 和 inspect fingerprint，并执行：

1. 重新 probe 原始目录并比较 fingerprint；变化则返回 `RAW_SOURCE_CHANGED`；
2. 验证全部 user resolutions 与 profile version；
3. byte-preserving 复制到 staging 的 `source/`；
4. 生成 canonical annotation、manifest 和 checksum；
5. 用现有 ManifestLoader、ingestion readiness 和同步前合同重新验证；
6. 计算 bundle root/file inventory hash；
7. 复用 M6 的 session/revision promotion、SQLite transaction、audit 和 recovery；
8. 原子完成或完整回滚，不留下半导入 revision。

同一 transaction 的重试必须返回同一个 session/revision。M7 v0.4 的一次新 raw import action 默认
创建一个新 Session；不同 transaction 不因 source hash 相同而静默合并。若项目中已存在相同 exact
source fingerprint，界面给出 non-blocking duplicate warning，但仍由用户决定是否导入。把 raw
source 附加为既有 Session 的新 revision 不在本修订范围内。任何路径都不得覆盖已有 revision。

## 8. Partial data 与参考资源

- adapter inventory 始终声明 X、U、I、G、EEG、ECG、pilot_camera；只有实际文件才标记 `present`；
- `required_for_import` 是技术可执行性，不是能力评价门槛；当前 v0.x 至少需要能建立 session
  master timeline，默认仍由 X mapped coverage 提供；
- 非必需模态缺失产生 `ready_partial`；依赖它们的 Evidence source binding 被 omitted；
- omitted Evidence 不生成负面 state/likelihood；BN 使用其余 observations 与先验边缘化；
- Session-local reference 只有实际导出时才进入 `references/`；否则可声明 `source=model_bundle`，
  由运行时锁定的任务方案解析；
- 某 Evidence 需要 reference、phase、event 或 AOI 而当前 Session/TaskScheme 均不提供时，仅该
  Evidence 不可计算，不得自动生成参考数据。

## 9. JSON-RPC 与兼容性

新增产品级方法：

```text
session.source.inspect
session.source.import
session.import-profile.list
session.import-profile.get
session.import-profile.save
```

`session.source.inspect` 自动识别 source kind，并返回 discriminated response：

- canonical：现有 `IngestionReadinessReport`；
- raw：`RawSessionInspection` 与可编辑 `RawImportResolutionDraft`。

`session.source.import` 对 canonical source 委托既有 exact-copy import；对 raw source 执行 §7。
现有 `session.inspect` 和 `session.import` 继续保留，作为 canonical Bundle 的兼容 API；不修改已有
request/response JSON shape。

所有写操作继续使用 transaction ID、乐观状态检查、审计事件和幂等 receipt。stdout 仍只传 JSON-RPC
协议消息，大型数据只传 path/session/artifact identity。

## 10. WinUI 导入界面

Session 页面把“选择 Session Bundle”改为“选择 Session 数据文件夹”。流程：

1. 选择目录；
2. inspect 并显示“标准 Bundle”或“模拟器原始导出”；
3. raw source 显示 profile、文件到输入族映射、annotation 映射和缺失模态；
4. 未声明单位的字段显示可编辑 unit ComboBox（常用建议＋允许输入）；
5. 时间单位、坐标系等 unresolved items 集中显示，完成一项立即由 backend 重新验证 draft；
6. 展示将生成的 manifest 摘要，而不是要求用户编辑原始 JSON；
7. `can_materialize=true` 后启用“导入到项目”；
8. 导入完成后显示 managed SessionRevision、readiness 和各模态 present/missing 状态。

普通界面不显示长 hash、schema ID 或内部 transaction ID；它们放在高级详情和诊断页。中英文只
影响界面标签、帮助和错误提示；用户填写的 canonical 单位、字段和技术内容保持统一英文符号。

## 11. 错误语义

至少定义：

| code | 含义 |
|---|---|
| `SESSION_SOURCE_UNRECOGNIZED` | 既不是标准 Bundle，也不满足 raw root 最小结构 |
| `RAW_PROFILE_AMBIGUOUS` | 多个 profile 同级匹配 |
| `RAW_PROFILE_UNSUPPORTED` | 没有可用 profile |
| `RAW_REQUIRED_INPUT_UNRESOLVED` | 单位/字段/时钟等必需输入尚未完成 |
| `RAW_UNIT_DIMENSION_MISMATCH` | 用户单位与 canonical field 维度不兼容 |
| `RAW_ANNOTATION_MAPPING_INVALID` | annotation 无法按确认映射规范化 |
| `RAW_SOURCE_CHANGED` | inspect 后原始 bytes/inventory 改变 |
| `RAW_MATERIALIZATION_INVALID` | 生成的 canonical Bundle 未通过既有合同 |

所有错误都返回具体 raw path/field、可恢复标记和操作建议，但不得把 Python traceback 暴露到普通
界面。失败不会修改原始目录或创建可见 SessionRevision。

## 12. 轻量验证与验收

### 12.1 Python focused tests

1. 只有 `streams/`、`annotations/` 和轻量 X/U CSV 的 raw fixture 可 inspect；
2. 未知单位列在 `required_user_inputs`，inspect 成功但 import 未启用；
3. 用户提供单位后生成 manifest，resolved units 与 provenance 精确保存；
4. I/G/EEG/ECG/pilot_camera 不生成文件，descriptor 精确为 missing；
5. 原始 source bytes/hash 和目录内容在成功/失败导入前后完全不变；
6. source 在 inspect/import 间改变时返回 `RAW_SOURCE_CHANGED`；
7. canonical annotation 缺项生成明确的空文档，不生成虚构 interval/event；
8. 生成 Bundle 通过 ManifestLoader/readiness 并进入 managed SessionRevision；
9. 标准 Bundle 继续走现有 exact-copy path，既有 tests 不变；
10. 一个依赖缺失 G 的 Evidence omitted，一个仅依赖 X/U 的 Evidence computed，BN 运行完成。

测试只使用一个小型 fixture，不生成大量帧、长时序或多套数据。

### 12.2 C#/RPC/UI verification

1. source-kind union、raw inspection、resolution 和 import response 可跨语言序列化；
2. ViewModel 在 unresolved unit 存在时禁用 Import，填写后启用；
3. 用户取消 picker/inspect/import 时不改变项目；
4. 中英文切换覆盖新增标签与 typed errors；
5. x64 Debug build 通过；
6. 启动真实 WinUI，确认目录选择、raw preview、单位输入和 managed import 页面可操作。

### 12.3 产品验收

用户拿到只有 `streams/` 和 `annotations/` 的模拟器导出目录时，不需要理解或手写 manifest；在
界面补齐系统无法可靠知道的单位/任务元数据后，可以导入受管项目。系统生成的 manifest、checksum
和 canonical annotation 可在高级详情中查看；缺失模态清晰显示但不阻止已有数据的部分评估。

## 13. 文档取代与后续更新

批准后：

- 在 `DECISIONS.md` 写入 D-060（raw export 在受管 staging 中 materialize canonical Bundle）和
  D-061（不猜测未声明工程语义，单位由 profile 或用户明确输入）；
- 修订 M6 spec §6.1，明确其只描述 canonical Bundle 分支；
- 修订 M7 spec §12 Session Import，加入统一 source import；
- 修订 `03_SESSION_BUNDLE_SPEC.md`，明确 canonical manifest 是内部/标准交换合同，不是模拟器
  原始导出义务；
- 更新产品 README、GLOSSARY、implementation status 和 M8 文档大纲；
- 实施完成前不得宣称 WinUI 已支持 raw simulator import。
