+++
document_id = "PAS-RELEASE-001"
language = "zh-CN"
title = "发布构建与交付验收手册"
short_title = "发布与验收"
product_version = "0.1.0"
document_version = "0.1.0"
status = "released"
audience = ["maintainer", "release"]
information_types = ["tutorial", "how-to", "reference"]
scope = "说明如何构建、在仓库外验证并交付 Windows x64 v0.1.0-rc.4，同时不提前宣称最终用户验收。"
prerequisites = ["位于目标 annotated tag 的 clean source checkout", "明确选择且已保存的 current system model", "Windows x64 build environment"]
scientific_status = "engineering-only"
related_documents = ["PAS-ARCH-001", "PAS-QUICKSTART-001", "PAS-PORTABILITY-001", "PAS-PYTHON-CORE-001"]
support = "保留 delivery JSON、ZIP hash、tag/commit、build log、verification evidence 和签字验收清单。"
release_channel = "release-candidate"
release_label = "v0.1.0-rc.4"
user_acceptance = "pending"
+++

# 发布构建与交付验收手册

## 1. 候选 identity 与边界

本手册适用于：

| Field | Required value |
|---|---|
| Product version | `0.1.0` |
| Release channel | `release-candidate` |
| Candidate | `rc.4` |
| Release label/tag | `v0.1.0-rc.4` |
| User acceptance | `pending` |
| Scientific status | `engineering-only` |
| Formal assessment | supplied starter 保持 `formal_run_authorized=false` |

完成 engineering verification 的 candidate 不等于最终 accepted `v0.1.0`。用户必须实际操作并检查这一份准确 ZIP 后才能记录 acceptance。纯文档修正可按明确类别记录；code/model change 必须产生新的 candidate identity。

RC.4 保留 Assessment 技术执行、任务栏图标和全局删除节点，并修复主动“保存全部”、普通节点松手回弹和五个绿色 Raw Input Family 根不可拖动。静态界面仍真实的截图可以明确记录为从 RC.3 复用；保存和拖拽属于交互行为，必须用实际 WinUI 运行证据验证，不能由静态图片代替。

## 2. Release inputs

构建有四项权威输入：

1. annotated candidate tag 指向的 clean Git commit；
2. 明确选择且 clean 的 current `system\` model library；
3. released 双语 Markdown catalog 与 registered candidate screenshots；
4. frozen Python/.NET dependency 与 toolchain inputs。

Builder 不能猜测 system source，也不能静默回退 starter。Selected model 只有在证明 library identity、dynamic node/scheme counts、database/schema compatibility、clean edit session、zero user-owned rows 与 zero WAL/SHM transients 后才可只读捕获。

## 3. 必须包含的产品内容

Windows x64 ZIP 包含：

- 产品根目录唯一的 self-contained `PilotAssessment.exe` 启动器，以及收纳在 `app\` 中的 `PilotAssessment.Desktop.exe`、private .NET/Windows App SDK files 与语言资源；
- 根目录中清晰可见的 `backend\`、`system\`、`runtime\`、`developer\`、`docs\`、`licenses\` 与 `manifest\` 语义目录；
- private Python runtime 与 private dependencies；
- 暴露的 active `backend/src/pilot_assessment/` source、lock 与 dependency helper；
- selected current `system\` model library；
- schemas、integrity manifest、SBOM 与 third-party notices/licenses；
- release notes、known limitations、portable README 与 acceptance checklist；
- 24 份 generated DOCX：11 份模块手册加 1 份自动总册，中英文各一套；
- 手册使用的 10 张 registered/privacy-reviewed UI screenshots。

不得包含 user project、Session、result、biometric data、test fixture、cache、build directory、source-control metadata 或 PDB。

## 4. 准备 source 与 documentation

1. 完成全部 source/manual changes 与 released-document validation；
2. 从准确 final UI source tree 捕获 screenshots，并登记 file/hash/language/dimensions/source identity/privacy review；
3. 构建 24 份 DOCX，渲染并目视检查每一页；
4. 运行 focused backend、schema、documentation、release、C# unit/contract 与 x64 Release gates；
5. 确认 `git status --short` 为空；
6. 创建 annotated `v0.1.0-rc.4` tag，并证明它 peel 到 `HEAD`。

Candidate screenshot capture 后不能再改 UI code；否则 source identity 失效，必须重新截图。

## 5. 构建 candidate

关闭 desktop application，在 tagged repository root 运行：

```powershell
.\.tools\uv\uv.exe run python tools\release\build_portable.py `
  --system-source .pilot-assessment-local\system `
  --release-label v0.1.0-rc.4 `
  --release-channel release-candidate `
  --candidate rc.4 `
  --user-acceptance pending `
  --documentation-status released
```

预期 external delivery artifacts：

```text
PilotAssessment-0.1.0-rc.4-win-x64.zip
PilotAssessment-0.1.0-rc.4-win-x64.zip.sha256
PilotAssessment-0.1.0-rc.4-win-x64.delivery.json
```

Delivery JSON 记录 filename/bytes/SHA-256、tag/commit、system identity/counts、documentation/SBOM hashes 与 pending acceptance，不能暴露 build-machine absolute paths。

## 6. 在仓库外验证

权威 acceptance rehearsal 把 ZIP 解压到 repository-external temporary directory，并只使用 packaged runtimes：

```powershell
.\.tools\uv\uv.exe run python tools\release\verify_archive_external.py `
  --dist dist\releases\PilotAssessment-0.1.0-rc.4-win-x64.zip `
  --verify-editable-source `
  --verify-operator-extension `
  --launch-desktop `
  --restricted-path
```

Verifier 必须证明：

- archive/internal checksum integrity；
- 不依赖 repository/system Python/dotnet/PATH tools；
- headless no-project 与 two-disposable-project workflows；
- visible desktop startup 与 clean shutdown；
- automatic sidecar/private SQLite behaviour 与 zero TCP listeners；
- current system identity/counts 与 clean edit state；
- 在 disposable copy 修改 live Python source 后 restart identity 变化；
- operator-extension example 与 dependency metadata；
- 24 documents、10 screenshots、SBOM/licenses 与 acceptance files；
- source system 无 mutation，且无 surviving process/WAL/SHM。

## 7. Privacy 与 archive scan

检查 ZIP member names、extracted text 与 DOCX XML：

- build-machine usernames 与 absolute home/repository paths；
- user project/Session/result identifiers 或 data rows；
- gaze、EEG、ECG、pilot-camera 或 participant content；
- caches、test data、`.git`、`.venv`、`__pycache__`、logs 或 PDBs；
- unlisted executables 或 SBOM 未列 licenses。

候选 screenshots 必须来自 release 外部的 anonymous disposable project，不能显示 private paths 或 real Session content。

## 8. 交付给用户

同时交付 ZIP、`.sha256`、delivery JSON、release notes、known limitations 与 acceptance checklist。接收用户应：

1. 验证 ZIP SHA-256；
2. 解压到 clean writable directory；
3. 在 product root 外创建 project；
4. 导入自己的 Session，包括 partial-modality case；
5. 运行并检查 Evidence/BN results 与 diagnostics；
6. 编辑/复制/保存 model nodes 与 task schemes，重启后确认持久化；
7. 可选：在 copied software directory 检查和修改 Python source；
8. 记录 accepted、documentation-only corrections 或 changes required。

验收清单返回前，所有 release records 保持 `user_acceptance=pending`。

## 9. Promote 或替换 candidate

- 无 product changes 并验收通过时，执行最终 release procedure，记录用户 evidence 并提升 clean final identity；不能只重命名 candidate ZIP；
- 仅文档修正且符合约定类别时，记录 exact corrected document hashes 与 status；
- code、model、runtime、screenshots 或 executable behaviour 变化时创建新的后续 candidate，重新捕获相关 evidence 并执行 external verification；
- software acceptance 不代表 scientific calibration、expert endorsement 或 formal authorization。

## 10. Release-maintainer 检查单

- [ ] clean annotated tag 等于 intended commit；
- [ ] explicit saved system 已只读捕获；
- [ ] 24 DOCX 已渲染并逐页目视检查；
- [ ] 10 张 candidate screenshots 已登记并 privacy-reviewed；
- [ ] focused Python/C#/release gates 通过；
- [ ] external restricted-PATH verification 通过；
- [ ] ZIP/privacy/SBOM/license scan 通过；
- [ ] source system 未变，且无 process/lock；
- [ ] ZIP hash 与 delivery JSON 已记录；
- [ ] candidate 以 `user_acceptance=pending` 交付。
