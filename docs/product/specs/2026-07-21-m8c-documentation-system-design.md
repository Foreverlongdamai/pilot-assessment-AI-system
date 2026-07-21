# M8C Documentation System and Versioned DOCX Design

> **状态：已由 2026-07-21 用户“继续推进 M8B 和之后计划实施”的授权接受。** 本规格把 M8 总路线图中的文档要求收口为可实施合同；M8C-0 可立即实施，M8C-1 的最终截图、备份、发布验收内容必须等待对应产品能力稳定。

| 字段 | 值 |
|---|---|
| 里程碑 | M8C — Documentation and Versioned DOCX Pipeline |
| 产品版本 | 0.1.0 engineering |
| 权威上游 | M8 outline、D-031–D-071、当前 contracts/UI/release layout |
| 目标读者 | evaluator、expert、developer、maintainer、release maintainer |
| 科学状态 | engineering-only；不把 starter 内容写成 validated assessment method |

## 1. 目标与明确排除

M8C 建立一套可以长期维护、自动生成、版本化和随产品交付的正式文档系统：

1. Markdown 是唯一人工维护的正文；
2. 中文与英文分别维护、分别生成，不在同一段落混排；
3. 每份手册有稳定 document ID、metadata、版本、读者、信息类型、科学状态和 related-doc references；
4. DOCX 由固定工具链生成，带封面、静态目录、真实 Heading styles、页眉页脚、图表、代码、表格、版本与变更记录；
5. 《系统技术参考总册》从模块原稿聚合，不复制出第三套正文；
6. 文档构建执行结构、链接、隐私、版本、截图、图和 DOCX render QA；
7. release package 只携带最终文档，不携带构建缓存、测试数据或用户数据。

M8C 不进行领域专家科学校准，不认证 ISO/IEC/IEEE 合规，不把未完成 M8D/M8E 行为写成可用功能，也不在产品中建设富文本编辑器。

## 2. 轻量方法参考

- ISO/IEC/IEEE 26514:2022 只用于读者、任务、结构、呈现和维护意识；
- ISO/IEC/IEEE 42010:2022 只用于 stakeholder、concern、viewpoint 和 view 的架构说明；
- Diátaxis 只用于标记 tutorial、how-to、reference、explanation 的章节目的；
- C4 以 system context 和 container 为必选图，component 只在源码、protocol 或 release 关系难以用文字说明时使用；
- 项目实际 UI、contracts、source tree、release layout 和用户决策永远优先；文档只写“参考”，不写“认证符合”。

## 3. 权威模型与目录

```text
docs/product/manuals/
├── catalog.json                         # 12 类文档、语言、stable IDs、聚合规则
├── schemas/document-metadata.schema.json
├── assets/
│   ├── diagrams/                        # .mmd 权威图源 + 确定性 SVG/PNG
│   └── screenshots/                     # 受控截图及 manifest；M7 UAT 后补齐 final
├── shared/                              # 术语、warning、support 等可复用片段
├── zh-CN/                               # 中文 Markdown 权威正文
├── en-GB/                               # 英文 Markdown 权威正文
└── template/pilot-assessment-reference.docx

tools/documentation/
├── pyproject.toml / uv.lock             # pinned Python 文档工具链
├── package.json / pnpm lock             # pinned Mermaid renderer；node_modules 不提交
├── build_manuals.py
├── validate_manuals.py
└── ...                                  # metadata、Markdown、DOCX、diagram helpers

dist/documentation/
└── PilotAssessment-<product-version>-docs/
    ├── catalog.json
    ├── zh-CN/*.docx
    └── en-GB/*.docx
```

`dist/` 继续为生成物而非 Git 权威。构建模板是检查进仓库的、无正文的样式基线；生成器不会在模板中隐藏业务文本。

## 4. Metadata 与 catalog 合同

每个 Markdown 使用 `+++` 包围的 TOML front matter。至少包含：

```toml
document_id = "PAS-ARCH-001"
language = "zh-CN"
title = "产品总览与系统架构"
product_version = "0.1.0"
document_version = "0.1.0"
status = "review"
audience = ["evaluator", "expert", "developer", "maintainer"]
information_types = ["explanation", "reference"]
scientific_status = "engineering-only"
related_documents = ["PAS-QUICKSTART-001", "PAS-EXPERT-EVIDENCE-001"]
```

允许状态为 `draft | review | released | superseded`；语言为 `zh-CN | en-GB`；科学状态为 `engineering-only | expert-reviewed | calibrated`。catalog 保存：

- 12 个 logical document ID；
- 每种语言的 source、output file、title 和 status；
- master technical reference 的有序组成；
- release inclusion 与 dependency gate；
- screenshot/diagram stable IDs。

同一 logical document 的中英文必须共享 document ID、product/document version、科学状态和 related-document set；标题与正文分别本地化。技术 identity、文件名、RPC、schema、operator ID、错误 ID 和代码保持英文原值。

## 5. 十二类手册与依赖门

| ID | 手册 | 当前依赖 |
|---|---|---|
| PAS-ARCH-001 | 产品总览与系统架构 | M8B stable，可在 M8C-0 完成 |
| PAS-QUICKSTART-001 | 安装、启动与快速开始 | M7 UAT 最终路径前保持 review |
| PAS-EVALUATOR-001 | 普通评估用户操作手册 | M7 UAT 最终路径与截图 |
| PAS-EXPERT-EVIDENCE-001 | Evidence 与任务方案专家设计手册 | M7 UAT/D-055 |
| PAS-EXPERT-BN-001 | BN、父节点、状态与 CPT 专家手册 | M7 UAT/D-055 |
| PAS-SESSION-001 | Session Bundle 与五类原始输入接口手册 | 当前 contracts stable，可先写 reference |
| PAS-PYTHON-EXT-001 | Python operator 与源码扩展开发手册 | M8B complete，可在 M8C-0 迁入正式体系 |
| PAS-PYTHON-CORE-001 | Python 核心代码维护手册 | M8B complete，可先写 source map |
| PAS-PROTOCOL-CSHARP-001 | 前后端协议与 C# 开发手册 | M7/M8B stable，可先写 |
| PAS-BACKUP-001 | 项目备份、恢复、迁移与故障排查 | M8D gate |
| PAS-RELEASE-001 | 发布构建与交付验收手册 | M8E gate |
| PAS-TECHREF-001 | 系统技术参考总册 | 从 1–11 聚合；不单独维护正文 |

依赖未关闭的文档可以生成 `draft/review` 内部候选，但不得进入 `released` catalog 或被描述为最终用户操作事实。

## 6. DOCX 视觉与结构合同

选择 documents skill 的 `compact_reference_guide` preset 作为所有手册的唯一正文样式，并选择 `editorial_cover` 作为统一首屏模式。精确 token：

- US Letter portrait，四边 `1.0 in`，header/footer `0.492 in`，内容宽 `9360 DXA`；
- Calibri 11 pt，body `after=6 pt`、`line=1.25`；
- H1 `16 pt #2E74B5 before=18 after=10`；H2 `13 pt before=14 after=7`；H3 `12 pt #1F4D78 before=10 after=5`；
- bullet/decimal marker `0.187 in`，text `0.375 in`，hanging `0.188 in`，after `4 pt`，line `1.25`；
- table 总宽 `9360 DXA`、indent `120 DXA`、cell margins `80/80/120/120`，header fill `#E8EEF5`；
- navy `#203748`、blue `#2E74B5`、muted `#5A6470`、green accent `#1F7A64`；
- 封面包含产品、手册标题、document ID、产品/文档版本、状态、读者、科学状态；不使用装饰性表格堆正文；
- 页眉显示产品和短标题；页脚显示 document ID/version 与动态页码；
- 使用真实 Heading styles、真实 Word numbering、固定 DXA table geometry；不使用假标题、Unicode 假 bullet、固定 row height 或百分比表格宽度。

模板和生成器都接受该 token map 的结构审计。任何偏差必须是命名 override，不能成为随机直接格式。

## 7. Markdown 到 DOCX

M8C-0 支持项目手册实际需要的 CommonMark 子集：

- H1–H4、paragraph、bold/italic/code/link；
- real bullet/numbered lists；
- fenced code blocks；
- tables；
- images/diagram references 与 captions；
- note/warning callouts；
- stable document references `[[DOC:PAS-...]]` 和 section anchors；
- page break marker 和 master aggregation marker。

不支持的 token 使构建失败，不能静默丢失。静态目录由 heading bookmarks 生成并在 headless 环境可读；Word-native TOC field 可附带，但不能成为渲染正确性的唯一依赖。跨文档引用生成相对 DOCX hyperlink 和可读 title/document ID。

## 8. 图、截图与隐私

- Mermaid `.mmd` 是图的权威源，renderer/version/config 被锁定；生成 SVG 后转为适合 DOCX 的 PNG，并保存 source/render SHA-256；
- C4 context/container 图必须含 scope、reader、legend 和关系标签；
- 每幅图在 Markdown 中有 caption、stable asset ID 和文字替代说明；
- screenshot manifest 至少保存 screenshot ID、product version、language、theme、source path、SHA-256、captured-at、privacy review、status；
- final screenshot 必须来自对应 build，不能含真实 Session、用户名、外部绝对路径、个人/生物数据；
- M7 UAT 前只使用图和无敏感 mock/synthetic UI；最终操作截图保持 pending，不伪造。

## 9. 构建、验证与发布

单一入口：

```powershell
.\tools\documentation\build_docs.ps1 validate
.\tools\documentation\build_docs.ps1 build --status review
.\tools\documentation\build_docs.ps1 render-check
```

验证至少覆盖：

1. catalog/front matter/schema/parity；
2. source、relative Markdown link、stable document/asset reference；
3. unsupported Markdown 与未决 placeholder；
4. product/document version、scientific status 和 dependency gate；
5. diagram/screenshot hash、隐私和绝对路径扫描；
6. DOCX zip integrity、styles、headings、numbering、table geometry、TOC/bookmarks、header/footer；
7. render 成每页 PNG，并对所有页面做视觉 QA；
8. master 只从模块构建，release catalog/hash 与实际输出一致。

M8A/M8B portable builder 在 M8C-0 后可携带当前 `released` 文档；`review/draft` 只有在明确 engineering package 时进入 `docs/review/`，不能冒充最终手册。

## 10. M8C 分段完成门

### M8C-0 Documentation Infrastructure

- catalog、metadata schema、双语 source layout、template、pinned toolchain 和 build/validate/render pipeline 存在；
- 中英文 `PAS-ARCH-001` 完整生成并通过逐页视觉 QA；
- context/container 图、静态 TOC、table/list geometry、header/footer、version 和 cross-doc reference 可验证；
- `PAS-PYTHON-EXT-001` 被纳入新 catalog 或明确迁移映射；
- 12 类文档依赖门都在 catalog 中，不用空白正文冒充完成。

### M8C-1 Final Manuals

- 11 个模块手册双语正文完成，`PAS-TECHREF-001` 自动聚合；
- M7 最终截图、M8D、M8E 内容与 UI terminology parity 完成；
- 24 个语言版 DOCX（12 × 2）通过结构、链接、privacy、render 和 release-copy 验证；
- 只有此时才关闭整体 M8C。

## 11. 自审边界

- 文档状态不会反向改变代码、科学状态或产品完成状态；
- DOCX 是生成物，任何手工修改都会在下一次构建被覆盖；
- 英文技术 identity 不翻译；UI 文案按语言本地化；模型 canonical 内容仍遵循 D-055；
- 文档工具只用于构建交付，不进入 Python assessment runtime；
- M8C-0 完成后应转向 M8D，再回填 backup/release 手册并关闭 M8C-1/M8E。
