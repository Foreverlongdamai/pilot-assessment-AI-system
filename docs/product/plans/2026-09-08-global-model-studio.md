# 全局Model Studio实施计划

目标：在现有WinUI增加共享场景配置的可视化总画布。依据[已授权布局与接口](../specs/2026-09-08-global-model-studio.md)。复用.NET10与既有Python环境，不安装依赖、不改变研究模型。

- [x] 后端：增加目录注册及scene.list/按ID加载；先测旧入口、未知ID及多目录发现，再实现。
- [x] Core：增加列表DTO/gateway、多场景文档状态、纯图投影；先测命名空间、边语义、状态保持和缺报告。
- [x] Canvas：原生WinUI三列图、箭头/虚线图例、缩放滚动、节点事件；独立于保存与推断。
- [x] 主窗口：左侧Model Studio+动态场景菜单；右侧节点检查器与CPT编辑；共享配置、每场景保存状态和关闭处理。
- [x] 联调：真实RPC目录合同，Python回归、.NET单元/合同、Debug x64构建；实际窗口观察/编辑检查，记录范围。
- [x] 文档：说明三个输入输出按钮，更新使用指南、交接和当前阶段入口。

完成情况及验证边界见[验证记录](../reviews/2026-09-08-global-model-studio-verification.md)。最终使用独立 scene-studio 输出目录构建，启动脚本已同步。

测试命令沿用pytest tests/scene_assessment与sidecar framing/dispatcher、两个Desktop测试项目；WinUI构建dotnet build src/PilotAssessment.Desktop/PilotAssessment.Desktop.csproj -c Debug -p:Platform=x64。独立Python检查可并行，.NET构建串行避免输出目录占用。
