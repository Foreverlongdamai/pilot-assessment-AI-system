# SCN-001 v2 输入与配置

当前软件使用本目录的 2.0 格式：4 个 item、16 个检查点、25 个数据量。旧上级目录的 1.0 文件仅供历史版本使用，不会自动迁移。

- configuration-template.json：期望值、D/A 有符号偏差范围均留空；三个飞行 item 的先验、状态分值与 CPT 草稿也留空。
- input-template.json：按 item → checkpoints → values/samples 组织；单次结果为 null、时序为空列表，没有虚构成绩。
- engineering-demo-configuration.json、engineering-demo-input.json：完全合成的软件检查数据。数字不来自模拟器、官方标准或人因研究，不可当作推荐参数。
- engineering-demo-report.json：用上述演示配置和输入实际计算的完整报告，包含所有输入/配置快照。
- engineering-demo-ui-report.json：从实际 WinUI 界面评估后导出的报告；已回读核对输入、配置、时序和时间占比。示例生成器不覆盖此界面验证产物。

可以先在软件加载 engineering-demo-configuration.json，再导入 engineering-demo-input.json 并评估。四个 item 的结果依次为 D、D、U、D，整场 U／Fail，无缺项。空中滑行航向为：

| 飞行相对时间 | 实际航向 | 期望航向 | 最短有符号偏差 | 等级 |
|---|---:|---:|---:|---|
| [40,44) 秒 | 0° | 359° | +1° | D |
| [44,45) 秒 | 7° | 359° | +8° | U |
| [45,47) 秒 | 2° | 359° | +3° | A |
| [47,50) 秒 | 0° | 359° | +1° | D |

本例 D/A/U 分别占有效时长的 70%/20%/10%，保留失误和修正过程；最后恢复 D 不撤销 Fail。模型方法显示 pending_method，不输出能力概率或分数。

每个 sample 的 start_s/end_s 是外部给定的区间边界，系统不猜采样间隔或截取飞行阶段。原始值与期望值需同单位、同参考系。一次性事实放在所属检查点的 values 中，不能把 false/null 换成数值 0。

使用已有项目环境运行 tools/Generate-SceneSeriesExamples.py 可从当前 catalog 重新生成上述文件。默认空白模板与合成演示配置是不同文件。
