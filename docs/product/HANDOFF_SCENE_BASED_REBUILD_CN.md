# 交接：场景化评估改造

**2026-11-12 工作边界（D-008、D-009）：只用现有内容，不向他人确认，可以查阅资料；设计出来的就是定稿。** 当前评估方法设计见[系统修订讨论稿](plans/2026-11-02-system-revision-discussion.md)，其中已确认的D-001～D-009优先于下方各轮场景、item与检查点描述。讨论稿草案部分仍在讨论，软件尚未按新方案修改。原需开发方核实、专家或教员标注的事项，由本项目依据现有实采数据与资料直接确定。软件界面、报告、配置、模板和说明不标注未确认、待验证、未标定、暂定、演示模型等状态，也不写已验证、已标定。设计依据保留在设计文档中，由用户被问及时解释。下方各轮记录中的“未标定”“演示假设”等措辞属于历史状态，软件按新方案修改时一并去除。

**2026-10-11 当前场景范围按真实任务修订。** 用户确认加速减速任务没有正常进近至悬停，当前 v3 SCN-001 删除 A-S2-23，以及 approach/approach_deceleration/arrival_hover 三阶段与八个专属输入量。快速停止 item A-S2-30 改名“快速减速／快速停止”，参照 FAA-S-ACS-2 CP.VI.A Rapid Deceleration/Quick Stop，现有检查不宣称覆盖最大性能减速。确认结束只是任务边界。本轮保留起飞前检查单，SCN-002 不变；未新增检查点、改阈值、改CPT或改概率方法。当前 SCN-001 为3 item/12检查点/17输入量；SCN-002 为2/6/13，总画布25节点（2 Task/5 item/18检查点）。下方九月计数和进近设计均为历史状态。

当前配置与六份合成输入另存：[本轮演示包](../../examples/task-scope-2026-10-11/README_CN.md)。已核对所有保留 item 的帧、参数、模型及分数与九月包一致。旧 v3 配置/输入含 A-S2-23 时需明确整理，不自动丢弃用户数据；历史包与原始 CSV/视频保留。当前模板已同步。参见[修改范围](plans/2026-10-11-scn001-task-scope.md)及[验证记录](reviews/2026-10-11-scn001-task-scope-verification.md)。

**2026-09-23 界面名称统一为“贝叶斯网络”。** 按用户要求，软件主界面、Model Studio、参数编辑器、结果窗口和演示网页不再单列强调“贝叶斯＋补偿”。α 对外称“更新系数”，逐帧明细称“CPT 观测更新／观测目标／概率调整量／更新后概率”。仅调整展示文字，融合机制、公式、配置值和 JSON 协议字段不变。六输入与全部配置／报告数值核对一致，365 项 Python、302 项桌面单测通过；原快捷方式 exe 已于本日 13:14 重建，0 警告／0 错误。技术说明仍保留真实计算公式，内部 method 和 compensation 字段不改名。

**2026-09-23 后续决定：删除旧方法，只保留新版。** 用户明确要求不再保留旧方法或手动转换入口。当前软件仅运行 `sequential_bayes_compensation_v1`；旧 κ=3、近3秒局部推断、τ 过程和旧单次 EAP 生产实现已移除。已知旧 v3 配置导入时自动转换并保留先验、CPT、分值，缺省补偿 α=0.2；已有新法 α 不重置，未知方法仍拒绝。导出保存为新法，不覆盖原文件。旧数据格式只保留规则支持，不能再算旧概率。历史研究材料和已导出的旧报告是档案，不作为可选择的计算方法。下方本日先前“旧方法仍可重放、需点击转换”已被此决定替代。

**2026-09-23 当前软件方法：传统 CPT 贝叶斯更新后，再做双向补偿。** 用户明确确认该顺序。新 `sequential_bayes_compensation_v1` 用上一帧补偿后概率作为下一帧先验；先算 `q ∝ prior × CPT likelihood`，再算 `p=(1−α)q+α×本帧等级目标`，最后才由概率映射分数。两个场景全部 5 个飞行 item／14 个飞行检查点采用同一条链；新结果、累计输出和过程曲线终点一致，不再由 κ=3 另算主分。item 融合同帧检查点似然，先验只计一次、补偿只做一次；目标取已有最差检查点等级。α 默认演示值 0.2，可编辑，按有效帧使用，未标定。检查单、原始值判档和 P/F 保持。

**新方法的输出含义：末帧模型状态。** 它依赖证据顺序和采样率，不是整段平均质量。后段恢复可把概率拉回高档，但历史 U／Fail 仍保留。每帧报告包含先验、CPT 后验、补偿目标、补偿比例及补偿变化量；连续同类证据仍可能使概率接近 1，补偿保证反向证据仍有修正入口，不保证概率永不饱和。旧方法仅保留兼容重放，旧配置可在编辑器明确转换；不自动覆盖原文件。不包含跨训练学员状态自动保存。

当前入口：[新版六例配置与输入](../../examples/bayes-compensation-2026-09-23/README_CN.md)、[已确认计算合同](plans/2026-09-23-bayes-compensation.md)、[本轮验证](reviews/2026-09-23-bayes-compensation-verification.md)。下方 9 月 16 日及以前的 κ、τ、空模板 pending 和双算法主分说明是历史记录。

**2026-09-16 最新展示：过程下图改为逐帧 D/A/U 色带。** 用户确认后，桌面 item／检查点报告及两个场景网页同步采用绿D、黄A、红U；缺测灰色，不适用和时间空档留白。上方时序后验曲线保留，log BF 移至高级折叠明细。色块是实际帧的显示占位，不推断帧间观测持续时间，不改变评分。参考[色带计划](plans/2026-09-16-grade-band.md)和[验证记录](reviews/2026-09-16-grade-band-verification.md)。

**2026-09-16 时序过程分析已作为加法接入。** 用户批准将固定 item 水平 S＋时间相关观察用于过程描述。两个场景全部 5 个飞行 item／14 个飞行检查点新增 `fixed_skill_markov_v1`：完整时序后验期望、逐帧表现及高级证据明细，参数编辑器可显式启用并编辑三态相关时间 τ；新版演示配置全部设为未标定 [5,5,5] 秒。先验只计一次，融合条件似然而非检查点后验；阶段切换只重开观察链，保留已有能力证据。检查单仍为 true/false 完成性。原输入、CPT、阈值、最终后验/分数、原累计曲线和 P/F 均保持；未来把过程信息纳入最终评估仍未实施。旧配置不自动启用，演示需重新加载 configuration.json 并评估。

**本轮验证与交接边界：** Python 505、Desktop UnitTests 297、六例真实合同 6、既有绘图 18 均通过；独立高精度对照 14,078 个后验、六演示重算 9,180 个过程点通过。原快捷方式目标 exe 已重建，浏览器双图已实际查看。原生主界面已启动；进一步逐项点选因检测到用户同时操作窗口而暂停，不能把构建/合同测试写成原生结果窗口已验收。详见[实现验证](reviews/2026-09-16-temporal-process-verification.md)、[独立审查](reviews/2026-09-16-temporal-process-independent-review.md)、[实现合同](plans/2026-09-16-temporal-process-analysis.md)。下方“研究候选、尚未接入”的记录是本次实现之前的状态；正式整段最终量化方法仍待研究，与已接入的过程分析有别。

**2026-09-16 逐帧贝叶斯方法审查（研究候选，未替换运行模型）：** 用户提出“item 能力→检查点 CPT，按帧更新能力后验并量化”。已核对测量文献及当前实现，完成[方法审查](reviews/2026-09-16-sequential-item-bayes-review.md)、[原始文献笔记](reviews/2026-09-16-sequential-bayes-literature-notes.md)与[离线数学对照](reviews/assets/sequential-bayes-2026-09-16/math-review.md)。方向合理，但直接将当前 CPT 按独立帧累乘会受重复信息、采样率及后验饱和影响。候选为固定当次 item 水平 S、显式建模观测时间依赖；动态瞬时表现是另一种估计对象。现行占比＋κ=3、CPT、D/A/U、P/F 和 exe 均未因此变更，候选转移参数尚未标定。

**2026-09-15 当前速度与演示输入修订：** 空中滑行首检查点改为“加速与保速速度控制”，新 `air_taxi_airspeed_mps` 覆盖 acceleration/hold，`item_profile` 单表以 acceleration 第一帧为共同0秒，节点之间仅插值参考值。删除独立保速时长与 hold_end；既不拉伸时间也不补观测，缺起点/参考越界/缺尾端不能完整评估。演示参考0s→0m/s、6s→10m/s、16.1s→10m/s，属于项目目标而非官方规定。stop允许连续多帧，三例均提供5秒51帧，未新增最少采样或时长规则。信号版本 `continuous-multiscale-shared-speed-v3`；须同时重新加载配置与输入。当前SCN-001为4 item/14检查点/25指标键，SCN-002为2/6/13，总图仍28节点。下方旧速度字段、单帧stop和历史分数已被替代。

**同轮全量审查：** [20检查点标准映射](reviews/2026-09-15-full-flight-standards-audit.md)及[180组概率参数对照](reviews/assets/bayesian-audit-2026-09-15/SUMMARY_CN.md)已单列；当前CPT及κ=3保留为未标定基线。急停缺速度、垂直升降缺高度、路线距离不证明沿向进度等列为下一轮讨论，不擅自增加机型阈值。停止多帧是输入改进，不将稀疏采样审查转成用户未要求的新系统规则。最新完成与验证见[本轮记录](reviews/2026-09-15-shared-speed-and-audit-verification.md)。

**2026-09-15 最新演示输入修订：** 用户要求原值曲线增加连续、细碎的修正波动。两场景六例已采用 `continuous-multiscale-demo-v2` 合成信号，保留原配置/CPT、帧时刻与阶段，位置/速度解析一致、激光同帧几何一致。新数据须重新导入并评估；已打开的报告是旧评估快照。最新分数以演示包 `SUMMARY_CN.md` 为准，历史验证中的旧分数不再代表当前数据。频率和幅度为未标定合成演示选择。见[本轮计划](plans/2026-09-15-demo-signal-jitter.md)。

**本轮结果展示已实现并验收：** 两场景的独立 item 窗口、完整观测图、累计分数、Model Studio 入口与原生导出回读已通过；原快捷方式目标 exe 已更新。自动检查为 Python 411、C# 单元 255、场景合同 10、绘图 18。见[结果窗口验证记录](reviews/2026-09-15-item-report-window-verification.md)。Windows 文件框须使用完整路径或直接浏览选择文件；本轮相对路径引起的“文件名无效”已通过完整路径导入验证排除文件名长度问题。

**2026-09-15 最新结果展示修订：独立 item 结果窗口＋完整过程图。** 用户要求评估后点击 item 打开窗口、按检查点整齐展开完整时间过程，图形采用实际曲线、期望虚线、D绿色内带/A浅黄色外带。随后明确选择累计 item 分数（截至当前时刻），曲线终点须与整段最终分数一致。主页面保留简洁结果卡，参数编辑使用独立入口；结果窗口持有评估快照。新增可选 `cumulative_trace`，不重置phase、不把过去3秒代替全程、不累乘重叠前缀、不将尚未出现的检查点填为好表现；观察覆盖与最终完整性分开。旧局部诊断数据继续兼容，正式参数与P/F不改。具体合同见[本轮实施计划](plans/2026-09-15-item-report-window.md)及[当前指南](SCENE_CALCULATOR_GUIDE_CN.md)。下文将近3秒曲线作为主界面或将点击结果与编辑合并的说明为历史。

**2026-09-15 最新已批准修订：合并悬停高度与定点 item。** SCN-002 删除独立 `A-S2-01`，`A-S2-02` 改为「定点悬停保持」，四检查点依次为水平位置（X/Y＋水平速度）、高度（当前上下目标高度＋垂直速度）、航向、激光；同一次悬停的全部原始值进入该 item 的同一帧，不合成 XYZ 总距离，不补值。四检查点参与同一份悬停 CPT 模型和整项演示后验，各有独立局部过程曲线，原 D/A/U、P/F 不被分数覆盖。`SCENE-VERTICAL` 保持不变。当前 SCN-002 目标结构为 2 item／6 检查点／13 指标键，两场景总图为 28 节点（2 Task、6 item、20 检查点），飞行 item 共 5 个。旧 `A-S2-01` 输入和旧悬停 CPT 配置须按新模板明确整理，软件不静默丢字段或平均合并旧 CPT。FAA CP.IV.A.S5/S6/S8、EASA FEM 3.3 与 CAA03(H) 支持同一悬停任务中检查位置、高度和航向；速度、激光、5 秒流程及分档量化为项目适配。先读[本次合并计划](plans/2026-09-15-hover-item-consolidation.md)、[当前指南](SCENE_CALCULATOR_GUIDE_CN.md)、[本次验证记录](reviews/2026-09-15-hover-item-consolidation-verification.md)。下文“高度与定点不合并”、SCN-002 三 item、29 节点以及合并前演示分数均为历史；本轮实际完成状态以新验证记录为准。

**2026-09-15 导师演示包：** 两场景各三份合成输入（熟练、勉强合格、局部失误后恢复的 Fail），每场景共用配置。部分 A 容差直接锚定 FAA-S-ACS-2；其他阈值和 CPT 明确为演示假设。v3 可显式选择 `demo_normalized_grade_likelihood_v1`：按检查点帧占比、等权、固定 κ=3 得整项演示后验/EAP；各检查点另有过去 3 秒的局部证据曲线，按已提供 phase 重置，不是 DBN。默认空模板仍 pending；P/F 不被分数覆盖。原始值图、概率、局部分数、源参数及输入快照均保留。先读[演示包](../../examples/supervisor-demo-2026-09-15/README_CN.md)、[参数依据](../../examples/supervisor-demo-2026-09-15/PARAMETER_BASIS_CN.md)、[方法](plans/2026-09-15-supervisor-demo-method.md)。下文“v3 不计算任何概率”的表述是未显式加载演示模型时的基线。

**2026-09-15 当前决定：A-S2-23 精简为两个检查点。** 用户批准“进近航迹控制＋到点建立悬停”。前者按每帧实际三维位置到手工折线路线的空间距离，以 D/A 通道半径判档，高度包含在内；后者保留到点位置、近零地速与航向。移除当前场景的固定横向位置及逐秒空速／高度／垂直速度参考剖面，不以时序曲线约束一般进近。输入仍是 item.frames，不识别阶段或补帧。SCN-001 为 4 item／14 检查点／26 输入指标键（三维位置键含三个分量），SCN-002 为 3／6／13，总画布 29 节点。路线、到点目标、半径均手填；无统一权威 D/A 默认数值。下方三／四检查点、时间参考曲线及旧计数全部为历史。当前读[路线合同](plans/2026-09-15-approach-route-corridor.md)、[使用指南](SCENE_CALCULATOR_GUIDE_CN.md)和[验证记录](reviews/2026-09-15-approach-route-corridor-verification.md)。

**2026-09-15 最新决定：正常进近至悬停先做通用操纵评估。** A-S2-23 移出第四个“机型程序执行”检查点，保留进近航迹、稳定进近与减速、到点建立悬停三项；当前不要求 `approach_checklist_completed`、`approach_procedure_configuration_correct`，无对应检查点或 CPT。检查单、构型与机型操作程序留待具体型号时再定义；已有起飞前检查 item 保留，前三项及悬停场景方法不变。当前两场景分别 4/15/29 与 3/6/13（item/检查点/输入量），总画布 2 Task、7 item、21 检查点，共 30 节点。通用方法的目标、参考剖面和容差仍须按场景填写，不提供统一权威数值。当前定义见[进近修订合同](plans/2026-09-15-approach-hover-refinement.md)，本轮验证单列于[通用评估裁减记录](reviews/2026-09-15-general-approach-refinement.md)。下方“四检查点”和 31 节点是此次裁减前历史，不代表当前目录。

**2026-09-15 起点 item 修订：** 用户确认 SCN-001 在起飞后从别处进近起点、减速并建立悬停。因此用“正常进近至悬停”（A-S2-23，参照 FAA-S-ACS-2 CP.V.D）替代单帧起点就位；四个检查点涵盖航迹、稳定进近与减速、到点悬停、程序执行。进近数值使用手工参考剖面，到点环节采用固定位置/速度/航向目标。SCN-002 删除起点就位，保留悬停高度、悬停定点、垂直升降三个 item，本轮不合并高度与定点。两场景分别 4/16/31 与 3/6/13（item/检查点/输入量）；总画布 31 节点。新目录不能读取含旧 SCENE-START 的输入/配置，不自动迁移。阈值、参考剖面、CPT 均无权威通用默认值，贝叶斯计算方法仍待定。以下旧计数及起点定义是历史状态。

当前修订：[数据与条款合同](plans/2026-09-15-approach-hover-refinement.md)、[实现与原桌面快捷方式验证](reviews/2026-09-15-approach-hover-refinement-verification.md)。已重建并实际验证新版；参考剖面可编辑并保留空值草稿。

**2026-09-15 当前状态：两个场景的 v3 逐帧评估已实现。** SCN-001 为起飞前检查、起点就位、空中滑行、急停 4 个 item（15 检查点）；SCN-002 为起点就位、悬停高度、悬停定点、垂直升降 4 个 item（9 检查点）。输入使用 `items[item_id].frames`，每帧提供精确 `timestamp_s`、已归属的 `phase_id` 和原始 `values`，可附操纵输入；系统不识别事件、截取阶段或补帧。报告输出逐帧 D/A/U、P/F、有效帧数占比和输入/配置快照，不再将帧统计称为时长占比。阈值与 CPT 尚未科学标定，CPT 保留草稿编辑，v3 不计算贝叶斯概率或技能分数。

最新入口：[使用指南](SCENE_CALCULATOR_GUIDE_CN.md)、[v3 验证记录](reviews/2026-09-15-two-scenes-frames-v3-verification.md)。以下保留历次交接正文；其中 v2 区间输入、仅一个场景、软件尚未迁移及旧分数描述均为历史状态，不能覆盖本段。

**2026-09-14 coding 更新：已按用户授权实施 v2 原始值与时序方案。** 当前 SCN-001 为 4 个 item、16 个检查点、25 个数据量；检查单读取 true/false，飞行数值按“原始值−期望值”及有符号 D/A 容差判断，航向使用最短角差。输入按 item/checkpoint 组织，时序区间由外部明确提供，不检测或截取事件。过程、时间占比、A/U 片段和输入/配置快照已接入报告，Model Studio 保留顶部入口和飞行 CPT 草稿编辑。整段占比到后验及动态 item 模型仍待选择，v2 不输出旧静态模型分数。当前阅读入口：[使用指南](SCENE_CALCULATOR_GUIDE_CN.md)、[数据合同](plans/2026-09-14-checkpoint-series-v2.md)、[验证记录](reviews/2026-09-14-checkpoint-series-v2-verification.md)、[新模板](../../examples/scenes/SCN-001/v2/README.md)。以下“尚未迁移软件”“六 item 默认演示模型”等均为历史状态，不能覆盖本段。

**2026-09-14最新用户纠正：JSON已经按item/检查点整理好对应阶段的详细原始值，急停数据范围包含末端；系统不再识别阶段或截取事件。** 系统计算“实际值−期望值”的有符号偏差（航向为最短角差），D/A下界和上界表示相对期望值允许低于/高于多少，不再要求外部预算偏差。见[输入与有符号容差基线](../../../current_stage_scene_based_assessment_2026-08-31/scenes/SCN-001_accel_decel_quickstop/scope_refinement_2026-09-13/CHECKPOINT_INPUT_AND_SIGNED_TOLERANCE_2026-09-14_CN.md)及[共同方法v1.1](../../../current_stage_scene_based_assessment_2026-08-31/ITEM_DESIGN_METHOD_CN.md)。本轮仅更新设计文档；下方旧输入字段、最大偏差和区间语义仍是历史实现，未迁移软件、模板或EXE。

**2026-09-13 最新用户方向：起飞前／座舱类检查简化为 checklist，以每次飞行 JSON 中逐项 true/false 表示是否完成；不再要求起飞前眼动停留秒数。** 见[检查单与场景分工记录](../../../current_stage_scene_based_assessment_2026-08-31/scenes/SCN-001_accel_decel_quickstop/scope_refinement_2026-09-13/DESIGN_CN.md)。用户拟设独立悬停场景，现建议将 SCN-001 末端两个持续悬停 item 移过去，急停仍保留动作完成和收尾控制；这一场景拆分尚待确认。本轮仅记录设计，以下六 item 界面及旧输入合同仍是现有实现状态，未更新软件或 EXE。

**2026-09-08最新界面：默认全局 Model Studio 位于左侧顶部，各场景列在下面。** 当前 SCN-001 的总画布展示 1 个 Task、6 个item、19 个检查点，共 26 个节点。Task → item 虚线仅表示归属，item → 检查点实线表示贝叶斯依赖；Task 没有 CPT 或技能总分，原规则 D/A/U、P/F 独立保留。点击item可编辑先验、状态分值和各检查点 CPT；检查点的模型入口只编辑该点 CPT。模型编辑与未填写的检查区间分开校验，画布与场景页使用同一份配置，应用后旧报告失效。

**文件操作按工具栏显示的当前场景进行。** “导出空白输入模板”输出预计算结果字段，值为`null`；“导入结果值”读取外部已经计算好的 JSON；“导出评估报告”输出规则结果、EAP、后验概率和输入/配置快照。保存、加载和导入不会跨场景混用，切换场景保留各自配置、输入、报告、文件路径及未保存状态。系统仍不检测或提取原始眼动、飞行数据。

**新增场景的同步方式：** 完成新场景的评估规则及模型，提供完整 catalog loader 并在 Python `scene_assessment/catalog.py` 的 `SCENE_CATALOG_LOADERS` 登记后，重启包含该目录的新版软件，菜单和总画布从同一列表同步生成。当前只发布 SCN-001；不是在 UI 任意建场景，也不是热更新。

先读[Model Studio 规格](specs/2026-09-08-global-model-studio.md)、[使用指南](SCENE_CALCULATOR_GUIDE_CN.md)和[本轮验证记录](reviews/2026-09-08-global-model-studio-verification.md)。当前 exe 为`src/PilotAssessment.Desktop/bin/x64/Debug/scene-studio/PilotAssessment.Desktop.exe`；`tools/Start-SceneAssessment.ps1`使用独立输出目录，以保留此前正在运行的旧窗口，`-Build`与`-LegacyWorkbench`继续可用。下方旧“左侧只有场景”“Task 参与三层BN评分”等历史设计不能覆盖本次实现。

**2026-09-07最新加法：六item静态贝叶斯网络与EAP已接入场景计算器及WinUI。** 用户确认将地面起飞的小模型量化方法推广到全部六项。各自以原检查点等级为唯一表现观察，估计本次低/中/高技能概率，并以可配置状态分值计算EAP；原D/A/U和P/F独立保留。新配置含未校准演示模型，旧配置不会自动补模型；没有历史BKT、原始数据提取或场景总分。当前依据为[量化规格](specs/2026-09-07-six-item-bayesian-eap.md)、[使用指南](SCENE_CALCULATOR_GUIDE_CN.md)和[本次验证记录](reviews/2026-09-07-six-item-bayesian-eap-verification.md)。下面关于“未接BN/无连续分数”的说明已被本次实现取代。

**2026-09-07最新工程进展：用户已确认场景完成并授权coding，首个开发版已落地。** 在原仓库新增独立`scene_assessment` Python包与stdio入口、新WinUI默认场景窗口、Desktop.Core场景DTO/编辑状态/客户端；复用进程通信和运行环境。新流程支持六item参数编辑、配置及输入JSON、分档和报告快照；旧工作台由`--legacy-workbench`进入。先读[使用指南](SCENE_CALCULATOR_GUIDE_CN.md)、[实施规格](specs/2026-09-07-scene-calculator-rebuild.md)及[验证记录](reviews/2026-09-07-scene-calculator-verification.md)。下方“待审/软件未实现”仅是先前讨论状态；旧模型图、BN、检测器和原始数据接入方案不控制新模块。

**2026-09-07当前讨论进展：六个item的方法稿已写齐。** 用户要求保持节奏完成剩余item后统一审阅，当前先读[全场景审阅总览](../../../current_stage_scene_based_assessment_2026-08-31/scenes/SCN-001_accel_decel_quickstop/REVIEW_ALL_ITEMS_2026-09-07_CN.md)。A-S2-08地面起飞、A-S2-05空中滑行已有方案，本轮补齐A-S2-30急停、A-S2-02悬停定点、A-S2-01悬停高度v0.1稿；各检查点标明官方条款或项目适配。末端两个item共用同一次保持及同一组时长参数。下一步根据用户反馈修订方法；草案齐全不表示逐点获批、数值已标定或软件已实现。

**2026-09-07已确认基线：** 用户明确确认第一个item设计完成，并要求所有后续场景与item沿用同一方式。先读[共同方法与item模板 v1.0](../../../current_stage_scene_based_assessment_2026-08-31/ITEM_DESIGN_METHOD_CN.md)，再读[已确认的A-S1-06方法 v1.0](../../../current_stage_scene_based_assessment_2026-08-31/scenes/SCN-001_accel_decel_quickstop/preflight_gaze_design_2026-09-07/DESIGN_CN.md)。六区域、结果字段、参数编辑与判档规则已确定；数值手填、默认留空，没有权威数字不影响设计完成。业务软件尚未按此实现。本文件后续历史结构、原始数据算子、旧检查点数量及旧事实源声明不得覆盖以上两份基线。

**2026-09-07用户进一步澄清的全局边界：这是接收“已检测结果”的理论评估计算系统。对所有场景、所有item，只设计评估内容、需要哪些结果值、配置参数和D/A/U、P/F判定，不考虑这些结果来自何种检测或如何提取。** 下文旧原始数据接入、时间事件求解和指标提取方案不再属于当前实施范围。不要把这个边界仅理解为起飞前眼动item的特殊适配。

**2026-09-07最新用户裁定优先：[起飞前仪表区域注视时长评估设计](../../../current_stage_scene_based_assessment_2026-08-31/scenes/SCN-001_accel_decel_quickstop/preflight_gaze_design_2026-09-07/DESIGN_CN.md)。** SCN-001先移除A-S1-02座舱检查，保留六个item；A-S1-06直接接收各仪表区域停留时间JSON，点击item弹出各区期望时间与Desired/Acceptable区间编辑器，计算D/A/U及P/F。用户明确指定该眼动指标直接用于本item门控，因此旧文档关于此类数据仅作诊断的限制不再适用于这个方法。本轮不做眼动提取、不实例化新BN分数；下文旧数量和冲突地面方法仅作历史背景，DECISIONS保持不动。

**日期：** 2026-09-05
**交接给：** Codex（后续开发全部由你负责）
**分支：** `feat/scene-based-assessment`（已建，基于 `main` 的 `a6beb34`）
**本文件为产品交接入口；评估内容与方法以顶部链接的2026-09-07已确认基线为准。** 以下为原交接正文，供工程历史追溯。

---

## 1. 一句话说明发生了什么

这个软件原本是「通用贝叶斯模型工作台」，现在改成 **「以飞行任务场景为核心的评估工具」**。

用户原话：

> 原版软件的很多设计和原则不用太遵守了，按新方案做就行。不要 Project、Session、Model Studio、Runs、Results 这么多条目了。左侧就是不同任务切换，点进每个任务就是固定的 item，里面可以看到每个 item 的检查点，并且可以修改。可以做成一个贝叶斯网络的样子。

---

## 2. 目标形态

```
左侧导航 = 场景列表（且只有场景）
  · SCN-001  加速减速与急停
  · （未来）SCN-002 悬停任务 —— item 与检查点会和 SCN-001 差很多
        ↓ 点进去
场景页 = 该场景的贝叶斯网络，三条泳道
  Task ──▶ Item × 5 ──▶ Checkpoint × 19
        ↓ 点节点
  Checkpoint：依据条款（只读）· 计算规则（只读）· 容差参数（可改）· CPT（可改）
  Item：      条款引用（只读）· 检查点清单（只读）· 门控规则（只读）· CPT（可改）
  Task：      6 个 item · 门控与评分策略
```

**结构锁死、数值放开：**

| 锁死（随软件发布，用户改不了） | 放开（专家在软件里调） |
|---|---|
| 场景有哪些 | 容差数值 |
| 一个场景包含哪些 item | 检测器参数 |
| 一个 item 有哪些检查点 | CPT 数值 |
| 检查点的计算规则 | 状态分值、`score_cap_on_fail` |
| item ↔ 检查点父子关系 | 场景参数表（几何量、任务量） |

场景不可新建、不可复制、不可删除。**加新场景 = 发新软件版本。**

Session 导入 / 运行 / 结果这些能力**不要删**，只是不再作为顶层导航——收进场景页内部。

---

## 3. 原交接文件清单（历史）

研究侧产物在 `C:\Users\long\Desktop\CranfieldOffer\proj\current_stage_scene_based_assessment_2026-08-31\`。下表保留原交接时的用途与地位，当前事实源是顶部链接的共同方法与已确认item，不再以旧原始字段或检查点规则主导设计：

| 文件 | 作用 | 权威性 |
|---|---|---|
| `scenes/SCN-001_accel_decel_quickstop/CHECKPOINT_RULES_CN.md` | **判定规则的事实源** | ⭐ 最高 |
| `scenes/SCN-001_accel_decel_quickstop/SIMULATOR_FIELD_DICTIONARY_CN.md` | 33 列字段语义、已确认/待确认 | ⭐ 最高 |
| `scenes/SCN-001_accel_decel_quickstop/DESIGN_RULINGS_v1.md` | 对你上一版映射设计 17 项提问的裁定 | 高 |
| `scenes/SCN-001_accel_decel_quickstop/item_task_scoring_cpt_v0.2.json` | 31 张已物化 CPT | 高 |
| `EVIDENCE_GRADING_MODEL_CN.md` | 分档模型（`emits` 机制） | 高 |
| `ITEM_TASK_SCORING_CN.md` | 门控与评分、CPT 参数族 | 高 |
| `scenes/SCN-001_accel_decel_quickstop/checkpoints_v0.2.json` | 检查点结构 | ⚠️ **计算描述部分已被 `CHECKPOINT_RULES_CN.md` 取代**，只用它的 ID / `emits` / item 归属 |

本仓库内：`docs/product/DECISIONS.md` 的 **D-092**（含「实施裁定」段）。

**已作废：** `docs/product/specs/2026-09-04-scn001-checkpoint-operator-mapping.md`（你写的那份 657 行映射设计）。用户明确否决了那条路线：

> 你现在设计出来的算子我感觉根本就不好编辑，而且很死

该文件保留作历史记录，**不作为实施依据**。但其中三处发现已被采纳（相位循环定义、记录完整性、`temporal.event-select` 端口 metadata 错误）。

---

## 4. 已完成（不要重做）

| commit | 内容 |
|---|---|
| `fb4e12b` | `signal.sample-at-event` 算子。算子目录 45 → 46 |
| `22d21f1` | 修 D/A/U 词汇 bug：前端 `["desired","adequate","undesired"]` → `unacceptable→adequate→desired` |

工作区还有 `docs/product/DECISIONS.md` 的未提交修改（D-092），那是我写的，**不要动，也不要提交**——由用户决定何时提交。

---

## 5. 设计裁定汇总

### 5.1 结构

1. **Item 不新增 `ComponentKind`。** Item 就是 `BnNodeVersion` + 新增 `BnNodeRole.ITEM`；再加 `BnNodeRole.TASK` 表示场景根节点。`AGGREGATE_COMPETENCY` / `SUB_SKILL` 退役但保留供历史重放。
2. **不新增第三类边。** 门控直接读 `EvidenceBindingVersion.ordered_probabilistic_parent_ids`——检查点的父 item 已记在那里。
3. **item 的条款引用不进软件合同。** 68 项主清单是独立研究数据文件；`BnNodeConcept.concept_id` 用 item ID（如 `A-S2-30`）作外键。软件只校验「场景所选 item ID 存在于主清单中」。
4. **门控与评分策略进 `CoverageReportingPolicyVersion`** 的 `output_rules` / `coverage_rules` / `applicability_rules`——三个自由 JSON 字段已存在，该层零合同改动。
5. **场景 = packaged profile 目录**，沿用 `model_library/profile_data/hover/` 那套 checksum-bound 机制。加载器 `load_model_profile()` 本来就是通用的。
6. **已授权**：`BnNodeRole` 同版本 additive enum widening + 重导出受影响的 10 份 schema，历史冻结 schema 保持字节不变。

### 5.2 判定

7. **分档词汇全系统统一** `DESIRED / ACCEPTABLE / UNACCEPTABLE`，不引入第二套 Pass/Fail 词汇。每个检查点声明自己的 `emits`：三档或二档。二档只产出 `DESIRED` / `UNACCEPTABLE`。
8. **结果只有这三种，没有第四态。** ⚠️ **这是 2026-09-05 的重要修订，取代了早前设计中的 `NOT_EVALUATED` / `NOT_APPLICABLE` / `INCOMPLETE` 机制** —— 详见 §5.7。
9. **Item：** 任一检查点 `UNACCEPTABLE` → Fail；否则 Pass。
10. **Task：** 5 个 item 全 Pass → Pass；任一 Fail → Fail。
11. **分数：** Item 与 Task 各有一个 `[0,1]` 分数，**无论 Pass 还是 Fail 都给出**，由三层 BN 算出，**永不改写门控结论**。

### 5.3 计算方式（这是用户最在意的一条）

**每个检查点都是同一个形状：**

```
实测量  vs  参考量  →  偏差  →  比容差  →  D / A / U
```

**所有会变的东西集中成一张参数表，判定逻辑里不含任何写死的数字。**

- 仿真里把门往后挪 → 系统里改 `s_gate_center` 一个数字
- 要测更高速度的急停 → 改 `V_nom` 一个数字
- 觉得急停该更快 → 改 `t_stop_ideal` 一个数字

**参数一律手工填入，系统不做自动推导、不猜、不补、不随速度自动缩放。** 参数表是仿真场景设计的一份镜像。

⚠️ **不要再走「13 个新增通用算子 + 共享时间线 provider」那条路。** 用户的原话是那样「不好编辑，而且很死」。判定规则本质上是少量标量的算术比较，实现方式应当让「改一个参数」这件事显而易见。具体怎么实现由你判断，但必须满足：

- 场景参数在界面上是**一张可编辑的表**，不是埋在算子图的节点参数里；
- 计算规则在场景页**只读可见**，不是黑盒；
- 改参数不需要改任何结构。

### 5.4 事件求解顺序（原设计是循环定义，已修正）

```
1. t_entry   ← s(t) 首次到达 s_entry
2. t_onset   ← 搜索窗 [t_entry, session_end]，不依赖任何其他事件
3. t_capture ← 搜索窗 [t_entry, t_onset)
4. t_stop    ← 搜索窗 [t_onset, session_end]
相位（半开区间）
   P1 = [t_entry, t_capture)   P2 = [t_capture, t_onset)
   P4 = [t_onset, t_stop)      P5 = [t_stop, t_stop + hold_duration)
```

**`t_onset` 用纵向操纵杆动作判定**（`onset_definition` 默认 `control`）。理由：这个检查点问的是「飞行员什么时候决定刹车」，用减速度判会把航空器响应延迟算进去，而那是构型属性——样例里就有 `Time Delay = 0.2 s`。

### 5.5 两条通用规则

**规则一：场景里只放现在真能算出来的检查点。**

做了什么就用什么。算不出来的（缺通道、规格没定清）**不进场景**，不放空壳节点。以后有了新通道或补齐规格再加 —— 那时是发新版本。一个 item 若一个检查点都做不出来，**该 item 也不进场景**。

**规则二：参数没填齐不许开跑。**

容差为空是**配置没做完**，属于**运行前的拦截条件**，不是运行后的一种结果。绝不允许用 0 或默认值顶替。

同理，「某根轴飞行员没在操纵」是场景设计问题，不是运行时状态：场景不涉及横向机动就别放横向检查点；放了就说明它要评。

### 5.7 ⚠️ 已撤销的机制（对你上一轮设计的重要修订）

上一轮设计里的以下机制**全部撤销**：

| 撤销项 | 原因 |
|---|---|
| `NOT_EVALUATED` 运行时状态 | 把「还没设计的检查点」与「这次数据缺失」混为一谈 |
| `NOT_APPLICABLE` 运行时状态 | 那是场景设计问题，不是运行时状态 |
| `INCOMPLETE` 任务结果 | 25 个检查点里放 9 个空壳，导致每次运行都被拖成 `INCOMPLETE`，既没意义又掩盖真实结果 |
| `recording_scope: full/partial/unknown` 会话事实 | 为区分「没减速」与「文件截断」而引入；场景与导出都由研究者自己控制，不需要这层机制 |
| 「空壳节点、接口完整算法可空」 | 场景只放真能算的检查点 |

用户原话：

> 这个没必要缺失数据就上报了，我们现在是一点一点检查点去设计去做的，我觉得现在就是做了什么就先用什么，后面肯定会再加新的检查点，加的时候再改就行了

**结果状态因此只剩 `DESIRED` / `ACCEPTABLE` / `UNACCEPTABLE` 三种。** 不要再实现第四态。

### 5.6 两条护栏（全手填的代价）

场景参数保存时自检并**告警**（只告警，不自动改）：

1. `标记线到门远边的距离 ≥ V_nom² / (2 × 可接受减速度)` —— 否则物理上停不进门
2. 飞机的**实际航迹方向**（从速度算 `atan2(V_ey, V_ex)`）与走廊方向的夹角，在零风零侧滑下应当很小；长期偏大说明 `psi_nom` 或两个走廊端点填错了

---

## 6. 数据契约

详见 `SIMULATOR_FIELD_DICTIONARY_CN.md`。要点：

- 33 列，100 Hz，从 **Simulink** 导出
- **`Ze` 向下为正**（已确认）；`h_AGL = −Ze − Ground_Elevation`；`Ground Elevation` 是地面海拔，不是飞机高度
- **`psi` 是机头朝向，以世界坐标系为基准**。已知 `psi = 270° ↔ 机头指向 −X`，但**不必推算角度约定** —— `psi_nom` 的填法是「沿走廊正确对准时读到的 psi 值」
- **走廊不必沿坐标轴。** 录入仿真里的两个点（走廊起点、门中心）即可定死原点与方向，`s`/`d` 是一次二维旋转
- **`Pilot Lon`：`0` = 中立，`−100` = 前推到底，`+100` = 后拉到底**
- **机体系速度 ≠ 地面系速度**，是同一矢量的两种表示；`|V_e| ≡ |V_b|` 但 `V_ex ≠ V_bx`
- `V_e*_kts` 只是 `V_e*_m/s` 的单位换算，不是独立测量
- `Control_Mode` 恒为 1，**仿真器尚未实现模式切换**，当前不阻塞
- `Time Delay` / `Lon Frequency` / `Long Damping` 是固定仿真设置，属构型指纹，**不是飞行员能力指标**

### 纵向操纵杆 ✅ 已确认（2026-09-05）

```
−100  ←────────  0  ────────→  +100
前推到底        中立         后拉到底
```

由此：`u_lon_decel_sign = +1`（后拉为减速）；onset 检测**基线固定取 `0`**，不必从数据估计配平值；全行程检查两端为 `−100` 与 `+100`。

**没有硬阻塞了。**

### 样例 CSV 的地位

`data/S_101500_Time_2026_05_14_16_48_54_P_1.csv` **不是加速减速任务的记录**，只是随意飞行导出的数据。只能用于核对字段语义和管线冒烟测试，**不能作为评估样例**。

---

## 7. 红线（来自项目 `CLAUDE.md`）

1. 无条款引用的技能只登记为 `research_hypothesis`，**永不参与门控**。
2. 无可观察行为的技能**不声称可测**。
3. 未经独立验证与校准的模型**不输出资质结论**。当前 31 张 CPT 是 `engineering_default_uncalibrated`，分数只能标为未验证的诊断读数。
4. **生理数据无条款依据**，只能进诊断层。
5. 门控层：**不加权、无总分、无百分比通过线**。
6. 历史 immutable RunSnapshot / result / artifact **不得改变**。
7. `EvidenceUnavailable` **绝不能向上传播成 Pass**。

---

## 8. 建议的任务顺序

### 阶段一：场景包（后端，可测）

1. 加 `BnNodeRole.ITEM` / `TASK`，重导出 10 份 schema，逐字节验证历史冻结 schema 未变
2. 建 `model_library/profile_data/scn001_accel_decel/`：
   - 1 个 Task 节点 + **5 个 Item 节点 + 19 个 Checkpoint 节点** + 19 个 binding + 25 张 CPT
   - ⚠️ CPT 文件 `item_task_scoring_cpt_v0.2.json` 里是按 6 item / 25 checkpoint 生成的 31 张，**请按 v1 范围取子集**：19 张 checkpoint CPT + 5 张 item CPT + 1 张（task→item 用同一参数族）。矩阵数值直接复用，不要重算
   - source descriptors、task profile（装场景参数表）、reporting policy（装门控与评分策略）
   - **写生成脚本**（参考 `profile_data/generate_hover_starter.py`），从研究 JSON 生成，不手写死
3. 场景注册表：加载器从写死 `"hover"` 改为枚举全部场景包；`SystemDescriptor` 承载多个种子
4. 实现门控 reducer + 分数计算，结果走现有 `RunResultEnvelope.reporting_refs` 槽位

### 阶段二：外壳（WinUI）

5. `MainWindow.xaml` NavigationView：移除 Project/Sessions/Model Studio/Runs/Results 五个顶层条目，改为场景列表
6. `TaskSchemeSidebar` 的新建/复制/重命名/归档去掉
7. 场景页复用 `ModelGraphControl`；`GraphProjection` 的分层从 `ExtractedData/Evidence/SubSkill/Competency` 改成 `Checkpoint → Item → Task`（注意 `LayerOf` 对未知 kind 会抛异常）
8. **场景参数表编辑界面**——这是用户最在意的交互，务必做得直观
9. Item 节点复用 `BnNodeEditor`，加条款引用与检查点清单的只读区
10. 结构编辑操作对场景包节点一律禁用，只放开参数与 CPT

### 阶段三：跑通

11. 冒烟测试。⚠️ **样例 CSV 不是加速减速任务的记录**（随意飞行导出），它没有走廊、没有门、没有减速段，**不能用来验证评估结果**，只能验证"数据读得进、字段解析对"。

    真正的端到端验证要等仿真环境里按 `CHECKPOINT_RULES_CN.md` §1 的参数表布置好场景、录一次真实任务之后。在那之前：
    - **不要为了让管线跑通而编造输入**
    - 参数没填齐时管线应当**在运行前拦截**并说明缺哪些参数（规则二）

---

## 9. 未决项

| # | 未决 | 谁来定 |
|---|---|---|
| 1 | ~~纵向杆量程/单位/方向~~ | ✅ 已确认，见 §6 |
| 2 | ~~航向零点约定~~ | ✅ 已绕开：`psi_nom` 改为「沿走廊对准时读到的 psi 值」，直接填数，不需要知道角度约定 |
| 3 | `CP-S2-02-04 漂移修正及时性` 规格不完整，**本轮不进场景** | 我（Claude）后补，补齐后作为新版本加入 |
| 4 | `A-S1-06 起飞前检查与功率检查` 三个检查点全部缺通道，**本轮整个 item 不进场景** | 等检查单事件通道与功率通道；**这是可反悔的决定**，若用户希望它先占位可改回来 |
| 5 | `ax/ay/az` 坐标系与是否含重力 | 仅 `onset_definition=response` 时需要，低优先 |
| 6 | 68 项主清单文件尚未生成（`assessment_item_catalog_v1.json`） | 我（Claude）后补 |

---

## 10. 工作方式

- 在 `feat/scene-based-assessment` 分支，分次 commit
- commit message 末尾加 `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`
- 不要动 `docs/product/DECISIONS.md`
- 每个阶段完成后报告：改了哪些文件、测试结果（具体数字）、**以及你认为哪条裁定在技术上有问题**
- 遇到必须修改已发布合同才能推进的情况，**停下来报告**，不要硬改
- 给用户的报告里请说清楚「现在软件里能看到什么」——用户不深入技术细节

**上一轮你两次拒绝在含糊规格上硬写代码、先提问再动手，那是对的，请继续这样做。**
