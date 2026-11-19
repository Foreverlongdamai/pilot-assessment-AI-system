# 六 item 贝叶斯量化实施计划

依据[已授权规格](../specs/2026-09-07-six-item-bayesian-eap.md)，在现有模块内增量实现，保留现有未提交工作与DECISIONS。

- [x] Python：先增加有意义的分数/门控/回归测试，再实现skill_quantification.py与目录模板、配置校验和calculator输出。仅后端agent编辑Python及其tests。
- [x] Desktop.Core：增加JSON DTO与source-generation注册；先写编辑会话和兼容性测试，扩展SceneItemEdit/Workspace原子提交及快照比较。Root独占这些文件。
- [x] WinUI：item弹窗新增模型字段，候选校验包含skill_models；结果显示EAP和分布。UI agent只改Desktop项目的编辑器/窗口。
- [x] Root完善真实Python→C#合同测试，运行Python与.NET适当测试、格式检查和WinUI构建。
- [x] 复核6项解释/二态观察/共享证据边界，更新使用指南与当前阶段入口，记录实际验证范围。

采用原有Python环境和.NET SDK，不新增依赖。默认演示模型与评分锚点明确为研究设置，真实阈值仍由用户填写。

完成结果及交互验证范围见[验证记录](../reviews/2026-09-07-six-item-bayesian-eap-verification.md)。
