# M8B-1 Implementation Plan Self-Review

| 字段 | 值 |
|---|---|
| Review ID | M8B1-PLAN-SELF-REVIEW-2026-07-21 |
| 日期 | 2026-07-21 |
| Artifact | `plans/2026-07-21-m8b1-source-provenance-and-snapshot-implementation-plan.md` |
| Reviewer | 主代理 inline self-review |
| 结论 | **通过；可直接实施** |

## 1. 覆盖性结论

计划完整覆盖批准规格 §11–§13、§17 和 §18：loaded identity、release baseline、disk drift、restart-required、内容寻址源码快照、历史合同兼容、runtime status、Diagnostics 和 portable 重建均有明确 owner 与验收项。

## 2. 关键边界复核

- 没有把 starter Evidence/BN/CPT 的科学正确性设为验收条件；
- 没有把源码修改误建模成 project-local 修改；
- 没有让 preflight 自动执行 artifact 内的 Python；
- 没有把绝对路径、用户数据、虚拟环境或第三方包字节写入 snapshot；
- v0.1 历史记录保留可读，新 run 使用严格 v0.2，不以可空字段假装完成；
- restart-required 只处理同一进程的 loaded/disk 漂移，重启后允许专家修改后的源码运行；
- 验证采用微型 Session 和 focused tests，没有引入重型合成数据。

## 3. 主要风险与控制

| 风险 | 控制 |
|---|---|
| build/runtime 各自实现 hash 导致口径漂移 | 抽取单一 Python provenance 实现，builder/verifier 显式校验同一 algorithm/version |
| snapshot owner 依赖尚未生成的 preflight ID | 先由确定性 artifact bytes 得到 ID，再构建 preflight identity，最后用稳定 owner 绑定 |
| 修改源码后旧进程继续跑出混合结果 | preflight 与 run start 两次重扫并阻止运行，要求重启 |
| 合同升级破坏历史 JSON | 新增 v0.2 类型并保留 v0.1 parser/type union |
| diagnostics 被误读为算法质量结论 | 文案明确为技术执行身份，不出现“通过科学验证”表述 |

未发现开放 P0/P1 计划问题。

