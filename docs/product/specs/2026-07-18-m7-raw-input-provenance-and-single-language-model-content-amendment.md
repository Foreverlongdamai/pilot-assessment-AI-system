# M7 Raw-Input Provenance and Single-Language Model Content Amendment

| 字段 | 值 |
|---|---|
| 设计基线 | M7 v0.2 amendment |
| 日期 | 2026-07-18 |
| 状态 | 已批准并实现；D-054 画布部分已可见验证，D-055 单语 current-model contract、持久化与 current-system 迁移已由 M8E 完成 |
| 上游 | M7 WinUI Expert Designer and Task Activation Workspace Design |
| 决策 | D-054、D-055（已写入 `DECISIONS.md`） |
| 科学状态 | 不改变 starter Evidence、BN、CPT 或 `formal_run_authorized=false` |

> **后续取代说明：** 本文 D-054 的绿色输入族与 typed provenance 继续有效；输入族固定显示、统一平移、顶层筛选和保存边界已由 [M7 Staged Edit Session and Five-Layer Canvas Amendment](2026-07-18-m7-staged-edit-session-and-five-layer-canvas-amendment.md) 的 D-056/D-057 取代。D-055 的实现与 legacy compatibility 口径由 [M8E Final Release Candidate Design](2026-07-21-m8e-final-release-candidate-and-handoff-design.md) 及其实施计划收口。

## 1. 目的与取代关系

本修订只收口两项 M7 用户验收发现：

1. Model Studio 主画布需要在现有细粒度 Raw Input 节点左侧增加五个更醒目的原始输入族入口，并让细粒度节点能够沿可视化溯源关系回到输入族；
2. 软件界面的中文／英文切换与专家模型内容语言必须彻底分离。界面文字随语言完整切换，Evidence、BN、operator、TaskScheme 等 canonical 模型内容只保存一套英文文本，不再保存和编辑中英双份名称或说明。

本修订取代以下旧口径：

- M7 规格中 `name_zh/name_en`、`short_name_zh/short_name_en`、`description_zh/description_en` 和 bilingual help text；
- M7 规格 §7.1 中“切换界面语言时同步切换模型节点名称”；
- M7 规格 §14 与旧 M7B Task 13 中的跨语言模型内容 fallback marker；
- D-052 中“后端保存双语模型元数据”的部分。D-052 的任务侧栏、active/dim、独立多浮窗和即时界面语言切换继续有效。

本修订不改变三类 canonical 节点、两类 canonical edge、EvidenceRecipe、BN 方向、任务激活、autosave、RunSnapshot 或 Python 计算边界。

## 2. 已确认的产品口径

### 2.1 主画布

- 保留当前所有细粒度 Raw Input、Evidence 和 BN `ModelNode`；
- 保留它们当前的相对布局、拖拽、缩放、复制、激活和编辑行为；
- 在最左侧增加 `X(t)`、`U(t)`、`I(t)`、`G(t)`、`P(t)` 五个 **Raw Input Family projection nodes**；
- 五个族节点比普通圆形节点稍大，并统一使用绿色，与其他节点类别形成清晰区分；
- 现有蓝色细粒度 Raw Input 节点按照 typed source provenance 连接到对应族节点；
- operator 不成为主画布第四类 canonical 节点。本修订也不新增独立 Operator 菜单；operator 继续在 Evidence 浮动窗口的 recipe graph 与参数页中使用。

### 2.2 语言

- 中文模式下，应用菜单、按钮、字段标题、说明、提示、状态、对话框和错误信息使用中文；
- 英文模式下，上述界面文字全部使用英文；
- 发布构建中不得显示中英并排文本、`[EN fallback]`、`[中文回退]` 或其他面向用户的缺失翻译标记；
- 模型名称、描述、help text 以及其他专家定义的模型文本只保存英文 canonical value；状态、按钮、节点类别等应用标签属于 UI localization；
- 切换界面语言不翻译、复制或改写模型内容，也不产生 backend mutation、revision 或 hash 变化。

## 3. 三种对象不能混淆

| 对象 | 是否 canonical `ModelNode` | 是否进入 backend graph/hash | 是否可被任务激活 | 作用 |
|---|---:|---:|---:|---|
| Raw Input Family projection node | 否 | 否 | 否 | 在画布上汇总 X/U/I/G/P 并提供来源溯源入口 |
| 细粒度 Raw Input node | 是 | 是 | 是 | 保存确切 source descriptor、schema、field/unit/clock 与 Evidence data binding |
| operator recipe node | 否（属于 EvidenceRecipe 内部） | 作为 Evidence 定义的一部分 | 随所属 Evidence | 执行 Evidence 内部计算步骤 |

五个大节点是确定性的前端投影，不创建第二套 Raw Input 数据定义。Evidence extraction edge 仍然从确切的细粒度 Raw Input `ModelNode` 指向 Evidence；不能改成从族节点直接运行计算。

## 4. 五大原始输入族投影

### 4.1 固定身份和视觉

投影使用以下稳定 UI identity，不占用模型库 `node_id`：

| UI identity | 英文界面标签 | 中文界面标签 | 展示含义 | 主题色 |
|---|---|---|---|---|
| `raw-family.X` | `X(t) Flight State` | `X(t) 飞行状态` | 位置、姿态、速度、加速度和其他飞行状态 | 统一绿色 |
| `raw-family.U` | `U(t) Control Input` | `U(t) 操纵输入` | 操纵杆、踏板、推力和控制输入 | 统一绿色 |
| `raw-family.I` | `I(t) Visual Input` | `I(t) 视觉输入` | VR 第一视角及相关视觉采集入口 | 统一绿色 |
| `raw-family.G` | `G(t) Gaze and AOI` | `G(t) 注视与 AOI` | gaze、fixation、stare、AOI 与视野关联 | 统一绿色 |
| `raw-family.P` | `P(t) Physiology` | `P(t) 生理输入` | EEG、ECG 和后续生理模态 | 统一绿色 |

视觉约束：

- 普通节点当前直径为 `116` logical pixels；族节点目标直径为 `148` logical pixels，约大 28%；
- 五个族节点共用一组 light/dark theme-aware 绿色 token，保持文字和边框对比度，并与其他节点类别明显区分；
- 绿色只表达“原始输入族”这一共同类别；圆内必须显示 `X/U/I/G/P`、随界面语言切换的类别短名和 Raw Input Family 图标，以区分五种输入；
- 族节点固定在最左侧独立 lane。现有 canonical layout 只在投影时统一向右平移，不写回 `global_layout` 或 `layout_revision`，因此其相对位置不变；
- 族节点不可复制、删除、归档、激活或打开 canonical node editor。悬停或选择时显示成员、来源数和说明。

### 4.2 族归属计算

归属由 backend 已返回的 typed `RawInputNodeDefinition.family`、`SourceDescriptor.raw_modality` 和 `source_dependencies` 确定，前端不得按节点名称前缀猜测。

| physical/source modality | 画布输入族 | 说明 |
|---|---|---|
| `X` | X | 直接归属 |
| `U` | U | 直接归属 |
| `I` | I | 直接归属 |
| `G` | G | 直接归属 |
| `EEG`、`ECG` | P | P 是 physiology 概念族，物理 stream 仍分别保存 |
| `pilot_camera` | I | 仅作为 UI 的 auxiliary visual-source 归组；它在合同中仍是独立 `pilot_camera` modality，绝不能伪装成飞行员在 VR 中看到的 I(t) scene |

对 derived source，projection 递归读取 `source_dependencies`，连接到其最终闭合到的所有 X/U/I/G/P 族。一个 derived source 可以同时有多条族溯源边。

`task_reference`、session duration、phase/event annotation、AOI definition 等若没有 raw-modality provenance，则显示 `TASK / REFERENCE RESOURCE` 徽标且不伪造族连接。它们仍可以作为合法 typed task/session resource 参与 EvidenceRecipe。

### 4.3 第三种“线”只属于显示层

主画布新增 `family provenance link`，形成：

```text
Raw Input Family projection -> precise Raw Input ModelNode -> Evidence ModelNode
                               family provenance            extraction
```

`family provenance link` 的约束：

- 它不是第三种 canonical `ModelGraphEdgeKind`；
- 它不进入 backend persistence、model hash、TaskScheme、CPT、BN inference 或 RunSnapshot；
- 它由当前 canonical source descriptors 确定性重建；
- 它使用比 extraction edge 更细的实线或淡色连接，并在 legend 中明确标为 `Source family / 来源归属`；
- 鼠标悬停显示完整 provenance path，例如 `P(t) -> EEG.channels -> H5`；
- 当前任务启用细粒度节点时，族节点和对应 link 正常高亮；没有任何活跃成员时，族节点降低不透明度但仍保留在画布上；
- 用户不能直接创建、删除或反转该 link。修改确切 source descriptor 后，投影自动重算。

这样既满足直观溯源，也不会把显示归属误保存成 Evidence 数据依赖或 BN 概率关系。

## 5. Canonical 模型内容改为单一英文

### 5.1 新字段

当前模型合同升级为单语言内容版本。`ModelNode` 与 `TaskScheme` 的公共文本收口为：

```text
name
short_name
description
```

`RawInputNodeDefinition`、`EvidenceNodeDefinition` 与 `BnNodeDefinition` 的帮助文字收口为：

```text
help_text
```

以下对象已经只有一套文本，继续保持单一英文内容：

- `OperatorDefinition.name/description/pseudocode`；
- operator ports、parameter UI metadata；
- `EvidenceRecipe` anchor、input/output、documentation、state labels；
- BN state labels、documentation 和 reporting metadata；
- TaskScheme 名称、说明、group/tags。

系统不使用自动语言识别阻止专家保存，也不尝试自动翻译。文档和字段提示明确要求 canonical model content 使用英文；平台只验证非空、长度、schema 和可执行性。

### 5.2 版本与迁移

- 新写入的 `model-node` 与 `task-scheme` 使用新的 contract version，并只输出单语言字段；
- legacy `0.1.0` reader 继续用于历史数据库、导入和 immutable RunSnapshot replay；
- 迁移优先取 `name_en/short_name_en/description_en/help_text_en`；
- starter/current 对象若英文值缺失，使用由稳定 ID 生成的明确英文占位内容并记录 migration diagnostic，不能把中文静默标成英文，也不能调用在线翻译；
- legacy 中文值只留在原始 migration/audit payload 或旧 RunSnapshot 中，不继续成为 current canonical editable field；
- 数据库迁移在一个 transaction 中完成，重新计算新合同 content hash，并保留旧 hash、migration event 与 lineage；
- 历史 RunSnapshot 保持原字节和原 hash，不原地重写。回放 adapter 将旧双语对象投影为单一英文只读视图；
- UI 与 JSON-RPC current-model DTO 同步改为 `Name/ShortName/Description/HelpText`，不再暴露 current `NameZh/NameEn` 等成对字段。

## 6. 界面本地化与模型内容语言彻底分离

### 6.1 界面本地化

以下内容必须由 localization resources 提供，并在语言切换时刷新所有已打开页面、对话框和独立节点窗口：

- shell、NavigationView、CommandBar、页面标题和工具栏；
- 表单字段标题、占位提示、帮助说明、确认对话框；
- validation、autosave、conflict、backend、run/result 与错误状态；
- graph kind/status/active/inactive 标签、legend、tooltip 的界面部分；
- accessibility name、automation text 和 screen-reader status。

发布前执行中英文 resource-key parity 检查。任一 UI key 缺失即为 build/packaging blocker，而不是运行时显示英文 fallback 的正常路径。

### 6.2 不随界面语言变化的内容

以下内容不翻译：

- 专家创建或修改的 Evidence、BN、Raw Input、operator 和 TaskScheme 英文内容；
- node/scheme/operator/source ID；
- Python implementation path、schema ID、parameter key、JSON field、formula；
- session 文件名、hash、revision、timestamp、单位和原始数据值。

示例：中文界面中字段标题显示“名称（系统内容使用英文）”，字段值仍为 `Task Control Proficiency`；切换到英文后标题变为 `Name (canonical content in English)`，字段值逐字不变。

### 6.3 编辑器

- Raw Input、Evidence、BN 与 TaskScheme 编辑器各只显示一个 Name、Short name、Description 和 Help text 输入面；
- 不再左右并排显示“中文名称／英文名称”；
- operator recipe 参数的 key、operator-authored label/help 属于英文 canonical content；应用提供的“参数”“保存失败”“输入数值”等外围提示随界面语言切换；
- 所有正常编辑仍通过 typed JSON-RPC mutation 保存到 Python backend canonical definitions；语言切换本身不发送 mutation。

## 7. 明确不做的工作

本修订不包括：

- 新增独立 Operator Library 菜单；
- 把 operator 放入主画布；
- 改变现有 Evidence/BN 节点关系或 starter CPT；
- 重新排列现有 canonical 节点的相对布局；
- 把 pilot camera 合并进 I(t) 数据合同；
- 自动翻译专家模型内容；
- 判断专家输入的英文是否科学正确；
- 修改 Python operator 源码扩展机制或 M8 打包方案。

## 8. 保存、运行与历史语义

- 五个 family projection nodes 与 provenance links 是显示投影，不产生 canonical save；
- 细粒度 Raw Input、Evidence、BN、TaskScheme 和 operator parameters 的编辑继续保存到 backend canonical repository；
- 单语言合同迁移后，任何真实模型内容修改继续增加 semantic revision 并改变 content hash；
- 切换界面语言只修改本机 UI preference，不改变 model/session/project/run 状态；
- `run.start` 继续冻结当时 exact single-language current objects；legacy run 继续冻结和回放旧对象，不因迁移被改写。

## 9. 验收条件

### 9.1 画布

1. 任何 Model Studio 图始终在最左侧显示 X/U/I/G/P 五个较大、统一绿色、文字清楚的族节点，并且绿色与其他节点类别显著区分；
2. 普通节点直径保持 116，族节点直径为 148；
3. X/U/I/G/EEG/ECG/pilot-camera raw streams 按 §4.2 显示正确 provenance link；
4. derived raw/task resource 根据 source dependency closure 显示零条、一条或多条真实族溯源，不按名称猜测；
5. 无 raw provenance 的 task/reference resource 不产生错误连线；
6. 从族节点沿 provenance + extraction 可以追到使用它的 Evidence；
7. provenance link 不出现在 backend edge list、hash、TaskScheme、RunSnapshot 或 BN 中；
8. 现有节点相对布局和 stored layout revision 不因新增 lane 改变；
9. light/dark theme、active/dim、搜索过滤与 zoom/fit 下仍能辨认五个族节点和连接。

### 9.2 语言与模型内容

1. 中文模式下没有可见的英文 UI fallback；英文模式下没有可见的中文 UI 文本；
2. 模型内容字段在两种界面语言下逐字相同且为单一 canonical value；
3. 当前编辑器、C# DTO、Python current contracts 和 JSON-RPC 不再要求成对 `*_zh/*_en` 字段；
4. 切换语言不产生 model mutation、revision、hash 或 audit event；
5. 所有已打开节点窗口和当前页面即时刷新 UI labels；
6. legacy current objects 能确定性迁移，旧 RunSnapshot 能保持原 hash 回放；
7. 现有 starter 节点和方案的英文内容迁移后语义不变；
8. 中英文 localization keys 一一对应且所有代码引用 key 均存在。

### 9.3 验证边界

验证保持轻量：

- projection unit tests：五个族节点、尺寸、位置 offset、direct/derived provenance、pilot-camera UI 归组和 task-resource 无伪连接；
- localization tests：resource parity、运行时刷新、模型内容不变；
- contract/migration tests：v0.1 bilingual -> vNext English、hash/revision/audit 和 legacy snapshot replay；
- one tiny real-sidecar graph smoke；
- WinUI x64 Debug build 与一次可见界面验收。

这些测试只证明展示、迁移、保存和运行合同一致，不证明任何 Evidence、BN 或 CPT 科学有效。

## 10. 文档批准后的收口动作

本文档经用户复核批准后，实施计划必须先完成：

1. 在 `DECISIONS.md` 写入 D-054（五大输入族投影与 provenance link）和 D-055（界面本地化与英文 canonical content 分离）；
2. 修订 M7 规格 §3.1、§3.2、§4.2、§7.1、§14 及 D-052 当前适用性；
3. 修订产品 README、`06_VISUAL_GRAPH_EDITOR_DESIGN.md`、`08_WINDOWS_FRONTEND_DESIGN.md`、GLOSSARY、implementation status 和 M7B roadmap 的双语旧口径；
4. 版本化 Python/C# current contracts、SQLite migration 和 JSON-RPC DTO；
5. 实现 GraphProjection family lane/provenance、单字段编辑器和完整 UI localization audit；
6. 完成 §9 的轻量验证后交给用户继续 M7 手动验收。
