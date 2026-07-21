# M8E Final Release Candidate Design Self-Review

| 字段 | 结果 |
|---|---|
| 日期 | 2026-07-21 |
| 被审查规格 | `2026-07-21-m8e-final-release-candidate-and-handoff-design.md` |
| 审查方式 | INLINE，逐条对照 M8 outline、M8C、M8D、D-055、D-065、D-075–D-077 与用户最新决定 |
| 结论 | **PASS — 可提交用户书面规格复核** |

## 1. 用户决定映射

| 用户要求 | 规格位置 | 结果 |
|---|---|---|
| 不再先做 M7 中间验收 | §2 | 已明确取代旧 Gate 0 时机 |
| 直接验收完整最终版本 | §2、§6.2 | 采用完整 `rc.1` 统一验收 |
| 仍需诚实记录是否已验收 | 导言、§4、§9 | `user_acceptance=pending`，不冒充 final |
| 继续完成最后工作 | §3–§6、§11 | D-055、M8C-1、M8E 打包和交付形成完整顺序 |
| 保留自由修改 Evidence/BN/Python | §1、§5 | 前端 system editing 与唯一 live Python tree 均保留 |
| 不把 starter 算法当科学结论 | 导言、§1、§8、§11 | `engineering-only` 与 `formal_run_authorized=false` 保持 |

## 2. 跨文档一致性

- D-055 仍按已批准单一英文 canonical 内容规格执行，没有用 display-name resolver 替代真实合同迁移。
- D-065 的 clean tagged source 要求保留，并具体化为 `v0.1.0-rc.1`。
- D-075 没有被删除；它被细化为 `release-candidate -> final` 两阶段 screenshot 状态。
- D-076 的 Markdown 权威、DOCX 生成物和技术总册聚合规则保持不变。
- D-077 的 current-system capture、无专用 backup/restore、project 整目录复制保持不变。
- M8A–M8D 已完成的 runtime、source、system ownership、portability 和 diagnostics 合同不被重写。

## 3. 歧义检查

### 3.1 “最终发布版本”与“尚未验收”

采用 release candidate 消除循环依赖：用户验收完整候选，候选通过后从同一 accepted source 重建 final。规格禁止只重命名 ZIP，因此 manifest 和 hashes 始终真实。

### 3.2 clean-machine 声明

当前环境查询 Windows Sandbox 需要提权，规格没有把仓库外 restricted-PATH verification 写成已经完成的 Sandbox 验收。自动证据和用户独立验收分开记录。

### 3.3 截图状态

候选手册需要真实 UI 截图，但用户尚未验收。`release-candidate` 状态允许使用对应候选 build 的隐私安全图片，又不会提前称其为 final。

### 3.4 版本语义

Python/API product version 保持 `0.1.0`；release manifest 单独保存 channel、candidate 和 label，避免 PEP 440、.NET assembly version 与交付标签互相污染。

## 4. 范围检查

规格只包含首个 portable release candidate 所需内容：

- 包含 D-055、M8C-1、release metadata、candidate screenshots、ZIP 和验证；
- 排除 installer、MSIX、code signing、auto-update、cloud、backup product 和科学校准；
- 不新增模型算法、Evidence、BN 节点、CPT 或 operator 科学方法；
- 不把一次性验证项目或 screenshot fixture 带入产品。

范围较大但各部分具有严格依赖顺序，不能把 D-055 或手册留到 ZIP 之后再补，因此适合作为一个里程碑下的分阶段 inline 实施计划。

## 5. Placeholder 与可执行性扫描

- 无未决产品选择；候选身份、目录名、tag、manifest 字段和验收状态均已确定。
- 无模糊的“适当验证”要求；§6、§8 和 §11 列出可观察结果。
- 无固定 starter cardinality；`54 / 2` 只作为当前 capture 实际值。
- 无用户数据打包、隐藏源码或自动 fallback 路径。
- promotion、repair 和 documentation-only correction 均有明确版本后果。

## 6. 风险与控制

| 风险 | 控制 |
|---|---|
| D-055 迁移破坏 current system | 副本先验证、事务迁移、legacy diagnostics、历史 snapshot 不重写、动态 identity 对比 |
| 候选截图泄露数据 | 一次性工程项目、无身份内容、manifest hash/privacy review、release content scan |
| 24 份 DOCX 语言或版本漂移 | shared document ID/version/status、catalog parity、deterministic builder 和 render audit |
| 候选被误称正式 accepted release | manifest、封面、release notes、状态文档统一 `user_acceptance=pending` |
| 构建机环境掩盖缺依赖 | repository-external short path、restricted PATH、private runtime、package-internal verifier |
| 验证修改交付包或 source system | disposable copy；构建前后 source identity/file hash 比较 |

## 7. 审查结论

规格完整覆盖用户批准的方案 A，并诚实保留用户验收和科学验证边界。没有发现需要改变既有架构的冲突；可以在用户复核书面规格后进入 INLINE implementation plan。
