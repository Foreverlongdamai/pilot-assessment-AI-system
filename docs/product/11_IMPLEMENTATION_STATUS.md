# Implementation Status — Backend Foundation M1

| 字段 | 当前值 |
|---|---|
| 状态日期 | 2026-07-11 |
| 产品设计基线 | v0.1 |
| 已完成里程碑 | Backend Foundation M1 |
| 软件状态 | in_progress（M1 verified，不代表完整 Core alpha） |
| 科学状态 | engineering_default（not scientifically validated） |
| Python package | `pilot-assessment-system 0.1.0` |

## 1. 已实现

### 1.1 Python 工程基础

- `src/` package layout、`pyproject.toml`、uv lockfile 和隔离开发环境；
- Python 3.11、Pydantic v2、pytest、Ruff、ty、uv_build；
- 可构建 source distribution 与 wheel。

### 1.2 稳定合同

- `SessionManifest` 与所有嵌套 DTO；
- `StreamDescriptor` 与五种状态：present、export_pending、missing、invalid、not_applicable；
- 七个核心 descriptor：X、U、I、G、EEG、ECG、pilot_camera；
- 同一 0.x 版本允许保留新的可选 stream ID，`P` 仍只表示 physiology 概念组；
- 统一 `AnchorResult`、七种 calculation status、D/A/U likelihood、quality、source trace、parameter hash 与 provenance；
- 非 computed AnchorResult 不允许携带 evidence state、likelihood 或 continuous score；
- 统一 `DomainErrorData`，供后续 runtime 复用。

### 1.3 Bundle inspect 边界

当前 `ManifestLoader` 支持未压缩目录 bundle，并执行只读 inspect：

- UTF-8 JSON 与 Pydantic 合同校验；
- 不支持 major version 的明确拒绝；
- POSIX 相对路径、无绝对路径/盘符/UNC/反斜杠/`..`；
- Windows 大小写规则下的重复路径检测；
- present stream、phase/event/baseline annotation 与 checksum 文件存在性；
- symlink/junction 解析后仍位于 bundle root；
- `checksums.sha256` 解析、descriptor/checksum 清单一致性和实际 SHA-256；
- checksum 项必须与 manifest 声明文件精确相等，不允许借 checksum 清单扩大读取范围；
- manifest/checksum 大小、文件数量、单文件和总哈希字节使用可配置上限；
- 重复 JSON key、NaN/Infinity、过深 JSON 和超大整数统一返回 typed `INVALID_MANIFEST`；
- 原始 bundle 只读，不制造 export_pending 文件，也不重写 manifest。

这一结果只表示 `inspect_only_structure_and_declared_file_integrity` 通过。路径检查和读取之间仍可能发生源文件并发变化，所以该对象**不能授权正式 `session.import` 或正式 run**。未来 managed-storage importer 必须从同一安全文件句柄完成最终路径/reparse 检查、哈希与复制，再生成不可变 session snapshot。当前结果也不表示 Parquet/EDF/MP4 内容、单位、时间同步或信号质量已通过。

默认 inspect 上限由 `ManifestLoaderLimits` 明确给出：manifest 4 MiB、checksum 文件 8 MiB、声明路径 10,000、checksum 项 10,000、单文件哈希 64 GiB、单 bundle 总哈希 256 GiB。后续 runtime 可以提交经批准的配置，但不得移除有界读取与哈希预算。

### 1.4 跨语言 Schema

已确定性生成：

- `schemas/session-manifest-0.1.0.schema.json`
- `schemas/anchor-result-0.1.0.schema.json`

Schema 使用 JSON Schema 2020-12，并固定 URN `$id`。概率和、continuous score 公式、checksum key/path 集合相等之类无法仅由标准 JSON Schema 完整表达的规则，记录在 `x-runtime-invariants`，并由 Pydantic 与测试强制执行。

## 2. 验证证据

2026-07-11 在 Windows / Python 3.11.15 上重新执行：

```powershell
uv run python -m pilot_assessment.schemas.export
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv build
```

结果：

- pytest：142 passed；
- Ruff lint：passed；
- Ruff format check：passed；
- ty：passed；
- build：生成 `pilot_assessment_system-0.1.0.tar.gz` 与 `pilot_assessment_system-0.1.0-py3-none-any.whl`；
- schema exporter 连续生成内容一致；canonical fixtures 通过 Pydantic 与 JSON Schema 验证；不兼容 major、非法 ID、路径穿越、错误 checksum 和字符串伪装的布尔/数值会被前后端合同共同拒绝。

## 3. 关键文件

| 内容 | 路径 |
|---|---|
| 通用 ID、路径、checksum | `src/pilot_assessment/contracts/common.py` |
| Session 合同 | `src/pilot_assessment/contracts/session.py` |
| AnchorResult 合同 | `src/pilot_assessment/contracts/anchor.py` |
| 统一错误 | `src/pilot_assessment/contracts/errors.py` |
| Manifest loader | `src/pilot_assessment/ingestion/manifest_loader.py` |
| Schema exporter | `src/pilot_assessment/schemas/export.py` |
| Canonical fixtures | `tests/fixtures/` |
| M1 实施计划 | `docs/product/plans/2026-07-11-backend-foundation-m1-implementation-plan.md` |

## 4. 尚未实现

- zip bundle 与受控 external reference；
- CSV、Parquet、EDF/EDF+、MP4/frame index、image sequence adapters；
- X/U/I/G/EEG/ECG 内容 schema、单位和设备 metadata gate；
- clock mapping、offset/drift、aligned t_ns、phase/event/baseline 语义校验；
- 18 个 AnchorPlugin、依赖 DAG、evidence scoring 与 coverage；
- model bundle、graph/CPT、BN engine、draft/revision/publish；
- JSON-RPC sidecar、persistence、reporting；
- WinUI 3 前端和图编辑器；
- 领域专家校准与任何科学有效性研究。

## 5. 下一里程碑

根据已批准的完整闭环方向，M2 范围为“多模态理想合同 + synthetic full bundle + ingestion readiness inspection”：

1. 定义 adapter registry、RawStream/NormalizedStream 与 `IngestionReadinessReport`；
2. 为当前真实模拟器 CSV 建共享 X/U adapter，不把列名写死到通用合同；
3. 固化 I/G/EEG/ECG/pilot_camera 的理想第一版文件合同；
4. 以真实 X/U 时间范围生成独立 synthetic scene、gaze、EEG、ECG 和 pilot-camera 文件；
5. 生成七个 core modalities 全 present 的 synthetic bundle，并完成全模态 ingestion readiness inspection；
6. 通过 M2 后依次进入 M3 synchronization、M4 18-anchor/evidence、M5 BN、M6 端到端 runner。

详细已批准规格见 [M2 Multimodal Synthetic Foundation Design](specs/2026-07-11-multimodal-synthetic-foundation-design.md)。M2 不应提前实现 BN，也不应把 synthetic 信号或当前 CSV 样本误当作科学有效的完整产品数据。

逐任务 RED/GREEN 顺序见 [M2 Implementation Plan](plans/2026-07-11-m2-multimodal-synthetic-foundation-implementation-plan.md)。

## 6. M1 独立自审

本里程碑经过计划、代码、文档和 loader 健壮性四类只读复审：

- P0：0；
- 计划审查发现的 7 个 P1 已在实施前修正；
- 代码审查发现的 3 个 P1（Schema/Pydantic 约束不对称、JSON scalar 静默转换、soft likelihood 主类别冲突）已修正并由反例测试关闭；
- loader 审查发现的 3 个 P1（checksum 扩大读取范围与无界工作、异常 JSON 泄漏非 typed error、inspect/import TOCTOU 边界混淆）已修正或明确隔离到未来 managed import gate；
- 最终复审未发现阻止 M1 inspect-only 交付的残余 P0/P1。

非阻塞 P2：极端超长 bundle root 在错误序列化时仍需统一截断/规范化；未来 JSON-RPC 接入前必须补测试。正式 importer 还必须加入可取消、可报告进度的同句柄哈希与复制，不能直接复用 inspect 结果作为授权。
