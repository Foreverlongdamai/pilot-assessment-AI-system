# 正常进近至悬停：两检查点软件验证

日期：2026-09-15。合同：[三维航迹与到点状态](../plans/2026-09-15-approach-route-corridor.md)。

## 当前实现

- A-S2-23 只保留 -01 进近航迹控制与 -03 到点建立悬停；原 -02 的时间剖面检查和 CPT 移出当前目录。
- 原始 `approach_position_m` 包含 x_m、y_m、height_m；配置为手工 route_points 折线路线和 D/A 空间通道半径。高度已包含在空间距离中。
- 编辑器支持增删路线点、完整应用和未完成草稿；报告展示实际 XYZ、最近路线点、线段编号、空间距离及精确时刻分档。显示形式是位置／距离时序图，不是交互三维视图。
- SCN-001 4 item／14 检查点／26 指标键；SCN-002 3／6／13；总图实际核对为 29 节点。
- 空白模板、合成示例、使用指南及阶段交接已同步；旧进近指标或 CPT 文件不静默迁移。

## 验证结果

| 检查 | 结果 |
|---|---|
| Python 场景测试 `pytest tests/scene_assessment -q` | 342 通过，含 56 个路线用例 |
| Desktop.UnitTests | 229 通过，含 20 个路线用例 |
| Desktop.ContractTests，筛选 Scene | 4 通过，含两个 v3 场景的真实 stdio 后端 |
| SceneTimelineDrawingChecks | 7/7 通过 |
| WinUI 构建至 scene-studio 输出目录 | 成功，0 警告、0 错误 |
| 原桌面快捷方式、真实编辑／导入／评估／导出 | 通过，下列记录可回查 |

几何用例覆盖有限线段端点、拐弯、倾斜／垂直路线、高度偏离、等距取首段、D/A 边界、缺失与未知字段、重复点及恢复后保留 U。独立审查发现的零半径精确共线误判和极端有限数值异常已修正并加入回归；没有向用户的分档范围添加数值容差。

桌面合同检查空路线／未填坐标草稿和事务性编辑，拒绝不适用于该指标的字段，即使字段值为 null 也不静默丢弃。未填几何仍不能产生完整 Pass。

## 原快捷方式与界面证据

原快捷方式 `C:/Users/long/Desktop/PilotAssessment.Desktop.exe - 快捷方式.lnk` 的目标已回读确认：

`src/PilotAssessment.Desktop/bin/x64/Debug/scene-studio/PilotAssessment.Desktop.exe`，无附加参数。

通过该快捷方式实际启动新版，完成：

1. 总图 29 个真实节点，含进近航迹控制及到点建立悬停，没有“稳定进近与减速”。
2. 初始化两个路线点、添加再删除第三点，填写首点 X=12.5，其余留空；保留草稿并保存 JSON，确认空值未被补齐。
3. 加载工程示例的三点路线，回读 UI 坐标与 D/A 半径，完整应用通过；进近报告为 62 个路线帧，整个进近 item 93 帧。
4. 两场景分别导入合成数据、运行评估、导出报告。SCN-001 进近为 D/Pass，空中滑行的合成失误使任务 U/Fail；SCN-002 保留合成失误的 U/Fail。
5. 桌面导出报告中的配置、原始输入与工程文件逐项相同；路线全部 62 帧的精确时刻、XYZ、最近点、线段号、距离及档位与当前 Python 输出一致。
6. 桌面导出的空白输入与当前目录模板一致。

最终又做了一次仅针对路线编辑器的布局精简：重复说明收进默认折叠的“路线填写说明”，让路线坐标输入优先显示。最终 WinUI 重建成功（13.12 秒，0 警告／0 错误）；由原快捷方式于 13:05:07（Europe/London）启动的新进程 PID 28936 打开新编辑器，已目视检查两个空白路线点及 D/A 半径布局。计算规则和文件合同没有随这次布局调整改变。当前打开的是空白配置编辑器，没有把工程示例数值作为默认值留下。

证据位于 `tmp/scene_v3_qa/`：`route-global-ui.json`、`route-editor-ui.json`、`route-partial-draft.json`、`route-scn001-ui-report.json`、`route-scn002-ui-report.json`、`route-ui-input-template.json`、`route-final-editor-ui.json`、`route-final-editor.png`。可运行 `verify_route_exports.py` 回查。UI 操作启动时曾在工作区初始化完成前找不到按钮，等待页面就绪后重试通过；这不计为完成验证的结果。

## 保留边界

路线和半径属于项目适配，不是 FAA/EASA 的统一阈值。当前只检验空间通道与到点状态，不能单凭这些指标证明全过程稳定进近、完整资格考试或训练有效性。贝叶斯量化仍待定；没有新增未标定概率或分数。

未修改 PPT、环境或保护文件。本轮前后 `docs/product/DECISIONS.md` SHA256 均为 `70F8808EEE46E0BAEA6832958C8841A8F0EF09E6249891992D6D2310ED6C10FE`；原有 Git 工作区改动保留，未提交。
