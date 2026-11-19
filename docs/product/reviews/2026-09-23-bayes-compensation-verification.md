# 2026-09-23 CPT 贝叶斯＋双向补偿：实施与验证

> 本文记录第一轮“新法接入、旧法兼容”的完成状态。用户随后要求删除旧方法，已完成的最新代码与构建状态见[统一新版清理记录](2026-09-23-single-method-cleanup.md)；下文的手动转换、旧方法重放和先前构建指纹不再代表当前版本。

用户确认每帧“先用上一帧概率与 CPT 算贝叶斯后验，再补偿”，本轮已经修改 Python 计算器、桌面参数编辑、Model Studio、报告及配置读写，并重建原桌面快捷方式对应的程序。

## 实现范围

方法 ID 为 `sequential_bayes_compensation_v1`。两场景共 5 个飞行 item、14 个飞行检查点使用统一递推；起飞前检查保持检查单完成性。原规则、D/A/U 容差、原始值图和 P/F 不因概率分数改变。

配置 `compensation.alpha` 默认为演示值 0.2，允许 0–1；缺省初始先验和 CPT 仍是待填写草稿。旧配置仍可按原方法重放；编辑器提供显式转换，保留原 CPT、先验和状态分值，删除新方法不使用的旧 τ 配置。新方法不使用 κ=3；累计输出、过程输出及最后结果来自同一条链。

每帧按内部低／中／高顺序执行：

```
likelihood[s] = CPT[s, observed_grade]                  # 单检查点
likelihood_item[s] = product(CPT_j[s, observed_grade_j]) # 同帧适用检查点
q = normalize(prior * likelihood)
p = (1 - alpha) * q + alpha * target
score = sum(p * state_scores)
next_prior = p
```

item 同帧只使用一次先验和一次补偿，target 是既有本帧最差检查点等级，不能将各检查点后验再次相乘。报告新增 `prior`、`bayes_posterior`、`compensation_target`、`compensation_alpha`、`compensation_delta`；后者是三维向量 `p−q`。固定 α 下，补偿量随 `target−q` 的反差变化。

## 验证结果

| 检查 | 本轮结果 |
|---|---|
| Python scene_assessment 全集 | 534 通过，包括新算法 29 项 |
| C# Desktop UnitTests 全集 | 321 通过 |
| C# Scene ContractTests | 16 通过，包括六个新配置＋真实 Python RPC 的完整往返 |
| SceneTimelineDrawingChecks | 7 项时间轴选择＋11 项原始观测绘图通过 |
| 独立 Decimal 80 位公式复算 | 9,180 个有效过程点；176,163 个数值对照；最大绝对差 2.84217e-14 |
| 独立验证断言 | 238,494 项通过；七种审计字段篡改均能检出 |
| 原六输入、规则层、先验与 CPT | 输入实际 SHA256 相同；完整规则输出、P/F 与参数保持 |
| 最终桌面构建 | x64 Debug scene-studio，0 警告、0 错误 |

新单元测试覆盖 CPT 手算、α=0/1、零先验恢复、极端状态反向修正、item 先验只计一次、同帧检查点顺序无关、分值不影响概率、阶段保留状态、缺测阻断和过程末点一致。独立验证脚本不导入生产推断函数。

新六例包位于 `examples/bayes-compensation-2026-09-23`。同一场景三份输入共用一份配置；旧六例输入原样复制，没有为新分数修改信号。完整输出、参数与 SHA 清单在新包；独立审计明细在 `tmp/compensation_qa/independent-verification.json`。

本地网页 `http://127.0.0.1:8767/index.html` 为新报告的只读展示，直接渲染报告，不另算概率。已在实际浏览器检查两个场景切换、检查点选择、真实末帧滑块及概率明细，检查三概率和分数过程图及色带；未见脚本错误。网页服务器仅监听 127.0.0.1。原 8766 页面未替换。

原生桌面界面采用编译、绘图、单元及真实跨端合同验证；本轮没有完成原生窗口逐项鼠标点选验收，不将网页检查等同于原生 UI 验收。

## 实算示例与解释边界

以下用原演示 CPT、α=0.2，初始概率按 **D／A／U** 展示；每列均从同一初始状态独立观察一次，并非连续三次观察：

| 初始 D／A／U | 初始分数 | 一次 D 后 | 一次 A 后 | 一次 U 后 |
|---|---:|---:|---:|---:|
| .90／.05／.05 | 92.5 | 98.678679 | 73.020285 | 3.255814 |
| .05／.90／.05 | 50.0 | 64.383562 | 49.483275 | 14.322453 |
| .05／.05／.90 | 7.5 | 48.196721 | 16.333907 | .075079 |

这验证了当前参数下既能上调也能下调；不是现实飞行能力的标定结果。CPT 本身会造成较强跳变，本轮未改 CPT 来人为平滑曲线。完整贝叶斯步与补偿步的合成行为不等同于此前纯线性补偿候选的全部数学性质。

尤其需要保留以下含义：

- 最后结果是**末帧模型状态**，不是顺序无关的整段平均。新六例中，不合格案例的五个飞行 item 在末段恢复 D 后，末分均可接近100；历史 U 与整项 Fail 仍完整保留。界面已明确末帧标签。
- 连续相同证据仍可使概率趋近某一状态；正 α 让新观测的目标状态重新获得概率，不承诺三个概率永远不接近 0 或 1。
- A 不保证将分数严格拉向50；多个检查点同时参与时，item 的最差等级补偿与其它 CPT 证据共同作用，不保证含 U 的每帧分数必降。
- α 与 CPT 按有效帧更新，响应受采样率影响；本轮没有自动跨训练学员状态保存。模型参数尚未用真实数据标定。

## 构建位置与复核命令

桌面快捷方式仍指向：

`C:\Users\long\Desktop\CranfieldOffer\proj\pilot_assessment_system\src\PilotAssessment.Desktop\bin\x64\Debug\scene-studio\PilotAssessment.Desktop.exe`

2026-09-23 12:01（Europe/London）最终构建，程序 DLL SHA256：`92A3DB4EF3616DFFEDC7246D012625927F60ECC088E6A9542431A5F3DBF76B69`；Core DLL SHA256：`B297700C81826D8E6ED7F405D7CC699A7261B6E2C4FC2F33011EA49A1C4CCC1D`。开发 sidecar 从本仓库 Python 源码运行，未修改旧 RC.4 便携发行目录。

在 `pilot_assessment_system` 中可复核：

```powershell
& .\.venv\Scripts\python.exe -X utf8 -m pytest tests/scene_assessment -q
& .\.venv\Scripts\python.exe -X utf8 tools/Verify-BayesCompensationDemo.py
dotnet test tests/PilotAssessment.Desktop.UnitTests --nologo
dotnet test tests/PilotAssessment.Desktop.ContractTests --filter 'FullyQualifiedName~Scene' --nologo
dotnet run --project tests/SceneTimelineDrawingChecks --no-restore
```

新包手工使用方法见 [README](../../../examples/bayes-compensation-2026-09-23/README_CN.md)，公式合同见[实施计划](../plans/2026-09-23-bayes-compensation.md)。
