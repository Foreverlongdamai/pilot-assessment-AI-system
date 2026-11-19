# SCN-001 空白文件模板

**2026-09-14：本目录的两个 1.0 JSON 保留为历史模板。当前软件请使用 [v2 模板及工程演示](v2/README.md)。以下为旧格式说明，不能作为 2.0 输入合同。**

- `configuration-template.json`：27行可配置数值参数；科学阈值为空，明确的偏差期望值和固定下界为0。
- `input-template.json`：30个已计算结果字段，初始全部为null。不是试飞样例或示范成绩。

可直接在新场景评估界面加载配置模板，再点击item逐行填写参数。输入模板填写外部已获得的结果值后导入软件；不要把缺失值替换为0。

输入字段的秒数、米、米/秒及度数含义见界面item编辑器和包内`scene_assessment/scn001.json`。两个末端item共享唯一的`terminal_hover_duration_s`结果及配置行。三个事实字段为`deceleration_started`、`stop_achieved`（布尔）和`quickstop_prohibited_event_count`（非负整数）。

模板由已打包的场景目录生成；参数只是可编辑配置，不是FAA或人因研究推荐数值。
