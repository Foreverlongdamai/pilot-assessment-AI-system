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

- [M8D Current-System Packaging Verification](2026-07-21-m8d-current-system-packaging-verification.md) — 显式 current-system capture、动态 model baseline、source 不变性、完整 project directory copy/reopen/replay、typed Diagnostics、disposable package verifier 与 privacy scan；关闭 M8D engineering gate，不关闭 M7 UAT、M8C-1/M8E 或科学校准。
- [M8D Current-System Packaging Design Self-Review](2026-07-21-m8d-current-system-packaging-design-self-review.md) — 核对 D-077、current-system capture、完整 project 目录 portability、catalog 迁移与旧 backup 口径取代；仅关闭书面设计自审，不关闭 M8D 实现。
- [M8C-0 Documentation Infrastructure Verification](2026-07-21-m8c0-documentation-infrastructure-verification.md) — 12 类 catalog/schema、固定工具链、C4 assets、三份代表 DOCX 的 28 页逐页 QA、确定性 hash 与 portable review-doc integration；关闭 M8C-0，不关闭 M8C-1/M8D/M8E 或 M7 UAT。
- [M8C-0 Documentation Infrastructure Plan Self-Review](2026-07-21-m8c0-documentation-infrastructure-plan-self-review.md) — 核对 metadata/catalog、pinned toolchain、DOCX preset、Mermaid/C4、双语代表手册与 render QA；明确 M7/M8D/M8E 内容门。
- [M8B-2 Python Operator Extension Handoff Verification](2026-07-21-m8b2-python-operator-extension-verification.md) — 普通源码扩展入口、私有依赖 add/remove/sync、通用 schema UI、clean ZIP 与外部 extension/run/desktop 的 fresh gate；关闭 M8B，不关闭 M7 UAT、M8C–M8E 或科学校准。
- [M8B-1 Source Provenance and Snapshot Verification](2026-07-21-m8b1-source-provenance-and-snapshot-verification.md) — loaded source/runtime/dependency/operator identity、disk drift/restart boundary、RunSnapshot v0.2、source artifact 与 portable baseline v2 的 fresh engineering gate；不关闭 M8B-2、M7 UAT 或科学校准。
- [M8B-1 Implementation Plan Self-Review](2026-07-21-m8b1-implementation-plan-self-review.md) — 核对启动时冻结、运行前重扫、旧合同可读、新 run 严格 provenance 和轻量验证边界。
- [M8B-2 Implementation Plan Self-Review](2026-07-21-m8b2-implementation-plan-self-review.md) — 核对普通源码扩展入口、private dependency tool、通用参数 UI、release-copy vertical slice 与非 plugin 边界；计划随后已实施。
- [M8B-0 System Model Ownership Verification](2026-07-21-m8b0-system-model-ownership-verification.md) — system store、双项目共享、旧 run 隔离、legacy import、portable baseline 与仓库外桌面启动的 fresh engineering gate；不关闭 M8B-1/2、M7 UAT 或科学校准。
- [M8B-0 Implementation Plan Self-Review](2026-07-21-m8b0-implementation-plan-self-review.md) — 核对 system ownership 实施顺序、双项目/快照验证、legacy migration 与 M8B-1/2 停止边界；计划已获用户批准并进入实施。
- [M8B System-Owned Model Library Design Self-Review](2026-07-21-m8b-system-owned-model-library-design-self-review.md) — 核对 software-copy system store、project data boundary、legacy migration、exact RunSnapshot 与 loaded-source provenance；written spec 已获用户批准。
- [M8A Portable Windows Release Verification](2026-07-20-m8a-portable-windows-release-verification.md) — 最终 ZIP 的仓库外解压、私有 Python/sidecar、可编辑唯一活动源码、无 TCP listener、内容隔离、checksums 与回归验证；关闭 M8A engineering gate，不代表整个 M8 完成。
- [M8 Pre-UAT Outline Self-Review](2026-07-18-m8-outline-self-review.md) — 核对 M7 user-acceptance gate、前端正常编辑与全局 Python source editing 的双层边界、M8 非实施状态以及对 26514/42010/Diátaxis/C4 的轻量使用。
