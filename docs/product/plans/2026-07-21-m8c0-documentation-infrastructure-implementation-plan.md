# M8C-0 Documentation Infrastructure Implementation Plan

> **执行方式：INLINE、轻量垂直切片。** 本计划只关闭文档基础设施和一套双语代表手册，不批量生成空壳、不伪造最终 UI 截图，也不提前关闭 M8C-1。

| 字段 | 值 |
|---|---|
| 日期 | 2026-07-21 |
| 状态 | 已授权，开始实施 |
| 规格 | [M8C Documentation System Design](../specs/2026-07-21-m8c-documentation-system-design.md) |
| 上游 | M8B complete |
| 下游 | M8D；随后 M8C-1/M8E |

## Task 0 — 决策、规格与自审

- [x] 保存 M8C 正式规格；
- [x] 写入 D-072–D-076；
- [x] 保存计划自审并确认不把 M7/M8D/M8E 冒充完成。

## Task 1 — Catalog、schema 与 source layout

- [ ] 建立 12 类 stable document catalog；
- [ ] 建立 metadata JSON Schema 和 TOML front matter parser；
- [ ] 建立 `zh-CN`、`en-GB`、shared/assets/template 目录；
- [ ] 建立 screenshot/diagram manifests 和依赖门。

## Task 2 — Pinned documentation toolchain

- [ ] 建立独立 Python documentation project 和 lock，不污染 assessment runtime；
- [ ] 固定 python-docx、Markdown parser、Pillow/lxml；
- [ ] 固定 Mermaid renderer/config，node_modules 与 cache 不提交；
- [ ] 提供一个 PowerShell 入口，优先使用仓库 `.tools/uv` 与明确 Node/pnpm 路径。

## Task 3 — Reference template 与 DOCX primitives

- [ ] 实现 `compact_reference_guide` 精确 token map；
- [ ] 生成 editorial cover、running header/footer、page number；
- [ ] 实现真实 heading/list numbering、固定 DXA tables、code/callout/image/caption；
- [ ] 生成并审计 reference template。

## Task 4 — Markdown、目录与交叉引用

- [ ] 解析受支持 Markdown tokens，未知 token fail closed；
- [ ] 生成 deterministic heading bookmarks/static TOC；
- [ ] 解析 `[[DOC:...]]` 与 section references；
- [ ] master aggregation 只读取模块 sources。

## Task 5 — Mermaid/C4 与受控 assets

- [ ] 保存 system context/container `.mmd`；
- [ ] 确定性渲染并保存 source/render hash；
- [ ] 写 caption、asset ID、alt text 与 reader/scope；
- [ ] screenshot manifest 先明确 final screenshots pending M7 UAT。

## Task 6 — 双语代表手册

- [ ] 完成 `PAS-ARCH-001` 中文原稿；
- [ ] 完成 `PAS-ARCH-001` 英文原稿；
- [ ] 将现有 Python extension 手册映射到 `PAS-PYTHON-EXT-001`，不复制漂移正文；
- [ ] 生成两份 versioned DOCX 与 documentation catalog。

## Task 7 — Validators 与 render QA

- [ ] metadata/catalog/language parity/link/reference/privacy/version validators PASS；
- [ ] DOCX structural/preset/table/navigation audit PASS；
- [ ] 用 documents skill `render_docx.py` 渲染全部代表手册页面；
- [ ] 主代理逐页查看 100% PNG，修复所有 clipping、overlap、表格和分页问题；
- [ ] 记录 M8C-0 fresh verification。

## Task 8 — Release integration 与状态收口

- [ ] portable builder 只复制符合 inclusion policy 的 generated manuals/catalog；
- [ ] external release verifier 检查 docs catalog/hash 且不把 draft 冒充 released；
- [ ] 更新 README、文档中心、Implementation Status 与 M8 roadmap；
- [ ] 提交 M8C-0 独立检查点并进入 M8D。

## 完成边界

M8C-0 完成只代表“文档系统可以可靠生产正式手册”。M7 UAT 截图、M8D backup 内容、M8E release acceptance、其余双语手册和总册仍属于 M8C-1/M8E，不得在本计划中关闭。
