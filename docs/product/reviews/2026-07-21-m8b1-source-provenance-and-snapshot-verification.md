# M8B-1 Source Provenance and Snapshot Verification

| 字段 | 结果 |
|---|---|
| 日期 | 2026-07-21 |
| 范围 | loaded backend identity、disk drift、preflight/run v0.2、source snapshot artifact、Diagnostics、portable source baseline v2 |
| 结论 | **PASS — M8B-1 engineering gate closed** |
| 科学边界 | 只证明执行身份和历史可复现性；不证明 Evidence/BN/CPT/operator 科学有效 |

## 1. 实现结果

- `SystemApplication` 启动时冻结一棵 active first-party Python tree、`pyproject.toml`、`uv.lock`、私有 Python、已安装依赖和 operator catalog 的组合身份；
- tree hash 使用 normalized case-insensitive relative path、原始 bytes 和确定顺序，不使用 mtime、绝对安装路径或 Windows 路径大小写；
- release baseline 可区分 added/modified/deleted；开发环境没有 baseline 时返回 unavailable/unknown，不伪称 clean；
- `runtime.status` 和 WinUI Diagnostics 返回 loaded identity、baseline comparison 与 `runtime_restart_required`；
- preflight 和 run start 两次重扫磁盘。启动后源码或 lock 漂移会阻止该次 run 并要求重启；重启后本地修改正常运行；
- ready preflight 在 project artifact store 中保存确定性 source ZIP；相同源码复用相同 artifact，RunSnapshot v0.2 保存 identity/ref；
- snapshot 只含 canonical `backend/src/pilot_assessment/**`、`backend/pyproject.toml`、`backend/uv.lock` 和 manifest；不含用户数据、绝对路径、环境或第三方 package bytes；
- 旧 current-model preflight/snapshot v0.1 保持可读，但不能被用来创建缺失 provenance 的新 run；
- Runs 页面在折叠技术区显示历史 run 冻结的 source identity 与 artifact reference。

## 2. 轻量验证证据

### Python focused gate

```powershell
.\.tools\uv\uv.exe run pytest \
  tests/contracts/test_source_provenance.py \
  tests/contracts/test_run_contracts.py \
  tests/runtime/test_source_provenance.py \
  tests/runtime/test_current_preflight.py \
  tests/runtime/test_current_run_snapshot.py \
  tests/runtime/test_run_repository.py \
  tests/sidecar/test_methods.py \
  tests/schemas/test_schema_export.py \
  tests/integration/test_m8b_system_model_project_boundary.py -q
```

结果：`56 passed in 74.61s`。

新增的 restart boundary 独立切片：

```powershell
.\.tools\uv\uv.exe run pytest \
  tests/integration/test_m8b_source_provenance_run_boundary.py -q
```

结果：`1 passed in 15.55s`。它证明第一次 run 的 snapshot JSON 在软件重启和源码修改后保持 byte-equivalent；第二次 run 获得新的 source-tree identity 和 source artifact。

### Desktop gates

- Desktop Unit：`102/102`；
- real-sidecar Contract：`4/4`；
- x64 Debug build：`0 warning / 0 error`；
- 实际启动：`PilotAssessment.Desktop.exe` 获得非零主窗口句柄 `2362272`，标题 `Pilot Assessment System`。

### Portable gate

```powershell
.\.tools\uv\uv.exe run python tools/release/build_portable.py --skip-archive
```

结果：PASS。工程目录大小 `690,191,267` bytes，`4,276` 个 checksummed files，`293` 个 first-party backend files，双 project/no-project Model Studio/私有 Python sidecar smoke 通过。

发布副本身份：

| Identity | SHA-256 / count |
|---|---|
| source tree / release baseline | `d304a73fad3a8bc4493549ac0a3a43e14bdd42186e25cd8846eb0237d25f77e9` |
| combined backend identity | `b75efef04ff7f40154912aadfb865af0aa2b020866eec486982adbefa043e7ae` |
| private Python runtime | `bd866c8de5a2dd5ea90cd974d334e35b850f5d678cace4285f3cf445afff4c54` |
| dependencies | 16 packages / `8d32adcde37bc4776fdda1ef0d37b8828b487f41e9e158dd981cc54d46b552b4` |
| operator catalog | 45 operators / `488e257f987e13383eb99aa270870677e078e3a161925a5f8a12f9ef44bfd239` |

随后在该 release directory 的 disposable edit 中修改 `dispatcher.py`，重启 sidecar 后：

- edited source 被实际 import；
- `locally_modified=true`；
- fresh process `runtime_restart_required=false`；
- verifier 恢复原文件并再次通过 baseline/checksum 校验。

## 3. 自审结论

- baseline divergence 不是审批门；
- restart-required 只防止同一进程混用旧 import 与新磁盘 bytes；
- artifact 不会被当前 runtime 自动执行；
- system model edits 与 Python source edits 仍是两条清晰路径；
- 测试没有生成万行多模态数据，也没有把 starter 分数正确性作为断言。

M8B-1 已完成。下一阶段是 M8B-2：把发布包中新 operator 的普通源码入口、private dependency tool、通用 schema UI 和 disposable release-copy run 闭环正式交付。

