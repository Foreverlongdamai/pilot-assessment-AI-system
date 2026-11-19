# 起点 item 修订（2026-09-15）

**历史方案提示：** 本文件中的三个／四个检查点及时间参考剖面已被用户后续决定替代；当前按[三维航迹与到点状态合同](2026-09-15-approach-route-corridor.md)实施。以下保留历史依据和修订过程，不作为当前输入模板。

用户已确认：SCN-002 删除独立起点就位；SCN-001 先起飞，从别处进近起点、减速并建立悬停。后者改为“正常进近至悬停”，沿用原 item 库的 A-S2-23（旧筛选表此前因本场景没有正常进近剖面而未选；本次流程确认后纳入）。本次不合并 SCN-002 的高度和定点 item。

**2026-09-15 后续裁减：** 用户要求先讨论 general 评估方法。A-S2-23 当前只保留三个操纵表现检查点，“机型程序执行”及两个布尔输入、对应 CPT 移出当前评估，留待具体机型时再定义。已有起飞前检查 item 保留，前三项和 SCN-002 的方法不变。

## 官方内容与项目适配

依据 FAA-S-ACS-2，CP.V.D Normal Approach to a Hover。当前三个检查点：

1. 进近航迹：CP.V.D.S5。以约定直线进近坐标系的实际横向坐标对比手工配置中心线；不从原始数据拟合航线。
2. 稳定进近与减速：CP.V.D.S3/S6。实际空速、高度、垂直速度对比机型及场景定义的参考剖面。这三种量和参考剖面是操纵表现的项目适配，不能单独证明全部稳定进近要求。
3. 到点建立悬停：CP.V.D.S7；航向保持补充参照 CP.IV.A.S8。仅到点环节检查 X、Y、高度、三轴地速和航向；不以单帧声称稳定悬停。

CP.V.D.S1/S3 中的检查单、程序及构型要求留待具体机型扩展，不作为当前第四个检查点。复飞决策、通信、SRM/CRM、选点等也尚未完整覆盖。通用操纵评估只是官方内容的部分适配；前三项仍需配置场景目标、参考剖面及容差，没有统一默认数值。

来源：https://www.faa.gov/training_testing/testing/acs/commercial_pl_acs_2.pdf （CP.V.D 印刷25–27页）。S7 的 ±2 feet 不直接复制为 X/Y/Z 各自容差，也不拆成 D/A。D/A 阈值、参考剖面及“任何已知 U 导致 Fail”仍是项目配置/汇总规则，不是完整 FAA 考试结论。

## 数据及计算合同

- SCN-001 顺序：preflight → approach → approach_deceleration → arrival_hover → acceleration → hold → hold_end → deceleration → stop。
- 三个新环节由输入给出，系统不识别/截取环节。每环节 minimum_frame_count=2 是最低数据充分性要求，不是官方时长要求。首末帧跨度仅说明记录范围，不推断中间持续状态。
- 航迹及参考剖面数据用于 approach/approach_deceleration；到点位置、速度和航向量仅用于 arrival_hover。当前不要求 `approach_checklist_completed`、`approach_procedure_configuration_correct`，不建立程序检查点或对应 CPT，也不根据控制轴推断是否执行程序。
- 剖面 metric 标记 target_mode=phase_profile（只用于 linear）。参数含 expected:null、desired、acceptable、reference_profiles；reference_profiles 的每个键为 metric.phase_ids 中的环节，值为至少两个 {elapsed_s, expected} 节点。
- elapsed_s 从该 item 的该环节首帧计时，首节点必须为 0，后续严格递增且有限。只对用户明确配置的参考节点做分段线性插值。观测帧不插值、不重排；不对参考剖面外推，超出覆盖的帧标缺失，不能判 Pass。
- 原始值减参考值形成有符号偏差；航向仍最短角差。固定目标、径向光点规则保持既有行为。
- 空模板不提供阈值、参考曲线、CPT或分数。独立工程示例明确为合成算术用例。
- SCN-001：4 item / 15 检查点 / 29 输入量；SCN-002：3 / 6 / 13。总画布 2 Task / 7 item / 21 检查点，共 30 节点。旧起点或含已移出进近程序字段/CPT 的输入与配置明确报错，不自动删除或转换。

## 首次进近修订的实施和验证（此次裁减前历史）

- [x] 替换目录、生成模板与工程示例；同步设计说明。
- [x] Python 剖面/不足帧验证与逐帧计算，检查无外推及缺失不通过。
- [x] 桌面剖面编辑、配置保存加载、画布及报告联动。
- [x] Python、.NET unit、真实 stdio 合同及桌面构建通过。
- [x] 从原桌面快捷方式启动并核对两个场景、总画布和新编辑器。

详见[四检查点进近验证记录](../reviews/2026-09-15-approach-hover-refinement-verification.md)。该记录保留裁减前的数量和验证结果，不代表当前三检查点版本已由同一记录验证。草稿允许 0/1 个节点及部分空值；完整评估仍要求至少两个完整节点。“保留草稿”更新工作区，“保存配置”才写入文件。到点稳定性、参考剖面等科学校准未由工程测试替代。

## 通用评估裁减记录

本轮只移出 A-S2-23 的机型程序检查，目录、模板、示例、模型和界面随之同步。验证结果单独记录于[通用评估裁减验证记录](../reviews/2026-09-15-general-approach-refinement.md)，不改写此前历史验证。
