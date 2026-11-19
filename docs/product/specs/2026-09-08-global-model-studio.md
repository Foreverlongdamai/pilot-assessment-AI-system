# 全局场景 Model Studio

用户已明确要求在左侧顶部增加总Model Studio，下面列场景；画布包含全部Task、item和检查点，可编辑贝叶斯参数，并随新增场景同步更新。本次直接实现该布局，保留六item规则与既有研究模型。

## 交互与语义

- 默认打开Model Studio。左侧第一项为Model Studio，随后是由服务器场景目录生成的场景菜单。当前只发布SCN-001，不创建虚构场景。
- 一个全局画布按场景分组，每组展示Task、item、checkpoint三列。支持缩放、适应全图和双向滚动；节点提供名称、已有等级和item技能分。刷新从当前配置/报告重建投影。
- Task至item用虚线表示场景归属；item至checkpoint用有方向实线表示P(检查点等级 | item技能状态)。Task保留确定性P/F，没有新设的Task概率或总技能分；画布不把归属关系冒充贝叶斯依赖。
- 点击Task选择该场景，侧面说明其判定方式并可进入场景页。点击item/检查点，在画布右侧显示内容和编辑入口。item入口编辑先验、状态分值和各CPT；检查点入口直接展示对应CPT，另外可打开其原D/A区间编辑器。
- 模型编辑使用同一SceneWorkspace的SceneItemEdit副本；应用前调用后端校验，只阻塞当前item的模型问题。模型单独编辑不被未填的容差阻塞。取消不改变状态，应用使旧报告失效，场景页马上使用更新配置。
- 导出空白输入模板、导入结果值、导出评估报告使用更完整的标签及说明。它们分别是结果字段合同、一次训练的外部结果输入、评估后输出，不提取原始数据。
- 导航时保留每个场景的参数、输入、报告、文件路径及未保存状态。保存配置仍按单个场景进行；总图保存按钮明确显示所选场景。关闭时逐个处理有未保存修改的场景。

## 共享接口与职责

Python增加scene.list返回{schema_version, scenes:[{scene_id,name,description}]}；scene.catalog可选scene_id，省略时兼容SCN-001。配置的scene_id用于选择已发布目录，未知场景不静默回退。发布新场景只需登记后端目录，前端从列表加载全部catalog后生成菜单和节点。新场景的评估规则和模型仍需正式设计/实现，此机制不会替新场景虚构规则。

Core代理拥有Desktop.Core/SceneAssessment及UnitTests：

- SceneRegistry DTO（TraceId可选、SchemaVersion、Scenes List<SceneSummary>）；SceneSummary包含SceneId/Name/Description；SceneGateway.GetSceneListAsync、GetCatalogAsync(string sceneId, CancellationToken=default)，旧无参数重载保留。
- SceneStudioState.Documents为IReadOnlyList<SceneDocument>；AddCatalog(SceneCatalog)、GetDocument(string)。SceneDocument.Workspace为SceneWorkspace，ConfigurationPath/InputPath可空读写，IsDirty布尔读写。相同scene id拒绝重复加入，不重置已有编辑。
- SceneGraphProjection.Build(IEnumerable<SceneWorkspace>)，返回Nodes、Edges、Width、Height。节点SceneGraphNode公开init属性Id/SceneId/ItemId?/CheckpointId?/Kind/Title/Detail/Grade?/Score?/X/Y/Width/Height。Kind=task|item|checkpoint。边SceneGraphEdge.FromId/ToId/Kind，Kind=membership|bayesian。ID包含scene限定，避免跨场景相同item混淆。Task无Score，节点无证据不得编造等级/零分。
- 布局每场景三列：Task x40 width230，item x340 width270，checkpoint x760 width330；checkpoint高76，纵向间隔约92，item/task放在各子树中心。整体留白和场景间分隔。投影不持有可变编辑对象。

Canvas代理仅拥有Desktop/Controls/Graph/SceneModelCanvas.cs：纯WinUI UserControl。公开SetProjection(SceneGraphProjection)，event EventHandler<SceneGraphNode>? NodeInvoked。布局、缩放、滚动、图例、Task虚线/BN实线与箭头、节点可点击，使用现有ThemeResource。首次加载适应画布宽度（保持可读），适应全图按钮另外提供。不得自行调用后端或复制模型状态。

Root拥有窗口导航/右侧检查器、独立模型编辑弹窗（可复用SceneSkillModelEditor并增加可选checkpoint过滤）、真实RPC合同测试、文档和统一构建。后端代理拥有Python及测试。保留DECISIONS和所有原有未提交更改，不提交或迁移数据库。

## 验证

核心：两场景重复item标识的节点不碰撞，所有检查点恰好一条BN边，Task边类型正确；模型编辑取消/应用/场景切换不丢失且隔离；缺报告不伪造分数。真实RPC列表和按ID加载、未知ID拒绝。回归六itemBN/PF及JSON往返。WinUI构建，实际验证总图导航、节点选取、CPT编辑入口与场景切换；如自动化限制则准确记录。
