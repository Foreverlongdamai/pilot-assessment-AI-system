# Product Manual Sources

This directory is the authoritative source for M8C manuals.

- `catalog.json` defines the twelve logical documents, language variants, dependency gates and output names.
- `zh-CN/` and `en-GB/` contain language-specific Markdown. Each source begins with TOML front matter between `+++` delimiters.
- `assets/diagrams/` stores Mermaid source and deterministic renders; `assets/screenshots/` stores only privacy-reviewed UI captures.
- `template/` contains the generated style-only DOCX reference template.
- `dist/documentation/` contains generated DOCX deliverables and is never the source of truth.

Edit Markdown, metadata or controlled assets, then run the documentation build. Do not hand-edit generated DOCX files.
