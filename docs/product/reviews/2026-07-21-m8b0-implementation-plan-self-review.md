# M8B-0 Implementation Plan Self-Review

| 字段 | 值 |
|---|---|
| Review ID | M8B0-PLAN-SELF-REVIEW-2026-07-21 |
| 日期 | 2026-07-21 |
| Artifact | `plans/2026-07-21-m8b0-system-model-ownership-implementation-plan.md` |
| Reviewer | 主代理 inline self-review |
| 结论 | **通过；可按 Task 0 → Task 8 顺序实施** |

## 1. 复核结论

实施计划完整覆盖已批准规格中的 system owner、无 project Model Studio、project/run 分离、legacy import、双项目共享、快照隔离和 portable baseline。计划没有把 M8B-1 source provenance、M8B-2 operator 扩展闭环、M8C 文档、M8D 备份或 M8E 最终交付冒充为 M8B-0 内容。

## 2. 关键不变量检查

- canonical ModelNode/TaskScheme 只有 system database 一个写入 owner；
- project 只接收 immutable execution materialization 和 RunSnapshot；
- system staged edit session 不随 project 切换；
- legacy collision 使用 typed reference remap，禁止任意 JSON 字符串替换；
- 普通模型修改不增加审批、发布或 per-save 测试门；
- 验证使用两个空 project、微型图和最小 Session，不使用重型合成数据；
- portable package 允许出厂 system baseline，但继续禁止用户 project/session/result。

## 3. 执行风险与控制

| 风险 | 控制 |
|---|---|
| 复用 project SQLite migrations 造成 ownership 混淆 | 物理表可复用，服务入口严格分离；测试断言 project current-model rows 为空 |
| run 在冻结前后读到不同 system revision | preflight 保存 model lock，run start 重新 stale-check，再写 project snapshot |
| 现有 dirty 工作树被误提交 | 每阶段仅选择性暂存本阶段文件，提交前检查 staged diff |
| 一次性重构过大 | 先完成 SystemStore 和 no-project read，再迁移 mutation/run，最后处理 legacy 与 portable |

未发现开放 P0/P1 计划问题。
