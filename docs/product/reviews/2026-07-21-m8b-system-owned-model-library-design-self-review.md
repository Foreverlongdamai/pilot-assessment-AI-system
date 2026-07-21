# M8B System-Owned Model Library Design Self-Review

| 字段 | 值 |
|---|---|
| Review ID | M8B-DESIGN-SELF-REVIEW-2026-07-21 |
| 日期 | 2026-07-21 |
| Artifact | `specs/2026-07-21-m8b-system-owned-model-library-and-editable-backend-provenance-design.md` |
| Reviewer | 主代理 inline self-review |
| 结论 | **内部一致；2026-07-21 用户批准并进入 M8B-0 实施** |

## 1. 复核范围

本次只复核 M8B 书面设计是否准确落实用户选择的“每个解压软件副本拥有自己的系统模型库”，以及它与 M6/M7 project persistence、M8A portable layout、RunSnapshot 和 editable Python source 的衔接。未复核算法科学性、CPT 合理性或最终 M8C–M8E 交付内容。

## 2. 发现与修正

| 级别 | 初始问题 | 修正 |
|---|---|---|
| P1 | 若运行中编辑 `.py`，磁盘 hash 可能代表新文件，而 Python 进程仍执行旧 import | 冻结 `loaded_source_identity`；preflight 检测 disk drift 并要求重启，不把 baseline divergence 当阻断条件 |
| P1 | legacy ID remap 若在任意 task-binding JSON 中文本替换，可能误改普通字符串 | 只改写明确 typed reference；不做字符串猜测，无法验证时整笔迁移失败 |
| P1 | 两个 legacy project 都有 dirty draft 时，单一 system edit session 无法安全自动合并 | 只恢复一套 dirty session；第二套保留原文件并返回 recoverable conflict |
| P2 | 物理 SQLite table 与逻辑 owner 可能被误解为必须立即删除所有 legacy tables | 明确 system/project 可以复用 SQLite kernel，但 canonical current state 只有 system owner；legacy project tables只读保留 |
| P2 | “源码修改自由”可能被误解为运行中热重载 | 明确关闭应用、编辑、重启；不实现 hot reload 或隐藏 fallback |

## 3. 一致性检查

- 与 D-047–D-053 一致：节点仍是完整对象，TaskScheme 仍是激活集合，C# 不复制算法；只把 ownership 从 project scope 提升到 software-copy scope。
- 与 D-056 一致：所有模型修改仍进入一个后端持久 edit session，关闭应用时 Save all/Discard all/Cancel；project 切换不再触发模型提交。
- 与 D-063 一致：每个软件副本只有一棵活动 backend source；没有 project source overlay。
- 与 D-064 一致：ZIP 不包含用户 project/Session/result；`system/model-library.sqlite3` 是产品系统状态，不是用户评估数据。
- 与 M6 project portability 一致：project 继续自带 exact Session、RunSnapshot、result 和 artifacts；历史运行不依赖 current system model。
- 与 M8D 边界一致：本阶段只定义 ownership、migration receipt 和 source snapshots，不提前实现完整 backup/restore UI。

## 4. Placeholder、范围与歧义扫描

- 规格未包含 `TBD`、`TODO` 或未选择的存储位置；
- system root、owner、project creation、project switching、run freeze、legacy migration、dirty conflict、source identity 和错误状态均有确定语义；
- M8B 拆为 M8B-0/1/2，实施计划应按这一顺序拆分，不把整个 M8C/M8D/M8E 混入；
- 验证只使用两个空 project、微型图和 disposable release copy，不引入重型多模态 fixture；
- 用户已明确批准 written spec；D-066–D-071 已正式写入决策记录，M8B-0 可以进入生产代码实施。

未发现开放 P0/P1 设计问题。
