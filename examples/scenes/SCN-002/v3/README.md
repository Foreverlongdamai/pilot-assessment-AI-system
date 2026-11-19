# SCN-002 / v3 帧输入与软件验证示例

日期：2026-09-15。用于当前双场景桌面开发版，schema_version 为 3.0。

| 文件 | 功能 |
|---|---|
| [configuration-template.json](configuration-template.json) | 空白规则与CPT草稿。无依据的目标和容差留空。 |
| [input-template.json](input-template.json) | item.frames 结构，每个阶段有一帧占位。复制持续阶段帧并填写精确时刻和原始值。 |
| [engineering-demo-configuration.json](engineering-demo-configuration.json) | 人工构造的算术验证参数，不是权威阈值，不用于实际训练结论。 |
| [engineering-demo-input.json](engineering-demo-input.json) | 合成的好表现—短暂失误—恢复输入，未取自实际飞行记录。 |
| [engineering-demo-report.json](engineering-demo-report.json) | 同一计算器生成的完整报告；保留失误与Fail，没有虚构贝叶斯分数。 |

在软件左侧选择本场景，加载工程演示配置，再导入工程演示帧数据，点击开始评估即可浏览。实际训练请使用空白模板自行配置，不直接采用示例数字。

到达下方初始点为前置流程，不单独评分。阶段：lower_1、upper_1、lower_2、upper_2 四次悬停，每次首末帧覆盖至少5秒；rise_1、descend_1、rise_2 三次转移。上下高度和靶面用不同原始量键，落点对象包含status/u_m/v_m。miss表示已知脱靶，null/unavailable表示缺测。

所有 item 使用同一个场景仿真时钟，timestamp_s 为非负相对秒；每个 item 内递增，不能每次重复阶段重新归零。无 start_s/end_s；没有从样例日志切片或自动识别阶段。

控制输入可作为可选 controls 对象保留 Pilot Lon、Pilot Lat、Pilot Yaw、Pilot Heave，不能代替实际位置/速度/航向，也不按动杆多少打分。

需要重新生成这些验证文件时，从仓库运行已有环境：

```powershell
.\.venv\Scripts\python.exe tools/Generate-SceneFrameExamples.py
```

完整说明：[场景评估与 Model Studio 使用指南](../../../../docs/product/SCENE_CALCULATOR_GUIDE_CN.md)。


当前两个 item 共六个检查点：A-S2-02“定点悬停保持”包含水平位置、高度、航向和激光四个检查点；SCENE-VERTICAL“垂直升降控制”包含两个检查点。此前的 SCENE-START 和独立高度 item A-S2-01 已取消。四次悬停各帧统一放在 A-S2-02 下，同时提供当前低/高点对应高度及其他悬停指标；高度和水平位置各自判定容差，不计算 XYZ 合成距离。水平速度归入水平位置，垂直速度归入高度。旧输入与配置需按照本目录新模板重新整理，软件不自动丢弃旧数据。
