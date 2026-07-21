# M8D Current-System Packaging Design Self-Review

| 字段 | 结果 |
|---|---|
| 日期 | 2026-07-21 |
| 复核对象 | `2026-07-21-m8d-current-system-packaging-project-portability-and-diagnostics-design.md` |
| 结论 | PASS — 可交用户书面复核；尚未授权实施代码 |
| 科学边界 | 未校准 Evidence/BN/CPT；`formal_run_authorized=false` |

## 1. 核心事实复核

- 开发 WinUI 使用 `.pilot-assessment-local/system/`，不是 project-local model library；
- 设计时只读检查显示当前开发 system 已与 starter cardinality 不同，证明固定 starter counts 不能作为发布约束；
- 当前 `build_portable.py` 仍重新初始化 starter system，并硬编码 `53` nodes / `1` scheme；
- 因此“前端保存的 current system 随下一次正式打包交付”尚未实现，M8D 必须显式关闭该缺口；
- 本轮没有修改、复制或删除 `.pilot-assessment-local/system/`，也没有运行会写入该 store 的命令。

## 2. 设计完整性

| 检查项 | 结果 |
|---|---|
| 明确目标与非目标 | PASS |
| 说明 system/project/Python ownership | PASS |
| 说明保存、关闭、捕获与分发时点 | PASS |
| 无效 source 不静默 seed | PASS |
| 任意 node/scheme cardinality | PASS |
| 用户数据不进产品包 | PASS |
| project 关闭后完整目录复制 | PASS |
| diagnostics 不生成 support archive | PASS |
| 轻量测试边界 | PASS |
| failure semantics | PASS |

## 3. 跨文档一致性

- 新增 D-077，明确取代 `.paprojbackup`、Backup/Restore UI 和 backup completion gate；
- M8 productization outline 与 implementation outline 已改为 current-system packaging/project portability；
- M8C catalog 将未发布 `PAS-BACKUP-001` 迁移为 `PAS-PORTABILITY-001`；
- M8B、M6、M5 和 expert-editable 历史规格增加适用性说明；
- Product Overview、Glossary、README、Implementation Status、Validation、Known Limitations 与双语架构手册已统一；
- 历史 verification/self-review 中关于当时 backup 候选的记录不重写事实，由 D-077 和新规格明确取代其未来适用性。

## 4. 自动检查

- `catalog.json` JSON 解析：PASS；
- M8C `validate_manuals.py --status review`：PASS，12 catalog documents、3 selected sources；
- placeholder scan：新规格无 `TBD`、`TODO`、`FIXME` 或未决占位；
- `git diff --check`：PASS。

## 5. 实施前仍需完成

本自审不表示 M8D 已实现。书面规格经用户复核后，实施计划仍需冻结：

1. system source lock/inspection/capture 的文件与 API 边界；
2. 目标 clean edit workspace 的重建方式；
3. release manifest 的 dynamic model fields；
4. portable verifier 从 fixed starter counts 迁移到 captured facts；
5. Diagnostics 的最小新增字段；
6. disposable system 和 micro project 的轻量 vertical slices。
