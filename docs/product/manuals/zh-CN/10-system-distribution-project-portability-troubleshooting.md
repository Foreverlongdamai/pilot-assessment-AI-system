+++
document_id = "PAS-PORTABILITY-001"
language = "zh-CN"
title = "系统分发、项目迁移与故障排查"
short_title = "迁移与故障排查"
product_version = "0.1.0"
document_version = "0.1.0"
status = "released"
audience = ["evaluator", "expert", "developer", "maintainer", "release"]
information_types = ["how-to", "reference"]
scope = "说明如何复制 software/system 或 user project、恢复常见故障并保持 source/model/run identities。"
prerequisites = ["复制前能够关闭应用", "能够访问需要迁移的完整源目录"]
scientific_status = "engineering-only"
related_documents = ["PAS-QUICKSTART-001", "PAS-SESSION-001", "PAS-PYTHON-EXT-001", "PAS-RELEASE-001"]
support = "恢复前保留原始 ZIP、release hash、Diagnostics 摘要与不含隐私的目录清单。"
release_channel = "release-candidate"
release_label = "v0.1.0-rc.3"
user_acceptance = "pending"
+++

# 系统分发、项目迁移与故障排查

## 1. 两种内容独立复制

产品有意不设计专用 Backup/Restore 归档。Windows 整目录复制就是完整迁移机制，但必须选对范围：

| 复制对象 | 包含 | 不包含 |
|---|---|---|
| 完整已解压软件目录 | executable/runtime、editable Python、dependencies、global `system\` model library、manuals 与 release manifests | 存放在外部的 user projects/Sessions |
| 完整 user project root | project metadata、SQLite、managed Sessions、RunSnapshots、runs、results、artifacts、logs 与 staging metadata | Python source 与 global system model |

复制软件会带走 current Evidence/BN/task-scheme library 和 Python modifications；复制 project 会带走数据与历史。因为 project records 使用 contained relative paths，两者可独立迁移。

## 2. 迁移或复制 software/system

1. 保存或放弃全部 staged system-model edits；
2. 关闭所有 app instances，确认根启动器、`app/PilotAssessment.Desktop.exe` 与 child Python process 已退出；
3. 复制完整 product root，不能只选 EXE、`system\` database 或 `backend\`；
4. 从目标产品根目录启动唯一入口 `PilotAssessment.exe`；
5. 在 Diagnostics 确认 product/release label、model library identity/counts、source identity 与 dependency/operator identity。

复制完成后，目标软件与原软件独立演化，不会自动同步。应保留原始 candidate ZIP 与 `.sha256` 作为 delivered baseline。

## 3. 迁移或复制 project

1. 等待 import/run 进入 durable final state；
2. 关闭应用，确保 SQLite/logs/artifacts 无 writer；
3. 复制完整 project root，包括 hidden/empty managed directories；
4. 在目标软件选择“打开项目”，选中复制后的 root；
5. 开始新 run 前查看 compatibility 与 recovery diagnostics。

不要只复制 `project.sqlite3`；managed Session files 与 content-addressed artifacts 属于同一 project。不要把 project 放进以后会被替换或重新分发的 product root。

Historical runs 保存 frozen model/source identities。即使目标软件的 current global model 不同，打开 project 也不会重写历史；future run 使用目标软件当前 saved model。

## 4. 复现或恢复 software baseline

需要恢复 delivered code 时，把原始 verified ZIP 解压到新目录，不能覆盖 locally modified copy。随后选择：

- 用 clean software 打开已有 project；
- 或先复制完整目标软件目录，从而带走其完整 `system\`，再启动。

当前候选不提供“合并两个 system databases”按钮。需要保留两套独立演化 global model libraries 时，应保留两个并列软件副本。

## 5. 理解 source divergence

直接修改 `backend/src/pilot_assessment/`、`backend/pyproject.toml`、`backend/uv.lock` 或 private dependencies 会主动改变 backend identity，使其与 release baseline 不同；这是允许行为，并在 Diagnostics 显示。

修改后：

1. 完整关闭并重启应用；
2. 确认 `restart_required` 已清除；
3. 检查 operator catalog/dependencies；
4. 运行一个相关的小型 workflow；
5. 让新 runs 保存新的 source artifact。

不能人工改 checksum manifest 来伪装成未修改系统，provenance 应真实描述差异。

## 6. 启动故障排查

| 现象 | 检查 | 处理 |
|---|---|---|
| 双击无反应 | ZIP 是否完整解压、路径可写、EXE 是否与依赖分离 | 将完整 ZIP 重新解压到短可写目录 |
| Windows App Runtime missing | 候选包是否完整、architecture 是否匹配 | 使用完整 candidate package；仍出现时记录原始弹窗 |
| Backend startup failed | Diagnostics/stderr、active source syntax/import、private runtime | 恢复或修复命名 source/dependency，重启整个 app |
| 反复出现 project chooser | 目标 root 缺失/invalid 或尚无 current project | 新建 project 或打开完整 existing root |
| File locked | 其他 desktop/sidecar process 仍占用 system/project | 关闭所有 instances，运行期间不要复制 |

## 7. Import 与 run 故障排查

| 现象 | 检查 | 处理 |
|---|---|---|
| 原始导出无法识别 | top-level `streams\`、optional `annotations\`、adapter diagnostics | 修正目录形状或增加 trusted adapter |
| Checksum mismatch | 复制后 source bytes 是否变化 | 重新导出/复制，不能忽略 integrity failure |
| 部分 Evidence unavailable | managed manifest 中缺失 modality/input binding | 接受 partial inference 或提供真实完整 Session |
| Preflight blocked | incomplete CPT、missing operator、cycle、dirty edit session、schema incompatibility | 按 exact blocking diagnostic 修正，不能伪造数据 |
| 差分数被误记为 missing | method/adapter 返回错误 status | finite poor performance 应保持 computed，修复机制 |
| Run interrupted | Diagnostics recovery state | 重新打开 project，reconcile/retry durable boundary |

## 8. Model edit 故障排查

| 现象 | 检查 | 处理 |
|---|---|---|
| 启用 child 自动点亮其他节点 | fixed ancestor closure | 预期行为，检查 child complete parents |
| parent 不能静默停用 | 存在 active downstream impact | 审阅 descendants，选择继续级联或取消 |
| 修改影响多个任务 | 同一 complete node 被共享 | 为 task-specific difference 复制节点，再改 activation |
| parent 在不同任务应不同 | 一个节点被过度复用 | 新建 copied child 并设置自身 fixed parents |
| 关闭弹出确认 | 存在 staged system edits | 保存并关闭、放弃并关闭或取消 |
| Revision conflict | expected revision 已被新 saved state 取代 | reload/rebase，不盲目覆盖 |

## 9. 隐私安全的支持材料

优先提供 release label、UI language、stable error code/trace ID、Diagnostics summary、model/source identities，以及只含 names/sizes 的目录树。删除 user/home paths 与 participant identifiers。未经授权数据治理流程明确要求，不能发送 raw gaze、EEG、ECG、pilot-camera images 或 Session rows。

## 10. 迁移检查单

- [ ] 已选择正确范围：whole software 或 whole project；
- [ ] app 与 child process 已关闭；
- [ ] source directory 完整复制；
- [ ] original ZIP/hash 已保留；
- [ ] destination 可打开且已记录 Diagnostics identities；
- [ ] historical runs 保持不变；
- [ ] redistributed product ZIP 未加入 user project/Session；
- [ ] support material 不含 private path/biometric content。
