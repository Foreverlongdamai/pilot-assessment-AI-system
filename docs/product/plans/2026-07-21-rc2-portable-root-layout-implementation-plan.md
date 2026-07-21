# RC.2 Portable Root Layout Implementation Plan

> 执行方式：inline、轻量回归、完成后构建新 candidate；不得移动或重写 `v0.1.0-rc.1`。

## Task 1：冻结 RC.1 验收结论

- [x] 记录用户结论 `changes-required`、94 个根目录文件夹与 374 个根目录文件。
- [x] 保留 RC.1 tag、commit 与产物不变。

## Task 2：建立根目录合同

- [x] 增加八个语义目录、`README.txt` 与唯一 launcher 的精确白名单测试。
- [x] 让 release identity 支持递增的 `rc.<positive-integer>`，不再把 builder 锁死在 rc.1。
- [x] 把 handoff 文档收纳到 `docs/`。

## Task 3：实现启动边界

- [x] 新增 self-contained single-file `PilotAssessment.exe` launcher。
- [x] 将 desktop publish 整体复制到 `app/`。
- [x] 让 WinUI 后端定位器从 `app/` 解析父级产品根目录。
- [x] 将 launcher 源码随 `developer/desktop-source/` 交付。

## Task 4：修订 manifest、verifier 与文档

- [x] 升级 release manifest 并写入 `portable_layout`。
- [x] 让 packaged/external verifier 使用动态 candidate identity，并从 root launcher 启动。
- [x] 修订双语 Markdown 权威源、release handoff 与 README。
- [x] 从 clean annotated `v0.1.0-rc.2` source 生成 24 份 released DOCX。

## Task 5：RC.2 交付门

- [x] Python release/documentation tests 通过。
- [x] .NET unit/contract/x64 Release gates 通过。
- [x] 创建 annotated `v0.1.0-rc.2`，证明 peel 到 clean `HEAD`。
- [x] 构建 RC.2 ZIP，确认根目录计数为 8 directories / 2 files / 1 launcher。
- [x] 在仓库外 restricted-PATH extraction 中完成 editable source、operator extension、run 与真实桌面启动验证。
- [x] 记录 hashes、counts、process/window evidence 与 `user_acceptance=pending`。
