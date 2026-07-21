+++
document_id = "PAS-ARCH-001"
language = "zh-CN"
title = "产品总览与系统架构"
short_title = "产品总览与架构"
product_version = "0.1.0"
document_version = "0.1.0"
status = "review"
audience = ["evaluator", "expert", "developer", "maintainer", "release"]
information_types = ["explanation", "reference"]
scope = "解释 Pilot Assessment System 的产品边界、角色、容器、数据所有权、模型结构、计算方向和扩展方式。"
prerequisites = []
scientific_status = "engineering-only"
related_documents = ["PAS-QUICKSTART-001", "PAS-EVALUATOR-001", "PAS-EXPERT-EVIDENCE-001", "PAS-EXPERT-BN-001", "PAS-SESSION-001", "PAS-PYTHON-EXT-001"]
support = "遇到问题时保留产品版本、错误 ID、Diagnostics 摘要和对应 project 的脱敏说明。"
+++

# 产品总览与系统架构

## 1. 这套产品解决什么问题

Pilot Assessment System 是一套离线 Windows 软件，用来把飞行仿真 Session 中的多模态原始数据转换为可解释的 Evidence，再通过专家设计的贝叶斯网络形成子技能和聚合能力的量化结果。它首先是一个**专家可设计、可修改、可追溯的软件框架**，不是已经完成科学校准的飞行员评价标准。

当前交付包含一个可运行的 starter template，用于证明从输入、Evidence 到 BN 结果的工程工作流能够贯通。starter 中的 Evidence、阈值、operator 参数、父节点、状态、CPT、11 个子技能和 4 个聚合能力都可以被专家修改、复制、停用或替换。工程运行成功不代表这些初始内容已经获得领域验证。

产品的核心价值有三点：

- **透明：** 原始输入、EvidenceRecipe、operator、BN parents/states/CPT、任务激活和运行来源均可查看；
- **可编辑：** 普通模型修改在前端完成，新的底层计算机制可以直接修改发布包内的 Python 源码；
- **可复现：** 每次运行冻结 exact Session revision、模型闭包、源码、依赖和 operator identity，后续编辑不会改写旧结果。

## 2. 读者与职责

| 角色 | 主要工作 | 通常不需要做的事 |
|---|---|---|
| 评估用户 | 创建/打开 project，导入 Session，选择任务方案，运行并查看结果 | 修改 Python、设计 CPT 或判断算法科学有效性 |
| 领域专家 | 新增/复制 Evidence 与 BN 节点，修改 recipe、parents、states、CPT 和任务激活 | 管理 SQLite 服务或手工编辑运行快照 |
| 算法扩展开发者 | 当现有 operators 无法表达新方法时，增加 Python operator 或修改核心计算 | 为普通阈值变化发布插件版本 |
| C#/协议维护者 | 维护 WinUI、typed DTO、sidecar lifecycle 和错误恢复 | 在 C# 中复制 Evidence 或 BN 算法 |
| 发布维护者 | 构建便携 ZIP、验证 checksum/SBOM/文档并执行交付检查 | 把用户 Session 或 project 打进产品包 |

新用户的第一条实际操作路径见 [[DOC:PAS-QUICKSTART-001]]；评估流程见 [[DOC:PAS-EVALUATOR-001]]。

## 3. 系统环境视图

[[ASSET:c4-system-context]]

该视图借用 C4 system-context 层级：它只说明人员、外部数据、产品和受管 project 之间的关系，不展开内部类或数据库表。

- 仿真器可以提供完整 canonical Session Bundle，也可以只提供 `streams/` 与 `annotations/`；
- 产品只读检查外部目录，再把可用内容复制到用户 project 的受管存储；
- 评估用户操作当前 project，领域专家编辑当前软件副本的全局模型库；
- 运行结果、Evidence trace、BN posterior、artifacts 和 exact RunSnapshot 保存在 project 中；
- 产品 ZIP 不携带任何用户 Session、project、结果或生物数据。

## 4. 一套软件、一个系统模型库、多个用户项目

```text
一套解压后的软件副本
├── Python 后端源码与私有运行环境
│   ├── 通用 Evidence 执行器
│   ├── operators / adapters
│   └── BN 推理引擎
├── system/ 系统级模型库
│   ├── 所有 Raw Input / Evidence / BN 节点
│   ├── 所有任务方案与 active selection
│   ├── parents、states、CPT、layout
│   └── 当前持久 edit session
└── 用户选择的多个 project（在软件目录之外）
    ├── 受管 Session revisions
    ├── immutable RunSnapshots
    ├── runs / results
    └── content-addressed artifacts
```

这个所有权边界解决了两个看似冲突的需求：模型设计要对所有 project 全局生效，而每个用户的 Session 和结果又必须独立、可迁移。专家在前端保存一个节点修改后，同一软件副本打开的所有 project 都会在未来运行中使用它；已经完成的历史运行仍使用自己的冻结快照。

复制整套解压目录会复制当前 `system/` 和 Python 源码，从而形成一个独立演化的软件分支。复制或移动单个 project 则只移动该项目的数据和历史，不复制当前全局模型。

## 5. 容器、运行时与数据所有权

[[ASSET:c4-container]]

| 容器/存储 | 职责 | 权威边界 |
|---|---|---|
| WinUI Desktop | 画布、节点窗口、表单、任务切换、运行和结果投影 | 只发送 typed intent，不复制 Python 计算 |
| Python sidecar | 本地 JSON-RPC、domain services、持久化、Evidence/BN 执行 | stdout 只传协议，日志走 stderr，不监听网络端口 |
| Active Python Source | adapters、operators、compiler/executor、BN engine、contracts | 当前解压副本唯一活动的一方源码；修改后重启生效 |
| System Model Library | 所有 current ModelNode、TaskScheme、CPT、layout 和 edit session | 属于软件副本，不属于任何 project |
| User Project | Session、RunSnapshot、run/result/artifact | 属于用户数据，不进入通用产品包 |
| Versioned Manuals | 操作、专家设计、接口、源码和发布说明 | Markdown 原稿生成 DOCX；文档不改变运行逻辑 |

前端启动时自动监督 private Python sidecar。用户不需要手工激活 Conda、启动 SQLite 服务或打开网络端口；SQLite 是由 Python 进程直接读写的嵌入式文件数据库。

## 6. 从原始输入到能力结果

主计算工作流按下列顺序运行：

1. 检查并受管导入一个 Session；
2. adapters 把 X/U/I/G/P 和可选 `pilot_camera` 映射为 typed signals/resources；
3. active Evidence 节点执行各自 EvidenceRecipe；
4. operator graph 形成连续值、trace 和 D/A/U observation；
5. BN inference 使用 Evidence observations 与 CPT 计算 posterior；
6. 结果工作区显示 Evidence、子技能、聚合能力、影响信息和 provenance；
7. project 保存 exact RunSnapshot、结果和 artifacts。

五类原始输入是：

| Family | 内容 |
|---|---|
| X(t) | 飞行器状态、姿态、位置、速度与任务相关状态 |
| U(t) | 飞行员控制输入和控制器状态 |
| I(t) | 飞行员在 VR 中看到的场景或视觉帧 |
| G(t) | gaze、stare、fixation、AOI 和视线映射 |
| P(t) | EEG、ECG 和未来声明的其他生理信号 |

`pilot_camera` 是可选的驾驶员面部/身体相机，不等同于 I(t)。缺失输入不会被产品自动合成；只依赖现有模态的 Evidence 仍可计算，依赖缺失输入的 Evidence 会形成明确 availability 状态。表现很差、控制剧烈或生理数值异常本身不是“低质量数据”，不会因为分数差而被过滤。

接口细节见 [[DOC:PAS-SESSION-001]]。

## 7. 节点、画布和正确的 BN 方向

系统持久模型有三类核心节点：Raw Input、Evidence 和 BN。前端为了理解性把它们投影成五层：

1. Raw Input Family；
2. Extracted Data；
3. Evidence；
4. Sub-skill；
5. Competency。

Evidence 的计算依赖只来自原始输入或经过 typed preprocessing 的数据，不能由抽象能力反向生成。BN 的生成模型方向保持 `Competency → Sub-skill → Evidence observation`：一个 child 的 CPT 条件是其 fixed parents。实际评估时，Evidence observation 被观测后，推理引擎沿同一 joint probability model 更新隐藏能力的 posterior；这不是把结构箭头反画成 `Evidence → Skill`。

operator 不作为主画布节点。它是 EvidenceRecipe 内部的可复用计算步骤，在 Evidence 节点详情和 Operator 菜单中查看和配置。完整专家操作分别见 [[DOC:PAS-EXPERT-EVIDENCE-001]] 与 [[DOC:PAS-EXPERT-BN-001]]。

## 8. 全局节点与任务方案

每个可见节点只有一个 current definition，其中包含名称、固定父节点以及完整 recipe 或 states/CPT。若两个任务需要不同计算逻辑或不同父节点，它们就是两个独立节点，而不是同一节点的隐藏版本。

任务方案只选择当前激活的节点和边：

- active 节点/边明亮，未被当前任务采用但真实存在的全局节点/边变暗；
- 启用 child 时自动递归启用 fixed parents；
- 停用仍有 active downstream 的 parent 时，专家选择继续级联停用或取消；
- 复制节点默认只复制该节点并继续引用原 fixed parents；
- 多个任务可以共享完全相同的节点；需要定制时再复制、重命名、修改并停用旧节点。

因此系统可以逐渐积累大量相似但独立的 Evidence/BN 节点，例如基础 `Precise`、专家后来创建的 `hover.Precise` 和 `straight.Precise`。是否采用它们由任务方案决定，而不是反复覆盖一个算法再改回来。

## 9. 两层修改方式

### 9.1 普通专家修改

参数、window、threshold、scorer、recipe 组合、节点、parents、states、CPT、任务激活和 layout 都在前端修改。修改先进入 Python 管理的持久 edit session；关闭主窗口时选择保存全部、放弃全部或取消。无需发布 plugin，也不要求每次改参数都运行开发测试。

### 9.2 新计算机制

只有现有 operator catalog 无法表达新方法时，才编辑发布目录中的 Python：

```text
backend/src/pilot_assessment/
```

新增 operator 后在显式 extension 入口注册，必要时用 bundled dependency tool 增加私有依赖，然后重启应用。修改作用于当前软件副本的所有 project 和未来运行；历史 RunSnapshot 不变。详细步骤见 [[DOC:PAS-PYTHON-EXT-001]]。

## 10. 运行身份与历史不变性

运行前 preflight 锁定：

- exact managed Session revision；
- clean TaskScheme 和 active node closure；
- ModelNode/recipe/CPT hashes；
- loaded source tree、private Python、dependency manifest 和 operator catalog identity。

如果 Python 进程启动后磁盘源码又发生变化，系统要求重启，避免“记录的是新文件 hash、实际执行的是旧 import”这种不一致。与出厂 baseline 不同只显示 `locally_modified`，不会因为专家修改而阻止运行。新 source identity 第一次运行时保存 content-addressed source snapshot artifact，以便将来解释历史结果。

## 11. 启动、关闭与迁移的基本事实

- 首个交付是 Windows x64 portable ZIP，建议解压到较短且可写的目录，例如 `D:\PilotAssessment`；
- 双击 `PilotAssessment.Desktop.exe` 即可启动前端和受监督 sidecar；
- 不单独启动 SQLite，不手工激活 Python；
- project 由用户选择创建位置，不放进产品目录；
- 软件关闭时如存在模型改动，会询问保存全部、放弃全部或取消；
- 新产品版本解压到新的并列目录，不自动覆盖已修改旧目录；
- 发布构建显式捕获已经保存并关闭的 current system；软件关闭后，完整软件目录或完整 project 目录都可以作为独立副本复制，不提供专用 Backup/Restore 功能。

## 12. 当前状态与科学边界

截至本手册版本，M1–M8B、M8C-0 与 M8D 的工程门已关闭，M8C-1 最终文档仍在等待后续门槛。M7 的完整用户手工验收和 D-055 canonical 单英文模型迁移仍未关闭；M8E final clean-machine handoff 也尚未完成。

所有 starter/synthetic 运行都保持 `formal_run_authorized=false`。本产品可以证明数据合同、编辑、持久化、推理和追溯工作流能够运行，但不能证明当前 Anchor/Evidence、任务结构、阈值或 CPT 能准确评价飞行员能力。最终科学方法由领域专家在该框架中设计、校准和验证。

## 13. 推荐阅读路线

- 第一次运行：[[DOC:PAS-QUICKSTART-001]]；
- 导入数据并评估：[[DOC:PAS-EVALUATOR-001]]；
- 设计 Evidence/任务：[[DOC:PAS-EXPERT-EVIDENCE-001]]；
- 设计 BN/CPT：[[DOC:PAS-EXPERT-BN-001]]；
- 对接采集数据：[[DOC:PAS-SESSION-001]]；
- 新增底层算法：[[DOC:PAS-PYTHON-EXT-001]]。

## 14. 变更记录

| 文档版本 | 日期 | 变化 |
|---|---|---|
| 0.1.0 | 2026-07-21 | 建立 M8C 双语架构基线，纳入 system/project/source ownership、任务节点、BN 方向和科学边界 |
