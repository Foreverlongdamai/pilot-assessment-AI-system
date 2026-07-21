# Product Review Records

本目录保存重要规格、计划和实现检查点的复核证据。它不取代 `DECISIONS.md`、已批准规格、实施计划、代码测试或 Git 历史；其作用是让后续维护者知道某项方案由谁、按什么范围复核，发现了什么问题，以及问题如何关闭。

每条记录至少包含：

- review ID、日期、被复核 artifact 与 Git 基线；
- 复核范围和明确不覆盖的范围；
- reviewer 类型（主代理、独立子代理、外部 CLI，如实际使用）；
- P1/P2 发现、修订位置和最终结论；
- 自动批准或用户明确批准的授权来源；
- 尚待用户醒后复核的重大边界，不得以“已记录”冒充已获科学或领域批准。

复核记录只描述当时可见的提交。后续代码或规格变化必须创建新记录或追加新的、带日期的 review entry，不能静默改写旧结论。

## 当前记录入口

- [M8B System-Owned Model Library Design Self-Review](2026-07-21-m8b-system-owned-model-library-design-self-review.md) — 核对 software-copy system store、project data boundary、legacy migration、exact RunSnapshot 与 loaded-source provenance；等待用户复核 written spec。
- [M8A Portable Windows Release Verification](2026-07-20-m8a-portable-windows-release-verification.md) — 最终 ZIP 的仓库外解压、私有 Python/sidecar、可编辑唯一活动源码、无 TCP listener、内容隔离、checksums 与回归验证；关闭 M8A engineering gate，不代表整个 M8 完成。
- [M8 Pre-UAT Outline Self-Review](2026-07-18-m8-outline-self-review.md) — 核对 M7 user-acceptance gate、前端正常编辑与全局 Python source editing 的双层边界、M8 非实施状态以及对 26514/42010/Diátaxis/C4 的轻量使用。
