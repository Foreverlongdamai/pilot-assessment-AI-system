# 正常进近至悬停：通用范围裁减

2026-09-15，用户明确当前研究通用评估方法，第四项机型程序执行留待讨论具体型号时再加。

本次删除目录中的 A-S2-23-04 及其两个布尔输入：approach_checklist_completed、approach_procedure_configuration_correct。模板、报告、CPT 草稿与 Model Studio 均随同一目录更新；前三个检查点、计算算法和已有起飞前 checklist item 不变。

当前 SCN-001 为 4 item / 15 检查点 / 29 输入量，SCN-002 为 3 / 6 / 13。总画布为 2 Task / 7 item / 21 检查点，共 30 节点。机型程序不是默认通过，而是当前不纳入该 item 的评分及输入要求。前三项容差和参考剖面仍需场景设定，没有引入通用数值标准。

验证：目录与真实 stdio 示例测试 7 项通过；.NET 真实 Gateway 两场景合同 2 项通过。重新生成两场景的空模板和合成示例；无机型程序输入时，合成进近仍完整得 D/Pass，空中滑行既有 U 不变。

本次为 Python 场景目录变更，无 .NET 生产代码变更，原 EXE 通过项目后端读取新目录；无需重新编译 EXE。原干净窗口正常关闭，再通过原桌面快捷方式启动以刷新目录（新进程 41012）。实际 Model Studio 显示 2 场景 / 7 item / 21 检查点，A-S2-23 只剩 -01/-02/-03；场景卡片和参数编辑器均只有三个现行检查点，未出现机型程序执行。UI 快照：tmp/scene_v3_qa/general-approach-final-ui.json、general-approach-editor-ui.json。旧四检查点验证记录保留为本次裁减前历史。

DECISIONS.md 的 SHA256 仍为 70F8808EEE46E0BAEA6832958C8841A8F0EF09E6249891992D6D2310ED6C10FE，未修改。
