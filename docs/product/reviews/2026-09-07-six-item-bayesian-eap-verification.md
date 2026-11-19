# 六item贝叶斯/EAP开发版验证记录

日期：2026-09-07。范围：六项本次静态BN、EAP、模型配置、编辑器及报告。没有使用真实学员或样例飞行数据；本记录证明所列软件行为，不证明测量有效性或概率已校准。

## 自动验证

| 检查 | 当前结果 |
|---|---|
| `.venv/Scripts/python.exe -m pytest tests/scene_assessment tests/sidecar/test_framing.py tests/sidecar/test_dispatcher.py -q` | 123 passed |
| `dotnet test tests/PilotAssessment.Desktop.UnitTests/PilotAssessment.Desktop.UnitTests.csproj -c Debug --nologo` | 136 passed，0 failed，0 skipped |
| `dotnet test tests/PilotAssessment.Desktop.ContractTests/PilotAssessment.Desktop.ContractTests.csproj -c Debug -p:Platform=x64 --nologo` | 5 passed，0 failed，0 skipped |
| `dotnet build src/PilotAssessment.Desktop/PilotAssessment.Desktop.csproj -c Debug -p:Platform=x64 --nologo` | 成功，0警告，0错误；SDK 10.0.302 |
| Ruff check及format --check：新scene包和测试 | 通过；10文件格式一致 |
| `git diff --check` | 通过；已有DECISIONS换行提示，未改其内容 |

共264项测试。Desktop.Core新增测试先因缺少SceneSkillModel编译失败，实现后9项新增行为测试全部通过；真实RPC新增断言先因目录未返回模型失败，后端完成后整套合同测试通过。

验证内容包括：6模型／19观察字母表；先验与CPT严格校验；全D、全U、三态后验与EAP；零概率和极小似然；未执行／未知／非法动作；急停已开始但未停住仍保留U；缺配套来源结果时score=null；两个末端item不复制额外时长证据；旧配置无模型兼容；输入JSON仍拒绝模型字段；配置和报告深复制；取消／原子应用／旧报告失效。

真实Python进程经SceneGateway返回六项完整模型和量化DTO；合同测试验证默认标尺下地面起飞：

- D/D/D：96.974248927分，D／Pass。
- D/D/A：86.995515695分，A／Pass。
- D/D/U：77.766990291分，U／Fail。
- 概率和非法：invalid_model、score=null，原D／Pass保持。
- 配置移除skill_models：六项not_configured、score=null，原D／Pass保持。

上述数字只检查演示模型的算术，不是官方评分或实测飞行结果。

## 实际窗口检查及范围

启动此次Debug x64构建，真实主窗口连接Python后显示“场景已就绪”和六项卡片；打开急停item、展开“贝叶斯技能量化”，观察到量化对象、未校准说明、三项先验和状态分值，以及三个D/A/U检查点表和一个D/U禁止事件表。取消后返回主窗口，没有产生未保存修改标记。

本轮没有完成文件选择器导入／导出及新分数的实际窗口端到端操作；JSON保存／往返及六项计算由真实协议和Workspace测试覆盖。自动化工具的set_value返回UIA CacheRequest错误；系统文件选择器由PickerHost承载，未提供可单独选取的窗口，目标校验拒绝点击。已取消文件选择，未将此工具限制记作软件通过或软件缺陷。未因该限制增加旁路导入接口。

人工验证数据保留在[算术验证目录](assets/six-item-bayesian-2026-09-07/README.md)，供后续交互复核；不是产品默认容差或用户训练数据。

## 交付与边界

本地开发版已实现Python计算、C#合同／状态管理、WinUI模型编辑和结果展示，启动方式见[使用指南](../SCENE_CALCULATOR_GUIDE_CN.md)。概率与状态分值可编辑且未校准；原D/A/U及P/F独立，缺数据不补分，未新增学习历史或场景总分。

`DECISIONS.md` SHA-256维持`70F8808EEE46E0BAEA6832958C8841A8F0EF09E6249891992D6D2310ED6C10FE`。保留原有未提交修改、旧工作台、数据库与历史结果；没有提交、推送或重新打包发布。
