# M8C-0 Documentation Infrastructure Plan Self-Review

| 字段 | 值 |
|---|---|
| Review ID | M8C0-PLAN-SELF-REVIEW-2026-07-21 |
| 日期 | 2026-07-21 |
| Reviewer | 主代理 inline self-review |
| 结论 | **通过，可实施** |

## 覆盖性

计划从 metadata/catalog 开始，经过 pinned toolchain、模板、Markdown、目录/引用、Mermaid/C4、双语代表手册、DOCX render QA 到 release integration，覆盖 M8C-0 的完整可重复垂直切片。它没有把“创建 12 个文件名”误当作 12 份手册完成。

## 关键边界

- Markdown 是正文权威；DOCX、PNG、SVG 和 master 都是可重建生成物；
- M8C-0 只完成双语架构代表手册与 extension 手册迁移映射；
- final UI screenshots 等待 M7 UAT；backup/release 手册等待 M8D/M8E；
- 工具链与 assessment private runtime 隔离；
- 标准只轻量参考，不声称认证；
- 每个 DOCX 必须 render 并逐页视觉检查，结构检查不能替代视觉 QA；
- starter Evidence/BN 继续标记 engineering-only，不因进入手册而变成科学真值。

## 风险与控制

| 风险 | 控制 |
|---|---|
| 双语内容漂移 | catalog parity + shared IDs/version/related-doc validator |
| DOCX 看似生成但版面损坏 | render-to-PNG + every-page visual review |
| 总册形成第三份正文 | aggregate-only catalog entry，构建时拼接模块 body |
| Mermaid/字体在机器间漂移 | renderer/config/version lock + source/render hash |
| 未完成功能进入用户手册 | dependency gate + status/inclusion policy |
| screenshot 泄露路径或用户数据 | manifest + privacy review + absolute-path/content scan |

未发现阻止实施的 P0/P1 计划缺口。
