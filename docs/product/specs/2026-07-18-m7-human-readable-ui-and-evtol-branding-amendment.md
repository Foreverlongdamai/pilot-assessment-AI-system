# M7 Human-readable UI and eVTOL Branding Amendment

| 字段 | 值 |
|---|---|
| 设计基线 | M7 user-acceptance amendment |
| 日期 | 2026-07-18 |
| 状态 | 已批准，按方案 A 实施 |
| 决策 | D-058、D-059 |
| 科学边界 | 不改变 Evidence、BN、CPT、operator 或推理结果 |

## 1. 目的

本修订收口三项用户验收问题：普通界面暴露长技术 ID、模型名称带有 fallback 标记，以及应用缺少明确、专业的 eVTOL 产品图标。

技术 ID、revision、hash 和 artifact identity 继续存在并保持原有后端语义；本修订只改变其展示层级，不改变 canonical identity、持久化、RunSnapshot 或计算。

## 2. 人可读名称

普通工作界面只显示简洁英文模型名称，不使用 `node_id`、`scheme_id`、UUID、hash 或“未命名节点”作为可见名称。

节点名称按以下确定顺序解析：

1. 已保存的英文 short name；
2. 已保存的英文 full name；
3. Raw Input 使用 `SourceDescriptor.name` 或其 typed family/modality；
4. Evidence 使用 `EvidenceRecipe.anchor.name`；
5. BN 使用 reporting metadata、group、documentation 与 `BnNodeRole` 中最能表达实际作用的语义；
6. 最后才对稳定 ID 中非技术、非随机的语义 token 做人类可读化，并使用节点类型作为安全后备。

任务方案优先使用英文名称；缺失时从 task binding、group 或 tags 生成简洁的 `... Assessment Scheme` 名称。生成结果必须是英文、可读且不包含 UUID/hash。

名称解析是确定性的只读展示投影，不静默修改 canonical object。新建和编辑仍应要求专家提供英文模型名称；后续 D-055 单字段合同迁移负责永久移除双语 canonical 字段。

## 3. 技术身份展示边界

以下普通界面不显示长技术身份：

- Results 的 Evidence 和 posterior 列表；
- Model Studio 节点圆、tooltip、选择摘要；
- Runs/Results 的普通运行选择标题；
- 独立节点窗口的标题和默认上下文区域；
- Task Scheme 侧栏的方案标题。

以下诊断或高级技术区域可以继续显示 exact ID/hash：

- Diagnostics；
- Results 的 Provenance 与 Artifacts 页签；
- Runs 的 frozen snapshot 技术详情；
- 节点窗口中默认折叠的 Technical identity 区域；
- operator/source/schema/CPT state 等必须由专家精确编辑的技术字段。

## 4. 语言与 fallback

- `[EN fallback]`、`[中文回退]`、`[ID fallback]` 不得出现在发布界面；
- UI 菜单、按钮、字段标题和提示继续随中文/英文切换；
- Evidence、BN、Raw Input、operator 和 Task Scheme 的模型内容名称统一显示英文，不随 UI 语言切换；
- 名称缺失时使用第 2 节的语义解析，不显示“未命名”占位符。

## 5. 应用图标

新图标使用原创的极简 eVTOL 评估标记：

- 深海军蓝圆角方形底板；
- 白色俯视 eVTOL 单线轮廓与四个简化旋翼；
- 中央包含一个克制的评估/网络节点语义；
- 无文字、无渐变、无阴影、无现有品牌仿制；
- 在 16、24、32、48、64、128、256 px 仍可辨识。

项目保存 1024 px master，并从同一 master 确定性派生 `.ico`、Square、Store、Splash、Wide 与 unplated Windows assets。

## 6. 验收条件

1. Results Evidence/posterior 列表不再显示 `model-node...` 第二行；
2. 普通界面与 accessibility name 中没有 fallback marker 或长随机 ID；
3. 名称字段全部缺失的 Raw Input/Evidence/BN fixture 分别得到与实际定义对应的英文名称；
4. 技术 ID/hash 仍可在 Diagnostics、Provenance 或折叠技术身份区域查看；
5. 应用窗口、任务栏和 Windows 资产使用同一套 eVTOL 图标；
6. 资源键 parity、桌面单元测试、x64 Debug build 和真实窗口启动通过；
7. 本修订不产生 Python canonical model mutation，也不改变任何运行结果。
