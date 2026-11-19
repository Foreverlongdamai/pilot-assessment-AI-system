# 场景评估软件重建：第一版实施规格

日期：2026-09-07。用户已确认SCN-001六个item的方法设计完成，并授权开始coding及选择复用或重建路线。本规格记录该授权下的工程选择。

## 路线

在现有仓库、WinUI项目和Python包内建立独立场景评估模块，替换默认启动界面。复用桌面运行环境、JSON-RPC/JSONL传输、文件选择和打包；保留旧模型工作台代码，通过`--legacy-workbench`显式进入。旧模型、运行记录、SQLite及已发布合同不迁移、不重解释。

原窗口保存/关闭绑定模型编辑会话，原Python启动会创建旧模型库。因此新建SceneAssessmentWindow和`python -m pilot_assessment.scene_assessment`入口，不让新流程经过旧Project、Model、BN或原始数据管线。

替代方案是直接改旧MainWindow或另建技术栈。前者保留大量旧业务耦合；后者重复运行环境和打包工作。本轮选择同仓独立重建。

## 用户能完成的流程

1. 打开软件，左侧是场景，当前只有SCN-001加速减速任务；主区域列六个item。
2. 点击item弹出检查点参数编辑器，显示结果含义、单位、期望值、D/A上下限及条款来源；无上限必须显式选择。参数无科学默认数字，允许保存尚未填齐的场景配置文件，计算前显示缺项。
3. 保存/加载参数JSON；导出空白输入模板；导入外部提供的预计算结果JSON。软件不生成检测结果。
4. 计算并展开各结果、检查点、item及场景的D/A/U和P/F，查看输入及区间与原因。
5. 导出包含输入和配置快照的独立结果JSON。参数或输入改变后，旧结果明确标为需重新计算，禁止冒充最新结果导出。

默认主界面不提供图结构编辑、CPT、连续分数或原始数据检测设置。六item和检查点由场景目录定义，界面不重复硬编码其评估逻辑。

## Python与.NET共享接口（实现以此为准）

新增包`src/pilot_assessment/scene_assessment/`。RPC沿用hello/协议1.0，能力为`runtime.protocol.v1`与`scene.assessment.v1`，不宣称旧model能力。

- `scene.catalog`，参数`{}`，返回下述目录对象。
- `scene.validate_configuration`，参数`{"configuration": ...}`，返回`{"valid": true或false, "issues": [{"path": "...", "message": "..."}]}`。
- `scene.evaluate`，参数`{"configuration": ..., "input": ...}`，返回下述报告。
- `runtime.shutdown`关闭进程。

传输层会在成功RPC响应中附加`trace_id`；仅目录、配置验证结果和评估报告DTO接纳该响应标识，输入与配置文件仍严格拒绝未知字段。健康查询`capabilities.list`和`runtime.status`与现有桌面进程host兼容，不加载旧模型库。

目录对象：

```text
schema_version: "1.0"
scene_id: "SCN-001"
name, description: 中文文本
metrics: [{metric_id, name, description, unit,
           value_type: "number"|"boolean"|"integer",
           rule: "interval"|"must_be_true"|"zero_events",
           parameter_kind: "gaze"|"error"|"hold"|"signed"|"duration"|"fact",
           shared: bool}]
items: [{item_id, name, description,
         checkpoints: [{checkpoint_id, name, description, metric_ids: [string],
                        sources: [{document, clause, page, url, support, note}],
                        fail_when: [{metric_id, equals: 0或false}],
                        not_required_when: [{metric_id, equals: 0或false}]}]}]
configuration_template: 配置对象
input_template: 输入对象
```

包内`scn001.json`是检查点、字段和来源的唯一软件目录。官方数字只出现在来源说明中，不生成参数默认值。目录loader构造模板。

配置对象：

```json
{"schema_version":"1.0","scene_id":"SCN-001","parameters":{
  "某个interval结果字段": {
    "expected": null,
    "desired": {"lower": null,"upper": null,"unbounded_upper": false},
    "acceptable": {"lower": null,"upper": null,"unbounded_upper": false}
  }
}}
```

所有数值留空；error/signed的明确期望0可以显示0，error区间的固定下界0可以显示0。这不是科学容差默认值。事实规则不提供可编辑参数。末端保持只有`parameters.terminal_hover_duration_s`一份，其中D/A下界分别对应设计文档`terminal_hold_desired_s`/`terminal_hold_acceptable_s`，两个item引用同一对象。

输入对象：`{"schema_version":"1.0","scene_id":"SCN-001","results":{"结果字段": 数值或布尔或null}}`。六个起飞前字段使用已确认的energy_electrical等名称，其值均为秒。其余字段严格沿用六份方法稿。模板全部null，不内置试飞成绩。

报告对象：

```text
schema_version, scene_id, evaluated_at
calculation_status: "complete"|"needs_input"
grade: "D"|"A"|"U"|null
passed: true|false|null
configuration: 实际使用的配置快照
input: 实际使用的输入快照
issues: [{path, message}]
items: [{item_id, name, grade, passed,
         checkpoints: [{checkpoint_id, name, grade,
                        metrics: [{metric_id, value, grade,
                                   status: "calculated"|"missing"|"invalid"|"not_required",
                                   reason, parameter: 配置行或null}]}]}]
```

null是尚无可计算结论，不是第四种表现等级。任一已确定U可形成所属检查点/item/场景U，即使其他结果待补；存在缺项时不输出完整Pass。配置/输入快照深复制，后续编辑不改变已返回报告。

## 计算与校验

- 有限数值；布尔不可冒充数值，事件计数必须非负整数，绝对偏差/秒数/速度非负，实际减速耗时正数，起动位置允许有符号。
- 闭区间，D严格包含于A，期望值在D内；error两下界为0、期望0；gaze最低A下界严格正；hold两个正下界满足A<D；signed两个区间包含0；duration下界非负。
- 无上限由`unbounded_upper=true`表达且upper为空；空上限且false表示缺参；拒绝倒序、相等D/A、非嵌套和无穷/NaN。
- 数值先D后A否则U，事实true→D/false→U，禁止事件0→D/非0→U。检查点、item、场景取最差档；P/F仅从档位映射。
- `fail_when`支持明确0秒或false直接使检查点U。未发生动作的其余缺值可记not_required，不补0；合法已提供结果仍如实显示。缺失本身不能触发该规则。
- 可选`not_required_when`仅豁免未发生动作的缺失结果，不产生D/A/U。末端保持时长0时，航向结果不必提供，航向检查点仍无独立档位；悬停定点item由位置保持检查点的U决定。
- 未开始减速使急停①②U；未停止使②U；三类保持时长0使相应保持检查点U。数据或参数有变化即使旧结果失效，不自动改变区间或补结果。
- 未知字段、错误场景/version、错误数据类型在问题列表中说明，避免误拼字段悄悄被忽略。

## 验证与交付

先写针对闭区间、配置错误、最差档、缺值与未执行、共享保持的失败测试，再实现calculator。RPC用真实stdio往返验证；Desktop.Core测试配置编辑取消、共享引用、结果失效和JSON往返。新WinUI窗口完成Debug构建，生成本地候选程序并做实际启动存活验证；可视交互若工具无法操作须如实记录。

工程合成数字仅在tests中验证算术，不出现在程序默认参数或学员输入里。本轮不会把测试通过解释为评估标准已完成科学验证。
