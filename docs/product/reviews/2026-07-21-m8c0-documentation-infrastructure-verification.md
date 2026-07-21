# M8C-0 Documentation Infrastructure Verification

| 字段 | 值 |
|---|---|
| 日期 | 2026-07-21 |
| 结论 | **PASS — M8C-0 engineering gate closed** |
| 范围 | 文档 catalog/schema、固定工具链、DOCX 生成、C4 assets、代表手册、render QA、portable release integration |
| 不覆盖 | M7 用户验收、最终 UI 截图、M8D、M8C-1、M8E、领域专家科学校准 |

## 1. 实现结果

- `docs/product/manuals/catalog.json` 登记 12 类逻辑文档及其 stable document IDs、语言和前置 gate；没有用空白正文冒充完成手册。
- `tools/documentation/` 使用独立 `pyproject.toml`、`uv.lock`、`package.json` 和 `pnpm-lock.yaml`，不把文档依赖加入 assessment runtime。
- Markdown front matter、catalog、语言配对、链接、交叉引用、隐私、版本、asset manifest 和 DOCX 结构均由 fail-closed validators 检查。
- 保存 C4 system-context/container Mermaid source、SVG、PNG、caption、alt text 及 source/render hashes。
- portable engineering package 只把 `review` 文档放入 `docs/review/<language>/`；没有把它们标为 `released`。

## 2. 代表文档与逐页检查

| 文档 | 语言 | 页数 | DOCX SHA-256 |
|---|---:|---:|---|
| `PAS-ARCH-001` | zh-CN | 11 | `1b376018b4db8ff10744acdb7b172e56c23dca7824e1a0664e7551dbe874f35d` |
| `PAS-ARCH-001` | en-GB | 10 | `aebfdb7f3e79c59d7c16feae8b3be6aee46edc4b270909a75026174b3eb685a6` |
| `PAS-PYTHON-EXT-001` | en-GB | 7 | `61d0f55ffeccc52f3dc7c2f2a52fb9f8771d16ada47c9e0fa5986d8da5a08e0e` |

三份 DOCX 的 28 页均通过项目受控的 headless LibreOffice → PDF → PyMuPDF PNG 路径渲染，并逐页检查。最终 source hygiene 修订后，24 页与已检查页面的像素 hash 完全一致；4 个含 C4 图的变化页面再次人工查看通过。修正了 Markdown emphasis、连续编号、表格 inline code 和输出目录稳定性；最终页面未发现 clipping、overlap、不可读表格或异常分页。

documents skill 提供的通用 `render_docx.py` 在本 Windows 主机把盘符路径转换为 LibreOffice URI 时不兼容，并触发 LibreOffice `bootstrap.ini` 弹窗。该进程已终止，未改动产品或用户数据；M8C 使用项目内正确调用 `Path.as_uri()` 的无界面 renderer 完成相同 QA。后续不把不兼容的通用脚本作为本项目门禁。

## 3. 确定性与发布闭环

连续两次构建得到完全相同的五个关键 hash：

- documentation manifest：`5d22fbaaeb23a8049fbb07fbae005c780de426a74c24ef687c69a065fa661436`
- source catalog：`4168ca61a985593630f1488d1c7c57367ae92be1b3fdb45def035d1626da241e`
- 三份 DOCX：见上表。

`PilotAssessment-0.1.0-win-x64` M8C-0 staging package 完成：

- package bytes：`768,563,951`
- checksummed files：`4,288`
- backend source files：`294`
- documentation outputs：`3 review / 0 released`
- clean operator catalog：`45`；disposable extension verification：`46`
- 示例 extension recipe：`2.75 / desired`
- clean disposable-copy static verifier：`PASS`
- extension/install/restart/run/source-snapshot verifier：`PASS`

static 与 extension/run verifier 都必须在 disposable package copy 中执行，因为真实 sidecar 启动会写入 SQLite 运行元数据；不允许对待归档 staging 目录原地执行验收。验证副本中 Python extension 的安装、recipe 执行和评估运行不会污染最终 package；最终 package 仍为 clean system model，包含 `53` starter nodes、`1` starter TaskScheme、零用户 Session/project/result 数据。

## 4. 结论与下一门

M8C-0 已证明文档系统能够确定性地产生受控 DOCX，并由发布构建器按状态安全装入工程包。它没有证明 12 类双语手册已经完成。**后续适用性：D-077 已取消 backup/restore 并把 M8D 重定义为 current-system packaging/project portability/diagnostics。** M8C-1 应在该行为冻结后回填相应手册、最终 M7 UI 截图和技术总册，M8E 才能生成 released 文档与最终交付候选。
