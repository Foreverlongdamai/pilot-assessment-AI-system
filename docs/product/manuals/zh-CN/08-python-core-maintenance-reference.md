+++
document_id = "PAS-PYTHON-CORE-001"
language = "zh-CN"
title = "Python 核心代码维护手册"
short_title = "Python 核心维护"
product_version = "0.1.0"
document_version = "0.1.0"
status = "released"
audience = ["developer", "maintainer"]
information_types = ["how-to", "reference", "explanation"]
scope = "维护 Python contracts、ingestion、synchronization、Evidence execution、BN inference、persistence、runtime 与 sidecar。"
prerequisites = ["掌握 Python 3.11", "理解产品架构和 immutable run boundary"]
scientific_status = "engineering-only"
related_documents = ["PAS-ARCH-001", "PAS-PYTHON-EXT-001", "PAS-PROTOCOL-CSHARP-001", "PAS-RELEASE-001"]
support = "记录 source-tree identity、失败 contract/schema ID、命令、traceback 和最小隐私安全复现。"
release_channel = "release-candidate"
release_label = "v0.1.0-rc.2"
user_acceptance = "pending"
+++

# Python 核心代码维护手册

## 1. 范围与权威含义

Python backend 是 project/session 管理、model persistence、Evidence execution 与 Bayesian inference 的 canonical execution implementation。“Canonical”表示它拥有 durable state transitions 与 computation，并不表示 starter algorithms 具有科学权威或不允许修改。

普通 model content 应保存在 system model library 并通过前端编辑。只有修改通用 engine rule、data adapter、operator mechanism、inference capability、persistence contract 或 protocol service 时才改 core Python。一套解压产品只有一棵暴露的 live source tree，因此重启后 core change 会影响该副本打开的所有 project 的 future runs。

## 2. Source map

| Package | 职责 |
|---|---|
| `contracts/` | strict Pydantic DTOs 与 versioned immutable payload shapes |
| `schemas/`、`schema_resources/` | deterministic JSON Schema export 与 packaged schemas |
| `ingestion/` | canonical bundle validation、raw-source adapters 与 readiness |
| `synchronization/` | native-clock mapping 与 aligned views，不重写 source |
| `evidence/` | operator definitions、registry、recipes、compiler 与 executor |
| `anchors/` | legacy/starter anchor compatibility 与 result contracts |
| `bayesian/` | DAG validation、factors 与 posterior inference |
| `model_workspace/` | global complete nodes、task schemes、staged edit operations 与 execution projection |
| `model_library/`、`schemes/` | model assets 与 legacy/current scheme support |
| `persistence/` | SQLite migrations、repositories、transactions、audit 与 content-addressed artifacts |
| `runtime/` | system/project composition、preflight 与 run lifecycle |
| `sidecar/` | JSON-RPC method boundary 与 stdin/stdout server |

源码仓库中它们位于 `src/pilot_assessment/`；portable product 中同一 active tree 位于 `backend/src/pilot_assessment/`。

## 3. 保持 ownership boundaries

三类 durable scope 必须分开：

- **software/system scope**：global model library、nodes、recipes、parents、CPTs、task schemes 与 staged edits；
- **project scope**：managed Sessions、RunSnapshots、runs、results、artifacts 与 audit records；
- **release/source scope**：Python code、dependencies、UI、manuals 与 integrity manifests。

不能为了简化 query 把 current model rows 移进 project；不能把 user Sessions 存进 product directory；不能让 live source 静默回退到 installed wheel。正是这些边界保证 whole-software 与 whole-project copy 行为可预测。

## 4. Contracts 与 schema evolution

Current domain payloads 使用 strict versioned contracts。序列化含义变化时增加新 schema/contract version。为 historical RunSnapshots/results 保留明确 legacy readers，不能重新解释或改写 stored bytes。

推荐顺序：

1. 在 legacy type 旁定义新的 current contract；
2. 如有需要，为 live current rows 增加 deterministic decoder/migration；
3. migration 保持 append-only、idempotent，并保存 old payload/hash lineage；
4. 用新 versioned filename 导出 additive JSON Schema；
5. 新写入使用新 contract，旧 reader 继续按 ID/version 区分；
6. 证明旧 run 仍能 byte-stable round-trip。

不能因为当前 UI 不再创建旧类型就删除 historical schema。

## 5. Persistence 与 transactions

SQLite 由后端嵌入式打开。Migration number 单调递增，每次 migration 要么完整 commit，要么保留旧数据库可用。路径应相对 owner project/system root，验证 containment，避免保存 machine-specific absolute paths。

所有外部 mutation 使用 transaction ID、expected optimistic revision 与 idempotent replay semantics。Domain service 完成验证和一次 atomic commit；JSON-RPC layer 不能在第二个 store 重复写。Change journal 支持 undo/redo 与 traceability，但不是科学审批流程。

不要用一次性 SQL patch 修改 live SQLite。应实现正常 migration/service operation，在完整 disposable copy 测试，再让应用正常打开目标 root。

## 6. Ingestion 与 synchronization 修改

新仿真器格式应做成 adapter：只读检查 external source，物化 canonical managed bundle，并明确展示 file/column mapping。新 physical modality 应有独立 contract、stream descriptor、clock 与 adapter，不能藏在无关 CSV 列中。

Synchronization 保留 native rows，并确定性映射 timestamps 到 Session `t_ns`。它报告技术 coverage，但不筛选差飞行表现。不能因为极端 finite flight/physiology value 看起来不理想，就将其改成 missing/invalid。

## 7. Evidence execution 修改

优先使用 [[DOC:PAS-PYTHON-EXT-001]] 的普通 extension 路径增加 operator。只有新增跨 operators 通用能力（如 port type、temporal semantic、trace contract 或 deterministic artifact rule）时才改 generic compiler/executor。

Evidence computation 必须最终闭合到 raw/session/task resources，不能读取 inferred Sub-skill/Competency scores 来制造 observation。缺少 required data 产生 typed unavailable；已有但表现差的数据正常计算。Output、status、trace、parameter hash、operator identity 与 input artifact identities 应一起保存。

## 8. Bayesian inference 修改

当前 generic engine 对 typed DAG 和 materialized discrete CPTs 进行推理。Node count、task name 与 starter hierarchy 都是数据，不是 hard-coded engine constants。普通 graph edit 只修改 model rows，不需要改 Python，因为 engine 从 parents、states 与 CPTs 动态构造 factors。

只有增加通用 inference/model family capability 时才改 BN engine。保持 canonical `P(child | parents)`、stable state order、probability normalization 与 missing-observation marginalization。任何新 inference backend 都应在 run provenance 中冻结 implementation identity 与 exact graph snapshot。

## 9. Runtime 与历史复现

Run 前 preflight 解析一个 managed Session revision、一个 clean current task scheme、complete active closure、operator implementations、Python/dependency identity 与 scientific boundary。Run creation 冻结这些事实；后续 source/model edit 永远不能更新 completed RunSnapshot/result。

Runtime 会检测启动后的 source changes，并要求重启后才能再次运行，以免 provenance 声称使用 current disk bytes，而进程还执行旧 imported modules。

## 10. 轻量修改工作流

本项目明确欢迎专家修改，应按变更风险做适量验证，而不是套用庞大固定审批：

1. 完成最小 coherent source change；
2. 执行最接近变更模块的 focused contract/unit test；
3. execution behaviour 变化时跑一个 lightweight end-to-end workflow；
4. compatibility-sensitive 变更确认一个 historical result 仍可打开；
5. 重启并检查 Diagnostics/source identity；
6. 在软件副本 maintenance notes 记录修改。

源码仓库常用命令：

```powershell
.\.tools\uv\uv.exe run pytest path\to\focused_test.py -q
.\.tools\uv\uv.exe run ruff check src\pilot_assessment path\to\focused_test.py
.\.tools\uv\uv.exe run ty check src\pilot_assessment
.\.tools\uv\uv.exe run python -m pilot_assessment.schemas.export
```

不要仅为证明 wiring 运行庞大 synthetic datasets；数值测试只覆盖实际改变的机制。

## 11. 恢复

Source edits 导致无法启动时，查看 stderr/Diagnostics 中精确 import/contract failure。通过 version control 恢复修改文件，或把原始 ZIP 解压到并列目录，再从恢复软件打开已有 project，不覆盖 project root。System model 被修改时，也只能复制完整目标软件目录或执行明确 model edit；应用运行时不能单独复制数据库文件。

## 12. Maintainer 检查单

- [ ] 已识别正确 durable scope；
- [ ] 能作为 current model content 的修改未硬编码进 core；
- [ ] 新 serialized meaning 使用新 contract/schema version；
- [ ] historical payloads 保持 byte-stable/readable；
- [ ] transaction/idempotency semantics 保留；
- [ ] paths 保持 relative/contained；
- [ ] poor performance 未被当作 missing data；
- [ ] focused tests 与一个相关 lightweight workflow 通过；
- [ ] source identity 与 restart behaviour 已验证。
