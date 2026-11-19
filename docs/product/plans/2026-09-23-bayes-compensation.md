# 2026-09-23 已确认：CPT 贝叶斯更新后补偿

用户明确选择“按此顺序：CPT 贝叶斯更新后再补偿”，并要求实际修改软件。分数只是最终概率的显示映射。本实施合同替代根目录补偿研究报告中无 CPT 的候选递推；不实施其他候选模型。

## 计算合同

新增 method `sequential_bayes_compensation_v1`，内部数组沿用低/中/高，观测 D/A/U 分别映射高/中/低。每个有效帧：

1. 先验为上帧补偿后的 p，首次为配置 prior。
2. 单检查点似然为该观测对应 CPT 列；item 同帧合并所有适用检查点的似然（条件独立假设），不乘检查点后验。
3. `q = normalize(p * likelihood)`。
4. `p_new = (1-alpha)*q + alpha*target`。
5. 检查点 target 为其当前 D/A/U 的 onehot；item target 为系统已有本帧 item 等级的 onehot（适用检查点取最差档）。item 同帧只补偿一次，不依赖检查点遍历顺序。
6. `score = sum(p_new * state_scores)`。state_scores 不参与概率更新，D/A/U/PF 规则不受分数控制。

配置新增 `compensation: {"alpha": 0.2}`，alpha 为每个有效帧的固定比例，允许[0,1]；0退化为无补偿Bayes。0.2仅为可编辑、未标定的演示设置。本轮按逐帧完整 CPT 更新，不宣称采样率无关；时间戳保留精确时刻，不自动补持续时间。旧相关时间tau不属于新方法。

trace 点新增 `prior`、`bayes_posterior`、`compensation_target`、`compensation_alpha`、`compensation_delta`；`posterior`为补偿后。log BF 保留原CPT证据含义，不含补偿。本轮整体是“贝叶斯更新＋工程补偿”，补偿后概率不冒称纯贝叶斯后验。

## 同源输出与边界

- 新算法仅计算一条序贯过程，主结果的后验/分数、累计过程和temporal item曲线的有效末点一致；不再同时运行κ=3来给新算法主分。
- 最后一个状态表示截至末帧、含补偿的模型判断，依赖顺序，不标成顺序无关的整段平均质量。
- 阶段变化不重置 prior；不适用不加证据；缺测/不完整继续执行既有严格状态，不伪造概率。
- 用户后续要求删除旧方法：生产内核只保留本方法。已知旧 v3 配置加载时自动转换，保留先验/CPT/分值并补缺省 α=.2；新版 α 不覆盖，未知方法拒绝。不保留旧推断或手动切换入口。历史文件保留但须重新评估。
- 两场景全部飞行item及检查点覆盖；起飞前checklist只判完成性。
- 不额外改CPT以保证曲线平滑。任意可编辑CPT不保证每个A都将期望分数拉向50；只验证声明公式与当前参数的一致性。

## 实施分工及验证

Python：新统一内核、method/compensation校验、v3路由、空模板及测试。C#：严格DTO、校验、clone/dirty、编辑器、Model Studio、报告图和明细、真实跨端合同。根任务：新演示包、独立oracle、文档、最后构建快捷方式真实目标。

验收：CPT手算、alpha0/1、双向极端恢复、项先验仅一次、CP顺序无关、概率/分数解耦、缺测/phase、最终分与过程末点一致；运行Python scene套件、C# UnitTests、六场景真实RPC合同、构建原exe路径。新演示以原六组输入和原CPT为基准，不优化数据以迎合分数。

软件目标：`src/PilotAssessment.Desktop/bin/x64/Debug/scene-studio/PilotAssessment.Desktop.exe`。无需触碰旧rc.4便携版；开发sidecar从本仓库Python源码启动。
