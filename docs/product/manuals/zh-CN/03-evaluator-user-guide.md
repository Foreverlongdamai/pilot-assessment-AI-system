+++
document_id = "PAS-EVALUATOR-001"
language = "zh-CN"
title = "评估用户操作手册"
short_title = "评估用户手册"
product_version = "0.1.0"
document_version = "0.1.0"
status = "released"
audience = ["evaluator"]
information_types = ["tutorial", "how-to", "reference"]
scope = "面向 Windows 软件评估用户，说明 project、Session、run、result 与 diagnostics 的完整工作流。"
prerequisites = ["已经完整解压产品", "可写的 project 目录", "仿真器导出目录或 canonical Session Bundle"]
scientific_status = "engineering-only"
related_documents = ["PAS-QUICKSTART-001", "PAS-SESSION-001", "PAS-EXPERT-EVIDENCE-001", "PAS-PORTABILITY-001"]
support = "报告问题时提供发布标签、简洁 project 名称、run 状态、稳定错误码和不含隐私的 Diagnostics 摘要。"
release_channel = "release-candidate"
release_label = "v0.1.0-rc.3"
user_acceptance = "pending"
+++

# 评估用户操作手册

## 1. 评估边界

本手册覆盖普通操作：创建或打开 project、导入 Session、选择任务方案、运行工程管线并查看结果。评估用户不需要编辑 Python、设计 Evidence 算法或校准 CPT。

当前候选版是可解释的工程框架。starter model 保持 `formal_run_authorized=false`，输出不能被表述为已经完成科学验证的飞行员资格结论。

## 2. 打开或创建 project

启动后选择一项操作：

- “创建项目”在用户指定目录建立空 project；
- “打开项目”打开一个完整的现有 project 根目录；
- “最近项目”只在对应根目录仍存在时重新打开。

project 名称应简洁，并避免包含敏感参与者信息。技术 project ID 由应用生成。project 保存受管 Session revisions、不可变 RunSnapshots、runs、results 和 artifacts。全局 Evidence/BN 定义位于软件副本的 `system\`，因此会作用于该副本打开的所有 project。

## 3. 导入 Session

打开“会话”，选择外部来源。来源可以是含 `manifest.json` 的 canonical bundle，也可以是只有 `streams\` 和可选 `annotations\` 的仿真器导出目录。

导入分为两个明确阶段：

1. “检查外部来源”只读执行，用户检查识别到的文件、模态映射、annotations、时间列和 diagnostics；
2. “导入到受管项目”把接受的内容复制进 project，并记录 canonical revision 与 receipt。

外部目录不会被当作可修改的工作区。重复导入同一来源是幂等操作：后端会核对已有受管 revision，而不是静默生成重复数据。

缺少模态不会让整个 Session 失效。应用不会合成缺失数据；现有模态支持的 Evidence 可以继续计算，不具备输入的 Evidence 会明确标记为 unavailable，BN 则使用实际存在的 observations 继续推理。

## 4. 选择任务方案

任务方案是对全局共享完整节点与边的一组持久选择，决定本次评估使用哪些 Raw Input、Extracted Data、Evidence、Sub-skill 与 Competency 节点。

可在“模型工作室”或运行工作区选择方案。启用节点明亮显示，未启用的库节点保留但变暗。切换方案不会创建临时模型版本，也不会覆盖其他方案。如果启用了子节点，后端会自动启用它的固定祖先闭包。

除非你同时承担领域专家职责，不要只为了让 preflight 通过而改任务方案。专家工作流见 [[DOC:PAS-EXPERT-EVIDENCE-001]]。

## 5. 执行技术 preflight

打开“运行”，选择一个受管 Session revision、一个任务方案和运行用途，然后点击“技术预检”。Preflight 不会生成结果，也不评价科学质量；它只检查当前 snapshot 是否能由已安装引擎执行。

重点检查：

- Session revision 与 task scheme identity；
- active node closure 与当前 model content hashes；
- operator 是否安装及其参数合同；
- 已有和缺失的模态；
- schema/runtime compatibility；
- scientific boundary 与精确 blocking diagnostics。

飞行表现差、轨迹误差大、控制剧烈或生理数值异常都是评估观察，不是丢弃可解析数据的理由。结构性缺失或不可能执行的合同会单独报告为 unavailable 或 blocked。

“评估”用途与科学授权状态是两个字段。只要 technical disposition 为 ready，选择“评估”也可启动并完成运行；如果当前模型或 Session 未获正式授权，preflight 显示 `run.assessment_not_authorized` warning，run 关联的 frozen preflight provenance 继续记录 `formal_run_authorized=false`。该 warning 不阻止工程计算，也不得被忽略为科学有效性声明。

## 6. 启动、监控或取消 run

只有 preflight ready 后才点击“开始运行”。“评估”用途不再因为 false scientific authorization 单独禁用该按钮；真正的结构、依赖、dirty/stale source 或 runtime 问题仍会阻止运行。后端会在计算前创建不可变 RunSnapshot。正常阶段依次为 snapshot validation、ingestion、synchronization、Evidence extraction、Bayesian inference、reporting 和 completion。

关闭再打开应用不会改写 durable run。后端会从 project 恢复 queued、interrupted 或 completed 状态。取消请求也会与 canonical backend run 对账；复制 project 前应等待其进入最终状态。

## 7. 查看结果

[[SCREENSHOT:ui-run-results-diagnostics]]

打开“结果”并选择一个 completed run，建议按由具体到抽象的顺序阅读：

1. Evidence continuous value、D/A/U observation 与 availability；
2. Evidence trace、参数、输入模态和 operator identity；
3. Sub-skill posterior distribution；
4. aggregate competency posterior distribution；
5. missing-Evidence 与 influence information；
6. frozen model、Session 与 backend source provenance。

`DESIRED`、`ACCEPTABLE` 和 `UNACCEPTABLE` 是模型状态，不是法律或医学判断。Posterior 取决于专家编写的图、CPT 与实际 Evidence。缺失 observation 由 BN 边缘化处理，不会被静默替换成理想值或零。

## 8. 使用 Diagnostics

启动、导入、run recovery 或 source identity 不清楚时打开 Diagnostics。常用区域包括 backend/runtime status、current system model identity 与数量、project compatibility、run recovery、schema identities、JSON-RPC capabilities、Python source identity、installed dependencies 和 operator catalog。

普通界面会有意隐藏长 UUID 和 hash；Diagnostics 与 provenance 保留这些技术身份以便复现和支持。除非授权流程明确要求，只复制不含隐私的摘要。

## 9. 安全结束工作

先结束或取消活动操作，再正常关闭主窗口。如果专家暂存了系统模型更改，关闭对话框会提供“保存全部并关闭”“放弃全部并关闭”和“取消”。评估用户的 project 数据不依赖该全局 model edit session。

需要迁移时先关闭应用，再复制整个 project 根目录，不要只复制 SQLite 文件。详见 [[DOC:PAS-PORTABILITY-001]]。

## 10. 评估用户检查单

- [ ] 已确认正确的产品发布和目标 system model；
- [ ] 已打开正确 project；
- [ ] 导入前已检查外部来源；
- [ ] 已选择受管 Session revision；
- [ ] 已选择目标任务方案；
- [ ] 已审阅 technical preflight；
- [ ] run 已进入 durable final state；
- [ ] 已审阅 missing Evidence 与 scientific boundary；
- [ ] 对外使用结论时同时保留 provenance。
