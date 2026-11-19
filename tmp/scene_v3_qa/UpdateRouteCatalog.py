import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
path = root / 'src/pilot_assessment/scene_assessment/scn001_v3.json'
catalog = json.loads(path.read_text(encoding='utf-8'))
item = next(x for x in catalog['items'] if x['item_id'] == 'A-S2-23')
item['description'] = '已起飞后，从别处沿指定三维路线进近起点，减速并建立悬停。当前评价航迹空间偏离及到点状态；环节由输入给出，不自动截取，不规定逐秒速度曲线，不等同完整官方资格考试。'
item['checkpoints'] = [p for p in item['checkpoints'] if p['checkpoint_id'] != 'A-S2-23-02']
point = item['checkpoints'][0]
point['name'] = '进近航迹控制'
point['description'] = '进近及进近减速环节，逐帧计算实际三维位置到手工指定路线的最短空间距离。高度偏离包含在内；D/A 通道半径手填，不要求按固定时间到达路线上的某点。'
point['metric_ids'] = ['approach_position_m']
point['sources'][0].update(page='印刷26页／PDF31', url='https://www.faa.gov/training_testing/testing/acs/commercial_pl_acs_2.pdf#page=31', note='官方要求整个进近保持合适地面航迹并修正侧风。三维折线、空间距离及D/A通道半径为项目适配；不单凭沿线飞行证明S6全部稳定进近要求。')
point['sources'].append({'document':'EASA Flight Examiners Manual CPL(H)', 'clause':'Section 2(l) Approaches (various profiles)', 'page':'11', 'url':'https://www.easa.europa.eu/en/downloads/138658/en#page=11', 'support':'直升机考核参照／项目适配', 'note':'采用适当进近剖面提供内容参照，不规定所有eVTOL统一的三维通道半径或逐秒飞行轨迹。'})
arrival = item['checkpoints'][1]
arrival['sources'][0].update(page='印刷26页／PDF31', url='https://www.faa.gov/training_testing/testing/acs/commercial_pl_acs_2.pdf#page=31')
old = {'approach_lateral_position_m','approach_airspeed_mps','approach_height_m','approach_vertical_speed_mps'}
new = {'metric_id':'approach_position_m','name':'进近三维位置与航迹距离','description':'每帧实际米制三维坐标{x_m,y_m,height_m}；系统计算到手工路线各有限线段的最短空间距离，高度包含在内。路线与输入须同坐标系、同高度基准；不拟合路线，不推断前进方向或速度。','unit':'m','value_type':'object','rule':'interval','parameter_kind':'error','input_kind':'frame','comparison':'route_3d','shared':False,'phase_ids':['approach','approach_deceleration'],'default_expected':0}
metrics=[]
for metric in catalog['metrics']:
    if metric['metric_id'] == 'approach_lateral_position_m':
        metrics.append(new)
    elif metric['metric_id'] not in old:
        metrics.append(metric)
catalog['metrics']=metrics
path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
