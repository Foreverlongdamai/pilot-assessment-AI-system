from pathlib import Path

root = Path(__file__).resolve().parents[1]
guide = root / 'docs/product/SCENE_CALCULATOR_GUIDE_CN.md'
text = guide.read_text(encoding='utf-8')
replacements = {
    '| SCN-001 加速减速任务 | 起飞前检查、起点就位、空中滑行（加速与保速）、快速减速／急停 | 15 |': '| SCN-001 加速减速任务 | 起飞前检查、正常进近至悬停、空中滑行（加速与保速）、快速减速／急停 | 16 |',
    '| SCN-002 双高度悬停任务 | 起点就位、悬停高度保持、悬停定点保持、垂直升降控制 | 9 |': '| SCN-002 双高度悬停任务 | 悬停高度保持、悬停定点保持、垂直升降控制 | 6 |',
    '2 个 Task、8 个 item、24 个检查点，共 34 个节点': '2 个 Task、7 个 item、22 个检查点，共 31 个节点',
    '七个飞行 item': '六个飞行 item',
    '两个场景各自的“起点就位”拥有独立配置和结果。': 'SCN-002 到达下方初始点是训练前置流程，不单独计分。',
    '不切分完整日志，不排序、插值或补帧。起点状态、检查单和明确的停止状态使用单帧；': '不切分完整日志，不排序、插值或补充观测帧。起飞前检查单、保速结束和明确停止状态使用单帧；',
    '当前界面不静默转换版本或跨场景导入。': '当前界面不静默转换版本或跨场景导入。仍含 SCENE-START 的旧 v3 输入或配置不兼容本轮目录，必须按新模板明确整理；系统不会偷偷删除或迁移旧记录。',
}
for old, new in replacements.items():
    assert old in text, old
    text = text.replace(old, new)
section = '''## 正常进近至悬停

SCN-001 的起点环节现在按“已经起飞，从别处进近起点、减速并建立悬停”定义，项目 ID 为 SCENE-APPROACH-HOVER，参考 FAA-S-ACS-2 CP.V.D。它包含四个检查点：进近航迹保持、稳定进近与减速、到点建立悬停、机型程序执行。起飞过程本身不在当前评分中。

进近航迹使用约定直线进近坐标系中的横向位置，不以航向代替航迹。进近空速、高度、垂直速度采用可编辑的参考剖面；到点后才使用固定的 X/Y/高度、零地速和指定航向。输入与配置必须使用相同单位、坐标和高度基准，垂直速度向上为正。

在 item 编辑器中，为每个进近环节添加“环节开始后秒数／期望值”节点。每组至少两个节点，第一个时刻为 0，后续时刻严格递增。系统以该 item 该环节首帧为时间零点，对参考节点做明确的分段线性插值，得到每帧目标值；只对参考值插值，不对实际飞行帧插值。超过参考曲线覆盖范围标为缺失，不能通过，不向外延伸目标。重新截掉开头帧会改变时间零点，所以输入须包含约定环节起始帧。

对应 JSON 参数为 `expected:null`、原有 `desired/acceptable`，以及 `reference_profiles:{phase_id:[{elapsed_s:0,expected:数值}, ...]}`。空模板中的曲线为空。参考剖面由机型程序和场景设计确定；若时间剖面不适合后续机型，应先明确新的参考方法再实现，不能声称当前时间剖面是 FAA 的规定。

到点的程序检查接收上游已认定的本次进近检查单完成、程序及构型正确两个布尔结果。缺少机型判断依据不能默认 true。到点每帧提供截至该时刻的结果，软件不自行检测执行动作。

SCN-001 顺序为 preflight → approach → approach_deceleration → arrival_hover → acceleration → hold → hold_end → deceleration → stop。新进近 item 的三个环节各至少两帧，单个到点截图不再足以通过。两帧只是最低数据要求，不证明采样密度、帧间连续稳定或官方规定时长。

官方依据支持检查内容。复飞决策、选点、通信、SRM/CRM 等尚未完整覆盖；本 item 不能被称为完整 FAA 资格考试。CP.V.D.S7 的 ±2 feet 不直接复制为三轴各自容差，D/A 数值及严格最差帧汇总是项目规则。详见[条款映射与修订合同](plans/2026-09-15-approach-hover-refinement.md)。

'''
text = text.replace('## 文件与操作\n', section + '## 文件与操作\n')
guide.write_text(text, encoding='utf-8')

entry = '''**2026-09-15 起点 item 修订：** 用户确认 SCN-001 在起飞后从别处进近起点、减速并建立悬停。因此用“正常进近至悬停”（SCENE-APPROACH-HOVER，参照 FAA-S-ACS-2 CP.V.D）替代单帧起点就位；四个检查点涵盖航迹、稳定进近与减速、到点悬停、程序执行。进近数值使用手工参考剖面，到点环节采用固定位置/速度/航向目标。SCN-002 删除起点就位，保留悬停高度、悬停定点、垂直升降三个 item，本轮不合并高度与定点。两场景分别 4/16/31 与 3/6/13（item/检查点/输入量）；总画布 31 节点。新目录不能读取含旧 SCENE-START 的输入/配置，不自动迁移。阈值、参考剖面、CPT 均无权威通用默认值，贝叶斯计算方法仍待定。以下旧计数及起点定义是历史状态。\n\n'''
for relative, link in [
    ('docs/product/HANDOFF_SCENE_BASED_REBUILD_CN.md', 'plans/2026-09-15-approach-hover-refinement.md'),
    ('../current_stage_scene_based_assessment_2026-08-31/README.md', '../pilot_assessment_system/docs/product/plans/2026-09-15-approach-hover-refinement.md'),
    ('../current_stage_scene_based_assessment_2026-08-31/scenes/SCN-002_hover_vertical/README.md', '../../../pilot_assessment_system/docs/product/plans/2026-09-15-approach-hover-refinement.md'),
    ('../current_stage_scene_based_assessment_2026-08-31/scenes/SCN-002_hover_vertical/DESIGN_DRAFT_2026-09-14_CN.md', '../../../pilot_assessment_system/docs/product/plans/2026-09-15-approach-hover-refinement.md'),
]:
    path = root / relative
    text = path.read_text(encoding='utf-8')
    title, remainder = text.split('\n', 1)
    path.write_text(title + '\n\n' + entry + f'当前修订：[数据与条款合同]({link})。\n' + remainder, encoding='utf-8')

for scene in ('SCN-001', 'SCN-002'):
    path = root / 'examples/scenes' / scene / 'v3/README.md'
    text = path.read_text(encoding='utf-8')
    if scene == 'SCN-001':
        text = text.replace('preflight 检查单、start 起点；', 'preflight 检查单；approach 进近、approach_deceleration 进近减速、arrival_hover 到点建立悬停；')
        text += '\n进近 item 已替换旧 SCENE-START。进近空速/高度/垂直速度使用 reference_profiles，每环节至少两个时间—期望值节点，时间从本环节首帧计；只插值参考曲线，不插值飞行数据或外推。三个进近环节各至少两帧。示例剖面与容差全部为合成算术参数，不声称物理轨迹完整一致或机型标准。\n'
    else:
        text = text.replace('阶段：start 起点；', '到达下方初始点为前置流程，不单独评分。阶段：')
        text += '\n本轮已删除 SCENE-START，当前三个 item 共六个检查点。旧输入与配置需按照本目录新模板重新整理，软件不自动丢弃旧数据。\n'
    path.write_text(text, encoding='utf-8')
