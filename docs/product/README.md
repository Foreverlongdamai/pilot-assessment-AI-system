# Pilot Assessment System — 产品设计文档中心

| 字段 | 当前值 |
|---|---|
| 设计基线 | 产品 v0.1.0-rc.2 portable correction source；D-031–D-083 已获用户确认 |
| 基线日期 | 2026-07-21 |
| 产品阶段 | M1–M8E engineering history 保持完整；`v0.1.0-rc.1` 用户验收为 `changes-required`。RC.2 source 已按 D-082/D-083 收纳 `app/` desktop payload 并建立唯一根启动器，tagged build/external verification 尚待执行；starter/synthetic `formal_run_authorized=false` |
| 运行范围 | Windows 本地、离线 session 评估 |
| 科学状态 | 参考模型待领域专家校准与验证 |
| 权威范围 | pilot_assessment_system 的产品设计与实现约束 |

2026-07-17 M7B Task 12 已完成普通表单字段的 350 ms autosave、同一 canonical 对象的有序写入、独立对象并发、transaction-ID 幂等重试、晚响应 rebase、Reload/Reapply 冲突恢复、编辑器/主窗口保存状态和关闭前 flush。可见验证将 BN 描述写入后端、恢复原文并在重开窗口后读回 revision `2`；因此前文 Task 11 时点的“Task 12 才负责”已由本段取代。离散 activation/edge/copy/archive 与 parent/state/CPT 仍直接使用已有原子后端操作，不经过延迟表单保存。

2026-07-17 M7B Task 13 已完成即时中英文切换：shell、页面、任务侧栏、active/dim 图、对话框以及已打开的 Raw Input/Evidence/BN/CPT 节点窗口均原地刷新；模型翻译缺失时显示明确 fallback 标记。语言只保存为 `%LOCALAPPDATA%` UI preference，不发送模型写操作，也不改变 ID、revision、hash、参数或结果。fresh gate 为 desktop Unit `75/75`、Contract `3/3`、focused localization `8/8`、x64 Debug build `0 warning / 0 error`，`527` 对资源键与 `481` 个实际引用均零缺失。下一项是 Task 14 actual run/results/trace/diagnostics；`model.preview.node` 仍只是 frozen snapshot metadata，不代表已经执行评估。

2026-07-17 M7B Task 14 已完成真实运行与结果工作区。专家从当前 managed session revision + current task scheme 执行技术预检后即可直接运行，不需要 Publish；Python 后端自动冻结 immutable RunSnapshot，并唯一负责 Evidence/BN/CPT/run 计算。WinUI 展示单调进度、取消/重启恢复、Evidence D/A/U、Observation、BN posterior、只读 inference influence、provenance、受管 artifact references 与 diagnostics；canonical BN edges 和 inference influence 不混淆。fresh gate 为 focused Unit `6/6`、desktop Unit `81/81`、Contract `3/3`、localization `8/8`、real-sidecar Python `2/2`、x64 Debug build `0 warning / 0 error`。可见受管案例得到 `18` Evidence、`4` posterior variables、`39` artifact references，并在应用重启后恢复同一 snapshot/result；科学状态仍明确为 `not_supported / engineering workflow only`。下一项是 Task 15 completion gate。

2026-07-17 M7B Task 15 已关闭 M7 工程完成门，代码/测试提交为 `d1dbdd2`。fresh gate 为 desktop Unit `84/84`、real-sidecar Contract `4/4`、x64 Debug build `0 warning / 0 error`；1,000-node in-memory UI projection 在 `1280 × 720` buffered viewport realization `40` 个节点且满足 `<2 s`。可见应用自动恢复同一 immutable result，完成 light/dark/system、键盘焦点、screen-reader headings/live status、`1920/1279/959` logical-width responsive layout，以及主窗口和 ECG/EEG 两个非模态编辑器三窗并存；运行中的应用、`uv`、Python 与 console host 合计 TCP listener 为 `0`。M7 只宣告工程工作区完成；M8 最终分发、真实 exporter/device 适配和领域专家科学校准仍未完成。

2026-07-18 用户明确要求先亲自验收 M7，并预期验收后仍可能修改。因此 M7 当前准确状态是 **engineering verified / user acceptance pending**。本轮只保存 [M8 pre-UAT 候选设计大纲](specs/2026-07-18-m8-productization-editable-python-documentation-and-handoff-outline.md) 和 [阶段路线图](plans/2026-07-18-m8-pre-uat-implementation-outline.md)；没有实施 M8、没有新增正式 D-编号，也没有生成发布包。M8 v0.2 候选进一步明确：正常参数/Evidence/BN/task 修改继续在前端完成；只有现有方法无法达到新目标时，专家才直接编辑发布目录中唯一活动的 Python backend source tree，重启后对该系统副本全局生效，不要求 plugin package 或源码编辑 UI。

2026-07-18 用户进一步确认 D-056/D-057，取代旧 autosave 的正式提交时机：节点、边、CPT、任务方案和布局先进入由 Python 管理的持久 edit-session SQLite；主窗口关闭时统一选择“保存全部并关闭／放弃全部并关闭／取消”。dirty 草稿明确阻止 preview/preflight/run；Ctrl+Z/Ctrl+Y 操作全局草稿历史。M8B-0 已将该 edit session 的 owner 从 project 提升为软件副本 `system/`，交互语义不变。主画布的唯一五层分类为 `Raw Input Family -> Extracted Data -> Evidence -> Sub-skill -> Competency`，非输入族筛选不再固定显示五个绿色根，BN 生成箭头仍保持 `Competency -> Sub-skill -> Evidence`。该返修仍等待用户实际操作验收。

2026-07-18 用户进一步确认 D-058/D-059：普通产品界面只显示由节点/方案实际语义确定的英文名称，随机 ID/hash 仅留在诊断、溯源、artifact、frozen snapshot 与折叠技术身份区域；所有 fallback marker 从发布界面移除。桌面应用改用统一的原创极简 eVTOL 评估图标，并从项目内 1024 px master 确定性派生全部 Windows assets。**该段是 2026-07-18 历史检查点**：当时 D-055 的单字段 contract/database 迁移仍是独立待办；后续已在 M8E 完成。

2026-07-20 用户确认 D-060/D-061：Session Import 统一识别 canonical Bundle 与只有 `streams/`/`annotations/` 的 simulator raw source。raw source 始终只读，后端在项目 staging 中生成 canonical manifest、checksum 与 annotations，再进入既有受管 revision 流程；缺失模态保持 missing，不生成合成数据。源/profile 未声明单位时不询问、不猜测、不换算，数值按固定 adapter/Evidence 方法透传并记录 provenance。Python、JSON-RPC、C# contract、ViewModel 和 WinUI 页面均已实现，用户手工验收仍待完成。

2026-07-20 用户进一步授权执行既定 M8 路线并开始打包。D-062–D-065 与 M8A 正式规格已经实现：发布脚本生成 Windows x64 unpackaged self-contained 产品目录和 ZIP，包含 WinUI/.NET/Windows App SDK、私有 CPython、production dependencies 与唯一活动的完整第一方 backend source；不包含用户 project/session/result。最终 ZIP 已在仓库外解压验证自动 sidecar、visible desktop、live-source edit/restart、checksums 和零 TCP listener。**该段是 M8A 当时的检查点**：当时 M8B–M8E、用户验收和科学校准仍未完成；后续工程状态见本文开头。

2026-07-21 用户批准 D-066–D-071 与 [M8B system-owned model library 规格](specs/2026-07-21-m8b-system-owned-model-library-and-editable-backend-provenance-design.md)。M8B-0 已按 [实施计划](plans/2026-07-21-m8b0-system-model-ownership-implementation-plan.md) 完成工程实现：current ModelNode/TaskScheme/edit session 的 owner 从单个 project 提升为每套解压软件副本的 `system/`；Model Studio 可在无 project 时工作；Project 只保存 Session、不可变 RunSnapshot/materialization、result 和 artifacts；legacy project-local 模型采用确定性、幂等、无覆盖导入。新 portable ZIP 已携带 clean starter system baseline，并完成双项目共享与旧运行快照隔离验证。精确命令、hash 与边界见 [M8B-0 Verification](reviews/2026-07-21-m8b0-system-model-ownership-verification.md)。

2026-07-21 M8B-1 已按 [Source Provenance and Snapshot Plan](plans/2026-07-21-m8b1-source-provenance-and-snapshot-implementation-plan.md) 完成工程实现：sidecar 启动时冻结 loaded source、私有 Python、依赖与 operator catalog identity；运行前磁盘漂移要求重启，但 release baseline divergence 本身不阻止专家修改后的系统运行；新 RunSnapshot v0.2 保存 exact identity 和内容寻址 source snapshot artifact。M8B-2 随后完成普通 Python operator 扩展入口、私有依赖工具、既有通用 schema 表单和 release-copy run 闭环；正式 ZIP 与 fresh 证据见 [M8B-2 Verification](reviews/2026-07-21-m8b2-python-operator-extension-verification.md)。M8B 已完成。

2026-07-21 M8C-0 已按 [Documentation System Design](specs/2026-07-21-m8c-documentation-system-design.md) 和 [Implementation Plan](plans/2026-07-21-m8c0-documentation-infrastructure-implementation-plan.md) 完成：12 类 stable catalog、metadata schema、固定文档工具链、DOCX reference template、Markdown/交叉引用、C4 assets、双语架构手册和 Python extension 手册均已接入。三份 review DOCX 共 28 页，逐页 render QA 与连续两次 deterministic build 通过；portable builder/verifier 正确区分 `review` 和 `released`。完整证据见 [M8C-0 Verification](reviews/2026-07-21-m8c0-documentation-infrastructure-verification.md)。D-077 已取消专用 backup/restore；随后 M8D 已完成 current-system packaging、project portability 与 diagnostics。最终 12 类双语内容、M7 截图和技术总册继续属于 M8C-1。

2026-07-21 用户批准 D-078–D-081 与 [M8E Final Release Candidate Design](specs/2026-07-21-m8e-final-release-candidate-and-handoff-design.md)：不再单独执行 M7 中间验收，改为先完成 D-055、M8C-1 和 tagged clean-source `v0.1.0-rc.1`，再直接验收完整候选。D-055 单一英文 current-model contract/持久化迁移、24 份 released DOCX、10 张隐私审核后的 `release-candidate` screenshots、annotated tag、最终构建以及内部/仓库外自动隔离验证现均已完成；精确证据见 [M8E Verification](reviews/2026-07-21-m8e-release-candidate-verification.md)。候选形成不等于用户接受，也不得在 `user_acceptance=pending` 时称为正式 `v0.1.0`。

2026-07-21 用户完成 RC.1 的首项独立验收并给出 `changes-required`：产品根目录暴露 94 个文件夹和 374 个文件。D-082/D-083 与 [RC.2 Portable Root Layout Amendment](specs/2026-07-21-rc2-portable-root-layout-amendment.md) 冻结新口径：RC.1 不可变，RC.2 将完整 WinUI/.NET runtime 收纳到 `app/`，根目录只提供 `PilotAssessment.exe` 一个启动入口，并显式保留八个语义目录。当前 tagged RC.2 build 与仓库外验证尚待执行。

## 1. 文档用途

本目录是产品交付、开发、审查和后续专家配置的统一入口。它回答五类问题：

1. 产品解决什么问题、明确不解决什么问题；
2. 原始 session 如何进入系统并保持多模态时间一致；
3. 专家如何用全局完整节点、任务激活方案、可编辑 EvidenceRecipe 和 BN 组合任意任务模型；
4. Windows 前端如何展示并修改节点、边、参数和 CPT；
5. 如何验证软件、校准评估模型并把产品交给下一位维护者。

文档中的 Hover、O1–O13、H1–H5 和 33-node BN 是一套**可编辑 starter template**。算法、阈值、拓扑和 CPT 只用于启动系统与给专家提供示例；产品不以证明它们科学正确为目标。专家可以在全局节点库中创建、复制和修改任意 Evidence/BN 节点，再由不同 `TaskScheme` 激活所需节点。每个可见节点只有一个当前完整定义；任务需要不同定义时使用新的节点，而不是在同一个节点中切换版本。书面设计、实施计划、代码实现、工程可运行与科学有效性是不同状态，不能相互替代。

## 2. 推荐阅读顺序

| 顺序 | 文档 | 主要读者 | 内容 |
|---:|---|---|---|
| 1 | [01_PRODUCT_OVERVIEW.md](01_PRODUCT_OVERVIEW.md) | 所有人 | 产品边界、角色、工作流和总架构 |
| 2 | [M7 WinUI Expert Designer and Task Activation Workspace Design](specs/2026-07-17-m7-winui-expert-designer-and-task-activation-workspace-design.md) | 专家、产品、前后端 | 当前产品权威：完整节点、任务激活、复制/停用、多浮窗、autosave 与 RunSnapshot |
| 2.1 | [M7 Implementation Roadmap](plans/2026-07-17-m7-winui-expert-designer-implementation-roadmap.md) | 开发、审查者 | 当前实施顺序：M7A 后端 current-model 迁移后再做 M7B WinUI；定义跨阶段门与轻量验证边界 |
| 2.2 | [M7A Current Model Runtime Implementation Plan](plans/2026-07-17-m7a-current-model-runtime-implementation-plan.md) | 后端开发、审查者 | 12 个 INLINE 任务：完整节点、任务激活、SQLite v2、自动快照、sidecar 与 legacy replay |
| 2.3 | [M7B WinUI Expert Designer Implementation Plan](plans/2026-07-17-m7b-winui-expert-designer-implementation-plan.md) | Windows 前端、审查者 | 15 个 INLINE 任务：sidecar client、active/dim 画布、多浮窗、编辑器、双语与 run/results |
| 2.4 | [M7 Raw-Input Provenance and Single-Language Amendment](specs/2026-07-18-m7-raw-input-provenance-and-single-language-model-content-amendment.md) | 专家、产品、前后端 | D-054/D-055：五个统一绿色的 X/U/I/G/P 画布投影及只读溯源；界面本地化与单一英文模型内容分离 |
| 2.4.1 | [M7 Raw Input Family Provenance Canvas Plan](plans/2026-07-18-m7-raw-input-family-provenance-canvas-implementation-plan.md) | Windows 前端、审查者 | 已实现并可见验证：绿色输入族 lane、typed provenance、可逆布局偏移和 minimap |
| 2.4.2 | [M7 Single-Language Canonical Content Plan](plans/2026-07-18-m7-single-language-canonical-content-implementation-plan.md) | 前后端、审查者 | 待实施：旧 bilingual contract/UI 迁移为单一英文 canonical 模型内容 |
| 2.5 | [M7 Staged Edit Session and Five-Layer Canvas Amendment](specs/2026-07-18-m7-staged-edit-session-and-five-layer-canvas-amendment.md) | 专家、产品、前后端 | D-056/D-057：后端持久草稿、关闭时统一保存/放弃/取消、全局 undo/redo、五层画布与 dirty run guard |
| 2.5.1 | [M7 Staged Edit Session and Five-Layer Canvas Plan](plans/2026-07-18-m7-staged-edit-session-and-five-layer-canvas-implementation-plan.md) | 前后端、审查者 | 已实现并工程验证：edit-session SQLite、`model.edit.*`、五层投影、长按拖动与关闭事务 |
| 2.6 | [M7 Human-readable UI and eVTOL Branding Amendment](specs/2026-07-18-m7-human-readable-ui-and-evtol-branding-amendment.md) | 专家、产品、Windows 前端 | D-058/D-059：语义英文名称、普通界面 ID 分层、无 fallback marker 与统一 eVTOL 图标 |
| 2.6.1 | [M7 Human-readable UI and eVTOL Branding Plan](plans/2026-07-18-m7-human-readable-ui-and-evtol-branding-implementation-plan.md) | Windows 前端、审查者 | INLINE 返修：统一名称解析、Results/graph/node window 展示收口、图标派生与启动验证 |
| 2.7 | [M7 Simulator Raw Session Import Adapter Amendment](specs/2026-07-20-m7-simulator-raw-session-import-adapter-design.md) | 产品、数据、前后端 | D-060/D-061：raw source 受管物化、缺失模态与未声明单位原值透传 |
| 2.7.1 | [M7 Simulator Raw Session Import Adapter Plan](plans/2026-07-20-m7-simulator-raw-session-import-adapter-implementation-plan.md) | 开发、审查者 | INLINE 实施：source contracts、materializer、persistence、RPC、WinUI 与轻量验证 |
| 2.8 | [M8 Productization Design Outline](specs/2026-07-18-m8-productization-editable-python-documentation-and-handoff-outline.md) | 产品、交付、维护者 | **已批准路线图：** 便携分发、前端 canonical 编辑、直接可改的全局 Python backend、分类文档/DOCX、current-system packaging/project portability 与交付边界 |
| 2.8.1 | [M8 Implementation Roadmap](plans/2026-07-18-m8-pre-uat-implementation-outline.md) | 产品、开发、审查者 | M8A–M8E 阶段关系、M7 UAT/M8E 门与当前执行点 |
| 2.9 | [M8A Portable Windows Release Design](specs/2026-07-20-m8a-portable-windows-release-design.md) | 产品、交付、维护者 | 已实现：Windows x64 self-contained ZIP、私有 Python、唯一活动 backend source、用户数据隔离与发布元数据 |
| 2.9.1 | [M8A Implementation Plan](plans/2026-07-20-m8a-portable-windows-release-implementation-plan.md) | 开发、审查者 | 已完成：portable-first locator、publish profile、builder、外部 verifier 与交付收口 |
| 2.9.2 | [M8A Verification](reviews/2026-07-20-m8a-portable-windows-release-verification.md) | 用户、交付、审查者 | 最终 ZIP 的精确路径、大小、hash、仓库外运行、可编辑源码、内容隔离、回归结果和残余限制 |
| 2.10 | [M8B System-Owned Model Library and Editable Backend Provenance Design](specs/2026-07-21-m8b-system-owned-model-library-and-editable-backend-provenance-design.md) | 产品、专家、前后端、交付 | 当前 ownership 权威：software-copy `system/`、project/run 边界、legacy import，以及 M8B-1/2 source/operator 后续边界 |
| 2.10.1 | [M8B-0 System Model Ownership Implementation Plan](plans/2026-07-21-m8b0-system-model-ownership-implementation-plan.md) | 开发、审查者 | 已完成：system store、无 project Model Studio、双项目共享、exact run materialization、legacy import 与 portable rebuild |
| 2.10.2 | [M8B-0 Verification](reviews/2026-07-21-m8b0-system-model-ownership-verification.md) | 用户、交付、审查者 | focused tests、双项目快照隔离、桌面构建、仓库外 ZIP 启动、system baseline 与用户数据隔离证据 |
| 2.10.3 | [M8B-1 Source Provenance and Snapshot Plan](plans/2026-07-21-m8b1-source-provenance-and-snapshot-implementation-plan.md) | 开发、审查者 | 已完成：loaded source/runtime/dependency/operator identity、restart boundary、RunSnapshot v0.2 与 source artifact |
| 2.10.4 | [M8B-1 Verification](reviews/2026-07-21-m8b1-source-provenance-and-snapshot-verification.md) | 用户、交付、审查者 | focused tests、发布 baseline v2、源码修改/重启、artifact 去重与真实桌面证据 |
| 2.10.5 | [M8B-2 Python Operator Extension Handoff Plan](plans/2026-07-21-m8b2-python-operator-extension-handoff-implementation-plan.md) | 开发、维护者、审查者 | 已完成：普通源码扩展入口、私有依赖工具、通用参数 UI、release-copy vertical slice 与维护手册 |
| 2.10.6 | [M8B-2 Verification](reviews/2026-07-21-m8b2-python-operator-extension-verification.md) | 用户、交付、维护者 | focused gates、依赖 add/remove、clean ZIP、外部源码编辑/extension/run/desktop 证据与科学边界 |
| 2.11 | [M8C Documentation System Design](specs/2026-07-21-m8c-documentation-system-design.md) | 所有人、文档、交付、维护者 | Markdown/TOML/catalog 权威、双语 12 类手册、DOCX 样式/目录/图/截图/验证与 M8C-0/1 gates |
| 2.11.1 | [M8C-0 Documentation Infrastructure Plan](plans/2026-07-21-m8c0-documentation-infrastructure-implementation-plan.md) | 开发、文档、审查者 | 已完成：catalog/schema、pinned toolchain、template、Markdown/DOCX、C4、双语代表手册和 render QA |
| 2.11.2 | [M8C-0 Verification](reviews/2026-07-21-m8c0-documentation-infrastructure-verification.md) | 用户、交付、维护者 | 三份 DOCX、28 页逐页 QA、确定性 hashes、portable review-doc integration 与未关闭边界 |
| 2.12 | [M8D Current-System Packaging, Project Portability and Diagnostics Design](specs/2026-07-21-m8d-current-system-packaging-project-portability-and-diagnostics-design.md) | 产品、交付、维护者 | D-077：取消专用 backup/restore；显式捕获已保存 current system、完整 project 目录复制、compatibility 与轻量 diagnostics |
| 2.12.1 | [M8D Current-System Packaging Implementation Plan](plans/2026-07-21-m8d-current-system-packaging-implementation-plan.md) | 开发、交付、审查者 | INLINE 六个垂直切片：只读捕获、动态 manifest/verifier、后端与 WinUI diagnostics、project copy/reopen 和一次最终工程构建 |
| 2.12.2 | [M8D Current-System Packaging Verification](reviews/2026-07-21-m8d-current-system-packaging-verification.md) | 交付、维护者、审查者 | source 不变性、`54 / 2` 动态模型、完整 project copy/replay、typed Diagnostics、package verifier 与 privacy scan 的 fresh evidence |
| 2.13 | [M8E Final Release Candidate Design](specs/2026-07-21-m8e-final-release-candidate-and-handoff-design.md) | 产品、交付、维护者、用户 | D-078–D-081：完整候选后统一验收、`v0.1.0-rc.1`、candidate screenshots、两层验收证据与最终交付边界 |
| 2.13.1 | [M8E Final Release Candidate Implementation Plan](plans/2026-07-21-m8e-final-release-candidate-implementation-plan.md) | 开发、文档、交付、审查者 | INLINE 13 个任务：D-055、M8C-1、C#/WinUI、tagged candidate、自动隔离验证和用户交付 |
| 2.13.2 | [M8E Design Self-Review](reviews/2026-07-21-m8e-final-release-candidate-design-self-review.md) | 产品、交付、审查者 | 已批准规格的范围、候选身份、隐私、current-system capture 和验收声明自审 |
| 2.13.3 | [M8E `v0.1.0-rc.1` Verification](reviews/2026-07-21-m8e-release-candidate-verification.md) | 用户、交付、维护者、审查者 | clean tag、fresh gates、source 不变性、ZIP/SBOM/checksum 与仓库外 editable-source/operator/run/desktop 的最终工程证据 |
| 2.14 | [RC.2 Portable Root Layout Amendment](specs/2026-07-21-rc2-portable-root-layout-amendment.md) | 产品、交付、维护者、用户 | D-082/D-083：RC.1 changes-required、`app/` desktop payload、唯一根启动器、manifest v3 与根白名单 |
| 2.14.1 | [RC.2 Implementation Plan](plans/2026-07-21-rc2-portable-root-layout-implementation-plan.md) | 开发、交付、审查者 | inline 实施、轻量回归、clean RC.2 tag、仓库外启动验证与不可变 RC.1 边界 |
| 2.14.2 | [RC.1 User Acceptance Result](reviews/2026-07-21-v0.1.0-rc.1-user-acceptance-result.md) | 用户、产品、交付 | `changes-required` 的独立验收事实、根目录计数、必要修订和新 candidate 规则 |
| 3 | [M5 Shared Versioned Model Library and Bayesian Workspace Design](specs/2026-07-16-m5-shared-versioned-model-library-and-bayesian-workspace-design.md) | 专家、产品、前后端 | 已实现的后端基础与历史 identity/publish 语义；冲突处由 M7 规格取代 |
| 4 | [M5 Implementation Plan](plans/2026-07-16-m5-shared-versioned-model-library-and-bayesian-workspace-implementation-plan.md) | 开发、审查者 | 已完成：inline 任务、合同冻结、O8 迁移、轻量验证与完成门 |
| 5 | [M6 Local Runtime, Durable Persistence and Sidecar Protocol Design](specs/2026-07-16-m6-local-runtime-persistence-and-protocol-design.md) | 前后端、交付、审查者 | 已实现：受管项目、SQLite、artifact、run lifecycle 与 JSON-RPC sidecar |
| 6 | [M6 Implementation Plan](plans/2026-07-16-m6-local-runtime-persistence-and-sidecar-implementation-plan.md) | 开发、审查者 | 已完成：15 个 INLINE 任务、轻量 test-first、focused smoke 与完成门 |
| 7 | [03_SESSION_BUNDLE_SPEC.md](03_SESSION_BUNDLE_SPEC.md) | 数据与后端 | X/U/VR/gaze/EEG/ECG 数据合同与同步 |
| 8 | [04_REFERENCE_MODEL_V0_1.md](04_REFERENCE_MODEL_V0_1.md) | 领域专家、算法 | 18 个 starter anchor 的算法和初始参数 |
| 9 | [05_BAYESIAN_NETWORK_AND_CPT_DESIGN.md](05_BAYESIAN_NETWORK_AND_CPT_DESIGN.md) | 算法、后端 | BN 拓扑、状态、CPT、缺失证据和解释 |
| 10 | [02_ASSESSMENT_CORE_DESIGN.md](02_ASSESSMENT_CORE_DESIGN.md) | 后端开发 | 模块边界与完整计算流水线 |
| 11 | [06_VISUAL_GRAPH_EDITOR_DESIGN.md](06_VISUAL_GRAPH_EDITOR_DESIGN.md) | 前后端开发 | 历史细节：三类节点、两类边、事务和 CPT 迁移；冲突处由 M7 规格取代 |
| 12 | [07_RUNTIME_PROTOCOL_DESIGN.md](07_RUNTIME_PROTOCOL_DESIGN.md) | 前后端开发 | sidecar 生命周期与 JSON-RPC 合同 |
| 13 | [08_WINDOWS_FRONTEND_DESIGN.md](08_WINDOWS_FRONTEND_DESIGN.md) | UI/UX、前端 | 历史页面细节；当前交互由 M7 规格取代 |
| 14 | [09_VALIDATION_AND_HANDOFF.md](09_VALIDATION_AND_HANDOFF.md) | 测试、交付 | 验证层级、验收门槛和移交清单 |
| 15 | [11_IMPLEMENTATION_STATUS.md](11_IMPLEMENTATION_STATUS.md) | 开发、接手者 | 当前代码、验证证据、限制和下一里程碑 |
| 16 | [DECISIONS.md](DECISIONS.md) | 维护者 | 已锁定决策及其理由 |
| 17 | [GLOSSARY.md](GLOSSARY.md) | 所有人 | 术语、ID 和状态语义 |
| 18 | [REFERENCES.md](REFERENCES.md) | 审查者、领域专家 | 公开文献、DOI 与证据用途 |
| 19 | [10_DESIGN_SELF_REVIEW.md](10_DESIGN_SELF_REVIEW.md) | 审查者 | 本轮设计自审、发现和遗留风险 |
| 20 | [后端 M1 实施计划](plans/2026-07-11-backend-foundation-m1-implementation-plan.md) | 开发、审查者 | RED/GREEN 任务、范围和完成定义 |
| 21 | [M2 多模态合成基础规格](specs/2026-07-11-multimodal-synthetic-foundation-design.md) | 开发、数据、审查者 | 已批准：理想 I/G/EEG/ECG/camera 合同、合成 bundle 与 ingestion readiness |
| 22 | [M2 实施计划](plans/2026-07-11-m2-multimodal-synthetic-foundation-implementation-plan.md) | 开发、审查者 | shared X/U、adapter、generator、readiness 与本地 E2E 的 TDD 步骤 |
| 23 | [M3 Native-Rate Time Synchronization 规格](specs/2026-07-12-m3-native-time-synchronization-design.md) | 开发、数据、审查者 | 已批准：native-rate clock mapping、session window、aligned views 与同步报告 |
| 24 | [M3 实施计划](plans/2026-07-12-m3-native-time-synchronization-implementation-plan.md) | 开发、审查者 | 已完成：Task 0–14 的实现、实测完成门与 handoff/关闭记录 |
| 25 | [Expert-Editable Evidence and Assessment Model Design](specs/2026-07-15-expert-editable-evidence-and-model-design.md) | 专家、产品、前后端 | typed EvidenceRecipe/operator graph、自动参数表单与最小技术校验；旧 apply 交互由 M7 取代 |
| 26 | [M4R Editable Evidence Computation Foundation Implementation Plan](plans/2026-07-15-m4r-editable-evidence-computation-foundation-implementation-plan.md) | 开发、审查者 | 已完成：合同、registry、validator、compiler/executor、recipe 生命周期、18 个 starter resources 与轻量 E2E |
| 27 | [M4 Anchor Calculation and Evidence Availability 规格](specs/2026-07-13-m4-anchor-evidence-availability-design.md) | 开发、算法、审查者 | 历史/迁移规格：Task 0–28 与 15 个插件已实现；固定插件和 completion gate 已由 2026-07-15 新规格取代 |
| 28 | [M4 原实施计划](plans/2026-07-13-m4-anchor-evidence-availability-implementation-plan.md) | 开发、算法、审查者 | 历史计划，已被取代且不得执行 |
| 29 | [M4 轻量工作流验证修订](specs/2026-07-13-m4-lightweight-workflow-validation-amendment.md) | 开发、算法、审查者 | 历史 fixed-plugin 验证修订；不再定义 M4R completion gate |
| 30 | [M4 replacement 实施计划](plans/2026-07-13-m4-anchor-evidence-availability-replacement-implementation-plan.md) | 开发、算法、审查者 | Task 0–28 已完成；Task 29–36 已停止且不得执行 |
| 31 | [M4 Task 3 Reference Candidate Binding 修订](specs/2026-07-13-m4-task3-reference-candidate-binding-amendment.md) | 开发、数据、审查者 | 已实现的 session/reference binding 合同，继续保留 |
| 32 | [M4 Task 7 Catalog and Resource Identity 修订](specs/2026-07-13-m4-task7-catalog-resource-identity-amendment.md) | 开发、算法、审查者 | 已实现的 legacy catalog/resource identity，供迁移与 replay |
| 33 | [M4 Task 8 Canonical Fingerprint and Runtime Identity 修订](specs/2026-07-13-m4-task8-canonical-fingerprint-runtime-identity-amendment.md) | 开发、审查者 | 已实现的 legacy canonical/runtime identity，供迁移与 replay |
| 34 | [Autonomous Review Ledger](reviews/2026-07-13-autonomous-review-ledger.md) | 维护者、审查者 | 保存历史复核与关闭证据 |
| 35 | [Captured-Format Multimodal Software Demo](specs/2026-07-16-external-multimodal-session-demo-design.md) | 开发、数据、审查者 | 已执行：格式样例 X/U + 合成缺失模态经完整 M6 后端运行；仅证明软件闭环 |
| 36 | [Captured-Format Multimodal Software Demo Plan](plans/2026-07-16-external-multimodal-session-demo-implementation-plan.md) | 开发、接手者 | 已完成：轻量生成、真实故障定位、18/18 Evidence、BN 推理与结果路径 |

### 2.1 文档目录的职责

- `docs/product/` 根目录中的编号文档、`DECISIONS.md` 和 `GLOSSARY.md` 是当前产品基线；
- `docs/product/specs/` 保存单个里程碑或子系统的状态受控设计合同，只有标记为“已批准”的规格才进入实施；
- `docs/product/plans/` 主要保存从已批准规格派生的实施步骤、选择性测试策略、验证命令和提交边界；若因上游尚待用户验收而保存 pre-UAT 路线图，必须在标题、metadata 和正文开头同时标为 `Candidate / 不可执行`。计划不能覆盖 `DECISIONS.md` 或已批准规格；完成后继续保留，作为产品如何实现和验证的移交证据。
- `docs/product/reviews/` 保存规格、计划和实现检查点的复核 ledger；它不取代正式决策、测试或 Git 历史。

## 3. 权威性规则

发生冲突时按以下优先级处理：

1. [M7 WinUI Expert Designer and Task Activation Workspace Design](specs/2026-07-17-m7-winui-expert-designer-and-task-activation-workspace-design.md)、[D-056/D-057 修订](specs/2026-07-18-m7-staged-edit-session-and-five-layer-canvas-amendment.md)、本目录中状态为“当前”的正式产品文档与后续决策；
2. 历史 RunSnapshot、已发布 legacy scheme/component records 及其 exact hashes；
3. 产品代码与自动化测试，用于说明“目前已实现什么”，不能覆盖已确认但尚未实施的新产品目标；
4. 研究阶段的 PPT、讨论稿和历史说明。

历史草案 [2026-07-08-backend-core-runtime-adapter-design.md](../superpowers/specs/2026-07-08-backend-core-runtime-adapter-design.md) 仅用于说明设计演进。其 FastAPI、H1–H6、CSV-only 或不可编辑拓扑等旧假设不能覆盖本基线。

## 4. 当前锁定口径

- 原始数据族：X(t) 飞行状态、U(t) 控制输入、I(t) 飞行员在 VR 中实际看到的第一视角场景、G(t) 在该动态场景上的 gaze/AOI、P(t) 生理信号（至少 EEG 与 ECG）。
- Starter template：O1–O13 与 H1–H5 共 18 个示例 evidence；通用 engine 和 expert model 不限制数量，专家可新增、复制、disabled、retired 或替换。
- 顶层输出：TCP、PC、SM、OC 四项 aggregate competencies；中间层为 11 个 latent sub-skills。
- 证据等级：Desired、Adequate、Unacceptable。`computed + Unacceptable` 是有效负面 evidence，raw availability 与 computed D/A 一样为 1；coverage/availability 表示证据是否形成，不表示表现好坏。
- `export_pending/missing/invalid/not_applicable` 是 M1–M3 的 stream 生命周期或结构状态；M4 AnchorResult v0.2 的非 computed 状态固定为 `missing_input/not_applicable/not_computable/dependency_missing/extractor_error`，M4 不生成 `invalid_quality`。
- M4 假定进入它的 aligned input 已满足上游结构合同，不判断原始采集“质量够不够好”，也不因 coverage、gap、噪声、幅值、生理范围或差表现过滤 evidence；这些技术统计只进入 diagnostics/provenance。
- 全局节点库中的每个可见 Evidence/BN `ModelNode` 只有一个当前完整定义；若算法、parents、states、CPT 或语义不同，就创建另一个节点。内部 revision/history 不作为任务侧可选版本。
- 每个 `TaskScheme` 是并列、可自由编辑的节点激活集合；修改先进入项目内的后端持久草稿，选择“保存全部”后才更新正式模型。切换任务只改变 active/dim 与执行 closure，不替换节点内部定义。
- 主画布只使用 `Raw Input Family -> Extracted Data -> Evidence -> Sub-skill -> Competency` 五个理解层；底层执行合同仍严格区分 Raw Input、Evidence、BN Node 三类 canonical 节点以及 extraction/probabilistic 两类 edge。
- Hover starter 的 canonical BN 生成方向为 Competency → Sub-skill → Evidence；评估时由 observed evidence 计算 competency posterior。只读 inference overlay 可以显示反向信息影响，但不得反转已存 BN edges。
- 通用引擎允许专家建立其他合法 DAG，但必须通过新的完整节点或明确修改后的节点定义表达，不是同一图的显示反转。
- 专家通过前端决定模型内容；后端维护持久草稿、正式 canonical state、最小技术校验、CPT 原子迁移、持久化和执行一致性，但不拥有科学内容决定权。
- 正常 UI 取消业务 Draft/Published/Apply/Publish；一次应用编辑会话在关闭时统一保存或放弃。只有 clean canonical workspace 可以 run，每次 run 自动冻结 exact managed session、当前 TaskScheme active closure、完整节点定义、recipes/operators、CPT 与 hashes 为 immutable RunSnapshot。
- 软件测试通过与科学有效性成立是两个独立结论。
- 当前 repository-external 2,902-row simulator CSV 只是一次随意飞行产生的采集格式样例，仅用于接口、解析、时间和软件 E2E；它不是标准轨迹、任务 ground truth、专家 phase annotation 或能力证据。围绕它生成的 reference/annotations/biometrics 也只是 synthetic fixtures。

## 5. 当前实现边界

截至 2026-07-13，Python Core 已完成 M1、M2 与 M3：严格 SessionManifest/StreamDescriptor/legacy AnchorResult 0.1 合同、inspect-only directory-bundle integrity gate、shared X/U、版本化 profiles/adapters、deterministic multimodal generator、`IngestionReadinessReport`，以及 native-rate `AlignedSession`/`SynchronizationReport`。M3 使用 master-clock X mapped coverage、Decimal round-half-even 与版本化 temporal bindings，保留所有 source rows，并输出确定性的 synchronization fingerprint；它不插值、不重采样，也不建立全局或 anchor window grid。完成门实测仍为 `694 passed, 2 skipped`，配置 repository-external CSV 后 M2/M3 格式样例 E2E 为 `2 passed`，隔离 wheel 的 M3 micro E2E 为 `1 passed`。这些结果不验证样例飞行的任务、表现或科学有效性；M2/M3 report 始终保持 `formal_run_authorized=false`，synthetic fixture 为 `not_supported`。

旧 M4 replacement Task 0–28 已完成并保留为历史迁移资产。2026-07-15 用户确认产品应首先服务专家自由设计 Evidence 和 BN，接受 D-031–D-035 与 EvidenceRecipe/operator architecture，并批准正式规格和 replacement M4R plan。M4R 现已实现 canonical contracts/schema、trusted operator catalog、only-technical validator、generic compiler/executor、backend-only draft/preview/apply/replay、18 个可编辑 starter recipes 和轻量 E2E；任意第 19 个 recipe 无需 Anchor-ID 分支即可注册和运行。15 个旧插件继续作为 legacy/reference，H4/H5/O13 使用 operator composition 而没有新增 whole-Anchor plugin。2026-07-16 用户进一步确认 D-036–D-040：全局 immutable component versions、exact-pinned task schemes、三类节点/两类边、starter canonical BN 与 posterior inference flow 的区分，以及 legacy Evidence-to-Evidence extraction 的非覆盖迁移规则。M5 已完成 generic identity、model/BN/scheme/inference public DTO、16 类双目录 Draft 2020-12 schema、typed source/M4R preflight、global exact-version repository/service、exact-pinned scheme closure/technical validation、typed scheme operations、incomplete autosave、undo/redo、copy-on-write atomic publish、exact replay、generic CPT validation/materialization/migration、finite-discrete exact inference/read-only influence trace、17 个 compatible M4R active imports/同 concept compliant TPX parallel version、checksummed Hover starter BN package，以及 read-only draft preview/posterior/influence/copy-on-write publish/replay workflow。该 starter 物化 4 个 competency、11 个 sub-skill、18 个 Evidence binding 与 33 张工程默认 CPT，全部可由专家另行 clone/修改；这些数量未进入 generic loader。旧 O8 原 bytes/hash 仍作为 legacy/replay 资产保留。

M6 completion gate 也已关闭：受管 project/session/artifact、SQLite component/draft/run persistence、idempotency/audit、exact technical preflight、dynamic Evidence→Observation→BN pipeline、single-worker progress/cancel/recovery，以及无网络端口的 JSON-RPC/JSONL stdio sidecar 均已实现。轻量纵向闭环证明 external bundle 删除后仍可从受管副本运行，整个 project 换目录重开后 exact scheme/result/artifact 仍可回放。

2026-07-17 用户确认 D-047–D-053：M7 改用完整独立节点、全局节点库、任务激活集合、默认只复制节点且复用 fixed parents、启用 parent closure、停用 parent 前级联确认、多浮动节点窗口以及 automatic immutable RunSnapshot。M7A/M7B 原工程工作区已完成。2026-07-18 的 D-056/D-057 又把原“每次 autosave 立即写正式模型”取代为 backend-managed staged edit session，并把主画布收口为五层理解投影；C# 仍只构造 typed intent 和只读投影，Python 后端负责草稿/canonical 事务与全部 Evidence/BN/CPT/run 计算。D-055 单一英文 canonical 模型内容、M8C-1 和 M8E tagged candidate 已完成。D-077 取消专用 backup/restore。当前只剩用户验收和未来科学验证，starter/synthetic `formal_run_authorized=false`。完整状态见 [11_IMPLEMENTATION_STATUS.md](11_IMPLEMENTATION_STATUS.md)。

2026-07-16 另以 repository-external 的 2,902-row 格式样例 X/U 和工程合成 I/G/EEG/ECG/pilot-camera 跑通一次完整 M6 software-test：ingestion/preflight ready、18/18 Evidence computed、exact BN inference completed、39 个结果/追踪工件成功回读且 sidecar stderr 为空。该运行继续标记 `scientific_status=not_supported`；它验证真实产品接口与计算流水线，不验证样例飞行、starter algorithms、阈值或 CPT 的科学正确性。详见 [Captured-Format Multimodal Software Demo](specs/2026-07-16-external-multimodal-session-demo-design.md)。

## 6. 维护规则

- 修改跨文档口径时，先更新 [DECISIONS.md](DECISIONS.md)，再更新受影响文档。
- 任何 run 或导出结果必须保存 exact immutable RunSnapshot 与 content hashes；不得依赖会继续变化的 current scheme/node 状态来重放历史。
- 参数、公式、计算图、拓扑、激活集合或 CPT 修改自动暂存到后端 edit session；主窗口关闭时统一保存全部或放弃全部。无需业务 Draft/Published/Apply/Publish、人工审批或 per-edit 工程测试。
- 不在前端执行任意 Python。普通新 Anchor 使用 existing operators/EvidenceRecipe；只有现有 operator library 无法表达新的计算机制时，扩展开发者才直接修改发布副本中公开的第一方 Python operator/core 源码，完成技术验证后重启该系统副本。首个 M8 不要求 plugin package。
- 示例中的数值必须标注为“默认工程值”“文献直接支持”或“专家校准值”之一。
- 每次设计基线发布前重新执行 [09_VALIDATION_AND_HANDOFF.md](09_VALIDATION_AND_HANDOFF.md) 中的文档自检。
