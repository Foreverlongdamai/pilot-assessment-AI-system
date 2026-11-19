import json
from pathlib import Path

root = Path(__file__).resolve().parents[1] / 'src/pilot_assessment/scene_assessment'
path = root / 'scn001_v3.json'
catalog = json.loads(path.read_text(encoding='utf-8'))
old = next(item for item in catalog['items'] if item['item_id'] == 'SCENE-START')
old_keys = {key for cp in old['checkpoints'] for key in cp['metric_ids']}
process = ['approach', 'approach_deceleration']
arrival = ['arrival_hover']

def metric(key, name, unit, description, phases, comparison='linear', **extra):
    return dict(metric_id=key, name=name, description=description, unit=unit,
                value_type='number', rule='interval', parameter_kind='signed',
                input_kind='frame', comparison=comparison, shared=False,
                phase_ids=phases, **extra)

new_metrics = [
    metric('approach_lateral_position_m', '进近横向位置', 'm',
           '约定直线进近坐标系中的实际横向坐标；与手工指定中心线位置比较。必须先约定坐标系、正方向及中心线，不根据数据拟合航线，也不把航向代替航迹。', process),
    metric('approach_airspeed_mps', '进近空速', 'm/s',
           '实际空速与该环节手工配置的空速参考剖面比较；不以终端零地速要求进近空速。', process, target_mode='phase_profile'),
    metric('approach_height_m', '进近高度', 'm',
           '实际高度与机型及场景定义的高度剖面比较；输入与参考须采用相同高度基准。', process, target_mode='phase_profile'),
    metric('approach_vertical_speed_mps', '进近垂直速度', 'm/s',
           '实际垂直速度（向上为正）与手工配置的参考剖面比较。不能单独证明全机型稳定进近条件。', process, target_mode='phase_profile'),
    metric('arrival_x_m', '到点悬停 X 位置', 'm', '到点悬停环节每帧实际 X 坐标；目标为指定悬停点的同坐标系 X。', arrival),
    metric('arrival_y_m', '到点悬停 Y 位置', 'm', '到点悬停环节每帧实际 Y 坐标；目标为指定悬停点的同坐标系 Y。', arrival),
    metric('arrival_height_m', '到点悬停高度', 'm', '实际高度与悬停点同基准的目标高度比较。', arrival),
    metric('arrival_vx_mps', '到点悬停 X 地速', 'm/s', '与位置同坐标系的实际 X 地速，目标为停住时的零地速。', arrival, default_expected=0),
    metric('arrival_vy_mps', '到点悬停 Y 地速', 'm/s', '与位置同坐标系的实际 Y 地速，目标为停住时的零地速。', arrival, default_expected=0),
    metric('arrival_vz_mps', '到点悬停垂直地速', 'm/s', '实际垂直地速（向上为正），目标为零；不使用操纵杆 Heave 输入替代。', arrival, default_expected=0),
    metric('arrival_heading_deg', '到点悬停航向', 'deg', '到点悬停环节实际机头航向，与指定航向比较最短角差；不要求进近时机头始终同向。', arrival, comparison='angle_degrees'),
]
for key, name, desc in [
    ('approach_checklist_completed', '进近检查单完成', '上游明确给出的本次进近适用检查单完成结果：true 已完成，false 未完成，缺少结果不可通过。此处不识别检查动作。'),
    ('approach_procedure_configuration_correct', '进近程序与构型正确', '上游按已定义机型规则认定本次进近程序及构型是否正确；不由几何轨迹或操纵轴自动推断。未配置机型判据时不得默认 true。'),
]:
    new_metrics.append(dict(metric_id=key, name=name, description=desc, unit='',
                            value_type='boolean', rule='must_be_true', parameter_kind='boolean',
                            input_kind='frame', comparison='boolean', shared=False, phase_ids=arrival))

def source(clause, note, page='印刷25–27页／PDF30–32'):
    return dict(document='FAA-S-ACS-2', clause=clause, page=page,
                url='https://www.faa.gov/training_testing/testing/acs/commercial_pl_acs_2.pdf#page=30',
                support='官方内容依据／项目适配', note=note)

def cp(number, name, desc, keys, sources):
    return dict(checkpoint_id=f'SCENE-APPROACH-HOVER-{number:02d}', name=name,
                description=desc, metric_ids=keys, sources=sources, fail_when=[])

item = dict(
    item_id='SCENE-APPROACH-HOVER', name='正常进近至悬停',
    description='已起飞后，从别处沿约定直线进近指定起点，减速并建立悬停。参考 FAA CP.V.D 的操纵内容；环节由输入给出，不自动截取。复飞决策、通信、SRM/CRM及选点等未完整覆盖，不等同完整官方资格考试。',
    assessment_kind='flight',
    phases=[dict(phase_id=key, name=name, single_frame=False, required_duration_s=None,
                 minimum_frame_count=2) for key, name in [
        ('approach', '进近'), ('approach_deceleration', '进近减速'), ('arrival_hover', '到点建立悬停')]],
    checkpoints=[
        cp(1, '进近航迹保持', '进近及进近减速环节逐帧检查约定直线航迹的横向位置；不以机头航向代替地面航迹。',
           ['approach_lateral_position_m'], [source('CP.V.D.S5', '官方要求整个进近保持合适地面航迹并修正侧风。采用约定横向坐标与固定中心线比较属于直线场景适配；不覆盖曲线进近。')]),
        cp(2, '稳定进近与减速', '空速、高度、垂直速度分别对照机型及场景参考剖面；按环节首帧相对时间取目标。只插值参考节点，不插值观测或外推。',
           ['approach_airspeed_mps', 'approach_height_m', 'approach_vertical_speed_mps'], [source('CP.V.D.S3/S6', '官方要求适当操纵、构型及稳定进近。选用三个可观察量、时间参考剖面和D/A容差是项目适配，需机型及专家校准；不能由其单独证明全部稳定进近要求。')]),
        cp(3, '到点建立悬停', '仅在 arrival_hover 环节逐帧检查目标位置、近零地速及指定航向；至少两帧仅为最低数据要求，不代表官方规定时长，不推断帧间状态。',
           ['arrival_x_m', 'arrival_y_m', 'arrival_height_m', 'arrival_vx_mps', 'arrival_vy_mps', 'arrival_vz_mps', 'arrival_heading_deg'], [
               source('CP.V.D.S7', '官方要求到达指定点上方并建立稳定悬停。S7的±2 feet不直接解释为X/Y/Z各自容差；三轴分解、近零地速阈值和逐帧汇总由项目定义。'),
               dict(source('CP.IV.A.S8', '航向保持借鉴垂直起降及悬停控制内容；此为补充依据，不声称CP.V.D.S7规定相同航向容差。', '印刷18页／PDF23'), url='https://www.faa.gov/training_testing/testing/acs/commercial_pl_acs_2.pdf#page=23')]),
        cp(4, '机型程序执行', '接收已认定的进近检查单完成、程序及构型正确两个布尔结果。二者都true为D，有false为U；缺失不能通过。到点各帧提供截至该时刻的本次程序结果。',
           ['approach_checklist_completed', 'approach_procedure_configuration_correct'], [source('CP.V.D.S1/S3', '官方支持适用检查单及正确机型程序/构型；将已认定结果用布尔值输入是项目适配。复飞决策等未纳入此布尔值，仍属覆盖限制。')]),
    ], skill_name='正常进近至悬停当次表现',
    skill_description='保留逐帧表现与可编辑CPT草稿；贝叶斯量化方法尚未确定，不输出未校准分数。')
index = catalog['items'].index(old)
catalog['items'][index] = item
first = next(i for i, m in enumerate(catalog['metrics']) if m['metric_id'] in old_keys)
catalog['metrics'] = [m for m in catalog['metrics'] if m['metric_id'] not in old_keys]
catalog['metrics'][first:first] = new_metrics
catalog['phase_sequence'] = ['preflight', 'approach', 'approach_deceleration', 'arrival_hover', 'acceleration', 'hold', 'hold_end', 'deceleration', 'stop']
catalog['description'] = '起飞前检查→正常进近至起点悬停→加速与保速→快速减速并停在终点。进近前已完成起飞；起飞过程不属于本场景当前评分。输入按item内精确时间frames排列，比较原始值与手工配置目标或参考剖面。'
path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

path = root / 'scn002_v3.json'
catalog = json.loads(path.read_text(encoding='utf-8'))
catalog['items'] = [i for i in catalog['items'] if i['item_id'] != 'SCENE-START']
used = {key for i in catalog['items'] for cp in i['checkpoints'] for key in cp['metric_ids']}
catalog['metrics'] = [m for m in catalog['metrics'] if m['metric_id'] in used]
catalog['phase_sequence'] = [key for key in catalog['phase_sequence'] if key != 'start']
catalog['description'] = '到达下方指定点后开始：下点停留5秒→上升→上点停留5秒→下降→下点停留5秒→再次上升→上点停留5秒。到达初始点作为训练前置流程，不单独设起点就位item。逐帧评估高度、平面定点、运动与航向、激光落点及升降控制；输入已标明环节。'
path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
